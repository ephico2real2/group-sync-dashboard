# Review — PR #118 (#116): the mock OpenShift API (mock-app)

Adversarial pass, 2026-09-14, on an eight-claim brief for the mock cluster (`local-development/mock-app/`):
TLS/CA fidelity, the ~13 consumed API paths + SAR, CRD/apiVersion fidelity, test non-vacuity, portability,
the CI workflow, and the next real use. Codex ran `gpt-5.6-sol`/xhigh with a shell (it executed a real TLS
handshake, drove a TestClient over the reference fixture, and ran the four personas through `SarAuthorizer`;
its sandbox refused a writable tmp so it could not run the full 42-test suite or bind a socket — those it
marked and the orchestrator ran). Cursor ran `cursor-grok-4.6-high-fast` in ask mode, source only. Every
accepted fix was applied and the mock-app suite run to green here (55 tests; the orchestrator has a writable
tmp Codex lacked).

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 TLS/CA real, drives `verify()` mode 2 | CONFIRMED | CONFIRMED | **Accepted a gap**: the leaf was valid 1h back / 1d forward — a >24h Form-B lab or a >1h-behind runner clock fails. Widened to 1 day back / 30 days forward |
| C2 the consumed paths are byte-identical; `redirect_slashes=False` | CONFIRMED | CONFIRMED | — |
| C3 SAR contract + the four personas | **REFUTED** | CONFIRMED w/ gap | **Accepted**: `_subject_intersects` ignored `kind: ServiceAccount` — a CRB to an SA denied the canonical `system:serviceaccount:<ns>:<name>` user. The in-code comment claiming "no extra handling needed" was WRONG (it conflated the binding subject with the request identity). Now expanded; the comment corrected |
| C4 CRD/apiVersion fidelity | **REFUTED** | CONFIRMED | **Accepted**: every non-core List emitted `apiVersion: "unknown"`. `gsd.kube` ignores the envelope today (latent), but a faithful mock must not. Added `_LIST_API_VERSIONS`, fail-loud on an unknown kind |
| C5 tests non-vacuous | **REFUTED** | **REFUTED** | **Accepted (converged)**: `test_poll_end_to_end` asserted only `poll_once=="ok"` and `test_refresh_bindings_runs` had ZERO assertions — a valid-but-empty server passed both. Rewritten to assert the persisted groups/groupsyncs/members/users, the bindings, the namespace source and the operator config |
| C6 portability | **REFUTED** | CONFIRMED w/ deps | **Accepted (converged)**: every handle shared `GSD_MOCK_TOKEN`, so two servers in one process clobbered the token (the first 401s). Now per-handle (`GSD_MOCK_TOKEN_<id>`). Cursor's machine-path `sys.path` fallback in conftest removed |
| C7 CI workflow | **REFUTED** | **REFUTED** | **Accepted (converged) — the CI blocker**: `mock-cluster.yml` had literal `@<checkout-release-tag-commit-sha>` placeholders, so the branch's own `test_workflow_pins.py` was RED. Pinned to the repo's actual SHAs (NOT Codex's own lookup — the repo pins checkout `3d3c42e…`/setup-python `5fda3b9…` everywhere, and Dependabot keeps them together); added `workflow_dispatch:` (so `container-smoke` is reachable) and `poller.py`/`store.py` to the PR paths |
| C8 next use | CONFIRMED | REFUTED | Partly accepted; see deferred |

## Rejected / deviations

- **Codex's Fix 7 action SHAs were not taken.** It proposed its own `checkout@11bd719…`/`setup-python@42375…`;
  the repo pins a single version of each across all workflows (`3d3c42e…` v7.0.1, `5fda3b9…` v7.0.0). Using
  the repo's pins keeps Dependabot's single-bump model and consistency — the finding (real SHAs, not
  placeholders) is right; its specific revisions are not.

## Deferred (noted, not blocking; own follow-up)

- **Fix 8 — `/_mock/reload` 500→422 and fail-loud nested-typo validation.** `/_mock/*` is a dev/inspect
  endpoint the poller never calls; a malformed reload source is operator error, not a poll path. The
  fail-loud fixture validation is worth doing but is a larger change to `Fixture.from_dict`; deferred.
- **Fix 9 — an endpoint-parity guard** (a test that fails when `gsd.kube` grows a 14th path the mock has not
  copied). A good drift guard, but additive; deferred as an enhancement.
- **Fix 6 — `chmod 0777 out` for the Form-B bind mount.** Only the manual `container-smoke` job (now
  `workflow_dispatch`, off the PR path) touches it; a README/CI ergonomics note, not a suite defect.
- **The two-servers-distinct-tokens regression test** needs a factory fixture the suite does not have; the
  per-handle-token FIX is applied and the whole suite passes, so the gap is closed even without the dedicated
  test.

## Outcome

The TLS + path + SAR-oracle core was sound; four real defects were converged on by both reviewers (the vacuous
tests, the shared token, the placeholder-SHA workflow) or found by Codex's execution (the SA-subject SAR gap,
the `unknown` apiVersion, the short cert window). All are fixed and locked by tests run to green here (55
mock-app + the workflow-pins guard). The mock-app suite runs in CI via `mock-cluster.yml`, now executable.
Second pass to follow on the fixed head.
