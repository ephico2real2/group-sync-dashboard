# SPEC C1 — CSV and JSON export of the table on screen

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | C — product |
| Release | R3 — Product wins |
| Version on release | app 0.14.0, chart 0.14.0 |
| Issue | [#61](https://github.com/ephico2real2/group-sync-dashboard/issues/61) |
| Status | specified |
| Source | design agent output `a836ef1bc0058551a`; two messages; the first ended inside a ```sh fence and the second began with two fence lines (a closer and a stray duplicate), so one duplicate fence line was dropped |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- First feature of R3: app 0.14.0, chart 0.14.0; the body's version numbers are superseded. Default answer to the design's question 1: exports are not recorded in `dashboard_user_activity` (client-side action).

## Batch preamble (verbatim from the design)

# Design: four modules for the OCP Access Tracking Dashboard

Every claim below is grounded in a file read in this session, cited as `path#anchor`. Nothing was written or edited.

## 0. Cross-cutting decisions

### 0.1 The switches and their defaults (operator amendment applied)

| Module | Chart value | ConfigMap key → `Settings` field | Default | Why that default |
|---|---|---|---|---|
| C1 CSV/JSON export | `ui.export.enabled` | `uiExportEnabled` → `ui_export_enabled` | **true** | Client-side, makes no request, needs no grant, exports only rows the server already served this reader. Off keeps files off the page for a platform team that wants that. |
| C4 Idle timeout | `session.idleTimeout.{enabled,minutes,warningSeconds}` | `sessionIdleTimeout{Enabled,Minutes,WarningSeconds}` → `session_idle_timeout_{enabled,seconds,warning_seconds}` | **false** / 30 / 60 | A session policy the platform team chooses; it signs people out. Chart refuses it without the proxy (no session to end) and when it can never fire (idle ≥ `oauthProxy.cookie.expire`). |
| C2a Provider allow-list | `config.users.providers` | `usersProviders` → `users_providers` | **`[]`** (= all) | A value that is simply empty; nothing changes until a name is listed. |
| C2b Exact first login | `rbac.identities` | `identitiesReadEnabled` → `identities_read_enabled` | **false** | Extra RBAC (`get,list identities.user.openshift.io`), which the chart's `rbac.yaml` does not grant today. |
| C3 Namespace report (HTML core) | `features.namespaceReport.enabled` | `namespaceReportEnabled` → `namespace_report_enabled` | **false** | A new administrator-tier surface and a new tab section; a policy choice. Refused without `rbac.bindings`. |
| C3 Absence attestation | `rbac.namespaces` | `namespacesReadEnabled` → `namespaces_read_enabled` | **false** | Extra RBAC (`get,list namespaces`, core group). |
| C3 PDF module | `features.namespaceReport.pdf.{enabled,image.*,variant,resources}` | `namespaceReportPdfUrl` → `namespace_report_pdf_url` | **false** | A second image (WeasyPrint and its C libraries) as a sidecar. Refused without `features.namespaceReport.enabled`. |

Pure-UI flags reach the page the way `timezone` does: `gsd/api.py#version` gains a `features` object read by `index.html` at boot (`data.version`). Session-shaped config reaches the page the way `cookie_expire_seconds` does: inside `session` on `/api/whoami` (`gsd/api.py#whoami`), present only when `authenticated`.

### 0.2 PR order and versions

Current: app `0.11.0` (`local-development/pyproject.toml`, `gsd/__init__.py`), chart `0.10.0` (`Chart.yaml`). Every PR touches `charts/`, so every PR bumps the chart (`.github/workflows/ci.yml` "Chart changes bump the chart version") and moves the app triple together (`tests/test_chart_versions.py`).

| PR | Module | App | Chart | Why this order |
|---|---|---|---|---|
| 1 | C1 export | 0.12.0 | 0.11.0 | Introduces `downloadBlob`, the `features` block on `/api/version`, and the row-selection helpers C3 reuses. |
| 2 | C4 idle timeout | 0.13.0 | 0.12.0 | Independent; touches `whoami` and the poll loop only. |
| 3 | C2 providers + identities | 0.14.0 | 0.13.0 | Migration 8. |
| 4 | C3 namespace report + PDF module | 0.15.0 | 0.14.0 | Migration 9; reuses PR1's helpers; second image `group-sync-dashboard-report:0.15.0`. |

Each PR: bump `pyproject.toml` `version`, `gsd/__init__.py` `__version__`, `Chart.yaml` `version` + `appVersion` + a history comment, a `docs/CHANGELOG.md` section, chart README rows.

### 0.3 Conventions every PR follows

- Config keys parse through `gsd/config.py#_bool_setting` / `_num_setting` (env wins over ConfigMap), strict where a wrong value is a security consequence, fallback-with-warning where it is not — the discipline `_duration_setting`'s docstring states.
- Chart helpers are nil-safe (`default dict` on every hop, never `dig` — `_helpers.tpl#gsd.cookieExpire` explains why) and refuse bad shapes at render time.
- New endpoints: GET, docstring whose first line stands alone (R1), every `Query` described (R2), `total`/`truncated` beside any `limit` (R3), `@consistent` for more than one store call (R5) — `docs/api-contract.md`, enforced by `tests/test_api_contract.py`. Every new path is added to `local-development/API.md` (`test_every_endpoint_appears_in_api_md`).
- Visibility: nothing is exported or reported except what `viewer_scope`/`require_admin_tier` served. C1 exports from `data` (what arrived on the wire for this reader); C3's endpoints sit behind `require_admin_tier` exactly like `/bindings/findings`.
- UI: one file, no build step; colours only via `app.css` tokens (`tests/test_accessibility.py`), sizes only via `--text-*` (`tests/test_type_scale.py`), every control a real `<button>`/`<a>`/`<input>`, ids on anything focus must survive the 60 s repaint (`index.html#function renderFilters` restore-by-id), Playwright tests following `tests/test_ui.py`'s fixtures.

---


## Design (verbatim)

## C1 — CSV and JSON export of the table on screen

### Goal and the switch

Export exactly the rows the browser holds for the current table, after the page's own filter and sort, as RFC 4180 CSV or as a JSON envelope that names the cluster, tab, tier, filter, sort and truncation — generated in the browser from `data`, downloaded through a Blob and an `<a download>`. Switch: `ui.export.enabled` (default **true**), served as `features.export` on `/api/version`; off, the filter bar renders no export control and an install sees no change.

### Decision: client-side export, not a `GET /api/…/export`, not recorded in `dashboard_user_activity`

Compared:

| | Client-side Blob (chosen) | Server-side `GET /api/clusters/{id}/<tab>/export` |
|---|---|---|
| Exports "what was served after filter and sort" | Yes by construction: the filter (`index.html#function matchesSearch`, chips) and sort (`sortBy`) are client-side; the export reads the same arrays the table paints. | No: the server does not know the client filter/sort; it would export a different set from the one on screen, or the six filter/sort rules would have to be re-implemented server-side. |
| Tier safety | Cannot widen: the browser only holds what `viewer_scope`/`require_admin_tier` served. | A seventh scoping path that must be kept identical to six handlers — the shape `gsd/api.py#SKIP_AUTH_PATHS` records as the one that drifted and was exploitable. |
| `@consistent` | n/a | Streaming is forbidden inside a snapshot (`gsd/api.py#consistent`: "must not stream, yield or await"), so the CSV would be fully materialised anyway. |
| Session | No request. | Every request re-stamps the proxy cookie (`docs/DESIGN_session_and_signout.md` §"What ships") and, with `X-GSD-Interaction`, counts. |

Audit: `dashboard_user_activity` is one row per user per UTC day with a request count, "deliberately not a page-view log" (`charts/group-sync-dashboard/values.yaml#userActivity`, `gsd/api.py#record_dashboard_use`). An export is a client action over rows whose serving request was already counted (the tab fetch carries the interaction mark, `index.html#async function refresh`). Recording "an export happened" would need a per-action event kind — the thing that table was designed not to be — and a synthetic request to carry it would be the page talking to itself, which the interaction header exists to exclude. So exports are **not** recorded, the design doc says so, and the JSON envelope carries `exported_at`, `viewer` and `scope` so the file itself states its provenance. (Operator question Q1 below records the alternative.)

UTF-8 BOM: **CSV carries the BOM, JSON does not.** The consumer the report designs name is a spreadsheet in an access review (`docs/namespace-report-design.md` §6); Excel opens BOM-less UTF-8 as the local code page and mangles a non-ASCII `full_name` from the directory, while every programmatic reader accepts `utf-8-sig`. JSON must not carry one (RFC 8259 §8.1). Formula-injection: a string cell beginning `= + - @ \t \r` is prefixed with `'` (OWASP CSV injection mitigation); directory-supplied text is already treated as hostile for HTML (`index.html#function esc`, the crafted-hash test), and a display name is the same source. This is the only transformation and the design doc says so.

Filename: `gsd_<cluster>_<tab>[_self][_partial]_<YYYYMMDDTHHMMSSZ>.<csv|json>`. `_self` when the payload declared `scope: "self"`; `_partial` when the server said the page is a cut of a larger set (`truncated`, `total` — R3 fields already on `/users`, `/bindings/findings`, `/user-bindings`, `/logins`). The note beside the buttons says the same.

### Files

#### `local-development/gsd/config.py` — edit

OLD:
```python
    user_activity_enabled: bool = True
    # "self" | "all". Who may read /api/dashboard/activity. Defaults to self, because the
```
NEW:
```python
    # ── OPTIONAL MODULES ───────────────────────────────────────────────────────────────────────────
    # Each module has its own switch; the default is chosen per module and the values comment
    # says why. CSV/JSON export (docs/DESIGN_export.md) is ON: it runs in the browser over rows
    # the server already served this reader, makes no request and needs no grant. Off removes
    # the control from the filter bar and nothing else changes.
    ui_export_enabled: bool = True

    user_activity_enabled: bool = True
    # "self" | "all". Who may read /api/dashboard/activity. Defaults to self, because the
```

OLD:
```python
        user_activity_enabled=_bool_setting(
            raw, "GSD_USER_ACTIVITY_ENABLED", "userActivityEnabled", True
        ),
```
NEW:
```python
        user_activity_enabled=_bool_setting(
            raw, "GSD_USER_ACTIVITY_ENABLED", "userActivityEnabled", True
        ),
        ui_export_enabled=_bool_setting(raw, "GSD_UI_EXPORT_ENABLED", "uiExportEnabled", True),
```

#### `local-development/gsd/api.py` — edit (`version`)

OLD:
```python
    @app.get("/api/version")
    def version() -> dict:
        """What is actually running, provable back to a commit.

        Stamped into the image at build time. `dirty: true` means the build included
        uncommitted changes, so no commit reproduces it — which is the honest answer when
        someone asks "is my fix in there?".
        """
        commit = os.environ.get("GSD_GIT_COMMIT", "unknown")
```
NEW:
```python
    def feature_flags() -> dict:
        """Which optional modules this deployment switched on, for the page to show or hide.

        The page reads this ONCE at boot beside `timezone`, exactly as it learns the display
        zone: a fact about the deployment, not about the reader. A module absent from this
        dict on an older build renders nothing — every check on the page is `=== true`.
        Session-shaped modules (the idle timeout) ride /api/whoami's `session` instead,
        because they only exist when there is a session.
        """
        return {"export": settings.ui_export_enabled}

    @app.get("/api/version")
    def version() -> dict:
        """What is actually running, provable back to a commit.

        Stamped into the image at build time. `dirty: true` means the build included
        uncommitted changes, so no commit reproduces it — which is the honest answer when
        someone asks "is my fix in there?". `features` names the optional modules switched on
        for this deployment (docs/DESIGN_export.md), so the page renders a control only where
        the operator enabled it.
        """
        commit = os.environ.get("GSD_GIT_COMMIT", "unknown")
```

OLD:
```python
            "dirty": commit.endswith("-dirty"),
            "timezone": {
```
NEW:
```python
            "dirty": commit.endswith("-dirty"),
            "features": feature_flags(),
            "timezone": {
```

#### `charts/group-sync-dashboard/values.yaml` — add, before the `# Clusters to observe.` comment

```yaml
# ---------------------------------------------------------------------------
# Dashboard UI modules
# ---------------------------------------------------------------------------
# Each optional module has its own switch. The default is chosen per module — on when it is
# cheap, safe and needs nothing extra; off when it needs a grant, another image, or is a
# policy the platform team should choose — and the comment on each says which.
ui:
  export:
    # CSV and JSON download of the table on screen: Users, Groups, Access granted, Namespace
    # audit and Logins. Built IN THE BROWSER from the rows the server already served this
    # reader, after the page's own filter and sort, so it can never contain a row the reader's
    # tier withheld; it makes no request and needs no grant, which is why it defaults ON. The
    # file names the cluster, tab, tier and UTC time, and says when the page was a cut of a
    # larger set (`_partial` in the name, `truncated` in the JSON) so a spreadsheet never implies
    # completeness. Exports are not recorded: the Usage tab counts interactions per day, not
    # actions (docs/DESIGN_export.md). Set false to keep the control off the page.
    enabled: true

```

#### `charts/group-sync-dashboard/templates/configmap.yaml` — edit

OLD:
```yaml
    userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}
```
NEW:
```yaml
    userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}
    # The UI modules (values.yaml `ui`). Read at boot from /api/version; a module off here
    # renders no control at all rather than a disabled one.
    uiExportEnabled: {{ .Values.ui.export.enabled }}
```

#### `local-development/gsd/static/app.css` — append after the `td.num.warn` rule

```css
/* ---- Export (docs/DESIGN_export.md) ---------------------------------------------------
   Two real buttons in the filter bar and a note that states what the file will hold. The note
   wears the truncation edge whenever the page is a cut of a larger set, so "partial" is read
   before the download, not discovered in the spreadsheet. Tokens only: the contrast tables in
   tests/test_accessibility.py already cover every colour used here. */
.export { display: inline-flex; align-items: center; gap: 6px; }
.export-label { color: var(--text-secondary); font-size: var(--text-sm); }
.export-note { font-size: var(--text-sm); color: var(--text-muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.export-note.partial {
  color: var(--text-primary); padding: 1px 8px;
  border-left: 3px solid var(--status-warning);
  background: color-mix(in srgb, var(--status-warning) 8%, transparent);
  border-radius: 0 6px 6px 0;
}
```

#### `local-development/gsd/static/index.html` — edits

(a) Users page: share the row selection. OLD (in `usersPage`):
```js
  const all = d.users || [];
  const self = d.scope === "self";
  const never = { count: (d.never_logged_in_members || {}).count || 0,
                  names: Array.isArray((d.never_logged_in_members || {}).names) ? d.never_logged_in_members.names : [] };
  const provs = (u) => Array.isArray(u.providers) ? u.providers : [];
  const captureOn = d.login_capture !== "off";
  // Chips: a whole-row predicate; the search box narrows further. Provider chips come from the
  // rows themselves, so a cluster with one identity provider shows one.
  const providers = [...new Set(all.flatMap(provs))].sort();
  const chip = view.userFilter || "all";
  const byChip = (u) => chip === "all" ? true
    : chip === "grouped" ? (u.group_count || 0) > 0
    : chip === "nogroup" ? (u.group_count || 0) === 0
    : chip.startsWith("provider:") ? provs(u).includes(chip.slice(9))
    : true;
  // Both fields, so a reader who knows only the display name still finds the id — which is what
  // they need next, because the id is what `oc` and the group members answer to.
  const matched = all.filter((u) => byChip(u) && matchesSearch([u.user_name, u.full_name], view.userSearch));
```
NEW:
```js
  // The row selection is SHARED with the export (usersMatched): the table and the file it
  // downloads read one function, so they cannot disagree about which rows "shown" means.
  const { all, matched, provs, chip } = usersMatched(d);
  const self = d.scope === "self";
  const never = { count: (d.never_logged_in_members || {}).count || 0,
                  names: Array.isArray((d.never_logged_in_members || {}).names) ? d.never_logged_in_members.names : [] };
  const captureOn = d.login_capture !== "off";
  // Chips: a whole-row predicate; the search box narrows further. Provider chips come from the
  // rows themselves, so a cluster with one identity provider shows one.
  const providers = [...new Set(all.flatMap(provs))].sort();
```

Insert immediately before `function usersPage() {`:
```js
/* The Users tab's row selection — chips, then the free-text box — written once so the table and
   the export (docs/DESIGN_export.md) read the same rows. Only the PAINT is capped (USERS_RENDER);
   this returns every match, which is what an export must carry. */
function usersMatched(d) {
  const all = d.users || [];
  const provs = (u) => Array.isArray(u.providers) ? u.providers : [];
  const chip = view.userFilter || "all";
  const byChip = (u) => chip === "all" ? true
    : chip === "grouped" ? (u.group_count || 0) > 0
    : chip === "nogroup" ? (u.group_count || 0) === 0
    : chip.startsWith("provider:") ? provs(u).includes(chip.slice(9))
    : true;
  // Both fields, so a reader who knows only the display name still finds the id — which is what
  // they need next, because the id is what `oc` and the group members answer to.
  const matched = all.filter((u) => byChip(u) && matchesSearch([u.user_name, u.full_name], view.userSearch));
  return { all, matched, provs, chip };
}

```

(b) Groups page. OLD (in `groupsPage`):
```js
  const rows = all.filter((g) => matchesSearch([g.name], view.groupSearch));
```
NEW:
```js
  const rows = groupsMatched().rows;
```
Insert before `function groupsPage() {`:
```js
/* The Groups tab's row selection, shared with the export for the same reason as usersMatched. */
function groupsMatched() {
  const all = data.groups || [];
  return { all, rows: all.filter((g) => matchesSearch([g.name], view.groupSearch)) };
}

```

(c) Access granted. OLD (in `bindingsPage`):
```js
  const q = view.bindingSearch || "";
  const searching = q.trim().length > 0;
  const f = raw && !raw.forbidden ? Object.fromEntries(
    ["ok", "dangling", "unresolved", "built_in", "unmanaged"].map((t) =>
      [t, (raw[t] || []).filter((r) => bindingMatches(r, q))])) : null;
  // Which tiers the selected filter paints — the search note's denominator, so it never
  // counts a match the reader cannot see (Built-in is hidden on the default view).
  const visible = ({ review: ["dangling", "unresolved", "unmanaged", "ok"], ok: ["ok"],
                     built_in: ["built_in"], unmanaged: ["unmanaged"] })[view.bindingFilter]
                  || ["dangling", "unresolved", "unmanaged", "ok", "built_in"];
```
NEW:
```js
  const q = view.bindingSearch || "";
  const searching = q.trim().length > 0;
  // The filtered tiers and which of them this filter paints, shared with the export.
  const { f, visible } = raw && !raw.forbidden ? bindingsVisible(raw) : { f: null, visible: [] };
```
Insert before `function bindingsPage() {`:
```js
/* Which binding rows the Access granted tab paints: every tier filtered by the Find box, and the
   tiers the "Show" filter admits, in the order the page lays them out. Shared with the export. */
const BINDING_TIERS = ["ok", "dangling", "unresolved", "built_in", "unmanaged"];
function bindingsVisible(raw) {
  const q = view.bindingSearch || "";
  const f = Object.fromEntries(BINDING_TIERS.map((t) =>
    [t, (raw[t] || []).filter((r) => bindingMatches(r, q))]));
  // Which tiers the selected filter paints — the search note's denominator, so it never
  // counts a match the reader cannot see (Built-in is hidden on the default view).
  const visible = ({ review: ["dangling", "unresolved", "unmanaged", "ok"], ok: ["ok"],
                     built_in: ["built_in"], unmanaged: ["unmanaged"] })[view.bindingFilter]
                  || ["dangling", "unresolved", "unmanaged", "ok", "built_in"];
  return { f, visible };
}

/* One sort for the binding table and its export. Rows with no Group object have nothing to say
   in Reaches; whichever way the column is sorted they go last, so a descending sort still starts
   with the biggest real group. */
function sortedBindings(rows) {
  const key = view.bindingSort, dir = view.bindingDir;
  let sorted = sortBy(rows, BIND_SORT[key] || BIND_SORT.group, dir);
  if (key === "reaches") sorted = sorted.filter((r) => r.member_count != null).concat(sorted.filter((r) => r.member_count == null));
  return sorted;
}

```
OLD (in `bindingTable`):
```js
  const key = view.bindingSort, dir = view.bindingDir;
  let sorted = sortBy(rows, BIND_SORT[key] || BIND_SORT.group, dir);
  // Rows with no Group object have nothing to say in Reaches; whichever way the column is
  // sorted they go last, so a descending sort still starts with the biggest real group.
  if (key === "reaches") sorted = sorted.filter((r) => r.member_count != null).concat(sorted.filter((r) => r.member_count == null));
  const th = (label, k, extra) => sortableTh(label, k, key, dir, "bind", extra);
```
NEW:
```js
  const key = view.bindingSort, dir = view.bindingDir;
  const sorted = sortedBindings(rows);
  const th = (label, k, extra) => sortableTh(label, k, key, dir, "bind", extra);
```

(d) Namespace audit. OLD (in `directUserGrants`):
```js
  const GRANT_SORT = {
    person: (b) => b.user_name,
    // Sort the ROLE by privilege, not alphabetically: "admin" < "edit" < "view" as text
    // puts the dangerous grants in the middle, which is the opposite of useful.
    risk: (b) => (PRIVILEGE_RANK[b.role_name] || 0) * 10 + (b.binding_namespace ? 0 : 1),
    scope: (b) => b.binding_namespace || "",
    binding: (b) => b.binding_name,
  };
  const sorted = sortBy(rows, NS_SORT[view.nsSort] || NS_SORT.risk, view.nsDir);
  const sortedGrants = sortBy(
    bindings, GRANT_SORT[view.nsGrantSort] || GRANT_SORT.risk, view.nsGrantDir);
```
NEW:
```js
  const sorted = sortBy(rows, NS_SORT[view.nsSort] || NS_SORT.risk, view.nsDir);
  const sortedGrants = grantsSorted(ub);
```
Insert after the `const PRIVILEGE_RANK = ...` line:
```js

/* The flat grant list's sort, at module scope so the table and its export share it. */
const GRANT_SORT = {
  person: (b) => b.user_name,
  // Sort the ROLE by privilege, not alphabetically: "admin" < "edit" < "view" as text
  // puts the dangerous grants in the middle, which is the opposite of useful.
  risk: (b) => (PRIVILEGE_RANK[b.role_name] || 0) * 10 + (b.binding_namespace ? 0 : 1),
  scope: (b) => b.binding_namespace || "",
  binding: (b) => b.binding_name,
};
function grantsSorted(ub) {
  return sortBy(ub.bindings || [], GRANT_SORT[view.nsGrantSort] || GRANT_SORT.risk, view.nsGrantDir);
}
```

(e) The export module. Insert immediately before `function sortableTh(` (after `sortBy`):
```js
/* ── Export: what was served, and nothing more (docs/DESIGN_export.md) ────────────────────
   The file is built HERE, from `data` — the rows the server served THIS reader at THEIR tier —
   after the page's own filter and sort, read through the same selection functions the tables
   paint from. It makes no request: a server-side export would have to re-implement six
   handlers' scoping and six pages' filters, and could export a set the reader never saw.
   Columns are an explicit projection per tab, so a payload field the page does not render is
   not smuggled out either. */
const EXPORT_COLUMNS = {
  users: ["user_name", "full_name", "logged_in", "first_login_at", "providers", "group_count",
          "last_login_at", "first_seen_at"],
  groups: ["name", "member_count", "sync_provider", "group_synced_at", "ldap_uid"],
  bindings: ["finding", "group_name", "member_count", "logged_in_count", "role_kind", "role_name",
             "binding_kind", "binding_namespace", "binding_name", "managed_source", "exception"],
  myaccess: ["via_group", "role_kind", "role_name", "binding_kind", "binding_namespace", "binding_name"],
  nsaudit: ["user_name", "role_kind", "role_name", "binding_kind", "binding_namespace", "binding_name",
            "is_platform"],
  logins: ["at", "user_name", "full_name", "outcome", "provider", "ldap_result_code", "detail",
           "pod_name", "known_user", "has_history", "in_access_group", "refusal_reason", "break_glass"],
};

function exportEnabled() {
  const v = data.version;
  return !!(v && v.features && v.features.export === true);
}

/* The table the current page holds, or null when the page has no exportable table (a drill-down,
   a refusal, a Loading state). `served` is how many rows the server sent; `total` the whole set
   it described (R3), or null when the endpoint does not page. rows < total is what "partial"
   means, and the note, the filename and the JSON all say it. */
function exportDescriptor() {
  if (!view.cluster) return null;
  const num = (x) => (typeof x === "number" ? x : null);
  if (view.page === "users" && !view.user) {
    const d = data.users;
    if (!d || d.forbidden) return null;
    return { tab: "users", columns: EXPORT_COLUMNS.users, rows: usersMatched(d).matched,
             served: (d.users || []).length, total: num(d.total), scope: d.scope || null,
             viewer: d.viewer || null,
             filter: { search: view.userSearch || "", chip: view.userFilter || "all" },
             sort: { key: "user_name", dir: "asc" } };
  }
  if (view.page === "groups" && !view.group && !view.user) {
    if (!data.groups) return null;
    const meta = data.groupsMeta || {};
    const { all, rows } = groupsMatched();
    return { tab: "groups", columns: EXPORT_COLUMNS.groups, rows, served: all.length, total: null,
             scope: meta.scope || null, viewer: meta.viewer || null,
             filter: { search: view.groupSearch || "", state: view.groupFilter },
             sort: { key: "name", dir: "asc" } };
  }
  if (view.page === "bindings") {
    if (narrowedReader()) {
      const m = data.myAccess;
      if (!m) return null;
      return { tab: "access-granted", columns: EXPORT_COLUMNS.myaccess, rows: m.bindings || [],
               served: (m.bindings || []).length, total: null, scope: "self", viewer: m.viewer || null,
               filter: {}, sort: { key: "binding", dir: "asc" } };
    }
    const raw = data.findings;
    if (!raw || raw.forbidden) return null;
    const { f, visible } = bindingsVisible(raw);
    return { tab: "access-granted", columns: EXPORT_COLUMNS.bindings,
             rows: visible.flatMap((t) => sortedBindings(f[t])),
             served: BINDING_TIERS.reduce((n, t) => n + (raw[t] || []).length, 0),
             total: num(raw.total), scope: raw.scope || "all", viewer: raw.viewer || null,
             filter: { search: view.bindingSearch || "", show: view.bindingFilter },
             sort: { key: view.bindingSort, dir: view.bindingDir } };
  }
  if (view.page === "nsaudit") {
    const ub = data.userBindings;
    if (!ub || ub.forbidden) return null;
    return { tab: "namespace-audit", columns: EXPORT_COLUMNS.nsaudit,
             rows: ub.scope === "self" ? (ub.bindings || []) : grantsSorted(ub),
             served: (ub.bindings || []).length, total: num(ub.total), scope: ub.scope || null,
             viewer: ub.viewer || null, filter: { namespace: view.nsNamespace },
             sort: { key: view.nsGrantSort, dir: view.nsGrantDir } };
  }
  if (view.page === "logins") {
    const d = data.logins;
    if (!d || !d.enabled) return null;
    const rows = d.attempts || [];
    return { tab: "logins", columns: EXPORT_COLUMNS.logins, rows, served: rows.length,
             total: num(d.total), scope: d.scope || null, viewer: d.viewer || null,
             filter: { outcome: view.loginOutcome }, sort: { key: "at", dir: "desc" } };
  }
  return null;
}

function exportIsPartial(desc) {
  return desc.total !== null && desc.served < desc.total;
}

/* RFC 4180: a field is quoted when it holds a quote, a comma or a line break, quotes are
   doubled, records end in CRLF. Arrays (providers) join with "; " — a semicolon can never be
   the delimiter of this file, so it is unambiguous. A string that a spreadsheet would EVALUATE
   (leading = + - @ tab CR) is prefixed with an apostrophe so it stays text: directory-supplied
   names are hostile input for HTML on this page (esc) and they are the same input here. Numbers
   and booleans are never touched. */
const CSV_BOM = "\ufeff";
function csvField(value) {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) value = value.join("; ");
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return String(value);
  let s = String(value);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  if (/[",\r\n]/.test(s)) s = '"' + s.replace(/"/g, '""') + '"';
  return s;
}
/* The BOM is deliberate for CSV and absent from JSON (RFC 8259 §8.1): a spreadsheet opened from
   a double-click reads BOM-less UTF-8 as the local code page and mangles a non-ASCII display
   name, while every programmatic reader accepts utf-8-sig. */
function toCsv(columns, rows) {
  const lines = [columns.map(csvField).join(",")];
  for (const r of rows) lines.push(columns.map((c) => csvField(r[c])).join(","));
  return CSV_BOM + lines.join("\r\n") + "\r\n";
}

/* gsd_<cluster>_<tab>[_self][_partial]_<UTC stamp>.<ext>. The cluster id is URL-safe already
   (config.py refuses a slash) and is reduced to a filename-safe alphabet here anyway. */
function exportFilename(desc, ext) {
  const safe = (s) => String(s || "").replace(/[^A-Za-z0-9._-]+/g, "_");
  const stamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\.\d{3}Z$/, "Z");
  return `gsd_${safe(view.cluster)}_${desc.tab}${desc.scope === "self" ? "_self" : ""}`
    + `${exportIsPartial(desc) ? "_partial" : ""}_${stamp}.${ext}`;
}

/* A Blob and an <a download>: no server round trip, no new window. The object URL is revoked
   after the click has had its tick — revoking synchronously cancels the download in Firefox. */
function downloadBlob(text, filename, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function runExport(format) {
  const desc = exportDescriptor();
  if (!desc) return;
  const partial = exportIsPartial(desc);
  // A projection into NEW objects: exactly the declared columns, absent keys as null.
  const rows = desc.rows.map((r) => Object.fromEntries(
    desc.columns.map((c) => [c, r[c] === undefined ? null : r[c]])));
  if (format === "csv") {
    downloadBlob(toCsv(desc.columns, rows), exportFilename(desc, "csv"), "text/csv;charset=utf-8");
    return;
  }
  const v = data.version || {};
  const doc = {
    exported_at: new Date().toISOString(),
    dashboard: { version: v.version || null, commit: v.commit || null },
    cluster: view.cluster,
    tab: desc.tab,
    scope: desc.scope,
    viewer: desc.viewer,
    filter: desc.filter,
    sort: desc.sort,
    count: rows.length,
    served: desc.served,
    total: desc.total,
    truncated: partial,
    note: partial
      ? `partial: the page held ${desc.served} of ${desc.total} rows the server described; `
        + `rows past the page were never loaded and are not here`
      : "every row the server served for this view, after the page's own filter and sort",
    columns: desc.columns,
    rows,
  };
  downloadBlob(JSON.stringify(doc, null, 2), exportFilename(desc, "json"), "application/json");
}

/* The filter-bar control. Rendered by renderFilters when the module is on and the page holds an
   exportable table; the note states the row count and wears the truncation edge when the page
   is partial, so "partial" is read before the download rather than discovered after it. */
function exportControlHtml() {
  if (!exportEnabled()) return "";
  const desc = exportDescriptor();
  if (!desc) return "";
  const partial = exportIsPartial(desc);
  const n = desc.rows.length;
  const help = "Downloads exactly the rows this page holds, after the filter and sort — never more than the server served you.";
  return `<span class="export" role="group" aria-label="Export this table">
      <span class="export-label" id="export-label">Export</span>
      <button type="button" id="export-csv" title="${esc(help)}" aria-describedby="export-note">CSV</button>
      <button type="button" id="export-json" title="${esc(help)}" aria-describedby="export-note">JSON</button>
      <span id="export-note" class="export-note${partial ? " partial" : ""}">${partial
        ? `${n} row${n === 1 ? "" : "s"} · partial: ${desc.served} of ${desc.total} loaded`
        : `${n} row${n === 1 ? "" : "s"}`}</span>
    </span>`;
}

```

(f) Filter bar. OLD (in `renderFilters`):
```js
  // aria-current, not just a class: it is what tells a screen reader which section is
  // open. The visual bar and the bolder label are the sighted half of the same signal.
```
NEW:
```js
  html += exportControlHtml();
  // aria-current, not just a class: it is what tells a screen reader which section is
  // open. The visual bar and the bolder label are the sighted half of the same signal.
```
OLD:
```js
  const of = $("f-outcome");
  if (of) of.onchange = (e) => { view.loginOutcome = e.target.value; refresh(); };
```
NEW:
```js
  const of = $("f-outcome");
  if (of) of.onchange = (e) => { view.loginOutcome = e.target.value; refresh(); };
  const ec = $("export-csv");
  if (ec) ec.onclick = () => runExport("csv");
  const ej = $("export-json");
  if (ej) ej.onclick = () => runExport("json");
```

### Tests

#### New `local-development/tests/test_export_module.py`

```python
"""The export module's switch: a config key, an env var, and the flag /api/version serves.

The export itself runs in the browser (tests/test_ui.py TestExport); this pins the one thing the
server contributes — the flag — in both states, and the parsing behind it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings, load_settings

BASE = """
clusters:
  - name: c1
    apiUrl: https://x
    tokenEnv: T
"""


def _client(tmp_path, **kw) -> TestClient:
    return TestClient(build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[], **kw),
                                run_poller=False))


def test_the_module_is_on_by_default_and_version_says_so(tmp_path):
    with _client(tmp_path) as c:
        assert c.get("/api/version").json()["features"]["export"] is True


def test_off_is_served_as_false_not_as_an_absent_key(tmp_path):
    """The page checks `=== true`; an absent key would also hide the control, but an explicit
    false is what lets an operator read the deployment's state off the endpoint."""
    with _client(tmp_path, ui_export_enabled=False) as c:
        assert c.get("/api/version").json()["features"]["export"] is False


def test_the_configmap_key_is_read(tmp_path, monkeypatch):
    monkeypatch.delenv("GSD_UI_EXPORT_ENABLED", raising=False)
    p = tmp_path / "c.yaml"
    p.write_text(BASE + "uiExportEnabled: false\n")
    assert load_settings(str(p)).ui_export_enabled is False
    p.write_text(BASE)
    assert load_settings(str(p)).ui_export_enabled is True


def test_the_env_var_wins_and_accepts_the_yaml_spellings(tmp_path, monkeypatch):
    p = tmp_path / "c.yaml"
    p.write_text(BASE + "uiExportEnabled: true\n")
    monkeypatch.setenv("GSD_UI_EXPORT_ENABLED", "off")
    assert load_settings(str(p)).ui_export_enabled is False
    monkeypatch.setenv("GSD_UI_EXPORT_ENABLED", "nonsense")
    assert load_settings(str(p)).ui_export_enabled is True, "the fallback is the default, on"
```

#### `local-development/tests/test_chart_strategy.py` — append

```python
class TestUiExportModule:
    """The export switch threads from values to the ConfigMap key the app reads, in both states.

    Lives here because ci.yml's `chart` job runs this file by name.
    """

    def test_on_by_default(self):
        ok, out = render()
        assert ok, out
        assert _config_data(out)["uiExportEnabled"] is True

    def test_off_reaches_the_app_as_false(self):
        ok, out = render(ui__export__enabled="false")
        assert ok, out
        assert _config_data(out)["uiExportEnabled"] is False
```

#### `local-development/tests/test_ui.py` — edits and additions

Edit the `quiet_server` fixture (it becomes the module-off server). OLD:
```python
        db_path=db,
        login_capture_enabled=False,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port,
        log_level="warning"))
```
NEW:
```python
        db_path=db,
        login_capture_enabled=False,
        # The export module OFF, so the shared fixtures can keep the default (on) and the
        # absent-control state still has a server to assert against.
        ui_export_enabled=False,
    )
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(
        build_app(settings, run_poller=False), host="127.0.0.1", port=port,
        log_level="warning"))
```

Append:
```python
class TestExport:
    """CSV/JSON export of the table on screen (docs/DESIGN_export.md).

    The file is built in the browser from `data`, so what these prove is the correspondence:
    the download holds exactly the rows the table shows, after the filter and sort, says when
    the page was a cut of a larger set, and never makes a request.
    """

    def _users(self, dash):
        dash.locator("button[data-nav='users']").click()
        dash.wait_for_selector("tr[data-user]")
        dash.wait_for_selector("#export-csv")

    @staticmethod
    def _csv_rows(download):
        import csv
        import io
        raw = open(download.path(), "rb").read()
        assert raw.startswith("\ufeff".encode("utf-8")), "the CSV must carry the UTF-8 BOM"
        text = raw.decode("utf-8-sig")
        assert "\r\n" in text, "records end in CRLF (RFC 4180)"
        return list(csv.reader(io.StringIO(text, newline="")))

    def test_the_control_is_absent_when_the_module_is_off(self, page, quiet_server):
        page.goto(quiet_server + "#page=users&cluster=crc-local")
        page.wait_for_selector("tr[data-user]")
        assert page.locator("#export-csv").count() == 0
        assert page.evaluate("() => data.version.features.export") is False

    def test_the_buttons_are_real_buttons_in_the_filter_bar_and_keep_focus_across_the_poll(self, dash):
        self._users(dash)
        el = dash.locator("#filters #export-csv")
        assert el.evaluate("el => el.tagName") == "BUTTON"
        dash.focus("#export-csv")
        dash.evaluate("() => render()")  # the 60s poll
        assert dash.evaluate("() => document.activeElement.id") == "export-csv"

    def test_the_csv_holds_the_rows_shown_with_the_declared_columns(self, dash):
        self._users(dash)
        with dash.expect_download() as dl:
            dash.click("#export-csv")
        rows = self._csv_rows(dl.value)
        assert rows[0] == ["user_name", "full_name", "logged_in", "first_login_at", "providers",
                           "group_count", "last_login_at", "first_seen_at"]
        assert [r[0] for r in rows[1:]] == ["alice", "gatekeeper", "kubeadmin"]
        assert rows[1][1] == "Alice Cooper" and rows[2][1] == ""
        import re
        assert re.fullmatch(r"gsd_crc-local_users_\d{8}T\d{6}Z\.csv", dl.value.suggested_filename)

    def test_the_export_follows_the_filter_and_the_chip(self, dash):
        self._users(dash)
        dash.fill("#f-user-search", "gate")
        dash.wait_for_function("() => view.userSearch === 'gate'")
        assert "1 row" in dash.locator("#export-note").inner_text()
        with dash.expect_download() as dl:
            dash.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert [r["user_name"] for r in doc["rows"]] == ["gatekeeper"]
        assert doc["filter"] == {"search": "gate", "chip": "all"}
        assert doc["scope"] == "all" and doc["truncated"] is False and doc["count"] == 1
        assert doc["cluster"] == "crc-local" and doc["tab"] == "users"
        assert set(doc["rows"][0]) == set(doc["columns"])
        dash.locator("#f-user-search").press("Escape")

    def test_a_partial_page_is_said_in_the_note_the_filename_and_the_json(self, dash):
        self._users(dash)
        dash.evaluate("() => { data.users = Object.assign({}, data.users, { truncated: true, total: 50 }); render(); }")
        note = dash.locator("#export-note")
        assert "partial" in note.inner_text() and "3 of 50" in note.inner_text()
        assert "partial" in (note.get_attribute("class") or "")
        with dash.expect_download() as dl:
            dash.click("#export-json")
        assert "_partial_" in dl.value.suggested_filename
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["truncated"] is True and doc["served"] == 3 and doc["total"] == 50
        assert "partial" in doc["note"]
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.users && data.users.truncated === false")

    def test_the_csv_helper_quotes_per_rfc_4180_and_neutralises_formulas(self, dash):
        """The helper, exercised directly: the one place quoting lives."""
        got = dash.evaluate("""() => toCsv(["a", "b"], [
            { a: "x,y", b: 'he said "hi"' },
            { a: "line\\nbreak", b: null },
            { a: "=SUM(1)", b: ["p", "q"] },
            { a: 3, b: true },
        ])""")
        assert got == ("\ufeffa,b\r\n"
                       '"x,y","he said ""hi"""\r\n'
                       '"line\nbreak",\r\n'
                       "'=SUM(1),p; q\r\n"
                       "3,true\r\n")

    def test_access_granted_exports_the_visible_sections_in_page_order_and_sort(self, dash):
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        dash.wait_for_selector("#export-csv")
        with dash.expect_download() as dl:
            dash.click("#export-csv")
        rows = self._csv_rows(dl.value)
        assert rows[0][0] == "finding"
        findings = [r[0] for r in rows[1:]]
        # The default view paints dangling, unresolved, unmanaged, then granted — never built-in.
        assert "built_in" not in findings
        assert findings == sorted(findings, key=["dangling", "unresolved", "unmanaged", "ok"].index)
        assert dl.value.suggested_filename.startswith("gsd_crc-local_access-granted_")

    def test_the_export_makes_no_request(self, dash):
        self._users(dash)
        dash.evaluate("() => { window.__calls = 0; const f = window.fetch;"
                      " window.fetch = (...a) => { window.__calls++; return f(...a); }; }")
        with dash.expect_download():
            dash.click("#export-csv")
        dash.wait_for_timeout(300)
        assert dash.evaluate("() => window.__calls") == 0

    def test_no_control_on_a_drill_down_or_a_loading_page(self, dash):
        self._users(dash)
        dash.locator("tr[data-user='alice']").click()
        dash.wait_for_selector("#back-groups")
        assert dash.locator("#export-csv").count() == 0
        dash.locator("#back-groups").click()
        dash.wait_for_selector("#export-csv")


class TestExportVisibility:
    """A narrowed reader's export is their own rows and nothing else — by construction, because
    the file is built from the payload the server served them, but pinned anyway."""

    def test_a_narrowed_readers_users_export_is_their_own_row_and_says_self(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='users']").click()
        p.wait_for_selector("tr[data-user='alice']")
        p.wait_for_selector("#export-json")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["scope"] == "self" and doc["viewer"] == "alice"
        assert [r["user_name"] for r in doc["rows"]] == ["alice"]
        assert "_self_" in dl.value.suggested_filename
        text = open(dl.value.path()).read()
        for other in ("gatekeeper", "kubeadmin", "dave"):
            assert other not in text

    def test_a_narrowed_readers_access_export_is_their_own_path(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_selector(".scope-banner")
        p.wait_for_selector("#export-csv")
        with p.expect_download() as dl:
            p.click("#export-csv")
        rows = TestExport._csv_rows(dl.value)
        assert rows[0][0] == "via_group"
        names = {r[5] for r in rows[1:]}
        assert names == {"managed-admin-rb", "hand-made-crb"}, names

    def test_the_administrator_exports_the_whole_cluster(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='users']").click()
        p.wait_for_selector("tr[data-user='kubeadmin']")
        with p.expect_download() as dl:
            p.click("#export-json")
        import json
        doc = json.load(open(dl.value.path()))
        assert doc["scope"] == "all" and doc["count"] == 3
```

### Docs, changelog, chart

- New `docs/DESIGN_export.md`: the decision table above, the BOM and formula-guard rationale, the filename grammar, the columns per tab, the "not recorded" ruling, and the R3 truncation contract, citing `gsd/static/index.html#function exportDescriptor`, `index.html#function toCsv`, `gsd/api.py#feature_flags`, `gsd/config.py#Settings`, `charts/group-sync-dashboard/values.yaml#ui`.
- `docs/CHANGELOG.md`, new top section:
  ```
  ## Application 0.12.0 — chart 0.11.0 — <date>

  - **CSV and JSON export on every table.** Users, Groups, Access granted, Namespace audit and
    Logins gain Export buttons in the filter bar. The file is built in the browser from the rows the
    server served this reader — after the page's own filter and sort, at the reader's own tier — so it
    can never hold a row the tier withheld. RFC 4180 with a UTF-8 BOM (spreadsheets), JSON without one
    (RFC 8259), a formula-looking cell prefixed with an apostrophe, the file named for the cluster, tab,
    tier and UTC time, and `_partial` in the name plus `truncated` in the JSON when the page was a cut
    of a larger set. Not recorded in Usage: an export makes no request, and the activity table counts
    interactions per day, not actions. `/api/version` gains `features`. (design `DESIGN_export.md`)
  - **Chart 0.11.0:** `ui.export.enabled` (default true) → `uiExportEnabled`.
  ```
- Chart README, "Application" table, add: `| \`ui.export.enabled\` | \`true\` | CSV/JSON download of the table on screen, built in the browser from what the server served this reader; the file says when the page was partial. Off removes the control |`
- `Chart.yaml`: `version: 0.11.0`, `appVersion: "0.12.0"`, history comment: `# CHART 0.11.0 (<date>), MINOR: appVersion moves to application 0.12.0 and a new value, ui.export.enabled (default true), reaches the ConfigMap as uiExportEnabled. Rendered objects otherwise unchanged.` and under appVersion: `# 0.12.0. CSV/JSON export on the tables; /api/version gains `features`. Additive on the wire, MINOR.`
- `local-development/API.md`, under `/api/version`: `features` — the optional modules switched on (`export`).

### Verification

```
cd local-development && ./.venv/bin/python -m pytest tests/test_export_module.py tests/test_api_contract.py tests/test_type_scale.py tests/test_accessibility.py -q
./.venv/bin/python -m pytest tests/test_ui.py -q -k "Export"          # expect: all passed, downloads land in the Playwright temp dir
./.venv/bin/python -m pytest tests/test_chart_strategy.py -q -k UiExport
helm template t charts/group-sync-dashboard --set ingress.host=t.example.com | grep uiExportEnabled   # -> uiExportEnabled: true
```

### Risks and how they are closed

- A payload field leaks into the file that the page never showed → columns are an explicit projection (`EXPORT_COLUMNS`); the tier test parses the file.
- The file and the table disagree → one selection function per tab feeds both (`usersMatched`, `groupsMatched`, `bindingsVisible`+`sortedBindings`, `grantsSorted`).
- A partial page reads as complete → note, `_partial` filename, `truncated` in JSON, all from the server's R3 fields.
- Formula injection from directory names → apostrophe guard, unit-tested.
- Old server without `features` → the control never renders (`=== true`).

---


## Batch closing sections (verbatim)

## Questions only the operator can answer

1. **Exports and audit** — accept "not recorded" (chosen), or extend `dashboard_user_activity` with an export count per day (a schema change and a synthetic interaction-marked request per export)?
2. **Namespace report classification marking** — the provenance block prints "Handling: internal — access review evidence"; is there an organisational marking to print instead (a value `features.namespaceReport.marking`)?
3. **PDF module base** — the hardened family is assumed to satisfy WeasyPrint's library closure via the builder's `dnf`; if the Hummingbird runtime refuses any of those libraries at first build, is a UBI9-based report image acceptable for that one container?
4. **Question E's alternative** — should a follow-up design `-pass-access-token` for project members' own-namespace reports, given the session design's measured refusal of that flag?

## Critical files for implementation

- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/static/index.html`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/api.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/config.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/deployment.yaml`
