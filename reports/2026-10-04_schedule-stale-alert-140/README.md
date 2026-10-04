# #140 on the lab: the schedule-status series and the stale-schedule alert, 2026-10-04

**Outcome.** The lab served application 4.5.0, deployed by Argo CD from main at `d5ca0f54` (PR #596, SPEC_F5).
The pods started at 07:32Z; Argo CD read Synced and Healthy. The spec's §5 check passed (`walk.log`; read-only, no
cluster write):
- **The series equal the page.** The report pod's `/report/metrics` exports 16 `gsd_report_schedule_status` lines,
  four per schedule. For each of the lab's four schedules, the series at 1 is the state the Reporting status payload
  shows (0 mismatches):

  | Schedule | State |
  |---|---|
  | `weekly-namespace-access` | `never` |
  | `quarterly-compliance` | `ok` |
  | `biweekly-groups` | `disabled` |
  | `delivery-walk` | `disabled` |

- **The rule is deployed:** the lab's PrometheusRule holds `GroupSyncDashboardReportScheduleLate`, with expression
  `max by (schedule) (gsd_report_schedule_status{status="late"}) == 1`, `for: 15m` and severity `warning`, among 20
  alerts.

## What this does not show
No lab schedule is late now, so the alert's firing is not shown live. It is proved by T140-6, `promtool test rules`
over the rendered rule (Prometheus 3.15.0, run by both reviewers of #596): the alert fires on `late` only, and a
negative control on `never` fails. The lab's Prometheus scrape of the series was not read (the querier needs a
token session).

| Path | Contents |
|---|---|
| `walk.log` | each command and its output |
| `evidence/state.json` | the raw series and the page's states read in the report pod |
| `scripts/` | `run.sh`, `in_pod.py` |
