# Tab feature contract — what a redesign may not remove

Taken from the rendered DOM of the running dashboard (Playwright, logged in as an administrator on
`crc-local`) **and** from the render functions in `local-development/gsd/static/index.html`. Every item
below exists today. A redesign of these tabs (#153) may re-lay-out, re-style and add — it may **not**
silently drop anything here.

**Why this file exists.** A first blueprint pass reduced these pages to headline + KPIs + a table, and
in doing so deleted most of their value. The tables are not the product. The product is the
**explanatory text** that tells a reader what a number does and does not mean — a body of hard-won
domain knowledge that is invisible in a screenshot and irrecoverable once removed.

## The cross-cutting machinery

- **Shared filter bar** (`renderFilters()`), rebuilt on every 60s repaint. It **restores focus and caret
  by element id** and skips the rebuild during an IME composition. Any redesign that moves a control
  into a repainting region inherits this problem — the existing solution is load-bearing.
- **Export (CSV/JSON)** on Users, Groups, Access granted, Namespace audit and Logins — with a row-count
  note that distinguishes a complete export from a partial one, and a JSON envelope that says which it
  is. **Not** on RBAC policy, Usage, Overview or any drill-down.
- **Scope pill** with three distinct states, including *"restrictions are off for this deployment"* —
  which deliberately does not claim the reader holds a permission.
- **`refusalCard`**: *"**Withheld, not empty.** … **For administrators only.** Nothing on this page is
  broken and nothing is missing from the cluster — this view is simply not part of yours."*
- **Badges carry a shape glyph plus text**, never colour alone.
- **Loading is a real state** — pages fail closed rather than rendering an empty truth.

## Per tab — the parts that carry meaning

### Groups
Columns `Name · Members · Owner · Last refreshed · Source DN`. Server-side state filter
(`all/empty/unattributed`) with a distinct note per state. Owner renders a stable per-CR colour dot
assigned by the provider's global position, **not** by filter position. Empty states distinguish *"the
search is hiding them"* from *"the data is empty"*, and quote the denominator.

### Users
KPIs `Have logged in · In a synced group · Logged in, no synced group · Synced, never logged in`.
Columns `User · Status · Provider · Groups · Last login · First seen in a group`. Provider chips.
**The `identitiesNote` has four mutually exclusive variants** (`ok` / `forbidden` / `pending` / `off`)
and the `approx.` chip explains that the User creation time is *"earlier than it for an account created
by hand and linked later"*. Truncation note states the cut **and that search only sees the loaded rows**.

### Access granted
Sections `Dangling · Unresolved · Unmanaged · Granted · Built-in`, each with its own explanatory note —
including that unresolved findings *"do not raise alerts: a group that has never been seen cannot be
told apart from one that simply has not synced yet"*. Five **sortable** columns
(`Group named by the binding · Reaches · Grants · Scope · Binding`). `Reaches` renders member count
**and how many have ever logged in**; `0 members` is an error state. Group names are drillable **only**
for findings where a Group object exists, each non-drillable case carrying a title saying why.
Standing caveat: *"Role rules are **not** evaluated, so this is what has been granted, not a computed
list of permitted actions."*

### RBAC policy
KPIs `Policy CRs · Unmanaged · Audit-stamped`. `configHealth` table (`Kind · Name · State · Last
success`) **survives the refusal card** — CR health is governance data. Distinct "operator not
installed" state. The `oc get ... -l rbac.ocp.io/unmanaged=true` hint appears **only** when something is
audit-stamped. Shares `bindingTable` (and its sort state) with Access granted — one component, two tabs.

### Namespace audit

Captured late — #153 named this page a reference and skipped it, so the one page the contract calls a
reference is the one page whose features were never written down. The full inventory, measured off the
running dashboard, is `docs/design/nsaudit-feature-capture.md`; what a redesign may not remove is here.

Six cards: `Namespace audit` (the verdict), `Why this is a risk`, `Exposure by namespace`, `How to close
it`, `Every grant`, `Namespaces`. The last one is a different subject from the other five — the whole
namespace index, 106 rows on the reference cluster — and it is the third drill-down, so it stays.

KPIs `Namespaces at risk · People exposed · Grants to migrate · Critical · High`, **all five from the
per-namespace rollup, which the server neither pages nor filters**. `People exposed` is the *union* of
the rollup's name lists and not the sum of its `distinct_users`: the sum double-counts anyone with
grants in more than one namespace (measured: 11 against a truth of 8). `Grants to migrate` is summed the
same way, because a count taken from the paged list below *"shrinks when the reader narrows the filter,
which reads as the problem getting smaller because they looked at it closely"*. Narrowing the detail list
must leave all five unmoved.

`riskTier`'s ranking is the page's argument and must survive intact: **privilege and scope, never
count** — *"one forgotten cluster-admin outranks twenty view grants, and a page sorted by volume puts the
twenty first and buries the one"*. Four tiers, each carrying its **word** beside its colour.

`Exposure by namespace` has six columns (`Risk · Namespace · Highest privilege · People · Grants · Who is
exposed`), five of them sortable through a `<button>` in the `<th>` with `aria-sort`, and a **Restore
risk order** control that appears only when the order is not the default. `Who is exposed` is bounded by
`WHO_PREVIEW` = 4 with an honest `+N more`, and the bound's reasoning is load-bearing: the names are
*"corroboration"*, the full roster is one section down, and an unbounded column *"would decide the width
of the whole table — on the view that is supposed to be the scannable one"*.

`Every grant` is **collapsed by default** — *"on a cluster with thousands of direct grants rendering
every row costs time nobody gets value from"* — behind a disclosure that states the server's `total`
rather than the rendered count. Its namespace selector is a **server-side** filter that opens the
disclosure with it, its sort ranks roles by privilege and not alphabetically, and its truncation note
says the rest are *"not hidden findings — they are ranked below these"*.

The runbook's five steps are the tab's other half: identify the role by the naming convention, add the
person to the group, **wait one sync** (*"deleting first leaves them locked out"*), delete the binding,
confirm. It ends on the sentence the page is for — *"**Operational goal:** zero rows on this page"* — and
the zero state is a page of its own, not an empty table.

Two exclusions are stated rather than silent: the platform count (*"system components and `kubeadmin` are
break-glass … with nowhere to migrate to"*), and the platform folding on the namespace page (*"the
deployed demo-prod page listed 54 bindings, 41 of them these"*; `system:image-pullers` in every namespace
would make *"zero in both"* impossible).

The index's empty states distinguish three things and must keep doing so: *"the search is hiding
them"* (quoting the denominator — *"All 106 are still there"*), *"No namespaces recorded for this
cluster yet"*, and the self tier's *"That is your view, not the cluster"*. A refused namespace read is
a fourth: the list *"cannot attest absence"* and says so rather than looking complete.

The namespace page (`nsDetail`) is part of this tab: labels as KPIs with the *"outside the naming
convention, so no mnemonic-based report will ever pick it up"* note, `Who reaches it, and through which
group`, the cluster-wide reach, `Direct grants` with the operational-goal-is-zero line, the sibling
namespaces, and `History` with its first-observed / granted / revoked vocabulary. It carries **no
export**, deliberately: offering the audit's export there *"exported rows the reader was not looking
at"*.

**Visibility.** `/user-bindings` is **self-scoped, not refused** — a reader's own grants are theirs to
see — so the narrowed page renders `selfGrantsView` and **none of the wide view's aggregates**: a KPI
recomputed over one person *"keeps its label and changes its meaning"*. The refusal card is reached only
where there is no identity to key the rows on. Nothing on this page is on `/metrics`: the only public
trace is one `gsd_alerts_total{kind="direct_user_binding"}` per cluster, so unlike the Cluster Overview
this tier is not theatre.

### Logins
The richest page in the product. Capture-off, nothing-recorded (three sub-variants), and normal states.
A **stalled-capture** warning computed from the read interval. A window banner stating that
*"the oauth-server's log dies with its pod and cannot be read backwards"*. Ten outcome labels with
severities, three refusal badges each with its own reasoning, and chips for `break-glass`,
`local provider`, `not in access group`. The `Replica` column becomes `Node` when the source is the
audit log. Cluster-access panel with four mutually exclusive shapes, plus `Access that cannot be used`
and `Allowed to log in, holds no access`. The table footnote explaining what **No match** cannot
distinguish is among the most valuable paragraphs in the product.

### Usage
Cluster selector **deliberately omitted** (usage is a property of the dashboard, not a cluster).
KPIs `Distinct users · Days recorded · Interactions · Retention`, all from whole-set server summaries —
never counted from the visible page. The standing footnote explains that `Day` is a **UTC bucket** while
times are server-zone, and that *"an interaction is one deliberate action … not one HTTP request"*.

### The persistent shell  (operator, 2026-09-17: "don't forget the refresh and logout button and our current settings")

Every page renders **inside** the shell (`header.top` + `.filters` + `#main`), and the shell is not a tab —
a redesign of any page inherits it and may not drop it. Measured on the live app, in `index.html` — the `header.top` markup, the `refresh()` and sign-out
handlers, and the settings control they sit beside — and on the mocks: two of eight carried these; six had silently lost Refresh and
Sign out.

| control | live element | what it is |
|---|---|---|
| **Refresh** | `button#refresh` | a manual poll of the current page's data, beside the automatic 60 s repaint |
| **Sign out** | `a#logout` (shown behind the proxy) | ends the oauth-proxy session |
| **Idle timeout** | the `Still there?` dialog — *Stay signed in* / *Sign out now* | `docs/DESIGN_session_and_signout.md`; a page may not hide or restyle it away |
| **Tier chip** | "Full view — you are seeing everything" / the narrowed wording | what the viewer is seeing, stated |
| **Version · updated** | `v0.24.0 · 52bba392b2 · updated 17:21:04` (`data.version`) | which build, and how fresh |
| **Cluster selector** | `select#f-cluster` | a **position** — part of the URL, travels with Back |
| **Group state** | `select#f-state` (Groups page) | `all / synced / unattributed` — a filter, not a position |
| **Find** | `#f-group-search`, `#f-user-search`, `#f-member-search`, `#f-binding-search` | the pattern boxes, multi-word AND, Escape clears |
| **Appearance · Colour** | the two selects, in the shell, never in `renderFilters()` | global; `?mode=` / `?theme=` (#152) |

The rule: a page mock carries the shell **verbatim**, with every control present even where the page does
not use it — the shell is the one thing a reader must be able to find on every screen.

### Cluster Overview  (operator ruling, 2026-09-17: keep as-is, do not redesign)

*"I love it … we cannot afford to lose them. We can just create a new KPI panel and keep what we
design there. No need to litigate that again."* This page is settled. A KPI redesign adds a **new**
page; it does not reshape this one.

Three cards, all of which must survive:

1. **One card per connected cluster** (`crc-local`, `mock` today). These are already the tiles the
   page grows into as clusters are added — the position `#page=overview&cluster=<id>` exists today,
   so making a tile clickable needs no new navigation model.
2. **GroupSync CRs** — `NAME · STATE · SCHEDULE · GROUPS · LAST SYNC · NEXT EXPECTED`. `state`,
   `next_expected` and `error_is_current` are computed per request, never stored: a stored state is
   wrong the moment the clock moves past it.
3. **Policy operator (NamespaceConfig / GroupConfig)** — `KIND · NAME · STATE · LAST SUCCESS`, with
   the note that *"a currently-failing one means RBAC has quietly stopped reconciling — new
   namespaces receive nothing"*. That sentence is the reason the card exists.

**Visibility, measured against `api.py` rather than assumed** — relevant because opening this page
has been raised. It is not uniform:

| card | tier | why |
|---|---|---|
| cluster cards + counts | every tier | already on the unauthenticated `/metrics` (`gsd_groups_total`, `gsd_bindings_total{finding=…}`); withholding would be theatre |
| GroupSync CRs | every tier | `/metrics` is in the chart's `skipAuthRegex` and already serves `gsd_groupsync_state`, `gsd_groupsync_last_sync_timestamp_seconds`, `gsd_groupsync_groups_total` per CR |
| Policy operator | **administrator only** | `require_admin_tier`. No `/metrics` analogue exists, so this is a genuinely private aggregate — an explicit reversal (03ad446) of the earlier "governance data about objects" ruling |

Two fields are delivered but never rendered, and are omitted at the self tier: `ldap_filter` and
`error_message`, because both can embed directory DNs and the gate group. `refresh()` fetches
`/groupsyncs` inside `if (view.cluster)` — true on **every** page — so a narrowed reader's browser
downloads this payload whichever tab they are on. "The Overview tab is admin-only" never protected
them.

## The rule

Redesign the layout. Keep the words. Where a note is moved behind a disclosure, it must still be
reachable — a caveat a reader cannot find is a caveat that was deleted.
