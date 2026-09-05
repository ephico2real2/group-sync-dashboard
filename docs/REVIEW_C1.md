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

Codex pinned its review to the commit it was given (`4fc8e7a`) while the Cursor-round fixes landed
beside it, and measured with a shell: `helm template` both states, `_bool_setting` behaviour, an
in-memory `/api/version`, the citation and version tests, and `csvField` on fourteen inputs.

| Claim | Codex | Decision |
|---|---|---|
| C1 export reads what the table paints | REFUTED on the Users cap | **Accepted on the wording** — the design doc said "the same arrays the table paints"; it now names the paint cap as the one deliberate difference; Codex's prose test rejected |
| C2 tier safety | CONFIRMED | — ; it traced the narrowing follow-up in `refresh()` |
| C3 `csvField` | REFUTED | **Accepted** — OWASP also names LF and the full-width `＝＋－＠` initiators; the guard covers them; Codex's fourteen-case test added (trimmed to the cases that hold across engines) |
| C4 `downloadBlob` | CONFIRMED | — ; MDN's guidance is that the URL is no longer needed once the download has started. Cursor's opposite risk (a save dialog outliving a timer) was already applied; both agree the change is harmless, so it stands |
| C5 the control | REFUTED | **Accepted** — the same tier-guard gap Cursor found, applied in the Cursor round |
| C6 the switch | CONFIRMED by execution | — |
| C7 wire and docs | CONFIRMED by execution | — ; `features` is the only added key |
| C8 fidelity | CONFIRMED | — ; 16 files, 31 spec blocks found, the appended tests byte-identical |
| C9 reference cluster | PLAUSIBLE (sandbox) | — ; measured here (chart 0.15.0, app 0.14.0, `features.export: true`) |
| C10 flake sources | REFUTED | **Accepted** — the same sleep Cursor found, removed in the Cursor round; Codex's test that parses the test file rejected |

**Volunteered (Codex, accepted):** the narrowed Namespace audit export's JSON `sort` reported the wide
view's retained sort keys although a narrowed reader's rows are painted as the store serves them
(cluster-admin first, cluster-scoped first, namespace, user — `store.py` `direct_user_bindings`'s
`ORDER BY`, verified). The envelope now names that order; Codex's test with the `carol` persona added.

## Outcome

Cursor refuted four claims and volunteered three findings; Codex refuted four (two overlapping) and
volunteered one. Eight findings accepted and applied — the tier guard, the whitespace and full-width
formula initiators, the timer-free object URL, two honest sort envelopes, the sleep, and two wording
corrections — three tests rejected as prose or test-source assertions, one nil-safety suggestion
rejected for consistency with the ConfigMap's other keys. Re-validated after the fixes: the fifteen export
browser tests (twelve from the spec plus three from the review), `test_export_module.py`, the chart
tests, the full suite; CI green on the branch before the fixes and re-run after; CRC redeployed.
