# Review — PR #95, session tooling: the change-log folder, the skills and settings into git

Adversarial second-opinion pass, 2026-09-14, on the six-claim brief for #95 (head `629c20c`: the
`docs/session-changelogs/` folder, `.claude/settings.json` with the post-commit hook, the tracked
`adversarial-review` and `changelog` skills, the `.gitignore` negation patterns). Codex (gpt-5.6-sol,
xhigh, CLI launched with stdin closed, its own scratch subdirectory, a `git archive` export of the head)
had a shell and measured; Cursor (Grok 4.6 high fast, ask mode, shell blocked) traced from the working
tree and marked every runtime claim PLAUSIBLE. Every verdict was re-checked here before a decision.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 the ignore patterns admit exactly five files | REFUTED | PLAUSIBLE (intended gate) | **Accepted on the fact; snippet rejected** |
| C2 the PostToolUse hook is correct as shell | CONFIRMED (six stdins run) | PLAUSIBLE | — |
| C3 the changelog skill's citation rule is true of the test | CONFIRMED | PLAUSIBLE | — |
| C4 the session log's Part 3 is factual | REFUTED (heading span; "six") | PLAUSIBLE (heading span) | **Accepted** |
| C5 the Codex launch block parses and the stdin claim is right | PLAUSIBLE (help text + open-pipe hang measured) | PLAUSIBLE | **Accepted: the help quote added** |
| C6 the .gitignore comment's claims about frontend-design | PLAUSIBLE | CONFIRMED | — |

## C1 — "exactly five" is a measurement, not a guarantee

**Finding (Codex).** After `touch .claude/skills/changelog/unlisted.md` in a scratch repository with the
same `.gitignore`, `git add -A --dry-run` listed six files, not five: the negation of a directory admits
every file inside it. Proposed: negate each of the five files by name, with `.claude/skills/<dir>/*`
ignore lines between.

**Re-check.** True by the ignore semantics (Cursor's trace agrees: "files inside the two un-ignored
directories do not need a further `!` line — that is how the four skill files get in"). The brief's
wording "nothing else can be added without a further negation" was the orchestrator's over-claim; the
`.gitignore` comment and the log claim only that the two hand-written skill directories and the settings
file are tracked, and the log's "lists exactly the five intended files" is what `git archive HEAD
.claude` printed.

**Decision.** Accepted on the fact; snippet rejected. The unit of tracking is the skill directory: a
skill grows templates beside its `SKILL.md` (the review skill already has two), and a per-file list
would turn every added template into a `.gitignore` edit that is easy to forget — the opposite of the
gate's purpose. The residual risk (a stray file dropped inside one of the two directories rides in on
`git add -A`) is visible in `git status` and accepted.

## C4 — the Part 3 heading closed at 05:48 while its last phase is 05:54

**Finding (both).** The Part 3 heading read "05:43 → 05:48"; the third subsection, the stdin gotcha, is
05:54 (`ed97dbf`). Cursor supplied a check that fails before and passes after; Codex also flagged the
word "six" at the export's line 209.

**Re-check.** Cursor's check run here: before, `heading 05:43 → 05:48 subsections ['43','43','48','54']
-> MISMATCH`; after the edit, `-> ok`. The "six" had already been corrected to "five" in the working
tree before the reviewers ran (the orchestrator's own re-count while writing the brief: the earlier
`git archive` call had been asked for `.gitignore` too), which is why Cursor, reading the tree, saw
"five" and Codex, reading the export of `629c20c`, saw "six".

**Decision.** Accepted. The heading now ends at the last phase's time; the "five" wording (with the
sentence saying what the first count had counted) is committed with this record.

## C5 — the stdin claim, with the CLI's own words

**Finding (Codex).** `bash -n` on the substituted block exits 0. `codex exec --help` (v0.144.1): "If stdin
is piped and a prompt is also provided, stdin is appended as a <stdin> block". A guarded probe with an
open pipe was still at "Reading additional input from stdin..." after eight seconds; the `< /dev/null`
run in Codex's sandbox failed for an unrelated reason (the in-process app-server client is not permitted
there), so the header could not be measured by Codex.

**Re-check.** The header WAS measured by the orchestrator, this session: the launch of this very pass
printed "OpenAI Codex v0.144.1 … model: gpt-5.6-sol … reasoning effort: xhigh" within 25 seconds of a
`< /dev/null` start.

**Decision.** Accepted; the help-text sentence is added to the gotcha as the documentary evidence
beside the measurement.

## Not asked, and what happened to it

- **Both reviewers: Step 4's suite command does not work from the repository root.**
  `local-development/.venv/bin/python -m pytest tests -q --ignore=tests/test_ui.py` names a `tests/`
  that exists only under `local-development/`; re-checked: from the root, "no tests collected"; CI's
  command from `local-development/` (`--deselect tests/test_ui.py --deselect tests/test_live_smoke.py`)
  collects 2854. Accepted on the fact; wording mine — the skill now gives CI's command from CI's
  directory and names `local-development/release-crc.sh` by its path. Codex's variant (root-relative
  paths) was rejected because the skill should say the command CI runs; Cursor's variant was the
  direction taken, with its nested code fence flattened.
- **Cursor: Step 5 cites the memory note as a backticked `.md` path** that is not in the repository,
  against the changelog skill's own rule. Accepted: plain italic words, as the changelog skill does.
- **Codex: jq prints a parse error to stderr on non-JSON stdin** (case e). Recorded, no change: the
  hook's stdin is always the tool call's JSON, the exit code is 0 either way, and the skill's rule is
  the smallest fix that closes a hole — there is no hole.

## Outcome

Two claims refuted (C1 on the wording, C4 on the heading), one accepted with an addition (C5), three
held. Snippets rejected: C1's per-file negation list (the directory is the unit), Codex's root-relative
Step 4 (the skill says what CI runs). Applied: the Part 3 heading, the Step 4 command and paths, the
Step 5 memory wording, the help-text quote in the gotcha. Re-validated after the edits: Cursor's heading
check (ok), the docs tests on the tree (`test_docs_citations.py`, `test_docs_diagrams.py`,
`test_prepare_release.py`), and CI on the pushed head. A second pass on the fixed head follows in the
same PR.
