# Session change log — group-sync-dashboard, 2026-10-04 (afternoon)

This log continues `docs/session-changelogs/2026-10-04_epic-f-release.md`, from the moment its PR (#608) merged.

- **Times.** Times are git author times in America/Chicago. Merge instants and lab instants are UTC, as `gh` and the
  cluster printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the product change is described.** The `## Unreleased` section of `docs/CHANGELOG.md` (application 5.1.0,
  chart 0.70.2).

Outcome in one line: **the operator's two decisions (#592 yes, #593 "start tick with html") and the debt the epic's
seal check found (#607) shipped as application 5.1.0, deployed and checked on the lab. The Tech debt milestone is
closed at 0 open and 15 closed. 3 PRs merged, #609 to #611.**

| | Before | After |
|---|---|---|
| main | `4e5a708d` (#608), 5.0.0 / chart 0.70.1 | `f5f3abf4` (#611), 5.1.0 / chart 0.70.2 |
| deployed on the lab | 5.0.0 | 5.1.0 at `930796769f`, Synced and Healthy |
| "Tech debt" milestone | 1 open (#607) | closed: 0 open, 15 closed |
| #592, #593 | open for the operator | decided and closed |

---

## Part 1 — SPEC_F7 (10:00 → 10:27) — commits `e975580f`, `679bc5b5`, PR #609

- **The decisions:** the operator chose "yes" on #592, after the recommendation and their concern, "I dont wanna users
  to think that the data is not accurate". On #593 they chose "Start tick with html". Both are recorded on the issues.
- **The spec:** OB1-lite researched and wrote SPEC_F7. Its 40 blocks across 19 files applied to main with 0
  mismatches. The full hermetic suite gave 7623 passed, and the browser suite 694.
- **Retracted:** I had told the operator that all five reports' sha256 would change. OB1-lite measured three
  (compliance-snapshot, login-activity, groupsync-health). Groups and dormant-access change only at a moved edge.
- **Reviewed by Codex**, which confirmed C3 to C7 and found that `snapshot_at` is parsed on every read.
  - **Rejected: the cache.** "Parsed once" was the orchestrator's own brief, not the spec; a cache would grow the
    code for no change in result.
  - **Accepted: the failure modes,** stated in §3.1.

## Part 2 — the implementation (10:52 → 11:26) — commits `9407a204`, `82e71b03`, `2d35645b`, PR #610

- **Applied from the spec's 40 blocks.** Full suite 8317 passed; rendered RBAC rules unchanged (default 19, the lab's
  21, REMOVED 0); version check 5.0.0 → 5.1.0 accepted.
- **Found by OB2:** the snapshot copy was stamped before the writer's lock. A poll committed rows into a copy named
  earlier: measured, a row at `16:00:00Z` in a copy stamped `15:59:59.637Z`.
  - **Accepted.** The stamp is now taken under the lock. T592-3 uses an Event, not OB2's fixed sleep; it failed 3 of
    3 runs before and passed 5 of 5 after.
- **Found by Codex:** the window queries had no end bound for login events, which carry the audit log's clock, and
  compared microsecond times with whole-second cutoffs as text.
  - **Accepted:** `julianday` comparisons, bounds at the stamp, and dormancy at whole seconds. T592-4 failed with the
    lock fix alone and passes now.
- **Both fixes went into the spec first.** The oracle (clean main plus SPEC_F7, 51 blocks across 22 files) reproduces
  the branch with 0 differences.
- **Full suite:** 8319 passed, 27 skipped, 5 xfailed; CI green.
- **Held** until the operator finished an IPsec test on the CRC and said "It is free".

## Part 3 — Argo CD's Route-schema error, investigated (17:23 → 17:27 UTC)

- **Restarted.** Three Argo apps had read Unknown since 14:53:54Z. The controller was restarted at 17:23:59Z, and all
  10 apps were Synced and Healthy at 17:26:25Z.
- **The cause, measured** at the operator's request:
  - kube-apiserver started at 14:52:50Z;
  - Argo's schema was loaded and the error recorded at 14:53:54Z;
  - openshift-apiserver, which serves `route.openshift.io`, started at 14:53:55Z.
  Argo CD v3.4 rebuilds that schema only at startup or on a 24 h resync.
- **The upstream fix:** argoproj/argo-cd PR #28289 reloads the schema on an APIService event. It is present in v3.5.3
  and absent from v3.4.7, the lab's version. OpenShift GitOps 1.22.0 ships v3.5.3, and its InstallPlan waits for the
  operator's approval.

## Part 4 — 5.1.0 on the lab (17:28 → 18:06 UTC) — commit `ead195f8`, PR #611

- **Deployed:** #610 merged at 17:28:05Z. 5.1.0 was Synced and Healthy at 17:30:55Z, with the PVC UIDs unchanged.
- **SPEC_F7 §5 passed** (`reports/2026-10-04_snapshot-clock-592/`):
  - two runs per report, three minutes apart over one snapshot, gave one sha256 each, and the window "To" equals the
    stamp;
  - the `mock-trusted` diff across snapshots reads No change;
  - the form opens HTML-only at 1280 and 375 px.
- **Defects in the walk, found by its own runs:**
  - Run 1 reused the 1280 px page, so its PDF tick carried to 375 px.
  - Run 2 held one ticket past its 300 s lifetime.
  Both scripts were corrected, and the README says so.
- **Closed:** #592, #593 and #607, at `f5f3abf4`. The Tech debt milestone is closed.

---

## Numbers

| | |
|---|---|
| PRs merged | 3: #609, #610, #611 |
| Review passes | 3: Codex on the spec; OB2 and Codex on the implementation |
| Reviewer findings | 3: two accepted in full (OB2, Codex on #610), one in part (Codex on the spec: the cache rejected, the failure modes kept) |
| Full suite, final | 8319 passed, 27 skipped, 5 xfailed on `2d35645b` |
| Longest single loss | the lab check's two false starts, run 1 from 17:31 and run 2 ending 17:44:59 (log stamps). Written down so it does not recur: a walk gets a fresh session per viewport and a fresh ticket per phase |

## State left behind

- **The lab:** 5.1.0, chart 0.70.2, Argo CD Synced and Healthy.
- **Open for the operator:** approving the GitOps 1.22.0 InstallPlan, which removes the Route-schema race.
- **Held:** #598. **Parked:** #600, Epic P (#388). Everything else open is a new feature, which the operator ruled out
  for now.
