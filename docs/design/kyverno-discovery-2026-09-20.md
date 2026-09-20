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
| the legacy family | `kyverno.io` still serves `clusterpolicies`, `policies`, `cleanuppolicies`, `clustercleanuppolicies`, `globalcontextentries`, `updaterequests`; `reports.kyverno.io` serves `ephemeralreports` / `clusterephemeralreports` (the intermediate reports the controllers aggregate; not read) |
| reports controller flags | `--admissionReports=true --aggregateReports=true --policyReports=true --validatingAdmissionPolicyReports=true --mutatingAdmissionPolicyReports=false --openreportsEnabled=false` |
| admission controller flags | `--admissionReports=true --maxAdmissionReports=1000 --generateValidatingAdmissionPolicy=true` |
| background controller flags | `--enableReporting=validate` (the `--maxBackgroundReports` default, 10 000, is not set) |

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
| **`source` tells the family** | `kyverno` for the legacy `ClusterPolicy` family (667 results, all `background scan`); **`KyvernoValidatingPolicy`** for the CEL `ValidatingPolicy` (6 results, all `admission review`) — this is the field the CEL-only scope filters on |
| **`rule` is empty for CEL** | the 6 `KyvernoValidatingPolicy` results carry `rule: None`; the 667 legacy results carry rule names (finding 5, confirmed on the wire: key by policy + resource) |

The legacy family is **in use on this lab**: four `ClusterPolicy` objects (`group-naming-app-ocp-rbac`,
`group-naming-bda-rbac`, `namespace-oud-group-allowlist`, `rbac-standards-enforcement`; all `background:
true`, `validationFailureAction: Audit`) produce 667 of the 673 results. The module does not read them
(#165's scope) — but it must **say** they are there: a page that showed 6 results on a cluster carrying 673
would read as a clean cluster. "N results from the deprecated `ClusterPolicy`/`Policy` family are not
shown; that family is removed in Kyverno 1.20" is a first-class state, like truncation.

## 3. Finding 10 — does one `ValidatingPolicy` report twice?

Both flags are on (`--generateValidatingAdmissionPolicy=true`, `--validatingAdmissionPolicyReports=true`).
Measured: `oc get validatingadmissionpolicies` lists **11**, `-l app.kubernetes.io/managed-by=kyverno` lists
**0** — the 11 are OpenShift's own (52 d old). The one `ValidatingPolicy`, `restrict-nco-config-writers`
(`evaluation.admission: true`, `background: false`, `validationActions: [Audit]`, `failurePolicy: Fail`),
has **no generated VAP**: its `variables` build a `SubjectAccessReview` with `dyn()` and use
`request.userInfo` — CEL the VAP generator does not translate, so Kyverno keeps it in its own engine. Its
results appear **once**, under its own kind (`source: KyvernoValidatingPolicy`), on the 9 objects it has
admitted (6 cluster-scoped `NamespaceConfig`/`GroupConfig`, 3 `GroupSync`). **Answer:** a VAP-translatable
policy would report under both kinds; this one — and any policy using authorizer or `dyn()` expressions —
reports under its own kind only. The reader must treat a generated VAP's report (`source` naming the VAP)
as the same policy, keyed by the policy name the VAP's `kyverno.io/policy-name`-style label carries, and
never count it twice; the first CRC test of that path needs a translatable policy (none exists here yet).

## 4. The breaker

Scraped from the dashboard pod (`kyverno-reports-controller-metrics.kyverno.svc:8000/metrics`, 212 795
bytes): `kyverno_breaker_total{circuit_name="background scan reports"} 3949` — the breaker is invoked, and
that counter exists. **`kyverno_breaker_drops` is absent from the scrape.** OpenTelemetry counters are
exported once they have been incremented, so absence means *no drop has happened on this install*, not
*unsupported* — the reader treats a missing `kyverno_breaker_drops` as 0 and says "no drops observed", and a
present one as the truncation state. Also served, for the CEL family specifically:
`kyverno_validating_policy_results_total` and `kyverno_validating_policy_execution_duration_seconds_*`; for
the legacy one `kyverno_policy_results_total` (with `rule_name`, `policy_type`, `rule_execution_cause`).
The families carry `resource_kind` and `policy_name` but **never a resource name or namespace** — the same
rule the module's own `/metrics` output must keep.

## 5. What this settles for the build

- **Reader:** discover `openreports.io/v1alpha1`, else `wgpolicyk8s.io/v1alpha2` (here); LIST both report
  kinds paginated, keep only `results[].source` in the CEL set (`KyvernoValidatingPolicy`,
  `KyvernoMutatingPolicy`, `KyvernoGeneratingPolicy`, `KyvernoDeletingPolicy`, `KyvernoImageValidatingPolicy`
  — the naming pattern measured on the one kind present; the other four are inferred from it and must be
  confirmed the first time one is installed), count the rest as "not shown (deprecated family)".
- **Store:** one row per `(cluster, policy, resource kind, resource namespace, resource name, result)` with
  the report's `timestamp`, the `message`, `severity`, `category`, `properties.process`; `rule` kept nullable
  for the day the CEL engine fills it, never part of the key.
- **Definitions:** policies from the five `policies.kyverno.io` kinds through the preferred version, with
  `evaluation.admission/background`, `validationActions`, `failurePolicy` — the page says whether a policy
  can produce reports at all (`background: false` + `Audit` means admission-time only).
- **Denials:** `validationActions: [Deny]` would build no report (finding 2) — the audit-log path stands;
  on this lab every policy is `Audit`, so the first live denial must be provoked on purpose.
- **Truncation:** `kyverno_breaker_total` (present) and `kyverno_breaker_drops` (absent until a drop).

The dump behind every line: `oc get clusterpolicyreports -o yaml`, `oc get policyreports -A -o yaml`,
`oc get validatingpolicies -A -o yaml`, the four `oc get deploy -n kyverno … -o jsonpath='{.spec.template.spec.containers[0].args}'`
reads, `oc get crd <name> -o jsonpath='{range .spec.versions[*]}{.name}:{.served}:{.storage}{"\n"}{end}'`,
and one `oc exec` into the dashboard pod for the scrape — all taken 2026-09-20 between 07:30 and 07:45 local.
