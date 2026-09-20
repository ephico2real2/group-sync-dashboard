# Kyverno step 0 — discovery on CRC, 2026-09-19

The measurement #170 says nothing else starts before: what the report API actually serves on this
cluster, the shape of a result, and the answer to finding 10. Every number below was read from the
running `crc-local` (OpenShift 4.22.7, Kyverno chart 3.9.1 / v1.19.1, five policies applied by hand
from `openshift-rbac-automation/working-sessions/policies/`). Trimmed samples of the real objects
are beside this file under `kyverno-step0/`; the full dumps (604 KB of ClusterPolicyReports) were
read, not committed.

## 1. What the API serves

| Group | Versions served | Resources |
|---|---|---|
| `wgpolicyk8s.io` | **`v1alpha2` only** (finding 1 confirmed) | `policyreports` (namespaced, short `polr`), `clusterpolicyreports` (cluster, `cpolr`) |
| `openreports.io` | **not served** on this cluster | — |
| `policies.kyverno.io` | `v1`, `v1beta1`, `v1alpha1` | `validatingpolicies`, `mutatingpolicies`, `generatingpolicies`, `deletingpolicies`, `imagevalidatingpolicies` (cluster) and the five `namespaced*` twins; `policyexceptions` |
| `kyverno.io` | `v2`, `v1`, `v2beta1`, `v2alpha1` | the legacy family, deprecated (the controller logs the deprecation on every list) |
| `reports.kyverno.io` | `v1` | `ephemeralreports` (0 present) |

So the collector reads `wgpolicyk8s.io/v1alpha2` and nothing else for reports; `openreports.io` in #170's
RBAC list is right to be optional — on this cluster the group does not exist and a hard dependency
would fail discovery.

## 2. What exists: 3 PolicyReports, 112 ClusterPolicyReports

**A report is per resource, not per policy.** Each `ClusterPolicyReport` carries a `scope` naming ONE
object and is itself named by that object's UID:

| scope kind | reports |
|---|---|
| `Namespace` | 106 |
| `NamespaceConfig` | 4 |
| `GroupConfig` | 2 |

and the 3 `PolicyReports` are the three namespaced objects a policy matched. A report's `summary`
counts `pass / fail / warn / error / skip` for that one object. Counting "how many findings" therefore
means summing `results[]` across reports, never counting reports.

## 3. The shape of a result

`kyverno-step0/policyreport.sample.json` is a real one. `results[]` items carry exactly:

```
category, message, policy, properties{process}, result, scored, severity, source, timestamp{seconds,nanos}
```

- **`source` is the discriminator between the families** — measured values: `kyverno` for a legacy
  `ClusterPolicy`, `KyvernoValidatingPolicy` for the CEL `ValidatingPolicy`. Nothing else appears.
- **`policy` is the policy's name, and for a NAMESPACED CEL policy it is namespace-qualified**
  (`klt-pass-both/step0-probe-require-owner` — measured with the probe in §5). A collector that joins
  results to policy objects by bare name misses every namespaced policy.
- `result` ∈ `pass | fail | skip` here (`warn`/`error` exist in the schema, none present).
- `timestamp` is `{seconds, nanos}`, not a string.
- `severity` and `category` come from the policy's annotations (`high`, `RBAC`); absent when the
  policy has none.
- `properties.process` = `admission review` or `background scan` — how the result was produced.

Results on this cluster, by source × policy × result (`kyverno-step0/results-by-source-policy-result.json`):

| source | policy | result | count |
|---|---|---|---|
| kyverno | rbac-standards-enforcement | skip | 486 |
| kyverno | namespace-oud-group-allowlist | skip | 102 |
| kyverno | rbac-standards-enforcement | pass | 58 |
| kyverno | rbac-standards-enforcement | fail | 17 |
| KyvernoValidatingPolicy | restrict-nco-config-writers | pass | 9 |
| kyverno | namespace-oud-group-allowlist | pass / fail | 3 / 1 |

`skip` dominates (588 of 676): the legacy policies' rules evaluate every Namespace and skip the ones
their preconditions exclude. A dashboard that shows `skip` as a number shows noise; it is the
"not applicable" state.

## 4. Finding 10 — do the two chart flags make a CEL policy report twice?

Both flags ARE on (chart 3.9.1 defaults, read with `helm get values -a`):
`generateValidatingAdmissionPolicy.enabled: true`, `validatingAdmissionPolicyReports.enabled: true`.

**The flags alone generate nothing for the CEL kinds.** `restrict-nco-config-writers` has
`status.generated: false` and none of the cluster's 11 `ValidatingAdmissionPolicy` objects is
Kyverno's (they are OpenShift's own). The CRD says why: `spec.autogen.validatingAdmissionPolicy.enabled`
— *"Enabled specifies whether to generate a Kubernetes ValidatingAdmissionPolicy. Optional. Defaults
to false."* Generation is **per policy, opt-in**; the chart flag only permits it. (Whether that policy's
`resource.Post(...)` SubjectAccessReview would survive as a VAP is a question the generator never asks: it
checks its own RBAC, this opt-in and the pod-controller autogen only, and copies `variables`/`validations`
verbatim — `kyverno-discovery-2026-09-20.md` §3.)

Measured with a probe (§5): with `autogen.validatingAdmissionPolicy.enabled: true` Kyverno creates
`vpol-<name>` and `vpol-<name>-binding`, owner-referenced to the policy, labelled
`app.kubernetes.io/managed-by=kyverno`, `validationActions: [Audit]` as the policy's. **Within 150 s
of admitting a violating object through that VAP, the PolicyReport carried NO row for the policy
from either source**, and no result with `source: ValidatingAdmissionPolicy` exists anywhere on the
cluster. The row the SAME policy had produced for an object admitted before the VAP existed (via
the webhook, `source: KyvernoValidatingPolicy`) stayed. So on this cluster and in that window: one
policy does not report under two sources; enabling VAP generation moved admission to the API server
and the report for that admission had not been written by the reports-controller. Whether it arrives
later from the background scan was not measured (the probe was removed) — **a collector must not
assume a VAP-enforced policy reports promptly, and must never double-count by source.**

## 5. The probe, so it can be repeated

An Audit-only `NamespacedValidatingPolicy` in `klt-pass-both` requiring an `owner` label on
ConfigMaps, then a cluster-scoped `ValidatingPolicy` with the same rule scoped by
`namespaceSelector`, two violating ConfigMaps, `autogen.validatingAdmissionPolicy.enabled` flipped on
the cluster one. Both policies reached `WebhookConfigured=True`, `RBACPermissionsGranted=True`
("Policy is ready for reporting"); the first violating ConfigMap's report cited both policies
(`fail`, `source: KyvernoValidatingPolicy`, the namespaced one namespace-qualified); the second, admitted
after the VAP, cited only the namespaced policy. Everything was deleted afterwards; the VAP and its
binding went with their owner (0 left, measured).

## 6. Seen on the way — for `openshift-rbac-automation`

The reports-controller logs, every reconcile:
`admissionpolicy/validate.go:48 failed to resolve kind for group redhatcop.redhat.io, version *, resource groupsyncs` (and `namespaceconfigs`, `groupconfigs`, `userconfigs`). `restrict-nco-config-writers`
matches with `apiVersions: ["*"]`; Kyverno's VAP-validation path cannot resolve a wildcard version.
Harmless to enforcement (the policy is webhook-only), noisy in the log, and a wildcard the policy
does not need — `v1alpha1` is the only version those CRDs serve. An issue on that repository.

## What this settles for #170

- Read `wgpolicyk8s.io/v1alpha2` only; treat `openreports.io` as optional.
- Model a result with the nine fields above (a legacy row adds `rule`); the shipped key is
  `(policy kind, policy, resource uid)` with the worse of two results keeping the row —
  `kyverno-discovery-2026-09-20.md` §5 supersedes the `(source, policy, result)` key first written here; join
  namespaced CEL policies by `namespace/name`.
- Reports are per object: a "finding" is a `fail` result, an object is its `scope`, and `skip` is
  "not applicable", not a count.
- Finding 10: no double reporting was observed, and VAP-enforced admissions may not be reported at
  all — the module treats `generated: true` as a state to show, not a second source to sum.
