# #312 closed out on the lab: #354 deployed, the checks re-run — 2026-09-24

Captured on the CRC lab (OpenShift 4.22.7) against main `244d4ab` — #355 (docs and reports) on top of #354, which
stops the chart's own `rbac.ocp.io/config-source` label from counting as "a policy operator is in use" — application
0.32.0 and chart 0.53.1. It was deployed with `local-development/release-crc.sh --argocd` from a detached worktree at
that commit: both images built and stamp-verified, the Application Synced/Healthy at 01:20:51Z, `244d4ab9c0` verified
in-pod, and the two kept PVCs identical before and after (`walk/pvc-before.txt`, `walk/pvc-after.txt`: UIDs
`f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, both created 2026-09-19T00:56:50Z).
The lab ran `4f4c070b08` before.

The scripts in `walk/` are copies of `reports/2026-09-24_rbac-provenance-and-review-counts/walk/` re-pointed at this
folder, with one change: the planted-grant script reads the refresh count it waits for from the pod's log instead of
carrying 206 and 205 (`diff` the two folders to see exactly that). Every number below is quoted from the `.out` files;
the pictures are the same captures the previous folder made, taken again on this deploy. The Logins capture the
verification script also takes belongs to #346, which is closed, and is not committed here.

| File | What it shows |
|---|---|
| `walk/release-244d4ab.log` | the deploy: build, push, the Argo CD sync to `244d4ab9c0`, the in-pod check (the image layer lines removed) |
| `walk/pvc-before.txt`, `walk/pvc-after.txt` | the two PVCs' UID, volume and creation time before and after the deploy — identical |
| `walk/verify-fixes.sh`, `.out` | #312's binding, the auditor tier with its negative control, the three pages as deployed |
| `walk/evidence-347.sh`, `.out` | a planted hand-made grant on a synced group: before, with it, after removing it |
| `walk/after-shared-rnd.out` | every cluster re-read once `shared-rnd`'s own refresh had run |
| `screenshots/347-access-granted.png` | the Access granted tiles with no unmanaged grant: 205 = 38 + 6 + 161 |
| `screenshots/347-access-granted-with-unmanaged.png` | the same tiles with the planted grant: 207 = 38 + 7 + 162 |
| `screenshots/347-unmanaged-section.png` | the planted grant in the page's Unmanaged section |
| `screenshots/347-overview-tile.png` | the Overview's `dashboard` tile: 7 bindings to review |
| `screenshots/347-kpi.png`, `347-kpi-posture-with-unmanaged.png` | the KPI page's To review: 18, then 21 = 18 unresolved · 0 dangling · 3 unmanaged |

## The chart's own auditor binding (the first three lines of #312's Definition of Done)

From `walk/verify-fixes.out`:

- `group-sync-dashboard-ra-b78c05817c9d` carries `config-source=group-sync-dashboard` (#350's label, chart 0.53.1).
- `oc auth can-i list clusterrolebindings` answers **yes** as a member of `app-ocp-rbac-groupsync-ns-auditor` and
  **no** without that group — the negative control. That is the question `visibility.adminSar` asks, so the auditor
  tier still passes it after the label.
- The new pod's first binding refresh, `refreshed 205 group bindings for dashboard` at 21:20:50 CDT, logged 0
  `UNMANAGED GRANT DISCOVERED` lines for the `-ra-` binding.
- `/api/clusters` reports 0 unmanaged grants on every cluster; the Access granted tiles read 205 = 38 + 6 + 161.

## #354 on a lab that uses the policy operator

#354 changes one thing: the chart's own label value no longer opens the `unmanaged` finding on a host with no policy
operator. The lab has one — 51 bindings carry `rbac.ocp.io/config-source`, 44 Group subject rows among them under
`baseline-nonprod-rbac`, `baseline-cluster-rbac`, `baseline-prod-rbac` and three others, measured 2026-09-24 with
`oc get clusterrolebindings,rolebindings -A -o json` — so the gate is open with or without the chart's 8 labelled
bindings, and #354 must change nothing here. It did not: a hand-made grant is still reported and every count is the
one the previous folder measured on `4f4c070`.

| | Before | With the grant | After removing it |
|---|---|---|---|
| `dashboard` findings (API) | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 | 207: ok 38, unresolved 6, **unmanaged 1**, built-in 162 | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 |
| Access granted tiles | 205 = 38 + 6 + 161 | **207 = 38 + 7 + 162** | — |
| Overview, bindings to review | — | **7** on `dashboard`, `shared-qa` and `shared-rnd` | — |
| KPI, To review | 18 = 18 unresolved · 0 dangling · 0 unmanaged | **21 = 18 unresolved · 0 dangling · 3 unmanaged** | — |
| `/api/clusters`, unmanaged | 0 / 0 / 0 | 1 / 1 / 1 | 0 / 0 / 1, then 0 / 0 / 0 (`walk/after-shared-rnd.out`) |

- The grant was a RoleBinding granting `view` to the synced group `app-ocp-rbac-groupsync-ns-auditor` in a namespace
  of its own, with no labels; the poller logged it at 21:36:49 CDT (`UNMANAGED GRANT DISCOVERED — … RoleBinding
  gsd-evidence-347/evidence-347-hand-made grants view to group …`).
- The tiles sum to the total in both states; the new namespace also adds one built-in binding, so the total rose by 2
  and the refresh line read 207, not 206. The copied script's wait for 206 therefore matched nothing and ran its
  twelve-minute budget; no number depends on it — the counts were read afterwards.
- `dashboard`, `shared-qa` and `shared-rnd` are the same CRC by design, so the one grant counts three times on the KPI
  page. After the namespace was deleted, the `dashboard` refresh at 21:37:49 CDT read 205 and `shared-rnd`'s own refresh
  came at 21:47:50 CDT; the re-read at 20:49:23 CDT shows all three back at 0.

## What this closes

#312's Definition of Done, line by line: the label is on every RBAC object the chart renders (#350, chart 0.53.1,
held by `local-development/tests/test_chart_rbac_provenance.py`); the live cluster no longer reports the auditor
binding, with the auditor tier passing its `can-i` and its negative control (above); and the ServiceAccount-subject
asymmetry is decided — not by inference but by the operator's label, the capability specified for #353 (SPEC_U1, in
its own pull request).
