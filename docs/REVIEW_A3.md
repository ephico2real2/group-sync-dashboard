# Review — PR #71, A3: the release preparation script

Adversarial second-opinion pass, 2026-09-04, on the ten-claim brief for #71 (`docs/specs/SPEC_A3_release_script.md`
applied). Codex had a shell, ran the script in temporary copies and called its functions; Cursor's first run died
with an empty record and was relaunched, so it reviewed the head that already carried the Codex fixes — the
confirmation pass — in ask mode with the shell blocked, tracing from source. Every verdict was re-checked here.

## Verdicts

| Claim | Codex | Cursor (on the fixed head) | Decision |
|---|---|---|---|
| C1 `kind_of_bump` classifies and refuses correctly | CONFIRMED (12 pairs) | CONFIRMED (12 pairs) | — |
| C2 a failed version test or an existing branch leaves edits and commits nothing | REFUTED | REFUTED (the pre-fix half) | **Accepted** |
| C3 history line and paragraph land above their fields, wrapped, nothing else touched | CONFIRMED | CONFIRMED | — |
| C4 the two Chart.yaml regexes and the workflow extractors accept the same forms | REFUTED | CONFIRMED (narrower) | **Accepted on the fact, routed to A2** |
| C5 CHANGELOG with and without `## Unreleased` | CONFIRMED | CONFIRMED | — |
| C6 the reason's punctuation survives every output site | REFUTED | REFUTED (a second hole) | **Both accepted; Codex's snippet rejected** |
| C7 argv-only subprocesses; `--date` validated | REFUTED | CONFIRMED | **Accepted** |
| C8 the tests run the real script under isolated git config | CONFIRMED | CONFIRMED | — |
| C9 docs match the spec's NEW blocks except the recorded deviations | CONFIRMED | CONFIRMED | — |
| C10 the next real release (app 0.12.0, chart 0.11.0) needs no hand fix | CONFIRMED | CONFIRMED | — |

## C2 — "completes or changes nothing" was not true for an existing branch

Codex sabotaged the version test and pre-created `release/app-9.0.0` in copies: both left the four edits in
the tree with nothing committed. The failed-test case is what the design's "WHAT IT REFUSES" promises (edits
left for inspection); the existing-branch case was checked after the edits for no reason. Applied: the branch
check runs before any edit (skipped under `--no-commit`, which never branches), the docstrings say what is
true, and the test asserts a clean tree after that refusal. Cursor's pass on the fixed head confirmed it.

## C4 — the workflow's `sed` is a broader grammar than the script's

Codex: `helm.yaml` accepts `version: 1..2` and an empty quoted `appVersion`; the script and the build script
require `X.Y.Z`. True, and harmless here: everything the script writes is accepted by every consumer. The
tightening belongs to A2, which rewrites `helm.yaml`; it is in A2's spec notes with the test Codex proposed.

## C6 — what a reason can do to the changelog bullet

Codex: an unbalanced backtick opens a code span that swallows the rest of the changelog. Its fix escaped every
backtick and asterisk, which would turn "the `--pr` flag" — a code span the operator means — into literal
backslashes. Rejected; the reason is refused, never rewritten, when its backticks are unbalanced or it
contains `*`, and a balanced pair is tested to pass through intact. Cursor, on the fixed head: a reason of
only full stops strips to nothing and lands as `- **.**`. Accepted with its test.

## C7 — the date

Codex: `--date 2026-99-99` passed the shape check and was written into both history records. Applied: a real
calendar date with an isoformat round-trip; three bad dates tested. The subprocess half of the claim held: argv
lists, no shell, `cwd=REPO`.

## Not asked, and what happened to it

- Cursor: the test harness spread `os.environ` and so inherited `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_*`;
  `GIT_CONFIG_COUNT=0` closes it. Applied.
- Cursor: the `Chart.yaml` preamble says nothing but a human writes the file, which the script now does. A
  comment-only edit under `charts/` costs a chart release, so the sentence is corrected in B4's PR, the first
  to bump the chart; routed in B4's spec notes.
- Cursor: the spec's verification section says "13 passed"; that is the design's count and the file now holds
  17. Recorded in the spec's notes; the verbatim body stands.
- Codex: the brief's path `tests/test_prepare_release.py` was relative to `local-development/`, as the spec
  writes it. No change.

## Outcome

Four claims refuted by Codex and one more hole found by Cursor on the fixed head; all five accepted on the
fact, one reviewer snippet rejected for the reason above, one finding routed to the spec that owns the file.
After the edits: 17 tests in `test_prepare_release.py`, the dry run on the real tree repeated and undone, the
citation and index tests green, CI green on the PR.
