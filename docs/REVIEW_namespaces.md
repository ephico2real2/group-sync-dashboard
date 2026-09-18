# Review record — namespaces as entities (#167, PR #181)

Branch `feat/namespaces`, base `feat/design-foundation`. Head reviewed: `3365484` (the feature commit
`a801e00` plus the merge of `origin/feat/design-foundation`). Three reviewers on one brief
(`review_167/brief.md` in the session scratchpad; its ten claims are restated in the table): Grok 4.6
(Cursor, ask mode — no shell, verdicts from the source and the pinned tests); OB1 (Claude Fable — drove
the app at both tiers with Playwright, probed the store with seeds the branch's tests lack, proved five
fixes fail-before/pass-after on a copy); Codex (GPT-5.6, xhigh — an in-memory API probe; its sandbox
could not launch Chromium). Grok's pass landed first and its fixes were applied as batch 1; OB1's and
Codex's landed together and their additions are batch 2, below the first five findings.

Every verdict was re-checked against the branch source before a decision; the re-check is quoted with
the line it rests on. Line numbers are those of the reviewed head and are not maintained.

## Claims × reviewers × decision

| # | Claim | Grok | OB1 | Codex | Re-check | Decision |
|---|---|---|---|---|---|---|
| N1 | List counts: distinct groups in the namespace, non-platform person grants, cluster-wide once on the envelope; self tier = own in-namespace paths | REFUTED — envelope `cluster_wide_groups` is binding rows not distinct groups; self-tier empty copy is a false absence | REFUTED — envelope `cluster_wide_groups` is binding rows; the self-tier list hides what a cluster-wide path reaches (inconsistent with N2's reach rule) | REFUTED — the same count (probe: 2 for one group bound twice); the self-tier exclusion is a policy choice ACCESS_CONTROL.md does not settle | `api.py:1710` `len(wide["via_groups"])` — rows. The card's copy says "cluster-wide group **binding**s", so rows is what it claims. The empty copy at self (`index.html:3311`) said "No namespaces recorded" over the viewer's own slice | Reversed in batch 2: the envelope counts what its column counts — F6; the self-tier list follows the reach rule — F7. Copy fixed — F3 |
| N2 | Detail: reach before lookup, twin 403s, member_count, people, siblings, changes, retention | CONFIRMED, two holes named (F4, F5) | CONFIRMED (probe: dangling group → `member_count` 0, `people` 3, `present: false` 200, 404 when nothing names it) | CONFIRMED (probe: byte-identical 403s, `people: 4`) | `api.py:1744–1757` as quoted; `store.py:1466` `namespace_reach` binds `IN (?, '')` | Accepted; F4 applied, F5 applied. Codex's path-parameter descriptions rejected: R2 is the query-parameter rule by design and no handler describes a path parameter |
| N3 | `@consistent` on both handlers (R5), parameters described (R2), API.md matches the wire | CONFIRMED | CONFIRMED (list 4 store calls, detail 5; API.md field for field) | REFUTED — path parameters carry no OpenAPI description | Both handlers carry the decorator; `test_api_contract.py` passes | — |
| N4 | List counts agree with each detail, including a group bound twice and a platform-only namespace | CONFIRMED; neither fixture is in the seed | CONFIRMED (probe with a group bound twice and a platform-only namespace: the cases the seed lacks) | CONFIRMED (the same probe) | The seed has no group bound twice in one namespace and no platform-only namespace | OB1 and Codex probed both cases: the row counts hold. F6 adds the group-bound-twice case to the API tests for the envelope |
| N5 | The card lists every namespace, the box ANDs over name and label values, `N of M shown`, Escape, the Exposure table untouched | CONFIRMED | CONFIRMED (driven: 9 rows, headers, `demo` → 2, `demo qa` → 1, Escape → 9, `#ns-pick` options unchanged) | REFUTED — `data.namespaces`/`data.ns` are not in the auto-refresh fingerprint | `namespacesCard` at `index.html:3282` | — |
| N6 | `ns` in `POSITION_KEYS`; every handler clears it; labels; pasted link rises | REFUTED — the cluster selector and the keyboard user-drill keep `ns`; a pasted link labels `← namespace audit` | CONFIRMED (driven: Back/Forward walk, labels, pasted link rises) | REFUTED — the keyboard user-drill omits `ns: null` | `index.html:1031` `navigate({ cluster, groupsync: null, group: null, user: null })` — no `ns`; the `.drill` keydown handler the same, with `preventDefault` on the click that would have cleared it | F2 applied. The pasted-link label names the tab, which is where `goBack()` lands (the list under the audit tab); kept |
| N7 | The page's five cards match the mock; the three `(first observed)` rows are right | PLAUSIBLE (could not load the mock); the flag is right by the baseline rule | PLAUSIBLE — the cards match the mock; the baseline cell reads `+ granted (first observed)`, against #177's rule | PLAUSIBLE — three first-observed rows are right | The seed writes each stream once, so its rows are the first observation of that stream (`docs/DESIGN_binding_events.md`) | — |
| N8 | Fixtures: keys on `server`, none on `scoped_server`; a self-tier test of the card exists | REFUTED — no self-tier test of the card or the page | REFUTED — no scope branch in the card: "No namespaces recorded" and "Every namespace the poller sees" to a narrowed reader; no self-tier test | REFUTED — no self-tier browser test | None existed | Self-tier tests added: `nobody` (F3's copy), carol (F7), alice's page (F7) |
| N9 | 375 px on the card and the page | PLAUSIBLE (not run) | CONFIRMED (375 at both tiers) | PLAUSIBLE | `test_the_page_holds_at_phone_width` passes in the fixed tree's run | — |
| N10 | Nothing else moved | PLAUSIBLE | CONFIRMED (nine tabs byte-identical, old build beside new) | PLAUSIBLE | The group and user drills gained `ns: null` only | — |

## Findings

### F1 — `docs/CHANGELOG.md` was an unresolved merge — accepted

**Finding (Grok).** Lines 13–19 of the file carry `<<<<<<< HEAD` … `=======` … `>>>>>>> origin/feat/binding-events`
around the Unreleased bullets.

**Re-check.** `git grep -n -e '^<<<<<<< ' origin/feat/namespaces` → `docs/CHANGELOG.md:13`. The pair came in
with the merge `cf4f310`; the conflict on `test_docs_citations.py` in the same merge was resolved and this
file was not read again. No test scanned for markers.

**Decision.** Both sides kept (the #167 and #152/#166 bullets, then the `binding_event` bullet), markers
removed. Grok's test asserted the two bullet titles under Unreleased, which breaks the day the release
moves them; the guard added instead (`tests/test_tree_hygiene.py`) scans every tracked text file for a
line beginning `<<<<<<< ` or `>>>>>>> ` — the class of defect, not this instance — with a self-check
that the scan sees a marker at the start of a line and not a quoted one. Fails on `3365484`, passes after.

### F2 — the cluster selector and the keyboard user-drill kept `ns` — accepted

**Finding (Grok).** `ns` joined `POSITION_KEYS` without joining the selector's drop list, so a namespace
page survived a cluster change and refetched the name against the new cluster; the keyboard drill to a
person omitted `ns` and `preventDefault`s the click that would have cleared it.

**Re-check.** Both as quoted (`index.html:1031`, the `.drill` keydown in `wireDrilldown`). The same hole
was closed for `group` and `user` earlier (`test_switching_cluster_abandons_the_drilldown`).

**Decision.** Applied as proposed — `ns: null` on both `navigate()` calls, and the comment above the
selector names the third key. Two tests in `TestNamespaces`: the selector from a namespace page lands on
the new cluster's list with no `ns` and no error card; Enter on a person's name leaves `ns` behind. Both
fail on `3365484`.

### F3 — the self tier's empty Namespaces card claimed the poller saw nothing — accepted

**Finding (Grok).** At `scope: self` the rows are the viewer's own in-namespace paths; zero rows painted
"No namespaces recorded for this cluster yet", a confident wrong absence. A viewer whose only path is
cluster-wide (the UI seed's carol) sees exactly that.

**Re-check.** `store.py:1420` `namespaces()` skips a namespace at self unless an own path is bound *in*
it; `api.py` returns `count: 0, source.state: ok` for carol; the card's else-branch had one copy for
both tiers.

**Decision.** Copy split on `d.scope`: at self, "None of your memberships or direct grants names a
namespace. That is your view, not the cluster: a namespace missing here may exist, and a cluster-wide
grant is not an in-namespace path." Grok's alternative — listing every namespace for a viewer with a
cluster-wide path — is a store change that would show the whole cluster to anyone holding cluster-wide
`view` who still fails the admin SAR; not taken. The API test pins the behaviour the copy describes
(carol → empty list, `source.state == "ok"`) and passes on both heads by design; the UI test on
`scoped_server` as carol fails on `3365484`.

### F4 — cluster-wide grants naming a person were missing from the namespace page — accepted, smaller snippet

**Finding (Grok).** `Store.namespace_detail` folded cluster-wide **group** bindings into
`cluster_wide_groups` and `people`, but cluster-wide **user** bindings (`binding_namespace = ''`) appeared
nowhere on the page — not in `direct_grants` (in-namespace only), not in `people`, not on the
"also reached cluster-wide" line — while the list's envelope counted them (`cluster_wide_grants`).
A reader of `prod-ns` concluded only group paths and in-namespace directs reach it; carol's cluster-admin
ClusterRoleBinding was invisible there.

**Re-check.** `store.py:1500–1511`: `direct` is `binding_namespace = name` only; `people` is members ∪
non-platform `direct`. `index.html:3330–3367`: `wide` is `cluster_wide_groups` only. The issue's plan
comment says nothing either way; the operator's rule for an open question is best practice, and a
"who reaches it" that omits a cluster-admin naming a person is the same false absence as F3.

**Decision.** Applied, with a smaller change than proposed: the in-namespace query became a closure
`named(namespace)` called twice (`direct = named(name)`, `cluster_wide_grants = named("")`); `people`
adds the non-platform names of the second; the detail returns `cluster_wide_grants`; the list's envelope
reads that key instead of the `direct_grants` of a `name=""` call (same value, explicit). The page's
cluster-wide line lists the groups and then the people ("named directly"), platform identities left
off it — kubeadmin's `ka` reaches every namespace by definition and would be one more line on every
page. `API.md` documents the key. Grok's whole-function rewrite was not taken: it changed nothing else
and the closure keeps the diff to the lines that moved. Tests: the API seed gains `erin` (cluster-wide
`view` by name, in no group); `quiet-ns` names her and counts two people; the self tier does not see
her; the UI seed's carol is on `quiet-corner`'s page and kubeadmin is not. Three API assertions and the
UI test fail on `3365484`.

### F5 — the namespace page offered the audit table's export — accepted

**Finding (Grok).** `exportDescriptor`'s `nsaudit` branch did not require `!view.ns`, unlike the users
and groups branches, so the namespace page still offered CSV/JSON of the direct-grants table it does
not show.

**Re-check.** As quoted; the buttons render whenever the descriptor is non-null.

**Decision.** `if (view.page === "nsaudit" && view.ns) return null;` ahead of the branch. Whether the
Namespaces list should be a second export of the audit tab is left open as accepted debt
(`docs/DESIGN_export.md`: the rows the page holds — the tab now holds two tables and exports one);
it is a feature, not a defect. Test: the buttons are present on the tab and absent on the page; fails on
`3365484`.

### CI — three store methods absent from `StorageBackend` — accepted (not a reviewer finding)

`tests/test_storage_seam.py::TestContract::test_the_protocol_declares_every_method_the_application_calls`
failed on `3365484` in CI (`tests (3.11)` and `tests (3.14)`): `namespaces`, `namespace_detail`,
`namespace_reach` were called on the backend and not declared. Declared beside `namespaces_source`
with the store's signatures. The non-UI suite had not been run on this head before the push; it is now
part of the checklist for every push of this stack.

## Batch 2 — OB1 and Codex

### F6 — the envelope counted binding rows where its column counts distinct groups (OB1 F1, Codex N1) — accepted, reversing the N1 decision

**Finding.** `cluster_wide_groups` was `len(wide["via_groups"])`: a group with a cluster-admin and a
view ClusterRoleBinding counted twice (OB1's probe: `2`, the detail's distinct groups `1`; Codex's probe
the same), while every row's `via_groups` is `COUNT(DISTINCT group_name)`.

**Re-check.** `api.py:1718` as quoted. Batch 1 had kept rows because the card's copy said "group
binding**s**"; two reviewers converging on the column's semantics is the better argument — the envelope
and the column answer the same question and must count the same thing. Reversed.

**Decision.** Distinct groups on the envelope; the card's line reads "N group(s) bound cluster-wide and M
cluster-wide direct grant(s)"; API.md says so. Test: `TestClusterWideCounts` (one group, two CRBs → the
detail lists two bindings, the envelope counts one). Fails on `3365484`.

### F7 — a self-tier viewer with a cluster-wide path got an empty list while the detail opened every namespace (OB1 F2) — accepted, a ruling

**Finding.** `namespace_reach` treats a cluster-wide path as reaching every namespace (carol opens
`quiet-ns`; a real name 200s, a fake one 404s), but the list skipped every namespace without an
in-namespace own path — carol saw nothing, and "the grant that affects her most is the one the list never
mentions". Grok had cautioned against listing every namespace for such a viewer.

**Re-check.** `store.py:1459` as quoted. The rule for an open question is best practice, not a block:
the list and the detail must answer the same reach rule, and a viewer holding cluster-wide `view` can
list namespaces with `kubectl` already, so the list reveals nothing they cannot see — the same argument
that settles the existence-oracle debt below.

**Decision.** `Store.namespaces(..., every=)`: the handler computes the viewer's own cluster-wide paths
at both tiers (`namespace_detail(cluster_id, "", user_name=me, groups=groups)`), reports them on the
envelope (non-null at self now) and passes `every` when either is non-zero, so every row stays with its
columns still counting the viewer's in-namespace paths; the card's line says "of yours" at the self tier
and renders only when there is a path to explain. `API.md` and `StorageBackend` follow. Tests: carol's
list is four with `(1, 0)` (API); carol's card is nine rows with "0 groups bound cluster-wide and 1
cluster-wide direct grant of yours" (UI, `scoped_server`); alice's card is nine rows through her group's
hand-made CRB and `prod-ns`'s page carries her own memberships only, no People KPI, no label column
(UI). Batch 1's carol-empty-list test was replaced. All fail on `3365484`.

### F8 — a baseline history row read "+ granted (first observed)" (OB1 F4) — accepted

**Re-check.** `docs/DESIGN_binding_events.md:72`: a consumer renders a baseline row as "first observed by
this dashboard", never as "added". The cell said both. It reads "first observed" alone now; the test
opens `prod-ns` (three baseline rows) and reads every change cell. Fails on `3365484`.

### F9 — the namespace payloads were not in the auto-refresh fingerprint (Codex N5) — accepted

**Re-check.** `refresh()` wrote `data.namespaces` and `data.ns` (lines 4514–4515) and the fingerprint at
4527–4531 omitted both, so a poll whose only change was a label or a grant skipped the repaint the
fingerprint's own comment forbids skipping — the same class as #172's `data.fleet`. Added. Codex offered a
source-scan test; the test written intercepts `/namespaces`, relabels `prod-ns` on the wire, calls
`refresh({auto: true})` and waits for the cell. Fails on `3365484`.

### F10 — the list was fetched on the namespace page, where the card is not rendered (OB1, not asked) — accepted

One request a minute for nothing. The page fetches the detail, the tab the list, never both.

### F11 — the card's intro said "Every namespace the poller sees" to a narrowed reader (OB1 F3) — accepted

Batch 1 had fixed the empty copy only; the intro line was the wide tier's too. Both speak of the viewer's
own memberships and grants at the self tier; the empty copy no longer claims a cluster-wide grant is not a
path (with F7 it is one). Test: `nobody` at the self tier (fails on `3365484`).

### Rejected
- **Codex N3 — `Path(description=…)` on the path parameters.** R2 (`test_r2_every_query_parameter_is_described`)
  is the query-parameter rule by design; no handler in `api.py` describes a path parameter (`Path(` is not
  imported), and describing two of them would be the inconsistency.
- **OB1 F5's guard file.** Batch 1's `tests/test_tree_hygiene.py` covers it (tracked files by
  `git ls-files`, the two seven-character markers); OB1 saw it in the working tree and said so.
- **Codex's changelog-marker test** asserting `=======` absent — a setext underline in Markdown; the two
  seven-character markers are the guard.

## Not asked

- **Unbounded list.** `list_namespaces` takes no `limit`; the R3 test flags only handlers that take one.
  Measured on CRC: 110 namespaces. Accepted as cluster-bounded, like `user-bindings`' per-namespace
  rollup; if paging is ever added, `total` + `truncated` are mandatory.
- **`json_each('[]')`.** An empty group list matches nothing; `namespace_reach` then rests on the
  `user_binding` EXISTS alone. One JSON parameter, so no variable-limit hole (#177's scar).
- **`#ns-pick` vs the list.** The rollup says `(cluster-scoped)`, the entity list uses `''` on the
  envelope. Two widgets, two vocabularies; not wired together. Accepted.
- **Self tier with a cluster-wide path is an existence oracle.** `namespace_reach` is true for every
  name, so such a viewer gets 200 for a real namespace and 404 for a fake one. Accepted: cluster-wide
  `view` already lists namespaces with `kubectl`, so the answer reveals nothing they cannot see.
- **Pasted `ns=` link.** `#back` reads `← namespace audit` (no `from`), and `goBack()` lands on that tab's
  list. Kept — the label names where the button goes.
- **5,000 namespaces (Codex).** An in-memory list of 5,000 rows returned in 67.8 ms and encoded to
  1,023,929 JSON bytes; the card builds 5,000 rows synchronously with no virtualisation. The same accepted
  debt as the unbounded list above, with a measurement behind it.
- **The export of the Namespaces list (Codex, OB1).** Both name it a product decision; recorded above as
  accepted debt.

## Outcome

Pass 1, three reviewers: eleven findings accepted (Grok five, applied as batch 1; OB1 and Codex six more
as batch 2, one reversing a batch-1 decision and one a ruling on the self tier), one CI failure fixed
alongside, three rejected, fourteen new tests plus a tree-wide guard — every test shown failing on
`3365484` except the two whose fixes live in the same file as their fixture (proved against the frozen
fixture instead) and the F3 API pin. Focused runs on the fixed tree: the API, seam, hygiene, contract and
docs tests — 1021 passed, 12 skipped; the four UI classes around the change — 48 passed; the full suites on
the fixed tree — non-UI 3376 passed, 17 skipped; UI 320 passed. CI on the pushed head and the second pass
are recorded below when they land.

## Pass 2 — over `6a8fa85`

Grok (source only) and Codex (in-memory `TestClient` probes and the shipped renderer evaluated
directly; no Chromium) on the fixed head; OB1's second pass was lost to the session limit while its
Playwright driver ran, and is replaced by one confirmation run on the final head. A fourth source joined
this pass: the head deployed on CRC (`76ebaff21e`, through PR #183's stack) and walked as kubeadmin.

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| P1 | `cluster_wide_grants`: platform rows in the detail, out of the envelope and `people`; DISTINCT across the four sources | CONFIRMED | CONFIRMED (probe: `people 4` with an overlapping member/direct person) | — |
| P2 | The line's grammar at 0 / 1 / many, "of yours" at self | CONFIRMED | CONFIRMED (renderer executed) | — |
| P3 | `every` = the viewer's own cluster-wide paths; R5 four calls; the 403 before lookup | CONFIRMED — a platform identity cannot be a person | REFUTED — `every` came from the counts, which drop platform rows, while `namespace_reach` does not: kubeadmin at the self tier opened any namespace and saw an empty list | A — the switch is the reach itself (`cluster_wide_path`, on the envelope); the counts stay the review's counts; the card names the platform-only case |
| P4 | The four personas' copy | CONFIRMED (traced from the tests) | REFUTED as written — P2 changed the wide line, so "byte-identical" and P2 could not both hold | The brief contradicted itself; the intro and empty strings are identical, the line is P2's. No change |
| P5 | The baseline cell | PLAUSIBLE — the words match, the class is still `change-added` (green) | REFUTED, the same | B — `change-baseline`, muted |
| P6 | The fingerprint; `data.ns` on the list | CONFIRMED | CONFIRMED (JSON probe) | — |
| P7 | The fetch gating; Back does not flash Loading | CONFIRMED | CONFIRMED | — |
| P8 | `ns` dropped by the selector and the keyboard | CONFIRMED for the user drill; Enter on a GROUP's name goes nowhere (volunteered, V1) | REFUTED — the same (`group-enter { prevented: true, calls: 0 }`) | C — every drill activates through the click's own path |
| P9 | The export | CONFIRMED | CONFIRMED | — |
| P10 | `StorageBackend` | CONFIRMED | CONFIRMED (5 passed) | — |
| P11 | The marker guard | CONFIRMED | CONFIRMED (`tracked-via-git 546`, 124 binaries skipped) | — |
| P12 | API.md and the CHANGELOG against the wire | CONFIRMED (no request-spy test for the fetch gating) | REFUTED on the P3 edge only | A documents `cluster_wide_path` |

### A — a platform identity's reach and its list disagreed (Codex) — accepted
`namespace_reach` counts every binding naming the viewer, a platform identity's included; the list's
`every` came from the two counts, which leave platform identities out — so `kubeadmin` at the self tier
(the UI seed's `ka`, a platform ClusterRoleBinding) opened any namespace and saw an empty list. The
switch is the reach itself now, returned as `cluster_wide_path`; the counts are unchanged; the card's
line says "A cluster-wide grant to a platform identity of yours reaches every namespace below" for that
case instead of "0 groups … and 0 grants of yours reach every namespace". Tests: an API test with a
platform-only self viewer; kubeadmin on `scoped_server` (nine rows, the platform sentence).

### B — a baseline row wore the added colour (Grok P5, Codex) — accepted
`first observed` is not an addition; `change-baseline` (muted) beside `change-added` and
`change-removed`. Test: three synthetic rows painted from one payload, class and text asserted.

### C — Enter on a group's name went nowhere (Grok V1, Codex) — accepted
The `.drill` keydown handler cancelled the key and navigated only for a person's name; every drill takes
the click's own path now (`el.click()`), which also drops `ns`. Test: user and group, Enter and Space, with
Back restoring the namespace. The same handler is on `feat/drilldown` (#174), where Grok and Codex found
the same swallow on the lookup's doors; the fix text is identical on both branches.

### D — the deployed page's cluster-wide line was a 54-binding wall (the CRC walk) — accepted
Measured on the deployed head (`demo-prod`): "Also reached cluster-wide, by 54 bindings" listing
`system:authenticated`, `system:nodes`, `system:masters`, `system:serviceaccounts`… with `basic-user`,
`self-provisioner`, `system:discovery`… — 41 of the 54 are virtual `system:` groups (`SYSTEM_GROUP_PREFIX`
in `gsd/kube.py`: "reserved-by-convention … classified and labelled, never silently dropped"), and the
who-reaches table listed `system:serviceaccounts:demo-prod` as a hand-made path. Every `via_groups` and
`cluster_wide_groups` row carries `is_platform` now (real groups first); the table badges the virtual
ones; the line lists the real groups and the people, then folds the rest: "and 41 platform bindings to
virtual groups (system:authenticated, system:nodes, system:masters, …) that every namespace carries"; the
list's `cluster_wide_groups` count leaves them out, as the person counts leave platform identities out.
Tests: the API seed gains `system:authenticated` (cluster-wide) and `system:serviceaccounts:demo-prod`
(in the namespace); the UI test injects four virtual cluster-wide rows and one in-namespace row and reads
the badge and the fold.

### Rejected / kept
- Codex's `cluster_wide_path` copy variant for the wide tier — not needed: the wide tier's line is
  unchanged.
- Grok's "of yours" nit (attached to the grants half) — the sentence reads correctly for both halves.
- OB1's own guard file, Codex's `=======` check — as in pass 1.

### Measured on the fixed tree
API/seam/contract/docs/CSS-guard tests 1354 passed, 12 skipped; the four UI classes around the change 55
passed. Fail-before on `6a8fa85`: eight of the ten new cases fail (the two user-key keyboard cases already
passed there — user drills worked; the group-key cases, the platform-identity list, the virtual-group fold,
the baseline class and the changed count assertions fail). Full suites on the fixed tree: non-UI 3377 passed, 17
skipped; UI 327 passed. CI on the pushed head and OB1's confirmation run are recorded below when they land.

## Pass 3 — OB1's confirmation over `ff6b0dd`

One reviewer on the final head (pass 2's `f44e560` merged with the foundation's `a668d51`), seven claims
(`review_167/pass3/brief.md`): a Playwright drive on the UI seed's scoped servers as every persona (alice, carol,
jdoe by its DN, kubeadmin, nobody, root), an in-process TestClient over the same seed, a keyboard sweep over every
`.drill` signature on every page (click, Enter and Space, with `navigate`, `refresh`, `pushState` and
`replaceState` counted), contrast by the composited colours, and every fix proved on a clone (10 failed on
`ff6b0dd` → 44 passed; the clone's full suites: non-UI 3378 passed, UI 334 passed). OB1's own pass-2 run was
lost to the session limit; this is its replacement. OB1 proved first which `gsd` its interpreter imported (the
venv's editable install points at the main repo; `python -m pytest` from the worktree wins).

| # | Claim | OB1 | Decision |
|---|---|---|---|
| C1 | `cluster_wide_path` is the reach; the list and the detail agree for every persona | CONFIRMED — for every persona the set the list returns equals the set the detail opens over the recorded namespaces; the one difference (`dev-ns`: 200 with `present: false` for jdoe and root, a namespace the store no longer holds but a binding still names) is the designed detour. The IN-namespace half is REFUTED, volunteered as NA-1: a platform identity whose only path is a RoleBinding in a namespace got an empty list while the detail opened it | A |
| C2 | The baseline class, its contrast | PLAUSIBLE — on the card face 4.68:1 (light) / 4.85:1 (dark); on a zebra row (`--zebra` over the card, which the stylesheet guard never composites) `--text-muted` is 4.45:1 / 4.43:1 for 13 px text | B — routed to #184 |
| C3 | The keyboard | CONFIRMED — every signature on every page: click = Enter = Space = one navigate, one pushState, no replaceState, the same destination; `ns` dropped where the click drops it; Back restores. One pre-existing exception (NA-2): a group drill inside a group row on a user's page navigated twice | C |
| C4 | Virtual groups | CONFIRMED on the wire (real rows first, `people` unchanged, the envelope's count leaves them out) and on the page (the badge, the fold's every shape); the deployed fold's copy volunteered as NA-4, the column's count as NA-3, the API doc as NA-6 | D, E, F |
| C5 | The merge of the foundation | CONFIRMED — 375 px: header 167 px, the labels above their selects, `scrollWidth` 375; `index.html` untouched by the merge, the CHANGELOG the only conflict; the reporting fixture's clock live | — |
| C6 | Two invocations and the poll | CONFIRMED — page → Back → sibling → Back with a `pageerror` listener armed: none; an unchanged auto refresh leaves the DOM alone, a changed label repaints the page and the list (the fingerprint carries both) | — |
| C7 | A hand-made badge on a virtual group's row | REFUTED — the seed's `pullers-0` (`system:image-pullers`-shaped) wears both badges while the findings API tiers the same binding `built_in`, never `unmanaged` | G |

### A — the in-namespace half of the reach (OB1, NA-1) — accepted
`namespace_reach` counts every binding naming the viewer; the list kept a row only for a non-platform grant
(`is_platform = 0`) or a group path, so a platform identity whose only path is a RoleBinding in a namespace —
kubeadmin bound `admin` in one namespace, everyone self — got an empty list while the detail opened that
namespace: the same disagreement pass 2's A closed cluster-wide. The self-tier rows follow the reach: a namespace
where any binding names the viewer keeps its row, with the review's counts beside it (0, 0 — platform identities
stay out of the count). Test: `test_a_platform_identity_in_namespace_path_is_listed_where_the_detail_opens`
(list `["one"]`, detail 200 on `one`, 403 on `two`), `[] == ['one']` on `ff6b0dd`.

### B — `--text-muted` on a zebra row (OB1, C2) — accepted on the fact, routed to #184
OB1 proposed `--text-secondary` for `.change-baseline` alone (7.34:1 on a zebra row) with a test that composites
the painted cell. Not taken here: the zebra idiom undercuts every token the guard measures "on a card" — the same
rows put `.change-added` at 4.28:1 (light), `.change-removed` at 4.44:1 / 4.11:1, every `td.muted` at 4.44 /
4.43 (OB1's NA-5) — and #183's pass 2 measured the drill link at 4.305:1 / 4.375:1 there. Recolouring one class
hides one instance of a design-system defect; the fix is one token change on the foundation (#184, where OB1's
numbers are now posted), with a guard that composites the row, not the card.

### C — a group drill inside a group row navigated twice (OB1, NA-2) — accepted
A user's page nests a `button.drill[data-group]` inside a `tr[data-group]` (memberships, history); the
`[data-group]` handler, unlike `[data-user]`'s, did not stop propagation — click, Enter and Space each gave two
navigates (a push, then a replace of the same position) and two fetches, the first superseded. Pre-existing,
not #167's keyboard change; `e.stopPropagation()` as the user handler does. Test:
`test_a_group_drill_inside_a_group_row_navigates_once` — `[2, 2]` on `ff6b0dd`, `[1, 1]` after.

### D — the Via groups column counted virtual groups (OB1, NA-3) — accepted; a decision the operator can veto
Pass 2's D took platform groups out of the envelope's `cluster_wide_groups` and pinned the opposite for the rows
(demo-prod `(2, 1)`, "the virtual group counts as bound in the namespace"). On OpenShift every namespace carries
`system:image-pullers` → `system:serviceaccounts:<ns>`, so on CRC's 110 namespaces the column read ≥ 1 on every
row and the card's own promise — "A namespace with zero in both is a result an access review wants to confirm"
— could never come true (measured on the seed: ns0–ns5 read 1 each with nothing but the virtual group behind
them). The row and the page's KPI count groups of people; the virtual row stays on the page, badged, and the
who-reaches heading says how many are platform (the Direct grants card's own pattern, "· N · M platform"). The
self tier is untouched (a viewer's synced groups are never `system:`). Tests: the API pin is `(1, 1)`, the
list/detail agreement filters `is_platform`, and `test_the_via_groups_column_counts_groups_of_people_not_virtual_groups`
reads the column (0), the KPI (0) and the heading ("· 0 · 1 platform") with the virtual row still listed.
This reverses a pass-2 assertion; recorded here for the operator.

### E — the fold names the most-bound groups first and counts them (OB1, NA-4) — accepted
The deployed fold read "35 platform bindings to virtual groups (system:authenticated, system:cluster-admins,
system:masters, …)": the three names were an accident of the store's sort (role, then group) and the "…" hid
how many groups the rest were. The fold now names the groups most-bound first — `system:authenticated`, every
logged-in user, carries most of a cluster's platform bindings — counts them, says "… N more" behind the three,
and reads the singular for one ("1 platform binding to 1 virtual group (system:authenticated)"). Tests: the
pass-2 fold assertion updated and `test_the_fold_says_how_many_virtual_groups_and_names_the_most_bound_first`.
A number to check on the walk: the record said 41 of demo-prod's 54 cluster-wide bindings were virtual groups
and the deployed fold said 35 — the fold counts `cluster_wide_groups` rows only; if the 41 counted platform
grants naming a user too (`cluster_wide_grants`, never listed on the line), both are right.

### F — API.md (OB1, NA-6) — accepted
The detail example's `via_groups` row carries `is_platform`; the list's prose says which groups the column
counts; the `is_platform` paragraph names the badge rule.

### G — no hand-made badge on a platform row (OB1, C7) — accepted
Nobody hand-makes `system:image-pullers`; the namespace controller does, and the findings tier that binding
`built_in` before the `unmanaged` branch — two surfaces, one binding, two answers. The badge's own definition
("None means nothing manages this binding — somebody created it by hand") is false on a virtual row. No
hand-made badge where `is_platform`; a real group's hand-made binding keeps it. Test:
`test_a_virtual_groups_default_binding_is_not_badged_hand_made` (`pullers-0` badged platform only;
`was-managed` still hand-made).

### Not asked
- NA-5 — the zebra rows vs the status tokens (routed with B).
- The record's "Rejected": nothing OB1 would decide differently.

### Tests
Eight tests fail on `ff6b0dd` (the two changed API assertions, the in-namespace reach, the updated fold
assertion, the fold's count and order, the badge, the column's count, the double navigation) and pass after.
Focused on the fixed tree (the namespaces API, `TestNamespaces`, `TestNamespaceAuditPage`, `TestBrowserHistory`,
the CSS guards, the API contract, the docs citations): 1302 passed, 12 skipped.
Full UI suite 332 passed (218.47 s); non-UI suite 3378 passed, 13 skipped (574.51 s). CI on `862df79`: green on
every job. Merged into `feat/drilldown` as `b21ea86` (clean; 976 passed on the merged tree) for the deployed walk.

## Pass 4 — OB3's integration review (max effort), over `integration/design-programme`

Not a review of this branch: a review of all five features merged onto one branch, where the seams are. Two
of its findings are this page's.

### H — the self-tier page stated two facts about everyone (OB3, C10) — accepted
At the self tier `direct_grants` and `via_groups` are the VIEWER's own paths — the endpoint's own docstring
says so — and the page read them as the namespace's. Measured on the seeded app: alice on `prod-ns` was
shown *"No RoleBinding names a person here directly, which is the state an access review wants to
confirm"* while `jdoe-admin` names one; alice on `klt-pass-both` was shown *"not granted to anyone through
the policy system"* while `app-ocp-rbac-klta-ns-audit` is bound there. Both are false statements about the
cluster, made to the reader least able to check them, in a tool built for access review.

Three sentences now speak only for the viewer at the self tier, and the KPI labels follow the numbers they
sit beside — "Via your groups", "Your direct grants" — which is the rule `SPEC_per_user_visibility`
already states: never a recomputed number under its old label. The wide tier is unchanged. Test:
`test_the_self_tier_page_never_speaks_for_everyone`; the existing KPI-label assertion moved with the labels.

### I — the policy sweep did not cover this branch's endpoints (OB3, C8) — accepted
`CLUSTER_ENDPOINTS` is the sweep proving every cluster-scoped handler answers `hidden` exactly as `unknown`,
so a hidden cluster is not an oracle. Neither `namespaces` nor `namespaces/{name}` was in it. Both added,
and the second earns its place by mutation: with `require_cluster` deleted from `namespace_detail` the sweep
fails on `namespaces/prod-ns` alone (1 failed, 57 passed) and passes on the real code (58 passed) — repeated
here rather than taken on the reviewer's word.

### Tests
Browser suite 333 passed; non-browser 3380 passed, 13 skipped.
