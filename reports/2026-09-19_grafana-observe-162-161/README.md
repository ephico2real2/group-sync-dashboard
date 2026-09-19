# Evidence — the Grafana and Observe integration (#162, #161, #157's doors)

Captured 2026-09-19 on CRC (OpenShift 4.22.7, the M5 Pro) from the deployed image `0.24.0-0101f8ec72`
(branch `feat/openshift-grafana-chart`), with the `openshift-grafana` chart 0.1.0 installed as release
`grafana` in the `group-sync-dashboard` namespace (`grafana.route.enabled=true`) and user-workload
monitoring switched on that day.

| File | What it shows |
|---|---|
| `01-kpi-page-both-doors-crc.png` | The KPI page through the real proxy as `kubeadmin`: **Open in Grafana** (from `grafana.url` + `dashboardUid` in `environments/crc.yaml`) and **Observe → Dashboards** (the console discovered from `openshift-config-managed/console-public`, the link scoped to the pod's own namespace) |
| `02-grafana-board-kpi-panels-crc.png` | The board the `GrafanaDashboard` CR provisioned (31 panels), reading live series through the chart's Thanos datasource: the six KPI panels — memory and CPU as a share of the cgroup limit, the throttled share with its 1 % mark, membership changes, login attempts, the volume's disk |
| `04-kpi-page-doors-368003f.png` | The KPI page as `kubeadmin` on `368003f` — the doors after the Observe fix (`972b143`) |
| `05-observe-as-view-only-user-368003f.png` | **The Observe door as a view-only reader** (CRC's `developer`, a temporary `view` RoleBinding on the namespace, deleted after; the console's last-used project primed to *All Projects*): the project selected, the graphs drawn through the tenancy proxy |
| `06-observe-old-form-as-view-only-user-bad-request.png` | The same reader on the first door (`?project-dropdown-value=…`): *Project: All Projects*, every graph on *Bad Request* — the operator's report, reproduced |
| `07-observe-as-kubeadmin-last-project-all-368003f.png` | kubeadmin with `console.lastNamespace` set to All Projects first: the new door still selects the project |
| `08-observe-measurements.txt` | The deployed `/api/kpi` links; the walk's selector text and the `namespace=` each panel request carried, old door and new, both users; prom-label-proxy's 400 on :9092 with an empty `namespace=` |
| `09-kpi-page-doors-discovered-46ee06d.png` | The KPI page on `46ee06d` with **nothing configured** — `environments/crc.yaml` sets no monitoring, grafana or console value — both doors present: Grafana discovered from the Route, the console from `console-public` |
| `10-grafana-door-through-openshift-login-46ee06d.png` | The discovered Grafana door followed through the OpenShift login to the board (24 panels) |
| `11-defaults-measurements.txt` | The Grafana release on `--reset-values` (no user values), the gate's `user-workload monitoring: ON`, no object left in `openshift-monitoring`, the objects the dashboard chart's defaults rendered, the CR synced, the pod's Route lookup and the discovered links |
| `12-secrets-minted-on-the-cluster.txt` | The hook that mints the Grafana admin and proxy-cookie Secrets on the cluster instead of rendering them: the four upgrades it took to get there, measured (Helm's failed-revision diff base, the operator's datasource backoff), and the KEPT result from a deployed revision |
| `observe_walk.py` | The Playwright walk (CONSOLE_USER / CONSOLE_PASSWORD / OBS_PATH) |
| `03-measurements.txt` | The datasource's health (`OK`), an instant query through it returning both pods' `gsd_process_memory_bytes` from `openshift-user-workload-monitoring/user-workload`, the CR's `DashboardSynchronized=True`, `/api/kpi`'s `links`, and `console-public` read with the dashboard's own ServiceAccount |

Two things measured on the way that the reference architecture did not say:

- The tenancy port's kube-rbac-proxy authorises the HTTP method as the RBAC verb — Grafana's default
  POSTed query was refused as `create pods`; the datasource uses GET (`get pods`, which `view` grants).
- grafana-operator substitutes `GrafanaDashboard.spec.datasources[].datasourceName` verbatim into the
  panels' `uid` fields — the datasource's NAME rendered in the browser (a name fallback) but Grafana's
  query API answered *Data source not found*; the binding takes the uid.
