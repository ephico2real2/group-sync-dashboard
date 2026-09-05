# SPEC B3 — Grafana dashboard shipped with the chart

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | B — observability |
| Release | R2 — Alerts, retention, Grafana |
| Version on release | chart 0.13.0 (chart only) |
| Issue | [#60](https://github.com/ephico2real2/group-sync-dashboard/issues/60) |
| Status | released |
| Source | design agent output `abe89ca84ad184702`; two messages; the first ended inside a ```python fence with a partial `def test_env_overrides_the_file` and the second re-emitted that test from its first line under a new fence opener, so the partial tail and the duplicate opener were dropped and the code continues inside the original fence |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Lands third in R2 as a chart-only release: chart 0.13.0; the body's shared version pair is superseded. The operator has no Grafana yet: validation installs grafana-operator v5 in a test namespace on CRC, imports the ConfigMap through `GrafanaDashboard.spec.configMapRef`, and the README carries both the sidecar-label and the operator-CR recipes.
- The `## Unreleased` heading already exists (A1).

- Deviations recorded at implementation (PR for #60): (1) the body's values edit re-adds `for.groupCountCliff: 15m`, already placed by B4, so only the `grafanaDashboard` block is inserted; (2) the never-written design doc is cited as this spec; (3) `docs/reference-architecture.md` has no paragraph between the topology diagram and the next heading, so the sentence is its own paragraph there; (4) `environments/crc.yaml` enabled the dashboard on the reference cluster for this validation (the override was removed with chart 0.14.0, operator decision 2026-09-05: nothing on CRC reads the board) (no Prometheus Operator there, so the ServiceMonitor it would follow stays off) and the environments README table lists it — its guard now renders an empty-string default as `""`, the way values.yaml writes it. Validated live: grafana-operator v5.24 installed from Community Operators into `grafana-test` (all namespaces), a `Grafana` labelled `dashboards: grafana`, a `GrafanaDashboard` in the dashboard's namespace with `allowCrossNamespaceImport: true` and `configMapRef` to the chart's ConfigMap: status `DashboardSynchronized: Dashboard was successfully applied to 1 instances`, uid `gsd-group-sync-dashboard`; screenshot `docs/screenshots/06-grafana-dashboard-crc.png` — every panel renders, all "No data" because the cluster has no Prometheus, and the datasource input `${DS_PROMETHEUS}` shows unresolved under provisioning (the review's C5).

- Found in review (PR #74, Cursor Grok 4.6): (1) an extra label named `grafana_dashboard` overwrote the convention value (last key wins, measured: the rendered label became `0`), so the sidecar would silently ignore the ConfigMap — the chart refuses a colliding key. (2) The body's README offered "set a folder and label your sidecar recognises" as a fix for sidecar namespace scope, which the body's own risk section says cannot work, and its operator recipe lacked `allowCrossNamespaceImport: true`, which the live import on CRC needed; the subsection now lists the three real remedies with kube-prometheus-stack's nesting, explains both datasource paths, and carries the validated recipe. (3) Three stat panels (Cluster up, WAL mode, Leader replicas) painted "No data" alarm-red, as the CRC screenshot shows; their base threshold step is neutral now and Leader replicas alarms on 0 and on 2+, not on absence. All three held by tests.

- Found in review (PR #74, Codex gpt-5.6-sol xhigh): (1) `--set monitoring.grafanaDashboard=null` crashed the render with `nil pointer evaluating interface {}.labels`; the template reads the map nil-safely now, tested. (2) The body's parenthetical "`{{- end }}` would eat the block scalar's final newline" is false — measured, both forms render byte-identical; the template's comment says so and keeps the untrimmed form for readable YAML. (3) The README's sidecar prose said the sidecar watches only its own namespace; current kube-prometheus-stack defaults `searchNamespace` to `ALL` while older releases and the Grafana chart alone do not, and `folderAnnotation`/`foldersFromFilesStructure` are configuration, not defaults — the README says "check your values" and names both. (4) Accepted in scoped form: every panel expression is parsed by `promtool check rules`; CI installs promtool and the test must run there, locally it skips. Codex's C3 label-collision finding matched Cursor's and was already applied.

- Found in the second review pass (PR #74, Cursor Grok 4.6, on the fixed head): (1) six more stat and bar-gauge panels painted "No data" healthy GREEN (Last poll age, Poll duration, Empty groups, Unattributed groups, Backup age, Login capture read age, Alerts by kind) — the same class as the red ones with the other colour; every coloured panel's base step is neutral now and a real zero earns green from the next step, held by one general test. (2) `--set monitoring=null` — rejected as unreachable: `templates/monitoring.yaml` dereferences the `monitoring` map itself, so a null map fails the render there before the dashboard helper runs; the helper's nil-safe read of that map is kept as harmless, without a test.

- Second review pass (PR #74, Codex gpt-5.6-sol xhigh, on the fixed head): fifteen of seventeen items confirmed with renders and probes; the green-base finding matched Cursor's and was already applied; new: the operator recipe bound no datasource, so a Grafana with two Prometheus datasources would pick the first option for `DS_PROMETHEUS` — the README recipe carries grafana-operator's `datasources` input mapping, held by the README test. Environment-limited (no promtool, no Grafana locally): the PromQL parse runs in CI, the schema 39 import is within Grafana 12's migration range.

## Batch preamble (verbatim from the design)

I have read everything the design needs. Here is the complete design document.

---

# DESIGN — B3 Grafana dashboard shipped with the chart, B4 group-count cliff alert with read-only silencing

**Status: specification.** Written from the code as it is on 2026-09-04 (application 0.11.0, chart 0.10.0). Every claim below is grounded in a file that was read; citations are `path#anchor`. Save this file as `docs/DESIGN_grafana_dashboard_and_group_count_cliff.md`.

## 0. Ground truth the design rests on

| Fact | Where |
|---|---|
| Metrics are collected from the store at scrape time by one collector; series are per cluster and per CR only, never per group or user, because `/metrics` is unauthenticated | `gsd/metrics.py` module docstring (`CARDINALITY IS DELIBERATELY BOUNDED`), `gsd/metrics.py#DashboardCollector` |
| The emittable alert-kind vocabulary is `gsd/metrics.py#ALERT_KINDS`; `tests/test_metrics.py#test_every_alert_kind_a_rule_references_is_one_the_collector_can_emit` holds it to every `kind="..."` literal in `state.py`, and every `gsd_alerts_total{kind="..."}` matcher in the rendered PrometheusRule to it | `gsd/metrics.py#ALERT_KINDS` |
| Every metric a rule references must be DECLARED (HELP line) by a bare `DashboardCollector(store, grace, None)` | `tests/test_metrics.py#test_every_metric_an_alert_references_is_declared_by_the_collector` |
| `gsd_alerts_total` promises parity with `/api/alerts` at the wide tier: both call `gsd/state.py#compute_alerts` with the same store reads; a degraded cluster reports one critical alert with its poll outcome as the kind and none of the computed kinds | `gsd/metrics.py#Kept in step with the /api/alerts call site`, `gsd/api.py#list_alerts`, `docs/DESIGN_metrics_refresh.md` §5.2 |
| Alerts are DERIVED at request time, never stored | `docs/reference-architecture.md#Derived, never stored` |
| `Alert` is a frozen dataclass `(cluster, kind, subject, detail, severity="warning")` with `as_dict()` | `gsd/state.py#Alert` |
| `compute_alerts` docstring still says the group-count cliff is EXCLUDED ("needs a tuned floor as well as a ratio, PLAN §8"); README says the same under `Not built yet` | `gsd/state.py#compute_alerts`, `README.md#Not built yet` |
| The self tier receives only the kinds in `SELF_ALERT_DETAILS`; a kind that names groups from the self-scoped Groups tab (`empty_group`, `unattributed`, `stale_group`) is withheld; a new kind defaults to withheld | `gsd/api.py#SELF_ALERT_DETAILS`, `gsd/api.py#_alerts_for_self` |
| `group_state` is REPLACED wholesale each poll (`DELETE` then `INSERT`) and holds `member_count` for the current poll only — no history | `gsd/store.py#Store.replace_group_state` |
| `membership_event` is append-only, one row per `(group, user, added|removed)` with our `observed_at`; a group that disappears upstream has every member recorded as `removed`; it has NO retention by design | `gsd/store.py#Store.sync_members`, `gsd/metrics.py#gsd_retention_rows_deleted_total` HELP ("membership_event and sync_event deliberately have none") |
| The poller builds group rows from `GroupView` (`name, member_count, sync_provider, group_synced_at, ldap_uid, members`); `_group_view` reads exactly two annotations, `SYNC_TIME_ANNOTATION` and `LDAP_UID_ANNOTATION` | `gsd/kube.py#GroupView`, `gsd/kube.py#_group_view`, `gsd/poller.py#poll_once` |
| The read-only precedent for something an administrator sets on a cluster object: `UNMANAGED_EXCEPTION_ANNOTATION` on bindings is read in `kube.py` and carried as the `exception` column; the dashboard writes nothing back | `gsd/kube.py#UNMANAGED_LABEL`, `gsd/audit.py#StampPlan` ("The discovery IS the deliverable — there is no write") |
| Schema changes go through `_MIGRATIONS` keyed by `PRAGMA user_version`; the latest is 7; a fresh DB gets `SCHEMA` and then replays every step, so `ALTER TABLE ADD COLUMN` must tolerate `duplicate column name` | `gsd/store.py#_MIGRATIONS`, `gsd/store.py#_migrate`, `tests/test_migrations.py#test_a_fresh_database_lands_on_the_latest_migration` |
| Settings come from the ConfigMap's `clusters.yaml` via `load_settings`, env overriding through `_bool_setting` / `_num_setting`; a `ConfigError` refuses to start | `gsd/config.py#load_settings`, `gsd/config.py#_bool_setting`, `gsd/config.py#_num_setting` |
| The chart's monitoring objects are gated by `monitoring.serviceMonitor.enabled` / `monitoring.prometheusRule.enabled`, both default false because the CRDs may be absent; under Argo they carry `SkipDryRunOnMissingResource=true` | `charts/group-sync-dashboard/templates/monitoring.yaml`, `charts/group-sync-dashboard/values.yaml#monitoring:` |
| Alert thresholds live in values: `overdueSeconds 7200`, `notPollingSeconds 600`, `walMiB 256`, `captureStalledSeconds 1800`, `backupStaleSeconds 43200` | `charts/group-sync-dashboard/values.yaml#prometheusRule:` |
| Chart tests shell out to `helm template` via a `render(**values)` helper and skip when helm is absent | `tests/test_chart_strategy.py#render` |
| The Overview renders alerts in one function; the UI test asserts every `.alert-row .badge` label is `critical` or `warning` | `gsd/static/index.html#function alertsCard`, `tests/test_ui.py#test_alerts_use_severity_words_not_cr_state_words` |
| Chart changes bump `Chart.yaml` `version` with a `# CHART x.y.z (date), KIND: reason` line above it; `appVersion` must equal `pyproject.toml` and `gsd/__init__.py` | `charts/group-sync-dashboard/Chart.yaml`, `tests/test_chart_versions.py` |
| `docs/CHANGELOG.md` has no `## Unreleased` heading today — one is added | `docs/CHANGELOG.md` |
| Doc citations must resolve (`path#anchor`; `.json` is not a citable extension, so the dashboard file is referred to by plain path) | `tests/test_docs_citations.py#CITATION` |

---


## Design (verbatim)

# FEATURE B3 — Grafana dashboard shipped with the chart

## B3.1 Goal

Ship one Grafana dashboard that renders every family `gsd/metrics.py#DashboardCollector` exports, with thresholds equal to the shipped PrometheusRule's, so an operator who turns monitoring on sees the picture without hand-building panels — and so the dashboard can never reference a metric the collector does not declare (a test holds it, the same way the rules are held).

## B3.2 Switch, default, why

`monitoring.grafanaDashboard.enabled: ""` — a tri-state. `""` means **follow `monitoring.serviceMonitor.enabled`**; `true`/`false` are explicit.

Why derive rather than a fixed default:

- **ON unconditionally** fails the house rule's "no side effect" test only weakly (a 40 KB ConfigMap is free and a core resource that can never fail an install), but it is pointless on every install that has no scrape: a dashboard over metrics nobody collects is a red wall of "No data". It would also ship the `grafana_dashboard: "1"` label into namespaces where a sidecar might import it as an empty board.
- **OFF unconditionally** breaks "one switch turns monitoring on": an operator enabling the ServiceMonitor gets rules but no board, and discovers the board exists from the README.
- **Following the ServiceMonitor** makes the board appear exactly when its data starts to exist, needs no new value on the happy path, and stays overridable both ways: `enabled=true` with the ServiceMonitor off is legitimate (scraping via a plain `scrape_config`), `enabled=false` with it on is legitimate (no Grafana).

Modelled as derive, not refuse, because neither combination is unsafe.

**ConfigMap only; no `GrafanaDashboard` CR.** Reasons, in order of weight:

1. A ConfigMap is a core resource: it cannot fail an install or an Argo dry-run, which is the exact failure `monitoring.yaml` had to work around for the CRD-backed objects. Adding a CR would re-import that failure mode into a feature that is supposed to be free.
2. The Grafana sidecar convention (`grafana_dashboard: "1"` label, optional `grafana_folder` annotation) is what kube-prometheus-stack, the community OpenShift Grafana deployments and grafana-operator v5's sidecar-compatible mode all read.
3. grafana-operator v5 consumes a ConfigMap directly through `GrafanaDashboard.spec.configMapRef`, so an operator user needs a 10-line CR that references THIS ConfigMap — the README gives it. Shipping the CR ourselves would force a choice between two incompatible API versions in the wild (`integreatly.org/v1alpha1` versus `grafana.integreatly.org/v1beta1`) and require an `instanceSelector` matching labels on a Grafana instance the chart cannot know.

So `monitoring.grafanaDashboard.operatorCR` is deliberately NOT a value. If demand appears it is additive later.

## B3.3 Interactions

| With | Behaviour |
|---|---|
| `monitoring.serviceMonitor.enabled` | derived default, above |
| `argocd.enabled` | none needed — ConfigMap is core; no `SkipDryRunOnMissingResource` |
| `monitoring.prometheusRule.*` thresholds | the JSON hard-codes the shipped DEFAULTS (600, 7200, 256 MiB, 1800, 43200). A test holds the JSON to `values.yaml`'s defaults so they cannot drift; an operator who tunes a threshold edits the panel in Grafana (the board is `editable: true`) — a Helm-templated JSON would break the byte-identity guarantee and the `{{` escaping story for no gain |
| Multi-replica (`replicaCount > 1`) | every gauge is aggregated `max by (...)`, every counter `sum by (...)`, per the `gsd_leader` HELP text in `gsd/metrics.py#DashboardCollector._gather` |

## B3.4 Helm templating and the `{{` question

The JSON lives at `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json` and is loaded with `.Files.Get`. Helm's engine only parses files under `templates/` as templates; `.Files.Get` returns the file's bytes as a plain string and never runs them through the template engine. Therefore the Grafana template strings the JSON contains — `$cluster`, `${DS_PROMETHEUS}`, `$__rate_interval` — and any literal `{{ }}` (Grafana legend templating, e.g. `{{cluster}}`) are safe. The only place `{{` would be interpreted is inside `templates/*.yaml`, which is why the JSON is NOT inlined there.

Embedding: a YAML literal block scalar (`|`) with `indent 4`. The file ends with exactly one newline; `indent` turns that trailing newline into a final whitespace-only line, which YAML clip-chomping folds away, so the decoded `data` value equals the file byte-for-byte. `tests/test_chart_grafana_dashboard.py#test_rendered_configmap_json_is_byte_identical_to_the_file` verifies it against `helm template` (Helm v3.14.0 is available locally). If a future Helm changed block handling, the fallback is `| quote` (Go `%q` → YAML double-quoted, also lossless for ASCII JSON), and the same test would catch the need.

`helm package` includes every file in the chart directory except `templates/` internals and `.helmignore` matches; there is no `.helmignore`, so `dashboards/` ships.

## B3.5 Files — complete code

### New: `charts/group-sync-dashboard/templates/grafana-dashboard.yaml`

```yaml
{{- /*
Grafana dashboard, delivered the way Grafana sidecars expect it: a ConfigMap carrying the
`grafana_dashboard: "1"` label (kube-prometheus-stack, the community OpenShift Grafana
deployments, and grafana-operator v5's sidecar mode all watch for it). grafana-operator v5
can also point a GrafanaDashboard CR at this ConfigMap by name (spec.configMapRef) — the
chart README shows the ten-line CR. No CR is shipped here on purpose: a ConfigMap is a core
resource that cannot fail an install or an Argo dry-run, while the CR has two incompatible
API versions in the wild and needs an instanceSelector the chart cannot know.

THE JSON IS A PLAIN FILE, loaded with .Files.Get, and that placement is load-bearing. Helm
runs the template engine over templates/ only; a file read with .Files.Get is returned
verbatim, so the Grafana templating the JSON carries — $cluster, ${DS_PROMETHEUS},
$__rate_interval, and {{cluster}} legend formats — is never mistaken for a Helm action. The
same JSON inlined in this file would fail the render on its first `{{`.

Embedded as a literal block scalar. `indent` turns the file's final newline into a
whitespace-only last line, which YAML's clip chomping folds away, so the ConfigMap value is
byte-identical to the file — tests/test_chart_grafana_dashboard.py holds that against a
real `helm template`.

DEFAULT FOLLOWS THE SERVICEMONITOR (values.yaml, monitoring.grafanaDashboard.enabled: "").
A board over metrics nobody scrapes is a wall of "No data", and "one switch turns
monitoring on" is the contract the README documents.
*/ -}}
{{- if eq (include "gsd.grafanaDashboardEnabled" .) "true" }}
{{- $json := .Files.Get "dashboards/group-sync-dashboard.json" }}
{{- if not $json }}
{{- fail "dashboards/group-sync-dashboard.json is missing from the chart package; monitoring.grafanaDashboard cannot render" }}
{{- end }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "gsd.fullname" . }}-grafana-dashboard
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    grafana_dashboard: "1"
    {{- with .Values.monitoring.grafanaDashboard.labels }}{{- toYaml . | nindent 4 }}{{- end }}
  {{- if or .Values.monitoring.grafanaDashboard.folder .Values.monitoring.grafanaDashboard.annotations }}
  annotations:
    {{- with .Values.monitoring.grafanaDashboard.folder }}
    # The sidecar's folderAnnotation default. A Grafana without that setting ignores it.
    grafana_folder: {{ . | quote }}
    {{- end }}
    {{- with .Values.monitoring.grafanaDashboard.annotations }}{{- toYaml . | nindent 4 }}{{- end }}
  {{- end }}
data:
  group-sync-dashboard.json: |
{{ $json | indent 4 }}
{{ end }}
```

(The closing `{{ end }}` deliberately has no left-trim dash: `{{- end }}` would eat the block scalar's final newline and break byte-identity.)

### Edit: `charts/group-sync-dashboard/templates/_helpers.tpl`

Append after the `gsd.logLevel` define (end of file):

```
{{/*
monitoring.grafanaDashboard.enabled is a tri-state: "" follows monitoring.serviceMonitor.enabled,
true/false are explicit. Anything else refuses the render — a misspelt "ture" must not
silently become "off". Returns the string "true" or "false".
*/}}
{{- define "gsd.grafanaDashboardEnabled" -}}
{{- $raw := ((.Values.monitoring | default dict).grafanaDashboard | default dict).enabled -}}
{{- if or (kindIs "invalid" $raw) (eq (toString $raw) "") -}}
{{- toString .Values.monitoring.serviceMonitor.enabled -}}
{{- else if eq (toString $raw) "true" -}}
true
{{- else if eq (toString $raw) "false" -}}
false
{{- else -}}
{{- fail (printf "monitoring.grafanaDashboard.enabled must be true, false or \"\" (follow the ServiceMonitor); got %q" (toString $raw)) -}}
{{- end -}}
{{- end -}}
```

### Edit: `charts/group-sync-dashboard/values.yaml`

Old (end of the `monitoring:` block; the last lines of the file's `prometheusRule.for` map):

```yaml
      # Long: this is a migration backlog, not an incident. It should be visible and
      # tracked, never paging anyone at 3am.
      directUserGrants: 1h
```

New:

```yaml
      # Long: this is a migration backlog, not an incident. It should be visible and
      # tracked, never paging anyone at 3am.
      directUserGrants: 1h
      # The cliff is computed over a window of config.alerts.groupCountCliff.windowHours, so
      # the condition itself already persists; this only needs to outlast a scrape gap.
      groupCountCliff: 15m

  # A Grafana dashboard over every family /metrics exports, delivered as a ConfigMap with the
  # `grafana_dashboard: "1"` label the Grafana sidecar watches (kube-prometheus-stack, the
  # community OpenShift Grafana deployments, grafana-operator v5 in sidecar mode). A core
  # resource: it needs no CRD and cannot fail an install, unlike the two objects above.
  #
  # DEFAULT: "" — FOLLOW monitoring.serviceMonitor.enabled. The board is only useful once the
  # scrape exists, and one switch should turn monitoring on. Set true to ship it with the
  # ServiceMonitor off (a hand-written scrape_config), false to withhold it with the
  # ServiceMonitor on (no Grafana). Anything other than true / false / "" refuses to render.
  #
  # Thresholds in the panels equal the prometheusRule defaults above (600, 7200, 256 MiB,
  # 1800, 43200) and a test holds them together. The board is editable in Grafana; the JSON
  # is deliberately not templated, so it renders byte-identical to
  # dashboards/group-sync-dashboard.json.
  #
  # NOT SHIPPED: a GrafanaDashboard CR. grafana-operator v5 reads this ConfigMap through
  # spec.configMapRef — the chart README carries the CR. Shipping one would pick between two
  # incompatible CR API versions and need an instanceSelector the chart cannot know.
  grafanaDashboard:
    enabled: ""
    # Extra metadata labels, e.g. a sidecar configured with a non-default label.
    labels: {}
    # Extra annotations. `folder` below is the common one and has its own key.
    annotations: {}
    # Grafana folder, written as the `grafana_folder` annotation the sidecar's
    # folderAnnotation setting reads. Empty writes no annotation.
    folder: ""
```

(The `groupCountCliff: 15m` line belongs to B4 and is placed here because both edits touch the same block; see B4.)

### New: `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json`

Every `expr` uses only names registered in `gsd/metrics.py`: `gsd_cluster_up`, `gsd_cluster_last_poll_timestamp_seconds`, `gsd_cluster_poll_duration_seconds`, `gsd_groups_total`, `gsd_groups_empty_total`, `gsd_groups_unattributed_total`, `gsd_bindings_total`, `gsd_groupsync_state`, `gsd_groupsync_last_sync_timestamp_seconds`, `gsd_groupsync_groups_total`, `gsd_groupsync_reconcile_error_current`, `gsd_alerts_total`, `gsd_sqlite_wal_bytes`, `gsd_sqlite_checkpoint_busy_total`, `gsd_sqlite_wal_enabled`, `gsd_backup_last_success_timestamp_seconds`, `gsd_backup_failures_total`, `gsd_retention_rows_deleted_total`, `gsd_visibility_decisions_total`, `gsd_visibility_tier_checks_total`, `gsd_visibility_admin_refusals_total`, `gsd_login_capture_enabled`, `gsd_login_capture_last_read_timestamp_seconds`, `gsd_leader`, `gsd_build_info`.

```json
{
  "__inputs": [
    {
      "name": "DS_PROMETHEUS",
      "label": "Prometheus",
      "description": "",
      "type": "datasource",
      "pluginId": "prometheus",
      "pluginName": "Prometheus"
    }
  ],
  "__requires": [
    { "type": "grafana", "id": "grafana", "name": "Grafana", "version": "10.4.0" },
    { "type": "datasource", "id": "prometheus", "name": "Prometheus", "version": "1.0.0" },
    { "type": "panel", "id": "stat", "name": "Stat", "version": "" },
    { "type": "panel", "id": "timeseries", "name": "Time series", "version": "" },
    { "type": "panel", "id": "table", "name": "Table", "version": "" },
    { "type": "panel", "id": "bargauge", "name": "Bar gauge", "version": "" },
    { "type": "panel", "id": "text", "name": "Text", "version": "" }
  ],
  "annotations": {
    "list": [
      {
        "builtIn": 1,
        "datasource": { "type": "grafana", "uid": "-- Grafana --" },
        "enable": true,
        "hide": true,
        "iconColor": "rgba(0, 211, 255, 1)",
        "name": "Annotations & Alerts",
        "type": "dashboard"
      }
    ]
  },
  "description": "OCP Access Tracking Dashboard (group-sync-dashboard): every family /metrics exports. Gauges are max()ed and counters sum()ed across replicas; per-cluster and per-CR only, never per group or user.",
  "editable": true,
  "fiscalYearStartMonth": 0,
  "graphTooltip": 1,
  "id": null,
  "links": [],
  "liveNow": false,
  "panels": [
    {
      "id": 1,
      "type": "stat",
      "title": "Cluster up",
      "description": "gsd_cluster_up: 1 if the last poll succeeded. A never-polled cluster is 0 and has no last-poll series.",
      "gridPos": { "h": 4, "w": 4, "x": 0, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "max by (cluster) (gsd_cluster_up{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "none",
          "mappings": [
            { "type": "value", "options": { "0": { "text": "DOWN", "color": "red", "index": 0 }, "1": { "text": "UP", "color": "green", "index": 1 } } }
          ],
          "thresholds": { "mode": "absolute", "steps": [ { "color": "red", "value": null }, { "color": "green", "value": 1 } ] }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "background", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 2,
      "type": "stat",
      "title": "Last poll age",
      "description": "time() - gsd_cluster_last_poll_timestamp_seconds. Red at monitoring.prometheusRule.notPollingSeconds (600) — GroupSyncDashboardNotPolling.",
      "gridPos": { "h": 4, "w": 4, "x": 4, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "time() - max by (cluster) (gsd_cluster_last_poll_timestamp_seconds{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "decimals": 0,
          "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 300 }, { "color": "red", "value": 600 } ] }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 3,
      "type": "stat",
      "title": "Poll duration",
      "description": "gsd_cluster_poll_duration_seconds, wall time of the most recent poll (leader only). Compare against config.pollIntervalSeconds and requestTimeoutSeconds.",
      "gridPos": { "h": 4, "w": 4, "x": 8, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "max by (cluster) (gsd_cluster_poll_duration_seconds{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "decimals": 1,
          "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 15 }, { "color": "red", "value": 30 } ] }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "area", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 4,
      "type": "stat",
      "title": "Groups",
      "description": "gsd_groups_total: Group objects observed on the cluster.",
      "gridPos": { "h": 4, "w": 4, "x": 12, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "max by (cluster) (gsd_groups_total{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "thresholds": { "mode": "absolute", "steps": [ { "color": "blue", "value": null } ] } }, "overrides": [] },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "none", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 5,
      "type": "stat",
      "title": "Empty groups",
      "description": "gsd_groups_empty_total: operator-managed groups with zero members (alert kind empty_group).",
      "gridPos": { "h": 4, "w": 4, "x": 16, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "max by (cluster) (gsd_groups_empty_total{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 1 } ] } }, "overrides": [] },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 6,
      "type": "stat",
      "title": "Unattributed groups",
      "description": "gsd_groups_unattributed_total: groups with no sync-provider label, so managed by no GroupSync CR (alert kind unattributed).",
      "gridPos": { "h": 4, "w": 4, "x": 20, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
          "expr": "max by (cluster) (gsd_groups_unattributed_total{cluster=~\"$cluster\"})",
          "legendFormat": "{{cluster}}",
          "instant": true
        }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 1 } ] } }, "overrides": [] },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    },
    {
      "id": 7,
      "type": "timeseries",
      "title": "Groups over time",
      "description": "Total, empty and unattributed. A step down in total alongside a step up in dangling bindings is a group deletion.",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 4 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster) (gsd_groups_total{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} total" },
        { "refId": "B", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster) (gsd_groups_empty_total{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} empty" },
        { "refId": "C", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster) (gsd_groups_unattributed_total{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} unattributed" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "line", "lineInterpolation": "stepAfter", "fillOpacity": 5, "showPoints": "never" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "none" } }
    },
    {
      "id": 8,
      "type": "timeseries",
      "title": "Bindings by finding",
      "description": "gsd_bindings_total by finding. dangling means the binding grants nobody — DanglingRoleBinding fires on it.",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 4 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster, finding) (gsd_bindings_total{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} {{finding}}" }
      ],
      "fieldConfig": {
        "defaults": { "unit": "none", "custom": { "drawStyle": "line", "lineInterpolation": "stepAfter", "fillOpacity": 10, "showPoints": "never", "stacking": { "mode": "normal", "group": "A" } } },
        "overrides": [
          { "matcher": { "id": "byRegexp", "options": ".*dangling" }, "properties": [ { "id": "color", "value": { "mode": "fixed", "fixedColor": "red" } } ] }
        ]
      },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "none" } }
    },
    {
      "id": 9,
      "type": "timeseries",
      "title": "GroupSync last-sync age per CR",
      "description": "time() - gsd_groupsync_last_sync_timestamp_seconds. Red line at monitoring.prometheusRule.overdueSeconds (7200) — GroupSyncOverdue.",
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 12 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "time() - max by (cluster, groupsync, namespace) (gsd_groupsync_last_sync_timestamp_seconds{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} {{namespace}}/{{groupsync}}" }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "custom": { "drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 0, "showPoints": "never", "thresholdsStyle": { "mode": "line" } },
          "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "red", "value": 7200 } ] }
        },
        "overrides": []
      },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "desc" } }
    },
    {
      "id": 10,
      "type": "table",
      "title": "GroupSync CRs",
      "description": "Per CR: state (the one series of gsd_groupsync_state that is 1), groups attributed, and whether a ReconcileError is newer than the last success.",
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 12 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "State", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster, groupsync, namespace, state) (gsd_groupsync_state{cluster=~\"$cluster\"} == 1)", "format": "table", "instant": true },
        { "refId": "Groups", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster, groupsync, namespace) (gsd_groupsync_groups_total{cluster=~\"$cluster\"})", "format": "table", "instant": true },
        { "refId": "Error", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster, groupsync, namespace) (gsd_groupsync_reconcile_error_current{cluster=~\"$cluster\"})", "format": "table", "instant": true }
      ],
      "transformations": [
        { "id": "joinByField", "options": { "byField": "groupsync", "mode": "outer" } },
        {
          "id": "organize",
          "options": {
            "excludeByName": { "Time": true, "Time 1": true, "Time 2": true, "Time 3": true, "Value #State": true, "cluster 2": true, "cluster 3": true, "namespace 2": true, "namespace 3": true },
            "renameByName": { "cluster 1": "cluster", "namespace 1": "namespace", "state": "state", "Value #Groups": "groups", "Value #Error": "reconcile error current" }
          }
        }
      ],
      "fieldConfig": {
        "defaults": { "custom": { "align": "auto", "cellOptions": { "type": "auto" } } },
        "overrides": [
          { "matcher": { "id": "byName", "options": "reconcile error current" }, "properties": [ { "id": "mappings", "value": [ { "type": "value", "options": { "0": { "text": "no", "color": "green", "index": 0 }, "1": { "text": "YES", "color": "red", "index": 1 } } } ] }, { "id": "custom.cellOptions", "value": { "type": "color-text" } } ] },
          { "matcher": { "id": "byName", "options": "state" }, "properties": [ { "id": "mappings", "value": [ { "type": "value", "options": { "ok": { "color": "green", "index": 0 }, "late": { "color": "orange", "index": 1 }, "overdue": { "color": "red", "index": 2 }, "unknown": { "color": "text", "index": 3 } } } ] }, { "id": "custom.cellOptions", "value": { "type": "color-text" } } ] }
        ]
      },
      "options": { "showHeader": true, "cellHeight": "sm", "footer": { "show": false, "reducer": ["sum"], "fields": "" } }
    },
    {
      "id": 11,
      "type": "bargauge",
      "title": "Alerts by kind and severity",
      "description": "gsd_alerts_total as /api/alerts serves them at the wide tier. kind=group_count_cliff_silenced is a cliff an administrator silenced — reported, not hidden.",
      "gridPos": { "h": 9, "w": 12, "x": 0, "y": 20 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (cluster, kind, severity) (gsd_alerts_total{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}} {{severity}} {{kind}}", "instant": true }
      ],
      "fieldConfig": {
        "defaults": { "unit": "none", "min": 0, "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 1 } ] } },
        "overrides": [
          { "matcher": { "id": "byRegexp", "options": ".* critical .*" }, "properties": [ { "id": "thresholds", "value": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "red", "value": 1 } ] } } ] },
          { "matcher": { "id": "byRegexp", "options": ".*_silenced" }, "properties": [ { "id": "thresholds", "value": { "mode": "absolute", "steps": [ { "color": "text", "value": null } ] } } ] }
        ]
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": true, "minVizHeight": 12, "minVizWidth": 0, "namePlacement": "auto", "sizing": "auto", "valueMode": "color" }
    },
    {
      "id": 12,
      "type": "text",
      "title": "The twelve shipped alerts (monitoring.prometheusRule)",
      "gridPos": { "h": 9, "w": 12, "x": 12, "y": 20 },
      "options": {
        "mode": "markdown",
        "content": "| Alert | Severity | Fires on |\n|---|---|---|\n| `GroupSyncOverdue` | warning | `time() - gsd_groupsync_last_sync_timestamp_seconds > overdueSeconds` (7200) |\n| `DanglingRoleBinding` | critical | `gsd_bindings_total{finding=\"dangling\"} > 0` |\n| `GroupSyncDashboardNotPolling` | critical | `time() - gsd_cluster_last_poll_timestamp_seconds > notPollingSeconds` (600) |\n| `GroupSyncClusterUnreachable` | warning | `gsd_cluster_up == 0` |\n| `GroupSyncDashboardDirectUserGrants` | warning | `gsd_alerts_total{kind=\"direct_user_binding\"} > 0` |\n| `GroupSyncDashboardConfigReconcileError` | critical | `gsd_alerts_total{kind=\"config_reconcile_error\"} > 0` |\n| `GroupSyncGroupCountCliff` | warning | `gsd_alerts_total{kind=\"group_count_cliff\"} > 0` — silenced cliffs count under `group_count_cliff_silenced` and do not fire |\n| `GroupSyncDashboardWalGrowing` | warning | `gsd_sqlite_wal_bytes > walMiB` (256 MiB) |\n| `GroupSyncDashboardWalDisabled` | warning | `gsd_sqlite_wal_enabled == 0` |\n| `GroupSyncDashboardVisibilityChecksFailing` | critical | failing outcomes of `gsd_visibility_tier_checks_total` over 15m |\n| `GroupSyncDashboardLoginCaptureStalled` | warning | `time() - gsd_login_capture_last_read_timestamp_seconds > captureStalledSeconds` (1800) while `gsd_login_capture_enabled == 1` |\n| `GroupSyncDashboardBackupStale` | critical | `time() - gsd_backup_last_success_timestamp_seconds > backupStaleSeconds` (43200) |\n\nGauges are per replica: aggregate with `max()`; counters with `sum()`. `/metrics` names no group and no user by design."
      }
    },
    {
      "id": 13,
      "type": "timeseries",
      "title": "SQLite WAL size",
      "description": "gsd_sqlite_wal_bytes. Red line at monitoring.prometheusRule.walMiB (256 MiB) — GroupSyncDashboardWalGrowing. Sustained growth means checkpoints are starved by open readers.",
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 29 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max(gsd_sqlite_wal_bytes)", "legendFormat": "WAL bytes" }
      ],
      "fieldConfig": {
        "defaults": {
          "unit": "bytes",
          "custom": { "drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 10, "showPoints": "never", "thresholdsStyle": { "mode": "line" } },
          "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "red", "value": 268435456 } ] }
        },
        "overrides": []
      },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 14,
      "type": "timeseries",
      "title": "Checkpoints refused by a reader",
      "description": "increase(gsd_sqlite_checkpoint_busy_total). Occasional is normal; a rise every cycle beside a growing WAL is starvation.",
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 29 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum(increase(gsd_sqlite_checkpoint_busy_total[$__rate_interval]))", "legendFormat": "busy checkpoints" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "bars", "fillOpacity": 60, "showPoints": "never" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 15,
      "type": "stat",
      "title": "WAL mode",
      "description": "gsd_sqlite_wal_enabled. 0 means the filesystem refused WAL and readers block on every write — GroupSyncDashboardWalDisabled.",
      "gridPos": { "h": 4, "w": 4, "x": 16, "y": 29 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "min(gsd_sqlite_wal_enabled)", "legendFormat": "WAL", "instant": true }
      ],
      "fieldConfig": {
        "defaults": {
          "mappings": [ { "type": "value", "options": { "0": { "text": "OFF", "color": "red", "index": 0 }, "1": { "text": "WAL", "color": "green", "index": 1 } } } ],
          "thresholds": { "mode": "absolute", "steps": [ { "color": "red", "value": null }, { "color": "green", "value": 1 } ] }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "background", "graphMode": "none", "textMode": "value", "orientation": "auto" }
    },
    {
      "id": 16,
      "type": "stat",
      "title": "Leader replicas",
      "description": "sum(gsd_leader). Exactly 1 is healthy; 0 means nobody is polling; 2 means two writers on one database.",
      "gridPos": { "h": 4, "w": 4, "x": 20, "y": 29 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum(gsd_leader)", "legendFormat": "leaders", "instant": true }
      ],
      "fieldConfig": {
        "defaults": { "unit": "none", "thresholds": { "mode": "absolute", "steps": [ { "color": "red", "value": null }, { "color": "green", "value": 1 }, { "color": "red", "value": 2 } ] } },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "background", "graphMode": "none", "textMode": "value", "orientation": "auto" }
    },
    {
      "id": 17,
      "type": "stat",
      "title": "Build",
      "description": "gsd_build_info labels: the running version and commit.",
      "gridPos": { "h": 4, "w": 8, "x": 16, "y": 33 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max by (version, commit) (gsd_build_info)", "legendFormat": "{{version}} @ {{commit}}", "instant": true }
      ],
      "fieldConfig": { "defaults": { "thresholds": { "mode": "absolute", "steps": [ { "color": "text", "value": null } ] } }, "overrides": [] },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "none", "graphMode": "none", "textMode": "name", "orientation": "auto" }
    },
    {
      "id": 18,
      "type": "stat",
      "title": "Backup age",
      "description": "time() - gsd_backup_last_success_timestamp_seconds. Red at monitoring.prometheusRule.backupStaleSeconds (43200) — GroupSyncDashboardBackupStale. No data means backups are disabled or none exists yet.",
      "gridPos": { "h": 6, "w": 6, "x": 0, "y": 37 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "time() - max(gsd_backup_last_success_timestamp_seconds)", "legendFormat": "backup age", "instant": true }
      ],
      "fieldConfig": {
        "defaults": { "unit": "s", "decimals": 0, "noValue": "no backup", "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 21600 }, { "color": "red", "value": 43200 } ] } },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value", "orientation": "auto" }
    },
    {
      "id": 19,
      "type": "timeseries",
      "title": "Backup failures",
      "description": "increase(gsd_backup_failures_total): VACUUM INTO errors or an unwritable backupDir.",
      "gridPos": { "h": 6, "w": 6, "x": 6, "y": 37 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum(increase(gsd_backup_failures_total[$__rate_interval]))", "legendFormat": "failures" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "bars", "fillOpacity": 60, "showPoints": "never" }, "color": { "mode": "fixed", "fixedColor": "red" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "hidden", "placement": "bottom", "showLegend": false }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 20,
      "type": "timeseries",
      "title": "Retention rows deleted",
      "description": "increase(gsd_retention_rows_deleted_total) by table. login_event is capped at 5000 per cycle; a rate pinned there means the backlog is not draining.",
      "gridPos": { "h": 6, "w": 12, "x": 12, "y": 37 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum by (table) (increase(gsd_retention_rows_deleted_total[$__rate_interval]))", "legendFormat": "{{table}}" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "bars", "fillOpacity": 60, "showPoints": "never", "stacking": { "mode": "normal", "group": "A" } } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "none" } }
    },
    {
      "id": 21,
      "type": "timeseries",
      "title": "Visibility: scope decisions served",
      "description": "rate(gsd_visibility_decisions_total) by threshold and tier. The all:self mix shifting toward self while tier checks fail is the everyone-silently-narrowed signature.",
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 43 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum by (threshold, tier) (rate(gsd_visibility_decisions_total[$__rate_interval]))", "legendFormat": "{{threshold}} → {{tier}}" }
      ],
      "fieldConfig": { "defaults": { "unit": "reqps", "custom": { "drawStyle": "line", "lineInterpolation": "linear", "fillOpacity": 10, "showPoints": "never", "stacking": { "mode": "normal", "group": "A" } } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "none" } }
    },
    {
      "id": 22,
      "type": "timeseries",
      "title": "Visibility: tier checks that FAILED",
      "description": "increase(gsd_visibility_tier_checks_total{outcome=~\"unreachable|auth_failed|forbidden|error\"}). Every failure served the self view fail-closed — GroupSyncDashboardVisibilityChecksFailing.",
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 43 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum by (threshold, outcome) (increase(gsd_visibility_tier_checks_total{outcome=~\"unreachable|auth_failed|forbidden|error\"}[$__rate_interval]))", "legendFormat": "{{threshold}} {{outcome}}" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "bars", "fillOpacity": 60, "showPoints": "never", "stacking": { "mode": "normal", "group": "A" } }, "color": { "mode": "palette-classic" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "list", "placement": "bottom", "showLegend": true }, "tooltip": { "mode": "multi", "sort": "none" } }
    },
    {
      "id": 23,
      "type": "timeseries",
      "title": "Visibility: administrator-tier refusals",
      "description": "increase(gsd_visibility_admin_refusals_total): 403s from the administrator gate on the cluster-scoped views. Occasional is a non-admin clicking a tab.",
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 43 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "sum(increase(gsd_visibility_admin_refusals_total[$__rate_interval]))", "legendFormat": "refusals" }
      ],
      "fieldConfig": { "defaults": { "unit": "none", "custom": { "drawStyle": "bars", "fillOpacity": 60, "showPoints": "never" } }, "overrides": [] },
      "options": { "legend": { "displayMode": "hidden", "placement": "bottom", "showLegend": false }, "tooltip": { "mode": "single", "sort": "none" } }
    },
    {
      "id": 24,
      "type": "stat",
      "title": "Login capture",
      "description": "gsd_login_capture_enabled. While 1, absence of the last-read series means capture has never once succeeded.",
      "gridPos": { "h": 5, "w": 6, "x": 0, "y": 51 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "max(gsd_login_capture_enabled)", "legendFormat": "capture", "instant": true }
      ],
      "fieldConfig": {
        "defaults": {
          "mappings": [ { "type": "value", "options": { "0": { "text": "OFF", "color": "text", "index": 0 }, "1": { "text": "ON", "color": "green", "index": 1 } } } ],
          "thresholds": { "mode": "absolute", "steps": [ { "color": "text", "value": null } ] }
        },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value", "orientation": "auto" }
    },
    {
      "id": 25,
      "type": "stat",
      "title": "Login capture: last successful read age",
      "description": "time() - gsd_login_capture_last_read_timestamp_seconds per cluster. Red at monitoring.prometheusRule.captureStalledSeconds (1800) — GroupSyncDashboardLoginCaptureStalled. No data: never read.",
      "gridPos": { "h": 5, "w": 18, "x": 6, "y": 51 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "time() - max by (cluster) (gsd_login_capture_last_read_timestamp_seconds{cluster=~\"$cluster\"})", "legendFormat": "{{cluster}}", "instant": true }
      ],
      "fieldConfig": {
        "defaults": { "unit": "s", "decimals": 0, "noValue": "never read", "thresholds": { "mode": "absolute", "steps": [ { "color": "green", "value": null }, { "color": "orange", "value": 900 }, { "color": "red", "value": 1800 } ] } },
        "overrides": []
      },
      "options": { "reduceOptions": { "calcs": ["lastNotNull"], "fields": "", "values": false }, "colorMode": "value", "graphMode": "none", "textMode": "value_and_name", "orientation": "auto" }
    }
  ],
  "refresh": "1m",
  "schemaVersion": 39,
  "tags": ["openshift", "group-sync", "rbac", "gsd"],
  "templating": {
    "list": [
      {
        "name": "DS_PROMETHEUS",
        "label": "Prometheus",
        "type": "datasource",
        "query": "prometheus",
        "current": {},
        "hide": 0,
        "options": [],
        "refresh": 1,
        "regex": ""
      },
      {
        "name": "cluster",
        "label": "Cluster",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
        "definition": "label_values(gsd_cluster_up, cluster)",
        "query": { "query": "label_values(gsd_cluster_up, cluster)", "refId": "PrometheusVariableQueryEditor-VariableQuery" },
        "current": { "selected": true, "text": ["All"], "value": ["$__all"] },
        "hide": 0,
        "includeAll": true,
        "allValue": ".*",
        "multi": true,
        "options": [],
        "refresh": 2,
        "regex": "",
        "sort": 1
      }
    ]
  },
  "time": { "from": "now-24h", "to": "now" },
  "timepicker": {},
  "timezone": "browser",
  "title": "OCP Access Tracking Dashboard — group sync",
  "uid": "gsd-group-sync-dashboard",
  "version": 1,
  "weekStart": ""
}
```

Formatting rules the tests enforce: valid JSON, no tab characters, no trailing whitespace on any line, ends with exactly one `\n`. The implementer should write the file with `json.dump(obj, f, indent=2, ensure_ascii=False); f.write("\n")` from the object above, which produces exactly that.

## B3.6 Tests — new file `local-development/tests/test_chart_grafana_dashboard.py`

```python
"""The shipped Grafana dashboard: parses, references only metrics the collector declares,
carries the shipped alert thresholds, and reaches the cluster byte-identical.

Why byte-identity is asserted against a real `helm template` rather than assumed: the JSON
contains `$cluster`, `${DS_PROMETHEUS}`, `$__rate_interval` and `{{cluster}}` legend
formats — everything Helm would mangle if the file were inlined into a template. It is
loaded with .Files.Get, which Helm never templates; this file is what proves that stays true.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from datetime import timedelta

import pytest
import yaml
from prometheus_client import CollectorRegistry, generate_latest

from gsd.metrics import DashboardCollector
from gsd.store import Store

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
DASHBOARD = CHART / "dashboards" / "group-sync-dashboard.json"
VALUES = CHART / "values.yaml"

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _dashboard_configmaps(docs: list[dict]) -> list[dict]:
    return [d for d in docs
            if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-grafana-dashboard")]


def _walk_panels(panels: list[dict]):
    for p in panels:
        yield p
        yield from _walk_panels(p.get("panels", []))


def _exprs(board: dict) -> list[str]:
    out = []
    for p in _walk_panels(board["panels"]):
        for t in p.get("targets", []):
            if t.get("expr"):
                out.append(t["expr"])
    for v in board["templating"]["list"]:
        q = v.get("query")
        if isinstance(q, dict):
            q = q.get("query")
        if isinstance(q, str) and "gsd_" in q:
            out.append(q)
    return out


class TestTheFile:
    def test_parses_and_is_canonically_formatted(self):
        text = DASHBOARD.read_text()
        board = json.loads(text)
        assert board["uid"] == "gsd-group-sync-dashboard", "the uid is what makes re-imports update in place"
        assert board["schemaVersion"] >= 39
        assert "\t" not in text
        assert not [ln for ln in text.splitlines() if ln != ln.rstrip()], "trailing whitespace would survive `indent` and break byte-identity"
        assert text.endswith("}\n") and not text.endswith("\n\n")

    def test_every_metric_referenced_is_declared_by_the_collector(self):
        """The rule tests' guard, applied to panels: a panel over a metric nobody emits is
        a permanent 'No data' that reads as an outage."""
        referenced = set()
        for expr in _exprs(json.loads(DASHBOARD.read_text())):
            referenced |= set(re.findall(r"\bgsd_[a-z0-9_]+", expr))
        assert referenced, "no gsd_ metrics found in any expr; the probe itself is broken"

        store = Store(":memory:")
        try:
            registry = CollectorRegistry()
            registry.register(DashboardCollector(store, timedelta(seconds=120), None))
            text = generate_latest(registry).decode()
        finally:
            store.close()
        declared = {line.split()[2] for line in text.splitlines() if line.startswith("# HELP")}
        assert not (referenced - declared), f"dashboard references undeclared metrics: {referenced - declared}"

    def test_panel_thresholds_equal_the_shipped_alert_thresholds(self):
        """The board hard-codes values.yaml's prometheusRule defaults; this holds them together."""
        rule = yaml.safe_load(VALUES.read_text())["monitoring"]["prometheusRule"]
        board = json.loads(DASHBOARD.read_text())
        by_title = {p["title"]: p for p in _walk_panels(board["panels"])}

        def red_step(title: str) -> float:
            steps = by_title[title]["fieldConfig"]["defaults"]["thresholds"]["steps"]
            return next(s["value"] for s in steps if s["color"] == "red")

        assert red_step("Last poll age") == rule["notPollingSeconds"]
        assert red_step("GroupSync last-sync age per CR") == rule["overdueSeconds"]
        assert red_step("SQLite WAL size") == rule["walMiB"] * 1024 * 1024
        assert red_step("Login capture: last successful read age") == rule["captureStalledSeconds"]
        assert red_step("Backup age") == rule["backupStaleSeconds"]

    def test_the_text_panel_names_every_shipped_alert(self):
        monitoring = (CHART / "templates" / "monitoring.yaml").read_text()
        shipped = set(re.findall(r"- alert: (\w+)", monitoring))
        board = json.loads(DASHBOARD.read_text())
        text_panel = next(p for p in _walk_panels(board["panels"]) if p["type"] == "text")
        missing = {a for a in shipped if f"`{a}`" not in text_panel["options"]["content"]}
        assert not missing, f"text panel does not name: {missing}"

    def test_a_cluster_variable_scopes_the_per_cluster_panels(self):
        board = json.loads(DASHBOARD.read_text())
        names = {v["name"] for v in board["templating"]["list"]}
        assert {"DS_PROMETHEUS", "cluster"} <= names
        cluster_var = next(v for v in board["templating"]["list"] if v["name"] == "cluster")
        assert "label_values(gsd_cluster_up, cluster)" in json.dumps(cluster_var)
        assert cluster_var["includeAll"] and cluster_var["multi"]


@needs_helm
class TestTheConfigMap:
    def test_off_by_default_because_the_servicemonitor_is(self):
        assert not _dashboard_configmaps(_render())

    def test_follows_the_servicemonitor_when_left_empty(self):
        docs = _render("monitoring.serviceMonitor.enabled=true")
        cms = _dashboard_configmaps(docs)
        assert len(cms) == 1
        assert cms[0]["metadata"]["labels"]["grafana_dashboard"] == "1"
        assert "grafana_folder" not in (cms[0]["metadata"].get("annotations") or {})

    def test_explicit_true_ships_it_without_the_servicemonitor(self):
        docs = _render("monitoring.grafanaDashboard.enabled=true")
        assert _dashboard_configmaps(docs)
        assert not [d for d in docs if d.get("kind") == "ServiceMonitor"]

    def test_explicit_false_withholds_it_with_the_servicemonitor_on(self):
        docs = _render("monitoring.serviceMonitor.enabled=true",
                       "monitoring.grafanaDashboard.enabled=false")
        assert not _dashboard_configmaps(docs)

    def test_a_typo_refuses_the_render(self):
        args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                "--set-string", "monitoring.grafanaDashboard.enabled=ture"]
        done = subprocess.run(args, capture_output=True, text=True, timeout=120)
        assert done.returncode != 0
        assert "monitoring.grafanaDashboard.enabled" in done.stderr

    def test_folder_and_extra_labels_land(self):
        docs = _render("monitoring.grafanaDashboard.enabled=true",
                       "monitoring.grafanaDashboard.folder=Access",
                       "monitoring.grafanaDashboard.labels.team=platform")
        cm = _dashboard_configmaps(docs)[0]
        assert cm["metadata"]["annotations"]["grafana_folder"] == "Access"
        assert cm["metadata"]["labels"]["team"] == "platform"

    def test_rendered_configmap_json_is_byte_identical_to_the_file(self):
        """No Helm mangling: the `$cluster` / `{{cluster}}` strings survive, and the block
        scalar's chomping reproduces the file's single trailing newline exactly. If this
        ever fails on the final newline alone, switch the template to `| quote` — Go %q
        into a YAML double-quoted scalar is also lossless for this file."""
        cm = _dashboard_configmaps(_render("monitoring.grafanaDashboard.enabled=true"))[0]
        rendered = cm["data"]["group-sync-dashboard.json"]
        assert rendered == DASHBOARD.read_text()
        assert json.loads(rendered)["uid"] == "gsd-group-sync-dashboard"
```

## B3.7 Docs, CHANGELOG, chart README, Chart.yaml

**`charts/group-sync-dashboard/README.md`** — prerequisites bullet (old → new):

Old:
```
* The Prometheus Operator CRDs, only if you enable `monitoring.*`.
```
New:
```
* The Prometheus Operator CRDs, only if you enable `monitoring.serviceMonitor` or `monitoring.prometheusRule`. The Grafana dashboard (`monitoring.grafanaDashboard`) is a plain ConfigMap and needs no CRD.
```

Values rows — insert after the `monitoring.prometheusRule.for.*` row:

```
| `monitoring.grafanaDashboard.enabled` | `""` | `""` **follows `monitoring.serviceMonitor.enabled`**; `true`/`false` are explicit; anything else refuses to render. A ConfigMap labelled `grafana_dashboard: "1"` carrying `dashboards/group-sync-dashboard.json` byte-for-byte — no CRD, cannot fail an install |
| `monitoring.grafanaDashboard.folder` | `""` | written as the `grafana_folder` annotation the sidecar's `folderAnnotation` reads |
| `monitoring.grafanaDashboard.labels` / `.annotations` | `{}` / `{}` | extra metadata, e.g. a sidecar configured with a non-default label |
```

New subsection after `#### The twelve alerts` table (see B4 for the rename), titled `#### The Grafana dashboard`:

```
#### The Grafana dashboard

`monitoring.grafanaDashboard` ships `dashboards/group-sync-dashboard.json` as a ConfigMap with the
`grafana_dashboard: "1"` label that Grafana's dashboard sidecar watches. The sidecar only watches its
own namespace unless configured otherwise (`sidecar.dashboards.searchNamespace: ALL` in
kube-prometheus-stack), so either install the chart beside Grafana, set a folder and label your
sidecar recognises, or copy the ConfigMap. The board's thresholds equal the defaults above and are
held to them by a test; edit them in Grafana if you tune the rules.

Running grafana-operator v5? It reads this ConfigMap directly:

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: group-sync-dashboard
spec:
  instanceSelector:
    matchLabels:
      dashboards: grafana        # whatever your Grafana CR is labelled
  configMapRef:
    name: group-sync-dashboard-grafana-dashboard   # <fullname>-grafana-dashboard
    key: group-sync-dashboard.json
```

The chart does not ship that CR: the operator's CRD has two incompatible API versions in the wild
and the `instanceSelector` is yours to know.
```

**`README.md#Monitoring`** — old:
```
`/metrics` serves Prometheus exposition; the chart ships a ServiceMonitor and eleven alerting
rules, both off by default because they need the Prometheus Operator CRDs.
```
New:
```
`/metrics` serves Prometheus exposition; the chart ships a ServiceMonitor and twelve alerting
rules, both off by default because they need the Prometheus Operator CRDs, and a Grafana
dashboard (a sidecar-labelled ConfigMap, `monitoring.grafanaDashboard`) that follows the
ServiceMonitor's switch by default — see `docs/DESIGN_grafana_dashboard_and_group_count_cliff.md`.
```

**`docs/reference-architecture.md`** — after the deployment-topology mermaid block (the paragraph following `sm["ServiceMonitor + PrometheusRule<br/>optional"]`), add one sentence: "A third optional monitoring object, the Grafana dashboard ConfigMap (`charts/group-sync-dashboard/templates/grafana-dashboard.yaml`), is a core resource and follows the ServiceMonitor's switch." (Not added to the mermaid diagram: `tests/test_docs_diagrams.py` governs those and the sentence carries the fact.)

**`docs/CHANGELOG.md`** — insert directly above `## Application 0.11.0 — chart 0.10.0 — 2026-09-04`:

```
## Unreleased

- **Chart 0.11.0: a Grafana dashboard ships with the chart.** `monitoring.grafanaDashboard` renders
  `dashboards/group-sync-dashboard.json` as a ConfigMap labelled `grafana_dashboard: "1"` — the
  sidecar convention; grafana-operator v5 reads it through `configMapRef` (recipe in the chart
  README). Default `""` follows `monitoring.serviceMonitor.enabled`. Every panel expression is held
  to the collector's declared families, the thresholds to `values.yaml`'s defaults, and the rendered
  JSON to the file byte-for-byte, all by `tests/test_chart_grafana_dashboard.py`.
  (design `DESIGN_grafana_dashboard_and_group_count_cliff.md`)
```

**`charts/group-sync-dashboard/Chart.yaml`** — see B4.7 (one combined history line for chart 0.11.0).

## B3.8 Verification

1. `local-development/.venv/bin/python -m pytest local-development/tests/test_chart_grafana_dashboard.py local-development/tests/test_metrics.py local-development/tests/test_docs_citations.py -q`
2. `helm template t charts/group-sync-dashboard --set monitoring.serviceMonitor.enabled=true | yq 'select(.kind=="ConfigMap" and (.metadata.name|test("grafana"))) | .data["group-sync-dashboard.json"]' | python -m json.tool >/dev/null` — decodes.
3. `helm lint charts/group-sync-dashboard` and `helm package charts/group-sync-dashboard && tar tzf group-sync-dashboard-0.11.0.tgz | grep dashboards/` — the file is packaged.
4. Import the JSON into any Grafana 10.4+ via Dashboards → Import; select the Prometheus datasource; the `cluster` variable populates from `gsd_cluster_up`.

## B3.9 Risks

- The sidecar watches its own namespace by default; a dashboard installed elsewhere is silently ignored. Documented; a values `folder`/`labels` cannot fix namespace scope.
- Grafana's table `joinByField` column naming (`cluster 1`, `Value #Groups`) is version-sensitive; if a Grafana major renames them the CR table panel shows raw columns but nothing breaks. Editable in place.
- Go `%q`-vs-block-scalar: covered by the byte-identity test.

---


## Batch closing sections (verbatim)

## Operator-only questions

- Which namespace does your Grafana sidecar watch, and which label/annotation is it configured for? (Sets `monitoring.grafanaDashboard.labels`/`folder`, or whether to install beside Grafana.)
- grafana-operator v5 in use? If so, the `instanceSelector` labels for the `GrafanaDashboard` CR recipe.
- Does the group-sync-operator preserve a foreign annotation on the Group objects it syncs? (Risk 1 above.)
- Directory scale: is a floor of 10 and ratio 0.5 right for your largest groups, or should `minMembers` start higher?

### Critical Files for Implementation
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/state.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/metrics.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/monitoring.yaml
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/values.yaml
