# Review — reporting code, last 24 hours (P1 + P2 as shipped, 0.21.0–0.22.0)

Adversarial pass, 2026-09-16, over the reporting code written in the previous 24 hours (the P1 mock
fixtures and the P2 multi-dimension namespace selector — `docs/REVIEW_p1_mock_fixtures.md`,
`docs/REVIEW_p2_multidim_selector.md`), run through the **Fable + Codex pipeline** the operator
asked for: **Cursor Fable 5.1 (high)** in ask mode reads the code and produces the full fix for every
issue it finds; **Codex (gpt-5.6-sol, xhigh)** then verifies each finding end to end with a shell —
CONFIRMED/REFUTED plus the failing test — and adjusts the fix where Fable's was wrong or incomplete.
The orchestrator re-checked every verdict here before applying, and traced each proposed fix's
mechanism before trusting it (a correct finding does not make its fix correct).

Fable is NO ZDR; this is deployed-lab reporting code with no secret material, so the trade was
acceptable. The app is deployed on CRC (0.22.0 / chart 0.30.0), so Fable could exercise the UI with
Playwright while it read.

## Verdicts

| Claim | Fable (high) | Codex (xhigh) | Decision |
|---|---|---|---|
| F1 `GET /report/api/namespace-count` 500s on a deeply nested `selectors` JSON (`json.loads` → `RecursionError`, not a `ValueError`) | CONFIRMED, fix + test | CONFIRMED; **Fable's test invalid**, replaced | **Accepted on the fact; test replaced** |
| F2 a stale non-empty `reporting.namespaceSelector.label` renders cleanly (Helm ignores unknown keys) and the selector silently vanishes | CONFIRMED, fix + test | CONFIRMED; **Fable's guard too strict**, relaxed | **Accepted on the fact; guard corrected** |
| N3 a pre-capture snapshot (no `cluster_namespace_label` table) reports an attested `0` instead of "unknown" | CONFIRMED, fix + test | CONFIRMED; **Fable's fix incomplete** (mnemonics path unguarded), completed | **Accepted on the fact; fix extended to both paths + the endpoint** |
| V4 `Snapshot.namespace_selectors` is dead — no caller since P2 superseded it with `namespace_selector_dimensions` | CONFIRMED | CONFIRMED | **Accepted; removal deferred to the compat-field removal (issue #133)** |

## F1 — the namespace-count preview 500s on a pathologically nested selector

**Finding (Fable).** `GET /report/api/namespace-count` parses `selectors` with `json.loads` inside a
`try/except (ValueError, ValidationError)`. A deeply nested JSON array (`"["` repeated ~10 000 times,
which fits inside h11's 16 KiB request line) makes `json.loads` raise `RecursionError` — which is
**not** a subclass of `ValueError` — so it escapes the catch and returns a 500, against the endpoint's
documented "bad input, an empty selection or a missing snapshot returns a null count" contract. Fix:
add `RecursionError` to the caught tuple. Test: post a 100 000-bracket string as the `selectors` query
through `TestClient` and assert 200 / `{"namespaces": null}`.

**Re-check.** The mechanism is real and is CPython-version-specific in its depth but not in its class:
`json.loads("["*20000)` raises `RecursionError` on this interpreter (3.13.5), first observed at
recursion depth ~9998, and `issubclass(RecursionError, ValueError)` is `False` — so the escape is
exactly as described. **Fable's test is invalid**: `httpx` (Starlette's `TestClient`) raises
`InvalidURL: URL component 'query' too long` before the request ever reaches the app, so the test
would error in the client, not exercise the endpoint. Verified by running it. **Codex's replacement**
monkeypatches `gsd.reporting.server.json.loads` to raise `RecursionError` for a sentinel value and
drives the endpoint normally — it reproduces the decoder's behaviour at the seam the fix touches,
without depending on a wire payload the client rejects.

**Decision.** Accepted on the fact; Fable's test replaced with Codex's monkeypatch test. Applied:
`except (ValueError, ValidationError, RecursionError)` in `local-development/gsd/reporting/server.py`
`namespace_count`, with a comment stating the class relationship and the h11 line-size fact. Test
`test_json_recursion_error_is_null_not_500` in `TestNamespaceCountPreview` (fails 500 before, passes
null after).

## F2 — a removed singular `reporting.namespaceSelector.label` renders silently

**Finding (Fable).** `reporting.namespaceSelector.label` was removed in 0.22.0 (P2 made the selector
multi-dimension: `reporting.namespaceSelector.labels`, a list). Helm ignores keys the templates do not
read, so a values file left over from 0.21 that still sets `.label` renders cleanly while the selector
it configured silently disappears — the exact silent-misconfiguration class the chart refuses
everywhere else. Fix: fail the render when the key is present. Fable's guard:
`{{- if hasKey $nsSelector "label" -}} {{- fail … -}} {{- end -}}`.

**Re-check.** The finding is real: `helm template … --set reporting.namespaceSelector.label=x` renders
with return code 0 on the unfixed chart. **Fable's guard is too strict**: 0.21 shipped `label: ""` as
its default, and an upgrader may carry `label: null` or `label: ""` in an override; `hasKey` alone
fails the render on those *no-op* values, turning a clean upgrade into a hard error over a value that
never did anything. **Codex's fix** refuses only a materially-set value:
`{{- if and (hasKey $nsSelector "label") (not (empty (get $nsSelector "label"))) -}}` — an empty or
null `.label` stays an allowed no-op, a non-empty one fails with a message pointing at the 0.22.0
upgrade note and `reporting.namespaceSelector.labels`.

**Decision.** Accepted on the fact; guard relaxed to the material-value form. Applied in
`charts/group-sync-dashboard/templates/_helpers.tpl`, before the `.labels` range guard so the removed
key is refused first even when both keys are present. Tests: a refusal row in
`test_chart_reporting.py::TestRefusals::test_each_guard_names_its_key` and a dedicated
`test_the_removed_singular_label_refuses_only_a_material_value` proving `label=""` renders (return
code 0), a material `.label` fails with "was removed", and both-keys-set still fails on the removed key.

## N3 — a pre-capture snapshot claims an attested zero

**Finding (Fable).** The namespace-label capture (`cluster_namespace_label`) arrived at snapshot schema
12. A copy written before that — an older dashboard's snapshot still inside the rolling window — has no
such table, and `Snapshot.namespaces_for_selectors` / `namespaces_for_metadata` guard on
`has_table(...)` and return the empty list when it is absent. So a selector or mnemonic selection over
a pre-capture snapshot expands to `[]` and is reported as "0 namespaces match" — indistinguishable
from a real empty match, and wrong: the truth is "this snapshot cannot answer". Fix: detect the missing
table and refuse/return-unknown instead of 0. Fable guarded the `selectors` branch of `build()`.

**Re-check.** The finding is real. **Fable's fix is incomplete**: the deprecated `mnemonics` branch of
`build()` expands the *same* table and would still report an attested 0; and the preview endpoint
(`GET /report/api/namespace-count`) has the same defect independently. **Codex's fix** adds one
predicate, `Snapshot.selector_capture_present()` (`return self.has_table("cluster_namespace_label")`),
and calls it in all three places: both branches of `catalogue/namespace_access.py::build()` (raising
`ValidationError("… this snapshot carries no namespace-label capture (it predates the capture) …")`)
and the endpoint (returning `{"namespaces": null}`).

**Decision.** Accepted on the fact; fix extended to both `build()` branches and the endpoint. Applied
in `snapshot.py`, `catalogue/namespace_access.py` and `server.py`. Tests:
`test_a_pre_capture_snapshot_returns_unknown_not_zero` (endpoint) in `TestNamespaceCountPreview`, and
`test_a_pre_capture_snapshot_refuses_selectors_and_mnemonics` in `TestMultiDimensionSelector`, each
dropping the table and setting `PRAGMA user_version = 11` on the copy — both assert the refusal for
the selectors path and the mnemonics path (the branch Fable's own fix missed).

## V4 — `Snapshot.namespace_selectors` is dead code (removal deferred)

**Finding (Fable).** `Snapshot.namespace_selectors(self, key: str)` in
`local-development/gsd/reporting/snapshot.py` is the pre-P2 single-dimension gather for the B3
multi-select. P2 (0.21.0) replaced it with the batched, multi-dimension `namespace_selector_dimensions`
— and `namespace_selectors` now merely wraps that single-key. Nothing calls it any more.

**Re-check.** Confirmed: `grep -rn "\.namespace_selectors(" local-development/` returns no call site;
the only remaining references are doc comments (two in `snapshot.py`, one in the docstring of
`tests/test_reporting_server.py::test_a_table_read_after_a_clean_open_that_fails_is_200_not_500`) that
cite it as an example of the SnapshotError boundary — and that test-comment claim ("wraps
`clusters()`+`namespace_metadata_values`") is itself stale, since the method now wraps
`namespace_selector_dimensions`.

**Decision.** Accepted, but **not removed in this PR.** Operator decision (2026-09-16): defer the
removal to the compat-field-removal PR — the one that drops the deprecated `mnemonics` report parameter
("still works one release") — so the dead-code sweep lands in one reviewable place and this PR stays
the three-defect fix. Tracked as **issue #133**, which also lists the stale comments to repoint when
the method goes.

## Not asked, and what happened to it

- Fable exercised the deployed UI (0.22.0) with Playwright and reported the per-dimension selector and
  the debounced preview count render correctly against the live snapshot — no defect. Recorded, no
  change.

## Outcome

Four findings, all CONFIRMED by both models. Three are code defects fixed in this PR (F1, F2, N3); the
fourth (V4) is dead code — `Snapshot.namespace_selectors`, uncalled since P2 — whose removal is
deferred to the compat-field-removal PR and tracked as issue #133, kept out of this PR to keep the fix
focused. In every one of
the three code fixes Codex's verification corrected Fable's proposed fix — an invalid test (F1), a
too-strict guard (F2), an incomplete fix that left the mnemonics path and the endpoint exposed (N3) —
which is the pipeline working as designed: Fable finds and drafts, Codex proves and hardens, the
orchestrator traces and applies. Each fix ships with a fail-before/pass-after test; the fail-before was
demonstrated by stashing the four source changes and running the new tests against the unfixed head
(exactly the five new assertions failed, the twelve pre-existing guard rows passed). Re-validated after
the edits: the reporting server, namespace-selector and chart-reporting suites; `helm template` for the
material-value, empty-value and both-keys-set states of `.label`; version bump to application 0.23.0 /
chart 0.31.0 with the CHANGELOG entry. A second pass on the fixed head was not run separately — the
Codex verification *was* the second model on each finding, on the fixed snippets.
