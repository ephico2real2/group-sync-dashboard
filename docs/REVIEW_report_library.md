# Review record — the report library tab (#229, PR #233)

Branch `feat/229-report-library`, base `main` at `4f93ad1`. Three seats on head `586e763` (deployed on the lab at
that head and walked, `reports/2026-09-20_report-library/`): Cursor Grok 4.6 (ask mode — no shell, so its C1, C11
and C12 are PLAUSIBLE from source), Codex GPT-5.6 xhigh (a clone of the branch with the base commit; the old
`prune()` extracted and diffed over 108 settings × 37 runs; the page's functions executed; a 200-run listing; a
1 001-run listing) and OB3 (Opus 5 — its column added when it lands).

## Claims × decision

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| C1 | prune() deletes exactly the old set | PLAUSIBLE (could not run) | CONFIRMED — 3 996 decisions, `doomed_set_differences=0` | Holds. |
| C2 | `expires_at` is the earliest deletion instant; the pin's mutants | CONFIRMED; mutant `newest_first = id` survives (completion ≠ request invisible) | CONFIRMED — 2 268 + 216 cases, 0 violations; mutant `prune(overrides=None)` survives `TestRetentionStanding` | **Accepted** Codex's override pin (`test_a_per_schedule_override_drives_the_real_prune_boundary`). Grok's mutant is pinned by the pre-existing `test_retention_ages_a_run_from_completion_not_from_its_request`. |
| C3 | top-K kept whatever its age | CONFIRMED | CONFIRMED (age-expired rank 2/2 survives a 2027 prune) | Holds. |
| C4 | the API's plan = prune's settings, once per request | CONFIRMED | CONFIRMED (`retention_calls=1` for 200 rows; kwargs identical) | Holds. |
| C5 | tier and privacy unchanged | CONFIRMED | CONFIRMED (narrowed viewer 403) | Holds. |
| C6 | sections = catalogue × schedules, nothing named | CONFIRMED (not driven) | CONFIRMED (10 → 11 sections with an added schedule) | Holds. **Accepted** Grok's most-important finding beside it: two schedules on one report minted one `lib-gen-<report>` id — the id is the section's for a scheduled section (`lib-gen-sec-<schedule>`), the report's otherwise; a test holds the ids distinct. |
| C7 | the heading rule | CONFIRMED | CONFIRMED (`Weekly groups`, `Daily groups`, `Namespace access — 1st & 16th, paused`) | Holds. |
| C8 | the run position | REFUTED on the copied hash's `cluster` (already in the notes); the rest holds | REFUTED twice: the `cluster` in the hash; a run past the 1 000-row page reads "Run not found" while `/runs/{id}` answers 200 | **Accepted** the second: the positioned run is fetched by id and joined (`libraryPositionRun()`, `data.libraryRun` in the fingerprint); a test routes the listing without the target. **Rejected** the router rewrite that strips `cluster` from the library's position: the position is the app's (`#page=groups&cluster=…` is the documented shape), a reader on a two-cluster dashboard must land on the right one, and the change touched every page's boot for a cosmetic hash. |
| C9 | the fingerprint and focus | CONFIRMED; the PR's poll test never changed the store (vacuous) | CONFIRMED | **Accepted** Grok's test: the poll's only change is one run's status, the card must repaint and keep focus. |
| C10 | the tab token | CONFIRMED | CONFIRMED (8.738:1 / 7.533:1; 576 guard tests pass) | Holds. |
| C11 | 375 px | PLAUSIBLE (not measured) | PLAUSIBLE (the assertions exist; the walk measured `True` for both) | Holds on the walk. |
| C12 | the guards; the E-batch change loosens nothing | CONFIRMED from the regex | REFUTED — `(R\d\|—)` admitted `—` on A1 too | **Accepted** — `_index_rows()` requires `R\d` on A–D and `—` on E. |
| C13 | fidelity to the spec's blocks | REFUTED — `manual:cap`'s words deviate from the mock, unrecorded (the app is right per §3) | CONFIRMED (four service blocks verbatim; every page hook present) | **Accepted** the note in the spec (the mock's "goes on the next prune" is false with `manual_days` 0). |
| C14 | nothing reads the wall clock | CONFIRMED (retention) | REFUTED — `ago()`/`untilShort()` read `Date.now()` (2036: "3653d ago") | **Rejected** the re-basing on `status.as_of`: every page in the app reads the browser clock for relative words; one page drifting from the rest is the worse defect, and no test asserts a relative word against wall time. Recorded here. |

Grok's not-asked #2 — manual runs of a scheduled report are painted under every schedule section of that report — is the mock's shape and stays (DEBT-ACCEPTED, the lab has one schedule per report).

## Re-validation

- After the pass: `test_reporting_server.py` + the guards 145 passed; `TestLibraryPage` 6; the full suite in the PR's comment.
