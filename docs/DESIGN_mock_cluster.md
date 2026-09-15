# DESIGN — Portable mock OpenShift API server for group-sync-dashboard

GitHub issue #116. Grounds every request shape in a full read of
`local-development/gsd/kube.py` (lines 1–1829), `config.py`, `auditlog.py`, `loginlog.py`,
`poller.py`, and `gsd/reporting/`. Line references below are absolute-file-verified.

---

## 1. Goal and non-goals

### 1.1 Goal

Stand up a **self-contained HTTP(S) server that answers exactly the request surface
`kube.py` issues** — the ~16 read endpoints, the two node-log-proxy shapes, the pod-log
stream, and the SubjectAccessReview POST — from a **declarative fixture** (one YAML/JSON
file describing groups, users, identities, bindings, roles, namespaces, nodes, an OAuth CR,
and canned audit lines). It must be:

- **Portable** — a pure-Python process with a `cryptography`-only extra for TLS. No cluster,
  no VM, no container runtime required for the CI/local form. Runs on a laptop and in a
  GitHub Actions Linux runner unchanged.
- **Faithful** — every response satisfies the parse contract in §3 so `kube.py` reaches its
  real code paths: `_get`/`_list_all`/`_list_all_with` paging, the `_groupsync_view` /
  `_group_view` / `_binding_views` parsers, the streaming node-log resume/rotation machinery,
  and the TierResolver SAR decision. A malformed 200 must be a *deliberate* fixture choice,
  never an accident of the mock.
- **A real RBAC authorizer for SAR** — good enough that the four measured personas
  (`kubeadmin`, `dana.lee`, `lateef.o`, `jane.smith`) resolve to their measured tiers from a
  fixture of `(Cluster)RoleBinding` → `(Cluster)Role` rules, not from a hardcoded answer map.
- **Two run forms from one codebase** — an in-process pytest fixture on an **ephemeral port**
  (CI/local), and a **container on :6443** (lab e2e), sharing the same handler and fixture.

### 1.2 Non-goals

- **The report service needs nothing from this mock.** Confirmed by reading `gsd/reporting/`
  in full: the package never imports `kube`/`ClusterClient`/`ClusterConfig`, never resolves a
  token, and its only inputs are a snapshot SQLite file and the local ArtifactStore
  (`reporting/snapshot.py`, `runs.py`, `server.py`). To integration-test the
  report you seed a `gsd-<stamp>.db` snapshot — you do **not** stand up this mock. This mock
  is wired to the **dashboard/poller only**.
- Not a general OpenShift emulator. It serves the dashboard's read surface plus SAR; it does
  not implement watch, apply, admission, or write verbs (the dashboard issues none — SAR is a
  query that creates no object, `kube.py`).
- Not a conformance target. Fidelity is defined by "`kube.py` parses it without error and
  reaches the intended branch", not by upstream API-machinery semantics.

### 1.3 Why not minishift / CRC / envtest / a real cluster

| Option | Why rejected for this purpose |
|---|---|
| **minishift** | OpenShift 3.x, dead upstream. Wrong API groups (`redhatcop.redhat.io/v1alpha1` GroupSync CRs, `user.openshift.io/v1`, the node-log proxy) are not what a v3 minishift serves. Not portable to CI. |
| **CRC (CodeReady Containers)** | This is the *real* lab cluster the e2e-walk already uses — heavyweight (9GB+ VM), slow to start, single-node, and **its API-server cert is issued by CRC's own cert-manager CA**, which is a *cluster-specific* trust root. Pinning the mock's trust to CRC's CA would make the test non-portable (it would only pass on a machine that has that exact CRC instance). The mock must generate its **own** ephemeral CA so the trust path is reproducible anywhere — see §4.4. CRC stays the target of `e2e-walk`, not a unit/integration dependency. |
| **envtest (controller-runtime)** | Boots a real `kube-apiserver` + `etcd`. But (a) it is a *Kubernetes* apiserver, not OpenShift — no `user.openshift.io`, no `config.openshift.io/v1 OAuth`, no `redhatcop.redhat.io` CRDs, and critically **no `/api/v1/nodes/<node>/proxy/logs/...` kubelet file-server** and no real oauth-server audit log. We would have to register every CRD and *still* fake the node-log proxy and the audit content. (b) It needs the `kube-apiserver`/`etcd` binaries on the box — not portable to a bare CI runner without a setup step. (c) SAR against envtest would exercise the real authorizer, but seeding fixture RBAC into it is heavier than evaluating our own rules over a YAML file. envtest tests *our client against a real apiserver*; that value is real but orthogonal, and it cannot cover the OpenShift-specific and node-proxy surface that is most of `kube.py`. |
| **Record/replay (VCR-style cassettes)** | Brittle: any change to params (the `limit=500`/`continue` paging, the `labelSelector`, the SAR body's `spec.groups` union) invalidates the cassette, and cassettes cannot *compute* a SAR verdict for a new persona. A fixture-driven authorizer stays correct as the client evolves. |
| **httpx.MockTransport only** | Already used in the repo (`test_membership.py`, `test_identities_read.py`) and it is the right tool for *unit* tests of the parsers because it short-circuits the socket. But it exercises **no TLS, no CA, no token, no real HTTP server**, so it cannot cover the enterprise-CA trust path (§4), the container e2e form, or a browser/`oc`-driven manual poke at `:6443`. The mock server *complements* MockTransport; it does not replace it. |

**Net:** a purpose-built fixture-driven server is the only option that is portable (no VM, no
binaries), OpenShift-shaped (right groups + node-proxy + audit format), TLS-real on a
reproducible CA, and able to *compute* SAR verdicts. The container form on :6443 additionally
lets `oc login`/browser/e2e poke it like a tiny cluster.

---

## 2. Architecture at a glance

```
                       fixture.yaml  (groups, users, identities, bindings,
                             │        roles, namespaces, nodes, oauth, audit lines)
                             ▼
                     ┌───────────────┐
                     │  Fixture      │  loads + validates → in-memory model
                     └───────┬───────┘
                             ▼
   ClusterConfig    ┌───────────────────────────────────────────────┐
   (api_url,   ───► │  MockClusterHandler (http.server BaseHTTPReq…)  │
    token,          │   • auth gate (Bearer)                         │
    caBundleFile)   │   • router → list / get / sar / nodelog / podlog│
                    │   • SarAuthorizer (RBAC over fixture)          │
                    │   • AuditLog server (canned lines, Range)      │
                    │   • /_mock/* control + inspection page         │
                    └───────────────────────────────────────────────┘
                             ▲
              ┌──────────────┴───────────────┐
              │                              │
   Run form A: in-process on :0     Run form B: container on :6443
   (pytest fixture, ephemeral)      (podman/docker, lab e2e)
              │                              │
     ephemeral self-signed CA        same CA baked in / mounted
     → ca.crt handed to dashboard    → ca.crt handed to dashboard
        as caBundleFile                 as caBundleFile
```

Single handler class; the two run forms differ only in **how the server is started** and
**how the CA reaches the dashboard**. The RBAC authorizer and audit server are plain classes
usable in isolation (unit-testable without a socket).

---

## 3. The full request surface the mock must satisfy

Every row is a request `kube.py` actually issues. **Verb is GET unless stated.** List params
are `limit=500` (+`continue=<tok>` on later pages) unless noted. "Parse contract" is the
minimum that makes `kube.py` parse without error and reach the healthy branch.

| # | Endpoint (path) | kube.py caller | Kind | Parse contract (minimum healthy response) |
|---|---|---|---|---|
| a | `/apis/redhatcop.redhat.io/v1alpha1/groupsyncs` | `fetch()` `_list_all` | list | `200` + `{"items":[…]}`. Items: `metadata.{name,namespace,generation}`, `spec.schedule`, `spec.providers[].name`, `spec.providers[].ldap.{rfc2307\|activeDirectory\|augmentedActiveDirectory}.groupsQuery.filter`, `status.lastSyncSuccessTime`, `status.conditions[]` (type `ReconcileError`/`ReconcileSuccess`). **CRD-absent branch:** plain `404` (body present) → `groupsyncs=None`, Groups still fetched. |
| b | `/apis/user.openshift.io/v1/groups` | `fetch()`, `fetch_groups_of_user()` | list | `200` + `{"items":[…]}`. Items: `metadata.name`, `metadata.labels["group-sync-operator.redhat-cop.io/sync-provider"]`, `metadata.annotations[sync-time / openshift.io/ldap.uid / groupsync-dashboard.io/silence-group-count-cliff]`, **top-level** `users` (array of strings, or null). |
| c | `/apis/user.openshift.io/v1/users` | `fetch_users()` | list | `200` + `{"items":[…]}`. Items: `metadata.{name(required),creationTimestamp}`, top-level `fullName`, top-level `identities` (array). **403 tolerated** → `None`. |
| d | `/apis/user.openshift.io/v1/identities` | `fetch_identities()` | list | `200` + `{"items":[…]}`. Items: `user.name` (required, stripped), `metadata.creationTimestamp` **must be ISO-8601** (`…Z`/offset) or item silently dropped. **403 tolerated** → `None`. |
| e | `/api/v1/namespaces` | `fetch_namespaces(label_keys)` | list | `200` + `{"items":[…]}`. Items: `metadata.{name(required),creationTimestamp,labels}`, `status.phase`. Only configured label keys are read. **403 tolerated** → `None`. |
| f | `/apis/rbac.authorization.k8s.io/v1/rolebindings` | `fetch_bindings()`, `fetch_user_bindings()` | list | `200` + `{"items":[…]}`. Items: `metadata.{namespace,name,labels[rbac.ocp.io/config-source, rbac.ocp.io/unmanaged], annotations[rbac.ocp.io/unmanaged-exception]}`, `roleRef.{kind,name}`, `subjects[].{kind,name}`. **No 403/404 tolerance** — any error propagates. |
| g | `/apis/rbac.authorization.k8s.io/v1/clusterrolebindings` | same as (f) | list | Same shape as (f); `metadata.namespace` absent/`""`. |
| h | `/apis/redhatcop.redhat.io/v1alpha1/namespaceconfigs` | `fetch_operator_configs()` | list | `200` + `{"items":[…]}`. Items: `metadata.name`, `status.conditions[]` (ReconcileError/Success). **Plain 404** → this CRD skipped. |
| i | `/apis/redhatcop.redhat.io/v1alpha1/groupconfigs` | `fetch_operator_configs()` | list | Same as (h). If **both** h and i are 404 → `None`. |
| j | `/api/v1/nodes` | `fetch_nodes(sel)` `_list_all_with` | list | `200` + `{"items":[…]}`; items `metadata.name`. **Query carries `labelSelector=<sel>&limit=500` on every page** (incl. continue pages). **403 tolerated** → `None`. |
| k | `/apis/config.openshift.io/v1/oauths/cluster` | `fetch_access_group_dn()`, `fetch_oauth_providers()` | **single GET** (not a list) | `200` + object with `spec.identityProviders[]` (each `.name`, `.ldap.url`). **No `items` key required.** 403 tolerated → `None`; plain 404 → `None`. |
| l | `/api/v1/namespaces/<ns>/pods` | `fetch_oauth_pods(ns)` `_list_all` | list | `200` + `{"items":[…]}`; items `status.phase` (kept iff `Running`), `metadata.name`. 403 tolerated → `None`. |
| m | `/api/v1/namespaces/<ns>/pods/<pod>/log` | `fetch_pod_log()` | **stream, TEXT** | `client.stream`; params `timestamps=true` (+`sinceSeconds`). Body = lines each prefixed with an **RFC3339 UTC** timestamp + space. `>=400` → parsed as k8s `Status` JSON (`.reason`, `.message`). |
| n | `/api/v1/nodes/<node>/proxy/logs/<dir>/` | `list_node_log_files()` | **HTML** | Single `get`, **Accept: `*/*`** (`NODE_LOG_HEADERS`). Body = HTML with `<a href="…">` entries (kubelet `http.FileServer` listing). `application/json` → **406** is a real failure this code was written around. |
| o | `/api/v1/nodes/<node>/proxy/logs/<path>` | `fetch_node_log_file()` | **stream, bytes** | `client.stream`, Accept `*/*`, optional `Range: bytes=<off>-`. `200`→bytes; `206`→partial; **`416` MUST carry `Content-Range: bytes */<total>`**; `416` without it → client retries once **unranged**. HEAD is never issued (proxy answers 405). |
| p | `/apis/authorization.k8s.io/v1/subjectaccessreviews` **POST** | `create_subject_access_review()` | POST JSON | Request body §5.1. Response **`200`/`201`** + `{"status":{"allowed": <bool>}}` — value **must be a JSON boolean** or the client raises → fails closed to self. |

### 3.1 Cross-cutting parse rules (from §2 of the audit, verified)

- **Never a 3xx.** `follow_redirects` is httpx-default `False`; a `<400` redirect falls through
  to `.json()` and fails as non-JSON → UNREACHABLE. Every JSON endpoint answers `200`.
- **List bodies MUST carry `items`.** A `200` without `items` → `ClusterError(UNREACHABLE, "…without an 'items' field…")` (`_list_all`, kube.py). `items` may be `[]` or `null`; any other type → UNREACHABLE.
- **Paging.** To end paging omit `metadata` or send `metadata:{}`. To test paging: `{"items":[…],"metadata":{"continue":"<tok>"}}` then a final page (carrying `limit=500&continue=<tok>`, and for nodes also `labelSelector`) with no `continue`.
- **Tolerated-403 branches** (c,d,e,j,k,l and SAR): return `403` whose **body text contains the endpoint's own path** — the code matches `FORBIDDEN and path in exc.message`.
- **CRD-absent 404 branches** (a,h,i,k): return a plain `404` (any body) — the `_get` message starts `"HTTP 404 on <path>"`.
- **Auth failure:** `401` anywhere → `AUTH_FAILED`.

---

## 4. CA / TLS model

The whole point of a TLS mock (over MockTransport) is to exercise the **enterprise-CA trust
path** in `config.py` — the fallback that makes external clusters work
(`config.py`, `_trusted_ca_context` 65-108). We drive the **real** trust path, not
`insecure_skip_verify`.

### 4.1 The three trust modes in `verify()` (config.py, verified)

1. `insecure_skip_verify=True` → `verify()` returns `False` (no verification). *Escape hatch only.*
2. `ca_bundle_file=<path>` set → `ssl.create_default_context(cafile=path)`. Per-cluster explicit bundle, "always wins".
3. else → `_trusted_ca_context()` from `GSD_TRUSTED_CA_FILE` (colon-separated); if that yields `None`, returns `True` (system trust).

Modes 2 and 3 both build a `create_default_context` → **`CERT_REQUIRED` + hostname checking
are ON**. The mock's leaf cert **must** have a SAN matching the host in `api_url`.

### 4.2 Primary design: ephemeral self-generated CA handed over as `caBundleFile` (mode 2)

The mock generates, at startup, an **ephemeral CA** and a **leaf** signed by it, using the
`cryptography` library (already a transitive dep; declared explicitly in the extra):

- **CA:** an RSA-2048 (or EC P-256) self-signed cert, `CA:TRUE`, `keyCertSign`, valid ~1 day.
- **Leaf:** signed by the CA, CN `mock-openshift`, **SAN** = `IP:127.0.0.1`, `DNS:localhost`
  (in-process form) **and** `DNS:mock-openshift` (container form, so an in-cluster/e2e caller
  reaching it by service name verifies). `serverAuth` EKU.
- The **CA cert PEM is written to a file** (`ca.crt`) and its path handed to the dashboard as
  `ClusterConfig(ca_bundle_file=<ca.crt>)` — the real mode-2 path. hostname + chain
  verification succeed; a poll completes over verified TLS.

**Why `caBundleFile` (mode 2) as the default rather than `GSD_TRUSTED_CA_FILE` (mode 3):** it
is the simplest hand-over (one config field, no env var, no cache to clear) and it is exactly
the per-cluster idiom an operator uses for a cluster with its own CA. It exercises
`create_default_context(cafile=…)` — the same primitive mode 3 uses — so the TLS behaviour is
identical; only the *source of the path* differs.

### 4.3 Secondary: exercise mode 3 (the injected/enterprise fallback) on demand

For a test that specifically covers the `_trusted_ca_context` fallback (the "external cluster
signed by a corporate CA" story), the fixture flips a flag: leave `ca_bundle_file=None` and
set `GSD_TRUSTED_CA_FILE=<ca.crt>`. **Cache gotcha (verified, config.py):** `_ca_cache`
is a module global keyed on the raw env *string* and a null result is deliberately uncached.
A test matrix reusing the same `GSD_TRUSTED_CA_FILE` value across cases with different CA
contents serves a **stale** context — the fixture must `gsd.config._ca_cache.clear()` (or vary
the path) between cases. The pytest fixture does this in teardown.

### 4.4 Why NOT CRC's cert-manager CA — portability

CRC issues its API-server cert from its **own cert-manager CA**, unique to that CRC instance.
Trusting it would make a test pass only on the one machine holding that CRC. The mock's CA is
**generated fresh in the test process** and its `ca.crt` handed straight to the dashboard, so
the trust path is **reproducible on any machine** — a laptop, a bare GitHub runner, a
container — with no external cluster and no pre-provisioned trust root. CRC remains the target
of the `e2e-walk` skill (real deployed dashboard); it is not a dependency of this mock.

### 4.5 Negative controls the model enables

- **CA absent** (`ca_bundle_file=None`, `GSD_TRUSTED_CA_FILE` unset) → `verify()` returns
  `True` (system trust) → the ephemeral-CA leaf fails verification → `_get` raises
  `ClusterError(UNREACHABLE)`. This is the "TLS problem that presents as an outage" the
  fallback exists to fix, and a test asserts it.
- `insecure_skip_verify=True` → same server is reachable (verification off).

### 4.6 Auth side (verified, config.py:133-159 + kube.py:613-630)

The mock **requires and matches** `Authorization: Bearer <exact token>`. The dashboard's
`ClusterConfig` carries `token_env` (env var the test sets) or `token_file`. The auth gate:

- Missing/wrong bearer → **401** (→ `AUTH_FAILED`).
- Correct bearer but a request the fixture RBAC denies at *transport* level (a path marked
  forbidden in the fixture) → **403** with the path in the body (→ `FORBIDDEN`).

Both classified outcomes are thus reachable. **No mTLS:** `kube.py` never sets `cert=` (grep-
confirmed in the audit); the only TLS knob is `verify`, so the mock never requests a client
cert.

---

## 5. The SAR evaluator (a real RBAC authorizer over the fixture)

### 5.1 The exact request body (kube.py:1414-1418, verified)

```json
{
  "apiVersion": "authorization.k8s.io/v1",
  "kind": "SubjectAccessReview",
  "spec": {
    "user": "<viewer>",
    "groups": ["<resolved OpenShift Group memberships…>", "<virtual system:* groups…>"],
    "resourceAttributes": { "verb": "...", "resource": "...", "group": "...",
                            "namespace": "<optional>", "subresource": "<optional>" }
  }
}
```

Notes the evaluator relies on:
- The field is **`group`** (the k8s ResourceAttributes API-group field), not `apiGroup`. An
  empty `group` string is the **core** group (pods/namespaces), never "unset".
- `spec.groups` is **pre-resolved by the client** — it is the union of
  `fetch_groups_of_user(viewer)` (a **fresh** GROUP_API list, byte-exact membership match) and
  `_virtual_groups_for(viewer)`. The mock does **not** resolve membership for the SAR; it
  takes `spec.groups` as given and treats each as a Group subject. (Membership resolution is
  exercised separately by serving endpoint (b) — the SAR authorizer trusts the union.)
- `resourceAttributes` is built once from Settings; `namespace`/`subresource` are **omitted
  entirely** when empty.

### 5.2 What the authorizer computes (kube.py:1439-1446 reads only `status.allowed`)

Input: `spec.user`, `spec.groups`, `spec.resourceAttributes{verb,resource,group,namespace?,subresource?}`.

1. **Subject set** = one `User` named `spec.user` + one `Group` per name in `spec.groups`
   (including `system:authenticated`, `system:authenticated:oauth`, `system:serviceaccounts[:ns]`
   — all ordinary Group subjects here).
2. **Scope selection:**
   - No `namespace` → **cluster-scoped** check → consider **ClusterRoleBindings → ClusterRoles only**.
   - With `namespace` → additionally consider **RoleBindings in that namespace**.
   - (`clusterrolebindings` is itself cluster-scoped, so a namespaced RoleBinding can never grant it.)
3. **Match:** for every binding whose `.subjects` intersect the subject set, resolve to its
   `(Cluster)Role` rules. `allowed = TRUE` iff **any** rule satisfies **all** of:
   - `verb ∈ rule.verbs` or `"*" ∈ rule.verbs`
   - `spec.group ∈ rule.apiGroups` or `"*" ∈ rule.apiGroups`  (empty string = core group, matched literally)
   - `resource ∈ rule.resources` or `"*" ∈ rule.resources`
   - subresource: when a `subresource` is asked, the rule must carry the `"resource/subresource"`
     form; when none asked, a rule scoped to `resource/sub` does **not** grant the bare resource.
   - **`resourceNames` caveat:** a rule carrying `resourceNames` does **not** grant an
     *unqualified* `list`/`update` of the resource (the admin default is `list`, the usage
     default is `update`; neither names an object). `cluster-admin` (`["*"]/["*"]/["*"]`) matches everything.
4. **Return** `{"status":{"allowed": <bool>}}` with HTTP **201** (or 200), value a real JSON
   boolean. Missing `status`, missing `allowed`, or a non-bool → the client **raises and fails
   closed to self** — so the authorizer must always emit a clean boolean.

### 5.3 The two default checks (verified, config.py:440-464)

| Resolver | verb | resource | group | ns | sub | Gates |
|---|---|---|---|---|---|---|
| **WIDE / admin** | `list` | `clusterrolebindings` | `rbac.authorization.k8s.io` | — | — | `/bindings/findings`, `/operator-configs`, operator_configs figure, PROJECTS list |
| **USAGE** | `update` | `clusterrolebindings` | `rbac.authorization.k8s.io` | — | — | Usage tab only (a **write** verb on purpose, to exclude cluster-reader) |

Both call the same `create_subject_access_review`; they differ **only in the verb**. The mock
serves both from one `SarAuthorizer` — the verb comes in the request.

### 5.4 Expected verdicts against the measured personas (config.py:426-432)

The fixture RBAC (§6) must be authored so these hold — this is the acceptance oracle:

| Persona | fixture RBAC | `list clusterrolebindings` (wide) | `update clusterrolebindings` (usage) | tier |
|---|---|---|---|---|
| `kubeadmin` | `cluster-admin` CRB | **ALLOW** | **ALLOW** | all / all |
| `dana.lee` | `cluster-reader` CRB (read verbs, no `update`) | **ALLOW** | **DENY** | all wide / self usage |
| `lateef.o` | no admin CRB | DENY | DENY | self |
| `jane.smith` | in a Group **named** `…-cluster-admin` but **no CRB behind it** | DENY | DENY | self |

`jane.smith` is the key negative fixture: a suggestively-named group with no real binding must
**not** grant the tier. Only a real `(Cluster)RoleBinding` reaching a `spec.groups`/`spec.user`
subject grants it.

---

## 6. Fixture format

One YAML file (JSON accepted), loaded and validated at startup. It is the single source of
truth for every endpoint. Top-level keys mirror the resources; unknown keys are rejected
(fail-loud). Missing keys default to empty lists / empty OAuth.

```yaml
# fixture.yaml  — a small reference cluster
meta:
  clusterName: mock-openshift          # cosmetic; the inspection page title
  token: "mock-token-abc123"           # the Bearer the auth gate requires

groupsyncs:                            # endpoint (a)   [] or omit → CRD present, empty
  - name: ldap-sync
    namespace: group-sync-operator
    generation: 3
    schedule: "*/30 * * * *"
    providers: [{name: acme-ldap, kind: rfc2307, filter: "(objectClass=groupOfNames)"}]
    lastSyncSuccessTime: "2026-09-14T08:00:00Z"
    conditions:
      - {type: ReconcileSuccess, lastTransitionTime: "2026-09-14T08:00:00Z"}
  crdAbsent: false                     # true → endpoint (a) answers plain 404

groups:                                # endpoint (b)
  - name: app-ocp-rbac-demo-cluster-admin
    syncProvider: acme-ldap
    syncTime: "2026-09-14T08:00:00Z"
    ldapUid: "cn=…"
    users: [kubeadmin, jane.smith]     # TOP-LEVEL users array
  - name: cluster-readers
    users: [dana.lee]

users:                                 # endpoint (c)  — 403 if `forbidden: true`
  entries:
    - {name: lateef.o, fullName: "Lateef O.", creationTimestamp: "2026-01-02T00:00:00Z",
       identities: ["acme-ldap:lateef.o"]}
  forbidden: false

identities:                            # endpoint (d)
  entries:
    - {userName: lateef.o, creationTimestamp: "2026-01-02T00:00:00Z"}  # ISO-8601 required
  forbidden: false

namespaces:                            # endpoint (e)
  entries:
    - {name: acme-app, phase: Active, creationTimestamp: "2026-01-02T00:00:00Z",
       labels: {"team": "acme"}}
  forbidden: false

roles:                                 # ClusterRoles + namespaced Roles for the SAR authorizer
  clusterRoles:
    - name: cluster-admin
      rules: [{verbs: ["*"], apiGroups: ["*"], resources: ["*"]}]
    - name: cluster-reader
      rules:
        - {verbs: [get, list, watch], apiGroups: ["*"], resources: ["*"]}
  namespacedRoles:
    - {namespace: acme-app, name: viewer, rules: [{verbs: [get, list], apiGroups: [""], resources: [pods]}]}

bindings:                              # endpoints (f)+(g) AND the SAR subject graph
  clusterRoleBindings:
    - name: cluster-admin-crb
      roleRef: {kind: ClusterRole, name: cluster-admin}
      subjects: [{kind: Group, name: app-ocp-rbac-demo-cluster-admin}]  # → kubeadmin only
      labels: {"rbac.ocp.io/config-source": "gitops"}
    - name: cluster-reader-crb
      roleRef: {kind: ClusterRole, name: cluster-reader}
      subjects: [{kind: Group, name: cluster-readers}]                  # → dana.lee
  roleBindings:
    - {namespace: acme-app, name: viewer-rb, roleRef: {kind: Role, name: viewer},
       subjects: [{kind: User, name: lateef.o}]}
  # NOTE: no CRB references jane.smith's "…-cluster-admin" group → she stays self (the decoy).

operatorConfigs:                       # endpoints (h)+(i)
  namespaceConfigs: [{name: acme-nsconfig, conditions: [{type: ReconcileSuccess, lastTransitionTime: "…"}]}]
  groupConfigs: []
  namespaceConfigsCrdAbsent: false
  groupConfigsCrdAbsent: false

nodes:                                 # endpoint (j)  — labelSelector honoured
  entries: [{name: master-0, labels: {"node-role.kubernetes.io/master": ""}}]
  forbidden: false

oauth:                                 # endpoint (k)  — single object, no items
  identityProviders:
    - {name: acme-ldap, ldapUrl: "ldap://ldap.acme/ou=groups,dc=acme?cn?sub?(cn=ocp-admins)"}
  forbidden: false
  crdAbsent: false

oauthPods:                             # endpoint (l)
  namespace: openshift-authentication
  entries: [{name: oauth-openshift-abc, phase: Running}]
  forbidden: false

auditLog:                              # endpoints (n)+(o) — see §7
  node: master-0
  dir: oauth-server
  files:
    - name: audit.log                  # live file
      lines:
        - {kind: credential, decision: allow, user: jane.smith, at: "2026-09-03T10:15:27.234567Z", code: 302}
        - {kind: cli,        decision: deny,  user: lateef.o,   at: "2026-09-03T10:16:01.000000Z", code: 401}
    - name: "audit-2026-09-01T00-00-00.000.log"   # a rotated backup (lumberjack form)
      lines: [{kind: session, decision: allow, user: dana.lee, at: "2026-09-01T09:00:00.000000Z", code: 302}]

podLog:                                # endpoint (m)  — optional Debug-level klog lines
  namespace: openshift-authentication
  lines:
    - '2026-09-03T10:15:27.234567Z I0903 10:15:27.234 1 login.go:1] Login with provider "acme-ldap" succeeded for "jane.smith"'
```

The loader compiles this into typed dataclasses (`Fixture`, `GroupSyncCR`, `GroupCR`, …) so
the router and authorizer never touch raw dicts. Audit `lines` are **shorthand** the audit
server expands into full Kubernetes-audit JSON (§7) — the fixture author does not hand-write
the JSON envelope.

---

## 7. The audit-log endpoint

Two node-proxy shapes (endpoints n, o), plus the pod-log stream (m). All verified against
`auditlog.py`, `loginlog.py`, and the node-proxy contract in `kube.py`.

### 7.1 Directory listing (n) — HTML, Accept `*/*`

`GET /api/v1/nodes/<node>/proxy/logs/oauth-server/` returns `200`, `Content-Type: text/html`,
a kubelet-`http.FileServer`-style listing. The parser is `href="([^"?#]+)"`, unquote, strip
trailing `/`, take last segment. So the body is simply:

```html
<pre>
<a href="audit-2026-09-01T00-00-00.000.log">audit-2026-09-01T00-00-00.000.log</a>
<a href="audit.log">audit.log</a>
</pre>
```

Rotated files use the lumberjack backup form `audit-<YYYY-MM-DD>T<HH>-<MM>-<SS>.<ms>.log`
(`auditlog.py` ROTATED regex); the live file is `audit.log`. `application/json` Accept →
**406** (never happens because the mock is queried with `*/*`; but the mock must not answer
`200` to `application/json` on this path, mirroring the proxy the code was written around).

### 7.2 File read (o) — bytes, Range-aware

`GET /api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log`:

- **No Range** → `200`, `Content-Type: text/plain`, body = the file's audit lines (one JSON
  event per line, `\n`-joined; the mock may prepend the node name, tolerated by
  `line.find("{")`).
- **`Range: bytes=<off>-`** and `off < size` → `206 Partial Content`, `Content-Range:
  bytes <off>-<size-1>/<size>`, body = bytes from `off`.
- **`Range: bytes=<off>-`** and `off >= size` → **`416`** with **`Content-Range: bytes */<size>`**
  (parsed by `_content_range_total`, kube.py). `size==off` → nothing new; `size<off` →
  rotated. A `416` **without** a parseable `Content-Range` triggers the client's single
  unranged retry — the mock offers a fixture flag to emit that malformed 416 to exercise the
  retry.
- **HEAD** → `405` (never issued by the client; asserted for fidelity).
- `404` → rotated-away (client: None/debug); `403` (path in body) → missing `nodes/proxy`
  grant (None/warning); `401` → `AUTH_FAILED`.

Each line is expanded from fixture shorthand into a Kubernetes-audit event that
`parse_audit_line` (auditlog.py) accepts. The **credential-success** template
(verified minimal line):

```json
{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata",
 "auditID":"<uuid>","stage":"ResponseComplete",
 "requestURI":"/login","verb":"post",
 "user":{"username":"system:anonymous"},"userAgent":"Mozilla/5.0",
 "responseStatus":{"code":302},
 "requestReceivedTimestamp":"<at>","stageTimestamp":"<at>",
 "annotations":{"authentication.openshift.io/username":"<user>",
                "authentication.openshift.io/decision":"allow"}}
```

- `kind: credential` → `requestURI:/login` (or `/login/<idp>` when `provider` given), `verb:post`.
- `kind: cli` → `requestURI:/oauth/authorize?client_id=openshift-challenging-client`, `verb:get`.
- `kind: session` → same as cli but any other `client_id` (e.g. `console`).
- `decision` ∈ {allow, deny, error} → the annotation decision; the parser maps to
  success/failed/provider_error. `user.username` stays `system:anonymous` (the parser reads
  the **annotation**, not `user.username`, deliberately). System accounts (`kube:admin`,
  `system:*`) are rejected by the parser — the fixture should not use them as login subjects.

### 7.3 Pod log (m) — TEXT stream

`GET /api/v1/namespaces/<ns>/pods/<pod>/log?timestamps=true[&sinceSeconds=N]` → `200`,
`Content-Type: text/plain`, each line prefixed with an RFC3339-UTC timestamp + space
(`^(\d{4}-…Z)\s`, loginlog.py). The verdict grammar the parser anchors on
(`loginlog.py`): `]\s+Login with provider "<provider>" (succeeded|failed) for (?:login )?"<user>"`.
The fixture supplies whole lines (the timestamp prefix + a klog body) so the author controls
exactly what the klog parser sees. `>=400` → a k8s `Status` JSON body (`.reason`, `.message`).

---

## 8. The two run forms

Both use the same `MockClusterHandler` + `Fixture` + `SarAuthorizer` + `AuditServer`. They
differ only in start-up and CA hand-over.

### 8.1 Form A — in-process pytest fixture, ephemeral port (CI + local)

```python
@pytest.fixture
def mock_cluster(tmp_path):
    fx = Fixture.from_yaml(FIXTURE_DIR / "reference.yaml")
    server = MockClusterServer(fx, host="127.0.0.1", port=0, tls=True)  # port 0 → ephemeral
    server.start()                          # threaded HTTPServer on its own daemon thread
    ca_path = tmp_path / "ca.crt"
    ca_path.write_bytes(server.ca_pem)      # ephemeral CA written for the dashboard
    try:
        yield MockHandle(base_url=server.base_url,   # https://127.0.0.1:<ephemeral>
                         token=fx.token, ca_file=str(ca_path), server=server)
    finally:
        server.stop()
        gsd.config._ca_cache.clear()        # §4.3 stale-context guard
```

The test then builds `ClusterConfig(name="c1", api_url=handle.base_url, token_env="T",
ca_bundle_file=handle.ca_file)` (with `T` set to `handle.token`), and drives
`poll_once(store, cfg, timeout, …)` / `refresh_bindings(...)` / a `TierResolver`. This
exercises the **real** `_get`/`_list_all`/streaming/SAR paths over **real verified TLS** —
the coverage MockTransport cannot give. Ephemeral port → parallel-test-safe, no fixed-port
collisions on a shared runner.

### 8.2 Form B — container on :6443 (lab e2e)

A `Containerfile` builds a tiny image (python-slim + the mock package + a baked
`reference.yaml`). Entrypoint: `python -m mock_app --fixture /fixtures/reference.yaml
--host 0.0.0.0 --port 6443 --tls`. The CA is either (a) generated at boot and **written to a
mounted volume** (`/out/ca.crt`) the dashboard also mounts as `caBundleFile`, or (b) a
**pre-generated** CA+leaf mounted in (stable across restarts, for a persistent lab).
`podman run -p 6443:6443 -v ./fixtures:/fixtures:ro -v ./out:/out mock-openshift`. The
dashboard's ConfigMap points `clusters[0].apiUrl: https://mock-openshift:6443`,
`caBundleFile: /etc/gsd/mock-ca/ca.crt`, `tokenFile: /etc/gsd/mock-token`. Port 6443 mirrors a
real API server so `oc login` / a browser / the e2e-walk can poke it. Same handler, same
fixture — the only new surface is the SAN including `DNS:mock-openshift`.

---

## 9. The control / inspection page

A tiny operator surface under a reserved prefix that is **not** part of the kube API (so it
never shadows a real path). Served as HTML at `GET /_mock/` and JSON at `GET /_mock/state`.

- **`GET /_mock/`** — a single self-contained HTML page (no external assets; CSP-safe inline
  CSS): the loaded fixture at a glance (cluster name, group/user/binding/node counts), a live
  **request log** (method, path, status, matched endpoint id a–p, bytes) so an implementer can
  *see* the poller's traffic, and a **SAR probe** form (enter user + pick verb → shows the
  computed allow/deny and the matching binding, for eyeballing the authorizer). The request
  log is an in-memory ring buffer (last N requests), rendered server-side; a small
  `setInterval` fetch of `/_mock/state` refreshes it.
- **`GET /_mock/state`** — JSON: `{fixture_summary, recent_requests:[…], sar_cache_note}`.
  Machine-readable for a test assertion ("did the poller actually hit `/nodes`?").
- **`POST /_mock/sar-probe`** — `{user, verb, resource, group, namespace?}` → the authorizer's
  verdict + the binding that granted it (or "no binding"), for the inspection UI. Does not
  touch the real SAR path.
- **`POST /_mock/reload`** (guarded, form B only) — re-reads the fixture file without a
  restart, for iterating in the lab.

The `/_mock/` page follows the repo's `frontend-design` taste (it is operator-facing), but is
deliberately minimal — it is a debugging window, not a product surface.

---

## 10. Exact file layout of `mock-app/`

```
local-development/mock-app/
├── README.md                     # what it is, both run forms, the fixture schema, the SAR oracle
├── pyproject.toml                # package `gsd-mock`; deps: cryptography, pyyaml; extra [server]
├── mock_app/
│   ├── __init__.py               # version, public exports (MockClusterServer, Fixture)
│   ├── __main__.py               # `python -m mock_app` CLI (form B): argparse → serve()
│   ├── server.py                 # MockClusterServer: ThreadingHTTPServer + TLS wrap + lifecycle
│   ├── handler.py                # MockClusterHandler(BaseHTTPRequestHandler): auth gate + router
│   ├── router.py                 # path→handler dispatch table (endpoints a–p + /_mock/*)
│   ├── fixture.py                # Fixture dataclasses + from_yaml() loader/validator
│   ├── responses.py              # k8s List/object envelope builders; paging (limit/continue)
│   ├── sar.py                    # SarAuthorizer: RBAC evaluation over the fixture (§5)
│   ├── auditlog.py               # AuditServer: shorthand→audit JSON, HTML listing, Range/416 (§7)
│   ├── podlog.py                 # pod-log text stream builder (§7.3)
│   ├── tls.py                    # ephemeral CA+leaf via cryptography; ca_pem property (§4)
│   ├── inspect.py                # /_mock/ HTML page + /_mock/state + sar-probe (§9)
│   └── errors.py                 # helpers: forbidden_403(path), crd_absent_404(path), status_json()
├── fixtures/
│   ├── reference.yaml            # the four-persona reference cluster (§5.4 oracle)
│   ├── crd-absent.yaml           # GroupSync/operator CRDs missing (404 branches)
│   ├── forbidden.yaml            # 403-tolerated branches on users/identities/namespaces/nodes/oauth/pods
│   └── paging.yaml               # multi-page groups/nodes to exercise continue tokens
├── containerfile/
│   ├── Containerfile             # form B image (python-slim + package + baked reference.yaml)
│   └── entrypoint.sh             # generates/loads CA to /out, execs `python -m mock_app`
└── tests/
    ├── conftest.py               # the `mock_cluster` fixture (§8.1) + ClusterConfig helper
    ├── test_request_surface.py   # each endpoint a–p parsed by a real ClusterClient over TLS
    ├── test_sar_personas.py      # the §5.4 oracle: 4 personas × 2 verbs → measured tiers
    ├── test_tls_trust.py         # mode-2 caBundleFile, mode-3 GSD_TRUSTED_CA_FILE, negative control
    ├── test_audit_stream.py      # listing HTML, Range 206, 416+Content-Range, rotated ordering
    └── test_poll_end_to_end.py   # poll_once + refresh_bindings + TierResolver against the mock
```

The **dashboard code is not modified** — the mock lives beside `gsd/` and is imported only by
tests and the container. It depends on `gsd.config`/`gsd.kube` only in *tests* (to build
`ClusterConfig` and drive the poller), never the reverse.

---

## 11. Per-file interfaces (unambiguous contracts)

### `mock_app/tls.py`
```python
def generate_ca_and_leaf(sans: list[str]) -> CaLeaf: ...
    # sans e.g. ["IP:127.0.0.1", "DNS:localhost", "DNS:mock-openshift"]
    # returns CaLeaf(ca_pem: bytes, leaf_cert_pem: bytes, leaf_key_pem: bytes)
class CaLeaf(NamedTuple):
    ca_pem: bytes; leaf_cert_pem: bytes; leaf_key_pem: bytes
def build_ssl_context(leaf: CaLeaf) -> ssl.SSLContext: ...   # server-side, wraps the socket
```

### `mock_app/fixture.py`
```python
@dataclass(frozen=True)
class Fixture:
    cluster_name: str; token: str
    groupsyncs: list[GroupSyncCR]; groupsyncs_crd_absent: bool
    groups: list[GroupCR]
    users: FeedOrForbidden[UserCR]           # .entries + .forbidden
    identities: FeedOrForbidden[IdentityCR]
    namespaces: FeedOrForbidden[NamespaceCR]
    cluster_roles: list[Role]; namespaced_roles: list[Role]
    cluster_role_bindings: list[Binding]; role_bindings: list[Binding]
    operator_configs: OperatorConfigs
    nodes: FeedOrForbidden[NodeCR]
    oauth: OAuthCR                            # .identity_providers + .forbidden + .crd_absent
    oauth_pods: OAuthPods
    audit: AuditFixture; pod_log: PodLogFixture
    @classmethod
    def from_yaml(cls, path: str | Path) -> "Fixture": ...   # validates, rejects unknown keys
```

### `mock_app/responses.py`
```python
def k8s_list(items: list[dict], continue_token: str | None = None) -> dict: ...
    # {"apiVersion":..,"kind":"…List","items": items, "metadata": {"continue": tok}?}
def paginate(items: list[dict], limit: int, cursor: str | None) -> tuple[list[dict], str | None]: ...
    # honours limit=500 + opaque continue tokens; returns (page, next_cursor_or_None)
def groupsync_item(cr) -> dict; def group_item(cr) -> dict; def user_item(cr) -> dict
def identity_item(cr) -> dict; def namespace_item(cr) -> dict; def binding_item(b) -> dict
def oauth_object(oauth) -> dict; def pod_item(p) -> dict; def node_item(n) -> dict
    # each emits the exact nesting §3 lists (metadata.labels/annotations objects,
    # top-level users/identities arrays, status.conditions, roleRef, subjects…)
```

### `mock_app/sar.py`
```python
class SarAuthorizer:
    def __init__(self, fx: Fixture): ...
    def review(self, user: str, groups: list[str], attrs: dict) -> bool: ...
        # attrs = {verb, resource, group, namespace?, subresource?}; §5.2 algorithm.
        # returns a real bool. Never raises for a well-formed body.
    def explain(self, user, groups, attrs) -> tuple[bool, str | None]: ...
        # (allowed, granting_binding_name_or_None) for /_mock/sar-probe
```

### `mock_app/auditlog.py`
```python
class AuditServer:
    def __init__(self, audit: AuditFixture): ...
    def listing_html(self) -> bytes: ...                 # endpoint (n): <a href> per file
    def read(self, filename: str, rng: Range | None) -> AuditResponse: ...
        # endpoint (o): AuditResponse(status, headers, body_bytes)
        #   200 full | 206 partial + Content-Range | 416 + "bytes */<size>"
    def expand_line(self, shorthand: dict) -> str: ...   # → one Kubernetes-audit JSON line (§7.2)
```

### `mock_app/handler.py` / `router.py`
```python
class MockClusterHandler(BaseHTTPRequestHandler):
    # attaches: self.server.fixture, .sar, .audit, .podlog, .inspect, .reqlog
    def _authorize(self) -> bool: ...        # Bearer match → else 401 (writes + returns False)
    def do_GET(self): ...  ; def do_POST(self): ...  ; def do_HEAD(self): ...  # 405 on node-proxy
# router.py
ROUTES: list[tuple[re.Pattern, Callable[[MockClusterHandler, re.Match], None]]]
# ordered: /_mock/* first, then exact API paths, then the two templated node-proxy patterns.
def route(handler) -> None: ...              # match path, dispatch, or 404 with a body
```

Each endpoint handler consults the fixture's `forbidden`/`crd_absent`/`entries`, and calls
`errors.forbidden_403(path)` (body **contains the path**, §3.1) or `errors.crd_absent_404(path)`
(body → `_get` message starts `"HTTP 404 on <path>"`) to reach the tolerated branches.

### `mock_app/server.py`
```python
class MockClusterServer:
    def __init__(self, fixture: Fixture, host="127.0.0.1", port=0, tls=True,
                 sans: list[str] | None = None, ca_leaf: CaLeaf | None = None): ...
    def start(self) -> None: ...             # bind (port 0 → ephemeral), TLS-wrap, serve on a thread
    def stop(self) -> None: ...
    @property
    def base_url(self) -> str: ...           # "https://127.0.0.1:<actual-port>"
    @property
    def ca_pem(self) -> bytes: ...           # the CA cert to hand over as caBundleFile
```

### `mock_app/__main__.py` (form B CLI)
```
python -m mock_app --fixture PATH [--host 0.0.0.0] [--port 6443] [--tls/--no-tls]
                   [--ca-out /out/ca.crt] [--ca-in DIR] [--sans DNS:mock-openshift,IP:…]
```

---

## 12. CI job

A GitHub Actions job runs form A. Portable — no cluster, no container runtime, no OpenShift.

```yaml
# .github/workflows/mock-cluster.yml
name: mock-openshift
on:
  pull_request:
    paths:
      - 'local-development/gsd/kube.py'
      - 'local-development/gsd/config.py'
      - 'local-development/mock-app/**'
      - '.github/workflows/mock-cluster.yml'
  push:
    branches: [main]
jobs:
  mock-cluster:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@<release-tag-commit-sha>       # pinned by the tag's commit (memory: pin-actions-by-release-tag-commit)
      - uses: actions/setup-python@<release-tag-commit-sha>
        with: { python-version: '3.12' }
      - name: Install
        working-directory: local-development
        run: |
          python -m pip install -e .            # the dashboard (gsd) — provides ClusterClient/ClusterConfig
          python -m pip install -e mock-app[server] pytest
      - name: Run the mock-cluster suite
        working-directory: local-development
        run: pytest mock-app/tests -q
```

The suite (§10 `tests/`) covers: every endpoint a–p parsed by a **real** `ClusterClient` over
real TLS; the SAR persona oracle (§5.4); all three TLS trust modes plus the negative control
(§4.5); the audit Range/416/rotation machinery; and a full `poll_once` + `refresh_bindings` +
`TierResolver` cycle. A **container-smoke** job (form B) is optional and gated to a manual
`workflow_dispatch` — it builds the image and `curl`s `/_mock/state` and one list endpoint —
because it needs a container runtime and is redundant with form A for parse coverage.

**Adversarial review + changelog** (memory: load-project-skills-before-autonomous-work): the
implementing PR runs the `adversarial-review` skill (Codex + Cursor on a per-claim brief,
snippet-only) before it is called ready, and the `changelog` skill appends the session entry
after tests + review pass. `main` is protected — the change lands via a PR the operator merges
(memory: main-is-protected).

---

## 13. Risks / decisions to confirm with the operator (best-practice defaults per memory)

1. **Server stack:** `http.server.ThreadingHTTPServer` (stdlib, zero deps) vs a tiny ASGI app.
   Default = stdlib — portability first, and the streaming/Range handling is explicit and
   debuggable. *(Settle on best practice unless the operator prefers ASGI.)*
2. **CA lifetime in form B:** boot-generated (simplest) vs pre-generated mounted (stable across
   restarts). Default = boot-generated to a mounted `/out`, with `--ca-in` to pin a persistent
   lab CA.
3. **`/_mock/` exposure:** the control page is unauthenticated (it is a test tool). In form B on
   :6443 it should be bound to loopback or gated behind the same Bearer if the lab is shared —
   flagged, not assumed.
