"""The module's KPIs — the shape of `gsd/kpi/definitions.py`, appended to its lists.

Every family here is `public`: bounded labels (a cluster id, a CEL kind, a result word), aggregate
counts, and never a policy name, a resource name or a namespace — those reach the tier-gated JSON only.
Kyverno's own families DO carry `resource_namespace` (discovery §4); this module does not copy it.
A cluster where Kyverno is not installed emits nothing (None from the collector, omitted), which is how
the KPI module says "unmeasured is not zero".
"""

from __future__ import annotations

from ..kpi import GAUGE, PUBLIC, Context, Kpi, Sample
from . import CEL_KINDS, RESULTS

POLICY_KINDS = CEL_KINDS + ("other",)


def _summaries(ctx: Context) -> dict[str, dict]:
    if ctx.store is None:
        return {}
    out = {}
    for cluster in ctx.cluster_ids:
        summary = ctx.store.kyverno_summary(cluster)
        if summary.get("present"):
            out[cluster] = summary
    return out


def _policies(ctx: Context):
    found = _summaries(ctx)
    if not found:
        return None
    samples = []
    for cluster in found:
        by_kind = {k: 0 for k in POLICY_KINDS}
        for p in ctx.store.kyverno_policies(cluster):
            by_kind[p["kind"] if p["kind"] in by_kind else "other"] += 1
        samples.extend(Sample((cluster, kind), n) for kind, n in by_kind.items())
    return samples


def _results(ctx: Context):
    found = _summaries(ctx)
    if not found:
        return None
    samples = []
    for cluster in found:
        counts: dict[tuple[str, str], int] = {(k, r): 0 for k in POLICY_KINDS for r in RESULTS}
        for (kind, result), n in ctx.store.kyverno_result_counts(cluster).items():
            key = (kind if kind in POLICY_KINDS else "other", result)
            counts[key] = counts.get(key, 0) + n
        samples.extend(Sample((cluster, kind, result), n) for (kind, result), n in counts.items())
    return samples


def _presence_field(field: str, *, skip_none: bool = False):
    def collect(ctx: Context):
        found = _summaries(ctx)
        if not found:
            return None
        out = []
        for cluster, summary in found.items():
            value = summary.get(field)
            if value is None and skip_none:
                continue
            out.append(Sample((cluster,), value or 0))
        return out or None
    return collect


KYVERNO_KPIS: tuple[Kpi, ...] = (
    Kpi("gsd_kyverno_policies",
        "CEL policies (policies.kyverno.io) the poller listed on the cluster, by kind. Absent where no "
        "policy-report API group is served (Kyverno not installed).",
        GAUGE, ("cluster", "kind"), PUBLIC, _policies),
    Kpi("gsd_kyverno_results",
        "Policy-report results of the CEL family, one per (policy, resource), by the policy's kind and the "
        "result word. The deprecated ClusterPolicy/Policy family is not read; see gsd_kyverno_legacy_results.",
        GAUGE, ("cluster", "policy_kind", "result"), PUBLIC, _results),
    Kpi("gsd_kyverno_legacy_results",
        "Results the reports carry from the deprecated ClusterPolicy/Policy family (the API says it will be removed "
        "in a future release), counted and not shown — a cluster with these is not a clean cluster.",
        GAUGE, ("cluster",), PUBLIC, _presence_field("legacy_results")),
    Kpi("gsd_kyverno_report_breaker_drops",
        "kyverno_breaker_drops as the dashboard last scraped it from the reports controller: reports the "
        "breaker dropped, so the results above are incomplete. Absent until a drop is observed or when "
        "kyverno.metricsUrl is not set.",
        GAUGE, ("cluster",), PUBLIC, _presence_field("breaker_drops", skip_none=True)),
)
