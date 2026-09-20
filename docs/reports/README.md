# Reports

The report service renders **eleven standard reports** from a read-only copy of the dashboard's
data. Every document — HTML, PDF or JSON — carries the sha256 of its data, the snapshot it was built
from, and who generated it. A report is produced two ways: **on demand** from the **Reports** tab, or
**automatically on a schedule** (see [Scheduling](#scheduling)).

## The standard report names

Each report carries **two names**: the **report name** (kebab-case) — used by a schedule's `report:`,
the Reports-tab picker, and the `generated_by = schedule:<name>` tag — and the **config key**
(camelCase) — used only in `reporting.reports.<key>.enabled` to turn the report on or off.

| Report name (`report:`) | Config key (`reporting.reports.<key>`) | Report | What it shows |
|---|---|---|---|
| `namespace-access` | `namespaceAccess` | Namespace access report | Per namespace: every group binding classified with who it reaches, every direct user grant, findings first. |
| `access-matrix` | `accessMatrix` | Access matrix | Every subject (group or direct user), the namespaces it is bound in and the role granted — the "who has access where" sheet, by role name. |
| `privileged-access` | `privilegedAccess` | Privileged access review | Every subject holding cluster-admin at any scope, or admin/edit cluster-wide, with the people behind each group. |
| `binding-findings` | `bindingFindings` | RBAC binding findings | Dangling, unresolved and unmanaged group bindings and direct user grants; `system:*` virtual groups are omitted (a platform built-in, not a person's grant). |
| `groups` | `groups` | Groups and membership changes | Every synced group: provider, member count, last sync, bindings, cliff silence; the empty and unattributed lists; joins and leaves in the window. |
| `users` | `users` | Users | Every User object (a login), its identity providers, group count and direct grants; manual accounts; synced members who have never logged in. |
| `login-activity` | `loginActivity` | Login activity | Attempts by outcome and provider, per-user successes and failures, and rejected attempts resolved against the login gate. |
| `dormant-access` | `dormantAccess` | Dormant and unusable access | Members with access who have never logged in, members outside the login gate, gate members with no access, and — with login capture — nobody-in-N-days. |
| `groupsync-health` | `groupsyncHealth` | GroupSync and policy-operator health | Every GroupSync CR with its computed state, schedule and last sync; reconcile errors (current vs stale); syncs in the window; NamespaceConfig/GroupConfig health. |
| `compliance-snapshot` | `complianceSnapshot` | Compliance snapshot | One page of KPIs — groups, users, bindings, findings, privileged grants, dormant access, sync health — and the coverage statement that says what this evidence can attest. |
| `access-certification` | `accessCertification` | Access certification pack | Per group (with roster) and per directly-bound user: every binding held, with Approve / Revoke / Comment columns and a sign-off block for the named reviewer. |

### Enabling a report

Ten reports are `enabled: true` by default. **`loginActivity` is special** — its default is `enabled: ""`,
a sentinel meaning *follow `loginCapture`*: it is on only when login capture is on, so a login report can
never exist with no login data. A report referenced by a schedule must be enabled.

```yaml
reporting:
  reports:
    loginActivity:      { enabled: true }   # explicit on — but the report is empty unless
                                            # loginCapture.enabled (the poller feature) is also on
    complianceSnapshot: { enabled: true }
```

Report enablement (the report service) and data *capture* (the poller — `loginCapture`, `rbac.identities`,
`rbac.namespaces`) are separate knobs: enabling a report does not turn on the data it needs, and a report
whose underlying capture is off renders empty.

## Report parameters

Each report takes its own inputs. A schedule supplies them under `params:`; the Reports tab renders one
control per parameter. Anything omitted uses the report's default.

| Report | Parameters (type) |
|---|---|
| `namespace-access` | `selectors` (selector-map), `mnemonics` (csv), `namespaces` (namespaces), `include_members` (bool) |
| `access-matrix` | `subject_kind` (enum), `namespace_prefix` (str) |
| `privileged-access` | `include_members` (bool), `roles` (csv) |
| `groups` | `window_days` (int), `include_members` (bool) |
| `users` | `providers` (csv) |
| `login-activity` | `window_days` (int), `user` (str) |
| `dormant-access` | `dormant_days` (int) |
| `groupsync-health` | `window_days` (int) |
| `access-certification` | `campaign` (str), `due` (date), `reviewer` (str), `scope` (enum), `include_members` (bool), `group_prefix` (str) |
| `binding-findings`, `compliance-snapshot` | none (cluster + format only) |

## Scheduling

Automated runs are configured under `reporting.schedules` in the chart's `charts/group-sync-dashboard/values.yaml`.
**Each entry is one report on its own cron** — so every report can have its own cadence, and the same
report can appear more than once with different parameters. The chart renders one CronJob per entry; the
CronJob POSTs a run with the service token, gated by the [run window](../reference-architecture.md), and
the artefact lands in the store like any other.

```yaml
reporting:
  schedules:
    - name: biweekly-compliance       # schedule name → CronJob name + generated_by=schedule:<name>
      schedule: "0 6 1,16 * *"        # standard 5-field cron — this is the cadence
      report: compliance-snapshot     # one of the standard report names above
      # cluster: omitted → every enabled cluster in the report service's snapshot (see Clusters below)
      params: {}                      # that report's own parameters (optional)
      formats: [html]                 # optional; the scheduled default is html+json (see Formats below)
    - name: nightly-dormant
      schedule: "0 3 * * *"
      report: dormant-access
      cluster: crc-local              # pins one cluster, by the id the dashboard names it
      params: {dormant_days: 30}
    - name: weekly-access-cert
      schedule: "0 7 * * 1"
      report: access-certification
      enabled: false                  # paused: the CronJob stays, suspended, until this is removed or true
      params: {campaign: "Weekly access review", reviewer: "Security Team", scope: all}
```

`schedules` is empty by default — nothing runs automatically until you add an entry.

### Clusters

A report runs against one cluster's data, but a schedule is **cluster-agnostic** — clusters are defined
once, in the chart's top-level `clusters` list, and the report service reads them from its snapshot:

- **omit `cluster`** → the schedule runs for **every enabled cluster** in the snapshot, one run each;
- **`cluster: name`** → that one cluster only (the id the dashboard names it).

The chart renders **one CronJob per schedule** (not one per cluster). When it fires, the service queues the
fan-out as **one queue slot** — all of its clusters or none — and the Job waits for every run, failing if
any did. So five schedules are five CronJobs whether the deployment monitors one cluster or a hundred, and
adding a cluster is picked up automatically with no schedule edits. Each run is tagged
`generated_by = schedule:<name>` on its own cluster, retained per **(schedule, cluster)** so no single
cluster's history crowds out another's. `enabled: false` keeps the CronJob and suspends it — its
definition, history and audit trail stay; remove the entry to retire it.

### Cadence

`schedule:` is a standard 5-field cron expression (`minute hour day-of-month month day-of-week`), fired in
the run window's time zone.

| Cadence | cron |
|---|---|
| Every 15 days | `0 6 1,16 * *` (1st & 16th, 06:00) |
| Weekly (Monday) | `0 6 * * 1` |
| Monthly (1st) | `0 6 1 * *` |
| Daily | `0 3 * * *` |

### Naming

A schedule `name` becomes the CronJob's name and the `schedule:<name>` origin tag, so it must be a
DNS-1123 label. The convention is **`<cadence>-<report>`** — `biweekly-compliance`, `nightly-dormant`,
`weekly-access-cert` — so the cadence and the report are both legible in the status page and the run
history.

## The Reporting status page

`#page=reporting`, linked from the Reports catalogue ("Reporting status, schedules and history →"), is
the report service's own account of itself — read from the service, no personnel data beyond the
`generated_by` a run already carries:

- **Reporting status** — the service (version, PDF variant, enabled reports, what a scheduled run
  stores), the **run window** (open or closed now, its hours, zone and days, when it next opens or
  closes), both **retention** tiers, and what is **in flight** (running, queued, how many automated
  requests the window refused since the service started).
- **Scheduled reports** — one row per `reporting.schedules[]` entry: the cadence in words with the
  expression beneath (read in the CronJob's zone — the run window's when one is configured), the
  effective retention (a per-schedule override is marked), **On** or **Paused**, the last success, the
  next fire, and a state: `ok` — the last expected fire has a success after it, or is less than 30
  minutes old (the grace for the queue and the render); `late` — the last expected fire is more than
  30 minutes behind and nothing has succeeded since it (a fire the CronJob missed reads the same way);
  `never` — no success recorded yet; `disabled` — paused. Every instant on the page is UTC, as the
  service stamps it.
- **Report history** — every run, newest first, with Report / Origin / Status / Cluster filters that
  run on the service across the whole history, paged, with the artefact downloads.

Next and previous fires are computed from the cron expression (a spring-forward gap fires nothing, a
fall-back overlap fires twice, as Kubernetes' cron does), not read from kube-state-metrics — the
values the chart renders already determine them, and a Prometheus read would need access and RBAC the
service does not have.

## Formats and retention

A report can be written as HTML, PDF and JSON; JSON is always written. On the Reports tab the operator
chooses HTML and/or PDF per run.

Formats default by **origin** (`reporting.formats`): a scheduled run stores **HTML + JSON** (no PDF — the
HTML report has a print button, so a reviewer prints to PDF on demand), a manual run **HTML + JSON + PDF**.
A schedule's `formats:` overrides its default; a defaulted PDF is dropped where PDF is off, an explicit one
refused.

Retention is **two-tier** ([#149](https://github.com/ephico2real2/group-sync-dashboard/issues/149) R2),
so a burst of on-demand runs can never evict a scheduled report. A **scheduled** run is kept while
within the newest `keepPerSchedule` (default 2) per (schedule, cluster) **or** younger than `days`
(default 90), and is exempt from the manual run-count cap. A **manual** run is kept `days` (default 3)
and at most `maxRuns` (default 500), whichever prunes first. See `reporting.retention` in the chart
values; `keepPerSchedule` is a floor, so `scheduled.days: 0` disables scheduled deletion altogether.
