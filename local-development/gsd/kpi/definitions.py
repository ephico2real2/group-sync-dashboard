"""The definitions. Each is one `Kpi`; `PUBLIC_KPIS` and `INTERNAL_KPIS` are what the renderers walk.

Two families of source:

- the process's own cgroup and volume (`system.py`) — the same definitions serve BOTH processes,
  the `component` label naming which one is reporting (each process emits itself only);
- the dashboard's store — the churn counters under an id watermark (`RuntimeSignals`), the windowed
  trends and the people counts.

Label vocabularies are fixed tuples here, like STATES and FINDINGS in gsd/metrics.py, so every
combination is pre-seeded to 0 and increase() has a baseline before the first event. The one open
dimension is `provider` on the login counter — an identity provider's name, operator configuration
and never a person, the same class as the `schedule` label the report service exports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .. import loginlog
from . import COUNTER, GAUGE, INTERNAL, PUBLIC, Context, Kpi, Sample

MEMBERSHIP_CHANGES = ("added", "removed")
#: The outcome vocabulary, read OFF THE PARSER (the same rule as api.LOGIN_OUTCOMES): loginlog.py is
#: where an outcome is decided, so a new one must not need a second list edited.
LOGIN_OUTCOMES = tuple(v for k, v in vars(loginlog).items() if k.startswith("OUTCOME_") and isinstance(v, str))
#: The provider value for an attempt whose row carries none, and for one whose provider is not an
#: identity provider the cluster knows (`Store.identity_providers`): a login row's provider is a
#: parsed log field, and /metrics is unauthenticated, so only a real IdP's name becomes a label.
UNKNOWN_PROVIDER = "unknown"
OTHER_PROVIDER = "other"
#: The in-app trend window, and the rollup's.
TREND_DAYS = 30
ROLLUP_DAYS = 90


# -- the process: cgroup v2 and the volume ----------------------------------------------------------

def _memory(ctx: Context):
    m = ctx.system.memory() if ctx.system is not None else None
    return None if m is None else [Sample((ctx.component,), m.current_bytes)]


def _memory_limit(ctx: Context):
    m = ctx.system.memory() if ctx.system is not None else None
    return None if m is None or m.limit_bytes is None else [Sample((ctx.component,), m.limit_bytes)]


def _cpu(field):
    def collect(ctx: Context):
        c = ctx.system.cpu() if ctx.system is not None else None
        if c is None:
            return None
        value = getattr(c, field)
        return None if value is None else [Sample((ctx.component,), value)]
    return collect


def _disk(field):
    def collect(ctx: Context):
        if ctx.volume is None:
            return None
        from .system import disk
        d = disk(ctx.volume)
        return None if d is None else [Sample((ctx.component,), getattr(d, field))]
    return collect


# -- the store: churn under an id watermark, trends over a window, people ---------------------------

def _membership_changes(ctx: Context):
    if ctx.signals is None or ctx.store is None:
        return None
    totals = ctx.signals.membership_change_totals(ctx.store, ctx.cluster_ids)
    return [Sample((cluster, change), totals.get((cluster, change), 0))
            for cluster in ctx.cluster_ids for change in MEMBERSHIP_CHANGES]


def _login_attempts(ctx: Context):
    if ctx.signals is None or ctx.store is None:
        return None
    totals = ctx.signals.login_attempt_totals(ctx.store, ctx.cluster_ids)
    # The label is BOUNDED to the cluster's identity providers plus `unknown`: a provider string
    # that is not one of them — a log field is data, not configuration — folds into `other`. Every
    # outcome is pre-seeded under every bounded value, so a new outcome's first increase() has a
    # baseline.
    known = {cluster: set(ctx.store.identity_providers(cluster)) | {UNKNOWN_PROVIDER} for cluster in ctx.cluster_ids}
    folded: dict[tuple[str, str, str], int] = {}
    for (cluster, outcome, provider), n in totals.items():
        label = provider if provider in known.get(cluster, ()) else OTHER_PROVIDER
        folded[(cluster, outcome, label)] = folded.get((cluster, outcome, label), 0) + n
    samples = []
    for cluster in ctx.cluster_ids:
        others = {OTHER_PROVIDER} if any(k[0] == cluster and k[2] == OTHER_PROVIDER for k in folded) else set()
        for provider in sorted(known[cluster] | others):
            for outcome in LOGIN_OUTCOMES:
                samples.append(Sample((cluster, outcome, provider), folded.get((cluster, outcome, provider), 0)))
    return samples


def _window_start(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _churn(change):
    def collect(ctx: Context):
        if ctx.store is None:
            return None
        since = _window_start(TREND_DAYS)
        return [Sample((cluster,), ctx.store.membership_churn(cluster, since)[change]) for cluster in ctx.cluster_ids]
    return collect


def _logins(field):
    def collect(ctx: Context):
        if ctx.store is None:
            return None
        since = _window_start(TREND_DAYS)
        return [Sample((cluster,), ctx.store.login_outcomes(cluster, since)[field]) for cluster in ctx.cluster_ids]
    return collect


def _reports(field):
    def collect(ctx: Context):
        if ctx.store is None:
            return None
        since = _window_start(TREND_DAYS)
        return [Sample((cluster,), ctx.store.report_volume(cluster, since)[field]) for cluster in ctx.cluster_ids]
    return collect


def _people(field):
    def collect(ctx: Context):
        if ctx.store is None:
            return None
        return [Sample((cluster,), ctx.store.people_counts(cluster)[field]) for cluster in ctx.cluster_ids]
    return collect


PUBLIC_KPIS: tuple[Kpi, ...] = (
    Kpi("gsd_process_memory_bytes",
        "Memory the process's cgroup currently charges (cgroup v2 memory.current). Absent on cgroup v1.",
        GAUGE, ("component",), PUBLIC, _memory),
    Kpi("gsd_process_memory_limit_bytes",
        "The cgroup's memory limit (memory.max). Absent when unlimited or on cgroup v1; never 0.",
        GAUGE, ("component",), PUBLIC, _memory_limit),
    Kpi("gsd_process_cpu_usage_seconds_total",
        "CPU time the cgroup has consumed (cpu.stat usage_usec). rate() of this over "
        "gsd_process_cpu_limit_cores is utilisation of the limit.",
        COUNTER, ("component",), PUBLIC, _cpu("usage_seconds")),
    Kpi("gsd_process_cpu_limit_cores",
        "The cgroup's CPU quota in cores (cpu.max quota/period). Absent when unlimited; never 0.",
        GAUGE, ("component",), PUBLIC, _cpu("limit_cores")),
    Kpi("gsd_process_cpu_periods_total",
        "Scheduler periods elapsed under a CPU quota (cpu.stat nr_periods).",
        COUNTER, ("component",), PUBLIC, _cpu("periods")),
    Kpi("gsd_process_cpu_throttled_periods_total",
        "Periods in which the cgroup was throttled (cpu.stat nr_throttled). The saturation signal: "
        "rate(throttled_periods)/rate(periods) is the share of time the workload hit its ceiling — "
        "measured 1.10 % on the reference dashboard while utilisation still read as headroom.",
        COUNTER, ("component",), PUBLIC, _cpu("throttled_periods")),
    Kpi("gsd_process_cpu_throttled_seconds_total",
        "Time the cgroup spent throttled (cpu.stat throttled_usec).",
        COUNTER, ("component",), PUBLIC, _cpu("throttled_seconds")),
    Kpi("gsd_volume_disk_used_bytes",
        "Used bytes on the filesystem holding the component's volume (statvfs) — the node's disk on "
        "a hostPath volume. The component's OWN bytes are gsd_sqlite_* and gsd_report_artifacts_disk_bytes.",
        GAUGE, ("component",), PUBLIC, _disk("used_bytes")),
    Kpi("gsd_volume_disk_total_bytes",
        "Size of the filesystem holding the component's volume (statvfs).",
        GAUGE, ("component",), PUBLIC, _disk("total_bytes")),
    Kpi("gsd_membership_changes_total",
        "Group membership changes observed, by change (added|removed). A cluster's first observation "
        "is not counted. Accumulated from membership_event under an id watermark, so retention "
        "cannot move it backwards; resets with the process.",
        COUNTER, ("cluster", "change"), PUBLIC, _membership_changes),
    Kpi("gsd_login_attempts_total",
        "Login attempts captured, by outcome and identity provider (operator configuration, never a "
        "person). Accumulated from login_event under an id watermark; resets with the process.",
        COUNTER, ("cluster", "outcome", "provider"), PUBLIC, _login_attempts),
)

INTERNAL_KPIS: tuple[Kpi, ...] = (
    Kpi("membership_added_30d", "People who joined a group in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _churn("added")),
    Kpi("membership_removed_30d", "People who left a group in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _churn("removed")),
    Kpi("login_attempts_30d", "Login attempts captured in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _logins("attempts")),
    Kpi("login_successes_30d", "Successful logins in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _logins("successes")),
    Kpi("login_providers_30d", "Identity providers seen in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _logins("providers")),
    Kpi("report_runs_30d", "Report runs requested in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _reports("runs")),
    Kpi("report_runs_done_30d", "Report runs that finished in the last 30 days.", GAUGE, ("cluster",), INTERNAL, _reports("done")),
    # People counts: personnel information, so internal — the gsd_dashboard_active_users ruling.
    Kpi("users_total", "User objects on the cluster.", GAUGE, ("cluster",), INTERNAL, _people("users")),
    Kpi("members_total", "Distinct people in at least one group.", GAUGE, ("cluster",), INTERNAL, _people("members")),
)

ALL_KPIS = PUBLIC_KPIS + INTERNAL_KPIS

#: What the daily rollup records per cluster (gsd/kpi/rollup.py): the counts with no history.
ROLLUP_METRICS = ("groups", "groups_empty", "groups_unattributed", "bindings", "bindings_dangling",
                  "bindings_unresolved", "users", "members")

