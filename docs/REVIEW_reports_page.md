# Review record — the Reports page: a report as a position (#173, PR #218)

Branch `feat/173-reports-page`, base `main`. Head reviewed: `21f8ff1` (the branch moved on under the
pass — `36883bb` the arrival rule found on the deployed page, `cccbf46` the walk's evidence, `f4fc71b`
the findings). Three reviewers on one brief of eight claims (`review_brief_173.md` in the session
scratchpad): Grok 4.6 (Cursor, ask mode — from the source), Codex (GPT-5.6, xhigh — the navigation
functions extracted and executed, `backLabel()` driven with crafted `from` states, the escaping
harness; its Playwright runs were refused by its sandbox), OB3 (Opus 5 — five drive scenarios against the
seeded reporting server, forty click/Enter landings at 1280 and 375 with a simulated sticky header and
the long form after the names popover, the keyboard paths, the aria state; every measurement on a copy).
Every verdict was re-checked on the branch. Line numbers are those of `21f8ff1`.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| M1 | `report` is a position: push/replace, Back/Forward, the pasted link, the tab round-trip | REFUTED — a tab click keeps `report`; the form reopens; the Groups URL carries `&report=` | REFUTED — the same, executed | REFUTED — the same, measured, plus: history Back strands the names dialog over the catalogue; Forward/pasted link did not land (fixed by `36883bb` before its report) | **Accepted (`f4fc71b`)** — `applyPosition()` is the chokepoint: a report exists on the Reports page only (every page-changing `navigate()` site covered), the tab handler drops it explicitly like the other drill-downs, and a report change closes the names dialog. Tests: OB3's `…a_tab_click_closes_it_and_no_other_back_control_names_it`, `…closes_the_names_dialog`; the position test extended. |
| M2 | The back control's label; escaping | REFUTED — with the leak, a group's own back control reads the report's title | REFUTED — the same (`prev.report` tested unconditionally); escaping complete | REFUTED — the same, measured on the group and namespace pages; escaping complete | **Accepted** — the report branches apply on the Reports page only; with the leak gone `prev.report` is truthy only when the previous position was a form. |
| M3 | The landing arithmetic | CONFIRMED (source) | CONFIRMED | CONFIRMED — forty landings inside the viewport; a simulated sticky header counted; the long form re-clicked | Holds. **OB3's N1**: the arrival rule (`36883bb`) made a re-click of the open report a no-op (1960 px on a 740 px viewport) — **accepted**, a click clears the landed mark; its test. |
| M4 | The form unchanged | CONFIRMED | CONFIRMED (function-by-function diff) | CONFIRMED (diffed; one benign change noted — a re-click keeps the run status) | Holds. |
| M5 | No form until a pick | CONFIRMED | PLAUSIBLE (the fallbacks are unreachable with null) | CONFIRMED (every reader of `view.report` listed) | Holds. |
| M6 | The rows: key, count, disabled row, 375 px | CONFIRMED | CONFIRMED | CONFIRMED — measured with rows in the runs table: the catalogue 405 px inside a 301 px wrap, the runs 485 px inside `.scroll-x`, document 375 | Holds. |
| M7 | Accessibility: roles, keys, focus | REFUTED — Back drops focus to `<body>` | REFUTED — the same (keyboard Enter on `#report-back`) | REFUTED — the same, plus `aria-selected="null"` on a fresh catalogue | **Accepted** — after Back to the catalogue focus lands on the row of the form just left; `!!pick`. Grok's N1: the control is a `.back` like every drill-down's, not `.linkish` — **accepted**. Tests: OB3's keyboard and aria tests, mine extended. |
| M8 | The two tests fail on main, pass on the head | PLAUSIBLE (not run) | REFUTED — its sandbox refused Chromium | CONFIRMED, with the correction that they fail on main for the position model (a default pick, no `view.report`), not for the landing or the wrapper | Holds as corrected. |
| N | `.rp-key` 2px is `--space-1`; a stale "scrollIntoView" comment; CHANGELOG line; design README row | N2, N3, N4 | the same three | N2 with a `test_type_scale` guard, N3; N4 refuted as unnecessary | **Accepted** — the token, the guard, the comment, the CHANGELOG entry; the README row marked implemented (harmless, kept). |
| N6 (OB3) | popstate paints after its fetches, so the old form stays under the new URL for the requests' length — pre-existing, every position | — | — | observed, no fix offered | Noted; not a #173 change. |

## Measured

- On CRC, deployed `7748b69` through Argo, walked through the proxy as kubeadmin
  (`reports/2026-09-20_reports-page-173/`): the click landed at 100 px; the same position from a pasted link
  on a fresh load sat at 849 px on an 800 px viewport — the finding behind `36883bb` (`deep : form top: 12`
  after it); 375 px `[12, 740, no horizontal overflow, wrap auto]`; no uncaught error.
- `tests/test_ui.py` 446 pass (441 + OB3's five); `test_type_scale.py` 18; hermetic suite 3710 passed, 15
  skipped. OB3's fixes patch applied clean on `cccbf46` and its six tests fail on `21f8ff1`'s static files
  (five) and on the tip (the re-click one), pass with the fixes.
