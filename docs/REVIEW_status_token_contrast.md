# Review record — the status text tokens on zebra and hovered rows (#204, PR #217)

Branch `fix/204-status-token-contrast`, base `main`. Head reviewed: `ca65496` (the branch moved on under
the pass — `1a138c6` Codex's and Grok's findings, `1a18f64` OB3's). Three reviewers on one brief of
seven claims (`review_brief_204.md` in the session scratchpad): Grok 4.6 (Cursor, ask mode — from the
stylesheet and the test, no shell), Codex (GPT-5.6, xhigh — an independent WCAG 2.1 implementation over
all 30 cells, HSL hue per pair, the test run against main's sheet, every `var(--status-*)` use grepped
and the chip's stacked surfaces measured), OB3 (Opus 5 — the seeded dashboard driven in Chromium for all
ten variants, the row hovered, the **painted pixel** under the text read from a screenshot). Every
verdict was re-measured with the fixture's own functions before a decision.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| M1 | every cell ≥ 4.5 on card, zebra, hover | **REFUTED — the dark sheet's `--series-1-wash` is 14 %, the fixture composes 10 % for both themes**; the real dark hover measures 4.29–4.39 in four variants | CONFIRMED on the fixture's model (min 4.5051) | REFUTED on the pixel: 4.30–4.40 in dark, dark/deuter, dark/protan, dark/trit, and **light deuter/protan good 4.494 — Chromium truncates the blend** | **Both accepted.** The fixture reads each theme's wash percentage and composes the row surfaces rounded *away* from the text (floor light, ceil dark — the worst case under either rounding). Every token re-solved against that: the dark trio 2–13 % toward white, light deuter/protan good and trit warn one 8-bit step. |
| M2 | hue preserved, ≤ 9 % | REFUTED on the letter (light good's R/B 10 %) | CONFIRMED (max 0.26°) | CONFIRMED (every value the minimal 0.1 % step, hue ≤ 0.3°) | Held; the comment says 1–10 %. |
| M3 | nothing else moved | CONFIRMED | CONFIRMED | CONFIRMED (twins identical) | Holds. |
| M4 | 31 fail on main's sheet, 487 pass | CONFIRMED (reconstructed) | CONFIRMED (executed) | CONFIRMED — and the count was **nine** variants (light/contrast through `--warn`), floor **3.96**, not eight / 4.01 | **Accepted** — the test comment and the CHANGELOG say nine / 3.96 / 31 pairs; `ca65496`'s message stands corrected on the PR. |
| M5 | `--warn` ≥ 15° from critical | REFUTED — light deuter/protan/trit 0.5° | REFUTED — 0.474° | — | **Accepted.** Pre-existing: the CVD palettes inherited the default amber against their vermilion critical. Each carries its own warning hue: the Okabe-Ito orange darkened (`#906300`) for light deuter/protan, the palette's pink darkened (`#94597a`) for light trit; in dark the blocks' own `#e69f00` / `#cc79a7`. Held by a test at **14°** — the reference palette's own vermilion/orange separation; the brief's 15° was an unmeasured number. The unconditional palette block matches dark roots too (Codex): the dark twins restate `--warn` and the fixture models the leak. |
| M6 | the only text uses | REFUTED — `.kpi-page .chip.crit` on the chip's translucent zebra wash inside a hoverable row, 4.29 | REFUTED — the same, 4.06–4.31 in eight variants | — | **Accepted** — opaque `--surface-1` under the chip's text; a test holds it there. |
| M7 | dark good / contrast pairs unchanged | CONFIRMED | CONFIRMED | CONFIRMED | Held at `ca65496`; the dark default good moves with M1. |
| N | stale ratio comments; no CHANGELOG entry | both | both | (C9) the same, with the measured replacements | **Accepted** — five comments rewritten from measurement; the entry under Unreleased. Codex's record-guard test (pinning comment strings) rejected as more than the fix needs. |
| N2 (OB3) | the first cell's glyphs paint under the 3px inset hover rail (measured pixels), a one-rule fix and a failing test | — | — | volunteered | **Routed to #219** — a 3px shift of every rowlink table's first column at rest is a design call outside #204; belongs with #153. |

## Measured

- `tests/test_accessibility.py`: 507 pass on the head; 31 fail with main's stylesheet under the
  extended guard; 21 fail with `ca65496`'s (8 dark hover, 10 chip, 3 hue); 11 fail with `1a138c6`'s
  (the truncation cells). Hermetic suite 3788 passed, 15 skipped. CI green on every head.
- OB3's painted-pixel harness (its scratch `ob3-204/ui_drive_test.py`): after its re-solve every hovered
  status cell 4.50–4.59 in dark, 4.50–4.54 in light, zebra 4.88–4.96, nothing below 4.5 — the model
  this record's fixture now encodes.

## What the pass changed in the tooling

The accessibility fixture now reads the hover wash per theme from the stylesheet instead of assuming
it, composes the row surfaces as the compositor rounds them, and models a light palette block's leak
into dark roots — three ways the previous model was kinder than the browser, each found by a different
reviewer.
