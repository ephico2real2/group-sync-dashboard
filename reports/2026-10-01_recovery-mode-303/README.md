# Recovery mode on the CRC lab — the SPEC_E2 §5 walk (#303)

Walked 2026-10-02 00:01–00:23 UTC on CRC (OpenShift 4.22.7), PR #518 at `98d20df0` (the spec's blocks, the review
fixes `258a4c68`, and these values files). Every rollout went through the lab's pipeline:
`local-development/release-crc.sh --argocd feat/303-recovery-mode --values reports/2026-10-01_recovery-mode-303/<file>`,
which points the Argo CD Application at the branch with that file as its only values file. Each file is
`environments/crc.yaml` plus the lines at its end. The full record, command by command, is `walk.log`.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | Before: PVC UIDs, row counts | `f065b7a4-…` / `08c7d45c-…`; membership 1843, sync 2728, binding 4328; `user_version` 20; app 2.0.0, leader |
| 2 | On under image 2.0.0 (T303-13) | the banner lines, no `ModuleNotFoundError`; pod `1/2 Running`; no ready endpoint; Deployment Progressing, then `ProgressDeadlineExceeded` (the pipeline's wait reported it failed, as the spec says) |
| 3 | Holds past 11 minutes (T303-17) | at 15 min `restartCount` 0; no descriptor on `/data/gsd.db`, `-wal` or `-shm`; self-heal kept the values file; frozen counts equal step 1's |
| 4 | A restart keeps the TTL | after `kill -TERM 1`: `kept from this pod's first start at 00:01:36Z`, same end `02:01:36Z`; the old container exited 0 |
| 5 | The TTL ends visibly (`values-ttl3m.yaml`) | at 3 min the summary line names the values file and no command; `CrashLoopBackOff`, restarts 2, a back-off event |
| 6 | SIGTERM as PID 1 (T303-11) | `oc delete pod --wait` took 0.74 s (grace period 30 s) |
| 7 | Off (T303-18) | Synced/Healthy 48 s after the rollout began (operation phase Succeeded at the start); the app leads on the same file, counts identical to step 1, endpoint ready, PVC UIDs unchanged |
| 8 | RBAC | `rbac_rules.py`, main vs the branch: recovery off 65/65 and on 65/65, REMOVED 0, ADDED 0 |

The offsite mount was not walked: the lab has no offsite CronJob (#304's walk turns it on).

After this walk the lab's Application still tracks `feat/303-recovery-mode` with `values-off.yaml`; once PR #518
merges it is pointed back at `main` (`release-crc.sh --argocd main`).
