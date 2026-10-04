# Session change log — group-sync-dashboard, 2026-10-03 → 2026-10-04

This log continues `docs/session-changelogs/2026-10-03_seal-and-tooling.md`, from the moment its PR (#573) merged.

- **Times.** Times are git author times in America/Chicago, from `git log`. Merge instants and lab instants are UTC,
  as `gh` and the cluster printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the product change is described.** `docs/CHANGELOG.md`, under `## Application 5.0.0 — chart 0.70.1 —
  2026-10-04`, and the GitHub release `group-sync-dashboard-0.70.1`.

Outcome in one line: **Epic F finished and released: CSV, report diffs, webhook delivery, the stale-schedule alert and
a ticket key of its own, each specified, reviewed, deployed and walked. The Tech debt milestone was cleared in one
sweep. Application 5.0.0 and chart 0.70.1 are published, deployed and walked end to end: 20 PRs merged, #574 to
#606.**

| | Before | After |
|---|---|---|
| main | `8b1afe94` (#573), 4.1.0 / chart 0.66.5 | `75e88d91` (#606): 5.0.0 / chart 0.70.1, released at `704943a11c` (#605) |
| deployed on the lab | 4.1.0 | 5.0.0 at `704943a11c`, Synced and Healthy |
| Epic F (#386) | step 1 of 6 closed (#270) | every child closed; released as 5.0.0 |
| "Tech debt" milestone | 14 open | 0 open, 14 closed |

---

## Part 1 — Epic F, steps 2 to 6 (2026-10-03 17:38 → 2026-10-04 03:18)

Every step went the same way:
- the spec, applied with `local-development/apply-spec-blocks.py`;
- the code, applied from the spec's blocks;
- two reviewer seats, neither of them the author;
- the review's decisions written into the spec as Orchestrator's notes before the code;
- a CRC deploy and a lab walk, with the evidence under `reports/`;
- the issue closed against the evidence's merge sha.

### F2, CSV as a fourth format (#106) — commits `4ce52a2d` → `c2889e40`, PRs #574, #575, #576, #580

- **Shipped:** application 4.2.0, chart 0.66.6. `environments/crc.yaml` has the lab's schedules store CSV (#576).
- **Reviewed by Codex and OB3** (in Grok's seat; Cursor is out of usage).
  - **Accepted:** floats laid out as ECMAScript does (OB3's fix), and a ticked CSV that survives a repaint (OB3).
  - **Rejected:** Codex's float fix, because it converts every integer to a double and rounds one above 2**53.
- **Full suite:** 8115 passed, 26 skipped, 5 xfailed. Lab evidence: `reports/2026-10-03_csv-format-106/`.

### F3, `report-diff` (#108) — commits `0ae35e27` → `f3d82d81`, PRs #578, #579, #582

- **Shipped:** application 4.3.0, chart 0.66.7.
- **Reviewed by Codex and OB3.** Accepted:
  - a diff recomputes its inputs' seal;
  - coverage is compared as one block, Codex's version. OB3's version kept "No change" and only added a warning, so
    it was rejected.
  - the picker pages past the newest 100 runs;
  - the Library listing counts diffs.
- **Full suite:** 8153 passed, 26 skipped, 5 xfailed.
- **Lab evidence** (`reports/2026-10-04_report-diff-108/`): "No change" over the same data, and exactly the planted
  RoleBinding after the refresh.

### F4, webhook delivery (#109) — commits `7b0ef24f` → `74e19202`, PRs #581, #583, #584

- **Shipped:** application 4.4.0, chart 0.67.0.
- **Reviewed by Codex and OB3.** Accepted:
  - every attempt held to the deadline;
  - a failed artefact read named `omitted` while the other runs are still delivered;
  - the 5 MiB cap checked on the bytes read;
  - a malformed `Retry-After` falling back to the backoff.
  - The wording "four times" became "up to 4 attempts".
- **Full suite:** 8175 passed, 26 skipped, 5 xfailed.
- **Lab evidence** (`reports/2026-10-04_webhook-delivery-109/`): one CloudEvent per run, and the URL in no log.

### F5, the stale-schedule alert (#140) — commits `4406a749` → `5c3097cb`, PRs #586, #596, #599

- **Shipped:** application 4.5.0, chart 0.68.0.
- **Reviewed by Codex** (no findings) **and OB3.**
  - **Accepted:** OB3's README alert count (Block R1, held by T140-5b).
  - **Accepted:** its measured observation that a `Recreate` restart leaves a gap and `for:` restarts, written into
    two comments.
- **Filed while specifying:** #585, cron names.
- **Full suite:** 8195 passed, 27 skipped, 5 xfailed.
- **Lab evidence:** `reports/2026-10-04_schedule-stale-alert-140/`.

### F6, a ticket key of its own (#392) — commits `2e800e7f` → `27ad4832`, PRs #597, #601, #602

- **Shipped:** application 4.6.0, chart 0.69.0.
- **Two corrections at implementation**, written into the spec first: its version blocks followed F5's 4.5.0 / 0.68.0,
  and F5's tests needed the ticket key. Without the second, 4 tests failed.
- **Reviewed by OB2** (accept, no findings) **and Codex.** Accepted: Codex's one finding, an authenticated payload
  that is not a JSON object, now refused as a `TicketError`.
- **Full suite:** 8220 passed, 27 skipped, 5 xfailed.
- **Lab evidence** (`reports/2026-10-04_ticket-signing-key-392/`): a forged ticket got 401 and 403; a real one got
  202.

### Closed without new code

- **#149:** the operator chose the waiver, which cites #154's test.
- **#410:** part A had shipped in `c825182c` (PR #529). Part B is held as #598.

## Part 2 — the Tech debt sweep (2026-10-04 03:15 → 04:27) — PRs #603, #604

- **Fourteen issues, one commit per batch:** `fef2e10a`, `a0fdd1cd`, `1a3aed84`, `f34658fe`, `33c7e23a` and
  `aa5517bd`. Codex Astra wrote them.
- **The version commit:** `6fbeb82b`, application 4.7.0, chart 0.70.0.
- **Decided by the operator during the session:**
  - PDF is refused on every scheduled path (#594); manual runs keep it, and the HTML prints.
  - Two questions only the operator can answer were filed as #592 and #593.
  - The manifest loader was parked as #600.
- **#555's cause, measured** on GitHub's runners with probe PR #595 (closed unmerged): a SIGTERM that lands before
  `time.sleep` waits out the sleep. The original script timed out 6 times in 3,600 runs; the wakeup-pipe fix, 0 times.
- **Found by the full suite:** `test_p2_selectors.py` still sent `--format pdf` to the trigger (`70962730`).
- **Reviewed by Codex and OB1-lite** (`db43c399`, `02c40ccc`).
  - **Accepted:** OB1-lite's three findings: a stale CronJob comment, a #591 test that could not fail, and the
    CHANGELOG's bullet order.
  - **Accepted on the fact, with a wider fix:** Codex's `MON/2` finding. The same line gave numeric `1/2` a Sunday
    that Kubernetes never fires, so `_field` was fixed for both. 3 of the 5 new cases fail before the fix.
  - **Rejected:** Codex's commit-fold request, because history order is not the tree.
- **Lab evidence:** `reports/2026-10-04_tech-debt-sweep-470/`. The walk ran twice. The first read the CronJobs' `args`
  (null) and cut the Backups heading off, so `run.sh` and `walk.py` were corrected; the README says so.
- **Closed:** all 14 issues, each with its evidence at `1bad1947`.

## Part 3 — release 5.0.0 (2026-10-04 04:41 → 08:04) — PRs #605, #606

- **The cut:** `prepare-release.py --app 5.0.0` (`6f433bf9`). The first bullet names the epic's children (`f3a9cef6`).
- **Review:** Codex confirmed C1 to C4, with an empty patch.
- **Retracted:** my review comment said the 4.0.0 release PR had also had one seat. #564 carries no review comment, so
  the phrase was removed from the comment.
- **Published:** `publish.yml` and `helm.yaml` succeeded. skopeo 1.13.3 read one digest per image across `5.0.0`,
  `0.70.1` and `latest`, labelled 5.0.0 at `704943a11c`.
- **Deployed:** `release-crc.sh --argocd main` gave Synced and Healthy at `704943a11c`, with the PVC UIDs unchanged.
- **The e2e walk,** run with the operator's go-ahead (`reports/2026-10-04_release-5.0.0-e2e-walk/`):
  - main pass 84/84, second pass 24/24, all 11 reports integrity-checked;
  - the Epic F surfaces read with `oc`.
  - The first schedule-status read used `/metrics`, not `/report/metrics`, and printed nothing. The corrected read is
    an addendum: 16 series.
- **The release note** is on `group-sync-dashboard-0.70.1`. The walk PDF went to the operator; the HTML is committed.
- **The epic's seal check, as its Definition of Done words it** (`reports/2026-10-04_epic-f-seal-check/`). The
  earlier walks had proved the seal on `groups` and `access-certification`; the epic names `compliance-snapshot`, so
  it was run as written:
  - two runs one after the other on one snapshot: both sha256 `161cba2f…`;
  - the scheduled run on an older snapshot: `61b5b1c8…`;
  - a `report-diff` between the two: 3 blocks changed, with bindings 110 → 107 and unmanaged 61 → 58.
- **Found by that check:** two of the 3 changed blocks were only instants, "Last poll" and the capture note's
  "last read". On the static `mock-trusted` cluster, a diff across snapshots reported exactly those 2 blocks and
  nothing else. Filed as #607 in the Tech debt milestone, the class #589 fixed.

---

## Numbers

| | |
|---|---|
| PRs merged | 20 before this log's own: #574–#576, #578–#584, #586, #596, #597, #599, #601–#606; probe #595 closed unmerged |
| Issues closed | 21: #106, #108, #109, #140, #149, #392, #410, #535, #543, #545, #546, #548, #555, #577, #585, #587–#591, #594 |
| Issues filed | #585, #592, #593, #594, #598, #600, #607 |
| Review passes | 13: two seats on each of F2–F6's implementation PRs and on the sweep, one on the release |
| Full suite, final | the sweep's head: 8293 passed, 27 skipped, 5 xfailed before its one test fix, which was verified in its own file and in CI |
| Lab walks committed | 8 (the seal check included) |
| Longest single loss | the 4.7.0 walk's first pass, whose CronJob read proved nothing. Written down so it does not recur: read the field the data is actually in before claiming its absence |

## Where things are recorded

- **The specs:** SPEC_F2 to SPEC_F6, with their Orchestrator's notes, now `released` in `docs/specs/README.md`.
- **The walks:** the eight folders above, indexed in `reports/README.md`.
- **The decisions:** on each PR (#575, #579, #583, #596, #601, #603, #605) and on #386.

## State left behind

- **The lab:** 5.0.0, chart 0.70.1, Argo CD Synced and Healthy at `704943a11c`, with the PVC UIDs unchanged.
- **Open for the operator:** #592 and #593.
- **Next:** #607, the one Tech debt item left, found after the release.
- **Held:** #598. **Parked:** #600 and Epic P (#388).
- **Kept on purpose:** the branch `probe/555-sigterm-race`, because #555's evidence cites a commit only it reaches.
