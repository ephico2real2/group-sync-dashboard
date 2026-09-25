# #312, #346 and #347 on the lab — 2026-09-24

Captured on the CRC lab (OpenShift 4.22.7) against main `4f4c070`, application 0.32.0 and chart 0.53.1. It was
deployed with `local-development/release-crc.sh --argocd`: Synced/Healthy, `4f4c070b08` verified in-pod, and the
kept PVCs identical to the baseline. The scripts that ran and their raw output are in `walk/`; every number in the
sections below is quoted from that output, except the Logins dates, which are read from
`screenshots/346-logins-banner.png`.

#312's follow-up, #354, was not deployed when this was captured. It changes only the check that decides whether a
policy operator is in use, and the lab has one in use, so no number here depends on it.

| File | What it shows |
|---|---|
| `walk/verify-fixes.sh`, `.out` | #312's binding, the auditor tier with its negative control, and the three pages as deployed |
| `walk/evidence-347.sh`, `.out` | #347 with a planted hand-made grant: before, with it, and after removing it |
| `screenshots/346-logins-banner.png` | the Logins page's window note under the audit-log source |
| `screenshots/347-access-granted-before.png` | the Access granted tiles with no unmanaged grant: 205 = 38 + 6 + 161 |
| `screenshots/347-access-granted-with-unmanaged.png` | the same tiles with the planted grant: 207 = 38 + 7 + 162 |
| `screenshots/347-unmanaged-section.png` | the planted grant in the page's own Unmanaged section |
| `screenshots/347-overview-tile.png` | the Overview's `dashboard` tile: 7 bindings to review |
| `screenshots/347-kpi-posture-with-unmanaged.png` | the KPI page: To review 21 = 18 unresolved · 0 dangling · 3 unmanaged |

## #312 — the chart's own auditor binding

From `walk/verify-fixes.out`:

- `group-sync-dashboard-ra-b78c05817c9d` carries `config-source=group-sync-dashboard`.
- `oc auth can-i list clusterrolebindings` answers **yes** as a member of `app-ocp-rbac-groupsync-ns-auditor`, and
  **no** without that group (the negative control). That is the question `visibility.adminSar` asks
  (`list clusterrolebindings`, `charts/group-sync-dashboard/values.yaml`), so the auditor tier still passes it.
- The new pod logged 0 `UNMANAGED GRANT DISCOVERED` lines for the binding, after its first binding refresh
  (`refreshed 205 group bindings for dashboard`).
- `/api/clusters` reports 0 unmanaged grants on every cluster.

## #346 — the Logins page and its source

From `walk/verify-fixes.out`, on the deployed page under `loginCapture.source: audit-log`:

- "oldest audit file still on the control-plane nodes": present.
- "dies with its pod": absent.
- The Node column and the "control-plane node whose audit file" help: present.

`screenshots/346-logins-banner.png` shows the note beside its own dates: "Watching since 2026-09-21 02:15:28 EDT" and
"oldest attempt still retained 2026-09-16 10:26:15 EDT", older than capture because the first read backfilled
through the rotated audit files.

## #347 — every review count includes unmanaged grants

#312 labelled the lab's only unmanaged grant, so the lab had none to show. `walk/evidence-347.sh` planted one in a
namespace of its own and removed it afterwards. It was a RoleBinding granting `view` to the synced group
`app-ocp-rbac-groupsync-ns-auditor`, with no labels.

| | Before | With the grant | After removing it |
|---|---|---|---|
| `dashboard` findings (API) | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 | 207: ok 38, unresolved 6, **unmanaged 1**, built-in 162 | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 |
| Access granted tiles | 205 = 38 + 6 + 161 | **207 = 38 + 7 + 162** | — |
| Overview, bindings to review | — | **7** on `dashboard`, `shared-qa` and `shared-rnd` | — |
| KPI, To review | 18 = 18 unresolved · 0 dangling · 0 unmanaged | **21 = 18 unresolved · 0 dangling · 3 unmanaged** | — |

- The tiles sum to the total in both states; the unmanaged grant is counted under **Need review**.
- The new namespace also added one built-in binding, which is why the total rose by 2.
- The KPI page sums the fleet. `dashboard`, `shared-qa` and `shared-rnd` are the same CRC by design, so the one
  grant counts three times.
- The poller logged it at 20:31:35 EDT: `UNMANAGED GRANT DISCOVERED — dashboard: RoleBinding
  gsd-evidence-347/evidence-347-hand-made grants view to group …`.
- After the namespace was deleted, the 20:36:35 refresh reported 205 bindings, and every cluster was back to 0
  unmanaged.
