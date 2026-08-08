# Review — feat/group-search

**Status: OPEN. One pass, Fable, extra-high effort. Scope is this branch alone.**

Two commits on top of `main`, rebased after PR #12 merged.

| commit | what |
|---|---|
| `feat(ui): free-text search on the Groups tab, ANDing every word` | a filter box; `matchesGroupSearch`; focus/caret preservation in `renderFilters`; honest denominator in the header; 11 browser tests |
| `refactor(ui): lift the stylesheet out of index.html into /static/app.css` | 725 lines of CSS moved to a same-origin `<link>`; two tests re-pointed at the file; a guard that no inline `<style>` returns |

Files: `local-development/gsd/static/index.html`, `local-development/gsd/static/app.css`,
`local-development/tests/test_ui.py`, `local-development/tests/test_type_scale.py`,
`local-development/tests/test_accessibility.py`, `docs/namespace-report-design.md`.

Suite: `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`
— baseline on this branch **1049 passed, 1 skipped**; `main` is 1039.

## Claims to test — prefer refutation

- **G1** `matchesGroupSearch` ANDs every whitespace term, is order-independent and case-insensitive, and
  treats the query as literal text — no regex, no globbing. A group name is never interpolated into
  markup by it.
- **G2** The search cannot mislead: while filtering, the header states `N of M` and the empty state says
  the search is hiding rows rather than the data being empty.
- **G3** Focus AND caret survive a filter-bar repaint. `renderFilters` replaces the whole bar's
  `innerHTML` and the page repaints every 30s, so without this the box is unusable. Check the capture
  is by id, that `selectionStart` is read defensively, and that nothing throws inside a render.
- **G4** Filtering issues no network request. The groups endpoint applies no limit, so the whole list is
  already in the browser.
- **G5** A filtered row still drills in, through `navigate()`, landing on a page that can render it.
- **G6** The accessible name of the box is the visible label "Find". The help text is a DESCRIPTION
  behind `aria-describedby` in a `.sr-only` span — `aria-label` must NOT override the name (WCAG 2.5.3
  Label in Name). `.sr-only` must be 1px-clipped, never `display:none`/`visibility:hidden`, or the text
  leaves the accessibility tree.
- **G7** The CSS extraction lost nothing: every custom property and rule `main` had still applies, the
  page has no inline `<style>`, and `/static/app.css` is served (`text/css`, 200).
- **G8** The two stylesheet tests read `app.css`, and the new guard makes a re-inlined block a failure
  rather than an invisible bypass of both.
- **G9** Nothing else regressed: `test_display_timezone.py` slices the page between named landmarks, and
  the extraction moved 725 lines out of that same file.

## Out of scope

- Do not restyle anything, propose a framework, or add a build step. One page, vanilla JS, no build.
- Do not split the JavaScript. That is deliberately deferred: `test_display_timezone.py` slices the page
  between named landmarks, so modules are a test-harness change too, and it wants its own review.
- Do not revisit login capture, the cluster-access gate, or anything merged in PR #12.
- Do not propose server-side search. Measured: the endpoint applies no limit.

## Requirements

Full replacement code in THIS file for every finding, plus a complete test that fails before and passes
after. A file:line, a concrete trigger, and the consequence stated as what a reader would believe that is
false. Comments in this codebase say WHY, not WHAT — a replacement that strips the reasoning is a
regression even when the logic is right. Measure rather than reason: run the suite, drive the page, show
the command and its output. Judge technical debt in the three buckets: DEBT-INTRODUCED / DEBT-ACCEPTED /
DEBT-AVOIDED.

## Fable — findings

Write below.

## Arbitration

The arbiter fills this in.
