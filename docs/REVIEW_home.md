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

## Not asked
- The e2e walk visits Home for free (it walks `button.tab`, and Home is first); Grok suggests a drill step —
  click a group row, wait for the group page, go back — since `walk_tabs` never leaves the tab. Worth adding.

## Outcome
Four findings from one reviewer, all four accepted with their fixes traced before applying (A's fix was
rewritten to remove a duplicated rule rather than add a fifth copy; A's second test was rewritten because the
first version passed before the fix). Nine tests fail on `af3d47d` and pass after. Full browser suite 364
passed; non-UI 3420 passed, 13 skipped. Codex's pass on the same brief and the third reviewer's confirmation
are recorded below when they land.
