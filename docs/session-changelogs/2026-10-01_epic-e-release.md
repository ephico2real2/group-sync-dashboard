# Session change log — group-sync-dashboard, 2026-10-01 → 2026-10-02

What this session did, when, and how each claim was measured.

- **Times.** Times are git author times in America/Chicago, and a PR's merge time is its merge commit's time on main.
  Lab instants are the cluster's UTC as the commands printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the evidence lives.** Each child's lab walk is committed under `reports/` and cited by folder. Part 4's
  release reads were not committed; this log and the GitHub release `group-sync-dashboard-0.61.3` are their record.
- **The working rule.** The operator set it for this session: research first, spec second, code third. Every
  child was specced and its spec merged before any code. Code was applied only from the spec's implementation blocks,
  and a block that failed was corrected in the spec first, with the reason under its Orchestrator's notes.
- **The product changelog.** The application 3.0.0 entry in `docs/CHANGELOG.md` says what the release changed for an
  operator. This log says what the session did.

Outcome in one line: **Epic E (#385) released as application 3.0.0 with chart 0.61.3 and deployed to the lab. Ten
specs (E2–E10 and W1) and Epic G's four (G1–G4) were written and merged. Ten Epic E PRs merged, and seven walks were
committed under `reports/`. 32 PRs merged in all (#504–#531, #536–#539).**

| | Before the session | After |
|---|---|---|
| main | `5c03a9b1` (#502), 2.0.0 | `7ac6339f` (#539), 3.0.0 / chart 0.61.3 |
| deployed on the lab | 2.0.0 | 3.0.0 at `7ac6339f57`, Argo CD Synced and Healthy, offsite backup on to the PVC destination |
| Epic E (#385) | specs not written | every child closed; released and deployed; closes after this log merges |
| Epic G (#387) | specs not written | SPEC_G1–G4 merged (#506, #508, #510, #517); no code yet |

---

## Part 1 — specs before code (2026-10-01 07:08 → 2026-10-02 09:32)

- Mockups for Epics E and G (#504), and the restore mock's Helm values (#505).
- Epic E's specs: E2 #507, E3 #512, E4 #509, E5 #511, E6 #513, E7 #514, E8 #515, E9 #516, and E10 #536, which was
  written after #300's walk found the runbook defects.
- Epic G's specs: G1 #506, G2 #508, G3 #510, G4 #517.
- SPEC_W1 (#519) holds #426, which the operator named the north star: specified only, not built now.

## Part 2 — Epic E built, child by child (2026-10-01 19:45 → 2026-10-02 10:52)

Each child went through the same steps: OB1-lite implemented it from its spec, one review, the merge, then a CRC
walk, except #529 and #530, which have no walk folder. Each walk's evidence is committed under `reports/` and posted
on the issue, pinned to the merge sha.

- **#303, recovery mode (SPEC_E2): PR #518, `64d52877`, 2026-10-01 19:45.** Walk: `reports/2026-10-01_recovery-mode-303/`.
- **#302, `restore-db.sh` (SPEC_E3): PR #520, `093e17fe`, 21:06.** Walk: `reports/2026-10-02_restore-db-302/`.
  - The walk restored a real copy from schema 21 to 20, and every history table equalled the copy.
  - **Found by CI:** a test passed locally and failed only on Linux. The harness fed the helper to Python as a file,
    and on Linux `/dev/stdin` then resolves to the file, so that file's directory came first on `sys.path` and
    imported the wrong `gsd`.
  - **The first hypothesis was refuted:** it blamed the working directory, and a measurement refuted that before
    any fix was written. That measurement was not committed; the memory note *python-dev-stdin-file-vs-pipe* is its
    record.
  - The fix (pass the text with `input=`) was corrected in the spec first: SPEC_E3, Orchestrator's note 23.
- **#391, per-pod backup rotation (SPEC_E4): PR #521, `721a78db`, 21:37.** Walk: #523.
- **The lab's offsite backup to its PVC: PR #522, `7c9ba624`, 22:04 (operator's request).** It set
  `backup.offsite.enabled` and `destination.type: pvc` in `environments/crc.yaml`.
  - **Found by CI:** the change needed two rows in `environments/README.md`'s key table.
- **#304, the offsite backup on by default (SPEC_E5): PR #524, `934a9fab`, 22:38.** Walk:
  `reports/2026-10-02_offsite-default-304/` (#525).
- **#306, the KPI page's Backups card (SPEC_E6): PR #526, `c57f2927`, 23:19.** Walk:
  `reports/2026-10-02_kpi-backups-306/` (#527).
- **#300, the schema line and the runbook's checks before an upgrade (SPEC_E7): PR #528, `2e7d33be`, 2026-10-02
  00:29.** Walk: `reports/2026-10-02_runbook-schema-line-300/` (#531).
  - The walk measured #532: recovery mode, switched off under Argo CD, waited 12 min 49 s on Argo CD's retry backoff.
  - It also found the runbook defects that became #533.
- **#410 PR A, the chart-publish label gate and the chart-version check (SPEC_E8): PR #529, `ffe9de32`, 01:03.**
- **#425, `:latest` follows the newest signed main build (SPEC_E9): PR #530, `521c2bb0`, 02:02.**
  - The publish run on `521c2bb0` moved both images' `:latest` after `attest`.
  - **Found by the session:** `cosign` v2.4.1 cannot read the v3 signature bundles; v3.1.3 verifies them. Filed as #535.
- **#533, runbook corrections and the break glass under Argo CD (SPEC_E10): PR #537, `f0964580`, 10:52.** Walk:
  `reports/2026-10-02_runbook-corrections-533/` (#538).
  - **Found by the operator:** I had applied the rule "values file only, Argo CD is a conduit" to an incident
    procedure without asking. The operator's procedure replaced it: pause Argo CD, edit by hand, restore, reconcile
    git, then unpause.
  - Measured on the lab:
    - pausing alone did not stop the running operation;
    - `argocd app terminate-op` ended it in at most 2.08 s;
    - the app was back 40.5 s after unpausing;
    - the restored template differed in 0 of 163 fields.

## Part 3 — the release (2026-10-02 11:17) — PR #539, `7ac6339f`

- Cut with `prepare-release.py --app 3.0.0`: chart 0.61.3, and SPEC_E2–E10 moved to `released`. The script could not
  open the PR because the branch was not yet pushed, so it was pushed and the PR opened by hand.
- **Found by CI:** SPEC_G2 said app 2.6.0, no longer above the new tree. The test stops at the first spec it fails, so
  CI named only G2; SPEC_G3, at app 2.5.0 with chart 0.61.3, broke the same rule and was moved with it.
  - Under SPEC_E5's version rule each moved to the next free number, keeping its kind of bump and its order: G3 to
    app 3.1.0 with chart 0.61.6, G2 to app 3.2.0 with chart 0.63.0 kept.
  - Fixed in commit `c7e986f8`, then merged.
- CI on `7ac6339f`, from the run's log:
  - unit and integration, on both 3.11 and 3.14: 6829 passed, 23 skipped, 661 deselected, 5 xfailed;
  - browser tests: 657 passed.
  - `Release Charts`, `publish` and `mock-openshift` succeeded too.

## Part 4 — published, deployed and walked (2026-10-02 16:28Z → 16:47Z; lab and registry reads)

- **The images on quay.** Read with skopeo 1.13.3: the tags `3.0.0`, `0.61.3`, `latest` and `3.0.0-7ac6339f57` resolve
  to one digest per image, labelled version 3.0.0 and revision `7ac6339f57`.
  - dashboard: `sha256:340030e8…`
  - report: `sha256:7a6012fd…`
- **The deploy.** Argo CD auto-synced `main` before the script ran: its operation finished at 16:20:48Z, and the pods
  started at 16:18:39Z.
- **#534 measured again.** `release-crc.sh --argocd main --values environments/crc.yaml` timed out after 900 s on
  "status is for the previous spec". The Application's spec and its last sync differed only in `"parameters": []`.
- **The walk.**
  - `/healthz` returned 200, and `/readyz` returned 200 with 6 clusters.
  - `/metrics` reported `gsd_build_info{branch="main",commit="7ac6339f57",version="3.0.0"}`.
  - The database is at `PRAGMA user_version` 20, the same as main's migrations.
  - No `GSD_RECOVERY_*` variable is set, and the dashboard pod has 0 restarts.
  - The offsite CronJob runs `:3.0.0`.
- **The PVCs.** The three UIDs did not change across the deploy:
  - data `f065b7a4-535c-4ef1-868c-58f5afee4953`;
  - report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`;
  - backup-offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`.
- **The offsite default, rendered on `7ac6339f`.** A default `helm template` renders the offsite ServiceAccount,
  ConfigMap, PVC, bind Job and CronJob. With `persistence.enabled=false reporting.enabled=false` it renders none.
- **The release note.** The epic summary was written into the GitHub release `group-sync-dashboard-0.61.3`.
- **Branch cleanup.** 26 Epic E branches were deleted, each re-proven first: its tip an ancestor of `origin/main`,
  and its PR merged.
  - Kept: `feat/410-promote-release-branch` (#430 is open), `feat/426-rollout-blue-green` (moved out), and Epic G's
    spec branches.

---

## Numbers

| | |
|---|---|
| Commits authored | 73, all by the operator's identity, between `5c03a9b1` and `7ac6339f` |
| PRs merged | 32: #504–#531, #536–#539 |
| Review passes run | not totalled in this log; OB2 held Codex's review seat while Codex and Cursor were out of usage, and each PR records its review and decisions |
| Reviewer findings accepted / rejected | not totalled in this log; each PR records its own |
| Defects found by tooling rather than reviewers | 4 by CI: #520's Linux-only `sys.path`, #518's missing reports-index row, #522's missing key-table rows, #539's spec version ladder |
| Full suite, final | CI on `7ac6339f`: 6829 passed on both Python 3.11 and 3.14; 657 browser tests passed |
| Longest single loss | the release-crc wait, 900 s on #534's empty `parameters` list, and earlier one wait on a revision that moved after main merged; both were settled by reading the lab directly |

## Where things are recorded

- The specs: `docs/specs/README.md`, with SPEC_E2–E10 `released`, SPEC_G1–G4 and SPEC_W1 `specified`.
- The walks: the seven `reports/2026-10-0*` folders listed in `reports/README.md`.
- The runbook: `docs/RUNBOOK_backup_restore.md` (§0, §4, §4a, §4c, §4d's break glass).
- Memory notes added: *break-glass-pauses-argocd*, *background-agents-cost-tokens*, *issue-426-north-star-deferred*,
  *python-dev-stdin-file-vs-pipe*.

## State left behind

- **The lab:** 3.0.0 at `7ac6339f57`, offsite backup on to the PVC destination. The node disk was at 83% when last
  read during the session (not re-read for this log).
- **Open follow-ups:**
  - #532: recovery mode as its own workload, after 3.0.0;
  - #534: the `release-crc.sh` wait;
  - #535: cosign v3 in the install guide;
  - #410's PR B (#430) and #426 moved out of the epic.
- **Next:** Epic G (#387), beginning with G1 (#239).
