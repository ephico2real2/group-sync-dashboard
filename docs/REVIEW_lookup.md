# Review record — one lookup over the three kinds (#174, PR #183)

Branch `feat/drilldown`, base `feat/namespaces`. Head reviewed: `76ebaff`. Three reviewers on one brief
(`review_174/brief.md` in the session scratchpad; its ten claims are restated in the table): Grok 4.6
(Cursor, ask mode — source only); Codex (GPT-5.6, xhigh — source, an in-memory API probe, the shipped
renderer executed in Node; no Chromium); OB1 (Claude Fable — a seeded-app Playwright harness with three
servers, 24 measurements; `EXPLAIN QUERY PLAN`; a 10,000-user / 1,000-group scale probe; the mark's
contrast over 30 theme × palette × OS combinations; every fix proved on a copy with thirteen tests, 13
failed on `76ebaff` → 13 passed, and the full UI suite on the copy, 331 passed). OB1 also found that by the
time it probed CRC the cluster had been redeployed to PR #180's head (my sequencing — the per-PR deploy
loop had moved on), so its measurements are on the seeded app; the deployed walk of `76ebaff` earlier in
the day (the lookup for "demo": 6 of 67 groups, 7 of 110 namespaces) stands as the live evidence.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB1 | Decision |
|---|---|---|---|---|---|
| L1 | The position: a page, not a tab; `lookupSearch` a preference; "← search" | CONFIRMED — carried across a cluster switch | CONFIRMED | CONFIRMED (Back/Forward driven; carried) | Carried, as `userSearch` is; what the page then says on an empty cluster is F5 |
| L2 | The Find box rule; typing where nothing filters; IME; Escape | CONFIRMED | REFUTED — `compositionend` only repaints | REFUTED — measured on the real IME path (CDP): no `input` follows `compositionend`, so a committed CJK query never opened the lookup; a query of spaces pushed a history entry | F1 |
| L3 | Matching and marking; the entity case | CONFIRMED (the entity break is real) | REFUTED (Node probe: `a&<mark>amp</mark>;b`) | REFUTED — two breaks: inside an entity, and inside the `<mark>` the previous term inserted ("alice a" painted "ark>aliceark>") | F2 |
| L4 | The doors' counts, lines and refusal copies | REFUTED — the Namespaces door's "outside your tier" for an identity 403 | REFUTED — "have logged in" counts rows, not `logged_in_total`; the same copy point | REFUTED — measured: a manual account counted as a login (CRC has one today: 63 rows, 62 logins); neither refusal copy is reachable; "outside your tier" is wrong in principle (no tier refuses these lists) | F3 |
| L5 | `binding_count` on both branches, every predicate, the index | PLAUSIBLE (no plan run) | CONFIRMED (EXPLAIN: covering index) | CONFIRMED (EXPLAIN in every shape; 2.06 ms at 1,000 groups) | Held; the two-bindings-in-one-namespace row added to the seed (Grok 3) |
| L6 | The also-line: counts only what is held; no fetch on a keystroke | CONFIRMED; would not decide differently | CONFIRMED; agrees with the deviation | CONFIRMED; agrees — and found it counting a **filtered** slice ("1 group" of 2 after the Groups tab's `empty` filter) | Kept; the filtered-slice count is F6 |
| L7 | `wireLookup`'s one navigation per click; keyboard | REFUTED — Enter/Space on a door or a group/namespace hit swallowed | REFUTED, the same | REFUTED, the same, measured on every surface — and pre-existing on Access granted's group drills | F7 |
| L8 | The lookup's fetches, the fingerprint, the self tier | REFUTED — `groups?state=all` written into `data.groups` poisons the Groups tab's first paint | REFUTED, the same | REFUTED, the same, measured (4 rows under "empty", then 2); a self-tier reader's users is a 200/self payload, not `{forbidden}` | F6 |
| L9 | Render order and wiring; the self tier's namespaces | CONFIRMED | CONFIRMED | CONFIRMED (every handler wired once); risk: the self-tier lookup carries no scope statement | F4 |
| L10 | 375 px; `.scroll-x`; the mark in both themes; reduced motion | PLAUSIBLE | PLAUSIBLE | CONFIRMED at 375 and for reduced motion; REFUTED on the mark: 3.40:1 (light) / 3.74:1 (dark) under the sheet's 4.5:1 bar, every wash fails | F8 |

## Findings and decisions

- **F1 — the committed IME composition opens the lookup; whitespace is not a position change** (Codex F2,
  OB1). One `openLookupFor(key)` called from both the input handler and `compositionend`; `trim()` on the
  query. OB1's test drives the real IME path (CDP `Input.imeSetComposition`); Codex's synthetic
  `CompositionEvent`/`InputEvent` test was refuted — dispatched from JS they do not drive Blink's IME.
- **F2 — `hl` marks on the raw text and escapes each fragment** (Grok 1, Codex F3, OB1). OB1's `matchAll`
  over the terms longest-first, one pass, so marks never nest; Grok's range-merge did the same in more code.
- **F3 — the Users door counts logins the way the Users tab does; the one refusal has one sentence** (Grok 2,
  Codex F4, OB1). `logged_in_total`, with the tab's own fallback; both doors say "needs an authenticated
  identity" — Codex's whoami-keyed "outside your tier" variant rejected (no tier refuses these lists; the
  identity-less case paints the API error card before any door exists).
- **F4 — the lookup says when its counts are the reader's own** (OB1). A scope line from `groupsMeta.scope`,
  as every list page has.
- **F5 — the empty state does not claim data a cluster does not have** (OB1). "The data is not empty" only
  when something is held; otherwise "this cluster has nothing to search yet".
- **F6 — the groups rows carry the state they were fetched under** (Grok 5, Codex F5, OB1). OB1's tag on
  `groupsMeta.state` rather than Grok's second `lookupGroups` slot: one tag on the meta that already travels
  with the rows and is already fingerprinted closes both the Groups tab's first paint (Loading, never the
  other slice under this filter's copy) and the also-line's filtered-slice count, which a second slot would
  have left open. Two stubs in `TestGroupSearchEmptyStateHonesty` now say which slice they stub.
- **F7 — every drill activates from the keyboard** (Grok 4, Codex F1, OB1). OB1 removed the `.drill` keydown
  handler outright (every `.drill` is a native button); this branch keeps the identical text #181 committed
  for the same hole (`preventDefault(); el.click()`) so the two branches merge cleanly — the behaviour is the
  same, and OB1's tests pass on it (a door, a group hit, a namespace hit, a user hit, and the pre-existing
  Access granted drill).
- **F8 — the mark keeps the text above the contrast bar** (OB1). No wash; weight is the channel that costs no
  contrast. A visual deviation from the mock's wash, forced by the sheet's own 4.5:1 bar; recorded here for
  the operator.
- **G6 — "open the full list to see them" carries the query to that list's box** (Grok 6, OB1 agrees).
- **Grok 3** — the seed's two-bindings-in-one-namespace row (the SQL was already right).
- **Nits from the deployed walk**: the doors' double chevron (a literal beside `.drill::after`'s); the capture
  script's `relative_to` crash for an output folder outside the repository.

### Rejected / kept
- Grok's `lookupGroups` slot (see F6); Codex's synthetic IME test and whoami-keyed refusal copy (see F1, F3).
- OB1's deletion of the keydown handler (see F7 — behaviourally identical; the text follows #181).
- The Find box on a user's page navigating away — the mock's rule (`drilldown-mock.html`, the
  `view.user || view.ns` branch); kept.
- "Owner matches unmarked" (Grok): a group found through its provider shows no mark; cosmetic, not fixed.

## Not asked
- **10,000 users / 1,000 groups** (OB1 measured): `/users?limit=10000` is 3.1 MB in 292 ms; a tab parked on
  the lookup pays it every poll, as the Users tab already does. Accepted debt, stated. A keystroke at that
  scale costs 10.5 ms to match and 11 ms to paint (twelve rows per kind and "988 more").
- **The e2e walk and screenshot scripts** enumerate `button.tab`; the lookup is not a tab, so neither visits
  it. The deployed walk of this head was done with a probe (`probe_crc_lookup.py`) that types the plan's
  probes; a step for the walk scripts is a follow-up.
- **The CHANGELOG entry's claims** not tested at `76ebaff` — "every hit a drill to its page", "the matched
  substring marked" (correctness, not presence), "twelve per kind", the IME commit, the self-tier lookup,
  the twice-in-one-namespace count — are all tested now.

## Outcome
Pass 1: nine findings across the three reviewers (the seven OB1 named with tests, Grok's G6 and seed row,
plus two nits from the deployed walk), applied from OB1's validated recipe with #181's keyboard text;
thirteen tests fail on `76ebaff` (OB1, 13 failed → 13 passed on its copy); on the merged base `d489bcc` eleven
fail and the two keyboard tests already pass — that merge carries #181's fix for the same handler. Focused on
the fixed tree (the lookup, the three search classes, the IME class, the namespaces class, the count test, the
CSS guards): 434 passed; full non-UI suite 3383 passed, 17 skipped; full UI suite 347 passed. CI on the pushed
head, the deploy and the second pass are recorded below when they land.
