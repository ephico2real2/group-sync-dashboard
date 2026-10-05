# Session change log — group-sync-dashboard, 2026-10-03

This log continues `docs/history/session-changelogs/2026-10-02_cleanup-recovery-epic-g.md`, from the moment its PR (#566)
merged.

- **Times.** Times are git author or merge times in America/Chicago, from `git log --first-parent`. Lab instants are
  the cluster's UTC, as the commands printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the product change is described.** The `## Unreleased` section of `docs/CHANGELOG.md`.

Outcome in one line: **the release wait fixed (#534), SPEC_T1's remaining parts withdrawn, the 4.0.0 release walked
end to end, and Epic F's first step shipped: a report's sha256 now covers its data only (#270, application 4.1.0,
chart 0.66.5). 6 PRs merged, #567 to #572.**

| | Before | After |
|---|---|---|
| main | `94f5ebbb` (#566), 4.0.0 / chart 0.66.4 | `fba80ff3` (#572), 4.1.0 / chart 0.66.5 |
| deployed on the lab | 4.0.0 | 4.1.0 at `a38c3b0c`, Synced and Healthy |
| Epic F (#386) | not started | step 1 of 6 closed (#270); #106 next |
| `release-crc.sh --argocd main` with nothing to sync | timed out at 900 s | Synced and Healthy in 3 s |

---

## Part 1 — release tooling and the spec index (14:55 → 15:22)

### The release wait (14:55 → 15:09) — commits `48ea1a2d`, `55b48230`, PR #567

- **The defect (#534).** `argocd-wait.sh` compared the Application's `spec.source` with `status.sync.comparedTo`
  as JSON text. Argo CD writes the status from Go structs whose `valueFiles` and `parameters` are `omitempty`
  (argo-cd v3.4.7 `types.go`), so an empty list in the spec never matched and the waiter ran to its 900 s timeout.
- **The fix,** from SPEC_A4's three blocks: both sides drop empty values before comparing. The new test is
  `test_waiter_reads_an_empty_field_as_argo_cd_does`.
- **Measured on the lab:** `release-crc.sh --argocd main` returned Synced/Healthy in 3 s.

### SPEC_T1 withdrawn (15:22) — commit `3ded3a2d`, PR #568

- On the operator's word (2026-10-03), the remaining parts of `docs/specs/SPEC_T1_tier_model.md` were withdrawn.
  Its delivered parts stay as released; the index row says so.

---

## Part 2 — the 4.0.0 release walk (15:14 → 15:37) — commit `99615b67`, PR #569

- **Asked for by the operator** ("Where is last walk that I asked for?"). The earlier 4.0.0 walk had been CLI-only.
- **Measured:**
  - main pass 84 of 84 steps, second pass 24 of 24;
  - all 11 reports generated, downloaded as PDF, HTML and JSON, with 11 of 11 passing the four-way integrity check;
  - the five 4.0.0 surfaces captured view-only;
  - macOS Vision OCR of 80 PNGs gave 15,272 lines, 0 of them `sha256~`.
- **Run 1 did not walk:** `run_walk.sh` needs the venv under its own repository. Run 2 called it from the main
  checkout.
- **The evidence** is `reports/2026-10-03_release-4.0.0-e2e-walk/`; its PDF was sent and not committed.

---

## Part 3 — Epic F step 1: the seal covers the data only (#270) (15:12 → 17:19)

### The spec (15:12 → 15:50) — commits `7f9c8bb1`, `1f669f8a`, PR #570

- **The spec** is `docs/specs/SPEC_F1_data_only_seal.md`. Page one (Provenance and coverage) becomes a section with
  `sealed=False`; its data facts are sealed through `api_url` and `sealed_provenance`.
- **The probe** built all 11 reports twice over one seeded snapshot: every hash differed, and page one was the only
  difference for 10 of them.
- **Found by the in-session review:** the CHANGELOG block made a second `## Unreleased`, because #567 had created
  one first. `test_kyverno.py`'s f3 test failed on it. The block was corrected in the spec.

### The implementation (15:53 → 16:54) — commits `041c0c37`, `3d7b41f2`, `647d6ef8`, `335f19f7`, PR #571

- **Found by the orchestrator, before review.** The walk's `local-development/e2e-walk/integrity_check.py` keeps its
  own copy of the canonical keys, and the spec had missed it: the next walk would have flagged all 11 reports.
  Written into the spec as Block 13 and T270-7. T270-7 fails on main's script (AttributeError).
- **Review of `3d7b41f2`:** Codex (gpt-5.6-sol, xhigh) and OB3 (in Grok's seat; Cursor was out of usage).
  - Both confirmed the seal: a mutation of every page-one row, byte-identical renders apart from the hash, no
    stored run recomputed.
  - **Accepted:** the docs said two runs over one snapshot "hash the same" with no exception. Five builders read
    `ctx.now`, and OB3 found `dormant-access` changing two minutes apart on a cutoff edge.
  - **Accepted:** a pre-4.1.0 `.json` crashed the walk's check, and the walk then lost its document (OB3).
  - **Accepted:** only page one may be unsealed (OB3).
  - **Accepted:** the walk document's recipe (OB3).
  - **Rejected:** Codex's test that greps seven terms in five docs, because it pins wording. OB3's T270-10 pins the
    clock-reading set from the source.
- **Proof.** The corrected spec applied to a clean main reproduced the reviewed target byte for byte. T270-8 to 11
  fail on `3d7b41f2` (4 failed). Full hermetic suite: 8072 passed, 26 skipped, 5 xfailed. Rendered RBAC: 62 rules,
  REMOVED 0. CI and publish were green on main.

### On the lab (16:54 → 17:19) — commit `487c9ea4`, PR #572

- **Found by the deploy:** the #410 race again. Argo CD synced before `:4.1.0` existed; the dashboard, report and
  bind-hook pods sat in `ErrImagePull`. They started on their own: the dashboard at 21:56:40Z, the report pod at
  21:57:31Z.
- **Measured:** two viewer runs of `groups` by `dana.lee`, 11 s apart over the snapshot
  `2026-10-03T22:02:49.597664Z`, both sealed `9b7b51a6…`. Run ids and page one differed; the sealed sections were
  equal; `recompute()` matched both. PVC UIDs unchanged.
- **The evidence** is `reports/2026-10-03_data-only-seal-270/`. #270 is closed with it, pinned to `a38c3b0c`.

---

## Correction to the previous log

`docs/history/session-changelogs/2026-10-02_cleanup-recovery-epic-g.md` says, under "State left behind", that the
fleet-account Lease "has not been written since the narrowing". That was a stale read. The Lease had been written at
18:06:22Z by a ping, outcome ok, on the Role alone. The correction was posted on #387 the same day.

## Numbers

| | |
|---|---|
| Commits authored | 11 non-merge commits between `94f5ebbb` and `fba80ff3` |
| PRs merged | 6: #567 to #572 |
| Lab walks committed | 2 |
| Review passes | an in-session review of SPEC_F1; Codex and OB3 on #571 (5 findings accepted, 1 test rejected) |
| Defects found by tooling rather than reviewers | the spec's second `## Unreleased` (the test suite); the #410 image race (the deploy) |
| Full suite, final | 8072 passed, 26 skipped, 5 xfailed on `335f19f7` |
| Longest single loss | the walk the operator asked for, first delivered CLI-only. Written down so it does not recur: a release walk is the full e2e walk |

## Where things are recorded

- The specs: SPEC_A4, SPEC_F1 (with the review's decisions as Orchestrator's notes) and SPEC_T1, in
  `docs/specs/README.md`.
- The walks: the two folders above, indexed in `reports/README.md`.
- The decisions: on #571 (the review), #270 and #386 (Epic F's progress).

## State left behind

- **The lab:** 4.1.0, chart 0.66.5, Argo CD Synced and Healthy at `a38c3b0c`.
- **Open for the operator:** SPEC_F1's open question 1, whether report windows should end at the snapshot's stamp.
- **Next:** #106 (`csv` as a format), then #108, #109, #140 and #392. Epic F releases as 5.0.0.
- **Open:** #535, #543, #545, #546, #548, #555.
