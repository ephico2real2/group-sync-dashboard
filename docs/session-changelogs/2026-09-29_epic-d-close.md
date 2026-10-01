# Session change log — group-sync-dashboard, 2026-09-29 → 2026-09-30

What this session did, when, and how each claim was measured. Times are git author times in America/Chicago; a PR's
merge time is its merge commit's on main; lab instants are the cluster's UTC as the commands printed them. Every
"measured" claim is one the session ran a command for; nothing below is recalled from memory alone. Two kinds of
measurement live only here, because their command output was not committed: the lab reads that this log is the only
record of (the Before table's failed sync at 2026-09-30 03:19:15Z, all of Part 1, and Part 4), and the local
full-suite totals of `merge_pinned.sh` (the session's merge helper, outside the repository: the hermetic AND browser
suites on the exact head it merges, so its totals are larger than CI's hermetic job; 6739 is also quoted on #492's
closing comment). A few other unpublished command outputs are labelled in place: the `registries.conf` mtime and the
31-of-31 re-run, Grok's 650-of-650 second pass on the browser file, `prepare-release.py` under the system Python, and
the review-pass counts from the session's scratchpad. Everything else cites a PR, a commit or a committed file. The session resumed after a laptop reboot, with the scope the operator set at
23:50 on 2026-09-29: this Mac only, Epics C and D only. The product changelog (`docs/CHANGELOG.md`) says what each
release changed for an operator; this says what a working session did.

Outcome in one line: **Epic D released as application 2.0.0 and closed — the lab re-synced after the reboot, #244
walked and closed, #492 found on that walk, fixed, walked and closed, the release cut and deployed, the composition
review passed (K1–K7) with its one runbook fix merged, the release walked with redaction proven by OCR; then Epic C's
last proofs walked (#291's live login, #285's tab row, #310's `userSelfLogin` renewal with `oauth/cluster` at
600 s, #445's step 6) and every child closed, the epic itself to close when this log merges; ten PRs merged
(#491, #493–#501).**

| | Before the session | After |
|---|---|---|
| main | `d874fbc6` (#489, 1.20.0 / chart 0.59.22) | `a3b17163` (#501), 2.0.0 / chart 0.59.25 |
| deployed on the lab | 1.19.0 (`ad102d9f1f`); Argo's sync to `d874fbc6` failed at 2026-09-30 03:19:15Z | 2.0.0 (`b40b5cf82a`), chart 0.59.25, Argo Synced at main and Healthy (the #310 handover re-created the nightly CronJob, clearing its failed run) |
| Epic D (#384) | #244 merged, not walked, open | closed; GitHub milestone 9 (2.0.0) closed at 19/19 |
| Epic C (#383) | lab items #445 step 6, #285, #286, #291, #310, #315, #288 open | every child closed with evidence; the epic and its milestone close once this log merges (the epic's Definition of Done asks for it) |

---

## Part 1 — the lab after the reboot (2026-09-29 23:47 → 23:49; lab reads, not committed)

- `crc start` exited 0. The Multus client certificate on the node runs 2026-09-30 03:34:04Z → 2026-10-01 03:34:04Z,
  and the newest `FailedCreatePodSandBox` event was 03:38:25Z (the pre-reboot fix), so hook pods could network.
- Before: PVC UIDs `f065b7a4-…` (data) and `08c7d45c-…` (report-artifacts), `gsd-cluster-shared-qa` rv 2981054,
  `/api/version` 1.19.0 through the pod loopback at 04:47:15Z.
- `16-keycloak` and `20-shop-envoy` showed the Route `parseableType` ComparisonError; the application controller was
  restarted, and all eight other Applications read Synced/Healthy 20 s later.
- The sync to `d874fbc6` was triggered at 04:48:26Z with the Application's own sync options and retry policy; it
  Succeeded at 04:48:39Z, and `/api/version` read 1.20.0 (`d874fbc619`) at 04:49:15Z with the PVC UIDs unchanged.
  Health stayed Degraded only for the nightly-report Job of 2026-09-30T02:00:00Z.

## Part 2 — #244 walked and closed (2026-09-30)

### The walk (00:18) — commit `283952c8`, PR #491

- OB1-lite (implementer) walked A–F on the lab at 1.20.0: all PASS; log and API `action` byte-identical (`cmp`, 130
  bytes) (`reports/2026-09-29_ca-244-walk/`).

### The review (00:40) — commit `d3bc341e`, merged `320f60b0`

- Grok and OB2 confirmed the four DoD lines and the redaction. **Found by OB2**, **Accepted**: the README's cause for
  "37 clusters" was wrong, and three redaction claims had no file. **Routed** to #492: the green `verified` chip above
  a verify failure. The decisions are in the commit message of `d3bc341e`, not in a PR comment.
- **Found by the pinned merge's local full suite**: 2 failures in `tests/test_release_crc.py` (the manifest-list tests,
  which call the real `oc` and are skipped on CI). Cause measured: `~/.config/containers/registries.conf` was corrupted
  at 22:44:24 on 2026-09-29 (a TOML error at line 8). Repaired from the file's own bytes; the test file then passed 31
  of 31, and the retry merged (local full suite 6735 passed).
- #244 closed with the DoD table and four screenshots pinned to `320f60b0`.

## Part 3 — #492, the `verify failed` chip (2026-09-30)

### The fix (01:02) — commit `f842627c`, PR #493

- OB1-lite (implementer) from OB2's proven patch: `ccTls` paints `verify failed` when the entry carries `action`.
  SPEC_D5's block 20 had to carry the new lines and the new test had to sit outside block 33, both measured by the
  spec check. Application 1.21.0, chart 0.59.23.

### The review (01:31) — commit `c8e5efd3`, merged `98433814`

- **Found by Codex** (C4) and Grok (F1): the neighbour test's narrowed locator hid the module-scoped Store's leak.
  **Accepted**: `cc_rig`'s teardown deletes `east`'s rows; on a copy without the cleanup the `[1280]` case fails with
  `['shared API URL', 'verify failed']`. Grok's second pass reported the whole browser file at 650 of 650.
- Merged at 1.21.0 (local full suite 6739 passed; 9 of 9 checks, quoted on #492's closing comment). Argo deployed
  1.21.0 at 07:00:59Z (same comment).

### The walk (02:20 → 02:43) — commits `0037e538`, `4f1dff45`, PR #494, merged `1173fe06`

- The first launch of the walker sent a literal `$(the brief)` placeholder; the walker rightly did nothing and was
  resumed with the brief.
- A–F PASS at 1280 and 375 px. Grok and OB2: the "Home, not the refusal card" reading was a same-document navigation
  read before its refresh painted. **Accepted**: the README rewrite, with the dim measured and committed
  (`evidence/P-precheck-dim.txt` in the walk folder), and the pin test. **Rejected**: the `walk.py` change (the script
  stays the one that produced the evidence) and Grok's full-sha point (no snippet).
- Merged (local full suite 6746 passed). #492 closed with the evidence pinned to `1173fe06`.

## Part 4 — the 2.0.0 release (2026-09-30)

### The release (03:04 → 03:05) — commits `691f2035`, `7bd377a9`, PR #495, merged `b40b5cf8`

- `prepare-release.py` under the system Python found no pytest and committed nothing, as designed; its edits were
  restored and it was re-run with the venv's Python. The epic's children were added to the first bullet.
- Grok and Codex found nothing to change; Codex's C6 corrected the brief's own wording (five render-diff classes).
- Deploy (lab reads): Argo tried `:2.0.0` before `publish.yml` had pushed it — `ImagePullBackOff` 08:38:24Z → pulled
  08:38:54Z (dashboard) and 08:38:47Z → 08:39:30Z (report), old pods serving (#410's race). The lab served 2.0.0 at
  08:48:22Z. `release-crc.sh --argocd main` then exited 1 at its 900 s Synced/Healthy wait: Synced throughout, never
  Healthy, solely for the nightly-report CronJob's failed 02:00Z run. It is owed a re-run after the next scheduled run
  succeeds.

## Part 5 — Epic D's composition review and the release walk (2026-09-30)

### The runbook (04:03 → 04:27) — commits `99974cdb`, `a39cece2`, PR #496, merged `eebc2f36`

- OB2's composition review at `b40b5cf8`: K1–K7 confirmed — 0 fleet binds from Refresh or Rejoin over 9 steps, Rejoin
  keeps `tlsClientConfig` and writes only its own entry, #244's log/API identity holds under any Rejoin credential,
  retired rows are inert (the verdicts are in #496's body).
- **Found by OB2** (K5), **Accepted**: the runbook did not say the TLS chip is the last poll's. One sentence, chart
  0.59.25, a test failing on main's runbook and passing after (proven on a copy).
- **Found by CI**, then Grok and Codex (C2): the changelog wrote `Chart 0.59.25`, and the Unreleased guard reads lower
  case. The orchestrator had run four test files, not the full suite, before pushing; the hermetic suite then passed
  6096 (quoted on #496).

### The release walk (05:18 → 06:25) — commits `7d6ef8df`, `2cc982ae`, `17e30a2a`, PR #497, merged `b6cf6a32`

- OB1-lite walked all 14 tabs and all 11 reports (four-way integrity PASS) at 2.0.0 / 0.59.25; Refresh on
  `mock-privateca` changed no Secret (`reports/2026-09-30_release-2.0.0-walk/`).
- **Found by the orchestrator's OCR check**: the Logins screenshot showed the fleet account's name (the mask landed on
  the `<span>` beside it) and the walk HTML embedded the same leak; every text check had passed. A Vision OCR tool was
  built, proven on the leaking image, and run over every PNG and embedded image; the walker fixed the mask, re-captured
  the tab and rebuilt the HTML, and the branch was squashed before its first push. Final: 0 of 88 PNGs, 0 of 65
  embedded images (`evidence/ocr-redaction.txt` in the walk folder).
- **Found by Grok and Codex**: README facts no file carried. **Accepted**: each now cites its file. The masks still
  miss a name split by `<mark>` or held in an `<input>`: **Accepted** on the fact, the code change **Rejected** here,
  and the gap written beside the mask claim.
- Merged (local full suite 6752 passed). The first description of #497 and the summary on #384 said "17 tabs"; the
  walk says 14, and both were corrected in place (**Found by** Grok's review of this log).
- Epic D closed with its summary; GitHub milestone 9 closed at 19/19.

---

## Part 6 — Epic C: the last proofs walked and every child closed (2026-09-30)

### Closed on existing evidence (10:13, GitHub's close time) — #315, #286

- Each checklist line mapped to its evidence and pinned on each issue's closing comment: #315 to #416 (`ed3edda7`)
  and its named tests (`test_credential_gate_account.py`), with `shared-rnd` polling `ok` at 15:11:51Z (a lab read
  through the pod's loopback, carried only by #315's closing comment); #286 to #422 (`b6797011`) and #444's re-count.

### The two outstanding proofs (11:00) — PR #499, merged `708e6be1`

- #291's live login as `developer`: `test_live_fleet_login.py` passed, challenging-client tokens 6 → 7 → 6; the fleet
  account 2 → 2. #285's fleet-account row captured at 1280 and 375 px with the name masked (OCR: 0 of 8, controls 1/1).
- **Found by the walker's own run** (run 1, 15:17:32Z → 15:18:56Z, kept in the walk folder): its shape check failed on
  the label read upper-cased (`innerText`), and its mask log counted 2 masked elements in the row, the instant too.
  Both fixed in the committed walker and the captures retaken, so the grant stood twice (84 s, 83 s).
- **Rejected** Codex's C3 on #499 (its sandbox could not run the OCR or read the Lease; Grok and the orchestrator ran
  both). #291 closed.

### #310 Part A (16:14) — PR #500, merged `57735e9e`

- Prepared with no cluster writes; the plan reviewed by OB3 and Grok, both GO WITH CHANGES. **Found by OB3**: a group
  SIGTERM could kill the log's `tee` so the trap died of SIGPIPE and left 600 s; the capture's stop always exited 1 and
  would have aborted the run after the observation. **Found by OB3 and Grok**: the restore had no retry and no restore
  command printed before the patch. All fixed (`8a02acd7`), proven on 17 stub exit paths.
- The auto-mode classifier blocked the first launch; the operator allowed it and phase 2 ran 20:17:40Z → 20:45:37Z, exit
  0: `oauth/cluster` at 600 s, two renewals of `developer`'s session at `renew_at` + one poll cycle, the new session in
  before the old revoked, polling unbroken (longest gap 60.1 s); the fleet account 0 authorizes; `31536000` restored and
  the lab left as found on 17 EQUAL lines. Analysis 14 passed.
- **Found by Codex** on the results: the walk README named the lab `developer` password's value. **Accepted**: removed
  in `69f16149`. #310 closed.

### #445, step 6 (18:58) — PR #501, merged `a3b17163`

- The step's rewrite was already merged in #461; the walk was owed. Prepared with no cluster writes; Cursor was out of
  usage, so OB3 took Grok's seat (the operator's ruling) beside Codex. **Found by OB3**: a signal during Argo's cascade
  could remove the keep-grant and print no hand-back; a failed hand-back exited 0. **Found by Codex**: second-precision
  bounds compared with MicroTime as strings, and the walk pod's tenure not its real lifetime. Both merged (`f0d397f8`);
  OB3's 15 stub scenarios pass.
- Phase 2 ran 23:08:15Z → 23:10:36Z, exit 0: the spec's program printed `HELD`, `ClaimHeld … until
  2026-09-30T23:12:38Z`, `RELEASED`; 0 authorizes for `developer` and the fleet account; the lab left as found on 15
  EQUAL lines. **Recorded, not applied** (OB3): the walks' `capture.sh audit` could report a false 0 after a malformed
  log line (not triggered: 0 of 38370).
- #445, #285, #288 and #238 closed, each with its evidence; the epic's branches proven merged and deleted.

---

## Numbers

| | |
|---|---|
| Commits authored | 28 (`git rev-list --no-merges --count d874fbc6..a3b17163`) |
| PRs merged | 10: #491, #493–#501 (issue #492 filed and closed on the way) |
| Review passes run | 29 completed: Grok 15, Codex 8, OB2 3, OB3 3 (one per review directory in the session's scratchpad; one Grok launch refused for usage, not counted) |
| Reviewer findings accepted / rejected | not counted here: each PR's decisions are in its comment or, for #491, in commit `d3bc341e` |
| Defects found by tooling rather than reviewers | 5: the pinned merge's local full suite (the corrupted `registries.conf`), CI (the changelog case), the OCR check (the mask), the #499 walker's first run (the upper-cased label, the mask over the instant) |
| Full suite, final | 6777 passed, 22 skipped — `merge_pinned.sh`'s local run (hermetic and browser) on `1dbc15b2`, not published; CI's hermetic job on the same head: 6127 passed, 21 skipped |
| Longest single loss | a walker launched with a literal placeholder instead of its brief — one round trip |

## Where things are recorded

- Review decisions: the comments on PRs #493–#501; for #491, the message of commit `d3bc341e`.
- Evidence: `reports/2026-09-29_ca-244-walk/`, `reports/2026-09-30_chip-492-walk/`,
  `reports/2026-09-30_release-2.0.0-walk/`, `reports/2026-09-30_epic-c-proofs/`,
  `reports/2026-09-30_selflogin-renewal-310/`, `reports/2026-09-30_claimheld-step6-445/`.
- The release: `docs/CHANGELOG.md` (Application 2.0.0), the GitHub release group-sync-dashboard-0.59.24, the summary on
  #384.

## State left behind

- Lab: 2.0.0 / chart 0.59.25, Argo Synced at main and Healthy; `oauth/cluster` `31536000`; nothing carries a walk
  label; PVC UIDs unchanged; `shared-qa` rv 2981054.
- Owed: the operator's decision on the fleet account's name already in 30 images and 156 text files on main (quoted on
  #384's summary); the walks' `capture.sh audit` fix for the next walk's copy; the step 6 spec's two prose slips (open
  question 6 in the #445 walk's README).
