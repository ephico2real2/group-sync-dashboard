# SPEC F3 — `report-diff` runs: what changed between two runs of one report on one cluster (#108)

| | |
|---|---|
| Programme | Epic F (#386), reports: honest seals, more formats, diffs and delivery. Build step 3 of 6: a stored, sealed comparison of two runs F1 sealed |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 4.3.0, chart 0.66.7 |
| Version note | Image content (a new module, a branch in `create_run` and in the worker), so the next application MINOR, 4.3.0 (`docs/specs/README.md`, the version ladder). The chart takes the PATCH that moves `appVersion`, 0.66.7: its only other change is the README's reports paragraph; no value key, default, template or RBAC rule changes (the chart's rule, `charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`; 0.66.5 and 0.66.6 were the same kind of step). Read on `43b231b6` (application 4.2.0, chart 0.66.6); W1 is `specified` at chart 0.67.0, which stays above 0.66.7, so W1 does not move. A release that lands first makes the version blocks (§7, Blocks 12 to 15) fail their check; the implementing pull request corrects them here first |
| Issue | [#108](https://github.com/ephico2real2/group-sync-dashboard/issues/108) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-03, from the issue's refined body (2026-09-26), `docs/DESIGN_reporting_output_and_delivery.md` §1 and §3 re-measured against main after F1 (#270) and F2 (#106). Measured on main `43b231b6` with the repository's venv (Python 3.14): §2.3's probes built all eleven reports over the seeded snapshot of `tests/test_report_seal.py`. No lab read; §5 states the walk. §7's blocks were proved against a clean checkout of `43b231b6` (§4.3) |

## How to read this spec

The plain point first: an access review asks "what changed since the last review?". Today the reviewer opens two
reports and compares them by eye. Every run already stores its report as sealed JSON of one shape, so the service
can compare two of them itself. This spec adds a run named `report-diff`: it names a base run and a head run of one
report on one cluster, lists per table the rows removed and the rows added, and is stored, sealed and downloadable
like any report, in every format.

§1 is the mandate. §2 is the research: sources, the code, the probes. §2a weighs the alternatives. §3 is the
design, one rule per subsection with its reason. §4 maps each Definition-of-Done item to a test. §5 is the walk on
the lab. §6 is what an operator sees. §7 is the change as implementation blocks (`docs/specs/README.md`,
"Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F3_report_diff.md . --apply

Line citations into the code at `43b231b6` are `file:line` in plain text inside quoted output and tables; prose
cites `path#anchor`.

## Orchestrator's notes

1. **The page's "Diff vs…" action is specified in §3.8 but has no blocks yet (out of this spec's budget).** The
   service side (§7, Blocks 1 to 16) is complete and proved (§4.3). The page change — a "Diff vs…" button on the
   Report history rows, its picker and its browser test (T108-9) — is described rule by rule in §3.8 and is
   **not measured**: the implementing pull request writes its blocks into §7 first, under this note, and proves
   T108-9 failing on main and passing after, before applying anything. Until then the API (`POST /report/api/runs`
   with `report: "report-diff"`) is the only way to request a diff.
2. **The issue's "titles carry live counts" does not hold on main.** Measured (§2.3): none of the 44 tables of the
   eleven reports over the seed carries a digit in its title. What varies is a section title carrying a
   PARAMETER (`Membership changes, last {window_days} days`, groups.py:51; `Dormant: no successful login in
   {dormant_days} days`, dormant_access.py:60) or a SUBJECT (`Group: {name}`, `Bindings of {name}`,
   access_certification.py:95-112). §3.1 keys a block on its section title, kind, title and columns; a varying
   title therefore reads as one block removed and another added, which is what happened.
3. **The design doc predates #149, #270 and #106** (§2.4 lists what no longer holds). Its status line gains one
   sentence pointing here (Block 16).
4. **The issue's line numbers moved.** It cites server.py:312-316 and :307-309 for `create_run`, runs.py:166
   for the catalogue lookup, index.html:3140 and :3381 for the history and the drawer. On `43b231b6`:
   server.py:312-339, runs.py:167, index.html:3275 (`reportingHistoryCard`) and the Library from :3334.
5. **The index count.** Fifty-four on `43b231b6`; this row makes it fifty-five, and
   `local-development/tests/test_specs_index.py` moves to 55. #108 is below the numbers of the rows above it, so
   F3 is excluded from the rising-number assert by its id and pinned to #108, as F1 and F2 were.
6. **Dates.** Blocks 14 and 15 date the history lines 2026-10-03; the implementing pull request writes its own.
7. **"One write" is already two-and-two.** The issue cites `create_run` as the service's only state-changing
   endpoint. Since H1 (#542) the module docstring (server.py:4-9) names two non-GETs plus, with
   `housekeeping_enabled`, a DELETE and a cleanup POST for the dashboard's token. This spec adds no route: a diff
   is a `POST /report/api/runs` like any run, so the contract test (`test_reporting_server.py`, class
   `TestItsOwnContract`) holds unchanged.

Open questions only the operator can answer:

1. **Different parameters.** §3.4 allows a diff of two runs made with different parameters and prints a warning
   in the diff. Should it refuse them (422) instead? Refusing is simpler to read; allowing keeps the
   access-certification case ("this campaign against the last one", whose `campaign`/`due`/`reviewer` differ).
2. **The manual cap.** A diff is a manual run, so it takes one of `reporting.retention.manual.maxRuns`' slots
   (§3.6). Should diffs have their own cap instead? Not proposed: it would be a third tier.

## 1. The mandate, and what is out of scope

The mandate (#108, "The change" and "Definition of Done"): settle row identity, what a diff run records (base and
head ids, both sha256s, its own seal), retention (the manual tier) and the refusals (422 for a base or head that is
unknown, unfinished, of another report or cluster, or pruned); build `build_diff`, the `report-diff` branch in
`create_run` and in the worker, both before the `REGISTRY` lookup, and a "Diff vs…" action on the Report history;
render through the ordinary renderers (JSON, HTML, PDF, CSV).

Must not change (the issue): the eleven-report catalogue and every count that asserts it; the stored base and head
runs; the one-write contract; two-tier retention for existing runs.

Out of scope: per-cell change detection (v1 lists a changed row as removed and added; §2a, option C); a diff of
more than two runs; a scheduled diff (§3.5 refuses a schedule); anchoring the clock-reading reports' windows to the
snapshot (SPEC_F1, open question 1; §3.3 states what a diff of them shows).

## 2. Research, measured

### 2.1 Sources

| Source (fetched 2026-10-03) | What it does | What this spec takes |
|---|---|---|
| GNU diffutils manual, "Comparing and Merging Files", <https://www.gnu.org/software/diffutils/manual/diffutils.html> | Lines are compared whole; a changed line is reported as a deletion and an insertion in the normal and unified formats | The v1 rule: a changed row is one removed and one added |
| SQL `EXCEPT ALL` (PostgreSQL 17 docs, "Combining Queries", <https://www.postgresql.org/docs/17/queries-union.html>) | "EXCEPT ALL" keeps duplicates: a row in the left input m times and the right n times appears max(m−n, 0) times | Rows are compared as multisets (Python `Counter` subtraction is the same arithmetic), so a duplicate row is counted, never collapsed |
| daff, "Data diffs" (<https://github.com/paulfitz/daff>) | A table diff with keyed rows marks a row `+++` (added), `---` (removed) or `->` (changed cells) when a key column is known | Rejected for v1: it needs a key column per table, which the model does not declare (§2a, option C) |
| W3C PROV-O, `prov:wasDerivedFrom` (<https://www.w3.org/TR/prov-o/#wasDerivedFrom>) | A derived entity names the entities it was derived from | The diff run's `params` names both input runs and their sha256s, and the seal covers them (§3.7) |

Not measured: the sources were read for their stated behaviour; no tool among them was run here.

### 2.2 The code, read on `43b231b6`

```text
local-development/gsd/reporting/model.py:99-112      canonical(): name, cluster, api_url, params, coverage, totals, truncated, include_members, sealed_provenance, sealed sections only
local-development/gsd/reporting/model.py:120-129     to_json(): canonical + every section with its `sealed` flag + the run facts + sha256
local-development/gsd/reporting/artifacts.py:39-63   Run: id, report, cluster, params, formats, generated_by, …, schedule, sha256, bytes, origin
local-development/gsd/reporting/artifacts.py:191-203 read(): the bytes, or None once pruned
local-development/gsd/reporting/artifacts.py:320-330 _retention(): a run with no `schedule` is the MANUAL tier (newest maxRuns, aged by days)
local-development/gsd/reporting/server.py:321-329    create_run: REGISTRY check → 404, enabled check → 404, validate_params → 422
local-development/gsd/reporting/server.py:343-352    formats: origin default, or an explicit subset of html, pdf, csv
local-development/gsd/reporting/server.py:380        generated_by = schedule:<name> or the viewer
local-development/gsd/reporting/runs.py:167          _render: spec, build = REGISTRY[run.report] (a KeyError for any other name: "render failed: KeyError")
local-development/gsd/reporting/runs.py:183-195      sha256 from the report; json always, then csv, html, pdf from the one Report
local-development/gsd/reporting/catalogue/common.py:383-393 assemble(): page one first (sealed=False), then the builder's sections
local-development/gsd/static/index.html:3275-3307    reportingHistoryCard: one row per run with .<format> buttons for a done run
```

So a diff that is an ordinary `Report` reaches json, csv, html and pdf through runs.py:184-195 with no code of its
own, and a `Run` with `schedule=None` is the manual tier with no code of its own.

The catalogue counts that must hold: test_reporting_server.py:801 (`len(body["reports"]) == 11`), `:1392`
(`reports_enabled == 11`); test_ui.py:8740, `:9137`, `:9342`, `:9867`.

### 2.3 The probes

Probe 1 (scratch, not in the tree) built the eleven reports over `test_report_seal.py`'s seeded snapshot and walked
each sealed section's blocks. On `43b231b6`:

```text
{'tables': 44, 'titles_with_digits': 0, 'dup_tables': 0, 'kv': 14, 'note': 10}
no section holds two tables with one (title, columns)
section titles that vary: 'Membership changes, last 30 days' (groups), 'Dormant: no successful login in 90 days' (dormant-access),
  'Group: <name>', 'User (direct grants): <name>' (access-certification), 'Namespace: <ns>' (namespace-access)
no table on the seed holds a duplicate row
```

Probe 2 ran this spec's `build_diff` (§7, Block 2) over pairs of runs on that snapshot: another viewer, run id and
two minutes later (the clock unchanged for login-activity, F1's `_other_run`); two hours later; 31 days later. The
blocks reported changed, per report:

```text
report               other run   +2 h                                        +31 days
namespace-access     []          []                                          []
access-matrix        []          []                                          []
privileged-access    []          []                                          []
binding-findings     []          []                                          []
users                []          []                                          []
access-certification []          []                                          []
groups               []          []                                          Summary/Groups, Membership changes…/Changes (8 removed, 1 added)
login-activity       []          Summary/Window (2 removed, 2 added)         + Per user/Users, Rejected, Attempts… (9 removed, 2 added)
dormant-access       []          []                                          []
groupsync-health     []          Summary/Pipeline, GroupSync CRs/CRs (2, 2)  the same
compliance-snapshot  []          Key figures/Sync pipeline (1, 1)            + Key figures/Directory and users (2, 2)
```

What it settles: the six clock-free reports diff to "No change" over one snapshot at any clock; the five that read
the clock (SPEC_F1's list) diff to exactly the blocks computed against it, and to nothing else. dormant-access did
not move on this seed at +31 days; SPEC_F1's review measured it moving with `dormant_days=1` and a login on the cutoff.

### 2.4 What `DESIGN_reporting_output_and_delivery.md` §1 and §3 say that no longer holds

| The design doc | `43b231b6` |
|---|---|
| §1: formats ⊆ {html,pdf} | Origin defaults (#149) and `csv` (#106): server.py:343-352 |
| §1: the canonical `.json` is the report | `.json` = canonical + page one + run facts; the hash covers the sealed sections only (#270, model.py:99-129) |
| §3.2: `_tables` reads every section's tables | It would read page one, whose run id and clock differ on every run, so "No change" could never be reported (the issue's "Blocked in practice by #270"). §3.2 reads `sealed` sections only |
| §3.2: tables keyed by "section — title", rows as a SET of `str` cells | Keyed by section, kind, title and columns (§3.1); rows as a MULTISET of JSON-typed rows, so `1` and `"1"` differ and a duplicate counts |
| §3.2: only tables compared | Key-value lists and notes are data too (login-activity's `Window` is a list, probe 2); all three kinds are compared |
| §3.2: "`report-diff` is added to the catalogue as a report that is not offered a param form" | Contradicts its own "stays out of the catalogue"; the issue settles it: out of `REGISTRY` (T108-7) |
| §3.1: "the Recent-runs table" | Now the Report history (#221) and the Library (#229) |

## 2a. Alternatives considered

| Option | Cost here | Decision |
|---|---|---|
| A. Match blocks by title alone | Two blocks with one title in a section (none today) would merge; a kv and a table of one title would collide | Rejected |
| B. Match by (section, kind, title, columns, occurrence) | A renamed title or a new column reads as a block removed and one added | **Chosen**: what changed is shown, nothing is guessed |
| C. Keyed rows, per-cell "changed" (daff's `->`) | Needs a key per table in eleven builders; the model has none | Out of scope (v1); the issue's choice |
| D. Rows as a set of `str` cells (the design doc) | `1` and `"1"` equal; duplicates collapse | Rejected |
| E. Rows as a multiset of canonical JSON | — | **Chosen** |
| F. Compare the whole `.json` | Page one and the run facts differ on every pair | Rejected (F1) |
| G. A new `Run` field for base and head | A manifest key every reader must learn | Rejected: `params` already carries a run's inputs and is in the record, the API and page one |

## 3. The design

### 3.1 Row identity and block matching

A block of a sealed section is matched by `(section title, kind, block title, columns, occurrence)`: a `Table` by
its own columns; a `KeyValues` as a two-column block (`key`, `value`) of its items; a section's `Note`s together as
one block `Notes` (`level`, `note`). The occurrence numbers blocks with one key in order, so two are never merged.
A row is the whole row as canonical JSON; rows are counted as a multiset: a row in the base m times and the head n
times is removed max(m−n, 0) times and added max(n−m, 0) times. A changed cell is one row removed and one added. A
block or a section on one side only has every row added (or removed). Reason: every match is exact and every
difference is shown; nothing is inferred (§2a).

### 3.2 The sealed data only

`build_diff` reads each `.json`'s `sections` whose `sealed` is true, the same set `canonical()` hashes. Page one
(who, when, run id, release, the snapshot's age) is never compared, so two runs over one snapshot diff to "No
change" for the six clock-free reports (T108-2). A `.json` with no `sealed_provenance` was written before 4.1.0,
when page one was inside the data: refused, the run failed with that sentence (T108-6). Reason: SPEC_F1; a diff
that always reports page one cannot say "No change".

### 3.3 The clock-reading reports

login-activity, groups, dormant-access, groupsync-health and compliance-snapshot compute values against the
generation clock (SPEC_F1, note 1). A diff of two of their runs over one snapshot shows exactly those blocks when
the clock moved enough to change them (§2.3, probe 2), and nothing else (T108-3 pins the two-hour case). The diff
says what moved; it does not hide it. Reason: the window a report states is part of what it asserts.

### 3.4 What a diff run is

A `POST /report/api/runs` with `report: "report-diff"`, `cluster`, and `params: {base, head}`, handled before the
`REGISTRY` lookup in `create_run` and in the worker; `REGISTRY` is untouched, so the catalogue stays eleven. The
stored `params` become `{report, base, head, base_sha256, head_sha256}`. The diff is a `Report` named
`report-diff`, titled `Changes in <title>`: page one (`sealed=False`: generated at, by, run id, release); `Inputs`
(the two runs' ids, sha256s, generation times, snapshots and parameters, and a note on the row rule; a warning when
the parameters differ or either run was truncated); `Summary` (one row per changed block, or "No change"); then one
section per changed block holding `Removed` and `Added` tables with the block's columns. `totals` counts blocks
changed, rows removed and rows added. It renders through the ordinary json/html/pdf/csv path with no code of its
own (T108-4). Reason: the issue; evidence of a comparison is itself evidence.

### 3.5 Refusals, and who may ask

422 at the request: params other than exactly `base` and `head`; a base or head unknown (or pruned: prune removes
the record), not `done`, itself a diff, or without its `.json` on disk; base equal to head; base and head of
different reports or clusters; a `cluster` other than theirs; a `schedule` or a `clusters` list, or no `cluster`
(T108-5). At render, a base or head pruned since the request, or whose `.json` no longer carries the sha256
recorded at the request, fails the diff run with a sentence and touches no other run (T108-6). Who: the same
principal as any run, a wide-tier ticket or the service token (server.py's `principal`). Reason: refuse early what
can be known at the request; the worker belts what can change after it.

### 3.6 Retention: the manual tier

A diff has no schedule, so `_retention` ranks it with the manual runs: `reporting.retention.manual.days` and
`maxRuns`, no new rule (T108-4 reads `retained_by: manual:…`). A scheduled run's standing is unchanged by a diff
(T108-8). A diff does take one manual slot, as any manual run does (open question 2). A diff outlives its inputs
when they are pruned first: it carries their ids and sha256s, so it still says what it compared.

### 3.7 The audit trail

The record (`GET /report/api/runs/<id>`) carries `params.base`, `params.head` and both sha256s; the diff's own
sha256 covers them (they are `params`, sealed) and the `Inputs` table. Two diffs of one pair hash the same (T108-4),
because the run facts are on page one. Reason: PROV-O's `wasDerivedFrom`, held by the seal.

### 3.8 The page (no blocks yet: Orchestrator's notes 1)

On the Report history (index.html `reportingHistoryCard`), a done run whose report is not `report-diff` gets a
`Diff vs…` button beside its artefacts. Clicking it asks the service for `GET /report/api/runs?report=<r>&cluster=<c>
&status=done`, keeps the runs older than this one, and shows a picker under the table (requested at, sha256's first
twelve, by), with "No earlier finished run of <r> on <c>" when there is none. Generate posts the diff with the
form's default formats and refreshes the history; the diff run is a row like any other, with its `.html`, `.pdf`,
`.json` (and `.csv` when asked) buttons from `run.formats` (index.html:3284). The picker's state lives in `view`, so
a history poll's repaint keeps it (F2's review lesson). The Library lists the catalogue's reports and does not list
diffs (not measured: the implementing pull request checks its grouping with a diff run present).

### 3.9 What does not change, and the test that holds it

| Must not change | Held by |
|---|---|
| The catalogue of eleven | T108-7; test_reporting_server.py:801, `:1392`; test_ui.py:8740, `:9137`, `:9342`, `:9867` (unchanged, run in §4.3) |
| The stored base and head runs | T108-4 compares every file of both run directories before and after |
| The one-write contract | No route is added; `TestItsOwnContract` passes unchanged (§4.3) |
| Retention for existing runs | T108-8; no block touches `artifacts.py` beyond `exists()` |
| The other formats' bytes and the seal of an ordinary run | No block touches `model.py` or a renderer; `test_report_seal.py`, `test_report_csv.py` pass unchanged |

### 3.10 Safety budget

No RBAC, value key, migration or new route. A diff reads two files the service wrote and writes one run directory
of its own. Zero existing artefacts rewritten.

## 4. Tests

### 4.1 One test per Definition-of-Done item

`local-development/tests/test_report_diff.py` (Block 7).

| ID | Test | Definition-of-Done item |
|---|---|---|
| T108-1 | `test_t108_1_rows_added_removed_and_no_change` | `build_diff` reports added rows, removed rows, and "No change" for identical data |
| T108-2 | `test_t108_2_two_runs_over_one_snapshot_diff_to_no_change` (six) | Two runs over one snapshot diff to "No change" |
| T108-3 | `test_t108_3_a_clock_reading_report_shows_what_the_clock_moved` (five) | What a diff of a clock-reading report shows |
| T108-4 | `test_t108_4_a_stored_diff_seals_renders_and_leaves_its_inputs` | A stored diff seals and renders in every format; the record; the inputs untouched; manual tier |
| T108-5 | `test_t108_5_refusals` (nine cases) | A mismatched, unfinished, unknown or pruned base/head is refused with 422; a diff of a diff |
| T108-6 | `test_t108_6_the_worker_refuses_an_input_that_changed_or_predates_the_seal` | The worker's belt |
| T108-7 | `test_t108_7_the_catalogue_stays_eleven` | The catalogue still lists 11 |
| T108-8 | `test_t108_8_a_diff_leaves_scheduled_retention_alone` | Retention for existing runs |
| T108-9 | the "Diff vs…" browser test | The page (Orchestrator's notes 1: not written) |

### 4.2 Each test fails without the change, and why

Run on a clean `43b231b6` with only Block 7's file added (§4.3):

- T108-1, T108-2, T108-3: `ModuleNotFoundError: No module named 'gsd.reporting.diff'`.
- T108-4, T108-5: the diff request answers `404 unknown report 'report-diff'` (server.py:321-322).
- T108-6: `ModuleNotFoundError` (it imports `build_diff_run`).
- T108-7: passes on both trees: it guards the catalogue.
- T108-8: passes on both trees (on main its diff request is a 404 it does not assert): it guards the scheduled
  run's standing.

### 4.3 The proof

The blocks checked against a clean detached worktree of `43b231b6`, then applied to it, with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` from its `local-development` and the repository's venv (Python 3.14).
Recorded:

```text
$ python local-development/apply-spec-blocks.py docs/specs/SPEC_F3_report_diff.md <clean 43b231b6>
16 blocks check out across 13 files

before the blocks (Block 7's file alone added to the clean tree):
  tests/test_report_diff.py: 15 failed, 2 passed in 6.15s
    T108-1, T108-2 (6), T108-3 (5), T108-6: ModuleNotFoundError: No module named 'gsd.reporting.diff'
    T108-4: AssertionError: {"detail":"unknown report 'report-diff'"}; assert 404 == 202
    T108-5: KeyError: 'id' (the diff it needs for the diff-of-a-diff case is a 404)
    T108-7, T108-8: passed (the guards)

$ python local-development/apply-spec-blocks.py docs/specs/SPEC_F3_report_diff.md <clean 43b231b6> --apply
$ git diff --stat        (diff.py and test_report_diff.py are new)
 charts/group-sync-dashboard/Chart.yaml       |  7 +++--
 charts/group-sync-dashboard/README.md        |  4 ++-
 docs/CHANGELOG.md                            |  9 +++++++
 docs/DESIGN_reporting_output_and_delivery.md |  4 ++-
 docs/specs/SPEC_C3_reporting_microservice.md |  3 +++
 local-development/API.md                     |  2 +-
 local-development/gsd/__init__.py            |  2 +-
 local-development/gsd/reporting/artifacts.py |  4 +++
 local-development/gsd/reporting/runs.py      | 40 ++++++++++++++++------------
 local-development/gsd/reporting/server.py    | 25 ++++++++++++-----
 local-development/pyproject.toml             |  2 +-
 11 files changed, 71 insertions(+), 31 deletions(-)
 (runs.py's 40 lines are the existing build re-indented under the `else`; no change to model.py or any renderer)

after the blocks:
  tests/test_report_diff.py: 17 passed in 3.91s
  tests/test_reporting_*.py tests/test_report_seal.py tests/test_report_csv.py tests/test_chart_versions.py
  tests/test_kyverno.py: 359 passed in 37.41s
  this spec's branch (the spec, its index row, the index test at 55):
  tests/test_specs_index.py tests/test_docs_citations.py: 1939 passed, 18 skipped in 18.55s
the browser suite: not run (no page blocks, Orchestrator's notes 1); the full hermetic suite: not run (the budget)
```

## 5. On the lab (the implementing pull request)

After the image is deployed through the release's values file and pipeline:

1. As a wide-tier viewer, generate `namespace-access` twice on `crc-local` with the same namespaces, then request a
   diff of the two (the page's action, or `POST /report/api/runs` with `report-diff`). Pass: the diff is done, its
   `Summary` says "No change", its record carries both ids and sha256s.
2. Plant a RoleBinding in one of those namespaces; after the next binding refresh (hourly by default since #368)
   generate `namespace-access` again and diff it against the second run. Pass: one block changed, one row added:
   the planted binding. Delete the planted binding.
3. Download the diff as `.html`, `.pdf`, `.csv` and `.json`. Pass: every `X-GSD-Report-SHA256` equals the record's.

Evidence under `reports/<date>_<slug>/` and on #108, pinned to the full merge sha. This spec makes no lab write.

## 6. What an operator sees, and what it costs

A `report-diff` row in the Report history, like any run, with its downloads; a document titled `Changes in <report>`
whose `Inputs` names the two runs, whose `Summary` lists each changed block with its counts (or "No change"), and
then a `Removed` and an `Added` table per changed block. A diff of a clock-reading report two hours apart shows the
window or state that moved (§2.3). Cost: one module of about 150 lines, two branches, one store method; no RBAC,
value key, migration, route or runtime cost for anyone who does not ask for a diff.

## 7. Implementation blocks

### Block 1 — `local-development/gsd/reporting/artifacts.py`: `exists()`, so a request can refuse a run whose `.json` is gone

<!-- block: local-development/gsd/reporting/artifacts.py | edit -->
```python
    def get(self, run_id: str) -> Run | None:
```

```python
    def exists(self, run_id: str, fmt: str) -> bool:
        """Whether the run's artefact is on disk: a diff refuses a run whose .json is gone (#108)."""
        return (self._dir(run_id) / f"report.{fmt}").is_file()

    def get(self, run_id: str) -> Run | None:
```

### Block 2 — `local-development/gsd/reporting/diff.py`: the diff

<!-- block: local-development/gsd/reporting/diff.py | create -->
```python
"""What changed between two runs of one report on one cluster (#108, docs/specs/SPEC_F3_report_diff.md).

A diff reads two stored `.json` artefacts, never the snapshot, and compares their SEALED data only
(SPEC_F1): page one states the run, so it is left out, and two runs over one snapshot diff to
"No change" unless the report's own data reads the generation clock. Every table, key-value list
and the notes of each sealed section are compared as a multiset of whole rows: a row present in
the head and not the base is added, the reverse is removed, and a changed cell is one row removed
and one added (v1). The result is an ordinary `Report` named `report-diff`, sealed, stored and
rendered like any other run, and kept out of the catalogue (`REGISTRY`).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from .. import __version__
from .artifacts import ArtifactStore, Run
from .catalogue.common import ValidationError
from .config import ReportSettings
from .model import KeyValues, Note, Report, Section, Table, iso

#: The run name a diff is requested and stored under. Not a catalogue entry, so the catalogue stays eleven.
DIFF_REPORT = "report-diff"
#: The wording of a diff with nothing to show; the page and the walk look for it.
NO_CHANGE = "No change"


def diff_params(store: ArtifactStore, params: dict, cluster: str | None) -> dict:
    """The diff's parameters, checked at request time: two known, finished runs of one report on the
    named cluster, neither a diff, both with their `.json` still on disk. The answer records both
    sha256s beside the ids, so the stored run says which evidence it compared. ValidationError → 422."""
    if set(params) != {"base", "head"}:
        raise ValidationError("a report-diff names exactly two runs: params {base, head}")
    base, head = store.get(str(params["base"])), store.get(str(params["head"]))
    for side, run in (("base", base), ("head", head)):
        if run is None:
            raise ValidationError(f"{side} run {params[side]!r} is unknown or was pruned")
        if run.status != "done":
            raise ValidationError(f"{side} run {run.id} is {run.status}, not finished")
        if run.report == DIFF_REPORT:
            raise ValidationError(f"{side} run {run.id} is itself a diff")
        if not store.exists(run.id, "json"):
            raise ValidationError(f"{side} run {run.id} no longer has its .json")
    if base.id == head.id:
        raise ValidationError("base and head are the same run")
    if base.report != head.report or base.cluster != head.cluster:
        raise ValidationError(f"base is {base.report} on {base.cluster} and head is {head.report} on {head.cluster}: "
                              "a diff compares one report on one cluster")
    if cluster != head.cluster:
        raise ValidationError(f"the diff names cluster {cluster!r}; its runs are on {head.cluster!r}")
    return {"report": head.report, "base": base.id, "head": head.id,
            "base_sha256": base.sha256, "head_sha256": head.sha256}


def _blocks(doc: dict) -> dict[tuple, tuple[list, list]]:
    """Every comparable block of the sealed sections, keyed by where it sits and what it holds:
    (section title, kind, block title, columns, occurrence). The occurrence keeps two blocks with one
    key apart; a block's rows are its table rows, its key-value pairs, or the section's notes."""
    out: dict[tuple, tuple[list, list]] = {}
    for section in doc["sections"]:
        if not section["sealed"]:
            continue
        notes = [[b["level"], b["text"]] for b in section["blocks"] if b["kind"] == "note"]
        found = [("note", "Notes", ["level", "note"], notes)] if notes else []
        for b in section["blocks"]:
            if b["kind"] == "table":
                found.append(("table", b["title"], b["columns"], b["rows"]))
            elif b["kind"] == "kv":
                found.append(("kv", b["title"], ["key", "value"], [list(item) for item in b["items"]]))
        for kind, title, columns, rows in found:
            key = (section["title"], kind, title, tuple(columns))
            n = sum(1 for k in out if k[:4] == key)
            out[(*key, n)] = (columns, rows)
    return out


def _row_counts(rows: list) -> Counter:
    # A row's identity is the whole row, written canonically, so 1 and "1" stay different values.
    return Counter(json.dumps(row, sort_keys=True, default=str) for row in rows)


def _rows(counts: Counter) -> list:
    # A row removed (or added) twice is listed twice: the multiset keeps duplicate rows honest.
    return [json.loads(row) for row in sorted(counts.elements())]


def build_diff(base: dict, head: dict, *, run_id: str, now: datetime, generated_by: str, generated_by_note: str,
               settings: ReportSettings) -> Report:
    """The diff of two stored `.json` documents as a sealed Report. Deterministic in its inputs: two
    diffs of one pair hash the same, because the run facts are on page one, which is not sealed."""
    for side, doc in (("base", base), ("head", head)):
        if "sealed_provenance" not in doc:
            raise ValidationError(f"the {side} run {doc.get('run_id')} was written before 4.1.0 (SPEC_F1): its page one "
                                  "is inside its data, so it cannot be compared")
    b, h = _blocks(base), _blocks(head)
    summary, sections, added_total, removed_total = [], [], 0, 0
    for key in [*b, *(k for k in h if k not in b)]:          # the base's order, then blocks new in the head
        columns = (h.get(key) or b[key])[0]
        before, after = _row_counts(b.get(key, (None, []))[1]), _row_counts(h.get(key, (None, []))[1])
        removed, added = before - after, after - before
        if not removed and not added:
            continue
        where = key[0] if key[1] == "note" else f"{key[0]} — {key[2]}"
        summary.append([key[0], key[2], sum(removed.values()), sum(added.values())])
        removed_total, added_total = removed_total + sum(removed.values()), added_total + sum(added.values())
        sections.append(Section(where, [Table("Removed", columns, _rows(removed), empty_text="none removed"),
                                        Table("Added", columns, _rows(added), empty_text="none added")]))
    inputs = Table("The two runs", ["side", "run id", "sha256", "generated at", "snapshot", "parameters"], [
        [side, doc["run_id"], doc["sha256"], doc["generated_at"], doc["sealed_provenance"].get("snapshot_stamp"),
         ", ".join(f"{k}={v}" for k, v in sorted(doc["params"].items())) or "none"]
        for side, doc in (("base", base), ("head", head))])
    notes = [Note("Rows are compared whole: a changed cell shows as one row removed and one added. Only the sealed "
                  "data is compared, so who ran a report and when never shows as a change.", "note")]
    if base["params"] != head["params"]:
        notes.append(Note("The two runs were made with different parameters, so a difference may be the question "
                          "asked rather than the cluster.", "warning"))
    if base["truncated"] or head["truncated"]:
        notes.append(Note("At least one run cut a table at its row limit; rows past the cut are not compared.", "warning"))
    overview = [Table("Changes per block", ["section", "block", "removed", "added"], summary, empty_text=NO_CHANGE)]
    if not summary:
        overview.append(Note(f"{NO_CHANGE}: every table, list and note in the sealed data is the same in both runs.", "note"))
    page_one = Section("Provenance and coverage", [KeyValues("Run", [
        ("Generated at (UTC)", iso(now)), ("Generated by", f"{generated_by} ({generated_by_note})"), ("Run id", run_id),
        ("Report service", f"{__version__} @ {settings.git_commit}")])], sealed=False)
    return Report(
        name=DIFF_REPORT, title=f"Changes in {head['title']}", cluster=head["cluster"], api_url=head["api_url"],
        generated_at=iso(now), generated_by=generated_by, generated_by_note=generated_by_note, run_id=run_id,
        params={"report": head["name"], "base": base["run_id"], "head": head["run_id"],
                "base_sha256": base["sha256"], "head_sha256": head["sha256"]},
        coverage={}, provenance={"marking": settings.marking, "report_service_version": __version__,
                                 "commit": settings.git_commit},
        totals={"blocks_changed": len(summary), "rows_removed": removed_total, "rows_added": added_total},
        truncated=bool(base["truncated"] or head["truncated"]), include_members=bool(head["include_members"]),
        sections=[page_one, Section("Inputs", [inputs, *notes]), Section("Summary", overview), *sections],
    ).seal()


def build_diff_run(store: ArtifactStore, run: Run, settings: ReportSettings, now: datetime) -> Report:
    """The worker's step: read both stored `.json` files and check each still carries the sha256 the
    request recorded, then build. A run pruned or rewritten since the request fails this run, never
    another one."""
    docs = []
    for side in ("base", "head"):
        data = store.read(run.params[side], "json")
        if data is None:
            raise ValidationError(f"the {side} run {run.params[side]} was pruned before this diff rendered")
        doc = json.loads(data)
        if doc.get("sha256") != run.params[f"{side}_sha256"]:
            raise ValidationError(f"the {side} run's .json no longer carries the sha256 recorded at request time")
        docs.append(doc)
    return build_diff(*docs, run_id=run.id, now=now, generated_by=run.generated_by,
                      generated_by_note=run.generated_by_note, settings=settings)
```

### Block 3 — `local-development/gsd/reporting/server.py`: the import

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
from .config import ReportSettings, load_report_settings, retention_overrides
```

```python
from .config import ReportSettings, load_report_settings, retention_overrides
from .diff import DIFF_REPORT, diff_params
```

### Block 4 — `local-development/gsd/reporting/server.py`: `create_run` takes `report-diff` before the catalogue

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
        if body.report not in REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown report {body.report!r}")
        if body.report not in settings.enabled_reports:
            raise HTTPException(status_code=404, detail=f"report {body.report!r} is not enabled on this deployment")
        spec, _ = REGISTRY[body.report]
        try:
            params = validate_params(spec, body.params)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
```

```python
        if body.report == DIFF_REPORT:
            # A diff of two stored runs (#108), checked before the catalogue it is not part of: one named cluster,
            # never a schedule, and its base and head refused here (422) rather than failed in the worker.
            if body.schedule or body.clusters is not None or body.cluster is None:
                raise HTTPException(status_code=422, detail="a report-diff names one cluster and no schedule")
            try:
                params = diff_params(store, body.params, body.cluster)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        elif body.report not in REGISTRY:
            raise HTTPException(status_code=404, detail=f"unknown report {body.report!r}")
        elif body.report not in settings.enabled_reports:
            raise HTTPException(status_code=404, detail=f"report {body.report!r} is not enabled on this deployment")
        else:
            spec, _ = REGISTRY[body.report]
            try:
                params = validate_params(spec, body.params)
            except ValidationError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
```

### Block 5 — `local-development/gsd/reporting/runs.py`: the import

<!-- block: local-development/gsd/reporting/runs.py | edit -->
```python
from .config import ReportSettings, retention_overrides
```

```python
from .config import ReportSettings, retention_overrides
from .diff import DIFF_REPORT, build_diff_run
```

### Block 6 — `local-development/gsd/reporting/runs.py`: the worker builds a diff before the catalogue lookup

<!-- block: local-development/gsd/reporting/runs.py | edit -->
```python
        try:
            spec, build = REGISTRY[run.report]
            params = validate_params(spec, run.params)
            path = newest_snapshot(self.settings.snapshot_dir)
            with Snapshot(path) as snap:
                info = snap.info()
                cluster = snap.cluster(run.cluster)
                if cluster is None:
                    raise ValidationError(f"unknown cluster {run.cluster!r} in the snapshot")
                now = self._clock()
                ctx = RunContext(settings=self.settings, cluster=cluster, now=now, run_id=run.id,
                                 generated_by=run.generated_by, generated_by_note=run.generated_by_note,
                                 snapshot_stamp=info.stamp, snapshot_age_seconds=info.age_seconds(now),
                                 schema_version=info.schema_version,
                                 namespace_selector_labels=self.settings.namespace_selector_labels)
                from .catalogue.common import assemble
                report = assemble(spec, snap, ctx, params, build(snap, ctx, params))
            run.snapshot_stamp, run.sha256 = info.stamp, report.sha256
```

```python
        try:
            if run.report == DIFF_REPORT:
                # Two stored runs, not the snapshot (#108): checked before the catalogue it is not part of.
                report, stamp = build_diff_run(self.store, run, self.settings, self._clock()), None
            else:
                spec, build = REGISTRY[run.report]
                params = validate_params(spec, run.params)
                path = newest_snapshot(self.settings.snapshot_dir)
                with Snapshot(path) as snap:
                    info = snap.info()
                    cluster = snap.cluster(run.cluster)
                    if cluster is None:
                        raise ValidationError(f"unknown cluster {run.cluster!r} in the snapshot")
                    now = self._clock()
                    ctx = RunContext(settings=self.settings, cluster=cluster, now=now, run_id=run.id,
                                     generated_by=run.generated_by, generated_by_note=run.generated_by_note,
                                     snapshot_stamp=info.stamp, snapshot_age_seconds=info.age_seconds(now),
                                     schema_version=info.schema_version,
                                     namespace_selector_labels=self.settings.namespace_selector_labels)
                    from .catalogue.common import assemble
                    report = assemble(spec, snap, ctx, params, build(snap, ctx, params))
                stamp = info.stamp
            run.snapshot_stamp, run.sha256 = stamp, report.sha256
```

### Block 7 — `local-development/tests/test_report_diff.py`: the tests

<!-- block: local-development/tests/test_report_diff.py | create -->
```python
"""What changed between two runs (docs/specs/SPEC_F3_report_diff.md, #108): a `report-diff` run compares the
sealed data of two stored runs of one report on one cluster, row by row, and is itself a sealed, stored run that
renders through the ordinary renderers; the catalogue, the stored inputs and the retention of other runs stay as
they are."""
from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import Run
from gsd.reporting.catalogue import REGISTRY
from gsd.reporting.config import ReportSettings
from reporting_seed import CLUSTER, NOW
from test_report_seal import CLOCK_DERIVED, _other_run, _run, snap  # noqa: F401 — `snap` is a fixture
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

DIFF = "report-diff"
#: What the five clock-reading reports show when the clock moves two hours over one snapshot (measured, §2.3).
CLOCK_MOVED = {
    "login-activity": {("Summary", "Window")},
    "groups": set(),
    "dormant-access": set(),
    "groupsync-health": {("GroupSync CRs", "CRs"), ("Summary", "Pipeline")},
    "compliance-snapshot": {("Key figures", "Sync pipeline")},
}


def _build(base: dict, head: dict):
    from gsd.reporting.diff import build_diff   # imported here: before SPEC_F3 the module does not exist
    return build_diff(base, head, run_id="20260906T130000.000000Z-ef56", now=NOW, generated_by="alice",
                      generated_by_note="proxy-verified", settings=ReportSettings())


def _doc(report) -> dict:
    return json.loads(report.to_json())


def _changed(diff) -> set:
    summary = next(s for s in diff.sections if s.title == "Summary").blocks[0]
    return {(row[0], row[1]) for row in summary.rows}


def test_t108_1_rows_added_removed_and_no_change(snap):  # noqa: F811
    """A row only in the head is added, one only in the base removed, a changed cell is one of each, a duplicate
    row counts twice, a section on one side only is all added; identical data is "No change". Without SPEC_F3:
    ModuleNotFoundError, gsd.reporting.diff."""
    base = _doc(_run(snap, "groups"))
    same = _build(base, copy.deepcopy(base))
    assert _changed(same) == set() and same.totals == {"blocks_changed": 0, "rows_removed": 0, "rows_added": 0}
    assert any(b.kind == "note" and b.text.startswith("No change:") for s in same.sections for b in s.blocks)
    head = copy.deepcopy(base)
    inventory = next(s for s in head["sections"] if s["title"] == "Inventory")["blocks"][0]
    gone, changed = inventory["rows"][0], inventory["rows"][1]
    inventory["rows"] = [[changed[0], "another-provider", *changed[2:]], *inventory["rows"][2:], inventory["rows"][2]]
    head["sections"].append({"title": "New section", "sealed": True, "page_break": False,
                             "blocks": [{"kind": "kv", "title": "Facts", "items": [["k", "v"]]}]})
    diff = _build(base, head)
    blocks = {s.title: s.blocks for s in diff.sections}
    removed, added = blocks["Inventory — Groups"]
    assert removed.rows == sorted([gone, changed], key=lambda r: json.dumps(r, sort_keys=True))
    assert added.rows == sorted([[changed[0], "another-provider", *changed[2:]], inventory["rows"][-1]],
                                key=lambda r: json.dumps(r, sort_keys=True))
    assert blocks["New section — Facts"][1].rows == [["k", "v"]] and blocks["New section — Facts"][0].rows == []
    assert diff.totals == {"blocks_changed": 2, "rows_removed": 2, "rows_added": 3}


@pytest.mark.parametrize("name", sorted(set(REGISTRY) - CLOCK_DERIVED))
def test_t108_2_two_runs_over_one_snapshot_diff_to_no_change(snap, name):  # noqa: F811
    """The six clock-free reports: another viewer, run id and minute, one snapshot: nothing changed, because page
    one (who and when) is not sealed data. Without SPEC_F3: ModuleNotFoundError."""
    diff = _build(_doc(_run(snap, name)), _doc(_other_run(snap, name)))
    assert _changed(diff) == set(), name


@pytest.mark.parametrize("name", sorted(CLOCK_DERIVED))
def test_t108_3_a_clock_reading_report_shows_what_the_clock_moved(snap, name):  # noqa: F811
    """The five reports that read the generation clock: two hours apart over one snapshot, the diff shows exactly
    the blocks computed against the clock (CLOCK_MOVED, measured), and nothing else. Without SPEC_F3:
    ModuleNotFoundError."""
    later = _run(snap, name, now=NOW + timedelta(hours=2), run_id="20260906T140000.000000Z-cd34")
    assert _changed(_build(_doc(_run(snap, name)), _doc(later))) == CLOCK_MOVED[name], name


def _done(client, report="groups", cluster=CLUSTER, headers=None, **body) -> dict:
    r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": report, "cluster": cluster, **body},
                    headers=headers or _viewer())
    assert r.status_code == 202, r.text
    run = _wait_done(client, r.json()["id"], headers or _viewer())
    assert run["status"] == "done", run.get("error")
    return run


def _diff(client, base: str, head: str, **body):
    return client.post(f"{REPORT_PREFIX}/api/runs", json={"report": DIFF, "cluster": CLUSTER,
                                                          "params": {"base": base, "head": head}, **body},
                       headers=_viewer())


def _files(app, run_id: str) -> dict:
    d = Path(app.state.store.root) / run_id
    return {p.name: p.read_bytes() for p in d.iterdir()}


def test_t108_4_a_stored_diff_seals_renders_and_leaves_its_inputs(service):  # noqa: F811
    """A diff run stores and serves json, html, pdf and csv with its own seal; its record names both runs and
    both sha256s; two diffs of one pair hash the same; it is a manual run; the two inputs' files are byte-equal
    afterwards. Without SPEC_F3: 404 unknown report 'report-diff'."""
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    before = {r: _files(app, r) for r in (base["id"], head["id"])}
    r = _diff(client, base["id"], head["id"], formats=["html", "pdf", "csv"])
    assert r.status_code == 202, r.text
    run = _wait_done(client, r.json()["id"], _viewer())
    assert run["status"] == "done", run.get("error")
    assert run["report"] == DIFF and run["schedule"] is None and run["retained_by"].startswith("manual:")
    assert run["params"] == {"report": "groups", "base": base["id"], "head": head["id"],
                             "base_sha256": base["sha256"], "head_sha256": head["sha256"]}
    assert set(run["bytes"]) == {"json", "html", "pdf", "csv"}
    for fmt in ("json", "html", "pdf", "csv"):
        a = client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": fmt}, headers=_viewer())
        assert a.status_code == 200 and a.headers["x-gsd-report-sha256"] == run["sha256"], fmt
    doc = json.loads(client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": "json"},
                                headers=_viewer()).content)
    assert doc["name"] == DIFF and doc["sha256"] == run["sha256"] and doc["totals"]["blocks_changed"] == 0
    clock["now"] += timedelta(minutes=1)
    again = _wait_done(client, _diff(client, base["id"], head["id"], formats=["html"]).json()["id"], _viewer())
    assert again["sha256"] == run["sha256"], "two diffs of one pair are the same evidence"
    assert {r: _files(app, r) for r in (base["id"], head["id"])} == before, "a diff never rewrites its inputs"


def test_t108_5_refusals(service):  # noqa: F811
    """422 for an unknown base, an unfinished one, another report, another cluster, a pruned .json, a diff of a
    diff, one run twice, a schedule and stray parameters. Without SPEC_F3: every request is a 404."""
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    other = _done(client, report="users")
    store = app.state.store
    queued = store.create(Run(id="20260906T000000.000000Z-0000", report="groups", cluster=CLUSTER, params={},
                              formats=[], generated_by="root", generated_by_note="", schedule=None,
                              requested_at="2026-09-06T00:00:00Z"))
    elsewhere = store.create(Run(**{**store.get(base["id"]).public(), "id": "20260906T000001.000000Z-0001",
                                    "cluster": "another-cluster"}))
    store.write(elsewhere.id, "json", store.read(base["id"], "json"))
    cases = {
        "unknown": _diff(client, "20200101T000000.000000Z-dead", head["id"]),
        "queued": _diff(client, queued.id, head["id"]),
        "report": _diff(client, other["id"], head["id"]),
        "cluster": _diff(client, elsewhere.id, head["id"]),
        "same": _diff(client, head["id"], head["id"]),
        "schedule": client.post(f"{REPORT_PREFIX}/api/runs", headers=SERVICE, json={
            "report": DIFF, "cluster": CLUSTER, "schedule": "nightly", "params": {"base": base["id"], "head": head["id"]}}),
        "params": client.post(f"{REPORT_PREFIX}/api/runs", headers=_viewer(), json={
            "report": DIFF, "cluster": CLUSTER, "params": {"base": base["id"], "head": head["id"], "x": 1}}),
    }
    diff = _wait_done(client, _diff(client, base["id"], head["id"]).json()["id"], _viewer())
    cases["diff of a diff"] = _diff(client, diff["id"], head["id"])
    (Path(store.root) / base["id"] / "report.json").unlink()
    cases["pruned"] = _diff(client, base["id"], head["id"])
    for case, r in cases.items():
        assert r.status_code == 422, (case, r.status_code, r.text)


def test_t108_6_the_worker_refuses_an_input_that_changed_or_predates_the_seal(service):  # noqa: F811
    """A base rewritten after the request, or a .json written before 4.1.0, fails the diff run with a sentence,
    and no other run. Without SPEC_F3: 404 at the request."""
    from gsd.reporting.diff import build_diff_run
    from gsd.reporting.catalogue.common import ValidationError
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    store = app.state.store
    run = Run(id="20260906T000002.000000Z-0002", report=DIFF, cluster=CLUSTER, formats=[], generated_by="root",
              generated_by_note="", schedule=None, requested_at="2026-09-06T00:00:02Z",
              params={"report": "groups", "base": base["id"], "head": head["id"],
                      "base_sha256": "0" * 64, "head_sha256": head["sha256"]})
    with pytest.raises(ValidationError, match="sha256 recorded"):
        build_diff_run(store, run, ReportSettings(), NOW)
    old = json.loads(store.read(base["id"], "json"))
    del old["sealed_provenance"]
    with pytest.raises(ValidationError, match="before 4.1.0"):
        _build(old, json.loads(store.read(head["id"], "json")))


def test_t108_7_the_catalogue_stays_eleven(service):  # noqa: F811
    """`report-diff` is not a catalogue entry: the catalogue lists eleven and the status counts eleven. Passes before
    and after SPEC_F3: it guards the issue's "Must not change"."""
    client, _, _ = service
    assert DIFF not in REGISTRY and len(REGISTRY) == 11
    names = [r["name"] for r in client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()["reports"]]
    assert len(names) == 11 and DIFF not in names
    assert client.get(f"{REPORT_PREFIX}/api/status", headers=_viewer()).json()["service"]["reports_enabled"] == 11


def test_t108_8_a_diff_leaves_scheduled_retention_alone(service):  # noqa: F811
    """A diff is a manual run: a scheduled run's standing is the same before and after one. Passes before and
    after SPEC_F3 for the scheduled run (the guard); the diff's own `manual:` standing is T108-4."""
    client, app, clock = service
    sched = _done(client, headers=SERVICE, schedule="nightly")
    clock["now"] += timedelta(minutes=1)
    manual = _done(client)
    standing = lambda: client.get(f"{REPORT_PREFIX}/api/runs/{sched['id']}", headers=_viewer()).json()["retained_by"]  # noqa: E731
    before = standing()
    _diff(client, manual["id"], _done(client)["id"])
    assert standing() == before
```

### Block 8 — `local-development/API.md`: `report-diff` on the run POST

<!-- block: local-development/API.md | edit -->
```markdown
| `POST /report/api/runs` | ticket or token | queue one run (`report`, `cluster`, `params`, `formats`); 202 with the run id — **the one write in either service's API, deliberately not on the dashboard**. `clusters: [...]` in place of `cluster` (#267) queues one run per cluster as one slot and answers `{"runs": [...]}`; a cluster the snapshot lacks fails its own run and no other |
```

```markdown
| `POST /report/api/runs` | ticket or token | queue one run (`report`, `cluster`, `params`, `formats`); 202 with the run id — **the one write in either service's API, deliberately not on the dashboard**. `clusters: [...]` in place of `cluster` (#267) queues one run per cluster as one slot and answers `{"runs": [...]}`; a cluster the snapshot lacks fails its own run and no other. `report: "report-diff"` with `params: {base, head}` (#108, not a catalogue entry) compares two finished runs of one report on the named cluster: rows removed and added per table of their sealed data, stored as a sealed manual run whose `params` record both ids and both sha256s; 422 for an unknown, unfinished, pruned or mismatched base or head, a diff of a diff, or a schedule |
```

### Block 9 — `docs/CHANGELOG.md`: the diff run

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased
```

```markdown
## Unreleased

- **What changed between two runs: `report-diff` (#108, Epic F #386, `docs/specs/SPEC_F3_report_diff.md`;
  application 4.3.0, chart 0.66.7).** `POST /report/api/runs` with `report: "report-diff"` and `params: {base, head}`
  compares two finished runs of one report on one cluster over their sealed data only (SPEC_F1): per table, list
  and the notes of each section, the rows removed and the rows added (a changed cell is one of each). Two runs over
  one snapshot diff to "No change" for the six reports that do not read the clock; for the five that do, the diff
  shows exactly the blocks computed against it. The diff is a sealed manual run, rendered in every format; its
  record names both runs and their sha256s. The catalogue stays eleven, the inputs are never rewritten, and no
  route, permission, value key or migration is added.
```

### Block 10 — `local-development/pyproject.toml`: application 4.3.0

<!-- block: local-development/pyproject.toml | edit -->
```toml
version = "4.2.0"
```

```toml
version = "4.3.0"
```

### Block 11 — `local-development/gsd/__init__.py`: application 4.3.0

<!-- block: local-development/gsd/__init__.py | edit -->
```python
__version__ = "4.2.0"
```

```python
__version__ = "4.3.0"
```

### Block 12 — `charts/group-sync-dashboard/Chart.yaml`: the chart PATCH and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# default, template logic or RBAC change.
version: 0.66.6
```

```yaml
# default, template logic or RBAC change.
# CHART 0.66.7 (2026-10-03), PATCH: appVersion moves to application 4.3.0 (below); #108, SPEC_F3. The
# README's reports paragraph names report-diff; no key, default, template or RBAC change.
version: 0.66.7
```

### Block 13 — `charts/group-sync-dashboard/Chart.yaml`: application 4.3.0

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
appVersion: "4.2.0"
```

```yaml
# 4.3.0 (2026-10-03). What changed between two runs: a report-diff run compares the sealed data of two finished runs of one report on one cluster, rows removed and added per table, stored as a sealed manual run naming both inputs and their sha256s (#108). MINOR.
appVersion: "4.3.0"
```

### Block 14 — `charts/group-sync-dashboard/README.md`: the reports paragraph names the diff

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
`reporting.*`; the refuse/derive column says what happens when switches meet.
```

```markdown
`reporting.*`; the refuse/derive column says what happens when switches meet. A `report-diff` run (#108) compares
two finished runs of one report on one cluster, rows removed and added; it is not a twelfth report, needs no
value, and is kept like any manual run (`reporting.retention.manual`).
```

### Block 15 — `docs/specs/SPEC_C3_reporting_microservice.md`: a pointer to the diff

<!-- block: docs/specs/SPEC_C3_reporting_microservice.md | edit -->
```markdown
## Design
```

```markdown
**Amendment (#108, 2026-10-03):** a `report-diff` run compares two stored runs of one report on one cluster;
it is not a catalogue entry. `docs/specs/SPEC_F3_report_diff.md`.

## Design
```

### Block 16 — `docs/DESIGN_reporting_output_and_delivery.md`: the status line

<!-- block: docs/DESIGN_reporting_output_and_delivery.md | edit -->
```markdown
renderer or its `#` label rows (SPEC_F2 §2.4, §2a).** Record: `docs/REVIEW_reporting_output_delivery.md`. Four
```

```markdown
renderer or its `#` label rows (SPEC_F2 §2.4, §2a). §3 (diffs) is built by `docs/specs/SPEC_F3_report_diff.md`
(#108), which compares the sealed sections only and keys blocks by section, kind, title and columns (SPEC_F3
§2.4).** Record: `docs/REVIEW_reporting_output_delivery.md`. Four
```
