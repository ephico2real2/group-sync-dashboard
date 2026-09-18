# Review record — Cluster Overview relayout (#172, PR #180)

Branch `feat/overview-relayout`, base `feat/design-foundation`. Head reviewed: `759cd7d`. Three
reviewers on one brief (`review_172/brief.md` in the session scratchpad; its ten claims are restated in
the table): Grok 4.6 (Cursor, ask mode — no shell; verdicts from the source), OB1 (Claude Fable — drove
the app at 2/6/14/40 clusters with Playwright, diffed the DOM base-vs-head from one seed, applied every
fix to a copy and proved 13 tests fail-before/pass-after), Codex (GPT-5.6, xhigh — source and the
contract; its sandbox could not launch Chromium). Every verdict was re-checked on the branch before a
decision. Line numbers are those of `759cd7d` and are not maintained.

## Claims × reviewers × decision

| # | Claim | Grok | OB1 | Codex | Re-check / decision |
|---|---|---|---|---|---|
| O1 | Two positions, one key: `#page=overview` is the fleet, `&cluster=` the scoped view; boot stamps no default on the Overview; Back/labels/pasted links | CONFIRMED | CONFIRMED (a full drive of the stack, Forward included) | PLAUSIBLE | Holds; OB1's drive is the artefact. The stale-payload hole on the fleet → cluster transition is F5 |
| O2 | Density from the served count (3/8/24); worst-first past three; request budget 7/15/3/3 | CONFIRMED | CONFIRMED, one sub-claim refuted: compact tiles hid the CR and policy figures | PLAUSIBLE | Measured 7/15/3/3 by OB1. The plan says the compact tiles carry those two figures; the mock's CSS hid them — F12 |
| O3 | Alerts paged eight per page, worst-first, silenced last, the page is view state | CONFIRMED | CONFIRMED (20 alerts at 14 clusters driven) | PLAUSIBLE | Holds. The kinds chips drew a blank glyph — F13 |
| O4 | Status carries its consequence in the right vocabulary | REFUTED — `ok` is on every healthy row, which the tests require | REFUTED for `unknown` | CONFIRMED | `ok` on every healthy row is the tests' contract (kept). Two real holes: `unknown` blamed the cluster (F1), the dense rows read `unknown` for `auth_failed` (F2) |
| O5 | The contract's cards, words and columns survive in both views | CONFIRMED | CONFIRMED, caveat: the policy count sat inside the `h3` | CONFIRMED | Holds; the count is a sibling span now (with F14) |
| O6 | The Policy tab's strip is the same card; the absent path | REFUTED — "likely dropped a per-cluster absent note" | CONFIRMED | CONFIRMED | Grok's refutation is refuted: `311f544`'s `configHealth` returned `""` for `present: false` too (line 3833). The fleet ADDS an absent note, and that note was wrong for an unpolled cluster — F3 |
| O7 | The tile-to-block string rewrite is well-formed | CONFIRMED | markup CONFIRMED, the scoped view's heading button inert and the tile's styles lost | CONFIRMED | F4 |
| O8 | 375 px on every tier and the scoped view | PLAUSIBLE | CONFIRMED (`scrollWidth` 375 at 2/6/14/40 and scoped) | PLAUSIBLE | Holds |
| O9 | The fleet fixture leaks nothing; the waits are not racy | CONFIRMED | CONFIRMED | PLAUSIBLE | Holds. A false comment in one test ("upper-cased by CSS") corrected |
| O10 | Nothing else moved; the Policy tab differs by the consequence line only | REFUTED — six differences | REFUTED — six differences, seven other tabs byte-identical | REFUTED | The claim was wrong. The Policy tab's card is the pre-#172 card plus the line now — F14 |

## Findings

Numbered by the accepted list; each names who found it, the re-check, and the test that fails on
`759cd7d` (all fourteen were run against that head: 17 failed — the fourteen, the Policy-tab test and the
density test at 2 and 14 clusters, whose assertion changed with F12 — and pass on the fixed tree with the
PR's own classes, 74 passed).

### F1 — `unknown` blamed the cluster (OB1) — accepted
`api.enrich()` calls `compute_state()` without `reachable`, so a CR is never `unknown` for its cluster
being down: it has never synced, or its schedule is unusable (`state.py:104–108`, interval None). The
row's line read "never observed a sync, or the cluster is unreachable" — false on both counts for a CR
synced three minutes ago with `schedule "not a cron"` (OB1's seed). Now `syncMeans(r)` picks the schedule
sentence when `schedule_valid === false` and a last sync exists, and the never-synced sentence otherwise.

### F2 — dense rows read `unknown` for every unreachable cluster (Grok, OB1) — accepted
`denseRow` called `badge("critical")`; `badge()` maps any word outside `STATES` to `unknown`. One
`reachBadge(c)` for the tile, the dense row and the opened cluster, so the three cannot disagree.

### F3 — the fleet's absent note was said of clusters that reported nothing (OB1) — accepted
`store.operator_configs()` returns `present: bool(...)`, so a never-polled or failed-poll cluster reads
`present: false` and the fleet card said "prod-east reports these CRDs absent" of an `auth_failed`
cluster. The caller passes `polled` (status `ok`) and the note requires it. The store's two-valued
`present` is noted as the root; an API-layer fix is a separate change.

### F4 — the opened cluster kept an inert heading button and lost the tile's styles (Grok, OB1) — accepted
`clusterDetail` string-replaced the tile's tags; the `<button class="tile-open">` stayed with no handler
(`.tile[data-cluster]` no longer matched) and every `.tile`-scoped rule was lost — OB1 measured `.api`
inline in the UI face, `.poll` at 14 px, `.cn` weight 400. `clusterTile(c, density, detail)` renders a
plain block with a plain heading; the CSS names `.tile-detail` beside `.tile`.

### F5 — a cluster change from the fleet dropped nothing (OB1; found tracing Grok's F5 snippet) — accepted
`applyPosition` cleared the scoped payloads only when `view.cluster` was non-null; the fleet leaves it
null, so a tile opened after a scoped visit cleared nothing and the next tab painted crc-local's four
groups under " - prod-east" (OB1 measured it). The guard is `pos.cluster !== view.cluster` now; at boot
every payload is already null, so the extra clear is a no-op.

### F6 — the first paint of the fleet claimed "shown per cluster" of a fleet of two (OB1) — accepted
The tab handler paints before it fetches and `overviewPage` treated `!data.fleet` as the past-eight case.
Three answers now: past the medium tier the per-cluster note; below it "Loading…" until the payload
lands; then the tables.

### F7 — `data.fleet` rendered, not fingerprinted (Grok, OB1, Codex) — accepted
The fingerprint's own comment forbids omitting a rendered payload; an automatic refresh whose only change
was a CR's schedule repainted nothing (OB1 measured `*/30` on screen against `*/20` on the wire). Added.
Grok's test mutated `data.fleet` before calling the refresh that refetches it and could not fail; OB1's
changes the store and waits for the cell.

### F8 — a failed per-cluster fetch folded into "all syncing" (OB1) — accepted
The fleet stage's `.catch(() => null)` and `(f.groupsyncs || [])` left a 500 for prod-east's CRs out of
the table and out of the count. The clusters whose request failed are named under the table.

### F9 — a refused reader ran the fleet stage every poll (OB1) — accepted
Behind the refusal card a narrowed reader's browser fetched two payloads per cluster per poll — N
designed 403s a minute on `/metrics` for nothing shown. Skipped for `narrowedFor(whoami)`; per cluster,
the policy payload is asked for only where whoami says the reader is wide there. The self-tier Overview
itself is a contract question routed to #182.

### F10 — a link to a retired cluster was the generic error card, with no tab bar (Grok, OB1, Codex) — accepted
`require_cluster` 404s a retired or unknown id; the batch rejected before `render()` ran, so the page's
own note ("No cluster by that id is configured. A removed cluster's link is a detour, not a dead end")
was unreachable and the filter bar never painted. On the scoped Overview only, the two cluster-level
fetches resolve to null on 404. Codex also wrapped a CR detail's events fetch — rejected: a deleted CR's
404 is the "may have been deleted" card by design.

### F11 — a superseded refresh wrote `data.fleet` (OB1) — accepted
The write sat before the `superseded()` check, against the codebase's own rule. Moved after it.

### F12 — compact tiles hid the CR and policy figures (OB1, from Grok's O2 note) — accepted, a design decision
Compact (9–24 clusters) has no fleet tables, so the tile was the only place those two figures could
appear, and the mock's CSS hid them. Only Empty is dropped at compact now; the density test's assertion
changed with it.

### F13 — the kinds summary drew blank-glyph badges (OB1) — accepted
A `.badge` with no state class rendered a 9 px transparent square. The kinds are `.kind` chips.

### F14 — the Policy tab changed by more than the consequence line (Codex, OB1's O10) — accepted
The shared card had moved the failing row first and added the count, the attention wash and the state
cell to the Policy tab. `configsCard(entries, { plain })`: the Policy tab passes `plain`, and its card is
the pre-#172 card plus the line; the Overview's two forms keep the count — as a sibling span beside the
heading, the GroupSync card's arrangement, not inside the `h3` (OB1's O5 caveat).

### F15 — a tile did not paint before it fetched (Grok) — accepted, after F5
The tab handler paints the destination first (2–4 ms against a 271–337 ms round trip, benchmark §6a); a
tile did `navigate(); refresh()` and left the dimmed fleet on screen for the length of the fetch. Applied
to the tile and the dense row only, and only because F5 makes the first paint honest — the tile, its
alerts and "Loading…". The cluster selector keeps its dim-then-swap: it is the shell's control on every
tab and no measurement of it was taken here.

### Rejected and routed
- **Codex F3 / X3 — the self-tier Overview.** The tab-feature contract (PR #168) says cluster cards and
  GroupSync CRs are every-tier; `docs/ACCESS_CONTROL.md` says the Overview is for administrators only;
  the API already projects every fleet payload at the self tier; a visibility-spec test pins the refusal.
  A tier-policy decision between two documents, not a relayout defect — routed to #182 with both citations.
- **Codex F1's `applyPosition` rewrite** — the one-line guard change (F5) does the same with nothing else
  moved.
- **Grok's O6 refutation** — refuted by `311f544:3833` (see the table).
- **Grok's F4 test** — could not fail (see F7).

## Not asked
- The e2e walk and screenshot scripts select `button.tab` and any `h2`; the fleet has an `h2` at every
  tier. Unchanged (all three).
- OB1: `test_a_pasted_groupsync_link…` expects "← overview" on a CR detail whose parent is now the scoped
  view; "← crc-local" would name the destination. Truthful as it is; left.
- OB1: the store's two-valued `present` (F3's root) is an API-layer change if wanted.
- Codex: a 5,000-row measurement is on the #167 record, not this one.

## Outcome
Pass 1: fifteen findings accepted across the three reviewers (Grok five, OB1 thirteen, Codex four, with
the overlaps noted), one routed (#182), two rejected. Fourteen tests in `TestOverviewReview` plus the
Policy-tab test, each shown failing on `759cd7d`; the CSS guards (334) and the PR's own classes (74) pass
on the fixed tree; the fleet at 2/6/14/40, the scoped view and the Policy tab were rendered and read.
Full suites on the fixed tree: non-UI 3303 passed, 17 skipped; UI 344 passed. CI on the pushed head and the second pass are recorded below when they land.

## Pass 2 — over `c806112`

Grok (source only) and Codex (source and executed snippets; no Chromium) on the fixed head; OB1's second
pass was lost to the session limit mid-measurement and is replaced by one confirmation run on the final
head. Every verdict re-checked on the branch.

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| P1 | The retired-cluster detour: only the scoped Overview absorbs the 404; the bar renders | CONFIRMED, one leftover: the selector shows "all clusters" beside the detour | REFUTED on the same selector | V1 — the id gets its own selected option, "— not configured" |
| P2 | `reachBadge()` at all three sites | CONFIRMED | CONFIRMED (executed: null → unknown/no data yet, ok, auth_failed/timeout → critical) | — |
| P3 | `syncMeans()` | PLAUSIBLE — never-synced + invalid schedule takes the never-synced sentence | REFUTED, the same case | V2 — an unusable schedule is the cause with or without a last sync; the sentence no longer assumes one |
| P4 | The absent note needs a poll | CONFIRMED | CONFIRMED | — |
| P5 | The opened cluster's markup and styles | REFUTED — the rails (`.tile.bad`/`.warnrail`) were not paired | REFUTED, the same | V3 — paired |
| P6 | The chokepoint clears on fleet → cluster and nothing on cluster → fleet | CONFIRMED | CONFIRMED | — |
| P7 | Paint-first on a tile; `navSeq` | CONFIRMED | CONFIRMED | — |
| P8 | The three answers; a widened reader is not stuck on Loading | CONFIRMED | CONFIRMED | — |
| P9 | The fleet stage's guards; `undefined` vs `null` | CONFIRMED | CONFIRMED (`JSON.stringify([undefined]) === JSON.stringify([null])`) | — |
| P10 | The Policy tab's plain card is the old card plus the line | REFUTED — the heading was wrapped in `.row-wrap` even when plain, so `.card > h3::before` (the accent rail) no longer matched | REFUTED, the same | V4 — the plain heading is a direct child again, and the rail selector also names `.row-wrap > h2/h3`, so the Overview's counted headings keep their rail too |
| P11 | Compact keeps the two figures | CONFIRMED | CONFIRMED | Reversed on the operator's ruling (2026-09-18): the mock's visuals — compact hides the three extra figures, as the Overview mock's CSS does; the scoped view carries them all. OB1's F12 offered as a suggestion, declined |
| P12 | The kinds chips' contrast | CONFIRMED (`--border` is the badge's own faint edge) | REFUTED — `--border` measures 1.24:1 / 1.34:1 on the surfaces | Rejected: `.badge` uses the same 1 px `--border` edge and the chip is the badge's shape; a heavier chip edge than the badges' would be the inconsistency. `--border`'s contrast is a design-system token question, already recorded on #152's review |
| P13 | The fixtures and the two ordering-sensitive tests | CONFIRMED | CONFIRMED | — |

**Volunteered and accepted — Codex: the e2e walk picked "all clusters" as the second cluster.**
`e2e_extra.py` read option labels and compared them to the select's value; with the fleet option first
(`value=""`, label "all clusters") the walk's second-cluster evidence stayed on the fleet. A
`next_configured_cluster(options, current)` helper in `e2e_capture.py` skips empty-valued options; the
walk selects by value and waits for `view.cluster`; a unit test loads the module by path.

**Tests.** Six new (the rail, the selector, the accent rail on the Overview's counted headings, the Policy
tab's direct-child heading, the never-synced invalid schedule, the walk's cluster pick), each failing on
`c806112` (6 failed) and passing on the fixed tree; the density test's assertion is back to the mock's
tiers and the compact-figures test is gone. Focused: the review classes, the Policy tab, the walk test and
the CSS guards — 391 passed; full UI suite 348 passed; full non-UI suite 3304 passed, 17 skipped. CI on the
pushed head and OB1's confirmation run are recorded below when they land.

## Pass 3 — OB1's confirmation over `a78cb79`

One reviewer, the final head (pass 2's `602eaf7` merged with the foundation's `a668d51`), eight claims
(`review_172/pass3/brief.md`): a Playwright drive over four seeded fleets (3, 6, 14 and 40 clusters, a retired
cluster, an unusable schedule, restrictions on), twenty state snapshots across the poll, both themes × five
palettes, the full UI suite once (349 passed), every fix proved on a copy; OB1 first proved which `gsd` its
interpreter imported (the venv's editable install points at the main repo; `python -m pytest` from the
worktree wins). Pass 2's own OB1 run was lost to the session limit; this is its replacement.

| # | Claim | OB1 | Decision |
|---|---|---|---|
| C1 | The opened cluster keeps the tile's rail — colour and width, every theme × palette | CONFIRMED — 20 combinations, tile = opened block to the token's rgb, 0 mismatches (the tile read after its 160 ms transition, which the first read caught mid-way) | — |
| C2 | The counted headings keep the accent rail; no other `.row-wrap` heading gained one | CONFIRMED for the counted headings; REFUTED on the rest — every fleet tile's name wears it (3 px, 16 px inboard of a bad tile's own status rail) while its opened form does not; the CR detail's heading too | A |
| C3 | An unusable schedule's sentence with and without a last sync; no row says "the last there will be" | CONFIRMED — six rows measured against the API's `state` and `schedule_valid` | — |
| C4 | A retired id in the selector, pasted twice in a row; Back to the fleet | CONFIRMED — one "not configured" option each time, Back clean; on every other tab (`#page=groups&cluster=nope`) the generic error card with no bar, as before | Recorded — F10's scope |
| C5 | The density tiers and the mock's `k-extra` rule | CONFIRMED at 3, 6, 14 and 40 (`k-empty` nowhere in the DOM or the sources) | — |
| C6 | The walk's second-cluster pick and its wait | CONFIRMED on the pick; REFUTED on the wait — a TypeError at `e2e_extra.py:55` (positional `arg`), and the wait itself returns before the paint | B, C |
| C7 | The merge of the foundation moved nothing of #172's rendering; 375 px; the fixture's clock | CONFIRMED — header 140 px, the labels above their selects; `git merge-tree` conflicts in the CHANGELOG only, `index.html` absent from the diff; 349 passed | — |
| C8 | Two invocations and the poll: twenty snapshots | CONFIRMED — the rail, Back, the selector's value, the scoped rows all agree at every step; zero page errors | — |

### A — every tile's name wore the accent rail (OB1) — accepted
Pass 2 widened the accent-rail selector to `.card > .row-wrap > h2::before` for the counted headings
("GroupSync CRs 6", the Policy heading beside its count), and a tile is a `.card` whose name sits in a
`.row-wrap`: measured 3 px on every tile at full density, 19 px from the tile's edge, 16 px inboard of a bad
tile's 3 px status rail — two rails — while the same heading in the opened cluster (`.tile-detail`, not a
card) measures `auto`. The mock's tile (`cluster-overview-mock.html`) is a `<button class="tile">` with the
status rail on its own edge and no leading rule, and the pre-#172 cluster card had none: the rail was a side
effect of pass 2's selector, not a decision. `.card:not(.tile) > .row-wrap > h2::before` — the counted
headings keep theirs; the tile and its opened form agree. Test
`test_a_tile_heading_carries_no_accent_rail_like_its_opened_form`: `('3px', 'auto')` on `a78cb79`, passes
after. The CR detail's heading (`row-wrap mt-5`) also gained the rail in pass 2 and keeps it — the group
and user pages' headings wear it, so it is now consistent with its siblings.

### B — the walk's cluster switch raised a TypeError (OB1) — accepted
Pass 2 (`602eaf7`) wrote `page.wait_for_function("(id) => view.cluster === id", cluster_id)` in
`e2e_extra.py`; the installed Playwright's signature is `(expression, *, arg=None, timeout=None,
polling=None)`, so the walk would have raised "too many positional arguments" the moment it reached its
second cluster — invisible to `bash -n`, an AST parse and the by-path import of `next_configured_cluster`,
which is all pass 2 ran. `arg=cluster_id`. The guard
`test_every_page_call_in_the_walk_binds_to_the_installed_playwright_api` binds every `page.<method>(...)`
call in both walk scripts, by shape, against the installed `Page` signature — the walk only ever runs against
a deployed cluster, so this is the one place a wrong call shape is caught before it does; on `a78cb79` it
fails naming exactly `e2e_extra.py:55`.

### C — the walk waited on the position, not the paint (OB1) — accepted
`view.cluster` changes the instant the selector fires, and `wait_for_load_state("networkidle")` resolves at
once when the document has already reached that state. Measured with the picked cluster's `/groupsyncs` held
1.5 s: the position true at 22 ms, networkidle at 24 ms with the previous cluster's heading on screen and
`#main` dimmed, still so after the script's 900 ms sleep (941 ms), the paint at 1523 ms. A route's round trip
is 271–337 ms per request with five in flight, so the sleep usually covered it — a race whose evidence
heading and screenshot would be the wrong cluster's the day it lost. `wait_for_cluster_paint(page,
cluster_id)` in `e2e_capture.py` waits for the position, the dim gone and a `.tile-detail h2` naming the id;
the walk calls it in place of the two waits (the settle stays). Test
`test_the_walks_cluster_switch_waits_for_the_paint_not_the_position` on a seeded server whose ASGI wrapper
holds prod-east's payload 1.2 s: returns ≥ 1.0 s later with the heading "prod-east" and the dim gone. It
lives in `test_ui.py` — CI's unit job runs `tests/` without Chromium, so OB1's placement beside the walk's
unit test would have failed there; the binding guard, which needs no browser, stays in that file.

### Recorded, not changed
- C4: on every tab but the Overview a link to a retired cluster is still the generic error card with no bar
  (its "← all groups" re-renders the same card) — F10 limited the absorption to the scoped Overview; widening
  it is a separate change, not a regression of this PR.
- The CR detail's heading rail (A).
- The merge's resolution placed the #172 CHANGELOG entry above the foundation's; ordering in the doc only.

### Not asked
- P12, the chip edge: OB1 measured the alpha-composited edge at 1.24:1 (Codex's figure; its own drive first
  printed 19.17:1, which ignored the alpha, and it retracted that) and would not reopen the rejection — the
  edge is the badge's own and the chip's text (19.2:1) carries the information. Stands.
- F12: the tiles follow the mock as ruled; nothing to add.
- The walk scripts' selectors resolve on every tab of the fixed head; the walk itself needs a cluster and was
  not run.

### Tests
Three new, each failing on `a78cb79` — `('3px', 'auto')`; `AttributeError` (no helper); the binding error
naming `e2e_extra.py:55` — and passing after. Focused on the fixed tree (the review classes, the fleet, the
Policy tab, the walk tests, the CSS guards, the title and skip-auth parity files): 409 passed.
Full UI suite 351 passed (236.83 s); non-UI suite 3305 passed, 12 skipped, with one environmental failure —
`test_every_panel_promql_expression_parses_with_promtool` refuses to skip under `CI=1` on a machine without
promtool (without the flag it skips; CI installs promtool). CI on `21e9538`: one browser failure —
`test_the_contract_survives_in_both_views` at 14 clusters read the scoped view after `#back`, which arrives
with the first paint (the tile, its alerts, "Loading…" — F15), and CI's runner had not landed the tables yet;
350 passed beside it and every local run was green. The same wait-on-the-position that C6 named in the walk:
an `_open_cluster` helper waits for the tables' paint and the two tests that read table content use it (the
tests that deliberately read the first paint do not). CI on that head is recorded below when it lands.
