# Review — PR #179, the design-system foundation (#152) and the phone-width tab bar (#166)

Adversarial pass, 2026-09-17/18, on the ten-claim brief for `53a366a` (`feat/design-foundation`). Three reviewers:
Codex (gpt-5.6-sol, xhigh; a shell, no Chromium — its sandbox refused the browser's temp profile, so it executed
the page's head and wiring scripts in a mocked DOM and the guards in memory); Grok 4.6 (ask mode, source only);
**OB1 — Fable 5.1 through the Agent tool**, standing in while Cursor's Fable is at its usage limit, with Playwright:
it rendered `ba20df6` and the head in the same browser from the same seed and diffed every element of 13 page
states on 31 computed properties. The branch moved under the second and third reviewers (`19d7b35`, the Grok
pass applied); OB1 read the diff between the two and measured both. Every verdict was re-checked here.

## Verdicts

| Claim | Codex | Grok | OB1 — Fable 5.1, Claude Code Agent | Decision |
|---|---|---|---|---|
| D1 nothing moved; every off-ladder literal noted | CONFIRMED — hunk by hunk; guards in memory, `literal_declaration_count=19` | PLAUSIBLE (no git) — the 19 notes listed | CONFIRMED — old-vs-new diff: only the #166 deltas, the chip tokens and the stated 16→15 px; 71 swept declarations map to their step | — |
| D2 the sheet parses as written | PLAUSIBLE — `nested_comment_openers=0`, `naive_top_level_rule_count=91` | CONFIRMED (source) | CONFIRMED — `cssRules.length` 269 = the file's block count; every token resolves on `<html>` | — |
| D3 `--line` / `--accent-soft` / `--warn` | **REFUTED** — `--accent-soft` on `:root` freezes on `--tab-overview` | **REFUTED** (F1) — same, with the fix | REFUTED at `53a366a`, CONFIRMED at `19d7b35`: Users chip `color(srgb .157 .451 .804)` before, the page's own mix after | accepted; on `body` |
| D4 palette cascade | CONFIRMED — blocks extracted, one-hex drift detected | CONFIRMED — specificity table | CONFIRMED — 30 combinations read from `getComputedStyle(html)` | — |
| D5 the head script | CONFIRMED — executed in a mocked DOM | CONFIRMED; noted a junk URL wiped the stored choice | CONFIRMED — throwing storage, junk stored values, OS-dark + `?mode=light` | junk now falls through to storage |
| D6 a change is never a navigation | CONFIRMED — same `history.state` object | CONFIRMED | CONFIRMED — drill group → user, change, Back: label and position intact; **F3** the URL sheds the query after Back | accepted (F3) |
| D7 the controls survive the repaint | CONFIRMED | CONFIRMED | CONFIRMED — `header_touched_by_render: false`; inert under the idle dialog | — |
| D8 the 92 inline styles preserved | **REFUTED** — a second `class=` at `index.html:3031` | **REFUTED** (F2) — same | REFUTED at `53a366a`, CONFIRMED at `19d7b35` (`margin-top 0px` → `6px`) | accepted; merged + a guard |
| D9 #166 | PLAUSIBLE (no Chromium) | PLAUSIBLE | CONFIRMED — nine tabs at 375: `scrollWidth 375`, bar 335×154; the old sheet's 676/696/five-beyond and the 477 reproduced | — |
| D10 the guards guard | **REFUTED** — the colour guard's `body { MISSED` | CONFIRMED + volunteered the same hole (F3) | **PARTLY REFUTED at HEAD** — `test_comments_do_not_nest` deleted by the Grok-pass slice | accepted; single-level bodies; the guard restored with a self-check |

## Findings and decisions

- **`--accent-soft` frozen on `:root`** (Codex D3, Grok F1, OB1). An unregistered custom property inherits its
  computed value, so a `:root` `color-mix(var(--accent) …)` resolved once against `--tab-overview`; the pressed chip
  on Users wore Overview's blue — measured `color(srgb 0.157 0.451 0.804 / 0.14)` against the page's own mix
  `color(srgb 0.055 0.455 0.565 / 0.14)`. **Applied** (`19d7b35`): the token lives on `body`, where
  `body[data-page]` overrides `--accent`; Grok's test samples both tabs and failed on the `:root` form.
- **A second `class=` attribute** (Codex D8, Grok F2). The bindings search note had an `id` between `class` and
  `style`, which the two-pass promotion did not expect; the parser drops the second attribute, so `mt-3` never
  applied. **Applied**: merged, and a guard forbids a repeated `class` anywhere in the page.
- **The raw-colour guard could not see `body`** (Codex D10, Grok F3). The block finder ran each `:root` match to the
  next *indented* `}`, so a palette block closing at column 0 swallowed the `body {}` rule that followed.
  **Applied**: single-level bodies; a parametrised guard proves a leak in `body`, `.badge` and `header.top` is seen.
- **`test_comments_do_not_nest` deleted** (OB1 F1, refuted at HEAD). The slice that rewrote the colour guard cut the
  file from that function to its end and took the comment guard with it — the guard for the exact parse failure the
  render check had found. **Applied**: restored, with a self-check that poisons the sheet with the first-cut shape.
- **Dark prints dark** (OB1 F2, volunteered, measured under print emulation: `color rgb(255,255,255)` on `#0d0d0d`,
  which Chrome prints as near-white on white). Nothing had ever set `data-theme` before this PR, so the explicit
  path is new exposure. **Applied**: every dark block is `@media screen`; the palettes stay unconditional and print
  in their light form; the test asserts `rgb(11, 11, 11)` / `light` / `#076607` under print and `dark` on screen.
- **The URL sheds `?mode`/`?theme` after one Back** (OB1 F3). `replaceState` rewrote only the current entry; Back
  restored an address that predates the change, and every entry pushed from there inherited the loss. **Applied**: a
  `popstate` listener re-stamps the query from the attributes on `<html>`, keeping the router's state object.
- **The 375 px sweep never saw Reports** (OB1 F4). The `server` fixture has no reporting, so the sweep ran on eight
  tabs; the live bar was nine and Reports was the first off the edge. **Applied**: a test on the reporting fixture —
  nine tabs, `scrollWidth 375`, none beyond the edge.
- **A junk `?mode=` value wiped the stored choice** (Grok, D5 note). **Applied**: an invalid URL value is not a
  choice; the stored one stands, with a test.
- Docstring count 21 → 24 (OB1 F5); the palette-override allow-list no longer names a token no palette sets (Grok).

## Not asked, and what happened to it

- Forced-colours rules, `color-scheme` on the new selects, the print path (before F2: no `@media print` anywhere),
  the `localStorage` keys (only `gsd-mode` / `gsd-palette`), the e2e and screenshot selectors (`#refresh`,
  `button.tab`, `#f-cluster`) — checked by all three; nothing changed.
- OB1's observations, recorded: the header measured 223 px tall at 375 px (was 113) at `9a0e29c`; `2061807`
  brought it to 142.5 by clipping the two labels, and pass 2's F2 (below) replaces that with a 167 px variant
  that keeps them visible; it wraps to two rows below ~1110 px at desktop — the cost of the two controls, a
  design decision; `--line` on the card is 1.75:1, a
  resting border, better than the fallback's ~1.4:1 but under the 3:1 boundary bar; `_declarations` exempts a whole
  line on one `optical:` note.
- Codex: the exact pytest command failed in its sandbox because capture needs a writable temp dir; with `-s` the
  332 static tests passed, by then on `19d7b35`.

## Re-validation

Guards 334 passed (the restored comment guard and its self-check included); the shell UI classes 17 passed (the
print, Back-URL and Reports-tab tests among them); the full `test_ui.py`, guards and citations run on the final
head follows this record. CI green on `53a366a` and `19d7b35`. A second, lighter pass on the fixed head follows.

## Outcome

Ten claims; three refuted at `53a366a` by Codex and Grok in agreement (the frozen wash, the dropped class, the
blind guard), all three closed with tests before OB1 measured the head — where it confirmed nine of ten with
Chromium and found the one regression the fixes had introduced, plus a print defect no brief had asked about.
OB1's element-by-element diff is the evidence the "nothing moved" claim rests on: only the #166 deltas, the chip
tokens and the two stated 16→15 px values differ from main. Eleven tests came out of the pass.

## Pass 2, OB1 — over `9a0e29c`, re-measured on `2061807` and `311f544`

OB1 ran with a shell and Playwright against `git archive` extracts pinned to named commits (the tree moved
twice under it), 90 theme × palette × tab samples for S1, a brace walk and print emulation for S2, a
registration-order trace for S3, and 137,496 computed-style comparisons across 22 page states for S7.
All seven claims CONFIRMED; three findings.

### F1 — the Reports class failed in full runs because the fixture's clock was frozen, not because a ticket expired — accepted; my earlier diagnosis retracted

**Finding.** `test_ui.py`'s `reporting_server` built the report service on `clock=lambda: clock["now"]`
with `clock["now"]` fixed at creation. The service verifies every ticket against that clock while the
dashboard mints with wall time; `ticket.py:95` refuses `issued > current + MAX_CLOCK_SKEW_SECONDS`
(30 s) and `server.py` maps every refusal but expiry to **403**, which `reportFetch` does not remint on
(401 only) — so any ticket minted more than 30 s after the fixture was created painted the narrowed-reader
refusal card where the picker belongs. Measured: 200 at 3 s after creation, 403 at 80 s and 350 s.
CI was red from `faf88b4` through `2061807` for exactly this (15 `TestReportsTab` failures, all
`#report-picker` timeouts), because pass 1's Reports-at-375 test created the fixture ten minutes ahead
of the class.

**Re-check.** Every premise holds on the branch: the frozen `clock`, the 30 s bound, the 403 mapping,
the 401-only remint, `/report/api/snapshot` computing `age_seconds` with the service clock. I retract the
diagnosis in `311f544` ("its report ticket outlived its 300 s TTL"): the fixture's TTL is 120 s and the
bound that bit was the skew; relocating the test hid the symptom (CI green) with a wrong cause and left
the trap armed for any test that requests the fixture 30 s early, or a slow runner.

**Decision.** The fixture's clock is live unless a test pins it (`clock["now"] or now()`); a guard test
reads the snapshot's age twice over the wire 1.2 s apart and requires it to move — it fails against the
frozen fixture ("the report service's clock is frozen: 0 -> 0") and passes with the live one; the
docstring of the relocated test now states the mechanism. No test pinned the clock.

### F2 — the phone header clipped its two labels from sighted readers — accepted

**Finding.** `2061807` took the header from 222.5 px to 142.5 px at 375 px by clipping the labels
(1 × 1 px, in the accessibility tree only): two selects reading "Auto" and "Default" with nothing naming
them on screen. OB1 measured the alternative — each label above its select below 520 px, the pair on one
row with Refresh — at 167 px, `scrollWidth` 375, both selects operable.

**Decision.** The stacked variant. A select that names nothing on its own is the copy rule broken; 24.5 px
buys both labels. The header test is replaced (bound 180 px, both labels visible and above their select,
one row) and fails on `311f544` (`visible: False`).

### F3 — two stale document lines — accepted
The pass-1 line in this record saying the header is 223 px "no change" (rewritten above) and the CHANGELOG
bullet's silence on print-is-light, the Back re-stamp, the junk fallthrough, the hashless boot and the
phone labels (appended).

### Not asked
The e2e and screenshot scripts still select `button.tab` (confirmed static); forced colours and reduced
motion hold under the `@media screen` wrappers; WebKit unmeasured (no browser installed).

### Outcome of pass 2
Three findings, three applied; two tests shown failing before. Focused: `TestReportsTab`,
`TestTheShellAtPhoneWidth`, `TestAppearanceAndColours` — 37 passed on the fixed tree; the full suites —
non-UI 3302 passed, 17 skipped; UI 306 passed. CI on the pushed head is recorded below when it lands.
