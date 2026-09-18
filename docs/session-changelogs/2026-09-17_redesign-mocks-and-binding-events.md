# Session change log — group-sync-dashboard, 2026-09-17 → 2026-09-17

What one working session did, in the order it did it, with the time of each commit taken from
`git log` (author time, America/Chicago) and the review, deployment and test facts from the commands
the session ran. Every "measured" claim is one the session ran a command for; nothing below is
recalled from memory alone.

Outcome in one line: **…**

| | Before the session | After |
|---|---|---|
| Application / chart | 0.24.0 / 0.33.0 (`docs/CHANGELOG.md`, 2026-09-16) | … |
| main | `54ecde7` (2026-09-16 20:05, PR #150 merged) | … |
| `docs/design/` | 2 files: the README and the reporting-status mock (`git ls-tree 54ecde7`) | … |
| PRs opened today (gh) | — | #154, #164, #168, #176, #177 |
| Issues filed today (gh) | — | #152–#175 |

---

## Part 1 — the redesign, driven from the live dashboard first (2026-09-17, 14:31 → 22:04)

### Mocks and records — branch `docs/landing-access-mock` (PR #164), `docs/drilldown-mock` (PR #168)

- The operator's mandate: drive the live app with Playwright before designing. The drill-down mock
  (drilldown-mock.html, on PR #168's branch) adopts the measured navigation model — hash positions, one history
  stack, contextual back labels, multi-word AND search proven by `alice zzz` → 0 results — and the
  Cluster Overview relayout (cluster-overview-mock.html, same branch) uses the real four-state status
  vocabulary traced through `local-development/gsd/state.py`, with density tiers by fleet size and paged alerts.
- **Found by the render check**: the KPI mock invented CPU motion with `Math.random` on a "live values"
  page and showed the mock cluster's sync as ok while the live store said overdue 3d — both corrected
  (`ec6532c`). The Reports-page mock had a stray `<style>` pair from the grafted form mock that put its
  CSS outside the stylesheet — removed (`77f381a`).
- Records committed on that branch: data-requirements.md, inventory-2026-09-17.md and
  kyverno-research-2026-09-17.md under the design directory; the feature contract gained the Cluster Overview and the
  persistent shell (Refresh, Sign out, settings, Appearance and Colour) as must-not-remove (`a719aba`).
- Issues #156–#175 filed from the audit; #171 is the tracking issue with the implementation order.

## Part 2 — binding_event: the bindings' membership history (2026-09-17, 21:40 → )

### Implementation — commit `1f55cb1`, PR #177

- Two rulings from the data audit implemented on the backend: namespace history (#167) and "who else
  is in my groups" (#158 G). `rbac_group_binding` / `user_binding` are still replaced each refresh, but
  the refresh first appends a `binding_event` per (binding, subject) that appeared or disappeared;
  `membership_event` and `binding_event` both carry a first-observation `baseline` flag (#175).
  `GET /api/clusters/{cluster_id}/binding-changes` (self-scoped), `gsd_binding_changes_total` pre-seeded
  with nameless labels, migration 13, retention shared with `membershipEventsDays`.
- Deployed to CRC as `0.24.0-1f55cb14ad` after a first attempt exited 125 (`oc whoami -t` has no token
  under the client-certificate kubeconfig — recorded in memory). **Measured live**: two RoleBindings created at
  02:52:06Z → three `added` rows at 02:57:18Z (the platform's `system:image-pullers` included), namespace
  deleted → three matching `removed` rows at 03:03:18Z; counters symmetric.

### Review pass 1 applied — commit `c59fddd` (2026-09-17 23:0x), PR #177

- **Found by Codex (gpt-5.6-sol, xhigh), C4 REFUTED, accepted and fixed**: an empty first poll left no rows, so the
  second poll's real additions were flagged `baseline = 1` (`first_empty=0 event_rows=0 second_nonempty=1
  second_baseline=1`). The first observation is now a consumed marker — `observation_state(cluster_id, stream)`,
  **migration 14** rather than Codex's rewrite of 13, because CRC already carried `user_version 13`.
- **Found by Codex, volunteered, accepted**: one SQL placeholder per viewer group → "too many SQL variables" past
  `SQLITE_LIMIT_VARIABLE_NUMBER`; one `json_each(?)` parameter now; the test forces the limit to 16.
- **Found by Cursor (Grok 4.6)**: two stale "two tables" comments and four preservation tests — **applied**; its
  accepted debt on the empty first observation is superseded by the marker.
- Measured: touched files 193 passed; full suite **3073 passed, 17 skipped** (`--ignore=tests/test_ui.py`); citations
  test 891 passed; CRC upgrade 13→14 wrote **0** baseline rows over 407 / 95 / 184 current rows; nine markers seeded;
  the route answers `count: 6, baseline_rows: 0`. Record: `docs/REVIEW_binding_events.md`.
- Process: Codex's own "leave the scratch directory empty" step deleted the launcher's `tee` target it shared —
  recovered byte-identical (25,265 bytes) from the harness capture; the second pass gives each reviewer its own
  directory and forbids deleting files it did not create.

### The OB1 skill (PR #176, branch `skill-ob1-reviewer`) — commits `c31e6a9`, `dff6d4c`, `30dc24e`

- The operator's branch conflicted with main (cut before `a3b4b07`); resolved keeping OB1, main's background-wakeup
  paragraph, Grok's ZDR tag and the demand-the-snippet sentence — PR #176 reads MERGEABLE (blocked only on approval).
- **The operator**: "It shouldn't be review only. It also produces the code fix for any suggestions" → OB1 hands back
  the full fix and its failing/passing test in its report; "Dont drop the cursor fable role" → the Cursor Fable rows
  stay; OB1 fills the role while Cursor's usage limit is hit (measured: `ActionRequiredError: You've hit your usage
  limit`), and Cursor Fable resumes when the quota resets.

### Review pass 2 applied — commit `127d5c7` (2026-09-18 00:1x), PR #177

- Three reviewers on `c59fddd`: Codex (gpt-5.6-sol xhigh), Grok 4.6, and **OB1** — Fable 5.1 through the Agent
  tool, standing in while Cursor's Fable is at its monthly limit (measured: `ActionRequiredError`).
- **Found by Codex and OB1, S3 refuted, accepted**: a cluster successfully polled empty on v13 IS provably observed
  (`groupsync_presence`, `poll_outcome status='ok'`, both in `sync_members`' transaction); **Grok** added
  `group_state`. **Found by OB1**: the deployed `1f55cb1` run against a v14 store would write rows with no
  marker and an applied migration never re-runs — the seed now runs at **every open** (`_OBSERVATION_SEEDS`,
  idempotent); the drafted migration 15 was dropped.
- **Found by Codex (the plan) and OB1 (the timing), S6(d) refuted, accepted — reversing pass 1's rejection**:
  306.82 ms per self-tier read at 300k rows against 1.80 ms with two index-served halves; `UNION ALL` applied with a
  plan test.
- **Found by OB1, V2**: the `_harden` docstring's "no SQL JSON functions" claim was false since `a7b155c` — restated.
- Measured: five touched files 156 passed; full suite **3081 passed, 17 skipped** (`--ignore=tests/test_ui.py`);
  CRC rolled to `0.24.0-127d5c735f`: no migration re-ran, nine markers unchanged (the open-time seed a measured
  no-op), 0 baseline rows, the route answers `count: 6, baseline_rows: 0`. Record: `docs/REVIEW_binding_events.md`.

---

## Part 3 — the design-system foundation, #152 + #166 (2026-09-17 → 18)

### Implementation — commit `53a366a`, PR #179 (branch `feat/design-foundation` from main)

- Measured before touching anything: 92 inline `style=` attributes (24 font sizes the type-scale guard could not
  see), three `var(--x, #hex)` fallbacks, radius literals 999/6/50%/10/4/3/2/5/1 px, 25+ spacing literals on a
  2 px grid; at 375 px on the live cluster the tab bar was **676 px** wide, the page **696**, five of nine tabs
  past the edge. Plan posted on #152 first.
- Spacing (`--space-1…11`) and radius ladders named at the sheet's own values — nothing moves; nineteen
  off-ladder literals carry an `optical:` note the guard requires. `--line` / `--accent-soft` / `--warn` defined.
  Okabe–Ito palettes solved to the default tokens' contrast bars by lightness alone (every theme × palette pair
  measured: 328 contrast checks). Appearance + Colours in the static header, applied before first paint from the
  URL, then storage. The 92 inline styles promoted to classes. `nav.tabs` wraps.
- **Found by the render check (a pixel diff against main from the same seed)**: a token-block comment quoting
  `/* optical: … */` closed early and the tail swallowed `--space-1: 2px;` — every chip lost its padding while
  the regex guards stayed green. Fixed; a comments-do-not-nest guard added. The diff's verdict on the final
  cut: groups / bindings / policy / nsaudit / usage **0 pixels changed** below the header.
- Measured: `test_ui.py` 297 passed; guards 340; 375 px `scrollWidth` 375 on every tab; CI green.

### Review pass 1 applied — commits `19d7b35`, `faf88b4`, `9a0e29c` (2026-09-17 23:48 → 2026-09-18)

- Three reviewers on `53a366a`: Codex (gpt-5.6-sol xhigh, no Chromium in its sandbox — it executed the head and
  wiring scripts in a mocked DOM), Grok 4.6, and OB1 with Playwright.
- **Found by Codex and Grok, D3 refuted, accepted**: `--accent-soft` on `:root` froze against `--tab-overview`
  (custom properties inherit their computed value) — the Users chip wore Overview's blue, measured
  `color(srgb .157 .451 .804 / .14)`; now on `body`. **D8 refuted, accepted**: a second `class=` attribute on the
  bindings search note (the parser drops it); merged, with a guard. **D10 refuted, accepted**: the raw-colour
  guard's finder swallowed `body {}`; single-level bodies, with a parametrised leak test.
- **Found by OB1, F1 (refuted at HEAD), accepted**: the Grok-pass rewrite had sliced `tests/test_type_scale.py`
  from the colour guard to its end and deleted `test_comments_do_not_nest` — restored with a self-check. **F2,
  volunteered, accepted**: `?mode=dark` printed dark text on white paper (measured under print emulation) —
  every dark block is `@media screen` now, with a test. **F3, accepted**: Back shed `?mode`/`?theme` from the
  URL — re-stamped on `popstate`. **F4, accepted**: the 375 px sweep never saw Reports — a test on the reporting
  fixture. **F5**: a docstring count. OB1's element-by-element diff of 13 page states on 31 computed properties
  against main is the evidence "nothing moved" now rests on.
- Measured: guards 334; the shell UI classes 17; citations 891; CI green on `19d7b35`. Record:
  `docs/REVIEW_design_foundation.md`. The second pass (Grok + OB1) on `9a0e29c` is running.

### Review pass 2 applied — commits `2061807` (2026-09-18 00:26), `311f544` (2026-09-18 00:41), `a668d51` (2026-09-18 02:04)

- Grok and OB1 on `9a0e29c`. **Grok, accepted**: a hashless link kept `?mode` only until the boot's
  `replaceState` (`location.hash || location.pathname` dropped the query) — `pathname + search` now, with a test
  (`2061807`); the two header labels were given to the accessibility tree by the clip idiom (`2061807`) — reversed
  below. **`311f544`** relocated the Reports-at-375 test beside its module-scoped fixture with a diagnosis
  ("its report ticket outlived its 300 s TTL") that OB1's pass 2 refuted and I retract: the fixture's
  report-service clock was frozen at creation, the dashboard mints with wall time, and `ticket.py` refuses a
  ticket issued more than 30 s after the service's "now" as future-dated — a 403 `reportFetch` never remints on
  (401 only). Measured by OB1: 200 at 3 s after the fixture's creation, 403 at 80 s and 350 s; the TTL is 120 s.
- **OB1 pass 2, accepted (`a668d51`)**: the fixture's clock is live unless a test pins it, and a guard reads the
  snapshot's age twice over the wire and requires it to move (`0 -> 0` against the frozen fixture); each phone
  label sits above its select below 520 px — 167 px measured, both labels visible and operable, against 142.5 px
  with them clipped from sighted readers; the record's stale "223 px, no change" line and the CHANGELOG's silences
  corrected. OB1's measurements behind the seven CONFIRMED claims: 90 theme × palette × tab samples for the
  accent wash, a brace walk and print emulation for the `@media screen` wrappers, a registration-order trace for
  the Back re-stamp, 137,496 computed-style comparisons across 22 page states for "nothing else moved".
- Measured: both new tests fail on `311f544`; `TestReportsTab`, `TestTheShellAtPhoneWidth`,
  `TestAppearanceAndColours` 37 passed; non-UI 3302 passed, 17 skipped; UI 306 passed; CI green on `a668d51`.
  Record: `docs/REVIEW_design_foundation.md`, "Pass 2, OB1". A confirmation pass on `a668d51` follows.

## Part 4 — the Cluster Overview relayout, #172 (2026-09-18)

### Implementation — commit `759cd7d` (2026-09-18 00:57), PR #180 (branch `feat/overview-relayout` from `feat/design-foundation`)

- The page follows the fleet, not the viewport: `data-density` from the served cluster count (3 / 8 / 24), a tile
  per cluster with the seven figures at full density, worst-first past three, the alerts card first past eight,
  eight alerts per page as view state, a consequence line under every non-ok state in `state.py`'s vocabulary,
  and the scoped view (`#page=overview&cluster=<id>`) as a position on the one history stack — the fleet stamps
  no default cluster.
- Measured before the review: the fleet at 2, 6, 14 and 40 clusters rendered at 1440 and 375 px (`scrollWidth`
  375 at every tier); `TestOverviewFleet` on the four fleets; CI green on `759cd7d`.

### Review pass 1 applied — commit `c806112` (2026-09-18 02:02), PR #180

- Three reviewers on one brief. **Grok** read the source: the dead heading button in the opened cluster, the
  dense rows reading `unknown` for `auth_failed` (`badge("critical")` fell through `STATES`), the retired-cluster
  link dying on a 404 before the page's own detour could render, `data.fleet` missing from the repaint
  fingerprint, no paint before a tile's fetch — its O6 refutation was itself refuted (`311f544:3833` returned
  `""` for `present:false` too) and its F4 test could not fail. **OB1** drove the app at 2/6/14/40 and measured
  thirteen findings: `unknown` blaming the cluster (`api.enrich()` never passes `reachable`), the fleet's absent
  note said of an unpolled cluster, the tile's styles lost in the opened block, a cluster change from the fleet
  clearing nothing (crc-local's four groups painted under prod-east), the first paint claiming "shown per cluster"
  of a fleet of two, a failed per-cluster fetch folded into "all syncing", a refused reader running the fleet
  stage every poll, a superseded refresh writing `data.fleet`, compact tiles hiding the two figures the plan
  named, blank-glyph kinds badges, and the Policy tab changed six ways. **Codex** read the contract: the Policy
  tab's card restored (the pre-#172 card plus the consequence line), and the self-tier Overview conflict between
  the tab-feature contract and `ACCESS_CONTROL.md` — routed to #182, not decided here.
- Measured: `TestOverviewReview` (14) and the Policy-tab test fail on `759cd7d` (17 failed with the changed
  density assertion); the fixed tree — the review class with the PR's own classes 74 passed, CSS guards 334,
  non-UI 3303 passed, 17 skipped, UI 344 passed; the fleet at 14, the scoped view and the Policy tab rendered
  and read; CI green on `c806112`. Record: `docs/REVIEW_overview_relayout.md`. The second pass is running.

### Review pass 2 applied — commit `602eaf7` (2026-09-18 04:55), merge `a78cb79` (2026-09-18 05:09), PR #180

- Grok and Codex on `c806112` (OB1's second pass was lost to the session limit mid-measurement — three OB1 runs
  had been launched at once; one confirmation run follows on the final head). Both converged on four residues
  of pass 1: the opened cluster's rail (`.tile.bad` never paired with `.tile-detail`), the accent rail lost on a
  heading inside `.row-wrap` (the Overview's counted headings and the Policy tab's), `syncMeans` gated on a last
  sync (a never-synced CR with an unusable schedule promised "its first fire"), and the selector showing "all
  clusters" beside the retired-cluster detour. **Codex, volunteered**: the e2e walk's second-cluster step chose
  "all clusters" — the fleet option's label — so its evidence stayed on the fleet; `next_configured_cluster()`
  skips empty-valued options, with a unit test.
- **The operator's ruling (2026-09-18: the mocks' visuals)**: compact tiles hide the three extra figures again,
  as the Overview mock's CSS does — OB1's F12 offered as a suggestion and declined. The kinds chips keep the
  badge's own edge (Codex's heavier edge rejected: the chip is the badge's shape).
- Measured: six new tests fail on `c806112` (forced checkout — the first proof had run on `759cd7d`), pass on
  the fixed tree; focused 391; non-UI 3304 passed, 17 skipped; UI 344 → 348 after the merge of the foundation's
  `a668d51` (a CHANGELOG conflict resolved; the merge was needed because a PR whose merge commit cannot be built
  gets no `pull_request` run — ten minutes of "no checks reported" before that was understood); CI green on
  `a78cb79`. Deployed to CRC (`0.24.0-602eaf7922`) and walked: the fleet, the scoped view, the Policy tab, 375 px
  — captures sent. The report pod's `readyz` 503 on that deploy is the designed guard ("snapshot schema 14 is
  newer than this report service understands (12)"): the drilldown stack had migrated the live store first.

### Review pass 3 applied — commits `21e9538` (2026-09-18 07:02), `97adf24` (2026-09-18 07:11), PR #180

- OB1's confirmation run on the merged head `a78cb79` (its pass-2 run had been lost to the session limit): a
  Playwright drive over four seeded fleets, both themes × five palettes, twenty snapshots across the poll,
  the full UI suite once (349 passed). Three refutations, each proved fail-before/pass-after: pass 2's wider
  accent-rail selector had reached every fleet tile's name (3 px, 16 px inboard of a bad tile's own status
  rail; the opened form and the mock's tile have none) — the rule stops at the tile; the e2e walk's cluster
  switch passed `cluster_id` positionally to Playwright's keyword-only `arg` (a TypeError at the second
  cluster that `bash -n`, an AST parse and a by-path import could not see) — `arg=`, and a guard binds every
  page call in both walk scripts against the installed signature; and the walk's wait returned before the
  cluster painted (the previous heading still on screen at 24 ms and after the 900 ms sleep, the paint at
  1523 ms with the fetch held 1.5 s) — a helper waits for the position, the dim gone and the opened
  cluster's heading. The browser-driven test moved into the UI suite: CI's unit job has no Chromium. C4's
  other-tab error card (a retired cluster on the Groups tab) recorded as F10's scope, not changed.
- Measured: the three tests fail on `a78cb79` and pass after; focused 409; full UI suite 351 passed
  (236.83 s); non-UI 3305 passed, 12 skipped, one environmental failure (the promtool test refuses to skip
  under `CI=1` on a machine without promtool). CI on `21e9538`: one browser failure — the fleet contract test
  read the scoped view after `#back`, which arrives with the first paint (F15), and CI's runner had not
  landed the tables at 14 clusters (350 passed beside it, every local run green): the same
  wait-on-the-position OB1 named in the walk, in a test; `97adf24` waits for the tables' paint at the two
  reads that touch table content — CI green on every job. Deployed to CRC (`0.24.0-21e9538e0c`; the report
  pod refused the schema-14 store by design, the drilldown head redeployed after) and probed: two tiles at
  full density, the opened cluster, Back, the Policy heading's rail, 375 px; captures sent. Record:
  `docs/REVIEW_overview_relayout.md`, Pass 3.

## Part 5 — namespaces as entities, #167 (2026-09-18)

### Implementation — commits `6420e7f` (2026-09-18 00:35), `cf4f310` (2026-09-18 00:36, the merge of #177), `a801e00` (2026-09-18 00:45), `3365484` (2026-09-18 00:57, the merge of the foundation), PR #181 (branch `feat/namespaces` from `feat/design-foundation`)

- `GET …/namespaces` (every namespace the poller sees, the configured labels, two counts, `source`) and
  `GET …/namespaces/{name}` (who reaches it and through which group, the grants naming a person, the cluster-wide
  grants, siblings under the first label, `people`, the history from `binding_event`); the Namespaces card on the
  audit tab with a pattern box over name and label values; the namespace page as the third drill-down. Self tier:
  own paths only, refused before any lookup so the two 403s are byte-identical.
- Measured: 11 API tests and 6 UI tests on the branch; CI on `3365484` **red** — one test, the storage-seam
  contract (three store methods not declared on `StorageBackend`), which the non-UI suite would have caught before
  the push had it been run; and the merge `cf4f310` had left conflict markers in `docs/CHANGELOG.md`, unseen.

### Review pass 1 applied — commit `6a8fa85` (2026-09-18 02:04), PR #181

- Three reviewers; two batches. **Grok**: the conflict markers (with a tree-wide guard now), `ns` kept by the
  cluster selector and the keyboard drill, the self tier's empty card claiming the poller saw nothing, cluster-wide
  grants naming a person missing from the namespace page (ruled on the issue: they belong there), the audit
  table's export offered on the namespace page. **OB1** (Playwright at both tiers, store probes): the envelope's
  `cluster_wide_groups` counting rows where the column counts distinct groups (Codex measured the same: 2 for one
  group bound twice) — a batch-1 decision reversed; the self-tier list hiding what a cluster-wide path reaches
  while the detail opened every namespace through it (ruled: the list follows the reach rule); the card's intro
  false at the self tier; a baseline history row reading "+ granted" against #177's rule; the list fetched on the
  namespace page. **Codex**: `data.namespaces` and `data.ns` missing from the auto-refresh fingerprint (the same
  class as #172's `data.fleet`); rejected — `Path(description=…)` on the path parameters (R2 is the query rule).
- Measured: fourteen new tests fail on `3365484` (the two whose fix shares a file with its fixture proved against
  the old fixture); the fixed tree — API/seam/hygiene/contract/docs 1021 passed, the four UI classes around the
  change 48 passed, non-UI 3376 passed, 17 skipped, UI 320 passed; CI green on `6a8fa85`. Record:
  `docs/REVIEW_namespaces.md`. The second pass is running.

### Review pass 2 applied — commit `f44e560` (2026-09-18 05:03), merge `ff6b0dd` (2026-09-18 05:09), PR #181

- Grok and Codex on `6a8fa85`, plus the deployed walk. **Codex**: `every` came from the two counts, which leave
  platform identities out, while `namespace_reach` counts every binding naming the viewer — kubeadmin at the
  self tier opened any namespace and saw an empty list; the switch is the reach itself now (`cluster_wide_path`).
  **Grok and Codex**: a baseline history row wore the added colour (`change-baseline`, muted); Enter on a group's
  name went nowhere — the `.drill` keydown handler cancelled the key and navigated only for a person (every
  drill takes the click's own path). **The deployed walk (CRC, `76ebaff21e`)**: `demo-prod`'s cluster-wide line
  listed 54 bindings, 41 of them virtual `system:` groups — every `via_groups` / `cluster_wide_groups` row carries
  `is_platform` now, the table badges the virtual ones, the line folds them ("and 41 platform bindings to
  virtual groups (system:authenticated, system:nodes, …)"), the list's count leaves them out.
- Measured: eight of the ten new cases fail on `6a8fa85` (the two user-key keyboard cases already passed there);
  focused 1354 + 55; non-UI 3377 passed, 17 skipped; UI 327; CI green on `ff6b0dd` after the foundation merge.

### Review pass 3 applied — commit `862df79` (2026-09-18 07:48), PR #181; merged into `feat/drilldown` as `b21ea86` (2026-09-18 07:49)

- OB1's confirmation run on the merged head `ff6b0dd` (its pass-2 run had been lost to the session limit): a
  Playwright drive as every persona of the UI seed, an in-process TestClient over the same seed, a keyboard sweep
  over every drill signature on every page, contrast by the composited colours, every fix proved on a clone.
  Taken, each proved fail-before/pass-after: the self-tier list follows the reach inside a namespace too (a
  platform identity's RoleBinding in a namespace listed nothing while the detail opened it); the Via groups
  column and the page's count are groups of people — on OpenShift every namespace carries
  `system:image-pullers`, so the column read 1 on every row and "zero in both" could never happen (a pass-2
  assertion reversed, recorded for the operator); no hand-made badge on a platform row (the findings tier the
  same binding built-in); the fold names the most-bound virtual groups first and counts them; a group drill
  inside a group row on a user's page navigated twice (pre-existing) — the handler stops propagation; API.md.
  Routed: OB1's recolour of the baseline cell — `--text-muted` composites to 4.45:1 (light) / 4.43:1 (dark) on
  a zebra row, and the same rows put the added and removed colours under 4.5 too — one token change on the
  foundation, #184, where the measurements are posted.
- Measured: eight tests fail on `ff6b0dd` and pass after; focused 1302 passed, 12 skipped; full UI suite 332
  passed (218.47 s); non-UI 3378 passed, 13 skipped; CI on `862df79` green on every job. Merged into
  `feat/drilldown` cleanly (`b21ea86`; the namespaces, lookup, history and audit classes with the API tests:
  976 passed) and deployed to CRC for the walk. Record: `docs/REVIEW_namespaces.md`, Pass 3.

## Part 6 — one lookup over the three kinds, #174 (2026-09-18)

### Implementation — commit `76ebaff` (2026-09-18 02:17), PR #183 (branch `feat/drilldown` from `feat/namespaces`)

- `#page=lookup`: three doors at rest with the lists' own counts, the matches by kind with text (twelve per
  kind), a Find box wherever no list has its own, the also-line on a list page, "search everything instead"
  inside a group; `binding_count` on every `/groups` row (the Grants column). Two pinned rules shaped the one
  deviation from the mock: typing never issues a request and the users list is fetched only on its own tab, so
  the also-line counts only what the session already holds (a first cut prefetched on the poll and failed the
  second rule; a second cut fetched once on the first keystroke and failed the first, moving the caret).
- Measured: the six `TestLookup` tests, the count test (5), the nine UI classes around the change 122 passed;
  non-UI 3381 passed, 17 skipped; UI 326; CI green; deployed to CRC (`0.24.0-76ebaff21e`, both pods verified
  in-pod) and walked — the lookup for "demo" over the real cluster (6 of 67 groups, 7 of 110 namespaces), the
  also-line, `demo-prod`'s page, 375 px; captures sent. The walk found the namespace page's 54-binding
  cluster-wide wall (fixed on #181's second pass) and the doors' double chevron.
- Merge `d489bcc` (2026-09-18 05:43): `feat/namespaces` at `ff6b0dd` (both review passes) into `feat/drilldown`, clean.

### Review pass 1 applied — commits `b6c9690` (2026-09-18 05:57), `f793b8e` (2026-09-18 06:04), PR #183

- Three reviewers on `76ebaff`. **OB1** (a seeded-app Playwright harness, `EXPLAIN QUERY PLAN`, a 10,000-user
  scale probe, the mark's contrast over 30 theme × palette × OS combinations, every fix proved on a copy)
  measured what the other two read: the committed IME composition never opened the lookup (Chromium fires no
  `input` after `compositionend` — Codex had named it, with a synthetic-event test that cannot drive Blink's
  IME); the highlighter corrupting names inside an entity and inside the previous term's `<mark>`; the Users
  door counting a manual account as a login (live on CRC: 63 rows, 62 logins); no scope statement on the
  self-tier lookup; "the data is not empty" on an empty cluster; the lookup's `groups?state=all` painting under
  the Groups tab's filter and counted by the also-line; every non-user drill dead to the keyboard (pre-existing
  on Access granted); the mark's wash at 3.40:1 under the sheet's 4.5:1 bar. **Grok** and **Codex** converged on
  the keyboard, the highlighter, the `state=all` slice and the door copy; Grok's "open the full list" carrying
  nothing and the two-bindings-in-one-namespace seed were taken too. OB1's recipe applied (its `groupsMeta.state`
  tag over Grok's second slot: it also closes the also-line's filtered-slice count); the keyboard block keeps
  #181's text so the branches merge cleanly. The deployed walk's two nits (the doors' double chevron, the
  capture script's out-of-repo path) folded in.
- Measured: thirteen tests fail on `76ebaff` (OB1) and eleven on the merged base `d489bcc` (the two keyboard
  tests already fixed there by #181's merge); focused 434; non-UI 3383 passed, 17 skipped; UI 347. CI on
  `b6c9690`: one browser failure — OB1's "open the full list" test read the Groups tab's box before the bar was
  repainted (a race on CI's runner, 3/3 green locally); `f793b8e` waits for the box; CI green on every job.
  Deployed to CRC (`0.24.0-b6c96905de`, the full stack, the report pod ready again at schema 14) and walked: the
  lookup for "demo", the also-line, `demo-prod` with the folded cluster-wide line ("19 real bindings; and 35
  platform bindings to virtual groups"), 375 px — captures sent. Record: `docs/REVIEW_lookup.md`. The second
  pass by Grok and Codex is applied in the next entry; OB1's confirmation runs behind #180's and #181's,
  one at a time.

### Review pass 2 applied — commit `3958c55` (2026-09-18 06:50), PR #183

- Grok and Codex on `f793b8e`, eleven claims; OB1's second pass queued behind its confirmation runs on #180
  and #181 (one at a time — three concurrent runs tripped the session limit and all were lost). Codex refuted
  two: the highlighter marked each term's matches in turn ("ab bc" on "abc" marked "ab", never "bc") — every
  match of every term is a range now, merged, so marks never nest; and the mark's contrast test composited on
  the card while the drill text on a zebra row measures 4.305:1 (light) / 4.375:1 (dark) — the foundation's
  drill colour against its zebra and hover tokens, on every table, filed as #184 rather than patched here.
  Grok confirmed all ten it could trace (P11 PLAUSIBLE, no shell) and volunteered the walk step: the capture
  script types "demo" into the Find box after the tabs, opens a namespace hit, reads the also-line, captures
  375 px, and records itself skipped on a build without the box. Grok's "leftmost-longest is acceptable" on
  the overlap was not taken (the function promises every occurrence). The union test's third case was first
  written expecting one mark over "ice coo" on "alice cooper"; the run refuted it (a space sits between the
  terms) and the expectation was corrected to two marks with the gap unmarked.
- Measured: the lookup class with the CSS guards 354 passed; the full UI suite 348 passed (225.96 s); the
  docs guards 893 passed, 12 skipped. Record: `docs/REVIEW_lookup.md`, Pass 2. CI on `3958c55` green on every
  job. Deployed to CRC (revision 250, `0.24.0-3958c5522a`, from a clean detached worktree — the release script
  refuses a dirty tree, and this entry was the dirt) and walked end to end: 79 steps, all passed, the new lookup
  step among them ("demo": 6 of 67 groups, 7 of 110 namespaces; `demo-prod`; the also-line; 375 px). OB1's
  confirmation is recorded when it lands.

## Part 7 — the reviewer seat: OB2, then OB3 (2026-09-18)

### The definitions — PR #185 (branch `skill-ob2-reviewer`), not yet merged

- OB1 was a launch RECIPE, not a definition: the `Agent` tool with `model: "fable"`, `subagent_type:
  "general-purpose"`, and the brief plus a read-only paragraph as its prompt — so it ran at whatever effort
  the session was on. The operator asked for it as a first-class agent: *"Create a new skill from OB1 called
  OB2 (OB1 high) with fable 5.1 but with high effort and assume OB2."* `.claude/agents/ob2.md` is that —
  `model: fable`, `effort: high`, and the reviewer's standing rules in the body (verdicts with artefacts;
  every REFUTED / risk-naming PLAUSIBLE / volunteered finding with the FULL code of its fix and a
  failing/passing test; read-only, a copy for anything it changes; measure, don't reason from memory; the
  report shape).
- **Measured, the same hour:** the `Agent` tool could not see the new definition — the registry is read at
  session start, so `subagent_type: "ob2"` answered "Agent type 'ob2' not found". The background path does
  see it, and that is how the reviewer now runs: `claude -p "<brief>" --agent ob2 --allowedTools
  "Bash,Read,Write,Edit,Glob,Grep" --output-format json --max-turns 300 < /dev/null`, with `CLAUDECODE`
  dropped from the environment. Verified with a one-line probe on haiku before the real launch.
- **The Fable weekly limit, measured:** that first OB2 background job — the confirmation pass on #183's
  merged head — died after **32 turns** with `"You've reached your Fable limit."`, **$4.93** spent and no
  report. The operator: *"We have hit our weekly fable usage limit. Create an ob3 from ob2 skill but use
  opus 5 high with auto switch effort… Then substitute the jobs and role of ob2 with ob3 now for the
  sessions."* `.claude/agents/ob3.md` is OB2's definition on `model: opus`, and OB3 holds the reviewer seat
  until the Fable quota resets.
- **On "auto effort" — what is actually available.** There is no `auto` value: the subagent frontmatter
  takes one fixed tier (`low`…`max`), and neither the `Agent` tool nor `claude -p` exposes an effort flag,
  so effort cannot be varied per launch from the outside. The tier is therefore pinned as a FLOOR and the
  self-scaling lives in the agent's body as a rubric the model applies per claim — a shallow claim (a
  string, a selector, a constant) is settled by a grep, a medium one (a render path, an API shape) by one
  drive, a deep one (a race, contrast over composited surfaces, cost at scale) gets the harness; the brief
  is budgeted as a whole so twelve claims are not twelve deep investigations; and the report opens by naming
  which claims were treated as deep. At the operator's instruction the same mandate went into OB2's body, so
  the judgement survives the quota reset rather than living only in the Opus definition.
- **OB3's passes are not settled.** The operator's rule: *"ob1 or ob2 should further review your work done
  with ob3."* Each definition carries its half — OB2 re-measures what OB3 marked CONFIRMED without an
  inspectable artefact and re-runs its failing/passing proofs against the head as it stands then; OB3 writes
  for that reader, keeps its drive script beside its report so the proof can be re-run, and flags what it
  treated as shallow, since that is what a second model is most likely to overturn. Agreeing with OB3
  because OB3 said it wastes the third-reviewer seat.
