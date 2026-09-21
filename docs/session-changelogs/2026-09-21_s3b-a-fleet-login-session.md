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
