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
