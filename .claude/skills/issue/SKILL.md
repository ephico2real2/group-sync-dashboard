---
name: issue
description: Write or refine ONE GitHub issue in the detailed, measured format — where it stands today (file:line, PRs, the lab), the problem in plain English, the change, what must not change, a testable Definition of Done, the implementer and reviewers — keeping the original description and linking it to its epic as a sub-issue. Invoke when the operator files an idea, asks to refine an issue, or an epic needs a child written.
---

# /issue — one issue, measured, testable, linked

The operator, 2026-09-26: *"refine the issues now to align with our current state … with clearly set of what done
means for each issue … create an /epic skill and an /issue that will allow us to work in this detailed version on
ideas and specifications."* The format below is the one the 51 children of epics #381–#388 were written in (44 refined, 6 new, and the
operator chart's #70).

## The rules
- **Measure, never recall.** Every fact carries its source: `file:line`, a command and its output, a PR or issue
  number, a lab read (read-only). Anything not measured is written "not measured".
- **Plain English.** Two to five sentences for the problem. A cold reader must follow every sentence.
- **Never remove or deprecate a feature** unless the issue itself asks for it and the operator agreed. An innovation
  is a separate proposal, never folded into a fix (the operator, 2026-09-26, about #291).
- **Keep the original.** The refined body replaces the old one, and the old one is appended, collapsed:
  `<details><summary>Original description (filed <date>)</summary> … </details>`. Nothing the operator wrote is lost.
- **Already done?** Say so in "Where this stands", with the evidence (the PR, the merge sha, the file:line, a lab
  read), and close it with a comment pinned to main's full sha. File any remainder as its own issue first, and name
  it in the closing comment.

## The body

```
**Epic:** #<epic> — <epic title>

## Where this stands (<date>)
Measured bullets: what shipped since the issue was filed, what is still true, what changed.

## The problem
Plain English, two to five sentences.

## The change
What will be built. Where a spec is needed (a wire format, an auth flow, a migration, a deprecation), write
"Research first, spec second, code third" and name what to research.

## Must not change
Behaviour, features and permissions this issue must leave exactly as they are.

## Definition of Done
- [ ] A test for each behaviour, which fails before the change and passes after.
- [ ] The full hermetic suite and the browser suite are green; CI is green on the PR's head.
- [ ] (chart changes) a version bump; rendered RBAC before and after, REMOVED 0.
- [ ] Docs updated: <name them>.
- [ ] Reviewed by at least two seats other than the implementer, Grok (with a shell) always one of them, as
      `.claude/skills/adversarial-review/SKILL.md` sets out; decisions recorded on the PR.
- [ ] Deployed to CRC and walked; the evidence (and screenshots, for screen changes) committed under
      `reports/<date>_<slug>/` and posted here, pinned to the full merge sha.
- [ ] Issue-specific checks: <each one testable>.

**Implementer:** <seat> · **Reviewers:** <at least two seats, Grok one of them> · **Size:** <S/M/L>
```

**Seats:** OB1-lite (the default builder), Codex Astra (large mechanical work), OB3 (only the riskiest design work).
The reviewers are the seats that did not write the change; Grok is always one of them. Launch lines: the memory note
*seat-invocations*, and `.claude/skills/adversarial-review/SKILL.md`.

## Posting and linking

```sh
# refine: the new body, then the original kept, collapsed
orig=$(gh issue view <n> --json body,createdAt)
gh issue edit <n> --body-file <new-body-with-original.md> --add-label "epic/<letter>"

# link to the epic as a sub-issue (GitHub keeps the link both ways)
q='{ repository(owner:"ephico2real2", name:"group-sync-dashboard") { e: issue(number:<epic>) { id } c: issue(number:<n>) { id } } }'
gh api graphql -f query="$q"                        # read both ids
gh api graphql -f query='mutation { addSubIssue(input:{issueId:"<epic id>", subIssueId:"<child id>"}) { issue { number } } }'
```

A child in another repository of the same owner links the same way (proven with the operator chart's #70 under #388).

## Lessons, each from a real slip
- **Check the posted body, not the draft.** Read it back from GitHub: the first line names the epic, no placeholder
  is left (`EPIC_*`, `NEW-*`), and the original is kept. A cross-repository reference once came out doubled
  (`owner/repoowner/repo#388`) because the draft already carried the prefix.
- **Balance the code fences** in every body before posting: an odd number of fences swallows the rest of the page.
- **Test a file check with a real test, not a multi-path `ls`.** A brace-expanded `ls` over the drafts once reported
  every one missing when each existed; a `Path.exists()` per file in Python was the check that held.
