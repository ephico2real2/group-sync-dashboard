# SPEC S2 — The Cluster Configurations tab: the writes, the form and its GitOps twin

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), step S2 of three — after S1 (`SPEC_S1_cluster_secrets.md`) |
| Batch | S — cluster configuration |
| Release | — (post-programme) |
| Version on release | chart 0.43.0 |
| Issue | [#230](https://github.com/ephico2real2/group-sync-dashboard/issues/230) |
| Status | in implementation |
| Source | the agreed mock `docs/design/cluster-configurations-mock.html` (operator: "I approve the design", 2026-09-20) and S1's contract; the orchestrator's own text, no separate design-agent output |

## How to read this spec

"Contract" is what the tab promises and what the four write routes accept and refuse — the part every
reviewer holds the code to. "Design" is the code, file by file, applied with an exact-match check on
every Old text. The page is a port of the agreed mock: its structure, its words and its states are
the mock's; where the mock's embedded payload differs in shape from S1's real one (`GET
/api/clusterconfigs`), S1's shape wins and the mapping is stated here. A deviation found necessary
during implementation is written back under "Orchestrator's notes", in the same pull request.

## Orchestrator's notes

- **A tier of its own, two levels — the operator's ruling of 2026-09-20 (#230), which SUPERSEDES this
  spec's original "administrator tier" wording.** The surface is cluster-admin only: *"available to
  cluster admin view only and not report auditor … we cannot allow auditor view or change this"*, then
  *"we can create a new tier boss — look at how argocd does it"*. `require_admin_tier` cannot express
  that: it is the WIDE tier, and `gsd/api.py` says so in its own words at `usage_scope` — *"the wide
  tier that cluster-reader — the deliberate auditor persona — also passes"*. Every route on this
  surface therefore asks a tier of its own, modelled on Argo CD's first-class `clusters` resource with
  its `get` / `create,update,delete` split ([Argo CD RBAC](https://argo-cd.readthedocs.io/en/stable/operator-manual/rbac/)):

  | level | SAR (default) | grants |
  |---|---|---|
  | `clusterconfig:view` | `get secrets` in the dashboard's namespace | the tab's existence and `GET /api/clusterconfigs` |
  | `clusterconfig:manage` | `create secrets` in that namespace | the four write routes and the form's Create / Rotate / Delete / Test |

  Measured on CRC 2026-09-20: `cluster-reader` carries **zero** rules covering `secrets`, so the auditor
  persona fails both levels by construction. The questions are also self-describing — you may see
  cluster credentials if you may read the Secrets holding them, and change them if you may create those
  Secrets — where borrowing the Usage tab's `update clusterrolebindings` would have gated cluster
  configuration on an unrelated question. Rules: fail closed (Argo's `policy.default: deny`) on no
  identity, no resolver or a resolver that raised; one resolver and cache per level, shared with
  nothing; `manage` does not imply `view` in code, so a site may grant them separately and get a
  read-only tab. `view` gates the tab's EXISTENCE — no button, no dispatch, no fetch — because an
  auditor must not learn the surface exists by being refused by it; a pasted `#page=clusters` draws the
  refusal card. **The page no longer defers to the wide tier for this payload** (`narrowedOnHost()` was
  removed from its fetch plan): the route asks `clusterconfig:view` alone, so a reader the wide tier
  narrows but this tier admits gets the page the API would answer.

- **The write gate also requires a trusted identity, which closed a hole this review found.** With the
  oauth proxy off `trusted_viewer` is None and the tier machinery is inert, so the write routes stamped
  the audit line `anonymous` and proceeded — an unauthenticated caller could mint cluster access
  (Codex C5, Grok, review of #237). `clusterconfig_allows` refuses a nameless reader at the gate, so
  every audit line names a person by construction.

- **Each level gates on its OWN SAR alone — no admin-rung composition (the operator, 2026-09-20).** An
  earlier design review proposed ordering the levels behind the administrator question, because a
  namespace administrator (`ClusterRole/admin` bound by ClusterRoleBinding) passes `get`/`create secrets`
  while failing the RBAC questions the other tiers ask. The operator reversed it: *"A user with cluster
  admin and auditor is fine. That is how Kubernetes RBAC works. As long as the user has the role needed
  or can get the right SAR needed, we are good."* RBAC is additive, the SAR **is** the action's own
  question, and anyone who passes it can do the same thing with `oc` — the dashboard's ServiceAccount
  performing the write grants nobody a permission they lack. The "no auditor" ruling still holds by
  measurement rather than by composition: the pure auditor persona (the chart's auditor role alone)
  answers `no` to both questions. S2 adds no ordering of its own; the levels are S1's to define.

- **The write gate adds an identity requirement of its own, which is S2's.** `visibilityEnabled: false`
  is a documented choice about READING — every tier answers `all` and, with the proxy off, there is no
  identity at all. A write into the credential store audited as "anonymous" is not covered by that
  choice, so `_writes_gate` refuses a caller with no proxy-verified viewer or with the tier machinery
  off, before `clusterconfig:manage` is asked. A test drives all four routes with no
  `X-Forwarded-User` and `view_restrictions_enabled: false` and asserts nothing reaches the API server.

- **Settings and chart values are S1's to ship** (`visibility_clusterconfig_view_sar_*`,
  `…_manage_sar_*`): this branch implements against those exact names so the two collapse to ONE
  definition when S2 rebases on S1's merge.

- **The mock's payload vs S1's.** The mock built its cards from `{name, server, credential: {kind, set},
  connection: {status, last_poll, error}}`; S1's C5 payload carries `{id, api_url, credential: <kind>,
  status, last_poll, error, retired, host}`. The page reads S1's. `credential` is always "set" for a
  listed cluster (the parser refuses a Secret without one), so the mock's `unset` badge has no live
  state and is not rendered; `host: true` is the mock's `in-cluster` source.
- **A write triggers a discovery.** S1's stage runs on the binding cadence (300 s); a cluster created
  from the form would otherwise appear up to five minutes later, and the reader would refresh into
  nothing. The poller gains `request_discovery()` — an event its discovery thread waits on beside the
  cadence — and every successful write sets it. A Secret written by GitOps is still picked up on the
  cadence; the two paths converge on the same `_discover_once()`.
- **The connection test never touches the registry, the store or a Secret.** It builds a
  `ClusterConfig` from the request through the SAME parser a Secret goes through (`parse_secret` on an
  in-memory Secret object), so a request the test accepts is a Secret discovery would accept, byte for
  byte; then two GETs with that client and nothing else.
- **The three TLS modes and their refusal are the operator's ruling of 2026-09-20** (S1's notes). The
  form offers exactly them; the API refuses `caData` with `insecure: true` before any write, with the
  parser's own finding code (`insecure-with-ca`).
- **The writes default OFF — pending the operator's ruling (the coordinator, 2026-09-20).** Two guards
  encode a product invariant the first suite run tripped: `test_r6_the_api_is_read_only` (no write route
  in the API) and `TestNoPatchVerbAtAnyAuditMode::test_the_only_write_in_the_role_is_the_dashboards_own_lease`
  (the Role's only write is the leader Lease). The dashboard is a READER. So C2–C7 are built with
  `clusterConfig.secrets.writes.enabled` / `GSD_CLUSTER_SECRETS_WRITES_ENABLED` **off by default** — the
  one switch in the chart that is, contrary to the chart-defaults rule, and said so in `values.yaml`:
  with it off, the four write routes are **not registered** (a write-only path is a 404, a POST on the
  read path a 405 — never a route that refuses), the Role has read verbs only, and the tab is read-only
  with the form producing only the YAML twin (Create / Test / Rotate / Delete hidden, a sentence saying
  writes are off and what turning them on means); with it on, the routes register and the Role gains
  `create`/`update`/`delete`. `GET /api/clusterconfigs` carries `secrets.writes` so the page decides
  from the payload. The two guards keep their invariant at the default and gain an EXACT carve-out
  (`test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on`,
  `test_the_cluster_secret_writes_are_the_one_opt_in_exception_and_exactly_that`): any fifth write route
  or any other write verb, in either state, still fails. The false default is a stated exception in
  `tests/test_values_defaults.py` (KEPT_OFF: "a write path on Secrets widens the dashboard's read-only
  posture; off until the operator turns it on"). **Default pending the operator's A/B call of
  2026-09-20; B flips the default and removes the exception** — the code is the same either way: a
  values default, the app default, and the exception entry.
- **Verification against the TLS rig, not the CRC API** (the coordinator, 2026-09-20): S1 deploys
  `local-development/mock-app/deploy/tls-modes/` — three copies of the mock OpenShift app as real TLS
  endpoints, `mock-trusted` (leaf signed by the CA the cluster's trusted bundle carries → the default
  mode), `mock-privateca` (its own CA → only `caData` works), `mock-selfsigned` (bare self-signed → only
  `insecure: true`), each with a labelled Secret. S2's walk (C9) is against that rig.

## Contract

### C1 — the tab

- Id `clusters`, label **Cluster Configurations**, position after Reports (and after Library, #229,
  when both are merged), landing `#page=clusters`. Accent `--tab-clusters`: `#6b3a12` light (8.90:1 on
  `--page #f9f9f7`), `#e0a060` dark (8.67:1 on `#0d0d0d`); `body[data-page="clusters"] { --accent:
  var(--tab-clusters) }`. `tests/test_accessibility.py` measures every `--tab-*` token, so the pair is
  under its 4.5:1 floor automatically.
- Administrator tier on the **host** (`narrowedOnHost()`), like KPIs and Reports: a narrowed reader
  gets the refusal card, and the fetch is skipped for a reader already known to be narrowed.
- One payload, `GET /api/clusterconfigs` (S1 C5), fetched only on this page; `data.clusterconfigs` in
  the auto-refresh fingerprint (the omission #157/#167/#228 each fixed); the page repaints from
  `view.clusterForm` / `view.clusterRotate` state so a poll never destroys what the reader typed
  (the Reports form's rule, `view.reportForm`); focus and caret survive by id (`render()`'s rule).
- The page's parts, in the mock's order: the head card (namespace, the label selector, the count by
  source — `in-cluster` = the host, `values`, `Secret` —, "N Secrets carry the discovery label" from
  `secrets.last_discovery`'s cycle, **Add cluster**); a card per cluster; **Findings** (S1's
  `findings[]`, each with the Secret, the code and the detail; empty → the mock's sentence); **Add
  cluster** with the YAML pane beside it.
- A cluster card: `id`, the source chip (`in-cluster` for `host: true`, `values`, `Secret <name>` for
  `secret:<name>`), `enabled`/`disabled` badge (a `retired` cluster: `disabled` and the foot "its Secret
  is gone — the history is kept"); `api_url`; the credential kind with the badge `set` and, for a Secret
  row, **Rotate** (a panel with one password field and **Overwrite token**); for `in-cluster` / `values`
  rows "read-only — the pod's own ServiceAccount" / "read-only — declared in the chart's values";
  `tls` as `verified · ca: <mode>` or the `insecure` warning badge; labels as chips (wrapping — a chip
  never widens the page); visibility and identity with the chart README's one-liners; the connection:
  the status badge (`ok` / `unreachable` / `auth_failed` / `forbidden` — the store's words — or `never`),
  `last_poll`, the error verbatim, and under `never` the Overview's consequence sentence; the foot:
  **Delete** (two clicks: the first arms it and says "Removes the Secret. Cluster history stays,
  disabled.") on a Secret row, the mock's sentences on the others.
- Every badge carries its word; no colour-only state.

### C2 — `POST /api/clusterconfigs` (create)

Administrator tier; registered only when `clusterConfig.secrets.writes.enabled` (chart) /
`GSD_CLUSTER_SECRETS_WRITES_ENABLED` (app) is on — off (the default, see the notes), the route does not exist.

```json
{"name": "ocp-west", "server": "https://api.ocp-west.example.com:6443",
 "credential": {"kind": "bearerToken", "token": "…"},
 "tls": {"mode": "caData", "caData": "<base64 PEM>"},        // | {"mode": "trustedBundle"} | {"mode": "insecure"}
 "visibility": "self-only", "identity": "none",
 "labels": {"environment": "prod"}}
```

- The Secret written: `metadata.name = gsd-cluster-<name>`, the pod's own namespace, labels
  `groupsync-dashboard.io/secret-type: cluster` plus the request's (a request label may not use the
  `groupsync-dashboard.io/` prefix — refused, it is the app's), annotation
  `groupsync-dashboard.io/managed-by: ui`, `type: Opaque`, `stringData` per S1 C1 with
  `config = {"bearerToken": …, "tlsClientConfig": {"insecure": <bool>[, "caData": …]}}`,
  `enabled: "true"`. The YAML pane on the page renders THIS object with the token as `<redacted>`
  (a test holds the two equal, field for field).
- Refusals, before any write, each `422 {"detail": "<code>: <sentence>"}` with S1's finding codes:
  `credential.kind: oauth` → `oauth-exchange-not-built: the password-for-token exchange is #119 P2,
  not built yet`; `tls.mode: caData` without `caData` or with one that does not load →
  `ca-data-invalid`; `caData` beside `insecure` cannot be expressed by the request shape and a raw
  `config` is not accepted; a `name` that fails the parser's pattern → `name-invalid`; the host's name
  or `https://kubernetes.default.svc` → `host-cluster-not-from-secret`; a `name` already a values
  entry or already discovered → `409 duplicate-cluster-name: <name> is already declared by <source>`;
  a Secret of that `metadata.name` already present → `409`.
- The write goes through the host cluster's client (`POST /api/v1/namespaces/<ns>/secrets`); a 403
  from the API server is `502 {"detail": "the ServiceAccount may not create Secrets here — the chart's
  clusterConfig.secrets.writes switch renders the grant"}`; any other API error is `502` with the
  server's sentence.
- On success: one log line `cluster Secret gsd-cluster-<name> created by <viewer> for cluster <name>`
  (the viewer from the proxy's trusted header — `trusted_viewer(request)` —, the verb, the Secret;
  never a field of the request), `request_discovery()`, `201 {"secret": "gsd-cluster-<name>",
  "cluster": "<name>", "discovery": "requested"}`.

### C3 — `PUT /api/clusterconfigs/{name}/credential` (rotate)

Body `{"token": "…"}`. Only a cluster whose source is `secret:<secret>` (`404` for an unknown name,
`409 not-a-secret-cluster` for a values or host cluster). The app GETs the Secret, **checks the label
itself** (RBAC cannot express "by label": a Secret in the namespace without our label is `409
not-our-secret`, never touched), replaces `config.bearerToken` in place keeping every other key,
PUTs it back. Log line `cluster Secret <secret> credential rotated by <viewer> for cluster <name>`;
`request_discovery()`; `200 {"secret": …, "cluster": …, "discovery": "requested"}`. The old token is
gone from the cluster on the write; the response never carries either.

### C4 — `DELETE /api/clusterconfigs/{name}`

Same eligibility and label check as C3. DELETEs the Secret; log line `cluster Secret <secret> deleted
by <viewer> for cluster <name>`; `request_discovery()` — the next discovery retires the cluster
(`enabled=0`, history kept, S1 C3); `200 {"secret": …, "cluster": …, "retired": "on the next discovery"}`.

### C5 — `POST /api/clusterconfigs/test` (the connection test)

The create body without `labels` (and `name` optional, `probe` when absent). Builds the Secret object in
memory, runs it through `parse_secret` (so every refusal above applies, same codes), then with that
`ClusterConfig`'s client: `GET /version` and `GET /apis/user.openshift.io/v1/users/~`. Returns

```json
{"reachable": true, "server_version": "v1.31.6", "identity": "system:serviceaccount:ns:reader", "error": null}
```

or `{"reachable": false, "server_version": null, "identity": null, "error": "<outcome>: <message>"}` —
`ClusterError`'s outcome words (`unreachable`, `auth_failed`, `forbidden`). A 404 on `users/~` (a
cluster without the OpenShift user API) leaves `identity` null with `reachable` true. Nothing is
stored, registered or logged beyond the line `connection test by <viewer> against <server>: <reachable>`.

### C6 — security (S1 C4, extended to the writes)

- Writes happen only in the pod's own namespace (`own_namespace()`), only on Secrets carrying our
  label (checked by the app before update/delete; set by the app on create), only at the
  administrator tier, only with the writes switch on.
- The credential exists in the request, the Secret and the process's memory: never in a response
  (the create/rotate/test responses above), never in a log line (the audit lines name the person, the
  verb and the Secret — a test greps every log record for the sentinel token), never in SQLite, never
  in `/metrics`. The page's token fields are `type=password`, cleared after a write; `view.clusterForm`
  holds the token in browser memory only until the write.
- The Role's write verbs render only with `clusterConfig.secrets.writes.enabled: true`, and the routes
  exist only with the same switch on in the app, so a chart with the grant and an app without the switch
  never writes — and the reverse cannot write either.

### C7 — the chart

`clusterConfig.secrets.writes.enabled: false` (OFF by default — the notes) → `clusterSecretsWritesEnabled`
in the ConfigMap and `create`, `update`, `delete` appended to the `-cluster-secrets` Role's verbs
(the same Role; off → `get`, `list`, `watch` only). README rows; chart 0.43.0; a CHANGELOG entry.

### C8 — tests

`tests/test_clusterconfig_tab.py`: the writer over a fake host client that records requests (create →
the Secret object the API sends equals the page's YAML twin with the token substituted; rotate keeps
every other `config` key; delete; the label check refuses a Secret without our label; the namespace is
`own_namespace()`'s); the API (each route's tier, each refusal code, the writes switch off → 409, the
duplicate rules, the API-server 403 → 502, the discovery request set); the connection test (reachable /
unreachable / auth_failed, the identity, nothing written); the no-credential pin (every response, every
log record, the store dump, `/metrics` — with the sentinel). `tests/test_ui.py::TestClusterConfigPage`:
the cards from a cold URL (`#page=clusters`), the source chips, Rotate/Delete present only on Secret
rows, the YAML preview following the inputs, the disabled oauth radio with its reason, the refusal card
for a narrowed reader, a create through the form landing as a card after the (fake) discovery, 375 px
without horizontal scroll, focus surviving a repaint; `TestTheShellAtPhoneWidth.TABS` gains `clusters`.
`tests/test_clusterconfig.py::TestChart` gains the writes switch (verbs on / off). `test_type_scale`
and `test_accessibility` hold the CSS.

### C9 — verification on CRC (when the lab is S2's)

Against S1's TLS rig (`local-development/mock-app/deploy/tls-modes/`), never the CRC API:
`reports/<date>_cluster-configurations/` — the tab with `crc-local` and the three rig rows
(`mock-trusted` default mode, `mock-privateca` `caData`, `mock-selfsigned` `insecure`) with their source
chips, `tls` modes and connection states; the finding for a `caData`+`insecure` Secret; the form
creating a FOURTH cluster against one of the mocks through the UI — Test connection, Create Secret,
the card appearing after the requested discovery — then Rotate (the new token polls), then Delete
(the card disabled, its rows kept); 1280 and 375; `errors : []`.

## Design

### S2.1 `gsd/kube.py`

`ClusterClient` gains `_send(client, method, path, *, json=None) -> dict | None` — the write twin of
`_get`: `client.request(method, path, json=json)`, the same status → `ClusterError` mapping (401
`AUTH_FAILED`, 403 `FORBIDDEN` naming the verb, ≥400 `UNREACHABLE` with the server's text), `None` for a
204/empty body, JSON otherwise. `_get` is untouched.

### S2.2 `gsd/clusterconfig/writer.py` (new)

```python
SECRET_NAME_PREFIX = "gsd-cluster-"
MANAGED_BY_ANNOTATION = "groupsync-dashboard.io/managed-by"

@dataclass(frozen=True)
class CreateRequest: name, server, credential_kind, token, tls_mode, ca_data, visibility, identity, labels

class WriteRefused(Exception): code, detail          # → 422 / 409 by the route
class WriteFailed(Exception): outcome, message        # → 502

def secret_object(req, namespace) -> dict            # the Secret the API writes; the page's twin
def validate(req, *, host_name, taken: dict[str, str]) -> ClusterConfig   # parse_secret + the duplicate rules
def create(host_client, namespace, req, *, host_name, taken) -> str
def rotate(host_client, namespace, secret_name, token) -> None
def delete(host_client, namespace, secret_name) -> None
def test_connection(req, *, host_name, timeout) -> dict
def _labelled(obj) -> bool                           # the label check before update/delete
```

### S2.3 `gsd/config.py`, `gsd/poller.py`

`Settings.cluster_secrets_writes_enabled: bool = False` (`GSD_CLUSTER_SECRETS_WRITES_ENABLED` /
`clusterSecretsWritesEnabled`). `Poller._discover_now = threading.Event()`; `request_discovery()` sets
it; `_run_discovery` waits on it with the cadence as the timeout and clears it after a cycle.

### S2.4 `gsd/api.py`

The four routes after `list_cluster_configs`, each `require_admin_tier(request)` first, the writes
switch second, then the writer; pydantic bodies `ClusterCreateBody`, `ClusterRotateBody`,
`ClusterTestBody`; the host client is `ClusterClient(settings.host_cluster())`; `app.state.poller`
carries the poller so a route can request a discovery (set in `build_app`; `None` when
`run_poller=False`, and the routes tolerate it).

### S2.5 `gsd/static/index.html`, `gsd/static/app.css`

`view.clusterForm` (the form's state), `view.clusterRotate` (the open rotate panel's name), the tab, the
dispatch (`clusterConfigPage()` + `wireClusterConfig()`), the fetch plan and the landing (the KPI
pattern with `narrowedOnHost()`), the fingerprint entry, the page functions ported from the mock
(`ccSourceChip`, `ccClusterCard`, `ccFindings`, `ccAddForm`, `ccYaml`), the writes through `api()`'s
`fetch` with `method` (a small `apiSend(path, method, body)` beside `api()`), the messages under the form
and the cards. `app.css`: `--tab-clusters` in the three token blocks, `body[data-page="clusters"]`, the
`.cc-*` rules ported from the mock (`.cc-kv`, `.cc-field`, `.cc-choices`, `.cc-warn`, `.cc-grid`, `.cc-yaml`,
`.cc-acts`, `.cc-foot`, `.cc-hint`, `.cc-chips`), every value on the ladders.

### S2.6 Chart, docs

`values.yaml` `clusterConfig.secrets.writes.enabled: true` under the S1 stanza with its comment;
`templates/configmap.yaml` `clusterSecretsWritesEnabled`; `templates/cluster-secrets-rbac.yaml` the
conditional verbs; README rows; `Chart.yaml` 0.43.0 with its history line; `API.md` the four routes;
`docs/CHANGELOG.md` the entry.
