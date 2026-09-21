# Review record — the report library tab (#229, PR #233)

Branch `feat/229-report-library`, base `main` at `4f93ad1`. Three seats on head `586e763` (deployed on the lab at
that head and walked, `reports/2026-09-20_report-library/`): Cursor Grok 4.6 (ask mode — no shell, so its C1, C11
and C12 are PLAUSIBLE from source), Codex GPT-5.6 xhigh (a clone of the branch with the base commit; the old
`prune()` extracted and diffed over 108 settings × 37 runs; the page's functions executed; a 200-run listing; a
1 001-run listing) and OB3 (Opus 5 — a 216-settings × 70-runs × 3-instants harness on the old and new prune, 17 mutants against the pin, a Playwright drive with a render counter and cold documents per case; it read the deployed head then the fixed one).

## Claims × decision

| # | Claim | Grok | Codex | OB3 | Decision |
|---|---|---|---|---|---|
| C1 | prune() deletes exactly the old set | PLAUSIBLE (could not run) | CONFIRMED — 3 996 decisions, `doomed_set_differences=0` | CONFIRMED (14 688 standings, 0 differences) | Holds. |
| C2 | `expires_at` is the earliest deletion instant; the pin's mutants | CONFIRMED; mutant `newest_first = id` survives (completion ≠ request invisible) | CONFIRMED — 2 268 + 216 cases, 0 violations; mutant `prune(overrides=None)` survives `TestRetentionStanding` | CONFIRMED (6 552 null cases held; 17 mutants killed by the pin+harness) | **Accepted** Codex's override pin (`test_a_per_schedule_override_drives_the_real_prune_boundary`). Grok's mutant is pinned by the pre-existing `test_retention_ages_a_run_from_completion_not_from_its_request`. |
| C3 | top-K kept whatever its age | CONFIRMED | CONFIRMED (age-expired rank 2/2 survives a 2027 prune) | CONFIRMED | Holds. |
| C4 | the API's plan = prune's settings, once per request | CONFIRMED | CONFIRMED (`retention_calls=1` for 200 rows; kwargs identical) | REFUTED on the consequence: `manual:cap` was emitted for BOTH a run beyond the cap (gone on the next prune) and one under the cap with no age bound (kept) — the page said "held" for a run the next prune deleted | Holds on the mechanics. **Accepted** OB3's F4: `manual:<days>d` for every run within the cap (`manual:0d` = kept indefinitely, the mirror of `age:0d`), `manual:cap` only beyond it; the page's words follow; API.md and §3 updated; three tests. |
| C5 | tier and privacy unchanged | CONFIRMED | CONFIRMED (narrowed viewer 403) | CONFIRMED | Holds. |
| C6 | sections = catalogue × schedules, nothing named | CONFIRMED (not driven) | CONFIRMED (10 → 11 sections with an added schedule) | REFUTED on one clause: a report with two schedules listed its manual runs under both sections (every card and chip twice under one id) | Holds. **Accepted** Grok's most-important finding beside it (the generate ids) and OB3's F2: manual runs belong to the report and sit under its first section only; a test routes a second `groups` schedule and holds one card. |
| C7 | the heading rule | CONFIRMED | CONFIRMED (`Weekly groups`, `Daily groups`, `Namespace access — 1st & 16th, paused`) | CONFIRMED | Holds. |
| C8 | the run position | REFUTED on the copied hash's `cluster` (already in the notes); the rest holds | REFUTED twice: the `cluster` in the hash; a run past the 1 000-row page reads "Run not found" while `/runs/{id}` answers 200 | REFUTED on the click/Enter-opened path: focus stayed on the card behind the overlay (render()'s by-id restore beat the dialog's first-control focus), so Escape did nothing and Tab walked the chips behind the dialog; the cold-URL path held; the `cluster` in the hash is the app's position, not a defect | **Accepted** Codex's beyond-the-page fetch AND OB3's F1 (the card blurs before the repaint; a test opens by click and by Enter and reads `activeElement`, then Escape). **Rejected** Codex's router rewrite (the position is the app's). |
| C9 | the fingerprint and focus | CONFIRMED; the PR's poll test never changed the store (vacuous) | CONFIRMED | CONFIRMED (renders=0 with no store change, 1 with one; focus survives on every drawer control) | **Accepted** Grok's test. |
| C10 | the tab token | CONFIRMED | CONFIRMED (8.738:1 / 7.533:1; 576 guard tests pass) | CONFIRMED (8.74:1 / 7.53:1) | Holds. |
| C11 | 375 px | PLAUSIBLE (not measured) | PLAUSIBLE (the assertions exist; the walk measured `True` for both) | CONFIRMED (Chromium 375×740, rest and drawer) | Holds. |
| C12 | the guards; the E-batch change loosens nothing | CONFIRMED from the regex | REFUTED — `(R\d\|—)` admitted `—` on A1 too | REFUTED at `586e763`, fixed at `b534805` | **Accepted** — `_index_rows()` requires `R\d` on A–D and `—` on E. |
| C13 | fidelity to the spec's blocks | REFUTED — `manual:cap`'s words deviate from the mock, unrecorded (the app is right per §3) | CONFIRMED (four service blocks verbatim; every page hook present) | REFUTED on one silent deviation at `586e763` (the `manual:cap` words), otherwise CONFIRMED | **Accepted** — superseded by F4's vocabulary; the spec's notes record it. |
| C14 | nothing reads the wall clock | CONFIRMED (retention) | REFUTED — `ago()`/`untilShort()` read `Date.now()` (2036: "3653d ago") | CONFIRMED (no wall-clock read in the diff beyond the page's shared `ago()`/`untilShort()`) | **Rejected** Codex's re-basing on `status.as_of`; recorded. |

Grok's not-asked #2 (manual runs under every schedule section) was first marked DEBT-ACCEPTED; OB3 measured the duplicate ids it produces and its F2 closes it. OB3's F3, volunteered: the positioned run's fetch (Codex's fix) was the one library request outside `guard403`, so a 403 painted the API-error panel instead of the refusal card — **Accepted**, guarded like the other three.

## Re-validation

- After the three seats: `test_reporting_server.py` + the guards 1039 passed; `TestLibraryPage` 10; the full suite and the CRC re-walk in the PR's comment.
- The lab: the walk at `586e763` is the branch's evidence; the re-walk after the passes waited on #235 — the S1 branch's migration 19 was on the shared database while this branch's report image read 18 (`/report/readyz` 503 "snapshot schema 19 is newer than this report service understands"), so the merge order became #235 first, then this branch on the merged head.
