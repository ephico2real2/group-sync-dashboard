# Kyverno policy dashboard — research record, 2026-09-17

What was researched, against what, and what it means for the module #165 describes. Every claim
below is cited to a file and line in the **Kyverno v1.19.1 source checkout** (chart 3.9.1,
the chart's `version` and `appVersion` in `charts/kyverno/Chart.yaml`) or to the **shipped CRDs**, re-verified on this date. Where the
earlier issue text overstated a source, this record corrects it and says so.

## Evidence on disk

| artefact | what it is |
|---|---|
| `kyverno-1.19.1/` (68 MB) | the tagged source tree; `charts/kyverno/Chart.yaml` → `version: 3.9.1`, `appVersion: v1.19.1` |
| `crds/` | the CRDs the chart ships: `wgpolicyk8s.io_{policyreports,clusterpolicyreports}`, `reports.kyverno.io_{ephemeralreports,clusterephemeralreports}`, `policies.kyverno.io_{validatingpolicies,imagevalidatingpolicies,policyexceptions}`, the legacy `kyverno.io_*` family |
| `kyverno-values.yaml` (92 KB) | chart 3.9.1 default values |
| the CRC cluster | Kyverno **is installed** (320 Mi requested; `kyverno`, `kyverno-cel-tutorial` namespaces) — measured 2026-09-17 |

## Scope decision (operator)

**CEL family only** — `ValidatingPolicy`, `MutatingPolicy`, `GeneratingPolicy`, `DeletingPolicy`,
`ImageValidatingPolicy`. The legacy `ClusterPolicy` / `Policy` / `CleanupPolicy` are not supported.

**Correction to #165's wording.** The issue said the legacy family "is deleted in v1.20 (~Nov 2026),
per the source". The source does not say that. What it says:

- `crds/kyverno.io_clusterpolicies.yaml`, on the `v1` entry of `spec.versions` — `deprecated: true` with
  `deprecationWarning: kyverno.io/v1 ClusterPolicy is deprecated and will be removed`
- `api/kyverno/v1/policy_types.go:28` — *"deprecated and will be removed in a future release;
  migrate to NamespacedValidatingPolicy and the other namespaced policy types (policies.kyverno.io)"*

"A future release", not a version. The decision to build only on the CEL family is unchanged —
the family is deprecated with a removal warning served by the API — but the date is not sourced.

## The findings, each cited

### 1. Build on `PolicyReport`, not on the policy CRDs
`wgpolicyk8s.io_policyreports.yaml` serves **one** entry in `spec.versions`, `v1alpha2`, and that entry
carries `storage: true` and `subresources: {}` — so a reader needs no `/status` subresource right. Every
policy type reports into this one result schema; the parser never needs to know policy kinds.

### 2. A blocked request produces no report
`pkg/webhooks/resource/vpol/handler.go:89-124`: `blocked := false` … set `true` on a failing
enforce result (`:92`) … and the report is built only under
`if !blocked && validation.NeedsReports(...)` (`:113`) before `BuildAdmissionReport` (`:124`).
The same pattern in `pkg/webhooks/resource/ivpol/handler.go` (`:156` comment: *"skips handleAudit
for a blocked request"*). **So a dashboard built only on reports systematically misses the
policies that actually deny.** Kyverno never populates `AdmissionResponse.AuditAnnotations` —
zero hits for `AuditAnnotations` under `pkg/webhooks` and `pkg/utils/admission` — so the denial's
only durable trace is the kube-apiserver audit log's `responseStatus.message`. We already read a
node-level audit log (`oc adm node-logs --path=`) for the oauth-server, so this is a known path.

### 3. `--maxBackgroundReports` silently truncates
`cmd/background-controller/main.go:149` — default **10000**; `:268` — `return count > maxBackgroundReports`
is the breaker predicate. When it trips, the drop is counted in `kyverno_breaker_drops`
(`pkg/metrics/breaker.go:35`; the companion `kyverno_breaker_total` at `:42`) and the call returns
success. **Scrape `kyverno_breaker_drops`** or a truncated cluster reads as a clean one.

### 4. Reports have no history
A report is owned by the resource it describes — `pkg/utils/report/new.go:50` sets the owner
reference (`controllerutils.SetOwner`, `pkg/utils/controller/metadata.go:79`) — so it is
garbage-collected with the resource. Emptied reports are deleted outright:
`pkg/controllers/report/aggregate/controller.go:899-901` — `if len(results) == 0 { … deleteReport }`.
**We must snapshot** into our own store, as Policy Reporter did when it added a database.

### 5. `rule` is empty for the CEL family
`pkg/cel/policies/vpol/engine/engine.go:201` — `ruleName := ""`. Grouping by `(policy, rule)` —
the obvious design — collapses every CEL result into one bucket. Group by policy + resource.

### 6. The autogen collapse cannot work for CEL
The only `autogen-` handling is by rule-name prefix, in the CLI:
`cmd/cli/kubectl-kyverno/commands/apply/print.go:97-105` and `commands/test/command.go:312`.
With `rule` empty (finding 5) there is no prefix to match, so one bad Deployment yields failing
results on the Deployment, its ReplicaSet and its Pod, and nothing folds them. A visible,
explained controlled-owner filter is needed instead of a silent collapse.

### 7. Two wire formats, switched, never dual-written
`cmd/internal/flag.go:187` — `--openreportsEnabled` (bool, default `false`, *"Use
openreports.io/v1alpha1 for the reporting group"*), consumed in `cmd/internal/setup.go:127` and
switched on throughout `pkg/utils/report/{create_permanent,results,delete,update}.go`. One group
or the other is written. **Discover the served API at runtime and refuse clearly if none is found.**

### 8. No server-side label to filter on
Permanent reports carry only `app.kubernetes.io/managed-by: kyverno`
(`pkg/utils/report/metadata.go:137`, `pkg/controllers/report/aggregate/controller.go:140`), so
every LIST must paginate and filter client-side.

### 9. Watches must survive HTTP 410
`pkg/controllers/report/resource/controller.go:385` handles `http.StatusGone` by re-listing —
Kyverno's own controller needed this; ours must do the same (re-LIST, then re-WATCH).

### 10. Two flags default **on** in chart 3.9.1 — a double-count risk to test on CRC
In `kyverno-values.yaml`, `validatingAdmissionPolicyReports.enabled: true` and
`generateValidatingAdmissionPolicy.enabled: true`. A `ValidatingPolicy` with
`autogen.validatingAdmissionPolicy.enabled` may then report under **both** the Kyverno policy and
the generated `ValidatingAdmissionPolicy`. Unverified — the open question in #165, answerable in
minutes now that Kyverno is on CRC.

## What this settles for the module

- Read `wgpolicyk8s.io/v1alpha2` (and `openreports.io/v1alpha1` when that flag is on); inventory
  the CEL policy CRDs only to list what is configured.
- Two data paths, not one: reports (audit/background) **and** the kube-apiserver audit log
  (denials).
- Snapshot results; key by policy + resource; collapse controlled owners visibly; scrape
  `kyverno_breaker_drops`; discover the API group at runtime; paginate and handle 410.
- **Our own metric labels, nameless** — Policy Reporter's default `detailed` mode labels by
  resource name and namespace, which the public `/metrics` rule forbids here.

## Not yet done
No mock: the data shape has to be observed on CRC first (finding 10, and the actual shape of
`results[]` on this cluster's reports). The next step is a `PolicyReport` dump from CRC.
