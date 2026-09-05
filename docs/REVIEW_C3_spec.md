# Review — PR #76, C3 spec: reporting as a microservice

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #76, a specification pull
request: `docs/specs/SPEC_C3_reporting_microservice.md` (5,400 lines, the complete code the R6
implementation will be applied from) replaces the earlier HTML-core-plus-loopback-PDF-sidecar body.
The claims attack the design's premises (oauth-proxy routing, the snapshot data path, the ticket, CSRF,
the PDF library, the chart guards, the dashboard changes, the catalogue SQL, the tests, CI and docs).
Cursor (Grok 4.6 high fast, ask mode, shell and network blocked) traced the spec against the chart
and application on the branch; Codex (gpt-5.6-sol, xhigh) is recorded below when its pass completes.
Every verdict was re-checked here against the spec text before a decision, and accepted corrections
are applied **in the spec body** — the spec stays the single source — with an orchestrator's note
listing them.

## Verdicts — Cursor

| Claim | Cursor | Decision |
|---|---|---|
| C1 oauth-proxy premises (multi-upstream path routing, identity header, `-upstream-ca`) | PLAUSIBLE | **Accepted** — §5.1 now states the ServeMux rule (`/report` without a slash is a 301 to `/report/`, forwarded to neither upstream), the `-pass-user-headers` default the repo already measured, and that `-upstream-ca` is unverified on the shipped tag; Cursor's ServeMux-simulation test rejected (it tests Python's `http.server`, not the proxy) |
| C2 the snapshot data path (temp name + rename, `immutable=1`, access modes) | CONFIRMED | — ; the writer renames atomically and the reader's filename pattern never opens `.tmp`; RWO pins the report pod by required affinity |
| C3 the ticket (HMAC, expiry, viewer binding, shared token via `lookup`) | CONFIRMED | — |
| C4 CSRF on `POST /report/api/runs`; dashboard API stays GET-only | CONFIRMED | — ; the custom ticket header makes the POST non-simple and the service answers 401 without it; no SameSite flag on the proxy cookie (documented, not relied on) |
| C5 fpdf2, its wheels, and the Hummingbird measurement | PLAUSIBLE | **Accepted** — §6.1 requires the `dnf list` re-measure at implementation; Cursor's `pip download` test rejected (a network call in the suite) |
| C6 switches against 0.14.0's rules; the guards; the Service/ServiceMonitor labels | REFUTED | **Accepted** — see below |
| C7 migration 11, leader-only snapshot and pull, usage tier on `/api/dashboard/reports` | CONFIRMED | — ; highest migration today is 8, C2 = 9 and D1 = 10 per the index's reconciliation, so 11 is right at R6 |
| C8 the catalogue's SQL against `SCHEMA` and the `Store` classification strings | CONFIRMED | — ; classification is `Store._FINDING_CASE`/`_FINDING_JOINS`/`_FINDING_WHERE`, concatenated not copied |
| C9 the test helpers the spec names | REFUTED | **Accepted** — see below |
| C10 CI/publish fit, version agreement, citations | PLAUSIBLE | **Accepted on one point** — §11's doc texts cited the deleted filename; corrected; Cursor's filename test rejected (prose) |

## C6 — the render guards printed into the manifests; the Service lacked the monitor's labels

**Finding (Cursor).** `gsd.reportingGuards` said "emits nothing" and then included `gsd.reportPdfVariant`
and `gsd.reportEnabledReports`, which return `pdf/a-2b` and the comma-joined catalogue; included from
both Deployments, the default render would begin each with that text and not be YAML. Separately, the
report Service's labels were `gsd.reportLabels` (the dashboard's `app.kubernetes.io/name`) while the
ServiceMonitor selects `gsd.reportSelectorLabels` (`…-report`): the scrape would find no Service, the
same trap `templates/service.yaml` records for the dashboard. And `monitoring.prometheusRule.for.
reportPull/reportSnapshot` were read by the rules but only mentioned in prose.

**Re-check.** All three read in the spec text: the two `include` lines at the end of the helper; the
Service `labels:` line; the rules' `for:` references at §8.17.13 with the prose-only values sentence.

**Decision.** Accepted. The helper assigns the validating helper's output to `$_` and reuses the
`splitList` it already had; the Service carries both label sets with a comment naming the trap; the
`for` keys are a values block. Cursor's tests (`test_chart_reporting.py` shapes) are the right tests
for R6 and are noted for implementation; nothing renders in a spec PR.

## C9 — the spec named test helpers with the wrong shapes

**Finding (Cursor).** §9.9 said "reusing `render()` and `_config_data()` from `test_chart_strategy.py`"
for document assertions, but `render(**values)` returns `(ok, text)` with `__` for dots; `_docs` is an
instance method; there is no `tests/conftest.py`; the document-list helper is `_render` in
`tests/test_chart_pdb.py`.

**Decision.** Accepted; §9.9 and §9.11 rewritten to name the helpers that exist and where the Playwright
fixture lives. Cursor's `inspect.signature` test rejected: it pins the suite's own helper signatures,
which is not a product invariant.

## Not asked, and what happened to it

- **Cursor N1, `namespace_access.py` imports.** The flagship report constructed `KeyValues(...)` and
  `Note(...)` but imported only `Section, Table`; a Generate would have failed before any SQL. Re-check:
  four constructions, two imports. Accepted; the import line is corrected. Cursor's AST test rejected in
  favour of the R6 suite importing and building the report.
- **Cursor N2, the ServiceMonitor/Service labels** — covered under C6.
- **Cursor, `-upstream-ca` and SameSite as accepted debt** — recorded in §5.1 and operator question 6.

## Verdicts — Codex

Pending; the section is completed when the pass lands.

## Outcome

Cursor refuted two claims, marked three plausible with a named risk, and volunteered one defect; all six
accepted on the fact and applied in the spec body, every proposed test rejected as either prose-pinning
or network-dependent, with the R6 chart tests noted for implementation. Re-validated:
`test_docs_citations.py`, `test_docs_diagrams.py` (the design's two sequence diagrams also needed brace
placeholders and no bare semicolon for the mermaid lint) and `test_specs_index.py` pass; CI green on the
branch before the corrections and re-run after them.
