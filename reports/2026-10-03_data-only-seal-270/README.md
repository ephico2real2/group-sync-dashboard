# #270 on the lab: two runs over one snapshot carry one sha256, 2026-10-03

**Outcome.** The lab served application 4.1.0 (`quay.io/ephico2real/group-sync-dashboard:4.1.0` and
`-report:4.1.0`), deployed by Argo CD from main at `a38c3b0c` (PR #571, SPEC_F1). Two viewer runs of `groups` on the
cluster `dashboard`, requested 11 s apart by `dana.lee`, gave one sha256 (`evidence/compare.txt`):
- **The seal:** `9b7b51a69224389edb9c4fd94b910cdaf97a11f7f8d4ac74ba26562efc464b85` for both runs. The run record,
  the `.json`'s own field and the walk's `recompute()` (`local-development/e2e-walk/integrity_check.py`) all match.
- **One snapshot:** the stamp `2026-10-03T22:02:49.597664Z` was the service's copy before the first run, after the
  second, and in both runs' `sealed_provenance`.
- **What differed:**
  - the run ids, `20261003T220454.016505Z-0d31` and `20261003T220505.410627Z-a7d4`;
  - the generation instants, 22:04:54Z and 22:05:05Z;
  - page one as a whole.
- **What was equal:** every sealed section.
- **Sealed flags:** `[False, True, True, True, True]` in both runs (page one unsealed).
- **PVC UIDs** were unchanged before and after (`evidence/run.log`): data `f065b7a4-…`, report-artifacts
  `08c7d45c-…`, offsite `7f505595-…`.

## How it ran

- **The user.** `dana.lee`, a cluster-reader and so on the wide tier, which mints report tickets.
- **The ticket.** It was minted on the dashboard pod's loopback with `X-Forwarded-User`. It went to the report pod
  on stdin only; it is not in any file here.
- **Why viewer runs.** Service-token runs are confined to the lab's night window (`environments/crc.yaml`); a
  viewer's run is not.
- **The script.** `scripts/run.sh` drives `scripts/in_pod.py` inside the report pod. That script queues the two runs
  on `https://127.0.0.1:8443`, with certificate checks off because the call is loopback only. It then waits for
  both runs and downloads each `.json`.

## What this does not show

- **Different viewers.** Both runs were by one viewer. T270-1 (`local-development/tests/test_report_seal.py`)
  covers different viewers over every report.
- **Clock-anchored reports.** `groups` counts membership changes in a window ending at the generation instant
  (SPEC_F1, the review's note). The two runs agreed because that 30-day window holds the same changes 11 s
  apart, not because the clock is out of the hash.

## Before the check: the #410 race, seen again

Argo CD synced the merge before `publish.yml` had pushed `:4.1.0`. The new dashboard, report and off-site bind
hook pods were read in `ErrImagePull`. They started on their own once the image existed, with no action taken:
- the dashboard container at 21:56:40Z, 45 s after its oauth-proxy sidecar started (21:55:55Z);
- the report container at 21:57:31Z.

Argo CD then read Synced, Healthy and Succeeded at `a38c3b0c`.

| Path | Contents |
|---|---|
| `evidence/runs.json` | the snapshot before and after, both run records and both `.json` documents |
| `evidence/compare.txt` | the comparison printed by the check |
| `evidence/run.log` | the images, the replicas and the PVC UIDs before and after |
| `scripts/` | `run.sh`, `in_pod.py` |
