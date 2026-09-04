"""Prometheus metrics, collected from the store at scrape time.

A custom collector rather than module-level counters that the poller increments: the store
is already the source of truth, so mirroring it into metric objects would create a second
copy that can drift from the first. Scraping reads what the API reads.

CARDINALITY IS DELIBERATELY BOUNDED. Series are emitted per cluster and per GroupSync CR
only — never per group and never per user. A label per group would be 62 series on this
cluster and tens of thousands on a real directory, which is how a dashboard's own metrics
take down the Prometheus scraping it. Group and user names are also membership data; a
metrics endpoint is typically less guarded than the API, and names in labels would leak
them into any federated store.

The single most useful series here is `gsd_groupsync_last_sync_timestamp_seconds`. With it,
staleness alerting belongs in Prometheus, expressed against real time:

    (time() - gsd_groupsync_last_sync_timestamp_seconds) > 7200
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from prometheus_client import CollectorRegistry
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from . import __version__, state as st
from .storage import StorageBackend

log = logging.getLogger(__name__)

STATES = (st.OK, st.LATE, st.OVERDUE, st.UNKNOWN)
FINDINGS = ("ok", "dangling", "unresolved", "built_in")

# The full kind vocabulary gsd_alerts_total can emit, kept beside the code that emits it:
# compute_alerts' kinds (state.py literals), the poll outcomes a failing cluster reports as
# its one critical alert (kube.py's AUTH_FAILED/FORBIDDEN/UNREACHABLE), and
# dangling_binding, the per-row critical /api/alerts adds. tests/test_metrics.py holds
# every PrometheusRule kind= matcher to this tuple AND holds this tuple to both upstream
# sources — the guard the dangling_binding gap showed was missing: a family can be declared
# while a label value on it is unemittable, and a rule on that value never fires.
ALERT_KINDS = (
    "groupsync_crd_absent", "unattributed", "empty_group", "invalid_schedule",
    "sync_stopped", "overdue", "reconcile_error", "stale_group",
    "config_reconcile_error", "direct_user_binding",
    "dangling_binding",
    # The group-count cliff, and the same cliff an administrator silenced (annotation or
    # values). Two KIND values rather than a `silenced` label, so the label set of
    # gsd_alerts_total — and every rule written against it — is unchanged, and the shipped
    # rule matches the unsilenced kind alone. Kind only: the group's name never reaches
    # /metrics (module docstring).
    "group_count_cliff", "group_count_cliff_silenced",
    "auth_failed", "forbidden", "unreachable",
)

# Vocabularies for the process-event families. Fixed tuples, like STATES and FINDINGS:
# every combination is pre-seeded to 0 so increase() has a baseline before the first event,
# and a typo'd label value fails loudly in tests instead of minting a new series.
TIER_THRESHOLDS = ("admin", "usage")
TIER_CHECK_OUTCOMES = ("allowed", "denied", "unreachable", "auth_failed", "forbidden", "error")
TIERS = ("all", "self")
RETENTION_TABLES = ("login_event", "dashboard_user_activity", "membership_event", "sync_event")


class RuntimeSignals:
    """Process-local counters for events that exist in no table.

    The module docstring's rule — read the store, never mirror it — is about STATE, which
    has a first copy to drift from. These are EVENTS: a tier check that failed, rows a
    prune deleted, a backup that did not happen. No store row records them, so the process
    counter IS the single copy. Per replica by construction: sum() across pods is the
    correct aggregation, unlike the store-backed gauges (see the gsd_leader comment), and
    a restart resets them the way Prometheus counters are allowed to reset.

    Explicit note_* methods rather than a generic inc(name, labels): the call sites are
    then greppable, typo-proof, and each one documents which vocabulary it draws from.
    Nothing here raises past the lock — a metrics bug must not become an application bug.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tier_checks: dict[tuple[str, str], int] = {}
        self._decisions: dict[tuple[str, str], int] = {}
        self._admin_refusals = 0
        self._retention: dict[str, int] = {}
        self._backup_failures = 0
        self._poll_seconds: dict[str, float] = {}

    def note_tier_check(self, threshold: str, outcome: str) -> None:
        with self._lock:
            key = (threshold, outcome)
            self._tier_checks[key] = self._tier_checks.get(key, 0) + 1

    def note_decision(self, threshold: str, tier: str) -> None:
        with self._lock:
            key = (threshold, tier)
            self._decisions[key] = self._decisions.get(key, 0) + 1

    def note_admin_refusal(self) -> None:
        with self._lock:
            self._admin_refusals += 1

    def note_retention(self, table: str, rows: int) -> None:
        if rows <= 0:
            return
        with self._lock:
            self._retention[table] = self._retention.get(table, 0) + rows

    def note_backup_failure(self) -> None:
        with self._lock:
            self._backup_failures += 1

    def note_poll_duration(self, cluster: str, seconds: float) -> None:
        with self._lock:
            self._poll_seconds[cluster] = seconds

    def snapshot(self) -> dict:
        """One consistent copy for the collector — a scrape never reads a half-updated dict."""
        with self._lock:
            return {
                "tier_checks": dict(self._tier_checks),
                "decisions": dict(self._decisions),
                "admin_refusals": self._admin_refusals,
                "retention": dict(self._retention),
                "backup_failures": self._backup_failures,
                "poll_seconds": dict(self._poll_seconds),
            }


def _epoch(value: str | None) -> float | None:
    parsed = st.parse_time(value)
    return parsed.timestamp() if parsed else None


class DashboardCollector:
    """Reads the store on each scrape and yields the current picture."""

    def __init__(self, store: StorageBackend, grace: timedelta, elector=None,
                 signals: RuntimeSignals | None = None, settings=None):
        self.store = store
        self.grace = grace
        self.elector = elector
        # The process-event seam (RuntimeSignals above) and the Settings object, both
        # optional: a collector built without them still DECLARES the new families, empty —
        # the alert-rule tests resolve rule references against HELP lines on a bare store —
        # but claims no measurements it never took.
        self.signals = signals
        self.settings = settings

    def collect(self):
        """Materialise the whole exposition inside ONE snapshot, then yield it.

        collect() is a GENERATOR, and prometheus_client drives it lazily while writing the
        response. Wrapping the generator itself in a read snapshot would therefore hold a
        WAL read-mark for the entire duration of the HTTP response rather than the duration
        of the queries — and a held read-mark blocks wal_checkpoint(TRUNCATE) from
        reclaiming anything, so a slow scrape would stall the poller's checkpoint and let
        the WAL grow. That is the precise failure this arrangement avoids: gather under the
        snapshot, release it, then yield.

        Consistency matters here for the same reason as the API: a scrape makes five store
        calls per cluster, and a poll committing between them exports a group count from
        one generation beside a CR state from the next.
        """
        with self.store.read_snapshot():
            families = list(self._gather())
        yield from families

    def _gather(self):  # noqa: C901 - a flat list of metric definitions
        build = GaugeMetricFamily(
            "gsd_build_info",
            "Always 1; the running build is carried in the labels.",
            labels=["version", "commit", "branch"],
        )
        build.add_metric(
            [
                os.environ.get("GSD_VERSION", __version__),
                os.environ.get("GSD_GIT_COMMIT", "unknown"),
                os.environ.get("GSD_GIT_BRANCH", "unknown"),
            ],
            1,
        )
        yield build

        # Every replica exposes the same gauge names, so Prometheus sees N series per
        # metric distinguished by `pod`. That is normal and not a clash, but it makes
        # `sum()` wrong — the counts are cluster facts, not per-pod facts, so aggregate
        # with max() or filter on gsd_leader. This series is what makes that filtering
        # possible, and also answers "which pod is actually writing?".
        # No labels: leadership is per-process — one Lease, one flag — and this used to
        # carry a `cluster` label that was always the empty string, asserting a per-cluster
        # fact that does not exist. Dropping it changes no selector: in PromQL an empty
        # label value is indistinguishable from an absent label.
        leader = GaugeMetricFamily(
            "gsd_leader",
            "1 on the replica holding the poll lease, 0 on standbys. Use it to pick one "
            "replica's series: gsd_groups_total and on(pod) gsd_leader == 1",
            labels=[],
        )
        if self.elector is not None:
            leader.add_metric([], 1 if self.elector.is_leader else 0)
        else:
            leader.add_metric([], 1)
        yield leader

        # One call, three metrics. The collector asks the backend how it is and exports
        # what comes back; it does not read SQLite attributes off the store, which is what
        # used to make this file engine-aware.
        #
        # The metric NAMES still say sqlite, deliberately. They are accurate today and they
        # appear in shipped alert rules, so renaming them is an operator-visible breaking
        # change that belongs with an actual engine change — at which point it is confined
        # to these few lines. Guarded because a usage statistic must never be why a scrape
        # 500s and takes every other metric with it.
        try:
            health = self.store.health()
        except Exception:  # noqa: BLE001
            # OMITTED, never zeroed. An earlier version of this guard fell back to an empty
            # dict, which produced `gsd_sqlite_wal_enabled 0` on a successful scrape — and
            # that value means "the filesystem refused WAL, readers now block on every
            # write", so GroupSyncDashboardWalDisabled would fire while nothing was wrong.
            # Reporting a failure to measure as a measurement of failure is the worst
            # available answer. Omitting leaves Prometheus holding the last good value,
            # which is what the pre-refactor code did by letting the scrape fail outright.
            log.exception("metrics: storage health unavailable; omitting those three series")
            health = None

        sqlite = (health or {}).get("sqlite") or {}
        if health is not None:
            # The WAL is the one thing here that can fill the volume while every other
            # signal stays green: checkpointing is best-effort and yields to open readers,
            # so a steady read load can starve it indefinitely. The database file stops
            # growing, the API keeps answering, and the pod dies on a full disk with nothing
            # having warned.
            #
            # Emitted only for an engine that reports them. A backend without a WAL — any
            # server-based engine — returns no such keys, and inventing a 0 for
            # wal_enabled would fire the same false alarm as the failure case above.
            if "wal_bytes" in sqlite:
                wal = GaugeMetricFamily(
                    "gsd_sqlite_wal_bytes",
                    "Size of the SQLite write-ahead log. Sustained growth means checkpoints "
                    "are being starved by open readers; compare against the PVC size.",
                    labels=[],
                )
                wal.add_metric([], int(sqlite["wal_bytes"]))
                yield wal

            if "checkpoint_busy_total" in sqlite:
                ckpt = CounterMetricFamily(
                    "gsd_sqlite_checkpoint_busy_total",
                    "Checkpoints that could not complete because a reader held an older "
                    "snapshot. Occasional is normal; monotonic increase alongside rising "
                    "WAL size is the starvation case.",
                    labels=[],
                )
                ckpt.add_metric([], int(sqlite["checkpoint_busy_total"]))
                yield ckpt

            # 1 only when WAL actually engaged. It is requested at startup but the
            # filesystem can refuse it, and in rollback mode readers block on every write —
            # a latency cliff with no other symptom.
            if "wal_enabled" in sqlite:
                journal = GaugeMetricFamily(
                    "gsd_sqlite_wal_enabled",
                    "1 if the database is in WAL mode. 0 means the filesystem refused it "
                    "and readers now block on writes.",
                    labels=[],
                )
                journal.add_metric([], 1 if sqlite["wal_enabled"] else 0)
                yield journal

        # gsd_dashboard_active_users USED TO BE EXPOSED HERE AND WAS REMOVED.
        # /metrics is deliberately unauthenticated so Prometheus can scrape it without
        # credentials (oauthProxy.skipAuthRegex), and a distinct-user-count is still
        # personnel information: it reports how many people worked on a given day to
        # anyone who can reach the Service. Unlabelled is not anonymous enough to publish
        # without authentication. The per-user detail remains in the database, behind
        # /api/dashboard/activity, which is authenticated and self-scoped.

        up = GaugeMetricFamily(
            "gsd_cluster_up",
            "1 if the last poll of this cluster succeeded, 0 otherwise — including a "
            "cluster never yet polled, which also has no last_poll series.",
            labels=["cluster"],
        )
        last_poll = GaugeMetricFamily(
            "gsd_cluster_last_poll_timestamp_seconds",
            "Unix time of the last poll attempt. Alert on this going stale: it catches a "
            "dead poller thread, which the health endpoints cannot.",
            labels=["cluster"],
        )
        groups = GaugeMetricFamily(
            "gsd_groups_total", "Groups observed on the cluster.", labels=["cluster"]
        )
        empty = GaugeMetricFamily(
            "gsd_groups_empty_total",
            "Operator-managed groups with zero members.",
            labels=["cluster"],
        )
        unattributed = GaugeMetricFamily(
            "gsd_groups_unattributed_total",
            "Groups with no sync-provider label, so managed by no GroupSync CR.",
            labels=["cluster"],
        )
        bindings = GaugeMetricFamily(
            "gsd_bindings_total",
            "Group-subject RoleBindings/ClusterRoleBindings by finding. "
            "finding=dangling means the binding grants nobody.",
            labels=["cluster", "finding"],
        )
        cr_last_sync = GaugeMetricFamily(
            "gsd_groupsync_last_sync_timestamp_seconds",
            "Unix time of the CR's last successful sync, straight from "
            ".status.lastSyncSuccessTime. Prometheus can express staleness against this "
            "directly, which is more honest than exporting a precomputed boolean.",
            labels=["cluster", "groupsync", "namespace"],
        )
        cr_state = GaugeMetricFamily(
            "gsd_groupsync_state",
            "1 for the CR's current state, 0 for the others.",
            labels=["cluster", "groupsync", "namespace", "state"],
        )
        cr_groups = GaugeMetricFamily(
            "gsd_groupsync_groups_total",
            "Groups currently attributed to this CR.",
            labels=["cluster", "groupsync", "namespace"],
        )
        cr_error = GaugeMetricFamily(
            "gsd_groupsync_reconcile_error_current",
            "1 when the CR's ReconcileError is NEWER than its last success. The condition "
            "itself stays True forever, so its raw status is not a health signal.",
            labels=["cluster", "groupsync", "namespace"],
        )
        alerts = GaugeMetricFamily(
            "gsd_alerts_total",
            "Alerts as /api/alerts serves them at the wide tier, by kind and severity. A "
            "failing cluster reports its poll outcome as one critical alert and none of "
            "the computed kinds (those would come from stale cache); dangling bindings "
            "count under kind=dangling_binding; a group-count cliff an administrator "
            "silenced counts under kind=group_count_cliff_silenced, never under "
            "group_count_cliff.",
            labels=["cluster", "kind", "severity"],
        )
        capture_last_read = GaugeMetricFamily(
            "gsd_login_capture_last_read_timestamp_seconds",
            "Unix time of the last successful oauth-log read for this cluster; advanced "
            "only by a read that reached at least one pod. Alert on staleness against "
            "pollIntervalSeconds — capture rides the poll thread. Absent until the first "
            "successful read: absence means never, not zero.",
            labels=["cluster"],
        )

        now = datetime.now(UTC)
        # The cluster listing itself is guarded, not just the per-cluster work. If the
        # store is unusable, the scrape must still return build info and empty families
        # rather than raising: an exposition that errors is indistinguishable from the
        # target being down, so the one signal that would explain the outage is the one
        # signal you lose.
        try:
            rows = self.store.clusters()
        except Exception:  # noqa: BLE001
            log.exception("metrics: cluster listing failed; exposing build info only")
            rows = []

        for row in rows:
            cluster = row["id"]
            try:
                up.add_metric([cluster], 1 if row["status"] == "ok" else 0)
                poll_ts = _epoch(row["last_poll"])
                if poll_ts is not None:
                    last_poll.add_metric([cluster], poll_ts)

                # Capture liveness rides the same snapshot as the counts it explains. None
                # means capture has never succeeded here, and that is OMITTED — an epoch-0
                # sample would fire the staleness alert on a cluster where capture is
                # simply not configured.
                status = self.store.login_capture_status(cluster)
                read_ts = _epoch((status or {}).get("last_read_at"))
                if read_ts is not None:
                    capture_last_read.add_metric([cluster], read_ts)

                counts = self.store.group_counts(cluster)
                groups.add_metric([cluster], counts["total"])
                empty.add_metric([cluster], counts["empty"])
                unattributed.add_metric([cluster], counts["unattributed"])

                by_finding = dict.fromkeys(FINDINGS, 0)
                for binding in self.store.all_bindings(cluster):
                    by_finding[binding["finding"]] = by_finding.get(binding["finding"], 0) + 1
                for finding, count in by_finding.items():
                    bindings.add_metric([cluster, finding], count)

                by_kind: dict[tuple[str, str], int] = {}
                # Read once and keep it: this list is needed again for compute_alerts below,
                # and a second call is a second query per cluster on every scrape for rows
                # that cannot have changed in between — the snapshot is already fixed.
                cluster_groupsyncs = self.store.groupsyncs(cluster)
                for cr in cluster_groupsyncs:
                    name, namespace = cr["name"], cr["namespace"]
                    labels = [cluster, name, namespace]

                    sync_ts = _epoch(cr["last_sync_at"])
                    if sync_ts is not None:
                        cr_last_sync.add_metric(labels, sync_ts)
                    cr_groups.add_metric(labels, cr["group_count"] or 0)

                    current = st.compute_state(
                        st.parse_time(cr["last_sync_at"]), cr["schedule"], now, self.grace
                    )
                    # Every state emitted, one of them 1: a series that disappears when the
                    # state changes leaves stale-looking data in the graph and breaks
                    # `by (state)` aggregation.
                    for value in STATES:
                        cr_state.add_metric([*labels, value], 1 if value == current else 0)

                    cr_error.add_metric(
                        labels,
                        1
                        if st.reconcile_error_is_current(
                            st.parse_time(cr.get("error_at")),
                            st.parse_time(cr.get("last_sync_at")),
                        )
                        else 0,
                    )

                # Kept in step with the /api/alerts call site: a kind that exists in one
                # and not the other makes gsd_alerts_total disagree with the UI, so a
                # Prometheus rule can never be written against it. That promise was broken
                # three ways and is now enforced (tests/test_metrics.py, both parity tests
                # and the ALERT_KINDS vocabulary check): a failing cluster contributes ONE
                # critical alert carrying its poll outcome as the kind and NONE of the
                # computed kinds — those would be recomputed from cache that stopped
                # updating when the poll did — and a healthy cluster reports one
                # dangling_binding per dangling row, the count by_finding already holds
                # from this same snapshot.
                if row["status"] and row["status"] != "ok":
                    by_kind[(row["status"], "critical")] = 1
                else:
                    # Same policy the API derives (gsd/api.py#list_alerts): None when the
                    # module is off OR when this collector was built without settings.
                    policy = st.cliff_policy(self.settings)
                    for alert in st.compute_alerts(
                        cluster=cluster,
                        groupsyncs=cluster_groupsyncs,
                        operator_configs=self.store.operator_configs(cluster)["configs"],
                        user_bindings=self.store.direct_user_bindings(cluster),
                        groups=self.store.groups(cluster, "all"),
                        groupsync_present=self.store.groupsync_present(cluster),
                        now=now,
                        grace=self.grace,
                        count_changes=(
                            self.store.group_count_changes(cluster, policy.since(now))
                            if policy else None
                        ),
                        cliff=policy,
                    ):
                        key = (alert.kind, alert.severity)
                        by_kind[key] = by_kind.get(key, 0) + 1
                    if by_finding.get("dangling"):
                        by_kind[("dangling_binding", "critical")] = by_finding["dangling"]
                for (kind, severity), count in by_kind.items():
                    alerts.add_metric([cluster, kind, severity], count)
            except Exception:  # noqa: BLE001
                # One bad cluster must not fail the whole scrape: a partial exposition is
                # far more useful than none, and a scrape that 500s looks identical to the
                # target being down.
                log.exception("metrics collection failed for cluster %s", cluster)

        yield from (
            up, last_poll, groups, empty, unattributed, bindings,
            cr_last_sync, cr_state, cr_groups, cr_error, alerts, capture_last_read,
        )
        yield from self._event_families()

    def _event_families(self):
        """Families whose source is the process or the filesystem, not the store.

        Always DECLARED (HELP/TYPE), even when there is nothing to say: the alert-rule
        tests resolve every PrometheusRule reference against a HELP line on a bare store,
        and a family that only exists after its first event would make a rule on it
        unverifiable. Samples are added only when the corresponding source is wired, so a
        bare DashboardCollector(store, grace) claims no measurements it never took. When
        wired, every enum combination is pre-seeded to 0 — the FINDINGS discipline — so
        increase() has a baseline before the first failure, which is the failure that
        matters.
        """
        snap = self.signals.snapshot() if self.signals is not None else None

        checks = CounterMetricFamily(
            "gsd_visibility_tier_checks_total",
            "Fresh SubjectAccessReview-backed tier resolutions, by threshold and outcome. "
            "allowed/denied are verdicts; every other outcome is a check that FAILED and "
            "served the self view fail-closed — a sustained nonzero rate means readers "
            "are being silently narrowed. Cache hits are not re-decided and single-flight "
            "followers ride the leader's check, so this counts decisions, not requests. "
            "Per replica: aggregate with sum().",
            labels=["threshold", "outcome"],
        )
        decisions = CounterMetricFamily(
            "gsd_visibility_decisions_total",
            "Scope decisions actually served to requests while view restrictions are on, "
            "by threshold and tier — cached, fresh, and no-identity decisions alike. The "
            "all:self mix shifting toward self while tier_checks reports failures is the "
            "everyone-silently-narrowed signature. Per replica: aggregate with sum().",
            labels=["threshold", "tier"],
        )
        refusals = CounterMetricFamily(
            "gsd_visibility_admin_refusals_total",
            "Requests refused (403) by the administrator-tier gate on the cluster-scoped "
            "views (/bindings/findings, /operator-configs). Occasional is a non-admin "
            "clicking a tab; a step change across every viewer alongside tier-check "
            "failures means the gate itself lost its answer. Per replica: sum().",
            labels=[],
        )
        retention = CounterMetricFamily(
            "gsd_retention_rows_deleted_total",
            "Rows removed by retention, by table. login_event, membership_event and "
            "sync_event deletes are bounded at 5000/cycle, so a rate pinned at that ceiling "
            "means the backlog is not draining; membership_event and sync_event prune only "
            "after a successful backup in the leader's life. Per replica (leader): sum().",
            labels=["table"],
        )
        backup_failures = CounterMetricFamily(
            "gsd_backup_failures_total",
            "Backup attempts that failed (VACUUM INTO error or unwritable backupDir). "
            "Pair with gsd_backup_last_success_timestamp_seconds: failures say it is "
            "breaking, the timestamp says how stale the last good copy already is.",
            labels=[],
        )
        poll_duration = GaugeMetricFamily(
            "gsd_cluster_poll_duration_seconds",
            "Wall time of the most recent poll of this cluster, successful or not. "
            "Emitted by the replica that polls (the leader); compare against "
            "pollIntervalSeconds and the request timeout — a rising duration under a "
            "green gsd_cluster_up is the slow-but-succeeding poll that the timestamp "
            "metrics cannot show.",
            labels=["cluster"],
        )

        if snap is not None:
            for threshold in TIER_THRESHOLDS:
                for outcome in TIER_CHECK_OUTCOMES:
                    checks.add_metric(
                        [threshold, outcome],
                        snap["tier_checks"].get((threshold, outcome), 0))
                for tier in TIERS:
                    decisions.add_metric(
                        [threshold, tier], snap["decisions"].get((threshold, tier), 0))
            refusals.add_metric([], snap["admin_refusals"])
            for table in RETENTION_TABLES:
                retention.add_metric([table], snap["retention"].get(table, 0))
            backup_failures.add_metric([], snap["backup_failures"])
            for cluster, seconds in sorted(snap["poll_seconds"].items()):
                poll_duration.add_metric([cluster], seconds)

        yield from (checks, decisions, refusals, retention, backup_failures, poll_duration)

        capture_enabled = GaugeMetricFamily(
            "gsd_login_capture_enabled",
            "1 when login capture is configured on. While this is 1, absence of "
            "gsd_login_capture_last_read_timestamp_seconds means capture has never once "
            "succeeded — a different failure from capture going stale.",
            labels=[],
        )
        if self.settings is not None:
            capture_enabled.add_metric([], 1 if self.settings.login_capture_enabled else 0)
        yield capture_enabled

        backup_ts = GaugeMetricFamily(
            "gsd_backup_last_success_timestamp_seconds",
            "Modification time of the newest backup file in backupDir. Read from the "
            "files rather than remembered from the last attempt, so it survives restarts "
            "and catches every failure shape, including a misconfigured directory. "
            "Absent when backups are disabled or none exists yet.",
            labels=[],
        )
        if self.settings is not None and self.settings.backup_dir:
            try:
                newest = max(
                    (p.stat().st_mtime
                     for p in Path(self.settings.backup_dir).glob("gsd-*.db")),
                    default=None,
                )
            except OSError:
                # OMITTED, never zeroed — the health() rule above: a failure to measure
                # must not read as a measurement of failure. Epoch 0 here would fire the
                # staleness alert while the backups may be perfectly fine.
                newest = None
            if newest is not None:
                backup_ts.add_metric([], newest)
        yield backup_ts


def build_registry(store: StorageBackend, grace: timedelta, elector=None,
                   signals: RuntimeSignals | None = None, settings=None) -> CollectorRegistry:
    """A dedicated registry — the default one carries process/GC collectors we do not want
    duplicated per app instance, and tests build several apps in one interpreter."""
    registry = CollectorRegistry()
    registry.register(DashboardCollector(store, grace, elector,
                                         signals=signals, settings=settings))
    return registry
