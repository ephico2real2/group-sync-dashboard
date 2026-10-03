# The Epic G release (application 4.0.0, chart 0.66.4) on the CRC lab

Deployed and walked 2026-10-03, 18:16 to 18:32 UTC, on CRC (OpenShift 4.22.7), after the release PR #564 merged as
`15613ccb95`, by `scripts/run.sh`. `walk.log` is the record, and the walk exited 0.

**The published release.**
- `Release Charts`, `publish`, `ci` and `mock-openshift` all succeeded on the merge.
- The GitHub release `group-sync-dashboard-0.66.4` targets `15613ccb95`.
- On quay, `4.0.0`, `0.66.4` and `latest` resolve to one digest per image, labelled version `4.0.0` and revision
  `15613ccb95`:
  - `group-sync-dashboard`: `sha256:ca7555fc59e74a7361d116f8a88d011ca4bee48a657ef69d26fd9a12c80721a0`
  - `group-sync-dashboard-report`: `sha256:0940b84b5d4ed2c685f630a71d201536591a6923852d1f26da2ffc919a0c763e`

**The deploy.**
- `release-crc.sh --argocd main --values environments/crc.yaml` timed out after 900 s on "status is for the previous
  spec", #534's wait defect, measured once more.
- The walk then read the lab directly: the Application is Synced and Healthy on `15613ccb95`, the operation
  Succeeded with `retryCount` absent, and the pod reports 4.0.0.

| Check | Result |
|---|---|
| Workloads | `group-sync-dashboard` 1/1 on `:4.0.0`; `group-sync-dashboard-recovery` 0/0 on `:4.0.0` (#532); `group-sync-dashboard-report` 1/1 on `:4.0.0` |
| Health | `/healthz` 200; `/readyz` 200 with 6 clusters; `gsd_build_info{branch="main",commit="15613ccb95",version="4.0.0"}` |
| Schema | `PRAGMA user_version` 20, and the image's `_MIGRATIONS` 20 |
| G1 (#239) | `developer` (the self tier) on `/api/housekeeping/copies`: "For cluster administrators only. Deleting reports and database copies is reserved to cluster administrators." |
| G2 (#255) and G3 (#503) | as `dana.lee`: `total` 9, `excluded_platform` 24, `platform_users_unmatched` `{}`, `acknowledged` 2, sources `["group-sync-operator-helm"]` |
| G4 (#420) | the ClusterRole has 0 Lease rules; the Role `group-sync-dashboard-leases` has `get`/`create`/`update` on Leases; the elector's Lease, held by the new pod, renewed at 18:31:45Z (`leaseTransitions` 15) |
| #542 | `features.housekeeping: true` |
| PVC UIDs | Unchanged: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6` |

Each feature's full walk is in its own folder: `2026-10-02_gui-cleanup-542/`, `2026-10-03_recovery-workload-532/`,
`2026-10-03_platform-users-255/`, `2026-10-03_acknowledged-grants-503/`, `2026-10-03_leases-role-420-step1/` and
`2026-10-03_leases-role-420-step2/`. G1 is tests and docs only, proved by CI.
