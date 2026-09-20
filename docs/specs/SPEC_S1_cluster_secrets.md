# SPEC S1 — Clusters as labelled Secrets: the contract, the reader, the API

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), step S1 of three — after the 2026-09 programme's ladder |
| Batch | S — cluster configuration |
| Release | — (post-programme; supersedes #119 P1's mount mechanics) |
| Version on release | chart 0.42.0, migration 19 |
| Issue | [#230](https://github.com/ephico2real2/group-sync-dashboard/issues/230) |
| Status | in implementation |
| Source | this document is the orchestrator's own design, researched and cited below; there is no separate design-agent output |

## How to read this spec

"Research" is what was read and where. "Contract" is what an operator or a GitOps process may
write and what the app promises about it — the part the next steps (S2's tab, S3's examples) and
every reviewer hold the code to. "Design" is the code, file by file, applied with an exact-match
check on every Old text. A deviation found necessary during implementation is written back here, in
the same pull request, under "Orchestrator's notes", with the reason.

The flows this contract produces are drawn — as mermaid and as ASCII — in
[`docs/DESIGN_cluster_connection_flows.md`](../DESIGN_cluster_connection_flows.md): the connection
path with every refusal point, the three TLS modes as a decision, the credential modes and which
object holds which secret, and the tier gate on the surface. The log vocabulary those pictures are
read against is `gsd/clusterconfig/events.py` (#245).

## Orchestrator's notes

- **The operator's ruling on the tier (2026-09-20, relayed during implementation):** this surface is
  **cluster-admin only — the reporting auditor may neither view nor change it**, and it gets *"a new tier
  boss — look at how argocd does it"* rather than borrowing an existing gate.

  *The defect this fixes, measured.* The route first shipped on `require_admin_tier`, which is the WIDE
  tier — and `gsd/api.py` says in its own words why that is not enough: *"the wide tier that cluster-reader
  — the deliberate auditor persona — also passes"* (`usage_scope`). So an auditor would have read the
  fleet's wiring, and at S2 held the writes that change it.

  *The model.* Argo CD's RBAC carries a first-class `clusters` resource with `get` and
  `create/update/delete` actions, granted to roles bound to SSO groups, default-deny. We hold no policy
  file — every tier here is a SubjectAccessReview against the host cluster, so OpenShift groups and
  RoleBindings already ARE that mapping — so the tier is a named pair of SAR questions about the very
  objects this surface exposes, the cluster Secrets themselves:

  | our level | Argo's action | SAR (default) | grants |
  |---|---|---|---|
  | `clusterconfig:view` | `clusters, get` | `get secrets` in the dashboard's namespace | the tab and `GET /api/clusterconfigs` |
  | `clusterconfig:manage` | `clusters, create/update/delete` | `create secrets` in that namespace | the write routes and the form's Create / Rotate / Delete / Test (S2) |

  It reads as what it is: *you may see cluster credentials if you may read the Secrets that hold them; you
  may change them if you may create those Secrets.*

  *Why these questions work, measured on CRC 2026-09-20:* `oc get clusterrole cluster-reader -o json` has
  **zero** of its 172 rules covering core/`secrets`, and `oc auth can-i {get,list,create,update,delete}
  secrets -n group-sync-dashboard` answers `no` for a non-admin subject. The auditor fails both levels by
  construction; a cluster-admin passes both.

  *Rules.* Fail closed (Argo's `policy.default: deny`): no resolver, no identity, or an errored check →
  refused. Each level has its **own** resolver instance and cache — never shared with the wide tier's or
  with each other — and its own metric threshold label, the rule `docs/SPEC_usage_admin_tier.md` already
  states. `manage` is **not** inferred from `view` in code, so a site may grant them apart. Settings
  `visibility_clusterconfig_{view,manage}_sar_*` (chart `visibility.clusterConfig{View,Manage}Sar`) let a
  site point either at its own question, e.g. a dedicated `fleet-admin` ClusterRole; an empty `namespace`
  means the pod's own, the opposite of the wide tier's empty, because these questions are namespaced by
  nature.

  *NO COMPOSITION WITH ANOTHER TIER — the ruling of 2026-09-20, which REVERSED an ordering added
  earlier the same day.* Each level asks **its own** question and nothing else: view = `get secrets`,
  manage = `create secrets`, in the dashboard's namespace. The operator: *"A user with cluster admin and
  auditor is fine. That is how Kubernetes RBAC works. As long as the user has the role needed or can get
  the right SAR needed, we are good."* Three reasons, in the order they settle the question:

  1. **RBAC is additive.** Holding the auditor role *and* a namespace- or cluster-admin grant is not a
     contradiction for the dashboard to resolve — it is the ordinary shape of a person with two jobs.
  2. **The SAR asks the ACTION'S OWN question.** Whoever passes `create secrets` in this namespace can
     write the cluster Secret with `oc` directly, so refusing them in the UI protects nothing; and
     because the gate *is* the action, the ServiceAccount that performs the write is not a confused
     deputy — it does only what the asker was already entitled to do.
  3. **The auditor ruling is satisfied without composition, measured.** On CRC 2026-09-20 the pure
     auditor persona — `lateef.o`, whose groups are `app-ocp-rbac-groupsync-ns-auditor`,
     `…-lateef-ns-developer`, `app-ssb-autobahnusers` — answers `no` to both `get secrets` and `create
     secrets` with those groups carried, while passing the WIDE tier (`list clusterrolebindings`: yes,
     and the admin-gated `/bindings/findings` serves him 200). The plain question already excludes him;
     an ordering would only have excluded identities that ALSO hold namespace `admin`/`edit`, who can
     write the Secret by hand.

  What the earlier ordering was reacting to is still worth recording, because it is what the questions
  do NOT claim: `get`/`create secrets` in a namespace is held by the stock `admin` ClusterRole, so these
  are not a *higher* bar than the wide tier — they are the bar that matches the action. A site that wants
  a narrower door repoints either question at its own (a dedicated `fleet-admin` ClusterRole, say).

  *What the review DID earn, and is kept:* no `restrict` short-circuit (turning `visibility.enabled` off
  must not widen this tier, and `userActivity.visibility: all` must not either); fail closed on no
  identity, no resolver, a junk answer or an API-server blip; each level its own resolver instance and
  cache; `manage` never inferred from `view`; and an unknown pod namespace refuses rather than silently
  asking a CLUSTER-SCOPED `get secrets`.

  *Division of labour.* **S1 ships both resolvers** and gates its read route on `view`; **S2 gates the
  write routes on `manage` and the tab's very existence on `view`** — a reader who fails `view` gets no tab
  button, no dispatch and no fetch, and reaching `#page=clusters` by URL shows the refusal card naming
  itself. **S2 gates its writes on the same resolver — there is ONE definition of each level.** Tests here: the auditor persona is refused with no cluster named while passing the wide tier;
  `manage` alone does not open the read route; it fails closed on a missing resolver, a missing identity
  and an exploding check; and a mutant reverting the route to `require_admin_tier` fails
  (`tests/test_clusterconfig.py::TestClusterConfigTier`).

- **The operator's ruling on TLS trust (2026-09-20, relayed during implementation):** a cluster's trust is
  one of three, said explicitly — (1) DEFAULT, no `tlsClientConfig.caData`: verify against the dashboard's
  own trust store, `GSD_TRUSTED_CA_FILE` (the chart's `trustedCA.*` bundle: the injected OpenShift CA + the
  enterprise ConfigMap, colon-joined) plus the system store — `ClusterConfig.verify()`'s existing third mode;
  (2) OVERRIDE, `tlsClientConfig.caData` (base64 PEM) — the named-bundle mode, this cluster only; (3)
  `tlsClientConfig.insecure: true` — verification off. `caData` together with `insecure: true` is REFUSED
  as a finding naming both fields (the rule `load_settings` applies to `insecureSkipVerify` beside
  `caBundleFile`). `GET /api/clusterconfigs` reports the mode per cluster as
  `tls: {insecure: bool, ca: "caData" | "trusted-bundle" | "serviceAccount" | "caBundleFile" | null}` and
  never the PEM. The C1 table below said modes 2 and 3 and the refusal; mode 1 was implied by the parser's
  fall-through and is now stated; the `tls` field is added to C5's payload; a test per mode and one for
  the refusal in `tests/test_clusterconfig.py`.
- The host cluster is never sourced from a Secret. The oauth-proxy authenticates the reader against
  the host (`values.yaml` `clusters[0]`, `Settings.host_cluster()`), so a Secret that names the host's
  `name` or `https://kubernetes.default.svc` would let whoever can write a Secret in the namespace
  replace the identity every tier decision rests on. It is refused as a finding
  (`host-cluster-not-from-secret`), which departs from Argo CD, where an in-cluster Secret *overrides*
  the built-in entry — Argo has no reader tier to protect.
- **The operator's ruling on where a credential lives (2026-09-20):** "A bearer token is minted by a cluster, so it lives inline in that cluster's own Secret — `gsd-cluster-<name>` carries the full ServiceAccount token in `config.bearerToken`; rotation replaces it in place. A shared username/password (the fleet's LDAP service account) is NOT written per cluster: #119 P2 adds `credentialRef: <credential Secret>` for that." S1's reader accepts `config.oauth{{username,password}}` inline and refuses it at poll time (`oauth-exchange-not-built`), as briefed; P2 adds `credentialRef` beside it and the inline form stays for a per-cluster password if one exists.
- Discovery runs on the binding cadence (`bindingIntervalSeconds`, 300 s), not a WATCH. The watch with
  `resourceVersion` resumption and `410 Gone` re-list (Kubernetes API concepts, cited below) is the
  same mechanism #170 step 3 owes the Kyverno reader; both land together so there is one
  implementation of it, not two. A LIST by label in one namespace is a few kilobytes per cycle.
- The `oauth` credential kind parses and is stored as a KIND only; resolving it is refused with a
  `ConfigError` naming #119 P2. A cluster declared with it is listed with `credential: oauth` and a
  finding `oauth-exchange-not-built`, never polled with an empty token.

## Research (read 2026-09-20)

1. **Argo CD's contract.** A cluster is a Secret in Argo's namespace labelled
   `argocd.argoproj.io/secret-type: cluster` with `stringData` `name`, `server`, `config` (JSON:
   `bearerToken` | `username`/`password` | `execProviderConfig` | `awsAuthConfig`, `tlsClientConfig
   {insecure, caData, certData, keyData, serverName}`, `proxyUrl`, `disableCompression`), optional
   `project`, `namespaces`, `clusterResources`, `shard`; the Secret's own name is arbitrary. The local
   cluster has no Secret and is `https://kubernetes.default.svc`.
   — [Declarative setup](https://argo-cd.readthedocs.io/en/stable/operator-manual/declarative-setup/).
   In `util/db/cluster.go`: Secrets are selected by `common.LabelKeySecretType =
   common.LabelValueSecretTypeCluster` through an informer (`db.watchSecrets()`, a
   `SharedIndexInformer` with that label selector) whose add/update/delete callbacks are
   `handleAddEvent` / `handleModEvent` / `handleDeleteEvent`; when no Secret names the internal API
   server, `getLocalCluster()` "falls back to the hardcoded local cluster"; `SecretToCluster()` does
   `json.Unmarshal(s.Data["config"], &config)` and **returns the error** on a bad `config` rather than
   skipping the Secret — [cluster.go](https://github.com/argoproj/argo-cd/blob/master/util/db/cluster.go).
   The ApplicationSet cluster generator exposes the Secret's `metadata.labels.<k>` and
   `metadata.annotations.<k>` as template parameters — the "labels are the fleet's metadata" property
   — [Cluster generator](https://argo-cd.readthedocs.io/en/stable/operator-manual/applicationset/Generators-Cluster/).
2. **Watch semantics, for the step after this one.** "A list result always contains a resourceVersion;
   clients can use the resourceVersion from a list result to start a watch from that point"; on `410
   Gone` "a client must handle this case by discarding the watch resources it has cached, performing a
   new list request, and starting the watch from the resourceVersion returned by that new list
   request"; bookmarks are "strongly recommended"; a list with `resourceVersion` unset is "Most Recent"
   — [API concepts: efficient detection of changes](https://kubernetes.io/docs/reference/using-api/api-concepts/#efficient-detection-of-changes).
   S1's LIST on a cadence is that first list, repeated; nothing here precludes the watch.
3. **Config loading in Python.** pydantic-settings layers sources by priority (init → env → dotenv →
   secrets directory → defaults) through `settings_customise_sources`, "first item is the highest
   priority" — [Settings management](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).
   The shape borrowed is the *layering with a stated precedence*, not the library: `load_settings()`
   (`gsd/config.py`) is deliberately strict and up-front — a typo at install fails the pod with the
   key named — and a runtime source written by a controller at 3 a.m. must NOT have that property. So
   there are two sources with two failure modes: values (strict, at start) and Secrets (lenient, a
   finding per bad object, at each cycle), merged with the precedence in the contract.
4. **Producers of a labelled Secret**, for S3's examples: External Secrets sets the produced Secret's
   name and labels through `spec.target.name` and `spec.target.template.metadata.labels`
   — [ExternalSecret API](https://external-secrets.io/latest/api/externalsecret/); Kustomize's
   `secretGenerator` takes `options.labels`; a Flux `Kustomization` or an Argo `Application` applies a
   plain Secret manifest. All produce the same object; the app sees no difference and the tab says
   which wrote it only through the Secret's own labels/annotations.

## Contract

### C1 — the Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: gsd-cluster-ocp-east                       # convention for people; the app never keys on it
  namespace: <the dashboard's namespace>           # the pod's own namespace, and only that one
  labels:
    groupsync-dashboard.io/secret-type: cluster    # discovery selects on this label and nothing else
    environment: prod                              # any other label: shown on the tab as the cluster's labels
type: Opaque
stringData:
  name: ocp-east                                   # REQUIRED — the cluster id (URL-safe, stable, ≠ the host's)
  server: https://api.ocp-east.example.com:6443    # REQUIRED — the API URL (https, no path)
  config: |                                        # REQUIRED — JSON
    {"bearerToken": "…",
     "tlsClientConfig": {"caData": "<base64 PEM>", "insecure": false}}
  visibility: self-only                            # optional — D2: inherit | self-only | hidden (default self-only)
  identity: none                                   # optional — D2: same-as-host | none (default none)
  enabled: "true"                                  # optional — "true" | "false" (default true)
```

`config` keys and their meaning, refusals with the key named:

| key | accepted | rule |
|---|---|---|
| `bearerToken` | yes | the credential, kind `bearer`; non-empty string |
| `oauth` | parsed | `{"username", "password"}` → kind `oauth`; **not resolvable in S1** (finding `oauth-exchange-not-built`, #119 P2) |
| *(no `tlsClientConfig.caData`)* | default | mode 1: the dashboard's own trust store — `GSD_TRUSTED_CA_FILE` (the chart's `trustedCA.*` bundles) plus the system store; `tls.ca = "trusted-bundle"` |
| `tlsClientConfig.caData` | yes | mode 2: base64 PEM, decoded and loaded into the SSL context at parse time, this cluster only; a bundle that does not load is a finding; `tls.ca = "caData"` |
| `tlsClientConfig.insecure` | yes | mode 3: boolean, verification off; `tls.insecure = true`. `true` beside `caData` is refused (`insecure-with-ca`, both fields named — the values rule, `load_settings`) |
| `username` / `password` (Argo's HTTP basic) | **refused** | `unsupported config key: username` — OpenShift's API server takes no basic auth |
| `execProviderConfig`, `awsAuthConfig`, `proxyUrl`, `disableCompression`, `tlsClientConfig.certData` / `keyData` / `serverName` | **refused** | `unsupported config key: <key>` — the pod runs no exec plugins, holds no client certificates |
| any other key | **refused** | `unsupported config key: <key>` |

Exactly one of `bearerToken` / `oauth` is required (`credential-missing`, `credential-ambiguous`).

### C2 — precedence and identity

- The **host** is `values.yaml` `clusters[0]` (the first enabled entry), always. A Secret whose `name`
  equals the host's, or whose `server` is `https://kubernetes.default.svc`, is refused
  (`host-cluster-not-from-secret`).
- A Secret and a values entry with the **same `name`** (not the host): the Secret wins; the values entry
  is reported on the tab as shadowed (finding `shadows-values-entry`, informational).
- Two Secrets with the same `name`: the one whose `metadata.name` sorts first wins; the other is a
  finding (`duplicate-cluster-name`).
- A discovered cluster's `visibility`/`identity` default exactly as a second values entry does
  (`Settings.cluster_policy`: `self-only` / `none`).

### C3 — discovery and lifecycle

- The stage runs in the poller on the **host** cluster's client, on `bindingIntervalSeconds`, and once
  synchronously at start (before `retire_absent_clusters`, so a restart does not retire a Secret-sourced
  cluster for one cycle). It LISTs `/api/v1/namespaces/<ns>/secrets?labelSelector=groupsync-dashboard.io/secret-type=cluster`
  in the pod's own namespace (`leader.own_namespace()`), paged. Only the leader writes; a standby
  replica reads what the leader wrote.
- A cluster whose Secret is present and parses is **upserted** (`cluster.source = secret:<metadata.name>`)
  and polled like a values cluster — its own thread, the same `poll_once`. A Secret that changes
  (token rotated, server changed) takes effect on the next cycle: the thread reads the registry each
  poll. A Secret that **vanishes** disables its cluster (`enabled=0`, history kept, #96) and stops its
  thread.
- A LIST that fails (403 because the Role is absent, unreachable) is one finding
  (`discovery-failed`, the error verbatim) and the previous registry stands.
- A malformed Secret is one finding per Secret with the code above; it never affects another Secret
  and never the pod.

### C4 — security

- The credential exists in the Secret and in the process's memory only: never in SQLite (the cluster
  row stores the KIND — `bearer` | `oauth` — and nothing else), never in a log line (the fields are
  `repr=False`; the parser logs the Secret's name and the finding code, never a value), never in a
  response (`/api/clusters`, `/api/clusterconfigs`, `/readyz`), never in `/metrics`. A test pins each.
- The Role grants `get`, `list`, `watch` on `secrets` in the release namespace only (`create`,
  `update`, `delete` are S2's, behind their own switch). The label domain is the chart's own
  (`groupsync-dashboard.io/…`), so an Argo cluster Secret in the same namespace is never read.
- The stage is off when `clusterConfig.secrets.enabled=false` (chart) / `GSD_CLUSTER_SECRETS_ENABLED`
  (app): no LIST, no Role, the values list alone — today's behaviour.

### C5 — the API (S2's tab builds on this)

`GET /api/clusterconfigs` — **`clusterconfig:view`** (`require_clusterconfig_view`, the host), the
cluster-configuration tier's read level, NOT the wide administrator tier. See the Orchestrator's note
below for why: the wide tier admits the auditor persona by design. A reader who fails it gets a 403
that names the control and no cluster, Secret or namespace.

```json
{
  "viewer": "kubeadmin", "scope": "all",
  "secrets": {"enabled": true, "namespace": "group-sync-dashboard",
              "label": "groupsync-dashboard.io/secret-type=cluster",
              "last_discovery": "2026-09-20T16:05:12Z", "error": null},
  "clusters": [
    {"id": "crc-local", "source": "values", "host": true, "api_url": "https://kubernetes.default.svc",
     "enabled": true, "credential": "in-cluster", "labels": {},
     "visibility": "inherit", "identity": "same-as-host", "tls": {"insecure": false, "ca": "serviceAccount"},
     "status": "ok", "last_poll": "2026-09-20T16:05:40Z", "error": null},
    {"id": "ocp-east", "source": "secret:gsd-cluster-ocp-east", "host": false,
     "api_url": "https://api.ocp-east.example.com:6443", "enabled": true, "credential": "bearer",
     "labels": {"environment": "prod"}, "visibility": "self-only", "identity": "none",
     "tls": {"insecure": false, "ca": "caData"},
     "status": "unreachable", "last_poll": "2026-09-20T16:05:41Z",
     "error": "ConnectError: [Errno -2] Name or service not known"}
  ],
  "findings": [
    {"secret": "gsd-cluster-broken", "code": "config-not-json", "detail": "Expecting value: line 1 column 1 (char 0)",
     "observed_at": "2026-09-20T16:05:12Z"}
  ]
}
```

Every entry carries `retired` (false above): a cluster the store holds but no source names — its Secret
vanished — is listed with `retired: true`, `enabled: false`, its last poll outcome, so the tab can say why it
is gone (added at implementation: without it a vanished Secret's cluster left the payload entirely, and the
"history kept" promise had no witness). `credential` is one of `in-cluster` (the host's SA), `file` (a values entry's `tokenFile`/`tokenEnv`),
`bearer`, `oauth`. `status`/`last_poll`/`error` are the poll outcome the cluster table already holds.
`findings` are the current cycle's (replaced each discovery, not accumulated — the history of a
finding is the audit log's job). POST/PUT/DELETE — writing a Secret from the tab — are **S2**.

### C6 — the chart

- `clusterConfig.secrets.enabled: true` (the chart-defaults rule: on) → `clusterSecretsEnabled` in the
  ConfigMap and a namespaced `Role`/`RoleBinding` `<fullname>-cluster-secrets` with `get`, `list`,
  `watch` on `secrets`. Off → neither renders.
- README rows for the value and the contract (a pointer to this spec); chart 0.42.0; a CHANGELOG entry.

## Design

### S1.1 `gsd/config.py`

`ClusterConfig` gains, all keyword defaults so every existing constructor call stands:

```python
    # A Secret-sourced cluster (SPEC_S1): the credential lives in memory, never on disk.
    token_value: str | None = field(default=None, repr=False, compare=False)
    ca_data: str | None = field(default=None, repr=False, compare=False)      # PEM text, decoded from the Secret
    oauth_username: str | None = field(default=None, repr=False, compare=False)
    oauth_password: str | None = field(default=None, repr=False, compare=False)
    source: str = "values"                       # values | secret:<metadata.name> | in-cluster
    labels: tuple[tuple[str, str], ...] = ()     # the Secret's other labels, for the tab
```

`resolve_token()` tries `token_value` first; an `oauth_*` pair with no token raises
`ConfigError("cluster {name!r}: username/password exchange against the OAuth server is #119 P2, not built")`.
`verify()` uses `ca_data` (`ssl.create_default_context(cadata=…)`) before `ca_bundle_file`.
`credential_kind` property: `oauth` | `bearer` | `in-cluster` (the SA token path) | `file`.

`Settings` gains `cluster_secrets_enabled: bool = True` (`GSD_CLUSTER_SECRETS_ENABLED` /
`clusterSecretsEnabled`) and a `cluster_registry: ClusterRegistry` (mutable, `compare=False`,
`repr=False`, default factory). `Settings.clusters` stays the values list. New:
`Settings.effective_clusters()` — the values list with Secret-sourced entries merged by the
precedence rule (C2) — and `Settings.cluster(name)` looks up the merged view; `host_cluster()` is
unchanged (values only). Every API and poller site that enumerates clusters moves from
`settings.clusters` to `settings.effective_clusters()` (listed in S1.4).

### S1.2 `gsd/clusterconfig/` (new package)

- `__init__.py`: `SECRET_TYPE_LABEL = "groupsync-dashboard.io/secret-type"`, `SECRET_TYPE_CLUSTER = "cluster"`,
  `FINDING_CODES` (the closed set: `name-missing`, `name-invalid`, `server-missing`, `server-invalid`,
  `config-missing`, `config-not-json`, `unsupported-config-key`, `credential-missing`,
  `credential-ambiguous`, `ca-data-invalid`, `insecure-with-ca`, `visibility-invalid`,
  `identity-invalid`, `enabled-invalid`, `host-cluster-not-from-secret`, `duplicate-cluster-name`,
  `shadows-values-entry`, `oauth-exchange-not-built`, `discovery-failed`).
- `parser.py`: `Finding(secret, code, detail)`; `parse_secret(obj, *, host_name) -> ClusterConfig | Finding`
  — pure, one function, one test per row of the C1 table.
- `registry.py`: `ClusterRegistry` — a lock, `discovered: dict[name, ClusterConfig]`, `findings:
  list[Finding]`, `last_discovery`, `error`; `replace(clusters, findings, at, error)`; `merge(values)`
  (C2); read methods for the API.
- `reader.py`: `discover(host_client, namespace, *, host_name, values_names) -> tuple[list[ClusterConfig], list[Finding]]`
  — the LIST (`_list_all_with(client, path, {"labelSelector": …})`), the parse, the duplicate and
  shadow rules.

### S1.3 `gsd/store.py`

Migration 19: `ALTER TABLE cluster ADD COLUMN source TEXT NOT NULL DEFAULT 'values'` and
`ALTER TABLE cluster ADD COLUMN credential TEXT NOT NULL DEFAULT ''`; `upsert_cluster(cluster_id,
api_url, enabled, *, source="values", credential="")`; `clusters()` returns the two columns;
`retire_absent_clusters` unchanged (it is called with the merged names). Findings are NOT a table:
they are the current cycle's list on the registry (C5 says so) — nothing to migrate for them.

### S1.4 `gsd/poller.py`

- `Poller.start()`: when `settings.cluster_secrets_enabled` and a host exists, one synchronous
  `discover()` (errors → `registry.error`), then `retire_absent_clusters([… effective_clusters()])`,
  then a thread per effective cluster, then the discovery thread.
- `_run_discovery()`: leader-only writes; on the binding cadence: `discover()` → `registry.replace()` →
  `_reconcile_threads()` (start a thread for a new name, set the per-cluster stop event for a vanished
  one and `upsert_cluster(…, enabled=False)`), `upsert_cluster` for every discovered cluster with its
  `source`/`credential`.
- `_run_cluster(cluster)`: reads the current `ClusterConfig` from `settings.cluster(name)` at the top of
  each cycle (a rotated token lands without a restart) and honours a per-cluster stop event beside
  `self._stop`.

### S1.5 `gsd/api.py`

`GET /api/clusterconfigs` per C5. `settings.clusters` → `settings.effective_clusters()` at the eight
enumeration sites (`local_cluster` at 388 stays `host_cluster()`; 432, 447, 456, 748, 2410 enumerate;
2613 `/readyz` counts). `API.md`: the endpoint, the payload, the tier.

### S1.6 Chart

`values.yaml` `clusterConfig.secrets.enabled: true`; `templates/configmap.yaml`
`clusterSecretsEnabled`; `templates/cluster-secrets-rbac.yaml` (Role + RoleBinding, conditional);
README rows; `Chart.yaml` 0.42.0; `docs/CHANGELOG.md`.

### S1.7 Tests

`tests/test_clusterconfig.py`: the parser (one test per C1 row and per C2 rule), the registry's merge,
the reader over a fake client serving labelled Secrets (paged), the poller (a discovered cluster is
polled — `poll_once` called for it; a vanished one disabled with rows kept; a bad Secret → finding, the
good one still polled; the switch off → no LIST), the API (tier; the payload shape; **no credential
string anywhere in `/api/clusterconfigs`, `/api/clusters`, `/readyz`, `/metrics` or the log records**
— one test with a sentinel token). `tests/test_migrations.py`, `test_binding_events.py`,
`test_history_retention.py` pins → 19. `tests/test_chart_reporting.py` (or the chart test that owns
RBAC): the Role renders with the three verbs on, and not at all off.

### S1.8 Verification on CRC

`reports/2026-09-20_cluster-secrets-230/README.md`: a labelled Secret created with `oc`, the pod's
loopback `GET /api/clusterconfigs` showing `source: secret:<name>`, the poller's log line for it, a
malformed Secret as a finding, the Secret deleted → `enabled: false` and the rows still there.
