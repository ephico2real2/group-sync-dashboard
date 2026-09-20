# Review record — the Flux HelmRelease example (#212, PR #231)

Branch `docs/212-flux-example`, head `61999c2` reviewed; three seats: Cursor Grok 4.6 (ask mode, from
source), Codex GPT-5.6 xhigh (a `git archive` export with the venv; the CRDs fetched, `helm template` at the
pinned versions, the tests run), OB3 (Opus 5; the CRDs compared byte-for-byte with the controllers' release
tags, a mutant validator run, helm-controller v1.6.4 and Helm v4.2.4 read at the source for the reconcile,
CRD and `lookup` semantics — nothing executed against a cluster, Flux not being on the lab).

## Claims × decision

| # | Claim | Grok | Codex | OB3 | Decision |
|---|---|---|---|---|---|
| C1 | The four objects validate against the current v2/v1 CRD schemas | CONFIRMED | CONFIRMED (jsonschema) | CONFIRMED (jsonschema + an unknown-key walk; five planted mutants all fail) | Holds. |
| C2 | The `values` render at the pinned versions; the dashboard pin | CONFIRMED on the render; REFUTED the pin — wants `0.41.1` | CONFIRMED; keep `0.41.0`, the published one | CONFIRMED; keep `0.41.0` — unpublished until merge, and the published tarball installs the same objects as the tree (diffed) | **Rejected** Grok's re-pin: the example must install when read. The header says the pins are the published versions on the date; OB3's test holds a pin ≤ the tree's version. |
| C3 | `dependsOn` is necessary and sufficient for the GrafanaDashboard CR | REFUTED — the release never reaches Ready (the 5 m default timeout) | CONFIRMED | PLAUSIBLE — sufficient, and NOT via OLM: helm-controller applies `crds/` before the render; and stronger than assumed: a deployed release is never re-rendered on the interval, so the order is load-bearing | **Accepted** OB3's sentence in the header, the README and the CHANGELOG; the timeout is C8. |
| C4 | `crds: CreateReplace` on the grafana release, and the prose about it | CONFIRMED (a hazard noted as PLAUSIBLE) | REFUTED the wording — `upgrade.crds` governs upgrades | REFUTED the setting — the chart's contract is "only when absent, never upgraded" (OLM owns the CRDs); CreateReplace force-applies the v5.24.0 copies over OLM's on every upgrade | **Accepted** OB3: the setting removed from both actions (Helm's default `Create` is `helm install`'s behaviour); the three sentences rewritten. The orchestrator's earlier draft had documented the hazard instead of removing it — retracted. |
| C5 | Hooks run as hooks; `lookup` sees the cluster | CONFIRMED | CONFIRMED | CONFIRMED at the source (`DisableHooks`, `DryRunNone` → the engine gets a client) | Holds. |
| C6 | The chart bump is required; the release tooling agrees | CONFIRMED / PLAUSIBLE | CONFIRMED (ci.yml:93 excludes only Chart.yaml) | CONFIRMED; N2 the missing Chart.yaml history line | **Accepted** N2. |
| C7 | The citations resolve | CONFIRMED | CONFIRMED (892 passed) | CONFIRMED by the resolver — and the suite would not catch a wrong basename (the 90 % ratio) | Holds; the ratio test's blind spot noted, not this PR's to fix. |
| C8 | The next real use | REFUTED — no `timeout`; cluster-scoped Flux; OperatorGroup clash; SA | PLAUSIBLE — `timeout: 15m` on grafana | PLAUSIBLE — `timeout: 15m`; `operator.source` beside `operator.package`; Flux ≥ 2.3 | **Accepted** all: `timeout: 15m` (the chart README's own `helm install` flag; the gate's ceiling is 720 s), the header's cluster-scoped-Flux / OpenShift-GitOps-is-Argo / OperatorGroup lines, `operator.source`, "≥ 2.3". |
| N1 | A test that renders the example against the charts | — | — | volunteered | **Accepted** — `tests/test_flux_example.py` (fails on the head on `install.crds` and the missing timeout; passes now). |

## Re-validation

`jsonschema` against the fetched CRDs: all three objects valid. `test_flux_example`, `test_docs_citations`,
`test_chart_versions`, `test_prepare_release`, `test_chart_renderers`: 929 passed, 14 skipped; `helm lint`
clean. The apply itself is not measured — Flux is not on the lab — and every document says so.
