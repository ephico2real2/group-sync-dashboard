# #322 on the lab — the cluster-admin tier, 2026-09-25

Walked on the CRC lab (OpenShift 4.22.7) against `18e7c6690a`, PR #372's reviewed head. It ran as image
`0.35.0-18e7c6690a`, chart 0.57.0. It was deployed with `local-development/release-crc.sh --argocd`: Argo CD
Synced/Healthy, and `18e7c6690a` verified in-pod (`walk/release-tail.log`). The kept PVCs have the same UIDs before
and after (`walk/pvc-before.txt`, `walk/pvc-after.txt`).

#372 merged as `49c4834`. Its only change after `18e7c66` is one sentence of the Cluster Configurations page and
the test that pins it (`4cc54b7`, from Codex's review).

The merge was then deployed the same way:
- Argo CD Synced/Healthy, and `running : 49c483430e — verified in-pod`.
- The PVCs are identical before and after (`walk/pvc-after-merge.txt`, the same UIDs as `walk/pvc-after.txt`).
- Both pods were ready with 0 restarts on image `0.35.0-49c483430e`, and the dashboard pod logged 0 ERROR lines in
  its first 10 minutes. Measured with `oc get pods` and `oc logs --since=10m`; the output is not committed.

The script that ran is `walk/walk.py`, and its raw output is `walk/walk-output.txt`. Every row below is quoted from
that output. How the second persona was made, and removed, is in `walk/persona.txt`.

## The two personas

| | who | `list clusterrolebindings` | `update clusterrolebindings` |
|---|---|---|---|
| cluster-admin | `kubeadmin` | yes | yes |
| cluster-reader | `developer`, with a **temporary** `cluster-reader` binding, deleted after the walk | yes | no |

`walk/persona.txt` records the `oc auth can-i` answers. The cluster-reader is the persona #322's negative control
names: it passes the wide view's question (`list`), and fails the new tier's (`update`).

## What each one got

| | cluster-admin | cluster-reader |
|---|---|---|
| `/api/whoami` → `visibility.cluster_admin` | `true` | `false` |
| KPIs tab | present | **absent** |
| Cluster Configurations tab | present | **absent** |
| `GET /api/kpi` | 200 | **403** |
| `GET /api/clusterconfigs` | 200 | **403** |
| direct visit to `#page=kpi` | the KPI page | "Withheld, not empty … For administrators only." |
| direct visit to `#page=clusters` | 21 clusters listed | "Withheld, not empty …" |
| the wide tabs (Access granted, RBAC policy, Namespace audit, …) | present | present |
| page errors | none | none |

The cluster-reader keeps the wide view: the tier removes only the two cluster-administrator surfaces.

## Screenshots

| File | What it shows |
|---|---|
| `screenshots/01-admin-home-1280.png` | the cluster-admin's tab strip, with KPIs and Cluster Configurations |
| `screenshots/02-admin-kpi-1280.png` | the KPI page for the cluster-admin |
| `screenshots/03-admin-clusters-1280.png` | the Cluster Configurations tab for the cluster-admin |
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

It writes the six screenshots beside the script and exits non-zero on any uncaught page error.
