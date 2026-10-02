# Off-volume backup on by default, on the CRC lab — the SPEC_E5 §5 walk (#304)

Walked 2026-10-02 03:38–03:44 UTC on CRC (OpenShift 4.22.7), after PR #524 merged as `934a9fab` (chart 0.61.0).
The lab's Argo CD Application tracks `main`. The lab's values file has set `backup.offsite.enabled: true` with the
`pvc` destination since PR #522; that is the strict form, and it renders the same objects as the new default.
The full record is `walk.log`.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | Before | PVC UIDs `f065b7a4-…` (data), `08c7d45c-…` (report artifacts), and `7f505595-…` (the offsite claim, created by #522) |
| 2 | Deploy and read the objects | Argo CD at `934a9fab`, Synced and Healthy, chart `group-sync-dashboard-0.61.0`. One CronJob (`15 */6 * * *`), one ConfigMap and one ServiceAccount (component `backup-offsite`). The claim is `Bound` on `crc-csi-hostpath-provisioner` (5Gi requested; the provisioner reports 149Gi capacity), with `helm.sh/resource-policy: keep` and `Prune=false,Delete=false,PruneLast=true`. It kept its UID through the upgrade |
| 3 | The alert before the first run | **Not observed:** the first offsite run (`gsd-offsite-check-030651`, 03:06 UTC, for #522) preceded this walk, so no moment before a first run existed |
| 4 | A manual run | `copied /data/backup/gsd-20261002T034300.088262Z.db -> /offsite/gsd-…db (14295040 bytes)`, `integrity_check ok; user_version 20`, `pruned 0 older copies (keep=14)`, and `no pre-upgrade-*.db under /data/pre-upgrade: nothing to ship`; the Job completed |
| 5 | The copy verifies | Runbook §1's `--check`, run as printed: `integrity_check ok`, `sidecar matches`, `user_version 20` |
| 6 | The alert clears | `kube_cronjob_status_last_successful_time` has a series for the CronJob; the rule's `absent(...)` returns nothing; no `GroupSyncDashboardOffsite*` alert is active |
| 7 | After | The three UIDs of step 1, unchanged |

The pre-upgrade pass ships after the first application release that migrates the schema. None exists at walk time:
2.1.0 and 2.2.0 migrate nothing, and SPEC_E3's walk moved its walk-only schema-21 copy to `/data/pre-restore/`.
