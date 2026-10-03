# The Lease narrowing on the CRC lab: the SPEC_G4 §5 step-2 walk (#420)

Walked 2026-10-03, 16:40 to 16:54 UTC, on CRC (OpenShift 4.22.7), across PR #562's merge (`ec51f50b6b`, chart
0.66.3): the ClusterRole's Lease rule removed, the dashboard's Leases granted only by the namespaced Role of step 1.
The operator agreed on #420. `scripts/run.sh` wrote `walk.log` and exited 0.
- **Recorders armed before the merge.** Argo CD auto-syncs `main`, so the T420-8 recorders were armed at 16:40:54Z,
  before the merge: `renew-trace.log` (the elector Lease every 2 s) and `old-pod-follow.log` (the running pod's
  log, followed).
- **The deploy.** Argo CD synced the merge 739 s later, at 16:53:13Z, with no Lease rule left in the ClusterRole.
- **Read-only.** Nothing in the walk writes to the cluster.

## T420-8: the Leases across the upgrade

| | Measured |
|---|---|
| The old pod `group-sync-dashboard-7dc7f74c5c-sj4xx` | held the Lease (`leaseTransitions` 13) for 353 samples; its last renewal was 16:52:52.48Z |
| The new pod `group-sync-dashboard-c8575bf57-cvb5v` | stood by while the old Lease was fresh: its log says "… holds lease …, renewed 10s of 30s ago — standing by". It took the Lease at 16:53:22.97Z, 30.5 s after the old pod's last renewal, as the 30 s Lease duration allows, with `leaseTransitions` 14. |
| Renewals with the ClusterRole's rule gone | 16:53:33.10Z, 16:53:43.13Z, 16:53:53.15Z, 16:54:03.18Z: every 10 s, granted only by the Role `group-sync-dashboard-leases` |
| Lease errors | 0 lines matching `forbidden reading lease`, `could not renew lease`, `lost leadership` or `fleet-state-unavailable`, in both the old pod's followed log and the new pod's log since its start |

This is today's behaviour on every upgrade at one replica, unchanged by the narrowing.

## T420-7: the narrowing

`ClusterRole group-sync-dashboard-reader` lists no `leases` among its resources. As
`system:serviceaccount:group-sync-dashboard:group-sync-dashboard`, `oc auth can-i {get,create,update}
leases.coordination.k8s.io` answers:

| Namespace | get | create | update |
|---|---|---|---|
| `default`, `kube-system`, `kube-node-lease`, `openshift-kube-controller-manager`, `openshift-kube-scheduler` | no | no | no |
| `group-sync-dashboard` | yes | yes | yes |

## Not shown here

- **The fleet-account Lease** (`gsd-fleet-666f1ba7f2fdead0`, `renewTime` 03:07:56Z) is a claim written when the
  dashboard binds as the fleet account: at lookup, at the daily ping and at self-login. It is not written on a timer.
  Its first write under the Role alone comes at the next fleet bind. It lives in the same namespace, and step 1's
  probe showed the Role grants exactly that namespace.
- **The PVC UIDs** are unchanged: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`.
