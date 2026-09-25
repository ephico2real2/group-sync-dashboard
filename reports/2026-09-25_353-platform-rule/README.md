# #353 on the lab: the platform rule deployed, the values path, a planted grant — 2026-09-25

Captured on the CRC lab (OpenShift 4.22.7) against main twice: `c00aa2e` (#360 merged — the unmanaged finding on
every subject kind with the platform rule, application 0.33.0, chart 0.54.0, schema migration 20) and then `de303e9`
(#362 merged — `environments/crc.yaml` gains the estate's platform namespaces, the reference answer `values.yaml`'s
own comment documents). Both were deployed with `local-development/release-crc.sh --argocd` from the main checkout at
that commit: images built and stamp-verified, the Application Synced/Healthy (06:06:09Z, then 06:18:01Z), the commit
verified in-pod, and the two kept PVCs identical before and after each deploy (`walk/pvc-*.txt`: UIDs
`f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, both created 2026-09-19T00:56:50Z).
The lab ran `244d4ab9c0` (0.32.0) before.

This is the lab proof SPEC_U1 §5 and the orchestrator's mandate for #353 ask for: the finding count and its breakdown
by namespace under the shipped defaults; the same after the values file names the estate's own platform namespaces;
and a planted unlabelled ServiceAccount grant in a namespace of its own — reported, then silent once its binding
carries the operator's label — beside a grant to an account in a platform namespace, built-in by rule. Every number
and time below is quoted from a file in `walk/` (the `.txt`/`.out` files, the two release logs, the pod-log lines the
counts script copied) or read off a picture in `screenshots/`; sums are worked from those values.

**Times.** The Argo CD, PVC and `oc` stamps are UTC (`Z`). The pod's own log lines are its `TZ`, America/New_York
(`-0400`), four hours behind — `02:06:04,325-0400` is 06:06:04Z — and the pages print EDT. The session log's times
are America/Chicago.

## Before anything was deployed (`walk/schema-before.txt`, `walk/argo-before.txt`, `walk/pod-before.txt`)

Read at 05:47:10Z from the running 0.32.0 pod (`244d4ab9c0`), the Application Synced/Healthy: the database at
`/data/gsd.db` reported `user_version 19` and `rbac_group_binding` **without** `is_platform` (its columns:
`cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name, group_name, observed_at,
managed_source, exception, audit_stamped`). That is the pre-deploy read the spec's §5 preamble requires — migration 20
was edited in place after #360 was first opened, and a database already at 20 without the column would not gain it —
and 19 is the "deploy as is" answer (the orchestrator's ruling, 2026-09-25).

## 1. The shipped defaults (`walk/release-c00aa2e.log`, `walk/counts-defaults.txt`, `walk/drift-vs-dump.txt`)

The new pod started 06:05:27Z; its log's first lines: `schema migration 20 applied: rbac_group_binding holds
ServiceAccount and User subjects beside Group ones` (02:05:28 pod time) and `refreshed 919 bindings for dashboard (206
Group, 678 ServiceAccount, 35 User subjects)` (02:06:04). The counts script then read, through the pod's loopback:

| Where | What it read |
|---|---|
| `/api/clusters/dashboard/bindings/findings` | total 919; `ok` 45, `dangling` 0, `unresolved` 6, `built_in` 743, `unmanaged` **125** |
| the `unmanaged` rows (`finding=unmanaged&limit=5000`) | **125 rows on 118 bindings**: 114 ServiceAccount, 11 User, 0 Group |
| ServiceAccount rows by the account's namespace | `metallb-system` 23, `group-sync-operator` 18, `kyverno` 15, `cert-manager` 14, `namespace-configuration-operator` 8, `group-sync-dashboard` 8, `mongodb-poc` 7, `cert-manager-operator` 6, `hostpath-provisioner` 6, `envoy-gateway-system` 6, `modernize-demo` 2, `ldap-testing` 1 |
| User rows | `jdoe` 3, `ocp-oauth-bind-serviceid` 2, `asmith`, `bwilliams`, `dana.lee`, `developer`, `jane.smith`, `tmp-contractor-9931` 1 each |
| the `built_in` rows | 743: 557 ServiceAccount, 24 User, 162 Group — 581 of them by the stored `is_platform` flag (the platform rule), the 162 Groups by the `system:` rule |
| `/api/clusters` (`dashboard`) | `unmanaged_bindings` 125, `unresolved_bindings` 6, `dangling_bindings` 0, `builtin_bindings` 743 |
| `/metrics` | `gsd_bindings_total{cluster="dashboard",finding="unmanaged"} 125.0`, `built_in` 743.0, `ok` 45.0, `unresolved` 6.0, `dangling` 0.0 |
| the pod's log | one `UNMANAGED GRANT DISCOVERED` WARNING per listed binding on that refresh (the script keeps the last eight; the first names `ClusterRoleBinding cluster-reader (cluster-wide) grants cluster-reader to user dana.lee`) |
| the page (`screenshots/defaults-access-granted.png`, `defaults-unmanaged-section.png`) | `v0.33.0 · c00aa2e4ff`; the tiles 919 = 45 granted + 131 to review (125 unmanaged + 6 unresolved) + 743 built-in; the section "Unmanaged · 125" |

**Against the spec's 124 rows on 117 bindings** (§2.2, measured on the 2026-09-24 dump): the live lab holds 919
stored rows where the dump held 915, and the unmanaged set differs by exactly one row —
`RoleBinding envoy-gateway-system/system:openshift:scc:nonroot-v2` → ClusterRole `system:openshift:scc:nonroot-v2` →
ServiceAccount `envoy-gateway-system/envoy-gwapi-demo-eg-8fbae7fe`, created 2026-09-25T02:17:09Z with no label — the
SCC RoleBinding OpenShift writes when a workload is admitted under the `nonroot-v2` SCC, for the `gwapi-demo` Envoy
proxy's account (its labels name `gateway.envoyproxy.io/owning-gateway-namespace: gwapi-demo`). It was created after the
dump and is the lab drift the mandate says to leave alone; `walk/drift-vs-dump.txt` is the row-by-row comparison
(the dump's 124 rows are all present; nothing else is new). So the rule's own count is the spec's, and the lab's is
that plus one.

## 2. The values path (`walk/release-de303e9.log`, `walk/counts-values.txt`)

#362 was merged only after the 125 above was recorded, so both counts are evidence. The redeploy: Synced/Healthy at
06:18:01Z, `de303e9b22` verified in-pod, the PVC UIDs identical (`walk/pvc-before-values.txt`,
`walk/pvc-after-values.txt`). The rendered ConfigMap's `clusters.yaml` carries
`platformNamespaces: {"additionalNames":["kyverno","group-sync-dashboard"],"additionalSuffixes":["-operator","-manager","-provisioner"]}`
under its `PLATFORM-CLASSIFICATION (#255, #353)` comment, and the new pod's first refresh (02:17:46 pod time) read the
same 919 bindings:

| Where | What it read |
|---|---|
| `/api/clusters/dashboard/bindings/findings` | total 919; `ok` **38**, `dangling` 0, `unresolved` 6, `built_in` **825**, `unmanaged` **50** |
| the `unmanaged` rows | **50 rows on 47 bindings**: 39 ServiceAccount, 11 User |
| ServiceAccount rows by namespace | `metallb-system` 23, `mongodb-poc` 7, `envoy-gateway-system` 6, `modernize-demo` 2, `ldap-testing` 1 — the seven namespaces the values file names are gone from the list |
| User rows | the same eleven |
| the `built_in` rows | 825: 639 ServiceAccount, 24 User, 162 Group — 663 by the flag |
| `/metrics` | `unmanaged` 50.0, `built_in` 825.0, `ok` 38.0 |
| the page (`screenshots/values-access-granted.png`, `values-unmanaged-section.png`) | `v0.33.0 · de303e9b22`; 919 = 38 + 56 + 825; "Unmanaged · 50" |

Against the spec's 49 rows on 46 bindings: the same one drift row (`envoy-gateway-system` reads 6 where the dump
read 5). Nothing else changed but what §5.7 says should: the chart's own seven labelled rows in `group-sync-dashboard`
moved from `ok` to `built_in` (the platform arm precedes provenance), so `ok` fell 45 → 38 and the Granted tile with it;
`unmanaged` fell by 75 (125 → 50) and `built_in` rose by 82 (743 → 825 = 75 + 7).

## 3. The planted grant (`walk/plant.out`, `walk/plant.sh`, `walk/plant2.sh`)

`plant.sh` created the namespace `gsd-evidence-353`, the ServiceAccount `u1-evidence-sa` in it and
`ClusterRoleBinding u1-evidence` (`view` → that account) at 06:18:44Z, then failed on its own check line — an f-string
with escaped quotes inside its braces, a `SyntaxError` the orchestrator caught while the wait ran blind. `plant2.sh`
continued from the check with that line rewritten (the fields bound to a variable first), re-creating nothing; the
record is the second half of `walk/plant.out`. One binding refresh is 300 s, so each step waited for the next one.

| Step | What the store said (through `/bindings/findings`) | When |
|---|---|---|
| the unlabelled grant, in a namespace of its own | `unmanaged 0 ServiceAccount gsd-evidence-353/u1-evidence-sa managed_source=None`; the pod's WARNING: `UNMANAGED GRANT DISCOVERED — dashboard: ClusterRoleBinding u1-evidence (cluster-wide) grants view to ServiceAccount gsd-evidence-353/u1-evidence-sa, outside the policy system` (02:23:46 pod time) | 06:23:47Z |
| labelled `rbac.ocp.io/config-source=platform-team` | `ok 0 … managed_source=platform-team` | 06:29:53Z |
| the platform half: `ClusterRoleBinding u1-platform` (`view`) → a new account `openshift-monitoring/u1-platform-sa` | `built_in 1 ServiceAccount openshift-monitoring/u1-platform-sa managed_source=None`; 0 log lines name it (a built-in row is never announced) | 06:34:48Z |
| removed: both ClusterRoleBindings by name (they are cluster-scoped; deleting the namespace would not remove them), the platform account, the namespace | both rows `absent`; `oc get` answers NotFound for the namespace, both bindings and the account | 06:40:53Z |

`walk/counts-after.txt` and `walk/clusters-after.txt`, read afterwards: `dashboard` back at 50 rows on 47 bindings,
`ok` 38, `built_in` 825; `shared-qa` and `shared-rnd` — the same cluster joined twice, by design — read the same
50 / 6 / 825; the three mock entries read 1 unmanaged each (the mock cluster's own hand-made grant, as before this
change).

## What this shows against #353's Definition of Done

- *Every non-platform ServiceAccount and User grant without the label reported*: 125 rows on 118 bindings under the
  shipped defaults, each named in the log and on the page; the planted one appeared on the refresh after it was made.
- *Platform identities silent, including a namespace added through `additionalNames`*: 581 rows built-in by the flag
  under the defaults; 663 once `environments/crc.yaml` named the estate's own — `kyverno` and `group-sync-dashboard`
  through `additionalNames`, the five `-operator`/`-manager`/`-provisioner` namespaces through `additionalSuffixes` —
  and a grant to an account in `openshift-monitoring` built-in on its first refresh.
- *A labelled grant no longer reported*: `u1-evidence` went `unmanaged` → `ok` on the refresh after its label.
- The PVCs were never replaced (identical UIDs across both deploys) and the pre-deploy schema read was 19.

| File | What it shows |
|---|---|
| `walk/lib.sh` | the helpers: the scratch kubeconfig, the pod, the loopback API, the PVC and Argo reads, the schema read |
| `walk/schema-before.txt`, `argo-before.txt`, `pod-before.txt` | the pre-deploy reads: schema 19 without `is_platform`, Synced/Healthy at `244d4ab9c0`, the 0.32.0 pod |
| `walk/release-c00aa2e.log`, `release-de303e9.log` | the two deploys: build, push, the Argo CD sync, the in-pod check (image layer lines removed) |
| `walk/pvc-before.txt`, `pvc-after.txt`, `pvc-before-values.txt`, `pvc-after-values.txt` | the two PVCs' UID, volume and creation time around each deploy — identical |
| `walk/counts.sh`, `counts-defaults.txt`, `counts-values.txt`, `counts-after.txt` | the counts through the API, the rows by kind and namespace, `/metrics`, the pod's log lines |
| `walk/drift-vs-dump.txt` | the live unmanaged rows against the 2026-09-24 dump: the one extra row, its object and its account |
| `walk/shots.sh`, `shots-values.out` | the page captures and the tile values they printed |
| `walk/plant.sh`, `plant2.sh`, `plant.out` | the planted grant: created, reported, labelled, the platform half, removed |
| `walk/clusters-after.txt` | every cluster entry's review counts once the planted objects were gone |
| `screenshots/defaults-access-granted.png` | the Access granted tiles under the shipped defaults: 919 = 45 + 131 + 743 |
| `screenshots/defaults-unmanaged-section.png` | the page's Unmanaged section: 125, ServiceAccounts named `namespace/name` beside the people |
| `screenshots/values-access-granted.png` | the same tiles with the estate's namespaces named: 919 = 38 + 56 + 825 |
| `screenshots/values-unmanaged-section.png` | the Unmanaged section: 50 |
