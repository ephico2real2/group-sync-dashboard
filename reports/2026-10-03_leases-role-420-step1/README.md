# The Leases Role on the CRC lab: the SPEC_G4 §5 step-1 walk (#420)

Walked 2026-10-03, 14:36 to 14:40 UTC, on CRC (OpenShift 4.22.7), after PR #560 merged as `878bbaed80` (chart 0.66.2,
step 1: a namespaced Role and RoleBinding for the dashboard's Leases, nothing removed), by `scripts/run.sh`.
`walk.log` is the record.
- Argo CD synced the merge on its own 163 s into the walk, and the dashboard pod restarted at 14:39:05Z.
- The only cluster writes by the walk were a throwaway ServiceAccount and RoleBinding (`g4-role-probe`, labelled),
  deleted within 4 s. The exit trap found nothing left.

| Check | Result |
|---|---|
| §5 1.2: the Role and RoleBinding | `group-sync-dashboard-leases` exists twice, as a Role and a RoleBinding. The Role's rules are exactly `[{"apiGroups":["coordination.k8s.io"],"resources":["leases"],"verbs":["get","create","update"]}]`. The RoleBinding's `roleRef` is that Role, and its one subject is `ServiceAccount group-sync-dashboard/group-sync-dashboard`. |
| §5 1.3: nothing narrowed | `ClusterRole group-sync-dashboard-reader` still carries the same Lease rule. `oc auth can-i {get,create,update} leases.coordination.k8s.io --as system:serviceaccount:group-sync-dashboard:group-sync-dashboard` answers `yes` in `default` and in `group-sync-dashboard`. |
| §5 1.4: the elector's Lease renews | `leases/group-sync-dashboard`, held by the current pod `group-sync-dashboard-7dc7f74c5c-sj4xx`: `renewTime` 14:39:32.960895Z, then 14:39:53.218853Z, read 20 s apart. |
| §5 1.4: no Lease error | 0 lines in the dashboard container's log since its start match `forbidden reading lease`, `could not renew lease`, `lost leadership` or `fleet-state-unavailable`. |
| The Role alone suffices (beyond §5, for the operator's condition on step 2) | A throwaway ServiceAccount bound only to the new Role: `get`, `create` and `update` on Leases answer `yes` in `group-sync-dashboard` and `no` in `default`. |
| PVC UIDs | Unchanged: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`. |

## What step 1 cannot show

- **No renewal can be attributed to the Role yet.** While the ClusterRole's rule exists, either grant admits the
  dashboard's Lease calls. The direct evidence is step 2's own walk (§5 step 2, T420-8): the `renewTime` trace and
  the logs across the upgrade, with the ClusterRole's rule gone.
- **The fleet-account Lease is not renewed on a timer.** `leases/gsd-fleet-666f1ba7f2fdead0` is a claim, written when
  the dashboard binds as the fleet account: at lookup, at the daily ping (`fleetPingIntervalSeconds: 86400`) and at
  self-login. Its `renewTime` was 03:07:56Z in both reads.
- **It is in this namespace.** Both Lease users write to the pod's own namespace (`own_namespace()`, recorded on
  #420), and the probe shows the Role grants exactly that namespace.
