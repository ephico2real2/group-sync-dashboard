# Review — PR #128 (P1: mock namespaces carry company.net/mnemonic + app-environment)

Focused pass, 2026-09-15, on a mock test fixture + two test assertions — the enabler for the
multi-dimension selector (design `docs/DESIGN_reporting_selectors_snapshots_and_windows.md` §6). **No
production code.** Cursor ran `cursor-grok-4.6-high-fast` in ask mode (source only). Codex
(`gpt-5.6-sol`/xhigh) hung on the codex-cli stdin gotcha (it ran 3+ hours reading stdin and was killed;
see the `codex-exec-stdin-hang` memory). **Operator decision (2026-09-15): proceed Cursor-only for this
mock-only PR; run the full two-reviewer pass on P2/P3/P4, where the production code lives.**

## Verdicts (Cursor)

| Claim | Verdict | Decision |
|---|---|---|
| C1 no regression to existing mock-app tests | CONFIRMED | — (no test asserts an exact namespace set/count; `test_fetch_namespaces` requests only `team`) |
| C2 the two-dimension down-select test is non-vacuous | CONFIRMED | — (`acme-app`'s exact-dict equality is the load-bearing probe: a whole-map regression fails it) |
| C3 the poll-e2e capture assertion is sound | CONFIRMED, with a volunteered strengthening | **Accepted** |
| C4 fixture adequacy for P2's AND/OR selector test | CONFIRMED | — with P2 notes (below) |

## Applied (C3)

The poll-e2e test asserted capture by membership (`in captured` / `not any`), so a hypothetical
whole-label-map regression would add `team` / `kubernetes.io/*` rows and still pass. C2 (the
request-surface exact-dict on `acme-app`) already catches that, but the poll test is stronger as an
**exact set**. Replaced the membership block with an exact-set assertion over all 13 expected rows
(re-verified against the live capture: `8 passed`). A whole-map regression now fails the poll test too.

## Notes carried to P2 (not P1 changes)

- The mock deliberately has **one** single-dimension namespace (`gsd-shared`, mnemonic only) per §6.
  P2's selector unit tests should synthesize the **env-only** and **unlabeled** duals via the existing
  synthetic snapshot in `local-development/tests/test_namespace_selector.py`, not the mock.
- P2's "omitted-dimension = unconstrained" case must select on **`prod`** (four mnemonics share it) so it
  is distinguishable from a specific mnemonic+env pair (the `qa`/`rnd` values are unique).

## Outcome

No blocking findings; the fixture is an adequate enabler and does not weaken existing coverage. The one
worthwhile test-strength improvement is applied. mock-app suite green. P1 merges on this review + the
orchestrator's own verification; the substantive PRs get both reviewers with the fixed codex invocation.
