# Per-pod backup rotation on the CRC lab — the SPEC_E4 §5 walk (#391, T391-10)

Walked 2026-10-02 02:40–02:59 UTC on CRC (OpenShift 4.22.7), after PR #521 merged as `721a78db`, on the published image
`quay.io/ephico2real/group-sync-dashboard:2.2.0` (label `GSD_VERSION=2.2.0`).

The lab release cannot run two replicas, so the walk installed a throwaway release (development, as §5 says):
`helm install gsd391 charts/group-sync-dashboard -n gsd-391-walk --create-namespace -f walk-391-values.yaml`, from the
merge commit's chart. Its values file, `walk-391-values.yaml`, is in this folder. The full record is `walk.log`.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | The lab release's PVC UIDs | `f065b7a4-535c-4ef1-868c-58f5afee4953`, `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` |
| 2 | The throwaway release at two replicas | `gsd391` deployed in `gsd-391-walk`; both pods `2/2 Running` |
| 3 | Six backups per pod | Each pod's six `backup written` lines name `/data/backup/gsd-<stamp>-<that pod>.db`, `(4 kept)` from the fourth on; `/data/backup` holds 8 files, 4 per pod name; each pod's `gsd_backup_last_success_timestamp_seconds` equals its own newest copy's mtime |
| 4 | Delete one pod | The replacement (`…-fztn7`) wrote its own four; the deleted pod's (`…-f76v4`) four stayed: 12 files, `{4hbh7: 4, fztn7: 4, f76v4: 4}` (Orchestrator's notes, 11) |
| 5 | The NFS leg | Not run (optional) |
| 6 | Clean up by name | `helm uninstall gsd391`; the kept claim `gsd391-group-sync-dashboard-data` deleted by name; namespace `gsd-391-walk` deleted; none of the release's seven cluster-scoped RBAC objects left |
| 7 | The lab release on the merged code | Argo CD on `main` at `721a78db`, Synced and Healthy, app 2.2.0, one replica; `/data/backup` names `gsd-<stamp>.db` (four copies, `keep` 4); PVC UIDs equal step 1's |
