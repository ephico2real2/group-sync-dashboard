# SPEC C2 — Users tab: provider allow-list and exact first login

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | C — product |
| Release | R3 — Product wins |
| Version on release | app 0.15.0, chart 0.15.0 |
| Issue | [#62](https://github.com/ephico2real2/group-sync-dashboard/issues/62) |
| Status | specified |
| Source | design agent output `a836ef1bc0058551a`; two messages; the first ended inside a ```sh fence and the second began with two fence lines (a closer and a stray duplicate), so one duplicate fence line was dropped |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
**verbatim** — it was sliced from the agent's output by heading and re-concatenated to the byte before
this file was written, and nothing in it was rewritten by hand. Implementation applies the code in
"Design" exactly as written, one file at a time; a deviation found necessary during implementation is
written back into this file in the same pull request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Second feature of R3: app 0.15.0, chart 0.15.0; schema migration 9 (the body says 8; B4 took 8).

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

## C2 — Users tab: provider allow-list and exact first login

### Goal and the switches

(a) `config.users.providers` (default `[]` = all): the Users tab lists only Users who have logged in through a listed identity provider, the API says so (`providers_filter`) and the page says "showing providers: x, y". (b) `rbac.identities` (default **false**): when granted, the poller reads Identity objects and each row's `first_login_at` becomes the earliest `Identity.metadata.creationTimestamp` naming the User — exact — with `first_login_source: "identity"|"user"` on the wire so the page can say which. A 403 is tolerated and reported (`identities_source: forbidden`), never fabricated, the way `rbac.users` is (`gsd/kube.py#ClusterClient.fetch_users`). The read is paged like every list (`gsd/kube.py#ClusterClient._list_all`).

Answers to `docs/DESIGN_users_tab_logins.md` §"Open questions": (1) both — chips stay, an allow-list is now a value; (2) `Identity.creationTimestamp` behind `rbac.identities`, the User time kept as the labelled fallback; (3) the never-logged-in line stays on the Users tab and is **not** narrowed by the allow-list — a member who logged in through an excluded provider has logged in.

Interactions modelled: the allow-list narrows `users`, `total` and `logged_in_total`; manual accounts (no identity) drop out under any allow-list; `never_logged_in_members` is unchanged (no User object at all); `/users/{name}` keeps the full truth for one person (a reader arrives there from a group page); Access granted's `logged_in_count` is a definition of login, not the tab's population, and is unchanged. With `rbac.create=false`, `rbac.identities` is only the read switch (bring your own grant).

### Files

#### `local-development/gsd/config.py`

Add to `Settings` after the idle block:
```python
    # ── USERS TAB MODULES (docs/DESIGN_users_tab_logins.md, "Decisions after 0.9.0") ─────────────
    # Identity-provider names the Users tab lists. EMPTY MEANS ALL — a value that is simply empty
    # by default. Applied at READ time, never at the poll, so changing it needs no re-poll and the
    # stored record stays the whole cluster; recorded on the wire as `providers_filter` so the tab
    # can say "showing providers: x, y" instead of quietly listing fewer people.
    users_providers: tuple[str, ...] = ()
    # Whether the poller reads Identity objects for the exact first login. One wire from the chart's
    # rbac.identities, like oauthProxyEnabled: the app cannot see its own RBAC, and trying a read
    # that is refused every poll would put a 403 a minute into the API server's audit log.
    identities_read_enabled: bool = False
```
Add a parser before `_require`:
```python
# An identity provider's name as OpenShift accepts it: it prefixes every `identities[]` entry as
# `<provider>:<id>`, so it can contain neither ':' nor '/', and this dashboard splits on the colon.
_PROVIDER_NAME = re.compile(r"[^:/\s]+")


def _providers_setting(raw: dict) -> tuple[str, ...]:
    """usersProviders: a comma-joined list (the loginCaptureHtpasswdProviders shape). STRICT — a
    malformed name is a startup error, because a name that can never match would silently empty
    the Users tab and read as "nobody has logged in"."""
    source = os.environ.get("GSD_USERS_PROVIDERS")
    if source is None:
        source = raw.get("usersProviders", "") or ""
    names = tuple(p.strip() for p in str(source).split(",") if p.strip())
    for name in names:
        if not _PROVIDER_NAME.fullmatch(name):
            raise ConfigError(
                f"usersProviders: {name!r} is not an identity-provider name (no ':' or '/', no "
                f"whitespace) — a name that can never match would list nobody"
            )
    return tuple(dict.fromkeys(names))
```
In `load_settings`, after `ui_export_enabled=…`:
```python
        users_providers=_providers_setting(raw),
        identities_read_enabled=_bool_setting(
            raw, "GSD_IDENTITIES_READ_ENABLED", "identitiesReadEnabled", False
        ),
```

#### `local-development/gsd/kube.py`

After `USER_API = …`:
```python
# The Identity objects: ONE per (provider, id), created by OpenShift at the first successful login
# through that provider and never before, naming the User it maps to. Its creationTimestamp is
# therefore the EXACT first login through that provider — where a User's creationTimestamp is only
# the first login for a User the provider created, and earlier than it for one an administrator
# made ahead of time (docs/DESIGN_users_tab_logins.md, open question 2). Read only when the chart
# grants it (rbac.identities → identitiesReadEnabled); a 403 is reported, never fabricated over.
IDENTITY_API = "/apis/user.openshift.io/v1/identities"
```
Add method after `fetch_users`:
```python
    def fetch_identities(self) -> dict[str, str] | None:
        """The exact first login per User — the earliest Identity creationTimestamp naming it — or
        None when we may not read them. Paged like every list. An Identity with no `user.name`
        (provisioning in flight, or a lookup-mapped provider before its first mapping) is skipped;
        two Identities for one User keep the earlier. RFC 3339 UTC strings from the API server
        share one format, so the string comparison is the time comparison."""
        with self._client() as client:
            try:
                items = self._list_all(client, IDENTITY_API)
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and IDENTITY_API in exc.message:
                    log.debug("%s: not permitted to list identities — first-login times stay "
                              "approximate", self.cluster.name)
                    return None
                raise
        earliest: dict[str, str] = {}
        for obj in items:
            user = ((obj.get("user") or {}).get("name") or "").strip()
            created = ((obj.get("metadata") or {}).get("creationTimestamp") or "").strip()
            if not user or not created:
                continue
            if user not in earliest or created < earliest[user]:
                earliest[user] = created
        log.debug("fetched exact first logins for %d users from %s", len(earliest), self.cluster.name)
        return earliest
```

#### `local-development/gsd/poller.py`

`poll_once` signature gains `identities_read: bool = False` (after `access_group_dn`), documented: "`identities_read` is the chart's rbac.identities, threaded like access_group_dn: one value, not the whole Settings." OLD:
```python
            else:
                store.replace_users(cluster.name, users, observed_at)
                log.info("%s: %d user(s) recorded, %d with a display name", cluster.name,
                         len(users), sum(1 for u in users if u.get("full_name")))
```
NEW:
```python
            else:
                # The exact first logins, read only when granted (rbac.identities). Three outcomes,
                # each recorded so the tab can say what its timestamps are: a dict (exact, 'ok'), None
                # (refused, 'forbidden' — rows fall back to the User time), or a raised transient
                # (this cycle's rows carry the User time and the status is left as it was).
                exact: dict[str, str] | None = None
                identity_state: str | None = "off"
                if identities_read:
                    fetch_identities = getattr(client, "fetch_identities", None)
                    if fetch_identities is None:
                        identity_state = None
                    else:
                        try:
                            exact = fetch_identities()
                        except ClusterError as exc:
                            log.warning("identity refresh for %s failed: %s — first-login times are "
                                        "approximate this cycle", cluster.name, exc.message)
                            identity_state = None
                        else:
                            identity_state = "ok" if exact is not None else "forbidden"
                            if exact is None:
                                log.info("%s: not permitted to list identities — first-login times "
                                         "are approximate. Grant user.openshift.io/identities "
                                         "[get,list] (chart: rbac.identities) for exact ones.",
                                         cluster.name)
                store.replace_users(cluster.name, users, observed_at, identity_created=exact)
                if identity_state is not None:
                    store.set_identities_status(cluster.name, identity_state, observed_at)
                log.info("%s: %d user(s) recorded, %d with a display name, %d with an exact first "
                         "login", cluster.name, len(users),
                         sum(1 for u in users if u.get("full_name")), len(exact or {}))
```
In `Poller._run_cluster`, OLD:
```python
                poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                          access_group_dn=self.settings.cluster_access_group)
```
NEW:
```python
                poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                          access_group_dn=self.settings.cluster_access_group,
                          identities_read=self.settings.identities_read_enabled)
```

#### `local-development/gsd/store.py`

SCHEMA: add to `ocp_user` after `has_identity`: `    identity_created_at TEXT,           -- migration 8: the earliest Identity creationTimestamp, exact first login; NULL when not read` and a new table after `ocp_user_status`:
```sql
-- Whether the last poll could read the Identity objects (rbac.identities). 'ok' | 'forbidden' |
-- 'off' (the read is not switched on). Absent means no poll has reported yet.
CREATE TABLE IF NOT EXISTS ocp_identity_status (
    cluster_id          TEXT PRIMARY KEY,
    state               TEXT NOT NULL,
    observed_at         TEXT NOT NULL
);
```
Migration appended to `_MIGRATIONS`:
```python
    (
        8,
        "ocp_user: identity_created_at (exact first login); ocp_identity_status",
        [
            # Tolerated on replay by _migrate's one allowed error, "duplicate column name".
            "ALTER TABLE ocp_user ADD COLUMN identity_created_at TEXT",
            """CREATE TABLE IF NOT EXISTS ocp_identity_status (
                   cluster_id          TEXT PRIMARY KEY,
                   state               TEXT NOT NULL,
                   observed_at         TEXT NOT NULL
               )""",
            # No backfill: exact times arrive with the next poll that may read identities; until then
            # every row's source reads `user`, which is the truth about it.
        ],
    ),
```
`users()`: signature gains `providers: tuple[str, ...] = ()`; SELECT adds `u.identity_created_at,` after `u.has_identity,`; after the `user_name` predicate:
```python
        if providers:
            # The allow-list, on the JSON list the row stores: a User qualifies when ANY of its
            # providers is listed. json_each is SQLite's own JSON1, present in every SQLite this
            # project ships (the image's 3.53.4; 3.38+ builds it in).
            sql += (" AND EXISTS (SELECT 1 FROM json_each(u.providers) je WHERE je.value IN ("
                    + ",".join("?" * len(providers)) + "))")
            params += list(providers)
```
`_user_row`:
```python
        row = dict(row)
        row["providers"] = json.loads(row.pop("providers") or "[]")
        row["logged_in"] = bool(row.pop("has_identity"))
        exact = row.pop("identity_created_at", None)
        # The exact Identity time when it was read, the User's creation time otherwise — and the
        # source says which, so the page never presents an approximation as an exact fact.
        row["first_login_at"] = (exact or row["created_at"]) if row["logged_in"] else None
        row["first_login_source"] = ("identity" if exact else "user") if row["logged_in"] else None
        return row
```
`count_users()`: same `providers` parameter and predicate (on `providers` column, alias-free: `EXISTS (SELECT 1 FROM json_each(ocp_user.providers) …`). `replace_users(self, cluster_id, users, observed_at, identity_created: dict[str, str] | None = None)`: the INSERT gains `identity_created_at` = `(identity_created or {}).get(u["user_name"])`. New methods:
```python
    def set_identities_status(self, cluster_id: str, state: str, observed_at: str) -> None:
        """The last poll's verdict on reading Identity objects: ok | forbidden | off."""
        with self._write() as conn:
            conn.execute(
                """INSERT INTO ocp_identity_status(cluster_id, state, observed_at) VALUES(?, ?, ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state=excluded.state,
                                                         observed_at=excluded.observed_at""",
                (cluster_id, state, observed_at),
            )

    def identities_source(self, cluster_id: str) -> dict | None:
        rows = self._rows(
            "SELECT state, observed_at FROM ocp_identity_status WHERE cluster_id=?", (cluster_id,))
        return dict(rows[0]) if rows else None
```
`gsd/storage.py` Protocol: add `providers: tuple[str, ...] = ()` to `users`/`count_users`, `identity_created: dict[str, str] | None = None` to `replace_users`, and `set_identities_status`, `identities_source`.

#### `local-development/gsd/api.py` (`list_users`, `user_detail`)

```python
        who = None if scope == "all" else require_viewer(viewer)
        providers = settings.users_providers
        rows = store.users(cluster_id, limit=limit, offset=offset, user_name=who, providers=providers)
        never = store.synced_members_without_user(cluster_id, user_name=who)
        status = store.users_source(cluster_id)
        istatus = store.identities_source(cluster_id)
        return {
            ...
            "source_observed_at": (status or {}).get("observed_at"),
            # Which provider names the list is narrowed to (config.users.providers); [] means all.
            # Applied to `users`, `total` and `logged_in_total`, NOT to never_logged_in_members: a
            # member who logged in through an excluded provider has logged in.
            "providers_filter": list(providers),
            # Whether first_login_at is exact: ok (Identity objects read), forbidden (rbac.identities
            # not granted — rows fall back to the User time), off (the read is not switched on),
            # pending (switched on, no poll yet).
            "identities_source": (istatus or {}).get("state")
                                  or ("pending" if settings.identities_read_enabled else "off"),
            "identities_source_observed_at": (istatus or {}).get("observed_at"),
            "login_capture": ...,
            "total": store.count_users(cluster_id, user_name=who, providers=providers),
            "logged_in_total": store.count_users(cluster_id, user_name=who, logged_in_only=True,
                                                 providers=providers),
```
Docstring gains: "`first_login_source` per row says whether `first_login_at` is the Identity's creation time (exact) or the User's (approximate); `identities_source` says why." `user_detail` adds `"first_login_source": record["first_login_source"] if record else None,` after `first_login_at`.

#### Chart

`values.yaml`, under `rbac:` after `users: true`:
```yaml
  # Identity objects: one per (provider, id), created by OpenShift at the first successful login
  # through that provider. Its creation time is the EXACT first login, where the User's is only
  # exact for a provider-created User. OFF by default: it is a grant the chart does not otherwise
  # need, and the Users tab is honest without it (it labels the User time "since", approximate).
  # This value is BOTH the grant and the read switch (identitiesReadEnabled in the ConfigMap): the
  # app cannot see its own RBAC, and a refused read every poll would put a 403 a minute in the
  # audit log. Requires rbac.users. With rbac.create=false it is only the read switch.
  identities: false
```
`config:` gains, after `unmanagedAudit`:
```yaml
  users:
    # Identity-provider NAMES the Users tab lists. EMPTY means every provider — a value that is
    # simply empty by default. Set it to show one directory's people on a cluster that also carries
    # test or break-glass providers (measured: 49 `ceo_rnd_oim` accounts beside 8 LDAP users). Applied
    # when the tab is read, not at the poll; the tab says "showing providers: …"; the never-logged-in
    # line is not narrowed (a member who logged in through another provider has logged in); manual
    # accounts with no identity drop out under any list. Names must match the identity provider's
    # `name:` in oauth.config.openshift.io/cluster, and cannot contain ':' or '/'.
    providers: []
```
`configmap.yaml` after `uiExportEnabled`:
```yaml
    usersProviders: {{ .Values.config.users.providers | join "," | quote }}
    identitiesReadEnabled: {{ .Values.rbac.identities }}
```
`rbac.yaml`, after the `users` rule's `{{- end }}`:
```yaml
  {{- if .Values.rbac.identities }}
  {{- if not .Values.rbac.users }}
  {{- fail "rbac.identities=true requires rbac.users=true: an Identity's creation time is the exact first login of a User the dashboard must also be able to read." }}
  {{- end }}
  # The EXACT first login: one Identity per (provider, id), created at the first successful login
  # through that provider. Read: its creationTimestamp and the User it names. get/list only.
  - apiGroups: ["user.openshift.io"]
    resources: ["identities"]
    verbs: ["get", "list"]
  {{- end }}
```

#### `index.html` — Users tab

In `usersPage`, OLD:
```js
  const status = (u) => u.logged_in === false
    ? `<span class="muted">manual account · never logged in</span>`
    : u.first_login_at
      ? `logged in since <span class="mono">${esc(fmtTime(u.first_login_at))}</span> <span class="muted">(${esc(ago(u.first_login_at))})</span>`
      : `<span class="muted">logged in</span>`;
```
NEW:
```js
  // `exact` marks an Identity creation time; `approx.` the User's, which precedes the first login
  // for an account an administrator created ahead of time. Neither word is colour.
  const sourceChip = (u) => u.first_login_source === "identity"
    ? ` <span class="chip" title="Exact: the Identity object's creation time, written by OpenShift at the first successful login through this provider.">exact</span>`
    : u.first_login_source === "user"
      ? ` <span class="chip" title="Approximate: the User object's creation time. Exact for a provider-created user; earlier than the first login for an account created by hand and linked later.">approx.</span>`
      : "";
  const status = (u) => u.logged_in === false
    ? `<span class="muted">manual account · never logged in</span>`
    : u.first_login_at
      ? `logged in since <span class="mono">${esc(fmtTime(u.first_login_at))}</span> <span class="muted">(${esc(ago(u.first_login_at))})</span>${sourceChip(u)}`
      : `<span class="muted">logged in</span>`;
```
After the `users-source-age` line, add:
```js
    ${(d.providers_filter || []).length
      ? `<div class="filterbar-note" id="users-provider-filter">Showing providers:
          <strong>${d.providers_filter.map(esc).join(", ")}</strong>. People who logged in only through
          another provider are not listed here; their group pages are unchanged.</div>` : ""}
    ${self ? "" : identitiesNote(d)}
```
And before `function usersPage()`:
```js
/* What the first-login column IS, said once above the table at the wide tier (the narrowed
   reader sees the chip on their own row). Names the grant like the users-source banner does. */
function identitiesNote(d) {
  const s = d.identities_source;
  if (s === "ok") return `<div class="filterbar-note" id="users-identities-note">First-login times are
    <strong>exact</strong> (Identity objects read${d.identities_source_observed_at
      ? ` <span class="mono">${esc(fmtTime(d.identities_source_observed_at))}</span>` : ""}).</div>`;
  if (s === "forbidden") return `<div class="truncation-note" id="users-identities-note">The dashboard is
    <strong>not permitted to list identities.user.openshift.io</strong>, so first-login times fall back to
    the User's creation time (approximate). Grant <code>rbac.identities</code> in the chart for exact ones.</div>`;
  if (s === "pending") return `<div class="filterbar-note" id="users-identities-note">Waiting for the first
    poll to read identities; first-login times are approximate until then.</div>`;
  if (s === "off") return `<div class="filterbar-note" id="users-identities-note">First-login times are
    <strong>approximate</strong> (the User's creation time). Exact times need the Identity read
    (<code>rbac.identities</code>).</div>`;
  return "";
}
```
`EXPORT_COLUMNS.users` gains `"first_login_source"` after `"first_login_at"`.

### Tests

- `tests/test_identities_read.py` (new, `httpx.MockTransport` like `tests/test_poller_users_read.py`): `fetch_identities` returns the earliest per user and skips identities without `user.name`; follows a `continue` token; 403 → `None`; poller matrix — `identities_read=False` never requests `IDENTITY_API` and status is `off`; `True`+200 → rows carry `first_login_source == "identity"` and status `ok`; `True`+403 → `user`/`forbidden`, rows kept; `True`+503 → rows carry `user`, status unchanged.
- `tests/test_users_tab_logins.py`: `_rec` gains `identity_created=None`; `_seed` passes `identity_created={"alice": _iso(NOW - timedelta(days=29))}`; tests: alice `first_login_at` is the Identity time and `first_login_source == "identity"`, kubeadmin `"user"`, manual `None`; envelope `identities_source` for `off`/`pending`/`ok`/`forbidden` (via `set_identities_status`); `Settings(users_providers=("ldap-local",))` → users `["alice","gatekeeper"]`, `total == 2`, `logged_in_total == 2`, `providers_filter == ["ldap-local"]`, `never_logged_in_members == {"count": 1, "names": ["dave"]}`, kubeadmin absent from `resp.text`; self tier: alice's row carries the source and nobody else's name; `/users/kubeadmin` detail shows `first_login_source == "user"` even under an allow-list that excludes him.
- `tests/test_config.py`: `usersProviders: "ldap-local, corp"` → tuple; `"bad:name"` → `ConfigError`; env wins; `identitiesReadEnabled` parsing.
- `tests/test_chart_strategy.py`: `TestTheIdentitiesGrantIsOffReadOnlyAndCoupled` — default renders no `identities` rule and `identitiesReadEnabled: false`; `rbac.identities=true` renders exactly `get,list`; `rbac.users=false` with identities on fails naming `rbac.users`; `config.users.providers={a,b}` → `usersProviders: "a,b"`.
- `tests/test_ui.py`: seed alice with an exact time; `test_the_status_says_whether_the_first_login_is_exact` (alice row has `exact`, kubeadmin `approx.`); `test_the_identities_note_names_the_state` for `forbidden`/`off` via `data.users` overrides; a `providers_server` fixture with `users_providers=("ldap-local",)` asserting `#users-provider-filter` and that kubeadmin is not a row while `#never-logged-in` still says 1.
- `tests/test_migrations.py`: migration 8 applies on a 7-database and replays on a fresh one.

### Docs, changelog, chart

- `docs/DESIGN_users_tab_logins.md`: status line gains "; the three open questions were closed in 0.14.0 — see 'Decisions after 0.9.0'"; new section answering each, citing `gsd/kube.py#ClusterClient.fetch_identities`, `gsd/store.py#Store._user_row`, `gsd/config.py#_providers_setting`.
- `docs/reference-architecture.md`: RBAC table row `| user.openshift.io | identities | get, list — only when rbac.identities |`.
- `docs/ACCESS_CONTROL.md` §4 `/users` row: "their own row (with `first_login_source`)".
- CHANGELOG `Application 0.14.0 — chart 0.13.0`: the two modules, the wire additions (`first_login_source`, `providers_filter`, `identities_source`), migration 8.
- Chart README rows: `rbac.identities` (`false`, RBAC table) and `config.users.providers` (`[]`, Application table).
- `Chart.yaml`: `version: 0.13.0`, `appVersion: "0.14.0"`, comment: MINOR — a new optional grant and a new value.

### Verification

```
./.venv/bin/python -m pytest tests/test_identities_read.py tests/test_users_tab_logins.py tests/test_config.py tests/test_migrations.py tests/test_storage_seam.py tests/test_no_duplicate_methods.py -q
./.venv/bin/python -m pytest tests/test_ui.py -q -k "UserSearch or Identit or Provider"
helm template t charts/group-sync-dashboard --set ingress.host=t --set rbac.identities=true | grep -A2 identities   # rule with get, list
oc auth can-i list identities.user.openshift.io --as=system:serviceaccount:<ns>:group-sync-dashboard   # yes only when granted
```

### Risks

- The allow-list empties the tab silently → the note names the filter; `total` shrinks with it; names are validated at startup.
- Identities refused after upgrade → `forbidden` state and banner, rows fall back with `approx.`; nothing fabricated.
- Two Identities for one User → the earlier is kept and tested.

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
