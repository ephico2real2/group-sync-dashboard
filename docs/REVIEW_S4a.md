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

### A gap in what the suite could prove — closed after the confirmation pass

Both reviewers raised **"API CA ≠ ingress CA"** as a plausible operational risk for the first non-CRC
cluster. The business owner measured why it had never been caught: **the reference lab is
structurally blind to it.** CRC's `kube-root-ca.crt` (the poller ServiceAccount's `ca.crt`) carries
six certificates, re-measured by OB1 with `openssl x509 -noout -subject`:

```
c0  OU=openshift, CN=kube-apiserver-lb-signer
c1  OU=openshift, CN=kube-apiserver-localhost-signer
c2  OU=openshift, CN=kube-apiserver-service-network-signer
c3  CN=openshift-kube-apiserver-operator_localhost-recovery-serving-signer@1785325898
c4  CN=*.apps-crc.testing                       <- the ingress LEAF
c5  CN=ingress-operator@1785325954              <- the ingress CA
```

So an API-only bundle verifies the OAuth host on CRC, and the split cannot occur there; a green CRC
run is not proof that a customer bundle is sufficient. On a cluster whose ingress is re-signed by an
enterprise PKI the login fails at the authorize step, after discovery succeeded. Two cautions the
owner recorded from building the reproduction: `curl` on a Mac gives a false pass (it falls back to
the system keychain, which trusts the CRC ingress CA) — verify TLS with Python's `ssl`; and a CA made
with a bare `openssl req -x509` lacks `basicConstraints`/`keyUsage`, so the failure reads
`CA cert does not include key usage extension` rather than the real `unable to get local issuer
certificate`.

| decision | what landed |
|---|---|
| **accepted: a permanent hermetic test, no cluster** | `TestTheSplitCATheLabCannotShow` in `local-development/tests/test_fleet_login.py`: two CAs generated per test with `openssl` under `tmp_path` (proper CA extensions, SAN `localhost`/`127.0.0.1`, `serverAuth`), CA A signing a loopback API server that serves the discovery document, CA B signing a loopback OAuth server that records every `Authorization` header; the bundle carries only A. Assertions in the owner's order: the credential never reached the OAuth host; discovery succeeded first; `phase=tls outcome=unreachable retryable=True`, two attempts; no password in `str(exc)` or the log; the `gave_up` action names the ingress CA. |
| **accepted: the control** | The same fixture with both CAs reaches the OAuth host exactly once (`Basic …`) and stops on the fixture's token-less 302 (`retryable=False`), so zero hits cannot be mistaken for a broken fixture. |
| `cryptography` vs `openssl` | `cryptography` is not a dependency of this project; the fixture shells out to `openssl` (OpenSSL 3.6.4 on the machine that ran it) and skips cleanly without it. No key material is committed. |
| the configuration contract | **not implemented here** — it is #284's (the owner posted the measurement there); the spec's §2.1 and this record say only that the lab cannot show the failure. |

## Third pass on the restructured control flow (with the CI-skip change)

Codex, harness-driven: all 21 `httpx.HTTPError` classes, statuses 100–599, exceptions injected
inside the new helpers. E1 (the lockout property is total) and E5 (no message or log leakage) clean.
Four findings, batched with the CI-skip change. **One of the four is a reversal of an orchestrator
decision, not a reviewer finding, and is marked as such.**

| # | finding | source | decision | reason and fix |
|---|---|---|---|---|
| R3-1 (P0) | The cleanup guard was still one step too late: an interruption inside `_token_from`, after the token was bound, measured `authorize=1 DELETE=0`. The third iteration of the same window — each refactor moved "the moment the token is bound". | Codex, measured | **accepted — made structural, not moved** | The guard in `gsd/fleetlogin.py#FleetLogin._login` is anchored on the **response**, not on any later binding: on any exception it re-reads the token off the response's own `Location` header (`_token_in`, pure and total, split on the first `#`) and revokes it. There is no line between "the token exists in this process" and "an exception here revokes it", because the response has carried it since the request returned, and no future refactor of the extraction can reopen the window. The boundaries Codex confirmed (expiry `0`, `-1`, non-numeric, `MAX+1`, `1`, `MAX`) stay: nothing inside the guard revokes, so revocation is attempted exactly once. Test: `test_an_interruption_inside_the_extraction_still_revokes` — `parse_qs` raises inside the extraction on its first call; DELETE count 1. |
| R3-2 (P1) | `revoked` lied two ways: the guard's revoke discarded the answer (invalid expiry + DELETE 200 → `revoked is None`), and a `fleet-logout` emitter failing after a 200 gave `revoked=False` with a line falsely saying the revoke "failed before the target answered". | Codex, measured | **accepted** | `_delete_token` is the wire only and answers as a value (`_RevokeAnswer`); `_revoke` — the one boundary every site goes through — records `revoked` from what the target said **before** writing the line, and a line that fails to write falls back to the stdlib logger without touching `revoked`. Test: `test_revoked_is_what_the_target_answered_from_every_site`. |
| **R3-3 (P1)** | **A reversal of the orchestrator's round-2 decision** ("make `_scrub` redact the credential regardless of length"). Measured harms: password `app` → issuer `https://oauth-openshift.<redacted>s.example.com`; password `certificate` → `ConnectError: certificate verify failed` no longer classifies, `phase=connect` instead of `tls` — R2-7's defect in a new place: a scrub altering a string the code derives meaning from. | Codex measured it; **the orchestrator's call was wrong** and is retracted here | **corrected — scoped, not reverted** | Three rules, now general in the module: (1) never scrub a classification input — the 401 challenge and the transport message are classified raw, only the displayed copy is scrubbed (`_transport_error`); (2) never scrub a structured value the operator acts on — the issuer and the endpoint's host are never substring-redacted; userinfo is stripped from the issuer **structurally** (`_without_userinfo` rebuilds `scheme://host/path`), so a legitimate host containing the password survives; (3) length-agnostic redaction stays only for free remote text (bodies, challenge values, error strings). Tests: `test_a_password_that_is_a_substring_of_a_host_leaves_the_issuer_intact`, `test_a_password_that_is_a_classification_word_does_not_change_the_phase`, `test_userinfo_in_the_issuer_is_stripped_structurally`. |
| R3-4 (P2) | The round-2 rewording ("attempted") flattened the outcomes: a test accepted `revoked=None`, and DELETE 200 and 500 satisfied the same assertions. | Codex | **accepted** | With `revoked` truthful, every revoke test asserts the value per status: 200 → True, 404 → True, 500 → False, 401 → False, including on the expiry-stop path (`test_a_revoke_that_failed_is_surfaced_never_reported_as_revoked`, `test_a_token_without_a_usable_expiry…`). |

### The CI-skip change (the business owner, between the passes)

A `-q` CI log cannot show whether the split-CA pair ran or skipped, and the local/CI counts
reconciled under both hypotheses. The skip is a developer-machine courtesy only: under `CI` a missing
`openssl` **fails** the tests (`_require_openssl`), matching the suite's existing convention for a
tool a proof depends on (`test_chart_grafana_dashboard.py`, promtool) rather than a new marker. Proven
locally in both directions (skip with `CI` unset; `Failed: … must never be skipped here` with
`CI=true`). `cryptography` stays out — a dependency added to avoid a shell-out that works on every
runner and Mac is not worth it. The servers run on daemon threads shut down in the fixture's
`finally`; a bind failure on the second server closes the first; `handle_error` is consulted only for
an exception while handling an accepted connection, so it cannot hide a bind failure. The CI counts
before and after are on PR #289: on `28d4bec` (before the pair) `4643 passed, 13 skipped`; on
`0169ce7` (with it) `4652 passed, 13 skipped` — the skipped count did not move across the addition of
two skippable tests, which already says they ran.

## Final scoped pass (round five)

The pass could execute nothing — its checkout had no `httpx`/`pytest` and no network — so nothing in
it was measured by the reviewer; **every claim was verified by the business owner on this head**,
and re-measured by OB1 before the fix was written. One claim was refuted and is recorded here with
the measurement, because a record that lists only accepted findings overstates the reviewers.
**F2 passed**: `revoked` is truthful from every site, the guard and `__exit__` share the boundary,
state is recorded before logging, no double-revoke on any expiry boundary; the structural guard
covers the previous window inside `_token_from`. R3-2 is closed; the guard's shape is unchanged.

| # | claim | verdict | decision | reason and fix |
|---|---|---|---|---|
| R5-1 (P0) | Duplicate `Location` headers defeat `_token_in`: httpx **comma-joins** repeated headers in `get`, and a first-`#` split of the joined string never sees a token carried by the second header — a minted token the guard cannot name. Owner's measurement on this head: `_token_in returns: None`; OB1 re-measured the same. | **real** | **accepted** | The structural fix is sound (there is still no line between "the token exists" and "an exception revokes it"); what failed was the guard's ability to *name* the token, so the naming is fixed and the guard is not reshaped. `gsd/fleetlogin.py#FleetLogin._fragments_of` reads **every** `Location` value (`headers.get_list`) and, within each, every `#`-segment — which also covers the case `get_list` alone would miss, a proxy that joined the duplicates itself into one value holding two URLs (measured: the joined value's second segment parses to the token). `_fragment_of` picks the first fragment carrying an `access_token`, else the first, else empty, and **both** the session path (`_token_from`) and the guard (`_token_in`) read that one, so they cannot disagree about which token exists. Tests: `test_a_token_in_a_second_location_header_is_still_named` — token in the second header, the first, and a single header; the session path and, on the error path, DELETE count 1 with `revoked is True`; plus the pre-joined value. |
| R5-2 (P2) | `return response` sat outside `_authorize`'s `try`; an interruption in that instruction window precedes the response-anchored guard. | narrow but valid | **accepted** | The `return` moved into the protected region (`try/except/else`). What remains is the store into `_login`'s local after the call returns — one bytecode, inherent to any call boundary — stated in the code rather than claimed closed. Test: an AST check that `_authorize`'s only `return` is inside its `Try` (`test_authorize_returns_from_inside_its_protected_region`). |
| R5-3 (P2) | `_revoke` derived the object name for the log before the wire (and `_delete_token` again); a failure there prevented the DELETE and, escaping `_revoke`, would replace the original exception; the fallback logger was unprotected. | narrow but valid | **accepted** | Nothing is computed before the wire that the wire does not need: the name is derived once inside `_delete_token` and returned on the answer; the fallback logger is wrapped so cleanup can never raise; `_text_of` guards a `str(exc)` that raises. Test: `token_object_name` patched to raise — the body's exception still propagates, `revoked is False`, a line is written; the fallback logger patched to raise — the original exception still propagates. |
| R5-4 (P3) | `_without_userinfo` returned `https://:bad/x` and `https://host:bad/x` instead of falling back. | valid, display-only | **accepted** | `hostname` must be present and `.port` must parse; otherwise the endpoint's host is used. Test: both inputs fall back. |
| — | **REFUTED:** an enormous fragment could make `parse_qs` raise during cleanup. | **false — owner's measurement:** `parse_qs with 200,000 fields: OK (did not raise)`; OB1 re-measured 200 000 fields → 200 000 keys, no raise | **rejected, not implemented** | Python's `parse_qs` enforces a field limit only when `max_num_fields` is passed, and it is not. No guard was added and no test written. |
