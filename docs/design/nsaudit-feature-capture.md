# Namespace audit — what the page holds today

Issue #153 named this page one of its two references — *"Namespace audit and Reports — already the
references; leave them"* — and skipped it. Two things follow, and both are facts rather than opinions:
it is the only major tab with no mockup in `docs/design/`, and `docs/design/tab-feature-contract.md`,
whose stated job is *"what a redesign may not remove"*, has no section for it. The page the contract
calls a reference is the one page whose features were never captured.

This file is that capture, taken before any redesign was drawn. Everything below was read off the
**running** dashboard or off the render functions; nothing is recalled and nothing is summarised from
a screenshot.

## How this was measured

| what | how |
|---|---|
| the rendered page | Playwright through the oauth-proxy as `kubeadmin`, 1280×1000 then 375×800 — `reports/2026-09-21_nsaudit-mock/capture.py`, output in `reports/2026-09-21_nsaudit-mock/capture.json` |
| the payloads behind it | the same page's own `data.*`, plus the pod's loopback (`curl -H 'X-Forwarded-User: …' localhost:8080/api/…`) for the tiers a browser cannot reach |
| the reasoning | the render functions in `local-development/gsd/static/index.html` and the endpoint in `local-development/gsd/api.py` |
| the build | `v0.30.0 · a90f1b277b`, cluster `dashboard-rnd`, poll observed at `2026-09-21T05:06:29Z` |

The narrowed tiers are read through the loopback on purpose: the self tier is cookie-only, a bearer
token always lands on the wide view, and the loopback believes `X-Forwarded-User` the same way the
app believes the proxy (`local-development/gsd/api.py#trusted_viewer`).

## The route and the dispatcher

`#page=nsaudit`; a namespace drill is `#page=nsaudit&cluster=<c>&ns=<n>`.

`local-development/gsd/static/index.html#function nsAuditPage` chooses between three shapes and says
in its own comment why it never decides: *"Both narrowed shapes are the SERVER's call, read off the
wire: a scoped payload renders the viewer's own grants, a designed 403 a named refusal. The page never
decides which applies."*

| payload | renders |
|---|---|
| absent | `Loading…` inside a card — the page fails closed rather than rendering an empty truth |
| `forbidden` | `refusalCard("Namespace audit", …)` |
| `scope === "self"` | `selfGrantsView(ub)` + `namespacesCard()` |
| otherwise | `directUserGrants(ub)` + `namespacesCard()` |

`render()` dispatches `nsDetail()` instead when `view.ns` is set, and wires `wireNsAudit()` +
`wireNsPage()` + `wireLookup()` on the audit, `wireDrilldown()` + `wireNsPage()` on the namespace page.

## The administrator view — six cards

Measured card headings, in order:
`Namespace audit` · `Why this is a risk` · `Exposure by namespace` · `How to close it` · `Every grant`
· `Namespaces · 106`.

### 1. The verdict — `local-development/gsd/static/index.html#function directUserGrants`

A risk pill, `<worst> exposure`, beside the words *"highest risk on this cluster"*. Measured:
`High exposure`.

Five KPIs, measured `5 · 8 · 11 · 0 · 2`:

| KPI | value | computed from | why that source |
|---|---|---|---|
| Namespaces at risk | 5 | `by_namespace.length` | the rollup is never paged and never filtered |
| People exposed | 8 | the **union** of the rollup's `users` lists | the comment names both wrong ways: counting `bindings` reports the page once anything is truncated, and summing `distinct_users` double-counts — *"on the reference cluster jdoe holds grants in three, so the sum says 6 where the truth is 4"* (on this cluster, 11 against 8) |
| Grants to migrate | 11 | `by_namespace` summed | *"a headline count taken from \[the detail list\] reports the page rather than the cluster, and shrinks when the reader narrows the filter, which reads as the problem getting smaller because they looked at it closely"* |
| Critical | 0 | namespaces whose `riskTier` is critical | carries `flag-critical` and `.err` only when non-zero |
| High | 2 | namespaces whose `riskTier` is high | carries `flag-warning` only when non-zero |

Verified on the live page: selecting one namespace in the detail list below leaves all five unchanged
(`grants.filtered` in `capture.json` — the KPIs read `5 · 8 · 11 · 0 · 2` with the list filtered to
`legacy-payments`, 3 of 11 rows).

**The empty state is a different page, not an empty table.** With no rows,
`directUserGrants` renders a hero `0` over *"namespaces grant access to a person"* and the sentence
*"Every role on this cluster is granted to a group. That is what makes offboarding a single action:
removing someone from an LDAP group revokes their access everywhere at once."* No cluster in the lab
reaches zero, so this branch is quoted from the source rather than measured.

### 2. Why this is a risk

Three items, each a heading and a paragraph, measured verbatim:

- **Offboarding does not revoke it** — *"Removing someone from an LDAP group revokes their access
  everywhere at once. A binding that names the person keeps granting after they leave the team, change
  role, or leave the company — until somebody remembers it exists."*
- **Invisible to access review** — *"Every group-based review — including the rest of this dashboard —
  answers "who is in the group?". These grants are attached to no group, so a clean review can coexist
  with standing access nobody approved."*
- **No approval trail** — *"Group membership is granted in the enterprise directory, with a request and
  an approver. A hand-made binding records only who ran `oc`, and only for as long as the audit log is
  retained."*

### 3. Exposure by namespace

Standing note, verbatim: *"Ranked by the **worst privilege granted**, not by count — one forgotten
`cluster-admin` matters more than twenty `view` grants."*

The ranking itself is `local-development/gsd/static/index.html#function riskTier`, whose comment is the
reasoning the page exists on: *"Ranked on PRIVILEGE and SCOPE, never on count: one forgotten
cluster-admin outranks twenty view grants, and a page sorted by volume puts the twenty first and buries
the one."* The four tiers:

| tier | condition |
|---|---|
| Critical | cluster-scoped **and** privilege ≥ admin, or privilege = cluster-admin |
| High | privilege ≥ admin, **or** cluster-scoped at any privilege |
| Medium | privilege ≥ edit |
| Low | everything else |

Six columns; five sortable, each a `<button>` inside its `<th>` carrying `aria-sort`:
`Risk ▼` · `Namespace` · `Highest privilege` · `People` (num) · `Grants` (num) · `Who is exposed`
(not sortable). Measured `aria-sort` on first paint: `descending, none, none, none, none` and no
attribute on the sixth. Clicking **People** set `view.nsSort=people`, `view.nsDir=desc` and the
column's `aria-sort` to `descending`.

**Restore risk order** (`[data-ns-reset]`) appears only when the order is not `risk`/`desc`, and
removes itself when the order is restored — measured both ways.

Rows measured:

| Risk | Namespace | Highest privilege | People | Grants | Who is exposed |
|---|---|---|---|---|---|
| High | **CLUSTER-WIDE** (`.err`) | `edit` | 3 | 3 | dana.lee, jdoe, ocp-oauth-bind-serviceid |
| High | legacy-payments | `admin` | 3 | 3 | asmith, bwilliams, jdoe |
| Medium | legacy-reporting | `edit` | 2 | 2 | jdoe, tmp-contractor-9931 |
| Low | openshift-console-user-settings | `view` | 2 | 2 | developer, jane.smith |
| Low | group-sync-operator | `view` | 1 | 1 | ocp-oauth-bind-serviceid |

`risk-row risk-<tier>` colours the row and its left edge; the tier's **word** is in the first cell, so
colour is never the only carrier.

**Who is exposed** is `local-development/gsd/static/index.html#function whoCell`, bounded by
`local-development/gsd/static/index.html#const WHO_PREVIEW` = 4. Its comment: *"A namespace with forty
direct grants would otherwise put forty names in one cell and the column would decide the width of the
whole table — on the view that is supposed to be the scannable one. … WHO_PREVIEW is small on purpose.
The question this table answers is "which namespaces are exposed and how badly"; the names are
corroboration, and the full roster lives one section down in Every grant."* Past the bound the cell
shows `+N more`, which toggles to `show fewer`. **The widest roster on this cluster is 3, so the
control never renders here** — measured: every `td.who` came back with `more: null`.

Closing note when `excluded_platform` is set, measured: *"24 platform identities excluded — system
components and `kubeadmin` are break-glass and cluster-internal, with nowhere to migrate to."*

### 4. How to close it

*"Work top-down: the table above is already in the order to do it in."* Then five numbered steps,
measured verbatim: identify the role against the naming convention (`<app>-ns-admin`, `-ns-developer`,
`-ns-audit`); add the person to that group through the request-and-approve path; **wait one sync** and
confirm on the Groups tab — *"Do not skip this — deleting first leaves them locked out"*; delete the
binding (`oc delete rolebinding <name> -n <namespace>`); confirm on the next refresh.

Closing line: *"**Operational goal:** zero rows on this page. At zero, one directory change offboards a
person from the entire cluster, and an access review that reads clean *is* clean."*

### 5. Every grant

A disclosure in the section head — measured `▸ Show 11 grants` / `▾ Hide 11 grants`, with
`aria-expanded` and `aria-controls="every-grant"`, **collapsed by default**. The count is `ub.total`,
the server's count before its limit, never `bindings.length`.

Note, verbatim: *"The per-namespace table above is the view to work from. This is the flat detail
list — collapsed by default on purpose, because on a cluster with thousands of direct grants rendering
every row costs time nobody gets value from."*

`<select id="ns-pick">` lists `All namespaces (5)` then one option per rollup row with its grant count
(`legacy-payments — 3 grants`, `cluster-wide — 3 grants`, …). It is a **server-side** filter: `onchange`
sets `view.nsNamespace`, forces the disclosure open — *"Choosing a namespace to inspect and then having
to expand the list is a pointless second click; the selection IS the request to see it"* — and calls
`refresh()`. Measured: the request came back with `namespace: "legacy-payments"`, `total: 3`.
**Clear filter** appears only while a namespace is picked.

Four sortable columns: `Person` · `Grants` · `Scope` · `Binding`. The default sort is
`local-development/gsd/static/index.html#const GRANT_SORT`'s `risk`, which ranks by privilege and not
alphabetically — *""admin" < "edit" < "view" as text puts the dangerous grants in the middle, which is
the opposite of useful"*. A row is flagged `risk-row risk-high` when its role is `admin`/`cluster-admin`
or its scope is cluster-wide. `binding_namespace` empty renders `cluster-wide` in `.err`.

Truncation note, rendered only when `ub.truncated`: *"Showing the **N** highest-privilege of **M**
grants … The rest are not hidden findings — they are ranked below these. Narrow with the namespace
selector to see them."* The server's cap is
`local-development/gsd/static/index.html#const NS_GRANT_PAGE` = 200, *"worst-first … so a truncated page
is the top of the list rather than a slice of the middle"*. This cluster serves 11 of 11, so the note
does not render — quoted from source.

### 6. Namespaces — `local-development/gsd/static/index.html#function namespacesCard`

Heading `Namespaces · 106`, becoming `· N of 106 shown` while the search box holds a query.

Two standing notes, measured:
*"Every namespace the poller sees, not only those with a grant. Click a row — a namespace is an entity
here, the third drill-down beside groups and users. The box in the bar finds by name or by any captured
label."* and *"13 groups bound cluster-wide and 3 cluster-wide direct grants reach every namespace
below; the columns count what is bound in each one. A namespace with zero in both is a result an access
review wants to confirm."*

Columns: `Namespace` (a `.drill` button; the whole row carries `data-ns`) · one column per captured
label key, short name — measured `mnemonic`, `app-environment`, `oud-group` · `Via groups` (num) ·
`Direct grants` (num, `.err` when non-zero). 106 rows.

Three further states, all measured or quoted:

- **refused read** (`source.state === "forbidden"`): *"The namespace read was refused (…), so this list
  cannot attest absence — a namespace missing here may exist. Grant namespaces [get,list] (chart:
  `rbac.namespaces`)."* — not reachable on this cluster, whose `source.state` is `ok`.
- **filter hides everything**: measured — *"Nothing matches **zzzz-no-match**. All 106 are still there —
  the filter is hiding them. Press Escape in the box to clear."*
- **self tier, nothing reached**: *"None of your memberships or grants reaches a namespace on this
  cluster. That is your view, not the cluster: a namespace missing here may exist."* Measured through
  the loopback: a viewer with no path gets `count: 0`.

`alsoLine()` adds a cross-tab line while the box holds a query — measured with `demo`:
`search everything for demo`.

## The namespace page — `local-development/gsd/static/index.html#function nsDetail`

Measured on `legacy-payments`. Back button label: `← all namespaces`.

Cards: the namespace itself · `Who reaches it, and through which group · 0 · 1 platform` ·
`Direct grants · 3` · `History · 4`. `Same <label>` renders only when the namespace has siblings
(measured on `demo-prod`: 4 siblings sharing `company.net/mnemonic=demo`).

KPIs measured: one per label key (`— none —` in `.muted` when absent), then `People who reach it 11`,
`Via groups 0`, `Direct grants 3` (`.err`).

Notes measured verbatim:

- *"Carries none of the captured labels (`company.net/mnemonic`, `company.net/app-environment`,
  `company.net/oud-group`) — outside the naming convention, so no mnemonic-based report will ever pick
  it up."*
- *"The answer the triangle exists for: a namespace, back to the groups that grant it, back to the
  people in those groups."*
- *"A person named by a binding rather than reached through a group — the rows a directory change cannot
  offboard. The operational goal for this card is zero."*
- the cluster-wide line — one sentence, measured at **975 characters / 66 words**, naming 53 bindings: *"Also
  reached cluster-wide, by 53 bindings that grant every namespace: \[13 group buttons\], dana.lee
  (cluster-reader, named directly), jdoe (edit, named directly), ocp-oauth-bind-serviceid
  (group-sync-dashboard-cluster-poller, named directly); and 37 platform bindings to 12 virtual groups
  (system:authenticated, system:nodes, system:authenticated:oauth, … 9 more) that every namespace
  carries."*

Badges measured on the page: `platform` (`.unknown`, hollow circle) on virtual `system:` groups and on
platform identities; `hand-made` (`.warning`, triangle) on a binding with no `managed_source`;
`admin`/`edit` as `.critical`, anything else `.warning`, on a direct grant's role.

Platform folding is deliberate and its reason is in the source: *"the deployed demo-prod page listed 54
bindings, 41 of them these"*, and *"`system:image-pullers` is in every OpenShift namespace, so a Via
groups count that held them read 1 on every row and "zero in both" could never happen"*.

History: `Change · Subject · Role · Binding · Observed`, with `first observed` / `+ granted` /
`− revoked`. Measured: all four rows are `first observed` at `2026-09-20 22:57:29 EDT`. The retention
line (`retentionNote`) renders only when `window_days > 0`; this deployment reports `window_days: 0`, so
nothing prints — the sentence it would print is *"rows older than N days are removed by retention, so a
timeline that begins there was cut there — it does not mean nothing happened before."* Empty state:
*"No binding change recorded here since this dashboard started watching."*

Two further states, both quoted from source: `no longer on the cluster` badge plus *"The store no longer
holds this namespace; what follows is what still names it"* when `present` is false, and the no-group
empty note: *"No group-based binding names this namespace. Access here is entirely by the direct grants
below — which is what makes it a finding."*

## The narrowed tiers

### `selfGrantsView` — the viewer's own grants

Measured through the loopback as `jdoe`: `scope: "self"`, `viewer: "jdoe"`, `by_namespace: null`,
`excluded_platform: null`, `total: 3`.

The comment above `local-development/gsd/static/index.html#function selfGrantsView` is the rule:
*""People exposed" or "Namespaces at risk" recomputed over one person keeps its label and changes its
meaning — the count-versus-page defect made permanent (requirements Q5) — so none of the wide view's
aggregates render here at all."*

Three columns (`Grants · Scope · Binding`), a `scopeBanner`, and the closing note *"A direct grant
survives offboarding. Consider asking for the equivalent group membership and having the binding
removed — the runbook on the administrator's view of this tab is the same one that applies to yours."*

With no rows — measured as `alice.cooper`, `total: 0` — the empty note is *"No role is granted directly
to **alice.cooper** on this cluster. Your access, if any, arrives through synced groups — the goal state
this audit exists to reach. This says nothing about whether OTHER accounts hold direct grants; that
worklist is the administrator tier."*

### `refusalCard` — withheld, not empty

*"**Withheld, not empty.** The per-namespace worklist of direct user grants names people and their
access. **For administrators only.** Nothing on this page is broken and nothing is missing from the
cluster — this view is simply not part of yours."*

**Not reachable on this lab, and the reason is measurable.** `/user-bindings` self-scopes rather than
refusing; it 403s only when there is no viewer to key the rows on, which needs a cluster whose policy is
`self-only` with `identity: none`. All five enabled clusters are `visibility: inherit` /
`identity: same-as-host` (measured from `/api/clusterconfigs`). The endpoint's answer with no identity
at all, measured: `this data is scoped to the authenticated viewer, and there is no authenticated
identity to scope it to`.

The namespace page's refusal **is** reachable and was measured: `GET …/namespaces/legacy-payments` as
`jeff` answers 403 — `this namespace is outside your view; namespace detail beyond your own grants needs
the wide tier` — and renders `refusalCard` with a back button and the sentence *"Only namespaces your
own memberships or grants reach are visible at your tier. This one is outside your view — or does not
exist; the two are deliberately indistinguishable."*

## The shell and the cross-cutting machinery, as this page uses it

| control | measured on this page |
|---|---|
| Cluster selector | `#f-cluster`, five options, `dashboard-rnd` selected — a position, part of the URL |
| Find namespace | `#f-ns-search`, placeholder `filter by name or label`, multi-word AND, Escape clears. **It filters the Namespaces card only** — the audit's own tables are untouched by it |
| Export | `CSV` / `JSON` plus a row count, measured `11 rows`. Title on both: *"Downloads exactly the rows this page holds, after the filter and sort — never more than the server served you."* |
| Scope pill | measured `Full view — you are seeing everything` |
| Version | measured `v0.30.0 · a90f1b277b`, beside `updated 01:08:14 EDT` |
| Appearance / Colours | `#pref-mode` (Auto/Light/Dark), `#pref-palette` (Default + three colour-vision palettes + High contrast) |
| Refresh / Sign out | `#refresh`, `#logout` |

The export descriptor for this tab (`local-development/gsd/static/index.html#function exportDescriptor`)
was measured directly: `tab: "namespace-audit"`, `served: 11`, `total: 11`, `scope: "all"`,
`filter: {namespace: "all"}`, `sort: {key: "risk", dir: "desc"}`, and seven columns —
`user_name, role_kind, role_name, binding_kind, binding_namespace, binding_name, is_platform`. **The
namespace page returns `null`**: *"offering the audit's direct-grants export there exported rows the
reader was not looking at"*. At the self tier the envelope names the server's own order rather than the
page's, because a narrowed reader's rows are painted as served.

## What `/metrics` carries about this page

Nothing countable. There is no `gsd_user_bindings_total` series; `gsd_bindings_total` counts
**group**-subject bindings by finding. The only public trace of this page's finding is one alert per
cluster — measured `gsd_alerts_total{cluster="dashboard-rnd",kind="direct_user_binding",severity="warning"} 1.0`.
So unlike the Cluster Overview's tiles, nothing here is already public, and the administrator tier on
the worklist is not theatre.

## Three things the capture turned up

Recorded here because they are measurements, not opinions; what to do about them is the redesign's
business.

1. **The worklist is a dead end.** The `Namespace` cell is `<strong>`, not a button: measured
   `buttons_in_row: []`, `data-ns` attributes in the row: `0`. Every other place a namespace appears on
   this page drills; the ranked worklist — the view the page says to work from — does not.
2. **The page's only filter box reaches its last card only.** Typing `legacy` left the audit table at
   its full row count and the KPIs unchanged while the Namespaces card went to `2 of 106 shown`.
3. **Seventy per cent of the page is the namespace index.** Measured at 1280×1000: document height
   5153 px, of which the Namespaces card is 3619 px starting at y=1456 — 106 rows under a 5-row
   worklist.

Also measured, and smaller: the `Who is exposed` cell separates names with a 6 px margin and no
character, so its text content reads `asmithbwilliamsjdoe` — what a reader copies, and what an
assistive technology reads, has no separator.
