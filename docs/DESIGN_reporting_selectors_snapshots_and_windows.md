# Design — multi-dimension namespace selectors, snapshot modes, and reporting windows

Status: draft for round-1 review. Author-driven from the operator's 2026-09-15 request, after the B3
mnemonic multi-select shipped (#117) and was validated live on CRC against the real
`company.net/mnemonic` namespace convention. This is a **reporting** feature set that spans the app,
the chart, the mock server and the frontend, decomposed into its own PRs after review, per the
programme's design-first rule and the adversarial-review skill (two reviewers, each PR).

The request, in the operator's words: *"support for reading mnemonic and app-environment metadata …
extend the mock server to have … namespaces too with both mnemonic and app-environment metadata …
ability to parameterize the snapshot rendering or reporting interval and a way to control manual or
turn on automatic snapshot … in a real environment with a lot of clusters … this is going to be a
heavy job … support cron tab when automated reports are run, control how often and what time of the
day too — reporting windows for the automated reporting. Manual report can run anytime we want."*

## 1. The problem, measured (what the code already gives us)

Grounding first, so this design does not rebuild what exists. Line references are to `main` at the
time of writing.

**Namespace metadata is already captured for MANY labels; the SELECTOR is single.**
- The dashboard poller captures a **list** of label keys: `local-development/gsd/config.py`
  `namespace_metadata_labels` is a `tuple[str, ...]`, rendered by the chart from
  `reporting.namespaceMetadata.labels` (`charts/group-sync-dashboard/templates/configmap.yaml`,
  `namespaceMetadataLabels`). Set to `[company.net/mnemonic, company.net/app-environment]` today and
  BOTH are captured into `cluster_namespace_label` — verified live on CRC 2026-09-15.
- But the report SELECTOR is a single label. The report service config
  `local-development/gsd/reporting/config.py` holds `namespace_selector_label` (str); the catalogue
  `local-development/gsd/reporting/server.py` `list_reports` calls `snap.namespace_selectors(<one
  label>)`; the namespace-access report `local-development/gsd/reporting/catalogue/namespace_access.py`
  expands one label via `snap.namespaces_for_metadata(cid, <one label>, mnemonics)`; the run context
  `local-development/gsd/reporting/catalogue/common.py` carries a single `namespace_selector_label`.
  The frontend renders one `<select multiple>` (`local-development/gsd/static/index.html`,
  `report-mnemonics`).
- **Gap:** the operator selects on `company.net/mnemonic` **and** `company.net/app-environment`
  together (e.g. "the `demo` and `gsd` mnemonics, `prod` only"), which the single selector cannot do.

**Snapshot cadence is a fixed interval; there is no manual/off mode.**
- The dashboard leader writes a read-only copy every interval: `local-development/gsd/poller.py`
  `_maybe_report_snapshot` runs in the poll tail, gated by (a) `reporting_url` set, (b) a monotonic
  deadline advanced by `reporting_snapshot_interval_seconds`, (c) `elector.is_leader`. It writes on
  the first post-startup cycle (the deadline is initialised to `0.0`). `local-development/gsd/store.py`
  `snapshot` does a `VACUUM INTO` (`_vacuum_into`), atomic `.tmp` + `os.replace`, keeping the newest
  `reporting_snapshot_keep` (default 2).
- The interval is **already parameterised**: `reporting.snapshot.intervalSeconds` (default 300, floor
  60 enforced both at render in `_helpers.tpl` `gsd.reportingGuards` and at runtime in
  `local-development/gsd/config.py`). A `VACUUM INTO` holds a read transaction ~3.2 s on a 61 MB /
  520k-row store (the floor's reason).
- **Gap:** with many clusters the periodic `VACUUM INTO` is a heavy standing cost even when no report
  runs. There is no way to turn the periodic snapshot **off** and take one **on demand**.

**Scheduled reports already exist, as Kubernetes CronJobs.**
- `charts/group-sync-dashboard/templates/report-cronjob.yaml` renders one `CronJob` per
  `reporting.schedules[]` entry (`{name, schedule, report, cluster, params, formats}`), running the
  report image's `local-development/gsd/reporting/trigger.py` (`--report --cluster --schedule --wait
  --param --format`), which POSTs a run with the service token and waits (Job status = run status).
  `concurrencyPolicy: Forbid`; `_helpers.tpl` validates each entry. Default `schedules: []`.
- A cron expression already controls **frequency and time of day**. Report generation is otherwise
  on-demand (a viewer's browser POST). There is **no** in-process scheduler, timer, or cron library.
- **Gap:** there is no cluster-wide **reporting window** — a rail that keeps automated (heavy) runs
  out of business hours regardless of how an individual schedule's cron was written or a stray
  service trigger fires.

**The mock server has only `team` labels.**
- `local-development/mock-app/fixtures/reference.yaml` defines two namespaces with `team: acme` /
  `team: platform`. The fixture schema (`local-development/mock-app/mock_app/fixture.py` `_namespace`)
  accepts any label keys and `local-development/mock-app/mock_app/responses.py` `namespace_item`
  serves the whole map, so this is data-only.
- **Gap:** the mock cluster cannot exercise the real `company.net/mnemonic` /
  `company.net/app-environment` convention, so the multi-dimension selector cannot be demoed or tested
  against the mock.

## 2. Decisions (settled with the operator, 2026-09-15)

1. **Selector combination — AND across dimensions, OR within a dimension.** `mnemonic ∈ {demo, gsd}`
   **and** `app-environment ∈ {prod}` selects namespaces carrying a matching mnemonic **and** a
   matching environment. Standard label semantics.
2. **Snapshot mode — a schedule/manual run refreshes first.** A new `automatic | manual` mode. In
   `manual`, the periodic `VACUUM INTO` is off; a fresh snapshot is taken **on demand just before a
   run renders** (both scheduled and manual UI runs), through a new leader endpoint. `ensure-fresh`
   semantics (a max-age) debounce concurrent requests so one `VACUUM` serves a burst.
3. **Reporting window — a global allowed-window rail.** A cluster-wide window (start/end/days,
   timezone) that **all automated (service/schedule) runs must fall inside**; the report service
   refuses a service run outside it. **Manual (viewer) runs always bypass** — "manual can run
   anytime." The window is a safety rail on top of each schedule's own cron, not a replacement.
4. **Delivery is out of scope here.** Automated runs land in the artefact store and the Usage tab as
   today; webhook/email delivery stays its own designed-but-unbuilt issue (#109,
   `docs/DESIGN_reporting_output_and_delivery.md` §4).
5. **The mock server carries the same labels.** Its namespaces carry `company.net/mnemonic` **and**
   `company.net/app-environment`, mirroring the real crc-local values, so the multi-dimension selector
   is exercisable against the mock cluster (operator, 2026-09-15).

## 3. Feature 1 — multi-dimension namespace selector

Turn the single selector label into an **ordered list** of selector labels, each of which must be one
of the captured `namespaceMetadata.labels`. Every selected dimension contributes a multi-select; the
report intersects them.

**Report service config** (`reporting/config.py`): `namespace_selector_label: str` →
`namespace_selector_labels: tuple[str, ...]`. Back-compat: a singular value is honoured as a
one-element list until the chart key is migrated (see the chart change below).

**Snapshot backend** (`reporting/snapshot.py`): keep the storage seam
(`local-development/tests/test_storage_seam.py`) — all SQL stays here.
- `namespace_selectors` gains a list form: per cluster id, a list of `{label, values}` (one per
  selector label), each `values` from the existing `namespace_metadata_values`. Wrapped in the same
  `sqlite3.Error → SnapshotError` boundary the B3 fix (D1) added, so the catalogue still degrades to an
  empty map rather than 500.
- A new selection method (call it `namespaces_for_selectors`) takes `cluster_id` and a mapping
  `{label: [values]}` and returns the namespace names in the **intersection across labels** of the
  **union within a label** — the AND/OR semantics of decision (1). It composes the existing
  per-label `namespaces_for_metadata` (one SQL `IN` per label) and intersects in Python, or a single
  `GROUP BY … HAVING COUNT(DISTINCT key) = N` query; the review picks the clearer of the two.

**Catalogue** (`reporting/server.py` `list_reports`): build `namespaceSelectors` per cluster from the
list of labels — `{cluster: [{label, values}, …]}` — so the form can render one control per dimension.

**Report** (`reporting/catalogue/namespace_access.py`): the `mnemonics` CSV param becomes a structured
selection `selectors: {label: [values]}` (a JSON object param), because a label like
`company.net/mnemonic` cannot be a flat form field name. The XOR with explicit `names` is preserved
(selectors **or** explicit names, never both), and `MAX_NAMESPACES` still bounds the expansion. The
run context `common.py` carries `namespace_selector_labels`.

**Frontend** (`static/index.html`): render one `<select multiple>` per entry in the cluster's
selector list, labelled by the label key (the current `report-mnemonics` control generalised). The C4
reset-on-cluster-switch fix (review #117) generalises to clear the whole `selectors` object when the
cluster changes. Posts `selectors` as the structured object.

**Chart**: `reporting.namespaceSelector.label` (scalar) → `reporting.namespaceSelector.labels` (list),
rendered to the report pod as a JSON env (`GSD_REPORT_NS_SELECTOR_LABELS`) the same way
`namespaceMetadataLabels` is rendered with `toJson`. The `_helpers.tpl` `gsd.reportingGuards` guard at
`:694` generalises: **every** selector label must be a member of `namespaceMetadata.labels`. Singular
`.label` still accepted (mapped to a one-element list) for one release, then removed.

## 4. Feature 2 — manual / automatic snapshot mode + on-demand snapshot

A new knob `reporting.snapshot.mode: automatic | manual` (default `automatic` — today's behaviour, the
chart's on-by-default philosophy). Threaded values → `reportingSnapshotMode` in `configmap.yaml` →
a `Settings` field in `config.py` (an enum setting, fail-safe to `automatic`, modelled on the existing
`_audit_mode_setting` / `_visibility_setting` pattern) → consumed in `poller.py`.

**In `automatic`** — unchanged: `_maybe_report_snapshot` writes every `intervalSeconds`.

**In `manual`** — `_maybe_report_snapshot` does **not** write on the interval. Instead a fresh
snapshot is produced **on demand, just before a run renders**, through a new leader endpoint:

- **`POST /api/report/snapshot` on the DASHBOARD** (the leader owns the live DB and is the only
  process that can `VACUUM INTO`). Service-token gated (the report SA), never a viewer. **`ensure-fresh`
  semantics**: the caller passes a max age; if the newest snapshot is younger, the endpoint returns
  its stamp and does nothing; otherwise it takes one `VACUUM INTO` (under a lock that serialises
  concurrent requests so a burst of clicks or a stampede of schedules causes at most one `VACUUM`) and
  returns the new stamp. This reuses `store.snapshot`; the lock preserves the single-writer invariant
  the periodic path relies on.
- **Who calls it.** Two callers, both settled at implementation by "simplest that is correct":
  - *Scheduled runs*: the schedule CronJob's `trigger.py` calls the dashboard endpoint before it POSTs
    the run (a new `--refresh-snapshot` flag the chart passes when `snapshot.mode == manual`). The
    trigger already runs in-cluster with the report token and can reach the dashboard Service.
  - *Manual UI runs*: the dashboard, which mints the ticket and is itself the leader, ensures a fresh
    snapshot locally before the browser's run POST when `mode == manual` (no extra network hop — it
    calls `store.snapshot` directly through the same lock).
- The report service render path is unchanged: it always reads `newest_snapshot`. Freshness is the
  caller's responsibility, which keeps the seam (`test_storage_seam`) intact and the report service
  stateless about cadence.

This is the operator's scale lever: at many clusters, `manual` means the expensive `VACUUM INTO`
happens once per report window, not every five minutes around the clock.

## 5. Feature 3 — the global reporting window

A new block `reporting.window` — `{enabled: false, timezone: "", start: "22:00", end: "06:00", days:
[Mon..Sun]}` — off by default (no behaviour change until an operator opts in). `timezone` defaults to
the app timezone already surfaced at `/api/version`.

**Enforcement is server-side and authoritative**, in `reporting/server.py` `create_run` (the one write
path). For a **service/schedule** caller (`principal.kind == "service"`, i.e. a `schedule` run), if the
window is enabled and the current time (in the window timezone) is **outside** the window, the run is
**refused** with a clear message naming the window (`"outside the reporting window 22:00–06:00
America/New_York"`). A **viewer** (ticket) run is never gated — manual runs anytime. The report pod
receives the window as env (`GSD_REPORT_WINDOW_*`), and `config.py` (report side) parses it with a
fail-safe (a malformed window logs and disables itself rather than blocking every run).

Refuse, not defer: deferring would need a queue that outlives the Job, which the CronJob model does not
provide; the operator sets each schedule's cron **inside** the window, and the rail catches a mis-set
cron or a stray manual service trigger. `trigger.py` may pre-check the window to fail fast with a
readable message, but the report service remains the authority. The chart guard validates
`start`/`end` as `HH:MM` and `days` as a subset of weekday names.

Interaction with Feature 2: a scheduled run in `manual` snapshot mode first refreshes the snapshot,
then POSTs the run, which the window then admits or refuses — the window check is on the run, and a
refused run does no snapshot work if the trigger checks the window before calling refresh.

## 6. Feature 4 (enabler) — mock server namespaces with both labels

`local-development/mock-app/fixtures/reference.yaml`: add namespaces carrying **both**
`company.net/mnemonic` and `company.net/app-environment`, mirroring the real crc-local values so the
mock cluster exercises the same convention — e.g. `demo-prod {mnemonic: demo, app-environment: prod}`,
`demo-qa {demo, qa}`, `gsd {mnemonic: gsd}`, `platform-prod {mnemonic: klta, app-environment: prod}`.
No Python change (the schema accepts arbitrary labels). Coverage: extend
`local-development/mock-app/tests/test_request_surface.py` `test_fetch_namespaces` to assert both keys
survive the client's key-set down-select, and add a two-dimension case to the end-to-end poll test.

This lands FIRST so Features 1–3 can be validated against the mock cluster through the embedded rig
(#116/#118), not only crc-local.

## 7. Guards (render-time), all failing loud

- Every `reporting.namespaceSelector.labels[]` entry must be in `reporting.namespaceMetadata.labels`
  (generalise the existing `:694` guard); the list must be non-empty when the namespace-access report
  is enabled and any metadata labels are set.
- `reporting.snapshot.mode` ∈ {automatic, manual}; anything else fails the render.
- `reporting.window.start` / `.end` must be `HH:MM`; `.days` a subset of the weekday names;
  `.timezone` a non-empty IANA name when `.enabled`.
- The existing floors stay: `intervalSeconds ≥ 60`, `ticket.ttlSeconds ∈ 30..3600`, `replicaCount = 1`,
  RWX, `rbac.namespaces = true` when metadata labels are set.

## 8. Security stance

- The on-demand snapshot endpoint is **service-token only** and **leader only**; a viewer cannot make
  the dashboard `VACUUM`. The `ensure-fresh` max-age + lock bound the cost a caller can induce.
- The window gates only service/schedule runs; it never restricts a human's manual run, and it never
  weakens the ticket/tier gates already on `create_run`.
- No new secrets, no new cluster-wide RBAC. The selector change reads only metadata already captured.
- The storage seam holds: all SQL stays in `store.py` / `reporting/snapshot.py`; `server.py` never
  imports `sqlite3` (`test_storage_seam`).

## 9. Decomposition (each its own PR, each its own two-reviewer review)

- **P1 — mock fixtures (Feature 4).** `reference.yaml` namespaces with both labels + tests. Smallest;
  unblocks testing the rest against the mock. Chart untouched; mock-app suite only.
- **P2 — multi-dimension selector (Feature 1).** App (config, snapshot, server, namespace_access,
  common), frontend (per-dimension controls, reset generalisation), chart
  (`namespaceSelector.labels`, env, guard). App + UI + chart; the largest change. Validated against the
  mock (P1) and crc-local through pure values.
- **P3 — snapshot mode + on-demand endpoint (Feature 2).** `reporting.snapshot.mode`, the leader
  `POST /api/report/snapshot` (ensure-fresh + lock), `trigger.py --refresh-snapshot`, the manual-UI
  refresh, chart knob + CronJob wiring. App + chart.
- **P4 — reporting window (Feature 3).** `reporting.window`, the `create_run` gate, report-side config,
  chart block + guard, optional trigger pre-check. App + chart.

Order: P1 → P2 → (P3, P4 independent of P2; P3 before P4 since the window admits/refuses a run that in
manual mode already refreshed). Each PR bumps the chart version (any `charts/` change) and, when the
app version changes, `pyproject.toml` / `gsd/__init__.py` / `Chart.yaml appVersion` together
(`test_chart_versions`), with a `docs/CHANGELOG.md` entry.

## 10. Verification

- `helm template` across the new switch states: multi-label selector (guard pass and the two failure
  cases), `snapshot.mode` automatic/manual, window enabled/disabled and malformed.
- The mock cluster (#116/#118) is the integration rig: P1 gives it both labels; P2 proves the
  two-dimension multi-select renders and expands (AND across / OR within) against the mock and
  crc-local; P3 proves a manual-mode run produces exactly one on-demand snapshot for a burst; P4 proves
  a service run is refused outside the window and a viewer run is not.
- `test_storage_seam`, `test_values_defaults` (every new false default enumerated),
  `test_chart_versions`, `test_chart_reporting`, and the citation tests stay green.
- Live on CRC: the two-dimension selector against the real `company.net/mnemonic` +
  `company.net/app-environment`; a `manual`-mode schedule that snapshots-then-renders inside a window,
  and is refused outside it.

## 11. Out of scope (named, not dropped)

- **Delivery** (webhook/email of automated runs) — issue #109, `docs/DESIGN_reporting_output_and_delivery.md` §4.
- **CSV / diff / preview** report-output features — issues #106/#107/#108 from the same design.
- **Per-cluster snapshot interval** — if the single global interval proves too coarse at scale, a
  follow-up; this design gives the bigger lever (manual mode) first.

## Open questions (to settle in review by "easy to manage, best practice")

1. `namespaces_for_selectors`: compose per-label `IN` queries and intersect in Python, or one
   `GROUP BY … HAVING COUNT(DISTINCT key)=N`. Pick the clearer; both are single-snapshot reads.
2. On-demand snapshot caller for manual UI runs: the dashboard refreshes locally at ticket mint, or the
   browser calls `POST /api/report/snapshot` explicitly before the run POST. The local path avoids a
   hop; the explicit path keeps the dashboard passive. Decide at P3.
3. Window "refuse" message channel: fail the run with status `failed` + reason, or return `409` from
   `create_run` so the CronJob Job fails fast without a stored failed run. Decide at P4.
