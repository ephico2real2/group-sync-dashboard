# Evidence — the KPI module (#156) and the KPI page (#157)

Captured 2026-09-19 on CRC (`crc-local` + the `mock` cluster) from the deployed image
`0.24.0-12065bf9e5` (branch `feat/kpi-page`, commit `12065bf9e5287d123cf6ff717c956c037c10b75f`, PR #207 stacked on PR #206),
through the real oauth-proxy as `kubeadmin`, with `local-development/capture-screenshots.py`.
Every figure on the page is the cluster's own; none is carried over from the mock.

| File | What it shows | Where from |
|---|---|---|
| `01-kpis-crc-1440-light.png` | The KPI page, light, 1440 px: the dashboard pod on **watch** (throttled 3.03 % of periods over a 1 % mark, the mark drawn at 20 % of a track scaled to 5 %), the report pod healthy, 69 groups (62 + 7), 48 bindings + 155 built-in, 6 to review, 2/2 clusters up with the leader held, 81.4 % login success over 43 attempts and 3 providers, 3/4 CRs with the mock's overdue, 4 report runs since 2026-09-19, the Observe door from `console.url` and no Grafana door (none configured) | CRC, the deployed image |
| `02-kpis-crc-375-dark.png` | The same page, dark, 375 px: no sideways scroll, the meters wrapped to two rows, the clusters table scrolling in its own container | CRC, the deployed image |
| `03-dashboard-metrics-12065bf.txt` | The dashboard pod's `/metrics`: the `gsd_process_*` and `gsd_volume_disk_*` families under `component="dashboard"`, `gsd_membership_changes_total`, and `gsd_login_attempts_total` by `developer` / `ldap-local` / `unknown` — no name in any label | `curl` on the pod's loopback |
| `04-report-metrics-12065bf.txt` | The report pod's `/report/metrics`: the same process families under `component="report"` | `curl` on the pod's loopback |

The report pod's CPU row reads `—` in these captures: the pod had just rolled and a rate needs two
samples at least five seconds apart (`gsd/kpi/system.py`); the next poll fills it. The throttled share
is a rate over the last poll interval, so it moves between captures (3.03 % at 15:13, 0.00 % at 15:13:35).
