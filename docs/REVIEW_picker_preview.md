# Review record — the namespace picker, the reviewer prefill and the totals preview (#143 phases 2–3, PR #224)

Branch `feat/143-picker-preview`, base `feat/149-forms` (PR #222) until it merged at `5e6b699`, then `main`.
Three seats on head `44587ce`: Cursor Grok 4.6 (ask mode, from source), Codex GPT-5.6 xhigh (a `git archive`
of the head with the venv; a TestClient probe of the endpoint, the backend modules run — 182 passed; Chromium
could not launch in its sandbox) and OB3 (Opus 5, the live worktree — report pending at the time of this
record's first commit; its column is added when it lands). Nine claims (M1–M9) plus "not asked".

## Claims × decision

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| M1 | The preview's contract: validated as a run, `build()` only, the slot released on every path | CONFIRMED (param and selector 422s before the slot; `try/finally`; the worker's `assemble`/`store`/`note_*` never entered) — caveat: the unknown-cluster 404 and the no-snapshot 503 sit after `acquire`, and `create_run` 202s those and fails in the worker (the preview is stricter) | REFUTED on the same caveat: unknown cluster → preview 404 / runs 202-then-failed; no snapshot → 503 / 202; a bad target while busy → 429; side effects none (`history=(1,1) artifacts-equal=True`), release after an exception (`500 200`) | **Rejected** — the difference is *when*, not *what*: the run POST is asynchronous by design (the worker answers), the preview is synchronous and refuses at once, which is the better answer for a form; a 429 for a bad target while a preview builds is transient and costs nothing. Codex's pre-slot validation would open the snapshot twice per preview for that. |
| M2 | Cost and safety: one `build()` under one slot; who may call | CONFIRMED — a ticket is minted only after `require_admin_tier`, so the bound is "one administrator at a time on this path"; the slot does not cover `RunManager._render` (the same person can already Generate) | CONFIRMED (`api.py` `require_admin_tier()`; one worker, one replica in the chart) | Holds; recorded: the slot is a bound on the endpoint, not a CPU cap. |
| M3 | The page's data flow: debounce, versioning, once per form+cluster, every change path, in-place write | REFUTED — three paths: the selectors' Clear (`clearNamespaceAccessSelectors`) never called `scheduleTotals`; the Subject Clear neither (`_totalsKey` already matched, so `wireReports` did not refetch); a cluster switch painted cluster A's totals beside cluster B for the debounce (keyed by spec only) | REFUTED, the same three | **Accepted** — both Clears schedule the totals; `view.reportTotals` carries the cluster and paints only for the cluster on screen; the test drives Clear and a `navigate()` to `prod-east`. Also Grok's dual-number note: the `#107` count ("80 namespaces match") beside the totals ("50 namespaces · …") on a wide selection — the totals count is after the 50-namespace cap, which is not a truncation (the artefact's Coverage note says so) — **documented**, not changed. |
| M4 | The namespaces picker: the lookup when the cluster has any, the text field otherwise; the posted shape; the XOR | CONFIRMED | CONFIRMED (`['prod-ns','(cluster-scoped)']` accepted; the XOR 422 reproduced) | Holds; Grok's "not asked": `(cluster-scoped)` was not a picker option — **accepted**, offered first when the cluster lists any namespace. |
| M5 | The reviewer prefill: once per page life, an edit kept, schedules untouched | CONFIRMED | CONFIRMED (`reviewer === undefined` only; `'  Alice  ' → 'Alice'`, `'   ' → 422`; the CronJob posts its `params` directly) | Holds. |
| M6 | The str trimmer's behaviour preservation | CONFIRMED | CONFIRMED (200 padded → length 200; 201 → 422; the three str params all default `''`) | Holds. |
| M7 | The discovered key set: seven, live and degraded, the page tolerating six | CONFIRMED | CONFIRMED (both answers `7` keys, listed) | Holds. |
| M8 | The tests pin what they claim | REFUTED — the route-inventory test never was "one POST" (it lists write routes; still strict); the UI test's "sorted and non-empty" is not "from the fixture"; Generate asserted once, before the pick; the 429 test never re-POSTs after `th.join()` | REFUTED, the same | **Accepted** — the picker asserted to the seed's list (`(cluster-scoped)` first, then its nine namespaces), the totals to the exact sentence, Generate after the pick; the server test POSTs after the join (200), a 422 raised inside `build()` (the slot released — 200 after), an unconfigured selector label (422). |
| M9 | The documentation | REFUTED — the answer shape omitted `report` and `cluster`; "when a cap bites" overclaims (`truncated` is the row limit, not the selector cap) | REFUTED — the same shape; "debounced on every change" contradicted by the two Clears | **Accepted** — the shape, the row-limit wording, the Clears fixed so the sentence is true. |
| N1 | (Codex) "1 namespaces" | — | the noun should agree; a twenty-entry noun table offered | **Accepted on the fact, snippet rejected**: one of a thing drops the trailing `s` of its key — `1 namespace · 2 group bindings · 1 user binding` on the seed; no table. |
| N2 | (Grok) `aria-live` on a node `render()` rebuilds: a poll's repaint re-announces the same sentence | drop the attribute from the template | 500 ms is adequate | **Rejected** — a live region inserted with its text is not a change to a live region, and the Reports page repaints on a poll only when its data changed (the fingerprint test); the in-place write now skips an unchanged text. |
| N3 | (both) the semaphore on a killed thread; one slot per app | `finally` is what there is; per-app is what you want | — | Holds; recorded. |

## Re-validation

- `tests/test_ui.py -k totals_preview` fails on the page without the fixes (the picker's first option) and
  passes with them; `TestReportFormsReview` + `TestReportsTab` 38 passed; `TestPreviewAndNamespacePicker`
  3 passed with the release and the selector-label assertions.
- The full suite and the CRC walk after the pass: the PR's comment.
