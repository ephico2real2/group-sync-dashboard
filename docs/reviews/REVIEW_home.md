# Review record — Home, the page every reader lands on (#158, PR #186)

Branch `feat/home`, based on `feat/drilldown`. Head reviewed: `af3d47d`. The brief's ten claims are in
`review_158/brief.md` in the session scratchpad and are restated in the table below.

Reviewers: **Grok 4.6** (Cursor, ask mode — source only, no shell) and **Codex** (GPT-5.6, xhigh). The third
seat was empty for this pass: the Fable weekly quota ran out the same day (the OB2 background job on #183's
brief died after 32 turns at the limit), and **OB3** — the reviewer on Opus 5 created to replace it — was
running #183's confirmation while this pass ran. OB3 or, once the quota resets, OB1/OB2 takes a confirmation
pass on the fixed head; that section is added below when it lands.

## Claims × reviewers × decision

| # | Claim | Grok | Decision |
|---|---|---|---|
| C1 | Nothing cross-user or cross-cluster-aggregate reaches the page; the payload is identical on both tiers | CONFIRMED — every read is `AND user_name=?`; `include_platform=True` only drops the platform filter, never widens past the viewer; the two tier bodies match | — |
| C2 | The identity: no combination answers 200 for a name nobody vouched for | CONFIRMED — `trusted_viewer` is `None` whenever the proxy is off, so `require_viewer` 403s; restrictions-off is the documented posture, not a spoof | — |
| C3 | `elsewhere` and the cross-cluster line | **REFUTED** — a `hidden` cluster is named, counted and its history folded in, while its own endpoint 404s | A |
| C4 | The derivation's ranking | **REFUTED** — `role_kind` is ignored, so a namespaced Role named `admin` is treated as the ClusterRole | B |
| C5 | `group_changes` — the folding, `id()`, the timestamps, the three counts | CONFIRMED on the mechanics (the caller builds a new dict per event, so `id()` is unique; `fromisoformat` accepts the store's trailing `Z` on 3.11 and 3.14; no event lands in two items or vanishes) — with D on the label | D |
| C6 | Every sentence true of the payload it renders | **REFUTED** — the cluster-wide foot, and the "more changes" line | C, D |
| C7 | The route and the shell | CONFIRMED — default, first tab, pasted hash, Back/Forward, the selector re-scoping without leaving the page, `data.home` dropped on a cluster switch and carried in the fingerprint, the folds pushing no history entry | — |
| C8 | What the default route moved in the tests | CONFIRMED — relocating, not weakening; the Overview's administrator-tier refusal is still proven | — |
| C9 | Cost | CONFIRMED — one payload per poll; 28 store reads on a 20-cluster fleet, and `@consistent` holds a read snapshot across all of them, which is why A's fix matters beyond the leak | A |
| C10 | 375 px and the design system | CONFIRMED for the token placement (`--tab-home` in all three palettes; the colour-vision palettes correctly do not override `--tab-*`); Home **adds** to #184's list | Routed to #184 |

## Findings and decisions

### A — a hidden cluster was named on Home (Grok C3/C9) — accepted
`hidden` is a serving rule: `require_cluster` answers 404 for an unknown, disabled or hidden cluster so the
response is not an oracle over which clusters this instance watches. Home's cross-cluster loop walked
`store.clusters()` — polled, still `enabled=1` — and kept any cluster whose viewer name matched, so a hidden
cluster the person is on was named in "you're also on", counted in `memberships_total`, and had its
membership history folded into **What changed**, while the very next request for it 404s.

The rule had four copies in `gsd/api.py` and this was the fifth site, which forgot a limb. Rather than add a
sixth, it is one predicate — `is_served(cluster_id)` — and `require_cluster` is its other caller.

Grok's second point on the same loop: it called `viewer_scope` per cluster, which for a `remote-sar` cluster
performs an HTTP SubjectAccessReview against that cluster's API — one per cluster in the fleet, inside the
handler's `@consistent` read snapshot. Home does not need a tier there; it needs the name question, which is
configuration. `vouches_for_host_identity(cluster_id)` answers it without a resolver. Traced against
`viewer_scope`'s own `keep` rule before applying: restrictions off vouches for everyone; the host vouches for
its own reader; an `inherit` remote is keyed by the host's username; `self-only` needs `identity:
same-as-host` — and `remote-sar` is required by config validation to carry exactly that, while every
`_decide` branch returns the viewer. The two agree on the name for every configuration.

Tests: `test_a_hidden_cluster_is_not_elsewhere` (fails before: `['east', 'west'] != ['east']`) and
`test_the_cross_cluster_loop_consults_no_tier_resolver`, which uses a real `remote-sar` cluster so it
discriminates — the first version of that test passed before the fix and was rewritten rather than trusted.

### B — only a built-in ClusterRole is ranked (Grok C4) — accepted
`ROLE_RANK` is the four ClusterRoles the platform fixes, and the code ranked by `role_name` alone. Kubernetes
has one ClusterRole `admin`; a namespaced Role of that name is a different object with whatever rules its
author gave it. Ranking it let the page say *"covered by admin"* and *"removing this would not change what you
can do"* about access nothing else grants. `is_builtin_clusterrole(kind, name)` gates the ranking, the
cluster-wide map is keyed by `(kind, name)` so the two do not merge into one row, and `covers_grant` takes both
kinds. Aggregation is recorded as the residual this does not model: a cluster can add rules to `edit` that
`admin` does not carry, so "already includes it" is the platform's default relation, not a proof.

### C — the cluster-wide foot spoke of groups that do not exist (Grok C6) — accepted
A cluster-wide role held by a **direct** grant has `via_groups: []`, so the foot read *"0 groups grant edit
cluster-wide, but admin already includes it — removing them would not change what you can do."* The sentence now
has a direct-grant form and the zero case cannot be reached. Proved on the page: the test fails with that exact
string.

### D — "N more changes" counted cards, not changes (Grok C5/C6) — accepted
`more` was `len(items) - 12`, and the page calls those changes: a leftover batch of eleven groups read *"1 more
changes in the window"* — wrong number and wrong grammar. `more` counts the rows the leftover cards stand for,
`more_items` keeps the card count, and the sentence reads as one change at one.

### Routed
- **#184** — `--warn` on `--page-2` (~4.4:1) and muted text on the row's hover wash: the same shape as the
  zebra-row finding that issue already records, and the fix is the same token change, not a per-class recolour.
  Grok's suggested guard additions are posted there.

### Accepted from the not-asked section
The phone-width sweep covers the new tab; two comments still described the pre-#158 landing page; the 30-day
window is the server's and arrives with the payload rather than being a second constant in the page (with a
test that changes the payload and reads the card); and the shell's `data-page` attribute named the old landing
page until the first paint.

### Recorded as a deviation from the mock, for the operator
A namespaced **direct** grant appears both under *Namespaces you can reach* and under *Direct grants*; the mock
shows the console's own namespace only under Direct. Kept: a namespace a binding reaches is one you can reach,
whichever path carries it, and the Direct card is what explains the path. Grok raised it; the operator's veto
stands over this record.

## Codex's pass — over the tree with Grok's fixes applied

Codex (GPT-5.6, xhigh) read the same brief against the tree **after** Grok's four fixes were in, so its
verdicts double as a check on those: it confirmed C1, C2, C3, C5, C7, C8 and C9 with its own probes — a
matrix probe over proxy × restrictions × identity printed `403` and `404` in every unvouched combination, and
it re-derived the hidden-cluster and resolver regressions. It refuted three more.

### E — the removal advice was a claim about live rules (Codex C4/C6) — accepted
The page said *"removing them would not change what you can do."* The stock ClusterRoles aggregate that way,
but a cluster may change what `edit` carries and default-role reconciliation can be turned off, so a role's
NAME is not proof of its live rules (the Kubernetes RBAC reference, which Codex cites). The card now says the
stronger role *"includes it by default — worth confirming before anyone relies on them"*: a lead for a review,
which is what this page is for, rather than a verdict it cannot support.

### F — `.stale` was the shell's refetch class (Codex C10) — accepted
The cross-cluster pill was called `.stale`, and `.stale { opacity: 0.55 }` is the shell's global refetch state,
applied to whatever carries the class. The pill therefore rendered at 55 % — **2.27:1 light, 2.60:1 dark**,
far under the bar — and one class meant both "this page is being refetched" and "this cluster's data is old".
Renamed `.poll-age`, with a test that reads the computed opacity.

### G — three sentences that could be false (Codex C6) — accepted
- `window_days: 0` means kept forever, so the oldest row held is where the dashboard began watching. The foot
  said *"older changes have been pruned by retention"* — inventing a deletion. It now says so only when a
  window is set.
- "two paths to the same grant" compared role NAMES, so a Role and a ClusterRole of one name were called the
  same grant — the collision B had just fixed in the ranking. It compares kind and name.
- The remaining copy points Codex raised (a fully-covered namespace still called a "grant", "1 / 1 groups
  grant" in a terse tag, and the 500-event cap not announcing that counts are lower bounds) are recorded here
  and not changed: the first two read correctly in context, and the cap is per cluster per poll on a page whose
  window is 30 days — worth a follow-up only if a fleet ever exceeds it.

### Measured by Codex, not asked
Contrast on the actual Home surfaces, light/dark: `--warn` on `--page-2` 4.40 / 5.87; `--text-muted` on
`--page-2` 4.21 / 5.03; muted on the 10 % row hover 3.99 / 4.22; the scope pill on its wash plus hover 6.11 /
4.16; `.tag.rwx` 6.88 / 8.01 (passes) and `.flap` on the card (passes). The failures are the same shape as
#184's and are posted there.

### H — Codex's second reading, over the committed tree — accepted
Codex re-ran the whole brief against `e3062f5` (the tree with both passes and the evidence folder in) and
refused to call it done. Three more:
- **"namespace grants" counted namespaces.** `answer.namespaces` are places; the sub-line called their
  count "namespace grants", so the deployed capture in `reports/2026-09-18_home-158/` literally reads
  *"covers 12 of your 13 namespace grants"* over thirteen namespaces. The evidence folder made the defect
  concrete, which is an argument for committing evidence. Now "the namespaces you reach". The tag beside it
  read "1 / 1 groups grant" at one.
- **The per-cluster history cap was silent.** Each cluster's history is read up to `HOME_EVENTS_LIMIT`, so
  on a busy cluster every count on the card is a lower bound presented as complete. The payload names the
  capped clusters and the card says the counts are at least that many.
- **Home's own contrast.** Measured, both themes: `--warn` on `--page-2` 4.40:1 (light), `--text-muted` on
  `--page-2` 4.21:1, and muted under the 10 % hover wash 4.05:1 — Grok had flagged the shape, Codex the
  numbers, and they agree. The root cause is that `--text-muted` only clears 4.68:1 on the card to begin
  with, so any wash sinks it: that token's headroom is #184's. What is Home's own — which token goes on a
  washed row, and which surface a pill sits on — is fixed here: the rows carry `--text-secondary`, the wash
  drops to 6 %, and the amber pills carry the card's own surface instead of `--page-2`. Measured after:
  every Home pair clears 4.5:1 in both themes with headroom (7.09 for row text on the wash, 4.89 for the
  amber pills), pinned by `test_home_text_clears_aa_on_the_surfaces_it_actually_sits_on` across all ten
  theme × palette variants — with a docstring saying it does NOT cover the shared tokens.

### I — the CHANGELOG said two things that had stopped being true (Codex) — accepted
It claimed the payload is "byte-identical whichever tier resolves it" — my own test pops `scope` and the
window's clock-derived start before comparing, so it was never byte-identical — and it quoted the removal
sentence the page no longer says. Both corrected. A changelog that quotes copy the product does not have is
the drift these records exist to prevent.

### J — the policy sweep did not cover the new endpoint (Codex) — accepted
`CLUSTER_ENDPOINTS` in `tests/test_multicluster_visibility.py` is the sweep that proves every cluster-scoped
handler answers `hidden` exactly as it answers `unknown`. `home` was not in it — nor, it turns out, was
`namespaces` from #167. Both added; both pass, because `require_cluster` guards the handler — but the
guard is what pins it, and the leak Grok found was in the one loop that did not go through it.

### The integration CI found
PR CI builds the merge of this branch into its base, and `feat/drilldown` had meanwhile gained OB3's
`TestTheWalksLookupStep`, whose setup loads the app and waits for the Overview's hero. Home's route change
moved that. The test names `#page=overview` now, like every other Overview-subject test this branch
relocated — found by CI on the merge, not by either branch's own suite.

## Not asked
- The e2e walk visits Home for free (it walks `button.tab`, and Home is first); Grok suggests a drill step —
  click a group row, wait for the group page, go back — since `walk_tabs` never leaves the tab. Worth adding.

## Outcome
Four findings from one reviewer, all four accepted with their fixes traced before applying (A's fix was
rewritten to remove a duplicated rule rather than add a fifth copy; A's second test was rewritten because the
first version passed before the fix). Nine tests fail on `af3d47d` and pass after. Full browser suite 374 passed; non-UI 3438 passed, 13 skipped, after Codex's second reading. The third
reviewer's confirmation (OB1 or OB2 when the Fable quota resets, per the operator's rule) is recorded below
when it lands.

## Pass 3 — OB3's integration review (max effort), over `integration/design-programme`

A review of all five features merged onto one branch. Its C3 asked the converse of the fingerprint question
this record's earlier passes only asked one way round: not "is every payload IN the fingerprint" (they are —
24 of the 26 slots, and the two outside are a boot-only version string and an unrendered credential) but
"does any payload in it change on EVERY poll", which would defeat the unchanged-payload skip entirely.

### K — `/home` echoed the request's clock, so Home repainted every 60 seconds (OB3, C3) — accepted
`group_changes` returned `since`, the window's start, computed per request from `datetime.now()` at second
precision. The shell fingerprints the whole payload, so Home — alone among the pages — never matched its
previous fingerprint and replaced `#main` on every automatic poll, throwing away scroll, selection and any
focus on a row (the rows carry no id, so `render()`'s focus restore cannot find them). Measured: three
polls, three repaints, the only differing slot `changes.since`, two seconds apart; every other page and
tier fingerprinted equal across three polls, and every other endpoint is byte-stable across two reads.

Nothing renders `since`. The window is named by `window_days` and every item carries its own `observed_at`,
so the field is simply gone from the wire.

**The part that is mine to own:** the tier-identity test popped `since` before comparing, with a comment
saying it is "the request's clock, a second apart". I saw the field move and worked around it in the test
rather than fixing the wire — which is how it survived two review passes. The workaround is gone; the two
tier bodies are now identical but for `scope`. Tests: `test_two_reads_of_an_unchanged_store_are_byte_identical`
(the bytes differed at `since`) and `TestHomeSkipsTheUnchangedPoll`, which marks a DOM node and requires it
to survive two automatic polls.

### Tests
Browser suite 375 passed; non-browser suite 3439 passed, 13 skipped.
