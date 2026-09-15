# Review — PR #129 (P2: multi-dimension namespace selector + #107 preview)

Adversarial pass, 2026-09-15, on the P2 implementation (design
`docs/DESIGN_reporting_selectors_snapshots_and_windows.md` §3). Codex ran `gpt-5.6-sol`/xhigh with a
shell (ran the suites in a copy, built two-label snapshots, drove `reportFormCard` and the collector in a
Node probe, rendered helm); Cursor ran `cursor-grok-4.6-high-fast` in ask mode (source only). Both on
branch `feat/p2-multidim-selector`. Every verdict re-checked by the orchestrator against the code before
acceptance.

## Verdicts

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 selector-map grammar | CONFIRMED | **REFUTED** (accepts a comma string where a list is required) | **Accepted (Codex)** |
| C2 AND/OR expansion | CONFIRMED | CONFIRMED | — |
| C3 catalogue + storage seam | CONFIRMED | CONFIRMED | — (both fields, first-dim compat, no sqlite3 in server.py) |
| C4 frontend | **REFUTED** (preview race) | **REFUTED** (preview race + `__proto__` crash + C7-A) | **Accepted (converged + Codex extras)** |
| C5 chart + JSON transport | PLAUSIBLE (not executed) | CONFIRMED (rendered) | — (guard, env, CronJob `--params-json` all render) |
| C6 count endpoint + config env | **REFUTED** (missing `sqlite3.Error` wrap → 500) | **REFUTED** (string value + unconfigured label leak) | **Accepted (converged, complementary)** |
| C7 rolling upgrade | CONFIRMED (a "acceptable") | **REFUTED** (a: new frontend + old pod renders NO control) | **Accepted (Codex — a real break)** |

## Accepted and applied

- **C1 (Codex):** `validate_selector_map` passed each dimension's values through `_string_items`, which
  accepts a comma string — so `{label: "beta,demo"}` was split and accepted, off-grammar
  (`dict[str, list[str]]`). Now requires `isinstance(values, list) and all(isinstance(v, str))`.
- **C4-A (both):** the #107 preview had no generation token; `clearTimeout` cannot cancel a GET already
  sent, so a late count for cluster A could paint under cluster B after a switch. Added a `_previewVersion`
  token + a captured `cluster`, discarded when either changes, and a `clearReportPreview()` used on cluster
  switch and report switch.
- **C4-B (Codex):** a selector label read/assigned by bracket key touched `Object.prototype` for a
  `__proto__` label (a valid map key). Now read by own-key (`selectedFor` with `hasOwnProperty`) and the
  collector stores into a null-prototype map. Defence in depth — the label is chart-validated, but cheap.
- **C6 (Cursor):** `namespaces_for_selectors` did not translate `sqlite3.Error → SnapshotError`, so a
  table read that fails after a clean open 500'd the count endpoint — the exact #117 D1 scar on a new GET.
  Added the wrap, the same boundary its siblings have.
- **C6-B (Codex):** `namespace_count` validated structure only, so an unconfigured selector label returned
  a count (0) instead of null. Now returns null for a label not among the deployment's dimensions.
- **C7-A (Codex):** the form hid `mnemonics` UNCONDITIONALLY, but an OLD report pod has no `selectors`
  ParamSpec, so a new frontend against an old pod rendered NO selector control at all. Now `mnemonics`
  hides only when the spec offers `selectors` (`supportsSelectorMap`); otherwise it renders the single
  control from `namespaceSelectors`.
- **N1 (Cursor):** an unconfigured selector label was a stored failed run (checked in `build()`), not a
  fast 422. Added the subset check in `create_run` (settings in scope) — a 422 before a Run is created;
  `build()` keeps the check as the worker's belt.
- **N2 (both):** `_selector_labels_env` silently dropped blank entries; only a literal `[]` should defer to
  the singular. A blank entry now fails at startup.
- **N3 (Cursor):** the chart README documented only `.label`; added the `.labels` row.
- **N4 (Cursor):** the 401 contract test now covers `/api/namespace-count`.
- **N5 (Cursor):** the catalogue-degrade tests now also assert `namespaceSelectorDimensions == {}`.
- **N6 (Cursor):** a `TestRefusals` row locks the generalized selector-labels guard.

Each fix has a fail-before/pass-after test: the selector-string rejection, the `__proto__` map, the stale
preview (a held newer/older GET pair), the old-pod mnemonic fallback, the count-endpoint 500→null and the
unconfigured-label null, the create_run 422, the blank-label startup error.

## Not weakened / confirmed

- C2 (AND across, OR within, deterministic sort, missing-dimension drop, omitted-dimension unconstrained)
  and C3 (both catalogue fields, first-dim compat, `SnapshotError` degrade, storage seam — no `sqlite3`
  in `server.py`) held under both reviewers. C5 rendered correctly (guard, `GSD_REPORT_NS_SELECTOR_LABELS`
  JSON env, CronJob `--params-json` round-trip). C7 (b)/(c)/(d) — old frontend + new pod, deprecated
  `mnemonics`, old-pod 422 of unknown `selectors` — all work.

## Deploy note (from C7)

On a rolling upgrade the **dashboard image should not roll ahead of the report image**: while the report
pod is old, a run posting `selectors` is 422'd. The new frontend now keeps the single `mnemonics` control
working against an old pod, so Generate still functions; the two images should still land together.

## Second pass (fixed head)

Both reviewers re-ran on the fixed head. V1 (each backend fix closes its hole without swallowing a real
logic error) and V3 (the count / create_run / build() label checks are consistent; a configured-but-
unmatched selector is a 0 count and a 202-then-failed run by design) CONFIRMED by both — Codex proved the
`namespaces_for_selectors` catch lets a `RuntimeError` propagate and only converts `sqlite3.Error`, and
that all three of `mnemonics`/`namespaces`/`selectors` still 202. Two converged findings, both applied:

- **V2-F1 (both):** leaving the namespace-access report cleared the #107 preview but returning did not
  recompute it, so a retained selection showed blank until the next change. Fixed: the report-pick handler
  reschedules the preview on a switch back to namespace-access. Cursor also caught the XOR case — the
  count kept painting when the reader set an explicit `namespaces` alongside `selectors` (which
  `create_run` 422s); fixed with an XOR guard in `schedulePreview` and a reschedule on any param change.
- **V4-F1 (both):** the catalogue gather was N+1 — `2 + clusters × (dimensions + 1)` reads on every 60s
  catalogue load (402 at 100 clusters × 3 dims), which does not scale to the many-cluster estate this whole
  design targets. Fixed: `namespace_selector_dimensions` now reads the whole estate in ONE
  `WHERE key IN (…)` query, `namespace_selectors` derives from it, and `list_reports` derives the compat
  first-dim map from the same fetch — **one** `cluster_namespace_label` read regardless of cluster or
  dimension count (locked by `test_the_catalogue_gathers_the_selector_values_in_one_query`).

Not applied (named, not blocking): the preview count is uncapped where `build()` caps expansion at
`MAX_NAMESPACES=50` (wording-accurate — "match this selection", not "in this report").

## Outcome

The backend AND/OR expansion, catalogue compatibility, storage seam, chart guard/env, JSON transport and
read-only count architecture were sound. First pass fixed two real code holes (the count-endpoint 500 and
the preview race), a real rolling-upgrade break (new frontend + old pod), and the grammar laxness plus the
fast-422/blank-label/doc/test gaps. Second pass fixed a preview-recompute regression and the catalogue
N+1 (the load-bearing many-cluster efficiency fix). Full non-UI suite and the UI selector tests green
after both passes; every verdict re-verified against the code before applying.
