# Design — multi-dimension namespace selectors, snapshot modes, and reporting windows

Status: **round-1 reviewed, corrections folded in.** Record: `docs/REVIEW_reporting_selectors_snapshots_windows.md`.
Author-driven from the operator's 2026-09-15 request, after the B3 mnemonic multi-select shipped (#117)
and was validated live on CRC against the real `company.net/mnemonic` convention. A **reporting**
feature set spanning the app, the chart, the mock server and the frontend, decomposed into its own PRs
after review, per the programme's design-first rule and the adversarial-review skill (two reviewers,
each PR). Issue #126.

The request, in the operator's words: *"support for reading mnemonic and app-environment metadata …
extend the mock server … with both mnemonic and app-environment metadata … parameterize the snapshot
rendering or reporting interval and a way to control manual or turn on automatic snapshot … in a real
environment with a lot of clusters … this is going to be a heavy job … support cron tab when automated
reports are run, control how often and what time of the day too — reporting windows for the automated
reporting. Manual report can run anytime we want."*

## 1. The problem, measured (what the code already gives us)

Grounding first, so this design does not rebuild what exists. Line references are to `main` at writing.

**Namespace metadata is already captured for MANY labels; the SELECTOR is single.**
- The dashboard poller captures a **list** of label keys: `local-development/gsd/config.py`
  `namespace_metadata_labels` is a `tuple[str, ...]`, passed to `local-development/gsd/kube.py`
  `fetch_namespaces`, which keeps every configured key that is present. Rendered by the chart from
  `reporting.namespaceMetadata.labels` (`charts/group-sync-dashboard/templates/configmap.yaml`,
  `namespaceMetadataLabels`, `toJson`). Set to `[company.net/mnemonic, company.net/app-environment]`
  today; BOTH are captured into `cluster_namespace_label` — verified live on CRC 2026-09-15.
- But the report SELECTOR is a single label: `local-development/gsd/reporting/config.py`
  `namespace_selector_label` (str); `local-development/gsd/reporting/server.py` `list_reports` calls the
  snapshot with one label; `local-development/gsd/reporting/catalogue/namespace_access.py` expands one
  label; `local-development/gsd/reporting/catalogue/common.py` carries a single
  `namespace_selector_label`; the frontend renders one `<select multiple>`
  (`local-development/gsd/static/index.html`, `report-mnemonics`).
- **Gap:** the operator selects on `company.net/mnemonic` **and** `company.net/app-environment` together
  (e.g. the `demo`/`gsd` mnemonics, `prod` only) — the single selector cannot.

**Snapshot cadence is a fixed interval; there is no manual/off mode.**
- When reporting is enabled, a **successful** leader poll cycle attempts a snapshot after a monotonic
  deadline expires; a failed or stalled poll delays the attempt. `local-development/gsd/poller.py`
  `_maybe_report_snapshot` runs in the poll tail, gated by `reporting_url` set, the deadline, and
  `elector.is_leader`; the deadline starts at `0.0` so the first post-startup cycle writes.
  `local-development/gsd/store.py` `snapshot` does a `VACUUM INTO` **on the poll thread only** — its
  docstring: "from a request handler would put a user's page behind it" — atomic `.tmp` + `os.replace`,
  keeping the newest `reporting_snapshot_keep` (default 2).
- The interval is **already parameterised**: `reporting.snapshot.intervalSeconds` (default 300, floor 60
  at render and runtime — a `VACUUM INTO` holds a read transaction ~3.2 s on a 61 MB / 520k-row store).
- **Gap:** with many clusters the periodic whole-database `VACUUM INTO` is a heavy standing cost even
  when no report runs. There is no way to turn the periodic snapshot **off** and take one **on demand**.

**Scheduled reports already exist, as Kubernetes CronJobs.**
- `charts/group-sync-dashboard/templates/report-cronjob.yaml` renders one `CronJob` per
  `reporting.schedules[]` entry (`{name, schedule, report, cluster, params, formats}`), running
  `local-development/gsd/reporting/trigger.py` (POSTs a run with the service token, waits). A cron
  expression already controls frequency and time of day. There is **no** in-process scheduler/timer/cron
  library. Default `schedules: []`.
- **Gap:** no cluster-wide **reporting window** — a rail that keeps automated (heavy) runs out of
  business hours regardless of how an individual schedule's cron was written or a stray service trigger.

**The mock server has no `company.net/*` selector labels.**
- `local-development/mock-app/fixtures/reference.yaml` defines two namespaces: both carry `team`, and
  `acme-app` additionally `kubernetes.io/metadata.name`. The fixture schema
  (`local-development/mock-app/mock_app/fixture.py` `_namespace`) accepts any label keys and
  `local-development/mock-app/mock_app/responses.py` `namespace_item` serves the whole map — data-only.
- **Gap:** the mock cluster cannot exercise the real `company.net/mnemonic` /
  `company.net/app-environment` convention, so the multi-dimension selector cannot be demoed/tested there.

## 2. Decisions (settled with the operator, 2026-09-15)

1. **Selector combination — AND across dimensions, OR within a dimension.**
2. **Snapshot mode — a schedule/manual run refreshes first, via a PVC SENTINEL (the dashboard stays
   GET-only).** The dashboard's "PULLS, never writes" contract is preserved: the schedule signals a
   refresh by writing a sentinel on the shared volume; the leader VACUUMs on its own poll thread. Manual
   UI runs use the newest snapshot. (Codex's alternative — a properly-authed dashboard POST — was
   considered and rejected to keep the GET-only contract; see the review record.)
3. **Reporting window — a global allowed-window rail.** All automated (service/schedule) runs must fall
   inside it; a service run outside is **refused (409)**. **Manual (viewer) runs always bypass.**
4. **Delivery is out of scope here** (#109, `docs/DESIGN_reporting_output_and_delivery.md` §4). The
   **preview count** (#107) is folded into P2 — previewing how many namespaces a two-dimension selection
   expands to is the scale concern this design raises.
5. **The mock server carries the same labels** — `company.net/mnemonic` **and**
   `company.net/app-environment`, mirroring the real crc-local values, so the selector is exercisable
   against the mock (operator, 2026-09-15).

## 3. Feature 1 — multi-dimension namespace selector

Turn the single selector label into an **ordered list**, each of which must be one of the captured
`namespaceMetadata.labels`. Every selected dimension is a multi-select; the report intersects them.

**Report service config** (`reporting/config.py`): `namespace_selector_label: str` →
`namespace_selector_labels: tuple[str, ...]` (chart JSON env). Singular honoured as a one-element list
one release (chart back-compat below).

**Param grammar** (`reporting/catalogue/common.py`): `validate_params` has a closed type set with **no**
object branch, so a raw object 422s as "must be a string." Add a `ParamSpec` type `selector-map`: accept
only a non-empty `dict[str, list[str]]`; keys ⊆ `namespace_selector_labels`; non-empty deduped string
values; **≤ `MAX_NAMESPACES` selected values in aggregate**; empty lists rejected; **an omitted dimension
is unconstrained** (not `[]` → `namespaces_for_metadata(...,[])` → every run empty). XOR is exactly one
of `selectors` / legacy `mnemonics` / explicit `namespaces` (note: **`namespaces`**, not "names"). Keep
`mnemonics` a hidden deprecated spec one release, mapping to the first configured label and rejected
alongside a replacement.

**Snapshot backend** (`reporting/snapshot.py`, keeping the seam — all SQL here, `test_storage_seam`):
- `namespace_selectors` gains a list form: per cluster id a list of `{label, values}` (one per selector
  label), each `values` from the existing `namespace_metadata_values`, wrapped in the same
  `sqlite3.Error → SnapshotError` boundary the B3 fix (D1) added.
- A new `namespaces_for_selectors(cluster_id, {label:[values]})` returns the **intersection across
  labels** of the **union within a label** — compose the per-label `IN` queries and intersect in Python
  (the clearer default; a `GROUP BY … HAVING COUNT(DISTINCT key)=N` variant must reject duplicate
  configured labels or it can never satisfy N).

**Catalogue** (`reporting/server.py` `list_reports`): emit a new
`namespaceSelectorDimensions: {cluster: [{label,values}, …]}` **and** keep the current
`namespaceSelectors: {cluster: {label,values}}` (populated from the first dimension) one release, so a
dashboard and report pod rolling independently never crash the Reports form.

**Report** (`reporting/catalogue/namespace_access.py`): the selection param is the structured
`selectors` (a `selector-map`); `build()` validates keys against `ctx.namespace_selector_labels`, computes
AND-across/OR-within, sorts namespace names deterministically, then applies `MAX_NAMESPACES` + the
coverage warning. `common.py` carries `namespace_selector_labels`.

**Frontend** (`static/index.html`): render one `<select multiple>` per dimension, `id="report-selector-<i>"`
+ `data-selector-label="<label>"` (a dotted label is not a valid CSS id); update `form.selectors[label]`
with bracket notation; prefer `namespaceSelectorDimensions`, fall back to `namespaceSelectors`; fallback
value is `[]`, not `{label:"",values:[]}`; generalise the C4 cluster-switch reset to clear `.selectors`
(and any leftover `.mnemonics`). **#107 (preview)** rides here: a debounced count beside Generate of how
many namespaces the current `selectors` expands to.

**Chart**: `reporting.namespaceSelector.label` (scalar) → `reporting.namespaceSelector.labels` (list),
rendered as `GSD_REPORT_NS_SELECTOR_LABELS` (JSON, like `namespaceMetadataLabels`). The `_helpers.tpl`
`gsd.reportingGuards` guard generalises: **every** selector label ∈ `namespaceMetadata.labels`. Singular
`.label` accepted (one-element list) one release. Scheduled params move to JSON: a `--params-json`
trigger arg rendered `{{ toJson ($s.params | default dict) }}` (Helm `%v` renders a nested map as
`map[k:v]`, not JSON); `--param` kept as a deprecated scalar path. **P2 therefore edits `trigger.py`**
(JSON transport) — sequenced before P3's trigger edit.

## 4. Feature 2 — manual / automatic snapshot mode (PVC sentinel)

A new knob `reporting.snapshot.mode: automatic | manual` (default `automatic`). Threaded values →
`reportingSnapshotMode` in `configmap.yaml` → a `Settings` enum field in `config.py` (an **explicitly
invalid** value **fails startup** — a typo like `manul` must not silently fall back to `automatic` and
re-enable the expensive VACUUM; a *missing* value defaults to `automatic`) → consumed in `poller.py`.
Enforce floors against the **effective** URL/mode/interval (the current interval-floor check reads
YAML-only `reportingUrl` and is bypassable when reporting is enabled via `GSD_REPORTING_URL`).

**In `automatic`** — unchanged: `_maybe_report_snapshot` writes every `intervalSeconds`.

**In `manual`** — no periodic write. A fresh snapshot is produced **on demand** without any dashboard
write endpoint (the API stays GET-only; VACUUM stays on the poll thread):
- **Signal:** the schedule CronJob mounts the shared RWX `/data` and writes a sentinel (e.g.
  `/data/report/.snapshot-request`; it does not match `newest_snapshot`'s `gsd-*.db` glob, so it is never
  read or pruned as a snapshot). The trigger gains `--refresh-snapshot` (the chart passes it when
  `snapshot.mode == manual`), then polls the existing `GET /report/api/snapshot` until the stamp advances
  before it POSTs the run.
- **Act:** the leader poller sees the sentinel in its tail and, under **single-flight** with the
  freshness re-check **inside** the store lock (`age ≤ manualMinAgeSeconds` → reuse, else one `VACUUM
  INTO`; the re-check-inside-lock is what makes a burst of N schedules one VACUUM), runs `store.snapshot`
  **on the poll thread**, then deletes the sentinel. `manualMinAgeSeconds` is **server-owned with a
  floor** (a caller cannot force age 0). The VACUUM runs with a bounded timeout, `finally` cleanup, and
  duration/failure/in-flight metrics — a hung VACUUM must not hold `_lock` and stall the poller forever.
- **Bootstrap:** in manual mode the leader still writes **one snapshot at start** (keep the first-cycle
  write, then disable the interval) so the report pod's `readyz` — which 503s on a missing snapshot — can
  go Ready. Make `newest_snapshot`'s "written every intervalSeconds" error and the
  `…ReportSnapshotStale` alert **mode-aware** (idle age is expected in manual mode; alert on refresh
  failure / stuck in-flight instead).
- **Manual UI runs** use the newest snapshot (they "run anytime" on the latest copy). No viewer path
  induces a VACUUM.

**Cost, stated honestly:** manual mode removes snapshots while no admitted report is rendering. A
`VACUUM INTO` copies the **whole** database (one file for all clusters), so its cost scales with DB size,
not cluster count; it runs at most once per freshness bucket, and runs separated by more than
`manualMinAgeSeconds` each produce a copy. Savings depend on run frequency and DB size — not "once per
window."

## 5. Feature 3 — the global reporting window

A new block `reporting.window` — `{enabled: false, timezone: "", start: "22:00", end: "06:00", days:
[Mon..Sun]}` — off by default. Rendered to the report pod as `GSD_REPORT_WINDOW_*`;
`GSD_REPORT_WINDOW_TIMEZONE = reporting.window.timezone | default .Values.timezone` (the report pod
already receives `TZ` from `.Values.timezone`; `/api/version` is dashboard-only and not consulted). The
CronJob also sets `spec.timeZone` to the same zone (else Kubernetes interprets the cron in the
controller's timezone).

**Origin, persisted.** Record an `origin` on `Run`: `viewer` (ticket), `schedule` (service token + a
non-empty `schedule`), `service` (service token, no schedule). Gate `schedule` **and** `service`; only
`viewer` bypasses. `principal.kind` alone is credential type, not origin — gating on `body.schedule`
would let a service curl without `--schedule` slip the window.

**Predicate (half-open, wrap-aware).** In the window timezone, with `t = local time`:
- same-day (`start < end`): inside iff `start ≤ t < end` and `weekday(today) ∈ days`;
- wrap (`start > end`, e.g. 22:00–06:00): inside iff `(t ≥ start ∧ weekday(today) ∈ days)` **or**
  `(t < end ∧ weekday(today − 1 day) ∈ days)` — so Monday 02:00 belongs to Sunday's window.
Reject `start == end` and an empty/duplicate `days` at the chart guard.

**Enforcement.** Authoritative in `reporting/server.py` `create_run`: for a `schedule`/`service` origin
outside the window, return **409 with `Retry-After`** (until the next opening) **before constructing the
Run** — no stored failed run per ordinary miss. The one-worker queue can carry an admitted run past the
close, so the worker **rechecks** before snapshot-refresh/render (that exceptional case may store a
failed run with a reason). `trigger.py` maps 409 → **exit 0** ("skipped: outside window"); any other
4xx/5xx → exit 1. An enabled **malformed** window **fails closed** (report-service startup failure), never
log-and-disable. Add `gsd_report_runs_outside_window_total` (no names) + a WARNING log, and monitor "no
successful schedule within its expected period" as an evidence gap — a wrong timezone must not silently
stop nightly evidence. A trigger-side pre-check is diagnostic only (same predicate); the server is the
authority, and the window is evaluated **before** any snapshot refresh so a refused run wastes no VACUUM.

## 6. Feature 4 (enabler) — mock server namespaces with both labels

`local-development/mock-app/fixtures/reference.yaml`: add namespaces carrying **both**
`company.net/mnemonic` and `company.net/app-environment`, mirroring the real crc-local values — e.g.
`demo-prod {mnemonic: demo, app-environment: prod}`, `demo-qa {mnemonic: demo, app-environment: qa}`,
`platform-prod {mnemonic: klta, app-environment: prod}`. Every fixture used for the two-dimension e2e
must carry **both** labels (a namespace with only `mnemonic` vanishes from a two-dimension AND); keep at
most one single-dimension namespace and name it an explicit missing-dimension negative case. No Python
change (the schema accepts arbitrary labels). Coverage: extend
`local-development/mock-app/tests/test_request_surface.py` `test_fetch_namespaces` to assert both keys
survive the client's key-set down-select, and add a two-dimension case to the end-to-end poll test.

Lands FIRST so Features 1–3 validate against the mock cluster (#116/#118), not only crc-local.

## 7. Guards (render-time), all failing loud

- Every `reporting.namespaceSelector.labels[]` ∈ `reporting.namespaceMetadata.labels` (generalise the
  existing guard); non-empty when the namespace-access report is enabled and metadata labels are set.
- `reporting.snapshot.mode` ∈ {automatic, manual}; anything else fails render (and startup).
- **`reporting.snapshot.keep ≥ 2`** at render and runtime — `keep: 0` disables pruning (retains every
  copy) and two copies close the newest-path/prune-handoff race.
- `reporting.window`: `start`/`end` are `HH:MM` and `start != end`; `days` a non-empty, duplicate-free
  subset of weekday names; `timezone` a non-empty IANA name when `enabled`.
- Existing floors stay: `intervalSeconds ≥ 60` (against the **effective** value), `ticket.ttlSeconds ∈
  30..3600`, `replicaCount = 1`, RWX, `rbac.namespaces = true` when metadata labels are set.

## 8. Security stance

- No new dashboard write endpoint; the API stays GET-only (`test_r6_the_api_is_read_only`). The
  sentinel-driven VACUUM is an **expensive-operation capability**: single-flight, a server-owned min-age
  floor (never age 0), a bounded timeout, and metrics/audit of refresh outcome bound the cost a caller
  can induce. Only the schedule pod (which mounts `/data`) can drop a sentinel; a viewer never induces a
  VACUUM.
- The window gates only `service`/`schedule` origins; it never restricts a human's manual run, and it
  never weakens the ticket/tier gates on `create_run`. **v1 treats the window as an operational rail,
  non-adversarial to a service-token holder** — the same HMAC secret signs viewer tickets and
  authenticates the service token, so a token holder could mint a viewer ticket to bypass a kind-based
  window; splitting the signing secret from the service bearer is a named follow-up.
- No new secrets, no new cluster-wide RBAC. The selector change reads only metadata already captured.
- The storage seam holds: all SQL in `store.py` / `reporting/snapshot.py`; `server.py` never imports
  `sqlite3`.

## 9. Decomposition (each its own PR + two-reviewer review) — order P1 → P2 → P4 → P3

- **P1 — mock fixtures (Feature 4).** `reference.yaml` namespaces with both labels + tests. **No `charts/`
  change → no chart bump.** Unblocks testing the rest against the mock.
- **P2 — multi-dimension selector (Feature 1) + preview count (#107).** App (config, snapshot, server,
  namespace_access, common), frontend (per-dimension controls, reset, preview), chart
  (`namespaceSelector.labels`, env, guard), `trigger.py` (`--params-json`). The largest change.
- **P4 — reporting window (Feature 3).** Persisted `origin`, the `create_run` 409 gate + worker recheck,
  report-side window config, chart `window` block + guard + CronJob `spec.timeZone`. **Before P3** so the
  window admission exists before snapshot refresh is wired.
- **P3 — snapshot mode + PVC sentinel (Feature 2).** `reporting.snapshot.mode`, the poller sentinel
  handler (single-flight, min-age, timeout, metrics), `trigger.py --refresh-snapshot` + `/data` mount on
  the schedule pod, mode-aware `readyz`/alert, the effective-URL floor fix, the `keep ≥ 2` guard.

These PRs share `reporting` config/server/values/helpers/deployment files — **sequential, not
independent**. The per-PR chart bump is enforced by the CI base-diff guard
(`.github/workflows/ci.yml`), not `test_chart_versions`; when the app version moves, `pyproject.toml` /
`gsd/__init__.py` / `Chart.yaml appVersion` advance together, with a `docs/CHANGELOG.md` entry.

## 10. Verification

- `helm template` across the switch states: multi-label selector (guard pass + the two failure cases),
  `snapshot.mode` automatic/manual (+ invalid fails), `window` enabled/disabled/malformed, `keep ≥ 2`,
  CronJob `spec.timeZone` and `--refresh-snapshot` wiring.
- Test list by PR: **P2** — `test_namespace_selector`, `test_reporting_server`, `test_ui` (CI-deselected,
  run locally), a new `trigger` JSON test, legacy `mnemonics`/`namespaceSelectors` compat, `company.net/…`
  DOM-id coverage; **P4** — same-day + wrap boundaries, anchor weekday, DST, viewer/service/schedule
  origins, queue-crossing recheck, fail-closed config, 409/no-artifact, CronJob `spec.timeZone`; **P3** —
  `test_api_contract` R6 stays green (the sentinel keeps the API GET-only), first-ever manual readiness,
  leader/non-leader, single-flight recheck, timeout/failure recovery, automatic-vs-manual alert
  rendering, the effective-URL floor.
- `test_storage_seam`, `test_values_defaults` (`window.enabled: false` added to `KEPT_OFF` with a reason;
  `snapshot.mode` default asserted exactly `automatic`, a string, not a KEPT_OFF boolean),
  `test_environments_readme` (+ `environments/README.md` for any CRC override), `test_chart_reporting`,
  the chart `README.md` rows, and the citation tests stay green.
- The mock cluster (#116/#118) is the integration rig: P1 gives it both labels; P2 proves the
  two-dimension multi-select renders + expands (AND across / OR within) against the mock and crc-local,
  with a preview count; P4 proves a service run 409s outside the window and a viewer run does not; P3
  proves a manual-mode burst of N schedules produces exactly one on-demand snapshot. A **target-scale
  load test** measures DB size, VACUUM duration, poll delay, and snapshots for N staggered schedules.
- Live on CRC: the two-dimension selector against real `company.net/mnemonic` + `company.net/app-environment`;
  a `manual`-mode schedule that snapshots-then-renders inside a window and 409s outside it.

## 11. Out of scope (named, not dropped)

- **Delivery** (webhook/email of automated runs) — #109, `docs/DESIGN_reporting_output_and_delivery.md` §4.
- **CSV** (#106) and **change/diff** (#108) report-output features — same design.
- **Per-cluster snapshot interval / secret-split for an adversarial window** — follow-ups; this design
  gives the bigger levers first (manual mode; the operational window rail).

(**#107 preview** is IN scope, folded into P2 — it directly serves the two-dimension selection's scale
concern.)
