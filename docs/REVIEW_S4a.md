# Review record — PR #289, S4a: the fleet login session (#283)

The adversarial pass on PR #289 (`feat/283-fleet-login-session`, head `aefe7aa`), three seats:
**Codex** (gpt-5.6-sol, xhigh), **Cursor** (Grok 4.6) and **OB1-lite** (Fable 5.1, default). Every
finding was traced and its underlying claim verified against upstream OpenShift source by the
business owner before a decision; where seats disagreed, the business owner decided. The fixes were
written into `docs/specs/SPEC_S4a_fleet_login_session.md` first (its "Orchestrator's notes" carry the
deviations) and the code regenerated from the spec's blocks, as the original implementation was.

The claims are the spec's requirements R1–R8 and the brief's claim ids as the orchestrator numbered
them; the brief's claim text lives with the orchestrator and is not reproduced here.

## Claims confirmed

| claim | Codex | Cursor | OB1-lite | decision |
|---|---|---|---|---|
| C1 | CONFIRMED | CONFIRMED | CONFIRMED | stands |
| C3 | CONFIRMED | CONFIRMED | CONFIRMED | stands |
| C5 | CONFIRMED | CONFIRMED | CONFIRMED | stands |
| C8 | CONFIRMED | CONFIRMED | CONFIRMED | stands |
| C9 | CONFIRMED | CONFIRMED | CONFIRMED | stands |

## Findings, verdicts and decisions

| # | finding | Codex | Cursor | OB1-lite | decision | reason |
|---|---|---|---|---|---|---|
| P0-1 | A remote-controlled `expires_in` (`999999999999999`) passes `int()` and the `<= 0` guard, then `expires_at_iso` raises `OverflowError` — not a `LoginError` — before `self.session` is set, so `__exit__` never revokes; the minted token is abandoned. Codex measured `authorize_count 1 delete_count 0`. | found | found | found | **accepted, both halves** | `MAX_EXPIRES_IN = 2**31 - 1` bounds the value at the source (`OAuthClient.accessTokenMaxAgeSeconds` is an int32 in `oauth.openshift.io/v1`); and `gsd/fleetlogin.py#FleetLogin._login` wraps everything from "the token exists" to "the session is returned" in a `BaseException` guard that revokes and re-raises, because the invariant — a minted token is never abandoned — must hold for exceptions nobody predicted. `_authorize` revokes before it raises, so the guard begins only once it has returned; the tests assert the DELETE count is exactly one. Tests: `test_an_expiry_beyond_int32_is_bounded_revoked_once_and_terminal`, `test_a_token_is_never_abandoned_whatever_raises_after_it_was_minted`. |
| P0-2 | The authorize step is retried after the password is on the wire: every non-302 was `retryable=True`, and `_transport_error` was retryable for read timeouts. Codex's harness: `200 → 5 binds`, `403 → 5`, `429 → 5`, `500 → 5`. | found; every HTTP answer terminal | found; every HTTP answer terminal | found; proposed keeping `429/502/503/504` retryable | **accepted — the STRICT rule; OB1-lite's narrower set REJECTED** | Verified by the business owner in upstream source: `pkg/authenticator/password/ldappassword/ldap.go` returns `nil, false, nil` (→ 401) only for LDAP result codes 48 and 49 and `nil, false, err` (→ 500 through `pkg/osinserver/defaults.go` `HandleError`) for every other result — including code 19, `Exceeded password retry limit`, what a directory that has **already locked** the account answers. So a "5xx is transient" rule retries hardest exactly when the account is locked. OB1-lite's set fails by its own reasoning: a `504` means the upstream took too long having *received* the request and may have bound; a `502` that it answered malformed having received it. The line is therefore whether the password bytes were written: only `httpx.ConnectError` and `httpx.ConnectTimeout` are retried on the authorize step; a `ReadTimeout`/`WriteError`/`ReadError`/`RemoteProtocolError`, every HTTP status that is not a usable 302, and a 302 without `access_token` are terminal. `_discover` sends no password and is unchanged. The asymmetry is the argument, stated in the module docstring and the spec's §3.1: a wrong retry is an estate-wide outage; a missed retry is one delayed login that #285's daily ping picks up. Tests: `test_once_the_password_is_on_the_wire_every_answer_is_terminal` (eleven cases, one bind each), `test_a_target_that_never_took_the_request_is_retried_with_exponential_backoff`. |
| P1-1 | A `401` on the revoke was recorded as "already gone". A 401 proves only that the DELETE was unauthenticated; the object may be alive, and a successful logout would be logged for a token still valid on the target. | found | missed | missed | **accepted** | Only a `404` means gone. A `401` is now `fleet-logout-failed phase=credential outcome=auth_failed` in its own words ("the token did not authorise its own revoke, so the object may still exist"); the log distinguishes `outcome=revoked`, `outcome=already-gone` and "revoke refused". Test: `test_a_401_on_the_revoke_is_a_failure_not_already_gone`; the former test's 401 case inverted. |
| P1-2 | `LoginError`'s docstring claimed every raise site scrubs the message; three did not — the endpoint's netloc (userinfo), the raw `Www-Authenticate` challenge, the raw `expires_in` via `!r`. The log was clean (emit-side redaction); `str(exc)` was not, and #284 will put that message on the page. | found | found | found | **accepted** | All three scrubbed through `_scrub`; an `authorization_endpoint` carrying userinfo is refused outright and never quoted. The pin now plants the password in every remote-controlled field — body, challenge, `Location` error query, discovery userinfo, `expires_in`, transport text — and asserts on the nine `LoginError`s as well as the log. Test: `TestTheRedactionPin::test_the_error_handed_to_the_caller_carries_no_password`. |
| P2-1 | `test_the_object_name_is_the_measured_derivation` recomputed the formula it tested, so a wrong formula — every DELETE answering 404 while the suite stayed green — would pass. | — | found | found | **accepted** | The test pins the literal `token_object_name("sha256~testsecret123") == "sha256~AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY"`, derived by the business owner with `openssl` (not Python), confirmed against the deployed pod and a live `OAuthAccessToken`, and re-derived by OB1 with the same `openssl` pipeline (identical). The comment says it must never be regenerated from the code under test. |
| P2-2 | An injected non-UTC or naive `clock` produced a `Z`-suffixed instant that was not UTC; production `_utcnow()` was fine. | found | — | — | **accepted** | `_as_utc` normalises an aware reading and refuses a naive one before anything is minted; `FleetSession.__post_init__` refuses a naive `obtained_at`; `expires_at_iso` formats through `astimezone(UTC)`. Test: `test_a_non_utc_clock_is_normalised_and_a_naive_one_refused`. |

## Tests inverted (they asserted the defect)

| before | after |
|---|---|
| `test_a_302_without_a_token_is_not_a_session_and_is_retried_within_the_ceiling` — 2 binds | `test_a_302_without_a_token_is_not_a_session_and_is_terminal` — 1 bind, no sleep, no DELETE |
| `test_an_unreachable_target_is_retried_with_exponential_backoff[read-timeout, http-503]` — the password sent three times | cases moved to `test_once_the_password_is_on_the_wire_every_answer_is_terminal`; the retried cases are `ConnectError`, `ConnectTimeout` and a TLS handshake failure under `test_a_target_that_never_took_the_request_is_retried_with_exponential_backoff` |
| `test_an_already_gone_token_is_not_a_failure` over `(404, 401)` | `404` only; `401` under `test_a_401_on_the_revoke_is_a_failure_not_already_gone` |
| `test_the_object_name_is_the_measured_derivation` recomputing the formula | the `openssl`-derived literal |

## Verification

The corrected `tests/test_fleet_login.py` run against the **previous** module (`aefe7aa`'s
`gsd/fleetlogin.py`) and against the fixed one, and the full hermetic suite on the fixed head, are
recorded with their counts in `docs/session-changelogs/2026-09-21_s3b-a-fleet-login-session.md` and
on PR #289.

## Confirmation pass on `28d4bec`

Codex ran a harness; Cursor read the source (it has no shell in this session and said so), so where
the two disagreed Codex's measured result won. Both said not mergeable; seven residual defects, one
introduced by P1-2. Every fix was written into the spec's blocks first (its notes carry the record)
and the files regenerated.

| # | finding | Codex | Cursor | decision | reason and fix |
|---|---|---|---|---|---|
| R2-1 (P0) | A hostile `Location` still leaks a minted token: `urlsplit()` raised `ValueError: Invalid IPv6 URL` before the token was read (`authorize=1 DELETE=0`), and the P0-1 guard began only after `_authorize` returned. | measured | — | **accepted** | `gsd/fleetlogin.py#FleetLogin._token_from` splits the header on its first `#` and parses the fragment alone — the rest of the URL is never validated — and `_login`'s guard begins the moment the token is bound, with `_expiry_from`, the session and the success line inside it. Measured while applying: `https://example.com]/…` (Codex's shape) is delivered by httpx and makes `urlsplit` raise; `https://[::1/…` is refused by httpx itself in `_send_handling_redirects`, which builds the redirect request even with `follow_redirects=False`, so a token behind such a header is one this process never sees — recorded in the module docstring beside the read timeout as #286's litter. Test: `test_a_hostile_location_never_stands_between_the_mint_and_the_revoke`. |
| R2-2 (P1) | A failure during cleanup replaced the original exception (`raised=RuntimeError original=Marker`). | measured | — | **accepted** | `_revoke_quietly` surfaces anything `_revoke` raises as a `fleet-logout-failed` line and answers False; the guard and `__exit__` both go through it, and the original exception propagates. Test: `test_a_failure_during_cleanup_never_replaces_the_original_exception`. |
| R2-3 (P1) | A DELETE answering 500 was reported to the caller as revoked (`DELETE=1 caller_says_revoked=True`); "revoked exactly once" is not an achievable invariant. | measured | — | **accepted; the invariant restated** | *Revocation is attempted exactly once, and a failure is surfaced, never swallowed.* `_revoke` returns whether the target said gone (200/404 only); `FleetLogin.revoked` carries it to the caller; the `expires_in` stop's message says the attempt was made and points at the `fleet-logout` line rather than claiming a result. The module docstring, spec §3.1 and every assertion use the new wording. Test: `test_a_revoke_that_failed_is_surfaced_never_reported_as_revoked`. |
| R2-4 (P1) | A password shorter than the shared floors (`events.redact` 4, `kube.redact_text` 8) was redacted nowhere. | measured | — | **accepted, locally** | The shared floors are **not changed** — they keep ordinary short strings intact across every log in the codebase. `_scrub` redacts the credential this class holds regardless of length, after the two helpers, longest first. Test: `test_a_password_shorter_than_the_shared_floors_is_still_redacted` (a 3-character password). |
| R2-5 (P1) | The `ValueError` from parsing a hostile `authorization_endpoint` reached the caller unscrubbed, carrying userinfo (`str_leak=True`). | measured | — | **accepted** | Caught in `_discover`, scrubbed, a non-retryable `connect` stop. Test: `test_a_discovery_endpoint_that_does_not_parse_is_a_scrubbed_stop`, and the pin plants it. |
| R2-6 (P1) | `issuer` is a remote field never scrubbed and never planted. | — | found | **accepted** | Scrubbed in `_discover`; the pin plants the password in it and asserts on `session.issuer` and the log (`TestTheRedactionPin._drive_everything`). |
| R2-7 (P2) | A regression from P1-2: the challenge was scrubbed before it was classified, so a password literally `Basic` turned a genuine refusal into `outcome=unreachable`. | measured | — | **accepted** | The raw header decides `is_basic`; only the quoted copy is scrubbed. Decide, then redact. Test: `test_a_password_that_is_literally_basic_still_classifies_the_refusal`. |
| — | `test_a_token_is_never_abandoned…` raised only from the success line, missing the parsing interval. | noted | — | **accepted** | The test also raises from inside `_expiry_from`. |

Confirmed on this pass and unchanged: the P0-1 bound, the P0-2 strict rule, P1-1 (401 is not gone),
P2-1 and P2-2.
