---
name: adversarial-review
description: The per-PR adversarial review pass — Codex (gpt-5.6-sol at xhigh) and Cursor (Grok 4.6 high fast) on a per-claim brief, snippet-only findings, the orchestrator's accept/reject in writing, then rebuild, test and validate. Run it on every PR before calling it ready, and as a second pass on the fixed head.
---

# Adversarial review — the orchestrator's pass

Every PR, docs PRs included, gets this pass before it is called ready. The operator's rule, verbatim
(2026-09-04): *"we need a review done after each PR and ask them to give the actual snippet and then
you decide and build locally and test and validate."* Nothing here is a template guess: every rule
below was measured on PRs #69–#71 of group-sync-dashboard and the reasons are stated.

## Your two roles

**Orchestrator.** You do not write from memory. The specification (`docs/specs/SPEC_<id>_*.md`) is the
source; a feature is applied from its fenced blocks, file by file, with an exact-match check on every
"Old" text before an edit. A deviation found necessary is written back into the spec, in the same PR,
under "Orchestrator's notes", with the reason. Reviewers propose; you decide; every decision is written
down with its reason before anything is applied.

**Surgeon.** A reviewer's snippet is applied only after you have traced it yourself. A correct finding
does not make its fix correct — measured four times in one day:

- The finding "GitHub compares strings case-insensitively" was right; the proposed `toJSON` comparison
  would have made `CI_UI_TESTS=False` silently RUN the job it was meant to turn off. Kept the semantics,
  fixed the words.
- The finding "an unbalanced backtick breaks the changelog bullet" was right; the proposed
  escape-every-backtick fix would have broken the code span an operator means (`` `--pr` ``). Refused
  the input instead of rewriting it.
- The finding "a fixed sleep can flake" was right; the proposed ready-flag fired on the fetch promise
  BEFORE the app's `.json()`-then-paint chain, so the assertion could pass before the paint it exists
  to rule out. Rejected: a weaker test that looks stronger.
- The finding "retention on with backups off deletes irreplaceable rows" was right; the proposed fix
  reverted an operator-decided default. Modelled the interaction instead (hold the prune).

Scope is yours too: a real finding in a file another spec owns is routed into that spec's notes
(A3's `helm.yaml` grammar finding went to A2; the `Chart.yaml` preamble sentence went to B4, the first
PR that bumps the chart), never left as a dangling "follow-up".

## The models — measured, use exactly these

| Reviewer | Invocation | Verified by |
|---|---|---|
| Codex, GPT-5.6, highest reasoning | plugin agent `codex:codex-rescue` with **`--model gpt-5.6-sol --effort xhigh`** stated in the request; CLI form `codex exec --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort="xhigh" …` | probe from the repo root; the session jsonl under `~/.codex/sessions` records `"effort":"xhigh"`. The id `gpt-5.6` is REFUSED on this ChatGPT account. |
| Cursor, Grok 4.6 high fast | `cursor agent -p --mode ask --output-format text --trust --model cursor-grok-4.6-high-fast "<brief>"` | probe from the repo root returns the expected words; `cursor agent models` lists the ids. |

Without the flags the plugin leaves model and effort UNSET and Cursor runs on `auto` — that is what the
first passes on #69–#71 ran on, and the operator noticed. Probe both with a one-line prompt before a
review if anything about the environment changed (login, plugin update, model list).

## Step 1 — the brief (never "review this")

One numbered claim per thing you want confirmed or refuted, each naming the exact file, symbol and
lines, what the claim asserts, and how to measure it. Demand for every claim one line
`C<n>: CONFIRMED | REFUTED | PLAUSIBLE` plus the artefact (a command and its output, file:line, a quoted
line from an installed package's source); a bare CONFIRMED counts as nothing. For EVERY finding —
a REFUTED verdict, a PLAUSIBLE verdict that names a risk, and anything volunteered under "not asked" —
demand the FULL code of the fix (the whole function, block or file section, with the file path and
where it goes, not a fragment or a description) AND a test that fails before and passes after. Say it
in the brief in these words: a finding without its full snippet and its test is not a finding and will
be discarded. That is the operator's rule ("ask them to give the actual snippet and then you decide"),
and a snippet is what lets you trace the mechanism before deciding. State the constraints: no
commits, no tracked-file edits, run the thing under review only in a COPY outside the repository, create
nothing inside the tree, delete every temp file. Cover: the semantics the change relies on (a GitHub
expression, an option's default, a wheel's tag), the OFF state and every switch interaction, fidelity to
the spec's NEW blocks, dependents (`needs:`), and what would go wrong on the NEXT real use.
`brief-template.md` beside this file is the skeleton. Write the brief to a scratchpad file and pass the
file's contents verbatim to both reviewers.

## Step 2 — launch both, each to its own output file

```sh
S=<scratchpad>
nohup cursor agent -p --mode ask --output-format text --trust --model cursor-grok-4.6-high-fast \
  "$(cat "$S/review_brief_<id>.md")" > "$S/review_cursor_<id>.txt" 2> "$S/review_cursor_<id>.err" &
```

and, in the same turn, the `codex:codex-rescue` agent with: the brief path, "pass its ENTIRE contents
verbatim", `--model gpt-5.6-sol --effort xhigh`, a scratchpad directory for copies (its own sandbox
`/tmp` may be read-only), "write Codex's complete unedited answer to `$S/review_codex_<id>.txt`
yourself", and "wait until the task is COMPLETELY finished".

What each can and cannot do: Cursor in ask mode has NO shell and no network — it traces from source and
must mark what it cannot measure PLAUSIBLE, not CONFIRMED. Codex has a shell and is the reviewer that
follows a value end to end; give it the venv interpreter path.

Known failure modes, all seen: Cursor's run dies silently with a 0-byte output — relaunch, the second
run works. `codex exec … &` launched from a backgrounded shell HANGS FOREVER at "Reading additional
input from stdin..." (0 % CPU, no session file, an empty answer — 4 h 16 min lost on D2's second pass,
2026-09-14): when stdin is not a TTY, `codex exec` appends whatever stdin carries to the prompt and waits
for EOF, and a backgrounded shell's stdin never closes. Always launch it with `< /dev/null`; the first
stderr lines must show the "OpenAI Codex … workdir: … model: …" header, not the stdin line alone. The codex-rescue agent can report "complete, tree clean" while its Codex task is STILL
running and writing probe artefacts INSIDE the repo (`.a3-adv-sandbox/`, a fake gitconfig, a hooks
dir); a sandbox copy of `Chart.yaml`/`values.yaml` made every basename citation ambiguous and failed the
resolver test. After a Codex pass: wait until no shell with `CODEX_COMPANION_SESSION_ID` is alive
(`pgrep -f CODEX_COMPANION_SESSION_ID`), then `git status --short` and remove untracked reviewer
artefacts BEFORE running the suite. Two reviewers writing into one file clobber each other — never share
an output file.

## Step 3 — decide, in writing, before applying

Re-check every verdict yourself, CONFIRMED included; CONFIRMED is the weakest verdict because it
produces nothing inspectable. For a semantic claim measure both the documentation and a real run (the
unset-variable case was proven by the job running on a repository with no variables). For a proposed
fix, trace the mechanism — promise order, escaping, what the flag means when the value is unset — and
for a proposed test make it fail against the current code before trusting it. Then write the decision:
accepted / accepted on the fact but snippet rejected (say why) / rejected (say why) / routed to spec X.

## Step 4 — apply, then build, test, validate

Apply accepted fixes surgically, with the deviation recorded in the spec's notes. Then, in order:
the affected test file; the full suite (`local-development/.venv/bin/python -m pytest tests -q
--ignore=tests/test_ui.py`, and `tests/test_ui.py` with the exact CI flags when the page changed);
`helm lint` and `helm template` for every switch state the spec names; the image built locally when
anything reaches it; `release-crc.sh` and the spec's live checks; the spec's own verification commands
repeated (a dry run undone, a probe, a count read back from the CI log). "Compiles" or "looks right" is
not validation. Commit with a message that names the review, push, comment on the PR with the decisions
and the re-validation, and wait for CI green on that commit.

## Step 5 — the record and the memory

`docs/REVIEW_<id>.md`: a table of claims × reviewers × decision; one section per accepted or rejected
finding with Finding / Re-check / Decision; a "Not asked" section for what a reviewer volunteered; an
Outcome paragraph. Add the file to `REVIEW_ARTIFACTS` in `local-development/tests/test_docs_citations.py`
— the record deliberately quotes wrong anchors and old lines, and that is the point of a record. Add one
dated data point to the memory `adversarial-review-before-shipping.md`: what each reviewer got right,
what it got wrong, what generalises. `record-template.md` beside this file is the skeleton.

## Step 6 — the second pass

After the fixes, a second brief on the fixed head with the SAME models: verify each accepted fix closes
its hole and opened no other, then attack what the first pass did not (inputs the first brief never
named, the next real use, two invocations in a row). The second reviewer on the fixed head is a cheap
confirmation pass and it still finds things (Cursor found the all-dots reason after Codex's four).

## Checklist, in order

1. Local tests, spec verification and CI green BEFORE the review; PR open early with `Closes #N`.
2. Brief written to a file: numbered claims, exact locations, artefact demanded, snippet + failing test
   demanded for refutations, constraints stated.
3. Probe both models if anything changed; launch both with the exact invocations above, own output files.
4. Wait for both; wait for the Codex process to actually exit; `git status`; remove reviewer artefacts.
5. Re-check every verdict yourself; decide each in writing with the reason; route out-of-scope findings.
6. Apply; deviations into the spec's notes; rebuild if the image is touched; full suite; helm; CRC; live
   checks; the spec's verification repeated.
7. `docs/REVIEW_<id>.md` + `REVIEW_ARTIFACTS`; commit naming the review; push; PR comment; CI green.
8. Second pass on the fixed head; repeat 4–7 for anything it finds.
9. Memory data point; only then call the PR ready. The operator merges.
