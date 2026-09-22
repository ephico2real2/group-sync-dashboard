# Session change log — group-sync-dashboard, 2026-09-21 (OB1: #283, the fleet login session)

What this session did, when, and how each claim was measured. Times are git author times in
America/Chicago. Every "measured" claim below is one the session ran a command for; nothing here is
recalled from memory alone. The product changelog (`docs/CHANGELOG.md`) says what each release
changed for an operator; this says what a working session did. The session is OB1's implementation of
issue #283 under the S3b programme board (#288), spec-first from `docs/specs/SPEC_S4a_fleet_login_session.md`.

Outcome in one line: **pending**

| | Before the session | After |
|---|---|---|
| main | `0cf1030` (#287 merged: SPEC_S4 on main) | pending |
| chart / app | 0.49.0 / 0.30.0 | pending |
| #283 | open, no branch; the issue's precondition section superseded by SPEC_S4 §10.1 | pending |
| open PRs | none | pending |
| the lab (CRC) | `developer` / `openshift-challenging-client` OAuthAccessToken count: 0 | pending |

---

## Part 1 — #283: the login session, spec first (2026-09-21)

### The spec, the module and the proof (16:0x → 17:37) — commit `aefe7aa`, PR #289

- Read in full before writing anything: issue #283, board #288, `docs/specs/SPEC_S4_token_retrieval.md`
  (all 304 lines; §3, §3.1, §5, §6, §8, §9 binding), `docs/specs/SPEC_S3_connection_modes.md`,
  `gsd/auditlog.py`, `gsd/kube.py#ClusterError`, `gsd/clusterconfig/events.py`, `gsd/poller.py#_log_poll_failure`,
  `charts/group-sync-dashboard/templates/fleet-account-rbac.yaml`.
- **Measured** the mechanism on CRC with the htpasswd `developer` account (`oc get user developer` →
  identity `developer:developer`; provider `developer:HTPasswd`), never the LDAP fleet account: discovery
  document names `https://oauth-openshift.apps-crc.testing/oauth/authorize`; the login answers **302,
  0-byte body**, fragment keys `access_token, expires_in, scope, token_type`, `expires_in=31536000`;
  the derived object name matched the server's (`userName=developer`, `expiresIn=31536000`); `DELETE
  useroauthaccesstokens/<name>` as the token's own user → **200**; 0.51 s end to end.
- **Found by the measurement, mine:** the CSRF probe (no `X-CSRF-Token`) answered 302 and minted a
  second token I had not captured — SPEC_S4 §6's "returns 401" did not reproduce. Revoked it as
  cluster-admin (`oc delete oauthaccesstoken sha256~00H6…`); count for `developer`/challenging-client
  back to **0** before any further work. Recorded in the spec's notes.
- Wrote `docs/specs/SPEC_S4a_fleet_login_session.md` with every change as a fenced block, then applied
  it with a script that writes whole-file blocks verbatim and refuses an edit whose Old text does not
  match exactly once. **Three deviations, all recorded in the spec with the reason:** the CHANGELOG
  Old text quoted a one-line bullet as two lines (refused by the script, corrected to anchor on the
  heading); two test assertions grepped prose (`gave_up` in an `action=` sentence, `sched` in the
  docstring) and were rewritten as field-syntax and AST assertions. The module's Python block applied
  verbatim on the first pass and was not changed.
- `tests/test_fleet_login.py`: **5 failed / 39 passed** on the first run (the two prose greps), **44
  passed** after the spec correction. Mutation check: refusal made `retryable=True` → 2 tests fail;
  revoke removed from `__exit__` → 6 tests fail.
- **Found by the live run, mine:** the first live test asserted a 401 on the first request after the
  session closed; CRC answered **200**. Re-measured once a second: the object was absent from
  `oc get oauthaccesstokens` at once (count **0 → 1 → 0**, the name present during and gone after) and
  the revoked token authenticated for **121 s** before 401 — the API server's token authenticator
  cache. Spec §2, the `_revoke` docstring and the live test corrected (it waits for the death, up to
  `GSD_LIVE_LOGIN_DEAD_WAIT`); second live run **1 passed in 121.00 s**, manual count 0 before / 0 after.
- Full hermetic suite on the head: **4622 passed, 16 skipped, 563 deselected in 227.98 s** (baseline
  on `a94e6c1` before #287's index row: 4566 passed, 2 failed — both `test_specs_index.py`, fixed by #287).
- `docs/specs/README.md` row `S4a`, `test_specs_index.py` id pattern `[A-Z]\d[a-z]?` and count 20,
  `docs/CHANGELOG.md` Unreleased entry. No chart change, no version bump.
- Review: pending (Codex + OB seats per #288's loop; Cursor cannot execute, measured by the orchestrator).

### The review's six findings (18:2x → 18:17) — commit `d6e5759`, PR #289

- Three seats (Codex gpt-5.6-sol xhigh, Cursor Grok 4.6, OB1-lite) reviewed head `aefe7aa`; C1/C3/C5/C8/C9
  **CONFIRMED** by all three; six findings, each decided by the business owner and recorded in
  `docs/REVIEW_S4a.md`. Every fix was written into `docs/specs/SPEC_S4a_fleet_login_session.md`'s blocks
  first (its notes carry the deviations and the inverted tests) and the files regenerated from the spec.
- **Found by all three, accepted:** a remote-controlled `expires_in` overflowed the instant arithmetic and
  the minted token was abandoned (Codex measured `authorize_count 1 delete_count 0`); bounded at int32
  and guarded by a `BaseException` revoke — both halves. **Found by all three, the strict rule accepted,
  OB1-lite's narrower retry set rejected:** every answer after the password is on the wire is terminal;
  only `ConnectError`/`ConnectTimeout` retry (upstream: 401 only for LDAP codes 48/49, 500 for all else,
  a locked account's code 19 included). **Found by Codex alone, accepted:** a 401 on the revoke is not
  "already gone". **Found by all three, accepted:** three raise sites left `str(exc)` unscrubbed. **Found
  by Cursor and OB1-lite, accepted:** the name test was circular — pinned to the `openssl` literal (re-run
  by OB1: `AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY`, identical). **Found by Codex, accepted:** a
  non-UTC injected clock.
- The corrected `tests/test_fleet_login.py` against the PREVIOUS module (the new constant shimmed in so
  it imports): **18 failed / 40 passed**; against this head: **58 passed**. Four tests inverted because
  they asserted the defect (named in the spec's notes and the review record).
- Full hermetic suite on this head: **4641 passed, 16 skipped, 563 deselected in 227.21 s**. Doc checks
  over the review record: 1065 passed.
- Live on CRC as `developer` after the fix: count **0 → 1 → 0**, the session's name present during and
  gone after, the revoked token dead after **121 s**; manual `oc` count 0 before / 0 after.

### The confirmation pass's seven findings (19:0x → 19:03) — commits `00f862e` (merge of main), `1bded21`, PR #289

- `origin/main` merged in first (#290, SPEC_S4 §9's renewal formula) so CI runs on a current head.
- Codex (harness) and Cursor (reading) on `28d4bec`: **not mergeable**, seven residual defects, one
  introduced by P1-2; Codex's measured result wins where they disagree. All seven **accepted**,
  written into the spec's blocks first, recorded in `docs/REVIEW_S4a.md`'s "Confirmation pass".
- **Found while applying R2-1, mine (measured):** the first test's hostile `Location`
  (`https://[::1/…`) was refused by httpx itself — `RemoteProtocolError` from
  `_send_handling_redirects`, which builds the redirect request even with `follow_redirects=False` —
  so the 302 never reached the module. The measured case Codex hit is `https://example.com]/…`:
  delivered as a 302, `urlsplit` raises. The test uses that; the limit (a token this process never
  sees) is recorded in the module docstring beside the read timeout.
- The invariant **restated** at the owner's instruction: revocation is attempted exactly once and a
  failure is surfaced, never swallowed; `FleetLogin.revoked` carries the answer. Nothing shared
  (`events.redact`, `kube.redact_text`) changed.
- The corrected `tests/test_fleet_login.py` against the previous module: **10 failed / 54 passed**
  (the `Basic` case reproduced Codex's `unreachable`); against this head: **64 passed**.
- Full hermetic suite: **4648 passed, 16 skipped, 563 deselected in 230.06 s**. Doc checks: 990 passed.
- Live on CRC as `developer`: count **0 → 1 → 0**, name present during and gone after, the revoked
  token dead after **121 s**; manual `oc` count 0 before / 0 after.
