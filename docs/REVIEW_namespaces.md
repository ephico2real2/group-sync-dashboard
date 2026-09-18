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
