# Review record — the Reporting status page (#149 R5/R6, PR #221)

Branch `feat/149-status-page`, base `feat/149-schedules-formats` (PR #220) then `main` once #220 merged.
Head reviewed: `3887a5b` (the branch moved on — `425388a` the findings, a merge of `main`). One seat this
time, OB3 (Opus 5), because the pass was deep where it mattered: a 6,256-triple differential of the cron
calculator against croniter 6.2.4 in four zones (UTC, America/New_York, Europe/London, Australia/Lord_Howe)
plus a minute-by-minute invariant scan of both 2026 New York DST transitions; the late predicate driven
through the endpoint with a frozen clock at seven instants around a fire, with and without a run in
flight; the retention override traced to the prune; the page under Playwright (request counts at the
fetch chokepoint, DOM identity across two automatic refreshes, tier changes mid-session); the window
property-checked over 1,360 instants; eight adversarial schedule shapes fed through the chart, the env
validator and the endpoint. Codex and Grok were not run on this PR: the branch was stacked twice and the
operator's mandate was to finish the programme tonight; the three-seat rule resumes with #222.

## Claims × decision

| # | Claim | OB3 | Re-check / decision |
|---|---|---|---|
| M1 | The cron calculator: parsing, the either-rule, steps, the horizon, DST | REFUTED on DST — wall times compared in one zone with `fold` ignored: a nonexistent 02:30 on the spring-forward day read as a fire; in the repeated hour the next fire came 45 min in the past and the previous in the future | **Accepted (`425388a`)** — `_instants()` names the real UTC instants a wall time has (none in the gap, two in the overlap, as Kubernetes' cron fires); next/prev compare instants. Its differential re-run clean; `test_reporting_cron` +7 (the scan's invariants). The one remaining croniter divergence (`0 0 29 2 *` → croniter 2028-02-29, ours None within 366 days) is the documented horizon. |
| M2 | `describe()` | REFUTED on a field listing every value ("Weekly Sun & Mon & … & Sat") | **Accepted** — read as `*`; a list stops past four dates. |
| M3 | The schedule status: the late predicate; the "effective" retention | REFUTED twice — the 30 min grace sat before the fire, so every healthy schedule read `late` from the instant it fired until its run finished; `ArtifactStore.prune` took `overrides` since the two-tier retention landed and nothing ever passed them, so the retention the page called effective was never applied | **Accepted** — `last < prev and now − prev > 30 min`; `retention_overrides(settings)` is one reading for the prune and the page. Tests at the seven instants and on the prune. |
| M4 | The window tile | CONFIRMED (four windows × 340 instants incl. the DST nights) | Holds. |
| M5 | The history filters, server-side | CONFIRMED (server and UI, requests captured) | Holds. |
| M6 | The page's data flow | PLAUSIBLE — `as_of` in the fingerprint repainted the page every poll (dropping a selection); a reader promoted mid-session saw Loading for a whole cycle | **Accepted** — `as_of` out of the fingerprint; the Reports page's own catch-up applied. |
| M7 | The Reports page after the move | CONFIRMED; the count fetch asked for 50 rows | **Accepted** — `limit=1`; the dead `reportRunsCard` removed. |
| M8 | The chart's schedules JSON; the env | REFUTED twice — a quoted `"false"` suspended the CronJob but reached the page as On with a next fire; `retention: {days: "twelve"}` passed startup and 500'd the status route | **Accepted** — the chart emits the boolean the CronJob decides; the env validated whole at startup (enabled a bool, retention non-negative integers). |
| M9 | 375 px; the badge shapes | CONFIRMED (computed styles at 375/1280) | Holds. |
| M10 | Tests | CONFIRMED | Holds. |
| N1 | CI's chart gate compares against the PR base; stacked, the bump sat in the base | — | Resolved by retargeting to `main` once #220 merged; the next PR in the stack (#222) bumps to 0.39.0. |
| N3/N4/N7/N9/N10 | "3h 60m"; dead code; the operator doc; no tab current on the child page; a filter change racing an in-flight poll | volunteered | **Accepted** — floor; removed; `docs/reports/README.md` describes the page and the four states; the Reports tab is current; every reply names the query it answered. |
| N5 | The walk folder had no README | volunteered | **Accepted** — written. |
| N6 | The R6 deviation was stated in code and CHANGELOG but not told to the issue | volunteered | **Accepted** — posted on #149 with the reasoning. |

## Measured on CRC (deployed `cb74ce1`, `reports/2026-09-20_reporting-status-149/`)

The three cards from live data; the three schedule shapes (`ok` after a fired run, `never` for the
quarterly, `disabled` for the paused); the filters narrowing the total on the service (6 → 4 → 2); Back
to Reports; 375 px clean. The `late`-until-rendered defect OB3 found could not show on that walk
because the walk's own run had finished; the predicate test holds it now.

## What the pass changed in the tooling

A DST-correct cron calculator is a thing to differential-test, not to reason about: the fix is one
function that asks the zone which real instants a wall time has. And a "30 minutes of grace" is only
grace on the side of the fire it was meant for — the test drives the instants on both sides.
