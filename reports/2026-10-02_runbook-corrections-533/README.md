# The corrected backup runbook on the CRC lab: the SPEC_E10 §5 walk (#533)

Walked 2026-10-02 14:49–15:18 UTC on CRC (OpenShift 4.22.7, OpenShift GitOps with Argo CD v3.4.7). The commands are
those of `charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md` as PR #537 changes it (`origin/feat/533-runbook-break-glass`, `961c1a42`):
§0, §1, §4 (the Risks box, steps 1–5, §4a, §4c) and §4d. The §4d lines were cut from that file and run byte for
byte, with only their placeholders filled. The lab runs application 2.4.0 (`521c2bb0b4`) and chart 0.61.2, with
the offsite backup on its `pvc` destination. On this lab `NS=group-sync-dashboard` and `REL=group-sync-dashboard`.
The runbook's example line sets `NS=group-sync`.

The values-file rollouts went through the lab's pipeline:
`local-development/release-crc.sh --argocd reports/533-runbook-walk --values reports/2026-10-02_runbook-corrections-533/<file>`
(branch head `d009ade8`). The image was the chart's default, the published
`quay.io/ephico2real/group-sync-dashboard:2.4.0`, which the script read back as application 2.4.0. Each values
file is `environments/crc.yaml` with a few lines added at the end. `helm template` against `crc.yaml` shows the
differences. `values-recovery.yaml` adds the recovery ConfigMap and the recovery render. `values-off.yaml` and
`values-replicas1.yaml` render identically to `crc.yaml`. `values-replicas0.yaml` differs only in `replicas`, the
configuration's `replicaCount` and `checksum/config`.

`walk.log` records every command with its output and exit code. In it, `<worktree>` is this walk's worktree and
`<scratch>` its scratch directory. Each wait has a bound, and each timestamp is the clock's reading at that moment.

| Step | SPEC_E10 §5 | Result |
|---|---|---|
| 1 | Before | PVC UIDs: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`. Application on `main` `566d042d`, Synced/Healthy. `spec.syncPolicy` saved: `{"automated":{"prune":true,"selfHeal":true},"retry":{…"limit":3},"syncOptions":[…"ServerSideApply=true"]}`. Pod template saved: 163 leaf fields, ReplicaSet `8596b4fb4b` |
| 2 | §0 step 1, the `/metrics` read | Three lines: `gsd_build_info{branch="main",commit="521c2bb0b4",version="2.4.0"} 1.0`, used `1.30869440512e+11`, total `1.60456224768e+11`; exit 0 |
| 3a | §4 steps 1–2, recovery on (`values-recovery.yaml`) | Operation started 14:49:43Z. Pod `1/2 Running`. Log `RECOVERY MODE`, `the app is NOT running and no data is collected`, `TTL 2h: ends 2026-10-02T16:50:02Z`. The pipeline's wait failed, as §4 step 2 says it does |
| 3b | `restore-db.sh --list` | `recovery mode, at least 1h56m6s of its TTL left`, 9 candidates; the newest is `20-20261002T140946.188889Z` (`backup`, sidecar `none`) |
| 3c | §1 on the newest copy | `integrity_check: ok`, `user_version: 20`, `membership_event 1843 rows, highest id 1843`, `sync_event 2863 rows, highest id 186168`, `login_event 7992 rows, highest id 8040` |
| 3d | `--from-version 20-20261002T140946.188889Z --yes` (no terminal) | Loss window `14:09:46Z -> 14:54:11Z (44m24s)`: 3 `sync_event` rows discarded, 0 in the other tables. The live set was kept under `/data/pre-restore/20261002T145415.792307Z/`. `user_version 20 -> 20`; exit 0 |
| 3e | §4 step 5, recovery off (`values-off.yaml`), and the Risks box | The off values reached the Application at 14:54:33Z. From 14:54:48Z it read OutOfSync while the recovery-on operation stayed Running. It went `Degraded` at 15:00:06Z, then `Retrying attempt #1 at 3:00PM`, `#2 at 3:02PM`, and `#3 at 3:05PM` (from 15:03:25.9Z). The recovery pod kept running all that time. The waiter, bounded to 480 s, exited 1 with `exceeded its progress deadline` |
| 3e′ | **§4d step 7, the terminate (the operator approved it)** | The step 2 pause at 15:03:12.55Z read `false Running`. Retry #2's hooks were running at 15:03:13.3Z, 0.7 s after the pause. The retry then failed while paused, and at 15:03:25.9Z the operation scheduled #3 (`retryCount` 3) and stayed Running. `argocd app terminate-op group-sync-dashboard` was issued at 15:06:30.720Z. It returned `operation terminating`, the phase read `Terminating` at 15:06:31.653Z, then `Failed` (`Operation terminated (retried 3 times).`) at 15:06:32.802Z. The step 2 check a minute later read `false Failed`, with the pod still in recovery. Step 5 ended the pause at 15:07:52.508Z: a new operation started 15:07:52Z, the command was uvicorn again at 15:08:13.5Z, and Synced/Healthy/Succeeded with one ready replica came at 15:08:33.030Z |
| 3f | §4c with step 3c's ids | `rollout status` reported `successfully rolled out`. `/api/version` returned `{"leader":true,"version":"2.4.0",…}`. Up to the ids: `membership_event 1843`, `sync_event 2863`, `login_event 7992`, each equal to 3c. The whole `sync_event` table held 2869 rows |
| 4a–b | Fallback: `replicaCount: 0` (`values-replicas0.yaml`), `oc wait --for=delete` | Synced/Healthy at 15:09:36Z. `oc wait` exited 0, with `replicas=0` and no pod |
| 4c | §4a's `oc debug --one-container` body, `gsd-….db` set to 3d's copy | `Starting pod/group-sync-dashboard-debug-76k74`, then `ok` and `kept /data/gsd.db under /data/pre-restore/20261002T150951Z`. `gsd.db` was 14340096 bytes, group `root`. `Removing debug pod ...`. **It returned in 6.0 s with exit 0** (15:09:47.831Z–15:09:53.864Z), and 0 debug pods were left |
| 4d–e | `replicaCount: 1` (`values-replicas1.yaml`), §4c with 3c's ids | Synced/Healthy at 15:10:48Z. `leader:true`, 2.4.0. Counts `1843`, `2863`, `7992`, each equal to 3c |
| 5 | Back on `main` before §4d (`release-crc.sh --argocd main`) | The Application is on `main` `566d042d`, Synced/Healthy. Its last operation finished at 15:10:38Z, and none ran for the hand-back. The waiter, bounded to 180 s, timed out on the empty `parameters`, the #300 walk's F5 seen again. The pod template is 0 of 163 fields from step 1's |
| 6.1 | §4d step 1 | The tracking-id is `group-sync-dashboard:apps/Deployment:group-sync-dashboard/group-sync-dashboard`. `ownerReferences` is empty: no ApplicationSet |
| 6.2 | §4d step 2 | The pause at 15:14:39.846Z read `false Succeeded`, and the check a minute later read `false Succeeded` too |
| 6.3 | §4d step 3 | The chart label read `group-sync-dashboard-0.61.2`. `helm pull … --version 0.61.2` exited 0, and the ConfigMap was `created`. `TTL=2h`. The patch at 15:15:41.448Z printed `patched`. One pod read `1/2 Running` 7 s later, its log `RECOVERY MODE … TTL 2h: ends 2026-10-02T17:15:44Z`. The Application read `false OutOfSync Progressing` with no new operation: the pause held |
| 6.4 | §4d step 4, with a restore | `--list` printed `recovery mode, at least 1h59m44s of its TTL left` and 4 candidates. §1 on the newest, `20-20261002T151031.581299Z`, gave `1843 rows, highest id 1843`, `2869 rows, highest id 186228`, `7992 rows, highest id 8040`. `--from-version … --yes` printed a loss window of `15:10:31Z -> 15:16:16Z (5m44s)` with 0 rows discarded in every table, and the live set was kept under `/data/pre-restore/20261002T151622.016368Z/`; exit 0 |
| 6.5 | §4d step 5 | Unpaused at 15:16:36.013Z. `oc wait … Synced` met at 15:16:52.095Z (+16.1 s), and `oc rollout status` succeeded at 15:17:10.651Z (+34.6 s). The command was uvicorn again, and `spec.syncPolicy` matched step 1's. 10 of 173 template fields still differed: the two variables, the `/scripts` mount and the `recovery-script` volume. Managers: `argocd-controller`, `kubectl-patch`, `kube-controller-manager` |
| 6.6 | §4d step 6, then §4c | The removal patch at 15:17:21.815Z was rolled out at 15:17:40.341Z (18.5 s), and the ConfigMap was `deleted`. **The pod template differs from step 1's in 0 of 163 fields, and its sorted JSON is byte-equal.** ReplicaSet `8596b4fb4b`, the pre-walk one. Managers: `argocd-controller` and `kube-controller-manager`. §4c read `1843`, `2869`, `7992` up to 6.4's ids, each equal to §1's. `/api/version` read `"leader":false` at 15:17:40Z, then `true` at 15:18:16Z. The new pod took the lease at 15:17:50.4Z (W3) |
| 7 | After | PVC UIDs are the three of step 1, unchanged. The Application is on `main` `566d042d`, Synced/Healthy. `spec.syncPolicy` is byte-equal to step 1's (`cmp`). One pod is `2/2`, with no debug pod and no recovery ConfigMap. `/metrics` reads `version="2.4.0"` |

## What the walk confirms in the corrected runbook

- §0's `/metrics` command prints the three series it names (step 2).
- §1 prints each table's highest id. §4c's count up to those ids equalled §1's rows all three times (3f, 4e, 6.6),
  even while the whole `sync_event` table had grown (2869 against 2863 in 3f).
- §4a's `oc debug --one-container` returns on its own, with exit 0, and leaves no pod (4c). The #300 walk's
  F2 is closed.
- The Risks box: the off change waits behind the retrying recovery-on operation (3e). A pause does not stop that
  operation: after the pause, retry #2 failed and the operation scheduled retry #3 and stayed Running (3e′), which
  bears out step 2's "a sync already running is not stopped by the pause".
- §4d steps 1–6 with a real restore. The hand edit gave a recovery pod that `restore-db.sh` accepted. After the
  give-back, Argo CD left the 10 added fields in place. Step 6 put the template back to step 1's exactly.
- §4d step 7 (3e′). `terminate-op` ended the retrying operation in at most 2.08 s from the command (issue to
  `Failed`). With no operation running, ending the pause let automated sync take the waiting recovery-off revision
  at once: the operation started in the same second, and the app was Synced/Healthy 40.5 s later.

## Findings

- **W1. §4d's text still says step 7 and the restore were not walked.** The §4d introduction reads "Every step was
  walked on the CRC lab … except the restore itself, the ApplicationSet case and step 7". Step 7 ends with "Not
  measured on the lab." Both have now been walked: the restore in 6.4, and step 7 in 3e′, with the numbers above.
  The instructions themselves worked as printed. Only the statements about what was measured are out of date.
- **W2. Step 7's command assumes an Argo CD CLI that is installed and logged in.** This workstation had no
  `argocd`. The walk downloaded the v3.4.7 CLI, the lab's server version, from the GitHub release (its sha256
  checked against `cli_checksums.txt`) and ran the printed command in `--core` mode. In that mode the CLI talks to
  the Kubernetes API with the kubeconfig and needs no Argo CD login. It also takes Argo CD's namespace from the
  kube context. The first run, with the default context (namespace `default`), failed with
  `configmap "argocd-cm" not found` (logged). The second run used a kubeconfig overlay naming a context with
  namespace `openshift-gitops`, and it worked. The run also passed the OpenShift GitOps component names
  (`--redis-name openshift-gitops-redis` and the like). Whether `terminate-op` needs them was not measured. A
  read-only `app get` worked without them. The UI path the runbook offers was not walked.
- **W3 (minor; OB2 remarked on it in SPEC_E10's notes, and it is now measured).** §4c's expected
  `{"leader":true,…}` read `"leader":false` straight after §4d step 6's `oc rollout status`. The replaced pod still
  held the 30 s lease: the log says `renewed 20s of 30s ago — standing by`, and the new pod took the lease at
  15:17:50.4Z, about 10 s later. In 3f and 4e the read was `true` at once.
- **O1 (restore-db.sh's wording under §4d, not the runbook).** Under the hand edit, `--list` printed
  `offsite: /offsite is not mounted (recovery mode mounts the offsite claim only when backup.offsite uses its pvc
  destination)`, yet the lab does use the `pvc` destination. The runbook's step 3 gives the right reason ("The
  offsite claim is not mounted by this edit"). After the restore, the script's closing line,
  `restored. Set recovery.enabled: false in this release's values file …`, names the values-file path. Under §4d
  the next step is step 5. These messages are outside SPEC_E10's scope and are recorded here only.

## Deviations

- `ARGOCD_WAIT_TIMEOUT` bounded every pipeline wait, because the walk shell cannot hold a 900 s command: 240 s for
  recovery on (§4 step 2 expects that wait to fail), 480 s for recovery off (so the walk could act on the retrying
  operation), 480 s for each `replicaCount` change, and 180 s for the hand-back to `main` (F5).
- `restore-db.sh --from-version … --yes`: the walk shell has no terminal to answer `y` in.
- §4d step 7 was walked inside the scripted path, as the mandate asked. So the restore (3d) and the commit of
  `recovery.enabled: false` (3e) came before the pause and the terminate. Step 7 lists them after the terminate.
  The terminate and the end of the pause ran as step 7 prints them.
- The `argocd` CLI was run as W2 describes, and its first run failed because of the walker's wrapper, not the
  runbook. The command line is in `walk.log`.
- The Application went back to `main` between the fallback and §4d (step 5), not at the end. §4d therefore ran on
  the release as the lab runs it, and step 1's saved template was a strict reference.
- §4d step 3 ran in `<scratch>`, so `./break-glass` was created there, outside the worktree, and was removed
  afterwards.
- §1's `gsd-….db` path was set to the chosen copy. The 4c body's `gsd-….db` was set to 3d's copy. Nothing else in
  any command changed.

## Loss windows

Each restore discarded what the dashboard had recorded after its copy was taken:

- 3d: `14:09:46Z -> 14:54:11Z` (44m24s), 3 `sync_event` rows, by the script's estimate.
- 4c: the app ran on 3d's restore from the recovery-off rollout (15:08:13–15:08:33Z) until the `replicaCount: 0`
  sync (15:09:06–15:09:36Z), and §4a's restore of the same copy discarded what it wrote. Step 4a read 2869 live `sync_event` rows, highest id 186228, against the
  copy's 2863, highest id 186168: 6 rows. The other tables read the same as the copy.
- 6.4: `15:10:31Z -> 15:16:16Z` (5m44s), 0 rows in every table.

After 4c the app wrote new `sync_event` rows up to id 186228 again, the same highest id as the rows 4c discarded.
That is the restore's own caveat: "after an earlier restore two branches of history can reuse ids".

## Lab writes

- The Application's spec was changed by `release-crc.sh` five times: four values files, then `main`.
  `syncPolicy.automated.enabled` was set and removed twice (3e′, then 6.2 and 6.5). One operation was terminated
  (3e′).
- The Deployment's pod template was changed by hand twice (6.3 and 6.6). The ConfigMap
  `group-sync-dashboard-recovery` was created and deleted. One debug pod was created, and `oc debug` removed it.
- Three restores wrote `/data/gsd.db`. The kept sets under `/data/pre-restore/` (`20261002T145415.792307Z/`,
  `20261002T150951Z/`, `20261002T151622.016368Z/`) were left in place as the way back.
- Every app start took a scheduled backup, so `keep: 4` rotated the on-volume copies `gsd-20261002T140606…` and
  `gsd-20261002T140655…` out.
- No PVC was touched. The walk did not use the Secret `gsd-cluster-shared-qa` or the fleet account. The kubeconfig's
  current context stayed `crc-admin`.
