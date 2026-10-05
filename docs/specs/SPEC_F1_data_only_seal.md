# SPEC F1 — the report seal covers the data only: page one's run facts leave the sha256 (#270)

| | |
|---|---|
| Programme | Epic F (#386), reports: honest seals, more formats, diffs and delivery. Build step 1 of 6: every later step that compares or delivers artefacts by hash reads the seal this step defines |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 4.1.0, chart 0.66.5 |
| Version note | The change is image content (the report service's model and one catalogue line), so it takes the next application MINOR, 4.1.0, and the chart PATCH that moves `appVersion`, 0.66.5 (SPEC_E5's rule, `local-development/tests/test_specs_index.py#test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`). Read on `94f5ebbb` (application 4.0.0, chart 0.66.4); the one other `specified` row, W1, holds chart 0.67.0, a MINOR, which stays above 0.66.5. The version blocks (§7, blocks 8 to 11) are written against that tree: a release that lands first makes them fail their check, and the implementing pull request then corrects them here before applying (`docs/specs/README.md`, "Implementation blocks") |
| Issue | [#270](https://github.com/ephico2real2/group-sync-dashboard/issues/270) |
| Status | released |
| Source | OB1-lite's research and specification of 2026-10-03, written before any code from the issue (its body of 2026-09-26, settled), the epic (#386) and SPEC_C3's definition of the seal. Measured on main `94f5ebbb` on this machine with the repository's venv (Python 3.14): the probe in §2.3 built all eleven reports twice over one seeded snapshot. No lab read was needed; §5 states the walk. §7's blocks were proved against a clean checkout of `94f5ebbb` (§4.3) |

## How to read this spec

The plain point first: a report's sha256 is meant to say "this is the same evidence". Today it also covers when
the report was generated, by whom, under which run id, by which release, and the chart's marking and binding
interval, because all of those are rows of page one, and page one is a section inside the hash. So two runs over
one unchanged snapshot never share a hash. This spec takes page one out of the hash, seals the few facts on it that
ARE data through their own fields, and leaves every word the reader sees where it is.

§1 is the mandate. §2 is the research: the primary sources, and the probe that measured which values move between
two runs. §2a weighs the alternatives and reconciles each external claim with this repository's code. §3 is the
design, one rule per subsection with its reason. §4 maps every Definition-of-Done item to a test and records each
one failing on a tree without the change. §5 is the walk on the lab. §6 is what an operator sees. §7 is the whole
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F1_data_only_seal.md . --apply

Line citations into the code at `94f5ebbb` are written as `file:line` in plain text inside the quoted command
output only; prose cites `path#anchor`.

## Orchestrator's notes

1. **The issue's own premise is narrower than the code.** The issue lists the run facts of page one as the only
   values that move between two runs over one snapshot. The probe in §2.3 found a fifth source: report BUILDERS
   that anchor a window or a state to the generation clock (`local-development/gsd/reporting/catalogue/common.py#window_start`
   called with `ctx.now`). Measured: with the clock two minutes apart, only login-activity's sealed data differs
   (its Window block prints `To` as the generation instant, to the second); with the clock two hours apart,
   groupsync-health and compliance-snapshot differ too (a CR's on-time/overdue state is computed against the
   clock). This spec does NOT move those anchors: the window a report states is part of what it asserts, and
   moving it to the snapshot's stamp changes the sections of five reports, which the issue lists under "Must not
   change". So the Definition of Done holds as measured: two runs over one snapshot, with the same parameters,
   hash the same for ten of the eleven reports whenever their clock-derived values coincide (always within one
   snapshot interval in the probe), and for login-activity only at the same clock; §4's T270-2 pins that limit so
   it cannot change silently. Open question 1 asks the operator whether a later step should anchor the windows to
   the snapshot's stamp.
2. **The snapshot stamp is sealed, so the hash answers "same evidence?", not "did access change?".** The issue
   proposes sealing the stamp, and this spec does, with the reason in §3.2. It follows that two snapshots of
   unchanged data hash differently, and that the old docstring's "the same data on two days hashes the same" was
   never achievable here: the coverage, which the issue requires sealed, carries the login-capture read instant
   (`local-development/gsd/reporting/catalogue/common.py#coverage`, `capture_note`), which moves on every read
   cycle. The new docstrings say what the code does. "Did anything change between Monday and Tuesday?" is
   answered by comparing the sealed sections, which is a diff, the subject of a later step of the epic, not by
   comparing two hashes.
3. **The renderer, the marking and the binding interval are run facts** (§3.3), as the mandate asked to settle.
   They stay on page one with the same words; a release, a new marking or a new interval no longer changes the
   hash of unchanged data.
4. **The index count.** The mandate expected PR #567 (A4) to make the index fifty-two. Main `94f5ebbb` does not
   carry A4: the index there says "Fifty-one", so this spec's row makes it fifty-two, and
   `local-development/tests/test_specs_index.py` moves from 51 to 52. Whichever of the two merges second takes
   fifty-three and the other's row in the test's message.
   **Update (orchestrator, 2026-10-03):** PR #567 (A4) merged while this spec was written. Merging main into this
   branch made the index fifty-three, with the test's count at 53 naming both A4 and F1. All 13 blocks still check
   out against the merged main.
5. **The issue-order test.** #270 is below the numbers of the rows above it (#542 is the last), so F1 is excluded
   from the rising-number assert by its id and pinned to #270, the way G2 (#255) and E7 (#300) were.
6. **Dates.** Blocks 10 and 11 date the chart and application history lines 2026-10-03, the day this was
   written; the implementing pull request writes its own date there if it differs.

Open questions only the operator can answer:

1. Should a later step of Epic F anchor the report windows (login-activity's `To`, the 30-day change counts, the
   overdue state) to the snapshot's stamp instead of the generation clock, so that every report, login-activity
   included, hashes the same over one snapshot at any clock? Cost measured in note 1: the sections of five reports
   change once, and the test seed's fixed `NOW` would no longer be the instant the windows end.

**Correction at implementation (orchestrator, 2026-10-03): the CHANGELOG block joins the existing `## Unreleased`.**
It was written against `94f5ebbb`, which had no Unreleased section, so it created one above the 4.0.0 heading. PR
#567 (A4) created that section first. Applied to today's main, the block left two `## Unreleased` headings, and
`tests/test_kyverno.py::test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`
read the first, A4's, which does not name chart 0.66.5. The block now adds this spec's bullet at the top of the one
`## Unreleased` section.

**Correction at implementation (orchestrator, 2026-10-03): the e2e walk's integrity check recomputes the seal, so it
moves with it (Block 13, T270-7).** `local-development/e2e-walk/integrity_check.py` rebuilds each downloaded report's
sha256 from its `.json` with its own copy of the canonical keys (`CANONICAL`: name, cluster, params, coverage,
totals, truncated, include_members, sections). §2 does not name that script, so its copy was not moved: after
blocks 1 to 12 it seals neither `api_url` nor `sealed_provenance` and keeps page one, and the next walk would report
`recomputed_matches: false` for every report. Block 13 gives the script a `recompute()` with T270-5's recipe, and
T270-7 runs that function over every report, so the walk's copy cannot drift from `Report.canonical()` unnoticed. A
`.json` written before 4.1.0 does not verify under the new recipe; the walk checks only the files it downloaded in
the same run.

**Review of the implementation (PR #571, 2026-10-03): Codex (gpt-5.6-sol, xhigh) and OB3 (in Grok's seat).** Both
confirmed the seal itself: no page-one row is data while sealed nowhere (a mutation of every row), the renderers'
HTML and PDF are byte-identical apart from the hash, every stored run keeps its own hash, and the chart change is
the version lines. The decisions:
- **Accepted: the docs promised more than the code does (Codex F1, OB3 F2).** "Two runs over one snapshot with the
  same parameters hash the same" held without exception in the model's docstrings, the design doc, the CHANGELOG,
  the index row, the chart's history line and the test's docstring. Five builders read the generation clock
  (`login-activity`, `groups`, `dormant-access`, `groupsync-health`, `compliance-snapshot`), and OB3 measured
  `dormant-access` with `dormant_days=1` changing its hash two minutes apart on a seed whose last login sits on the
  cutoff. Note 1 already said this; the published contract now says it too, naming the five and why each moves.
  The coverage can also reflect two report-service settings (`common.py`'s `coverage`: `login_capture_enabled`,
  and `namespaces_read_enabled` before the first Namespace read), which Codex measured; one sentence says so.
  Pinned by T270-10, which scans each builder's module for `ctx.now`, so a sixth clock-reading report fails it
  until the docs name it. Codex's own test, which greps seven terms in five documents, was **rejected**: it pins
  wording, where T270-10 pins the set.
- **Accepted: an old `.json` crashed the walk and took its document with it (OB3 F1).** On a `.json` written
  before 4.1.0, `recompute()` raised KeyError before `integrity.jsonl` was written; `run_walk.sh` guards that stage
  (`|| rc=1`) but not `build_doc.py`, which reads `integrity.jsonl` at import, so the walk ended with no document,
  against its own header ("The document is built either way"). `recompute()` now returns None, a FAIL row. T270-8.
- **Accepted: only page one may ride outside the seal (OB3 F3).** A section appended to a `.json` with
  `"sealed": false` left the recomputed hash unchanged, so the walk's check against the run record passed. The model
  leaves exactly page one out; `recompute()` refuses any other shape. T270-9.
- **Accepted: the walk document printed the old recipe (OB3 F4).** Block 14. T270-11.
- **Accepted: SPEC_C3's amendment said "two settings"** for the marking, the binding interval and the PDF variant
  and font; it now names them.
- **No change:** `render_pdf.py` and `runs.py` call the whole `.json` "canonical". Both predate this spec.

## 1. The mandate, and what is out of scope

The mandate (#270, "The change"): settle which provenance rows are data (sealed) and which are run facts
(unsealed), each with a reason; keep the unsealed half on page one with the same words and outside `canonical()`;
record the one-time hash change in the CHANGELOG; make the docstrings of `model.py` and `canonical()` describe the
code. Must not change (the issue): the page-one rows and words; the sections, tables and totals; the `.json` keys;
PDF/A 3b/3u embedding the canonical `.json`; stored runs.

Out of scope: the report windows' anchor (note 1, open question 1); a signature or a MAC over the artefact (the
sha256 is an identity of content, not an authentication of it, and stays so); a diff of two reports (a later step
of Epic F); re-hashing stored runs (never: their artefacts and `report_run.sha256` stay as written).

## 2. Research, measured

### 2.1 Primary sources

| Source (fetched 2026-10-03) | The sentence relied on | What it settles |
|---|---|---|
| Reproducible Builds, "Timestamps", <https://reproducible-builds.org/docs/timestamps/> | "Timestamps make the biggest source of reproducibility issues. Many build tools record the current date and time." | A digest meant to identify content must not cover the instant it was produced; the generation time leaves the hash |
| SLSA Provenance v1.0, <https://slsa.dev/spec/v1.0/provenance>, `runDetails.metadata` | `invocationId`: "Identifies this particular build invocation, which can be useful for finding associated logs or other ad-hoc analysis." `startedOn`: "The timestamp of when the build started." | The supply-chain standard keeps the run's id and instants in the run's metadata, beside the subject digest and not inside it: the shape `to_json()` already has (run facts beside `sha256`) |
| RFC 8785, JSON Canonicalization Scheme, <https://www.rfc-editor.org/rfc/rfc8785.html>, Abstract | "Cryptographic operations like hashing and signing need the data to be expressed in an invariant format so that the operations are reliably repeatable." | The alternative in §2a, rejected: the serialisation is already invariant for this model; what varies is the content |
| Python `json`, <https://docs.python.org/3/library/json.html> | `sort_keys`: "If `True`, dictionaries will be outputted sorted by key." `separators`: "To get the most compact JSON representation, you should specify `(',', ':')` to eliminate whitespace." | The canonical form `seal()` already writes is key-order and whitespace invariant, so a new key changes the hash only through its content |
| Python `dataclasses`, <https://docs.python.org/3/library/dataclasses.html>, `asdict` | "Each dataclass is converted to a dict of its fields, as `name: value` pairs. dataclasses, dicts, lists, and tuples are recursed into." | A field added to `Section` appears in every section's dict, in the hash and in the `.json`: the `sealed` flag is self-describing in the artefact |

### 2.2 The code, read on `94f5ebbb`

- `local-development/gsd/reporting/model.py#canonical` hashes `sections` whole; `local-development/gsd/reporting/model.py#seal`
  hashes `canonical()` with `sort_keys=True, separators=(",", ":")`; `local-development/gsd/reporting/model.py#to_json`
  writes `{**canonical(), title, api_url, generated_at, generated_by, generated_by_note, run_id, provenance, sha256}`.
- `local-development/gsd/reporting/catalogue/common.py#assemble` puts `provenance_section(...)` first in `sections`, so
  page one is inside the hash; `local-development/gsd/reporting/catalogue/common.py#provenance_section` writes the
  rows Handling, Cluster, Generated at (UTC), Generated by, Run id, Report service, Data as of, Last poll,
  Namespaces, User objects, Login capture, History retained since, Includes membership rosters, Parameters and,
  with PDF on, PDF; then the poll-failure warning, three coverage notes and the scope caveat.
- `local-development/gsd/reporting/catalogue/common.py#provenance` reads `marking`, `binding_interval_seconds`,
  `pdf_variant` and `git_commit` from the settings, `__version__` from the package, the snapshot facts from the
  run context, and `status`, `last_poll`, `message` from the snapshot's cluster row.
- `local-development/gsd/reporting/runs.py#RunManager` (the worker) builds the run context from the newest
  snapshot: `cluster=snap.cluster(...)`, so the poll facts are the snapshot's, constant for every run over it;
  `snapshot_age_seconds=info.age_seconds(now)`, so the age moves with the clock.
- `local-development/gsd/reporting/render_html.py#context` renders from `json.loads(report.to_json())`, so the
  HTML's sections are the `.json`'s; `local-development/gsd/reporting/render_pdf.py#render_pdf` iterates
  `report.sections` and embeds the `.json` bytes under 3b/3u.

### 2.3 The probe: what moves between two runs over one snapshot

The probe (kept in the scratch directory, not in the tree) seeds the report suite's database
(`local-development/tests/reporting_seed.py#seed_store`), writes one snapshot, and builds every report twice: the
second run by another viewer, under another run id, at a later clock. It compares the sha256 and every section but
page one. On `94f5ebbb`:

```text
+  120s namespace-access         sha_equal=False data_sections_differ=[]
+  120s access-matrix            sha_equal=False data_sections_differ=[]
+  120s privileged-access        sha_equal=False data_sections_differ=[]
+  120s binding-findings         sha_equal=False data_sections_differ=[]
+  120s groups                   sha_equal=False data_sections_differ=[]
+  120s users                    sha_equal=False data_sections_differ=[]
+  120s login-activity           sha_equal=False data_sections_differ=['Summary']
+  120s dormant-access           sha_equal=False data_sections_differ=[]
+  120s groupsync-health         sha_equal=False data_sections_differ=[]
+  120s compliance-snapshot      sha_equal=False data_sections_differ=[]
+  120s access-certification     sha_equal=False data_sections_differ=[]
+ 7200s namespace-access         sha_equal=False data_sections_differ=[]
+ 7200s access-matrix            sha_equal=False data_sections_differ=[]
+ 7200s privileged-access        sha_equal=False data_sections_differ=[]
+ 7200s binding-findings         sha_equal=False data_sections_differ=[]
+ 7200s groups                   sha_equal=False data_sections_differ=[]
+ 7200s users                    sha_equal=False data_sections_differ=[]
+ 7200s login-activity           sha_equal=False data_sections_differ=['Summary']
+ 7200s dormant-access           sha_equal=False data_sections_differ=[]
+ 7200s groupsync-health         sha_equal=False data_sections_differ=['Summary', 'GroupSync CRs']
+ 7200s compliance-snapshot      sha_equal=False data_sections_differ=['Key figures']
+ 7200s access-certification     sha_equal=False data_sections_differ=[]
```

What it settles: every report's hash differs today (the issue's finding, reproduced hermetically); for ten reports
at two minutes apart, page one is the ONLY difference, so taking it out of the hash is sufficient for them; the
remaining differences are clock-anchored windows and states inside the builders (note 1).

## 2a. Alternatives considered

| Option | Source | Cost here | Decision |
|---|---|---|---|
| A. Leave page one out of `canonical()` entirely, seal nothing in its place | the issue's first shape | The cluster's API URL, the snapshot stamp and schema and the last poll would leave the hash: a report re-pointed at another snapshot would keep its hash | Rejected: drops data facts the issue says are sealed |
| B. Split page one into two sections, a sealed one and an unsealed one | the issue's second shape | Page one would render as two headed sections and the rows would reorder: "What the reader sees on page one … same words" is broken | Rejected |
| C. Keep page one whole on the page, mark it `sealed=False`, and seal its data facts through their own fields (`api_url` and a `sealed_provenance` projection of the snapshot facts; coverage, parameters and the rosters switch are already sealed fields) | SLSA's subject-versus-run-metadata split (§2.1) | One `Section` field, one constant, a three-key change in `canonical()`, one keyword in `provenance_section`. Each section in the `.json` gains a `sealed` key and the `.json` gains `sealed_provenance`; no key is removed or renamed | **Chosen** |
| D. Canonicalise with RFC 8785 (JCS) | RFC 8785 | A new dependency or implementation; changes nothing about WHICH values vary, which is the defect | Rejected: the serialisation is already invariant (`sort_keys`, fixed separators); the content is the problem |
| E. Strip the run-fact rows from page one by label inside `canonical()` | — | Couples `model.py` to `common.py`'s row labels and to the words inside "Data as of", which mixes data (stamp, schema) and run facts (age, interval) in one string | Rejected: fragile, and the mixed row cannot be split without changing its words |
| F. Hash at a coarser clock (round `now` to the snapshot interval) | — | Still a hash over a time; two runs either side of a boundary differ | Rejected |

**Reconciliation.** Reproducible Builds says a timestamp in the output defeats reproduction: after the change
`local-development/gsd/reporting/model.py#canonical` leaves out every section whose `sealed` is false, and the one
such section is page one (`local-development/gsd/reporting/catalogue/common.py#provenance_section`), which holds
the generation instant and the snapshot's age. SLSA keeps the invocation id and start time beside the subject
digest: `local-development/gsd/reporting/model.py#to_json` already writes `run_id` and `generated_at` beside
`sha256` and outside `canonical()`, and after the change it also writes every section, page one included, beside
the sealed ones. Python's `json.dumps(sort_keys=True, separators=(",", ":"))` is order and whitespace invariant:
`local-development/gsd/reporting/model.py#seal` calls exactly that, unchanged. `dataclasses.asdict` recurses into
every field: the new `sealed` field therefore appears in each section's dict, and
`local-development/tests/test_report_seal.py#test_t270_5_the_json_alone_reproduces_the_hash` recomputes the hash
from the `.json` alone by keeping the sections whose `sealed` is true.

## 3. The design

### 3.1 The rule

A report's sha256 is the sha256 of `canonical()`: its name, cluster and API URL, parameters, coverage, totals,
truncation flag, rosters switch, the snapshot facts in `sealed_provenance`, and every section whose `sealed` is
true. Page one is the one section with `sealed=False`. Reason: page one restates the run; everything on it that is
data is sealed through its own field, so nothing the hash covered as data is lost.

### 3.2 Sealed: the data facts, each with its reason

| Page-one row | Sealed through | Reason |
|---|---|---|
| Cluster (id and API URL) | `cluster`, `api_url` | Which cluster the data describes. `api_url` was sealed only through page one; it moves into `canonical()` so it stays sealed |
| Data as of: the snapshot stamp | `sealed_provenance.snapshot_stamp` | Which observation the data is. Two snapshots are two observations: a hash that ignored the stamp would let a re-run over a newer snapshot present the older one's number |
| Data as of: the schema | `sealed_provenance.snapshot_schema_version` | The shape the data was read in; it changes how the tables are read |
| Last poll (instant, status, message) and the poll-failure warning | `sealed_provenance.last_poll`, `.poll_status`, `.poll_message` | Whether the data may be stale. They are the snapshot's cluster row, constant for every run over one snapshot (§2.2) |
| Namespaces, User objects, Login capture, History retained since, and the three coverage notes | `coverage` (unchanged) | What was read decides what absence means; the issue requires the coverage sealed |
| Includes membership rosters | `include_members` (unchanged) | Changes what the sections contain |
| Parameters | `params` (unchanged) | The question the report answers |
| The scope caveat | — | A constant; it carries no information to seal |

### 3.3 Unsealed: the run facts, each with its reason

| Page-one row | Reason |
|---|---|
| Generated at (UTC) | The instant of the run (Reproducible Builds, §2.1) |
| Generated by | Who asked; two people asking the same question of the same data get the same answer |
| Run id | Unique per run by construction (SLSA's `invocationId`) |
| Data as of: the snapshot's age at generation | `now − stamp`: the clock again |
| Report service (version and commit) | The renderer. If a release changes a builder's output, the sections change and so does the hash; a release that changes nothing about the data must not change it |
| Handling (the marking) | A label the chart applies to the document, not a fact about the cluster; a new marking re-labels, it does not change the evidence |
| Data as of: bindings refresh every … s | The chart's refresh cadence, a setting (#368 moved it to 3600 s and, by the old rule, changed every hash over unchanged data) |
| PDF (variant and font) | The rendering; the HTML and `.json` of the same run carry the same hash |

### 3.4 Where the unsealed half lives

Page one stays first in `sections`, rendered by both renderers with the same rows and words, and is written whole
into the `.json`'s `sections` with `"sealed": false`. The run facts are also in the `.json`'s existing top-level
keys (`generated_at`, `generated_by`, `generated_by_note`, `run_id`, `provenance`), as today.

### 3.5 The `.json`: additive only

`to_json()` keeps every existing key. It gains `sealed_provenance` (the five snapshot facts) and a `sealed` boolean
on each section. `sections` keeps every section, page one included, so the HTML (rendered from the `.json`) and the
PDF/A 3b/3u attachment are unchanged in content apart from that flag. The hash is reproducible from the `.json`
alone: the canonical keys, with `sections` narrowed to those whose `sealed` is true (T270-5).

### 3.6 The one-time hash change

Every artefact generated after this release hashes differently from one generated before it over the same data:
page one leaves the hash, and `api_url`, `sealed_provenance` and each section's `sealed` flag enter it. Stored runs
are not rewritten: their files and their `report_run.sha256` stay as written, and each still matches its own
`.json` under the rule it was generated with. The CHANGELOG says so (block 12).

### 3.7 Safety budget

The change binds, writes, deletes and widens nothing: no RBAC, no value, no migration, no new file at runtime. The
budget over the system: zero new permissions, zero rows rewritten, zero artefacts rewritten, across every replica
and every stored run.

## 4. Tests

### 4.1 One test per Definition-of-Done item

All in `local-development/tests/test_report_seal.py` (block 5), over the report suite's seeded snapshot.

| ID | Test | Definition-of-Done item |
|---|---|---|
| T270-1 | `test_t270_1_two_runs_over_one_snapshot_hash_the_same` (every report) | Two runs over one snapshot, same parameters, different clock, run id and viewer, give the same sha256; page one still shows different run ids and viewers |
| T270-2 | `test_t270_2_login_activity_differs_only_in_its_window_when_the_clock_moves` | The measured limit of note 1, pinned |
| T270-3 | `test_t270_3_the_renderer_marking_interval_and_pdf_rows_are_not_sealed` | The rulings of §3.3 |
| T270-4 | `test_t270_4_the_data_changes_the_hash_and_the_run_does_not` (snapshot, parameters, coverage) | Changing the snapshot's data, the parameters or the coverage changes the sha256 |
| T270-5 | `test_t270_5_the_json_alone_reproduces_the_hash` | The `.json` keeps its keys and page one, and reproduces the hash |
| T270-6 | `test_t270_6_a_new_snapshot_of_the_same_data_is_new_evidence` | The ruling of §3.2 on the stamp |
| T270-7 | `test_t270_7_the_walks_integrity_check_recomputes_the_seal` (every report) | The e2e walk's integrity check recomputes the same hash from the `.json` (Orchestrator's notes, the correction at implementation) |
| T270-8 | `test_t270_8_a_json_written_before_4_1_is_a_fail_row_not_a_crash` | An old `.json` is a FAIL row; the walk keeps its document (the review) |
| T270-9 | `test_t270_9_only_page_one_rides_outside_the_seal` | Only page one, the first section, may be unsealed (the review) |
| T270-10 | `test_t270_10_the_docs_name_every_report_whose_data_reads_the_clock` | The five clock-reading reports, found in the source, are named where the contract is stated (the review) |
| T270-11 | `test_t270_11_the_walk_document_states_the_recipe_the_check_runs` | The walk document prints the recipe the check runs (the review) |

### 4.2 Each test fails without the change, and why

- T270-1: page one's Generated at, Generated by and Run id rows, and the age in Data as of, are inside the hash.
- T270-2: page one differs between the runs, so the canonical documents differ outside the Window block too.
- T270-3: the Handling, Report service, Data as of (interval) and PDF rows are inside the hash.
- T270-4: each case first asserts its control, the same inputs run by another viewer under another run id, two
  minutes later; the control's hash differs before the change. The data assertion is the guard that holds the
  seal against leaving out too much, and passes on both trees.
- T270-5: `canonical()` has no `sealed_provenance` and the sections no `sealed` key (KeyError).
- T270-6: the canonical document has no `sealed_provenance` (KeyError); the hashes differing passes on both.
- T270-7: without Block 13 the script has no `recompute` (AttributeError); with only its old key list, every
  report's recomputed hash differs from its seal.
- T270-8: on the head before the review, KeyError: 'sealed_provenance' and no `integrity.jsonl` (OB3's measurement).
- T270-9: the appended unsealed section left the recomputed hash equal to the seal.
- T270-10: the CHANGELOG bullet named login-activity only.
- T270-11: `build_doc.py`'s sentence named neither `api_url` nor `sealed_provenance`.

### 4.3 The proof

The blocks checked against a clean checkout of `94f5ebbb`, then applied to a throwaway worktree of the same commit,
with `PYTHONPATH=<tree>/local-development` and the repository's venv. Recorded:

```text
$ python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F1_data_only_seal.md <clean 94f5ebbb>
13 blocks check out across 9 files

before the blocks:   tests/test_report_seal.py: 18 failed in 0.23s
  T270-1 (11 reports): AssertionError <report name> (the sha256s differ)
  T270-2: the canonical documents without the Window block differ
  T270-3: the two sha256s differ
  T270-4 (3 cases): AssertionError: the control: only the run differs
  T270-5: KeyError: 'sealed'
  T270-6: KeyError: 'sealed_provenance'
after the blocks:    13 blocks applied; tests/test_report_seal.py: 18 passed in 0.17s
touched suites:      test_reporting_model, _catalogue, _render, _server, _snapshot, test_chart_image_reference,
                     test_docs_citations, test_specs_index: 2100 passed, 18 skipped
                     the 27 test files that read CHANGELOG.md, Chart.yaml, appVersion or __version__
                     (test_ui and test_release_crc left out): 2442 passed, 18 skipped
the full hermetic suite: not run (the budget); the implementing pull request runs it
```

## 5. On the lab (the implementing pull request)

Development steps on the CRC lab, after the image is deployed through the release's values file and pipeline:

1. Read the snapshot interval the release runs with: `reporting.snapshot.intervalSeconds` in its values file
   (300 s by default).
2. As a wide-tier viewer, request the `groups` report on one cluster, then request it again at once (well inside
   one snapshot interval), from the Reports tab. Then ask a second person (or the API token path) to request it
   once more.
3. From `GET /report/api/runs`, read the three runs' `sha256` and `snapshot_stamp`. Pass: the three
   `snapshot_stamp`s are equal and the three `sha256`s are equal.
4. Open each run's HTML: page one shows three different Run ids and Generated at instants (and two viewers).
   Pass: the rows and words are those of a run before the release.
5. Wait past the interval and run it again: the `snapshot_stamp` is newer and the `sha256` differs (§3.2).
6. Leave the earlier runs' artefacts alone; a run generated before the release keeps its hash in
   `GET /report/api/runs`.

The evidence goes under `reports/<date>_<slug>/` and on #270, pinned to the full merge sha. No lab write is made by
this spec.

## 6. What an operator sees, and what it costs

A reader sees nothing new: page one's rows and words are unchanged. An auditor sees the same sha256 on reports run
over the same snapshot with the same parameters, whoever runs them; a release, a new marking or a new binding
interval no longer changes it. The `.json` gains `sealed_provenance` and a `sealed` flag per section. Once, at this
release, every new artefact's hash differs from an earlier artefact over the same data. Cost: one dataclass field,
one constant, about ten changed lines in `model.py`, one keyword in `common.py`; no RBAC, value, migration or
runtime cost.

## 7. Implementation blocks

### Block 1 — `local-development/gsd/reporting/model.py`: the module docstring says what is sealed

<!-- block: local-development/gsd/reporting/model.py | edit -->
```python
"""The one data model every report is built into and every renderer reads.

A report is SECTIONS of BLOCKS — tables, key/value lists, notes — plus the provenance and coverage
facts every report carries. HTML and PDF are two renderings of this structure, which is what makes
the sha256 honest: it is computed over the canonical JSON of the DATA (sections, params, coverage,
totals), never over a rendering and never over the timestamp, so the same data on two days hashes
the same and a PDF can be tied back to its .json by the number printed on page one.
"""
```

```python
"""The one data model every report is built into and every renderer reads.

A report is SECTIONS of BLOCKS — tables, key/value lists, notes — plus the provenance and coverage
facts every report carries. HTML and PDF are two renderings of this structure, and the sha256 is
computed over the canonical JSON of the DATA: the sealed sections, the parameters, the coverage, the
totals, the cluster, and the snapshot the data was read from (its stamp, its schema, how the
cluster's last poll before it ended). Page one's facts of the run — when, by whom, under which run
id or release, how old the snapshot was, the chart's marking or binding interval — are outside it,
so two runs over one snapshot with the same parameters hash the same whoever runs them, except where
a report's own data is computed against the generation clock (a window, a cutoff, an overdue state:
SPEC_F1, Orchestrator's notes 1): those agree only while the clock-derived values coincide. The
coverage can also reflect two report-service settings (`login_capture_enabled`,
`namespaces_read_enabled`), so a run under other settings is other evidence. A PDF can be tied back
to its .json by the number printed on page one. Page one states the run and is not sealed; what it
shows that is data is sealed through its own field. A new snapshot is new evidence even when no row
changed: its stamp and its coverage are sealed, so the hash answers
"is this the same evidence?", not "did access change?" (docs/specs/SPEC_F1_data_only_seal.md).
"""
```

### Block 2 — `local-development/gsd/reporting/model.py`: a section says whether it is sealed; the sealed provenance keys

<!-- block: local-development/gsd/reporting/model.py | edit -->
```python
    page_break: bool = False


@dataclass
class Report:
```

```python
    page_break: bool = False
    #: False for a section that states facts of the RUN (page one): rendered like any other and
    #: written into the .json, but left out of the sha256 (SPEC_F1, #270).
    sealed: bool = True


#: The provenance facts that describe the DATA rather than the run: which snapshot it was read from,
#: that snapshot's schema, and how the cluster's last poll before it ended. Every run over one
#: snapshot reads the same values, so they are sealed; the rest of `provenance` is the run's.
SEALED_PROVENANCE = ("snapshot_stamp", "snapshot_schema_version", "last_poll", "poll_status", "poll_message")


@dataclass
class Report:
```

### Block 3 — `local-development/gsd/reporting/model.py`: `canonical()` leaves out the unsealed sections; `to_json()` keeps them

<!-- block: local-development/gsd/reporting/model.py | edit -->
```python
    def canonical(self) -> dict:
        """The DATA, and only the data: what two runs over the same snapshot must agree on."""
        return {
            "name": self.name, "cluster": self.cluster, "params": self.params, "coverage": self.coverage,
            "totals": self.totals, "truncated": self.truncated, "include_members": self.include_members,
            "sections": [asdict(s) for s in self.sections],
        }
```

```python
    def canonical(self) -> dict:
        """The DATA, and only the data: what two runs over one snapshot with the same parameters agree
        on while the values a report computes against the generation clock coincide (the module
        docstring). A section marked `sealed=False` (page one, the run's facts) is left out; what page
        one shows that is data is here through its own key: the cluster and its API URL, the snapshot facts, the
        coverage, the parameters and the rosters switch. Every key is in the .json, so the hash can be
        recomputed from the .json alone by keeping the sections whose `sealed` is true."""
        return {
            "name": self.name, "cluster": self.cluster, "api_url": self.api_url, "params": self.params,
            "coverage": self.coverage, "totals": self.totals, "truncated": self.truncated,
            "include_members": self.include_members,
            "sealed_provenance": {key: self.provenance.get(key) for key in SEALED_PROVENANCE},
            "sections": [asdict(s) for s in self.sections if s.sealed],
        }
```

<!-- block: local-development/gsd/reporting/model.py | edit -->
```python
        """The .json artefact: the canonical data plus the run facts, and the hash of the former."""
        doc = {**self.canonical(), "title": self.title, "api_url": self.api_url,
```

```python
        """The .json artefact: the canonical data plus the run facts, and the hash of the former.
        `sections` is every section, page one included, each with its `sealed` flag: the renderers and
        the PDF/A attachment read the whole report, the hash covers the sealed ones."""
        doc = {**self.canonical(), "sections": [asdict(s) for s in self.sections],
               "title": self.title, "api_url": self.api_url,
```

### Block 4 — `local-development/gsd/reporting/catalogue/common.py`: page one is not sealed

<!-- block: local-development/gsd/reporting/catalogue/common.py | edit -->
```python
    blocks.append(Note("Scope: " + DIRECT_BINDINGS_CAVEAT + ".", "caveat"))
    return Section("Provenance and coverage", blocks)
```

```python
    blocks.append(Note("Scope: " + DIRECT_BINDINGS_CAVEAT + ".", "caveat"))
    # Page one states the RUN (when, by whom, run id, release, the snapshot's age, the chart's marking and
    # interval), so it is not sealed; every row on it that is data is sealed through its own field of the
    # Report (SPEC_F1, #270: model.py's SEALED_PROVENANCE, coverage, params, include_members, api_url).
    return Section("Provenance and coverage", blocks, sealed=False)
```

### Block 5 — `local-development/tests/test_report_seal.py`: the tests

<!-- block: local-development/tests/test_report_seal.py | create -->
```python
"""The seal covers the data only (docs/specs/SPEC_F1_data_only_seal.md, #270): two runs over one snapshot
with the same parameters hash the same whoever runs them, while the values a report computes against the
generation clock coincide; the snapshot, the parameters and the coverage are sealed; page one still shows the
run; the .json alone reproduces the hash."""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from gsd.reporting.catalogue import REGISTRY, RunContext, validate_params
from gsd.reporting.catalogue import common
from gsd.reporting.catalogue.common import assemble
from gsd.reporting import model
from gsd.reporting.config import ReportSettings
from gsd.reporting.model import Report
from gsd.reporting.snapshot import Snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot

LOCAL = Path(__file__).resolve().parents[1]
DOCS = LOCAL.parent / "docs"

#: What a report needs before it builds (the catalogue suite's defaults).
PARAMS = {
    "namespace-access": {"namespaces": "prod-ns,dev-ns"},
    "access-certification": {"campaign": "Q3 2026", "due": "2026-10-01", "reviewer": "Jane Reviewer"},
}
#: login-activity's Window prints the generation clock as its `To`: data anchored to the run (SPEC_F1,
#: Orchestrator's notes 1), so two of its runs agree only at one clock.
CLOCK_ANCHORED = {"login-activity"}
#: Every report whose builder reads the generation clock (`ctx.now`) into sealed data: a window, a cutoff, an
#: overdue state. Two of its runs over one snapshot agree only while those values coincide (SPEC_F1, note 1).
CLOCK_DERIVED = {"login-activity", "groups", "dormant-access", "groupsync-health", "compliance-snapshot"}
#: The .json keys before SPEC_F1; none is removed or renamed.
JSON_KEYS = {"name", "cluster", "params", "coverage", "totals", "truncated", "include_members", "sections", "title",
             "api_url", "generated_at", "generated_by", "generated_by_note", "run_id", "provenance", "sha256"}


def _snapshot(tmp_path: Path, **seed) -> Snapshot:
    store = seed_store(str(tmp_path / "writer.db"), **seed)
    directory = tmp_path / "snapshots"
    directory.mkdir()
    try:
        return Snapshot(write_snapshot(store, directory))
    finally:
        store.close()


@pytest.fixture(scope="module")
def snap(tmp_path_factory):
    snapshot = _snapshot(tmp_path_factory.mktemp("seal"))
    yield snapshot
    snapshot.close()


def _run(snapshot: Snapshot, name: str, *, now=NOW, run_id="20260906T120000.000000Z-ab12", viewer="alice",
         note="proxy-verified", params=None, **settings) -> Report:
    spec, build = REGISTRY[name]
    info = snapshot.info()
    ctx = RunContext(settings=ReportSettings(**{"login_capture_enabled": True, **settings}),
                     cluster=snapshot.cluster(CLUSTER), now=now, run_id=run_id, generated_by=viewer,
                     generated_by_note=note, snapshot_stamp=info.stamp, snapshot_age_seconds=info.age_seconds(now),
                     schema_version=info.schema_version)
    p = validate_params(spec, {**PARAMS.get(name, {}), **(params or {})})
    return assemble(spec, snapshot, ctx, p, build(snapshot, ctx, p))


def _other_run(snapshot: Snapshot, name: str, **over) -> Report:
    """The same report over the same snapshot by another viewer, under another run id, two minutes later
    (at the same clock for a clock-anchored report)."""
    later = NOW if name in CLOCK_ANCHORED else NOW + timedelta(minutes=2)
    return _run(snapshot, name, now=later, run_id="20260906T120200.000000Z-cd34", viewer="bob",
                note="schedule:nightly", **over)


def _page_one(report: Report) -> dict:
    return dict(report.sections[0].blocks[0].items)


@pytest.mark.parametrize("name", list(REGISTRY))
def test_t270_1_two_runs_over_one_snapshot_hash_the_same(snap, name):
    """Without SPEC_F1 every report fails: page one's Generated at, Generated by and Run id rows, and the
    snapshot's age in its Data as of row, were inside the hash."""
    first, second = _run(snap, name), _other_run(snap, name)
    assert first.sha256 == second.sha256, name
    one, two = _page_one(first), _page_one(second)
    assert one["Run id"] != two["Run id"] and one["Generated by"] != two["Generated by"], "page one still shows the run"
    if name not in CLOCK_ANCHORED:
        assert one["Generated at (UTC)"] != two["Generated at (UTC)"]


def test_t270_2_login_activity_differs_only_in_its_window_when_the_clock_moves(snap):
    """The measured limit (SPEC_F1, Orchestrator's notes 1): at another clock, login-activity's sealed data
    differs in its Window block and nowhere else. Without SPEC_F1 page one differs too."""
    first = _run(snap, "login-activity")
    second = _run(snap, "login-activity", now=NOW + timedelta(minutes=2), run_id="20260906T120200.000000Z-cd34",
                  viewer="bob")
    assert first.sha256 != second.sha256

    def without_window(report: Report) -> dict:
        doc = report.canonical()
        for section in doc["sections"]:
            section["blocks"] = [b for b in section["blocks"] if not (b["kind"] == "kv" and b["title"] == "Window")]
        return doc

    assert without_window(first) == without_window(second)


def test_t270_3_the_renderer_marking_interval_and_pdf_rows_are_not_sealed(snap, monkeypatch):
    """A release, a new marking, a new binding interval or another PDF variant re-labels the same evidence.
    Without SPEC_F1 the Handling, Report service, Data as of and PDF rows were inside the hash."""
    first = _run(snap, "groups")
    monkeypatch.setattr(common, "__version__", "9.9.9")
    second = _run(snap, "groups", marking="Handling: restricted", binding_interval_seconds=900,
                  git_commit="0123456789ab-dirty", pdf_variant="pdf/a-3b")
    assert first.sha256 == second.sha256
    rows = _page_one(second)
    assert rows["Handling"] == "Handling: restricted"
    assert rows["Report service"].startswith("9.9.9 @ 0123456789ab-dirty")
    assert "bindings refresh every 900 s" in rows["Data as of"] and rows["PDF"].startswith("variant pdf/a-3b")


@pytest.mark.parametrize("change", ["snapshot", "parameters", "coverage"])
def test_t270_4_the_data_changes_the_hash_and_the_run_does_not(snap, tmp_path, change):
    """The control (another viewer, run id and clock) fails without SPEC_F1; the data assertion holds the seal
    against leaving out too much, and passes with or without it."""
    name = "groupsync-health"
    base = _run(snap, name)
    assert _other_run(snap, name).sha256 == base.sha256, "the control: only the run differs"
    if change == "snapshot":
        other = _snapshot(tmp_path, reconcile_error=False)
        try:
            changed = _run(other, name)
        finally:
            other.close()
        assert changed.canonical()["sections"] != base.canonical()["sections"], "the seed change reaches the data"
    elif change == "parameters":
        changed = _run(snap, name, params={"window_days": 7})
    else:
        changed = _run(snap, name, login_capture_enabled=False)
        assert changed.coverage != base.coverage
    assert changed.sha256 != base.sha256, change


def test_t270_5_the_json_alone_reproduces_the_hash(snap):
    """The .json keeps every key and every section, page one included, and the hash is the sha256 of its
    canonical keys with the sections narrowed to the sealed ones. Without SPEC_F1: no `sealed_provenance`."""
    report = _run(snap, "groups")
    doc = json.loads(report.to_json())
    assert JSON_KEYS <= set(doc), JSON_KEYS - set(doc)
    assert [s["title"] for s in doc["sections"]] == [s.title for s in report.sections], "page one is in the .json"
    assert doc["sections"][0]["sealed"] is False and all(s["sealed"] for s in doc["sections"][1:])
    sealed = {key: doc[key] for key in ("name", "cluster", "api_url", "params", "coverage", "totals", "truncated",
                                         "include_members", "sealed_provenance")}
    sealed["sections"] = [s for s in doc["sections"] if s["sealed"]]
    digest = hashlib.sha256(json.dumps(sealed, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))
    assert digest.hexdigest() == doc["sha256"] == report.sha256


def test_t270_6_a_new_snapshot_of_the_same_data_is_new_evidence(tmp_path):
    """The stamp is sealed (SPEC_F1 §3.2): two snapshots of one database differ in their stamp and nothing
    else, and hash differently. Without SPEC_F1 the canonical document has no `sealed_provenance`."""
    store = seed_store(str(tmp_path / "writer.db"))
    directory = tmp_path / "snapshots"
    directory.mkdir()
    try:
        first, second = Snapshot(write_snapshot(store, directory)), Snapshot(write_snapshot(store, directory))
    finally:
        store.close()
    try:
        one, two = _run(first, "groups"), _run(second, "groups")
    finally:
        first.close()
        second.close()
    assert one.sha256 != two.sha256
    a, b = one.canonical(), two.canonical()
    assert a["sealed_provenance"].pop("snapshot_stamp") != b["sealed_provenance"].pop("snapshot_stamp")
    assert a == b, "the stamp is the only difference"


def _integrity_check():
    """The e2e walk's integrity script, loaded from its file (it is not a package module)."""
    module_spec = importlib.util.spec_from_file_location("integrity_check", LOCAL / "e2e-walk" / "integrity_check.py")
    integrity = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(integrity)
    return integrity


def test_t270_7_the_walks_integrity_check_recomputes_the_seal(snap):
    """The e2e walk recomputes each downloaded report's hash from its .json (local-development/e2e-walk/
    integrity_check.py), so its recipe must be the model's. Without Block 13 it has no `recompute`, and its
    old key list seals page one and neither `api_url` nor `sealed_provenance`."""
    integrity = _integrity_check()
    for name in REGISTRY:
        report = _run(snap, name)
        assert integrity.recompute(json.loads(report.to_json())) == report.sha256, name


def _walk_dir(tmp_path: Path, docs: dict[str, dict]) -> Path:
    """A walk's run directory holding these .json artefacts and the run records the page polled for them."""
    run = tmp_path / "walk"
    (run / "reports").mkdir(parents=True)
    steps = []
    for stem, doc in docs.items():
        (run / "reports" / f"{stem}.json").write_text(json.dumps(doc))
        steps.append({"run": {"id": doc["run_id"], "sha256": doc["sha256"]}})
    (run / "results.json").write_text(json.dumps({"steps": steps}))
    return run


def test_t270_8_a_json_written_before_4_1_is_a_fail_row_not_a_crash(snap, tmp_path, monkeypatch):
    """A .json written before 4.1.0 has no `sealed_provenance` and no `sealed` flags. The integrity stage writes
    it as a FAIL row and carries on; a KeyError there wrote no integrity.jsonl, and the walk's document stage
    (build_doc.py) then died reading it."""
    old = json.loads(_run(snap, "groups", run_id="r-old").to_json())
    del old["sealed_provenance"]
    for section in old["sections"]:
        del section["sealed"]
    new = json.loads(_run(snap, "groups", run_id="r-new").to_json())
    run = _walk_dir(tmp_path, {"a-old": old, "b-new": new})
    monkeypatch.setattr(sys, "argv", ["integrity_check.py", str(run)])
    assert _integrity_check().main() == 1
    rows = [json.loads(line) for line in (run / "integrity.jsonl").read_text().splitlines()]
    assert [row["recomputed_matches"] for row in rows] == [False, True]


def test_t270_9_only_page_one_rides_outside_the_seal(snap):
    """The model leaves exactly one section out of the hash: page one, the first. A .json carrying any other
    unsealed section, or page one marked sealed, does not verify: otherwise a section added to a .json with
    `"sealed": false` would pass the walk's check against the run record's hash."""
    integrity = _integrity_check()
    doc = json.loads(_run(snap, "groups").to_json())
    assert integrity.recompute(doc) == doc["sha256"]
    added = {**doc, "sections": [*doc["sections"], {"title": "Attestation", "page_break": False, "sealed": False,
                                                    "blocks": [{"kind": "note", "text": "approved", "tone": "note"}]}]}
    assert integrity.recompute(added) is None
    page_one_sealed = {**doc, "sections": [{**doc["sections"][0], "sealed": True}, *doc["sections"][1:]]}
    assert integrity.recompute(page_one_sealed) is None


def test_t270_10_the_docs_name_every_report_whose_data_reads_the_clock():
    """Two runs over one snapshot hash the same whoever runs them; the docs that say so name the reports whose
    sealed data reads the generation clock (T270-2 measures one; a dormant cutoff or a change window moves too)."""
    reads = {name for name, (_, build) in REGISTRY.items() if "ctx.now" in inspect.getsource(inspect.getmodule(build))}
    assert reads == CLOCK_DERIVED, reads ^ CLOCK_DERIVED
    changelog = (DOCS / "CHANGELOG.md").read_text()
    bullet = changelog[changelog.index("- **A report's sha256 covers its data only (#270"):]
    design = (DOCS / "DESIGN_reporting_service.md").read_text()
    paragraph = design[design.index("**What the sha256 covers (SPEC_F1, #270).**"):]
    for where, text in (("CHANGELOG.md", bullet[:bullet.index("\n\n")]),
                        ("DESIGN", paragraph[:paragraph.index("\n\n")])):
        assert not [n for n in sorted(CLOCK_DERIVED) if f"`{n}`" not in text], where
    assert "generation clock" in model.__doc__ and "generation clock" in model.Report.canonical.__doc__


def test_t270_11_the_walk_document_states_the_recipe_the_check_runs():
    """build_doc.py prints the seal's recipe in the walk document's integrity section: it names every key the
    integrity check seals and says page one is left out."""
    source = (LOCAL / "e2e-walk" / "build_doc.py").read_text()
    sentence = source[source.index("Every report is sealed with"):source.index("sorted keys, compact separators")]
    assert not [k for k in _integrity_check().CANONICAL if k not in sentence], sentence
    assert "page one" in sentence and "sealed" in sentence.replace("sealed_provenance", "")
```

### Block 6 — `docs/design/DESIGN_reporting_service.md`: the provenance block says what the hash covers

<!-- block: docs/design/DESIGN_reporting_service.md | edit -->
```markdown
### 7.5 Never in a report
```

```markdown
**What the sha256 covers (SPEC_F1, #270).** Page one is not sealed: it states the run. Its data facts are sealed
through their own fields: the cluster and its API URL, the snapshot's stamp and schema and the last poll's instant,
status and message (`sealed_provenance`), the coverage, the parameters and the rosters switch. Generated at,
generated by, the run id, the snapshot's age, the report service's version and commit, the marking, the binding
interval and the PDF variant and font are run facts, outside the hash. So two runs over one snapshot with the same
parameters hash the same, whoever runs them, while the values a report computes against the generation clock
coincide: `login-activity`'s window ends at the generation instant, so two of its runs agree only at one clock;
`groupsync-health` and `compliance-snapshot` compute the overdue state against it, `groups`, `groupsync-health` and
`compliance-snapshot` count changes in a window that ends at it, and `dormant-access` sets its cutoff from it
(SPEC_F1, Orchestrator's notes 1). The coverage can also reflect two report-service settings
(`login_capture_enabled`, `namespaces_read_enabled`), so a run under other settings is other evidence. A new
snapshot is new evidence and hashes differently. The `.json` carries every section, page one with `"sealed": false`,
and its hash is the sha256 of the canonical keys with the sections narrowed to the sealed ones; page one, the first
section, is the only one left out.

### 7.5 Never in a report
```

### Block 7 — `docs/specs/SPEC_C3_reporting_microservice.md`: the seal's definition, amended

<!-- block: docs/specs/SPEC_C3_reporting_microservice.md | edit -->
```markdown
## Design

## 1. Goal
```

```markdown
- **Amended by SPEC_F1 (#270), application 4.1.0.** The body's seal ("the sha256 of the canonical data") covered
  page one, a section inside `canonical()`, and with it the generation instant, the viewer, the run id, the
  snapshot's age, the release and the chart's settings on it (the marking, the binding interval, the PDF variant
  and font); two runs over one snapshot never shared a hash. Page one is now
  a section with `sealed=False`, left out of the hash and still rendered with the same rows and words; the data
  facts on it are sealed through `api_url` and `sealed_provenance` (the snapshot's stamp, schema and last poll)
  beside the coverage, the parameters and the rosters switch (`docs/specs/SPEC_F1_data_only_seal.md` §3).

## Design

## 1. Goal
```

### Block 8 — `local-development/pyproject.toml`: application 4.1.0

<!-- block: local-development/pyproject.toml | edit -->
```toml
version = "4.0.0"
```

```toml
version = "4.1.0"
```

### Block 9 — `local-development/gsd/__init__.py`: application 4.1.0

<!-- block: local-development/gsd/__init__.py | edit -->
```python
__version__ = "4.0.0"
```

```python
__version__ = "4.1.0"
```

### Block 10 — `charts/group-sync-dashboard/Chart.yaml`: the chart PATCH and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# declared, platform identities configured (#387).
version: 0.66.4
```

```yaml
# declared, platform identities configured (#387).
# CHART 0.66.5 (2026-10-03), PATCH: appVersion moves to application 4.1.0 (below); #270, SPEC_F1. No
# template, value or RBAC change.
version: 0.66.5
```

### Block 11 — `charts/group-sync-dashboard/Chart.yaml`: application 4.1.0

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# 4.0.0 (2026-10-03). Epic G: access declared, platform identities configured (#387). MAJOR.
appVersion: "4.0.0"
```

```yaml
# 4.0.0 (2026-10-03). Epic G: access declared, platform identities configured (#387). MAJOR.
# 4.1.0 (2026-10-03). A report's sha256 covers its data only: page one's run facts (when, by whom, the run id, the release, the snapshot's age, the marking and the binding interval) leave the hash; two runs over one snapshot with the same parameters hash the same while the values a report computes against the generation clock coincide; every artefact's hash changes once (#270). MINOR.
appVersion: "4.1.0"
```

### Block 12 — `docs/CHANGELOG.md`: the one-time hash change

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

```

```markdown
## Unreleased

- **A report's sha256 covers its data only (#270, Epic F #386, `docs/specs/SPEC_F1_data_only_seal.md`; application
  4.1.0, chart 0.66.5).** Page one (Provenance and coverage) is no longer inside the hash: it states the run. When
  the report was generated, by whom, its run id, the report service's version and commit, the snapshot's age, the
  marking, the binding interval and the PDF variant leave the hash; the data facts on page one stay sealed through
  their own fields: the cluster and its API URL, the snapshot's stamp and schema and the last poll
  (`sealed_provenance`), the coverage, the parameters and the rosters switch. Two runs of a report over one
  snapshot with the same parameters now return the same sha256, whoever runs them; a new snapshot hashes
  differently. Page one keeps every row and word. The `.json` keeps every key and every section and gains
  `sealed_provenance` and a `sealed` flag per section; its hash is the sha256 of the canonical keys with the
  sections narrowed to the sealed ones. **Every artefact generated after this release hashes differently from one
  generated before it over the same data**, once, because what the hash covers changed; stored runs are not
  rewritten and each still matches its own `.json`. Five reports compute part of their data against the generation
  clock, so two of their runs agree only while those values coincide: `login-activity`'s window ends at the
  generation instant (two of its runs agree only at one clock), `groupsync-health` and `compliance-snapshot`
  compute the overdue state against it, `groups`, `groupsync-health` and `compliance-snapshot` count changes in a
  window that ends at it, and `dormant-access` sets its cutoff from it (SPEC_F1, Orchestrator's notes 1). The
  coverage can also reflect two report-service settings (`login_capture_enabled`, `namespaces_read_enabled`), so a
  run under other settings is other evidence. No permission, value or migration.

```

### Block 13 — `local-development/e2e-walk/integrity_check.py`: the walk recomputes the seal as the model does

<!-- block: local-development/e2e-walk/integrity_check.py | edit -->
```python
For every <run>/reports/*.json: recompute the sha256 of the canonical data the same way the
service seals it (gsd/reporting/model.py, Report.seal: name, cluster, params, coverage, totals,
truncated, include_members, sections; sorted keys, compact separators, default=str) and compare
```

```python
For every <run>/reports/*.json: recompute the sha256 of the canonical data the same way the
service seals it (gsd/reporting/model.py, Report.seal: name, cluster, api_url, params, coverage,
totals, truncated, include_members, sealed_provenance, and the sections whose `sealed` is true;
sorted keys, compact separators, default=str; SPEC_F1, #270) and compare
```

<!-- block: local-development/e2e-walk/integrity_check.py | edit -->
```python
CANONICAL = ("name", "cluster", "params", "coverage", "totals", "truncated", "include_members", "sections")


def main() -> int:
```

```python
#: The keys Report.canonical() seals. `sections` is added by recompute(), narrowed to the sealed ones: the
#: .json carries page one too, which states the run and is left out of the hash (SPEC_F1, #270).
CANONICAL = ("name", "cluster", "api_url", "params", "coverage", "totals", "truncated", "include_members",
             "sealed_provenance")


def recompute(d: dict) -> str | None:
    """The sha256 the service sealed, from the .json alone; None for a .json this recipe does not verify, which
    main() writes as a FAIL row: one written before 4.1.0 (no `sealed_provenance`, no `sealed` flags), or one
    whose unsealed sections are not exactly page one, the first (the model leaves only page one out of the hash,
    so any other unsealed section would ride beside the seal unchecked)."""
    flags = [s.get("sealed") for s in d["sections"]]
    if "sealed_provenance" not in d or flags[:1] != [False] or not all(flags[1:]):
        return None
    canon = {k: d[k] for k in CANONICAL}
    canon["sections"] = d["sections"][1:]
    return hashlib.sha256(
        json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def main() -> int:
```

<!-- block: local-development/e2e-walk/integrity_check.py | edit -->
```python
        canon = {k: d[k] for k in CANONICAL}
        recomputed = hashlib.sha256(
            json.dumps(canon, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
```

```python
        recomputed = recompute(d)
```

### Block 14 — `local-development/e2e-walk/build_doc.py`: the walk document states the recipe the check runs

<!-- block: local-development/e2e-walk/build_doc.py | edit -->
```python
  P("<p>Every report is sealed with the sha256 of its canonical data (name, cluster, params, coverage, totals, truncated, include_members, sections; "
```

```python
  P("<p>Every report is sealed with the sha256 of its canonical data (name, cluster, api_url, params, coverage, totals, truncated, include_members, "
    "sealed_provenance, and the sections whose <span class='mono'>sealed</span> is true: page one states the run and is left out; "
```
