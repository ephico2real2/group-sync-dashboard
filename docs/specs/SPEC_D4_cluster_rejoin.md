# SPEC D4 — Rejoin: a cluster administrator signs in to a remote cluster as themselves, once, and the dashboard fetches a fresh poller token and forgets the password (#316)

| | |
|---|---|
| Programme | Epic D (#384), Reconnect a cluster from the screen — build step 3, after Refresh (#311, SPEC_D3) and the duplicate-URL warning (#314) |
| Batch | D — reconnect |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | the next application MINOR at merge and the chart PATCH its appVersion move takes; the orchestrator sets both |
| Issue | [#316](https://github.com/ephico2real2/group-sync-dashboard/issues/316) |
| Status | specified |
| Source | OB3's specification of 2026-09-27 (implementer, phase 1: research and the spec, no production code), written from issue #316 (its body, the runbook requirement and the design refinements of 2026-09-23, and D8 as the operator decided it on 2026-09-26), epic #384 and its mockup, SPEC_D3, SPEC_S4a, SPEC_S4c, SPEC_S4d, SPEC_S4e (branch `fix/432-ping-account-scope`, unmerged) and main `b18e62d` (application 1.3.0). Measured on this machine and read-only on the reference cluster. §8's blocks were cut from a copy of `b18e62d` with the design implemented, and applied back to a clean clone for the proof in §6 |

## How to read this spec

Each section opens with its point in one bold line; the rest is the evidence. §1 is the whole change in one table.
§2 is what was read and measured, each with its source. §3 is the design: the route and its gates, the
composition, the answers, the provenance, the dialog, the redaction pin, the budget over the system, what must not
change, what is left, and the decisions the issue left open. §4 is the runbook. §5 is the change file by file.
§6 maps every test to its result before and after, measured. §7 is the lab walk for the implementing PR. §8 is the
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_D4_cluster_rejoin.md . --apply

Line citations into the code at `b18e62d` are plain text, file:line, to keep them apart from the maintained
`path#anchor` citations. Upstream sources are cited with the commit they were read at, from the raw file with line
numbers (`curl` of the raw bytes, `nl -ba`). "Before" and "after" are `b18e62d` without and with §8's code blocks,
with the same test blocks in both.

**The constraint that overrides everything here:** nothing in this spec, its tests or its walk logs in as any
account, and never as the fleet account. The tests use placeholder names against a fake target. The research on the
lab was read-only, through the kubeconfig handed to it.

## Orchestrator's notes

- **The id and the file.** The issue proposed `SPEC_R1_rejoin.md` and left the name to the orchestrator; the brief
  names `SPEC_D4_cluster_rejoin.md`, the next step of batch D after SPEC_D3 (Refresh). The index row sits between S4d
  (#315) and L1 (#321), because `local-development/tests/test_specs_index.py` holds the rows in issue order.
- **The versions are the orchestrator's**, as for S4e: the release commit beside the implementing commit moves
  `pyproject.toml`, `gsd/__init__.py` and `appVersion` to the next MINOR, and the chart by the PATCH that move takes.
  No block here touches them. The PR needs that commit: `local-development/check-app-version-bump.py` requires the
  next MINOR for a change under `gsd/`, and CI's `version-bump` job refuses a change under `charts/` without a new
  `Chart.yaml` version (this change touches `values.yaml`, `README.md`, `CLUSTER_CREDENTIALS.md` and adds
  `RUNBOOK.md`).
- **D8 is decided, in its simple form** (the operator, 2026-09-26, #316): *"we log the response from the remote cluster
  but don't make things very complicated. We can check if the person joining the cluster is also a cluster admin on
  the remote cluster."* §3.3 step 4 is exactly that: one review, its answer logged, a no reads and writes nothing, and
  the login revoked on every exit as every `FleetLogin` already does.
- **The decisions the issue left open are in §3.11**, each with the evidence and the recommendation. The operator
  rules on them; this spec implements the recommendations.
- **S4e (#432) merged first, in #438 (application 1.4.0).** The daily ping now presents the password only as an
  account the configuration declares. This spec never writes the person's name into `lookup-account` or any
  declaration (§3.5), so it was safe before S4e and is safe with it;
  `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` runs the ping and counts the wire. With S4e taking
  index slot 31, this spec takes 32 (the orchestrator, merging main into this branch on 2026-09-27).
- **The runbook's commands are fenced with `~~~`.** `local-development/apply-spec-blocks.py` ends a block's fence at the
  first line that is exactly three backticks, so a Markdown file created by a block cannot carry backtick fences of
  its own. Tilde fences are CommonMark's other fence and render the same.
- **Three things found while writing, outside this change, for the orchestrator.** (1) The lookup's own session has the
  gap this spec's redaction pin found in Rejoin's first draft: `gsd/fleetlookup.py#lookup` reads the token Secret inside
  the `FleetLogin` session but never hands that token to `FleetLogin.add_secrets`, so a revoke that fails with a body
  echoing it writes it into `fleet-logout-failed`. Rejoin calls `add_secrets` (§8); the lookup must not change here, so
  it is a separate issue. (2) The card's element ids are `cc-refresh-<id>` and `cc-refresh-result-<id>`, so a cluster
  named `result-east` beside `east` gets a colliding id. Rejoin's dialog uses its own `rejoin-` prefix and cannot
  collide; the card's pattern is Refresh's and is left alone. (3) `gsd/config.py#valid_bootstrap_username` accepts a
  name that ends in a newline: Python's `$` also matches before a final newline, so `valid_bootstrap_username("svc\n")`
  is `True` (measured). The chart's own guard runs the same pattern through Go's `regexp`, whose `$` is the end of the
  text (measured, go1.27.1: `"svc\n"` does not match), so a values stanza cannot carry one; a Secret's stanza
  (clusterconfig/parser.py:197) and a `lookup-account` annotation (clusterconfig/reader.py:95) are read through the
  Python grammar and can. Rejoin refuses such a username itself and strips the fleet names it compares (§3.1); the
  shared grammar is left as it is, because tightening it would refuse Secrets that load today.
- **The figure.** §8 edits `docs/diagrams/remote-cluster-access/source.html`; the PNGs are binary and are re-rendered
  in the implementing commit (§5). The renderer is not byte-stable: measured, three figures whose source did not change
  came out a few bytes different. Commit only `joining-a-cluster.light.png` and `joining-a-cluster.dark.png`.

## 1. The point, in one table

**A cluster administrator signs in to a remote cluster as themselves, once; the dashboard fetches the poller's
token there and forgets the password.**

| | |
|---|---|
| **What goes wrong today** | When a remote's stored token stops working, the only repair is `oc create token` on the remote plus `oc patch secret` on the host: someone who is cluster-admin on both clusters, with two sessions (#316's body). The Secret it leaves names nobody. |
| **The change** | `POST /api/clusterconfigs/{name}/rejoin`, offered on the card after Refresh answers `auth_failed` or `pending`. One login as the person, one question to the remote about that person (D8), one read of the poller's token Secret, the login revoked, one write of `gsd-cluster-<name>` with the person's provenance. |
| **The safety property** | The password is presented at most once per press, is never retried, never stored and never presented as any other account, and the fleet account is never used (§3.8, measured). |
| **The gates** | The host: the cluster-admin tier (#322) and the writes switch. The remote: its own RBAC, asked about the person with the person's own login (D8). |
| **What it reuses** | #283's `FleetLogin`, #284's `read_sa_token` and `store`, #315's `CredentialGate` (the poller's one instance), #311's card and its route pattern, #143's static dialog. |
| **What is new** | `gsd/rejoin.py` (one module), the route, `rejoinable` on each row, three provenance annotations and the `rejoin` token-source, the dialog, `RUNBOOK.md`. |
| **What does not change** | Refresh, the credential gate, the lookup, the daily ping, self-login, Rotate, Delete, Test, the Add form and its `oauth` refusal, the dashboard ServiceAccount's permissions (REMOVED 0, ADDED 0). |

## 2. Read and measured

### 2.1 The login, and what it leaves behind

**`oc login -u … -p …` is one GET on the remote's OAuth server with Basic auth; it leaves one `OAuthAccessToken`, a
full-scope token for that person, which must be revoked.**

| source | what it says or shows |
|---|---|
| openshift-docs `270ee60`, modules/oauth-token-requests.adoc | lines 22-23: `openshift-challenging-client` "Requests tokens with a user-agent that can handle `WWW-Authenticate` challenges". Lines 37-44: every token request goes to `/oauth/authorize`, and a CLI authenticates by a `WWW-Authenticate` challenge. Lines 56-60: Basic challenges need a non-empty `X-CSRF-Token` header. Lines 62-66: an identity provider that does not support challenges needs a browser |
| SPEC_S4a §2 (measured 2026-09-21) | discovery at `/.well-known/oauth-authorization-server`; the authorize GET answered by a 302 whose `Location` fragment carries the token; the token's object is `sha256~` + base64url(sha256(the rest)); `DELETE …/useroauthaccesstokens/<name>` with the token itself as bearer answers 200; the token keeps authenticating from the API server's cache for about 121 s |
| the lab, read-only, 2026-09-27 | discovery names `https://oauth-openshift.apps-crc.testing/oauth/authorize`. `oauthclients/openshift-challenging-client`: `grantMethod: auto`, `respondWithChallenges: true`, `accessTokenMaxAgeSeconds: null`. `oauths/cluster`: `tokenConfig.accessTokenMaxAgeSeconds: 31536000`; identity providers `developer` (HTPasswd) and `ldap-local` (LDAP), both `mappingMethod: claim`. 189 `OAuthAccessToken` objects at 16:37Z; all 30 challenging-client ones carry `scopes: [user:full]` and `expiresIn: 31536000` (counted at 17:43Z); `kubeadmin` alone held 13 of them, left by `oc login` |
| OKD 4.20, "Managing user-owned OAuth access tokens" | `oc get useroauthaccesstokens --field-selector=clientName=…` lists your own; `oc delete useroauthaccesstokens <token_name>` deletes one; "Token names are not sensitive and cannot be used to log in"; "Deleting an OAuth access token logs out the user from all sessions that use the token" |
| the lab's RBAC | `system:openshift:useroauthaccesstoken-manager` (get, list, watch, delete `useroauthaccesstokens`) is bound to `system:authenticated:oauth`, so any person may list and delete their own |

**Decides.** The login is `FleetLogin` unchanged: the flow, the retry rule once the password is on the wire, and the
revoke on every exit. A Rejoin mints a `user:full` token for a cluster administrator that lives a year on the lab,
so the revoke is load-bearing, and a failed one is named to the person with the command that deletes it (§3.4). A
remote whose identity provider has no password challenge (OpenID Connect, GitHub, Google) cannot be rejoined: its
authorize answer carries no token and the login fails; the runbook names the manual path.

### 2.2 How the person's login reads the poller's token Secret

**The same read #284 makes, as the person instead of the fleet account.**

- `gsd/fleetlookup.py#read_sa_token` (fleetlookup.py:272-339) GETs
  `group-sync-operator/group-sync-dashboard-cluster-poller-token` by name with the session as the bearer, checks its
  type, its owner annotation and the legacy-token cleaner's `invalid-since` label, and decodes the token first so
  every refusal carries it as a secret to scrub.
- The lab, read-only: the Secret exists, `type: kubernetes.io/service-account-token`, annotated
  `kubernetes.io/service-account.name: group-sync-dashboard-cluster-poller`, labelled
  `kubernetes.io/legacy-token-last-used: 2026-09-27`, with `helm.sh/resource-policy: keep`.
- A cluster administrator may `get` it. So may an `admin` of `group-sync-operator`, who is not a cluster
  administrator (`docs/DESIGN_remote_cluster_access.md` §5). D8 is the stricter gate, and it runs first.

### 2.3 D8: one SelfSubjectAccessReview, with the login's own token

**A person may always ask the remote about themselves; the answer is a boolean and a reason, and nothing is stored.**

| source | what it says or shows |
|---|---|
| kubernetes/website `ce7891d`, content/en/docs/reference/access-authn-authz/authorization.md | lines 403-405: `kubectl auth can-i` "uses the `SelfSubjectAccessReview` API to determine if the current user can perform a given action". Lines 469-470: the answer is the returned object's `status`. Lines 472-500: the request and answer shapes |
| kubernetes/kubernetes `6c1c770`, staging/src/k8s.io/api/authorization/v1/types.go | lines 56-58: "Self is a special case, because users should always be able to check whether they can perform an action". Lines 258-276: `status` carries `allowed`, optional `denied`, `reason` and `evaluationError` |
| the lab: who may ask | `create selfsubjectaccessreviews` reaches `system:authenticated` through the bindings `basic-users`, `self-access-reviewers` and `system:basic-user`: no grant is needed |
| the lab: the exchange, JSON (`oc create -f` of the review, as the handed kubeconfig's `kubeadmin`) | asked `{"verb": "update", "group": "rbac.authorization.k8s.io", "resource": "clusterrolebindings"}`, answered `{"allowed": true, "reason": "RBAC: allowed by ClusterRoleBinding \"kubeadmin\" of ClusterRole \"cluster-admin\" to User \"kubeadmin\""}` with empty `metadata`; `oc get selfsubjectaccessreviews` answers `MethodNotAllowed`: nothing was kept |
| the lab: who passes | `oc adm policy who-can update clusterrolebindings.rbac.authorization.k8s.io`: the user `kubeadmin` and the groups `system:cluster-admins` and `system:masters` (plus system ServiceAccounts); no other person |

**Decides.** D8 is one `SelfSubjectAccessReview`, sent with the login's own `user:full` token, so the remote answers
for the person and the groups it resolves for them. It asks the host's own cluster-admin question,
`visibility.clusterAdminSar`, built as the host's `TierResolver` builds it (kube.py:1479-1495), so one definition of
"cluster administrator" serves both clusters. It runs before the token read. Only a boolean `allowed: true` is a yes;
anything else refuses. The remote's answer (`allowed`, `reason`, `evaluationError`) is logged, scrubbed.

### 2.4 Keeping the password out of every place it could land

**The password crosses one TLS hop into the app and one into the remote's OAuth server; it is in no URL, no log, no
store, no answer and no browser storage.**

| place | what could carry it | how it is kept out | source |
|---|---|---|---|
| a URL | a native form submission (GET by default) | the dialog has no `<form>`; the password travels in a POST body | the dialog (§3.6) |
| the proxy's request log | oauth-proxy's `-request-logging` writes the request URI | never the body or the `Authorization` header, and it is off by default | `charts/group-sync-dashboard/values.yaml` (`requestLogging`) |
| uvicorn's access log | the request line | method, path and status only | uvicorn 0.53.0, config.py:94 |
| the usage record | the activity middleware | records the user and the email, never the path or the body | api.py:939-942 |
| a 422 answer | FastAPI's validation of a typed body quotes a non-object body in `input` | measured with FastAPI 0.141.1 and pydantic 2.13.5: a typed `dict` body echoed `"input": "<the password>"` for a JSON string and for a list. The route takes `body: Any = Body(None)`, which FastAPI passes through unvalidated (measured: no echo), and refuses the shape itself, naming fields and never values | §3.1 |
| the app's lines, answers and refusals | a remote's echo quoted in a message | every line goes through the emit helper with the secrets in play; `FleetLogin` scrubs every message; Rejoin scrubs every answer with the password, its Basic form, the login's token and the token read | `gsd/clusterconfig/events.py#event`, `gsd/fleetlogin.py#FleetLogin._scrub`, §3.7 |
| a traceback | an exception's message | Python prints frames and messages, not local variables; every message on this path is scrubbed | §3.7 |
| the remote's audit log | the authorize request | the oauth-server audit log is written at Metadata level: user, verb, URI and decision, never headers. The password is in the `Authorization` header, never the URI | openshift-docs `270ee60` modules/nodes-nodes-audit-config-about.adoc lines 35, 61-63; `gsd/auditlog.py`'s module docstring |
| the host's audit log | the Secret write | the password never reaches the host's API server; the Secret the dashboard writes holds the token read, and Secrets are logged at metadata level under every profile | the same file, line 61 |
| the database | a row | Rejoin writes none; the Logins row the audit-log capture later stores carries the username and the decision | §3.7 (the store dumped) |
| the Secret | the write | the token read and the provenance, which names people, not secrets | §3.5 |
| the credential gate | a refused password | 64 bits of its SHA-256, in the process's memory, never on disk; a durable copy was rejected (§3.11, D4-7) | `gsd/fleetlookup.py#CredentialGate` |
| browser storage | the page | the page's `localStorage` holds only `gsd-mode` and `gsd-palette` (index.html:16, 82); the fields are read at the press and never copied into `view` | §3.6 |
| the browser's password manager | autofill and save prompts | `autocomplete="off"`: "When an element's autofill field name is "off", the user agent should not remember the control's data, and should not offer past values to the user". The same section lets a user agent override it, and lets it treat a text field followed by a password field as `username` and `current-password`: the page's own guarantee is that it stores nothing | WHATWG HTML, "Autofilling form controls: the autocomplete attribute" |
| the back/forward cache | a page left with the dialog open | the page is served `Cache-Control: no-cache, must-revalidate`, not `no-store` (api.py:3231), so the cache may keep typed values; the fields are cleared on `pagehide` | §3.6 |
| the idle sign-out | the dialog stays on screen while the page navigates away | `idleExpire` blanks `#main` and then navigates (index.html:8143-8160); it now closes the dialog first | §3.6 |

### 2.5 Can anything make one press run twice?

**Each layer between the button and the directory was read for a retry. One can resend, the browser, and only in a
narrow case this deployment's router makes rare.**

| layer | does it replay a POST it already sent? | source |
|---|---|---|
| the page | no: one request per press; the button is disabled and the password field emptied as the request leaves | §3.6, measured (§6) |
| the browser (Chromium) | **yes, in one case**: a reused keep-alive connection that closes before any response header arrives is resent, and the method is not consulted | chromium/src `71467d7`, net/http/http_network_transaction.cc lines 2103-2166 (`HandleIOError`) and 2331-2339 (`ShouldResendRequest`: "connection_is_proven && !has_received_headers") |
| the OpenShift router (HAProxy) | no: `retry-on` defaults to `conn-failure`, "retry when the connection or the SSL handshake failed and the request could not be sent", and the router's template sets none | HAProxy v2.8.0, doc/configuration.txt lines 11264-11344; openshift/router `6c5868c`, images/router/haproxy/conf/haproxy-config.template lines 164-170 and 652-693 |
| oauth-proxy (Go's `http.Transport`) | no: a request that was written is replayed only when its method is idempotent or it carries `Idempotency-Key` | golang/go `2ff5743`, src/net/http/transport.go lines 836-881 and src/net/http/request.go lines 1557-1571 |
| the app | no: one Rejoin at a time per process, the second answered `409` | §3.1, measured |
| the login | no: `ONE_TRY` | §3.3, measured |

**Decides.** The browser's resend needs the router to drop the browser's connection after reading the request and
before sending any header. The router answers a backend that died mid-request with a status of its own: a 502
"when the server returns an empty, invalid or incomplete response", a 504 "when the response timeout strikes"
(HAProxy v2.8.0, doc/configuration.txt lines 375-400). If it does
happen on the same pod, the resend meets the one-at-a-time `409` while the first runs, and the gate after a bound
failure; after a success it is a second successful login of a correct password, which counts toward no lockout. It
is stated in §3.8 and not guarded further: a client nonce would not survive the restart the only other cause is.

### 2.6 The code at `b18e62d`: what is reused, and what must change

**Every piece exists; four of them speak to the fleet account and one would hand the person to the daily ping.**

| piece | where | reused as is, or changed |
|---|---|---|
| `FleetLogin` | fleetlogin.py:309-744 | reused: the flow, `policy=`, the revoke on exit (366-372), `add_secrets` (374-376). Its refusal and next-try wording (fleetlogin.py:718-744) tells the reader to rotate the fleet password Secret, so the two strings become class attributes a subclass restates, byte-identical for the fleet (measured, §6) |
| `CredentialGate` | fleetlookup.py:102-177 | reused as the lookup uses it: `account_refusal` (152) before the login, `refuse` (171) after a bound failure; never `spend` |
| `read_sa_token` | fleetlookup.py:272-339 | reused as is; its refusal `action` names the fleet account, so Rejoin writes its own sentence for the person (§3.4) |
| `store` and `writer.store_lookup` | fleetlookup.py:360-391, writer.py:331-374 | changed: both take the Rejoin's provenance; the lookup's own values are unchanged |
| the "ours" rule | reader.py:122-129, registry.py:99-102 | changed: `writer.owned_by_mode` also counts `rejoin` over a `saTokenLookup` stanza, so the stanza keeps its policy and raises no `shadows-values-entry` |
| the daily ping's targets | poller.py:1726-1729, 1815 | unchanged, and the reason for §3.5: a Secret with `token-source: remote-lookup` and a `lookup-account` is pinged as that account, with the fleet password |
| the Add form's `oauth` refusal | writer.py:182-183 | unchanged (§3.11, D4-13) |
| the writes gate, unknown keys, the Refresh route's pattern | api.py:1180-1199, 1229-1233, 1346-1368 | reused |
| the static dialog | index.html:132-146 (`#ns-preview`) | the pattern Rejoin's dialog follows |

## 3. Design

### 3.1 The route and its gates

**`POST /api/clusterconfigs/{name}/rejoin`, behind the same gate as every write on the tab, registered only when
writes are on, and refused before anything is sent unless the request is exactly right.**

The route is `rejoin_cluster_config` inside `gsd/api.py#build_app`, beside Refresh inside the writes carve-out. In
order:

| step | check | refusal | anything sent? |
|---|---|---|---|
| 1 | the writes switch (`clusterConfig.secrets.writes.enabled`) | the route does not exist: `404` | no |
| 2 | `_writes_gate`: a proxy-verified identity and the cluster-admin tier (#322) — the **host's gate** | `403` | no |
| 3 | the body is exactly `{"username": <string>, "password": <string>}` | `422`, naming a field, never a value | no |
| 4 | the name is a live cluster | `404` | no |
| 5 | `gsd/rejoin.py#check`: the cluster is rejoinable (§3.2); the username is in the bootstrap grammar and does not end in a newline; it is not a fleet account, the names compared stripped and casefolded; the password is present, with no control character and no unpaired surrogate | `409 not-rejoinable`, or `422 rejoin-username-invalid`, `rejoin-fleet-account`, `rejoin-password-missing`, `rejoin-password-invalid` | no |
| 6 | this process runs a poller, whose credential gate Rejoin must use | `409` | no |
| 7 | no other Rejoin is running in this process | `409`, never queued | no |
| 8 | `gsd/rejoin.py#rejoin` (§3.3): the credential gate, the login, **the remote's gate (D8)**, the read, the revoke, the write | `200` with a refusal's code | at most one login |

`body: Any = Body(None)` is deliberate. A body typed `dict` lets FastAPI answer a non-object body with a 422 that
quotes it whole, password included (measured, §2.4). With `Any`, FastAPI passes what arrived unvalidated, and step 3
refuses it with a fixed sentence. A request whose JSON does not parse is still FastAPI's `422`, whose `input` is `{}`
(measured).

The final newline in step 5 is not cosmetic. The shared grammar, `gsd/config.py#valid_bootstrap_username`, is a
Python pattern ending in `$`, which also matches before a final newline: `SVC-GSD-Fleet\n` passes it (measured).
LDAP string preparation maps a line feed to a space, and a trailing space is insignificant in a compared value
(RFC 4518, lines 243-245 and 324-333), so a directory may read that name as the fleet account's. Before this
refusal, a script's Rejoin as `SVC-GSD-Fleet\n` answered `rejoined` against the test's fake remote, which accepts any
login. The page cannot send one: it trims the username.

A success wakes discovery, as every write on the tab does, so the card polls within seconds.

### 3.2 Which cards may be rejoined

**Secret-sourced rows and `saTokenLookup` stanzas: the epic's decision. `rejoinable` on each row is the route's own
rule, so the page offers Rejoin exactly where the route accepts it.**

| the row | rejoinable | what Rejoin writes | why |
|---|---|---|---|
| a Secret with a `bearerToken` (a hand-written one, like the lab's `shared-qa`; one the tab created; one the lookup wrote) | **yes** | updates it in place | the design's case: a stored token stopped working |
| a Secret that declares `saTokenLookup` | **yes** | updates it in place, as the lookup would | its token was never fetched, or the lookup is stuck |
| a Secret that declares `oauth` | **yes** | updates it in place: `bearerToken` replaces the `oauth` key | the declaration says a person's credential supplies it; Rejoin does that once, and removes any password the Secret held |
| a values stanza that declares `saTokenLookup` | **yes** | creates `gsd-cluster-<name>` with the stanza's policy | the stanza is pending, for example while the fleet account is locked |
| a Secret or a stanza that declares `userSelfLogin` | no | — | its credential is the poll thread's session; a stored token would replace the declared mode, and Refresh answers `not-probed` there |
| a Secret generated from a ConfigMap | no | — | its reconciler owns it (`not-our-secret`), and its stanza names its account |
| a values entry with its own token | no | — | a Secret would shadow the values entry (`shadows-values-entry`) |
| the host | no | — | it polls as the pod's own ServiceAccount |
| a retired row | no | — (`404`) | nothing describes it any more |

### 3.3 The composition, step by step

**One login, one question, one read, one revoke, one write — in that order, and each failure stops it.**

| step | what | on failure | the credential gate |
|---|---|---|---|
| 1 | `gate.account_refusal(username, password)`: has the directory answered this password for this account already, anywhere? | answered `login-refused`, with the target that answered; **nothing is sent** | read |
| 2 | `RejoinLogin(cluster, username, password, policy=ONE_TRY)`: #283's login, as the person | a bound failure (401, 500, a timeout after the password was written, a 302 without a token): `login-refused` or `login-failed`. A failure before the password was written: `login-failed`, the password not sent | `refuse(...)` after a **bound** failure only, exactly as the lookup does (#315) |
| 3 | inside the session: D8, `remote_says_cluster_admin` | `not-cluster-admin` (a clean no) or `access-review-failed` (no clean answer); nothing read or written | — (the password was right) |
| 4 | log `cluster-rejoin-review` with the remote's answer | — | — |
| 5 | inside the session: `read_sa_token`, then `login.add_secrets(token)` so a failed revoke's line cannot quote it | `sa-token-secret-missing`, `sa-token-unreadable`, `sa-token-invalidated`; nothing written | — |
| 6 | the session ends: `FleetLogin.__exit__` revokes the login, whatever happened | a failed revoke is a `fleet-logout-failed` line, and the answer names the object to delete | — |
| 7 | `store(..., rejoin=(person, account, instant))`: update the Secret in place, or create it for a stanza | `lookup-write-failed`; nothing stored | — |
| 8 | log `cluster-rejoined`; answer `rejoined` | — | — |

`ONE_TRY` is `RetryPolicy(attempts=1)`. The fleet's schedule retries a failure that bound nothing up to five times,
about a minute and a half; a person is waiting behind a router whose server timeout is 30 s by default (openshift/router
`6c5868c`, haproxy-config.template line 167), and the next press is the retry. The password is sent at most once
either way.

The caller holds a process-wide lock across steps 1 to 8, so the gate's check and the login it guards are one step:
two presses in one process can never both reach a password's first use.

### 3.4 The answer

**`200 {outcome, message, at}` for every Rejoin that reached the gate, as Refresh answers; `rejoined`, or a refusal's
code with one sentence for the person.** `at` is ISO-8601 UTC. `message` is scrubbed of every secret in play.

| `outcome` | when | password sent? | gate writes? | written here? |
|---|---|---|---|---|
| `rejoined` | the login, a yes from the remote, the read and the write all succeeded | once | no | the Secret |
| `login-refused` | the gate already held this password for this account | **no** | no | no |
| `login-refused` | the remote answered 401 with a Basic challenge | once | **yes** | no |
| `login-failed` | the password was written and no session came back: a 500 (a locked directory account's LDAP code 19 is a 500), any other answer, a read timeout, a 302 without a token | once | **yes** | no |
| `login-failed` | the login could not start: discovery failed, the connection or the TLS handshake failed | **no** | no | no |
| `not-cluster-admin` | the remote answered `allowed: false` | once | no | no |
| `access-review-failed` | the remote could not answer: a 403, a 500, a timeout, no boolean `allowed` | once | no | no |
| `sa-token-secret-missing`, `sa-token-unreadable`, `sa-token-invalidated` | the token Secret could not be used | once | no | no |
| `lookup-write-failed` | the token was read and the host refused the write | once | no | no |

Every answer after a session existed ends by saying how the login ended: "the login was signed out", or that it could
not be, naming the object and the command to delete it (the name is not a secret, §2.1).

Refusals before anything is sent are HTTP errors, as on the tab's other writes: `403`, `404`, `409` and `422`
(§3.1), each `detail` a code and a sentence that repeats no value.

### 3.5 The provenance on the written Secret

**The Secret says a person fetched it, who, as which account, and when; it never says so in `lookup-account`, which the
daily ping logs in as with the fleet password.**

| annotation | value | on an update in place | on a create |
|---|---|---|---|
| `groupsync-dashboard.io/token-source` | `rejoin` | set | set |
| `groupsync-dashboard.io/source-namespace` | `group-sync-operator` (the configured source) | set | set |
| `groupsync-dashboard.io/source-service-account` | `group-sync-dashboard-cluster-poller` | set | set |
| `groupsync-dashboard.io/rejoined-by` | the host identity who pressed Rejoin (the proxy's `X-Forwarded-User`, the same name the tab's other writes audit) | set | set |
| `groupsync-dashboard.io/rejoin-account` | the account the remote signed in | set | set |
| `groupsync-dashboard.io/rejoined-at` | the instant, ISO-8601 UTC | set | set |
| `groupsync-dashboard.io/lookup-account` | — | **removed** | never written |
| `groupsync-dashboard.io/managed-by` | — | kept as it was | `ui`: a person made it through the tab |

Three rules hold the provenance safe:

1. **Never `lookup-account`.** `Poller._ping_accounts` pings every Secret with `token-source: remote-lookup` and a
   `lookup-account`, logging in as that account with the one fleet password (poller.py:1726-1729, 1815; #432). Had
   Rejoin written the person there, the daily ping would present the fleet password as the person. A Rejoin removes
   the key from a Secret the lookup wrote, and the lookup removes the three Rejoin keys when it writes a Secret again
   (`writer.store_lookup`: one path's provenance replaces the other's).
2. **`rejoin` is not a mode's word, and the reader knows it.** The reader counts a Secret over a values stanza as the
   stanza's own only when its `token-source` names the stanza's mode (reader.py:122-129); otherwise the Secret is a
   `shadows-values-entry` finding and the merge serves it wholesale, dropping the stanza's policy (registry.py:99-102).
   `writer.owned_by_mode` counts `rejoin` over a `saTokenLookup` stanza as its own too: the same token Secret, read by
   a person. Every other combination answers as before.
3. **The two names are separate on purpose.** `rejoined-by` is who the dashboard verified; `rejoin-account` is who the
   remote signed in. They are usually the same person under the same name, and they need not be: the host's identity
   provider and the remote's may spell one person differently.

### 3.6 The dialog

**A static `<dialog>` outside `#main`, the `#ns-preview` pattern: the minute's repaint cannot touch what is typed, and
nothing typed outlives the dialog.**

| part | what |
|---|---|
| where | `#rejoin-dialog`, next to `#ns-preview`, outside `#main`; opened with `showModal()`, so Escape, the focus trap and the backdrop are the platform's |
| when the card offers it | a **Rejoin…** button in the card's action row, after Refresh, where the row is `rejoinable` and Refresh has answered `auth_failed` or `pending`; it stays while its own answer is shown. Absent, not disabled, for a reader below the tier or with writes off |
| the words | "Rejoin `<name>`"; "Sign in to `<name>` as yourself. The dashboard logs in once to `<server>`, asks it whether you are a cluster administrator there, reads the poller's token, writes `gsd-cluster-<name>`, and signs that login out. **Your username and password are used for this one login and are not stored** — not in the Secret, not in a log line, not in this page." |
| the two gates | "passed · 1 · this cluster, the host": you hold the cluster-admin tier here. "decided there · 2 · `<name>`, the remote": once you are signed in, it is asked the same question about you; if it says no, nothing is read or written, and this dashboard cannot override it |
| the one-try warning | "One try per password. If this password is refused, the dashboard does not send it again, to any cluster, while it is the same password. A locked directory account answers HTTP 500, not 401, so trying again only locks it further." |
| the fields | username (`autocomplete="off"`, `autocapitalize="none"`, `spellcheck="false"`) and password (`type="password"`, `autocomplete="off"`), in no `<form>` |
| a press | reads both fields, **empties the password field as the request leaves**, disables the button, and sends one `POST`; a press while one is out sends nothing, and so does a press with the field empty. Enter in the password field is a press |
| the answer | on the card, under the Refresh line: "Rejoin: ● rejoined · `<at>` — the message", or the refusal's code; a success closes the dialog, a refusal keeps it open with its sentence and an empty password field. An answer that never arrives (a gateway timeout) says the Rejoin may have finished anyway, and to press Refresh before pressing Rejoin again |
| clearing | both fields are cleared by Cancel and Escape, on `pagehide` (the back/forward cache keeps typed values), and by the idle sign-out, which closes the dialog before it blanks the page |
| state | `view.clusterRejoin[<id>]` holds the answer only, never a username or a password, so the repaint redraws the card's button and line from it |

The mockup (`docs/design/cluster-reconnect-mock.png`) draws the fields `autocomplete="username"` and
`"current-password"`; this spec uses `off` (§3.11, D4-14).

### 3.7 The redaction pin

**#283's pin, carried to this path: plant every secret in play in every field the remote controls, then look for it
everywhere the dashboard could keep or say something.**

`tests/test_cluster_rejoin.py#test_the_password_appears_on_one_header_and_nowhere_else` runs thirteen scenarios. In
each, the remote plants the secrets in play at that point: the password and its Basic form from the authorize on,
the login's token from the 302 on, and the token read from the read on. A value the dashboard has not been handed yet
is not its secret to scrub, and is not planted.

| scenario | where the remote plants them |
|---|---|
| `401`, `401-challenge` | the refusal's body; the `Www-Authenticate` realm |
| `500` | a 500's body (a locked account's answer) |
| `302-error` | the `Location` fragment's `error` |
| `issuer` | the discovery document's `issuer`, as userinfo |
| `review-reason`, `review-denied`, `review-500` | the review's `reason` and `evaluationError`; a 500's body |
| `read-500`, `read-owner` | the token Secret's error body; its owner annotation |
| `revoke-500` | the revoke's error body |
| `write-echo` | the host's write refusal, which quotes the object it was sent |
| `success` | nothing: the ordinary path |

Then it asserts that none of the password, its Basic form and the login's token appears in the answer, any log line
at DEBUG, any stored Secret, the credential gate, any finding, or the whole database dumped as SQL; that the token
read appears nowhere but the Secret it belongs in; and that on the wire the password rides one header of one request:
the authorize's `Authorization`.

### 3.8 The budget over the system

**Measured: one press presents the password at most once; a password the directory answered is not presented again by
that pod; the fleet account is never used. A restart and a second replica each start with an empty gate, which is the
stated scope, because nothing about a person's password is kept.**

The property, with its scope: *a Rejoin press sends the password in at most one authorize request, as the account the
same request named, and never retries it; a pod does not send a password the directory answered for that account
again until the pod restarts; nothing stores it; no fleet path presents the fleet password as the person, and the
person never presents as a fleet account.* The unit is SPEC_S4c's: an authorize request on the wire, counted by the
fake target. Each row is measured by the test named, from a fresh process; "outcomes" are the answers in order.

| shape | authorize requests | outcomes | measured by |
|---|---|---|---|
| one press, the right password | **1** | `rejoined` | `test_the_budget_over_the_system` |
| a double click on the dialog's button | **1** | one request, one answer | `test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` |
| a second press, the other tab or a script, while the first is out | **1** | the second answered `409`, nothing sent | `test_one_rejoin_at_a_time_in_this_process` |
| two presses in turn, the right password | 2 | `rejoined`, `rejoined` | `test_the_budget_over_the_system`: each press presents once, and a success is not gated |
| a 401, then the same password | **1** | `login-refused`, `login-refused` (not sent) | `test_the_budget_over_the_system` |
| a 500 (a locked account), then the same password | **1** | `login-failed`, `login-refused` (not sent) | the same |
| a timeout after the password was written, then the same | **1** | `login-failed`, `login-refused` (not sent) | the same |
| a failure before the password was written, then again | 1 | `login-failed` (not sent), `rejoined` | `test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` |
| a 401 on one cluster, then the same password on another | **1** | `login-refused`, `login-refused` (not sent) | `test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again` |
| a 401, then the right password | 2 | `login-refused`, `rejoined` | `test_the_budget_over_the_system` |
| a 401, then the same password on a restarted pod | 2 | `login-refused`, `login-refused` | the same: **the scope** |
| a 401, then the same password on a second replica | 2 | `login-refused`, `login-refused` | the same: **the scope** |
| a restart mid-flight, after the password was written, then the same password | 2 | no answer (the pod died), then the new pod's own outcome | stated below: the gate dies with the pod; the restarted-pod row measures the new pod's side |
| the daily ping after a Rejoin | 0 as the person | the ping presents only the fleet account's own pair | `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` |
| a fleet account's name typed into the dialog, in any capitalisation | 0 | `422 rejoin-fleet-account` | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value` |
| a fleet account's name with a final newline, sent by a script | 0 | `422 rejoin-username-invalid` | the same |

**The restart mid-flight, stated.** If the pod dies after the authorize request was written, the person's answer
never arrives, and the in-memory gate dies with the pod. A press on the new pod sends the password once more: the
"restarted pod" row. Whatever the remote minted is not revoked; its object is named by nobody. The runbook's §6 lists
the person's own tokens and deletes it.

**Can anything make one press run twice?** Each layer was read (§2.5). Only the browser resends a request it already
wrote, and only when a reused connection closes before any response header. In this deployment the browser's peer is
the router, which answers a failed backend with a status, so the resend needs the router itself to drop the connection
mid-request. On the same pod the resend then meets the `409` while the first runs, and the gate after a bound failure;
after a success it is one more successful login with a correct password, which counts toward no lockout. Not measured
end to end.

### 3.9 What must not change, and what holds each

**Everything the brief lists is untouched in behaviour, and each has a test or a render that says so.**

| must not change | held by |
|---|---|
| Refresh (#434): its route, probe, words and four states | `gsd/clusterconfig/writer.py#refresh` and the route are untouched; `tests/test_cluster_refresh.py` passes unchanged. One UI assertion changes, as SPEC_D3 §4 anticipated: on `auth_failed` the line now names Rejoin and the card draws its button; SPEC_D3's notes record it |
| the credential gate | `gsd/fleetlookup.py#CredentialGate` is untouched; Rejoin calls `account_refusal` and `refuse` as the lookup does. `tests/test_credential_gate_account.py`, `test_credential_gate_diagnostics.py` and `test_credential_gate_docs.py` pass unchanged |
| Epic C's ping and self-login | `gsd/poller.py`, `gsd/selflogin.py` and `gsd/fleetstate.py` are untouched; `tests/test_fleet_lifecycle.py` and `test_fleet_lifecycle_round3.py` pass unchanged; the ping never targets a rejoined Secret (§3.8) |
| the lookup: its schedule, gate, provenance and refusals | `store` and `store_lookup` write the lookup's values byte for byte when `rejoin` is empty (`tests/test_fleet_lookup.py` R1 and R2 unchanged); `FleetLogin`'s three fleet texts are byte-identical (measured: the same driver against both trees, `cmp` equal) |
| the dashboard ServiceAccount's permissions | no template changes. Rendered RBAC atoms (one verb on one resource, one subject on one role), before and after, for the default values, `environments/crc.yaml`, `environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`, each with leader election on and off: **REMOVED 0, ADDED 0** in all eight (63 to 73 atoms each). Rejoin writes through the existing Secret write grant |
| no feature removed, narrowed or deprecated | Rotate, Delete, Test, the Add form and its `oauth` refusal are untouched; their tests pass unchanged |
| the read-only API contract | `test_r6_the_api_is_read_only` is unchanged; the carve-out list gains the one route, on purpose, as Refresh's did |

### 3.10 What is left, stated

1. **The scope of the gate.** In memory, per pod: a restart or a second replica may send one wrong password once more
   (§3.8). Closing it needs a durable record of a person's password, which "never stored" forbids (§3.11, D4-7).
2. **A transient 500 holds a correct password back.** A 500 cannot be told from a locked account (the operator's
   ruling on #325), so the gate holds that password until the pod restarts, even if the directory was only sick. The
   runbook's §6 says so; a new password works at once.
3. **Directory aliases and spellings.** The fleet-account refusal compares names stripped and casefolded, and refuses a
   username ending in a newline (§3.1); one directory entry known by two names (a `uid` and a `mail`) is still not
   recognised as the fleet account under its other name, SPEC_S4d's residual. The credential gate compares the
   username as typed (#315's rule, `gsd/fleetlookup.py#CredentialGate`), so the same wrong password under another
   capitalisation of the name is a new try, as a different password is.
4. **A failed revoke leaves a full-scope token.** The answer and the `fleet-logout-failed` line name it; nothing sweeps
   it (`CLUSTER_CREDENTIALS.md` §6, point 3).
5. **The login lines keep #283's names.** A Rejoin's login lines read `fleet-login…`, because #283's closed vocabulary
   is pinned by `tests/test_fleet_login.py`'s parse of the source; each carries `rejoin_by=<person>` and the person's
   `account=`, and its refusal speaks to the person.
6. **An identity provider without password challenges** (OpenID Connect, GitHub, Google) cannot be rejoined (§2.1).
7. **The browser's resend** of a written request is not guarded beyond the lock and the gate (§3.8).

### 3.11 The decisions the issue left open

**Each is decided here as recommended, with the evidence; the operator rules.**

| # | decision | recommended, and why | the alternative, and why not |
|---|---|---|---|
| D4-1 | the spec's name | `SPEC_D4_cluster_rejoin.md`, the brief's: the next step of batch D after SPEC_D3 | `SPEC_R1_rejoin.md`, the issue's placeholder |
| D4-2 | which rows are rejoinable | Secret rows (a `bearerToken`, a `saTokenLookup` or an `oauth` declaration) and `saTokenLookup` stanzas (§3.2): the epic's decision, with `oauth` Secrets included because their declaration says a person supplies the credential | also `userSelfLogin` rows: a stored token would replace the declared mode |
| D4-3 | when the card offers it | after Refresh answers `auth_failed` or `pending`, and while its own answer is shown: diagnose first, the runbook's §1. The server accepts any rejoinable row without a prior Refresh | always on every rejoinable card: invites a Rejoin that cannot help (`forbidden`, `unreachable`) |
| D4-4 | D8's question | the host's own `visibility.clusterAdminSar`, asked by a `SelfSubjectAccessReview` with the login's token: one definition of cluster administrator, no grant, the person's own groups | a fixed `update clusterrolebindings`; or a `SubjectAccessReview` as the dashboard's remote ServiceAccount, which needs a grant and a group lookup |
| D4-5 | D8's place | before the token read: a no reads nothing, and a namespace `admin` of `group-sync-operator` is refused although RBAC would let them read the Secret | after the read: the token is already in hand |
| D4-6 | retries | none, not even a failure before the password was written (`ONE_TRY`): a person is waiting, and the next press is the retry | the fleet's five attempts: up to a minute and a half behind a 30 s router timeout |
| D4-7 | where the gate lives | the poller's in-memory `CredentialGate`: nothing about a person's password is stored | the fleet account's Lease pattern: it would keep a fingerprint of a person's password where `cluster-reader` can read it, and its salt is the fleet password Secret's uid, which a person's password has no equivalent of |
| D4-8 | what the gate records | every bound failure (401, 500, a timeout after the write, a 302 without a token), as #315; nothing for a success, a D8 no, a read or a write failure | only a 401: a locked account's 500 would be walked further |
| D4-9 | the fleet account typed in | refused by name, stripped and casefolded, against the chart's `fleetAccount.username`, every stanza's `ldapConnectionBootstrap` and every Secret's `lookup-account`; a username ending in a newline is refused before that comparison, since a directory may read it as the name without it (§3.1) | allowed: a person's retries would walk the account every cluster authenticates with |
| D4-10 | the provenance | `token-source: rejoin`, `rejoined-by`, `rejoin-account`, `rejoined-at`; `lookup-account` removed; the reader counts `rejoin` over a `saTokenLookup` stanza as its own (§3.5) | `token-source: remote-lookup` with the person in `lookup-account`: the daily ping would log in as the person with the fleet password |
| D4-11 | the body | exactly `{username, password}`, strings; a username in the bootstrap grammar and not ending in a newline (RFC 7617: no colon, no control character); a password without a control character or an unpaired surrogate; unknown keys named, values never; `body: Any` so FastAPI never echoes it | a typed body: its 422 quotes a non-object body, password included |
| D4-12 | concurrency | one Rejoin per process at a time, `409` for the second, never queued | per cluster, as Refresh: two clusters at once could both send one wrong password before either answer lands |
| D4-13 | the Add form's `oauth` choice | unchanged, still refused: joining a new cluster with a password is not this issue; Rejoin needs a card that already names the server and its trust | build it here: a larger change with its own design |
| D4-14 | the dialog's autofill | `autocomplete="off"`: the WHATWG meaning is "do not remember this value", which is what used once means; the page itself stores nothing either way | the mockup's `username`/`current-password`: invites the browser to save a remote cluster's password under the dashboard's origin |
| D4-15 | the answer's shape | `200 {outcome, message, at}` for every Rejoin that reached the gate, as Refresh; HTTP errors for refusals before anything is sent | HTTP 4xx and 5xx for the remote's refusals: the page would have to tell the dashboard's refusals from the remote's |
| D4-16 | `rejoinable` on each row | served by the route's own rule, so the page cannot offer Rejoin where the route refuses it | the page computing it from `source` and `credential`: two copies of one rule |
| D4-17 | the log lines | #283's login lines as they are, with `rejoin_by=`; `cluster-rejoin-review` for D8's answer (the operator: "we log the response"), then `cluster-rejoined` or `cluster-rejoin-failed` | new names for the login lines: breaks #283's pinned vocabulary |
| D4-18 | the lab walk's administrator | a named person given a disposable `cluster-admin` binding on the lab for the walk and removed after (§7): `kubeadmin`, the lab's only human cluster administrator today, is never a Logins row, so the Definition of Done's Logins check cannot pass with it | `kubeadmin`: the Logins check fails by design |

## 4. The runbook

**`charts/group-sync-dashboard/RUNBOOK.md`, beside `values.yaml` and `CLUSTER_CREDENTIALS.md`, in the house shape of
`docs/RUNBOOK_backup_restore.md`: numbered operations, each a command and what its answer looks like.**

The six sections are the ones the comment of 2026-09-23 lists, with what this spec measured:

| § | the operation | what it adds beyond the comment |
|---|---|---|
| 1 | decide whether the connection is broken: Refresh, and the log line | the outcome table: `auth_failed` and `pending` lead to Rejoin; `forbidden`, `unreachable` and `cert-verify-failed` do not; `not-probed` is a session |
| 2 | confirm the token on the remote before rejoining | present the stored token through your own remote context (`oc --context … whoami --token`), so the remote's CA comes from your kubeconfig; then the two things Rejoin needs there: `can-i update clusterrolebindings` and a live token Secret |
| 3 | Rejoin from the UI | who (both gates), what it asks, what it does, and how to confirm: the Secret's annotations, the log lines, and the login in the remote's audit log |
| 4 | when Rejoin is not the answer | a table of what each refusal means and what fixes it, `sa-token-secret-missing` and `not-cluster-admin` included |
| 5 | the manual fallback | the comment's two-cluster `oc create token` + `oc patch`, keeping the Secret's own `tlsClientConfig`; that a TokenRequest token expires; the discovery cadence; no provenance |
| 6 | what not to do | no repeated presses (a 500 is also a locked account); never the fleet account's password; after a lost answer or a restart, Refresh first, then list and delete your own leftover token |

`docs/README.md` lists it under "Troubleshooting and runbooks", and the chart's README and `CLUSTER_CREDENTIALS.md`
link to it. Its commands are fenced with `~~~` (orchestrator's notes). #285 has shipped, but SPEC_S4c §5 question 7's
`oc annotate lease …` concerns the fleet account's Lease; Rejoin keeps nothing on a Lease, so the runbook needs no
Lease step.

## 5. The change, file by file

**One new module, one new route, one dialog; four small changes to shared code, each byte-identical for its existing
callers; the rest is tests and the documents that describe Rejoin.**

| file | change | added | removed |
|---|---|---|---|
| `local-development/gsd/rejoin.py` | new: `RejoinLogin`, `refusal`, `fleet_accounts`, `check`, `question`, `question_words`, `remote_says_cluster_admin`, `rejoin` | +251 | −0 |
| `local-development/gsd/fleetlogin.py` | `FleetLogin.REFUSED_ACTION` and `FleetLogin.NEXT_TRY`: the refusal and next-try wording as class attributes, byte-identical for the fleet | +11 | −8 |
| `local-development/gsd/clusterconfig/writer.py` | `TOKEN_SOURCE_REJOIN`, the three Rejoin annotations, `owned_by_mode`, `CreateRequest.rejoin`; `store_lookup` takes `rejoin` and one path's provenance replaces the other's | +36 | −8 |
| `local-development/gsd/clusterconfig/reader.py` | the "ours" rule through `owned_by_mode` | +2 | −3 |
| `local-development/gsd/clusterconfig/registry.py` | the merge through `owned_by_mode` | +4 | −2 |
| `local-development/gsd/fleetlookup.py` | `store` takes `rejoin` | +10 | −8 |
| `local-development/gsd/api.py` | the route `rejoin_cluster_config` with its one-at-a-time lock; `rejoinable` on each live row | +47 | −1 |
| `local-development/gsd/static/index.html` | the dialog; the card's Rejoin button and line; the Refresh line's next step; `openRejoin`, `closeRejoin`, `clearRejoin`, `sendRejoin`; the `pagehide` listener; `idleExpire` closes the dialog | +116 | −3 |
| `local-development/gsd/static/app.css` | the dialog's width and its gates list | +6 | −0 |
| `local-development/tests/test_cluster_rejoin.py` | new: §6 | +583 | −0 |
| `local-development/tests/test_api_contract.py` | the carve-out gains the route | +3 | −2 |
| `local-development/tests/test_clusterconfig.py` | the pinned row gains `rejoinable` | +1 | −1 |
| `local-development/tests/test_ui.py` | Refresh's `auth_failed` assertion names Rejoin; two dialog tests | +129 | −2 |
| `charts/group-sync-dashboard/RUNBOOK.md` | new: §4 | +161 | −0 |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | §4 names Rejoin; §5 describes it as built and links the runbook; its rules | +20 | −10 |
| `charts/group-sync-dashboard/README.md` | links the runbook | +2 | −1 |
| `charts/group-sync-dashboard/values.yaml` | the `clusterAdminSar` comment: Rejoin is built, and the remote asks the same question (a comment only) | +2 | −1 |
| `docs/README.md` | lists the runbook | +1 | −0 |
| `local-development/API.md` | `rejoinable`; the route; six write routes | +28 | −2 |
| `docs/DESIGN_remote_cluster_access.md` | D7 built, D8 directed and built; §7's text and twin | +17 | −16 |
| `docs/diagrams/remote-cluster-access/source.html` | Figure 4 and the D8 card: Rejoin, D7 and D8 drawn as built | +14 | −13 |
| `docs/specs/SPEC_D3_cluster_refresh.md` | a note: #316 builds the next step §4 names | +4 | −0 |
| `docs/CHANGELOG.md` | the `## Unreleased` entry | +15 | −0 |
| **total** | 23 files | **+1463** | **−81** |

Measured with `git diff --numstat` on the tree the blocks produce. Two steps the blocks cannot carry, both in the
implementing commit:

1. **The figure's PNGs.** Render the figure with the command below, from the repository root; then commit only
   `joining-a-cluster.light.png` and `joining-a-cluster.dark.png` and restore the other six (renderer noise,
   orchestrator's notes). Rendered and checked on the implemented copy: the Rejoin, D7 and D8 boxes solid, the legend
   reading "Built: …", 375 px scroll width 375.
2. **The release commit's versions** (orchestrator's notes).

The render command for step 1 (`render.py` needs all four figure names):

    local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/remote-cluster-access/source.html \
      docs/diagrams/remote-cluster-access \
      policies-who-decides,inherit-vs-remote-sar-outcomes,remote-sar-decision-flow,joining-a-cluster

## 6. Tests, before and after

**Sixty-four new or changed test cases fail before and pass after; one guard passes both ways on purpose; the existing
suite is otherwise unchanged.**

"Before" is `b18e62d` plus §8's four test blocks only; "after" is `b18e62d` with every block applied. Run from
`local-development/` with `PYTHONPATH` set to that tree, `-p no:cacheprovider`, `PYTHONDONTWRITEBYTECODE=1` and a
`--basetemp` in the scratch directory, with `gsd` imported from the tree under test (printed with each run).

| what it proves | test (`local-development/tests/…`) | before | after |
|---|---|---|---|
| the exchange: the wire in order, one authorize as the person, D8 with the login's token, the in-place write and its provenance, no `lookup-account`, the fleet password never read, the lines | `test_cluster_rejoin.py::test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance` | FAILED `{"detail":"Not Found"}`: the route does not exist | passed |
| a lookup-written Secret loses `lookup-account` and keeps `managed-by` | `…::test_a_lookup_written_secret_rejoined_drops_lookup_account_and_keeps_who_made_it` | FAILED `KeyError: 'outcome'` | passed |
| a pending `saTokenLookup` stanza: created with the stanza's policy, `managed-by: ui`, and discovery counts it as the stanza's own | `…::test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own` | FAILED `Not Found` | passed |
| #432 read forward: the daily ping never presents the fleet password as the person who rejoined | `…::test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` | FAILED `KeyError: 'outcome'` | passed |
| the body is `{username, password}` and nothing else; no refusal echoes the password (seven shapes) | `…::test_the_body_is_username_and_password_and_nothing_else` | FAILED ×7 `Not Found` | passed ×7 |
| each refusal before the wire sends nothing and repeats no value: four rows (the host, a values entry, `userSelfLogin`, a ConfigMap's); three username shapes (a colon, a space, the fleet account's name with a final newline); four fleet-account names (the chart's in another capitalisation, a stanza's, a Secret's `lookup-account`, one recorded with a final newline); three password shapes | `…::test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value` | FAILED ×14 `Not Found` | passed ×14 |
| below the cluster-admin tier, and without an identity: `403`, nothing sent | `…::test_below_the_cluster_admin_tier_is_403_and_nothing_is_sent` | FAILED `assert 404 == 403` | passed |
| an unknown or retired name: `404` naming it | `…::test_an_unknown_or_retired_name_is_404_and_nothing_is_sent` | FAILED: the `404` does not name it | passed |
| no poller, no gate, no login | `…::test_no_poller_means_no_gate_and_no_login` | FAILED `assert 404 == 409` | passed |
| writes off: the route does not exist | `…::test_with_the_writes_switch_off_the_route_does_not_exist` | passed | passed: a guard, true both ways |
| a bound failure (401, 500, a read timeout after the write) is one authorize; the same password is not sent again, to another cluster either; a different password is | `…::test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again` | FAILED ×3 `KeyError: 'outcome'` | passed ×3 |
| a failure before the password is written: one request, no retry, not gated | `…::test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` | FAILED `KeyError: 'outcome'` | passed |
| D8's no: nothing read or written, the login revoked, the answer logged, the gate untouched | `…::test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked` | FAILED `KeyError: 'outcome'` | passed |
| a review that does not answer (403, 500, no status, a string `"true"`, a timeout) is a refusal, never a yes | `…::test_a_review_that_does_not_answer_is_a_refusal_never_a_yes` | FAILED ×5 `KeyError: 'outcome'` | passed ×5 |
| D8 asks the host's configured question | `…::test_the_review_asks_the_configured_cluster_admin_question` | FAILED `IndexError`: no review was asked | passed |
| a token read refusal (404, 403, invalidated) writes nothing and revokes the login | `…::test_a_token_read_refusal_writes_nothing_and_revokes_the_login` | FAILED ×3 `KeyError: 'outcome'` | passed ×3 |
| a refused write stores nothing and says so | `…::test_a_refused_write_stores_nothing_and_says_so` | FAILED `KeyError: 'outcome'` | passed |
| one Rejoin at a time in a process | `…::test_one_rejoin_at_a_time_in_this_process` | FAILED: the first login never started | passed |
| the redaction pin (§3.7), thirteen scenarios | `…::test_the_password_appears_on_one_header_and_nowhere_else` | FAILED ×13 `Not Found` | passed ×13 |
| the budget over the system (§3.8) | `…::test_the_budget_over_the_system` | FAILED `KeyError: 'outcome'` | passed |
| the runbook beside the values, six sections, linked from `docs/` and the chart's README | `…::test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it` | FAILED `FileNotFoundError` | passed |
| the carve-out, exact: six write routes | `test_api_contract.py::test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on` | FAILED: five routes | passed |
| the pinned row shape gains `rejoinable` | `test_clusterconfig.py::TestApi::test_the_payload_shape_the_tier_and_the_findings` | FAILED: no `rejoinable` | passed |
| Refresh's `auth_failed` line names Rejoin and the card draws it | `test_ui.py::TestClusterConfigPage::test_refresh_shows_four_states_that_survive_a_repaint_with_one_probe_in_flight` | FAILED: "Next step: Rejoin (#316), not built yet" | passed |
| the dialog: offered only where accepted and only after a refused Refresh; static and outside `#main`; no form; `autocomplete="off"`; survives a real repaint; fits 375 px; Cancel and Escape clear it; absent with writes off | `…::test_rejoin_is_offered_after_a_refused_refresh_and_its_dialog_keeps_what_is_typed` | FAILED: no Rejoin button (a 30 s wait) | passed |
| one press, one request, the password once; emptied as it leaves; a refusal keeps the dialog, a success closes it; nothing in storage, the URL or `view`; `pagehide` and the idle sign-out clear it | `…::test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` | FAILED `ModuleNotFoundError`: no `gsd.rejoin` | passed |

The new and changed tests alone (`tests/test_cluster_rejoin.py`, `tests/test_api_contract.py`,
`tests/test_clusterconfig.py` and the three `TestClusterConfigPage` tests above): before, `64 failed, 84 passed`,
the 84 being those files' other cases and the writes-off guard; after, `148 passed`. Each failure is the one the
table names.

**The whole suite**, `pytest tests/ -q --deselect tests/test_live_smoke.py`, browser tests included, on each proof tree:

| tree | result |
|---|---|
| before | `64 failed, 6121 passed, 19 skipped, 4 deselected in 528.24s`: the 64 are the table's, each for its reason |
| after | `6192 passed, 19 skipped, 4 deselected in 490.46s` |

The after tree collects seven cases more than the before tree, each parametrized over something the other blocks
add: `rejoin.py` in three module scans (`test_no_duplicate_methods.py`, and `test_storage_seam.py` twice),
`RUNBOOK.md` in `test_docs_diagrams.py`'s fence check, and the three citations the documents gain
(`test_docs_citations.py`). Measured by diffing the two trees' `--collect-only` lists: every other difference is a
citation's line number.

**The blocks**, on a clean clone of `b18e62d`: `python3 local-development/apply-spec-blocks.py <this spec> . --apply`
reports "69 blocks check out across 23 files", and the applied tree equals the implemented copy byte for byte in all
23 files.

**`FleetLogin`'s fleet wording is byte-identical.** One driver emits its three caller-facing texts (a refusal, a
terminal answer, a give-up after five attempts) against `b18e62d` and against the applied tree; the two outputs, seven
lines each, compare equal with `cmp`.

**Every design decision is held by a test.** Each was reverted in a copy of the implemented tree and its tests run
against the mutant; all fourteen were caught:

| reverted decision | caught by |
|---|---|
| the person written into `lookup-account`, under the lookup's `token-source` | `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` |
| a Rejoin over a `saTokenLookup` stanza counted as a shadow | `test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own` |
| the fleet's five attempts instead of `ONE_TRY` | `test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` |
| the gate not asked before the login | `test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again[401]` |
| a bound failure not written to the gate | the same |
| D8 not asked | `test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked` |
| a typed body | `test_the_body_is_username_and_password_and_nothing_else[string]` |
| no one-at-a-time lock | `test_one_rejoin_at_a_time_in_this_process` |
| a fleet account's name accepted | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value[…SVC-GSD-Fleet…]` |
| a username ending in a newline accepted | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value[…SVC-GSD-Fleet\n…]` |
| the fleet names compared unstripped | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value[…padded-account…]` |
| the token read not handed to the login's scrub | `test_the_password_appears_on_one_header_and_nowhere_else[revoke-500]` |
| the password field kept after the press | `test_ui.py::…::test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` |
| no clearing on `pagehide` | the same |

**RBAC.** Rendered before and after (§3.9): REMOVED 0, ADDED 0 in all eight renders.

## 7. On the lab, for the implementing pull request

**Break a throwaway entry, repair it with Rejoin as a named person, and prove the budget on the lab's own audit log.
`shared-qa` is never touched and nobody logs in as the fleet account.**

The walk runs on the deployed PR head (`local-development/release-crc.sh`), read through the route and the pod.
Before and after: the `group-sync-dashboard-data` and `-report-artifacts` PVC UIDs.

0. **Baseline, read-only.** `gsd-cluster-shared-qa`'s `resourceVersion`; the fleet account's Lease as JSON and its
   `openshift-challenging-client` token count (2 on 2026-09-27, the pre-existing pair); the walker's own token count;
   the start instant for the oauth-server audit log.
1. **The walker.** `kubeadmin` is the only person who passes D8 on the lab today (§2.3), and its logins are never a
   Logins row (`gsd/auditlog.py#SYSTEM_NAMES`). So a named person gets a disposable binding, removed in step 7:
   `oc create clusterrolebinding rejoin-walk-cluster-admin --clusterrole=cluster-admin --user=<walker>` (D4-18). The
   walker must not be named by any fleet path (D4-9).
2. **The throwaway entry.** On the tab's Add form, `rejoin-walk` at `https://api.crc.testing:6443`, trusted bundle, with
   a deliberately wrong token of eight or more characters. The card polls `auth_failed`; #314's warning names it beside
   `shared-qa` and `shared-rnd` (one URL, by design).
3. **Refresh, then Rejoin.** Refresh answers `auth_failed` and the card offers **Rejoin…**. Rejoin as the walker. Expect
   `rejoined`; Refresh then answers `connected`, and the card's `connection` row turns `ok` at the next poll.
4. **The evidence.** The Secret's annotations (`token-source: rejoin`, `rejoined-by`, `rejoin-account`, `rejoined-at`,
   no `lookup-account`); the log lines `fleet-login … rejoin_by=…`, then `cluster-rejoin-review … allowed=true` with
   the remote's reason naming the ClusterRoleBinding `rejoin-walk-cluster-admin`, then
   `cluster-rejoined … revoked=true`; the walker's `cli` login on the Logins tab; the walker's token count back to
   step 0's.
5. **One wrong password, twice.** Rejoin with a wrong password: `login-refused`, one `deny` in the audit log. The same
   wrong password again: `login-refused`, "so it was not sent", and **zero** new authorize in the audit log, counted.
6. **The remote's no.** Remove the binding from step 1 and Rejoin with the right password: `not-cluster-admin`,
   `cluster-rejoin-review … allowed=false` in the log, the Secret's `resourceVersion` unchanged, the walker's token
   count unchanged (the login was revoked).
7. **The end.** Delete `rejoin-walk` on the tab and the binding if it remains. `gsd-cluster-shared-qa`'s
   `resourceVersion` equals step 0's; the fleet account's token count is still 2, its audit-log authorizes 0 since step
   0, and its Lease byte-identical; the PVC UIDs are unchanged.

The evidence, with screenshots of the card's states and the dialog, goes under `reports/<date>_<slug>/`, pinned to the
merge sha, and on #316 against its Definition of Done.

## 8. Implementation blocks

**Sixty-nine blocks over twenty-three files, in apply order: the code, the tests, then the documents.** This spec's
Status, and its row in `docs/specs/README.md`, move to `merged` by hand in the implementing commit, beside the applied
blocks — a block cannot, because its Old text would also match inside its own fence — so that
`local-development/prepare-release.py` promotes them. The figure's PNGs and the versions are the two steps in §5.

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
    entering it twice is refused.
    """

```

```python
    entering it twice is refused.
    """

    #: What a refusal line tells its reader to do, and when the next try comes: the fleet account's words. A person's
    #: own login (Rejoin, SPEC_D4) states its own (`gsd/rejoin.py#RejoinLogin`); the events and every rule are these.
    REFUSED_ACTION = ("rotate the fleet password Secret or correct ldapConnectionBootstrap — no second attempt is made, "
                      "because a retry is the lockout walk against the account the target authenticates every user with")
    NEXT_TRY = "the next lookup or ping"

```

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
                    action=(f"the target refused the password for {self.username}: rotate the fleet "
                            f"password Secret or correct ldapConnectionBootstrap — no second attempt is "
                            f"made, because a retry is the lockout walk against the account the target "
                            f"authenticates every user with"),
```

```python
                    action=f"the target refused the password for {self.username}: {self.REFUSED_ACTION}",
```

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
            action = "not retried: fix what detail names before the next lookup or ping"
        elif gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until the next lookup or "
                      f"ping — check the API URL, the OAuth route and TLS trust for the OAuth host "
                      f"(the INGRESS CA, which the API's bundle may not carry) from this pod")
```

```python
            action = f"not retried: fix what detail names before {self.NEXT_TRY}"
        elif gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until {self.NEXT_TRY} — check the "
                      f"API URL, the OAuth route and TLS trust for the OAuth host (the INGRESS CA, which the API's "
                      f"bundle may not carry) from this pod")
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
TOKEN_SOURCE_SELF_LOGIN = CREDENTIAL_SELF_LOGIN  # userSelfLogin
```

```python
TOKEN_SOURCE_SELF_LOGIN = CREDENTIAL_SELF_LOGIN  # userSelfLogin
#: Rejoin (#316, SPEC_D4): the lookup's read, started by a person with their own login. The one `token-source` that
#: is not a mode's word, because no declaration resolves to it; `owned_by_mode` says which stanza it may serve.
TOKEN_SOURCE_REJOIN = "rejoin"
#: Who pressed Rejoin (the host identity), the account the remote authenticated, and when. Never `lookup-account`:
#: the daily ping logs in as whatever account that annotation names, with the fleet password (#432).
REJOINED_BY_ANNOTATION = "groupsync-dashboard.io/rejoined-by"
REJOIN_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/rejoin-account"
REJOINED_AT_ANNOTATION = "groupsync-dashboard.io/rejoined-at"
REJOIN_ANNOTATIONS = (REJOINED_BY_ANNOTATION, REJOIN_ACCOUNT_ANNOTATION, REJOINED_AT_ANNOTATION)
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
    onboarding: tuple[str, str, str] = ()
```

```python
    onboarding: tuple[str, str, str] = ()
    #: (who pressed Rejoin, the account, the instant) — REJOIN_ANNOTATIONS, in that order (SPEC_D4).
    rejoin: tuple[str, str, str] = ()
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python

def secret_object(req: CreateRequest, namespace: str, *, redact: bool = False) -> dict:
```

```python

def owned_by_mode(token_source: str | None, mode: str | None) -> bool:
    """Whether a Secret with this `token-source` is the retriever's own write for a values stanza whose mode resolves
    to `mode` (SPEC_S4 §1, SPEC_D2b §3.4): the mode's own word, or a Rejoin over a `saTokenLookup` stanza, which read
    the same token Secret the lookup reads (SPEC_D4). Such a Secret serves the stanza's policy and is no shadow."""
    if mode is None:
        return False
    return token_source == mode or (mode == TOKEN_SOURCE_LOOKUP and token_source == TOKEN_SOURCE_REJOIN)


def secret_object(req: CreateRequest, namespace: str, *, redact: bool = False) -> dict:
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
                                CONNECTION_HASH_ANNOTATION), req.onboarding))
```

```python
                                CONNECTION_HASH_ANNOTATION), req.onboarding))
    if req.rejoin:
        annotations.update(zip(REJOIN_ANNOTATIONS, req.rejoin))
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
                 source_namespace: str, source_service_account: str, lookup_account: str) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.
```

```python
                 source_namespace: str, source_service_account: str, lookup_account: str | None,
                 rejoin: tuple[str, str, str] = ()) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.
    With `rejoin` (SPEC_D4) it is a person's Rejoin of any Secret row: the same write, the person's provenance.
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
        meta["annotations"] = {**(meta.get("annotations") or {}),
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account,
                               LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
```

```python
        # ONE PATH'S PROVENANCE REPLACES THE OTHER'S (SPEC_D4): a Rejoin leaves no `lookup-account`, which the daily
        # ping would log in as with the fleet password (#432), and a lookup leaves no stale Rejoin behind.
        stale = (LOOKUP_ACCOUNT_ANNOTATION,) if rejoin else REJOIN_ANNOTATIONS
        provenance = dict(zip(REJOIN_ANNOTATIONS, rejoin)) if rejoin else {LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
        meta["annotations"] = {**{k: v for k, v in (meta.get("annotations") or {}).items() if k not in stale},
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_REJOIN if rejoin else TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account, **provenance}
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
          by=MANAGED_BY_LOOKUP, secrets=(token,))
```

```python
          by=rejoin[0] if rejoin else MANAGED_BY_LOOKUP, secrets=(token,))
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
```

```python
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN", "TOKEN_SOURCE_REJOIN",
           "REJOIN_ANNOTATIONS", "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "owned_by_mode",
           "validate", "create", "rotate",
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
from .writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION
```

```python
from .writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION, owned_by_mode
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
            ours = (values_modes or {}).get(parsed.name) is not None \
                and token_source.get(secret_name) == (values_modes or {}).get(parsed.name)
```

```python
            ours = owned_by_mode(token_source.get(secret_name), (values_modes or {}).get(parsed.name))
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
from .parser import Finding
```

```python
from .parser import Finding
from .writer import owned_by_mode
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
        (its token-source is that stanza's credential kind — the reader's "ours") keeps the credential and takes
```

```python
        (its token-source is that stanza's credential kind, or a Rejoin's over a lookup stanza — the reader's "ours",
        `gsd/clusterconfig/writer.py#owned_by_mode`) keeps the credential and takes
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
```

```python
            elif c.connection_mode is not None and owned_by_mode(found.token_source, c.credential_kind):
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, TOKEN_SOURCE_LOOKUP, CreateRequest, WriteFailed, WriteRefused, create, secret_name_for,
    store_lookup,
```

```python
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, MANAGED_BY_UI, TOKEN_SOURCE_LOOKUP, TOKEN_SOURCE_REJOIN, CreateRequest, WriteFailed,
    WriteRefused, create, secret_name_for, store_lookup,
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
          sa_token: SaToken, *, account: str) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=account)
```

```python
          sa_token: SaToken, *, account: str, rejoin: tuple[str, str, str] = ()) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`. `rejoin` is (who pressed, the account, the
    instant) for a person's Rejoin (SPEC_D4): the same write, with the person's provenance."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=None if rejoin else account, rejoin=rejoin)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP,
                            onboarding=cluster.onboarding, token_source=TOKEN_SOURCE_LOOKUP, **provenance)
```

```python
        managed_by = MANAGED_BY_UI if rejoin else MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=managed_by, onboarding=cluster.onboarding,
                            token_source=TOKEN_SOURCE_REJOIN if rejoin else TOKEN_SOURCE_LOOKUP, **provenance)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
               viewer=MANAGED_BY_LOOKUP)
```

```python
               viewer=rejoin[0] if rejoin else MANAGED_BY_LOOKUP)
```

<!-- block: local-development/gsd/rejoin.py | create -->
```python
"""Rejoin (#316, SPEC_D4): a cluster administrator signs in to a remote cluster as themselves, once, and the dashboard
fetches the poller's token there and forgets the password.

THE EXCHANGE IS THE LOOKUP'S, STARTED BY A PERSON (docs/DESIGN_remote_cluster_access.md §7): one login with the
person's own username and password (`RejoinLogin`: #283's `FleetLogin` in a person's words), one question to the
remote about that person (D8), one read of the poller's token Secret by name (#284's `read_sa_token`), the login
revoked on every exit, and one write of `gsd-cluster-<name>` here (#284's `store`, with the person's provenance).

WHAT KEEPS THE PASSWORD SAFE, in the order it runs:
  1. who may press: the route's writes gate (the cluster-admin tier, #322), then `check` — a Secret row or a
     `saTokenLookup` stanza, a username RFC 7617 allows, never an account a fleet path logs in as;
  2. one presentation per press: `ONE_TRY` retries nothing, not even a failure before the password was written;
  3. a password the directory answered is not sent again: the poller's `CredentialGate`, asked before the login and
     written after a bound failure, as the lookup does (#315); in memory only, because anything durable would store
     a fingerprint of a person's password;
  4. the remote decides (D8): `remote_says_cluster_admin` asks #322's question with the login's own token, and a no
     reads and writes nothing;
  5. nothing is kept: the password lives in this call and, hashed, in the gate; every answer and every line is
     scrubbed of it, of its Basic form, of the login's token and of the token read.
"""

from __future__ import annotations

import base64
import dataclasses
import logging

from .clusterconfig.events import event, failure
from .clusterconfig.writer import WriteRefused, secret_name_for
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig, Settings, valid_bootstrap_username
from .fleetlogin import TOKEN_PREFIX, FleetLogin, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, LookupSource, _scrub, read_sa_token, store
from .kube import AUTH_FAILED, UNREACHABLE, ClusterClient, ClusterError
from .timeutil import now_iso

log = logging.getLogger(__name__)

#: The success word. Every other outcome is a refusal's code: the lookup's (`gsd/fleetlookup.py#CODES`) or these two.
REJOINED = "rejoined"
NOT_CLUSTER_ADMIN = "not-cluster-admin"
REVIEW_FAILED = "access-review-failed"
#: One attempt and no retry, not even before the password is written: a person is waiting, and the next press is the retry.
ONE_TRY = RetryPolicy(attempts=1)
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
#: What the person reads when the token read refuses (#284's codes); the lookup's own `action` speaks to the fleet.
READ_SAYS = {
    "sa-token-secret-missing": "{cluster} has no poller token Secret to read: create it there first",
    "sa-token-invalidated": "the poller token Secret on {cluster} was invalidated by its legacy-token cleaner: delete "
                            "and recreate it there",
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}


class RejoinLogin(FleetLogin):
    """#283's login as the person who pressed Rejoin: the same wire, events and rules, in a person's words."""

    REFUSED_ACTION = ("check the username and password — it is not sent again from this dashboard while it is the same "
                      "password, because each refused try counts toward the directory's lockout of the account")
    NEXT_TRY = "the next Rejoin"

    def __init__(self, cluster: ClusterConfig, username: str, password: str, *, person: str, **knobs):
        super().__init__(cluster, username, password, **knobs)
        self.person = person

    def _fields(self) -> dict[str, str]:
        return {**super()._fields(), "rejoin_by": self.person}


def refusal(cluster: ClusterConfig, settings: Settings) -> str | None:
    """Why this cluster cannot be rejoined, or None: Secret rows and `saTokenLookup` stanzas only (the epic's decision,
    SPEC_D4 §3.2). `/api/clusterconfigs` serves it as `rejoinable`, so the page and the route answer alike."""
    host = settings.host_cluster()
    if host is not None and cluster.name == host.name:
        return "the host polls as the pod's own ServiceAccount; there is no token to fetch"
    if cluster.onboarding or cluster.source.startswith("configmap:"):
        return "a ConfigMap declares it, and its Secret is generated from the stanza there"
    if cluster.credential_kind == CREDENTIAL_SELF_LOGIN:
        return "it declares userSelfLogin: its credential is a session, and a stored token would replace that mode"
    if cluster.source.startswith("secret:") or cluster.sa_token_lookup:
        return None
    return "the chart's values give it its own credential, and a Secret would shadow that entry"


def fleet_accounts(settings: Settings) -> set[str]:
    """Every account a fleet path may present the fleet password as: the chart's, each stanza's
    `ldapConnectionBootstrap`, each Secret's `lookup-account`. Stripped, because the grammar lets a recorded name end
    in a newline; casefolded, because over-refusing is the safe side."""
    names = {settings.fleet_account_username}
    for c in (*settings.clusters, *settings.effective_clusters()):
        names.update((c.ldap_connection_bootstrap, c.lookup_account))
    return {name.strip().casefold() for name in names if name}


def check(cluster: ClusterConfig, settings: Settings, username: str, password: str) -> None:
    """The refusals made before anything is sent (SPEC_D4 §3.1). Each is a `WriteRefused`; none repeats a value."""
    reason = refusal(cluster, settings)
    if reason is not None:
        raise WriteRefused("not-rejoinable", f"{cluster.name} cannot be rejoined: {reason}", conflict=True)
    # The grammar's `$` also matches before a final newline, so it passes `name\n`, and a directory may read that as
    # `name` (RFC 4518: LF maps to a space, and a trailing space is insignificant): no fleet name may slip through.
    if username.endswith("\n") or not valid_bootstrap_username(username):
        raise WriteRefused("rejoin-username-invalid", "a username is letters, digits and . _ @ -, starting with a letter "
                                                      "or digit, at most 255 characters (RFC 7617 forbids a colon and "
                                                      "control characters); the value is not repeated")
    if username.casefold() in fleet_accounts(settings):
        raise WriteRefused("rejoin-fleet-account", "that username is an account the dashboard's fleet paths log in as; "
                                                   "Rejoin takes a person's own account, never the fleet account")
    if not password:
        raise WriteRefused("rejoin-password-missing", "a password is required")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or 0xD800 <= ord(ch) <= 0xDFFF for ch in password):
        raise WriteRefused("rejoin-password-invalid", "the password holds a control character, which RFC 7617 forbids, "
                                                      "or an unpaired surrogate, which UTF-8 cannot carry; it was not "
                                                      "sent")


def question(settings: Settings) -> dict[str, str]:
    """#322's cluster-admin question as a review's resourceAttributes, built as the host's `TierResolver` builds it."""
    attrs = {"verb": settings.visibility_cluster_admin_sar_verb,
             "resource": settings.visibility_cluster_admin_sar_resource,
             "group": settings.visibility_cluster_admin_sar_api_group}
    if settings.visibility_cluster_admin_sar_namespace:
        attrs["namespace"] = settings.visibility_cluster_admin_sar_namespace
    if settings.visibility_cluster_admin_sar_subresource:
        attrs["subresource"] = settings.visibility_cluster_admin_sar_subresource
    return attrs


def question_words(settings: Settings) -> str:
    """The question as the answer and the log say it: `update clusterrolebindings`."""
    attrs = question(settings)
    resource = "/".join(part for part in (attrs["resource"], attrs.get("subresource")) if part)
    where = f" in namespace {attrs['namespace']}" if attrs.get("namespace") else ""
    return f"{attrs['verb']} {resource}{where}"


def remote_says_cluster_admin(session_token: str, cluster: ClusterConfig, settings: Settings, *,
                              timeout: float) -> tuple[bool, str]:
    """D8: one SelfSubjectAccessReview on the remote, sent with the login's own token, so the remote answers for the
    person and the groups it resolves for them. (allowed, the remote's reason). Only a boolean `status.allowed` is an
    answer; anything else raises ClusterError, and the caller refuses: no answer is never a yes."""
    as_session = dataclasses.replace(cluster, token_value=session_token, sa_token_lookup=False, user_self_login=False,
                                     ldap_connection_bootstrap=None)
    remote = ClusterClient(as_session, timeout=timeout)
    body = {"apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
            "spec": {"resourceAttributes": question(settings)}}
    with remote._client() as client:
        answer = remote._send(client, "POST", SSAR_API, json=body)
    status = answer.get("status") if isinstance(answer, dict) else None
    allowed = status.get("allowed") if isinstance(status, dict) else None
    if not isinstance(allowed, bool):
        raise ClusterError(UNREACHABLE, f"{SSAR_API} answered without a boolean status.allowed")
    return allowed, "; ".join(str(status[key]) for key in ("reason", "evaluationError") if status.get(key))


def rejoin(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, username: str, password: str, viewer: str) -> dict:
    """One Rejoin, after `check`: the gate, the login, D8, the read, the revoke, the write. Answers `{outcome, message,
    at}`: `rejoined`, or a refusal's code with the person's sentence. The caller holds the one-at-a-time lock, so the
    gate's check and the login it guards are one step in this process."""
    timeout = settings.request_timeout_seconds
    asked = question_words(settings)
    # The password as the Basic header carries it (RFC 7617): a remote that quotes the header quotes this.
    secrets = [password, base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")]
    who = dict(cluster=cluster.name, by=viewer, account=username)
    login = RejoinLogin(cluster, username, password, person=viewer, timeout=timeout, policy=ONE_TRY)

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence; both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
        return {"outcome": code, "message": _scrub(f"{said} ({detail})" if detail else said, secrets), "at": now_iso()}

    answered = gate.account_refusal(username, password)
    if answered is not None:
        shown = _without_userinfo(answered) or "an earlier cluster"
        return refused("login-refused", f"{shown} already refused this password for {username}, so it was not sent: "
                                        f"type the right password (this dashboard holds a refused password back until "
                                        f"it restarts)")
    stopped: tuple[str, str, str | None] | None = None      # D8 refused, or could not be asked
    try:
        with login as session:
            secrets.append(session.token)
            try:
                allowed, reason = remote_says_cluster_admin(session.token, cluster, settings, timeout=timeout)
            except ClusterError as exc:
                stopped = (REVIEW_FAILED, f"{cluster.name} could not be asked whether {username} may {asked} there, "
                                          f"so nothing was read or written", f"{exc.outcome}: {exc.message}")
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=reason or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
                                                  f"was read or written: Rejoin needs a cluster administrator of "
                                                  f"{cluster.name}", reason or None)
                else:
                    sa_token = read_sa_token(session.token, cluster, LookupSource.from_settings(settings),
                                             timeout=timeout)
                    secrets.append(sa_token.token)
                    login.add_secrets(sa_token.token)   # the revoke line quotes the remote's body too
    except LoginError as exc:
        if exc.bound:
            # THE PASSWORD WAS ON THE WIRE (#283): the account's entry, exactly as the lookup writes it (#315).
            gate.refuse(cluster.api_url, username, password)
            if exc.outcome == AUTH_FAILED:
                return refused("login-refused", f"{cluster.name} refused the password for {username}: check the "
                                                f"username and password; it is not sent again from this dashboard "
                                                f"while it is the same password", exc.message)
            return refused("login-failed", f"the password for {username} was sent to {cluster.name} and no session "
                                           f"came back; it is not sent again from this dashboard while it is the same "
                                           f"password, and a locked directory account answers HTTP 500, so check the "
                                           f"account before you try again", exc.message)
        hint = "; the cluster's trust must verify both the API host and the OAuth route" if exc.phase == "tls" else ""
        return refused("login-failed", f"could not reach {cluster.name}'s login, so the password was not sent{hint}",
                       exc.message, phase=exc.phase)
    except LookupRefused as exc:
        exc.scrub(secrets)
        said = READ_SAYS.get(exc.code, "the poller token Secret could not be read").format(cluster=cluster.name)
        return refused(exc.code, f"{said}; nothing was written", exc.detail)
    if stopped is not None:
        return refused(*stopped)
    at = now_iso()
    try:
        written = store(host_client, own_namespace, cluster, settings, sa_token, account=username,
                        rejoin=(viewer, username, at))
    except LookupRefused as exc:
        exc.scrub(secrets)
        return refused(exc.code, f"the token was read on {cluster.name} but writing {secret_name_for(cluster.name)} "
                                 f"here failed, so nothing was stored", exc.detail)
    event(log, logging.INFO, "cluster-rejoined", **who, secret=secret_name_for(cluster.name), written=written,
          revoked="true" if login.revoked else "false", secrets=secrets)
    message = (f"Signed in to {cluster.name} as {username}, who may {asked} there; read the poller's token and "
               f"{written} {secret_name_for(cluster.name)} here. The cluster is read again within seconds"
               f"{_logged_out(login, cluster)}")
    return {"outcome": REJOINED, "message": _scrub(message, secrets), "at": at}


def _logged_out(login: FleetLogin, cluster: ClusterConfig) -> str:
    """How the login ended, for every answer after a session existed: revoked, or what to delete. An unprefixed
    token is its own object's name, so it is never shown (`gsd/fleetlogin.py#token_object_name`)."""
    if login.session is None:
        return ""
    if login.revoked:
        return "; the login was signed out"
    name = login.session.token_name if login.session.token.startswith(TOKEN_PREFIX) else "the login's token"
    return (f"; the login could NOT be signed out on {cluster.name}: delete {name} there (oc delete "
            f"useroauthaccesstokens <name>, as yourself)")


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "RejoinLogin", "check",
           "fleet_accounts", "question", "question_words", "refusal", "rejoin", "remote_says_cluster_admin"]
```

<!-- block: local-development/gsd/api.py | edit -->
```python

from fastapi import Depends, FastAPI, HTTPException, Query, Request
```

```python
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        from .clusterconfig.warnings import shared_api_warnings
```

```python
        from .clusterconfig.warnings import shared_api_warnings
        from .rejoin import refusal as rejoin_refusal
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
```

```python
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
                # SPEC_D4 (#316): the route's own rule, so the page offers Rejoin exactly where the route accepts it.
                "rejoinable": rejoin_refusal(c, settings) is None,
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                    refreshing.discard(name)
```

```python
                    refreshing.discard(name)

        # One Rejoin at a time in this process (SPEC_D4 §3.3): the gate's check and the login it guards are then one step,
        # so a double click, two tabs or a script can never both reach a password's first use. Refused, never queued.
        rejoining = threading.Lock()

        @app.post("/api/clusterconfigs/{name}/rejoin")
        def rejoin_cluster_config(request: Request, name: str, body: Any = Body(None)) -> dict:
            """SPEC_D4 (#316): a cluster administrator's own username and password, for ONE login to the remote; the
            dashboard reads the poller's token there, writes it here and keeps no password. `body: Any`, so FastAPI
            neither validates nor echoes what arrived (a typed body's 422 quotes a non-object body whole): the shape is
            refused here, naming fields, never values. Registered with the writes, like `/refresh`."""
            from . import rejoin
            from .clusterconfig.writer import WriteRefused
            viewer, namespace, host_client = _writes_gate(request)
            if not isinstance(body, dict):
                raise HTTPException(status_code=422, detail="body: must be an object with username and password")
            _reject_unknown("body", body, {"username", "password"})
            username, password = body.get("username"), body.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                raise HTTPException(status_code=422, detail="username and password: each must be a string")
            cluster = settings.cluster(name)
            if cluster is None:
                raise HTTPException(status_code=404, detail=f"unknown cluster {name!r}")
            try:
                rejoin.check(cluster, settings, username, password)
            except WriteRefused as exc:
                raise _write_error(exc) from exc
            # The poller's gate (#315), the one the lookup and self-login use: no poller, no gate, so no login.
            gate = getattr(getattr(app.state, "poller", None), "_credential_gate", None)
            if gate is None:
                raise HTTPException(status_code=409, detail="this process runs no poller, so it holds no credential "
                                                            "gate; nothing was sent")
            if not rejoining.acquire(blocking=False):
                raise HTTPException(status_code=409, detail="a Rejoin is already in flight on this pod; nothing was sent")
            try:
                answer = rejoin.rejoin(cluster, settings, host_client, own_namespace=namespace, gate=gate,
                                       username=username, password=password, viewer=viewer)
            finally:
                rejoining.release()
            if answer["outcome"] == rejoin.REJOINED:
                _request_discovery()
            return answer
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
</dialog>

<script>
```

```html
</dialog>

<!-- #316 (SPEC_D4 §3.6): Rejoin's dialog. Static and outside #main for #ns-preview's reason: render() replaces #main on
     every poll and would erase what is typed. No <form>, so no submission can carry the password into a URL; the
     fields are cleared on close and on pagehide, and autocomplete="off" asks the browser not to remember them. -->
<dialog id="rejoin-dialog" class="ns-preview cc-rejoin" aria-labelledby="rejoin-title">
  <h2 id="rejoin-title">Rejoin <span id="rejoin-name"></span></h2>
  <p>Sign in to <span class="mono rejoin-cluster"></span> as yourself. The dashboard logs in once to
    <span class="mono" id="rejoin-server"></span>, asks it whether you are a cluster administrator there, reads the
    poller's token, writes <span class="mono" id="rejoin-secret"></span>, and signs that login out.
    <strong>Your username and password are used for this one login and are not stored</strong> — not in the Secret,
    not in a log line, not in this page.</p>
  <div class="cc-field"><label for="rejoin-username">Username on <span class="rejoin-cluster"></span></label>
    <input id="rejoin-username" autocomplete="off" autocapitalize="none" spellcheck="false"></div>
  <div class="cc-field"><label for="rejoin-password">Password</label>
    <input id="rejoin-password" type="password" autocomplete="off"></div>
  <ul class="cc-gates" aria-label="Two gates, on two clusters">
    <li><span class="badge ok"><span class="glyph" aria-hidden="true"></span>passed</span> <strong>1 · this cluster, the
      host.</strong> You hold the cluster-admin tier here, which is why Rejoin is shown to you at all.</li>
    <li><span class="badge unknown"><span class="glyph" aria-hidden="true"></span>decided there</span> <strong>2 ·
      <span class="rejoin-cluster"></span>, the remote.</strong> Once you are signed in, it is asked the same question
      about you. If it says no, nothing is read or written, and this dashboard cannot override it.</li>
  </ul>
  <div class="cc-warn"><strong>One try per password.</strong> If this password is refused, the dashboard does not send it
    again, to any cluster, while it is the same password. A locked directory account answers HTTP 500, not 401, so
    trying again only locks it further.</div>
  <p class="cc-hint" id="rejoin-msg" aria-live="polite"></p>
  <div class="idle-actions rejoin-acts">
    <button type="button" id="rejoin-cancel">Cancel</button>
    <button type="button" class="btn cc-btn-acc" id="rejoin-go">Rejoin</button>
  </div>
</dialog>

<script>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
                clusterRotate: null, clusterDeleteArmed: null, clusterMsg: {}, clusterCreating: false, clusterRefresh: {},
```

```html
                clusterRotate: null, clusterDeleteArmed: null, clusterMsg: {}, clusterCreating: false, clusterRefresh: {},
                clusterRejoin: {},   // #316: each card's Rejoin answer by cluster id — never a username or a password
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
    out += `<div class="cc-hint">The stored credential was refused. Next step: Rejoin (#316), not built yet — until then, replace the credential where it is written.</div>`;
  }
  return out + "</div>";
```

```html
    out += `<div class="cc-hint">The stored credential was refused. Refresh only probes with it; it never logs in. ${c.rejoinable
      ? "To fetch a new token with your own account, use Rejoin." : "Replace the credential where it is written."}</div>`;
  }
  return out + "</div>";
}
/* #316 (SPEC_D4 §3.6): Rejoin is offered where the route accepts it (`rejoinable`, the server's rule), once Refresh has
   said the stored credential is refused or not there yet — and stays while its own answer is shown. */
function ccRejoinButton(c) {
  const r = view.clusterRefresh[c.id] || {};
  if (!c.rejoinable || !(["auth_failed", "pending"].includes(r.outcome) || view.clusterRejoin[c.id])) return "";
  const busy = (view.clusterRejoin[c.id] || {}).state === "flight";
  return `<button type="button" class="btn cc-btn-acc" id="cc-rejoin-${esc(c.id)}" data-cc-rejoin="${esc(c.id)}"${busy ? ` disabled aria-busy="true"` : ""}>${busy ? "Rejoining…" : "Rejoin…"}</button>`;
}
function ccRejoinLine(c) {
  const r = view.clusterRejoin[c.id];
  if (!r) return "";
  const head = `<div class="cc-consq" id="cc-rejoin-result-${esc(c.id)}"><strong>Rejoin:</strong> `;
  if (r.state === "flight") return `${head}signing in once and reading the poller's token…</div>`;
  const shape = r.outcome === "rejoined" ? "ok" : r.outcome === "unknown" ? "unknown" : "critical";
  let out = `${head}${ccBadge(shape, r.outcome)}`;
  if (r.at) out += ` · <span class="mono">${esc(r.at)}</span>`;
  return out + (r.message ? ` — ${esc(r.message)}` : "") + "</div>";
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  const refresh = !c.retired && ccWritesOn() ? ccRefreshButton(c) : "";
```

```html
  const refresh = !c.retired && ccWritesOn() ? ccRefreshButton(c) + ccRejoinButton(c) : "";
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
    <div class="cc-kv"><span class="k">connection</span><span class="v">${ccConnection(c)}${ccRefreshLine(c)}</span></div>
```

```html
    <div class="cc-kv"><span class="k">connection</span><span class="v">${ccConnection(c)}${ccRefreshLine(c)}${ccRejoinLine(c)}</span></div>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  });
  document.querySelectorAll("[data-cc-delete]").forEach((el) => {
```

```html
  });
  document.querySelectorAll("[data-cc-rejoin]").forEach((el) => {
    el.onclick = () => openRejoin(el.dataset.ccRejoin);
  });
  const rejoinDlg = $("rejoin-dialog");
  if (rejoinDlg) {
    $("rejoin-go").onclick = sendRejoin;
    $("rejoin-cancel").onclick = closeRejoin;
    $("rejoin-password").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); sendRejoin(); } };
    rejoinDlg.onclose = () => {
      clearRejoin();
      const b = $(`cc-rejoin-${rejoinDlg.dataset.cluster}`);   // by id: a repaint replaced the button that opened it
      if (b) b.focus();
    };
  }
  document.querySelectorAll("[data-cc-delete]").forEach((el) => {
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
           labels: {}, labelKey: "", labelVal: "", test: null };
}

```

```html
           labels: {}, labelKey: "", labelVal: "", test: null };
}
/* #316 (SPEC_D4 §3.6): the Rejoin dialog. What is typed lives only in its two fields: never in `view`, storage or a URL. */
function openRejoin(id) {
  const c = ((data.clusterconfigs || {}).clusters || []).find((x) => x.id === id);
  const dlg = $("rejoin-dialog");
  if (!c || !dlg || dlg.open) return;
  dlg.dataset.cluster = id;
  $("rejoin-name").textContent = id;
  $("rejoin-server").textContent = c.api_url || "";
  $("rejoin-secret").textContent = `gsd-cluster-${id}`;
  document.querySelectorAll(".rejoin-cluster").forEach((el) => { el.textContent = id; });
  $("rejoin-msg").textContent = "";
  dlg.showModal();
  $("rejoin-username").focus();
}
function closeRejoin() {
  const dlg = $("rejoin-dialog");
  clearRejoin();                      // now: the close event fires from a queued task
  if (dlg && dlg.open) dlg.close();   // Escape closes without this; the close handler clears then
}
function clearRejoin() {
  ["rejoin-username", "rejoin-password"].forEach((id) => { const el = $(id); if (el) el.value = ""; });
}
async function sendRejoin() {
  const dlg = $("rejoin-dialog"), id = dlg.dataset.cluster, field = $("rejoin-password");
  const username = $("rejoin-username").value.trim(), password = field.value;
  if ((view.clusterRejoin[id] || {}).state === "flight") return;          // one press, one request
  if (!username || !password) { $("rejoin-msg").textContent = "Type your username and your password."; return; }
  field.value = "";                                                       // sent once: another try means typing it again
  view.clusterRejoin[id] = { state: "flight" };
  $("rejoin-go").disabled = true;
  $("rejoin-msg").textContent = "Signing in once…";
  render();
  try {
    view.clusterRejoin[id] = { state: "done", ...(await apiSend(`/api/clusterconfigs/${encodeURIComponent(id)}/rejoin`, "POST", { username, password })) };
  } catch (e) {
    // No JSON answer (a gateway timeout, a dropped connection): the server may still have finished the Rejoin.
    view.clusterRejoin[id] = e.status ? { state: "done", outcome: `HTTP ${e.status}`, message: e.message, at: null }
      : { state: "done", outcome: "unknown", at: null, message: "The answer did not arrive, and the Rejoin may have "
          + "finished anyway. Press Refresh in a minute; do not press Rejoin again until Refresh answers." };
  }
  const r = view.clusterRejoin[id];
  $("rejoin-go").disabled = false;
  if (r.outcome === "rejoined") closeRejoin(); else $("rejoin-msg").textContent = `${r.outcome} — ${r.message}`;
  render(); refresh();
}
// The back/forward cache keeps a page's DOM, typed values included: a page left with the dialog open keeps none (#316).
window.addEventListener("pagehide", clearRejoin);

```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  navSeq++;
  $("idle-modal").hidden = true;
  setIdleChrome(false);
```

```html
  navSeq++;
  $("idle-modal").hidden = true;
  closeRejoin();   // #316: a typed username is on screen too, and it leaves with the rest
  setIdleChrome(false);
```

<!-- block: local-development/gsd/static/app.css | edit -->
```css
  dialog.ns-preview { border: 2px solid CanvasText; }
}

```

```css
  dialog.ns-preview { border: 2px solid CanvasText; }
}
/* #316 (SPEC_D4 §3.6): the Rejoin dialog wears #ns-preview's look, wider for two fields and the two gates. */
dialog.cc-rejoin { max-width: min(560px, calc(100% - 2 * var(--space-8))); }
dialog.cc-rejoin ul.cc-gates { max-height: none; overflow: visible; display: grid; gap: var(--space-4); }
dialog.cc-rejoin ul.cc-gates li { border: 1px solid var(--gridline); border-radius: var(--radius-md); padding: var(--space-5) var(--space-6);
  font-size: var(--text-md); color: var(--text-secondary); overflow-wrap: anywhere; }
dialog.cc-rejoin .rejoin-acts { justify-content: flex-end; margin-top: var(--space-6); }

```

<!-- block: local-development/tests/test_cluster_rejoin.py | create -->
```python
"""Rejoin (#316, docs/specs/SPEC_D4_cluster_rejoin.md): `POST /api/clusterconfigs/{name}/rejoin` takes a cluster
administrator's own username and password for ONE login to the remote, asks the remote whether that person is a
cluster administrator there (D8), reads the poller's token Secret, revokes the login and writes gsd-cluster-<name>
here. The password is presented at most once per press, never retried, never stored, never presented as any other
account, and the fleet account is never used. The page's dialog is in tests/test_ui.py::TestClusterConfigPage.

The remote is S4b's fake target, which records every request in order (`presented` decodes each authorize's Basic
header, so every budget here counts the wire), plus D8's SelfSubjectAccessReview. The host is the tab's in-memory
namespace (`_Host`). No real account or password appears here: ADMIN is a made-up administrator, and USER the fleet
harness's own fleet account."""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import pathlib
import re
import sqlite3
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import (
    LOOKUP_ACCOUNT_ANNOTATION, MANAGED_BY_ANNOTATION, SOURCE_NAMESPACE_ANNOTATION, SOURCE_SERVICE_ACCOUNT_ANNOTATION,
    TOKEN_SOURCE_ANNOTATION,
)
from gsd.config import ClusterConfig
from gsd.fleetlookup import INVALID_SINCE_LABEL, CredentialGate
from test_clusterconfig import TOKEN as STORED_TOKEN, _secret
from test_clusterconfig_tab import NS, _Host
from test_fleet_lifecycle import LeaseHost, process, retrieved
from test_fleet_login import DISCOVERY_PATH, OAUTH, PASSWORD, TOKEN, USER, USER_TOKEN_API, down, login_302, refused_401
from test_fleet_lookup import SA_TOKEN, SOURCE, LookupTarget, sa_secret
from test_visibility import H, _MapResolver, _seed, _settings

REPO = pathlib.Path(__file__).resolve().parents[2]
#: The contract's own strings, written out rather than imported: a test that imported them would pass whatever they said.
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
REJOINED_BY_ANNOTATION = "groupsync-dashboard.io/rejoined-by"
REJOIN_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/rejoin-account"
REJOINED_AT_ANNOTATION = "groupsync-dashboard.io/rejoined-at"
ADMIN, ADMIN_PASSWORD = "alice.admin", "Adm1n-pw-7f3e9c"
BASIC = base64.b64encode(f"{ADMIN}:{ADMIN_PASSWORD}".encode()).decode()
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
ADMIN_REASON = 'RBAC: allowed by ClusterRoleBinding "cluster-admins" of ClusterRole "cluster-admin" to Group "admins"'


def review(allowed=True, reason: str | None = ADMIN_REASON, **status) -> httpx.Response:
    """The remote's SelfSubjectAccessReview answer, in the shape measured on the lab (SPEC_D4 §2.3)."""
    body = {"allowed": allowed, **({"reason": reason} if reason else {}), **status}
    return httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "apiVersion": "authorization.k8s.io/v1",
                                     "metadata": {}, "status": body})


class RemoteTarget(LookupTarget):
    """S4b's fake target plus D8's review, answered from `review` (a Response, or a callable given the request)."""

    def __init__(self, *answers, review_answer=None, **kw):
        super().__init__(*answers, **kw)
        self.review = review() if review_answer is None else review_answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == SSAR_API:
            self.requests.append(request)
            return self._answer(self.review, request)
        return super().__call__(request)

    @property
    def reviews(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == SSAR_API]


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize request, in the order it reached the target."""
    out = []
    for request in target.authorize:
        user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
        out.append((user, password))
    return out


class _Poller:
    """The route's two needs from the poller: its one credential gate (#315) and the discovery wake."""

    def __init__(self):
        self._credential_gate = CredentialGate()
        self.woke = 0

    def request_discovery(self):
        self.woke += 1


@pytest.fixture
def remote(monkeypatch):
    """Every httpx.Client the login, the review and the read build goes to one fake target."""
    target = RemoteTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", "https://api.east.example:6443"),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


def _app(tmp_path, monkeypatch, host, *discovered, name="gsd", **kw):
    """One dashboard process: its own store, its own poller gate, `discovered` on its registry."""
    db = str(tmp_path / f"{name}.db"); _seed(db)
    settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True, **kw)
    settings.cluster_registry.namespace = NS
    settings.cluster_registry.replace(list(discovered), [], at="2026-09-27T14:00:00Z")
    monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
    monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.poller = _Poller()
    return app, settings


@pytest.fixture
def rig(tmp_path, monkeypatch, remote):
    host = _Host({"gsd-cluster-east": _secret(), "gsd-cluster-west": _secret("gsd-cluster-west", cluster="west",
                                                                           server="https://api.west.example:6443")})
    east = parse_secret(_secret(), host_name="c1")
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    app, settings = _app(tmp_path, monkeypatch, host, east, west)
    with TestClient(app) as c:
        yield c, app, settings, host, remote


def _rejoin(c, name="east", who="root", *, username=ADMIN, password=ADMIN_PASSWORD):
    return c.post(f"/api/clusterconfigs/{name}/rejoin", headers=H(who), json={"username": username, "password": password})


def _writes(host) -> list[tuple[str, str]]:
    return [call for call in host.calls if call[0] != "GET"]


# ── the exchange ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance(rig, caplog, monkeypatch):
    c, app, settings, host, remote = rig

    def never(*a, **kw):
        raise AssertionError("Rejoin entered the fleet account's lookup")
    monkeypatch.setattr("gsd.fleetlookup.lookup", never)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"outcome", "message", "at"} and body["outcome"] == "rejoined" and ISO.match(body["at"])
    assert "Signed in to east as alice.admin, who may update clusterrolebindings there" in body["message"]
    assert "the login was signed out" in body["message"]
    # the wire: discovery, ONE authorize as the person, D8 with the login's token, the read, the revoke
    order = [(q.method, q.url.path) for q in remote.requests]
    assert order[:4] == [("GET", DISCOVERY_PATH), ("GET", "/oauth/authorize"), ("POST", SSAR_API), ("GET", SOURCE)]
    assert len(order) == 5 and order[4][0] == "DELETE" and order[4][1].startswith(USER_TOKEN_API + "/")
    assert presented(remote) == [(ADMIN, ADMIN_PASSWORD)]
    assert remote.reviews[0].headers["authorization"] == f"Bearer {TOKEN}" == remote.reads[0].headers["authorization"]
    assert json.loads(remote.reviews[0].content) == {
        "apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": {"verb": "update", "resource": "clusterrolebindings",
                                        "group": "rbac.authorization.k8s.io"}}}
    # the host: updated in place with the person's provenance, and no lookup-account
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]
    assert [path for _, path in host.calls if "gsd-fleet-account" in path] == [], "the fleet password was read"
    stored = host.secrets["gsd-cluster-east"]
    assert json.loads(base64.b64decode(stored["data"]["config"])) == {"bearerToken": SA_TOKEN}
    assert stored["metadata"]["annotations"] == {
        TOKEN_SOURCE_ANNOTATION: "rejoin", SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
        SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        REJOINED_BY_ANNOTATION: "root", REJOIN_ACCOUNT_ANNOTATION: ADMIN, REJOINED_AT_ANNOTATION: body["at"]}
    assert app.state.poller.woke == 1, "a write wakes discovery, as every write in the tab does"
    # the lines: the login's own, marked as a Rejoin; the remote's answer, as D8 asks; the outcome
    assert any(m.startswith("fleet-login ") and "account=alice.admin" in m and "rejoin_by=root" in m for m in caplog.messages)
    assert any(m.startswith("cluster-rejoin-review cluster=east by=root account=alice.admin") and "allowed=true" in m
               and 'question="update clusterrolebindings"' in m and "cluster-admins" in m for m in caplog.messages)
    assert "cluster-rejoined cluster=east by=root account=alice.admin secret=gsd-cluster-east written=updated revoked=true" in caplog.text
    assert "cluster-secret-rotated secret=gsd-cluster-east namespace=ns cluster=east by=root" in caplog.text


def test_a_lookup_written_secret_rejoined_drops_lookup_account_and_keeps_who_made_it(rig):
    """A Secret the lookup wrote records the fleet account in `lookup-account`. Rejoin replaces the provenance and
    removes that key — the daily ping logs in as whatever account it names (#432) — and keeps `managed-by`."""
    c, app, settings, host, remote = rig
    written = _secret(); written["metadata"]["annotations"] = {
        MANAGED_BY_ANNOTATION: "sa-token-lookup", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
        SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator", SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        LOOKUP_ACCOUNT_ANNOTATION: USER}
    host.secrets["gsd-cluster-east"] = written
    assert _rejoin(c).json()["outcome"] == "rejoined"
    ann = host.secrets["gsd-cluster-east"]["metadata"]["annotations"]
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann and ann[MANAGED_BY_ANNOTATION] == "sa-token-lookup"
    assert ann[TOKEN_SOURCE_ANNOTATION] == "rejoin" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN


def test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own(tmp_path, monkeypatch, remote):
    """A values stanza whose lookup has not written its Secret yet (the fleet account locked, say): Rejoin creates
    gsd-cluster-rnd with the stanza's policy, `managed-by: ui`, and the person's provenance; discovery then counts it
    as the stanza's own (`owned_by_mode`), so it is no shadow and the stanza's policy is what is served."""
    rnd = ClusterConfig("rnd", "https://api.rnd.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER,
                        visibility="self-only", identity="none")
    host = _Host({})
    app, settings = _app(tmp_path, monkeypatch, host)
    settings.clusters.append(rnd)
    with TestClient(app) as c:
        r = _rejoin(c, "rnd")
    assert r.status_code == 200 and r.json()["outcome"] == "rejoined", r.text
    assert _writes(host) == [("POST", f"/api/v1/namespaces/{NS}/secrets")]
    stored = host.secrets["gsd-cluster-rnd"]
    ann = stored["metadata"]["annotations"]
    assert ann[MANAGED_BY_ANNOTATION] == "ui" and ann[TOKEN_SOURCE_ANNOTATION] == "rejoin"
    assert ann[REJOINED_BY_ANNOTATION] == "root" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann
    data = {k: base64.b64decode(v).decode() for k, v in stored["data"].items()}
    assert (data["visibility"], data["identity"]) == ("self-only", "none")
    clusters, findings = discover(None, NS, host_name="c1", values_names=("c1", "c2", "rnd"),
                                  values_modes={"rnd": "remote-lookup"}, items=[stored])
    assert [f.code for f in findings] == [], "the rejoined Secret over its own stanza is no shadow"
    settings.cluster_registry.replace(clusters, findings, at="2026-09-27T14:05:00Z")
    served = settings.cluster("rnd")
    assert served.credential_kind == "bearer" and served.token_source == "rejoin" and served.lookup_account is None
    assert (served.visibility, served.identity) == ("self-only", "none"), "the stanza's policy, not the Secret's own"


def test_the_daily_ping_never_logs_in_as_the_person_who_rejoined(rig, tmp_path, monkeypatch):
    """#432, read forward: the ping logs in as whatever account a retrieved Secret's `lookup-account` names, WITH THE
    FLEET PASSWORD. Had Rejoin written the person there, the ping would present the fleet password as the person —
    a refused login counted against their directory entry, once a day. It writes `rejoin-account` instead."""
    c, app, settings, host, remote = rig
    assert _rejoin(c).json()["outcome"] == "rejoined"
    rejoined, findings = discover(None, NS, host_name="c1", items=[host.secrets["gsd-cluster-east"]])
    assert findings == [] and rejoined[0].token_source == "rejoin"
    remote.answers = [login_302()] * 4
    start = len(remote.authorize)
    lease_host = LeaseHost()
    lease_host.rotate(PASSWORD)
    fleet = process(tmp_path, monkeypatch, lease_host, discovered=[*rejoined, retrieved("shared-rnd")],
                    fleet_account_username=USER)
    fleet._ping_accounts()
    assert presented(remote)[start:] == [(USER, PASSWORD)], "the ping presented the fleet password as someone else"


# ── the route's refusals: nothing is sent, and no value is repeated ─────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    f'"{ADMIN_PASSWORD}"',                                                        # a JSON string: a typed body quoted it whole
    f'["{ADMIN}", "{ADMIN_PASSWORD}"]',
    "12345",
    "",                                                                           # no body at all
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}", "token": "x"}}',  # a key the contract does not know
    f'{{"username": "{ADMIN}", "password": 12345}}',
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}"',                  # not JSON
], ids=["string", "list", "number", "empty", "unknown-key", "not-a-string", "malformed"])
def test_the_body_is_username_and_password_and_nothing_else(rig, raw):
    c, app, settings, host, remote = rig
    r = c.post("/api/clusterconfigs/east/rejoin", headers={**H("root"), "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422, r.text
    assert ADMIN_PASSWORD not in r.text and remote.requests == [] and _writes(host) == []


@pytest.mark.parametrize("name,username,password,status,code", [
    ("c1", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # the host: the pod's own ServiceAccount
    ("c2", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a values entry with its own credential
    ("sl", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a Secret declaring userSelfLogin
    ("cm", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # generated from a ConfigMap
    ("east", "alice:admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),   # RFC 7617: no colon in a user-id
    ("east", "alice admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),
    ("east", "SVC-GSD-Fleet\n", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),  # a final newline: the grammar's $ passes it
    ("east", "SVC-GSD-Fleet", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),    # the chart's fleet account, any case
    ("east", "stanza-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # a stanza's ldapConnectionBootstrap
    ("east", "recorded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"), # a Secret's lookup-account
    ("east", "padded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # one recorded with a final newline
    ("east", ADMIN, "", 422, "rejoin-password-missing"),
    ("east", ADMIN, "Adm1n-pw\nsecond-line", 422, "rejoin-password-invalid"),  # RFC 7617: no control characters
    ("east", ADMIN, "Adm1n-pw-\ud800", 422, "rejoin-password-invalid"),        # not encodable: an unpaired surrogate
])
def test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value(tmp_path, monkeypatch, remote, name, username,
                                                                          password, status, code):
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    discovered = [parse_secret(_secret(), host_name="c1"),
                  ClusterConfig("sl", "https://api.sl.example:6443", user_self_login=True, ldap_connection_bootstrap="svc-sl",
                                source="secret:gsd-cluster-sl"),
                  dataclasses.replace(west, name="cm", source="secret:gsd-cluster-cm", onboarding=("fleet", "uid-1", "0" * 64)),
                  dataclasses.replace(west, name="rec", source="secret:gsd-cluster-rec", token_source="remote-lookup",
                                      lookup_account="recorded-account"),
                  dataclasses.replace(west, name="pad", source="secret:gsd-cluster-pad", token_source="remote-lookup",
                                      lookup_account="padded-account\n")]
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, *discovered, fleet_account_username=USER)
    settings.clusters.append(ClusterConfig("st", "https://api.st.example:6443", sa_token_lookup=True,
                                           ldap_connection_bootstrap="stanza-account"))
    with TestClient(app) as c:
        r = c.post(f"/api/clusterconfigs/{name}/rejoin", headers={**H("root"), "Content-Type": "application/json"},
                   content=json.dumps({"username": username, "password": password}))
    assert r.status_code == status and r.json()["detail"].startswith(f"{code}: "), r.text
    assert remote.requests == [] and _writes(host) == []
    if code.startswith("rejoin-"):
        assert username not in r.text and (not password or password not in r.text), "a refusal repeats no value"
    gate = app.state.poller._credential_gate
    assert gate._refused == {} and gate._spent == set(), "a refusal before the wire records nothing"


def test_below_the_cluster_admin_tier_is_403_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    assert _rejoin(c, who="auditor").status_code == 403       # the wide tier, not the cluster-admin tier
    assert c.post("/api/clusterconfigs/east/rejoin", json={"username": ADMIN, "password": ADMIN_PASSWORD}).status_code == 403
    assert remote.requests == [] and _writes(host) == []


def test_an_unknown_or_retired_name_is_404_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    app.state.store.upsert_cluster("gone", "https://api.gone:6443", False)
    for name in ("nope", "gone"):
        r = _rejoin(c, name)
        assert r.status_code == 404 and name in r.json()["detail"], r.text
    assert remote.requests == []


def test_no_poller_means_no_gate_and_no_login(rig):
    c, app, settings, host, remote = rig
    app.state.poller = None
    r = _rejoin(c)
    assert r.status_code == 409 and "nothing was sent" in r.json()["detail"] and remote.requests == []


def test_with_the_writes_switch_off_the_route_does_not_exist(tmp_path):
    db = str(tmp_path / "off.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        assert c.post("/api/clusterconfigs/c1/rejoin", headers=H("root"), json={}).status_code in (404, 405)
    assert "/api/clusterconfigs/{name}/rejoin" not in app.openapi()["paths"]


# ── the gate: once the password is on the wire, the outcome is terminal (#283, #315) ─────────────────────────

@pytest.mark.parametrize("answer,first", [
    (refused_401, "login-refused"),
    (lambda: httpx.Response(500, text="Internal Server Error"), "login-failed"),    # a LOCKED account's LDAP code 19
    (lambda: (lambda request: httpx.ReadTimeout("timed out")), "login-failed"),     # written, then no answer
], ids=["401", "500", "read-timeout"])
def test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again(rig, answer, first):
    c, app, settings, host, remote = rig
    remote.answers = [answer(), login_302()]
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == first and len(remote.authorize) == 1
    assert "it is not sent again" in r1.json()["message"]
    r2 = _rejoin(c, "west")                                  # another cluster: the gate is the ACCOUNT's (#315)
    assert r2.json()["outcome"] == "login-refused" and "so it was not sent" in r2.json()["message"]
    assert len(remote.authorize) == 1, "the same password reached the directory twice"
    r3 = _rejoin(c, password="Adm1n-pw-corrected")          # a different password is a different entry
    assert r3.json()["outcome"] == "rejoined" and len(remote.authorize) == 2
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]


def test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated(rig):
    """ONE_TRY: the fleet's schedule retries a failure that bound nothing; a person is waiting, so it is answered at
    once, and the password is free to be sent on the next press."""
    c, app, settings, host, remote = rig
    remote.discovery = down
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == "login-failed" and "the password was not sent" in r1.json()["message"]
    assert [q.url.path for q in remote.requests] == [DISCOVERY_PATH], "one attempt, no retry"
    remote.discovery = {"issuer": OAUTH, "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
    assert _rejoin(c).json()["outcome"] == "rejoined" and presented(remote) == [(ADMIN, ADMIN_PASSWORD)]


# ── D8: the remote decides, with the login's own token ─────────────────────────────────────────────────────────

def test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked(rig, caplog):
    c, app, settings, host, remote = rig
    remote.review = review(allowed=False, reason=None)
    with caplog.at_level(logging.INFO):
        r = _rejoin(c)
    body = r.json()
    assert body["outcome"] == "not-cluster-admin" and "east says alice.admin may not update clusterrolebindings" in body["message"]
    assert "the login was signed out" in body["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1
    assert "cluster-rejoin-review cluster=east by=root account=alice.admin" in caplog.text and "allowed=false" in caplog.text
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None, "the password was right"


@pytest.mark.parametrize("answer", [
    httpx.Response(403, text="forbidden"),
    httpx.Response(500, text="Internal Server Error"),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {}}),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {"allowed": "true"}}),
    lambda request: httpx.ReadTimeout("timed out"),
], ids=["403", "500", "no-status", "string-true", "timeout"])
def test_a_review_that_does_not_answer_is_a_refusal_never_a_yes(rig, answer):
    c, app, settings, host, remote = rig
    remote.review = answer
    r = _rejoin(c)
    assert r.json()["outcome"] == "access-review-failed" and "could not be asked" in r.json()["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1


def test_the_review_asks_the_configured_cluster_admin_question(tmp_path, monkeypatch, remote):
    """#322's question is configurable (visibility.clusterAdminSar); the remote is asked the host's own question."""
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"),
                         visibility_cluster_admin_sar_verb="get", visibility_cluster_admin_sar_resource="secrets",
                         visibility_cluster_admin_sar_api_group="", visibility_cluster_admin_sar_namespace="group-sync-operator")
    with TestClient(app) as c:
        r = _rejoin(c)
    assert json.loads(remote.reviews[0].content)["spec"]["resourceAttributes"] == {
        "verb": "get", "resource": "secrets", "group": "", "namespace": "group-sync-operator"}
    assert "may get secrets in namespace group-sync-operator there" in r.json()["message"]


# ── the read, the write, and one Rejoin at a time ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("secret,code", [
    (httpx.Response(404, text="not found"), "sa-token-secret-missing"),
    (httpx.Response(403, text="forbidden"), "sa-token-unreadable"),
    (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "2027-09-22"})), "sa-token-invalidated"),
])
def test_a_token_read_refusal_writes_nothing_and_revokes_the_login(rig, secret, code):
    c, app, settings, host, remote = rig
    remote.secret = secret
    r = _rejoin(c)
    assert r.json()["outcome"] == code and "nothing was written" in r.json()["message"]
    assert _writes(host) == [] and len(remote.revokes) == 1
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None


def test_a_refused_write_stores_nothing_and_says_so(rig):
    c, app, settings, host, remote = rig
    host.refuse = True
    r = _rejoin(c)
    assert r.json()["outcome"] == "lookup-write-failed" and "nothing was stored" in r.json()["message"]
    assert json.loads(base64.b64decode(host.secrets["gsd-cluster-east"]["data"]["config"])) == {"bearerToken": STORED_TOKEN}


def test_one_rejoin_at_a_time_in_this_process(rig):
    """A second press — the other tab, a script, another cluster — while the first is out is refused, never queued:
    the gate's check and the login it guards are one step, so no two presses reach a password's first use."""
    c, app, settings, host, remote = rig
    inside, release, answers = threading.Event(), threading.Event(), {}

    def slow(request):
        inside.set()
        release.wait(10)
        return login_302()

    remote.answers = [slow]
    first = threading.Thread(target=lambda: answers.setdefault("first", _rejoin(c)))
    first.start()
    try:
        assert inside.wait(10), "the first login started"
        answers["second"] = _rejoin(c, "west")
    finally:
        release.set()
        first.join(10)
    assert answers["second"].status_code == 409 and "already in flight" in answers["second"].json()["detail"]
    assert answers["first"].json()["outcome"] == "rejoined" and len(remote.authorize) == 1
    remote.answers = [login_302()]
    assert _rejoin(c, "west").json()["outcome"] == "rejoined", "the slot is released when the Rejoin ends"


# ── the redaction pin (#283's, carried): the password is on one header of one request, and nowhere else ─────

def _planted(target_kind: str) -> dict:
    """One scenario's remote, with every secret in play at that point planted in every field it controls: the
    password and its Basic form from the authorize on, the login's token from the 302 on, the token read from the
    read on. A value the dashboard has not been handed yet is not its secret to scrub, and is not planted."""
    login = f"pw={ADMIN_PASSWORD} basic={BASIC}"
    session = f"{login} bearer={TOKEN}"
    read = f"{session} sa={SA_TOKEN}"
    return {
        "401": dict(answers=[refused_401(body=login)]),
        "401-challenge": dict(answers=[httpx.Response(401, headers={"Www-Authenticate": f'Basic realm="{ADMIN_PASSWORD}"'})]),
        "500": dict(answers=[httpx.Response(500, text=login)]),
        "302-error": dict(answers=[httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error={ADMIN_PASSWORD}"})]),
        "issuer": dict(discovery={"issuer": f"https://{ADMIN}:{ADMIN_PASSWORD}@oauth.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}),
        "review-reason": dict(review_answer=review(reason=session, evaluationError=session)),
        "review-denied": dict(review_answer=review(allowed=False, reason=session)),
        "review-500": dict(review_answer=httpx.Response(500, text=session)),
        "read-500": dict(secret=httpx.Response(500, text=session)),
        "read-owner": dict(secret=httpx.Response(200, json=sa_secret(sa=read))),
        "revoke-500": dict(revoke=httpx.Response(500, text=read)),
        "write-echo": dict(host_echo=True),
        "success": {},
    }[target_kind]


@pytest.mark.parametrize("kind", ["401", "401-challenge", "500", "302-error", "issuer", "review-reason", "review-denied",
                                  "review-500", "read-500", "read-owner", "revoke-500", "write-echo", "success"])
def test_the_password_appears_on_one_header_and_nowhere_else(tmp_path, monkeypatch, remote, caplog, kind):
    scenario = _planted(kind)
    for field in ("answers", "discovery", "secret", "revoke"):
        if field in scenario:
            setattr(remote, field, scenario[field])
    remote.review = scenario.get("review_answer", remote.review)
    host = _Host({"gsd-cluster-east": _secret()}, echo=scenario.get("host_echo", False))
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"))
    with caplog.at_level(logging.DEBUG), TestClient(app) as c:
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    gate = app.state.poller._credential_gate
    kept = "\n".join([r.text, caplog.text, json.dumps(host.secrets), repr(gate._refused), repr(gate._spent),
                      json.dumps([f.public() for f in settings.cluster_registry.findings()]),
                      "\n".join(sqlite3.connect(settings.db_path).iterdump())])
    for value in (ADMIN_PASSWORD, BASIC, TOKEN):
        assert value not in kept, f"{kind}: a secret was kept or echoed"
    assert SA_TOKEN not in kept.replace(json.dumps(host.secrets), ""), f"{kind}: the token read was echoed"
    for request in remote.requests:                        # on the wire: the authorize's Basic header, once
        seen = f"{request.url} {request.content!r} " + " ".join(f"{k}={v}" for k, v in request.headers.items()
                                                                if not (request.url.path == "/oauth/authorize" and k == "authorization"))
        assert ADMIN_PASSWORD not in seen and BASIC not in seen, (kind, request.method, request.url.path)
    assert len(remote.authorize) <= 1


# ── the budget over the system ───────────────────────────────────────────────────────────────────────────────

#: SPEC_D4 §3.8's rows: (the remote's answers in order, the presses as (process, password)). A new process name is a
#: restart or a second replica: its own poller gate, over the same host and remote.
BUDGET = {
    "one press, the right password": ([login_302()], [("p", ADMIN_PASSWORD)]),
    "two presses, the right password": ([login_302(), login_302()], [("p", ADMIN_PASSWORD)] * 2),
    "a 401, then the same password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-1")] * 2),
    "a 500 (a locked account), then the same password": ([httpx.Response(500), login_302()], [("p", "L0cked-pw-1")] * 2),
    "a timeout after the password was sent, then the same": (
        [lambda request: httpx.ReadTimeout("timed out"), login_302()], [("p", "T1meout-pw-1")] * 2),
    "a 401, then the right password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-2"), ("p", ADMIN_PASSWORD)]),
    "a 401, then the same password on a restarted process": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-3"), ("restarted", "Wr0ng-pw-3")]),
    "a 401, then the same password on a second replica": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-4"), ("replica", "Wr0ng-pw-4")]),
}


def test_the_budget_over_the_system(tmp_path, monkeypatch, remote):
    """SPEC_D4 §3.8's table, measured: authorize requests on the wire for each shape. One press presents the password
    at most once, and a password the directory answered is not presented again by that process. A restart and a
    second replica each start an empty gate: the stated scope, because nothing about a person's password is kept."""
    host = _Host({"gsd-cluster-east": _secret()})
    east = parse_secret(_secret(), host_name="c1")
    measured = {}
    for n, (shape, (answers, presses)) in enumerate(BUDGET.items()):
        remote.requests.clear()
        remote.answers = list(answers)
        outcomes, clients = [], {}
        for process_name, password in presses:
            if process_name not in clients:
                app, _ = _app(tmp_path, monkeypatch, host, east, name=f"budget-{n}-{process_name}")
                clients[process_name] = TestClient(app).__enter__()
            outcomes.append(_rejoin(clients[process_name], password=password).json()["outcome"])
        for client in clients.values():
            client.__exit__(None, None, None)
        measured[shape] = (len(remote.authorize), outcomes)
    assert measured == {
        "one press, the right password": (1, ["rejoined"]),
        "two presses, the right password": (2, ["rejoined", "rejoined"]),
        "a 401, then the same password": (1, ["login-refused", "login-refused"]),
        "a 500 (a locked account), then the same password": (1, ["login-failed", "login-refused"]),
        "a timeout after the password was sent, then the same": (1, ["login-failed", "login-refused"]),
        "a 401, then the right password": (2, ["login-refused", "rejoined"]),
        "a 401, then the same password on a restarted process": (2, ["login-refused", "login-refused"]),
        "a 401, then the same password on a second replica": (2, ["login-refused", "login-refused"]),
    }, measured


# ── the runbook (the 2026-09-23 requirement) ───────────────────────────────────────────────────────────────

def test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it():
    runbook = REPO / "charts/group-sync-dashboard/RUNBOOK.md"
    headings = re.findall(r"^## (\d)\. ", runbook.read_text(), re.M)
    assert headings == ["1", "2", "3", "4", "5", "6"], headings
    assert "../charts/group-sync-dashboard/RUNBOOK.md" in (REPO / "docs/README.md").read_text()
    assert "(RUNBOOK.md)" in (REPO / "charts/group-sync-dashboard/README.md").read_text()
    credentials = (REPO / "charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md").read_text()
    assert "Rejoin **PLANNED**" not in credentials and "(RUNBOOK.md)" in credentials
```

<!-- block: local-development/tests/test_api_contract.py | edit -->
```python
    "POST /api/clusterconfigs/{name}/refresh",     # SPEC_D3 (#311): a probe that writes nothing, carved out like /test
```

```python
    "POST /api/clusterconfigs/{name}/refresh",     # SPEC_D3 (#311): a probe that writes nothing, carved out like /test
    "POST /api/clusterconfigs/{name}/rejoin",      # SPEC_D4 (#316): a person's one login, then the Secret write
```

<!-- block: local-development/tests/test_api_contract.py | edit -->
```python
    """The carve-out, exact: with the switch on the schema carries these five non-GET routes and no
    other; any sixth, on or off, fails here or above."""
```

```python
    """The carve-out, exact: with the switch on the schema carries these six non-GET routes and no
    other; any seventh, on or off, fails here or above."""
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->
```python
                              "onboarding_configmap": None}
```

```python
                              "onboarding_configmap": None, "rejoinable": True}
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
            assert "Rejoin (#316), not built yet" in refused and page.locator("#cc-cluster-east [data-cc-rejoin]").count() == 0
```

```python
            # #316 (SPEC_D4): the next step is Rejoin, drawn where the route accepts it — the Secret row here
            assert "use Rejoin" in refused and page.locator("#cc-cluster-east [data-cc-rejoin]").count() == 1
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
            assert page.locator("[data-cc-refresh]").count() == 0
        finally:
            gate.set()
```

```python
            assert page.locator("[data-cc-refresh], [data-cc-rejoin]").count() == 0
        finally:
            gate.set()

    def test_rejoin_is_offered_after_a_refused_refresh_and_its_dialog_keeps_what_is_typed(self, page, cc_rig, monkeypatch):
        """#316 (SPEC_D4 §3.6): Rejoin appears only where the route accepts it (`rejoinable`) and only once Refresh said
        the stored credential is refused. Its dialog is static, outside #main, so the minute's repaint keeps what is
        typed; there is no form, so no submission can carry the password into a URL; Cancel clears both fields."""
        from gsd.kube import AUTH_FAILED, ClusterClient, ClusterError
        base, host, settings = cc_rig

        class _Refused(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Refused)
        _open_as(page, base, "root")
        page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
        assert page.locator("[data-cc-rejoin]").count() == 0, "no Rejoin before Refresh has said anything"
        page.click("#cc-refresh-east")
        page.wait_for_selector("#cc-rejoin-east")
        assert page.locator("#cc-cluster-east .cc-acts #cc-refresh-east + #cc-rejoin-east + #cc-delete-east").count() == 1
        assert "use Rejoin" in page.locator("#cc-refresh-result-east").inner_text()
        # the host and the values entry are refused by the route, so they are never offered it, refused or not
        page.click("#cc-refresh-crc-local"); page.click("#cc-refresh-prod-east")
        page.wait_for_function("() => ['crc-local', 'prod-east'].every((id) => (view.clusterRefresh[id] || {}).state === 'done')")
        assert page.locator("#cc-rejoin-crc-local, #cc-rejoin-prod-east").count() == 0
        assert "Replace the credential where it is written" in page.locator("#cc-refresh-result-prod-east").inner_text()
        page.click("#cc-rejoin-east")
        page.wait_for_selector("#rejoin-dialog[open]")
        assert page.evaluate("() => !document.getElementById('main').contains(document.getElementById('rejoin-dialog'))")
        text = page.locator("#rejoin-dialog").inner_text()
        assert "Rejoin east" in text and "are used for this one login and are not stored" in text and "decided there" in text
        assert "https://api.east.example:6443" in text and "gsd-cluster-east" in text
        assert page.locator("#rejoin-password").get_attribute("type") == "password"
        assert page.locator("#rejoin-username").get_attribute("autocomplete") == "off" == page.locator("#rejoin-password").get_attribute("autocomplete")
        assert page.locator("#rejoin-dialog form").count() == 0
        page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-typed")
        # a real repaint of #main, proved by a marker the old button carries and the new one lacks
        page.evaluate("() => { document.getElementById('cc-rejoin-east').dataset.old = '1'; lastFingerprint = null; return refresh({ auto: true }); }")
        page.wait_for_function("() => !document.getElementById('cc-rejoin-east').dataset.old")
        assert page.input_value("#rejoin-username") == "alice.admin" and page.input_value("#rejoin-password") == "Adm1n-pw-typed"
        assert page.evaluate("() => document.getElementById('rejoin-dialog').open")
        page.set_viewport_size({"width": 375, "height": 812}); page.wait_for_timeout(200)
        box = page.locator("#rejoin-dialog").bounding_box()
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth") and box["x"] >= 0 and box["x"] + box["width"] <= 375
        page.click("#rejoin-cancel")
        page.wait_for_function("() => !document.getElementById('rejoin-dialog').open")
        assert page.input_value("#rejoin-username") == "" and page.input_value("#rejoin-password") == ""
        page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
        page.fill("#rejoin-password", "Adm1n-pw-escaped"); page.keyboard.press("Escape")   # closes without closeRejoin
        page.wait_for_function("() => !document.getElementById('rejoin-dialog').open && !document.getElementById('rejoin-password').value")
        page.evaluate("() => { data.clusterconfigs.secrets.writes = false; render(); }")
        assert page.locator("[data-cc-rejoin]").count() == 0, "absent, not disabled, where the writes are off"

    def test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere(self, page, cc_rig, monkeypatch):
        """#316 (SPEC_D4 §3.6, §3.8): a press is one request carrying the typed password once. The field is emptied as the
        request leaves, so a double click, and a second press before it is typed again, send nothing more. A refusal
        keeps the dialog open with its sentence; a success closes it; both land on the card. The password is in no
        storage, no URL and no page state, and pagehide and the idle timeout clear what is typed."""
        import threading
        from gsd.fleetlookup import CredentialGate
        from gsd.kube import AUTH_FAILED, ClusterClient, ClusterError
        base, host, settings = cc_rig
        release, calls, answers = threading.Event(), [], ["login-refused", "rejoined"]

        class _Refused(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")

        class _Poller:
            _credential_gate = CredentialGate()

            def request_discovery(self):
                pass

        def rejoin(cluster, settings, host_client, *, own_namespace, gate, username, password, viewer):
            calls.append((cluster.name, username, password, viewer))
            release.wait(10)
            return {"outcome": answers.pop(0), "message": "the remote said so", "at": "2026-09-27T14:05:40Z"}

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Refused)
        monkeypatch.setattr(_SCOPED_APP.state, "poller", _Poller(), raising=False)
        monkeypatch.setattr("gsd.rejoin.rejoin", rejoin)
        posts: list[str] = []
        page.on("request", lambda r: posts.append(r.post_data) if r.method == "POST" and r.url.endswith("/rejoin") else None)
        kept = "() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), location.href, JSON.stringify(view)])"
        try:
            _open_as(page, base, "root")
            page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
            page.click("#cc-refresh-east"); page.wait_for_selector("#cc-rejoin-east")
            page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
            page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-once")
            page.dblclick("#rejoin-go")
            page.wait_for_selector("#cc-rejoin-east[disabled][aria-busy='true']")
            assert page.input_value("#rejoin-password") == "", "emptied as the request left"
            assert "Adm1n-pw-once" not in page.evaluate(kept)
            release.set()
            page.wait_for_function("() => (document.getElementById('cc-rejoin-result-east') || {innerText: ''}).innerText.includes('login-refused')")
            release.clear()
            assert page.evaluate("() => document.getElementById('rejoin-dialog').open") and "login-refused" in page.inner_text("#rejoin-msg")
            page.click("#rejoin-go")                                     # nothing typed again: nothing is sent
            assert "Type your username and your password" in page.inner_text("#rejoin-msg")
            assert [json.loads(p) for p in posts] == [{"username": "alice.admin", "password": "Adm1n-pw-once"}]
            page.fill("#rejoin-password", "Adm1n-pw-twice"); page.press("#rejoin-password", "Enter")
            release.set()
            page.wait_for_function("() => !document.getElementById('rejoin-dialog').open")
            assert "rejoined" in page.inner_text("#cc-rejoin-result-east")
            assert [c[1:] for c in calls] == [("alice.admin", "Adm1n-pw-once", "root"), ("alice.admin", "Adm1n-pw-twice", "root")]
            assert len(posts) == 2 and not any(p in page.evaluate(kept) for p in ("Adm1n-pw-once", "Adm1n-pw-twice"))
            # pagehide (the back/forward cache keeps typed values) and the idle timeout both clear the fields
            page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
            page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-left")
            page.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
            assert page.input_value("#rejoin-username") == "" and page.input_value("#rejoin-password") == ""
            page.fill("#rejoin-password", "Adm1n-pw-left")
            page.evaluate("() => { idle.logoutUrl = null; idleExpire(); }")
            assert not page.evaluate("() => document.getElementById('rejoin-dialog').open")
            assert page.input_value("#rejoin-password") == ""
        finally:
            release.set()
```

<!-- block: charts/group-sync-dashboard/RUNBOOK.md | create -->
```markdown
# Runbook — a remote cluster's connection is broken: Refresh, then Rejoin

The dashboard polls each remote cluster with a token it keeps in a Secret, `gsd-cluster-<name>`. When that token
stops working, this runbook finds out why and repairs it. Why it works this way is in
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file. This page is only the steps.

Refresh and Rejoin are on the Cluster Configurations tab. They need two things: you pass the dashboard's
cluster-admin tier (`visibility.clusterAdminSar`), and the release sets `clusterConfig.secrets.writes.enabled: true`.
Without that switch the tab has no Refresh and no Rejoin, and section 5 is the path. Commands run from a workstation
with `oc` and `jq`, logged in to the dashboard's cluster, with a second kubeconfig context logged in to the remote
cluster as yourself. Set these once:

~~~sh
NS=group-sync-dashboard; REL=group-sync-dashboard   # the release namespace and fullname (oc get deploy -n $NS)
C=shared-qa                                         # the cluster, by the name on its card
REMOTE=shared-qa-me                                 # your kubeconfig context on that cluster (oc config get-contexts)
~~~

## 1. Decide whether the connection is actually broken

On the Cluster Configurations tab, find the cluster's card and press **Refresh**. It probes the cluster with the
token the dashboard already holds. It never logs in and changes nothing. The same answer is in the pod's log:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-(unreachable|refreshed) .*cluster=$C " | tail -3
~~~

The word under the card's `connection` row, or `outcome=` in the line, says what to do next:

| outcome | what it means | next |
|---|---|---|
| `connected` (`ok` in the log) | the stored token works | nothing is broken; the card turns green at the next poll |
| `auth_failed` | the remote refused the stored token: expired, revoked, or wrong | section 2, then 3 |
| `pending` | no token was ever fetched: a `saTokenLookup` cluster whose lookup has not written its Secret | section 3 |
| `forbidden` | the token works, but the remote's RBAC does not let it read | section 4 |
| `unreachable` | the network, DNS, or the API server | section 4 |
| `cert-verify-failed` | the dashboard does not trust the remote's certificate | section 4 |
| `not-probed` | a `userSelfLogin` cluster: its credential is a session, which the card's credential row shows | not Rejoin; see `CLUSTER_CREDENTIALS.md` |

## 2. Confirm the token on the remote before you rejoin

A token that still works on the remote means the problem is elsewhere, and Rejoin will not fix it. Present the stored
token to the remote, through your remote context:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d | jq -r .bearerToken \
  | xargs -I{} oc --context="$REMOTE" whoami --token={}
~~~

- `system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller`: the token works. Go to section 4.
- `error: You must be logged in to the server (Unauthorized)`: the token is refused. Rejoin fixes this.

Then check the two things Rejoin needs on the remote:

~~~sh
oc --context="$REMOTE" auth can-i update clusterrolebindings.rbac.authorization.k8s.io
oc --context="$REMOTE" get secret -n group-sync-operator group-sync-dashboard-cluster-poller-token \
  -o jsonpath='{.type}{"  invalid-since="}{.metadata.labels.kubernetes\.io/legacy-token-invalid-since}{"\n"}'
~~~

- `yes`: you are a cluster administrator there, so Rejoin will accept you. `no`: ask someone who is.
- `kubernetes.io/service-account-token  invalid-since=` with nothing after the `=`: the token Secret is there and
  alive. `NotFound`, or a date after `invalid-since=`, is section 4.

## 3. Rejoin from the UI

**Who may do it.** Someone who passes the dashboard's cluster-admin tier **and** is a cluster administrator of the
remote. The dashboard asks the remote, with your own login, whether you may `update clusterrolebindings` there. If
it says no, nothing is read or written. Use **your own** account: the dashboard refuses the fleet account's name.

**What to do.** On the card, once Refresh answers `auth_failed` or `pending`, press **Rejoin…**. Type your username
and password for that cluster, and press **Rejoin**.

**What it does.** One login to the remote as you, and one question to the remote about you. One read of
`group-sync-operator/group-sync-dashboard-cluster-poller-token`. The login is signed out, and the token is written to
`gsd-cluster-<name>` here. Your password is used for that one login. It is not stored anywhere, and it is not sent
again.

**How to confirm it worked.** The card's `Rejoin:` line reads `rejoined`, and **Refresh** then reads `connected`.
The Secret carries the Rejoin's provenance:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o json \
  | jq '.metadata.annotations | with_entries(select(.key | startswith("groupsync-dashboard.io/")))'
~~~

~~~json
{
  "groupsync-dashboard.io/rejoin-account": "alice",
  "groupsync-dashboard.io/rejoined-at": "2026-09-27T14:05:40Z",
  "groupsync-dashboard.io/rejoined-by": "alice",
  "groupsync-dashboard.io/source-namespace": "group-sync-operator",
  "groupsync-dashboard.io/source-service-account": "group-sync-dashboard-cluster-poller",
  "groupsync-dashboard.io/token-source": "rejoin"
}
~~~

`rejoined-by` is who pressed Rejoin, as the dashboard knows them. `rejoin-account` is the account the remote signed
in. A Secret the tab or the lookup created also keeps its `managed-by`. The pod's log has the remote's answer and the
outcome:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-rejoin(ed|-review|-failed) .*cluster=$C "
~~~

Your login is in the remote's audit log under your name. When login capture reads that cluster, the Logins tab lists
it as a `cli` login there; `kubeadmin`'s logins are never listed.

## 4. When Rejoin is not the answer

A new token fixes only a refused token. For everything else, Rejoin either refuses or repeats the failure:

| what you see | why Rejoin does not help | what fixes it |
|---|---|---|
| `forbidden` on Refresh | the token works; the remote's RBAC is missing | bind the poller ServiceAccount to the dashboard's reader ClusterRole on the remote |
| `unreachable` on Refresh | nothing answered | the cluster's API URL, DNS, a NetworkPolicy or a proxy, from this pod |
| `cert-verify-failed` on Refresh | the trust is wrong | the cluster's CA (`tlsClientConfig.caData`) or the chart's `trustedCA` |
| `sa-token-secret-missing` from Rejoin | the remote has no token Secret to read | create it there: a `kubernetes.io/service-account-token` Secret named `group-sync-dashboard-cluster-poller-token`, annotated `kubernetes.io/service-account.name: group-sync-dashboard-cluster-poller` |
| `sa-token-invalidated` from Rejoin | the remote's legacy-token cleaner killed that token | delete and recreate that Secret on the remote |
| `not-cluster-admin` from Rejoin | the remote says you may not `update clusterrolebindings` there | ask a cluster administrator of the remote |
| `login-failed` from Rejoin, saying the password was not sent | the dashboard could not reach the remote's login | the checks for `unreachable`; the trust must cover the OAuth route too |

## 5. The manual fallback, when the UI is not available

The two-cluster path. It needs someone who is cluster-admin on **both** clusters, with two sessions open.

~~~sh
# on the REMOTE cluster: a token for the poller ServiceAccount (it expires after --duration)
oc --context="$REMOTE" create token group-sync-dashboard-cluster-poller -n group-sync-operator --duration=20m

# on the DASHBOARD's cluster: the whole config, not only the token, because a merge replaces the config value.
# Keep the tlsClientConfig the Secret has now: oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d
oc patch secret gsd-cluster-$C -n $NS --type=merge \
  -p '{"stringData":{"config":"{\"bearerToken\":\"<token>\",\"tlsClientConfig\":{\"insecure\":false}}"}}'
~~~

A token from `oc create token` expires. To store the long-lived token that Rejoin stores, read `.data.token` of
`group-sync-operator/group-sync-dashboard-cluster-poller-token` on the remote instead, and base64-decode it.

A Secret written by `oc` rides the discovery cadence: it takes effect within `discoveryIntervalSeconds` (300 seconds
by default), not in seconds as a write from the tab does. It carries no provenance either: nothing on it says who
wrote it or where the token came from.

## 6. What not to do

- **Do not press Rejoin again and again.** Once your password is sent, the answer is final. The dashboard does not
  send a refused password again while it is the same password. A locked directory account answers LDAP code 19,
  which OpenShift turns into an **HTTP 500, not a 401**, so trying again only locks it further. After a 500, check the
  account with your directory's administrators first. The dashboard holds that password back until its pod restarts,
  even once the account is fixed; a new password works at once.
- **Do not type the fleet account's password into Rejoin.** The dashboard refuses the fleet account's name, and a
  lockout of that account stops every cluster.
- **If the dialog says the answer did not arrive, or the pod restarted during a Rejoin, do not rejoin blindly.**
  Press Refresh first: the Rejoin may have finished. Then list your password logins on the remote and delete any the
  dashboard did not sign out. A token's name is not a secret and cannot log anyone in.

~~~sh
oc --context="$REMOTE" get useroauthaccesstokens --field-selector=clientName=openshift-challenging-client \
  --sort-by=.metadata.creationTimestamp
oc --context="$REMOTE" delete useroauthaccesstokens <name>
~~~
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
## 4. Recovering a cluster today

There is **no in-product way** to re-establish a credential. Today it is done by hand, and it
requires being cluster-admin on **both** clusters with two sessions:
```

```markdown
## 4. Recovering a cluster by hand

With writes on, Rejoin (§5) re-establishes a credential from the tab. Without writes, or without the UI, it is done
by hand, and it requires being cluster-admin on **both** clusters with two sessions. The steps, with what each
answer means, are in [`RUNBOOK.md`](RUNBOOK.md), beside this file:
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
## 5. The intended recovery flow — Refresh **BUILT**, Rejoin **PLANNED**
```

```markdown
## 5. The recovery flow — Refresh, then Rejoin
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
**Rejoin (#316).** When Refresh reports `auth_failed`, an administrator clicks Rejoin and supplies
**their own** cluster-admin username and password *at that moment*. The dashboard authenticates to
the remote cluster as that person, retrieves the ServiceAccount token, writes
`gsd-cluster-<name>`, and **discards the credentials**. Nothing is stored.
```

```markdown
**Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`).** When Refresh reports `auth_failed`, or `pending` for a
cluster whose token was never fetched, the card offers **Rejoin…** on a Secret-sourced cluster or a `saTokenLookup`
stanza. An administrator types **their own** username and password for that cluster, *at that moment*. The dashboard
logs in to the remote once as that person (`gsd/rejoin.py#RejoinLogin`), asks the remote whether that person may
`update clusterrolebindings` there (D8, one `SelfSubjectAccessReview` with the login's own token), reads the poller's
token Secret, signs the login out, and writes `gsd-cluster-<name>` with `token-source: rejoin` and the person's name
(`rejoined-by`, `rejoin-account`, `rejoined-at`). **The credentials are discarded.** Nothing is stored. The route is
`POST /api/clusterconfigs/{name}/rejoin` (`local-development/API.md`), and the steps are in
[`RUNBOOK.md`](RUNBOOK.md).
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
  is wrong precisely when the account is already locked.
- Both are admin-tier only.
```

```markdown
  is wrong precisely when the account is already locked. A Rejoin sends the password at most once per
  press, and the poller's gate holds a refused password back in that pod until it restarts: in memory
  only, because anything durable would keep a fingerprint of a person's password.
- Rejoin never uses the fleet account: it refuses any name a fleet path logs in as, and it writes
  `rejoin-account`, never `lookup-account`, which the daily ping logs in as with the fleet password.
- Both are for the cluster-admin tier only (#322), and exist only with writes on.
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file.
```

```markdown
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file. The repair itself, step by step (Refresh,
then Rejoin, then the manual fallback), is [`RUNBOOK.md`](RUNBOOK.md).
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
  #   Rejoin (#316), when it is built
```

```yaml
  #   Rejoin (#316) — and, asked of the REMOTE with the person's own login, the same question decides whether a
  #     Rejoin may read the token Secret there (SPEC_D4, D8)
```

<!-- block: docs/README.md | edit -->
```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
```

```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [RUNBOOK.md](../charts/group-sync-dashboard/RUNBOOK.md) — a remote cluster's connection is broken: find out why, then Refresh and Rejoin; kept beside the chart's values.
```

<!-- block: local-development/API.md | edit -->
```markdown
`/api/whoami`'s `visibility.cluster_admin`) and the four write routes below; `can.manage` is `true`
```

```markdown
`/api/whoami`'s `visibility.cluster_admin`) and the write routes below; `can.manage` is `true`
```

<!-- block: local-development/API.md | edit -->
```markdown
### The Cluster Configurations tab's writes (#230 S2)

Five routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

```markdown
**`rejoinable`** (#316) is on every live row: `true` where `POST /api/clusterconfigs/{name}/rejoin` accepts the
cluster — a Secret-sourced cluster that does not declare `userSelfLogin` and was not generated from a ConfigMap, or a
`saTokenLookup` stanza — and `false` for the host, a values entry with its own credential, a `userSelfLogin` cluster and
a ConfigMap-generated one. It is the route's own rule (`gsd/rejoin.py#refusal`). A retired row carries none.

### The Cluster Configurations tab's writes (#230 S2)

Six routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

<!-- block: local-development/API.md | edit -->
```markdown
same cluster is running in this process is `409`. One `cluster-refreshed` line per call, with no credential.
```

```markdown
same cluster is running in this process is `409`. One `cluster-refreshed` line per call, with no credential.

`POST /api/clusterconfigs/{name}/rejoin` (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`) with `{"username": "…",
"password": "…"}` → `200 {"outcome": "rejoined", "message": "Signed in to east as alice, who may update
clusterrolebindings there; …", "at": "2026-09-27T14:05:40Z"}`. A cluster administrator's **own** username and
password, for ONE login to the remote: the dashboard logs in as that person, asks the remote with that login's own
token whether the person may `update clusterrolebindings` there (the host's `visibility.clusterAdminSar` question; a
no reads and writes nothing), reads `group-sync-operator/group-sync-dashboard-cluster-poller-token`, signs the login
out, and writes the token to `gsd-cluster-<name>` with `token-source: rejoin`, `rejoined-by`, `rejoin-account` and
`rejoined-at` — never `lookup-account`. **The password is never stored, logged or echoed.** It is sent at most once
per request and never retried, and a password the directory answered is not sent again by this process while it is
the same password (the poller's credential gate, #315). `outcome` is `rejoined` or a refusal's code: `login-refused`,
`login-failed`, `not-cluster-admin`, `access-review-failed`, `sa-token-secret-missing`, `sa-token-unreadable`,
`sa-token-invalidated`, `lookup-write-failed`. Refused before anything is sent: `403` below the cluster-admin tier
or without an identity; `404` for an unknown or retired name, and with writes off (the route does not exist); `409
not-rejoinable` where `rejoinable` is false; `409` while another Rejoin is in flight in this process, or when the
process runs no poller; `422` for a body that is not exactly `{username, password}` as strings (an unknown key is named,
a value never), `rejoin-username-invalid` (outside the bootstrap grammar, or ending in a newline),
`rejoin-fleet-account` (a name a fleet path logs in as, compared stripped and casefolded), `rejoin-password-missing`
and `rejoin-password-invalid` (a control character, which RFC 7617 forbids, or an unpaired surrogate, which UTF-8
cannot carry). A success wakes discovery. One `cluster-rejoin-review` line carries the remote's answer, then
`cluster-rejoined` or `cluster-rejoin-failed`; each names the person and the account and carries no credential.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| Status | D1, D2 (`remote-sar` + `same-as-host`, the standard for every way a cluster is joined) and D5 built in SPEC_D2b (#338), the remote failure hold with them; D3 needs no code; D6's lab policy applied there; D4's fail-closed fallback built, its named finding recommended, not built; D7 directed, not built (#322); D8 open (§8) |
```

```markdown
| Status | D1, D2 (`remote-sar` + `same-as-host`, the standard for every way a cluster is joined) and D5 built in SPEC_D2b (#338), the remote failure hold with them; D3 needs no code; D6's lab policy applied there; D4's fail-closed fallback built, its named finding recommended, not built; D7 built (#322); D8 directed 2026-09-26 and built with Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`) |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
is joined. It also defines who may join or rejoin a cluster (§7): D7 (directed, not built) makes a person's join or
Rejoin a cluster-admin action checked on the host. Today the tab's writes ask only `create secrets` in the dashboard's
namespace, and the automatic lookup is started by configuration, not by a person.
```

```markdown
is joined. It also defines who may join or rejoin a cluster (§7): D7 (built with #322) makes a person's join or Rejoin a
cluster-admin action checked on the host, and D8 (built with #316) has the remote confirm it with the person's own
login. The automatic lookup is started by configuration, not by a person.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
exchange started by a person with their own credentials. It is not built: the tab accepts only a pasted bearer token
and refuses a username and password with `oauth-exchange-not-built`
(`local-development/gsd/clusterconfig/writer.py#validate`).
```

```markdown
exchange started by a person with their own credentials (`local-development/gsd/rejoin.py#rejoin`,
`docs/specs/SPEC_D4_cluster_rejoin.md`). The Add form still takes only a pasted bearer token: a username and password
there is refused with `oauth-exchange-not-built` (`local-development/gsd/clusterconfig/writer.py#validate`).
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
not cluster admin (§5). A person's Rejoin would be gated twice: on the host before the password exists (D7), and on
the remote once it does (D8). Dashed boxes are proposed and not built.*
```

```markdown
not cluster admin (§5). A person's Rejoin is gated twice: on the host before the password exists (D7), and on
the remote once it does (D8).*
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
 HOST    Rejoin (#316, not built), a person on the tab
```

```markdown
 HOST    Rejoin (#316), a person on the tab
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
 REMOTE  2 (D8, proposed, Rejoin only) SelfSubjectAccessReview: update clusterrolebindings?
             no -> refuse and revoke; the fleet account skips this step
```

```markdown
 REMOTE  2 (D8, Rejoin only) SelfSubjectAccessReview: update clusterrolebindings?
             the answer is logged; no -> nothing is read or written, and the login is revoked;
             the fleet account skips this step
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| Rejoin (#316) | not built | `clusterAdminSar`, then D8 on the remote | the host, then the remote | the person's own username and password, once, never stored |
```

```markdown
| Rejoin (#316) | `clusterAdminSar` on the host, then D8 on the remote | unchanged | the host, then the remote | the person's own username and password, once, never stored |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| **D8** | Confirm a Rejoin credential on the remote | none; or one `SelfSubjectAccessReview` with the login's own token (`update clusterrolebindings`, #322's cluster-admin question), refusing and revoking on no | **Open**, recommended for Rejoin only. It enforces D7's rule with the remote's own RBAC once a credential exists and needs no new grant (`system:basic-user`). The login's token is `user:full` (`docs/DESIGN_session_and_signout.md`), so the review answers with the person's own RBAC and groups, with no group lookup. It refuses a namespace admin of `group-sync-operator`, whom the `admin` role lets read the token Secret (§5). Like #322's, the question is a threshold: `cluster-admin` passes it, and so would any other role that grants the verb. The fleet account skips it. |
```

```markdown
| **D8** | Confirm a Rejoin credential on the remote | none; or one `SelfSubjectAccessReview` with the login's own token (`update clusterrolebindings`, #322's cluster-admin question), refusing and revoking on no | **Directed** (the operator, 2026-09-26: *"we log the response from the remote cluster but don't make things very complicated. We can check if the person joining the cluster is also a cluster admin on the remote cluster."*), in its simple form, and built with Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`): one review, the remote's answer logged, a no reads and writes nothing. It enforces D7's rule with the remote's own RBAC once a credential exists and needs no new grant (`system:basic-user`). The login's token is `user:full` (`docs/DESIGN_session_and_signout.md`), so the review answers with the person's own RBAC and groups, with no group lookup. It refuses a namespace admin of `group-sync-operator`, whom the `admin` role lets read the token Secret (§5). Like #322's, the question is a threshold: `cluster-admin` passes it, and so would any other role that grants the verb. The fleet account skips it. |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
`self-only` and `hidden` clusters nothing changes. #322's Rejoin row is D7: the host will decide who may start one,
and D8, if accepted, lets the remote refuse a credential that does not pass the same question there.
```

```markdown
`self-only` and `hidden` clusters nothing changes. #322's Rejoin row is D7: the host decides who may start one,
and D8 lets the remote refuse a credential that does not pass the same question there (#316).
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
      fleet account does it, automatically. Rejoin (#316) is the same exchange started by a person.</p>
    <figure>
      <div class="fig-scroll">
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the account was already refused, by any target, is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

```html
      fleet account does it automatically, and Rejoin (#316) is the same exchange started by a person.</p>
    <figure>
      <div class="fig-scroll">
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the account was already refused, by any target, is not sent again. Rejoin starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there and logs the answer, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
              <rect x="260" y="64" width="200" height="62" rx="6" stroke="currentColor" stroke-dasharray="5 4"/>
              <rect x="30" y="152" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="260" y="240" width="200" height="62" rx="6" stroke="currentColor" stroke-dasharray="5 4"/>
            </g>
            <rect x="260" y="152" width="200" height="62" rx="8" fill="var(--host-wash)" stroke="var(--host)" stroke-width="1.5" stroke-dasharray="5 4"/>
            <text x="130" y="86" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-weight="600">saTokenLookup: true</text>
            <text x="130" y="103" text-anchor="middle">a stanza or Secret · automatic</text>
            <text x="130" y="119" text-anchor="middle" fill="var(--muted)">stops first if writes are off</text>
            <text x="360" y="86" text-anchor="middle" font-weight="600">Rejoin (#316, not built)</text>
```

```html
              <rect x="260" y="64" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="152" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="260" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
            </g>
            <rect x="260" y="152" width="200" height="62" rx="8" fill="var(--host-wash)" stroke="var(--host)" stroke-width="1.5"/>
            <text x="130" y="86" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-weight="600">saTokenLookup: true</text>
            <text x="130" y="103" text-anchor="middle">a stanza or Secret · automatic</text>
            <text x="130" y="119" text-anchor="middle" fill="var(--muted)">stops first if writes are off</text>
            <text x="360" y="86" text-anchor="middle" font-weight="600">Rejoin (#316)</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
            <rect x="530" y="388" width="420" height="62" rx="6" fill="none" stroke="var(--remote)" stroke-width="1.2" stroke-dasharray="5 4"/>
            <text x="546" y="410" font-weight="600" fill="var(--remote)">② proposed (D8) · Rejoin only</text>
```

```html
            <rect x="530" y="388" width="420" height="62" rx="6" fill="none" stroke="var(--remote)" stroke-width="1.2"/>
            <text x="546" y="410" font-weight="600" fill="var(--remote)">② D8 · Rejoin only · the answer is logged</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
            <text x="30" y="852" fill="var(--host)" font-weight="600">Dashed = proposed, not built: Rejoin (#316), clusterAdminSar (#322, D7), the remote's confirmation (D8).</text>
```

```html
            <text x="30" y="852" fill="var(--host)" font-weight="600">Built: Rejoin (#316), its host gate clusterAdminSar (#322, D7) and the remote's check (D8).</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
        fleet account is configuration, not a person, and holds no cluster-admin grant (measured on the lab). A person's Rejoin would be gated twice: by the
```

```html
        fleet account is configuration, not a person, and holds no cluster-admin grant (measured on the lab). A person's Rejoin is gated twice: by the
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
          <tr><td>Rejoin (#316)</td><td>not built</td><td><code>clusterAdminSar</code>, then D8 on the remote</td><td>host, then remote</td><td>the person's own username and password, once, never stored</td></tr>
```

```html
          <tr><td>Rejoin (#316)</td><td><code>clusterAdminSar</code>, then D8 on the remote</td><td>unchanged</td><td>host, then remote</td><td>the person's own username and password, once, never stored</td></tr>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
        <div class="rec"><strong>Recommend: yes, for Rejoin only.</strong> It enforces D7's rule on the remote with
          the remote's own RBAC, after the join credential exists.</div>
```

```html
        <div class="rec"><strong>Directed, and built with Rejoin (#316)</strong> (the operator, 2026-09-26): <em>"we log the
          response from the remote cluster but don't make things very complicated."</em> One review, its answer logged;
          a no reads and writes nothing.</div>
```

<!-- block: docs/specs/SPEC_D3_cluster_refresh.md | edit -->
```markdown
  discovery to close that gap: it forces nothing (§3). A rotation made in the tab wakes discovery itself.
```

```markdown
  discovery to close that gap: it forces nothing (§3). A rotation made in the tab wakes discovery itself.
- **#316 builds the next step §4 names (`docs/specs/SPEC_D4_cluster_rejoin.md`).** On `auth_failed` the line now
  says to use Rejoin, and the card draws its **Rejoin…** control where the row is `rejoinable`; §4's "Rejoin (#316),
  not built yet" and "No Rejoin control is drawn until Rejoin exists" describe the page before #316. The route, the
  probe, the words and the four states are unchanged.
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased
```

```markdown
## Unreleased

- **Rejoin: an administrator signs in to a remote cluster as themselves, once, and the dashboard fetches a fresh
  poller token (#316, Epic D #384, `docs/specs/SPEC_D4_cluster_rejoin.md`).** When Refresh answers `auth_failed`, or
  `pending` for a token that was never fetched, a Secret-sourced card or a `saTokenLookup` stanza offers
  **Rejoin…**. Its dialog takes the administrator's own username and password for that cluster. The new
  `POST /api/clusterconfigs/{name}/rejoin` logs in once as that person and asks the remote, with that login's own
  token, whether the person may `update clusterrolebindings` there (D8: the answer is logged, and a no reads and
  writes nothing). It reads the poller's token Secret, signs the login out, and writes `gsd-cluster-<name>` with
  `token-source: rejoin`, `rejoined-by`, `rejoin-account` and `rejoined-at`. **The password is used for that one
  login and is never stored, logged or echoed.** One press presents it at most once, nothing is retried, and a
  password the directory answered is not sent again by that pod while it is the same password (the poller's
  credential gate, #315). The fleet account's name is refused. The route sits in the writes carve-out, so a default
  install has no Rejoin. `GET /api/clusterconfigs` rows gain `rejoinable`, and discovery counts a Rejoin over a
  `saTokenLookup` stanza as that stanza's own Secret. `charts/group-sync-dashboard/RUNBOOK.md` walks the repair:
  Refresh, then Rejoin, then the manual fallback. No RBAC change.
```

