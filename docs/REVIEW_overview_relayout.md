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
