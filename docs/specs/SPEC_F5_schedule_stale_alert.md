# SPEC F5 — an alert when a report schedule silently stops producing evidence: the status page's own verdict exported per schedule, one rule on `late` (#140)

| | |
|---|---|
| Programme | Epic F (#386), reports: honest seals, more formats, diffs and delivery. Build step 5 of 6: #140 item 2, the evidence-gap alert (review F5 of P4); item 1 (C4, unknown manifest keys) stays parked on its trigger |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 4.5.0, chart 0.68.0 |
| Version note | Image content (`gsd/reporting/server.py` and `metrics.py` gain the gauge), so the next application MINOR, 4.5.0 (`docs/specs/README.md`, the version ladder). The chart takes a MINOR: a new alert is behaviour (`charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`) and it adds a value key, `monitoring.prometheusRule.for.reportScheduleLate`, as each of the chart's other rules has one (§3.4); the history agrees (0.67.0: "MINOR: `reporting.schedules[].deliver` …"; 0.66.5 to 0.66.7 were PATCHes because they moved only appVersion and docs). Read on `451ff688` (application 4.4.0, chart 0.67.0). W1 was `specified` at chart 0.68.0; by SPEC_E5's rule (a `specified` spec names a chart version above `Chart.yaml` and above every other `specified` claim) this spec takes 0.68.0 as the next to be built and W1 moves to 0.69.0, its index row and its header in this spec's own commit. A release that lands first makes the version blocks fail their check; the implementing pull request corrects them here first |
| Issue | [#140](https://github.com/ephico2real2/group-sync-dashboard/issues/140) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-04, from the issue's refined body (2026-09-26, item 2) and the orchestrator's brief, re-measured against main `451ff688` (after F4). Measured with the repository's venv (Python 3.14, prometheus_client 0.26.0), `helm template`, promtool 3.15.0 from `quay.io/prometheus/prometheus` and read-only `oc get` on the lab. §7's 20 blocks were generated from a working copy and proved against a clean checkout of `451ff688` (§4.3) |

## How to read this spec

The plain point first: each report schedule has a state on the Reporting status page (`ok`, `late`, `never` or
`disabled`), and only someone who opens that page sees it. This spec exports that state as a Prometheus series
and adds one alert that fires when a schedule reads `late`: its last expected run time is more than 30 minutes
past and no run of it has succeeded since. The page and the alert read the same function, so they cannot
disagree.

§1 is the mandate. §2 is the research: sources, the code, the measurements. §2a weighs option A against option B.
§3 is the design, one rule per subsection with its reason. §4 maps each Definition-of-Done item to a test and
records the proof. §5 is the lab. §6 is what an operator sees. §7 is the change as implementation blocks
(`docs/specs/README.md`, "Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F5_schedule_stale_alert.md . --apply

Line citations into the code at `451ff688` are `file:line` in plain text inside quoted output and tables; prose
cites `path#anchor`.

## Orchestrator's notes

1. **The issue's line numbers moved.** The issue (filed 2026-09-16, refined 2026-09-26) cites server.py:543-552
   for the states and trigger.py:88-94 for the 409 skip. On `451ff688` the states are server.py:563-574 (the
   computation server.py:536-573, inside `reporting_status`, server.py:530) and the skip is trigger.py:241-247
   (F4 grew the trigger); the seed the issue cites at server.py:91-103 is server.py:94-106. metrics.py:87 and
   monitoring.yaml:77 still hold.
2. **The lab's schedules.** `nightly-namespace-access` was renamed `weekly-namespace-access` (`0 22 * * 0`,
   Sundays 22:00 America/New_York) on 2026-10-02; the lab's schedules are environments/crc.yaml:102-127
   (`weekly-namespace-access`, `quarterly-compliance`, `biweekly-groups` paused, `delivery-walk` paused). The
   Definition of Done's "reads `ok` for `nightly-namespace-access`" becomes `weekly-namespace-access` (§5).
3. **Monitoring on the lab is not parked any more.** The brief and the issue say the lab's Prometheus does not
   scrape the chart. Measured 2026-10-04 05:33Z (read-only): `enableUserWorkload: true` in
   `openshift-monitoring/cluster-monitoring-config`; `prometheus-user-workload-0` and
   `thanos-ruler-user-workload-0` Running in `openshift-user-workload-monitoring`; the chart's PrometheusRule
   `group-sync-dashboard` (19 alerts) and both ServiceMonitors present in `group-sync-dashboard` (age 2d3h,
   chart 0.67.0, report image 4.4.0). environments/crc.yaml:36-43 says the same (user-workload monitoring on since
   2026-09-19, the rules and monitors the chart's default since 0.36.0). Whether the series are actually
   scraped, and an alert's state, were **not measured**: no `oc get` path reaches the Prometheus API (the pod
   listens on loopback, `connection refused` on the pod proxy; the Thanos querier asked for credentials). §5
   therefore shows the series on the report pod's loopback and asks for the alert state through the console.
4. **One computation.** The per-schedule loop moves verbatim out of `reporting_status` into `schedule_rows(at)`
   inside `build_report_app` (Block 1, 3); the page and the collector both call it (Block 2). The cron logic
   stays in `gsd/reporting/cron.py`; nothing is copied into Go templates or PromQL.
5. **Second copies of what this spec changes** (`git grep -n 'ReportSnapshotStale\|seventeen'` outside
   `docs/specs` and `reports`): the chart README's alert table and its heading (README.md:659, :676), the
   Grafana board's alert panel and its title (dashboards/group-sync-dashboard.json:285, :289, held to the rules
   by `test_chart_grafana_dashboard.py::test_the_text_panel_names_every_shipped_alert`), `values.yaml` (the
   `for` key). All four are blocks. The CHANGELOG's chart 0.36.0 entry ("the seventeen alerts") is history and
   stays.
6. **The index count.** Fifty-six on `451ff688`; this row makes it fifty-seven, and
   `local-development/tests/test_specs_index.py` moves to 57. #140 is below the numbers of rows above it (A4 is
   #534), so F5 is excluded from the rising-number assert by its id and pinned to #140, as F1 to F4 were.
7. **Dates.** Blocks 15 and 16 date the history lines 2026-10-04; the implementing pull request writes its own.

Questions for the operator (each has a stated default; the operator may reopen any):

1. **`never` does not alert (§3.3).** A schedule with no success on record reads `never` from its creation until
   its first success, and the service holds no creation instant to tell "not due yet" from "missed". Default:
   no alert; the series is exported so an estate can write its own rule. Alternative: a second, `info`-severity
   rule on `never` with a long `for:` (it would fire on every new quarterly schedule for up to three months).
2. **A cron expression `cron.py` cannot read** (a month or day name, `SUN`, which Kubernetes accepts and
   `cron.py` refuses, gsd/reporting/cron.py:8-9) gives the page no previous fire, so the schedule reads `ok`
   (after a success) or `never` for ever and the alert can never fire. Inherited from #221, not changed here
   (the page's states are "Must not change"). Default: a follow-up issue to refuse names at render or teach
   `cron.py` names.

## 1. The mandate, and what is out of scope

The mandate (#140 item 2, "The change", "Must not change", "Definition of Done"): settle where each schedule's
expected period comes from (option A, export the page's verdict or a previous-fire timestamp; option B, one
rendered rule per schedule), measure both and choose; ship the metric and the PrometheusRule; keep the existing
gauges' names and labels, the `/metrics` no-names rule, the page's `late`, `never`, `ok` and `disabled` states
and their 30-minute grace, the other rules and their thresholds, and item 1's loader; test that the exported
signal matches the page for the four states and that `helm template` renders the rule only when
`monitoring.prometheusRule.enabled` and reporting are on; prove the expression with `promtool test rules`.

Out of scope: item 1 (C4, unknown manifest keys; parked on its trigger, unchanged); a `never` alert (open
question 1); cron names (open question 2); any change to what the page computes.

## 2. Research, measured

### 2.1 Primary sources

| Source | What it says | What this spec takes |
|---|---|---|
| Prometheus docs, `docs/practices/instrumentation.md` §"Avoid missing metrics" (prometheus/docs, main, lines 257-262) | "Time series that are not present until something happens are difficult to deal with … export a default value such as `0` for any time series you know may exist in advance." | every state of every schedule is a series, 0 or 1; none appears or vanishes when the state changes |
| prometheus_client 0.26.0 `Enum` (client_python metrics.py:746, "Enum metric, which of a set of states is true"), its exposition measured in §2.3 | one series per state, the current one `1.0`, the others `0.0` | the same shape, with the label named `status` (the page's field name) instead of the metric's own name |
| Prometheus alerting rules (`for`, `labels`, `annotations` templating `{{ $labels.x }}`) and `promtool test rules` (`alert_rule_test`, `exp_alerts`) | a rule is pending until its expression has held for `for`, then firing; promtool evaluates a rule file against synthetic series | §3.4's rule; §4's T140-6 |
| Kubernetes CronJob `spec.timeZone` | the cron is read in that zone, else the controller's | the page reads the cron in `reporting.window.timezone` when the window is on (server.py:547), the same zone the chart gives the CronJob (report-cronjob.yaml:30-33) |

### 2.2 The code, read on `451ff688`

| Fact | Where |
|---|---|
| The last-success gauge `gsd_report_schedule_last_success_timestamp{schedule}`, one series per schedule that has succeeded | local-development/gsd/reporting/metrics.py:87-93 |
| It is re-seeded at start from the newest `done` run per schedule in the manifests | server.py:94-106 |
| The page's states: `disabled` if not enabled; `never` if no success on record; `late` if a previous fire exists, the last success is before it and it is more than 30 minutes past; else `ok` | server.py:563-574 |
| The page reads the cron in the window's zone, else UTC; an unreadable cron gives no previous fire | server.py:547, :555-560 |
| The cron code: `parse`, `next_fire`, `prev_fire`, `describe`, DST-aware | gsd/reporting/cron.py:86-155 |
| Schedule names are bounded to a DNS label before they become a `/metrics` label | server.py:367-373 |
| The report service is scraped by its own ServiceMonitor, `/report/metrics`, rendered with reporting on | charts/group-sync-dashboard/templates/monitoring.yaml:71-105 |
| The two report rules sit in a `gsd.reportingEnabled` block inside the `prometheusRule.enabled` block; every one of the chart's 19 rules takes its `for:` from `monitoring.prometheusRule.for.*`, none is literal; report rules are `severity: warning` | monitoring.yaml:107, :340-362; `grep -n 'for: ' templates/*.yaml \| grep -v Values` finds none |
| Both switches are on by default | values.yaml:2465-2475 |
| A 409 (window closed) exits 0: a green CronJob is not evidence | gsd/reporting/trigger.py:241-247 |
| The report Deployment runs one replica | templates/report-deployment.yaml:11 |
| Every `gsd_` family a rule references must be declared by a bare registry (HELP present) | tests/test_metrics.py:224-281 |
| The board's alert panel must name every shipped alert | tests/test_chart_grafana_dashboard.py:121-127 |
| CI installs promtool (Ubuntu's `prometheus` package) so promtool tests do not skip there | .github/workflows/ci.yml:222-229 |

### 2.3 The measurements

**The lab's schedules' gaps between fires**, one year from 2026-10-04 in America/New_York, with `cron.py`:

    weekly-namespace-access    0 22 * * 0         fires=54 min_gap=6 days, 23:00:00 (2027-03-08T03:00Z->2027-03-15T02:00Z) max_gap=7 days, 1:00:00 (2026-10-26T02:00Z->2026-11-02T03:00Z)
    quarterly-compliance       0 5 1 1,4,7,10 *   fires=5 min_gap=89 days, 23:00:00 (2027-01-01T10:00Z->2027-04-01T09:00Z) max_gap=92 days, 1:00:00 (2027-10-01T09:00Z->2028-01-01T10:00Z)
    biweekly-groups            0 5 1,16 * *       fires=25 min_gap=13 days, 0:00:00 (2027-02-16T10:00Z->2027-03-01T10:00Z) max_gap=16 days, 1:00:00 (2026-10-16T09:00Z->2026-11-01T10:00Z)
    delivery-walk              0 23 * * 0         fires=54 min_gap=6 days, 23:00:00 (2027-03-08T04:00Z->2027-03-15T03:00Z) max_gap=7 days, 1:00:00 (2026-10-26T03:00Z->2026-11-02T04:00Z)

No schedule on the lab has one period. A weekly schedule in a DST zone has three (6d23h, 7d, 7d1h); a
day-of-month schedule's gap runs from 13 to 16 days; a quarterly one's from 89d23h to 92d1h.

**The cost of the page's computation per scrape**, the lab's four schedules, 200 runs: `0.08 ms`.

**The enum exposition** (prometheus_client 0.26.0, `Enum(..., states=["ok","late","never","disabled"])`,
`state("late")`):

    demo_schedule_state{demo_schedule_state="ok",schedule="weekly"} 0.0
    demo_schedule_state{demo_schedule_state="late",schedule="weekly"} 1.0
    demo_schedule_state{demo_schedule_state="never",schedule="weekly"} 0.0
    demo_schedule_state{demo_schedule_state="disabled",schedule="weekly"} 0.0

## 2a. Alternatives considered

| | Option | Taken? | Why |
|---|---|---|---|
| A1 | Export the page's verdict, one series per state (`gsd_report_schedule_status{schedule,status}` 0/1); the rule reads `status="late"` | **yes** | the page's own function decides; the cron, the zone, DST and the 30-minute grace stay in tested Python; the rule is one line; `never` and `disabled` are visible, not silent |
| A2 | Export `…_previous_fire_timestamp{schedule}` beside the last-success gauge; the rule compares `prev > last and time() - prev > 1800` | no | the grace and the `disabled`/`never` cases would be written twice (Python for the page, PromQL for the rule), which is the two-computations failure the mandate forbids; a paused schedule still has a previous fire, so the rule would need the enabled flag as a third series |
| A3 | Export only `gsd_report_schedule_late{schedule}` 1/0 (the issue's first idea) | no | `never`, `disabled` and `ok` all read 0: the series cannot say which, and a dashboard panel could not show the page's four states |
| B | One rule per schedule, `time() - gsd_report_schedule_last_success_timestamp{schedule="x"} > <period> + grace`, the period written into the chart | no | measured (§2.3): no lab schedule has one period. A fixed 7 d period on `weekly-namespace-access` fires falsely in the fall-back week (2026-10-26T02:00Z to 2026-11-02T03:00Z is 7d1h, so at 2026-11-02T02:31Z the age passes 7d30m half an hour before the schedule is due); the max gap avoids that but makes the quarterly rule up to two days and the 1st-and-16th rule three days late; Helm's template functions have no cron reader, so the period is hand-written per schedule and drifts from `schedule:` when either changes; and a paused schedule needs its rule withheld by a second template branch |

Why A1: it is the only option where the alert cannot disagree with the page, because there is nothing to agree:
one function computes both (§3.1).

## 3. The design

### 3.1 One computation

The per-schedule loop of `reporting_status` (server.py:546-573) moves, unchanged, into `schedule_rows(at)`, a
closure of `build_report_app` beside `snapshot_age`. The status route calls `schedule_rows(at)` for the page; the
report registry is given `schedule_states=lambda: [(s["name"], s["status"]) for s in schedule_rows(now())]` and
calls it on every scrape. Why a closure handed to the collector: `snapshot_probe` already works this way
(server.py:108-113, :120); the collector stays free of settings and clocks, and a test that builds a bare
registry (tests/test_metrics.py:276) needs no change. The cost is 0.08 ms per scrape (§2.3).

### 3.2 The metric

`gsd_report_schedule_status{schedule, status}`, a gauge. For each schedule in `reporting.schedules[]`, four
series, one per state in `SCHEDULE_STATES = ("ok", "late", "never", "disabled")`:

| The page shows | `status="ok"` | `status="late"` | `status="never"` | `status="disabled"` |
|---|---|---|---|---|
| `ok` | 1 | 0 | 0 | 0 |
| `late` | 0 | 1 | 0 | 0 |
| `never` | 0 | 0 | 1 | 0 |
| `disabled` | 0 | 0 | 0 | 1 |

Why four series and not one: "avoid missing metrics" (§2.1): a series that appears only when the state is
`late` vanishes when it recovers, and `max_over_time`, `changes` and a board's state panel all need it present.
Why the label is `status`: the page's field is `status` (server.py:582). The labels are a schedule name
(operator configuration, bounded to a DNS label at server.py:371) and a fixed word: no person, so the
`/metrics` no-names rule holds (T140-4). With no schedules the family is declared and empty (T140-3). Cardinality:
4 × the number of schedules (16 on the lab).

### 3.3 `never` and `disabled`

- `disabled` (the schedule's `enabled: false`; its CronJob is suspended): the series reads `status="disabled"` 1.
  The alert does not fire: pausing is the operator's decision, not a gap.
- `never` (no successful run of the schedule on record, after the start-up seed from the manifests): the series
  reads `status="never"` 1. The alert does not fire: a new schedule reads `never` until its first fire, up to a
  quarter for a quarterly one, and the service holds no instant from which it was due. Open question 1.
- A schedule whose last success was pruned by retention also reads `never` after a restart (the seed reads what
  is on disk). Retention keeps the newest `keepPerSchedule` runs of each schedule (default 2), so this needs every
  run of it older than `days`, which only a schedule paused for longer than `days` reaches.

### 3.4 The rule

In `templates/monitoring.yaml`, inside the existing reporting block (monitoring.yaml:340-362), after
`GroupSyncDashboardReportSnapshotStale`:

```yaml
- alert: GroupSyncDashboardReportScheduleLate
  expr: max by (schedule) (gsd_report_schedule_status{status="late"}) == 1
  for: {{ .Values.monitoring.prometheusRule.for.reportScheduleLate }}     # 15m
  labels: {severity: warning}
  annotations:
    summary: "report schedule {{ $labels.schedule }} has produced no evidence since its last expected fire"
    description: >-
      The Reporting status page reads {{ $labels.schedule }} as late: … Check its runs on the Report history, the
      CronJob <reportName>-{{ $labels.schedule }} (its spec.timeZone against reporting.window.timezone, its last
      Job's log), and the report pod's log.
```

- **Name**: the chart's `GroupSyncDashboardReport…` prefix for report rules (monitoring.yaml:345, :355).
- **`max by (schedule)`**: one alert per schedule, without the scrape's `pod`/`instance` labels, so a rollout
  that briefly scrapes two report pods raises one alert, not two (T140-6 holds it); the KPI rules aggregate the
  same way (`max by (component)`, monitoring.yaml:367).
- **`for: 15m`, from a new key `monitoring.prometheusRule.for.reportScheduleLate`**: every one of the chart's
  rules takes `for:` from that map, so this one does too. The page's `late` already waits 30 minutes after the
  expected fire, so `for:` only has to outlast a scrape gap or a report pod restart (the start-up seed restores
  the state within one scrape); the alert therefore fires 45 minutes after a missed fire.
- **`severity: warning`**: as the other two report rules; a missing report is evidence lost, not an outage.
- **Rendered** exactly when `monitoring.prometheusRule.enabled` and `gsd.reportingEnabled` are both true (the
  enclosing blocks; T140-5).

### 3.5 What does not change, and the test that holds it

| Must not change | Held by |
|---|---|
| `gsd_report_schedule_last_success_timestamp{schedule}`, name and label | T140-4; `test_reporting_server.py::TestScheduleLastSuccessSurvivesRestart` unchanged |
| The `/metrics` no-names rule | T140-4 (a viewer's run; the name is in no series; the new series carry only `schedule` and `status`) |
| The page's `ok`, `late`, `never`, `disabled` and the 30-minute grace | T140-1, T140-2; `test_reporting_server.py::TestReportingStatusReview` (fire + 29 min ok, + 31 min late) and `test_the_three_cards_come_from_config_window_store_and_signals` unchanged |
| The other rules and their thresholds | §4.3: `helm template` before and after differs, apart from the version labels, images and checksums, only by the new rule's 17 lines and the board's two lines |
| Item 1's loader | no block touches `artifacts.py` |
| RBAC | §4.3: rendered atoms REMOVED 0, ADDED 0 |

## 4. Tests

### 4.1 One test per Definition-of-Done item

| DoD item | Test (`tests/test_reporting_schedule_status.py`) |
|---|---|
| the exported late signal matches the page for `ok`, `late`, `never` and `disabled` | T140-1 (four schedules, one per state, page and `/metrics` read from one app), T140-2 (the gauge turns `late` with the page between fire + 29 min and fire + 31 min) |
| `helm template` renders the rule only when `monitoring.prometheusRule.enabled` and reporting are on | T140-5 (default on, the exact expression, `for` from its key, off with either switch) |
| the expression proved by `promtool test rules` | T140-6 (pending before 15m, one firing alert per schedule after, for `late` only, through a two-pod scrape); skips without promtool locally, fails in CI if absent |
| Must not change | T140-3, T140-4, §3.5 |

### 4.2 Each test fails without the change, and why

On `451ff688` with only the new test file copied in, the module does not import:
`ImportError: cannot import name 'SCHEDULE_STATES' from 'gsd.reporting.metrics'`, so every test in it errors
(§4.3). Without the import (each test's own reason): T140-1 and T140-2 find no `gsd_report_schedule_status`
series; T140-3 finds no `# TYPE` line; T140-4 counts zero status lines; T140-5 finds no rule; T140-6 finds no rule
to test.

### 4.3 The proof

Every command below ran on 2026-10-04 against a detached worktree of origin/main `451ff688` with this spec
committed into it, using the repository's venv (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` from
`local-development`) and helm on PATH. promtool is not installed on this machine; it ran from the official image,
`quay.io/prometheus/prometheus@sha256:efd719c99d83b060d9daefdcf00360461adf279f45ef5391f8d111892118753e`
(`promtool, version 3.15.0 (branch: HEAD, revision: 5241a27fe3c6983549fccc32f6e65917408c63cd)`), through a
`promtool` wrapper on PATH (`podman run --rm -v "$PWD":/w -w /w --entrypoint promtool <image> "$@"`), so T140-6
and the board's PromQL test ran rather than skipped. The worktrees were removed afterwards.

**The blocks.**

    $ python local-development/apply-spec-blocks.py docs/specs/SPEC_F5_schedule_stale_alert.md .
    20 blocks check out across 12 files
    $ python local-development/apply-spec-blocks.py docs/specs/SPEC_F5_schedule_stale_alert.md . --apply
    20 blocks check out across 12 files
    applied to …/proof

The applied tree is byte-equal, file by file (`cmp`, 12 files), to the working copy the blocks were generated from.

**The new tests fail on main** (the test file copied onto a clean `451ff688`):

    $ pytest -q tests/test_reporting_schedule_status.py
    E   ImportError: cannot import name 'SCHEDULE_STATES' from 'gsd.reporting.metrics'
    ERROR tests/test_reporting_schedule_status.py
    1 error in 0.24s

With that one import replaced by the same tuple written in the test, each test fails on its own assertion:

    T140-1  test_reporting_schedule_status.py:90  AssertionError: {}            (the page reads the four states; no series)
    T140-2  test_reporting_schedule_status.py:101 KeyError: 'stale'
    T140-3  test_reporting_schedule_status.py:107 assert '# TYPE gsd_report_schedule_status gauge' in …
    T140-4  test_reporting_schedule_status.py:124 assert 0 == (4 * 4)
    T140-5  test_reporting_schedule_status.py:138 assert None is not None
    T140-6  test_reporting_schedule_status.py:160 promtool: FAILED: alertname: GroupSyncDashboardReportScheduleLate, time: 16m … got: []
    6 failed in 3.62s

T140-1's first assertion passing on main is the point: the page already reads `ok`, `late`, `never`, `disabled`
for the four fixtures; only the series is new.

**promtool, positive and negative control** (the rendered rule alone, T140-6's test file):

    $ promtool test rules test.yaml
      SUCCESS
    $ promtool test rules negative.yaml        # `fresh` exports late=1 too: a second alert appears
      FAILED:
        alertname: GroupSyncDashboardReportScheduleLate, time: 16m,
            exp:[ 0: Labels:{alertname="GroupSyncDashboardReportScheduleLate", schedule="stale", severity="warning"} … ],
            got:[ …

**The suites on the applied tree:**

    $ pytest -q tests/test_reporting_schedule_status.py tests/test_reporting_*.py tests/test_chart_*.py \
        tests/test_report_*.py tests/test_specs_index.py tests/test_docs_citations.py tests/test_kyverno.py \
        tests/test_metrics.py tests/test_values_defaults.py tests/test_release_crc.py tests/test_crc_schedules_in_window.py
    FAILED tests/test_docs_citations.py::test_no_citation_uses_a_line_number
      docs/specs/SPEC_F5_schedule_stale_alert.md:34 -> server.py:543-552 in backticks (and three more in this spec)
    1 failed, 2999 passed, 20 skipped, 2 warnings in 190.23s (0:03:10)

The one failure was this spec's own prose: four `file:line` citations in backticks (Orchestrator's note 1 and
§2.1). They were un-backticked, as the house rule asks for plain-text line citations, and the two index suites
re-run on the corrected spec:

    $ pytest -q tests/test_docs_citations.py tests/test_specs_index.py
    1947 passed, 18 skipped in 19.33s

**`helm template`, before and after** (release `t` with the defaults, and `group-sync-dashboard` with
environments/crc.yaml, base chart `451ff688` against the applied chart):

    default 4177 -> 4194 changed 209 {'helm.sh/chart': 86, 'app.kubernetes.io/version': 86, 'board': 4, 'checksum': 4, 'image': 10, 'offsite bind name': 2, 'added (the rule)': 17}
    crc 4723 -> 4740 changed 241 {'helm.sh/chart': 98, 'app.kubernetes.io/version': 98, 'board': 4, 'checksum': 4, 'image': 18, 'offsite bind name': 2, 'added (the rule)': 17}

Every changed line falls in one of those classes (a line in none of them would be printed; none was): the version
labels, the image tags (4.4.0 → 4.5.0), `checksum/config` and the offsite RoleBinding's hashed name (both computed
from the labels on every bump), the board's title and alert panel (2 lines, old and new), and the 17 added lines of
the new rule. No other rule, monitor, CronJob or Deployment line differs.

**RBAC**, every Role, ClusterRole and binding rendered as atoms (kind, role, apiGroup, resource, verb, names;
binding subjects):

    default: RBAC atoms 64 -> 64; REMOVED 0, ADDED 0
    crc: RBAC atoms 71 -> 71; REMOVED 0, ADDED 0

**Not measured:** the lab (§5): the series on the report pod, the alert's state in the lab's Prometheus; the full
hermetic and browser suites (the implementing pull request runs them).

## 5. On the lab (the implementing pull request)

After the release is deployed with `release-crc.sh --argocd` (the data and report-artifacts PVC UIDs recorded
before and after), in namespace `group-sync-dashboard`:

1. **The rule is on the cluster.** `oc get prometheusrule group-sync-dashboard -o jsonpath='{range .spec.groups[*].rules[*]}{.alert} {end}'`
   lists 20 alerts, `GroupSyncDashboardReportScheduleLate` among them (19 on 4.4.0, §Orchestrator's notes 3).
2. **The series, from the report pod's loopback** (the Service's `/report/metrics` is unauthenticated; the
   loopback avoids the NetworkPolicy):
   `oc exec deploy/group-sync-dashboard-report -- python3.14 -c "import ssl,urllib.request as u; c=ssl.create_default_context(); c.check_hostname=False; c.verify_mode=ssl.CERT_NONE; print(u.urlopen('https://127.0.0.1:8443/report/metrics', context=c).read().decode())" | grep '^gsd_report_schedule_'`.
   Expected, compared row by row with the dashboard's Reporting status page: `weekly-namespace-access` `ok` 1 if its last Sunday run succeeded (the DoD's check,
   renamed per §Orchestrator's notes 2), `quarterly-compliance` `never` 1 until 2027-01-01 if it has never run
   (or `ok`), `biweekly-groups` and `delivery-walk` `disabled` 1; each schedule with exactly four series.
3. **The alert's state.** The lab runs user-workload monitoring (§Orchestrator's notes 3), but reading an alert
   needs a token session (Observe → Alerting in the console, or the Thanos querier with `oc whoami -t`); the
   client-certificate kubeconfig has none. If the walk has a token session, it records
   `ALERTS{alertname="GroupSyncDashboardReportScheduleLate"}` (expected: no series while every schedule is `ok`,
   `never` or `disabled`). No schedule is made late on the lab to fire it: that would need a missed fire, which
   costs a week of evidence on the only enabled weekly schedule. The firing path is proved by T140-6 instead.

The evidence (the `oc` outputs, the series beside the page's rows) is committed under
`reports/<date>_140-schedule-stale-alert/` and posted on #140 pinned to the merge sha.

## 6. What an operator sees, and what it costs

On `/report/metrics`: four more series per schedule. In Alertmanager: `GroupSyncDashboardReportScheduleLate`
for schedule `<name>`, warning, 45 minutes after a fire that produced no successful run (30 minutes of the page's
grace, 15 of `for:`), resolved by the next successful run of that schedule. On the Grafana board: the alert panel
names it. Cost: 0.08 ms per scrape for four schedules; no new image, permission, migration, route or outbound
call.

## 7. Implementation blocks

### Block 1 — `local-development/gsd/reporting/server.py`: one function computes each schedule's row, `status` included, for the page and the gauge

<!-- block: local-development/gsd/reporting/server.py | edit -->

```python
            return None

    # This process's self-report (#156): its own cgroup and the filesystem under the artefact volume,
```

```python
            return None

    def schedule_rows(at: datetime) -> list[dict]:
        """Each configured schedule as the Reporting status page shows it, its `status` one of ok, late,
        never or disabled. The page (`/api/status`) and the gauge `gsd_report_schedule_status` (#140) both
        call this one function, so the alert reads the page's own verdict and never a second copy of it."""
        from . import cron
        sig = signals.snapshot()
        tz = settings.window.timezone if settings.window.enabled else None
        overrides = retention_overrides(settings)         # what the prune applies — the same reading
        schedules = []
        for sch in settings.schedules:
            enabled = sch.get("enabled", True) is not False
            override = sch.get("retention") or {}
            keep, days = overrides.get(sch["name"], (settings.scheduled_keep_per_schedule, settings.scheduled_retention_days))
            try:
                spec = cron.parse(sch["schedule"])
                nxt = cron.next_fire(spec, at, tz) if enabled else None
                prv = cron.prev_fire(spec, at, tz)
                cadence = cron.describe(sch["schedule"])
            except cron.CronError:
                spec, nxt, prv, cadence = None, None, None, sch["schedule"]
            last = sig["schedule_last_success"].get(sch["name"])
            last_dt = datetime.fromtimestamp(last, UTC) if last else None
            if not enabled:
                state = "disabled"
            elif last_dt is None:
                state = "never"
            elif prv is not None and last_dt < prv and at - prv > timedelta(minutes=30):
                # the last expected fire is more than half an hour behind us (the grace for the queue
                # and the render) and nothing has succeeded since it. The grace sits AFTER the fire:
                # measured with it on the other side (`last < prv - 30 min`), every healthy schedule
                # read `late` from the instant it fired until its run finished (review of #221, OB3).
                state = "late"
            else:
                state = "ok"
            schedules.append({
                "name": sch["name"], "report": sch["report"], "schedule": sch["schedule"], "cadence": cadence,
                "enabled": enabled, "retention": {"keepPerSchedule": keep, "days": days,
                                                  "overridden": bool(override)},
                "last_success": last_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if last_dt else None,
                "next_fire": nxt.strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None,
                "previous_fire": prv.strftime("%Y-%m-%dT%H:%M:%SZ") if prv else None,
                "status": state,
            })
        return schedules

    # This process's self-report (#156): its own cgroup and the filesystem under the artefact volume,
```


### Block 2 — `local-development/gsd/reporting/server.py`: the registry is handed the page's verdicts

<!-- block: local-development/gsd/reporting/server.py | edit -->

```python
    registry = build_report_registry(signals, store, runs, settings.snapshot_dir, snapshot_age,
                                     system=system_monitor.sampler, volume=system_monitor.volume)
```

```python
    registry = build_report_registry(signals, store, runs, settings.snapshot_dir, snapshot_age,
                                     system=system_monitor.sampler, volume=system_monitor.volume,
                                     schedule_states=lambda: [(s["name"], s["status"]) for s in schedule_rows(now())])
```


### Block 3 — `local-development/gsd/reporting/server.py`: the status route reads the same function

<!-- block: local-development/gsd/reporting/server.py | edit -->

```python
        from . import cron
        at = now()
        change, when = settings.window.next_change(at)
        sig = signals.snapshot()
        counts = {"queued": 0, "running": 0}
        rows, _ = store.list(limit=1000)
        for r in rows:
            if r.status in counts:
                counts[r.status] += 1
        tz = settings.window.timezone if settings.window.enabled else None
        overrides = retention_overrides(settings)         # what the prune applies — the same reading
        schedules = []
        for sch in settings.schedules:
            enabled = sch.get("enabled", True) is not False
            override = sch.get("retention") or {}
            keep, days = overrides.get(sch["name"], (settings.scheduled_keep_per_schedule, settings.scheduled_retention_days))
            try:
                spec = cron.parse(sch["schedule"])
                nxt = cron.next_fire(spec, at, tz) if enabled else None
                prv = cron.prev_fire(spec, at, tz)
                cadence = cron.describe(sch["schedule"])
            except cron.CronError:
                spec, nxt, prv, cadence = None, None, None, sch["schedule"]
            last = sig["schedule_last_success"].get(sch["name"])
            last_dt = datetime.fromtimestamp(last, UTC) if last else None
            if not enabled:
                state = "disabled"
            elif last_dt is None:
                state = "never"
            elif prv is not None and last_dt < prv and at - prv > timedelta(minutes=30):
                # the last expected fire is more than half an hour behind us (the grace for the queue
                # and the render) and nothing has succeeded since it. The grace sits AFTER the fire:
                # measured with it on the other side (`last < prv - 30 min`), every healthy schedule
                # read `late` from the instant it fired until its run finished (review of #221, OB3).
                state = "late"
            else:
                state = "ok"
            schedules.append({
                "name": sch["name"], "report": sch["report"], "schedule": sch["schedule"], "cadence": cadence,
                "enabled": enabled, "retention": {"keepPerSchedule": keep, "days": days,
                                                  "overridden": bool(override)},
                "last_success": last_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if last_dt else None,
                "next_fire": nxt.strftime("%Y-%m-%dT%H:%M:%SZ") if nxt else None,
                "previous_fire": prv.strftime("%Y-%m-%dT%H:%M:%SZ") if prv else None,
                "status": state,
            })
```

```python
        at = now()
        change, when = settings.window.next_change(at)
        sig = signals.snapshot()
        counts = {"queued": 0, "running": 0}
        rows, _ = store.list(limit=1000)
        for r in rows:
            if r.status in counts:
                counts[r.status] += 1
        schedules = schedule_rows(at)
```


### Block 4 — `local-development/gsd/reporting/metrics.py`: the four states

<!-- block: local-development/gsd/reporting/metrics.py | edit -->

```python
from .config import REPORT_NAMES


class ReportSignals:
```

```python
from .config import REPORT_NAMES

#: The Reporting status page's schedule states (server.py `schedule_rows`), each exported as its own series
#: of `gsd_report_schedule_status` so a schedule's every state is present at 0 or 1, never missing (#140).
SCHEDULE_STATES = ("ok", "late", "never", "disabled")


class ReportSignals:
```


### Block 5 — `local-development/gsd/reporting/metrics.py`: the collector takes the verdicts

<!-- block: local-development/gsd/reporting/metrics.py | edit -->

```python
    def __init__(self, signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                 system=None, volume: str | None = None):
        self.signals, self.store, self.runs, self.snapshot_dir, self.snapshot_probe = signals, store, runs, snapshot_dir, snapshot_probe
        # The KPI module's sources (#156): this process's cgroup sampler and the artefact volume.
        self.system, self.volume = system, volume
```

```python
    def __init__(self, signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                 system=None, volume: str | None = None, schedule_states=None):
        self.signals, self.store, self.runs, self.snapshot_dir, self.snapshot_probe = signals, store, runs, snapshot_dir, snapshot_probe
        # The KPI module's sources (#156): this process's cgroup sampler and the artefact volume.
        self.system, self.volume = system, volume
        #: () -> [(schedule name, state)], the status page's own verdicts (#140); None declares the family empty.
        self.schedule_states = schedule_states
```


### Block 6 — `local-development/gsd/reporting/metrics.py`: the family `gsd_report_schedule_status`

<!-- block: local-development/gsd/reporting/metrics.py | edit -->

```python
        for sched, ts in snap["schedule_last_success"].items():
            last_success.add_metric([sched], ts)
        yield last_success
```

```python
        for sched, ts in snap["schedule_last_success"].items():
            last_success.add_metric([sched], ts)
        yield last_success
        status = GaugeMetricFamily("gsd_report_schedule_status",
                                   "Each schedule's state on the Reporting status page, 1 for the current one and 0 "
                                   "for the others: ok, late (its last expected fire is over 30 minutes past with no "
                                   "success since), never (no success on record) or disabled (paused).",
                                   labels=["schedule", "status"])
        for sched, state in (self.schedule_states() if self.schedule_states else ()):
            for s in SCHEDULE_STATES:
                status.add_metric([sched, s], 1 if s == state else 0)
        yield status
```


### Block 7 — `local-development/gsd/reporting/metrics.py`: the registry passes them on

<!-- block: local-development/gsd/reporting/metrics.py | edit -->

```python
def build_report_registry(signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                          system=None, volume: str | None = None) -> CollectorRegistry:
    reg = CollectorRegistry()
    reg.register(ReportCollector(signals, store, runs, snapshot_dir, snapshot_probe, system=system, volume=volume))
```

```python
def build_report_registry(signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                          system=None, volume: str | None = None, schedule_states=None) -> CollectorRegistry:
    reg = CollectorRegistry()
    reg.register(ReportCollector(signals, store, runs, snapshot_dir, snapshot_probe, system=system, volume=volume,
                                 schedule_states=schedule_states))
```


### Block 8 — `local-development/tests/test_reporting_schedule_status.py`: T140-1 to T140-6

<!-- block: local-development/tests/test_reporting_schedule_status.py | create -->

```python
"""#140 item 2: a schedule that silently stops producing evidence raises an alert.

The report service exports the Reporting status page's own verdict per schedule as
`gsd_report_schedule_status{schedule, status}`, and the chart's rule reads `status="late"`. These tests hold the
gauge to the page (one computation, so they can never disagree), the rule's render to its two switches, and the
rule's expression to Prometheus's own evaluator (`promtool test rules`). SPEC_F5 §4."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from datetime import UTC, datetime

import pytest
import yaml
from fastapi.testclient import TestClient

from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import ArtifactStore, Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.metrics import SCHEDULE_STATES
from gsd.reporting.server import build_report_app
from gsd.reporting.ticket import mint
from gsd.activity import USER_HEADER
from gsd.reporting import TICKET_HEADER
from reporting_seed import CLUSTER, seeded_dirs
from test_chart_pdb import CHART, _render

SECRET = b"s" * 48
SERVICE = {"Authorization": f"Bearer {SECRET.decode()}"}
VENDOR = CHART.parents[1] / "local-development" / "gsd" / "static" / "vendor"
FONTS = (str(VENDOR / "DejaVuSans.ttf"), str(VENDOR / "DejaVuSans-Bold.ttf"))
ALERT = "GroupSyncDashboardReportScheduleLate"

#: One schedule per page state at 2026-09-20 12:00 UTC (no window, so the cron reads UTC):
#: `fresh` succeeded after today's 02:00 fire, `stale` last succeeded yesterday (today's fire is 10 h past),
#: `unrun` has no run on record, `paused` is disabled although it once succeeded.
SCHEDULES = (
    {"name": "fresh", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "stale", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "unrun", "schedule": "0 2 * * *", "report": "groups"},
    {"name": "paused", "schedule": "0 2 * * *", "report": "groups", "enabled": False},
)
EXPECTED = {"fresh": "ok", "stale": "late", "unrun": "never", "paused": "disabled"}


def _done(run_id: str, day: str, schedule: str) -> Run:
    return Run(id=run_id, report="groups", cluster=CLUSTER, params={}, formats=["html"],
               generated_by=f"schedule:{schedule}", generated_by_note="unattended", schedule=schedule,
               origin="schedule", requested_at=f"{day}T02:00:00Z", started_at=f"{day}T02:00:01Z",
               finished_at=f"{day}T02:02:00Z", status="done", sha256="ab" * 32)


def _app(tmp_path, at: datetime, schedules=SCHEDULES, seed=()):
    tmp_path.mkdir(exist_ok=True)
    snapshots, artifacts = seeded_dirs(tmp_path)
    store = ArtifactStore(str(artifacts))
    for r in seed:
        store.create(r)
    settings = ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=True,
                              pdf_variant="pdf/a-2b", font_regular=FONTS[0], font_bold=FONTS[1],
                              login_capture_enabled=True, schedules=schedules, max_queued_runs=0)
    return build_report_app(settings, secret=SECRET, clock=lambda: at)


def _status_series(metrics_text: str) -> dict[str, dict[str, float]]:
    """{schedule: {status: value}} from the exposition's gsd_report_schedule_status lines."""
    out: dict[str, dict[str, float]] = {}
    for line in metrics_text.splitlines():
        if line.startswith("gsd_report_schedule_status{"):
            labels, value = line.rsplit(" ", 1)
            pairs = dict(p.split("=", 1) for p in labels[len("gsd_report_schedule_status{"):-1].split(","))
            out.setdefault(pairs["schedule"].strip('"'), {})[pairs["status"].strip('"')] = float(value)
    return out


SEED = (_done("20260919T020000.000000Z-0001", "2026-09-19", "stale"),
        _done("20260919T020000.000000Z-0002", "2026-09-19", "fresh"),
        _done("20260920T020000.000000Z-0003", "2026-09-20", "fresh"),
        _done("20260919T020000.000000Z-0004", "2026-09-19", "paused"))


class TestTheGaugeIsThePagesVerdict:
    def test_t140_1_each_schedule_exports_the_state_the_page_shows_for_ok_late_never_and_disabled(self, tmp_path):
        with TestClient(_app(tmp_path, datetime(2026, 9, 20, 12, 0, tzinfo=UTC), seed=SEED)) as client:
            page = {s["name"]: s["status"] for s in client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()["schedules"]}
            series = _status_series(client.get(f"{REPORT_PREFIX}/metrics").text)
        assert page == EXPECTED, page                                  # the four states, as the page has always read them
        assert set(series) == set(EXPECTED), series
        for name, state in page.items():
            assert series[name] == {s: (1.0 if s == state else 0.0) for s in SCHEDULE_STATES}, (name, series[name])

    def test_t140_2_the_gauge_turns_late_with_the_page_at_the_thirty_minute_grace(self, tmp_path):
        stale_only = (SCHEDULES[1],)
        seed = (SEED[0],)
        for i, (at, state) in enumerate(((datetime(2026, 9, 20, 2, 29, tzinfo=UTC), "ok"),
                                         (datetime(2026, 9, 20, 2, 31, tzinfo=UTC), "late"))):
            with TestClient(_app(tmp_path / str(i), at, schedules=stale_only, seed=seed)) as client:
                page = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()["schedules"][0]["status"]
                series = _status_series(client.get(f"{REPORT_PREFIX}/metrics").text)["stale"]
            assert page == state and series[state] == 1.0 and sum(series.values()) == 1.0, (at, page, series)

    def test_t140_3_no_schedule_no_series_and_the_family_is_still_declared(self, tmp_path):
        with TestClient(_app(tmp_path, datetime(2026, 9, 20, 12, 0, tzinfo=UTC), schedules=())) as client:
            text = client.get(f"{REPORT_PREFIX}/metrics").text
        assert "# TYPE gsd_report_schedule_status gauge" in text
        assert not _status_series(text)


class TestMustNotChange:
    def test_t140_4_the_last_success_gauge_keeps_its_name_and_label_and_no_person_is_named(self, tmp_path):
        at = datetime.fromtimestamp(int(time.time()), UTC)            # a ticket is checked against the real clock
        with TestClient(_app(tmp_path, at, seed=SEED)) as client:
            ticket = {TICKET_HEADER: mint(SECRET, "alice.person", "all", 300), USER_HEADER: "alice.person"}
            assert client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER},
                               headers=ticket).status_code == 202
            text = client.get(f"{REPORT_PREFIX}/metrics").text
        last = [ln for ln in text.splitlines() if ln.startswith("gsd_report_schedule_last_success_timestamp{")]
        assert sorted(ln.split("}")[0] for ln in last) == sorted(
            f'gsd_report_schedule_last_success_timestamp{{schedule="{n}"' for n in ("fresh", "paused", "stale"))
        assert "alice.person" not in text, "/metrics is unauthenticated: no viewer's name in any series"
        status_lines = [ln for ln in text.splitlines() if ln.startswith("gsd_report_schedule_status{")]
        assert len(status_lines) == len(SCHEDULES) * len(SCHEDULE_STATES)
        assert all(ln.split("{")[1].split("=")[0] == "schedule" and ',status="' in ln for ln in status_lines)


def _rule(docs: list[dict]) -> dict | None:
    hits = [r for d in docs if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"] for r in g["rules"]
            if r.get("alert") == ALERT]
    assert len(hits) <= 1
    return hits[0] if hits else None


class TestTheRule:
    def test_t140_5_the_rule_renders_only_with_the_rules_and_reporting_on(self):
        on = _rule(_render())                                          # both on by default (values.yaml)
        assert on is not None
        assert on["expr"] == 'max by (schedule) (gsd_report_schedule_status{status="late"}) == 1'
        assert on["for"] == "15m" and on["labels"] == {"severity": "warning"}
        assert "{{ $labels.schedule }}" in on["annotations"]["summary"]
        assert "t-group-sync-dashboard-report-{{ $labels.schedule }}" in on["annotations"]["description"]
        assert _rule(_render("monitoring.prometheusRule.for.reportScheduleLate=45m"))["for"] == "45m"
        assert _rule(_render("monitoring.prometheusRule.enabled=false")) is None
        assert _rule(_render("reporting.enabled=false")) is None

    def test_t140_6_promtool_fires_on_late_only_once_per_schedule_after_for(self, tmp_path):
        """Prometheus's own evaluator over the rendered rule. Skips locally without promtool; CI installs it
        (ci.yml, "Install promtool") and must run it, as the board's PromQL test does."""
        promtool = shutil.which("promtool")
        if promtool is None:
            if os.environ.get("CI"):
                pytest.fail("CI must install promtool; the rule's unit test must not skip there")
            pytest.skip("promtool not installed")
        rule = _rule(_render())
        (tmp_path / "rules.yaml").write_text(yaml.safe_dump({"groups": [{"name": "f5", "rules": [rule]}]}))
        (tmp_path / "test.yaml").write_text(yaml.safe_dump(PROMTOOL_TEST, sort_keys=False))
        done = subprocess.run([promtool, "test", "rules", "test.yaml"], cwd=tmp_path,
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stdout + done.stderr


def _late(schedule: str, values: str, pod: str = "report-0") -> dict:
    return {"series": f'gsd_report_schedule_status{{schedule="{schedule}",status="late",pod="{pod}"}}', "values": values}


#: The one alert `stale` raises: one per schedule, whichever pod exported it.
FIRING = [{
    "exp_labels": {"schedule": "stale", "severity": "warning"},
    "exp_annotations": {
        "summary": "report schedule stale has produced no evidence since its last expected fire",
        "description": ("The Reporting status page reads stale as late: its last expected fire is more than 30 minutes "
                        "past and no run of it has succeeded since. Check its runs on the Report history, the CronJob "
                        "t-group-sync-dashboard-report-stale (its spec.timeZone against reporting.window.timezone, its "
                        "last Job's log), and the report pod's log."),
    }}]

#: One-minute steps. `stale` reads late from minute 0, so the alert is pending until `for` (15m) and firing
#: after; it is scraped from two pods for the first 20 minutes (a rollout) and still alerts once. `fresh`,
#: `unrun` and `paused` export late=0 throughout (they are ok, never and disabled), so they never fire.
PROMTOOL_TEST = {
    "rule_files": ["rules.yaml"],
    "evaluation_interval": "1m",
    "tests": [{
        "interval": "1m",
        "input_series": [
            _late("stale", "1x40"),
            _late("stale", "1x20", pod="report-1"),
            _late("fresh", "0x40"),
            _late("unrun", "0x40"),
            _late("paused", "0x40"),
        ],
        "alert_rule_test": [
            {"eval_time": "14m", "alertname": ALERT, "exp_alerts": []},
            {"eval_time": "16m", "alertname": ALERT, "exp_alerts": FIRING},
            {"eval_time": "30m", "alertname": ALERT, "exp_alerts": FIRING},
        ],
    }],
}
```


### Block 9 — `charts/group-sync-dashboard/templates/monitoring.yaml`: the rule

<!-- block: charts/group-sync-dashboard/templates/monitoring.yaml | edit -->

```yaml
            description: "gsd_report_snapshot_age_seconds is above four snapshot intervals; reports would print stale data with an honest 'data as of' line."
        {{- end }}
```

```yaml
            description: "gsd_report_snapshot_age_seconds is above four snapshot intervals; reports would print stale data with an honest 'data as of' line."
        # A schedule that silently stopped producing evidence (#140). The report service exports the
        # Reporting status page's own verdict per schedule, so the rule and the page cannot disagree:
        # `late` already holds the page's 30-minute grace after the expected fire. `never` (no success on
        # record) and `disabled` (paused) do not fire. A completed CronJob is not evidence: a run refused
        # outside the reporting window exits 0. max by (schedule): one alert per schedule while a rollout
        # briefly scrapes two report pods.
        - alert: GroupSyncDashboardReportScheduleLate
          expr: max by (schedule) (gsd_report_schedule_status{status="late"}) == 1
          for: {{ .Values.monitoring.prometheusRule.for.reportScheduleLate }}
          labels: {severity: warning}
          annotations:
            summary: "report schedule {{ `{{ $labels.schedule }}` }} has produced no evidence since its last expected fire"
            description: >-
              The Reporting status page reads {{ `{{ $labels.schedule }}` }} as late: its last expected
              fire is more than 30 minutes past and no run of it has succeeded since. Check its runs on
              the Report history, the CronJob {{ include "gsd.reportName" . }}-{{ `{{ $labels.schedule }}` }}
              (its spec.timeZone against reporting.window.timezone, its last Job's log), and the report pod's log.
        {{- end }}
```


### Block 10 — `charts/group-sync-dashboard/values.yaml`: `for.reportScheduleLate`

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
      reportSnapshot: 30m   # GroupSyncDashboardReportSnapshotStale: the newest VACUUM INTO copy is older than this
```

```yaml
      reportSnapshot: 30m   # GroupSyncDashboardReportSnapshotStale: the newest VACUUM INTO copy is older than this
      # GroupSyncDashboardReportScheduleLate: the status page's `late` already waits 30 minutes past the
      # expected fire, so this only needs to outlast a scrape gap or a report pod restart.
      reportScheduleLate: 15m
```


### Block 11 — `charts/group-sync-dashboard/README.md`: the alert table's heading

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
#### The seventeen alerts, and two more wherever the offsite CronJob renders (the default)
```

```markdown
#### The eighteen alerts, and two more wherever the offsite CronJob renders (the default)
```


### Block 12 — `charts/group-sync-dashboard/README.md`: the alert table's row

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| `GroupSyncDashboardReportSnapshotStale` | `gsd_report_snapshot_age_seconds` above four snapshot intervals — the dashboard's leader is not writing copies, so a report would print stale data with an honest "data as of" line. Rendered only with `reporting.enabled` | `for.reportSnapshot`, `30m` |
```

```markdown
| `GroupSyncDashboardReportSnapshotStale` | `gsd_report_snapshot_age_seconds` above four snapshot intervals — the dashboard's leader is not writing copies, so a report would print stale data with an honest "data as of" line. Rendered only with `reporting.enabled` | `for.reportSnapshot`, `30m` |
| `GroupSyncDashboardReportScheduleLate` | `gsd_report_schedule_status{status="late"} == 1` — the Reporting status page reads a schedule as late: its last expected fire is more than 30 minutes past and no run of it has succeeded since (a wrong timezone, a Job that never starts). `never` and `disabled` do not fire. Rendered only with `reporting.enabled` | `for.reportScheduleLate`, `15m` |
```


### Block 13 — `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json`: the alert panel's title

<!-- block: charts/group-sync-dashboard/dashboards/group-sync-dashboard.json | edit -->

```json
"title": "The shipped alerts (monitoring.prometheusRule): seventeen, nineteen with backup.offsite",
```

```json
"title": "The shipped alerts (monitoring.prometheusRule): eighteen, twenty with backup.offsite",
```


### Block 14 — `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json`: the alert panel's row

<!-- block: charts/group-sync-dashboard/dashboards/group-sync-dashboard.json | edit -->

```json
the report service's data copy is stale; scraped from the REPORT pod's `/report/metrics` |\n| `GroupSyncDashboardPodThrottled` | warning | `max by (component) (rate(gsd_process_cpu_throttled_periods_total[15m]) / rate(gsd_process_cpu_periods_total[15m])) > kpi.thresholds.throttledPercent/100` (0.01) — the saturation signal the KPI page marks amber; raise the pod's CPU limit |\n| `GroupSyncDashboardPodMemoryHigh` | warning | `max by (component) (gsd_process_memory_bytes / gsd_process_memory_limit_bytes) > kpi.thresholds.memoryPercent/100` (0.8) — the next step is the OOM kill |\n| `GroupSyncDashboardVolumeDiskFull` | warning | `max by (component) (gsd_volume_disk_used_bytes / gsd_volume_disk_total_bytes) > kpi.thresholds.diskPercent/100` (0.8) — on a hostPath volume, the node's disk |\n\nGauges are per replica: aggregate with `max()`; counters with `sum()`. `/metrics` names no group and no user by design."
```

```json
the report service's data copy is stale; scraped from the REPORT pod's `/report/metrics` |\n| `GroupSyncDashboardReportScheduleLate` | warning | *(`reporting.enabled` only)* `max by (schedule) (gsd_report_schedule_status{status=\"late\"}) == 1` — the Reporting status page reads the schedule as late: no success since its last expected fire, 30 minutes on |\n| `GroupSyncDashboardPodThrottled` | warning | `max by (component) (rate(gsd_process_cpu_throttled_periods_total[15m]) / rate(gsd_process_cpu_periods_total[15m])) > kpi.thresholds.throttledPercent/100` (0.01) — the saturation signal the KPI page marks amber; raise the pod's CPU limit |\n| `GroupSyncDashboardPodMemoryHigh` | warning | `max by (component) (gsd_process_memory_bytes / gsd_process_memory_limit_bytes) > kpi.thresholds.memoryPercent/100` (0.8) — the next step is the OOM kill |\n| `GroupSyncDashboardVolumeDiskFull` | warning | `max by (component) (gsd_volume_disk_used_bytes / gsd_volume_disk_total_bytes) > kpi.thresholds.diskPercent/100` (0.8) — on a hostPath volume, the node's disk |\n\nGauges are per replica: aggregate with `max()`; counters with `sum()`. `/metrics` names no group and no user by design."
```


### Block 15 — `charts/group-sync-dashboard/Chart.yaml`: chart 0.68.0 and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# the dashboard and the Job; appVersion moves to application 4.4.0 (below); #109, SPEC_F4. No RBAC change.
version: 0.67.0
```

```yaml
# the dashboard and the Job; appVersion moves to application 4.4.0 (below); #109, SPEC_F4. No RBAC change.
# CHART 0.68.0 (2026-10-04), MINOR: the alert GroupSyncDashboardReportScheduleLate (warning) and its
# `monitoring.prometheusRule.for.reportScheduleLate` (15m), rendered with the rules and reporting on; it reads
# `gsd_report_schedule_status{status="late"}`, the Reporting status page's own verdict; the README's alert table
# and the board's alert panel name it; appVersion moves to application 4.5.0 (below); #140, SPEC_F5. No RBAC change.
version: 0.68.0
```


### Block 16 — `charts/group-sync-dashboard/Chart.yaml`: application 4.5.0's history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# 4.4.0 (2026-10-04). Webhook delivery of scheduled reports: each finished run of a schedule's fan-out is POSTed as one CloudEvent to the URL in a mounted Secret, retried for 408, 429, 500, 502, 503, 504 and network errors, never printing the URL; a run not delivered fails the Job (#109). MINOR.
appVersion: "4.4.0"
```

```yaml
# 4.4.0 (2026-10-04). Webhook delivery of scheduled reports: each finished run of a schedule's fan-out is POSTed as one CloudEvent to the URL in a mounted Secret, retried for 408, 429, 500, 502, 503, 504 and network errors, never printing the URL; a run not delivered fails the Job (#109). MINOR.
# 4.5.0 (2026-10-04). A schedule that silently stops producing evidence raises an alert: the report service exports each schedule's state on the Reporting status page (ok, late, never, disabled) as gsd_report_schedule_status, computed by the page's own code (#140). MINOR.
appVersion: "4.5.0"
```


### Block 17 — `local-development/pyproject.toml`: application 4.5.0

<!-- block: local-development/pyproject.toml | edit -->

```toml
# are unaffected, byte-for-byte.
version = "4.4.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
```

```toml
# are unaffected, byte-for-byte.
version = "4.5.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
```


### Block 18 — `local-development/gsd/__init__.py`: application 4.5.0

<!-- block: local-development/gsd/__init__.py | edit -->

```python
# before that test existed nothing did.
__version__ = "4.4.0"
```

```python
# before that test existed nothing did.
__version__ = "4.5.0"
```


### Block 19 — `docs/CHANGELOG.md`: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

```markdown
## Unreleased

- **Webhook delivery of scheduled reports (#109, Epic F #386, `docs/specs/SPEC_F4_webhook_delivery.md`;
```

```markdown
## Unreleased

- **An alert when a report schedule silently stops producing evidence (#140, Epic F #386,
  `docs/specs/SPEC_F5_schedule_stale_alert.md`; application 4.5.0, chart 0.68.0).** The report service exports
  `gsd_report_schedule_status{schedule, status}`: for each configured schedule one series per state (`ok`, `late`,
  `never`, `disabled`), 1 for the state the Reporting status page shows and 0 for the others, computed by the page's
  own function. `GroupSyncDashboardReportScheduleLate` (warning, `for.reportScheduleLate`, 15m) fires per schedule
  while it reads `late`: its last expected fire is more than 30 minutes past and no run of it has succeeded since.
  `never` and `disabled` do not fire. The existing gauges, the page's states and grace, and the other rules are
  unchanged; no RBAC change.

- **Webhook delivery of scheduled reports (#109, Epic F #386, `docs/specs/SPEC_F4_webhook_delivery.md`;
```


### Block 20 — `docs/DESIGN_reporting_selectors_snapshots_and_windows.md`: §5 names the mechanism

<!-- block: docs/DESIGN_reporting_selectors_snapshots_and_windows.md | edit -->

```markdown
stop nightly evidence. A trigger-side pre-check is diagnostic only (same predicate); the server is the
```

```markdown
stop nightly evidence. (Built by #140, `docs/specs/SPEC_F5_schedule_stale_alert.md`: the report service exports
the status page's per-schedule verdict as `gsd_report_schedule_status{schedule, status}`, and
`GroupSyncDashboardReportScheduleLate` fires while a schedule reads `late`.) A trigger-side pre-check is diagnostic only (same predicate); the server is the
```
