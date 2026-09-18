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

## The rule

Redesign the layout. Keep the words. Where a note is moved behind a disclosure, it must still be
reachable — a caveat a reader cannot find is a caveat that was deleted.
