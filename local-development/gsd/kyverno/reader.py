"""Read one cluster's Kyverno state: the policies of the CEL kinds, the reports' results, the breaker.

Runtime discovery, not configuration (finding 7): `openreports.io/v1alpha1` first, then
`wgpolicyk8s.io/v1alpha2`; neither served means Kyverno is not installed, which is a state the caller
records as absent — never as zero results. Every LIST follows the API server's continue tokens
(`ClusterClient._list_all`), because reports carry only `managed-by: kyverno` and are filtered client-side
(finding 8). A CEL result is keyed by policy and resource, never by rule (finding 5: `rule` is empty).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import httpx

from . import CEL_KINDS, CEL_SOURCES, CONTROLLED_KINDS, GENERATED_SOURCES, LEGACY_SOURCE, RESULTS

log = logging.getLogger(__name__)

#: The report API groups, in the order tried. The first that answers is the one read.
REPORT_GROUPS: tuple[tuple[str, str, str, str], ...] = (
    ("openreports.io/v1alpha1", "/apis/openreports.io/v1alpha1", "reports", "clusterreports"),
    ("wgpolicyk8s.io/v1alpha2", "/apis/wgpolicyk8s.io/v1alpha2", "policyreports", "clusterpolicyreports"),
)
def _policy_collection(kind: str) -> str:
    return f"/apis/policies.kyverno.io/v1/{kind.lower()[:-1]}ies"


#: The CEL policy kinds' collection paths — the cluster kind, then its `Namespaced<Kind>` twin, both tagged
#: with the FAMILY kind, because a namespaced policy's results carry the family's `source` and the
#: `namespace/name` wire string (the 09-19 probe: `KyvernoValidatingPolicy`, `klt-pass-both/step0-…`), and
#: kyverno_policies() joins on exactly that (review of #228, Grok and Codex: the first cut listed the five
#: cluster collections only, so a cluster using namespaced policies alone read "policies: 0"). The discovery
#: API's preferred version on 1.19.1 is `v1` (discovery §1); a cluster serving only an older version answers
#: 404 here and the kind reads as absent — said, not hidden.
POLICY_PATHS: tuple[tuple[str, str], ...] = tuple((kind, _policy_collection(name))
                                                   for kind in CEL_KINDS for name in (kind, f"Namespaced{kind}"))
MANAGED_BY = "app.kubernetes.io/managed-by"
KYVERNO = "kyverno"


@dataclass(frozen=True)
class PolicyView:
    kind: str
    namespace: str | None
    name: str
    admission: bool
    background: bool
    actions: tuple[str, ...]
    failure_policy: str
    ready: bool | None
    #: `status.generated`: a generated ValidatingAdmissionPolicy stands in for this policy, and its rows carry
    #: `source: ValidatingAdmissionPolicy` with `policy: vpol-<name>` (discovery §3).
    generated: bool = False
    #: `status.conditionStatus.message` — the controller's own word, e.g. "Policy is ready for reporting" or an
    #: RBAC gap the policy's Ready condition does not say (discovery §2).
    note: str = ""


@dataclass(frozen=True)
class ResultView:
    """One CEL result: what one policy decided about one resource. `controlled` marks a Pod/ReplicaSet/Job.

    `policy` is the wire string — `namespace/name` for a namespaced policy (`cache.MetaNamespaceKeyFunc`,
    `results.go:97`), the bare name for a cluster one, and a generated admission policy's `vpol-`/`mpol-`
    prefix stripped so its rows are the policy's. `resource_uid` is the report's own name: a resource deleted
    and recreated is a new row set, never merged into the old one's history (finding 4)."""
    policy_kind: str
    policy: str
    resource_kind: str
    resource_namespace: str
    resource_name: str
    resource_uid: str
    resource_api_version: str
    result: str
    severity: str
    category: str
    message: str
    process: str
    at: int | None
    controlled: bool


@dataclass
class BreakerView:
    total: int | None = None
    drops: int | None = None


@dataclass
class KyvernoRead:
    api_group: str
    policies: list[PolicyView] = field(default_factory=list)
    policy_kinds_served: tuple[str, ...] = ()
    results: list[ResultView] = field(default_factory=list)
    reports: int = 0
    legacy_results: int = 0
    other_results: int = 0
    breaker: BreakerView | None = None


def _bool(value, default: bool) -> bool:
    return default if value is None else bool(value)


def policy_view(kind: str, obj: dict) -> PolicyView:
    """One CEL policy as the page lists it. `ready` and `note` come from `status.conditionStatus` — the only
    status the five CRDs define (`ready`, `conditions[]`, `message`; no CEL CRD has a top-level
    `status.conditions`). `note` is a condition that is not True, as `type: message` — an RBAC gap says
    `RBACPermissionsGranted: reports-controller is missing RBAC…` — and, when nothing failed but the policy is
    still not ready, the controller's top-level `message`. That message is otherwise NOT a readiness note: the
    CRD defines it as "details about the generation of ValidatingAdmissionPolicy" (`skip generating
    ValidatingAdmissionPolicy: not enabled.` on a ready policy, measured on the lab; review of #228, OB3)."""
    spec = obj.get("spec") or {}
    meta = obj.get("metadata") or {}
    status = obj.get("status") or {}
    evaluation = spec.get("evaluation") or {}
    condition = status.get("conditionStatus") or {}
    ready = condition.get("ready") if isinstance(condition.get("ready"), bool) else None
    failing = [f"{c.get('type') or '?'}: {c.get('message') or c.get('reason') or ''}".strip(": ")
               for c in (condition.get("conditions") or []) if isinstance(c, dict) and c.get("status") != "True"]
    note = "; ".join(failing) if failing else (str(condition.get("message") or "") if ready is False else "")
    return PolicyView(
        kind=kind, namespace=meta.get("namespace"), name=meta.get("name", ""),
        admission=_bool((evaluation.get("admission") or {}).get("enabled"), True),
        background=_bool((evaluation.get("background") or {}).get("enabled"), True),
        actions=tuple(str(a) for a in (spec.get("validationActions") or ())),
        failure_policy=str(spec.get("failurePolicy") or "Fail"),
        ready=ready,
        generated=bool(status.get("generated")),
        note=note[:300],
    )


def result_views(report: dict) -> tuple[list[ResultView], int, int]:
    """The CEL results of one report, plus how many legacy and how many unknown-source results it held."""
    scope = report.get("scope") or {}
    meta = report.get("metadata") or {}
    kind = str(scope.get("kind") or "")
    out: list[ResultView] = []
    legacy = other = 0
    for r in report.get("results") or []:
        source = str(r.get("source") or "")
        if source == LEGACY_SOURCE:
            legacy += 1
            continue
        policy = str(r.get("policy") or "")
        policy_kind = CEL_SOURCES.get(source)
        if policy_kind is None and source in GENERATED_SOURCES:
            policy_kind, prefix = GENERATED_SOURCES[source]
            policy = policy[len(prefix):] if policy.startswith(prefix) else policy
        if policy_kind is None:
            other += 1
            policy_kind = "other"
        result = str(r.get("result") or "")
        stamp = r.get("timestamp") or {}
        out.append(ResultView(
            policy_kind=policy_kind, policy=policy,
            resource_kind=kind, resource_namespace=str(scope.get("namespace") or meta.get("namespace") or ""),
            resource_name=str(scope.get("name") or ""),
            resource_uid=str(scope.get("uid") or meta.get("name") or ""),
            resource_api_version=str(scope.get("apiVersion") or ""),
            result=result if result in RESULTS else "error",
            severity=str(r.get("severity") or ""), category=str(r.get("category") or ""),
            message=str(r.get("message") or "")[:1000],
            process=str((r.get("properties") or {}).get("process") or ""),
            at=int(stamp["seconds"]) if isinstance(stamp, dict) and isinstance(stamp.get("seconds"), int) else None,
            controlled=kind in CONTROLLED_KINDS,
        ))
    return out, legacy, other


_BREAKER_LINE = re.compile(r'^(kyverno_breaker_(?:total|drops))\{([^}]*)\}\s+([0-9.eE+-]+)\s*$')


def parse_breaker(text: str, into: BreakerView | None = None) -> BreakerView:
    """The two breaker families from one Kyverno metrics scrape, every circuit summed — there are three, one
    per controller (`admission reports`, `background scan reports`, `background-scan reports`), each on its
    own endpoint (discovery §4), and a report dropped by any of them is a result the page cannot show.
    `drops` stays None when the family is absent: OpenTelemetry exports a counter on its first increment, so
    absence means no drop observed since that process started, and the caller says so rather than printing 0
    as a measurement. `into` accumulates across endpoints."""
    view = into if into is not None else BreakerView()
    for line in text.splitlines():
        m = _BREAKER_LINE.match(line)
        if not m:
            continue
        family, _labels, value = m.groups()
        try:
            n = int(float(value))
        except ValueError:
            continue
        if family.endswith("_total"):
            view.total = (view.total or 0) + n
        else:
            view.drops = (view.drops or 0) + n
    return view


def read(cluster_client, metrics_url: str = "") -> KyvernoRead | None:
    """One read of one cluster. None when no report API group is served (not installed).

    `cluster_client` is a `gsd.kube.ClusterClient`; its `_client()`, `_get()` and `_list_all()` carry
    the token, the CA, the paging and the outcome mapping every other read uses. A 403 on the reports
    raises ClusterError(FORBIDDEN) like any other refused list — the poller records it. A 404 on a
    policy kind is that kind absent (an older Kyverno), not an error.
    """
    from ..kube import ClusterError  # local: kube imports nothing from here, and the module stays importable alone

    # Every SERVED report group is read, not only the first found: which group a cluster serves is decided by
    # which CRDs are installed, not by Kyverno's --openreportsEnabled flag, so openreports.io installed by
    # another tool beside a Kyverno still writing wgpolicyk8s.io would otherwise read as "installed, 0
    # reports" — a clean cluster that is not one (review of #228, OB3). Kyverno writes to exactly one group
    # (finding 7), so `api_group` names the one carrying its reports, or the first served when none does yet.
    with cluster_client._client() as client:
        served_groups: list[tuple[str, str, str, str]] = []
        for name, base, namespaced, cluster_scoped in REPORT_GROUPS:
            try:
                cluster_client._get(client, base, {})
            except ClusterError as exc:
                if exc.message.startswith(f"HTTP 404 on {base}"):
                    continue
                raise
            served_groups.append((name, base, namespaced, cluster_scoped))
        if not served_groups:
            return None
        out = KyvernoRead(api_group=served_groups[0][0])

        served: list[str] = []
        for kind, path in POLICY_PATHS:
            try:
                items = cluster_client._list_all(client, path)
            except ClusterError as exc:
                if exc.message.startswith(f"HTTP 404 on {path}"):
                    continue
                raise
            if kind not in served:
                served.append(kind)
            out.policies.extend(policy_view(kind, obj) for obj in items)
        out.policy_kinds_served = tuple(served)

        carrying: list[str] = []
        for name, base, namespaced, cluster_scoped in served_groups:
            before = out.reports
            for collection in (cluster_scoped, namespaced):
                path = f"{base}/{collection}"
                for report in cluster_client._list_all(client, path):
                    labels = (report.get("metadata") or {}).get("labels") or {}
                    if labels.get(MANAGED_BY) != KYVERNO:
                        continue
                    out.reports += 1
                    views, legacy, other = result_views(report)
                    out.results.extend(views)
                    out.legacy_results += legacy
                    out.other_results += other
            if out.reports > before:
                carrying.append(name)
        if carrying:
            out.api_group = carrying[0]

    urls = [u for u in re.split(r"[,\s]+", metrics_url or "") if u]
    if urls:
        breaker = BreakerView()
        for url in urls:
            try:
                response = httpx.get(url, timeout=10.0)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("%s: the Kyverno breaker scrape of %s failed (%s) — the truncation state is unknown this cycle",
                            cluster_client.cluster.name, url, exc)
                break
            parse_breaker(response.text, breaker)
        else:
            out.breaker = breaker
    return out
