# Review — PR #78, C1: CSV and JSON export of the table on screen

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #78
(`docs/specs/SPEC_C1_table_export.md` applied verbatim; app 0.14.0, chart 0.15.0). Cursor (Grok 4.6
high fast, ask mode, shell blocked) traced the branch; Codex (gpt-5.6-sol, xhigh) is recorded below
when its pass lands. Every verdict was re-checked here before a decision, and accepted fixes are
recorded as deviations in the spec's orchestrator's notes.

## Verdicts — Cursor

| Claim | Cursor | Decision |
|---|---|---|
| C1 export reads exactly what the table paints, through one function | REFUTED on the Users paint cap | — ; the spec intends it: the paint is capped at `USERS_RENDER`, the export carries every match and the note says the export's count. The Groups chip is applied on the wire, so paint and export read the same payload |
| C2 tier safety | REFUTED | **Accepted** — see below |
| C3 `csvField` / `toCsv` | CONFIRMED, one residual | **Accepted** — a leading whitespace run before a formula character is now neutralised too; Cursor's test added with the correct expected output |
| C4 `downloadBlob` | PLAUSIBLE | **Accepted on the fact; test rejected** — a browser set to ask where to save can keep its dialog open past a one-second timer; the URL now lives until the next export replaces it. Cursor's test asserted the function's source text, which is prose; the download tests cover the behaviour |
| C5 the control, focus, accessible names | REFUTED on the Loading case | **Accepted** — the same gap as C2 |
| C6 the switch | PLAUSIBLE (no render) | — ; measured here: `helm template` both states, `test_export_module.py` 4 passed |
| C7 wire and docs | PLAUSIBLE | — ; measured here: contract, citations, versions tests pass |
| C8 fidelity to the spec | PLAUSIBLE (no diff) | — ; every OLD anchor matched once before the edits, the diff holds only the spec's blocks plus the review fixes below |
| C9 the reference cluster | PLAUSIBLE (no oc) | — ; measured here: chart 0.15.0 / app 0.14.0 at revision 177, `features.export: true`, no `ui` override, `uiExportEnabled: true` |
| C10 flake sources | REFUTED | **Accepted** — the no-request test slept 300 ms after the download; the sleep is gone, the assertion stands on `expect_download` completing |

## C2 / C5 — the export did not fail closed on an unknown tier

**Finding (Cursor).** `bindingsPage` paints "Loading…" when `readerTierKnown()` is false (the
`/api/whoami` fetch failed this cycle), but `exportDescriptor`'s bindings branch had no such check.
The follow-up that nulls `data.findings` runs only when a new whoami is narrowed, so after a failed
whoami the page showed Loading while the export note and buttons still offered the previous cycle's
wide findings.

**Re-check.** `readerTierKnown()` at `index.html:544`, used by `bindingsPage` at `:2372`; the
export's bindings branch read `data.findings` unguarded. Reproduced by Cursor's test before the fix.

**Decision.** Accepted. The bindings branch returns null when the tier is unknown, with the reason in
a comment; Cursor's test (`test_no_control_while_the_bindings_tier_is_unknown`) added. Recorded as a
deviation in the spec's notes.

## Not asked, and what happened to it

- **Cursor N1**, the Loading test's name overclaimed — covered by the new test.
- **Cursor N2**, the narrowed Access export's JSON `sort` claimed `binding asc` while the rows are the
  store's order (kind, namespace, name) and the page does not re-sort. Accepted: the envelope names
  that order; Cursor's test added.
- **Cursor N3**, `{{ .Values.ui.export.enabled }}` is not nil-safe against `--set ui=null`. Rejected:
  every other ConfigMap key in `templates/configmap.yaml` reads its value the same way, and the spec's
  NEW block is exact; a nil map is a values-file error the chart reports loudly.

## Verdicts — Codex

Pending; the section is completed when the pass lands.

## Outcome

Cursor refuted four claims and volunteered three findings; five accepted and applied (one as a
documented exception), two rejected with the reason. Re-validated after the fixes: the fifteen export
browser tests (twelve from the spec plus three from the review), `test_export_module.py`, the chart
tests, the full suite; CI green on the branch before the fixes and re-run after; CRC redeployed.
