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
| Cursor, Grok 4.6 high fast (ZDR) | `cursor agent -p --mode ask --output-format text --trust --model cursor-grok-4.6-high-fast "<brief>"` | probe from the repo root returns the expected words; `cursor agent models` lists the ids. |
| Cursor, Claude Fable 5 **high** thinking (**NO ZDR**) | `cursor agent -p --mode ask --output-format text --trust --model claude-fable-5-thinking-high "<brief>"` | probe returns "Claude Fable 5"; `cursor agent models` lists the id. The lighter tier — the confirmation (second) pass, or a smaller PR. |
| Cursor, Claude Fable 5 **extra-high** thinking (**NO ZDR**) | `cursor agent -p --mode ask --output-format text --trust --model claude-fable-5-thinking-xhigh "<brief>"` | probe returns "Claude Fable 5"; `cursor agent models` lists the id. The deepest tier — the primary (first) pass / complex design; matches Codex xhigh. Cursor labels the 5.1 family "Claude Fable 5". |
| **OB1** (Obi-Wan) — Anthropic Fable 5.1, inside Claude Code | the `Agent` tool with **`model: "fable"`** (`claude-fable-5-1`), `subagent_type` general-purpose, the brief as its ENTIRE prompt plus the read-only rule below; the same Fable as Cursor's `claude-fable-5-thinking-*` rows above by another route — the pivot to OB1 exists because Cursor's Fable is capped by the Pro+ usage limit (measured 2026-09-17: the first launch hit the monthly limit); the Cursor Fable rows stay (the operator, 2026-09-17: "Dont drop the cursor fable role. We only pivot to ob1 because our token issues with cursor fable") | the agent's completion notification carries its answer; it runs with the session's tools, so its `bash -n` / read-only `kubectl` / `curl` outputs are in its report. |
| **OB2** — OB1 at **high** reasoning effort, the default from 2026-09-18 | the `Agent` tool with **`subagent_type: "ob2"`** — the project agent `.claude/agents/ob2.md` (`model: fable`, `effort: high`, the reviewer's standing rules in its body: verdicts with artefacts, every finding with its full fix and its failing/passing test, read-only, measure-don't-reason, the report shape); the brief is its whole prompt, no `model` parameter needed | the operator, 2026-09-18: *"Create a new skill from OB1 called OB2 (OB1 high) with fable 5.1 but with high effort and assume OB2"* — every launch uses OB2 now; OB1 (the general-purpose launch at the session's effort) only when the operator asks for it by name. Same tools, same rules, the same report; its completion notification carries the answer. |
| **OB3** — the same reviewer on **Opus 5**, choosing its own depth; the default from 2026-09-18 | the `Agent` tool with **`subagent_type: "ob3"`** — the project agent `.claude/agents/ob3.md` (`model: opus`, `effort: high` as a FLOOR, and a rubric in its body: shallow claims are settled by a grep, medium by one drive, deep ones get the harness, and the report names which it treated as deep). Also runnable as a background job: `claude -p "<the brief's prompt>" --agent ob3 --allowedTools "Bash,Read,Write,Edit,Glob,Grep" --output-format json --max-turns 300 < /dev/null` (drop `CLAUDECODE` from the environment first) | the operator, 2026-09-18: *"We have hit our weekly fable usage limit… use opus 5 high with auto switch effort… substitute the jobs and role of ob2 with ob3."* MEASURED that day: an OB2 background run died after 32 turns with "You've reached your Fable limit", $4.93 spent and no report. There is no `auto` effort value — the frontmatter takes a fixed tier and neither the `Agent` tool nor `claude -p` exposes an effort flag — so the tier is pinned at `high` and the self-scaling lives in the agent's body. |

The Cursor reviewers are **independent** — call either, or both; Fable is the *third* reviewer beside
Grok + Codex, through Cursor while its usage limit allows and through OB1 when it does not. **ZDR vs NO ZDR is the deciding trade:** Grok
4.6 is zero-data-retention; the Fable ids are marked `(NO ZDR)`, so a review sends the repo's code + the
brief to a provider that may **retain** it — weigh that against Fable's stronger reasoning before using it
on sensitive code (a design/plan review over markdown is lower-sensitivity than shipping code). Which
Cursor model is the session default is recorded in memory ([[cursor-fable-reviewer]]); absent that, Grok
is the ZDR-safe default.

Without the flags the plugin leaves model and effort UNSET and Cursor runs on `auto` — that is what the
first passes on #69–#71 ran on, and the operator noticed.

**OB1 gets the same instructions as the other two — no shorter brief, no softer rules.** Its prompt is the
brief file's content verbatim, preceded by one paragraph: it is the adversarial reviewer; do NOT modify any
file, do NOT run git write commands, kubectl apply, helm or anything that changes a cluster; it MAY read
files, run `bash -n`, read-only `kubectl`/`curl`/`jq`/`python3`; verdicts CONFIRMED / REFUTED / PLAUSIBLE
with quoted evidence (file:line, command + output) for every refutation; terse; end with an overall verdict
and the minimum changes. **Not review only:** for every REFUTED or risk-naming PLAUSIBLE verdict and anything it
volunteers, OB1 hands back the FULL code of the fix (the whole function, block or file section, with the path
and where it goes) and a test that fails before and passes after — the fix goes into its report, never into
the tree; the orchestrator traces it and applies it (the operator, 2026-09-17: "It shouldn't be review only. It
also produces the code fix for any suggestions"). OB1 is **required** for anything that becomes an upstream post (an issue, a PR, a
comment on someone else's repository) — the operator reads the draft under `docs/upstream/` after OB1 has,
and posts only on their word. Codex and Grok run beside it, not instead of it. Probe both with a one-line prompt before a
review if anything about the environment changed (login, plugin update, model list). A finding from ANY
reviewer is only a finding with the FULL code of the fix AND a failing/passing test — a design-level
description is not the solution; demand the snippet (the operator's rule).

## Prerequisites — a clone does not provide them

The invocations above need tools the tree does not ship, and the first sentence that fails a reader on a
fresh clone is Step 2's `codex exec` (no login), then Step 4's `.venv/bin/python` (no environment):

- The Cursor CLI, logged in (`cursor agent login` once; `cursor agent models` must list
  `cursor-grok-4.6-high-fast`), and the Codex CLI, logged in (`codex login status` must say logged in)
  or the `codex:codex-rescue` plugin agent. `~/.codex/sessions` is where the probe's effort is verified;
  `git clone` does not create it.
- The virtualenv under `local-development/`, created once from that directory with the recipe in
  `local-development/README.md`: `python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"`, plus
  `./.venv/bin/python -m playwright install chromium` for the browser tests. Step 4 uses that interpreter.
- Nothing under `.agents/` — that tree is third-party skill installs and is ignored; this pass does not
  read it.

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

## Step 2 — launch all three, each to its own output

```sh
S=<scratchpad>
nohup cursor agent -p --mode ask --output-format text --trust --model cursor-grok-4.6-high-fast \
  "$(cat "$S/review_brief_<id>.md")" > "$S/review_cursor_<id>.txt" 2> "$S/review_cursor_<id>.err" &
```

and, in the same turn, Codex — either the `codex:codex-rescue` agent with: the brief path, "pass its
ENTIRE contents verbatim", `--model gpt-5.6-sol --effort xhigh`, a scratchpad directory for copies (its
own sandbox `/tmp` may be read-only), "write Codex's complete unedited answer to
`$S/review_codex_<id>.txt` yourself", and "wait until the task is COMPLETELY finished"; or the CLI
directly, on a `git archive` export of the head in the reviewer's own scratch subdirectory, **with stdin
closed** — this is the line that worked on D2's second pass (2026-09-14), after the one without
`< /dev/null` hung for 4 h 16 min:

```sh
W="$S/review_<id>_codex"            # its own subdirectory; the export of HEAD lives in "$W/head"
cd "$W" && nohup codex exec --skip-git-repo-check -m gpt-5.6-sol -c model_reasoning_effort="xhigh" \
  -s workspace-write -C "$W" "$(cat "$W/brief.md")" < /dev/null \
  > "$S/review_codex_<id>.txt" 2> "$S/review_codex_<id>.err" &
sleep 20; head -c 400 "$S/review_codex_<id>.err"   # must show "OpenAI Codex … model: …", not only "Reading additional input from stdin..."
```

and, in the same turn, **OB3** (from 2026-09-18 — `subagent_type: "ob3"`, the project agent on Opus 5 that scales its own depth per
claim and carries the reviewer's standing rules; the brief is the whole prompt. OB2 is the same definition on Fable 5.1 and returns when
that quota resets) — or, only when the operator asks for OB1 by name, **OB1** — the `Agent` tool, `model: "fable"`, `subagent_type: "general-purpose"`,
`description: "OB1 adversarial review of <id>"`, the prompt = the read-only paragraph above + the brief's
full text + the file paths it needs (it works in the repository itself, read-only — no export needed, but
name the branch and say it must not switch). It runs in the background and reports on completion; never
predict or paraphrase its result before the notification arrives. Save its answer to
`$S/review_ob1_<id>.txt` yourself when it comes in, so the record has all three side by side.

What each can and cannot do: Cursor in ask mode has NO shell and no network — it traces from source and
must mark what it cannot measure PLAUSIBLE, not CONFIRMED. Codex has a shell and is the reviewer that
follows a value end to end; give it the venv interpreter path. OB1 has the session's tools and the live
repository: it can read the real files and run read-only commands against the lab, so it is the reviewer
that catches "the file the brief describes is not the file on disk" and "the number in the doc is not the
number the cluster gives".

**Every reviewer scales its own depth, and OB3's passes get a second reading.** OB1, OB2 and OB3 carry the
same rubric in their bodies: the frontmatter tier is a FLOOR, a shallow claim (a string, a selector, a
constant) is settled by a grep, a medium one (a render path, an API shape) by one drive, a deep one (a race,
contrast over composited surfaces, cost at scale) gets the harness — and the report opens by naming which
claims were treated as deep. The frontmatter has no `auto` value and no launch path sets effort, so this
judgement is the model's, not the flag's. **A pass OB3 ran while the Fable quota was out is re-reviewed by
OB1 or OB2 when it resets** (the operator, 2026-09-18): its verdicts are claims like any other, its
CONFIRMED-without-an-artefact lines get re-measured, and its failing/passing proofs get re-run against the
head as it stands then. Agreeing with OB3 because OB3 said it wastes the third-reviewer seat.

### Gotchas — all seen, all measured; read before every launch

- **A backgrounded `codex exec` must have stdin closed, or it waits forever.** Launched from a
  backgrounded shell without `< /dev/null`, it sits at "Reading additional input from stdin..." at 0 %
  CPU with no session file and an empty answer: when stdin is not a TTY, `codex exec` appends whatever
  stdin carries to the prompt and waits for EOF (`codex exec --help`, v0.144.1: "If stdin is piped and a
  prompt is also provided, stdin is appended as a `<stdin>` block"), and a backgrounded shell's stdin
  never closes. That
  cost 4 h 16 min on D2's second pass (2026-09-14) before it was caught. Always `< /dev/null`; then read
  the first stderr bytes — the "OpenAI Codex … workdir: … model: …" header means it is working, the
  stdin line alone means it is not — and `ps -o etime,%cpu` on the pid after twenty seconds.
- **Cursor's run can die silently with a 0-byte output.** Relaunch; the second run works.
- **The codex-rescue agent can report "complete, tree clean" while its Codex task is STILL running**
  and writing probe artefacts INSIDE the repo (`.a3-adv-sandbox/`, a fake gitconfig, a hooks dir); a
  sandbox copy of `Chart.yaml`/`values.yaml` made every basename citation ambiguous and failed the
  resolver test. After a Codex pass: wait until no shell with `CODEX_COMPANION_SESSION_ID` is alive
  (`pgrep -f CODEX_COMPANION_SESSION_ID`), then `git status --short` and remove untracked reviewer
  artefacts BEFORE running the suite.
- **Two reviewers writing into one file clobber each other** — never share an output file, and never
  give a reviewer the scratchpad root: a Codex exit trap once deleted the whole session directory. Each
  reviewer gets its own subdirectory and irreplaceable outputs are copied out first.

**Wait with a background wakeup, not a polling loop** (the operator, 2026-09-17: *"Pls dont poll background jobs
and waste tokens. Pls use watcher and ask them to notify you or wake up when the done"*). Reviewers, the suite and CI each take minutes;
every manual "is it done yet?" Read/Bash is a full-context model round-trip that re-bills the whole
conversation for one "not yet". Arm ONE waiter that wakes you when the condition holds and stay silent
until it fires: `Monitor` (or Bash `run_in_background`) with `until <done-check>; do sleep 3; done`,
its filter matching BOTH the success and the failure markers so a crash wakes you too (silence is not
success). A single status check is fine — is the pid alive, did the file appear — the *loop* of checks
is the waste. Gotcha: a `… 2>&1 | tail -N` output file stays EMPTY until the command exits, so reading
it early tells you nothing; that empty read is exactly what the wakeup spares you.

## Step 3 — decide, in writing, before applying

Re-check every verdict yourself, CONFIRMED included; CONFIRMED is the weakest verdict because it
produces nothing inspectable. For a semantic claim measure both the documentation and a real run (the
unset-variable case was proven by the job running on a repository with no variables). For a proposed
fix, trace the mechanism — promise order, escaping, what the flag means when the value is unset — and
for a proposed test make it fail against the current code before trusting it. Then write the decision:
accepted / accepted on the fact but snippet rejected (say why) / rejected (say why) / routed to spec X.

## Step 4 — apply, then build, test, validate

Apply accepted fixes surgically, with the deviation recorded in the spec's notes. Then, in order:
the affected test file; the full hermetic suite, from `local-development/` — the directory CI runs it
in. The pytest invocation without the `cd`, run from the repository root, collects nothing (measured
2026-09-14: "no tests collected"):

```sh
cd local-development && .venv/bin/python -m pytest tests -q \
  --deselect tests/test_ui.py --deselect tests/test_live_smoke.py
```

and `tests/test_ui.py` with the exact CI flags when the page changed; `helm lint` and
`helm template` for every switch state the spec names; the image built locally when anything reaches
it; `local-development/release-crc.sh` and the spec's live checks — the bare script (Helm, from the
worktree) while iterating, and `--argocd` on the pushed head before the PR is called ready, since Argo
reads the chart and the values file from GitHub and that is what an install does (the mode matrix is in
the script's header and in `local-development/README.md`); the spec's own verification
commands repeated (a dry run undone, a probe, a count read back from the CI log). "Compiles" or
"looks right" is not validation. Commit with a message that names the review, push, comment on the PR
with the decisions and the re-validation, and wait for CI green on that commit.

## Step 5 — the record and the memory

`docs/REVIEW_<id>.md`: a table of claims × reviewers × decision (the reviewers named as run: Codex, Grok,
**OB1 — Fable 5.1, Claude Code Agent**); one section per accepted or rejected
finding with Finding / Re-check / Decision; a "Not asked" section for what a reviewer volunteered; an
Outcome paragraph. Add the file to `REVIEW_ARTIFACTS` in `local-development/tests/test_docs_citations.py`
— the record deliberately quotes wrong anchors and old lines, and that is the point of a record. Add one
dated data point to the memory note *adversarial-review-before-shipping*: what each reviewer got right,
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
3. Probe Codex and Grok if anything changed; launch all three with the exact invocations above — own
   output files, own subdirectories, Codex with stdin closed (`< /dev/null`) and its stderr header read
   back, OB1 with the same brief and the read-only paragraph.
4. Wait for all three; wait for the Codex process to actually exit and for OB1's completion notification;
   `git status`; remove reviewer artefacts.
5. Re-check every verdict yourself; decide each in writing with the reason; route out-of-scope findings.
6. Apply; deviations into the spec's notes; rebuild if the image is touched; full suite; helm; CRC; live
   checks; the spec's verification repeated.
7. `docs/REVIEW_<id>.md` + `REVIEW_ARTIFACTS`; commit naming the review; push; PR comment; CI green.
8. Second pass on the fixed head; repeat 4–7 for anything it finds.
9. Memory data point; only then call the PR ready. **The operator merges — never merge yourself** (the
   operator, 2026-09-18: "Don't merge automatically, remember you need to approve it").
