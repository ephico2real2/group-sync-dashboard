# Review record — the hover rail clear of the first cell's ink (#219, PR #226)

Branch `fix/219-hover-rail`, base `main` (`1ef1dc8`). One rule and one test, applied as OB3 proposed in
the review of #204. Three seats on head `67cca41`: Cursor Grok 4.6 (ask mode, from source), Codex GPT-5.6
xhigh (a `git archive` of the head; a Chromium cascade probe with synthetic tables) and OB3 (Opus 5 —
column added when it lands).

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| M1 | The rule's reach and its specificity story | REFUTED — the rule matched the tables it should and moved nothing more than 3 px, but the cascade story was wrong: `:where()` zeroes the `:has()` only, so the rule was `(0,1,1)`, and the KPI page's 18 px won by source order, not by a class beating `(0,0,2)`; the claim's table list was false (Access granted, Logins, Reports and the audit exposure table carry no `.rowlink`) | REFUTED — the same, with a synthetic `.audit-table` carrying a rowlink row measuring 3 px: `.audit-table td` LOST to the rule by order; proposed `td:where(:first-child)` so the rule is `(0,0,1)` and every class-qualified padding wins by construction | **Accepted** both: the second `:where()` (the rule is the generic cell's own specificity), the comment and the CHANGELOG say what the cascade does; a synthetic probe in the test holds an `.audit-table` with a rowlink row at 0 and a plain one at 3. |
| M2 | The audit table | REFUTED — unchanged because the selector does not match (no rowlink), not because `.audit-table td` beats it; the risk pill's ink starts 27 px in on its own | REFUTED, the same (`rowlink: false`, the badge 12 px in past a 4 px resting rail; no hover rail to compose with) | Holds as measured; the preservation test asserts the audit table's own padding, its rail and no hover shadow. |
| M3 | The test | CONFIRMED as written — one table is not enough: it measured a button box, and the issue's glyph is on the user-History table | CONFIRMED; a 375 px sweep of five rowlink tables passed | **Accepted** Grok's tables: the user-History "− left" row (bob, reached by position) ≥ 3 px in; the KPI clusters table at 18 px; the audit table untouched — the two rowlink tests fail on main's stylesheet ("0.0px in", "1.0px in"). |

The walk: `reports/2026-09-20_hover-rail-219/` at `67cca41` — the first cell's ink 3 px in on Groups and
Users with the rail painted beside it.
