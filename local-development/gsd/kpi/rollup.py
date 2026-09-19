"""The daily rollup: the leader writes today's row for each cluster once, after the day's first
successful poll, from the same store methods the API and /metrics read. INSERT OR IGNORE in the
store makes a retried cycle or a second leader harmless; `kpi_daily_written` keeps the steady state
a read, not a write transaction per poll."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from .definitions import ROLLUP_METRICS

log = logging.getLogger(__name__)

#: Rows older than this are pruned by the leader beside the other retention tables. Two years of
#: daily points is ~5,800 rows per cluster.
KPI_DAILY_RETENTION_DAYS = 730


def today(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m-%d")


def values(store, cluster_id: str) -> dict[str, float]:
    """The day's reading, in ROLLUP_METRICS order, from the scalar queries the live surfaces use."""
    groups = store.group_counts(cluster_id)
    findings = store.count_bindings_by_finding(cluster_id)
    people = store.people_counts(cluster_id)
    reading = {
        "groups": groups["total"],
        "groups_empty": groups["empty"],
        "groups_unattributed": groups["unattributed"],
        "bindings": sum(findings.values()),
        "bindings_dangling": findings.get("dangling", 0),
        "bindings_unresolved": findings.get("unresolved", 0),
        "users": people["users"],
        "members": people["members"],
    }
    assert tuple(reading) == ROLLUP_METRICS
    return reading


def write_if_due(store, cluster_id: str, now: datetime | None = None) -> bool:
    """Write today's row if there is none. Returns whether a write happened."""
    day = today(now)
    if store.kpi_daily_written(cluster_id, day):
        return False
    written = store.write_kpi_daily(cluster_id, day, values(store, cluster_id))
    if written:
        log.info("%s: daily KPI rollup written for %s (%d metrics)", cluster_id, day, written)
    return bool(written)


def prune(store, cluster_id: str, now: datetime | None = None) -> int:
    before = ((now or datetime.now(UTC)) - timedelta(days=KPI_DAILY_RETENTION_DAYS)).strftime("%Y-%m-%d")
    return store.prune_kpi_daily(cluster_id, before)
