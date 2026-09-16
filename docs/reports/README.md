# Reports

The report service renders **eleven standard reports** from a read-only copy of the dashboard's
data. Every document — HTML, PDF or JSON — carries the sha256 of its data, the snapshot it was built
from, and who generated it. A report is produced two ways: **on demand** from the **Reports** tab, or
**automatically on a schedule** (see [Scheduling](#scheduling)).

## The standard report names

These are the canonical names. A schedule's `report:` and the Reports-tab picker use them verbatim; a
finished run records the one it ran, and a scheduled run is tagged `generated_by = schedule:<name>`.

| Name | Report | What it shows |
|---|---|---|
| `namespace-access` | Namespace access report | Per namespace: every group binding classified with who it reaches, every direct user grant, findings first. |
| `access-matrix` | Access matrix | Every subject (group or direct user), the namespaces it is bound in and the role granted — the "who has access where" sheet, by role name. |
| `privileged-access` | Privileged access review | Every subject holding cluster-admin at any scope, or admin/edit cluster-wide, with the people behind each group. |
| `binding-findings` | RBAC binding findings | Dangling, unresolved and unmanaged group bindings and direct user grants; `system:*` virtual groups are omitted (a platform built-in, not a person's grant). |
| `groups` | Groups and membership changes | Every synced group: provider, member count, last sync, bindings, cliff silence; the empty and unattributed lists; joins and leaves in the window. |
| `users` | Users | Every User object (a login), its identity providers, group count and direct grants; manual accounts; synced members who have never logged in. |
| `login-activity` | Login activity | Attempts by outcome and provider, per-user successes and failures, and rejected attempts resolved against the login gate. |
| `dormant-access` | Dormant and unusable access | Members with access who have never logged in, members outside the login gate, gate members with no access, and — with login capture — nobody-in-N-days. |
| `groupsync-health` | GroupSync and policy-operator health | Every GroupSync CR with its computed state, schedule and last sync; reconcile errors (current vs stale); syncs in the window; NamespaceConfig/GroupConfig health. |
| `compliance-snapshot` | Compliance snapshot | One page of KPIs — groups, users, bindings, findings, privileged grants, dormant access, sync health — and the coverage statement that says what this evidence can attest. |
| `access-certification` | Access certification pack | Per group (with roster) and per directly-bound user: every binding held, with Approve / Revoke / Comment columns and a sign-off block for the named reviewer. |

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
      # clusters: omitted → every enabled cluster the deployment monitors (see Clusters below)
      params: {}                      # that report's own parameters (optional)
      formats: [html]                 # optional; see Formats below
    - name: nightly-dormant
      schedule: "0 3 * * *"
      report: dormant-access
      clusters: [crc-local]           # a subset, by name from the chart's top-level `clusters` list
      params: {dormant_days: 30}
    - name: weekly-access-cert
      schedule: "0 7 * * 1"
      report: access-certification
      clusters: [prod-east, prod-west]
      params: {campaign: "Weekly access review", reviewer: "Security Team", scope: all}
```

`schedules` is empty by default — nothing runs automatically until you add an entry.

### Clusters

A report runs against one cluster's data, but a schedule **never re-lists cluster names** — clusters are
defined once, in the chart's top-level `clusters` list. A schedule targets them by reference:

- **omit `clusters`** → the schedule runs for **every enabled cluster** the deployment monitors;
- **`clusters: [name, name]`** → just those (names drawn from the `clusters` list).

The chart renders **one CronJob per schedule** (not one per cluster). When it fires, the trigger enqueues
**one run per target cluster** — all enabled, or the named subset — which the report service's queue paces.
So five schedules are five CronJobs whether the deployment monitors one cluster or a hundred, and adding a
cluster is picked up automatically with no schedule edits. Each run is tagged `generated_by = schedule:<name>`
on its own cluster, retained per **(schedule, cluster)** so no single cluster's history crowds out another's.

> Scale ([#149](https://github.com/ephico2real2/group-sync-dashboard/issues/149)): the multi-cluster
> fan-out, per-(schedule, cluster) retention, and the throughput/failure-isolation behaviour above are
> being finalised. Today a schedule names a single `cluster`.

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

## Formats and retention

A report can be written as HTML, PDF and JSON; JSON is always written. On the Reports tab the operator
chooses HTML and/or PDF per run.

> **Planned ([#149](https://github.com/ephico2real2/group-sync-dashboard/issues/149)):** scheduled runs
> default to **HTML + JSON only** (no PDF — the HTML report has a print button, so a reviewer prints to
> PDF on demand), and retention becomes two-tier — **scheduled** runs kept 90 days or the newest 2 per
> schedule (whichever keeps more), **manual** runs expired quickly (3 days / newest 500) to keep the
> volume lean. Until then, all runs share the retention in the chart values.
