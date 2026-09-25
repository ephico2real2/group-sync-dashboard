"""The in-app renderer: definitions → the payload the pages read, with its as-of.

Every KPI in the payload states where its number comes from and when it was true, so a legitimate
difference from a report's signed figure (a snapshot taken earlier) is explained rather than
mysterious. Trends carry `history_retained_since` — retention prunes the event tables, and a trend
that ignores the cut lies about a quiet month.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from . import Context, Kpi
from .definitions import ALL_KPIS, ROLLUP_DAYS, ROLLUP_METRICS, TREND_DAYS

log = logging.getLogger(__name__)


def render(kpis: tuple[Kpi, ...], ctx: Context) -> dict:
    """`{name: {"help", "kind", "privacy", "labels", "samples": [{labels..., "value"}]}}`; a KPI whose
    collector returned None is present with `samples: None` — unavailable, distinguishable from 0."""
    out = {}
    for kpi in kpis:
        try:
            samples = kpi.collect(ctx)
        except Exception:  # noqa: BLE001 — the same rule as the scrape: one source, not the page
            log.exception("KPI %s could not be collected; unavailable in this payload", kpi.name)
            samples = None
        out[kpi.name] = {
            "help": kpi.help, "kind": kpi.kind, "privacy": kpi.privacy, "labels": list(kpi.labels),
            "samples": None if samples is None else [
                {**dict(zip(kpi.labels, s.labels)), "value": s.value} for s in samples
            ],
        }
    return out


def posture(store, cluster_id: str, grace: timedelta, now: datetime) -> dict:
    """The access-posture inputs for one cluster, from the scalar queries the cluster rows and
    /metrics already use. The Clusters table (#157) reads them as they are; the band SUMS them across
    the fleet and combines named categories (dangling + unresolved + unmanaged = "to review", #347) — arithmetic over
    whole-set scalars, never over a capped row list. CR states are derived the way the CR list
    derives them."""
    from .. import state as st
    groups = store.group_counts(cluster_id)
    findings = store.count_bindings_by_finding(cluster_id)
    states: dict[str, int] = {}
    for cr in store.groupsyncs(cluster_id):
        state = st.compute_state(st.parse_time(cr.get("last_sync_at")), cr.get("schedule"), now, grace)
        states[state] = states.get(state, 0) + 1
    return {
        "groups": groups,
        # Every tier _FINDING_CASE names, `unmanaged` included: the page's Bindings figure is the
        # cluster's group bindings less the built-in ones, and a tier left out here left a hand-made
        # grant out of that count (measured: 3 of 4 on the UI seed).
        "bindings": {k: findings.get(k, 0) for k in ("ok", "dangling", "unresolved", "unmanaged", "built_in")},
        "groupsyncs": {"total": sum(states.values()), "states": states,
                       "oldest_last_sync": store.oldest_last_sync(cluster_id)},
    }


def page_payload(ctx: Context, *, dashboard_system: dict | None, report_system: dict | None,
                 report_system_at: str | None, last_poll: dict[str, str | None], now: datetime | None = None,
                 grace: timedelta = timedelta(seconds=120), thresholds: dict | None = None,
                 links: dict | None = None) -> dict:
    """The /api/kpi body. `dashboard_system` is this process's own sample (taken now); `report_system`
    the report service's last self-report, pulled with the usage feed, and `report_system_at` when.
    `thresholds` are the configured amber marks the page draws on every meter and names in its rule
    line; `links` the doors out (grafana, observe) — absent when not configured."""
    now = now or datetime.now(UTC)
    kpis = render(ALL_KPIS, ctx)
    trends, postures = {}, {}
    if ctx.store is not None:
        since_day = (now - timedelta(days=ROLLUP_DAYS)).strftime("%Y-%m-%d")
        # The sparklines' buckets: TREND_DAYS whole UTC days ending today, from the first day's
        # midnight. A rolling `now - 30d` start put a partial day in front of the thirty the page
        # draws (today and the 29 before it); its rows were in the scalars and off the line
        # (measured: 7 joiners at now-30d+1min, on the payload, absent from the sparkline).
        activity_since = (now - timedelta(days=TREND_DAYS - 1)).strftime("%Y-%m-%dT00:00:00Z")
        for cluster in ctx.cluster_ids:
            retained = ctx.store.history_retained_since(cluster)
            trends[cluster] = {
                "window_days": TREND_DAYS,
                "history_retained_since": retained,
                # Where the recorded report timeline starts — the mock's "timeline starts …": the
                # pull began with the reporting module, not with the cluster's history.
                "report_timeline_since": ctx.store.report_volume(cluster, "9999")["since"],
                # Per-day buckets over the window, for the sparklines.
                "activity": ctx.store.daily_activity(cluster, activity_since),
                "daily": {
                    "since": ctx.store.kpi_daily_since(cluster),
                    "window_days": ROLLUP_DAYS,
                    "series": {m: ctx.store.kpi_daily_series(cluster, m, since_day) for m in ROLLUP_METRICS},
                },
                "as_of": last_poll.get(cluster),
            }
            postures[cluster] = posture(ctx.store, cluster, grace, now)
    return {
        "as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "kpis": kpis,
        "posture": postures,
        "thresholds": thresholds or {},
        "links": links or {},
        "trends": trends,
        "system": {
            "dashboard": {"as_of": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **(dashboard_system or {})} if dashboard_system else None,
            "report": {"as_of": report_system_at, **report_system} if report_system else None,
        },
    }
