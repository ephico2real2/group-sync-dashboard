# Review record — the KPI page (#157, PR #207)

Branch `feat/kpi-page`, base `feat/kpi-module` (PR #206). Head reviewed: `6e6405b`. Three reviewers on
one brief of ten claims (`review_brief_157.md` in the session scratchpad; restated in the table): Grok
4.6 (Cursor, ask mode — no shell; verdicts from the source), Codex (GPT-5.6, xhigh — the payload, the
config loader and the store driven; Chromium could not launch in its sandbox), OB3 (Opus 5 — rendered
the page in pixels at four widths, fuzzed the fill/badge/rule agreement over 400 payloads, drove the
sparkline's window edge, both directions of the host-vs-selected-cluster mismatch on the scoped
server, and 19 pages × 3 widths base-vs-head from one store). Every verdict was re-checked on the
branch before a decision. Line numbers are those of `6e6405b` and are not maintained.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| P1 | Fidelity to the mock; every figure from a payload | REFUTED — "poll 60s" is a constant; the report's second sub-line | REFUTED — the same constant | REFUTED — the throttled track's SCALE (the mock draws the 1 % mark at 20 % of the track; on a 0–100 % track it sat 3 px in and 1.10 % vs 0.05 % filled within half a pixel of each other, measured at 1280) and the Bindings tile dropping the `unmanaged` tier (3 of 4 on the seed) | **Accepted, both OB3 findings** (**F1** `KPI_THROTTLE_SCALE = 5`, the mark and the fill drawn against a track to 5×; **F2** `posture` keeps all five tiers and the tile sums every non-built-in one). The cadence figure: kept — it is the page's own refresh, which the constant governs; reworded "refresh 60s" (Codex's payload-driven cadence rejected: a different design). "preempted 29×" is dropped, correctly: a one-off kube-events count from #97, no field carries it |
| P2 | Thresholds and state, decided once | CONFIRMED | CONFIRMED | REFUTED on "once" — two comparisons, split on a null threshold (`50 > null` is true) | **F3, accepted.** One `over(pct, limit)` per meter in `kpiComponent`, passed into `kpiMeter`; 400-payload fuzz 0 disagreements before, and the null-threshold input now agrees |
| P3 | Colour never the only channel; contrast | CONFIRMED | CONFIRMED (`--tab-kpi` 6.39:1 light / 8.10:1 dark; button text 6.56 / 7.26 on every palette; rails 3.00 / 4.50) | CONFIRMED; **N1** the over-threshold fill on its own track: 2.70:1 light — the token audit holds `--status-warning` at 3:1 on surface-1 only | **N1 accepted.** The fill wears `--warn` (the text-grade amber `td.num.warn` already uses on the page): 4.40 light, 5.87 dark; a test computes the composited ratio |
| P4 | Motion: reduced-motion, pulse-on-change, one timer | CONFIRMED | CONFIRMED; **volunteered:** `data.kpi` was missing from the repaint fingerprint — a poll whose only change was a KPI never repainted | CONFIRMED (timers wrapped, three round trips) | **Codex's finding accepted** — the fingerprint carries `data.kpi`; `test_a_kpi_only_auto_refresh_repaints` |
| P5 | Phone width | PLAUSIBLE (no pixels) | PLAUSIBLE (no browser) | CONFIRMED (375: 375 ≤ 375; `.scroll-x` 623 > 333; last column reachable; 393/768/1280 likewise) | Holds |
| P6 | The payload additions; every day present | REFUTED — a day both clusters have rows for was DROPPED (Map last-wins), not summed | CONFIRMED (plans indexed; baseline excluded; zero-filled) | REFUTED — the rolling `now − 30d` start put a partial day before the thirty the page draws (7 joiners on the figures, off the line); and the line's days came from the browser's clock, not the payload's as-of | **Both accepted.** Buckets summed per day across clusters (**F4**); the activity window is the thirty whole UTC days ending on `as_of`, from the first day's midnight, and `kpiSpark` ends on the payload's day (**F5**); the scalars stay rolling 30 × 24 h and API.md says the two differ by that day |
| P7 | The doors | CONFIRMED | REFUTED — `javascript:` / `data:` values reached the href verbatim | REFUTED — the same, plus a scheme-less host resolving into the dashboard's own origin (a dead button) | **F6, accepted.** `_door_url` refuses anything but an absolute `http(s)://` base without query or fragment at load (Codex's shape; OB3's warn-and-unset alternative not taken — the thresholds refuse the render too, one rule) |
| P8 | Tier and scope | REFUTED — the fetch keyed on the host, the paint on the SELECTED cluster: a host administrator with a narrowed remote selected was refused | CONFIRMED | REFUTED — the same, both directions (a self reader with a wide remote selected: Loading… for ever), and a `{forbidden:true}` marker reaching `kpiPage()` threw | **F7, accepted** (found by Grok and OB3 independently; the Reports tab's rule): the paint reads `narrowedOnHost()`, `kpiPage()` renders the refusal on `k.forbidden`; OB3's three-way test |
| P9 | Behaviour preservation | PLAUSIBLE | PLAUSIBLE (payload hash identical on the pre-existing keys; helm render differs by the seven keys) | CONFIRMED (19 pages × 3 widths byte-identical; the tab bar +1) | Holds |
| P10 | Tests | PLAUSIBLE | PLAUSIBLE (`TestPageSettings` 2 failed on the base, 2 passed on the head; 3534 passed) | CONFIRMED | Holds. `TestLookup::test_the_also_line…` fails on `main` on this machine and passes in CI; not this PR's (nobody could tell why offline) |

## Volunteered, besides the above

- **Grok N1** — the promotion catch-up: `refresh()` chose `/api/kpi` from the previous cycle's identity; a
  reader promoted mid-session sat on "Loading…" for a poll interval. Accepted, the Reports block's shape.
- **Grok N2 / OB3 N2, Codex** — three comments and a docstring misdescribed the code ("decided HERE and
  only here"; "returns the html and the state"; `posture()`'s "no arithmetic"). Reworded.
- **Grok N4** — `report_run` had no cluster-leading index, so `daily_activity`'s reports bucket and
  `report_volume` spanned every cluster's runs. Accepted: migration 17 `(cluster_id, requested_at)`;
  `test_the_activity_buckets_seek_their_indexes` pins all five plans to a seek.
- **Codex N3** — "entirely from `/api/kpi`" over-stated: the page sums the per-cluster figures. Reworded.

## Rejected

- Codex's payload-driven cadence for the heartbeat's "refresh 60s" (the constant IS the page's refresh).
- OB3's warn-and-unset for a bad door URL (refused at load instead, the thresholds' rule).

## Validation

`tests/test_kpi.py` 41; `tests/test_ui.py#TestKpiPage` 16 (every accepted finding with a fail-before/
pass-after test — the sparkline merge, the host headline and the fingerprint were re-run against the
previous page and failed). Full hermetic suite 3539 passed, 13 skipped.
