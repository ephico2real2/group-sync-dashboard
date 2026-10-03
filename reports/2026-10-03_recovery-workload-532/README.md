# Recovery mode as its own workload on the CRC lab — the SPEC_E11 §5 walk (#532)

Two runs on CRC (OpenShift 4.22.7, Kubernetes v1.35.6), 2026-10-03, both by `scripts/run.sh`.

- **Run 1:** chart 0.65.0, after PR #551 merged as `1c9c929dea`. Its log is `walk-run1.log`. It found the scheduler
  wait that PR #552 fixed.
- **Run 2:** chart 0.65.1, after PR #552 merged as `ddeda85d78`. Its log is `walk.log`, and the controller's log
  across §4d is `argo-controller-4d.log`. It is the walk of record: exit 0.
- **The application** was 3.1.0 in both runs.
- **The lab.** The lab's Argo CD Application (`openshift-gitops/group-sync-dashboard`) has `prune` and `selfHeal` on,
  and retry `{limit:3, 30s×2, max 5m}`.
- **What changed on the cluster.** The walk changed only what §5 names:
  - the Application's revision, set by `release-crc.sh --argocd`;
  - two walk commits on `lab/e11-recovery-walk`, which was never merged and was deleted at the end;
  - §4d's own pause, scale and give-back.

## Run 2 (chart 0.65.1): the walk of record

| Step | SPEC_E11 §5 | Result |
|---|---|---|
| 1 | Before | The Application is on `main` at `ddeda85d`, Synced and Healthy. `group-sync-dashboard` 1/1, `group-sync-dashboard-recovery` 0/0. PVCs: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`. |
| 2 | Recovery on, through the values file | `recovery.enabled: true` in `environments/crc.yaml` on the walk branch, pushed at 04:45:35Z. One operation, 04:45:39Z → 04:46:00Z, `retryCount` absent. The recovery pod was refused at 04:45:55Z ("didn't match pod anti-affinity rules": the app pod still existed) and scheduled at 04:45:56Z. The result: app 0/0, recovery 1/1, the Application Synced and Healthy. |
| 3 | `restore-db.sh --list` | It names `group-sync-dashboard-recovery-55bfd86bdc-x8ghp` ("recovery mode, at least 1h59m45s of its TTL left") and lists 7 copies at schema 20, backup and offsite sources, all restorable by this image. |
| 4 | Recovery off, through the values file | Pushed at 04:46:15Z. Argo CD's operation ran 04:48:45Z → 04:49:34Z, `retryCount` absent; the 150 s before it is Argo CD's poll. The recovery pod was killed at 04:49:01Z, and the app pod was refused and then scheduled in the same second, 04:49:01Z, on its own mirror term. The app was Ready at 04:49:36Z: **202 s from the push, 150 of them polling**. |
| 5 | Runbook §4d once | The pause read `false Succeeded`. The two `oc scale` commands gave recovery 1/1 and the app 0 within 6 s, and `restore-db.sh --list` named the recovery pod. The controller log, 04:49:37Z → 04:49:46Z: OutOfSync detected, no sync started. At 04:49:46Z it logged "Enabled automated sync", which is the give-back. The give-back's own sync restored the two `replicas` from Git. The app pod was scheduled at 04:49:47Z, and `oc rollout status` reported "successfully rolled out". Nothing was left to remove. |
| 6 | After | The Application is back on `main`, Synced and Healthy at `ddeda85d`, and the walk branch is deleted. The same three PVC UIDs. |

Every Argo CD operation in the run recorded `retryCount` absent (5 of 5).

## Run 1 (chart 0.65.0): what it found

- **Recovery on and off both worked as one operation without retries.** That is #532's fix.
- **The app pod then waited 303 s.** The recovery pod was killed at 01:52:04Z, the app pod was refused at
  01:52:04Z, and it was scheduled at 01:57:07Z.
- **The cause, in kube-scheduler v1.35.0.** On a delete, `interpodaffinity/plugin.go` L223–231 re-queues a waiting
  pod only when the deleted pod matches the waiting pod's own anti-affinity. Here it fell back to the 5-minute
  unschedulable flush (`scheduling_queue.go` L66).
- **The fix.** PR #552 gave the app pod the mirror term (SPEC_E11 note 8). Run 2 measures it: same second.
- **The rest of run 1 is not evidence about the product.** §4d's give-back, and everything after it, ran while the
  CRC node was rebooting for an unrelated experiment the operator ran in another window. A MachineConfig was applied
  at 01:59:17Z, and the node rebooted at 01:59:30Z, 02:33:43Z and 02:55:30Z. That is why `walk-run1.log` shows the
  rollout timing out, then `oc` losing its configuration, then step 6 not met.
- **A correction.** While diagnosing run 1, I read the sync at 01:57:37Z as Argo CD reverting the hand edit during
  the pause. That reading is wrong and is retracted. Run 2's controller log shows the pause holds, and that the sync
  right after it is the walk's own give-back, which comes 9 s later because the walk runs §4d with no restore in
  between.

A second attempt at run 2, at 04:44Z, stopped at step 2 before changing anything: run 1's local walk branch still
existed. Its log was overwritten by the run of record. `scripts/run.sh`'s exit trap now deletes the local branch.

## Before and after #532

| Recovery off, from the values file to the app Ready | Measured |
|---|---|
| 3.0.0, recovery as a failing readiness on the app's own Deployment | 12 min 49 s, waiting on Argo CD's retries (`reports/2026-10-02_runbook-schema-line-300/`) |
| chart 0.65.0, its own workload | 507 s: one operation, no retries, then 303 s of scheduler wait |
| chart 0.65.1, the mirror term | 202 s: one operation, no retries; 150 s of it is Argo CD's poll, and the app pod was scheduled in the same second as the recovery pod's delete |

## Logs

`walk.log`, `walk-run1.log` and `argo-controller-4d.log` hold no `sha256~` value and no `password` match.
