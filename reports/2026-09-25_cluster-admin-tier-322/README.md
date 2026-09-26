# #322 on the lab — the cluster-admin tier, 2026-09-25

This folder is a live walk of the cluster-admin tier from issue #322. It ran on the CRC lab (OpenShift 4.22.7) at
commit `18e7c6690a`, the reviewed head of PR #372, which shipped that tier. The image was `0.35.0-18e7c6690a`, chart
0.57.0.
- It was deployed with `local-development/release-crc.sh --argocd`: Argo CD Synced/Healthy, and `18e7c6690a`
  verified in-pod (`walk/release-tail.log`).
- The kept PVCs have the same UIDs before and after (`walk/pvc-before.txt`, `walk/pvc-after.txt`).

**After the walk.** #372 merged as `49c4834`. Its one change after `18e7c66` is `4cc54b7`, from Codex's review: the
Cluster Configurations page note no longer names the removed `clusterconfig:view` / `clusterconfig:manage` tiers.
`screenshots/03-admin-clusters-1280.png` shows the note as it was before that fix. The merge was deployed the same
way:
- `walk/release-tail-merge.log` ends `running : 49c483430e — verified in-pod`.
- `walk/pvc-after-merge.txt` has the same UIDs as `walk/pvc-after.txt`.
- `walk/pods-after-merge.txt`: both pods ready, 0 restarts, image `0.35.0-49c483430e`, and 0 ERROR or Traceback
  lines in the dashboard pod's log.

The script that ran is `walk/walk.py`, and its raw output is `walk/walk-output.txt`. The table below quotes that
output. How the second persona was made, and removed, is in `walk/persona.txt`.

## The two personas

| | who | `can-i list clusterrolebindings` | `can-i update clusterrolebindings` |
|---|---|---|---|
| cluster-admin | `kubeadmin` | yes (asked after the walk) | yes |
| cluster-reader | `developer`, with a **temporary** `cluster-reader` binding, deleted after the walk | yes | no |

Issue #322's negative control is this cluster-reader. They can list cluster role bindings, so the ordinary tabs stay
visible. They cannot update them, so the two administrator tabs must not appear. After the binding was deleted,
`developer` answers `no` to `list` again (`walk/persona.txt`).

## What each one got, as `walk/walk-output.txt` printed it

| | cluster-admin | cluster-reader |
|---|---|---|
| `whoami` | `"cluster_admin": true` | `"cluster_admin": false` |
| tabs | 14, including `"KPIs"` and `"Cluster Configurations"` | 12, neither of those two |
| `has KPI tab` / `has Cluster Configurations tab` | `True` / `True` | `False` / `False` |
| `/api/kpi`, `/api/clusterconfigs`, `/api/whoami` | `200`, `200`, `200` | `403`, `403`, `200` |
| `#page=kpi shows` | `"System status updated 1s ago · refresh 60s …"` | `"KPIs Withheld, not empty. This page reports the dashboard's own pods, …"` |
| `#page=clusters shows` | `"Cluster Configurations 21 clusters Every cluster the dashboard reads, …"` | `"Cluster Configurations Withheld, not empty. This page lists every cluster …"` |
| `page errors` | `[]` | `[]` |

The script trims each page's text at 160 characters. The rest of the two refusal cards, including "For administrators
only.", is in `screenshots/05-reader-kpi-1280.png` and `screenshots/06-reader-clusters-1280.png`.

The cluster-reader's 12 tabs are the cluster-admin's 14 without KPIs and Cluster Configurations. The wide view
stays; only the two administrator surfaces go.

## Screenshots

`walk.py` writes them beside itself (`walk/`); they are committed under `screenshots/`.

| File | What it shows |
|---|---|
| `screenshots/01-admin-home-1280.png` | the cluster-admin's tab strip, with KPIs and Cluster Configurations |
| `screenshots/02-admin-kpi-1280.png` | the KPI page for the cluster-admin |
| `screenshots/03-admin-clusters-1280.png` | the Cluster Configurations tab for the cluster-admin (the page note before `4cc54b7`) |
| `screenshots/04-reader-home-1280.png` | the cluster-reader's tab strip: neither tab |
| `screenshots/05-reader-kpi-1280.png` | `#page=kpi` opened directly by the cluster-reader: the refusal card |
| `screenshots/06-reader-clusters-1280.png` | `#page=clusters` opened directly by the cluster-reader: the refusal card |

## How to run it again

The passwords come from the environment only:

```sh
export GSD_ADMIN_USER=kubeadmin GSD_READER_USER=<a cluster-reader>
export GSD_ADMIN_PASSWORD=... GSD_READER_PASSWORD=...
local-development/.venv/bin/python reports/2026-09-25_cluster-admin-tier-322/walk/walk.py
```

It exits non-zero on any uncaught page error.
