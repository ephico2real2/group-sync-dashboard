# End-to-end walk — 2026-09-14, CRC, application 0.19.0 / chart 0.21.0

Playwright (Chromium, 1440×900) through the real route `https://group-sync-dashboard.apps-crc.testing`,
logged in as `kubeadmin` through oauth-proxy and OpenShift OAuth (provider `developer`). Run
2026-09-14T11:11:44Z → 11:17:00Z. The walk document `e2e-walk.pdf` (38 pages) embeds the screenshots and
reads every number from `results.json`, `results_extra.json`, `integrity.jsonl` and `env.json` — nothing
in it is typed from memory.

**Outcome: PASS.** 75 of 75 scripted steps in the main walk; 23 of 24 in the second pass, the one
failure being a product finding (#96), not a test defect. All 11 reports in the catalogue generated as
PDF/A-2b and HTML; 33 artefacts downloaded through the page's own download buttons; 11 of 11 passed the
four-way integrity check (hash recomputed from the JSON = the JSON's field = the run record = the PDF's
metadata; the HTML carries the prefix).

## What is here

| Path | Count | What |
|---|---|---|
| `artefacts/` | 33 | the generated reports: 11 × `.pdf` (PDF/A-2b), `.html`, `.json`, named `gsd_<cluster>_<report>_<UTC stamp>.<ext>` by the service |
| `screenshots/NN-*.png` | 35 | the main walk in order: the login path, the API probes, every tab, every report's form and status, the recent-runs table |
| `screenshots/extra-NN-*.png` | 20 | the second pass: the second cluster, the light theme, each HTML report opened in the browser |
| `screenshots/pdf-page1-*.png` | 11 | page 1 of each generated PDF, rendered from the downloaded file |
| `e2e-walk.pdf` | 1 | the walk document with the pictures embedded |
| `results.json`, `results_extra.json` | 2 | every step: time, verdict, detail, screenshot, API bodies, run records, file sizes |
| `integrity.jsonl` | 1 | the per-report hash checks |
| `env.json` | 1 | pods, images, chart revision, node CPU, preemption count, as measured at build time |
| `e2e_capture.py`, `e2e_extra.py`, `build_doc.py` | 3 | the scripts, as run |

## Findings recorded from this walk

- **#96** — a cluster removed from the configuration (`prod-east`, left over from the D2 live check)
  lingers in `/api/clusters` as `ok` with frozen data, feeds three stale critical alerts, and renders a
  404 when selected (`screenshots/extra-04-overview-cluster-prod-east.png`).
- **#97** — on this saturated lab node (99% CPU requests) the OLM `collect-profiles` cron preempts the
  priority-0 report pod every few minutes (29 times in the event window); every run in the walk still
  completed. Proposal: `priorityClassName` in the chart.

## To repeat it

```sh
cd local-development
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) .venv/bin/python \
  ../reports/2026-09-14_e2e-walk/e2e_capture.py \
  --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin --provider developer \
  --out /tmp/e2e/run
GSD_UI_PASSWORD=… .venv/bin/python ../reports/2026-09-14_e2e-walk/e2e_extra.py /tmp/e2e/run
# env.json: see build_doc.py's docstring for the fields; then
.venv/bin/python ../reports/2026-09-14_e2e-walk/build_doc.py /tmp/e2e/run /tmp/e2e/run/env.json
```

`e2e_extra.py` renders PDF first pages with macOS `sips`; on Linux substitute `pdftoppm`.
