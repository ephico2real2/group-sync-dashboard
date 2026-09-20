# Review record — the Kyverno policy module (#165, #170, PR #228)

Branch `feat/170-kyverno-module`, base `feat/170-kyverno-discovery` (PR #227) until it merged at `255f2ed`,
then `main`. Three seats on head `0989e4b` (the module deployed on the lab at that head): Cursor Grok 4.6
(ask mode, from source and the two discovery records), Codex GPT-5.6 xhigh (a `git archive` of the head with
the venv; executable probes of the store's transitions, the API's filters, the metrics' cost at 10 000 rows,
`ago()` over a million instants) and OB3 (Opus 5, the live lab: the deployed page driven through the route as kubeadmin, the CRD's status schema read off the cluster, mutants against the PR's tests, a 10 000-row cost measurement). OB3 ran on the same head after Grok and Codex, so several of its findings overlap fixes already on the branch; the column says which.

## Claims × decision

| # | Claim | Grok | Codex | OB3 | Decision |
|---|---|---|---|---|---|
| M1 | Fidelity to the measured result shape and the `source` map | CONFIRMED | CONFIRMED (the 09-19 sample read field by field) | CONFIRMED | Holds. |
| M2 | Discovery, 404 vs outcome, paging | CONFIRMED on the mechanism; the namespaced twins the chart grants are never listed (its N1) | REFUTED — the five cluster collections only; a cluster using namespaced policies alone read `policies: 0` beside its rows | PLAUSIBLE — a served-but-empty `openreports.io` group masked the `wgpolicyk8s.io` reports: the reader took the first group that answered, and which group a cluster *serves* is decided by installed CRDs, not by Kyverno's flag (its test fails on `0989e4b`) | **Accepted** (F1) — every served group is read, `api_group` names the one carrying reports; the mutant pins (a 503 on discovery raised, a 403 on a policy kind raised, every LIST paged) folded into `tests/test_kyverno.py`. |
| M3 | The store's transitions and the worse-result rule | CONFIRMED | CONFIRMED (a probe: recreated uid → appeared+cleared, renamed policy → appeared+cleared, still-problem → nothing; the plans seek the primary key) | CONFIRMED (a harness: recreated uid, renamed policy, worsening warn→fail, every result pair, absent-then-present baseline, one transaction, index seeks on every plan) | Holds; the harness folded in. |
| M4 | The poller stage and the retention window | CONFIRMED; the binding cadence is right | CONFIRMED (300 s default) | PLAUSIBLE — `kyverno.metricsUrl` names in-cluster Services and was handed to EVERY cluster's fetch: a remote cluster would print the host's breaker as its own | **Accepted** (F4) — `kyverno_metrics_url_for()`: the host cluster's URL only, `""` for the rest. Its cost note (a full LIST per refresh, 330 KB / 0.28 s for 112 reports) is step 3's watch, deferred and now said in the CHANGELOG. |
| M5 | The API | CONFIRMED | REFUTED — `?policy=` alone is not one policy: a ValidatingPolicy and a MutatingPolicy sharing a name answered `total=2` | CONFIRMED; `?policy=` refused a namespaced wire string at its maximum (63+1+253 = 317 > 253, a 422 measured on the live route) | **Accepted** — `max_length=317`; a test sends 317 characters. |
| M6 | The metrics | CONFIRMED (cost not measured) | REFUTED on cost — every scrape materialised every row (`kyverno_results(limit=1_000_000)`: 82 ms and 16.7 MiB peak at 10 000 rows, a temporary B-tree for the ORDER BY) | CONFIRMED; measured the row materialisation (36 ms at 10 000 rows vs 2.7 ms for the GROUP BY) | Already accepted from Codex (`kyverno_result_counts()`); OB3's F8 pin (the collector never calls `kyverno_results()`) folded in. |
| M7 | The chart | REFUTED — the CHANGELOG had no Kyverno entry (measured empty) | REFUTED — the same, plus `get` verbs the reader never uses, and the default render changes for an operator who sets nothing | REFUTED on two: no CHANGELOG entry at `0989e4b`; the namespaced twins granted but never read | Both already applied from Grok/Codex; OB3's guard (the Unreleased section names the current chart version when it moved) kept — unlike Grok's, it skips when there is no Unreleased section, so `prepare-release.py` still passes. |
| M8 | The page | REFUTED — the switch dropped focus (the payload nulled and Loading… painted destroyed `#kyverno-controlled` before the by-id restore); `span.warn` is not a class | REFUTED — the same focus loss; the auto-refresh fingerprint omitted `data.kyverno` (a Kyverno-only change updated memory, not the DOM); the policy's condition message hid in a `·` tooltip | REFUTED on focus (the deployed page's `activeElement` was BODY after the switch); the fingerprint omission; the breaker note blamed "not set" when the scrape had failed; the condition note hidden | Focus and fingerprint already applied from Grok/Codex; **Accepted** (F7) `breaker_configured` in the payload and the note telling "not set" from "set, the last scrape failed"; **Accepted** the policy buttons' ids and the `namespaced` chip; the note printed as `.err` text. |
| M9 | `ago()` | CONFIRMED | CONFIRMED (past instants 0..10⁶ s unchanged; the old function `RangeError` at +40 min, the new one "in 40m") | CONFIRMED (22 625 past instants, old vs new, 0 differences; +40 min: `RangeError` → "in 40m") | Holds. |
| M10 | Tests | CONFIRMED; one more mutant (its own) | CONFIRMED; the named mutants unpinned | CONFIRMED — five mutants survive the PR's tests (transition by name, warn/fail rank, events ascending, last-endpoint-wins breaker, any ClusterError on a policy path read as absent) | **Accepted** — the five pins folded into `tests/test_kyverno.py`; the 10 000-row timing test dropped (it prints a measurement and asserts nothing a unit test should). |

OB3's volunteered findings beside the table: **N4** (accepted, F6) — no CEL CRD defines a top-level
`status.conditions`; readiness is `status.conditionStatus.ready`, and `conditionStatus.message` is the
VAP-generation note (the CRD's own description), which the page had printed as the readiness note. The note is
now a condition that is not True (`RBACPermissionsGranted: reports-controller is missing RBAC…`) and the message
only when nothing failed and the policy is still not ready; the fixture takes the lab's measured shape. **N1–N3**
(three red pins at `0989e4b`) were already fixed on the branch. **N5** — step 3's watch and its cost were deferred
without being said; the CHANGELOG says it now. **N6–N8** — no fix owed.

## Re-validation

- `test_kyverno.py` 37 (the PR's 12, the two reviews' pins, OB3's harness) + the chart, versions, contract, KPI
  tests; `TestKyvernoPage` 5; each pin fails on the page or the module without its fix and passes with it.
- The full suite and the CRC walk after the pass: the PR's comment. The walk at `0989e4b`
  (`reports/2026-09-20_kyverno-170/`): 115 reports, 667 legacy results not shown, 9 CEL results, the three
  breakers summed (12 505, no drop), `errors : []`.
