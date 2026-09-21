# SPEC S4a — the fleet login session: obtain, expire, retry, revoke (#283)

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S4 designed the retrieval; this is its step A, the first code in the tree that can log in |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step A, the issue's own label S3b-A) |
| Version on release | no version change (a module nothing calls yet; the release that first calls it bumps) |
| Issue | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) |
| Status | in implementation |
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
| authorize | 302 without `access_token` (or with `#error=`) | `unreachable` | `credential` | **terminal** — the bind happened and the grant failed after it |
| authorize | 302 with a token but `expires_in` missing, non-numeric, ≤ 0 or > 2³¹−1 (`MAX_EXPIRES_IN`) | `unreachable` | `credential` | **the token is revoked at once**, then **terminal** |
| after the token exists | anything that raises before the session is returned (`BaseException`) | — | — | **the token is revoked, once**, and the exception propagates unchanged |

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

A MINTED TOKEN IS NEVER ABANDONED. From the moment the fragment carried a token, nothing leaves the
login without either handing the token to the caller inside a session or revoking it — whatever
raises, including what was not predicted. The lifetime the target states is bounded at int32
(MAX_EXPIRES_IN) because it is remote-controlled and the instant arithmetic is not.

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
                token, expires_in = self._authorize(endpoint)
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
            # FROM HERE THE TOKEN EXISTS ON THE TARGET, and nothing below may leave this frame
            # without either handing it to the caller inside a session or revoking it — whatever
            # raises, including what was not predicted (review of #289: an OverflowError from a
            # remote-controlled expires_in escaped `__enter__` with the token abandoned). `_authorize`
            # revokes before it raises, so this guard begins only once it has returned, and no token
            # is revoked twice.
            try:
                session = FleetSession(cluster=self.cluster.name, account=self.username, token=token,
                                       obtained_at=obtained_at, expires_in=expires_in, issuer=issuer,
                                       attempts=attempt)
                event(log, logging.INFO, "fleet-login", **self._fields(), oauth=issuer,
                      expires_at=session.expires_at_iso,
                      attempt=f"{attempt}/{policy.attempts}" if attempt > 1 else None,
                      secrets=(self._password, token))
            except BaseException:
                self._revoke(token)
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
        parts = urlsplit(endpoint) if isinstance(endpoint, str) else None
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
        issuer = document.get("issuer")
        return (issuer if isinstance(issuer, str) and issuer else f"https://{parts.netloc}"), endpoint

    def _authorize(self, endpoint: str) -> tuple[str, int]:
        """The challenging-client request, and the token read off the redirect's fragment.

        ONCE THE GET CARRYING THE PASSWORD IS ISSUED, EVERY OUTCOME IS TERMINAL (the module
        docstring says why). The one retryable failure here is one provably before the password
        bytes were written: the socket never opened, or the TLS handshake failed.
        """
        host = self._scrub(urlsplit(endpoint).netloc)
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
        if response.status_code == 401:
            # THE REFUSAL, and the one answer that is never retried. Measured (SPEC_S4 §6): a wrong
            # password is a bare 401 with `Www-Authenticate: Basic realm="openshift"` and an empty
            # body — there are no server's words to quote beyond that, and the same 401 answers a
            # username the directory cannot find. A 401 WITHOUT the Basic challenge did not
            # necessarily evaluate the password, so it is not recorded as a refusal; it is not
            # retried either, because retrying a 401 whose cause cannot be read is the lockout walk.
            challenge = self._scrub(response.headers.get("www-authenticate", ""))[:200]
            said = (f"401 Unauthorized from {host}; Www-Authenticate: {challenge or '<absent>'}; "
                    f"body: {self._scrub(response.text)[:200] or '<empty>'}")
            if challenge.strip().lower().startswith("basic"):
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
        fragment = parse_qs(urlsplit(response.headers.get("location", "")).fragment)
        token = (fragment.get("access_token") or [""])[0]
        if not token:
            # The bind happened and the grant failed after it: terminal for the same reason.
            error = (fragment.get("error") or ["<none>"])[0]
            raise LoginError(UNREACHABLE, f"302 from {host} carried no access_token in its Location fragment "
                             f"(error={self._scrub(error)[:100]}, keys={self._scrub(','.join(sorted(fragment)))[:100]}); "
                             f"not retried — the password was sent", phase="credential", retryable=False)
        raw_expiry = (fragment.get("expires_in") or [None])[0]
        try:
            expires_in = int(raw_expiry) if raw_expiry is not None else 0
        except ValueError:
            expires_in = 0
        if not 0 < expires_in <= MAX_EXPIRES_IN:
            # A token WAS minted. Revoke it before saying no session could be built from it, and
            # do not retry into a second one: the fragment's shape is a fact about the target.
            self._revoke(token)
            raise LoginError(UNREACHABLE, f"302 from {host} carried a token without a usable expires_in "
                             f"(got {self._scrub(str(raw_expiry))[:100]!r}; the bound is 1..{MAX_EXPIRES_IN}); "
                             f"the token was revoked", phase="credential", retryable=False)
        return token, expires_in

    # ── the logout ───────────────────────────────────────────────────────────────────────────

    def _revoke(self, token: str) -> None:
        """`oc logout`: DELETE the OAuthAccessToken by name, authorised by the token itself. Never
        raises — it runs from `__exit__`, where an exception would replace the body's own — and a
        failure is said out loud with the object's name, because that token is now litter on the
        target and #286's sweep deletes nothing it did not create.

        The object is gone the moment the DELETE answers 200. The token itself may go on authenticating
        from the API server's token cache for about two minutes (121 s measured on the reference
        cluster) — a fact for #285's "a 401 means re-authenticate" rule, not litter: nothing on the
        target names it any more, and `oc get oauthaccesstokens` shows it gone at once."""
        name = token_object_name(token)
        shown = name if token.startswith(TOKEN_PREFIX) else None   # an unprefixed name IS the token
        secrets = (self._password, token)
        try:
            response = self._client.delete(f"{USER_TOKEN_API}/{name}",
                                           headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
        except httpx.HTTPError as exc:
            problem = self._transport_error(exc, token)
            phase, outcome, detail = problem.phase, UNREACHABLE, problem.message
        else:
            if response.status_code in (200, 404):
                # Revoked, or the object is already gone. ONLY a 404 means gone: a 401 says the DELETE
                # was not authenticated and nothing about the object (review of #289, Codex).
                event(log, logging.INFO, "fleet-logout", **self._fields(), token=shown,
                      outcome="revoked" if response.status_code == 200 else "already-gone", secrets=secrets)
                return
            body = self._scrub(response.text, token)[:200] or "<empty body>"
            if response.status_code == 401:
                phase, outcome = "credential", AUTH_FAILED
                detail = (f"401 Unauthorized on DELETE {USER_TOKEN_API}/<name>: the token did not authorise "
                          f"its own revoke, so the object may still exist — {body}")
            else:
                phase, outcome = "poll", UNREACHABLE
                detail = f"HTTP {response.status_code} on DELETE {USER_TOKEN_API}/<name>: revoke refused — {body}"
        failure(log, "fleet-logout-failed", phase=phase, outcome=outcome, **self._fields(), token=shown,
                action=("the OAuthAccessToken may still be on the target and nothing here will try again: "
                        "delete it there as cluster-admin (oc delete oauthaccesstoken <token>) so it does "
                        "not become litter"),
                detail=detail, secrets=secrets)

    # ── the vocabulary ───────────────────────────────────────────────────────────────────────

    def _fields(self) -> dict[str, str]:
        mode = self.cluster.tls_mode
        return {"cluster": self.cluster.name, "account": self.username,
                "tls": "insecure" if mode["insecure"] else mode["ca"]}

    def _scrub(self, text: str, *more: str | None) -> str:
        """Every secret in play out of `text`, in both spellings the two helpers know: `gsd.kube`'s
        JSON-escaped forms and the emit helper's shorter floor. Before any truncation, always."""
        secrets = (self._password, *more)
        return redact(redact_text(text, *secrets), secrets)

    def _transport_error(self, exc: httpx.HTTPError, *more: str | None, retryable: bool = True) -> LoginError:
        """A transport failure in the one shape this process gives one — `<ExceptionType>: <text>`,
        which `is_verify_failure` and the poller's classifier both key on. Whether it may be retried
        is the caller's to say: it depends on whether the password was on the wire, not on the
        exception."""
        message = self._scrub(f"{type(exc).__name__}: {exc}", *more)
        return LoginError(UNREACHABLE, message, phase="tls" if is_verify_failure(message) else "connect",
                          retryable=retryable)

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
import logging
import pathlib
from datetime import UTC, datetime, timedelta, timezone

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
         clock=None) -> tuple[FleetLogin, list[float]]:
    """A FleetLogin wired to the fake target, with the sleeps it asked for recorded and the clock
    held at T0 unless the test brings its own."""
    cluster = cluster or ClusterConfig("east", API, insecure_skip_verify=True)
    sleeps: list[float] = []
    fl = FleetLogin(cluster, USER, PASSWORD, policy=policy, sleep=sleeps.append, clock=clock or (lambda: T0))
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
        assert len(target.revokes) == 1, "the token must be revoked exactly once"
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
        assert "revoked" in exc.value.message


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
        assert len(target.revokes) == 1, "revoked exactly once"
        assert target.requests[-1].url.path == f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"

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
            failing(Target(httpx.Response(401, text=f"csrf pw={PASSWORD}")))                # not a refusal, stopped
            failing(Target(login_302(expires_in=f"{PASSWORD}")))                            # revoke inside the login
            failing(Target(httpx.Response(503, text=f"down pw={PASSWORD}")))                # terminal HTTP answer
            failing(Target(lambda request: httpx.ReadTimeout(f"timed out pw={PASSWORD}")))  # terminal transport
            with make(Target(login_302()))[0]:                                              # fleet-login, fleet-logout
                pass
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
        assert len(errors) == 9
        for exc in errors:
            assert PASSWORD not in exc.message and PASSWORD not in str(exc), exc.message
            assert TOKEN not in exc.message

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
