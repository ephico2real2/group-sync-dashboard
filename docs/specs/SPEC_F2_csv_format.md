# SPEC F2 — CSV as a fourth report format: one file per run, the browser export's cell rule, off by default (#106)

| | |
|---|---|
| Programme | Epic F (#386), reports: honest seals, more formats, diffs and delivery. Build step 2 of 6: a fourth rendering of the report F1 sealed |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 4.2.0, chart 0.66.6 |
| Version note | The change is image content (a renderer, the service's allow-sets, the trigger, the page), so it takes the next application MINOR, 4.2.0 (`docs/specs/README.md`, the version ladder; SPEC_E5's rule). The chart takes the PATCH that moves `appVersion`, 0.66.6: no value key, default, template logic or RBAC rule changes, only comments and the README row that name `csv` as an allowed word (§3.9, with the measurement). Read on `fba80ff3` (application 4.1.0, chart 0.66.5); the one other `specified` row, W1, holds chart 0.67.0, which stays above 0.66.6, so W1 does not move. A release that lands first makes the version blocks (§7, Blocks 19 to 22) fail their check, and the implementing pull request corrects them here before applying |
| Issue | [#106](https://github.com/ephico2real2/group-sync-dashboard/issues/106) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-03, from the issue's refined body (2026-09-26), `docs/DESIGN_reporting_output_and_delivery.md` §2 re-measured against main, and SPEC_C1's browser export. Measured on main `fba80ff3` with the repository's venv (Python 3.14.7) and node 26.9.0: §2.3's probe built all eleven reports over the seeded snapshot. No lab read; §5 states the walk. §7's blocks were proved against a clean checkout of `fba80ff3` (§4.3) |

## How to read this spec

The plain point first: an auditor who wants a report's tables in a spreadsheet copies them out of the HTML by
hand today. The report service already holds every report as typed sections of tables, key-value lists and
notes, and already writes it three ways. This spec adds a fourth, `csv`: one `report.csv` per run, every block in
order under a labelled record, the sha256 at the top, written cell by cell exactly as the page's own table export
writes a cell. Nobody gets a CSV unless they ask for one.

§1 is the mandate. §2 is the research: the primary sources, the code as it stands, and the probe. §2a weighs the
alternatives. §3 is the design, one rule per subsection with its reason. §4 maps every Definition-of-Done item to
a test and records each one failing on a tree without the change. §5 is the walk on the lab. §6 is what an
operator sees. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F2_csv_format.md . --apply

Line citations into the code at `fba80ff3` are written as `file:line` in plain text inside quoted command output
and tables; prose cites `path#anchor`.

## Orchestrator's notes

1. **The design doc's renderer is not taken.** `docs/DESIGN_reporting_output_and_delivery.md` §2.2 sketches
   `render_csv` over `csv.writer`. Measured (§2.2): `csv.writer` writes `True` where the page writes `true`, a
   Python list's repr where the page joins with `; `, `""` for a lone empty field, and applies no formula guard.
   The issue requires the page's rule, so the renderer ports `csvField` and joins records itself (§3.4).
2. **The design doc's as-is predates #149 and #270** (§2.4 lists each claim that no longer holds). Its status
   line gains one sentence pointing here (Block 23); its body is a proposal record and is not rewritten.
3. **The issue's line numbers moved.** It cites index.html:6638-6660 for `csvField`, `:2802-2803` for the
   checkboxes, `:3915` for the artefact fetch, and test_ui.py:7491 for the catalogue count. On `fba80ff3`
   they are index.html:7154-7170, `:2946-2947`, `:4229` and test_ui.py:9137 (§2.2).
4. **The index count.** The index says "Fifty-three" on `fba80ff3`; this spec's row makes it fifty-four, and
   `local-development/tests/test_specs_index.py` moves from 53 to 54.
5. **The issue-order test.** #106 is below the numbers of the rows above it, so F2 is excluded from the
   rising-number assert by its id and pinned to #106, the way F1 (#270) was.
6. **Dates.** Blocks 21 and 22 date the chart and application history lines 2026-10-03; the implementing pull
   request writes its own date there if it differs.
7. **The form's boxes do not follow `reporting.formats.manual`.** The page posts an explicit list from its
   checkboxes (index.html:4177-4179), so the manual default applies only to an API caller that names no
   formats. The new CSV box follows the PDF and HTML boxes: a fixed default (unticked). Open question 2.

**Review of the implementation (PR #575, 2026-10-03): Codex (gpt-5.6-sol, xhigh) and OB3 (in Grok's seat).** Both
confirmed the formula guard (hostile names planted across all 11 reports: no unguarded cell), the RFC 4180 shape,
the seal (the CSV's sha256 record equals the `.json`, the run record and `X-GSD-Report-SHA256`), the wiring, the
unchanged bytes of json, html and pdf, and the chart (comments and version lines). The decisions:
- **Accepted: floats were laid out the Python way (both reviewers).** `1e21` was `1000000000000000000000` against the
  page's `1e+21`, and `1e-6` was `1e-06` against `0.000001`. No report emits a float today (OB3 counted 1,598 string
  and 188 integer cells over all 11 reports), but the mandate is "the same rule" in both exports. OB3's `_js_number`
  ports ECMA-262 Number::toString, and twelve cells in T106-2 hold it, cross-checked in node by T106-3.
- **Rejected: Codex's version of that fix** converts every integer to a double first. That rounds an integer above
  2**53, which the `.json` holds exactly; the CSV keeps it whole.
- **Accepted: a repaint of the form undid the format boxes (OB3, C7).** Ticking CSV, then any switch, segment or
  lookup pick, repainted the form from fixed defaults, and Generate posted `['html','pdf']`: the CSV was dropped.
  The boxes now live in `view.reportWant`, like Advanced's open state. Codex had confirmed C7; OB3's reproduction is
  the new browser test, which fails on the implementation's first head. The same repaint also undid an unticked
  PDF; that is fixed by the same lines.

Open questions only the operator can answer:

1. **The chart rung.** This spec reads the chart's own rule ("MAJOR and MINOR for behaviour, PATCH for a fix or
   a defaults change", `charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`) and its history
   (0.59.10 to 0.59.23: an application feature with no value change is a PATCH; 0.60.0, 0.66.0: new values are a
   MINOR) and takes 0.66.6: no key, default or template logic changes, and a rendered `csv` list is byte-equal
   before and after (§3.9). If the operator reads a new allowed word as a values change, the rung is 0.67.0,
   and W1's row and header move to 0.68.0 in the same pull request.
2. Should the form's three format boxes start from the deployment's `reporting.formats.manual` (read from
   `/report/api/status`) instead of fixed defaults? Out of scope here: it changes the PDF and HTML boxes too.

## 1. The mandate, and what is out of scope

The mandate (#106, "The change"): settle the file's shape, the formula-injection guard (the browser export's
rule) and the provenance; then build `csv` as an opt-in format within #149's origin-aware defaults: a generic
renderer over `Section` → `Table | KeyValues | Note`; `csv` in `FORMATS`, in `create_run`'s allow-set, in the
artefact endpoint's pattern and media map, in the trigger's `--format` choices and in
`reporting.formats.{scheduled,manual}`; a `report-want-csv` checkbox; a download button wherever a run's
formats are listed.

Must not change (the issue): the existing formats' bytes and the default format sets (`[html, json]`
scheduled, `[html, json, pdf]` manual); the browser-side table export (SPEC_C1); the artefact store's layout
(one directory per run) and its two-tier retention; the eleven-report catalogue.

Out of scope: XLSX or any other format (refused, T106-6); one CSV per table (§2a); delivery of a CSV by a
schedule (Epic F's delivery step); the form's defaults following the deployment (open question 2).

## 2. Research, measured

### 2.1 Primary sources

| Source (fetched 2026-10-03) | The sentence relied on | What it settles |
|---|---|---|
| RFC 4180, <https://www.rfc-editor.org/rfc/rfc4180.txt>, §2.1 | "Each record is located on a separate line, delimited by a line break (CRLF)." | Records end in CRLF, the last one too (§2.2: "The last record in the file may or may not have an ending line break"; this file has one, as the page's does) |
| RFC 4180, §2.4 | "Each line should contain the same number of fields throughout the file." | A SHOULD, not a MUST. A report's blocks have different widths; §3.2 accepts ragged records and says so |
| RFC 4180, §2.6 and §2.7 | "Fields containing line breaks (CRLF), double quotes, and commas should be enclosed in double-quotes." "…a double-quote appearing inside a field must be escaped by preceding it with another double quote." | The quoting rule `csvField` already applies |
| RFC 4180, §3 | "Optional parameters: charset, header" … "The "header" parameter indicates the presence or absence of the header line. Valid values are "present" or "absent"." | The media type: `text/csv; charset=utf-8; header=absent` (the first record is the title, not field names) |
| RFC 7111 (`text/csv` fragment identifiers, `#row=`, `#col=`, `#cell=`) | — | Not used: nothing links into a CSV. Its row numbering counts records, so a ragged file stays addressable |
| OWASP, "CSV Injection", <https://owasp.org/www-community/attacks/CSV_Injection> | The initiators: "Equals to (=)", "Plus (+)", "Minus (-)", "At (@)", "Tab (0x09)", "Carriage return (0x0D)". The advice: "Wrap each cell field in double quotes", "Prepend each cell field with a single quote", "Escape every double quote using an additional double quote". "Note: The above techniques are not reliable in Microsoft Excel after saving and re-opening the CSV file." | The guard: an apostrophe before a formula-leading cell. `csvField` prefixes rather than wrapping every field, and adds LF and the full-width forms (SPEC_C1's review); the service takes the page's rule as it is (§3.4). OWASP's last note is why the guard is defence in depth, not a guarantee (§6) |
| Python `csv`, <https://docs.python.org/3/library/csv.html>, `QUOTE_MINIMAL` | "Instructs writer objects to only quote those fields which contain special characters such as delimiter, quotechar, quoting or any of the characters in lineterminator." | Measured in §2.2: quoting agrees with RFC 4180 for text, but the type conversions and the lone-empty-field rule differ from the page's; not used |

### 2.2 The code, read on `fba80ff3`, and the measurements

The report service (each line read with `grep -n` on `fba80ff3`):

```text
local-development/gsd/reporting/artifacts.py:27     FORMATS = ("json", "html", "pdf")
local-development/gsd/reporting/artifacts.py:181-188 write(): refuses fmt not in FORMATS; writes <run dir>/report.<fmt> via .tmp + os.replace
local-development/gsd/reporting/artifacts.py:293,359,389 retention and deletes: shutil.rmtree(self._dir(run.id)) — the whole run directory
local-development/gsd/reporting/server.py:82-83     RunRequest.formats: "Subset of html, pdf; json is always written."
local-development/gsd/reporting/server.py:343-352   formats None -> the origin default (pdf dropped where pdf is off); else refuse anything outside {"html", "pdf"}
local-development/gsd/reporting/server.py:577-578   status payload: formats.scheduled/.manual = the settings + ["json"]
local-development/gsd/reporting/server.py:603       get_artifact: Query(default="pdf", pattern="^(json|html|pdf)$")
local-development/gsd/reporting/server.py:612-614   media map json/html/pdf; filename gsd_<cluster>_<report>_<stamp>.<format>
local-development/gsd/reporting/runs.py:183-191     json written always, then html if asked, then pdf if asked
local-development/gsd/reporting/trigger.py:55       --format choices=["html", "pdf"]
local-development/gsd/reporting/config.py:82-93     _formats_env: allowed {"html", "pdf", "json"}, json dropped, anything else SystemExit
local-development/gsd/reporting/config.py:205-206   formats_scheduled = ("html",), formats_manual = ("html", "pdf")
local-development/gsd/reporting/render_html.py:74   context(): data = json.loads(report.to_json()) — the HTML renders from the .json form
```

The two default sets differ in form, not in content: the chart lists `json` (`charts/group-sync-dashboard/values.yaml`
`reporting.formats`: `scheduled: [html, json]`, `manual: [html, json, pdf]`; the template's fallback
`list "html" "json"` and `list "html" "json" "pdf"`, templates/report-deployment.yaml:101-104), the service
does not (config.py:205-206), because `_formats_env` accepts a listed `json` and drops it: json is always
written. Both are held today by `test_chart_reporting.py::test_the_origin_formats_reach_the_report_pod`
(`"html,json"`, `"html,json,pdf"`) and `test_reporting_server.py::test_formats_default_by_origin_and_json_is_implied`
(`["html", "pdf"]`, `["html"]`). The chart has no `values.schema.json`; nothing in the chart constrains the
words: templates/report-cronjob.yaml:86-91 passes every non-`json` entry of a schedule's `formats` as `--format`.

The page (`local-development/gsd/static/index.html` on `fba80ff3`):

```text
:2933        the Generate button's label: PDF · HTML · JSON (what the form offers)
:2946-2947   report-want-pdf (only where pdf is enabled) and report-want-html, both checked
:3163-3164   a run's status: one Download button per run.formats + json
:3282        the history list: one link per x.formats + json
:3407, :3541 the Library card and the run drawer: one button per key of run.bytes
:4177-4179   generateReport posts formats from the two boxes (an explicit list, never the default)
:4228-4234   downloadArtifact: the one artefact fetch, format=<f>, the server's filename
:7154-7170   CSV_BOM and csvField; :7174-7176 toCsv: BOM + records joined by CRLF + a final CRLF
```

So every place a run's formats are listed derives them from `run.formats` or `run.bytes`: a stored `csv`
gets its button with no change there. The catalogue counts: test_reporting_server.py:801
(`len(body["reports"]) == 11`), `:1392` (`reports_enabled == 11`); test_ui.py:8740, `:9137`, `:9342`, `:9867`.

What `csv.writer(quoting=QUOTE_MINIMAL, lineterminator="\r\n")` writes, measured with the venv's Python
3.14.7:

```text
['']            -> '""\r\n'        (the page writes an empty line)
[None]          -> '""\r\n'
[True]          -> 'True\r\n'      (the page writes true)
[1.0]           -> '1.0\r\n'       (the page writes 1)
[['a', 'b']]    -> '"[\'a\', \'b\']"\r\n'   (the page writes a; b)
['=1+1']        -> '=1+1\r\n'      (the page writes '=1+1)
['a,b']         -> '"a,b"\r\n'     ['say "hi"'] -> '"say ""hi"""\r\n'   ['x\ry'] -> '"x\ry"\r\n'   (as the page)
```

### 2.3 The probe: what a report's cells hold

The probe (kept in the scratch directory, not in the tree) seeds the report suite's database
(`local-development/tests/reporting_seed.py#seed_store`), writes one snapshot, builds all eleven reports and
walks `json.loads(report.to_json())`. On `fba80ff3`:

```text
blocks {'kv': 25, 'note': 54, 'table': 44}
cell types {'str': 799, 'int': 94}
floats []
kv item shape list
```

What it settles: the three block kinds are the whole set the renderer must walk; on the seed a cell is a string
or an integer (a boolean, a null, a float or a list was not observed on the seed, and the port handles each the
way the page does); a key-value item arrives from the `.json` as a two-element list.

### 2.4 What `DESIGN_reporting_output_and_delivery.md` says that no longer holds

| The design doc | `fba80ff3` |
|---|---|
| §1: "formats ⊆ {html,pdf}" decided by the request alone | #149 R3: a request naming no formats gets the origin default (server.py:343-345); the deployment can change both sets (config.py:265-266) |
| §1: `store.write(id,"json",canonical); if html…; if pdf…` | Unchanged in order (runs.py:183-191); the `.json` now carries `sealed` flags and `sealed_provenance` (#270) |
| §2.2: "`test_ui.py`'s `["html","json","pdf"]` and `test_reporting_server.py`'s `{"json","html","pdf"}` stay green" | The UI pins `data-format` per button, not a list; the server pins `{"json", "html", "pdf"}` at test_reporting_server.py:133 for an explicit `["html", "pdf"]` request: unchanged by an opt-in format |
| §2.2's renderer: a `#`-prefixed label row, `csv.writer`, `"" if c is None` | Not taken: §2a, Orchestrator's notes 1 |
| "the download button appears because `run.formats` carries csv" | True for the status and history (index.html:3163, `:3282`); the Library and the drawer read `run.bytes` (`:3407`, `:3541`), which carries `csv` once written |
| "Status: proposed" | Block 23 adds that §2 is built by this spec |

## 2a. Alternatives considered

| Option | Source | Cost here | Decision |
|---|---|---|---|
| A. One `report.csv` per run, every block under a labelled record | the issue, the design doc §2 | Ragged records (RFC 4180 §2.4 is a SHOULD); one file, one format key, one download | **Chosen** |
| B. One CSV per table | the issue's alternative | A run would hold N files under one format, so `ArtifactStore.write(run_id, fmt, data)`, `read(run_id, fmt)`, the endpoint's one-file-per-format answer, `run.bytes[fmt]` and the page's one-button-per-format all change, or the files go in a zip (a fifth format in disguise). The issue's "Must not change" holds the store's layout | Rejected |
| C. A long ("tidy") file: fixed columns `section,block,row,column,value` | — | RFC-regular, but a spreadsheet user sees one value per line, not the report's tables | Rejected: the reader is an auditor in a spreadsheet |
| D. `csv.writer` with a guard in front | the design doc §2.2 | Measured in §2.2: `True`, a list's repr, `""` for a lone empty field; the same cell would differ from the page's | Rejected: the issue requires the page's rule |
| E. Port `csvField` and join records as `toCsv` does | SPEC_C1 | About 20 lines; pinned to the JavaScript by T106-3 | **Chosen** |
| F. No BOM | RFC 4180 does not mention one | A double-clicked file opens in the local code page and mangles a non-ASCII name (the page's own reason, index.html:7169-7171) | Rejected: the service's file matches the page's |

**Reconciliation.** RFC 4180 §2.1 and §2.6-2.7 are what `csvField` and `toCsv` do (index.html:7154-7176), and
what `local-development/gsd/reporting/render_csv.py#csv_field` and `#render_csv` do after the change. OWASP's six
initiators are a subset of the guard's class; its "prepend a single quote" is the guard's action; its "wrap every
field" is not taken, by the page or here (quoting only where RFC 4180 needs it keeps numbers numeric in a
spreadsheet). Python's `QUOTE_MINIMAL` agrees with RFC 4180 on quoting text; it is not used because its type
conversions differ (§2.2).

## 3. The design

### 3.1 One file per run

A run asked for `csv` stores one `report.csv` in its own directory beside `report.json` and `run.json`, like
`report.html` and `report.pdf`. Reason: the store keeps one file per format per run (artifacts.py:181-201), the
endpoint serves one file per format, and retention deletes the run's directory whole (`artifacts.py:293, 359,
389`); a CSV is one more file there and nothing else moves (T106-5 lists the directory).

### 3.2 The file's shape

```text
<BOM>Report,<title>
sha256 of the report data,<sha256>

Section,<section title>,sealed | not sealed: states the run

Table,<table title>                 List,<list title>          <Level>,<note text>
<column>,<column>,…                 <key>,<value>
<cell>,<cell>,…                     …
…  (or one record: <empty text>)
Note,<table note>   (when the table has one)
```

A blank record opens every `Section` record and every block. A table always prints its columns, then its rows,
or one record holding its empty text. A note's label is its level capitalised (`Note`, `Warning`, `Caveat`).
Records are ragged (RFC 4180 §2.4 is a SHOULD): a spreadsheet opens each block as a grid under its label, and a
script splits blocks on the blank records. Reason: the auditor's question is "show me the tables"; the labels say
which table, and nothing is invented that the model does not hold.

### 3.3 Provenance

The first two records are the title and the sha256 the run sealed, the same two facts the PDF prints at its top
(render_pdf.py:93, 97: "sha256 of the report data: …"). Page one ("Provenance and coverage") follows as the
first section, its rows written like any other block, under `Section,Provenance and coverage,not sealed: states
the run`. Reason: the sha256 ties the CSV to its `.json` and its run (`X-GSD-Report-SHA256`, `GET
/report/api/runs`), and page one says what was read, when and by whom.

The CSV never changes the seal: the renderer reads `json.loads(report.to_json())` after `seal()` and prints
`sha256`; it never calls `canonical()` or `seal()`, and the sealed report is not mutated (T106-4 re-seals after
rendering and compares). The sha256 is over the data (SPEC_F1), so the CSV of a run and its `.json` carry the same
number.

### 3.4 A cell is written as the page writes it

`csv_field` is `index.html`'s `csvField`, ported line for line: `None` → empty; a list → its items joined with
`; `; a boolean → `true`/`false`; a number → JavaScript's `String()` of it; any other value → its text, with an
apostrophe in front when, after any leading spaces, tabs, CRs or LFs, it starts with `= + - @`, tab, CR, LF or a
full-width `＝ ＋ － ＠`; then quoted, quotes doubled, when it holds `"`, `,`, CR or LF. Records are joined with
CRLF, end with CRLF, and the file starts with the UTF-8 BOM, as `toCsv` does. Reason: the issue's rule ("the two
CSV exports treat a cell the same way"), and RFC 4180 §2.6-2.7.

How parity is held: T106-3 compares `index.html`'s `CSV_BOM` and `csvField` source, verbatim, to a copy in the
test, so a change to the page's function fails until the port follows; and where `node` is installed (it is on
this machine, 26.9.0; CI's runner image is not asserted) it runs the page's function and the port over the same
24 cells and compares the outputs. Measured on the applied copy (§4.3): equal. Floats are laid out by ECMAScript's
Number::toString (`_js_number`, from the review of the implementation): `1e+21`, `0.00001`, `1e-7`, as the page
writes them. An integer beyond 2**53 is written whole, as the `.json` holds it, where the page's `JSON.parse` has
already rounded it.

### 3.5 Generic over the model

`render_csv` walks `doc["sections"]` and each section's `blocks`, dispatching on `kind` (`table`, `kv`, `note`),
as `templates/section.html` dispatches to one partial per kind. A kind it does not know raises `ValueError`, so a
new block kind gets its CSV form on purpose, like its HTML partial and PDF routine. No report has code here (T106-4
renders all eleven).

### 3.6 Where `csv` is wired, each with its file

| Where | Change |
|---|---|
| `gsd/reporting/artifacts.py` `FORMATS` | gains `"csv"`, so `write()` accepts it |
| `gsd/reporting/render_csv.py` | new: `CSV_BOM`, `csv_field`, `render_csv` |
| `gsd/reporting/runs.py` the render step | `csv` written right after the `.json`, when asked |
| `gsd/reporting/server.py` `RunRequest.formats` | the description names csv |
| `gsd/reporting/server.py` `create_run` | the allow-set is `{"html", "pdf", "csv"}`; `xlsx` and anything else stay 422 |
| `gsd/reporting/server.py` `get_artifact` | the pattern `^(json\|html\|pdf\|csv)$`; `csv` → `text/csv; charset=utf-8; header=absent`; the filename's extension is the format, so `.csv` |
| `gsd/reporting/server.py` the status payload | no change: it lists the configured sets plus `json`, so a configured `csv` shows |
| `gsd/reporting/trigger.py` `--format` | choices `html`, `pdf`, `csv` |
| `gsd/reporting/config.py` `_formats_env` | accepts `csv` |
| `gsd/static/index.html` the form | a `report-want-csv` box, unticked, after HTML; `generateReport` posts `csv` when ticked |
| `gsd/static/index.html` the run lists | no change: buttons come from `run.formats` and `run.bytes` (§2.2) |
| `local-development/API.md` | the artefact row names csv and its media type |
| `charts/…/values.yaml`, `templates/report-cronjob.yaml`, `README.md` | comments and the README row name `csv` as allowed and off by default; no key or default changes |

### 3.7 Off by default

`csv` is in no default set: `ReportSettings.formats_scheduled == ("html",)`, `formats_manual == ("html", "pdf")`,
the chart's `[html, json]` and `[html, json, pdf]`, all unchanged; the form's box is unticked. An operator turns
it on per origin with `reporting.formats.scheduled: [html, json, csv]` (or `.manual`), or per schedule with
`schedules[].formats`. Reason: the issue ("CSV is off unless the operator adds it").

### 3.8 What does not change, and the test that holds it

| Must not change | Held by |
|---|---|
| The existing formats' bytes | No block touches `model.py`, `render_html.py`, `render_pdf.py` or the templates (§4.3's `git diff --stat`); `test_reporting_render.py` and `test_reporting_server.py` pass unchanged |
| The default format sets | T106-7, `test_formats_default_by_origin_and_json_is_implied`, `test_the_origin_formats_reach_the_report_pod`, the status test's `formats` assert (test_reporting_server.py:1393) |
| The browser export | T106-3 pins `csvField` and `CSV_BOM` verbatim; no block edits them |
| The store's layout and retention | T106-5 lists the run directory; no block touches `artifacts.py` beyond `FORMATS` |
| The eleven-report catalogue | test_reporting_server.py:801, `:1392`; test_ui.py:8740, `:9137`; T106-4 iterates `REGISTRY` |

### 3.9 The chart takes a PATCH

Measured: `helm template` of the chart on `fba80ff3` with `--set reporting.formats.scheduled={html,json,csv}`
renders `GSD_REPORT_FORMATS_SCHEDULED` as `"html,json,csv"` (§4.3): the chart already passes the word; only the
service refused it. After the blocks, the same render differs from main's in the version labels, the image tags `appVersion`
sets, a config checksum and one hashed Job name, and nothing else (§4.3); the CronJob comment renders only with a
schedule. No key, default or RBAC rule changes, so by the chart's
rule the bump is a PATCH (open question 1).

### 3.10 Safety budget

The change binds, widens and migrates nothing: no RBAC, no new value key, no schema migration. A CSV is written
only when asked, into the run's own directory, and is removed with it by the existing retention. The budget over
the system: zero new permissions, zero rows rewritten, zero existing artefacts rewritten.

## 4. Tests

### 4.1 One test per Definition-of-Done item

`local-development/tests/test_report_csv.py` (block 12) and one browser test (block 13).

| ID | Test | Definition-of-Done item |
|---|---|---|
| T106-1 | `test_t106_1_the_renderer_walks_a_table_a_list_and_a_note` | The renderer over a `Table`, a `KeyValues` and a `Note`: exact bytes |
| T106-2 | `test_t106_2_a_formula_leading_cell_is_neutralised` (24 cells) | A formula-leading cell is neutralised |
| T106-3 | `test_t106_3_the_port_is_the_browser_export` | The same cell becomes the same text in both exports |
| T106-4 | `test_t106_4_every_report_renders_with_its_seal_and_page_one` (all eleven) | Generic renderer; sha256 and page one in the file; the seal unchanged |
| T106-5 | `test_t106_5_a_run_stores_and_serves_csv` | `create_run` accepts `csv`; the endpoint serves `text/csv`; the store's layout |
| T106-6 | `test_t106_6_create_run_refuses_xlsx_and_the_settings_accept_csv` | `create_run` refuses `xlsx`; `reporting.formats.*` may list `csv` |
| T106-7 | `test_t106_7_csv_is_off_unless_configured` | The default formats are unchanged when `csv` is not configured |
| T106-8 | `test_t106_8_the_schedule_trigger_takes_csv` | The trigger's `--format` takes `csv` |
| T106-9 | `test_ui.py::…::test_csv_is_a_box_off_by_default_and_a_ticked_one_downloads_a_csv` | The `report-want-csv` box, and a download button for the stored CSV |
| T106-10 | `test_ui.py::…::test_a_ticked_csv_box_survives_a_repaint_of_the_form` | A ticked CSV and an unticked PDF survive a repaint of the form and reach the POST (the review, OB3) |

### 4.2 Each test fails without the change, and why

Run on a clean `fba80ff3` with only block 12's file added (§4.3):

- T106-1, T106-2 (24 cases), T106-3, T106-4: `ModuleNotFoundError: No module named 'gsd.reporting.render_csv'`.
- T106-5: `{"detail":"unknown format(s) ['csv']; json is always written"}`, `assert 422 == 202`.
- T106-6: `SystemExit: GSD_REPORT_FORMATS_SCHEDULED='html,json,csv': unknown format(s) ['csv']; allowed html, pdf
  (json is always written)`. Its `xlsx` assertion passes on both trees.
- T106-7: passes on both trees: it guards the issue's "Must not change".
- T106-8: `argparse.ArgumentError: argument --format: invalid choice: 'csv' (choose from 'html', 'pdf')`,
  `SystemExit: 2`.
- T106-9: on main the form has no `#report-want-csv`; `wait_for_selector` times out (by construction; not run, §4.3).
- T106-10: on the implementation's first head (`51544845`), `AssertionError: the repaint undid the reader's boxes` (OB3's run).

### 4.3 The proof

The blocks checked against a clean detached worktree of `fba80ff3`, then applied to it, with
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.` from its `local-development` and the repository's venv (Python 3.14.7).
Recorded:

```text
$ python local-development/apply-spec-blocks.py docs/specs/SPEC_F2_csv_format.md <clean fba80ff3>
25 blocks check out across 18 files

before the blocks (block 12's file alone added to the clean tree):
  tests/test_report_csv.py: 30 failed, 1 passed
    T106-1, T106-2 (24 cases), T106-3, T106-4: ModuleNotFoundError: No module named 'gsd.reporting.render_csv'
    T106-5: AssertionError: {"detail":"unknown format(s) ['csv']; json is always written"}; assert 422 == 202
    T106-6: SystemExit: GSD_REPORT_FORMATS_SCHEDULED='html,json,csv': unknown format(s) ['csv']; allowed html, pdf (json is always written)
    T106-7: passed (the guard)
    T106-8: argparse.ArgumentError: argument --format: invalid choice: 'csv' (choose from 'html', 'pdf'); SystemExit: 2
  tests/test_ui.py -k csv_is_a_box (block 13's test alone on the clean tree):
    playwright._impl._errors.TimeoutError: Page.wait_for_selector: Timeout 30000ms exceeded.

$ python local-development/apply-spec-blocks.py docs/specs/SPEC_F2_csv_format.md <clean fba80ff3> --apply
25 blocks check out across 18 files
$ git diff --stat        (the tracked files; render_csv.py and test_report_csv.py are new)
 charts/group-sync-dashboard/Chart.yaml        |  8 ++++++--     local-development/gsd/__init__.py             |  2 +-
 charts/group-sync-dashboard/README.md         |  2 +-         local-development/gsd/reporting/artifacts.py  |  2 +-
 .../templates/report-cronjob.yaml             |  2 +-         local-development/gsd/reporting/config.py     |  6 +++---
 charts/group-sync-dashboard/values.yaml       |  2 ++         local-development/gsd/reporting/runs.py       |  4 ++++
 docs/CHANGELOG.md                             | 11 +++++++++++  local-development/gsd/reporting/server.py     | 10 ++++++----
 docs/DESIGN_reporting_output_and_delivery.md  |  5 ++++-      local-development/gsd/reporting/trigger.py    |  2 +-
 local-development/API.md                      |  2 +-         local-development/gsd/static/index.html       |  2 ++
 local-development/pyproject.toml              |  2 +-         local-development/tests/test_ui.py            | 23 ++++++++++
 16 files changed, 68 insertions(+), 17 deletions(-)
 (no change to model.py, render_html.py, render_pdf.py, the templates, artifacts.py beyond FORMATS, or csvField)

after the blocks:
  tests/test_report_csv.py: 31 passed in 4.17s   (node 26.9.0 on PATH: T106-3 ran the page's csvField and the port)
  tests/test_report_csv.py tests/test_reporting_*.py tests/test_report_seal.py tests/test_chart_versions.py
  tests/test_docs_citations.py tests/test_kyverno.py tests/test_p2_selectors.py tests/test_chart_reporting.py:
                                                  2228 passed, 18 skipped in 62.28s
  tests/test_ui.py -k "csv_is_a_box or several_clusters_run_as_one_action": 2 passed, 683 deselected in 6.34s
  this spec's branch (the spec, its index row, the index test at 54):
  tests/test_specs_index.py tests/test_docs_citations.py: 1935 passed, 19 skipped in 18.88s
the full hermetic suite and the whole browser suite: not run (the budget); the implementing pull request runs them

$ helm template t <chart> --set 'reporting.formats.scheduled={html,json,csv}'   (§3.9)
  fba80ff3:      GSD_REPORT_FORMATS_SCHEDULED value: "html,json,csv"
  applied copy:  GSD_REPORT_FORMATS_SCHEDULED value: "html,json,csv"
  diff, every changed line counted: 43 app.kubernetes.io/version 4.1.0 -> 4.2.0; 43 helm.sh/chart 0.66.5 -> 0.66.6;
  5 image tags 4.1.0 -> 4.2.0; 2 checksum/config; 1 backup-offsite bind Job name hash. Nothing else.
```

## 5. On the lab (the implementing pull request)

After the image is deployed through the release's values file and pipeline:

1. As a wide-tier viewer, open Reports, pick `groups` on one cluster, tick CSV (it starts unticked), untick PDF,
   Generate. Pass: the status offers Download .html, .csv and .json.
2. Download the `.csv` and open it in a spreadsheet. Pass: row 1 is `Report` and the title, row 2 the sha256;
   `GET /report/api/runs/<id>` gives the same `sha256`; the `Provenance and coverage` rows follow; each table
   sits under its `Table` label with its columns.
3. In the release's values file add `csv` to `reporting.formats.scheduled`, sync, and let a schedule fire (or
   run its CronJob's Job by hand). Pass: the run's `bytes` has `json`, `html` and `csv`.
4. Remove `csv` again. Pass: the next scheduled run stores `json` and `html` only.

The evidence goes under `reports/<date>_<slug>/` and on #106, pinned to the full merge sha. No lab write is made
by this spec.

## 6. What an operator sees, and what it costs

A reader sees a CSV box beside PDF and HTML on the report form, unticked, and a `.csv` button on any run that
stored one. The file opens in a spreadsheet with the report's tables under their labels, the sha256 at the top,
and page one's rows. A cell a spreadsheet would evaluate opens as text with a leading apostrophe, as the page's
export does; OWASP notes that Excel can strip that guard when a file is saved and re-opened, so the guard protects
the first open, not a re-saved copy. An operator who wants CSV on every scheduled run adds `csv` to
`reporting.formats.scheduled`. Cost: one module of about ninety lines, nine one-line wiring changes, one box on
the page; no RBAC, value key, migration or runtime cost for a run that does not ask for CSV.

## 7. Implementation blocks

### Block 1 — `local-development/gsd/reporting/artifacts.py`: the store accepts `csv`

<!-- block: local-development/gsd/reporting/artifacts.py | edit -->
```python
FORMATS = ("json", "html", "pdf")
```

```python
FORMATS = ("json", "html", "pdf", "csv")
```

### Block 2 — `local-development/gsd/reporting/render_csv.py`: the renderer

<!-- block: local-development/gsd/reporting/render_csv.py | create -->
```python
"""The CSV rendering of a Report (#106, docs/specs/SPEC_F2_csv_format.md): one file per run, every block
of every section in order, each under a labelled record, so a spreadsheet opens the report's tables and a
script can split them.

WHY NOT csv.writer. The page's table export (index.html `csvField`, SPEC_C1) already decides how a cell
becomes CSV: RFC 4180 quoting, a formula guard, `true`/`false`, arrays joined with "; ". csv.writer writes
`True`, a list's Python repr, `""` for a lone empty field and no guard (SPEC_F2 §2.2), so one cell would be
two different texts in the two exports. `csv_field` is the browser's function, ported; a test pins the port
to the JavaScript source and runs both side by side where node is installed.

The renderer reads the report's own JSON (`json.loads(report.to_json())`), as the HTML renderer does: the
JSON types the page's export reads too. It prints the sha256 and never computes it, so a CSV cannot change
the seal.
"""

from __future__ import annotations

import json
import math
import re
from decimal import Decimal

from .model import Report

#: UTF-8's byte-order mark, first in the file: a spreadsheet opened by a double-click reads BOM-less UTF-8
#: in the local code page and mangles a non-ASCII name (index.html `CSV_BOM`, SPEC_C1).
CSV_BOM = "﻿"
#: index.html `csvField`'s formula initiators, tested after any leading whitespace: OWASP's = + - @ tab CR,
#: plus LF and the full-width = + - @ (U+FF1D, U+FF0B, U+FF0D, U+FF20).
_FORMULA = re.compile("^[\t\r\n ]*[=+\\-@\t\r\n＝＋－＠]")
#: RFC 4180 §2.6: a field holding a double quote, a comma or a line break is enclosed in double quotes.
_NEEDS_QUOTES = re.compile('[",\r\n]')
#: The label record that opens a table-like block. A kind not here and not a note is refused, so a new
#: block kind gets its CSV form on purpose, as it gets its HTML partial and its PDF routine.
_LABEL = {"table": "Table", "kv": "List"}


def _js_string(value) -> str:
    """JavaScript's String(value) for the JSON scalars a report cell holds. An int is written whole: past
    2**53 the page's JSON.parse has already rounded it, and the CSV keeps the value the .json holds."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return _js_number(value)
    return str(value)


def _js_number(value: float) -> str:
    """ECMAScript's Number::toString of a float. repr() picks the same shortest round-trip digits; only the
    layout differs: JavaScript writes 2 for 2.0, 0.00001 for 1e-05, 1e-7 for 1e-07, and 1e+21 where
    str(int(1e21)) wrote all 22 digits (ECMA-262 Number::toString: exponent form below 1e-6 and from 1e21)."""
    if not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    if value == 0:
        return "0"
    sign, digits, exponent = Decimal(repr(value)).normalize().as_tuple()
    s, k = "".join(map(str, digits)), len(digits)
    n = exponent + k                                   # value = 0.<s> x 10**n, ECMA-262's n and k
    if k <= n <= 21:
        body = s + "0" * (n - k)
    elif 0 < n <= 21:
        body = s[:n] + "." + s[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * -n + s
    else:
        body = s[0] + ("." + s[1:] if k > 1 else "") + ("e+" if n > 0 else "e-") + str(abs(n - 1))
    return ("-" if sign else "") + body


def csv_field(value) -> str:
    """One cell, written as index.html's `csvField` writes it: null is empty, a list joins with "; ",
    numbers and booleans are written as they are, a text a spreadsheet would evaluate gets a leading
    apostrophe, and a text holding a quote, a comma or a line break is quoted with its quotes doubled."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = "; ".join(_js_string(v) for v in value)
    elif isinstance(value, (bool, int, float)):
        return _js_string(value)
    text = str(value)
    if _FORMULA.match(text):
        text = "'" + text
    if _NEEDS_QUOTES.search(text):
        text = '"' + text.replace('"', '""') + '"'
    return text


def _block(block: dict) -> list[list]:
    """A blank record, the block's label record, then its records. Generic over the three kinds."""
    kind = block["kind"]
    if kind == "note":
        return [[], [block["level"].capitalize(), block["text"]]]
    if kind not in _LABEL:
        raise ValueError(f"no CSV rendering for block kind {kind!r}")
    records = [[], [_LABEL[kind], block["title"]]]
    if kind == "kv":
        return records + [list(item) for item in block["items"]]
    # The columns say what was looked for even when nothing was found, so they head an empty table too.
    records += [block["columns"], *(block["rows"] or [[block["empty_text"]]])]
    if block.get("note"):
        records.append(["Note", block["note"]])
    return records


def render_csv(report: Report) -> str:
    """The whole file: the BOM, then CRLF-ended records (RFC 4180 §2.1). First the title and the sha256
    the run sealed, as the PDF prints them; then every section in order, page one included, each opened
    by a `Section` record that says whether the sha256 covers it."""
    doc = json.loads(report.to_json())
    records: list[list] = [["Report", doc["title"]], ["sha256 of the report data", doc["sha256"]]]
    for section in doc["sections"]:
        records += [[], ["Section", section["title"], "sealed" if section["sealed"] else "not sealed: states the run"]]
        for block in section["blocks"]:
            records += _block(block)
    return CSV_BOM + "\r\n".join(",".join(csv_field(v) for v in record) for record in records) + "\r\n"
```

### Block 3 — `local-development/gsd/reporting/runs.py`: the import

<!-- block: local-development/gsd/reporting/runs.py | edit -->
```python
from .render_html import render_html
```

```python
from .render_csv import render_csv
from .render_html import render_html
```

### Block 4 — `local-development/gsd/reporting/runs.py`: the render step writes the CSV after the `.json`

<!-- block: local-development/gsd/reporting/runs.py | edit -->
```python
            run.bytes["json"] = self.store.write(run.id, "json", canonical)
            if "html" in run.formats:
```

```python
            run.bytes["json"] = self.store.write(run.id, "json", canonical)
            if "csv" in run.formats:
                # A rendering of the sealed report, like the HTML: it prints the sha256, never computes it (#106).
                run.bytes["csv"] = self.store.write(run.id, "csv", render_csv(report).encode("utf-8"))
            if "html" in run.formats:
```

### Block 5 — `local-development/gsd/reporting/server.py`: the request field names csv

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
    formats: list[str] | None = Field(default=None, description="Subset of html, pdf; json is always written. Omitted: "
```

```python
    formats: list[str] | None = Field(default=None, description="Subset of html, pdf, csv; json is always written. Omitted: "
```

### Block 6 — `local-development/gsd/reporting/server.py`: `create_run` accepts `csv`

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
            bad = sorted(set(body.formats) - {"html", "pdf"})
```

```python
            bad = sorted(set(body.formats) - {"html", "pdf", "csv"})
```

### Block 7 — `local-development/gsd/reporting/server.py`: the artefact endpoint serves `csv`

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
                     format: str = Query(default="pdf", pattern="^(json|html|pdf)$", description="json, html or pdf."),
```

```python
                     format: str = Query(default="pdf", pattern="^(json|html|pdf|csv)$", description="json, html, pdf or csv."),
```

<!-- block: local-development/gsd/reporting/server.py | edit -->
```python
        media = {"json": "application/json", "html": "text/html; charset=utf-8", "pdf": "application/pdf"}[format]
```

```python
        # RFC 4180 §3: header=absent, because the first record is the report's title, not field names.
        media = {"json": "application/json", "html": "text/html; charset=utf-8", "pdf": "application/pdf",
                 "csv": "text/csv; charset=utf-8; header=absent"}[format]
```

### Block 8 — `local-development/gsd/reporting/config.py`: a deployment may list `csv`

<!-- block: local-development/gsd/reporting/config.py | edit -->
```python
    """A comma list of html/pdf (json is always written, so a listed `json` is accepted and dropped);
```

```python
    """A comma list of html/pdf/csv (json is always written, so a listed `json` is accepted and dropped);
```

<!-- block: local-development/gsd/reporting/config.py | edit -->
```python
    unknown = sorted(set(parts) - {"html", "pdf", "json"})
    if unknown:
        raise SystemExit(f"{name}={raw!r}: unknown format(s) {unknown}; allowed html, pdf (json is always written)")
```

```python
    unknown = sorted(set(parts) - {"html", "pdf", "csv", "json"})
    if unknown:
        raise SystemExit(f"{name}={raw!r}: unknown format(s) {unknown}; allowed html, pdf, csv (json is always written)")
```

### Block 9 — `local-development/gsd/reporting/trigger.py`: a schedule may ask for `csv`

<!-- block: local-development/gsd/reporting/trigger.py | edit -->
```python
    ap.add_argument("--format", action="append", default=[], choices=["html", "pdf"])
```

```python
    ap.add_argument("--format", action="append", default=[], choices=["html", "pdf", "csv"])
```

### Block 10 — `local-development/gsd/static/index.html`: the format boxes, the CSV one unticked, drawn from `view.reportWant`

<!-- block: local-development/gsd/static/index.html | edit -->
```html
      ${cat.pdf && cat.pdf.enabled ? `<label class="filterbar-note"><input type="checkbox" id="report-want-pdf" checked> PDF</label>` : ""}
      <label class="filterbar-note"><input type="checkbox" id="report-want-html" checked> HTML</label>
```

```html
      ${cat.pdf && cat.pdf.enabled ? `<label class="filterbar-note"><input type="checkbox" id="report-want-pdf"${view.reportWant.pdf ? " checked" : ""}> PDF</label>` : ""}
      <label class="filterbar-note"><input type="checkbox" id="report-want-html"${view.reportWant.html ? " checked" : ""}> HTML</label>
      <label class="filterbar-note"><input type="checkbox" id="report-want-csv"${view.reportWant.csv ? " checked" : ""}> CSV</label>
```

### Block 10a — `local-development/gsd/static/index.html`: the format boxes are the reader's state

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
                report: null, reportLanded: null, reportFocusRow: null, reportForm: {},
```

```javascript
                report: null, reportLanded: null, reportFocusRow: null, reportForm: {},
                reportWant: { pdf: true, html: true, csv: false },   // #106: the format boxes, kept across the form's repaints
```

### Block 10b — `local-development/gsd/static/index.html`: a box's change is kept across the form's repaints

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  if (link) link.onclick = () => { navigate({ page: "reporting" }); render(); refresh(); };
```

```javascript
  if (link) link.onclick = () => { navigate({ page: "reporting" }); render(); refresh(); };
  // The format boxes are the reader's, like Advanced's open state: a switch, a segment or a lookup pick repaints the
  // form, and a box rendered from a fixed default dropped a ticked CSV before Generate read it (review of #106, OB3).
  ["pdf", "html", "csv"].forEach((f) => { const box = $(`report-want-${f}`); if (box) box.onchange = () => { view.reportWant[f] = box.checked; }; });
```

### Block 11 — `local-development/gsd/static/index.html`: a ticked box posts `csv`

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  if ($("report-want-pdf") && $("report-want-pdf").checked) formats.push("pdf");
```

```javascript
  if ($("report-want-pdf") && $("report-want-pdf").checked) formats.push("pdf");
  if ($("report-want-csv") && $("report-want-csv").checked) formats.push("csv");
```

### Block 12 — `local-development/tests/test_report_csv.py`: the tests

<!-- block: local-development/tests/test_report_csv.py | create -->
```python
"""CSV as a fourth report format (docs/specs/SPEC_F2_csv_format.md, #106): one file per run, rendered
generically from the sealed report, carrying its sha256 and page one; the same cell becomes the same text as
in the page's table export (index.html `csvField`); off unless asked for."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from gsd.reporting import REPORT_PREFIX
from gsd.reporting.catalogue import REGISTRY, RunContext, validate_params
from gsd.reporting.catalogue.common import assemble
from gsd.reporting.config import ReportSettings, _formats_env
from gsd.reporting.model import KeyValues, Note, Report, Section, Table
from gsd.reporting.snapshot import Snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot
from test_p2_selectors import _FakeClient
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

LOCAL = Path(__file__).resolve().parents[1]
CHART = LOCAL.parent / "charts" / "group-sync-dashboard"
#: The page's export, verbatim from index.html (SPEC_C1). render_csv.csv_field is its port: a change to
#: either side fails T106-3 until the other follows.
JS_CSV_FIELD = r'''const CSV_BOM = "\ufeff";
function csvField(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) value = value.join("; ");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  let s = String(value);
  // Tested after any leading whitespace: an importer that trims before it decides would treat
  // " =cmd" like "=cmd". The initiators are OWASP's — = + - @, tab, CR, LF — plus their
  // full-width forms (U+FF1D, U+FF0B, U+FF0D, U+FF20), which some locales' spreadsheets
  // evaluate too (review, C1). The cell keeps its original text; this only decides the prefix.
  if (/^[\t\r\n ]*[=+\-@\t\r\n\uFF1D\uFF0B\uFF0D\uFF20]/u.test(s)) s = "'" + s;
  if (/[",\r\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
  return s;
}'''
#: Cells and the text both exports write for them (T106-2, T106-3).
CELLS = [
    ("=1+1", "'=1+1"), ("+1", "'+1"), ("-1", "'-1"), ("@SUM(A1)", "'@SUM(A1)"), ("\tx", "'\tx"),
    ("\rx", "\"'\rx\""), ("\nx", "\"'\nx\""), (" =x", "' =x"), ("＝x", "'＝x"), ("plain", "plain"),
    (" lead", " lead"), ("a,b", '"a,b"'), ('say "hi"', '"say ""hi"""'), ("", ""), (None, ""), (-1, "-1"),
    (0, "0"), (True, "true"), (False, "false"), (2.0, "2"), (0.5, "0.5"), (["a", "=b"], "a; =b"),
    (["=a", None, 3, True], "'=a; ; 3; true"), ([], ""),
    # JavaScript's number layout, not Python's (review of #106, OB3): measured against node 26.9.0
    (1e21, "1e+21"), (-1e21, "-1e+21"), (1e-5, "0.00001"), (1.5e-5, "0.000015"), (1e-6, "0.000001"), (1e-7, "1e-7"),
    (1.5e-7, "1.5e-7"), (1e300, "1e+300"), (2.0 ** 60, "1152921504606847000"), (123.456, "123.456"), (-0.0, "0"),
    ([1e21, 1e-7], "1e+21; 1e-7"),
]
PARAMS = {
    "namespace-access": {"namespaces": "prod-ns,dev-ns"},
    "access-certification": {"campaign": "Q3 2026", "due": "2026-10-01", "reviewer": "Jane Reviewer"},
}


def _render_csv(report: Report) -> str:
    from gsd.reporting.render_csv import render_csv   # imported here: before SPEC_F2 the module does not exist
    return render_csv(report)


def _synthetic() -> Report:
    return Report(
        name="t", title="Test report", cluster="c1", api_url="https://api.c1:6443", generated_at="2026-10-03T12:00:00Z",
        generated_by="alice", generated_by_note="proxy-verified", run_id="r1", params={}, coverage={}, provenance={},
        totals={}, truncated=False, include_members=False,
        sections=[
            Section("Provenance and coverage", [KeyValues("Run", [("Run id", "r1"), ("Generated by", "alice")]),
                                                Note("Scope: direct bindings only.", "caveat")], sealed=False),
            Section("Findings", [Table("Grants", ["Subject", "Count", "Reason"],
                                       [['=HYPERLINK("x")', 3, None], ["a, b", -1, "line\nbreak"]], note="2 rows"),
                                 Table("Empty", ["Name"], [], empty_text="none found")]),
        ]).seal()


def test_t106_1_the_renderer_walks_a_table_a_list_and_a_note():
    """Every block kind, in order, under its label record; page one marked not sealed; the sha256 printed.
    Without SPEC_F2: ModuleNotFoundError, gsd.reporting.render_csv."""
    report = _synthetic()
    expected = [
        "﻿Report,Test report", f"sha256 of the report data,{report.sha256}",
        "", "Section,Provenance and coverage,not sealed: states the run",
        "", "List,Run", "Run id,r1", "Generated by,alice",
        "", "Caveat,Scope: direct bindings only.",
        "", "Section,Findings,sealed",
        "", "Table,Grants", "Subject,Count,Reason", "\"'=HYPERLINK(\"\"x\"\")\",3,", '"a, b",-1,"line\nbreak"', "Note,2 rows",
        "", "Table,Empty", "Name", "none found",
    ]
    assert _render_csv(report) == "\r\n".join(expected) + "\r\n"


@pytest.mark.parametrize(("value", "text"), CELLS)
def test_t106_2_a_formula_leading_cell_is_neutralised(value, text):
    """OWASP's initiators (and the browser's LF and full-width forms) get an apostrophe; numbers and booleans
    are never touched. Without SPEC_F2: ModuleNotFoundError."""
    from gsd.reporting.render_csv import csv_field
    assert csv_field(value) == text


def test_t106_3_the_port_is_the_browser_export():
    """The same cell becomes the same text in both CSV exports. The JavaScript is pinned verbatim, so a change
    to the page's export fails here; where node is installed, both functions run over the same cells.
    Without SPEC_F2: ModuleNotFoundError (the pin itself holds on main)."""
    from gsd.reporting.render_csv import CSV_BOM, csv_field
    page = (LOCAL / "gsd" / "static" / "index.html").read_text(encoding="utf-8")
    start = page.index("const CSV_BOM")
    assert page[start:page.index("\n}\n", start) + 2] == JS_CSV_FIELD, "index.html's csvField changed: port it"
    assert CSV_BOM == "﻿" and 'return CSV_BOM + lines.join("\\r\\n") + "\\r\\n";' in page
    values = [value for value, _ in CELLS]
    ported = [csv_field(value) for value in values]
    assert ported == [text for _, text in CELLS]
    node = shutil.which("node")
    if node:
        script = JS_CSV_FIELD + "\nprocess.stdout.write(JSON.stringify(JSON.parse(process.argv[1]).map(csvField)));"
        ran = subprocess.run([node, "-e", script, "--", json.dumps(values)], capture_output=True, text=True, timeout=30, check=True)
        assert json.loads(ran.stdout) == ported


def _report(snap: Snapshot, name: str) -> Report:
    spec, build = REGISTRY[name]
    info = snap.info()
    ctx = RunContext(settings=ReportSettings(login_capture_enabled=True), cluster=snap.cluster(CLUSTER), now=NOW,
                     run_id="20260906T120000.000000Z-ab12", generated_by="alice", generated_by_note="proxy-verified",
                     snapshot_stamp=info.stamp, snapshot_age_seconds=info.age_seconds(NOW), schema_version=info.schema_version)
    params = validate_params(spec, PARAMS.get(name, {}))
    return assemble(spec, snap, ctx, params, build(snap, ctx, params))


def test_t106_4_every_report_renders_with_its_seal_and_page_one(tmp_path):
    """All eleven reports through the one generic renderer: the sha256 the .json carries, page one's rows,
    one Section record per section, and the seal unchanged by rendering. Without SPEC_F2: ModuleNotFoundError."""
    store = seed_store(str(tmp_path / "writer.db"))
    (tmp_path / "snapshots").mkdir()
    try:
        snap = Snapshot(write_snapshot(store, tmp_path / "snapshots"))
    finally:
        store.close()
    with snap:
        for name in REGISTRY:
            report = _report(snap, name)
            sealed = report.sha256
            text = _render_csv(report)
            lines = text.split("\r\n")
            assert lines[:2] == [f"﻿Report,{report.title}", f"sha256 of the report data,{sealed}"], name
            assert json.loads(report.to_json())["sha256"] == sealed == report.seal().sha256, name
            assert lines[3] == "Section,Provenance and coverage,not sealed: states the run", name
            assert f"Run id,{report.run_id}" in lines, name
            assert sum(line.startswith("Section,") for line in lines) == len(report.sections), name


def test_t106_5_a_run_stores_and_serves_csv(service):  # noqa: F811
    """`csv` is accepted, rendered after the .json, stored as report.csv in the run's own directory and served
    as text/csv with a .csv name. Without SPEC_F2: 422 (create_run's allow-set is html and pdf)."""
    client, app, _ = service
    r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["csv"]}, headers=_viewer())
    assert r.status_code == 202, r.text
    run = _wait_done(client, r.json()["id"], _viewer())
    assert run["status"] == "done", run.get("error")
    assert run["formats"] == ["csv"] and set(run["bytes"]) == {"json", "csv"}
    a = client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": "csv"}, headers=_viewer())
    assert a.status_code == 200 and a.headers["content-type"] == "text/csv; charset=utf-8; header=absent"
    assert a.headers["content-disposition"].startswith('attachment; filename="gsd_') and a.headers["content-disposition"].endswith('.csv"')
    assert a.headers["x-gsd-report-sha256"] == run["sha256"]
    assert a.content.startswith("﻿Report,".encode()) and f"sha256 of the report data,{run['sha256']}\r\n".encode() in a.content
    assert len(a.content) == run["bytes"]["csv"]
    # the store's layout: one directory per run, one file per format beside the manifest
    assert sorted(p.name for p in (app.state.store.root / run["id"]).iterdir()) == ["report.csv", "report.json", "run.json"]


def test_t106_6_create_run_refuses_xlsx_and_the_settings_accept_csv(service, monkeypatch):  # noqa: F811
    """`xlsx` stays refused; `csv` is a word the deployment may list. Without SPEC_F2 `_formats_env` refuses
    `csv` at startup (SystemExit)."""
    client, _, _ = service
    r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["csv", "xlsx"]}, headers=_viewer())
    assert r.status_code == 422 and "xlsx" in r.json()["detail"], r.text
    monkeypatch.setenv("GSD_REPORT_FORMATS_SCHEDULED", "html,json,csv")
    assert _formats_env("GSD_REPORT_FORMATS_SCHEDULED", ("html",)) == ("html", "csv")
    monkeypatch.setenv("GSD_REPORT_FORMATS_SCHEDULED", "html,xlsx")
    with pytest.raises(SystemExit):
        _formats_env("GSD_REPORT_FORMATS_SCHEDULED", ("html",))


def test_t106_7_csv_is_off_unless_configured(service):  # noqa: F811
    """The defaults name no csv: the service's settings, the chart's values, and what a request naming no
    formats stores. Passes before and after SPEC_F2: it guards the issue's "Must not change"."""
    assert ReportSettings().formats_scheduled == ("html",) and ReportSettings().formats_manual == ("html", "pdf")
    values = yaml.safe_load((CHART / "values.yaml").read_text())["reporting"]["formats"]
    assert values == {"scheduled": ["html", "json"], "manual": ["html", "json", "pdf"]}
    client, _, _ = service
    manual = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER}, headers=_viewer()).json()
    scheduled = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"},
                            headers=SERVICE).json()
    assert manual["formats"] == ["html", "pdf"] and scheduled["formats"] == ["html"]


def test_t106_8_the_schedule_trigger_takes_csv(monkeypatch, tmp_path):
    """A schedule's `formats: [csv]` reaches the run. Without SPEC_F2 argparse refuses the choice (exit 2)."""
    from gsd.reporting import trigger
    token = tmp_path / "token"
    token.write_text("secret")
    monkeypatch.setattr(trigger.httpx, "Client", _FakeClient)
    rc = trigger.main(["--url", "https://x", "--report", "groups", "--schedule", "weekly", "--token-file", str(token),
                       "--format", "html", "--format", "csv"])
    assert rc == 0 and _FakeClient.captured["json"]["formats"] == ["html", "csv"]
```

### Block 13 — `local-development/tests/test_ui.py`: the box and the download, in the browser

<!-- block: local-development/tests/test_ui.py | edit -->
```python
    def test_dismissing_the_note_on_one_form_keeps_what_another_form_is_owed(self, browser, reporting_server):
```

```python
    def test_csv_is_a_box_off_by_default_and_a_ticked_one_downloads_a_csv(self, browser, reporting_server):
        # #106 (SPEC_F2, T106-9): CSV is offered beside HTML and PDF, unticked; ticked, the run stores it and its
        # status offers it like the other formats, through the one artefact fetch.
        import json as _json
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=reports&cluster=crc-local&report=groups")
            page.wait_for_selector("#report-want-csv")
            assert not page.is_checked("#report-want-csv"), "CSV is off unless the reader ticks it"
            page.check("#report-want-csv")
            page.uncheck("#report-want-pdf")
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.click("#report-generate")
            assert _json.loads(info.value.post_data)["formats"] == ["html", "csv"]
            page.wait_for_selector("#report-status [data-artifact][data-format='csv']", timeout=30_000)
            with page.expect_download() as download:
                page.click("#report-status [data-format='csv']")
            assert download.value.suggested_filename.endswith(".csv"), download.value.suggested_filename
            assert not errors, errors
        finally:
            ctx.close()

    def test_a_ticked_csv_box_survives_a_repaint_of_the_form(self, browser, reporting_server):
        # Review of #106 (OB3): a switch, a segment or a lookup pick repaints the form, and the format boxes were
        # rendered from fixed defaults, so a ticked CSV (and an unticked PDF) was undone before Generate read it.
        import json as _json
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=reports&cluster=crc-local&report=groups")
            page.wait_for_selector("#report-want-csv")
            page.check("#report-want-csv")
            page.uncheck("#report-want-pdf")
            page.click('[data-switch="include_members"]')
            page.wait_for_selector('[data-switch="include_members"][aria-checked="true"]')
            assert page.is_checked("#report-want-csv") and not page.is_checked("#report-want-pdf"), "the repaint undid the reader's boxes"
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.click("#report-generate")
            assert _json.loads(info.value.post_data)["formats"] == ["html", "csv"]
            assert not errors, errors
        finally:
            ctx.close()

    def test_dismissing_the_note_on_one_form_keeps_what_another_form_is_owed(self, browser, reporting_server):
```

### Block 14 — `local-development/API.md`: the artefact formats

<!-- block: local-development/API.md | edit -->
```markdown
| `GET /report/api/runs/{id}/artifact?format=json\|html\|pdf` | ticket or token | the artefact, `Cache-Control: no-store`, `X-GSD-Report-SHA256`, as an attachment |
```

```markdown
| `GET /report/api/runs/{id}/artifact?format=json\|html\|pdf\|csv` | ticket or token | the artefact, `Cache-Control: no-store`, `X-GSD-Report-SHA256`, as an attachment; `csv` (#106) is `text/csv; charset=utf-8; header=absent`, one file per run: the title and sha256, then every section's blocks under labelled records, each cell written as the page's table export writes it |
```

### Block 15 — `charts/group-sync-dashboard/values.yaml`: `csv` is an allowed word, off by default

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
  # gets the PDF. json is always written. A defaulted pdf is dropped where pdf.enabled is false.
  formats:
```

```yaml
  # gets the PDF. json is always written. A defaulted pdf is dropped where pdf.enabled is false.
  # csv (#106) is allowed in either list and off by default: one file per run with the report's tables,
  # its sha256 and page one, each cell written as the dashboard's table export writes it.
  formats:
```

### Block 16 — `charts/group-sync-dashboard/templates/report-cronjob.yaml`: the comment names csv

<!-- block: charts/group-sync-dashboard/templates/report-cronjob.yaml | edit -->
```yaml
                # json is always written; the trigger's --format takes html and pdf only
```

```yaml
                # json is always written; the trigger's --format takes html, pdf and csv
```

### Block 17 — `charts/group-sync-dashboard/README.md`: the `reporting.formats` row

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
| `reporting.formats.scheduled` / `.manual` | `[html, json]` / `[html, json, pdf]` | what a run stores when the request names no formats, by origin: a schedule fires unattended and is printed from the HTML on demand, a person's manual run gets the PDF; `json` is always written | a defaulted `pdf` is dropped where `pdf.enabled` is false; an unknown name refuses startup |
```

```markdown
| `reporting.formats.scheduled` / `.manual` | `[html, json]` / `[html, json, pdf]` | what a run stores when the request names no formats, by origin: a schedule fires unattended and is printed from the HTML on demand, a person's manual run gets the PDF; `json` is always written; `csv` (#106) may be added to either, and is off by default | a defaulted `pdf` is dropped where `pdf.enabled` is false; an unknown name refuses startup (allowed: `html`, `pdf`, `csv`, `json`) |
```

### Block 18 — `docs/CHANGELOG.md`: the new format

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

```

```markdown
## Unreleased

- **CSV as a fourth report format, off by default (#106, Epic F #386, `docs/specs/SPEC_F2_csv_format.md`;
  application 4.2.0, chart 0.66.6).** A run asked for `csv` stores one `report.csv` beside its `.json`: the
  report's title and the sha256 the run sealed, then every section in order, page one included and marked
  `not sealed: states the run`, each table, key-value list and note under a labelled record. Every cell is written
  as the dashboard's table export writes it (`csvField`: RFC 4180 quoting, `true`/`false`, a list joined with
  `; `, an apostrophe before a cell a spreadsheet would evaluate), with the UTF-8 BOM and CRLF records. The report
  form gains an unticked CSV box; `GET /report/api/runs/{id}/artifact?format=csv` answers `text/csv; charset=utf-8;
  header=absent`; `reporting.formats.scheduled` and `.manual`, a schedule's `formats` and the trigger's
  `--format` accept `csv`. The default format sets, the other formats' bytes, the page's table export and the
  store's layout are unchanged. No permission, value key or migration.

```

### Block 19 — `local-development/pyproject.toml`: application 4.2.0

<!-- block: local-development/pyproject.toml | edit -->
```toml
version = "4.1.0"
```

```toml
version = "4.2.0"
```

### Block 20 — `local-development/gsd/__init__.py`: application 4.2.0

<!-- block: local-development/gsd/__init__.py | edit -->
```python
__version__ = "4.1.0"
```

```python
__version__ = "4.2.0"
```

### Block 21 — `charts/group-sync-dashboard/Chart.yaml`: the chart PATCH and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# template, value or RBAC change.
version: 0.66.5
```

```yaml
# template, value or RBAC change.
# CHART 0.66.6 (2026-10-03), PATCH: appVersion moves to application 4.2.0 (below); #106, SPEC_F2. The
# values, CronJob and README comments name csv as an allowed report format, off by default; no key,
# default, template logic or RBAC change.
version: 0.66.6
```

### Block 22 — `charts/group-sync-dashboard/Chart.yaml`: application 4.2.0

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
appVersion: "4.1.0"
```

```yaml
# 4.2.0 (2026-10-03). CSV as a fourth report format, off by default: one file per run with the report's tables, its sha256 and page one, each cell written as the page's table export writes it (#106). MINOR.
appVersion: "4.2.0"
```

### Block 23 — `docs/DESIGN_reporting_output_and_delivery.md`: the status line

<!-- block: docs/DESIGN_reporting_output_and_delivery.md | edit -->
```markdown
**Status: proposed — round 1 reviewed, corrections folded in.** Record: `docs/REVIEW_reporting_output_delivery.md`. Four features from `docs/REPORTING_ENHANCEMENTS.md`, taken forward
```

```markdown
**Status: proposed — round 1 reviewed, corrections folded in. §2 (CSV output) is built by
`docs/specs/SPEC_F2_csv_format.md` (#106), which re-measured it against main and did not take its `csv.writer`
renderer or its `#` label rows (SPEC_F2 §2.4, §2a).** Record: `docs/REVIEW_reporting_output_delivery.md`. Four
features from `docs/REPORTING_ENHANCEMENTS.md`, taken forward
```
