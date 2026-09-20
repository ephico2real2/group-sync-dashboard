# Design mockups

Static HTML mockups of designs under review — open them in a browser. They are design
artifacts (not shipped pages); the implemented pages live under `local-development/gsd/static/`.

| Mockup | For |
|---|---|
| [`reporting-status-mock.html`](reporting-status-mock.html) | **Implemented** (#149 R5) — the reporting status / schedules / history UI at `#page=reporting` |
| [`report-form-mock.html`](report-form-mock.html) | **Implemented** (#149 R7) — the report input forms: one ParamSpec-driven shell, discovered lookups with type-ahead, subject scopes |
| [`landing-access-mock.html`](landing-access-mock.html) | The self-scoped "Your access" landing page every user gets — what you can reach, where it came from, what changed — see issue #158 |
| [`overview-kpi-mock.html`](overview-kpi-mock.html) | The administrator Overview makeover — system status, access posture, trends, Grafana/Observe links — see issue #157 |
| [`tab-redesign-mock.html`](tab-redesign-mock.html) | The six tabs redesigned **feature-complete** against the contract — real rows, real caveats, real filters — see issue #153 |
| [`tab-feature-contract.md`](tab-feature-contract.md) | What a tab redesign may **not** remove — captured from the running dashboard and the render functions — see issue #153 |
| [`drilldown-mock.html`](drilldown-mock.html) | The drill-down experience — one pattern-matched lookup over users, groups **and** namespaces, then group → member → user → via-group, with the namespace as the third drillable entity — see issues #166 and #167 |
| [`cluster-overview-mock.html`](cluster-overview-mock.html) | The Cluster Overview relaid onto the shared design system — cluster tiles that shrink as the fleet grows, paged alerts, and every status carrying its consequence — see issue #157 |
| [`report-library-mock.html`](report-library-mock.html) | **Implemented** (#229, SPEC E1) — the Library tab, a new canvas beside the untouched Reports and Reporting-status pages: one section per configured report, built by JS from the three embedded lab payloads (the catalogue, `/api/status`, `/api/runs`), headed by the service's cadence in words ("Quarterly compliance"), each run with its formats, its failure reason and its expiry as `prune()` defines it, the run drawer at `#page=library&run=<id>`; drafted by Cursor Grok, six render-check findings fixed before agreement |
| [`reports-page-mock.html`](reports-page-mock.html) | **Implemented** (#173) — the Reports page as used: the catalogue (bolder names, a colour gradient per report) and the per-report form a click opens immediately, in view, as a shareable position; design lineage #149 |
| [`data-requirements.md`](data-requirements.md) | What every mock renders, where each number comes from today, and the ten gaps that stand between the mocks and real pages — see issues #156, #167, #149, #158 |
| [`inventory-2026-09-17.md`](inventory-2026-09-17.md) | The dated inventory: every finished mock, its owning issue, its review rendering, the decisions it embodies, and what was retired |
| [`kyverno-research-2026-09-17.md`](kyverno-research-2026-09-17.md) | The Kyverno research record — ten findings, each cited to the v1.19.1 source or shipped CRDs, and the correction to #165's removal-date claim |
| [`kyverno-step0-discovery-2026-09-19.md`](kyverno-step0-discovery-2026-09-19.md) | Step 0, first pass: the served report API, the result shape, the namespace-qualified `policy` string, and the finding-10 probe — VAP generation is per-policy opt-in and the VAP-admitted object reported under neither source within 150 s |
| [`kyverno-discovery-2026-09-20.md`](kyverno-discovery-2026-09-20.md) | Step 0, re-measured: the report groups and CRD versions, the controllers' flags, the `source` field that tells the CEL family from the legacy one, `rule` absent for CEL, finding 10's answer (no VAP because the opt-in is off — `status: skip generating ValidatingAdmissionPolicy: not enabled.`; once generated, the policy reports only under the VAP), the three breakers — #170 step 0 |
