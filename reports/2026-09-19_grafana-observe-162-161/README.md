# Evidence — the Grafana and Observe integration (#162, #161, #157's doors)

Captured 2026-09-19 on CRC (OpenShift 4.22.7, the M5 Pro) from the deployed image `0.24.0-0101f8ec72`
(branch `feat/openshift-grafana-chart`), with the `openshift-grafana` chart 0.1.0 installed as release
`grafana` in the `group-sync-dashboard` namespace (`grafana.route.enabled=true`) and user-workload
monitoring switched on that day.

| File | What it shows |
|---|---|
| `01-kpi-page-both-doors-crc.png` | The KPI page through the real proxy as `kubeadmin`: **Open in Grafana** (from `grafana.url` + `dashboardUid` in `environments/crc.yaml`) and **Observe → Dashboards** (the console discovered from `openshift-config-managed/console-public`, the link scoped to the pod's own namespace) |
| `02-grafana-board-kpi-panels-crc.png` | The board the `GrafanaDashboard` CR provisioned (31 panels), reading live series through the chart's Thanos datasource: the six KPI panels — memory and CPU as a share of the cgroup limit, the throttled share with its 1 % mark, membership changes, login attempts, the volume's disk |
| `03-measurements.txt` | The datasource's health (`OK`), an instant query through it returning both pods' `gsd_process_memory_bytes` from `openshift-user-workload-monitoring/user-workload`, the CR's `DashboardSynchronized=True`, `/api/kpi`'s `links`, and `console-public` read with the dashboard's own ServiceAccount |

Two things measured on the way that the reference architecture did not say:

- The tenancy port's kube-rbac-proxy authorises the HTTP method as the RBAC verb — Grafana's default
  POSTed query was refused as `create pods`; the datasource uses GET (`get pods`, which `view` grants).
- grafana-operator substitutes `GrafanaDashboard.spec.datasources[].datasourceName` verbatim into the
  panels' `uid` fields — the datasource's NAME rendered in the browser (a name fallback) but Grafana's
  query API answered *Data source not found*; the binding takes the uid.
