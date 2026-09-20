# Kyverno discovery on CRC — 2026-09-20 (#170, step 0)

The research record (`kyverno-research-2026-09-17.md`) was read from the v1.19.1 source; this is what the
running install on the lab actually serves, measured with read-only `oc` and one in-pod scrape. It settles
the data shape the module, its store and its mock are built on. Every number is a command's output.

**Where:** CRC, OpenShift 4.22.7 (Kubernetes v1.35.6); Kyverno `v1.19.1` in namespace `kyverno` — the
admission, background, cleanup and reports controllers (`oc get pods -n kyverno`), installed 2026-09-19.

## 1. What is served

| | measured |
|---|---|
| report groups | `wgpolicyk8s.io/v1alpha2` only — `policyreports`, `clusterpolicyreports` (`v1alpha2:served:storage`); **no `openreports.io`** (`oc api-resources` has none; the reports controller runs `--openreportsEnabled=false`) |
| CEL policy kinds | `policies.kyverno.io` serves **`v1`** (served, not storage), `v1alpha1` (served) and `v1beta1` (served, **storage**) for `validatingpolicies`; the five cluster kinds and their five `namespaced*` twins, plus `policyexceptions` |
| the legacy family | `kyverno.io` still serves `clusterpolicies`, `policies`, `cleanuppolicies`, `clustercleanuppolicies`, `globalcontextentries`, `updaterequests` and its own `policyexceptions` (`kyverno.io/v2`, distinct from the CEL family's); `reports.kyverno.io` serves `ephemeralreports` / `clusterephemeralreports` (the intermediate reports the controllers aggregate; not read) |
| reports controller flags | `--admissionReports=true --aggregateReports=true --policyReports=true --validatingAdmissionPolicyReports=true --mutatingAdmissionPolicyReports=false --openreportsEnabled=false` |
| admission controller flags | `--admissionReports=true --maxAdmissionReports=1000 --generateValidatingAdmissionPolicy=true` |
| background controller flags | `--enableReporting=validate,mutate,mutateExisting,imageVerify,generate`; `--maxBackgroundReports` (default 10 000) is a flag of both the background controller (`cmd/background-controller/main.go:149`) and the reports controller (`cmd/reports-controller/main.go:327`) and is set on neither — the breaker in §4 is the reports controller's |

So finding 7's discovery order holds (`openreports.io/v1alpha1` first, then `wgpolicyk8s.io/v1alpha2`) and
on this install the second is what answers. The research's "`policies.kyverno.io/v1alpha1`" is one of three
served versions here; the reader lists policies through the discovery API's preferred version (`v1`).

## 2. The reports and what is in them

| | measured |
|---|---|
| `clusterpolicyreports` | **112**, all `wgpolicyk8s.io/v1alpha2`; owners `Namespace` 106, `NamespaceConfig` 4, `GroupConfig` 2; every one labelled `app.kubernetes.io/managed-by: kyverno` and **nothing else** (finding 8: no server-side filter by policy) |
| `policyreports` | **3**, all in `group-sync-operator`, each owned by a `GroupSync` |
| naming and scope | `metadata.name` = the resource's UID; `scope: {apiVersion, kind, name, uid}` = the resource; `ownerReferences[0]` = the resource (finding 4: a report lives and dies with its resource) |
| summary totals | `pass 67 · fail 18 · warn 0 · error 0 · skip 588` across the 112 cluster reports |
| a result's fields | `category, message, policy, properties, result, rule, scored, severity, source, timestamp` — `timestamp` is `{seconds, nanos}`, `properties.process` is `background scan` or `admission review` |
| **`source` tells the family** | `kyverno` for the legacy `ClusterPolicy` family (667 results, all `background scan`); **`KyvernoValidatingPolicy`** for the CEL `ValidatingPolicy` (9 results, all `admission review`: 6 in the cluster reports, 3 in the namespaced ones) — this is the field the CEL-only scope filters on. `properties.process` is derived from the policy's own `evaluation` flags, background first (`pkg/utils/report/results.go#selectProcess`), so it says what the policy is, not which path produced the row |
| **`rule` is empty for CEL** | the 9 `KyvernoValidatingPolicy` results carry **no `rule` key at all** (omitted on the wire; a `.get()` reads it as `None`); the 667 legacy results carry one of seven rule names (finding 5, confirmed on the wire: key by policy + resource) |

The legacy family is **in use on this lab**: four `ClusterPolicy` objects (`group-naming-app-ocp-rbac`,
`group-naming-bda-rbac`, `namespace-oud-group-allowlist`, `rbac-standards-enforcement`; all `background:
true`, `validationFailureAction: Audit`). Two of them produce all 667 of the 673 cluster-report results
(`rbac-standards-enforcement` 561, `namespace-oud-group-allowlist` 106); the two `Group`-matching ones
(`group-naming-*`) produce **none** for the 62 `groups.user.openshift.io` on the cluster — the reports
controller's log says why, 20 times: *"reports-controller is missing RBAC to list/watch this resource —
grant it via reportsController.rbac.clusterRole.extraResources"* (`groups.user.openshift.io is forbidden`),
while the policies' own status says only `Ready`. A live policy whose kind cannot be scanned is a state the
page must show, like truncation. The module does not read the legacy family (#165's scope) — but it must
**say** it is there: a page that showed 9 results on a cluster carrying 676 would read as a clean cluster.
"N results from the deprecated `ClusterPolicy`/`Policy` family are not shown; the API says that family
*will be removed in a future release*" (its `deprecationWarning`; no version is named — the research
record's correction to #165 stands) is a first-class state, like truncation.

## 3. Finding 10 — does one `ValidatingPolicy` report twice?

Both flags are on (`--generateValidatingAdmissionPolicy=true`, `--validatingAdmissionPolicyReports=true`).
Measured: `oc get validatingadmissionpolicies` lists **11**, `-l app.kubernetes.io/managed-by=kyverno` lists
**0** — the 11 are OpenShift's own (52 d old). The one `ValidatingPolicy`, `restrict-nco-config-writers`
(`evaluation.admission: true`, `background: false`, `validationActions: [Audit]`, `failurePolicy: Fail`),
has **no generated VAP** because generation is a per-policy opt-in it does not set: `spec.autogen` is
absent (`spec.autogen.validatingAdmissionPolicy.enabled` — the CRD: *"Defaults to \"false\" if not
specified"*), and the generator's own word is on the object — `status.generated: false`,
`status.conditionStatus.message: "skip generating ValidatingAdmissionPolicy: not enabled."`. For a
`ValidatingPolicy` the generator checks only its own RBAC, this opt-in and the pod-controller autogen — never the
CEL (`pkg/controllers/admissionpolicygenerator/generate-vap.go:16-28,76-89`) — and copies `variables`/`validations` verbatim into the VAP (`pkg/admissionpolicy/builder.go:104-109`) — the
`dyn()`/`SubjectAccessReview` CEL is not what stops it, and neither is `background: false`. Its results
appear **once**, under its own kind (`source: KyvernoValidatingPolicy`), on the 9 objects it has admitted
(4 `NamespaceConfig`, 2 `GroupConfig`, 3 `GroupSync`). **Answer:** a policy never reports under both
kinds. Once a VAP is generated Kyverno stands down on that policy — the webhook drops it
(`pkg/controllers/webhook/controller.go:1489`), the CEL engine drops it (`pkg/cel/policies/vpol/engine/reconciler.go:72-77`)
and the background scan skips it (`pkg/controllers/report/background/controller.go:703-705`) — and its rows
come only from the VAP path: `source: ValidatingAdmissionPolicy`, `policy: vpol-<name>`, `properties.process:
background scan`, `properties.binding` (`pkg/utils/report/results.go:159-165`). The generated VAP carries
no policy-name label — only `app.kubernetes.io/managed-by: kyverno` and an `ownerReference` to the policy
(`builder.go:154-175`) — so the reader maps `vpol-<name>` (or the owner) back to the policy and shows those
rows as the policy's. The 2026-09-19 probe (`kyverno-step0-discovery-2026-09-19.md` §4) measured the same:
after generation the VAP-admitted object had no row from either source within 150 s.

## 4. The breaker

Scraped from the dashboard pod (`kyverno-reports-controller-metrics.kyverno.svc:8000/metrics`, 212 795
bytes): `kyverno_breaker_total{circuit_name="background scan reports"} 3949` — the breaker is invoked, and
that counter exists. **`kyverno_breaker_drops` is absent from the scrape.** Both instruments are registered
in one `init` (`pkg/metrics/breaker.go:34-47`) and `RecordDrop` is called only when the circuit opens
(`pkg/breaker/breaker.go:45-49`); the OTel Go SDK Kyverno builds with (`sdk/metric v1.44.0`) emits a
cumulative sum only for attribute sets that have been added to (`sdk/metric/internal/aggregate/sum.go:157-200`)
and drops a metric with no data points (`sdk/metric/pipeline.go:167`, `if n := inst.compAgg(&data); n > 0`),
so absence means *no drop since this process started* (2026-09-19T00:38Z, 0 restarts), not *unsupported* —
the reader treats a missing `kyverno_breaker_drops` as 0 and says "no drops observed", and a present one as
the truncation state. There are **three** circuits, one per controller, and each has its own `/metrics`:
`admission reports` on the admission controller (`kyverno-svc-metrics`; `--maxAdmissionReports=1000` on this
install; 8 436 invocations at 11:21 UTC), `background scan reports` on the reports controller (this scrape), and
`background-scan reports` on the background controller — never invoked here, so on that endpoint even
`kyverno_breaker_total` is absent, the same rule. The truncation state must scrape all three. Also served, for the CEL family specifically:
`kyverno_validating_policy_results_total` and `kyverno_validating_policy_execution_duration_seconds_*`; for
the legacy one `kyverno_policy_results_total` (with `rule_name`, `policy_type`, `rule_execution_cause`).
The families carry `resource_kind`, `policy_name` and `policy_namespace`; **no family carries a resource
name**, but `resource_namespace` **is** a label on `kyverno_client_queries_total` (106 namespace names on
this scrape), `kyverno_policy_results_total` and `kyverno_validating_policy_results_total` (`klt-pass-both`,
`group-sync-operator`) — a label the module's own `/metrics` output must **not** copy (the public
`/metrics` rule: no names, namespaces included).

## 5. What this settles for the build

- **Reader:** discover `openreports.io/v1alpha1`, else `wgpolicyk8s.io/v1alpha2` (here); LIST both report
  kinds paginated, keep `results[].source` in the CEL set — `KyvernoValidatingPolicy` (measured),
  `KyvernoMutatingPolicy`, `KyvernoGeneratingPolicy`, `KyvernoImageValidatingPolicy` (the four constants of
  `pkg/utils/report/source.go` at v1.19.1; there is **no** `KyvernoDeletingPolicy` — a `DeletingPolicy`
  has no report path in `ToPolicyReportResult`) — plus `ValidatingAdmissionPolicy` / `MutatingAdmissionPolicy`
  rows whose `policy` is `vpol-<name>` / `mpol-<name>` (`generate-vap.go:34`, `generate-map.go:60`), shown as that policy's (§3); count `kyverno` as
  "not shown (deprecated family)" and anything else as unknown, never as deprecated.
- **Store:** one row per `(cluster, source, policy, resource uid, result)` — `source` because a
  `ValidatingPolicy` and a `MutatingPolicy` may share a name; `policy` as the wire string, which is
  `namespace/name` for the namespaced kinds (`cache.MetaNamespaceKeyFunc`, `results.go:97`); the resource's
  `uid` (the report's own name) so a deleted-and-recreated resource is a new row set — with the `scope`'s
  `apiVersion`, `kind`, `namespace`, `name`, the result's `timestamp` (re-stamped by every background scan:
  221 results were re-stamped, none changed value, between the dump behind this record at 10:57 UTC and a
  re-dump at 11:21 UTC — it is "last evaluated", not "first seen"), the `message`, `severity`, `category`, `properties.process`, `properties.exceptions` and
  `properties.binding`; `rule` kept nullable for the day the CEL engine fills it, never part of the key.
- **Definitions:** policies from the five `policies.kyverno.io` kinds through the preferred version, with
  `evaluation.admission/background`, `validationActions`, `failurePolicy` — the page says whether a policy
  can produce reports at all (`background: false` + `Audit` means admission-time only).
- **Denials:** `validationActions: [Deny]` would build no report (finding 2) — the audit-log path stands;
  on this lab every policy is `Audit`, so the first live denial must be provoked on purpose.
- **Truncation:** `kyverno_breaker_total` and `kyverno_breaker_drops` (absent until a drop) on all three controllers' `/metrics` (§4).

The dump behind every line: `oc get clusterpolicyreports -o yaml`, `oc get policyreports -A -o yaml`,
`oc get validatingpolicies -A -o yaml`, the four `oc get deploy -n kyverno … -o jsonpath='{.spec.template.spec.containers[0].args}'`
reads, `oc get crd <name> -o jsonpath='{range .spec.versions[*]}{.name}:{.served}:{.storage}{"\n"}{end}'`,
and one `oc exec` into the dashboard pod for the scrape — all taken 2026-09-20 about 10:57 UTC (05:57 CDT).
