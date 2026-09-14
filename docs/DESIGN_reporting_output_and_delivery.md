# Reporting extension — CSV, change diffs, delivery, and preview counts (design + technical spec)

**Status: proposed (round 1 pending).** Four features from `docs/REPORTING_ENHANCEMENTS.md`, taken forward
together because they share the run/render/artefact machinery. Like the auditor/mnemonic work
(`docs/DESIGN_reporting_auditors_and_ns_selector.md`), this **extends** the reporting design and defers to
`docs/DESIGN_reporting_service.md`; it changes no tier, no ticket, no snapshot mechanism, no report gate.
Every code block is the proposed change with its file and where it goes, for the reviewers to attack.

The constraints these respect: the report service holds **no cluster credential and no RBAC**, reads a
**read-only snapshot**, is **wide-tier gated** by the ticket, and (today) makes **no outbound call**; the
data carries **no PHI/PII**. Three of the four keep those exactly; delivery (§4) adds the one deliberate
posture change — egress from the **schedule Job**, not from the report service — and says so loudly.

---

## 1. As-is — the run/render/artefact path (measured 2026-09-14)

```
 POST /report/api/runs {report,cluster,params,formats}   server.py:create_run
   ├─ validate: report enabled, params (422), formats ⊆ {html,pdf} (json always written), pdf.enabled
   └─ Run(id, report, cluster, params, formats, generated_by=viewer|schedule:<n>) → runs.submit(run)  [queue]
                                                      │
 runs._render(run):                                   ▼
   spec, build = REGISTRY[report]                     validate_params again
   with Snapshot(newest) as snap:  ctx = RunContext(settings, cluster, …)
     report = assemble(spec, snap, ctx, params, build(snap, ctx, params))   # Report: sections[Table|KeyValues|Note]
   canonical = report.to_json()   run.sha256 = report.sha256
   store.write(id,"json",canonical);  if html: render_html;  if pdf: render_pdf   # ArtifactStore.write(id,fmt,bytes)

 GET /report/api/runs, /runs/{id}, /runs/{id}/artifact?format=…   (ticket or service token; wide tier)
 Schedule: a CronJob runs `python -m gsd.reporting.trigger --url … --report … --cluster … [--format …] --wait`
           which POSTs a run with the service token and polls; it writes NOTHING but the artefact (to the PVC).
```

Key shapes this design builds on:
- `Report.sections: list[Section]`, `Section.blocks: list[Table|KeyValues|Note]`, `Table(title, columns,
  rows, note, empty_text)` (`local-development/gsd/reporting/model.py`). `Report.canonical()` is the sealed
  data; `to_json()` the `.json` artefact.
- `create_run` rejects any format outside `{html, pdf}` (`local-development/gsd/reporting/server.py`); the
  render loop writes each requested format (`local-development/gsd/reporting/runs.py`).
- `ArtifactStore.write(run_id, fmt, bytes)` / `read(run_id, fmt)` (`local-development/gsd/reporting/artifacts.py`).
- The schedule Job's only command is `gsd/reporting/trigger.py` (httpx, service token, `--wait`).

---

## 2. Feature 1 — CSV output

**Decision.** A fourth artefact format, `csv`, beside `pdf`/`html`/`json`, selectable per run. A report is a
list of Tables across Sections; CSV is flat, so one `.csv` carries every Table in order, each preceded by a
labelled header row so a reader (and a spreadsheet's "text to columns") can tell them apart. KeyValues blocks
render as a two-column table; Notes render as a labelled line. No new data, no snapshot change — a renderer
over the same `Report`.

### 2.1 Flow

```
 create_run: formats ⊆ {html,pdf,csv}   (csv joins the allow-set; json still always written)
 _render:  … if "csv" in run.formats: store.write(id,"csv", render_csv(report).encode("utf-8"))
 render_csv(report):  for section in report.sections: for block in section.blocks:
     Table    → "# <section> — <title>", columns, rows (csv.writer, QUOTE_MINIMAL, CRLF)
     KeyValues→ "# <section> — <title>", ["key","value"], items
     Note     → "# <section> — <title> [<level>]", [text]
 GUI: a "CSV" checkbox beside PDF/HTML; the download button appears because run.formats carries csv.
 trigger.py: --format gains "csv" (schedules can deliver CSV).
```

### 2.2 Snippets

```python
# server.py create_run: widen the allow-set (json is always written; csv is opt-in like html/pdf)
bad = sorted(set(body.formats) - {"html", "pdf", "csv"})
```

```python
# runs.py _render, after the json write (csv needs only the Report, no fonts, no snapshot):
if "csv" in run.formats:
    from .render_csv import render_csv
    run.bytes["csv"] = self.store.write(run.id, "csv", render_csv(report).encode("utf-8"))
```

```python
# gsd/reporting/render_csv.py (new) — a Table-flattening renderer.
from __future__ import annotations
import csv, io
from .model import Report, Table, KeyValues, Note

def render_csv(report: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    w.writerow([f"# {report.title} — {report.cluster} — generated {report.generated_at} — sha256 {report.sha256}"])
    for section in report.sections:
        for block in section.blocks:
            w.writerow([])
            if isinstance(block, Table):
                w.writerow([f"# {section.title} — {block.title}"])
                w.writerow(block.columns)
                for row in (block.rows or [[block.empty_text]]):
                    w.writerow(["" if c is None else c for c in row])
            elif isinstance(block, KeyValues):
                w.writerow([f"# {section.title} — {block.title}"]); w.writerow(["key", "value"])
                for k, v in block.items:
                    w.writerow([k, "" if v is None else v])
            elif isinstance(block, Note):
                w.writerow([f"# {section.title} [{block.level}]"]); w.writerow([block.text])
    return buf.getvalue()
```

The GUI already builds download buttons from `run.formats.concat(["json"])`; add a `report-want-csv`
checkbox to the form and include `csv` in the posted `formats`. `trigger.py`'s `--format` `choices` gain
`"csv"`. `MIME`/filename for `csv` (`text/csv`, `.csv`) join the artefact endpoint's format map.

---

## 3. Feature 2 — change / diff reports

**Decision.** Compare two finished runs **of the same report and cluster** and produce a diff document —
rows **added** and **removed** per Table since the base run. Runs already store their canonical `.json`, so
the diff is a pure read/compare of two stored artefacts: no snapshot, no new grant. v1 is a **row-set diff**
(a row is a whole tuple; added = in head not base, removed = in base not head); per-cell "changed" detection
needs a key column and is a follow-up, noted in the output. The diff is itself a `Report`, so it renders to
html/pdf/csv/json through the existing renderers, and — the important part for evidence — it is produced as
a **stored run** of a synthetic report id `report-diff`, sealed and downloadable like any other.

### 3.1 Flow

```
 POST /report/api/runs {report:"report-diff", cluster, params:{base:<run_id>, head:<run_id>}, formats}
   validate: base & head are finished runs of the SAME report+cluster (422 otherwise)
 runs._render special-cases report=="report-diff":
   base = json.loads(store.read(base_id,"json"));  head = json.loads(store.read(head_id,"json"))
   diff_report = build_diff(base, head)      # a Report: per Table, an "added" and a "removed" sub-table
   … seal, store.write json/html/pdf/csv exactly as a normal run (render path unchanged)
 GUI: on the Recent-runs table, a "Diff vs…" action picks an earlier run of the same report+cluster.
```

### 3.2 Snippets

```python
# server.py create_run: report-diff is a first-class report id with its own validation (before REGISTRY check)
if body.report == "report-diff":
    base, head = body.params.get("base"), body.params.get("head")
    b, h = runs.store.get(base), runs.store.get(head)   # ArtifactStore.get(run_id) -> Run | None
    if not (b and h and b.status == "done" and h.status == "done"):
        raise HTTPException(422, "base and head must both be finished runs")
    if b.report != h.report or b.cluster != h.cluster:
        raise HTTPException(422, "base and head must be the same report and cluster")
    # queue a diff run (formats validated as below); _render special-cases it. generated_by = the viewer.
```

```python
# gsd/reporting/diff.py (new) — the row-set diff over two canonical report dicts.
from __future__ import annotations
from .model import Report, Section, Table, Note, iso
from datetime import datetime

def _tables(canonical: dict) -> dict[str, dict]:
    out = {}
    for s in canonical.get("sections", []):
        for b in s.get("blocks", []):
            if b.get("kind") == "table":
                out[f"{s['title']} — {b['title']}"] = b        # keyed by section+table title
    return out

def build_diff(base: dict, head: dict, now: datetime, run_id: str) -> Report:
    bt, ht = _tables(base), _tables(head)
    sections: list[Section] = []
    for key in sorted(set(bt) | set(ht)):
        b, h = bt.get(key), ht.get(key)
        cols = (h or b)["columns"]
        brows = {tuple(map(_norm, r)) for r in (b or {}).get("rows", [])}
        hrows = {tuple(map(_norm, r)) for r in (h or {}).get("rows", [])}
        added = sorted(hrows - brows); removed = sorted(brows - hrows)
        if not added and not removed:
            continue
        sections.append(Section(key, [
            Table("Added", cols, [list(r) for r in added], empty_text="none added"),
            Table("Removed", cols, [list(r) for r in removed], empty_text="none removed"),
        ], page_break=True))
    if not sections:
        sections = [Section("No change", [Note("The two runs are identical over every table.")])]
    # a Report with base/head provenance; totals count the deltas; per-cell change detection is a follow-up.
    return _diff_report(base, head, sections, now, run_id)   # fills the Report fields + .seal()

def _norm(v):  # stable, JSON-safe row-cell identity
    return "" if v is None else str(v)
```

The diff's `params` carry `{base, head}`, so its sha256 seals the deltas and its provenance names both
source runs and their snapshots — the diff is auditable evidence, not a screen view. `report-diff` is added
to the catalogue as a report that is **not** offered a param form (it is invoked from the runs table), so
`list_reports`/the GUI treat it as internal.

---

## 4. Feature 3 — delivery of scheduled reports

**Decision.** After a **scheduled** run finishes, the **schedule Job** (not the report service) fetches the
artefact and sends it to a configured destination. This keeps the long-lived report service passive (no
outbound), and confines the one new network posture — egress to a webhook/SMTP/object store — to the
short-lived Job pod, gated by the chart. v1 destination is a **webhook** (a generic URL, which covers
Slack/Teams incoming webhooks) carrying the run facts and a link; SMTP email and object-store upload are the
next destinations behind the same abstraction. Nothing is sent for an ad-hoc viewer run — delivery is a
property of a schedule.

### 4.1 Flow

```
 CronJob (report image) → gsd.reporting.trigger --report … --wait --deliver webhook --webhook-url-file /etc/gsd/deliver/url
   trigger: POST /api/runs (service token) → poll to done → GET /runs/{id} (facts) →
            deliver(kind, run facts + sha256 + a link, [--attach pdf → GET /runs/{id}/artifact])
   webhook: httpx.post(url, json={report, cluster, run_id, sha256, generated_at, schedule, link})
 The report SERVICE makes no outbound call. The JOB's egress to the webhook host is the one new allowance —
 the schedule Job pod, not the report pod; NetworkPolicy/egress documented in the chart.
```

### 4.2 Snippets

```python
# trigger.py: after --wait reaches done, deliver. New args: --deliver {none,webhook}, --webhook-url-file,
# --attach {none,pdf,html,csv}. The URL/secret comes from a file (a mounted Secret), never argv.
if a.deliver == "webhook" and status == "done":
    url = open(a.webhook_url_file).read().strip()
    facts = {"report": a.report, "cluster": a.cluster, "run_id": run_id, "sha256": run.get("sha256"),
             "generated_at": run.get("started_at"), "schedule": a.schedule}
    with httpx.Client(timeout=30.0) as wc:
        resp = wc.post(url, json=facts)   # a link, not the bytes, by default; --attach adds the artefact
        resp.raise_for_status()
    log.info("delivered run %s to the configured webhook", run_id)
```

```yaml
# chart: a schedules[] entry gains a deliver block; the CronJob renders the trigger args + mounts the secret.
reporting:
  schedules:
    - name: quarterly-certification
      report: access-certification
      cluster: crc-local
      cron: "0 6 1 */3 *"
      formats: [pdf, csv]
      deliver:
        kind: webhook                 # none | webhook (SMTP, object-store: follow-ups)
        webhookUrlSecret: gsd-report-deliver   # a Secret with key `url`; mounted read-only in the Job
        attach: none                  # none | pdf | html | csv
```

The chart's report NetworkPolicy is unchanged (ingress-only to the report pod); the **Job**'s egress to the
webhook host is a new, documented allowance rendered only when `deliver.kind != none`. The webhook URL is a
Secret, mounted, never in argv or the CronJob spec. A delivery failure fails the Job (a red Job is the
signal a scheduled report did not reach its destination).

---

## 5. Feature 4 — pre-generation preview count

**Decision.** A cheap, wide-tier endpoint that runs a report's `build()` for its `totals` and section/row
counts and returns them **without rendering or storing** anything, so the form can show "this covers 12
namespaces, 340 bindings" before Generate. It reuses the exact `_render` setup (snapshot, `RunContext`,
`build`) and stops at the built totals — the same work Generate does minus the render and the write, so it
is bounded by the report itself; the GUI debounces the call on param change.

### 5.1 Flow

```
 POST /report/api/preview {report, cluster, params}   (ticket; wide tier; NO write, NO artefact)
   validate params (422) → Snapshot(newest) → build(snap, ctx, params) → return {totals, sections, rows, truncated}
 GUI: on param change (debounced ~400ms) call preview; render "N namespaces · M bindings · will truncate"
      beside Generate. A failed/again-in-flight preview never blocks Generate.
```

### 5.2 Snippets

```python
# server.py: a read-only sibling of create_run — validate, build, count, return. No queue, no store.
@app.post(f"{REPORT_PREFIX}/api/preview")
def preview_run(body: RunRequest, p: Principal = Depends(principal)) -> dict:
    if body.report not in REGISTRY or body.report not in settings.enabled_reports:
        raise HTTPException(404, f"unknown or disabled report {body.report!r}")
    spec, build = REGISTRY[body.report]
    try:
        params = validate_params(spec, body.params)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        with Snapshot(newest_snapshot(settings.snapshot_dir)) as snap:
            cluster = snap.cluster(body.cluster)
            if cluster is None:
                raise HTTPException(422, f"unknown cluster {body.cluster!r}")
            ctx = RunContext(settings=settings, cluster=cluster, now=_clock(), run_id="preview",
                             generated_by=p.name or "preview", generated_by_note="preview (not stored)",
                             snapshot_stamp="", snapshot_age_seconds=0.0, schema_version=0)
            built = build(snap, ctx, params)
    except SnapshotError as exc:
        raise HTTPException(503, "no snapshot yet") from exc
    return {"totals": built.totals, "truncated": built.truncated,
            "sections": len(built.sections), "rows": sum(_row_count(s) for s in built.sections)}
```

Preview reuses `validate_params`, so a bad parameter shows the same 422 message the user would get on
Generate — the form can surface it early. It never writes a run, so it does not appear in the runs table or
count toward retention.

---

## 6. What stays out of scope

- No tier, ticket, snapshot-mechanism or report-gate change; CSV, diff and preview are snapshot-side reads
  under the existing wide-tier ticket; delivery is a schedule-Job property.
- Diff v1 is added/removed rows only (per-cell change needs a key column — a follow-up in the backlog).
- Delivery v1 is a webhook; SMTP and object-store are the next destinations behind the same `deliver.kind`.
- The report service still makes no outbound call — only the schedule Job does, and only when `deliver.kind`
  is set.

---

## 7. Test plan (each issue carries its slice)

- **CSV:** `render_csv` over a report with a Table, a KeyValues and a Note; `create_run` accepts `csv` and
  rejects `xlsx`; `_render` writes the `csv` artefact; the artefact endpoint serves `text/csv`; `test_ui`
  shows the CSV checkbox and download.
- **Diff:** `build_diff` over two canonical dicts (added, removed, identical → "No change"); `create_run`
  rejects a base/head mismatch (different report/cluster/unfinished) with 422; a stored diff run seals and
  renders; `test_ui` the "Diff vs…" action.
- **Delivery:** `trigger.py --deliver webhook` posts the facts (a fake webhook); a delivery failure exits
  non-zero; the chart renders the Job egress + secret mount only when `deliver.kind != none`; `helm template`
  each state.
- **Preview:** `preview_run` returns totals without writing a run; a bad param is 422; no snapshot is 503;
  `test_ui` the debounced count beside Generate.

---

## 8. Proposed issue order (finalised after review round 1 — each its own PR)

Independent where possible; all four sit on the run/render/artefact machinery.

1. **Issue C1 — CSV output.** `render_csv.py`, the `create_run` allow-set, the `_render` write, the artefact
   MIME/filename, the `trigger.py` choice, the GUI checkbox, tests. Independent; smallest; can land first.
2. **Issue C2 — preview count.** The `/api/preview` endpoint, the GUI debounced count, tests. Independent of
   C1; snapshot-side read only.
3. **Issue C3 — change/diff reports.** `diff.py`, the `report-diff` id and its `create_run` validation, the
   `_render` special-case, the catalogue treatment, the runs-table "Diff vs…" action, tests. Depends on
   nothing structurally but is the largest; benefits from CSV (C1) so a diff can export CSV.
4. **Issue C4 — delivery.** `trigger.py` `--deliver`, the chart `schedules[].deliver` block, the Job egress
   and secret, tests. Independent; the one network-posture change, reviewed with care.

C1 and C2 are the quick, self-contained wins; C3 is the analytical centrepiece; C4 is the one that touches
the chart's network posture. Each is its own PR with its own two-reviewer pass on real code.

---

*Round 1 of review runs on THIS document. The reviewers' edits, full snippets and gotchas are folded in;
then the issues above are cut in the settled order.*
