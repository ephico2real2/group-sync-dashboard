# Review — PR #73, B2: retention for membership_event and sync_event

Adversarial second-opinion pass, 2026-09-05, on the nine-claim brief for #73 (`docs/specs/SPEC_B2_history_retention.md`
applied; app 0.13.0, chart 0.12.0). Codex ran at `gpt-5.6-sol` / `xhigh` with a shell and measured (Store probes, query
plans, a Node run of the page's helpers, a 12,000-row upgrade simulation); Cursor ran on `cursor-grok-4.6-high-fast` in
ask mode with the shell blocked and traced from source, marking the unmeasured PLAUSIBLE. Every verdict was re-checked
here; every accepted fix has a test that fails on the code before it.

## First pass — verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 order, hold, standby, exception isolation, once-only warning | PARTIAL: leadership read once for two deletes | CONFIRMED (traced) | **Accepted**: re-check before each table |
| C2 chronological cutoff, bounded batches, cluster scope, index plans | CONFIRMED (both plans shown) | PLAUSIBLE (no shell) | — |
| C3 `@consistent` on the two handlers; the wire; the self tier | PARTIAL: R5 blind to the helper's read | PLAUSIBLE, same finding | **Accepted**: the read at the call sites, new R5 test |
| C4 `retentionNote` renders only for a window, safe on null, three call sites | CONFIRMED (Node run) | CONFIRMED | — |
| C5 config, env, chart defaults; negative window | CONFIRMED; negative → 0 | CONFIRMED; negative → 0 | — (forever is the safe direction) |
| C6 metrics pre-seeded, counts equal the log, HELP true | CONFIRMED | CONFIRMED | — |
| C7 the restore scenario is documented where an operator reads | REFUTED (its most important) | PLAUSIBLE (its most important) | **Accepted**: chart README + CHANGELOG + test; spec risk row corrected in the notes |
| C8 fidelity to the spec and its recorded deviations | CONFIRMED (21 files, all deviations listed) | PLAUSIBLE (no diff) | — |
| C9 the 12,000-row upgrade drains 5000/5000/2000 with the edge advancing | CONFIRMED | CONFIRMED (traced) | — |
| Cursor, not asked: B4's SCHEMA comment says the table has no retention | — | finding | **Accepted**: corrected, held by a test |

## C7 — restoring an old backup

**Finding (both).** With the default 730-day window, a restored copy's first leader cycle takes a backup that succeeds,
which releases the hold, and the prune deletes 5,000 old `sync_event` rows in that same cycle with no warning. Codex
measured it: 6,001 restored rows, 1,001 live after one cycle, the fresh backup copy intact. The spec's closure says
"the runbook says to set both windows to 0 first", but B1's runbook does not exist until R4, and no shipped page —
RELEASING, the READMEs, the CHANGELOG — said it. **Applied:** the chart README's retention section and the CHANGELOG
bullet tell a restoring operator to set both windows to `0` first and why; a test holds both. The spec's risk row is
corrected in its notes: the successful path emits no warning.

## C3 — the API contract could not see the second read

**Finding (both).** `history_retention` read the store inside a helper, so the R5 guard's count of `store.` calls in the
handler body stayed at one, and removing `@consistent` from either handler would have passed. **Applied:** the call
sites pass `store.history_retained_since(cluster_id)` and a new R5 test counts it and requires the decorator.

## C1 — leadership, once for two deletes

**Finding (Codex).** The leader check ran once before both tables' deletes; leadership lost in between still deleted.
The elector is best-effort admission control, not a fence, and the poller says so; still, re-reading before each
destructive call costs nothing. **Applied**, with Codex's losing-elector test.

## Rejected

Nothing outright. Codex's C3 variant (an optional `retained` argument keeping the helper's own read for other handlers)
was not taken: one shape, the read always at the call site, is what the guard can count everywhere.

## Second pass, on the fixed head, with the same models

| Finding | Cursor | Codex | Decision |
|---|---|---|---|
| The four first-pass fixes close their holes | CONFIRMED ×4 | CONFIRMED ×4 (Store probes) | — |
| A `membershipEventsDays` window shorter than the cliff's `windowHours` blinds `GroupSyncGroupCountCliff` | PLAUSIBLE → derive | REFUTED → refuse | **Accepted as DERIVE**: the membership cutoff is the earlier of the two edges; refuse rejected (documented, bounded, and it would break a legal config on upgrade) |
| A person whose only rows were pruned is a 404 the page cannot explain | REFUTED → document, honest empty states, keep the 404 | REFUTED → 200 with a flag | **Accepted Cursor's**: a 200 for any name while a window is on is a username oracle; empty states say "cut", README says what a window costs |
| A degraded cluster's history is pruned like a healthy one's | CONFIRMED (not a gate) | REFUTED → hold it | **Rejected**: age-based retention does not depend on reachability; the backup hold is the safety |
| An exactly-full batch logs "more remain"; HELP infers backlog from one batch | CONFIRMED (a pinned rate is the signal) | REFUTED | **Accepted as wording**: log and HELP say what one batch can and cannot show |
| The version test does not hold the CHANGELOG heading to the pair | CONFIRMED (files agree) | REFUTED | **Accepted**: a new test in `test_chart_versions.py` |
| Release pair 0.13.0 / 0.12.0 everywhere | CONFIRMED | CONFIRMED | — |

## Live, on CRC (measured here)

`/api/version` 0.13.0; `membership-changes` → `{window_days: 0, retained_since: 2026-08-02T04:00:33Z}`; the CR events
endpoint → `{window_days: 730, …}`; the group detail carries the same object; `gsd_retention_rows_deleted_total`
pre-seeded at 0 for all four tables; no prune lines yet, as expected on a month-old history. Repeated after the review
fixes were redeployed (see the PR's comments).
