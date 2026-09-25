# SPEC S4a — the fleet login session: obtain, expire, retry, revoke (#283)

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S4 designed the retrieval; this is its step A, the first code in the tree that can log in |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step A, the issue's own label S3b-A) |
| Version on release | no version change (a module nothing calls yet; the release that first calls it bumps) |
| Issue | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) |
| Status | merged |
| Source | OB1's implementation specification of 2026-09-21, written before the code from the business owner's brief, `docs/specs/SPEC_S4_token_retrieval.md` §3, §3.1, §5, §6, §8 and §9, and the mechanism re-measured on the reference cluster |

## How to read this spec

"Measured" is what the reference cluster answered, with the command. "Design" is the code, file by
file, in fenced blocks that are applied **verbatim**: a whole-file block replaces or creates the file
it names, an edit block's "Old text" is replaced by its "New text" and must match exactly once. The
implementation is applied from these blocks by a script and never typed from memory; a block found
wrong during implementation is corrected **here first**, with the reason under "Orchestrator's notes",
and only then applied. The board for the programme this belongs to is issue #288.

The parent design is `docs/specs/SPEC_S4_token_retrieval.md`. Its §9 fixes what #283 owns — *the
SESSION, not just the login*: log in, read the expiry, apply the retry policy, and **log out** — and
§5, §6 and §8 fix the retry policy and the log vocabulary this step must ship with. The modes it
serves are `docs/specs/SPEC_S3_connection_modes.md` §3; the account is §3.1 there.

## Orchestrator's notes

- **Issue #283's "precondition" section is superseded by SPEC_S4 §10.1, and this spec records the
  correction.** The issue says the fleet account is probably not loginable and prescribes an
  `ldapsearch -s base uid memberOf` against the bind DN. That is refuted by the target's own record.
  Measured on the reference cluster, 2026-09-21:

  ```
  $ oc get user ocp-oauth-bind-serviceid -o jsonpath='{.metadata.name} created={.metadata.creationTimestamp} identities={.identities}'
  ocp-oauth-bind-serviceid created=2026-09-19T00:48:44Z
  identities=["ldap-local:Y249b2NwLW9hdXRoLWJpbmQtc2VydmljZWlkLG91PVRydXN0ZWRBcHBsaWNhdGlvbnMsZGM9ZXBoaWNvMnJlYWwsZGM9Y29t"]
  ```

  The Identity suffix decodes to `cn=ocp-oauth-bind-serviceid,ou=TrustedApplications,dc=ephico2real,dc=com`
  (`gsd/auditlog.py#decode_identity_suffix`). OpenShift creates a `User` only on a **first successful
  login through an identity provider**, so the object's existence is the proof that the account
  authenticates. **The prescribed check is therefore `oc get user <name>` / `oc get identities` on the
  TARGET cluster — no bind, no `ldapsearch`.** The caution that stands is absolute: **loginability is
  never tested by attempting a login.** A lockout takes down the account the target authenticates
  every user with. Nothing in this spec, its tests or its verification logs in as the fleet account;
  every live measurement below used the reference cluster's htpasswd `developer` account, which no
  directory sits behind.

- **The id is `S4a`, and the index regex admits a step letter.** The issue is a step of S4's design,
  not a sibling of it, and `SPEC_S4_token_retrieval.md` already holds the `S4` slot on the index (its
  row and count landed with PR #287). `test_specs_index.py`'s row pattern was `[A-Z]\d`; it becomes
  `[A-Z]\d[a-z]?`, the count moves to twenty, and the S-batch rule (`{230, 283}`) is unchanged because
  this row carries #283 too. The alternative — burning `S5` for a step — would have read as a fifth
  design.

- **`login-refused` is the refusal line's `outcome=` and is not yet in `FINDING_CODES`.** SPEC_S1
  §S1.2 makes the finding set a page contract — a new code is a page change — and #283 has no page:
  nothing on the tab calls the login until #284's lookup runs and surfaces its findings. The precedent
  is `cert-verify-failed`, which SPEC_S3 §9.2 records as a log-only outcome today. #284 adds the code
  to the closed set and the tab's sentence for it in the PR that first renders it.

- **A 401 without a Basic challenge is not recorded as a refusal — and is not retried either.**
  SPEC_S4 §6 says such a 401 "is a client fault … and must not be recorded as a refusal". This spec
  keeps that and adds the half §6 leaves open: the login does not retry it. The retry policy is keyed
  on whether a second attempt can bind with a wrong password, and a 401 whose cause cannot be read is
  exactly the answer a variant server might give a wrong password without the challenge header.
  Misclassifying a client fault as "stop and tell the operator" costs a look; misclassifying a refusal
  as retryable is the lockout walk. The line says which it was (`outcome=unreachable`, the challenge
  quoted as `<absent>`), so the operator is not sent to rotate a password that was never evaluated.

- **§6's "a missing `X-CSRF-Token` returns 401" did not reproduce.** Measured 2026-09-21 with basic
  auth sent pre-emptively and no `X-CSRF-Token` header: the reference cluster answered **302 with a
  token**, not 401. The header is still sent — it is what `oc` sends — and nothing here relies on
  the claim either way. Recorded because the design's rule for "401 without the challenge" was
  motivated by that example, and the rule stands on its own reasoning (above) rather than on the
  example.

- **The ceiling is five attempts, waiting 1, 2, 4 and 8 seconds.** SPEC_S4 §6 says "a stated ceiling"
  and the ASCII flow in SPEC_S3 §9.3.4 shows `1s→2s→4s→8s…`; neither fixes the count. Five is the
  smallest number that survives a restarting OAuth pod (measured rollouts on the lab take under a
  minute) without turning a down target into minutes of blocked lookup: 15 s of backoff plus up to
  five request timeouts. It is a `RetryPolicy` value, stated in the log as `attempt=<n>/5`, and #285
  may tune it with a measurement; nothing else reads it.

- **No chart change, no application version bump.** The chart's grant to read the fleet password
  (0.49.0, #282) is what the caller of this module will use; the module itself takes the password as
  a value. `charts/group-sync-dashboard/values.yaml`'s "Until S3b lands, a mode stanza is … not polled"
  stays true — nothing calls the login — and `CREDENTIAL_PENDING_REASONS` (`gsd/config.py`) keeps its
  wording for the same reason. The release that first calls this module carries its bump.

- **Two live artefacts, both counted.** The measurement in §2 minted **two** tokens for `developer`
  (the login, and the CSRF probe) and revoked one through the API as the token's own user; the other
  was revoked as cluster-admin afterwards (`oc delete oauthaccesstoken sha256~00H6…`), and the count
  of `developer`/`openshift-challenging-client` objects on the lab is back to **0**. Said here because
  #286 is about litter and this spec must not add to it.

- **Deviations found in implementation.** One, on the first apply (2026-09-21): §3.9's "Old text"
  for `docs/CHANGELOG.md` quoted the 0.49.0 bullet as ending at `#248).**` on its own line, and the
  apply script refused it (`old text matches 0 times`) because that bullet is one long line. The block
  was corrected to anchor on the `## Unreleased` heading alone — the one line that is unique and whole
  — and the new bullet is inserted after it, ahead of the 0.49.0 bullet, which is left untouched. No
  code block was affected; every Python block applied verbatim on the first pass.

  Two more on the first run of §3.5 (both in the TEST file; `gsd/fleetlogin.py` was not touched and
  behaved as specified — the captured lines are in the pull request): (a) the backoff test asserted
  `"gave_up" not in <retried line>`, which the module's own `action=` text defeats by *naming* the
  `gave_up` line a reader should wait for; the assertion is on the field syntax `gave_up=` now, in
  that test and in the refusal test, which is what "the field is absent" means. (b) the scope test
  grepped the module's source for `sched` and matched the docstring's "schedules anything" while
  saying the module does no such thing; it parses the AST now and asserts the imports and the client
  methods called, which is what "no timer, no write" is a fact of.

  A third, from the first LIVE run (2026-09-21), and this one corrected a *measurement* as well as a
  block: §2 had read the second DELETE's 404 as "the token no longer authenticates", and §3.6
  asserted a 401 on the first request after the session closed. The reference cluster answered that
  request **200**. Re-measured once a second: the object was absent from `oc get oauthaccesstokens`
  from the moment the session closed (count 0 → 1 → 0, the name present during and gone after), and
  the revoked token went on authenticating for **121 s** — the API server's token authenticator
  cache — then 401. §2 now records both numbers, §3.2's `_revoke` docstring states the window, and
  §3.6 waits for the token's death (up to `GSD_LIVE_LOGIN_DEAD_WAIT`, default 180 s) while the count
  remains the proof of the logout. The module's behaviour did not change.

- **Review of PR #289 (Codex gpt-5.6-sol xhigh, Cursor Grok 4.6, OB1-lite; decisions by the business
  owner; record in `docs/REVIEW_S4a.md`).** Six findings, each applied to the blocks above BEFORE the
  code was regenerated from them:
  1. *P0-1, all three seats:* `expires_in=999999999999999` passed `int()` and `<= 0`, then
     `expires_at_iso` raised `OverflowError` — not a `LoginError` — before `self.session` was set, so
     `__exit__` never revoked (Codex: `authorize_count 1 delete_count 0`). Two halves, not redundant:
     `MAX_EXPIRES_IN = 2**31 - 1` (`OAuthClient.accessTokenMaxAgeSeconds` is an int32) bounds the value
     at the source, and `_login` wraps everything from "the token exists" to "the session is returned"
     in a `BaseException` guard that revokes and re-raises. `_authorize` revokes before it raises, so the
     guard begins only once it has returned and no token is revoked twice — the tests assert the DELETE
     count is exactly one.
  2. *P0-2, all three seats; the STRICT rule adopted:* every non-302 on the authorize step, a 302
     without a token, and every transport failure after the request was written are terminal; only
     `ConnectError`/`ConnectTimeout` are retried. OB1-lite's narrower set (keep 429/502/503/504
     retryable) was **rejected**: a 504 or 502 means the upstream received the request. §3.1's table
     and the module docstring carry the upstream reasoning (`ldap.go` codes 48/49 → 401, everything
     else → 500 via `HandleError`, a locked account's code 19 included). `_discover` is unchanged.
  3. *P1-1, Codex alone:* a `401` on the revoke was "already gone". Only a `404` is gone; a `401` is
     now `fleet-logout-failed phase=credential outcome=auth_failed` in its own words, and the log
     distinguishes `revoked`, `already-gone` and `revoke refused`.
  4. *P1-2, all three seats:* three raise sites quoted a remote-controlled field unscrubbed (the
     endpoint's netloc, the `Www-Authenticate` challenge, the raw `expires_in`), so `str(exc)` — which
     #284 puts on the page — could carry a password the log had redacted. All three scrubbed; an
     endpoint carrying userinfo is refused outright; the pin plants the password in every
     remote-controlled field (body, challenge, `Location` error query, discovery userinfo, `expires_in`,
     transport text) and asserts on the nine exceptions as well as the log.
  5. *P2-1, Cursor and OB1-lite:* the object-name test recomputed the formula it tested. It pins the
     literal `sha256~testsecret123 → sha256~AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY`, derived with
     `openssl` (re-run by OB1: identical) and confirmed by the owner against a live object.
  6. *P2-2, Codex:* an injected non-UTC clock produced a `Z`-suffixed string that was not UTC. `_as_utc`
     normalises an aware reading and refuses a naive one before anything is minted; `FleetSession`
     refuses a naive `obtained_at`; `expires_at_iso` formats through `astimezone(UTC)`.

  **Tests inverted, because they asserted the defect:**
  `test_a_302_without_a_token_is_not_a_session_and_is_retried_within_the_ceiling` (2 binds) →
  `…_is_terminal` (1 bind); `test_an_unreachable_target_is_retried_with_exponential_backoff` lost its
  `read-timeout` and `http-503` cases (each sent the password three times) and became
  `test_a_target_that_never_took_the_request_is_retried_with_exponential_backoff` over
  `ConnectError`/`ConnectTimeout`/TLS, with the terminal answers under
  `test_once_the_password_is_on_the_wire_every_answer_is_terminal` (eleven cases, one bind each);
  `test_an_already_gone_token_is_not_a_failure` lost its `401` case, now
  `test_a_401_on_the_revoke_is_a_failure_not_already_gone`;
  `test_the_object_name_is_the_measured_derivation` pins the literal instead of the formula.

- **Confirmation pass on `28d4bec` (Codex with a harness, Cursor reading; Codex's measured result wins
  where they disagree). Seven residual defects, one of them introduced by P1-2.** Each applied to the
  blocks first:
  1. *R2-1 (P0), Codex:* `urlsplit()` raised `ValueError: Invalid IPv6 URL` on a hostile `Location`
     before the token was read (`authorize=1 DELETE=0`), and the P0-1 guard began only after
     `_authorize` returned. `_authorize` now returns the response; `_token_from` splits the header on
     its first `#` and parses the fragment alone — the rest of the URL is never validated — and the
     guard in `_login` begins the moment the token is bound, with `_expiry_from`, the session and the
     success line inside it. The retry loop's typed stops (401, non-302, no token) are unchanged.
  2. *R2-2 (P1), Codex:* a revoke that raised inside the guard replaced the body's exception. `_revoke_quietly`
     surfaces anything `_revoke` raises as a `fleet-logout-failed` line and answers False; the guard and
     `__exit__` both go through it.
  3. *R2-3 (P1), Codex:* a DELETE answering 500 was reported as revoked. **The invariant is restated**
     — *revocation is attempted exactly once, and a failure is surfaced, never swallowed* — in the
     module docstring, §3.1's table and every assertion's wording; `_revoke` returns whether the target
     said gone (200/404 only), `FleetLogin.revoked` carries it to the caller, and the `expires_in`
     stop's message no longer claims "the token was revoked".
  4. *R2-4 (P1), Codex:* a three-character password passed both shared floors (`events.redact` 4,
     `kube.redact_text` 8). **The floors are not changed** — they keep ordinary short strings intact
     across every log in the codebase; `_scrub` redacts the credential this class holds regardless of
     length, after the two helpers, longest first.
  5. *R2-5 (P1), Codex:* the `ValueError` from parsing a hostile `authorization_endpoint` reached the
     caller unscrubbed, carrying userinfo. Caught in `_discover`, scrubbed, a `connect` stop.
  6. *R2-6 (P1), Cursor:* `issuer` is a remote field that reached the session and the `oauth=` field
     unscrubbed and was never planted. Scrubbed in `_discover`; the pin plants the password in it and
     asserts on `session.issuer` and the log.
  7. *R2-7 (P2), Codex — a regression from P1-2:* the challenge was scrubbed before it was classified,
     so a password literally `Basic` turned a refusal into `unreachable`. The raw header decides
     `is_basic`; only the quoted copy is scrubbed.
  Also, per Codex: `test_a_token_is_never_abandoned…` now raises from inside the interval between the
  response and the session as well as from the success line. Nothing shared (`events.redact`,
  `kube.redact_text`) was changed.

  *Found while applying R2-1 (measured, 2026-09-21):* the first test used `https://[::1/…`, and httpx
  refused that header itself — `RemoteProtocolError: Invalid URL in location header` from
  `_send_handling_redirects`, which builds the redirect request before consulting
  `follow_redirects` — so the 302 never reached this module. The measured case Codex hit is
  `https://example.com]/…` (also `https://a[b/…`): delivered as a 302, `urlsplit` raises. The test uses
  those; the docstring records the httpx limit beside the read timeout as a token this process may
  never see. `test_a_token_without_a_usable_expiry…` asserts the restated wording ("attempted once")
  instead of "revoked".

- **A gap in what the suite could prove, closed hermetically (the business owner, after the
  confirmation pass).** Both reviewers raised "API CA ≠ ingress CA" as a plausible risk for the
  first non-CRC cluster, and the owner measured why no run had ever caught it: the reference lab is
  structurally blind to it (§2.1 — the six-certificate listing, re-measured by OB1 from the poller
  SA's bundle, includes the ingress leaf and CA). `TestTheSplitCATheLabCannotShow` generates two CAs
  with `openssl` under `tmp_path` (with `basicConstraints`/`keyUsage`, so the rejection is the
  real-world `unable to get local issuer certificate`), runs two loopback TLS servers, and asserts
  in the owner's order: the credential never reached the OAuth host; discovery succeeded first;
  `phase=tls outcome=unreachable retryable=True`; no password in `str(exc)` or the log; the
  `gave_up` action names the ingress CA — with a both-CAs control that reaches the host once and
  stops on the fixture's token-less 302. `cryptography` is not a dependency of this project, so the
  fixture shells out to `openssl` and skips without it. The configuration contract that closes the
  gap is #284's (the owner posted the measurement there); nothing of it is implemented here.
  *Amended (the owner, 2026-09-22):* a CI log at `-q` cannot show whether the two tests ran or
  skipped, and the local/CI counts (4650/16 vs 4652/13) reconciled under both hypotheses. So the skip
  is a developer-machine courtesy only: under `CI` a missing `openssl` **fails** the tests with a
  message saying the proof may never be skipped there — the suite's existing convention for a tool
  a proof depends on (`test_chart_grafana_dashboard.py`, promtool), matched rather than a new marker.
  `cryptography` stays out (a dependency added to avoid a shell-out that works, on runners and Macs
  that all carry `openssl`). The servers run on daemon threads and are shut down in the fixture's
  `finally`; a bind failure on the second server closes the first; `handle_error` is consulted only
  for an exception while handling an accepted connection, so it cannot hide a bind failure.

- **Third pass on the restructured control flow (Codex, harness-driven; record in
  `docs/REVIEW_S4a.md`). Four findings; one is a REVERSAL OF AN ORCHESTRATOR DECISION.**
  1. *R3-1 (P0):* the guard was still one step too late — an interruption inside `_token_from` after
     the token was bound measured `authorize=1 DELETE=0`, the third time "the moment the token is
     bound" moved with a refactor. **Made structural rather than moved:** the guard is anchored on the
     response and re-reads the token off its header (`_token_in`, pure and total) on any failure, so
     there is no line between "the token exists in this process" and "an exception here revokes it",
     and nothing inside the guard revokes (attempted exactly once; the expiry boundaries `0`, `-1`,
     non-numeric, `MAX+1`, `1`, `MAX` unchanged).
  2. *R3-2 (P1):* `revoked` was recorded only on exit and a `fleet-logout` line that failed to write
     after a 200 read as a failed revoke. `_delete_token` is the wire; `_revoke` records `revoked` from
     the target's answer at every site before the line, and a line that fails to write falls back to
     the stdlib logger.
  3. *R3-3 (P1) — the orchestrator's round-2 call was wrong and is retracted:* "make `_scrub` redact
     the credential regardless of length" was measured to mangle a legitimate issuer (`app` →
     `…<redacted>s.example.com`) and to unclassify a TLS failure (`certificate` → `phase=connect`).
     Scoped, not reverted: classify on the raw value (the challenge, the transport message) and scrub
     the copy; never substring-redact a structured value (the issuer, the host) — userinfo is stripped
     structurally by `_without_userinfo`; length-agnostic redaction only for free remote text.
  4. *R3-4 (P2):* the "attempted" rewording had flattened the outcomes; every revoke test asserts
     `revoked` per status (200/404 True, 500/401 False), the expiry-stop path included.
  *Found while applying R3-3 (measured):* the first version of the classification-word test used
  `[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed`, and passed on the OLD module — the
  case-sensitive scrub left the uppercase marker intact, so `is_verify_failure` still matched. The
  test carries the lowercase phrase alone (`certificate verify failed (_ssl.c:1010)`), which is
  Codex's measured case, and fails before the fix.

- **Final scoped pass (round five; the reviewer could execute nothing, every claim verified by the
  business owner and re-measured by OB1; record in `docs/REVIEW_S4a.md`).** F2 passed: `revoked` is
  truthful from every site and the structural guard covers the previous window; the guard's shape is
  unchanged. Four claims:
  1. *R5-1 (P0), real:* httpx comma-joins repeated `Location` headers in `get`, so the first-`#` split
     never saw a token carried by the second header — a minted token the guard could not NAME (the
     structural fix itself held). `_fragments_of` reads every value (`get_list`) and every `#`-segment
     of each — which also covers a proxy that joined the duplicates into one value, the case
     `get_list` alone would miss — and `_fragment_of` picks the first fragment carrying a token so
     the session path and the guard cannot disagree.
  2. *R5-2 (P2):* `_authorize`'s `return` moved into its protected region (`try/except/else`); the
     residual — the store into `_login`'s local after the call returns — is one bytecode and inherent
     to any call boundary, stated in the code rather than claimed closed.
  3. *R5-3 (P2):* nothing is computed before the wire that the wire does not need — the name is
     derived once in `_delete_token` and returned on the answer; the fallback logger is wrapped and
     `_text_of` guards a `str(exc)` that raises, so cleanup can never raise.
  4. *R5-4 (P3):* `_without_userinfo` honours its contract — no hostname, or a port that does not
     parse, falls back to the endpoint's host.
  **Refuted and not implemented:** "an enormous fragment can make `parse_qs` raise during cleanup" —
  the owner measured 200 000 fields without a raise, OB1 the same; `parse_qs` enforces a field limit
  only when `max_num_fields` is passed. No guard, no test.

  **R5-1's shape retracted by the owner after research, and this spec follows the research.** The
  first fix (commit `9a40691`: read every `Location` value and every `#`-segment, pick the first
  fragment carrying a token) was error recovery from a malformed construct. RFC 9110 §5.5 classifies
  `Location` as a **singleton field** — more than one is malformed, not two candidates — and says a
  "systems control client might consider any form of error recovery to be dangerous"; and "the first
  one carrying a token" is a rule the target controls (`Location: …#access_token=ATTACKER_CHOSEN`
  first, the real one second). Replaced by less code: `get_list` is used to **count**, more than one
  `Location` is a typed terminal stop and never a session, what the response carried is revoked
  best-effort with `best_effort=true` on the line and `revoked` truthful (None when nothing could be
  named — #286's litter, said in the message), and exactly one `Location` takes the simple path
  (first `#`, `parse_qs`). A value a proxy joined itself is one malformed value, not recovered. No
  evidence exists that a legitimate OpenShift OAuth server sends two `Location` headers — the
  measured flow sends one. `_fragments_of` and `_token_in` are deleted; `_minted_by` returns what the
  guard needs and nothing more. The implicit-flow note (RFC 9700 / OAuth 2.1 deprecation; why its
  threats do not apply here) is in the module docstring and §2.2.

## 1. Scope — login only

Obtain a session from a target cluster as the fleet account, read its expiry, apply the retry policy,
and log out. **Nothing is stored, nothing is written to any Secret, nothing is scheduled.** The read
and the write are #284; the daily ping, the `self-login` renewal and the per-credential suspension
across clusters are #285; the litter already on the lab is #286. The module this spec adds is a
library nothing in the tree calls yet — `credential_pending` still gates every mode stanza out of the
poll — and its only outbound writes are the revoke of the token it minted itself.

The business owner's eight requirements, numbered as the tests name them:

| R | requirement | where it is proven |
|---|---|---|
| R1 | login only: no Secret write, no timer | `TestScopeIsLoginOnly` |
| R2 | a session is a context manager and logs out on every exit path | `TestTheSessionLogsOut` |
| R3 | a failure before the password is on the wire backs off to a stated ceiling; once it is sent, every answer is terminal and `AUTH_FAILED` is never retried (call count exactly 1) | `TestTheRetryPolicy` |
| R4 | the expiry is an absolute instant from the target's own `expires_in`, never a hard-coded lifetime | `TestTheExpiryIsAnAbsoluteInstant` |
| R5 | the token is read off the `Location` fragment; the redirect is not followed | `TestTheTokenIsReadOffTheLocationFragment` |
| R6 | the OAuth host is discovered, never derived from the API URL | `TestTheOAuthHostIsDiscovered` |
| R7 | TLS verification is the cluster's `tls_mode`, the poller's own decision | `TestTLSFollowsTheClustersMode` |
| R8 | `attempt=`, `retry_in=`, `gave_up=` join #245's vocabulary, no new phase, the redaction pin covers every new path | `TestTheLogVocabulary`, `TestTheRedactionPin` |

## 2. Measured on the reference cluster (2026-09-21)

All of it with the htpasswd `developer` account (provider `developer:HTPasswd`; the cluster's other
provider is `ldap-local:LDAP`), verified against the poller ServiceAccount's `ca.crt` bundle (six
certificates, the ingress CA among them — SPEC_S3 §6), with `httpx` and `follow_redirects=False`:

```
GET https://api.crc.testing:6443/.well-known/oauth-authorization-server
  -> 200  issuer=https://oauth-openshift.apps-crc.testing
          authorization_endpoint=https://oauth-openshift.apps-crc.testing/oauth/authorize

GET <authorization_endpoint>?client_id=openshift-challenging-client&response_type=token
    Authorization: Basic <developer:…>   X-CSRF-Token: 1
  -> 302  body 0 bytes  Www-Authenticate: (absent)
          Location: …/oauth/token/implicit#access_token=sha256~<43 chars>&expires_in=31536000&scope=user%3Afull&token_type=Bearer

name = "sha256~" + base64url( sha256( <the 43 chars after the prefix> ) ).rstrip("=")
  -> found on the server: True   userName=developer  clientName=openshift-challenging-client  expiresIn=31536000

DELETE https://api.crc.testing:6443/apis/oauth.openshift.io/v1/useroauthaccesstokens/<name>
    Authorization: Bearer <the token>
  -> 200  kind=OAuthAccessToken            (the object is gone from `oc get oauthaccesstokens`)
DELETE again with the same token
  -> 404                                   (the OBJECT is absent; the request itself still authenticated — below)

elapsed, discovery to second DELETE: 0.51 s

`oc get oauthaccesstokens` for developer / openshift-challenging-client, around one session:
  before 0   during 1 (the session's own name present)   after 0 (the name absent)
GET /apis/user.openshift.io/v1/users/~ with the revoked token, once a second after the session closed:
  -> 200 … 200, then 401 after 121 s       (the API server's token authenticator cache; the object was
                                            absent from the list the whole time)
```

Four facts the design rests on, each load-bearing:

1. **The OAuth host is on a different name from the API** (`oauth-openshift.apps-crc.testing` against
   `api.crc.testing:6443`) and the API server publishes it, unauthenticated, at the well-known path.
2. **The token and `expires_in` are in the `Location` fragment of a 302 with an empty body.** A client
   that follows the redirect loses them.
3. **`expires_in` is the target's own lifetime** — 31536000 s here (CRC's `oauth_cr.yaml` sets a
   year), 86400 s by OpenShift default, an hour on an estate that tightens it. It is read, never assumed.
4. **The object's name is derivable from the token, and a DELETE by that name with the token itself as
   bearer revokes it.** That is `oc logout`, and it is what the session's exit does. The object is gone
   the moment the DELETE answers; the token *itself* goes on authenticating for about two minutes from
   the API server's token cache (121 s measured). That is a fact for #285's "a 401 means re-authenticate"
   rule and for any test that probes the token — not litter, because nothing on the target names it.

The 401 shape of a refusal is **not** re-measured here — it would take a wrong password — and is
taken from SPEC_S4 §6: a bare `401` with `Www-Authenticate: Basic realm="openshift"` and an empty body.

### 2.2 The flow is the OAuth implicit grant — deprecated for browsers, and this is not a browser

`response_type=token` is the OAuth **implicit** grant, which RFC 9700 and OAuth 2.1 deprecate
(https://oauth.net/2/grant-types/implicit/), chiefly because a token in a URL fragment leaks through
browser history and the `Referer` header. Neither threat applies to this client: it is not a
browser, it never follows the redirect (`follow_redirects=False`), and the fragment never reaches a
page. The flow is not chosen here — OpenShift's CLI login path (`openshift-challenging-client`)
defines it — and this module's use of it avoids the reason it was deprecated. A future reader should
not "fix" it. Related and also from the standard: `Location` is a **singleton field** (RFC 9110
§5.5, https://www.rfc-editor.org/rfc/rfc9110.html), so a 302 carrying more than one is malformed,
and this is the "systems control client" for which the RFC says error recovery "might be dangerous"
— §3.1 refuses it rather than choosing among its values.

### 2.1 What the reference lab cannot show: an API CA that is not the ingress CA

A green run on CRC is **not** evidence that a customer's bundle is sufficient, and the reason is
structural. The poller ServiceAccount's `ca.crt` (`kube-root-ca.crt`) on the lab carries six
certificates, measured 2026-09-21 with `openssl x509 -noout -subject` over each:

```
c0  OU=openshift, CN=kube-apiserver-lb-signer
c1  OU=openshift, CN=kube-apiserver-localhost-signer
c2  OU=openshift, CN=kube-apiserver-service-network-signer
c3  CN=openshift-kube-apiserver-operator_localhost-recovery-serving-signer@1785325898
c4  CN=*.apps-crc.testing                       <- the ingress LEAF
c5  CN=ingress-operator@1785325954              <- the ingress CA
```

Two of the six are the ingress certificate and its CA, so on CRC a stanza carrying only the API's
bundle verifies the OAuth host too, and the split between the two can never occur there. That merge
is a CRC convenience, not normal OpenShift: on a cluster whose ingress is re-signed by an enterprise
PKI (this estate runs cert-manager with an enterprise CA and a Venafi TPP issuer) the API bundle will
not carry the ingress CA, and the login fails at the authorize step with
`unable to get local issuer certificate` — after discovery succeeded. **Two cautions for whoever
tests this by hand:** `curl` on a Mac gives a false pass (it falls back to the system keychain, which
trusts the CRC ingress CA), so TLS claims are verified with Python's `ssl`, which is what the
dashboard uses; and a CA made with a bare `openssl req -x509` lacks `basicConstraints`/`keyUsage`,
so the failure then reads `CA cert does not include key usage extension` — a fixture defect, not
the real rejection. `TestTheSplitCATheLabCannotShow` reproduces the split hermetically, two local
CAs and two loopback TLS servers, with a control that proves the fixture. The configuration contract
that closes the gap (which bundle a stanza must carry) is #284's, not this step's.

## 3. Design

### 3.1 The retry policy, stated

The line is **whether the password was on the wire**, not the kind of answer. Verified by the
business owner against upstream (review of #289): the oauth-server's LDAP authenticator answers
`401` only for LDAP result codes 48 and 49 (`pkg/authenticator/password/ldappassword/ldap.go`) and
**every** other directory result with `500` (`pkg/osinserver/defaults.go`, `HandleError`) — code 19,
`Exceeded password retry limit`, the answer of a directory that has *already locked* the account,
included. A "5xx is transient" rule retries hardest exactly when the account is locked. A `504`
means the upstream took too long having *received* the request; a `502` that it answered malformed
having received it; a read timeout that the request was written. The asymmetry decides it: a wrong
retry is an estate-wide outage; a missed retry is one delayed login #285's daily ping picks up.

| step | answer | outcome | phase | policy |
|---|---|---|---|---|
| discovery (no password sent) | socket refused, DNS, any timeout, a non-HTTP answer, non-200, non-JSON | `unreachable` | `connect` (`tls` for a refused certificate) | **retried**: bounded exponential backoff, `attempt=<n>/5`, waits 1, 2, 4, 8 s, then `gave_up=true` |
| discovery | the document names no `https` endpoint, or one carrying userinfo | `unreachable` | `connect` | **not retried** — the password would travel on that URL; a fact about the target |
| before either | a CA bundle this pod cannot load | `unreachable` | `tls` | **not retried** — local; no request is made |
| authorize, **before the bytes were written** | `httpx.ConnectError` (socket, DNS, the TLS handshake), `httpx.ConnectTimeout` | `unreachable` | `connect` / `tls` | **retried**, the same loop — the target cannot have bound |
| authorize, **the request was written** | `ReadTimeout`, `WriteError`, `ReadError`, `RemoteProtocolError`, any other transport failure | `unreachable` | `connect` | **terminal** — the target may have bound |
| authorize | **401 with a Basic challenge — the refusal** | **`auth_failed`** | `credential` | **never retried.** One line, `fleet-login-refused outcome=login-refused`, quoting the status line and the challenge. Stop. |
| authorize | 401 without a Basic challenge | `unreachable` | `credential` | **terminal**, and not called a refusal (notes) |
| authorize | any other non-302 — a 200, 403, 429, 5xx, a proxy page | `unreachable` | `credential` | **terminal** — the password was sent; a 500 may be a locked account |
| authorize | 302 carrying more than one `Location` | `unreachable` | `credential` | **terminal, malformed** (RFC 9110 §5.5: a singleton field) — never a session; what it carried is revoked best-effort (`best_effort=true` on the line), `revoked` True only if every attempt said gone, None if nothing could be named (#286's litter, said so) |
| authorize | 302 without `access_token` (or with `#error=`) | `unreachable` | `credential` | **terminal** — the bind happened and the grant failed after it |
| authorize | 302 with a token but `expires_in` missing, non-numeric, ≤ 0 or > 2³¹−1 (`MAX_EXPIRES_IN`) | `unreachable` | `credential` | **the token is revoked at once**, then **terminal** |
| after the 302 is in hand | anything that raises before the session is returned (`BaseException`) — inside the extraction, the lifetime check, the session, the success line | — | — | **revocation is attempted exactly once**, of the token the guard re-reads off the **response** (`_token_in`), so no binding can be too late; a failed revoke is surfaced (`fleet-logout-failed`), never swallowed and never reported as success; `revoked` records the target's answer from this site too; the original exception propagates unchanged |
| the exit | the target answers the DELETE 200 or 404 | — | — | `FleetLogin.revoked` True; anything else — a 401, a 5xx, a transport failure, the revoke raising — is a surfaced failure and `revoked` False |

The phases are #245's closed set, unchanged. `credential` and `connect` name the *place*; `tls` names
the trust store; `poll` is used once, for an API server that answered the **revoke** with an HTTP
refusal (the token was presented and the delete declined) — the poller's own definition of that phase.
A `401` on the revoke is `phase=credential outcome=auth_failed`: the DELETE was not authenticated and
that says nothing about the object, so it is a `fleet-logout-failed`, never "already gone" — only a
`404` is gone.

### 3.2 `local-development/gsd/fleetlogin.py` — new module

**File:** `local-development/gsd/fleetlogin.py` — whole file

```python
"""Log in to a target cluster as the fleet account, and log out again — the session of #283.

WHAT THIS IS. `oc login -u … -p …` is the OAuth challenging-client flow that `gsd/auditlog.py`
already documents as the `cli` login kind: one GET on the target's authorization endpoint with HTTP
basic auth, answered by a 302 whose `Location` FRAGMENT carries the access token and its lifetime.
This module performs that request as the fleet account (SPEC_S3 §3.1), hands the caller a session —
the token, the account it belongs to, and the ABSOLUTE INSTANT it expires — and revokes the token
when the caller is done, whatever happened in between. Nothing here stores anything, writes a Secret
or schedules anything: the lookup that stores is #284, the lifecycle is #285.

MEASURED ON THE REFERENCE CLUSTER, 2026-09-21, with the htpasswd `developer` account (the fleet
account is never logged in with to test anything — SPEC_S4a, orchestrator's notes):

  GET /.well-known/oauth-authorization-server          -> authorization_endpoint =
                                                           https://oauth-openshift.apps-crc.testing/oauth/authorize
  GET <that>?client_id=openshift-challenging-client&response_type=token   basic auth, X-CSRF-Token: 1
  -> 302, empty body, Location: …/oauth/token/implicit#access_token=sha256~…&expires_in=31536000&…
  DELETE /apis/oauth.openshift.io/v1/useroauthaccesstokens/<name>       as the token's own user -> 200

THREE THINGS THE FLOW DICTATES:

1. THE OAUTH HOST IS DISCOVERED, NEVER DERIVED. `oauth-openshift.apps-crc.testing` serves an API at
   `api.crc.testing:6443`: no string transformation between the two is right in general, and the
   API server publishes the answer, unauthenticated, at the well-known path.
2. THE TOKEN IS READ OFF THE `Location` HEADER. A fragment is never sent to a server and is never in
   a body, so the client must not follow the redirect — following it loses the token.
3. THE LIFETIME IS THE TARGET'S. `expires_in` is 31536000 s (a year) on the reference cluster and
   86400 s (a day) by OpenShift's default; an estate may set an hour. The session records
   `obtained_at + expires_in` as an instant — never "daily", and never an age (the operator's
   ruling: server-side text carries instants).

THE RETRY POLICY IS THE HIGH-BLAST-RADIUS PART, and it ships with the first code that can log in.
The line is drawn at THE PASSWORD BEING ON THE WIRE, not at the kind of answer:

  discovery (no password is sent): any failure
      -> bounded exponential backoff to `RETRY_POLICY.attempts`, then give up OUT LOUD
  the authorize GET failed BEFORE its bytes were written — the socket never opened or the TLS
  handshake failed (httpx.ConnectError, httpx.ConnectTimeout)
      -> the same backoff: the target cannot have bound
  the authorize GET was written and ANYTHING came back — a 401, a 5xx, a 200, a 302 without a
  token, a read timeout, a dropped connection
      -> TERMINAL. One `fleet-login-refused` line for a 401 with a Basic challenge, one
         `fleet-login-failed … not retried` line for everything else. Stop.

WHY EVERY ANSWER IS TERMINAL (review of #289; verified against upstream by the business owner): the
oauth-server's LDAP authenticator answers 401 only for LDAP result codes 48 and 49
(pkg/authenticator/password/ldappassword/ldap.go) and EVERY other directory result with 500
(pkg/osinserver/defaults.go, HandleError) — including code 19, `Exceeded password retry limit`,
which is what a directory that has ALREADY LOCKED the account says. A "5xx is transient" rule
therefore retries hardest exactly when the account is locked. A 504 means the upstream took too
long having RECEIVED the request; a 502 that it answered malformed having received it; a read
timeout that the request was written. The asymmetry decides it: a wrong retry is an estate-wide
outage against the account the target authenticates EVERY user with; a missed retry is one delayed
login that #285's daily ping picks up. Suspending the credential across clusters needs a
coordinator and is #285's; the half that needs none is here.

A MINTED TOKEN IS NEVER ABANDONED — stated precisely, because a remote delete can always fail:
from the moment the 302 is in hand, nothing leaves the login without either handing the token to
the caller inside a session or ATTEMPTING ITS REVOCATION EXACTLY ONCE, and a failed revocation is
SURFACED — a `fleet-logout-failed` line, `FleetLogin.revoked` False — never swallowed and never
reported as success. Whatever raises, including what was not predicted; and cleanup never replaces
the exception it is cleaning up after. THE GUARD IS ANCHORED ON THE RESPONSE, NOT ON A BINDING:
on any failure it re-reads what the response's own `Location` carried (`_minted_by`, pure and
total), so there is no line between "the token exists in this process" and "an exception here
revokes it" — three refactors moved "the moment the token is bound" and each reopened the window
(review of #289, three passes). `Location` IS A SINGLETON FIELD (RFC 9110 §5.5,
https://www.rfc-editor.org/rfc/rfc9110.html): a 302 carrying more than one is MALFORMED, and this
is the "systems control client" the RFC says "might consider any form of error recovery to be
dangerous" — choosing among candidate tokens would be a rule the target controls. So more than
one `Location` is a typed terminal stop, never a session; anything such a response carried is
revoked best-effort and said so, and a token that cannot be confidently named is #286's litter,
logged as such — never recovered from, never silently dropped.

THE FLOW IS OPENSHIFT'S, NOT A CHOICE MADE HERE. `response_type=token` is the OAuth implicit grant,
which RFC 9700 / OAuth 2.1 deprecate (https://oauth.net/2/grant-types/implicit/) because a token
in a URL fragment leaks through browser history and the Referer header. Neither threat applies to
this client: it is not a browser, it never follows the redirect (`follow_redirects=False`), and the
fragment never reaches a page. OpenShift's CLI login path defines the flow; this module's use of it
avoids the reason it was deprecated. Do not "fix" it. The token is read off the header WITHOUT validating the rest of the URL (a
hostile `Location` must not stand between the mint and the name of what was minted), and the
lifetime the target states is bounded at int32 (MAX_EXPIRES_IN) because it is remote-controlled
and the instant arithmetic is not. `FleetLogin.revoked` is what the target answered, recorded from
EVERY revoke site.

REDACTION NEVER TOUCHES WHAT THE CODE DERIVES MEANING FROM (the third pass, correcting the
second): a classification input — the 401 challenge, a transport message's OpenSSL phrases — is
classified RAW and only the quoted copy is scrubbed; a structured value the operator acts on — the
issuer URL, the endpoint's host — is never substring-redacted, and userinfo is stripped from it
structurally; length-agnostic redaction is kept only for genuinely free remote text (bodies,
challenge values, error strings), where mangling costs a less readable quote and nothing else. What this cannot cover, and both are why the
answer is terminal rather than retried: a request the target answered after this process stopped
listening (a read timeout), and a 302 whose `Location` httpx itself cannot parse (it builds the
redirect request even with `follow_redirects=False` and raises `RemoteProtocolError`) — either may
have minted a token this process never saw, which is #286's litter.

THE SESSION IS A CONTEXT MANAGER. Every login mints an `OAuthAccessToken` on the target and this
module owns revoking it: `__exit__` deletes it by name after the body ran, after the body raised,
and — inside the login itself — when a token was minted but no session could be built from it.
That is what lets the lookup and the daily ping leave nothing behind by construction.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx

from .clusterconfig.events import event, failure, is_verify_failure, redact
from .config import ClusterConfig, ConfigError
from .kube import AUTH_FAILED, UNREACHABLE, ClusterError, redact_text

log = logging.getLogger(__name__)

#: Where an API server publishes its OAuth server (RFC 8414's well-known path), unauthenticated.
DISCOVERY_PATH = "/.well-known/oauth-authorization-server"
#: The client `oc login` and `curl -u` present; `gsd/auditlog.py` classifies its logins as `cli`.
CHALLENGING_CLIENT = "openshift-challenging-client"
#: The header `oc` sends on the challenging flow; the oauth-server's CSRF check reads it.
CSRF_HEADER = {"X-CSRF-Token": "1"}
#: A user's own tokens. DELETE by name revokes one, authorised by the token itself — `oc logout`.
USER_TOKEN_API = "/apis/oauth.openshift.io/v1/useroauthaccesstokens"
#: A token since OpenShift 4.6 is `sha256~<random>`, and its OAuthAccessToken object is named
#: `sha256~<base64url(sha256(<random>))>` so that the token itself is never an object's name.
TOKEN_PREFIX = "sha256~"
#: The largest lifetime a target can legitimately state: `OAuthClient.accessTokenMaxAgeSeconds` is an
#: int32 in oauth.openshift.io/v1. Anything above it is a remote-controlled value that would overflow
#: the instant arithmetic (review of #289, all three seats): the token is revoked and the answer is
#: terminal.
MAX_EXPIRES_IN = 2**31 - 1
#: The refusal line's outcome. It joins `clusterconfig.FINDING_CODES` — and the tab's sentence for
#: it — in #284, the step that first puts a lookup's findings on the page (SPEC_S1 §S1.2).
LOGIN_REFUSED = "login-refused"
#: The stamp every instant this module reports is written in: `gsd/timeutil.py`'s, fixed-width UTC.
STAMP = "%Y-%m-%dT%H:%M:%SZ"
#: Every event name this module emits — in one place, so the redaction pin can prove it drove each.
EVENTS = ("fleet-login", "fleet-login-failed", "fleet-login-refused", "fleet-logout", "fleet-logout-failed")


@dataclass(frozen=True)
class RetryPolicy:
    """Bounded exponential backoff for the failures that are safe to retry.

    `attempts` is the ceiling the log quotes as `attempt=<n>/<ceiling>`; the wait after the n-th
    failure is `base_seconds × 2^(n−1)`, capped at `max_wait_seconds`. Deterministic — no jitter —
    because the design has one retriever per estate (SPEC_S4 §6, the replica rule), so there is no
    herd to spread, and a stated sequence is one a reader can check against the `retry_in=` lines.
    """

    attempts: int = 5
    base_seconds: float = 1.0
    max_wait_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError(f"a retry policy needs at least one attempt, not {self.attempts}")

    def wait_after(self, failed_attempt: int) -> float:
        return min(self.base_seconds * (2 ** (failed_attempt - 1)), self.max_wait_seconds)


#: The stated ceiling: five attempts, waiting 1, 2, 4 and 8 seconds between them — 15 s of backoff
#: plus up to five request timeouts, so a target that is down costs about a minute and a half before
#: the loop gives up out loud. Nothing locks on any of these: a refusal never reaches this loop.
RETRY_POLICY = RetryPolicy()


class LoginError(ClusterError):
    """A login that produced no session, typed for the caller's next decision.

    `outcome` is `gsd.kube`'s word — `auth_failed` for a refusal, `unreachable` for everything
    else; `phase` is where it failed, from #245's closed set; `retryable` is what the policy
    consulted — False for a refusal, for any other 401, for a CA bundle this pod cannot load, and
    for an answer this module refuses to retry into; `attempts` is how many logins were tried.
    The message never carries the password: every raise site scrubs it first.
    """

    def __init__(self, outcome: str, message: str, *, phase: str, retryable: bool):
        super().__init__(outcome, message)
        self.phase = phase
        self.retryable = retryable
        self.attempts = 0


@dataclass(frozen=True)
class _RevokeAnswer:
    """What the target said to a DELETE, decided on the wire before any line is written about it."""

    gone: bool
    """True only when the target answered 200 (revoked) or 404 (already gone)."""
    name: str | None
    """The object's name as the wire used it, or None when the wire was never reached."""
    word: str
    """revoked | already-gone | unauthenticated | refused | unanswered — the line's `outcome=` word."""
    phase: str
    outcome: str
    detail: str | None


@dataclass(frozen=True)
class FleetSession:
    """One login as the fleet account: the token, whose it is, and when it dies."""

    cluster: str
    account: str
    token: str = field(repr=False, compare=False)
    obtained_at: datetime
    """UTC, read BEFORE the login request left this process."""
    expires_in: int
    """Seconds, the target's own figure exactly as the fragment carried it."""
    issuer: str
    """The OAuth server the token came from, as the target's discovery document named it."""
    attempts: int
    """How many logins it took; 1 when the first succeeded."""

    def __post_init__(self) -> None:
        # The instants this session reports carry a `Z`, so what it holds must BE UTC: an injected
        # clock is normalised at the read (`_as_utc`) and refused here if it slipped past naive
        # (review of #289, Codex) — a naive datetime cannot be normalised without guessing its zone.
        if self.obtained_at.utcoffset() is None:
            raise ValueError("FleetSession.obtained_at must be an aware datetime")

    @property
    def expires_at(self) -> datetime:
        """The absolute instant the session dies: `obtained_at + expires_in`. `obtained_at` is the
        clock before the request left, so this errs EARLY — the dashboard may believe a session
        died a round-trip before it did, never after."""
        return self.obtained_at + timedelta(seconds=self.expires_in)

    @property
    def expires_at_iso(self) -> str:
        return self.expires_at.astimezone(UTC).strftime(STAMP)

    @property
    def token_name(self) -> str:
        return token_object_name(self.token)


def token_object_name(token: str) -> str:
    """The name of the OAuthAccessToken object a token corresponds to.

    Measured on the reference cluster: `sha256~` + base64url(sha256(the part after the prefix)),
    unpadded, is exactly the name `oc get oauthaccesstokens` lists for a token minted by this flow.
    A token WITHOUT the prefix (a cluster older than 4.6) is its own object's name — which is why
    the name is never logged unprefixed and every line carries the token in `secrets=`.
    """
    if not token.startswith(TOKEN_PREFIX):
        return token
    digest = hashlib.sha256(token[len(TOKEN_PREFIX):].encode()).digest()
    return TOKEN_PREFIX + base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _describe(exc: BaseException) -> str:
    return type(exc).__name__


def _text_of(exc: BaseException) -> str:
    """`str(exc)`, and never the reason cleanup raises: an exception whose `__str__` raises would
    otherwise replace the exception being cleaned up after (final pass, R5-3)."""
    try:
        return str(exc)
    except BaseException:  # noqa: BLE001 - the description is all that is left to say
        return "<unprintable>"


def _without_userinfo(url: str) -> str | None:
    """A URL rebuilt from its parts without any userinfo — `scheme://host[:port]/path` — or None
    when it is not an https URL with a host. STRUCTURAL, not a substring redaction (third pass: the
    round-2 scrub turned `…apps.example.com` into `…<redacted>s.example.com` for a password of
    `app`); a host that happens to contain the password is the operator's host and survives."""
    try:
        parts = urlsplit(url)
        hostname, port = parts.hostname, parts.port     # `.port` raises on a port that is not a number
    except ValueError:
        return None
    if parts.scheme != "https" or not hostname:
        # `https://:bad/x` has no host and `https://host:bad/x` no usable port: both would rebuild
        # into a malformed authority, so both fall back to the endpoint's host (final pass, R5-4).
        return None
    del port
    return f"{parts.scheme}://{parts.netloc.rpartition('@')[2]}{parts.path}"


def _as_utc(moment: datetime) -> datetime:
    """An injected clock's reading, in UTC. Aware in any zone is converted; naive is refused, because
    a `Z`-suffixed instant built from a naive reading would claim a zone it does not have."""
    if moment.utcoffset() is None:
        raise ValueError("the clock must return an aware datetime")
    return moment.astimezone(UTC)


class FleetLogin:
    """`with FleetLogin(cluster, username, password) as session:` — log in on enter, log out on exit.

    The password is taken as a value and held only for the login. It is not a field of
    `ClusterConfig`, so `poller._credentials` never sees it (SPEC_S3 §3.1 rule 4): every line this
    class emits hands it — and the token, once there is one — to the emit helper as `secrets=`, and
    every message that can reach a caller is scrubbed of it first.

    `timeout` is the per-request budget the poller gives `ClusterClient` (`requestTimeoutSeconds`);
    `policy`, `sleep` and `clock` are the loop's knobs, injectable so a test can drive the whole
    ceiling without waiting fifteen seconds or trusting the wall clock. One instance is one session:
    entering it twice is refused.
    """

    def __init__(self, cluster: ClusterConfig, username: str, password: str, *,
                 timeout: float = 15.0, policy: RetryPolicy = RETRY_POLICY,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], datetime] = _utcnow):
        self.cluster = cluster
        self.username = username
        self._password = password
        self._timeout = timeout
        self._policy = policy
        self._sleep = sleep
        self._clock = clock
        self._client: httpx.Client | None = None
        self._entered = False
        self.session: FleetSession | None = None
        #: Whether the session's token was revoked on exit: None until then, True only when the
        #: target answered the DELETE 200 or 404, False for every surfaced failure (review of #289,
        #: confirmation pass: a 500 must never be reported to the caller as revoked).
        self.revoked: bool | None = None

    # ── the context manager ──────────────────────────────────────────────────────────────────

    def __enter__(self) -> FleetSession:
        if self._entered:
            raise RuntimeError(f"FleetLogin for {self.cluster.name!r} is one session; make a new one")
        self._entered = True
        try:
            self._client = self._build_client()
        except LoginError as exc:
            self._log_stop(exc)
            raise
        try:
            self.session = self._login()
        except BaseException:
            self._close()
            raise
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if self.session is not None:
                self._revoke(self.session.token)
        finally:
            self._close()
        return False

    def _close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── the client ───────────────────────────────────────────────────────────────────────────

    def _build_client(self) -> httpx.Client:
        """One client for discovery, the login and the logout, verifying the target exactly as the
        poller does — `ClusterConfig.verify()` is the one TLS decision (SPEC_S3 §6) — and NEVER
        following a redirect, because the token is in the redirect."""
        try:
            verify = self.cluster.verify()
        except ConfigError as exc:
            # A CA bundle this pod cannot load is local, not the target's doing, and no retry
            # changes it — the same classification `ClusterClient._client` makes.
            raise LoginError(UNREACHABLE, str(exc), phase="tls", retryable=False) from exc
        return httpx.Client(base_url=self.cluster.api_url, verify=verify, timeout=self._timeout,
                            follow_redirects=False)

    # ── the login, under the policy ──────────────────────────────────────────────────────────

    def _login(self) -> FleetSession:
        policy = self._policy
        attempt = 0
        while True:
            attempt += 1
            obtained_at = _as_utc(self._clock())
            try:
                issuer, endpoint = self._discover()
                response = self._authorize(endpoint)
            except LoginError as exc:
                exc.attempts = attempt
                if not exc.retryable:
                    self._log_stop(exc)
                    raise
                if attempt >= policy.attempts:
                    self._log_retry(exc, attempt, gave_up=True)
                    raise
                wait = policy.wait_after(attempt)
                self._log_retry(exc, attempt, retry_in=wait)
                self._sleep(wait)
                continue
            # FROM HERE THE TARGET MAY HAVE MINTED A TOKEN: the response is in hand, and this guard
            # holds until the session is returned. THE CLEANUP DEPENDS ON NO LATER BINDING (third
            # pass, Codex: an interruption after the token was bound inside `_token_from` still
            # abandoned it — the third time "the moment the token is bound" moved with a refactor).
            # On any exception the guard re-reads what the RESPONSE ITSELF carried (`_minted_by`,
            # pure and total), so there is no line between "the token exists in this process" and
            # "an exception here revokes it": the response has carried it since the request returned.
            # Revocation is attempted exactly once per token: nothing inside this block revokes.
            try:
                token, fragment = self._token_from(response, endpoint)
                expires_in = self._expiry_from(fragment, endpoint)
                session = FleetSession(cluster=self.cluster.name, account=self.username, token=token,
                                       obtained_at=obtained_at, expires_in=expires_in, issuer=issuer,
                                       attempts=attempt)
                event(log, logging.INFO, "fleet-login", **self._fields(), oauth=issuer,
                      expires_at=session.expires_at_iso,
                      attempt=f"{attempt}/{policy.attempts}" if attempt > 1 else None,
                      secrets=(self._password, token))
            except BaseException as problem:
                minted, malformed = self._minted_by(response)
                if minted:
                    # A well-formed 302 carries one token. A MALFORMED one (more than one Location)
                    # is refused above, and whatever it carried is revoked best-effort — one attempt
                    # each, `revoked` True only if the target said gone for all of them.
                    self.revoked = all([self._revoke(token, best_effort=malformed) for token in minted])
                if isinstance(problem, LoginError):
                    problem.attempts = attempt
                    self._log_stop(problem)
                raise
            return session

    def _discover(self) -> tuple[str, str]:
        """(issuer, authorization_endpoint) from the target's well-known document. Unauthenticated,
        so a failure here has bound nothing — it is retried like any other transport failure."""
        try:
            response = self._client.get(DISCOVERY_PATH, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
        if response.status_code != 200:
            raise LoginError(UNREACHABLE, f"HTTP {response.status_code} on {DISCOVERY_PATH}: "
                             f"{self._scrub(response.text)[:200]}", phase="connect", retryable=True)
        try:
            document = response.json()
        except ValueError as exc:
            raise LoginError(UNREACHABLE, f"non-JSON response from {DISCOVERY_PATH}: {exc}",
                             phase="connect", retryable=True) from exc
        endpoint = document.get("authorization_endpoint") if isinstance(document, dict) else None
        try:
            parts = urlsplit(endpoint) if isinstance(endpoint, str) else None
        except ValueError as exc:
            # `urlsplit` refuses some hostile strings (an unclosed IPv6 literal) with a ValueError
            # whose text must not reach the caller unscrubbed (confirmation pass, Codex).
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names an authorization_endpoint that does "
                             f"not parse: {self._scrub(str(exc))[:200]}", phase="connect", retryable=False) from exc
        if parts is None or parts.scheme != "https" or not parts.netloc:
            # The password travels on this URL. Anything but https is refused and never retried
            # into: a document naming a plain-http endpoint is a fact about the target, not weather.
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names no https authorization_endpoint "
                             f"(got {self._scrub(str(endpoint))[:200]!r})", phase="connect", retryable=False)
        if parts.username is not None or parts.password is not None:
            # Userinfo on the endpoint is a remote-controlled secret-shaped string that would ride into
            # every message naming the host (review of #289): refused, and never quoted.
            raise LoginError(UNREACHABLE, f"{DISCOVERY_PATH} names an authorization_endpoint carrying "
                             f"userinfo; refused", phase="connect", retryable=False)
        # The issuer is a remote field that reaches the caller on the session and the log as
        # `oauth=` — and it is a URL the operator acts on, so userinfo is stripped STRUCTURALLY
        # rather than by redaction (third pass; the round-2 scrub mangled a legitimate host).
        issuer = document.get("issuer")
        rebuilt = _without_userinfo(issuer) if isinstance(issuer, str) and issuer else None
        return rebuilt or f"https://{parts.netloc}", endpoint

    def _authorize(self, endpoint: str) -> httpx.Response:
        """The challenging-client request. Returns the response; reading the token off it is
        `_token_from`, kept apart so that everything after the response is in hand runs under the
        never-abandoned guard in `_login` — which re-reads the token off this response on failure.

        ONCE THE GET CARRYING THE PASSWORD IS ISSUED, EVERY OUTCOME IS TERMINAL (the module
        docstring says why). The one retryable failure here is one provably before the password
        bytes were written: the socket never opened, or the TLS handshake failed.
        """
        try:
            response = self._client.get(endpoint, params={"client_id": CHALLENGING_CLIENT, "response_type": "token"},
                                        headers=CSRF_HEADER, auth=(self.username, self._password))
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Provably before the password bytes were written: the target cannot have bound.
            raise self._transport_error(exc) from exc
        except httpx.HTTPError as exc:
            # The request may have been written and the target may have bound — a read timeout, a
            # dropped connection, a non-HTTP answer: terminal.
            raise self._transport_error(exc, retryable=False) from exc
        else:
            # Returned from inside the protected region (final pass, R5-2): the response must not
            # exist in an instruction window outside it. What remains is the store into `_login`'s
            # local after this call returns — one bytecode, and inherent to any call boundary.
            return response

    @staticmethod
    def _fragment_of(location: str) -> dict[str, list[str]]:
        """ONE `Location` value's fragment, parsed on its own: split on the first `#`, `parse_qs`.
        The rest of the URL is NEVER validated, because a hostile `Location` (an unclosed IPv6
        literal makes `urlsplit` raise) must not stand between the mint and the name of what was
        minted (confirmation pass). No multi-segment scan and no candidate selection: a value that
        holds two URLs (a proxy joined duplicates itself) is one malformed value, not two candidates,
        and what its second URL carried is #286's litter. Total: it cannot raise."""
        return parse_qs(location.split("#", 1)[1] if "#" in location else "")

    @classmethod
    def _minted_by(cls, response: httpx.Response) -> tuple[list[str], bool]:
        """(the access_token each `Location` value carried, whether the response is MALFORMED) —
        what the never-abandoned guard re-reads on failure. `Location` is a singleton field
        (RFC 9110 §5.5): `get_list` is used to COUNT, never to choose, and a response with more than
        one is malformed. The tokens are returned only so that a malformed response's litter can be
        revoked best-effort; a session is never built from one. Pure and total."""
        if response.status_code != 302:
            return [], False
        locations = response.headers.get_list("location")
        tokens = [token for token in ((cls._fragment_of(value).get("access_token") or [""])[0]
                                      for value in locations) if token]
        return tokens, len(locations) > 1

    def _token_from(self, response: httpx.Response, endpoint: str) -> tuple[str, dict[str, list[str]]]:
        """The token and the whole fragment off a 302, or the typed stop for every other answer."""
        host = urlsplit(endpoint).netloc   # structured, and `_discover` refused userinfo: never scrubbed
        if response.status_code == 401:
            # THE REFUSAL, and the one answer that is never retried. Measured (SPEC_S4 §6): a wrong
            # password is a bare 401 with `Www-Authenticate: Basic realm="openshift"` and an empty
            # body — there are no server's words to quote beyond that, and the same 401 answers a
            # username the directory cannot find. A 401 WITHOUT the Basic challenge did not
            # necessarily evaluate the password, so it is not recorded as a refusal; it is not
            # retried either, because retrying a 401 whose cause cannot be read is the lockout walk.
            # DECIDE ON THE RAW CHALLENGE, THEN SCRUB THE COPY THAT IS QUOTED (confirmation pass,
            # Codex): a password that is literally `Basic` redacted the challenge before it was
            # classified, and a genuine refusal came out as `unreachable`.
            raw_challenge = response.headers.get("www-authenticate", "")
            is_basic = raw_challenge.strip().lower().startswith("basic")
            challenge = self._scrub(raw_challenge)[:200]
            said = (f"401 Unauthorized from {host}; Www-Authenticate: {challenge or '<absent>'}; "
                    f"body: {self._scrub(response.text)[:200] or '<empty>'}")
            if is_basic:
                raise LoginError(AUTH_FAILED, said, phase="credential", retryable=False)
            raise LoginError(UNREACHABLE, f"{said} — no Basic challenge, so this is a client or server "
                             f"fault rather than a refusal; not retried", phase="credential", retryable=False)
        if response.status_code != 302:
            # The password was on the wire and the target answered: terminal, whatever the status —
            # a 500 is what the oauth-server says for every directory result but 48/49, a locked
            # account's code 19 included.
            raise LoginError(UNREACHABLE, f"HTTP {response.status_code} on {host}/oauth/authorize: "
                             f"{self._scrub(response.text)[:200]}; not retried — the password was sent",
                             phase="credential", retryable=False)
        locations = response.headers.get_list("location")
        if len(locations) > 1:
            # RFC 9110 §5.5: Location is a singleton field, so this response is MALFORMED — and a
            # systems control client does not recover from a malformed construct (§5.5, "might
            # consider any form of error recovery to be dangerous"): picking a candidate token would
            # be a rule the target controls. No session; the guard revokes what it carried best-effort.
            raise LoginError(UNREACHABLE, f"302 from {host} carried {len(locations)} Location headers — "
                             f"malformed (RFC 9110 §5.5: Location is a singleton field); a systems client "
                             f"does not recover, so no session is built and anything it minted is revoked "
                             f"best-effort (a token it could not name is #286's litter)",
                             phase="credential", retryable=False)
        fragment = self._fragment_of(locations[0] if locations else "")
        token = (fragment.get("access_token") or [""])[0]
        if not token:
            # The bind happened and the grant failed after it: terminal for the same reason.
            error = (fragment.get("error") or ["<none>"])[0]
            raise LoginError(UNREACHABLE, f"302 from {host} carried no access_token in its Location fragment "
                             f"(error={self._scrub(error)[:100]}, keys={self._scrub(','.join(sorted(fragment)))[:100]}); "
                             f"not retried — the password was sent", phase="credential", retryable=False)
        return token, fragment

    def _expiry_from(self, fragment: dict[str, list[str]], endpoint: str) -> int:
        """`expires_in` as the target stated it, bounded. Runs under the never-abandoned guard: a
        token WAS minted, so the guard attempts its revocation once and does not retry into a
        second one — the fragment's shape is a fact about the target."""
        host = urlsplit(endpoint).netloc
        raw_expiry = (fragment.get("expires_in") or [None])[0]
        try:
            expires_in = int(raw_expiry) if raw_expiry is not None else 0
        except ValueError:
            expires_in = 0
        if not 0 < expires_in <= MAX_EXPIRES_IN:
            raise LoginError(UNREACHABLE, f"302 from {host} carried a token without a usable expires_in "
                             f"(got {self._scrub(str(raw_expiry))[:100]!r}; the bound is 1..{MAX_EXPIRES_IN}); "
                             f"its revocation was attempted once — the fleet-logout line says whether it "
                             f"succeeded", phase="credential", retryable=False)
        return expires_in

    # ── the logout ───────────────────────────────────────────────────────────────────────────

    def _delete_token(self, token: str) -> _RevokeAnswer:
        """THE WIRE ONLY — `oc logout`: DELETE the OAuthAccessToken by name, authorised by the token
        itself — answered as a value, before any line is written about it. `gone` is True only when
        the target said so: 200, or 404 (already gone). ONLY a 404 means gone: a 401 says the DELETE
        was not authenticated and nothing about the object (review of #289, Codex). A transport
        failure is an answer here, never a raise.

        The object is gone the moment the DELETE answers 200. The token itself may go on authenticating
        from the API server's token cache for about two minutes (121 s measured on the reference
        cluster) — a fact for #285's "a 401 means re-authenticate" rule, not litter: nothing on the
        target names it any more, and `oc get oauthaccesstokens` shows it gone at once."""
        name = token_object_name(token)   # derived ONCE, here, where the wire needs it (final pass, R5-3)
        try:
            response = self._client.delete(f"{USER_TOKEN_API}/{name}",
                                           headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            problem = self._transport_error(exc, token)
            return _RevokeAnswer(False, name, "unanswered", problem.phase, UNREACHABLE, problem.message)
        if response.status_code == 200:
            return _RevokeAnswer(True, name, "revoked", "poll", "revoked", None)
        if response.status_code == 404:
            return _RevokeAnswer(True, name, "already-gone", "poll", "already-gone", None)
        body = self._scrub(response.text, token)[:200] or "<empty body>"
        if response.status_code == 401:
            return _RevokeAnswer(False, name, "unauthenticated", "credential", AUTH_FAILED,
                                 f"401 Unauthorized on DELETE {USER_TOKEN_API}/<name>: the token did not authorise "
                                 f"its own revoke, so the object may still exist — {body}")
        return _RevokeAnswer(False, name, "refused", "poll", UNREACHABLE,
                             f"HTTP {response.status_code} on DELETE {USER_TOKEN_API}/<name>: revoke refused — {body}")

    def _revoke(self, token: str, *, best_effort: bool = False) -> bool:
        """The ONE boundary every revoke site goes through — the exit and the login's guard alike.
        `best_effort` marks a token read off a MALFORMED response (more than one Location): the
        line says so, because whether the target minted it at all is not known.

        Three things, in this order, and the order is the point (third pass, Codex): the wire
        answers; `revoked` records what the TARGET said, from every site, so the caller (#284, #285)
        reads the truth about what was left behind; and only then is the line written — a line that
        fails to write after a 200 is not a failed revoke, and is said as what it is. Never raises:
        cleanup never replaces the exception it is cleaning up after (confirmation pass), so a fault
        of this process on the wire path is surfaced as a `fleet-logout-failed` line and answered
        False, and a fault while writing the line falls back to the stdlib logger, which cannot raise.
        """
        # NOTHING IS COMPUTED BEFORE THE WIRE THAT THE WIRE DOES NOT NEED (final pass, R5-3): the
        # name is derived once, inside `_delete_token`, and comes back on the answer for the line.
        try:
            answer = self._delete_token(token)
        except BaseException as exc:  # noqa: BLE001 - the wire never raises; this is a fault of this process
            answer = _RevokeAnswer(False, None, "unanswered", "connect", UNREACHABLE,
                                   f"{_describe(exc)}: {self._scrub(_text_of(exc), token)[:200]} — the revoke "
                                   f"itself failed before the target answered")
        self.revoked = answer.gone
        shown = answer.name if answer.name and token.startswith(TOKEN_PREFIX) else None   # unprefixed IS the token
        secrets = (self._password, token)
        try:
            if answer.gone:
                event(log, logging.INFO, "fleet-logout", **self._fields(), token=shown, outcome=answer.word,
                      best_effort="true" if best_effort else None, secrets=secrets)
            else:
                failure(log, "fleet-logout-failed", phase=answer.phase, outcome=answer.outcome, **self._fields(),
                        token=shown, best_effort="true" if best_effort else None,
                        action=("the OAuthAccessToken may still be on the target and nothing here will try "
                                "again: delete it there as cluster-admin (oc delete oauthaccesstoken <token>) "
                                "so it does not become litter"),
                        detail=answer.detail, secrets=secrets)
        except BaseException as exc:  # noqa: BLE001 - the LINE failed, not the revoke; `revoked` already holds the answer
            try:
                log.warning("fleet-logout line could not be written (revoked=%s): %s: %s", answer.gone,
                            _describe(exc), self._scrub(_text_of(exc), token)[:200])
            except BaseException:  # noqa: BLE001, S110 - the last resort: cleanup can never raise (final pass, R5-3)
                pass
        return answer.gone

    # ── the vocabulary ───────────────────────────────────────────────────────────────────────

    def _fields(self) -> dict[str, str]:
        mode = self.cluster.tls_mode
        return {"cluster": self.cluster.name, "account": self.username,
                "tls": "insecure" if mode["insecure"] else mode["ca"]}

    def _scrub(self, text: str, *more: str | None) -> str:
        """Every secret in play out of FREE REMOTE TEXT — a body, a challenge value, an error string,
        a transport message's quoted copy — in both spellings the two helpers know (`gsd.kube`'s
        JSON-escaped forms and the emit helper's) and then, REGARDLESS OF LENGTH, the raw value of
        each (confirmation pass: a three-character password passed both helpers' floors; the floors
        are theirs and stay). Before any truncation, always.

        THREE RULES ON WHERE THIS MAY BE APPLIED (third pass, correcting the round-2 instruction
        "regardless of length, everywhere" — measured: a password of `app` turned the issuer into
        `…<redacted>s.example.com`, and one of `certificate` unclassified a TLS failure into
        `phase=connect`): never on a classification input — decide on the raw value, scrub the
        displayed copy; never on a structured value the operator acts on — the issuer, the endpoint's
        host — where userinfo is stripped structurally instead; only on free text, where mangling
        costs a less readable quote and nothing else."""
        secrets = tuple(v for v in (self._password, *more) if v)
        out = redact(redact_text(text, *secrets), secrets)
        for secret in sorted(secrets, key=len, reverse=True):
            out = out.replace(secret, "<redacted>")
        return out

    def _transport_error(self, exc: httpx.HTTPError, *more: str | None, retryable: bool = True) -> LoginError:
        """A transport failure in the one shape this process gives one — `<ExceptionType>: <text>`,
        which `is_verify_failure` and the poller's classifier both key on. Whether it may be retried
        is the caller's to say: it depends on whether the password was on the wire, not on the
        exception."""
        raw = f"{type(exc).__name__}: {exc}"
        # DECIDE ON THE RAW MESSAGE, THEN SCRUB THE COPY (third pass: a password of `certificate`
        # scrubbed the phrase the classifier keys on and a TLS failure became `phase=connect`).
        phase = "tls" if is_verify_failure(raw) else "connect"
        return LoginError(UNREACHABLE, self._scrub(raw, *more), phase=phase, retryable=retryable)

    def _log_retry(self, exc: LoginError, attempt: int, *, retry_in: float | None = None,
                   gave_up: bool = False) -> None:
        ceiling = self._policy.attempts
        if gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until the next lookup or "
                      f"ping — check the API URL, the OAuth route and TLS trust for the OAuth host "
                      f"(the INGRESS CA, which the API's bundle may not carry) from this pod")
        else:
            action = f"retrying in {retry_in:g}s; if every attempt fails, the gave_up line says so"
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                attempt=f"{attempt}/{ceiling}", retry_in=None if retry_in is None else f"{retry_in:g}",
                gave_up="true" if gave_up else None, action=action, detail=exc.message,
                secrets=(self._password,))

    def _log_stop(self, exc: LoginError) -> None:
        if exc.outcome == AUTH_FAILED:
            failure(log, "fleet-login-refused", phase="credential", outcome=LOGIN_REFUSED, **self._fields(),
                    action=(f"the target refused the password for {self.username}: rotate the fleet "
                            f"password Secret or correct ldapConnectionBootstrap — no second attempt is "
                            f"made, because a retry is the lockout walk against the account the target "
                            f"authenticates every user with"),
                    detail=exc.message, secrets=(self._password,))
            return
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                action="not retried: fix what detail names before the next lookup or ping",
                detail=exc.message, secrets=(self._password,))
```

### 3.3 `local-development/gsd/clusterconfig/events.py` — the verify classifier, declared once

The poller classifies a refused certificate by the message's **provenance** (a transport message,
`<ExceptionType>: …`) and then by OpenSSL's phrases (#245, review of #247 Codex C3). The login needs
the same decision for its `phase=tls`, so the phrase list and the two predicates move here and the
poller reads them; the poller's behaviour is byte-for-byte the same expression.

**File:** `local-development/gsd/clusterconfig/events.py` — edit

Old text:

```python
_NEEDS_QUOTING = re.compile(r"[\s\"=]")
```

New text:

```python
_NEEDS_QUOTING = re.compile(r"[\s\"=]")

#: The phrases OpenSSL and CPython actually produce for a certificate the trust store refused.
#: Matched only against a TRANSPORT message — `<ExceptionType>: <text>`, the one shape this process
#: gives a transport failure — and never against a remote's answer, which is remote-controlled: a
#: proxy's 502 body mentioning certificates is not a TLS problem this cluster has (review of #247,
#: Codex C3). Declared once, here, for the poller's classifier and the fleet login's alike.
VERIFY_FAILURE_PHRASES = (
    "certificate_verify_failed", "certificate verify failed", "sslcertverificationerror",
    "self-signed certificate", "self signed certificate", "unable to get local issuer",
)


def is_transport_message(message: str) -> bool:
    """Whether a failure message is one THIS process wrote for a transport failure — a Python
    identifier before the first colon — rather than a remote's answer (`HTTP 502 on …`)."""
    return message.split(":", 1)[0].strip().isidentifier()


def is_verify_failure(message: str) -> bool:
    """A certificate the trust store refused: a transport message carrying one of the phrases.
    Provenance first, words second."""
    lowered = message.lower()
    return is_transport_message(message) and any(phrase in lowered for phrase in VERIFY_FAILURE_PHRASES)
```

### 3.4 `local-development/gsd/poller.py` — read the shared classifier

Two edits, both behaviour-preserving: the lazy import gains the predicate, and the inline expression
becomes the call. `transport` stays computed locally because the `phase=connect` branch below it
still reads it.

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
    from .clusterconfig.events import failure
    mode = cluster.tls_mode
```

New text:

```python
    from .clusterconfig.events import failure, is_verify_failure
    mode = cluster.tls_mode
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
    kind = message.split(":", 1)[0].strip()
    transport = kind.isidentifier()
    lowered = message.lower()
    verify_failed = transport and any(
        phrase in lowered for phrase in
        ("certificate_verify_failed", "certificate verify failed", "sslcertverificationerror",
         "self-signed certificate", "self signed certificate", "unable to get local issuer"))
```

New text:

```python
    kind = message.split(":", 1)[0].strip()
    transport = kind.isidentifier()
    verify_failed = is_verify_failure(message)
```

### 3.5 `local-development/tests/test_fleet_login.py` — the hermetic proof

Every requirement of §1 has a class; the refusal test asserts the authorize call count is **exactly
one** and that the scripted second answer was never consumed. The fake target records every request
in order, so "the redirect was not followed" and "the DELETE is the last request" are assertions about
the wire, not about the code's intent.

**File:** `local-development/tests/test_fleet_login.py` — whole file

```python
"""#283 (SPEC_S4a): log in to a target as the fleet account, read the expiry, apply the retry policy,
log out — against a fake OAuth server that records every request the module makes, in order.

Each class is one of the business owner's requirements as the spec numbers them: R1 login only,
R2 the session logs out on every exit path, R3 the retry policy (a refusal is NEVER retried — the
call count is asserted to be exactly one), R4 the expiry is an absolute instant from the target's own
`expires_in`, R5 the token is read off the `Location` fragment and the redirect is not followed,
R6 the OAuth host is discovered, R7 TLS follows the cluster's `tls_mode`, R8 the three log fields,
no new phase, and the redaction pin over every new path."""

from __future__ import annotations

import ast
import base64
import hashlib
import http.server
import json
import logging
import os
import pathlib
import shutil
import ssl
import subprocess
import threading
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import gsd.fleetlogin as fleetlogin
from gsd.clusterconfig.events import PHASES, is_verify_failure
from gsd.config import ClusterConfig, ConfigError
from gsd.fleetlogin import (
    CHALLENGING_CLIENT, DISCOVERY_PATH, EVENTS, LOGIN_REFUSED, MAX_EXPIRES_IN, TOKEN_PREFIX, USER_TOKEN_API,
    FleetLogin, FleetSession, LoginError, RetryPolicy, token_object_name,
)
from gsd.kube import AUTH_FAILED, UNREACHABLE, ClusterError

API = "https://api.example.com:6443"
OAUTH = "https://oauth-openshift.apps.example.com"
DISCOVERY = {"issuer": OAUTH, "authorization_endpoint": f"{OAUTH}/oauth/authorize",
             "token_endpoint": f"{OAUTH}/oauth/token"}
USER = "svc-gsd-fleet"
PASSWORD = "c0rrect-horse-battery-staple"
TOKEN = "sha256~Qm9ndXNUb2tlblRoYXRNdXN0TmV2ZXJSZWFjaEFMb2c"
T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
POLICY = RetryPolicy(attempts=5, base_seconds=1.0, max_wait_seconds=30.0)
BASIC = 'Basic realm="openshift"'


def login_302(expires_in: str = "31536000", token: str = TOKEN) -> httpx.Response:
    """What the reference cluster answered a correct password with (SPEC_S4a §2): a 302 with an
    empty body and everything in the fragment."""
    location = (f"{OAUTH}/oauth/token/implicit#access_token={token}&expires_in={expires_in}"
                f"&scope=user%3Afull&token_type=Bearer")
    return httpx.Response(302, headers={"Location": location})


def refused_401(body: str = "") -> httpx.Response:
    """A refused password as SPEC_S4 §6 measured it: a bare 401, the Basic challenge, an empty body."""
    return httpx.Response(401, headers={"Www-Authenticate": BASIC}, text=body)


def down(request: httpx.Request) -> Exception:
    return httpx.ConnectError("[Errno 61] Connection refused")


class Target:
    """The fake target: a discovery document at the API host, an authorize endpoint at the OAuth
    host answering from a script (a Response, or a callable given the request that returns a
    Response or an exception to raise), a revoke endpoint, and every request in order."""

    def __init__(self, *answers, discovery=None, revoke=None):
        self.answers = list(answers)
        self.discovery = DISCOVERY if discovery is None else discovery
        self.revoke = httpx.Response(200, json={"kind": "OAuthAccessToken"}) if revoke is None else revoke
        self.requests: list[httpx.Request] = []

    @staticmethod
    def _answer(answer, request):
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == DISCOVERY_PATH:
            if isinstance(self.discovery, dict):
                return httpx.Response(200, json=self.discovery)
            return self._answer(self.discovery, request)
        if request.url.path == "/oauth/authorize":
            return self._answer(self.answers.pop(0), request)
        if request.method == "DELETE" and request.url.path.startswith(USER_TOKEN_API + "/"):
            return self._answer(self.revoke, request)
        return httpx.Response(599, text=f"the fake target has no {request.method} {request.url}")

    @property
    def authorize(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/oauth/authorize"]

    @property
    def revokes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "DELETE"]


def scripted(*answers):
    """A discovery endpoint answering from a script, one answer per call."""
    queue = list(answers)
    return lambda request: queue.pop(0)


def make(target: Target, *, cluster: ClusterConfig | None = None, policy: RetryPolicy = POLICY,
         clock=None, password: str = PASSWORD) -> tuple[FleetLogin, list[float]]:
    """A FleetLogin wired to the fake target, with the sleeps it asked for recorded and the clock
    held at T0 unless the test brings its own."""
    cluster = cluster or ClusterConfig("east", API, insecure_skip_verify=True)
    sleeps: list[float] = []
    fl = FleetLogin(cluster, USER, password, policy=policy, sleep=sleeps.append, clock=clock or (lambda: T0))
    fl._build_client = lambda: httpx.Client(transport=httpx.MockTransport(target), base_url=API,
                                            follow_redirects=False)
    return fl, sleeps


def lines(caplog, name: str) -> list[str]:
    return [m for m in caplog.messages if m.startswith(name + " ")]


# ── R6 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheOAuthHostIsDiscovered:
    def test_the_login_goes_to_the_discovered_endpoint_not_the_api_host(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        wire = [(r.method, r.url.host, r.url.path) for r in target.requests]
        assert wire[0] == ("GET", "api.example.com", DISCOVERY_PATH)
        assert wire[1] == ("GET", "oauth-openshift.apps.example.com", "/oauth/authorize")
        assert "authorization" not in target.requests[0].headers, "discovery is unauthenticated"

    def test_the_authorize_request_is_the_challenging_client_flow(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        req = target.authorize[0]
        assert dict(req.url.params) == {"client_id": CHALLENGING_CLIENT, "response_type": "token"}
        assert req.headers["x-csrf-token"] == "1"
        basic = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        assert req.headers["authorization"] == f"Basic {basic}"

    def test_the_client_id_is_the_one_the_audit_log_classifies_as_cli(self):
        from gsd.auditlog import CHALLENGING_CLIENT as audited
        assert CHALLENGING_CLIENT == audited

    def test_a_plain_http_endpoint_is_refused_before_any_password_is_sent(self):
        target = Target(login_302(), discovery={"authorization_endpoint": "http://oauth.example.com/oauth/authorize"})
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert target.authorize == [] and sleeps == []
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False and exc.value.phase == "connect"

    def test_a_discovery_endpoint_that_does_not_parse_is_a_scrubbed_stop(self):
        """Confirmation pass (Codex): `urlsplit` raises `ValueError: Invalid IPv6 URL` on an unclosed
        literal, and its text reached the caller through no LoginError at all."""
        hostile = {"authorization_endpoint": f"https://{USER}:{PASSWORD}@[::1/oauth/authorize"}
        target = Target(login_302(), discovery=hostile)
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and exc.value.phase == "connect"
        assert "does not parse" in exc.value.message and PASSWORD not in str(exc.value)
        assert target.authorize == [] and sleeps == []

    def test_the_issuer_is_the_documents_and_falls_back_to_the_endpoints_host(self):
        with make(Target(login_302()))[0] as s:
            assert s.issuer == OAUTH
        bare = {"authorization_endpoint": f"{OAUTH}/oauth/authorize"}
        with make(Target(login_302(), discovery=bare))[0] as s:
            assert s.issuer == OAUTH


# ── R5 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheTokenIsReadOffTheLocationFragment:
    def test_the_token_and_expiry_come_from_the_fragment_and_the_redirect_is_not_followed(self):
        target = Target(login_302(expires_in="86400"))
        fl, _ = make(target)
        with fl as session:
            assert session.token == TOKEN and session.expires_in == 86400
        assert [r.url.path for r in target.requests] == [
            DISCOVERY_PATH, "/oauth/authorize", f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"]
        assert not any("/oauth/token/implicit" in str(r.url) for r in target.requests), "the redirect was followed"

    def test_a_302_without_a_token_is_not_a_session_and_is_terminal(self):
        """INVERTED by the review of #289: the first version retried this (2 binds). The bind
        happened and the grant failed after it, so a second attempt is a second bind."""
        no_token = httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error=server_error"})
        target = Target(no_token, login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert len(target.authorize) == 1 and sleeps == [] and target.revokes == []
        assert exc.value.retryable is False and "server_error" in exc.value.message

    def test_a_hostile_location_never_stands_between_the_mint_and_the_revoke(self):
        """Confirmation pass (Codex, measured `authorize=1 DELETE=0`): `urlsplit` raised on the
        malformed URL before the token was read, so a minted token was never named and never
        revoked. The header is split on its first `#` and the rest of the URL is never validated.

        THE STRING IS THE MEASURED ONE. `https://example.com]/…` is delivered by httpx as a 302 and
        makes `urlsplit` raise `Invalid IPv6 URL`; `https://[::1/…` is refused by httpx itself
        (`RemoteProtocolError: Invalid URL in location header`) inside `_send_handling_redirects`,
        which builds the redirect request even with `follow_redirects=False` — a token minted
        behind such a header is one this process never sees (the spec records the limit)."""
        hostile = f"https://example.com]/oauth/token/implicit#access_token={TOKEN}&expires_in=3600"
        target = Target(httpx.Response(302, headers={"Location": hostile}))
        with make(target)[0] as s:
            assert s.token == TOKEN and s.expires_in == 3600
        assert len(target.revokes) == 1 and target.requests[-1].method == "DELETE"
        unusable = f"https://example.com]/oauth/token/implicit#access_token={TOKEN}&expires_in=soon"
        target = Target(httpx.Response(302, headers={"Location": unusable}))
        fl, _ = make(target)
        with pytest.raises(LoginError):
            with fl:
                pass
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        no_token = Target(httpx.Response(302, headers={"Location": "https://a[b/x#error=server_error"}))
        with pytest.raises(LoginError) as exc:
            with make(no_token)[0]:
                pass
        assert "server_error" in exc.value.message and no_token.revokes == []

    def test_two_location_headers_are_malformed_a_stop_and_a_best_effort_revoke(self, caplog):
        """Final pass (R5-1), as corrected by the owner: `Location` is a singleton field (RFC 9110
        §5.5), so two of them are a malformed response — never a session, whichever value carries
        the token, because choosing would be a rule the target controls. What it carried is revoked
        best-effort and `revoked` is truthful about that; a token that cannot be named is litter,
        said so."""
        implicit = f"{OAUTH}/oauth/token/implicit"
        second = [("Location", f"{implicit}#error=denied"),
                  ("Location", f"{implicit}#access_token={TOKEN}&expires_in=60")]
        assert FleetLogin._minted_by(httpx.Response(302, headers=second)) == ([TOKEN], True)
        target = Target(httpx.Response(302, headers=second))
        fl, sleeps = make(target)
        with caplog.at_level(logging.INFO):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert fl.session is None and sleeps == [] and exc.value.retryable is False
        assert "malformed" in exc.value.message and "RFC 9110" in exc.value.message
        assert len(target.revokes) == 1 and fl.revoked is True, "what it carried was revoked, best-effort"
        assert "best_effort=true" in lines(caplog, "fleet-logout")[0]
        # two tokens: both revoked, one attempt each; one refused -> revoked is False
        both = [("Location", f"{implicit}#access_token={TOKEN}&expires_in=60"),
                ("Location", f"{implicit}#access_token=sha256~AnotherTokenTheTargetChose0000000000&expires_in=60")]
        target = Target(httpx.Response(302, headers=both))
        fl, _ = make(target)
        with pytest.raises(LoginError):
            with fl:
                pass
        assert len(target.revokes) == 2 and fl.revoked is True
        target = Target(httpx.Response(302, headers=both), revoke=httpx.Response(500, text="oops"))
        fl, _ = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError):
                with fl:
                    pass
        assert len(target.revokes) == 2 and fl.revoked is False
        assert any("best_effort=true" in m for m in lines(caplog, "fleet-logout-failed"))
        # no token in either: nothing to revoke, and the message says the litter is #286's
        none = [("Location", f"{implicit}#error=denied"), ("Location", f"{implicit}#error=denied")]
        target = Target(httpx.Response(302, headers=none))
        fl, _ = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert target.revokes == [] and fl.revoked is None and "#286" in exc.value.message
        # exactly one Location: the simple path, unchanged — and a value a proxy joined itself is
        # ONE malformed value, not two candidates: no session, no recovery
        with make(Target(login_302(expires_in="60")))[0] as s:
            assert s.token == TOKEN and s.expires_in == 60
        joined = {"Location": f"{implicit}#error=denied, {implicit}#access_token={TOKEN}&expires_in=60"}
        target = Target(httpx.Response(302, headers=joined))
        fl, _ = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert "no access_token" in exc.value.message and target.revokes == []

    def test_an_expiry_beyond_int32_is_bounded_revoked_once_and_terminal(self):
        """Review of #289, all three seats: 999999999999999 passed `int()` and the `<= 0` guard,
        then overflowed the instant arithmetic with an OverflowError that escaped `__enter__` —
        and the minted token was never revoked."""
        target = Target(login_302(expires_in="999999999999999"), login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and str(MAX_EXPIRES_IN) in exc.value.message
        assert len(target.authorize) == 1 and sleeps == [] and fl.session is None
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        with make(Target(login_302(expires_in=str(MAX_EXPIRES_IN))))[0] as s:
            assert s.expires_in == MAX_EXPIRES_IN and s.expires_at_iso.endswith("Z")
        with pytest.raises(LoginError):
            with make(Target(login_302(expires_in=str(MAX_EXPIRES_IN + 1))))[0]:
                pass

    def test_a_token_without_a_usable_expiry_is_revoked_at_once_and_not_retried(self):
        target = Target(login_302(expires_in="soon"), login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and exc.value.phase == "credential"
        assert len(target.authorize) == 1 and sleeps == [] and fl.session is None
        assert [r.url.path for r in target.revokes] == [f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"]
        assert "attempted once" in exc.value.message, "the message states the attempt, never a result it cannot know"
        assert fl.revoked is True, "and `revoked` states the result the target gave (200)"


# ── R4 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheExpiryIsAnAbsoluteInstant:
    @pytest.mark.parametrize("expires_in,expected", [
        ("31536000", T0 + timedelta(days=365)),   # the reference cluster: a year
        ("86400", T0 + timedelta(days=1)),        # OpenShift's default: a day
        ("3600", T0 + timedelta(hours=1)),        # an estate that tightened it
    ])
    def test_it_is_obtained_at_plus_the_targets_own_expires_in(self, expires_in, expected):
        with make(Target(login_302(expires_in=expires_in)))[0] as s:
            assert s.obtained_at == T0 and s.expires_at == expected
            assert s.expires_at.utcoffset() == timedelta(0)
            assert s.expires_at_iso == expected.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_the_clock_is_read_before_the_request_leaves(self):
        order: list[str] = []

        def clock():
            order.append("clock")
            return T0

        def answer(request):
            order.append("authorize")
            return login_302()

        with make(Target(answer), clock=clock)[0]:
            pass
        assert order == ["clock", "authorize"]

    def test_a_non_utc_clock_is_normalised_and_a_naive_one_refused(self):
        """Review of #289, Codex: an injected clock in another zone produced a `Z`-suffixed string
        that was not UTC."""
        chicago = T0.astimezone(timezone(timedelta(hours=-5)))
        assert chicago.hour == 7
        with make(Target(login_302(expires_in="3600")), clock=lambda: chicago)[0] as s:
            assert s.obtained_at == T0 and s.obtained_at.utcoffset() == timedelta(0)
            assert s.expires_at_iso == "2026-09-21T13:00:00Z"
        target = Target(login_302())
        with pytest.raises(ValueError, match="aware"):
            with make(target, clock=lambda: T0.replace(tzinfo=None))[0]:
                pass
        assert target.requests == [], "a naive clock is refused before anything is minted"
        with pytest.raises(ValueError, match="aware"):
            FleetSession(cluster="c", account="a", token=TOKEN, obtained_at=T0.replace(tzinfo=None),
                         expires_in=1, issuer=OAUTH, attempts=1)

    def test_the_success_line_carries_the_instant_never_an_age(self, caplog):
        with caplog.at_level(logging.INFO):
            with make(Target(login_302(expires_in="3600")))[0]:
                pass
        line = lines(caplog, "fleet-login")[0]
        assert "expires_at=2026-09-21T13:00:00Z" in line
        assert "ago" not in line and "expires_in" not in line and "hour" not in line


# ── R2 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheSessionLogsOut:
    def test_the_revoke_is_by_name_with_the_token_as_bearer_and_is_the_last_request(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        last = target.requests[-1]
        assert last.method == "DELETE"
        assert last.url.path == f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"
        assert last.headers["authorization"] == f"Bearer {TOKEN}"
        assert len(target.revokes) == 1

    def test_an_exception_in_the_body_still_revokes_and_propagates(self):
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(RuntimeError, match="the read failed"):
            with fl:
                raise RuntimeError("the read failed")
        assert len(target.revokes) == 1 and target.requests[-1].method == "DELETE"

    def test_a_base_exception_in_the_body_still_revokes(self):
        class Abort(BaseException):
            pass

        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(Abort):
            with fl:
                raise Abort()
        assert len(target.revokes) == 1

    def test_a_token_is_never_abandoned_whatever_raises_after_it_was_minted(self, monkeypatch):
        """Review of #289: the invariant is "a minted token is never abandoned", and it must hold for
        exceptions nobody predicted — here a KeyboardInterrupt inside the success line's emit."""
        real_event = fleetlogin.event

        def interrupted(log, level, name, **fields):
            if name == "fleet-login":
                raise KeyboardInterrupt()
            real_event(log, level, name, **fields)

        monkeypatch.setattr(fleetlogin, "event", interrupted)
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert fl.session is None
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        assert target.requests[-1].url.path == f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"
        # ... and from inside the interval between the response and the session (confirmation
        # pass, Codex: the first version raised only from the success line).
        monkeypatch.setattr(fleetlogin, "event", real_event)
        target = Target(login_302())
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_expiry_from", lambda fragment, endpoint: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert fl.session is None and len(target.revokes) == 1

    def test_an_interruption_inside_the_extraction_still_revokes(self, monkeypatch):
        """Third pass (Codex, `authorize=1 DELETE=0`): the guard began after `_token_from` returned,
        so an interruption inside it — after the token was bound — abandoned the token. The guard is
        anchored on the RESPONSE now and re-reads the token off it, so the window cannot exist."""
        real_parse_qs = fleetlogin.parse_qs
        calls: list[int] = []

        def parse_then_die(query: str):
            calls.append(1)
            result = real_parse_qs(query)
            if len(calls) == 1 and "access_token" in result:
                raise KeyboardInterrupt()          # the token is in hand, and the frame is leaving
            return result

        monkeypatch.setattr(fleetlogin, "parse_qs", parse_then_die)
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert fl.session is None and len(target.revokes) == 1 and fl.revoked is True
        # and after `_token_from` returned but before anything else ran
        monkeypatch.setattr(fleetlogin, "parse_qs", real_parse_qs)
        target = Target(login_302())
        fl, _ = make(target)
        real_token_from = fl._token_from

        def bind_then_die(response, endpoint):
            real_token_from(response, endpoint)
            raise KeyboardInterrupt()

        monkeypatch.setattr(fl, "_token_from", bind_then_die)
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert len(target.revokes) == 1 and fl.revoked is True

    def test_revoked_is_what_the_target_answered_from_every_site(self, monkeypatch, caplog):
        """Third pass (Codex): the guard's revoke discarded the answer, and a `fleet-logout` line
        that failed to write after a 200 was reported as a failed revoke."""
        target = Target(login_302(expires_in="soon"))      # the guard's site, DELETE 200
        fl, _ = make(target)
        with pytest.raises(LoginError):
            with fl:
                pass
        assert fl.revoked is True and len(target.revokes) == 1
        real_event = fleetlogin.event

        def emitter_that_dies(log, level, name, **fields):
            if name == "fleet-logout":
                raise RuntimeError("the emitter broke")
            real_event(log, level, name, **fields)

        monkeypatch.setattr(fleetlogin, "event", emitter_that_dies)
        target = Target(login_302())
        fl, _ = make(target)
        with caplog.at_level(logging.WARNING):
            with fl:
                pass
        assert fl.revoked is True, "a line that fails to write is not a failed revoke"
        assert lines(caplog, "fleet-logout-failed") == []
        assert not any("failed before the target answered" in m for m in caplog.messages)
        assert any("fleet-logout line could not be written (revoked=True)" in m for m in caplog.messages)

    def test_authorize_returns_from_inside_its_protected_region(self):
        """Final pass (R5-2): `return response` sat after the `try`, so the response existed in an
        instruction window outside the protected region. What remains — the store into `_login`'s
        local after the call returns — is one bytecode and inherent to any call boundary."""
        tree = ast.parse(pathlib.Path(fleetlogin.__file__).read_text())
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_authorize")
        assert not [n for n in fn.body if isinstance(n, ast.Return)], "a return outside the try"
        tries = [n for n in fn.body if isinstance(n, ast.Try)]
        assert tries and any(isinstance(n, ast.Return) for t in tries for n in ast.walk(t))

    def test_a_failure_before_the_wire_cannot_replace_the_original_exception(self, monkeypatch, caplog):
        """Final pass (R5-3): the object name was derived for the LOG before the wire, outside the
        protected path, so a failure there escaped `_revoke` — and the fallback logger could raise."""
        class BodyError(Exception):
            pass

        real_name = fleetlogin.token_object_name
        monkeypatch.setattr(fleetlogin, "token_object_name",
                            lambda token: (_ for _ in ()).throw(RuntimeError("naming broke")))
        target = Target(login_302())
        fl, _ = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(BodyError):
                with fl:
                    raise BodyError()
        assert fl.revoked is False and "naming broke" in lines(caplog, "fleet-logout-failed")[0]
        # the last resort: the line's emitter AND the fallback logger both raise
        monkeypatch.setattr(fleetlogin, "token_object_name", real_name)
        real_event = fleetlogin.event

        def emitter_that_dies(log, level, name, **fields):
            if name == "fleet-logout":
                raise RuntimeError("the emitter broke")
            real_event(log, level, name, **fields)

        monkeypatch.setattr(fleetlogin, "event", emitter_that_dies)
        monkeypatch.setattr(fleetlogin.log, "warning",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the logger broke")))
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(BodyError):
            with fl:
                raise BodyError()
        assert fl.revoked is True and len(target.revokes) == 1

    def test_a_failure_during_cleanup_never_replaces_the_original_exception(self, monkeypatch, caplog):
        """Confirmation pass (Codex: `raised=RuntimeError original=Marker`). The revoke's own
        failure is surfaced as a line and the body's exception is the one that propagates."""
        class BodyError(Exception):
            pass

        target = Target(login_302())
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_delete_token", lambda token: (_ for _ in ()).throw(RuntimeError("cleanup broke")))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(BodyError):
                with fl:
                    raise BodyError()
        assert fl.revoked is False
        assert "cleanup broke" in lines(caplog, "fleet-logout-failed")[0]
        # the same inside the login's own guard
        target = Target(login_302(expires_in="soon"))
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_delete_token", lambda token: (_ for _ in ()).throw(RuntimeError("cleanup broke")))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError):
                with fl:
                    pass
        assert len(lines(caplog, "fleet-logout-failed")) == 2

    def test_a_revoke_that_failed_is_surfaced_never_reported_as_revoked(self, caplog):
        """Confirmation pass (Codex: `revoke-500: DELETE=1 caller_says_revoked=True`). The invariant
        is that revocation is ATTEMPTED exactly once and a failure is surfaced — `revoked` is False,
        the line says so — never that the object is gone."""
        for status, expected in ((200, True), (404, True), (500, False), (401, False)):
            target = Target(login_302(), revoke=httpx.Response(status, text="answer"))
            fl, _ = make(target)
            with caplog.at_level(logging.WARNING):
                with fl:
                    pass
            assert fl.revoked is expected, status
            assert len(target.revokes) == 1, "revocation attempted exactly once"
        assert len(lines(caplog, "fleet-logout-failed")) == 2
        target = Target(login_302(expires_in="soon"), revoke=httpx.Response(500, text="oops"))
        fl, _ = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert "attempted once" in exc.value.message and "was revoked" not in exc.value.message
        assert len(target.revokes) == 1 and len(lines(caplog, "fleet-logout-failed")) == 3
        assert fl.revoked is False, "the target answered 500: not revoked, from this site too (R3-2, R3-4)"
        target = Target(login_302(expires_in="soon"))
        fl, _ = make(target)
        with pytest.raises(LoginError):
            with fl:
                pass
        assert fl.revoked is True and len(target.revokes) == 1

    def test_the_object_name_is_the_measured_derivation(self):
        """PINNED TO A LITERAL, never regenerated from the code under test (review of #289, Cursor
        and OB1-lite: the first version recomputed the formula, so a wrong formula — and every
        DELETE answering 404 while the suite stayed green — would have passed). The value came from
        `printf '%s' 'testsecret123' | openssl dgst -sha256 -binary | base64 | tr '+/' '-_' | tr -d '='`
        and was confirmed against a live OAuthAccessToken object on the reference cluster."""
        assert token_object_name("sha256~testsecret123") == "sha256~AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY"
        assert token_object_name("legacy-token-value") == "legacy-token-value"

    def test_an_already_gone_token_is_not_a_failure(self, caplog):
        """INVERTED for 401 by the review of #289 (Codex): only a 404 means gone."""
        target = Target(login_302(), revoke=httpx.Response(404, text="gone"))
        with caplog.at_level(logging.INFO):
            with make(target)[0]:
                pass
        assert lines(caplog, "fleet-logout-failed") == []
        assert "outcome=already-gone" in lines(caplog, "fleet-logout")[0]

    def test_a_401_on_the_revoke_is_a_failure_not_already_gone(self, caplog):
        """A 401 proves the DELETE was unauthenticated and nothing about the object, which may be
        alive; logging a successful logout for it would be a lie the count would later expose."""
        target = Target(login_302(), revoke=httpx.Response(401, text="Unauthorized"))
        with caplog.at_level(logging.INFO):
            with make(target)[0]:
                pass
        assert lines(caplog, "fleet-logout") == []
        line = lines(caplog, "fleet-logout-failed")[0]
        assert "outcome=auth_failed" in line and "phase=credential" in line and "may still exist" in line
        assert f"token={token_object_name(TOKEN)}" in line and "cluster-admin" in line
        refused = Target(login_302(), revoke=httpx.Response(403, text="Forbidden"))
        with caplog.at_level(logging.INFO):
            with make(refused)[0]:
                pass
        assert "revoke refused" in lines(caplog, "fleet-logout-failed")[1] and "outcome=unreachable" in lines(caplog, "fleet-logout-failed")[1]

    def test_a_revoke_the_target_refused_is_said_out_loud_and_does_not_raise(self, caplog):
        target = Target(login_302(), revoke=httpx.Response(500, text="oops"))
        with caplog.at_level(logging.WARNING):
            with make(target)[0]:
                pass
        line = lines(caplog, "fleet-logout-failed")[0]
        assert f"token={token_object_name(TOKEN)}" in line and "phase=poll" in line and "HTTP 500" in line
        assert "oc delete oauthaccesstoken" in line

    def test_a_failed_revoke_does_not_replace_the_bodys_exception(self, caplog):
        target = Target(login_302(), revoke=lambda request: httpx.ConnectError("the target went away"))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(RuntimeError, match="the body's own"):
                with make(target)[0]:
                    raise RuntimeError("the body's own")
        assert "phase=connect" in lines(caplog, "fleet-logout-failed")[0]

    def test_a_login_that_failed_has_nothing_to_revoke(self):
        target = Target(refused_401())
        with pytest.raises(LoginError):
            with make(target)[0]:
                pass
        assert target.revokes == []

    def test_one_instance_is_one_session(self):
        fl, _ = make(Target(login_302(), login_302()))
        with fl:
            pass
        with pytest.raises(RuntimeError, match="one session"):
            with fl:
                pass


# ── R3 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheRetryPolicy:
    def test_a_refused_password_is_never_retried(self, caplog):
        target = Target(refused_401(), login_302())     # the second answer must never be asked for
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1, "the refusal was retried — that is the lockout walk"
        assert len(target.answers) == 1, "the scripted second answer was consumed"
        assert sleeps == [] and target.revokes == []
        assert exc.value.outcome == AUTH_FAILED and exc.value.retryable is False and exc.value.attempts == 1
        line = lines(caplog, "fleet-login-refused")[0]
        assert f"outcome={LOGIN_REFUSED}" in line and "phase=credential" in line and f"account={USER}" in line
        assert "Www-Authenticate: Basic" in line, "the server's own words — the status line and the challenge"
        assert "attempt=" not in line and "retry_in=" not in line and "gave_up=" not in line
        assert lines(caplog, "fleet-login-failed") == []

    def test_a_password_that_is_literally_basic_still_classifies_the_refusal(self, caplog):
        """Confirmation pass (Codex): P1-2's scrub ran BEFORE the challenge was classified, so a
        password of `Basic` redacted a genuine refusal into `unreachable`. Decide, then redact."""
        target = Target(refused_401())
        fl, _ = make(target, password="Basic")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert exc.value.outcome == AUTH_FAILED and len(target.authorize) == 1
        assert len(lines(caplog, "fleet-login-refused")) == 1
        assert "Basic" not in exc.value.message and "<redacted> realm" in exc.value.message

    def test_a_refusal_is_a_typed_cluster_error_the_caller_can_branch_on(self):
        with pytest.raises(ClusterError) as exc:
            with make(Target(refused_401()))[0]:
                pass
        assert isinstance(exc.value, LoginError) and exc.value.outcome == AUTH_FAILED

    def test_a_401_without_a_basic_challenge_is_not_a_refusal_and_is_not_retried_either(self, caplog):
        target = Target(httpx.Response(401, text="no challenge"), login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1 and sleeps == []
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False
        assert lines(caplog, "fleet-login-refused") == []
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=credential" in line and "<absent>" in line and "not retried" in line

    @pytest.mark.parametrize("transient", [
        down,
        lambda request: httpx.ConnectTimeout("timed out connecting"),
        lambda request: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                           "self-signed certificate in certificate chain"),
    ], ids=["refused-socket", "connect-timeout", "tls-verify"])
    def test_a_target_that_never_took_the_request_is_retried_with_exponential_backoff(self, transient, caplog):
        """The only retryable failures on the authorize step: the socket never opened or the TLS
        handshake failed, so the password bytes were provably never written. (The first version of
        this test also retried a read timeout and a 503 — INVERTED below, review of #289.)"""
        target = Target(transient, transient, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.INFO):
            with fl as s:
                assert s.attempts == 3
        assert len(target.authorize) == 3 and sleeps == [1.0, 2.0]
        failed = lines(caplog, "fleet-login-failed")
        assert len(failed) == 2
        assert "attempt=1/5" in failed[0] and "retry_in=1" in failed[0] and "gave_up=" not in failed[0]
        assert "attempt=2/5" in failed[1] and "retry_in=2" in failed[1]
        assert "attempt=3/5" in lines(caplog, "fleet-login")[0]

    @pytest.mark.parametrize("answer", [
        lambda request: httpx.ReadTimeout("timed out"),
        lambda request: httpx.WriteError("connection reset while writing"),
        lambda request: httpx.ReadError("connection reset"),
        lambda request: httpx.RemoteProtocolError("illegal status line"),
        httpx.Response(200, text="<html>a proxy answered</html>"),
        httpx.Response(403, text="forbidden"),
        httpx.Response(429, text="slow down"),
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(502, text="Bad Gateway"),
        httpx.Response(503, text="oauth-server unavailable"),
        httpx.Response(504, text="Gateway Timeout"),
    ], ids=["read-timeout", "write-error", "read-error", "remote-protocol", "http-200", "http-403", "http-429",
            "http-500", "http-502", "http-503", "http-504"])
    def test_once_the_password_is_on_the_wire_every_answer_is_terminal(self, answer, caplog):
        """Review of #289 (Codex and Cursor; OB1-lite's narrower set rejected): the oauth-server
        answers EVERY directory result but 48/49 with a 500 — a locked account's code 19 included —
        so a "5xx is transient" rule retries hardest exactly when the account is locked; a 504 or
        502 means the upstream RECEIVED the request; a read timeout means it was written."""
        target = Target(answer, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1, "the password was sent again"
        assert sleeps == [] and target.revokes == [] and len(target.answers) == 1
        assert exc.value.retryable is False and exc.value.outcome == UNREACHABLE
        assert lines(caplog, "fleet-login-refused") == []
        line = lines(caplog, "fleet-login-failed")[0]
        assert "not retried" in line and "attempt=" not in line
        if isinstance(answer, httpx.Response):
            assert exc.value.phase == "credential" and f"HTTP {answer.status_code}" in line

    def test_it_gives_up_out_loud_at_the_ceiling(self, caplog):
        target = Target(down, down, down, down, down, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 5 and sleeps == [1.0, 2.0, 4.0, 8.0]
        assert len(target.answers) == 1, "a sixth attempt was made past the ceiling"
        assert exc.value.outcome == UNREACHABLE and exc.value.attempts == 5 and exc.value.retryable is True
        last = lines(caplog, "fleet-login-failed")[-1]
        assert "gave_up=true" in last and "attempt=5/5" in last and "retry_in=" not in last
        assert "Connection refused" in last, "the last error travels with the gave_up line"
        assert target.revokes == []

    def test_the_wait_sequence_is_the_stated_one(self):
        assert [POLICY.wait_after(n) for n in range(1, 5)] == [1.0, 2.0, 4.0, 8.0]
        assert RetryPolicy(attempts=8).wait_after(7) == 30.0, "capped at max_wait_seconds"
        assert fleetlogin.RETRY_POLICY == RetryPolicy(attempts=5, base_seconds=1.0, max_wait_seconds=30.0)
        with pytest.raises(ValueError):
            RetryPolicy(attempts=0)

    def test_a_discovery_failure_counts_as_an_attempt_and_is_retried(self, caplog):
        target = Target(login_302(), discovery=scripted(httpx.Response(502, text="bad gateway"),
                                                         httpx.Response(200, json=DISCOVERY)))
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with fl as s:
                assert s.attempts == 2
        assert sleeps == [1.0] and len(target.authorize) == 1
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=connect" in line and "attempt=1/5" in line and "HTTP 502" in line

    def test_a_tls_failure_is_phase_tls_and_a_socket_failure_phase_connect(self, caplog):
        tls = lambda request: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        target = Target(tls, down, login_302())
        with caplog.at_level(logging.WARNING):
            with make(target)[0]:
                pass
        failed = lines(caplog, "fleet-login-failed")
        assert "phase=tls" in failed[0] and "phase=connect" in failed[1]


# ── R7 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTLSFollowsTheClustersMode:
    class Recorder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    def test_verify_is_the_clusters_own_decision_and_redirects_are_never_followed(self, monkeypatch):
        monkeypatch.setattr(fleetlogin.httpx, "Client", self.Recorder)
        sentinel = object()
        monkeypatch.setattr(ClusterConfig, "verify", lambda self: sentinel)
        client = FleetLogin(ClusterConfig("east", API), USER, PASSWORD, timeout=7.5)._build_client()
        assert client.kwargs["verify"] is sentinel
        assert client.kwargs["follow_redirects"] is False
        assert client.kwargs["timeout"] == 7.5 and client.kwargs["base_url"] == API

    def test_insecure_and_default_modes_pass_what_the_poller_passes(self, monkeypatch):
        monkeypatch.setattr(fleetlogin.httpx, "Client", self.Recorder)
        monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
        insecure = ClusterConfig("east", API, insecure_skip_verify=True)
        assert FleetLogin(insecure, USER, PASSWORD)._build_client().kwargs["verify"] is False
        default = ClusterConfig("east", API)
        assert FleetLogin(default, USER, PASSWORD)._build_client().kwargs["verify"] == default.verify()

    def test_a_ca_bundle_this_pod_cannot_load_is_a_tls_stop_before_any_request(self, tmp_path, caplog):
        cluster = ClusterConfig("east", API, ca_bundle_file=str(tmp_path / "missing.pem"))
        fl = FleetLogin(cluster, USER, PASSWORD, sleep=lambda s: pytest.fail("slept"))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False and exc.value.phase == "tls"
        assert isinstance(exc.value.__cause__, ConfigError)
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=tls" in line and "tls=caBundleFile" in line and "not retried" in line


# ── R7, the split the reference lab cannot show ───────────────────────────────────────────────

OPENSSL = shutil.which("openssl")


def _require_openssl() -> None:
    """A developer machine without `openssl` skips the split-CA proof; CI never may. The suite's
    convention for a tool a proof depends on (`test_chart_grafana_dashboard.py`, promtool): under
    `CI` — which GitHub Actions always sets — a missing tool FAILS the test, so the one test that
    proves the credential is never sent to an OAuth host the bundle cannot verify cannot silently
    stop running (the business owner could not tell from a `-q` CI log whether it had)."""
    if OPENSSL is not None:
        return
    if os.environ.get("CI"):
        pytest.fail("openssl is not on PATH and this is CI: the split-CA proof must never be skipped "
                    "here — it is the only test that proves the credential is not sent to an OAuth host "
                    "the bundle cannot verify; put openssl on the runner's PATH")
    pytest.skip("openssl is not on PATH; the split-CA fixture generates its certificates with it")


_CA_CNF = """[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = {name}
[ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
"""
_SERVER_EXT = """basicConstraints = CA:FALSE
subjectAltName = DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
keyUsage = critical, digitalSignature, keyEncipherment
"""


def _pki(root: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """A CA with the extensions a real issuer carries — a bare `req -x509` lacks basicConstraints
    and keyUsage, and the failure then reads `CA cert does not include key usage extension`, a
    defect in the fixture rather than the real-world rejection — and a localhost server certificate
    it signed (SAN for localhost and 127.0.0.1, serverAuth). Returns (ca.crt, server.crt,
    server.key). Generated per test under tmp_path; nothing is committed."""
    cnf = root / f"ca{name}.cnf"
    cnf.write_text(_CA_CNF.format(name=f"test-ca-{name}"))
    ext = root / "server.ext"
    ext.write_text(_SERVER_EXT)
    ca_crt, ca_key = root / f"ca{name}.crt", root / f"ca{name}.key"
    srv_crt, srv_key, csr = root / f"srv{name}.crt", root / f"srv{name}.key", root / f"srv{name}.csr"

    def run(*args: object) -> None:
        subprocess.run([OPENSSL, *map(str, args)], check=True, capture_output=True)

    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", ca_key, "-out", ca_crt, "-days", "2",
        "-config", cnf, "-subj", f"/CN=test-ca-{name}")
    run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", srv_key, "-out", csr, "-subj", "/CN=localhost")
    run("x509", "-req", "-in", csr, "-CA", ca_crt, "-CAkey", ca_key, "-CAcreateserial", "-out", srv_crt,
        "-days", "2", "-extfile", ext)
    return ca_crt, srv_crt, srv_key


class _QuietServer(http.server.ThreadingHTTPServer):
    """A handshake a client refuses raises in the handler thread; that is the point, not noise.
    `handle_error` is consulted only for an exception while HANDLING an accepted connection —
    a bind failure raises from the constructor and is never routed here."""

    def handle_error(self, request, client_address) -> None:
        pass


class _TlsServer:
    """One loopback HTTPS server on a daemon thread, shut down by the fixture's `finally`; a test
    that fails cannot leave a listener behind, and a bind failure raises here, in the test."""

    def __init__(self, crt: pathlib.Path, key: pathlib.Path, handler: type) -> None:
        self.server = _QuietServer(("127.0.0.1", 0), handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(crt), str(key))
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def split_estate(tmp_path):
    """CA A signs the API server and CA B signs the OAuth server — the shape of a customer cluster
    whose ingress is re-signed by an enterprise PKI — plus a record of every Authorization header
    the OAuth host received and of every discovery the API host answered. Two bundles: A alone, and
    A with B (the control)."""
    _require_openssl()
    ca_a, api_crt, api_key = _pki(tmp_path, "A")
    ca_b, oauth_crt, oauth_key = _pki(tmp_path, "B")
    seen: dict = {"discovery": 0, "authorization": []}

    class OAuthHost(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["authorization"].append(self.headers.get("Authorization"))
            self.send_response(302)
            self.send_header("Location", "https://localhost/oauth/token/implicit#error=fixture")
            self.end_headers()

        def log_message(self, *args):
            pass

    oauth = _TlsServer(oauth_crt, oauth_key, OAuthHost)
    document = json.dumps({"issuer": f"https://localhost:{oauth.port}",
                           "authorization_endpoint": f"https://localhost:{oauth.port}/oauth/authorize"}).encode()

    class ApiHost(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["discovery"] += 1
            self.send_response(200 if self.path == DISCOVERY_PATH else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(document if self.path == DISCOVERY_PATH else b"{}")

        def log_message(self, *args):
            pass

    try:
        api = _TlsServer(api_crt, api_key, ApiHost)
    except BaseException:
        oauth.close()
        raise
    api_only = tmp_path / "api-only.crt"
    api_only.write_text(ca_a.read_text())
    both = tmp_path / "both.crt"
    both.write_text(ca_a.read_text() + ca_b.read_text())
    try:
        yield SimpleNamespace(api_url=f"https://localhost:{api.port}", api_only=str(api_only), both=str(both), seen=seen)
    finally:
        oauth.close()
        api.close()


class TestTheSplitCATheLabCannotShow:
    """The reference lab is structurally blind to this (SPEC_S4a §2.1): CRC's kube-root-ca.crt
    carries six certificates and two of them are the ingress leaf and the ingress CA, so an
    API-only bundle verifies the OAuth host too. On a customer cluster whose ingress is re-signed by
    an enterprise PKI it will not, and the login must fail at the authorize step WITHOUT the
    credential reaching the host. `curl` on a Mac gives a false pass here (the system keychain);
    Python's ssl is what the dashboard uses and what this drives — two real TLS servers, no mock."""

    POLICY = RetryPolicy(attempts=2, base_seconds=0.01)

    def test_an_api_only_bundle_never_sends_the_credential_to_an_ingress_signed_oauth_host(self, split_estate, caplog):
        cluster = ClusterConfig("split", split_estate.api_url, ca_bundle_file=split_estate.api_only)
        fl = FleetLogin(cluster, USER, PASSWORD, policy=self.POLICY)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        # 1. the point: the credential never reached the OAuth host
        assert split_estate.seen["authorization"] == [], "the credential reached the OAuth host"
        # 2. discovery succeeded first, so this proves the SPLIT and not merely a bad bundle
        assert split_estate.seen["discovery"] >= 1, "discovery failed: the test would pass for the wrong reason"
        # 3. a TLS failure before the password was written is the one class that still retries
        assert exc.value.phase == "tls" and exc.value.outcome == UNREACHABLE and exc.value.retryable is True
        assert exc.value.attempts == 2
        assert "unable to get local issuer certificate" in exc.value.message
        # 4. no password anywhere
        whole = "\n".join(caplog.messages)
        assert PASSWORD not in str(exc.value) and PASSWORD not in whole
        # 5. the gave_up action names the ingress CA
        last = lines(caplog, "fleet-login-failed")[-1]
        assert "gave_up=true" in last and "attempt=2/2" in last and "INGRESS CA" in last and "tls=caBundleFile" in last

    def test_the_control_a_bundle_with_both_cas_reaches_the_oauth_host(self, split_estate):
        """Without this, zero hits cannot be told from a broken fixture."""
        cluster = ClusterConfig("split", split_estate.api_url, ca_bundle_file=split_estate.both)
        fl = FleetLogin(cluster, USER, PASSWORD, policy=self.POLICY)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        headers = split_estate.seen["authorization"]
        assert len(headers) == 1 and headers[0].startswith("Basic "), headers
        assert exc.value.retryable is False and exc.value.phase == "credential", "a 302 without a token is terminal"


# ── R8 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheLogVocabulary:
    def test_no_new_phase_was_added(self):
        assert PHASES == ("discovery", "parse", "credential", "tls", "connect", "poll")

    def test_the_shared_verify_classifier_keeps_the_pollers_provenance_rule(self):
        assert is_verify_failure("ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        assert is_verify_failure("ConnectError: unable to get local issuer certificate")
        assert not is_verify_failure("HTTP 502 on /apis: certificate verify failed"), "a remote's words decide nothing"
        assert not is_verify_failure("ConnectError: [Errno 61] Connection refused")
        assert not is_verify_failure("")

    def test_every_line_names_the_cluster_the_account_and_the_tls_mode(self, caplog):
        with caplog.at_level(logging.INFO):
            with make(Target(down, login_302()))[0]:
                pass
        for line in [*lines(caplog, "fleet-login-failed"), *lines(caplog, "fleet-login"), *lines(caplog, "fleet-logout")]:
            assert "cluster=east" in line and f"account={USER}" in line and "tls=insecure" in line, line


class TestTheRedactionPin:
    """Every event this module can emit, driven with the password and the token planted in every
    text a remote controls, the whole log grepped for both. The set of events driven must equal
    EVENTS, and EVENTS must equal what the source emits — so a new emit site fails here twice, once
    for not being declared and once for not being driven with a secret in force."""

    def _drive_everything(self, caplog) -> list[LoginError]:
        """Every event, and the password planted in EVERY remote-controlled field: the body, the
        Www-Authenticate challenge, the Location error query, the discovery endpoint's userinfo,
        expires_in, and a transport error's text (review of #289: three raise sites quoted a field
        unscrubbed, so the log was clean and `str(exc)` — which #284 will put on the page — was not)."""
        errors: list[LoginError] = []

        def failing(target, **kw):
            with pytest.raises(LoginError) as exc:
                with make(target, **kw)[0]:
                    pass
            errors.append(exc.value)

        with caplog.at_level(logging.DEBUG):
            failing(Target(refused_401(body=f"denied pw={PASSWORD}")))                     # fleet-login-refused
            failing(Target(httpx.Response(401, headers={"Www-Authenticate": f'Basic realm="{PASSWORD}"'})))
            echo = lambda request: httpx.ConnectError(f"connect to https://{USER}:{PASSWORD}@host failed")
            failing(Target(echo, echo, echo, echo, echo))                                   # retried, gave up
            failing(Target(httpx.Response(302, headers={
                "Location": f"{OAUTH}/oauth/token/implicit#error={PASSWORD}&error_description={PASSWORD}"})))
            failing(Target(login_302(), discovery={
                "authorization_endpoint": f"https://{USER}:{PASSWORD}@oauth.example.com/oauth/authorize"}))
            failing(Target(login_302(), discovery={                                         # does not parse
                "authorization_endpoint": f"https://{USER}:{PASSWORD}@[::1/oauth/authorize"}))
            failing(Target(httpx.Response(401, text=f"csrf pw={PASSWORD}")))                # not a refusal, stopped
            failing(Target(login_302(expires_in=f"{PASSWORD}")))                            # revoke inside the login
            failing(Target(httpx.Response(503, text=f"down pw={PASSWORD}")))                # terminal HTTP answer
            failing(Target(lambda request: httpx.ReadTimeout(f"timed out pw={PASSWORD}")))  # terminal transport
            planted_issuer = {"issuer": f"https://{USER}:{PASSWORD}@oauth.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
            with make(Target(login_302(), discovery=planted_issuer))[0] as session:         # fleet-login, fleet-logout
                assert session.issuer == "https://oauth.example", "userinfo stripped structurally, host intact"
            with make(Target(login_302(), revoke=httpx.Response(500, text=f"echo {TOKEN} {PASSWORD}")))[0]:
                pass                                                                        # fleet-logout-failed
        return errors

    def test_every_new_log_path_is_driven_and_none_leaks(self, caplog):
        self._drive_everything(caplog)
        whole = "\n".join(caplog.messages)
        assert PASSWORD not in whole, "the password reached the log"
        assert TOKEN not in whole, "the token reached the log"
        assert "<redacted>" in whole
        seen = {m.split()[0] for m in caplog.messages if m.startswith("fleet-")}
        assert seen == set(EVENTS), f"driven {sorted(seen)}, declared {sorted(EVENTS)}"

    def test_the_error_handed_to_the_caller_carries_no_password(self, caplog):
        errors = self._drive_everything(caplog)
        assert len(errors) == 10
        for exc in errors:
            assert PASSWORD not in exc.message and PASSWORD not in str(exc), exc.message
            assert TOKEN not in exc.message

    def test_a_password_shorter_than_the_shared_floors_is_still_redacted(self, caplog):
        """Confirmation pass (Codex): `events.redact` floors at 4 and `kube.redact_text` at 8, so a
        three-character password reached the message AND the log. The floors are theirs and stay;
        the module scrubs the credential it holds regardless of length."""
        target = Target(refused_401(body="denied pw=abc"))
        fl, _ = make(target, password="abc")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert "pw=abc" not in exc.value.message and "pw=<redacted>" in exc.value.message
        assert "pw=abc" not in "\n".join(caplog.messages)

    def test_a_password_that_is_a_substring_of_a_host_leaves_the_issuer_intact(self):
        """Third pass — the round-2 rule "scrub regardless of length, everywhere" was the
        orchestrator's and was wrong: password `app` turned the issuer into
        `https://oauth-openshift.<redacted>s.example.com`. A structured value the operator acts on
        is never substring-redacted."""
        with make(Target(login_302()), password="app")[0] as s:
            assert s.issuer == OAUTH

    def test_userinfo_in_the_issuer_is_stripped_structurally(self):
        planted = {"issuer": f"https://{USER}:{PASSWORD}@oauth.example:8443/x", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
        with make(Target(login_302(), discovery=planted))[0] as s:
            assert s.issuer == "https://oauth.example:8443/x"
        unusable = {"issuer": "http://plain.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
        with make(Target(login_302(), discovery=unusable))[0] as s:
            assert s.issuer == OAUTH, "a non-https issuer falls back to the endpoint's host"
        # final pass (R5-4): a malformed authority falls back too, rather than being rebuilt malformed
        for bad in ("https://:bad/x", "https://host:bad/x"):
            assert fleetlogin._without_userinfo(bad) is None, bad
            with make(Target(login_302(), discovery={"issuer": bad, "authorization_endpoint": f"{OAUTH}/oauth/authorize"}))[0] as s:
                assert s.issuer == OAUTH, bad

    def test_a_password_that_is_a_classification_word_does_not_change_the_phase(self, caplog):
        """Third pass: password `certificate` scrubbed the phrase `is_verify_failure` keys on and a
        TLS failure became `phase=connect`. Classify raw, scrub the copy. THE MESSAGE CARRIES ONLY
        THE LOWERCASE PHRASE: with the uppercase `CERTIFICATE_VERIFY_FAILED` marker beside it the old
        case-sensitive scrub left that marker intact and the classifier still matched, so the test
        passed on the defect — measured while writing it."""
        tls = lambda request: httpx.ConnectError("certificate verify failed (_ssl.c:1010)")
        target = Target(tls, tls, tls, tls, tls)
        fl, _ = make(target, password="certificate")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert exc.value.phase == "tls" and "certificate" not in exc.value.message
        assert all("phase=tls" in m for m in lines(caplog, "fleet-login-failed"))

    def test_the_source_declares_every_event_it_emits_and_passes_secrets_on_each(self):
        tree = ast.parse(pathlib.Path(fleetlogin.__file__).read_text())
        emits = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("event", "failure")]
        assert emits
        assert all(any(k.arg == "secrets" for k in n.keywords) for n in emits), "an emit site without secrets="
        names = {(n.args[2] if n.func.id == "event" else n.args[1]).value for n in emits}
        assert names == set(EVENTS)


# ── R1 ─────────────────────────────────────────────────────────────────────────────────────────

class TestScopeIsLoginOnly:
    def test_the_module_only_ever_gets_and_deletes_its_own_token(self, caplog):
        target = Target(down, login_302())
        with make(target)[0]:
            pass
        assert {r.method for r in target.requests} == {"GET", "DELETE"}
        assert all(r.url.path.startswith(USER_TOKEN_API + "/") for r in target.revokes)

    def test_the_source_neither_writes_a_secret_nor_starts_a_timer(self):
        """Parsed, not grepped: the docstring says "schedules" and "Secret" while saying the module
        does neither. What is asserted is what the code IMPORTS and which methods it calls on its
        client — a write verb or a scheduler is a fact of the AST, not of the prose."""
        tree = ast.parse(pathlib.Path(fleetlogin.__file__).read_text())
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert imported.isdisjoint({"threading", "sched", "asyncio", "signal", "subprocess"}), imported
        called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert called.isdisjoint({"post", "put", "patch", "request", "stream", "Timer", "Thread"}), called
        assert {"get", "delete"} <= called
```

### 3.6 `local-development/tests/test_live_fleet_login.py` — the live proof, and the count

Skipped by default. The account it takes must be one the **target's** identity provider authenticates
and that no directory sits behind; on the reference cluster that is `developer`. The
`OAuthAccessToken` count before, during and after the session is the proof the review will use.

**File:** `local-development/tests/test_live_fleet_login.py` — whole file

```python
"""Live proof of #283 against a real OAuth server: the session is obtained, its expiry is the
target's own, the token authenticates while the session is open and not after it closes, and the
OAuthAccessToken it minted is gone when the session closes.

Skipped unless the environment names a target and an account the TARGET's identity provider will
authenticate. On the reference cluster that is the htpasswd `developer` account — NEVER the LDAP
fleet account: a wrong password there is the lockout walk this module exists to prevent, and its
loginability is proven by `oc get user <name>`, not by logging in (SPEC_S4a, orchestrator's notes).

    GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 \\
    GSD_LIVE_LOGIN_USER=developer GSD_LIVE_LOGIN_PASSWORD=… \\
    GSD_LIVE_LOGIN_CA=/path/to/the/poller/ca.crt \\
    KUBECONFIG=~/.crc/machines/crc/kubeconfig \\
    .venv/bin/python -m pytest tests/test_live_fleet_login.py -v -s

With KUBECONFIG pointing at a cluster-admin session, `oauth_token_count` also reads the target's
OAuthAccessToken objects for that account and client before, during and after the session — the
count the review holds the "logs out by construction" claim to: during == before + 1 with the
session's own name among them, and after == before with the name gone. Without `oc`, or without
the grant, the count is None and only the token's own behaviour is asserted.

THE TOKEN OUTLIVES ITS OBJECT, BRIEFLY. Measured on the reference cluster (2026-09-21): the object
is absent from the list the moment the session closes, while the revoked token goes on answering
`users/~` with 200 for 121 s — the API server's token authenticator cache — and then 401. So the
token's death is WAITED for, up to GSD_LIVE_LOGIN_DEAD_WAIT seconds (default 180), and the count
is what proves the logout; the wait proves the cache empties.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.fleetlogin import CHALLENGING_CLIENT, TOKEN_PREFIX, FleetLogin

API = os.environ.get("GSD_LIVE_LOGIN_API")
USER = os.environ.get("GSD_LIVE_LOGIN_USER")
PASSWORD = os.environ.get("GSD_LIVE_LOGIN_PASSWORD")
CA = os.environ.get("GSD_LIVE_LOGIN_CA")
DEAD_WAIT = float(os.environ.get("GSD_LIVE_LOGIN_DEAD_WAIT", "180"))
ME = "/apis/user.openshift.io/v1/users/~"

pytestmark = pytest.mark.skipif(
    not (API and USER and PASSWORD),
    reason="set GSD_LIVE_LOGIN_API, GSD_LIVE_LOGIN_USER and GSD_LIVE_LOGIN_PASSWORD to run the live fleet-login test",
)


def oauth_token_count(user: str) -> tuple[int, set[str]] | None:
    """(count, names) of the OAuthAccessToken objects `user` holds for the challenging client, read
    with `oc` through KUBECONFIG — a cluster-admin list, so None when `oc` is absent or refused."""
    try:
        run = subprocess.run(["oc", "get", "oauthaccesstokens", "-o", "json"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0:
        return None
    names = {i["metadata"]["name"] for i in json.loads(run.stdout)["items"]
             if i.get("userName") == user and i.get("clientName") == CHALLENGING_CLIENT}
    return len(names), names


def _cluster() -> ClusterConfig:
    return ClusterConfig("live", API, ca_bundle_file=CA) if CA else ClusterConfig("live", API)


def _whoami(token: str) -> httpx.Response:
    with httpx.Client(verify=_cluster().verify(), timeout=15.0) as client:
        return client.get(f"{API}{ME}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})


def test_the_session_is_obtained_and_revoked():
    before = oauth_token_count(USER)
    with FleetLogin(_cluster(), USER, PASSWORD) as session:
        assert session.token.startswith(TOKEN_PREFIX)
        assert session.expires_in > 0 and session.expires_at > session.obtained_at
        assert session.attempts == 1
        me = _whoami(session.token)
        assert me.status_code == 200 and me.json()["metadata"]["name"] == USER, me.text[:200]
        during = oauth_token_count(USER)
        if before is not None and during is not None:
            assert during[0] == before[0] + 1, (before[0], during[0])
            assert session.token_name in during[1] - before[1]
        print(f"\nlive: account={USER} issuer={session.issuer} expires_in={session.expires_in} "
              f"expires_at={session.expires_at_iso} token_name={session.token_name} "
              f"count_before={None if before is None else before[0]} "
              f"count_during={None if during is None else during[0]}")
    after = oauth_token_count(USER)
    if before is not None and after is not None:
        assert after[0] == before[0] and session.token_name not in after[1], (before[0], after[0])
        print(f"live: count_after={after[0]} (before={before[0]})")
    # The OBJECT is gone at once (above). The token itself keeps authenticating from the API server's
    # token cache for a window — 121 s measured on the reference cluster — so its death is waited for,
    # not asserted on the first request after the close.
    started = time.monotonic()
    while True:
        dead = _whoami(session.token)
        elapsed = time.monotonic() - started
        if dead.status_code == 401 or elapsed > DEAD_WAIT:
            break
        time.sleep(2)
    assert dead.status_code == 401, f"the token still authenticates {elapsed:.0f} s after the session closed: {dead.status_code}"
    print(f"live: the revoked token stopped authenticating after {elapsed:.0f} s (the API server's token cache)")
```

### 3.7 `local-development/tests/test_specs_index.py` — a step letter on the id

**File:** `local-development/tests/test_specs_index.py` — edit

Old text:

```python
    r"^\| (?P<id>[A-Z]\d) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)[^|]*\| [^|]+\| "
```

New text:

```python
    r"^\| (?P<id>[A-Z]\d[a-z]?) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)[^|]*\| [^|]+\| "
```

**File:** `local-development/tests/test_specs_index.py` — edit

Old text:

```python
    assert len(rows) == 19, f"expected nineteen index rows (the programme's thirteen, E1, S1, S2, S3, S4 and T1), matched {sorted(rows)}"
```

New text:

```python
    # a design's STEP carries the design's id and a letter (S4a, #283): the same slot, not a fifth design
    assert len(rows) == 20, f"expected twenty index rows (the programme's thirteen, E1, S1, S2, S3, S4, S4a and T1), matched {sorted(rows)}"
```

### 3.8 `docs/specs/README.md` — the index row

**File:** `docs/specs/README.md` — edit

Old text:

```markdown
| S4 | [`SPEC_S4_token_retrieval.md`](SPEC_S4_token_retrieval.md) — retrieving a cluster credential as the fleet account: the challenging-client login, the ServiceAccount token read, the write, and the lifecycle | S — cluster configuration | — | app and chart bumps per step, assigned at each step's PR | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) | specified |
```

New text:

```markdown
| S4 | [`SPEC_S4_token_retrieval.md`](SPEC_S4_token_retrieval.md) — retrieving a cluster credential as the fleet account: the challenging-client login, the ServiceAccount token read, the write, and the lifecycle | S — cluster configuration | — | app and chart bumps per step, assigned at each step's PR | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) | specified |
| S4a | [`SPEC_S4a_fleet_login_session.md`](SPEC_S4a_fleet_login_session.md) — S4 step A: the fleet login session — obtain, expire, retry, revoke; the code of #283 | S — cluster configuration | — | no version change (a module nothing calls yet; the release that first calls it bumps) | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) | in implementation |
```

### 3.9 `docs/CHANGELOG.md` — the Unreleased entry

**File:** `docs/CHANGELOG.md` — edit

Old text:

```markdown
## Unreleased
```

New text:

```markdown
## Unreleased

- **The dashboard can log in to a target cluster as the fleet account — and logs out again (#283; SPEC_S4 step A, `docs/specs/SPEC_S4a_fleet_login_session.md`).** The first code in the tree that can log in, and nothing calls it yet: `gsd/fleetlogin.py` is the library #284's lookup and #285's daily ping will use, so no cluster's behaviour changes with this release and a mode stanza is still listed with its credential pending. It performs the OAuth challenging-client flow `oc login` performs — measured on the reference cluster: the OAuth host is **discovered** from the API server's well-known document (`oauth-openshift.apps-crc.testing` against an API of `api.crc.testing:6443`, which no string surgery derives), the token and its lifetime are read off the **`Location` fragment** of a 302 without following it, and the expiry is returned as an **absolute instant** computed from the target's own `expires_in` — 31536000 s on CRC, 86400 s by OpenShift default — never a hard-coded "daily". **A session is a context manager and revokes its own `OAuthAccessToken` on exit** — after the body ran, after it raised, and when a token was minted but no session could be built — so a lookup or a ping leaves nothing behind by construction. **The retry policy ships with the mechanism**, because a wrong password in a values file would otherwise start a lockout walk against the account the target authenticates *every* user with: a refused password (`401` with a Basic challenge) is **never retried** — one `fleet-login-refused` line quoting the status line and the challenge, then stop; an unreachable target (socket, TLS, timeout, a 5xx) backs off **1, 2, 4, 8 s to a ceiling of five attempts** and then gives up out loud. Three fields join #245's vocabulary — `attempt=<n>/<ceiling>`, `retry_in=<seconds>`, `gave_up=true` — and no new `phase`; every line carries the password and the token as `secrets=`, and a pin drives every event the module can emit with both planted in remote-controlled text and greps the whole log. TLS verification is the cluster's existing `tls_mode`, the poller's own decision, not a second policy. A live test (`local-development/tests/test_live_fleet_login.py`, skipped by default) proves it against a real OAuth server and counts the target's token objects before, during and after the session.
```

## 4. Tests — what fails before and passes after

`tests/test_fleet_login.py` cannot import before the module exists, so every one of its tests fails
on `main` and passes on this head; `test_specs_index.py`'s count and pattern fail on `main` once the
spec file is present (the same failure the S4 spec produced in the baseline run before its row landed).
The one existing test touched indirectly — `test_clusterconfig_logging.py`'s TLS classification of
`_log_poll_failure` — passes on both heads, which is the behaviour-preservation check for §3.3/§3.4.

The requirement-to-test map is §1's table. The assertion that proves no retry on refusal is, in
`TestTheRetryPolicy.test_a_refused_password_is_never_retried`:

```python
        assert len(target.authorize) == 1, "the refusal was retried — that is the lockout walk"
        assert len(target.answers) == 1, "the scripted second answer was consumed"
```

## 5. Verification on the reference cluster

Run from `local-development/` with the poller ServiceAccount's bundle as the CA (it carries the
ingress CA; the dashboard's own injected bundle does not — SPEC_S3 §6) and a cluster-admin
`KUBECONFIG` so the count can be taken:

```
oc -n group-sync-operator get secret group-sync-dashboard-cluster-poller-token \
   -o jsonpath='{.data.ca\.crt}' | base64 -d > /tmp/poller-ca.crt
GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 GSD_LIVE_LOGIN_USER=developer \
GSD_LIVE_LOGIN_PASSWORD=<the htpasswd password> GSD_LIVE_LOGIN_CA=/tmp/poller-ca.crt \
KUBECONFIG=~/.crc/machines/crc/kubeconfig \
.venv/bin/python -m pytest tests/test_live_fleet_login.py -v -s
```

The count the review takes by hand, before and after any session:

```
oc get oauthaccesstokens -o json | python3 -c '
import json,sys; items=json.load(sys.stdin)["items"]
print(sum(1 for i in items if i["userName"]=="developer" and i["clientName"]=="openshift-challenging-client"))'
```

Expected: the number printed before a session equals the number printed after it, and the
`test_live_fleet_login.py` output names `count_before`, `count_during` (before + 1) and `count_after`
(before). The run's actual output is recorded in the session change log and in the pull request.

## 6. What the next steps inherit

- **#284** calls `FleetLogin(cluster, username, password, timeout=settings.request_timeout_seconds)`
  inside `with`, reads the ServiceAccount token during the body, and writes after; the password comes
  from the chart's `passwordSecret` grant (0.49.0). It adds `login-refused` to `FINDING_CODES` and
  the tab's sentence for it, and catches `LoginError` to turn `outcome`/`phase`/`retryable` into the
  finding — nothing here decides what a finding says on the page.
- **#285** builds the per-credential gate on `LoginError.outcome == AUTH_FAILED` — the refusal that
  must suspend the credential everywhere — and schedules renewal from `FleetSession.expires_at`
  with SPEC_S4 §3.1's margin. The `retry_in=`/`gave_up=` lines are what its coordinator reads to
  know a login is still being tried.
- **#286** must not sweep what this module minted: a session revokes its own token, so anything
  left under `openshift-challenging-client` for the fleet account predates this code or survived a
  `fleet-logout-failed` line, which names the object.
