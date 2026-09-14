# Review — reporting output/delivery, ROUND 1 (design + snippets), PR #105

Adversarial review of `docs/DESIGN_reporting_output_and_delivery.md` **before any code**. 2026-09-14.
Codex (gpt-5.6-sol, xhigh, shell, `git archive` export, stdin closed) measured against the real code;
Cursor (Grok 4.6 high fast, ask mode) traced from the tree. Every load-bearing claim re-checked here — all
seven held.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 CSV integration points exist as assumed | REFUTED | REFUTED | **Accepted** — add `csv` to `FORMATS` and the artefact Query pattern/MIME |
| C2 the diff design is sound against the run/artefact model | REFUTED | REFUTED | **Accepted** — handle `report-diff` before the REGISTRY checks; keep it out of the catalogue; define the builder |
| C3 delivery is confined to the Job; the posture change is real | REFUTED | REFUTED | **Accepted** — the confinement holds; the snippets are wrong (chart key, `log`, secret leak, no NP for a hostname) |
| C4 preview is a cheap, side-effect-free read | REFUTED | REFUTED | **Accepted** — real snapshot facts, define `_row_count`, resolve the one-POST contract, guard OOM |
| C5 the four respect the boundaries; the order holds | CONFIRMED | CONFIRMED | — |

## Re-check (the seven claims, measured here)

`ArtifactStore.FORMATS = ("json","html","pdf")` and `write` raises on anything else (`artifacts.py:24,103`);
`get_artifact`'s `format` is `Query(pattern="^(json|html|pdf)$")` (`server.py:232`); `create_run` does
`if body.report not in REGISTRY: 404` then `spec,_ = REGISTRY[body.report]` (`server.py:185,189`) and
`_render` does `REGISTRY[run.report]` (`runs.py:92`) — all three fire before any `report-diff` special-case;
the report service's contract test asserts `non_get == [("POST", …/api/runs")]` exactly
(`test_reporting_server.py:85`); the schedule key is `schedule:`, not `cron:`, and `trigger.py` uses
`print`, not `log`; `test_ui.py` asserts the catalogue has **11** reports (`:4057`) and formats
`["html","json","pdf"]` (`:4071`). `ArtifactStore.get(run_id)` exists (`artifacts.py:116`). Every claim
confirmed.

## The accepted corrections, by feature

### C1 — CSV

- `csv` must join `ArtifactStore.FORMATS` (else `write` raises `ValueError` on an accepted CSV run) **and**
  the `get_artifact` `Query` pattern (`^(json|html|pdf|csv)$`) with a `text/csv` MIME and `.csv` filename.
- Keep CSV **opt-in, default off**: `test_ui.py`'s formats assertion (`["html","json","pdf"]`) and
  `test_reporting_server.py`'s `{"json","html","pdf"}` stay green; a new test seeds `csv`.
- Confirmed: `_render` passes the live dataclass `Report`, so `render_csv`'s `isinstance` on
  `Table|KeyValues|Note` is correct.

### C2 — change/diff

- `report-diff` is not in `REGISTRY`, so the existing `create_run` 404 and both registry lookups fire
  first. The special-case must branch **before** `if body.report not in REGISTRY` in `create_run` and
  **before** `spec, build = REGISTRY[run.report]` in `_render`.
- Keep `report-diff` **out of `REGISTRY`/the catalogue** — `test_ui.py:4057` asserts exactly 11 catalogue
  reports; a synthetic diff id must not appear there. It is invoked from the runs table, not the form.
- `_diff_report`/`build_diff` must be fully defined (the snippet left `_diff_report` undefined); the diff
  `Report` still needs `assemble`-style provenance and `.seal()`. base/head are validated in `create_run`
  (`ArtifactStore.get` exists); the diff run is counted in the render metrics like any other.
- v1 remains added/removed row-set (per-cell change is a follow-up); table keys use `section — title`, and
  a title carrying a live count would miskey — so the diff keys on the **spec-stable** title, and titles
  with counts are noted as a builder concern.

### C3 — delivery

- The Job/service **confinement is correct** (both reviewers) — the report service still makes no outbound
  call; only the schedule Job does. The snippets are wrong:
  - the chart schedule key is `schedule:`, not `cron:` (`report-cronjob.yaml`); the `deliver` block renders
    into the existing CronJob's trigger args.
  - `trigger.py` uses `print`, not `log` — the snippet's `log.info` is undefined.
  - the trigger hook needs the run id and status in scope after `--wait`; a small refactor of the poll loop
    exposes them.
  - **secret leak:** `str(httpx.HTTPStatusError)` includes the request URL, and a Slack/Teams webhook carries
    its secret in the path — so a delivery failure must log the **status code only**, never the URL.
  - a webhook POST needs a **timeout** (it has one) and the promised link/attach logic.
- **No egress NetworkPolicy in v1.** A Kubernetes egress NP cannot match a hostname hidden in a Secret
  (it matches IP/namespace/port), so an auto-rendered "allow the webhook host" rule is impossible; and a
  webhook-only egress rule would break the Job's own `POST /report/api/runs` (it must still reach DNS and
  the report Service). Decision (Cursor's): **document egress**, do not render an Egress NP — matching the
  existing report-pod comment that its egress policy is documentation, not control. If one is ever added it
  must name all three peers (DNS, the report Service :8443, the destination) in values.

### C4 — preview

- The snippet supplied **false snapshot facts** (`snapshot_stamp=""`, `schema_version=0`); it must reuse
  `snap.info()` the way `_render` does, so a report whose `build` reads the stamp/schema behaves.
- `_row_count` is undefined — define it (sum of `Table.rows` lengths across a section's blocks).
- **The one-POST contract:** `test_reporting_server.py:85` asserts the report service's only non-GET is
  `create_run`. Preview needs a request body (report, cluster, params with arrays), so a GET with an
  encoded blob is fragile. Decision: preview stays a **POST that writes nothing**, and the contract test is
  updated to assert the only **state-changing** endpoint is `create_run` while permitting a documented
  read-only preview POST — the invariant is "one write", not "one non-GET". This is an explicit, commented
  test change, reviewed at implementation, not a silent break.
- **OOM guard:** `build()` for a big report is real work; running it outside the single render worker on
  every (debounced) keystroke can overlap a `render_pdf` and spike memory. Preview must share the render
  worker's concurrency limit or be rate-limited (a 429 when busy), and the GUI debounces.

## C5 — held

None of the four changes the tier, ticket, snapshot mechanism or report gate. The order is valid: CSV (C1)
precedes its optional consumers (a diff can export CSV, a delivery can attach it) but neither depends on it
structurally; preview (C2 in the order) is independent; diff (C3) and delivery (C4) are independent. Tests
that enumerate formats and the catalogue count stay green because `csv` is default-off and `report-diff`
stays out of `REGISTRY`.

## Outcome

Four of five claims refuted, all as defects in the snippets (C5, the boundaries and order, held). Every
load-bearing claim re-checked against the code and confirmed. The four features are the right shape — a
renderer over the report, a read-compare of two stored runs, a schedule-Job delivery, a write-free build —
but the snippets as first written would raise on the CSV write, 404/KeyError the diff before it ran, log a
secret webhook URL and render an impossible NetworkPolicy, and break the report service's one-write
contract. All accepted corrections are folded into the design; the issues (C1 CSV, C2 preview, C3 diff,
C4 delivery) are cut from the corrected §8, each implemented and reviewed as its own PR on real code.
