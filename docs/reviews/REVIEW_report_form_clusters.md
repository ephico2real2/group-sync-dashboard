# The report form names its cluster (PR #269, issue #267, app 0.30.0 / chart 0.47.0) — adversarial review record

**Target:** `feat/267-cluster-in-report-forms` at `1c971e2` (the merge of `main` into the feature
branch; merge-base with `main` is `977365e`). One reviewer ran this pass: **OB1-lite** (Anthropic
Fable 5.1 at default effort, the everyday third-reviewer seat), on an eight-claim brief naming the
exact file, symbol and expected behaviour per claim. It had the session's tools and worked from
read-only clones under the scratchpad — `tree` = head, `base` = `977365e`, `revert` = head with one
file group reverted — so every verdict below carries a command and its output rather than a reading.
The repository itself was never touched.

The brief was written around the one thing that would be expensive to get wrong: **a report is one
cluster's document.** Several clusters means N runs, N artefacts and N hashes, never one document
spanning clusters. Claims C1, C7 and C8 exist to catch that decision drifting.

**Baseline measured on the head before the pass:** `tests/test_reporting_server.py` 101 passed; the
hermetic suite (`tests/` less `test_ui.py` and `test_live_smoke.py`) 4465 passed, 15 skipped;
`tests/test_ui.py` 549 passed.

## Verdicts

| Claim | OB1-lite | Re-check | Disposition |
|---|---|---|---|
| C1 the seal: a single-cluster run's `canonical()` shape and hash are unchanged; `cluster` is always one id | CONFIRMED — no model file in the diff; `Run.cluster: str` and `canonical()` unchanged; base-vs-head and head-vs-head canonical documents differ on the *same two lines* (the About section's "Generated at" and "Run id"), so shape and data are identical | the two run facts sit inside `sections`, so any two runs differ today — pre-existing, not this PR | accepted, no change |
| C2 partial failure: one cluster's failure leaves the others' documents | CONFIRMED — the worker catches per run and `_loop` iterates ids; API test gives `{crc-local: done, ghost: failed, prod-east: done}`, both survivors carry a sha256 | the noted caveat — the UI test injects `ghost` via page state — is answered by the API test, which drives the service | accepted, no change |
| C3 the cluster-change chokepoint clears every lookup-sourced field and says what went | CONFIRMED on the clearing — `dropClusterBoundFields` covers `{mnemonics, selectors}` ∪ every ParamSpec with `source`, across every form; typed text is kept. **The sentence it shows is garbled on the fleet path** | true: `esc(note.to)` with `to: null` renders "changed from crc-local to — … the lookups now offered are 's." | **fixed** (V1), with a test |
| C4 the last chip cannot be unchecked, and there is no promote gesture on an unchecked chip | CONFIRMED — `targets.length === 1` guard, `aria-disabled`, click guard; clicking an unchecked chip *adds* it | — | accepted, no change |
| C5 tier and visibility: the chips leak nothing the nav does not | CONFIRMED — the ticket is minted only above `require_admin_tier`, the page refuses below the wide tier before any catalogue fetch, and the chip list is `/api/clusters`, reachable at every tier by design | matches the `/metrics`-style deliberate decision already recorded for that endpoint | accepted, no change |
| C6 the builder's claim that 8 tests fail on the unpatched code | CONFIRMED by reverting each file group and re-running — 4 reporting tests fail on 422-vs-202, 4 browser tests on the missing `#report-clusters`. **Two asserts in the list-shape test hold on base too** | measured: on base the 422 detail is the string `"a viewer run names its cluster"`, so `== 422` alone cannot tell "refused because the list is empty" from "refused because `clusters` is unknown" | **fixed**: both asserts now name the `loc` and the pydantic error type |
| C7 the docs describe N runs, not one document | CONFIRMED — `local-development/API.md` and `docs/CHANGELOG.md` both say one run per cluster, each artefact its own sha256 | the brief said `docs/API.md`; no such file exists — the API doc is `local-development/API.md`, which is what the PR changed | accepted; the brief was wrong, not the PR |
| C8 not asked | twenty clusters fine (cap 100, repeats refused, one queue slot); a cluster removed mid-selection silently leaves the set; schedules untouched; chips are `role=checkbox` in a labelled group with one live region per batch | — | accepted, no change |

## Volunteered findings

All three are page-side, none touches the seal, the service or the fan-out design. Each was traced
before its fix was applied — a correct finding does not make its fix correct.

**V1 — the note is garbled on the fleet path.** The Overview is the fleet (#172), so a visit there
records `to: null`; the boot cycle then stamps the first cluster *outside* `navigate()`, the one
sanctioned bypass, so no later chokepoint pass rewrites the note. The reader coming back to Reports
saw "Cluster changed from crc-local to — users picked on crc-local was cleared; the lookups now
offered are 's." **Traced:** the boot stamp's `navigate({}, {replace: true})` does re-enter the outer
block, but the drop is nested under `nextCluster !== view.cluster`, so the note genuinely survives.
**Fixed:** name the fleet for what it is, and quote the cluster the form is on *now* for the lookups —
which is identical to `note.to` on the ordinary path, since the drop runs before `view.cluster` moves,
so the change is behaviour-preserving everywhere but the fleet.

**V2 — a poll failure after the runs were queued was worded as a refusal.** Any error landed on
`batch.error`, and the head read "the request was refused" although the service answered 202 and the
runs render and reach the Library. **Traced:** `batch.runs` is populated only after the POST is parsed,
so a non-empty `runs` proves the request was accepted; the only errors reachable afterwards are the
per-run polls and the Library refresh, both of which are *following* the runs, not the request.
**Fixed:** branch the sentence on whether runs were answered.

**V3 — dismiss was global, the note is per form.** The note renders from `cleared[spec.name]`, but the
dismiss handler nulled `view.reportClusterNote` for every form, so a second form's cleared lookup was
never said to the reader who opened it. **Traced:** the fix keys the delete on `view.report`, which is
safe because the form card renders only for `view.report` — `pick` has no fallback (a key the catalogue
does not carry opens nothing). **Fixed:** delete this form's entry, and null the note only when the
last entry goes.

## Re-validation

- `tests/test_ui.py::TestReportClusterControl` — 6 passed patched; with `index.html` reverted to the
  head, exactly the 3 new tests fail and the 3 existing ones pass.
- The tightened list-shape asserts were measured against a reverted `server.py`: base answers a string
  detail, so the new assertions do not hold there — they now look at what they claim to.
- `tests/test_reporting_server.py` — 101 passed.
