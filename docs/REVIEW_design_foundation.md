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
- OB1's observations, recorded, no change: the header is 223 px tall at 375 px (was 113) and wraps to two rows
  below ~1110 px at desktop — the cost of the two controls, a design decision; `--line` on the card is 1.75:1, a
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
