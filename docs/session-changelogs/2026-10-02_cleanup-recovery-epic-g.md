# Session change log — group-sync-dashboard, 2026-10-02 → 2026-10-03

This log continues `docs/session-changelogs/2026-10-01_epic-e-release.md`, from the moment Epic E closed.

- **Times.** Times are git author or merge times in America/Chicago, from `git log --first-parent`. Lab instants are
  the cluster's UTC, as the commands printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the evidence lives.** Each lab walk is committed under `reports/`, and this log cites it by folder. The
  product changelog entry is `## Application 4.0.0 — chart 0.66.4 — 2026-10-03` in `docs/CHANGELOG.md`.

Outcome in one line: **the operator's three new requests delivered, then Epic G (#387) released as application 4.0.0
with chart 0.66.4 and walked on the lab. The requests: a weekly lab report, deleting reports and database copies from
the GUI, and recovery mode as its own workload. 19 PRs merged, #541 to #565.**

| | Before | After |
|---|---|---|
| main | `f8676198` (#540), 3.0.0 / chart 0.61.3 | `2c0a0ea4` (#565), 4.0.0 / chart 0.66.4 |
| deployed on the lab | 3.0.0 | 4.0.0 at `15613ccb95`, Synced and Healthy |
| Epic G (#387) | specs merged, no code | every child closed; released and walked; closes after this log merges |
| The lab's report schedule | `nightly-namespace-access`, daily | `weekly-namespace-access`, Sundays 22:00 New York |

---

## Part 1 — the operator's requests (2026-10-02 14:09 → 2026-10-03 00:05)

### The weekly report — PR #541, `2d20d0fb` (14:09)

- **The change.** `environments/crc.yaml` gains `weekly-namespace-access` (`0 22 * * 0`), replacing the nightly
  schedule.
- **Found by OB1-lite's review.** The quarterly and biweekly schedules fired at 06:00, outside the half-open
  22:00–06:00 window, and were silently skipped. They now fire at 05:00, and a test holds every lab schedule inside
  the window. The test failed on the old file (2 failed, 1 passed) and passes on the fix (3 passed).

### GUI deletion of reports and database copies (#542)

| Stage | PR | Merge |
|---|---|---|
| Spec (SPEC_H1) | #544 | `cc7a4462` |
| Implementation, 3.1.0 / 0.62.0 | #547 | `4e44fd02` |
| Walk | #549 | `a3394ba5` |

- **The spec author.** It ran 81 minutes. The orchestrator stopped it once its proof logs existed, and wrote §4.3 from
  them: hermetic 6864 → 6899, browser 657 → 660.
- **The spec review** was done in session, the operator's choice: 11 claims confirmed on the applied blocks.
- **The walk** (`reports/2026-10-02_gui-cleanup-542/`): one manual run deleted; 70 retired runs previewed, then
  deleted; one `pre-restore` copy deleted; the newest backup refused with 409; the lower tier refused with 403. 72
  audit lines were recorded.
- **Found by the session:** the copies card's layout, filed as #548.

### Recovery mode as its own workload (#532)

| Stage | PR | Merge |
|---|---|---|
| Spec (SPEC_E11) | #550 | `728e08ba` |
| Implementation, 0.65.0 | #551 | `1c9c929d` |
| Fix, 0.65.1 | #552 | `ddeda85d` |
| Walk | #553 | `c84eb93f` |

- **Found by run 1 of the walk.** On 0.65.0, recovery off ran as one Argo CD operation with no retries, but the app
  pod then waited 303 s. The cause is in kube-scheduler v1.35.0: on a delete,
  `interpodaffinity/plugin.go` L223–231 re-queues a waiting pod only when the deleted pod matches the waiting pod's
  own anti-affinity.
- **The fix.** The mirror term (#552), the operator's decision. Run 2 measured the app pod scheduled in the same
  second as the recovery pod's delete. Recovery off now takes 202 s; it took 12 min 49 s on 3.0.0.
- **Retracted.** The session's reading that Argo CD reverted §4d's hand edit while paused was wrong. Run 2's
  controller log shows the pause holds.
- **Not the product.** Run 1's later failures were CRC reboots from the operator's own experiment in another window.
- **Found by the session.** PR #552's body put the word "fix" directly before "#532", which GitHub reads as a closing keyword, and closed #532 early, before its walk. That is
  recorded on #532, and the keyword check now runs on every PR body.

## Part 2 — Epic G (2026-10-03 00:23 → 09:52)

Each child's spec was corrected before any block was applied, because the tree had moved since the specs were
written.

| Child | Spec correction | PR | Merge | Walk |
|---|---|---|---|---|
| G1 #239 | note 16: #542's five routes declared | #554 | `254f1515` | CI only (tests and docs) |
| G2 #255, 3.2.0 / 0.66.0 | note 5: block 41's anchor, the versions | #556 | `8fd1180c` | #557, `reports/2026-10-03_platform-users-255/` |
| G3 #503, 3.3.0 / 0.66.1 | note 6: block 57 onto G1's row, the versions | #558 | `aecc1c05` | #559, `reports/2026-10-03_acknowledged-grants-503/` |
| G4 #420 step 1, 0.66.2 | note 11: the versions, ten obsolete blocks removed | #560 | `878bbaed` | #561, `reports/2026-10-03_leases-role-420-step1/` |
| G4 #420 step 2, 0.66.3 | the marker flip of note 2 | #562 | `ec51f50b` | #563, `reports/2026-10-03_leases-role-420-step2/` |

- **G2.** The walk's own grant counted from the add stage on. A restart after its delete read the "before" numbers
  again (35 / 11 / 57), and the walk states every step against that.
- **G3.** "Before" was read on a walk branch at `983df2ff` (3.2.0) and "after" on 3.3.0: total 11 → 9, and
  acknowledged 2.
- **G4.** The narrowing removed a permission, with the operator's agreement on #420. Rendered RBAC: REMOVED 3, ADDED 0.
  - The new pod took the Lease 30.5 s after the old pod's last renewal, and renewed every 10 s on the Role alone.
  - `can-i` answers `no` in the five namespaces.
- **Found by CI on main.** One timeout in `test_t303_11` on Python 3.14 (`ddeda85d`). It did not reproduce in 1,100
  local and container runs, and is filed as #555.

## Part 3 — the release (2026-10-03 12:55) — PR #564, `15613ccb`

- **The number.** Epic G closed before Epic F, so it takes 4.0.0. The milestones were retitled: G is 4.0.0, F is 5.0.0.
- **Published.** All four workflows succeeded. `4.0.0`, `0.66.4` and `latest` share one digest per image: dashboard
  `ca7555fc…`, report `0940b84b…`.
- **Deployed and walked** (`reports/2026-10-03_release-4.0.0-walk/`, PR #565):
  - Synced and Healthy with no retries; health 200;
  - schema 20, matching the image's 20 migrations;
  - one live check per feature;
  - PVC UIDs unchanged.
- **#534 again.** `release-crc.sh`'s wait timed out on #534 once more.

---

## Numbers

| | |
|---|---|
| Commits authored | 29 non-merge commits between `f8676198` and `2c0a0ea4` |
| PRs merged | 19: #541, #544, #547, #549–#554, #556–#565 |
| Lab walks committed | 7 |
| Review passes | OB1-lite on #541 (one finding, applied); in-session reviews of SPEC_H1 and SPEC_E11; each spec correction proved by `apply-spec-blocks.py` against main |
| Defects found by tooling or the lab | the 303 s scheduler wait (walk run 1); the misplaced report schedules (review); one CI timeout (#555, unexplained) |
| Issues filed | #542, #543, #545, #546, #548, #555 |
| Longest single loss | the CRC reboots during #532's run 1, from a concurrent experiment. Written down so it does not recur: ask whether the CRC is free before a long walk. |

## Where things are recorded

- The specs: SPEC_H1, SPEC_E11 and SPEC_G1–G4 are `released` in `docs/specs/README.md`, each with its implementation
  notes.
- The walks: the seven folders above, indexed in `reports/README.md`.
- The decisions: on #542, #532, #420 and #503, and in the memory notes *gui-cleanup-and-weekly-reports* and
  *crc-shared-with-operator-experiments*.

## State left behind

- **The lab:** 4.0.0, chart 0.66.4. The dashboard ServiceAccount holds Leases only in its namespace.
- **The fleet-account Lease** has not been written since the narrowing: it is written on the next fleet bind or the
  daily ping.
- **Open:**
  - #534 (`release-crc.sh`'s wait), #535, #543, #545, #546, #548, #555;
  - Epic F (#386, now 5.0.0);
  - the operator's question on SPEC_T1's remaining parts (#239).
