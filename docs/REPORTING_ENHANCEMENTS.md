# Reporting — enhancement backlog

The candidate features for the reporting page, captured so none is lost. This is the **backlog**; a
feature moves out of here into a design doc (`docs/DESIGN_reporting_*.md`) and the two-reviewer process
before any code. Each entry states the value, the rough effort, and whether it fits the reporting design's
constraints: the report service holds **no cluster credential and no RBAC**, reads a **read-only snapshot**,
is **wide-tier gated** by the ticket, makes **no outbound call**, and carries **no PHI/PII** (internal
access-review evidence only).

Status legend: **NOW** = being designed in a current design doc · **BACKLOG** = agreed valuable, not yet
scheduled · **PARKED** = deliberately not doing, with the reason.

## In design now

These four are in `docs/DESIGN_reporting_output_and_delivery.md` (as-is → spec → snippets → review → issues):

| # | Feature | Value | Fits constraints |
|---|---|---|---|
| 1 | **CSV output** | Auditors work in spreadsheets; the report's Tables flatten to CSV cleanly. The dashboard tabs already export CSV. | Yes — a snapshot-side renderer over the report's Tables, a new `csv` format beside pdf/html/json. |
| 2 | **Change / diff reports** | Governance is about *change*. Runs are already stored with their sha256 and canonical JSON, so a diff of two runs of the same report — bindings/grants added and removed since last quarter — turns evidence into a review. Highest analytical value. | Yes — a pure read/compare of two stored run JSONs; no new data, no new grant. |
| 3 | **Delivery of scheduled reports** | The design's parked question 4: a scheduled run writes a PDF to a PVC nobody watches. Email (SMTP), object-store upload, or a webhook/Slack post carrying the sha256 closes the loop so a certification pack reaches its reviewer. | Yes, if the **schedule Job** delivers (it already runs `trigger.py --wait`), keeping the long-lived report service passive; the one posture change is egress from the Job, gated and documented. |
| 4 | **Pre-generation preview count** | Show "this will cover 12 namespaces, 340 bindings" from the loaded snapshot before Generate, so a wide selection is not a 200-page surprise. Pairs with the mnemonic selector. | Yes — run `build()` for `totals` without rendering or storing; same ticket, same snapshot. |

## Backlog — agreed valuable, not yet scheduled

- **Report bundles.** Run several reports as one "quarterly review" pack (access-certification +
  privileged-access + dormant-access), delivered as one archive. One action for the recurring campaign.
  *Fits: yes — an orchestration over existing runs. Effort: medium.*
- **Separation-of-duties (toxic combinations) report.** A classic governance artefact the data already
  supports: people holding conflicting roles, or admin plus a sensitive edit, across namespaces. A new
  report in the catalogue. *Fits: yes — snapshot-side. Effort: medium (define the conflict rules).*
- **Saved parameter presets.** Save a report plus its parameters as a named preset ("Q3 platform-namespace
  audit") to re-run — more useful now that the mnemonic selector exists. *Fits: yes; state is per-viewer.
  Effort: low-medium.*
- **Multi-cluster reports.** A report that spans the clusters a reader may see ("who holds admin across the
  fleet"), respecting D2 per-cluster visibility. *Fits: yes, per-cluster reads composed. Effort: medium-high.*
- **Report verification page.** Paste a report's sha256 and confirm it matches a recorded run and the
  snapshot it came from — closing the loop on the sealed hash. *Fits: yes. Effort: low.*
- **XLSX output.** Beyond CSV, a formatted spreadsheet. *Fits: yes but adds a dependency (openpyxl) to the
  hardened image — weigh against CSV, which needs none. Effort: medium.*
- **Detached signature on the artefact.** cosign/PKCS7 over the PDF, beyond the embedded sha256 — the supply
  chain already uses cosign. *Fits: yes. Effort: medium; the sha256 + provenance may already be enough.*
- **Retention pinning.** Mark a run as evidence so retention never prunes it (an audit artefact must not
  auto-delete). *Fits: yes — a flag on the run. Effort: low-medium.*

## Parked — deliberately not, with the reason

- **A sign-off workflow** (the reviewer marks Approve/Revoke and the system records the decision). The
  access-certification pack prints those columns today; making them stateful turns the product toward a
  full identity-governance engine, against the operator's framing of reports as *evidence*, not a workflow.
  Revisit only as a deliberate product direction.
- **Self-service schedule creation in the GUI.** Creating CronJobs needs a write path the report service
  deliberately does not have (no RBAC, no cluster credential); it would fight the two-pod security design.
  Schedules stay declarative in the chart.

## How an item leaves this backlog

Pick it, and it goes through the same path as the auditor and mnemonic work: an as-is section grounded in
the real code, a technical spec with full snippets and an ASCII flow, two review rounds (Codex + Cursor,
each finding re-checked and decided in writing), then ordered issues, each its own PR reviewed on real
code. Nothing here is committed to until it is in a design doc.
