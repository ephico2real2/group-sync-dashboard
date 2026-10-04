# Release 5.0.0 (Epic F) on the lab: the post-release e2e walk, 2026-10-04

**Outcome.** The lab served application 5.0.0 at commit `704943a11c` (release PR #605). It was deployed by
`release-crc.sh --argocd main`, and Argo CD read Synced and Healthy at main `704943a11c` before and after the walk
(`evidence/run.log`).
- **The main pass passed 84 of 84 steps** (`results.json`): the login path, all 14 tabs, the lookup, the Reports
  catalogue, and each of the 11 reports' form and status.
- **The second pass passed 24 of 24** (`extra/results_extra.json`).
- **All 11 reports were generated, downloaded and checked** as PDF, HTML and JSON (`reports/`: 11 of each). All 11
  passed the integrity check (`integrity.jsonl`): the recomputed sha256 equals the JSON's field, the run record and
  the PDF metadata, and the HTML and PDF/A markers are present.
- **The Epic F surfaces, read with `oc` after the walk** (`evidence/run.log`, step 5 and the addendum):
  - **#106 and #594:** the report pod's scheduled formats are `html,json,csv` and its manual formats
    `html,json,pdf`. None of the five CronJobs names `pdf`.
  - **#109:** the `delivery-walk` CronJob runs the trigger with `--deliver webhook --attach html`.
  - **#140:** the PrometheusRule holds `GroupSyncDashboardReportScheduleLate` (for 15m, warning) among 20 alerts.
    The report service exports 16 `gsd_report_schedule_status` series, four per schedule, with exactly one state at 1
    for each: `biweekly-groups` and `delivery-walk` disabled, `quarterly-compliance` ok, `weekly-namespace-access`
    never.
  - **#392:** the ticket key Secret is mounted by the dashboard, its recovery twin and the report pod, and by no
    other Deployment. The report pod logged "ticket key loaded".
- **Also on screen:**
  - **#577:** the access-certification form's Generate label reads "PDF · HTML · JSON" with PDF and HTML ticked
    (`43-report-access-certification-status.png`).
  - **#587:** the Reports description names CSV (`21-reports-catalogue.png`).
  - **The version:** the OCR finds `v5.0.0` in the header of all 41 dashboard captures, `04` to `44`. All 11 reports'
    JSON names report service 5.0.0 at commit `704943a11c`, not dirty. Page one of each PDF prints that line, seen as
    "5.0.0 @ 704943a11c" on `extra/pdf-page1-groups.png`.
- **The PVC UIDs were unchanged** before and after: data `f065b7a4-…`, report-artifacts `08c7d45c-…`, offsite
  `7f505595-…`.

The walk document is `doc/e2e_walk.html`. Its PDF was sent to the operator and is not committed (the operator's rule
for walk documents).

## How it ran

- **Who walked:** `developer`, CRC's htpasswd account, logged in through the route.
- **The grant:** the walk ran under a labelled grant, `scripts/grant.yaml`, with `update clusterrolebindings`, the
  cluster-admin tier, which the wide tier also consults.
  - The precheck answered `no` before the grant.
  - The grant was created at 13:00:35Z and held for 214 s.
  - Afterwards the exit trap found nothing carrying `walk.gsd.lab/run=release-500-e2e-2026-10-04`, and `can-i`
    answered `no`.
- **The tools:** `scripts/run.sh` drove the repository's `local-development/e2e-walk/run_walk.sh` from the main
  checkout (capture, second pass, integrity, env facts, document). Both read the UI password from the environment
  only.

## What the walk did not establish

- **The Overview capture.** `05-tab-overview.png` caught the GroupSync CRs section while it still read "Loading…", as
  in the 4.0.0 walk. The step passed; the capture came before that section painted.
- **The first schedule-status read.** Step 5 first read `/metrics`, where the report service does not serve these
  series, and printed nothing. The addendum reads `/report/metrics`, where the #140 walk reads them, and `run.sh` now
  reads that path.

## Redaction

macOS Vision OCR of the 75 PNGs recognised 15,316 lines (`evidence/ocr-all.txt`).
- **`sha256~`:** 0 lines.
- **"password":** 5 lines, all labels or help text: "Password *" on the three captures of the login form, and two lines
  of the Logins tab's note about LDAP bind failures.
- **The positive control,** "Overview", is found 44 times.

The screenshots show the lab's seeded user names, and nothing is masked. No Secret's data was read: the ticket key is
named and its mounts are listed.

| Path | Contents |
|---|---|
| `NN-*.png` | the main pass: the login path, every tab, the lookup, each report's form and status, the recent runs |
| `extra/` | the second pass: the second cluster, the light theme, every HTML report in Chromium, page 1 of every PDF |
| `reports/` | the 11 reports as PDF, HTML and JSON, downloaded through the page |
| `results.json`, `extra/results_extra.json`, `integrity.jsonl`, `env.json` | the tools' results |
| `doc/e2e_walk.html` | the walk document |
| `evidence/` | `run.log` (each command and its output), `run_walk.txt`, `ocr-all.txt`, `pngs.txt` |
| `scripts/` | `run.sh`, `grant.yaml` |

To repeat: `KUBECONFIG=<the lab kubeconfig> scripts/run.sh`.
