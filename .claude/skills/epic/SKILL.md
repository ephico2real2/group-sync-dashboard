---
name: epic
description: Plan and run an EPIC — a group of issues delivered together — the way epics #381–#388 were built on 2026-09-26: measure every child's current state, draft the epic and refined children (via /issue), give it a picture (a committed HTML mockup rendered to PNG, or a mermaid flow), record the decisions and the operator's open questions, post and link children as sub-issues, close what is already done, then execute child by child and close the epic with its evidence and branch cleanup. Invoke when the operator groups work into an epic or asks to plan a theme.
---

# /epic — a group of issues, planned from facts and delivered together

The operator, 2026-09-26: *"create an epic for each group first and refine the issues now to align with our current
state and link them to the epics and vice versa and with clearly set of what done means for each issue and each
epic. Add screenshot or mockup html or render visually in each epic and then execute."* Children are written with
the `/issue` skill (`.claude/skills/issue/SKILL.md`).

## 0. Before an epic programme starts
- Everything merged, CI green on main, and main **tagged** (an annotated `checkpoint-<date>`; the
  `group-sync-dashboard-<version>` tags are chart releases, so never reuse that naming).
- **Branches are deleted only when an epic closes, each one proven first:** its tip is merged into main
  (`git merge-base --is-ancestor`), its PR is merged or closed, and nothing references it (the lab's Argo CD
  `targetRevision`, `gh-pages`, a doc that cites a commit only that branch reaches). If in doubt, keep it.

## 1. Draft (read-only research, in parallel)
Give each drafting seat one or two epics, the format (the `/issue` body and the epic body below) and these rules:
read-only on the repository, on GitHub and on the lab; write only in its own scratch directory; measure every child
(`gh issue view <n> --comments`, the code, the linked PRs, a read-only lab read); mark each child REFINE /
CLOSE-CANDIDATE / SPLIT / MOVE; list the decisions the orchestrator must make. The 2026-09-26 run found, before any
code was written: seven issues already shipped (#119, #131, #165, #170, #171, #230, #245), a proposed file name that would have deleted fresh backups, a gate
change that would have broken another feature, and a UI bug. That is what the measuring is for.

**Decide every open question on "easy to manage, best practice"**, and record it in the epic. A question only the
operator can answer (a policy, a credential they own, a restart of a shared service) is written as **Open for the
operator** and asked when that child is reached, never guessed.

## 2. The epic body

```
**Epic <letter>: <title>** · status: planned · checkpoint: `<tag>`

## Goal
One paragraph, plain English: what the user, operator or lab gets, and why it matters.

## Why now
Two to four measured facts, each with its source.

## Scope
**In:** the children, one line each. **Out:** what this epic does not do, and where that lives.

## Build order
| # | Issue | What it delivers | Depends on | Implementer | Size |

## Picture
A committed mockup PNG (screen work) or a fenced mermaid flow (back-end work), with a caption. Current vs proposed
is marked.

## Risks and guardrails
Never reduce the dashboard ServiceAccount's permissions (a rendered RBAC diff, REMOVED 0); PVCs are never removed;
no feature is removed or deprecated unless an issue says so and the operator agreed.

## Definition of Done (epic)
- [ ] Every child issue closed, with evidence pinned to a full merge sha.
- [ ] The epic-level outcome, as a check someone can run.
- [ ] Released: `prepare-release.py` cut, with the epic as the first bullet under the new `docs/CHANGELOG.md`
      heading; the release PR merged; `.github/workflows/helm.yaml` published the chart;
      `.github/workflows/publish.yml` published the application image when `--app` was used.
- [ ] The published release deployed to CRC through `release-crc.sh --argocd main`, walked, PVC UIDs unchanged.
- [ ] The branches this epic used are deleted, each proven merged first.
- [ ] The session changelog records the epic.

## Decisions settled (<date>)
## Added while drafting
```

## 3. The picture
- **Screen work:** a self-contained HTML mockup built from the app's real `app.css` and page markup, labelled
  PROPOSED, committed as `docs/design/<name>-mock.html` with its rendered `<name>-mock.png`, with a row in
  `docs/design/README.md` (held by `local-development/tests/test_design_index.py`). The epic embeds the PNG pinned
  to the merge sha: `https://github.com/<owner>/<repo>/blob/<sha>/docs/design/<name>-mock.png?raw=true`.
- **The mockup contract, which Grok (with a shell) enforced over three passes on #380:**
  - everything undashed is today's app, or is visibly marked "abridged";
  - every proposed element carries its **own** PROPOSED label (a dashed outline alone is not a label);
  - captions about proposed things sit inside the proposed marking;
  - the header and tab bar, if simplified, say so;
  - no horizontal overflow at 375 px, no page error, no external load, no claude.ai link.
- **Back-end work:** a ```mermaid block; GitHub renders it in the issue.

## 4. Post and link
1. Create the epics (label `epic` + `epic/<letter>`), then the new issues, then write every body once all numbers
   exist.
2. **Replace placeholders longest first:** `EPIC_A` is a prefix of `EPIC_A_CLUSTER_SECRET_EXAMPLES`.
3. Refine each child with `/issue`: new body, original kept collapsed, the label, and `addSubIssue`.
4. Read it all back from GitHub: sub-issue counts, every child's first line naming the epic, no placeholder left, the
   originals kept, images returning HTTP 200.
5. Close the CLOSE-CANDIDATES with evidence, each remainder filed and named first.

A state file makes the posting idempotent: record every created number, and skip what exists on a re-run.

## 5. Execute
Child by child, in the build order, per `.claude/skills/adversarial-review/SKILL.md`:
- research, then the spec and a spec review, then code by the implementer seat;
- review by the seats `.claude/skills/adversarial-review/SKILL.md` names: never the implementer, Grok (with a
  shell) always one;
- CI green, then a CRC deploy and walk, then evidence on the issue, then close.

Grok can help with a hard problem as an advisor, but its proposals are checked like any other.

## 6. Close the epic
**Every epic is released and deployed, a docs-only one included.** The operator, 2026-09-26: *"In agile. You have
deploy or redeploy every epic and cut a release note. So we are remaining true."* Never offer to skip either.

1. **Release.** On a clean checkout of `main` (`git status` empty: the script refuses a dirty tree and, unless you
   pass `--no-commit`, any branch other than `main`), run `local-development/prepare-release.py` with the *next*
   version and a one-line reason:
   - `--app X.Y.Z` when `local-development/gsd/` changed, or when any other path in `publish.yml`'s filter changed
     and this epic ships the image. The script also bumps the chart's patch unless you pass `--chart`.
   - otherwise `--chart A.B.C`, the next chart patch.

   The reason is the script's positional argument: the epic's title, for example `"Epic A: quick cleanup (#381)"`.
   It must be one line, contain a letter or a digit, and contain no `*` and no unbalanced backtick. The script
   replaces `## Unreleased` in `docs/CHANGELOG.md` with `## Application X.Y.Z — chart A.B.C — date` or
   `## Chart A.B.C — application X.Y.Z — date`, puts the reason as that heading's first bullet, and moves every
   spec marked `merged` in `docs/specs/README.md` to `released`. Add the epic's children to that first bullet.
   Review and merge the release PR as any other. After the merge, `helm.yaml` publishes the chart and retags the
   existing `:<appVersion>` image as `:<chart-version>`. `publish.yml` builds an application image only on an
   `--app` release; a `--chart`-only merge builds none (`docs/RELEASING.md`, the chart-only flow).
2. **Release note.** Once `helm.yaml` has created the GitHub release, write the epic's summary (the children, their
   merge shas, the lab evidence) into that release's body. The tag is the **chart** version just cut, not the
   application version: `gh release edit group-sync-dashboard-<chart-version> --notes-file <file>`.
3. **Deploy.** After those workflows are green, deploy the published release with
   `local-development/release-crc.sh --argocd main`. That mode uses the chart on GitHub at `main` and the published
   quay image (the mode table in the `release-crc.sh` header and in `local-development/README.md`). Bare
   `--argocd` builds HEAD and pins that image, so it is not the published release. Walk it, and record the two PVC
   UIDs before and after; they must be unchanged.

Then:
- Every Definition-of-Done box ticked.
- A summary comment: each child's merge sha, the lab evidence, what was deferred and where.
- The epic's branches deleted, each proven merged.
- The session changelog updated.
- Evidence and screenshots posted for the operator's review, before the next epic starts.
