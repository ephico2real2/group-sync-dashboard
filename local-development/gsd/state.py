"""Derived state: schedule maths, CR health, and alert computation.

Nothing here touches a cluster or the database. It is pure functions over observed values so
the tricky parts — cron intervals and the sticky ReconcileError condition — can be tested
directly (PLAN §11, §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass
import fnmatch
from datetime import UTC, date, datetime, timedelta

from croniter import CroniterBadCronError, croniter

# PLAN §11: "next_expected needs a real cron parser, not arithmetic on the interval."
# `0 * * * *` and `*/30 * * * *` both look hourly if you only measure gaps from the last
# event; they differ only at :30.

OK = "ok"
LATE = "late"
OVERDUE = "overdue"
UNKNOWN = "unknown"


def parse_time(value: str | None) -> datetime | None:
    """Parse an RFC3339 timestamp from the Kubernetes API into an aware UTC datetime."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def is_valid_schedule(schedule: str | None) -> bool:
    return bool(schedule) and croniter.is_valid(schedule)


def schedule_interval(schedule: str, at: datetime) -> timedelta | None:
    """The gap between the two most recent scheduled fires at or before ``at``.

    Measured locally rather than assumed constant: a cron need not be periodic
    (``0 9,17 * * *`` alternates 8h and 16h), and using the gap around the moment in
    question keeps the "1 interval" of PLAN §11 meaningful for those.
    """
    if not is_valid_schedule(schedule):
        return None
    try:
        it = croniter(schedule, at)
        previous = it.get_prev(datetime)
        before_that = it.get_prev(datetime)
    except (CroniterBadCronError, ValueError):
        return None
    interval = previous - before_that
    return interval if interval > timedelta(0) else None


def next_expected(schedule: str, now: datetime) -> datetime | None:
    """The next scheduled fire strictly after ``now``.

    This is the "when should it next run" a reader wants on the detail page. It is
    intentionally computed from ``now`` and not from the last sync: anchoring on a stale
    last-sync would return a time in the past for exactly the CRs that are already broken,
    which reads as a bug rather than as information.
    """
    if not is_valid_schedule(schedule):
        return None
    try:
        return croniter(schedule, now).get_next(datetime)
    except (CroniterBadCronError, ValueError):
        return None


def compute_state(
    last_sync: datetime | None,
    schedule: str | None,
    now: datetime,
    grace: timedelta,
    reachable: bool = True,
) -> str:
    """Classify a GroupSync per PLAN §11, with a grace allowance.

    The plan's thresholds are ``ok <= 1 interval``, ``late > 1``, ``overdue > 2``. Applied
    literally they flap: a sync lands 3-14s after its cron minute (measured on CRC), and our
    poll adds up to one poll interval before we see it. So a perfectly healthy CR's observed
    age exceeds one interval for a short window at the end of every single cycle, and the
    card would blink `late` on each pass. ``grace`` absorbs scheduler latency plus poll lag;
    it shifts the boundary, it does not widen the classes.
    """
    if not reachable:
        return UNKNOWN
    if last_sync is None:
        # Never observed a sync — distinct from "synced long ago" and not an alert on its
        # own, since a freshly created CR legitimately looks like this until its first fire.
        return UNKNOWN

    interval = schedule_interval(schedule, now) if schedule else None
    if interval is None:
        return UNKNOWN

    age = now - last_sync
    if age <= interval + grace:
        return OK
    if age <= (2 * interval) + grace:
        return LATE
    return OVERDUE


def reconcile_error_is_current(
    error_at: datetime | None, success_at: datetime | None
) -> bool:
    """Is the CR's ReconcileError condition describing the *latest* cycle? (PLAN §2.1)

    The operator does not clear ReconcileError on a later success — both conditions sit at
    ``status: True`` indefinitely — so the condition's own status says nothing about current
    health. Only the ordering of the transition times does.
    """
    if error_at is None:
        return False
    if success_at is None:
        return True
    return error_at > success_at


@dataclass(frozen=True)
class Alert:
    """One computed alert (PLAN §8)."""

    cluster: str
    kind: str
    subject: str
    detail: str
    severity: str = "warning"
    # A silenced alert is still an alert: reported with the reason, never dropped. Only the
    # group-count cliff sets these today; every other kind carries the defaults on the wire so
    # the shape is uniform.
    silenced: bool = False
    silenced_by: str | None = None

    def as_dict(self) -> dict:
        return {
            "cluster": self.cluster,
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "severity": self.severity,
            "silenced": self.silenced,
            "silenced_by": self.silenced_by,
        }


def stale_group_threshold(interval: timedelta | None, write_window: timedelta) -> timedelta:
    """How far a group's own sync-time may lag its CR's before it counts as stale.

    A sync stamps its groups over several seconds and stamps the CR last (PLAN §3.1), so the
    two timestamps are legitimately unequal on a completely healthy sync. The threshold must
    clear that write window; below it, every large CR would report its earliest-written
    groups as stale on every cycle.
    """
    if interval is None:
        return write_window
    return max(interval, write_window)


@dataclass(frozen=True)
class CliffPolicy:
    """config.alerts.groupCountCliff, as the pure layer sees it. None means the module is off."""

    min_members: int = 10
    drop_ratio: float = 0.5
    window_hours: float = 24.0
    silence: tuple[str, ...] = ()

    def since(self, now: datetime) -> str:
        """The window's start in timeutil's fixed-width UTC format — the store compares
        observed_at lexicographically, so the format must be the poller's exactly."""
        return (now - timedelta(hours=self.window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def cliff_policy(settings) -> CliffPolicy | None:
    """Settings -> CliffPolicy, or None when the module is off or no settings were given.

    Duck-typed on purpose: this module imports nothing from config.py (it is the pure
    layer), and the metrics collector is legitimately built without settings in tests.
    """
    if settings is None or not getattr(settings, "group_count_cliff_enabled", False):
        return None
    return CliffPolicy(
        min_members=int(settings.group_count_cliff_min_members),
        drop_ratio=float(settings.group_count_cliff_drop_ratio),
        window_hours=float(settings.group_count_cliff_window_hours),
        silence=tuple(settings.group_count_cliff_silence),
    )


def cliff_silence(
    annotation: str | None, silence: tuple[str, ...], group: str, now: datetime
) -> str | None:
    """Why a cliff on ``group`` is silenced: "annotation", "values", or None.

    The annotation (kube.CLIFF_SILENCE_ANNOTATION) is "true" or "until=YYYY-MM-DD"; the
    date is inclusive and read as a UTC calendar date, and an expired or unparseable value
    un-silences rather than silencing — the direction that reports rather than hides.
    Values patterns are fnmatch globs, case-sensitive like group names.
    """
    if annotation is not None:
        word = annotation.strip().lower()
        if word == "true":
            return "annotation"
        if word.startswith("until="):
            try:
                until = date.fromisoformat(word[len("until="):].strip())
            except ValueError:
                until = None
            if until is not None and now.date() <= until:
                return "annotation"
    for pattern in silence:
        if fnmatch.fnmatchcase(group, pattern):
            return "values"
    return None


def compute_alerts(
    cluster: str,
    groupsyncs: list[dict],
    groups: list[dict],
    now: datetime,
    grace: timedelta,
    write_window: timedelta = timedelta(minutes=2),
    no_schedule_stale_after: timedelta = timedelta(hours=24),
    operator_configs: list[dict] | None = None,
    user_bindings: list[dict] | None = None,
    groupsync_present: bool | None = None,
    count_changes: dict[str, dict] | None = None,
    cliff: CliffPolicy | None = None,
) -> list[Alert]:
    """Compute the PLAN §8 conditions the first slice has data for.

    Excluded: dangling bindings (needs RBAC outside the first slice, PLAN §14). The group
    count cliff, once excluded for want of a floor, is computed when ``cliff`` is given:
    ``count_changes`` is store.group_count_changes for the policy's window
    (docs/specs/SPEC_B4_group_count_cliff.md).
    """
    alerts: list[Alert] = []
    by_provider: dict[str, list[dict]] = {}

    # THE CRD IS NOT INSTALLED. Raised first because it explains every other finding on the
    # page: with no CR to attribute anything to, every group is `unattributed` and every
    # provider-based check has nothing to work with.
    #
    # Explicitly `is False`, never falsy. None means "not observed yet" — a cluster that has
    # not polled since the migration added the presence table — and treating that as absent
    # would fire this for every existing cluster the moment it upgrades.
    if groupsync_present is False:
        alerts.append(
            Alert(
                cluster=cluster,
                kind="groupsync_crd_absent",
                subject="GroupSync CRD",
                detail="the group-sync-operator is not installed on this cluster, so no group "
                       "is managed by a CR and every group reports as unattributed. Groups "
                       "themselves are still read and shown.",
            )
        )

    for group in groups:
        provider = group.get("sync_provider")
        if provider is None:
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="unattributed",
                    subject=group["name"],
                    detail="no sync-provider label — not managed by any GroupSync CR",
                )
            )
            # An unattributed group raises ONE alert, as unattributed — deliberately NOT also
            # `empty_group`. This differs from the `empty` FILTER on purpose, which does return
            # it (store.py), and the difference is not an oversight:
            #
            #   the filter answers "which groups grant nobody?", so provenance is irrelevant
            #   the alert carries a REMEDY — "check the LDAP-side member DNs resolve" — and
            #   there is no LDAP side for a group somebody created by hand
            #
            # So the alert stream stays one row per group with the advice that fits it, while
            # the Groups tab lists the group under both filters. Documented in API.md.
            continue

        by_provider.setdefault(provider, []).append(group)

        if group.get("member_count") == 0:
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="empty_group",
                    subject=group["name"],
                    detail="synced with zero members — check the LDAP-side member DNs resolve",
                )
            )

    # THE GROUP-COUNT CLIFF. before = the count at the window's start, reconstructed exactly
    # from the membership events inside the window (state is replaced each poll; the events
    # are the history). Evaluated only for groups that still exist — a deleted group is the
    # dangling-binding finding's job — and only above the floor: below ten members, half is
    # one or two people, which is churn, not a cliff. Silenced cliffs are STILL reported,
    # under their own kind, so a reader sees "known" rather than "nothing".
    if cliff is not None and count_changes:
        for group in groups:
            change = count_changes.get(group["name"])
            if not change:
                continue
            after = int(group.get("member_count") or 0)
            before = after + int(change.get("removed") or 0) - int(change.get("added") or 0)
            if before < cliff.min_members:
                continue
            drop = before - after
            if drop <= 0 or drop < cliff.drop_ratio * before:
                continue
            by = cliff_silence(group.get("cliff_silence"), cliff.silence, group["name"], now)
            detail = (
                f"members {before} -> {after} within the last {cliff.window_hours:g}h "
                f"({drop / before:.0%} drop; floor {cliff.min_members}, ratio "
                f"{cliff.drop_ratio:g}) — a directory-side change, or a sync that resolved "
                f"fewer member DNs; compare the group's LDAP entry with its CR's last sync"
            )
            if by == "annotation":
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff_silenced",
                        subject=group["name"],
                        detail=detail + "; silenced by the Group's silence annotation",
                        silenced=True,
                        silenced_by="annotation",
                    )
                )
            elif by == "values":
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff_silenced",
                        subject=group["name"],
                        detail=detail + "; silenced by config.alerts.groupCountCliff.silence",
                        silenced=True,
                        silenced_by="values",
                    )
                )
            else:
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff",
                        subject=group["name"],
                        detail=detail,
                    )
                )

    for cr in groupsyncs:
        name = cr["name"]
        last_sync = parse_time(cr.get("last_sync_at"))
        schedule = cr.get("schedule")
        interval = schedule_interval(schedule, now) if schedule else None

        # An unparseable or missing schedule is itself a defect: the operator cannot
        # schedule the CR at all. It also makes every interval-based check unusable, so
        # without this the CR falls into `unknown` and alerts on NOTHING — a sync that has
        # stopped for days reports total silence. Alert on the cause, then fall back to an
        # absolute staleness bound so the stoppage is still caught.
        if not is_valid_schedule(schedule):
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="invalid_schedule",
                    subject=name,
                    detail=(
                        f"schedule {schedule!r} is missing or not a valid cron expression — "
                        f"the operator cannot schedule this CR, and no interval-based "
                        f"staleness check can be applied to it"
                    ),
                    severity="critical",
                )
            )
            if last_sync is not None and (now - last_sync) > no_schedule_stale_after:
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="sync_stopped",
                        subject=name,
                        detail=(
                            f"last sync {_ago(now - last_sync)} ago and the schedule is "
                            f"unusable — this CR has stopped syncing"
                        ),
                        severity="critical",
                    )
                )

        state = compute_state(last_sync, schedule, now, grace)
        if state == OVERDUE:
            age = now - last_sync if last_sync else None
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="overdue",
                    subject=name,
                    detail=(
                        f"last sync {_ago(age)} ago, schedule {schedule!r} "
                        f"(> 2 intervals) — the schedule has stopped firing"
                    ),
                    severity="critical",
                )
            )

        if reconcile_error_is_current(
            parse_time(cr.get("error_at")), parse_time(cr.get("last_sync_at"))
        ):
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="reconcile_error",
                    subject=name,
                    detail=(cr.get("error_message") or "reconcile failed").strip()[:400],
                    severity="critical",
                )
            )

        # Stale groups are measured against the CR's own timestamp, not against `now`.
        # The CR is stamped after its groups (PLAN §3.1), so this comparison is unaffected
        # by how long ago the whole CR last ran and stays quiet during an in-flight sync.
        if last_sync is None:
            continue
        threshold = stale_group_threshold(interval, write_window)
        for group in (g for key in _provider_keys(cr) for g in by_provider.get(key, [])):
            group_synced = parse_time(group.get("group_synced_at"))
            if group_synced is None:
                continue
            lag = last_sync - group_synced
            if lag > threshold:
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="stale_group",
                        subject=group["name"],
                        detail=(
                            f"group last refreshed {_ago(lag)} before its CR {name!r} "
                            f"last synced — it is no longer being updated with the rest"
                        ),
                    )
                )

    # The policy operator's CRs — the source of the RoleBindings that give synced groups
    # their access. A currently-failing one means RBAC has silently stopped reconciling:
    # new namespaces get nothing, drift stops being corrected, and nothing else alerts.
    # Same sticky-condition trap as GroupSync (ReconcileError stays True forever), so the
    # same current-vs-stale resolution applies: only the transition-time ordering decides.
    for config in operator_configs or []:
        if reconcile_error_is_current(
            parse_time(config.get("error_at")), parse_time(config.get("success_at"))
        ):
            alerts.append(
                Alert(
                    cluster=cluster,
                    kind="config_reconcile_error",
                    subject=f'{config["kind"]}/{config["name"]}',
                    detail=(config.get("error_message") or "reconcile failed").strip()[:400],
                    severity="critical",
                )
            )

    # Direct-user grants. ONE alert with the total, not one per binding: 36 separate
    # alerts would drown every other finding on the page, and the actionable unit is the
    # migration effort, not each row. The detail lives on the RBAC policy page.
    people = [u for u in (user_bindings or []) if not u.get("is_platform")]
    if people:
        namespaces = {u.get("binding_namespace") or "(cluster-scoped)" for u in people}
        elevated = [u for u in people if u.get("role_name") in ("cluster-admin", "admin")]
        alerts.append(
            Alert(
                cluster=cluster,
                kind="direct_user_binding",
                subject=f"{len(people)} direct user grant{'' if len(people) == 1 else 's'}",
                detail=(
                    f"across {len(namespaces)} namespace"
                    f"{'' if len(namespaces) == 1 else 's'}"
                    f"{f', {len(elevated)} granting admin or cluster-admin' if elevated else ''}"
                    " — access bound to a person rather than an enterprise-managed group. "
                    "These survive offboarding: removing someone from an LDAP group revokes "
                    "their access everywhere, a direct binding keeps granting to a name "
                    "nobody reviews."
                ),
                severity="warning",
            )
        )

    return alerts


def _provider_keys(cr: dict) -> list[str]:
    """Every sync-provider label value a CR's groups carry (PLAN §3).

    The operator writes ``<groupsync-name>_<provider>``. The provider suffix is not on the
    CR status, so the poller records the label values it actually saw and the CR carries
    every one matching its name; see poller.provider_keys_for. A CR with several providers
    has several, and missing the later ones means their groups are never staleness-checked.

    Falls back to the bare CR name for a CR the poller has attributed nothing to, which is
    what a CR that has produced no groups yet looks like.
    """
    return cr.get("provider_keys") or [cr["name"]]


def _ago(delta: timedelta | None) -> str:
    if delta is None:
        return "unknown"
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d{(seconds % 86400) // 3600:02d}h"
