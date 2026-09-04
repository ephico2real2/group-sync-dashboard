# Review — PR #70, A1: the browser tests run in CI

Adversarial second-opinion pass, 2026-09-04, on the nine-claim brief for #70 (`docs/specs/SPEC_A1_ui_tests_in_ci.md`
applied). Codex had a shell and measured; Cursor ran in ask mode with shell and network blocked, read the
installed packages and the diff, and marked what it could not measure PLAUSIBLE rather than guessing. Every
verdict was re-checked here before a decision.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 `if: vars.CI_UI_TESTS != 'false'`: unset runs, only `false` skips | REFUTED | PLAUSIBLE | **Accepted as a documentation defect; fix rejected** |
| C2 upload `path` against the workspace; pytest-playwright `--output` default | CONFIRMED | CONFIRMED | — |
| C3 the three pytest-playwright options and values exist in 0.8.0 | CONFIRMED | CONFIRMED | — |
| C4 3.14 wheels for playwright, pytest-playwright, greenlet | CONFIRMED | REFUTED (wording) | **Accepted as a wording correction** |
| C5 the live-smoke classification regex and `_code()` on the folded block | CONFIRMED | CONFIRMED | — |
| C6 Chromium sandbox off by default; no `--no-sandbox` needed | CONFIRMED | CONFIRMED | — |
| C7 nothing `needs: ui`; the OFF state leaves every job alone | CONFIRMED | CONFIRMED | — |
| C8 fidelity to the spec's NEW blocks; only the named files changed | CONFIRMED | PLAUSIBLE | — |
| C9 fixed sleeps are the only no-code-change failure source | REFUTED | CONFIRMED (with nuance) | **Framing accepted; both snippets rejected** |

## C1 — GitHub compares strings case-insensitively

**Finding (Codex).** `==` and `!=` ignore case in GitHub expressions, so `False` and `FALSE` turn the job off
as well as `false`; the workflow comment said "anything but the string 'false' runs the job". Proposed
fix: `if: toJSON(vars.CI_UI_TESTS) != '"false"'`.

**Re-check.** GitHub's expressions reference, Operators: "GitHub ignores case when comparing strings." The
unset case was measured rather than argued: `gh variable list` on the repository returns nothing, and the
job ran on the PR's first push, so an unset variable runs the job.

**Decision.** The comment and the test docstrings were wrong about the contract and now state it: the value
`false`, in any letter case, turns the job off; anything else, including an absent variable, runs it. The
`toJSON` fix was rejected: it would make the switch case-sensitive, so an operator who writes `False` — the
obvious way to mean off — would get the job running, which is the surprising outcome, not the safe one.
The test cannot evaluate GitHub's expression engine; it holds the text, and the docstring records the
measured semantics. Recorded in the spec's notes.

## C4 — the wheel facts

**Finding (Cursor).** The spec's risk sentence calls Playwright 1.62 an "abi3 wheel"; the locally installed
wheel is `py3-none-any`, and the binary risk is greenlet's cp314 wheel, which Cursor could not fetch.

**Re-check.** `pip download --only-binary=:all: --python-version 3.14 --platform manylinux2014_x86_64`:
`playwright-1.62.0-py3-none-manylinux1_x86_64.whl` (platform-tagged for the bundled driver, no Python ABI),
`pytest_playwright-0.8.0-py3-none-any.whl`, `greenlet-3.2.5-cp314-cp314-manylinux2014_x86_64.…whl`. Nothing
compiles. And the job installed and ran green on the ubuntu-latest / 3.14 runner: 223 passed in 117 s.

**Decision.** Accepted as a wording correction, recorded in the spec's notes. Cursor's own "py3-none-any" is
the macOS artefact, not the Linux one; the Linux wheel carries a platform tag.

## C9 — the sources of a red job with no code change

**Findings.** Codex: the browser and system-library install is network-dependent too, and there are 18 fixed
sleeps across 11 tests, the worst a 600 ms wait in `test_a_superseded_fetch_does_not_paint_the_wrong_page`;
proposed a `window.__released` flag set when the released fetch resolves, then `wait_for_function`. Cursor:
listed the same sleeps and proposed a `hashchange`-listener rewrite of `test_the_skip_link_does_not_navigate`.

**Re-check.** The sleeps are as listed. Codex's flag is set by a `.then` registered on the fetch promise
AFTER the application's own continuation was registered, and the application's continuation awaits
`.json()` and then paints — a further microtask chain — so the flag can be true while the paint that the
test exists to rule out has not yet had its chance. The assertion would then pass early: a weaker test that
looks stronger, which is the review scar this repository already records. Cursor's rewrite is sound but
changes a test that is not in A1's scope.

**Decision.** The framing is accepted: the install step's network dependence is a real second source, and
it fails visibly at `pip` or `apt`, which is the accepted form. Both snippets rejected. The sleeps are
bounded negative assertions — "nothing happened within N ms" has no event to wait for — and they ran green
in 117 s on the runner; if one flakes, the trace artifact names the test and that test gets a deterministic
wait then, not before.

## Not asked

- Codex: the venv's `pytest` console script has a shebang pointing at a root-level `.venv` that does not
  exist (the venv was created there and moved). A property of this laptop, not the repository; every
  documented invocation is `python -m pytest`, which is unaffected.
- Cursor: `chromium_sandbox` defaults to `None` in the Python signature and the docstring says the
  effective default is false. Consistent with C6; the test suite never sets it.

## Outcome

Two claims refuted, one on a documented contract and one on a wording detail; both accepted in the form the
evidence supports and neither reviewer's snippet applied. After the edits: `test_ci_ui_job.py` and the
citation test re-run, the workflow re-parsed, CI re-run on the PR.
