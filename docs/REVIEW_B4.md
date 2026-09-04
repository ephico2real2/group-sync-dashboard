# Review — PR #72, B4: the group-count cliff alert with read-only silencing

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #72 (`docs/specs/SPEC_B4_group_count_cliff.md`
applied; app 0.12.0, chart 0.11.0). Codex ran at `gpt-5.6-sol` / `xhigh` with a shell and measured (Store probes, helm
renders, EXPLAIN QUERY PLAN; its sandbox could not reach the cluster); Cursor ran on `cursor-grok-4.6-high-fast` in ask
mode with the shell blocked and traced from source, marking the unmeasured PLAUSIBLE. Every verdict was re-checked here,
and every accepted fix has a test that fails on the code before it.

## First pass — verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 `before = after + removed − added` over `observed_at >= since` is the count a poll `window` ago held | REFUTED | CONFIRMED | **Accepted (Codex)**: strictly after |
| C2 the `until=` grammar silences exactly `YYYY-MM-DD` up to and including today | REFUTED | CONFIRMED | **Accepted (Codex)**: shape check |
| C3 API and collector derive the same policy; both kinds withheld at self; uniform row keys | CONFIRMED | CONFIRMED | — |
| C4 migration 8, `replace_group_state`, Protocol, and the query uses the new index | CONFIRMED (plan shown) | PLAUSIBLE | — (plan measured here too) |
| C5 config validation, env precedence, list trimming | CONFIRMED | CONFIRMED | — |
| C6 chart guard, rule gating, `for: 15m`, quoted globs | CONFIRMED | CONFIRMED | — |
| C7 UI hero count, tag, badge, `esc` on null | CONFIRMED | CONFIRMED | — |
| C8 reader and poller carry and clear the annotation | CONFIRMED | CONFIRMED | — |
| C9 fidelity to the spec and its recorded deviations | CONFIRMED (seven listed) | CONFIRMED (ten listed) | — |
| C10 the next real upgrade needs no hand fix | PLAUSIBLE (no cluster) | PLAUSIBLE (no shell) | — (measured live here: see PR comment) |
| Cursor, most important: the ratio compare is a float compare and misses exact boundaries | — | REFUTED-class finding | **Accepted**: exact arithmetic |
| Cursor, not asked: the rule summary hardcodes "half" | — | finding | **Accepted**, as a percentage |
| Cursor, debt: `group_detail` lacks `cliff_silence` | — | noted | **Accepted**: added |

## C1 — the window's boundary

**Finding (Codex).** A real Store sequence — 20 members before the window, then 5 and then 8 in polls stamped exactly
at `since` — reconstructed `before = 20`, the state before the boundary poll, not the 8 that poll held. The inclusive
`>=` rewinds the poll that defines the window's start.

**Re-check.** The spec's own words are "the count a poll `window` ago would have recorded", which is the state AFTER
that poll. Codex's sequence reproduces. **Applied:** `observed_at > ?`, with the docstring saying why; Codex's boundary
test added; the spec's `test_a_deleted_group_records_its_departures` had set `since` equal to its adds' timestamp and
moves it one second earlier (recorded).

## C2 — the `until=` grammar

**Finding (Codex).** `date.fromisoformat("20260905")` parses on Python 3.11+, so a compact value the docs call malformed
silenced a cliff. **Applied:** a `YYYY-MM-DD` shape check before the parse (a regex rather than Codex's
length-and-dash check; same rule, plainer). Test covers the compact form, an unpadded date, a datetime and a week date.

## Cursor's ratio finding — accepted on the class, measured for the example

**Finding.** `drop < cliff.drop_ratio * before` is a float compare; Cursor's example `0.1 * 30 = 3.0000000000000004`
would miss an exact tenth. **Re-check:** on this interpreter `0.1 * 30` is exactly `3.0`, and so were my first two
examples. A brute-force search over two-decimal ratios and group sizes up to 1000 found 141 exact boundaries the float
compare misses, the first `0.07 * 100 = 7.000000000000001`. The class is real; the examples had to be measured.
**Applied:** `Fraction(drop, before) < Fraction(str(cliff.drop_ratio))`, exact integer arithmetic on the decimal the
operator wrote; the test uses the measured cases and fails on the previous code.

## Cursor's other findings

- The PrometheusRule summary said "lost at least half their members" whatever `dropRatio` is. Applied as a percentage
  (`mulf … 100`), not the raw ratio text Cursor proposed ("lost at least 0.3 of their members"); tested at 0.3 and 0.5.
- `Store.group_detail` did not select `cliff_silence`, so the detail row could disagree with the list row, which
  `API.md` says they must not. Applied, tested.
- EXPLAIN QUERY PLAN, which Cursor could not run: measured here and by Codex — `SEARCH membership_event USING INDEX
  membership_event_by_time`.

## Rejected

Nothing from the first pass was rejected outright; two snippets were reshaped (the regex, the percentage) and the
Cursor example replaced by measured ones.

## Live, on CRC (measured here, since neither sandbox could reach the cluster)

Migration 8 in the pod log; `/api/version` 0.12.0; the Group annotated before the change and re-synced by the
group-sync-operator (annotation preserved across the sync) shows `cliff_silence: until=2026-12-31`; all 66 group rows
carry the key; alert rows carry `silenced`/`silenced_by`; `/metrics` shows kinds only. Repeated after the review fixes
were redeployed (see the PR's comments).
