"""Derived state: schedule maths, CR health, and alert computation.

Nothing here touches a cluster or the database. It is pure functions over observed values so
the tricky parts — cron intervals and the sticky ReconcileError condition — can be tested
directly (PLAN §11, §2.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

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

    def as_dict(self) -> dict:
        return {
            "cluster": self.cluster,
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "severity": self.severity,
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
) -> list[Alert]:
    """Compute the PLAN §8 conditions the first slice has data for.

    Excluded: dangling bindings (needs RBAC outside the first slice, PLAN §14) and the group
    count cliff (needs a tuned floor as well as a ratio, PLAN §8).
    """
    alerts: list[Alert] = []
    by_provider: dict[str, list[dict]] = {}

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
            # An unattributed group is reported once, as unattributed. It is not also
            # "empty": EMPTY means a group the operator syncs whose members vanished
            # (PLAN §7), and a hand-made group with no members was never synced at all.
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
