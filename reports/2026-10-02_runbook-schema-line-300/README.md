# The backup and restore runbook on the CRC lab: the SPEC_E7 §5 walk (#300)

Walked 2026-10-02 05:32–06:20 UTC on CRC (OpenShift 4.22.7). The commands came from `charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md`
§0 and §4 as merged on main (PR #528, `2e7d33be`). The lab runs application 2.3.0 (`c57f292707`) and chart 0.61.1,
with the offsite backup on its `pvc` destination. On this lab `NS=group-sync-dashboard` and `REL=group-sync-dashboard`.
The runbook's example line sets `NS=group-sync`.

Every rollout went through the lab's pipeline:
`local-development/release-crc.sh --argocd reports/300-runbook-walk --values reports/2026-10-02_runbook-schema-line-300/<file>`.
That command points the Argo CD Application at this branch, with the file as its only values file, and the chart's
default image: the published `quay.io/ephico2real/group-sync-dashboard:2.3.0`, which the script read back as
application 2.3.0. Each values file is `environments/crc.yaml` plus the lines at its end.

`walk.log` records every command with its output and exit code. In it, `<worktree>`, `<scratch>` and `<checkout>`
stand for local paths. `restore-terminal.png` is the restore's terminal output (step 5d), rendered from the text the
command printed.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | Before | PVC UIDs: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`. Application on `main` at `2e7d33be`, Synced/Healthy |
| 2 | §0 step 1 | No `**Schema N → M.**` line in `docs/CHANGELOG.md` yet. `KNOWN_SCHEMA_VERSION` is `20`. `gsd_build_info{…,version="2.3.0"}` |
| 3 | §0 step 2, the Job branch | The CronJob exists. Job `manual-1790919163` reached `condition met` (Complete), then logged `copied /data/backup/gsd-20261002T042438.581853Z.db -> /offsite/… (14295040 bytes, …)` and `integrity_check ok; user_version 20` |
| 4 | §0 step 3 | `free 26973138944` and `databases 19084832`, so `free` is above `databases`. The gauges read total `1.60456224768e+11` and used `1.33483065344e+11`. Their difference, 26973159424, was read a moment later than `free` |
| 5a | §4 steps 1–2, recovery on (`values-recovery.yaml`) | Pod `1/2 Running`. The log begins `RECOVERY MODE`, `the app is NOT running and no data is collected`, `TTL 2h: ends 2026-10-02T07:34:05Z`. Image `…:2.3.0`. `/offsite` is mounted read-only. The pipeline's wait failed as §4 step 2 says (`Progressing`; the walk shortened it with `ARGOCD_WAIT_TIMEOUT=240`) |
| 5b | `restore-db.sh --list` | 4 candidates. The newest is `20-20261002T042438.581853Z`: `backup+offsite`, sidecar `ok`, `yes` |
| 5c | §1 on that copy | `integrity_check: ok`, `user_version: 20`, membership 1843, sync 2770, login 7968 |
| 5d | `--from-version 20-20261002T042438.581853Z` (`--yes`: the walk shell has no terminal) | Loss window `04:24:38Z -> 05:38:20Z (1h13m42s)`: 12 `sync_event` and 24 `login_event` rows discarded, 0 in the other tables. The live set was kept under `/data/pre-restore/20261002T053826.893557Z/`. `user_version 20 -> 20`. `gsd.db` has group `root` |
| 5e | Recovery off (`values-off.yaml`) | Synced/Healthy at 05:52:11Z. The rollout was applied at 05:38:43Z, but Argo did not start the sync until 05:51:32Z (finding F1) |
| 5f | §4c | `rollout status` reported `successfully rolled out`. `/api/version` answered `{"leader":true,"version":"2.3.0",…}`, the shape §4c shows. Counts: membership 1843 equals the copy; sync 2776 does not equal the copy's 2770 (finding F3). Bounded by the copy's highest id, all four tables equal the copy (5g) |
| 6a–b | Fallback: `replicaCount: 0` (`values-replicas0.yaml`), `oc wait --for=delete` | Synced/Healthy in 30 s. `oc wait` exited 0, with `replicas=0` and no pod. The render differs from `crc.yaml` only in `replicas`, the configuration's `replicaCount` and `checksum/config` |
| 6c | §4a's `oc debug` body as printed, `gsd-….db` set to the copy from step 5 | Every line of the body ran: `ok`, `kept /data/gsd.db under /data/pre-restore/20261002T055647Z`, `gsd.db` 14295040 bytes with group `root`. **`oc debug` did not return** (finding F2). The walker interrupted it: `Removing debug pod ...`, exit 1, no pod left |
| 6d–e | `replicaCount: 1` (`values-replicas1.yaml`), §4c | Synced/Healthy at 06:03:36Z. `/api/version` is `2.3.0`, leader. Bounded by id, all four tables equal the copy. This restore threw away what the app had written since 5f (finding F4) |
| 7a | After | PVC UIDs are the three of step 1, unchanged, at 06:04:33Z and again after the hand-back |
| 7b | `prepare-release.py --app 2.4.0 "walk" --no-commit` on scratch clones of `2e7d33be` | With a no-op migration 21: `schema  : 20 at c57f292707 (application 2.3.0), 21 at HEAD; the changelog entry says so`, and the entry carries `- **Schema 20 → 21.** …` under `- **walk.**`. Without it: `schema  : 20 at c57f292707 (application 2.3.0), 20 at HEAD; no schema line`, and no line in the entry |
| 7c | Hand-back: `release-crc.sh --argocd main` | The Application is on `main` `ffe9de32` (PR #529 merged during the walk; no chart change), Synced/Healthy, app 2.3.0, leader, PVC UIDs unchanged. **The script exited 1 after 900 s** (finding F5) |

## Findings

- **F1. Under Argo CD, turning recovery mode off waits for the "on" sync to give up.** The lab's Application has
  `automated` sync and `retry: {limit: 3, backoff: {duration: 30s, factor: 2, maxDuration: 5m}}`. The sync for
  recovery on started at 05:33:46Z. It waits for the Deployment to become healthy, which recovery mode never does. It
  failed when the Deployment went `Degraded`, then retried 3 times. The values change for recovery off was applied at
  05:38:43Z, but Argo did not start its sync until 05:51:32Z, 12m49s later. Until then the recovery pod kept running.
  §4 step 5 says "When the change is applied the recovery pod stops at once". §4 step 2 says only that the pipeline's
  wait reports a failure. Neither says that a GitOps controller's retrying operation holds the next change back. This
  walk measured the delay and did not test any way around it.
- **F2. §4a's `oc debug -n $NS deploy/$REL -c dashboard -- sh -c '…'` does not return on this release.** The debug
  pod copies the Deployment's oauth-proxy sidecar as well as the dashboard container (the events show both started).
  When the body ended, the pod stood at `1/2 NotReady`, and `oc debug` was still waiting after 5m13s. The walker sent
  SIGINT, as Ctrl-C would, and `oc debug` removed its pod. The restore itself had completed. The flag
  `oc debug --one-container` ("run only the selected container, remove all others", from `oc debug --help`, client
  4.22.13) is the likely fix. **Not walked.**
- **F3. §4c's "The numbers must equal the copy's (§1)" does not hold once the app runs.** The leader polls before
  the count runs, so `sync_event` read 2776 against the copy's 2770 (step 5f) and 2779 against it (step 6e). Counted at
  or below the copy's highest id, every table is equal. That is the comparison the #302 walk used.
- **F4. Spec §5 step 6, "the database is unchanged by it", did not hold.** Between 5f and 6c the app led from 05:51:58Z until the replicaCount-0 rollout at 05:55:59Z, about
  4 minutes, and wrote rows: live `sync_event` 2776 and `login_event` 7992 (step 6a). §4a's restore of the same copy
  set them back to the copy's 2770 and 7968. The content returned to the copy; it was not unchanged.
- **F5. The hand-back's wait cannot finish when nothing needs syncing.** `release-crc.sh --argocd main` applied
  `spec.source.helm.parameters: []`. Argo's `status.sync.comparedTo.source` leaves that key out, so
  `argocd-wait.sh`'s equality test stayed false: "equal, as the waiter tests it: False" and "equal without the empty
  parameters: True" (step 7d). Meanwhile the Application was Synced/Healthy on `ffe9de32`. The waiter printed
  "status is for the previous spec" for 900 s and exited 1. The chart had not changed, and the previous values file
  renders the same as `crc.yaml`, so no sync operation ran. In the earlier branch runs a sync operation did run, and
  the same empty `parameters` passed the waiter. Why the operation makes the difference was not measured.
- **F6 (minor).** §0 steps 1 and 3 name `gsd_build_info` and the two `gsd_volume_disk_*` gauges, but print no
  command to read them. The walk read `/metrics` through the pod's loopback (`oc exec … curl -s http://127.0.0.1:8080/metrics`).

## Deviations

- `ARGOCD_WAIT_TIMEOUT=240` on the recovery-on rollout only. §4 step 2 expects that wait to fail, so this only
  shortened it.
- `restore-db.sh --from-version … --yes`: the walk shell has no terminal to answer `y` in.
- §1's snippet was run on the chosen copy before the restore (5c), so that "the copy's" counts were recorded.
- Steps 5g and 6e add a count bounded by the copy's highest id (F3).
- In the §4a body, `gsd-….db` became `/data/backup/gsd-20261002T042438.581853Z.db`. Nothing else changed.
- `oc debug` was interrupted with SIGINT (F2).
- 7b: the second scratch clone is a local clone of the first, both at `2e7d33be`, because a second network clone
  stalled. The migration-21 commit exists only in the first clone and was never pushed.

## Lab writes

The writes were the Application's spec, changed by `release-crc.sh` five times (four values files, then `main`),
and Job `manual-1790919163`, created from the CronJob. Each restore also wrote under `/data`: `gsd.db` and the kept
sets `/data/pre-restore/20261002T053826.893557Z/` and `/data/pre-restore/20261002T055647Z/`. The kept sets were left
in place as the way back. The debug pod, removed by `oc debug` itself, was the only other write. The walk never
touched a PVC, `gsd-cluster-shared-qa` or the fleet account.
