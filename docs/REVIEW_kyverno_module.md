# Review record — the Kyverno policy module (#165, #170, PR #228)

Branch `feat/170-kyverno-module`, base `feat/170-kyverno-discovery` (PR #227) until it merged at `255f2ed`,
then `main`. Three seats on head `0989e4b` (the module deployed on the lab at that head): Cursor Grok 4.6
(ask mode, from source and the two discovery records), Codex GPT-5.6 xhigh (a `git archive` of the head with
the venv; executable probes of the store's transitions, the API's filters, the metrics' cost at 10 000 rows,
`ago()` over a million instants) and OB3 (Opus 5, the live lab — column added when it lands).

## Claims × decision

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| M1 | Fidelity to the measured result shape and the `source` map | CONFIRMED | CONFIRMED (the 09-19 sample read field by field) | Holds. |
| M2 | Discovery, 404 vs outcome, paging | CONFIRMED on the mechanism; the namespaced twins the chart grants are never listed (its N1) | REFUTED — the five cluster collections only; a cluster using namespaced policies alone read `policies: 0` beside its rows | **Accepted** — the reader lists the `Namespaced<Kind>` twin under the family kind (the 09-19 probe's `source: KyvernoValidatingPolicy`, `namespace/name`), listed once in `policy_kinds_served`; a test joins a namespaced policy's rows to its row. |
| M3 | The store's transitions and the worse-result rule | CONFIRMED | CONFIRMED (a probe: recreated uid → appeared+cleared, renamed policy → appeared+cleared, still-problem → nothing; the plans seek the primary key) | Holds. |
| M4 | The poller stage and the retention window | CONFIRMED; the binding cadence is right | CONFIRMED (300 s default) | Holds. |
| M5 | The API | CONFIRMED | REFUTED — `?policy=` alone is not one policy: a ValidatingPolicy and a MutatingPolicy sharing a name answered `total=2` | **Accepted** — `?kind=` beside `?policy=`; the page passes both from the row; API.md says so; a test holds `total=2` → `total=1`. |
| M6 | The metrics | CONFIRMED (cost not measured) | REFUTED on cost — every scrape materialised every row (`kyverno_results(limit=1_000_000)`: 82 ms and 16.7 MiB peak at 10 000 rows, a temporary B-tree for the ORDER BY) | **Accepted** — `kyverno_result_counts()`: one `GROUP BY policy_kind, result` per cluster per scrape; the privacy and zero/unknown semantics held as claimed. |
| M7 | The chart | REFUTED — the CHANGELOG had no Kyverno entry (measured empty) | REFUTED — the same, plus `get` verbs the reader never uses, and the default render changes for an operator who sets nothing | **Accepted** the CHANGELOG (the entry was lost in a `git stash` cycle around the merge of `main` — restored; Grok's guard over the Unreleased section **rejected**: `prepare-release.py` empties that section when a release is cut and runs the suite on the result, so the guard would have refused every release — measured, eight `test_prepare_release` failures) and `list`-only grants (the group discovery is API discovery every identity has). **Rejected** the opt-in default: the module auto-detects and the operator's rule is that switches default on; the CHANGELOG says a default install gains the grants. |
| M8 | The page | REFUTED — the switch dropped focus (the payload nulled and Loading… painted destroyed `#kyverno-controlled` before the by-id restore); `span.warn` is not a class | REFUTED — the same focus loss; the auto-refresh fingerprint omitted `data.kyverno` (a Kyverno-only change updated memory, not the DOM); the policy's condition message hid in a `·` tooltip | **Accepted** all: `refresh()` only on the switch and the narrowing (the filter bar's rule; the old rows stay until the answer lands), `data.kyverno` in the fingerprint, the note printed in words (`60eeb0f`), `.err` for a not-ready policy; a test drives the switch by keyboard and an auto refresh with a Kyverno-only change. |
| M9 | `ago()` | CONFIRMED | CONFIRMED (past instants 0..10⁶ s unchanged; the old function `RangeError` at +40 min, the new one "in 40m") | Holds. |
| M10 | Tests | CONFIRMED; one more mutant (its own) | CONFIRMED; the named mutants unpinned | The three review tests above pin the twins, the kind filter and the page's two defects; the remaining mutants (a recreated same-name resource's transition, warn vs fail, the events' order, the three-URL sum) are pinned in part by the store test's recreated-uid case and the breaker accumulation test — recorded, the rest owed. |

## Re-validation

- `test_kyverno.py` 12 + the chart, versions, contract, KPI tests; `TestKyvernoPage` 3; the switch/fingerprint
  test fails on the page without its fixes and passes with them.
- The full suite and the CRC walk after the pass: the PR's comment. The walk at `0989e4b`
  (`reports/2026-09-20_kyverno-170/`): 115 reports, 667 legacy results not shown, 9 CEL results, the three
  breakers summed (12 505, no drop), `errors : []`.
