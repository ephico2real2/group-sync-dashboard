# SPEC D3 — Refresh: probe an existing cluster with its stored credential; it never re-binds (#311)

| | |
|---|---|
| Programme | Epic D (#384), Reconnect a cluster from the screen — build step 1 of 4, before Rejoin (#316) |
| Batch | D — reconnect |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 1.2.0, chart 0.59.4 |
| Issue | [#311](https://github.com/ephico2real2/group-sync-dashboard/issues/311) |
| Status | merged |
| Source | Written by the implementer (OB1-lite) from #311's body, its reopening comment and its decisions comment of 2026-09-27, measured on main `6740e1e` (application 1.1.0); there is no separate design-agent output |

## How to read this spec

Each section starts with the plain point. "The decisions" are the operator's, copied from the issue.
"What Refresh does" and "What Refresh must never do" are the contract. The tables list every answer the
route gives and every state the button shows. "Tests" maps each rule to the test that holds it.
Citations use `file#name` anchors, so they move with the code.

## Orchestrator's notes

- The four decisions in §1 are the operator's (#311, comment of 2026-09-27). This spec does not re-open them.
- **Short by the brief's instruction.** The brief asked for a short spec, so the code is not carried here as
  implementation blocks. The PR's diff is the implementation. §6 names every function it adds or changes.
- **Decision the issue did not make — D3-1, `userSelfLogin` rows.** A `self-login` cluster stores no credential:
  its credential is the session the poll thread holds (`gsd/selflogin.py#SelfLoginSessions`), and getting or
  renewing that session is a login. Its kind is not in `CREDENTIAL_PENDING_REASONS`, so a plain probe of
  `settings.cluster(name)` would fail locally with `auth_failed` and send the reader to Rejoin for a cluster
  Rejoin does not serve. Refresh therefore answers a `self-login` row with `not-probed` and makes no network
  call, like the pending row. The credential row already shows the session's state and expiry. Probing with the
  session the poll thread holds is possible later. It would read another thread's session and would answer only on
  the replica that holds it, so it is left out.
- **Decision the issue did not make — D3-2, one-in-flight on the server too.** The page allows one probe per
  cluster. The route enforces the same rule, per process: a second request for a cluster whose probe is still
  running answers `409` and makes no network call. Two tabs, or a script, cannot queue work.
- **Decision the issue did not make — D3-3, the success word.** The API answers `ok`, the poller's word
  (`gsd/kube.py#OK`), so the route and the logs use one vocabulary. The page shows `ok` as **connected**, the
  word the issue and the mock use for the succeeded state.

## 1. The decisions (the operator, 2026-09-27)

| # | Decision | Why |
|---|---|---|
| 1 | The route is `POST /api/clusterconfigs/{name}/refresh`. | It stays under the prefix that is cluster-admin only. `/api/clusters/…` is reachable at every tier, and a probe that names what is wrong with a credential is an administrator's view. |
| 2 | It registers inside the writes carve-out, like `POST /api/clusterconfigs/test`. | `test_r6_the_api_is_read_only` stays true for a default install. A default install (writes off) has no Refresh. |
| 3 | Every non-retired row gets the button. | Probing the host's own in-cluster ServiceAccount is harmless. A retired row has no configuration to probe, so the route answers `404` for it. |
| 4 | A `saTokenLookup` row with no Secret yet returns its pending reason from `CREDENTIAL_PENDING_REASONS`, with no network call. | There is no credential yet. Probing would report a false `auth_failed` for a credential that was never presented. |

## 2. What Refresh does

**The plain point: Refresh asks the cluster "does the credential I already hold still work?" and reports the
answer. It changes nothing.**

1. The page calls `POST /api/clusterconfigs/{name}/refresh` with no body.
2. The route checks the caller exactly as `/test` does (`gsd/api.py#_writes_gate`): a proxy-verified identity,
   the cluster-admin tier (#322), and cluster Secret discovery on. Anyone else gets `403`.
3. It looks the cluster up by name in the live configuration (`settings.cluster(name)`). An unknown or retired
   name gets `404`.
4. If a probe of that cluster is already running in this process, it answers `409`.
5. If the cluster's credential kind is pending (`oauth`, `remote-lookup`) or is `self-login`, it answers at
   once, with no network call (§1 decision 4; note D3-1).
6. Otherwise it runs the connection test's own probe (`gsd/clusterconfig/writer.py#_probe`, shared with
   `test_connection`) on the stored configuration: `GET /version`, then `GET /apis/user.openshift.io/v1/users/~`,
   with the cluster's own token and TLS settings. `reachable` is set last, so an anonymous-readable `/version`
   cannot make a bad token look good.
7. It logs one line, `cluster-refreshed cluster=<name> credential=<kind> by=<person> outcome=<word>`, with the
   credential redacted.
8. It answers `200 {"outcome", "message", "at"}`.

### The answer

`at` is the instant the answer was made, ISO-8601 UTC (`2026-09-27T14:05:40Z`). `message` is one sentence.
Neither ever carries a token.

| `outcome` | When | Network call? |
|---|---|---|
| `ok` | `/version` and `users/~` both answered with the stored credential (a cluster without the OpenShift user API answers `404` there, which still counts as authenticated) | yes |
| `auth_failed` | the cluster answered `401`, or the token could not be read on this pod (the poller's `phase=credential` case) | yes, or none when the token could not be read |
| `forbidden` | the cluster answered `403` | yes |
| `cert-verify-failed` | the TLS certificate did not verify against the trust this cluster is configured with | yes |
| `unreachable` | no answer, a transport error, any other HTTP error, or a CA bundle this pod could not load | yes, or none when the CA could not be loaded |
| `pending` | the credential kind is in `CREDENTIAL_PENDING_REASONS`; `message` is that reason | **no** |
| `not-probed` | the credential kind is `self-login` (note D3-1) | **no** |

The first five words are the poller's own (`gsd/kube.py#AUTH_FAILED`, `FORBIDDEN`, `UNREACHABLE`, and
`cert-verify-failed` from `gsd/poller.py#_log_poll_failure`'s TLS branch), so the button and the log agree.

### Refusals

| Status | When |
|---|---|
| `403` | no proxy-verified identity, or the caller is below the cluster-admin tier |
| `404` | the name is unknown or retired; or the deployment's writes are off, so the route does not exist |
| `409` | a probe of this cluster is already in flight in this process; or cluster Secret discovery is off, or the pod names no namespace or host (the same `409`s as `/test`) |

## 3. What Refresh must never do

**The plain point: Refresh probes. It never logs in, never binds, and never writes.**

| Never | Why |
|---|---|
| call `FleetLogin`, the lookup (`gsd/fleetlookup.py#lookup`), or `SelfLoginSessions.credential_for` | Each of those can send a password to a directory. A button that binds on demand is the fastest way to lock out the fleet account (#283, #284). If the stored credential is refused, the fix is Rejoin (#316), where a person supplies their own credential once. |
| touch `CredentialGate` or a fleet account's Lease | The gate records bound failures. Refresh presents no password, so it has nothing to record and nothing to consult. |
| store anything | No Secret write, no poll outcome, no database row, no metric. The card's `connection` row still shows the last poll, unchanged. |
| rotate anything | The token it presents is the one already stored. |
| force a poll or a discovery | It does not call `Poller.request_discovery` or wake a poll thread. The next poll comes at its usual time. |
| retry | One probe per press. The next press is the retry. |
| echo a token | Not in the answer, not in the log line. The probe client redacts its own token from what a remote echoes, and the answer is scrubbed again with every secret the cluster holds. |

## 4. The page

**The plain point: a Refresh button on each card, beside Delete, that shows what it is doing and what it
found, in words.**

The button sits in the card's `.cc-acts` row. On a Secret row it sits beside Delete. On the host, values and
ConfigMap rows it gets its own `.cc-acts` row above the card's footer. It exists only when `ccWritesOn()` is true
(the writes switch and the cluster-admin tier), so it is absent, not disabled, for everyone else. A retired row
has no button.

### The four states

| State | Button | Line under the connection row |
|---|---|---|
| idle | `Refresh` | none |
| in flight | `Refreshing…`, disabled, `aria-busy="true"` | `Refresh: probing /version and users/~ with the stored credential…` |
| succeeded (`ok`) | `Refresh` | `Refresh:` ● `connected · 2026-09-27T14:05:40Z` — the message |
| refused (any other word) | `Refresh` | `Refresh:` ■ `<outcome> · <at>` — the message |

- Every state carries a word. Colour and the badge glyph are a second channel only.
- `pending` and `not-probed` use the grey `unknown` badge: nothing was refused, nothing was asked.
- A request that fails before the probe (for example a `403`) is shown as refused, with `HTTP <status>` as the
  word and the refusal's own sentence.
- **On `auth_failed` the line adds the next step, as text:** Rejoin (#316), not built yet; until then, replace
  the credential where it is written. No Rejoin control is drawn until Rejoin exists.
- The instant is shown exactly as the server stamped it, never as an age.

### Surviving the repaint

The tab repaints on every poll that changes `/api/clusterconfigs`, which is every minute, because `last_poll`
moves. So the state lives in `view.clusterRefresh[<cluster id>]`, never in the DOM. The repaint redraws the
button and the line from that state. A probe that lands after a repaint writes its answer into the same slot and
paints it.

### One in flight

A press while the cluster's state is `in flight` does nothing, whether the click reaches the old button or the
repainted one. The server's `409` (note D3-2) is the second guard.

## 5. Tests

| Rule | Test |
|---|---|
| the stored credential is used, the answer is `{outcome, message, at}` in the poller's words | `tests/test_cluster_refresh.py` — the probe sees the stored token; `ok`, `auth_failed`, `forbidden`, `unreachable`, `cert-verify-failed` |
| never calls `FleetLogin`, the lookup or a self-login session | the same file — each is patched to fail the test if called |
| a pending row and a self-login row make no network call | the same file — the client is patched to fail if built |
| unknown or retired name is `404`; below the tier is `403`; a second probe in flight is `409` | the same file |
| registered only when writes are on | `tests/test_api_contract.py` — the carve-out list gains the route; `test_r6_the_api_is_read_only` unchanged |
| no token in the answer or the log | the same file — a remote that echoes the bearer |
| nothing stored, no discovery requested | the same file — the poll outcome row and a recording poller |
| the four states survive a repaint; one in flight | `tests/test_ui.py::TestClusterConfigPage` |

## 6. Where the code goes

| File | Change |
|---|---|
| `local-development/gsd/clusterconfig/writer.py` | `_probe` (the probe, moved out of `test_connection` unchanged); `test_connection` calls it; `refresh` (new) |
| `local-development/gsd/api.py` | the route `refresh_cluster_config`, inside `if writes_on:` beside `/test`, with a per-process in-flight set |
| `local-development/gsd/static/index.html` | `view.clusterRefresh`; `ccRefreshButton`, `ccRefreshLine` (the line reuses `.cc-consq`); the card's `.cc-acts`; the click handler in `wireClusterConfig` |
| `local-development/gsd/static/app.css` | one rule: a disabled button in `.cc-acts` reads muted, with the progress cursor |
