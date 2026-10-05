# Review — PR #74, B3: the Grafana dashboard shipped with the chart

Adversarial second-opinion pass, 2026-09-05, on the eight-claim brief for #74 (`docs/specs/SPEC_B3_grafana_dashboard.md`
applied; chart 0.13.0, chart only). Codex ran at `gpt-5.6-sol` / `xhigh` with a shell (helm renders, an AST audit of every
expression against the collector's families, upstream docs where the network allowed); Cursor ran on
`cursor-grok-4.6-high-fast` in ask mode with the shell blocked and traced from source plus the CRC screenshot. Every
verdict was re-checked here — the label collision by a real render, the No-data colour by the screenshot — and every
accepted fix has a test that fails on the code before it.

## First pass — verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 every expression uses declared families with the right labels and types; PromQL parses | PLAUSIBLE (no parser reachable) | CONFIRMED (traced) | **Accepted in scoped form**: CI installs `promtool` and a test parses every expression there; locally it skips |
| C2 thresholds equal the rules; the text panel names all twelve alerts | CONFIRMED | CONFIRMED | — |
| C3 the tri-state, byte identity, folder and labels | REFUTED: `=null` nil pointer; a colliding `grafana_dashboard` label wins; the `{{- end }}` claim is false | REFUTED: the colliding label wins | **Accepted, all three**: nil-safe reads, a refusal of the reserved key, the comment corrected |
| C4 sidecar and operator conventions | REFUTED: `searchNamespace: ALL` is the current upstream default; folder needs configuration; the recipe lacks `allowCrossNamespaceImport` | REFUTED: the recipe lacks `allowCrossNamespaceImport` | **Accepted**: README says "check your values", names both settings, carries the validated recipe |
| C5 `${DS_PROMETHEUS}` serves both import paths | CONFIRMED (the datasource variable) | CONFIRMED (the screenshot's dropdown) | — |
| C6 multi-replica aggregation | CONFIRMED | CONFIRMED | — |
| C7 fidelity and the recorded deviations | CONFIRMED (17 files) | CONFIRMED | — |
| C8 the README's namespace remedies | REFUTED: "set a folder and label" cannot widen the scope | REFUTED, its most important | **Accepted**: the three real remedies |
| Volunteered: three stat panels paint "No data" alarm-red | found | found (its F3, from the screenshot) | **Accepted**: neutral base step; Leader replicas alarms on 0 and 2+, not on absence |

## What each accepted fix is

- **The reserved label.** `--set monitoring.grafanaDashboard.labels.grafana_dashboard=0` rendered a ConfigMap whose
  label was `0` (measured), which the sidecar ignores: a board that exists, looks right, and never appears. The chart
  refuses a colliding key.
- **Nil safety.** `--set monitoring.grafanaDashboard=null` died on `.labels` of nil; the map is read through
  `default dict` and a test renders the null form both with and without the ServiceMonitor.
- **The README.** The "folder and label" remedy was false against the spec's own risk section; the subsection now
  lists colocation, copying, or `searchNamespace: ALL` (nested under `grafana:` in kube-prometheus-stack), says
  current kube-prometheus-stack already defaults to `ALL` while older releases and the Grafana chart alone do not,
  names `folderAnnotation`/`foldersFromFilesStructure` as configuration rather than defaults, explains both datasource
  paths, and carries the operator recipe exactly as validated on CRC, `allowCrossNamespaceImport: true` included.
- **The comment about `{{- end }}`.** Codex rendered both forms: byte-identical. The template's comment and the
  spec's note now say the untrimmed form is kept for readable YAML, not for correctness.
- **No data is not an alarm.** On CRC (no Prometheus) Cluster up, WAL mode and Leader replicas painted red on "No
  data"; the base threshold step is neutral now, and Leader replicas alarms on 0 and on 2 or more.
- **PromQL parsing.** Neither reviewer could reach a parser; CI installs `promtool` and a test parses every panel
  expression through `promtool check rules`, failing in CI if the parser is missing and skipping locally.

## Rejected

Codex's version of the label-collision test asserted the word "reserved" in the error; the message says "must not
set" and the test asserts the key name instead. Codex's copy-the-chart test for the two `end` forms was not taken:
the byte-identity test already holds the form the chart uses, and the corrected comment records the measurement.

## Second pass, on the fixed head, with the same models

| Finding | Cursor | Codex | Decision |
|---|---|---|---|
| The six accepted fixes close their holes | CONFIRMED ×6 | CONFIRMED ×9 (renders) | — |
| Six more stat/bar-gauge panels paint "No data" healthy green | REFUTED (from the screenshot) | REFUTED (`verdict_coloured_base_steps=8`) | **Accepted**: every coloured panel's base step is neutral; one general test replaces the three-title one |
| `--set monitoring=null` dies in the helper | PLAUSIBLE → nil-safe | — | **Rejected as unreachable**: `monitoring.yaml` requires the map first; the helper's nil-safe read kept as harmless |
| The operator recipe binds no datasource; two Prometheus datasources → the first is picked | — | REFUTED | **Accepted**: the recipe carries the `datasources` input mapping |
| schemaVersion 39 imports on 10.4 and 12 | CONFIRMED (traced) | PLAUSIBLE (no Grafana locally) | — (validated live on the operator's Grafana 13.0.1) |
| promtool accepts every expanded expression | CONFIRMED (traced) | PLAUSIBLE (no promtool locally) | — (runs in CI) |
| `fullnameOverride`, ConfigMap size, upgrade from 0.12.0, the release tuple | CONFIRMED | CONFIRMED | — |

## Live, on CRC

grafana-operator v5.24 installed from Community Operators into `grafana-test`; a `Grafana` labelled
`dashboards: grafana`; a `GrafanaDashboard` in the dashboard's namespace with `allowCrossNamespaceImport: true` and
`configMapRef` to the chart's ConfigMap: `Dashboard was successfully applied to 1 instances`, uid
`gsd-group-sync-dashboard`; the board re-imported (its hash moved) after the threshold fix. Screenshot:
`docs/screenshots/06-grafana-dashboard-crc.png` — every panel renders, all "No data" because the cluster has no
Prometheus, none of them red.
