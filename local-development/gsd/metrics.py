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
from datetime import UTC, datetime, timedelta

from prometheus_client import CollectorRegistry
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from . import __version__, state as st
from .storage import StorageBackend

log = logging.getLogger(__name__)

STATES = (st.OK, st.LATE, st.OVERDUE, st.UNKNOWN)
FINDINGS = ("ok", "dangling", "unresolved", "built_in")


def _epoch(value: str | None) -> float | None:
    parsed = st.parse_time(value)
    return parsed.timestamp() if parsed else None


class DashboardCollector:
    """Reads the store on each scrape and yields the current picture."""

    def __init__(self, store: StorageBackend, grace: timedelta, elector=None):
        self.store = store
        self.grace = grace
        self.elector = elector

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
        leader = GaugeMetricFamily(
            "gsd_leader",
            "1 on the replica holding the poll lease, 0 on standbys. Use it to pick one "
            "replica's series: gsd_groups_total and on(pod) gsd_leader == 1",
            labels=["cluster"],
        )
        if self.elector is not None:
            leader.add_metric([""], 1 if self.elector.is_leader else 0)
        else:
            leader.add_metric([""], 1)
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
            "1 if the last poll of this cluster succeeded, 0 otherwise.",
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
            "Computed alerts, by kind and severity.",
            labels=["cluster", "kind", "severity"],
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

                for alert in st.compute_alerts(
                    cluster=cluster,
                    groupsyncs=cluster_groupsyncs,
                    operator_configs=self.store.operator_configs(cluster)["configs"],
                    user_bindings=self.store.direct_user_bindings(cluster),
                    groups=self.store.groups(cluster, "all"),
                    now=now,
                    grace=self.grace,
                ):
                    key = (alert.kind, alert.severity)
                    by_kind[key] = by_kind.get(key, 0) + 1
                for (kind, severity), count in by_kind.items():
                    alerts.add_metric([cluster, kind, severity], count)
            except Exception:  # noqa: BLE001
                # One bad cluster must not fail the whole scrape: a partial exposition is
                # far more useful than none, and a scrape that 500s looks identical to the
                # target being down.
                log.exception("metrics collection failed for cluster %s", cluster)

        yield from (
            up, last_poll, groups, empty, unattributed, bindings,
            cr_last_sync, cr_state, cr_groups, cr_error, alerts,
        )


def build_registry(store: StorageBackend, grace: timedelta, elector=None) -> CollectorRegistry:
    """A dedicated registry — the default one carries process/GC collectors we do not want
    duplicated per app instance, and tests build several apps in one interpreter."""
    registry = CollectorRegistry()
    registry.register(DashboardCollector(store, grace, elector))
    return registry
