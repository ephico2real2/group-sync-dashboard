---
name: changelog
description: The session change log — one file per working session under docs/session-changelogs/, appended after each commit that has passed its tests and review, in the measured before/after format the operator approved on 2026-09-14. Invoke at session start to open the day's file, after every validated commit to append, and at session end to close with the numbers table.
---

# Session change log — what happened, with the measurement behind each line

The operator's ask, verbatim (2026-09-14): *"I like the way you reordered this change log … a change
log should be added periodically during the session and set in post commit after testing and review
is done."* This is a **session** log, not the product changelog: `docs/CHANGELOG.md` says what a
release changed for an operator; a session log says what a working session did, when, and how each
claim was measured. The two never merge.

## Where

`docs/session-changelogs/YYYY-MM-DD_<slug>.md` — one file per session, named by the date the session
started and a two- or three-word slug of its subject (`2026-09-11_c3-d2-release.md`). A session that
spans midnight keeps its start date. `docs/session-changelogs/README.md` lists the convention; do not edit it per
session.

## When — three moments, never before validation

1. **Session start.** Create the file with the header, the "Outcome in one line" placeholder and the
   before/after table's *Before* column filled from the resume note and `git log`. Nothing else yet.
2. **After each commit that has passed its tests and review.** Append that commit's lines under the
   current phase heading. The PostToolUse hook on `git commit` reminds you; the rule is the skill's,
   not the hook's: a commit is logged when the suite is green on it and, for a reviewed PR, when the
   review decisions on it are recorded — never when it is merely pushed. A commit later found wrong
   gets a line saying so under the commit that fixed it, not a silent rewrite.
3. **Session end** (or when the operator asks). Fill the outcome line, the *After* column, the
   numbers table, "Where things are recorded" and "State left behind". Copy nothing from memory:
   `git log --date=format:'%Y-%m-%d %H:%M' --format='%h  %ad  %s'`, `gh pr view`, `gh issue view`
   and the test summary lines are the sources.

## Format — the approved shape, in this order

```
# Session change log — <repo>, <start date> → <end date>

<one paragraph: what the log is, where the times come from, and the sentence "every 'measured'
claim is one the session ran a command for; nothing below is recalled from memory alone">

Outcome in one line: **…**

| | Before the session | After |
|---|---|---|
| <3–5 rows: versions, artefacts, programme state, open PRs/issues> |

---

## Part N — <feature or theme> (<date span>)

### <phase> (<date, HH:MM → HH:MM>) — commit `<sha>` [, PR #n]

- <what was done and WHY, one or two sentences>
- **<Found by …>** / **<Accepted>** / **<Rejected>** lines name who found what and what was decided
- <the measurement: a count, a status code, a digest prefix, a test total> — every claim that could
  be measured names its measurement

---

## Numbers

| | |
|---|---|
| Commits authored | … |
| PRs merged | … |
| Review passes run | … |
| Reviewer findings accepted / rejected | … |
| Defects found by tooling rather than reviewers | … |
| Full suite, final | … |
| Longest single loss | … — and what was written down so it does not recur |

## Where things are recorded

- <the review records, spec notes, design docs, skills and memories this session touched>

## State left behind

- <lab state, running processes, anything the next session must know>
```

## Rules that make it trustworthy

- **Measured, or marked.** A number, a status code, a digest or a test total appears only when the
  session ran the command. If a fact was lost (an output filter dropped a test name), say so in the
  line rather than reconstructing it.
- **Who found it.** Every defect names its finder — a reviewer by name, "the full suite", "CI", "the
  live check", "the operator" — and every reviewer finding names the decision (accepted, accepted on
  the fact with the snippet rejected, rejected with the reason).
- **Bold the decision words**, never whole sentences: **Found by CI**, **Accepted**, **Rejected**.
- **Commit SHAs in backticks, PRs and issues as `#n`**, times as the git author time in the
  operator's zone (America/Chicago on this machine).
- **Citation-safe.** The folder is scanned by `local-development/tests/test_docs_citations.py`: every
  backticked repository path, with or without a `#anchor`, must resolve in the repository. Name memory notes and
  the untracked skills (frontend-design, the vendored design set) in plain words (the memory note
  *c3-resume-point*), never as backticked paths — they are not in the repository and the test
  fails on them. The tracked skills are cited by their full path from the repository root
  (`.claude/skills/changelog/SKILL.md`): the resolver's index skips the Claude directory, so a bare
  basename does not resolve. Never write a `file:NNN` line-number citation.
- **No product-changelog duplication.** Link to `docs/CHANGELOG.md`'s entry; do not restate it.

## The hook

`.claude/settings.json` carries a `PostToolUse` hook on `Bash` that, when the command contained
`git commit`, injects a one-line reminder to append the commit once it is validated. It reminds; it
does not write. The match is on the command's text, so a heredoc or a commit message that mentions
`git commit` also triggers it — a false reminder costs nothing, a missed one is what the hook exists to
prevent. If the reminder stops appearing after a Claude Code update, `/hooks` shows whether the hook
is loaded.
