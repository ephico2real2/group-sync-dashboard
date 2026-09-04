# SPEC C3 — Namespace access report, HTML core and optional PDF image

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | C — product |
| Release | R6 — Reporting |
| Version on release | app 0.18.0, chart 0.19.0, reporting image 0.1.0 |
| Issue | [#67](https://github.com/ephico2real2/group-sync-dashboard/issues/67) |
| Status | specified |
| Source | design agent output `a836ef1bc0058551a`; two messages; the first ended inside a ```sh fence and the second began with two fence lines (a closer and a stray duplicate), so one duplicate fence line was dropped |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
**verbatim** — it was sliced from the agent's output by heading and re-concatenated to the byte before
this file was written, and nothing in it was rewritten by hand. Implementation applies the code in
"Design" exactly as written, one file at a time; a deviation found necessary during implementation is
written back into this file in the same pull request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- R6: app 0.18.0, chart 0.19.0, reporting image 0.1.0; schema migration 11 (the body says 9; D1 takes 10). The operator's answers to the design's questions 2–4 are collected in the issue before the PR opens.

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

## C3 — Namespace access report

### The five questions, answered with defaults

| § 9 | Default | Override | Why |
|---|---|---|---|
| A unattended | **No.** Browser-driven, GET-only. | none in the chart | A CronJob would need a bearer identity that passes the wide tier through `oauthProxy.apiTokenAccess` (delegate URLs covering `/api`), the PDF module on, somewhere to put the file and someone to send it to — an operator-run job outside this chart, which writes nothing. Recorded, not built. |
| B PDF/A | **No** by default. | `features.namespaceReport.pdf.variant: pdf/a-3b` | Browsers cannot emit it (parked doc §4); the PDF module can, so it is a value, off. |
| C absence | **Not attested** by default. | `rbac.namespaces: true` | Needs `get,list namespaces`; without it the report prints the coverage note (§5's "document rather than fix"). |
| D authz layer | **Not built.** Gate = `require_admin_tier` + optional `oauthProxy.sar`. | — | The report is the binding surface `/bindings/findings` already refuses at self (`gsd/api.py#require_admin_tier`); the §3 layer touched 19 endpoints for one consumer and the parked doc itself offered the inline check. |
| E own namespaces | **Wide tier only.** | recorded alternative | Per-namespace SSAR needs `-pass-access-token`, which the session design refused after measurement (`docs/DESIGN_session_and_signout.md` §"Token revocation…", "the app never sees a user token"). A `view`/`edit` project member reporting on their own namespace stays not built. |

### Architecture: HTML core in the main image, PDF module as an optional sidecar

| | Browser print (parked §4) | PDF in the main image | **PDF sidecar (chosen, optional)** |
|---|---|---|---|
| Deps in the main image | none | WeasyPrint + pango/cairo (§4: OS-level CVE surface, OOM risk to the poller) | none |
| Canonical artifact | `.html` with sha256 | PDF | `.html` stays canonical; PDF renders the **same HTML** |
| Byte-identical PDF | no | yes | yes; PDF/A available |
| OOM blast radius | — | kills the poller | the sidecar's own container and limits; kubelet restarts it alone |
| Extra image | no | no | yes, `group-sync-dashboard-report` |

Recommendation: the report data endpoint, the self-contained HTML with a print stylesheet and "Download .html" live in the main image (`features.namespaceReport.enabled`); `features.namespaceReport.pdf.enabled` adds a loopback sidecar that fetches that same HTML from the app with the viewer's proxy headers and returns a PDF through a GET on the main app — one template, two renderings, tier scoping decided once, no proxy flag changes.

Data flow for PDF: browser → proxy → app `GET /api/clusters/{id}/report/namespaces.pdf?ns=` (admin tier checked) → app `GET http://127.0.0.1:8090/render?…` forwarding `X-Forwarded-User/Email` → sidecar `GET http://127.0.0.1:8080/api/clusters/{id}/report/namespaces.html?…` with the same headers (the tier is decided again by the app) → WeasyPrint → bytes back. The sidecar binds `127.0.0.1`, holds no cluster credential, mounts no data volume.

Switch interactions (all modelled, guards in `deployment.yaml`): `pdf.enabled` requires `namespaceReport.enabled` (fail); `namespaceReport.enabled` requires `rbac.bindings` (fail); `rbac.namespaces` is independent (an extra read, used by the report's coverage when both are on); `visibility.enabled=false` means every authenticated reader is wide and may generate a report (existing semantics, stated); `oauthProxy.enabled=false` gives `viewer: null` in the provenance, printed as "no authenticated viewer (proxy off)".

### Files (core)

#### `local-development/gsd/config.py`
```python
    # ── NAMESPACE REPORT (docs/namespace-report-design.md §10) ─────────────────────────────────────
    namespace_report_enabled: bool = False
    # The PDF module's loopback address when the sidecar is deployed; empty means no module.
    namespace_report_pdf_url: str = ""
    # Whether the poller reads Namespace objects (rbac.namespaces), which is what lets the report
    # attest ABSENCE — "this namespace exists and has no grants" — rather than "none observed".
    namespaces_read_enabled: bool = False
```
`load_settings`: `namespace_report_enabled=_bool_setting(raw, "GSD_NAMESPACE_REPORT_ENABLED", "namespaceReportEnabled", False)`, `namespace_report_pdf_url=(os.environ.get("GSD_NAMESPACE_REPORT_PDF_URL") or str(raw.get("namespaceReportPdfUrl", "") or "")).rstrip("/")`, `namespaces_read_enabled=_bool_setting(raw, "GSD_NAMESPACES_READ_ENABLED", "namespacesReadEnabled", False)`. `feature_flags()` returns `{"export": …, "namespace_report": settings.namespace_report_enabled, "namespace_report_pdf": settings.namespace_report_enabled and bool(settings.namespace_report_pdf_url)}`.

#### `local-development/gsd/kube.py`
```python
NAMESPACE_API = "/api/v1/namespaces"

    def fetch_namespaces(self) -> list[dict] | None:
        """Every Namespace's name, creation time and phase, or None when we may not list them
        (rbac.namespaces off). The report's coverage: with this read a requested namespace that
        does not exist is said not to exist, and one with no observed binding is "no grants" as a
        positive statement; without it neither can be told from "never observed"."""
        with self._client() as client:
            try:
                items = self._list_all(client, NAMESPACE_API)
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and NAMESPACE_API in exc.message:
                    log.debug("%s: not permitted to list namespaces", self.cluster.name)
                    return None
                raise
        return [
            {"name": name, "created_at": meta.get("creationTimestamp"),
             "phase": (obj.get("status") or {}).get("phase")}
            for obj in items
            if (meta := obj.get("metadata") or {}) and (name := meta.get("name"))
        ]
```

#### `local-development/gsd/poller.py` — `refresh_bindings` gains `namespaces_read: bool = False`; after the operator-configs block:
```python
    # Namespace objects ride the binding cadence: the report reads them beside the bindings, and
    # they change on administrative action. Read only when switched on (rbac.namespaces).
    if namespaces_read:
        fetch_namespaces = getattr(client, "fetch_namespaces", None)
        if fetch_namespaces is not None:
            try:
                namespaces = fetch_namespaces()
            except ClusterError as exc:
                log.warning("namespace refresh for %s failed: %s — the report's coverage keeps "
                            "its last verdict", cluster.name, exc.message)
            else:
                if namespaces is None:
                    store.mark_namespaces_unavailable(cluster.name, now_iso())
                else:
                    store.replace_namespaces(cluster.name, namespaces, now_iso())
```
`Poller._run_cluster` passes `namespaces_read=self.settings.namespaces_read_enabled`.

#### `local-development/gsd/store.py` — migration 9 and methods
```sql
-- Namespace objects (rbac.namespaces), replaced on the binding cadence. Exists only to let the
-- namespace report attest absence; nothing else reads it.
CREATE TABLE IF NOT EXISTS cluster_namespace (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    created_at          TEXT,
    phase               TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name)
);
CREATE TABLE IF NOT EXISTS cluster_namespace_status (
    cluster_id          TEXT PRIMARY KEY,
    state               TEXT NOT NULL,      -- ok | forbidden
    observed_at         TEXT NOT NULL
);
```
```python
    (9, "cluster_namespace + status: the namespace report's coverage", [ <the two CREATE IF NOT EXISTS above> ]),
```
```python
    # -- namespaces (the report's coverage) -----------------------------------------------
    def replace_namespaces(self, cluster_id, rows, observed_at):
        with self._write() as conn:
            conn.execute("DELETE FROM cluster_namespace WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO cluster_namespace(cluster_id, name, created_at, phase, observed_at)
                   VALUES(:cluster_id,:name,:created_at,:phase,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows])
            conn.execute(
                """INSERT INTO cluster_namespace_status(cluster_id, state, observed_at) VALUES(?, 'ok', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='ok', observed_at=excluded.observed_at""",
                (cluster_id, observed_at))

    def mark_namespaces_unavailable(self, cluster_id, observed_at):
        with self._write() as conn:
            conn.execute(
                """INSERT INTO cluster_namespace_status(cluster_id, state, observed_at) VALUES(?, 'forbidden', ?)
                   ON CONFLICT(cluster_id) DO UPDATE SET state='forbidden', observed_at=excluded.observed_at""",
                (cluster_id, observed_at))

    def namespaces_source(self, cluster_id):
        rows = self._rows("SELECT state, observed_at FROM cluster_namespace_status WHERE cluster_id=?", (cluster_id,))
        return dict(rows[0]) if rows else None

    def cluster_namespaces(self, cluster_id):
        return self._rows("SELECT name, created_at, phase FROM cluster_namespace WHERE cluster_id=? ORDER BY name", (cluster_id,))

    def binding_namespaces(self, cluster_id):
        """DISTINCT namespaces observed on any binding, with counts. '' becomes CLUSTER_SCOPE, the
        sentinel the API already speaks (parked design §5: the store, not a new grant, is the
        universe)."""
        return self._rows(
            """SELECT ns AS namespace, SUM(g) AS group_bindings, SUM(u) AS user_bindings
                 FROM (SELECT CASE WHEN binding_namespace='' THEN ? ELSE binding_namespace END AS ns,
                              1 AS g, 0 AS u FROM rbac_group_binding WHERE cluster_id=?
                       UNION ALL
                       SELECT CASE WHEN binding_namespace='' THEN ? ELSE binding_namespace END,
                              0, 1 FROM user_binding WHERE cluster_id=? AND is_platform=0)
                GROUP BY ns ORDER BY ns""",
            (self.CLUSTER_SCOPE, cluster_id, self.CLUSTER_SCOPE, cluster_id))

    def report_group_bindings(self, cluster_id, namespaces, limit, offset=0):
        """Classified group bindings in the given namespaces ('' for cluster scope), with reach,
        ordered namespace, severity, group, binding — deterministic so two reports diff cleanly."""
        marks = ",".join("?" * len(namespaces))
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name, b.role_kind, b.role_name,
                         b.group_name, b.managed_source, b.exception,"""
               + self._REACH_COLS + self._FINDING_CASE + " AS finding"
               + self._FINDING_JOINS + self._REACH_JOIN + self._FINDING_WHERE
               + f" AND b.binding_namespace IN ({marks})"
               + """ ORDER BY b.binding_namespace,
                       CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1 WHEN 'unmanaged' THEN 2
                                    WHEN 'ok' THEN 3 ELSE 4 END,
                       b.group_name, b.binding_name LIMIT ? OFFSET ?""")
        return self._rows(sql, (cluster_id, *namespaces, limit, offset))

    def count_report_group_bindings(self, cluster_id, namespaces):
        marks = ",".join("?" * len(namespaces))
        rows = self._rows("SELECT COUNT(*) AS n FROM rbac_group_binding WHERE cluster_id=? AND binding_namespace IN (" + marks + ")",
                          (cluster_id, *namespaces))
        return int(rows[0]["n"])

    def report_user_bindings(self, cluster_id, namespaces, limit, offset=0):
        marks = ",".join("?" * len(namespaces))
        return self._rows(
            """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name, user_name
                 FROM user_binding WHERE cluster_id=? AND is_platform=0 AND binding_namespace IN (""" + marks + """)
                ORDER BY binding_namespace,
                         CASE role_name WHEN 'cluster-admin' THEN 0 WHEN 'admin' THEN 1 WHEN 'edit' THEN 2 ELSE 3 END,
                         user_name, binding_name LIMIT ? OFFSET ?""",
            (cluster_id, *namespaces, limit, offset))

    def count_report_user_bindings(self, cluster_id, namespaces):
        marks = ",".join("?" * len(namespaces))
        rows = self._rows("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0 AND binding_namespace IN (" + marks + ")",
                          (cluster_id, *namespaces))
        return int(rows[0]["n"])

    def group_rosters(self, cluster_id, group_names):
        """Members per group, for the report's OPT-IN roster expansion only."""
        if not group_names:
            return {}
        marks = ",".join("?" * len(group_names))
        out: dict[str, list[str]] = {}
        for r in self._rows("SELECT group_name, user_name FROM group_member WHERE cluster_id=? AND group_name IN (" + marks + ") ORDER BY group_name, user_name",
                            (cluster_id, *group_names)):
            out.setdefault(r["group_name"], []).append(r["user_name"])
        return out
```
`_REACH_COLS` is the existing `reach_cols` string lifted from `all_bindings` to a class constant (the `CASE WHEN g.name IS NULL …` pair), and `all_bindings` reads `self._REACH_COLS if reach else ""`. All added to `gsd/storage.py#StorageBackend`.

#### New `local-development/gsd/report.py`
```python
"""The namespace access report: data, canonical hash and self-contained HTML.

docs/namespace-report-design.md §10. Built from the store only — the same rows the Access granted
and Namespace audit tabs read — under the handler's snapshot; rendered here into one HTML document
with the stylesheet inlined so the file is complete on its own. No SQL, no cluster, no user token.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime

CLUSTER_SCOPE = "(cluster-scoped)"
MAX_NAMESPACES = 50
_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
FINDING_ORDER = ("dangling", "unresolved", "unmanaged", "ok", "built_in")


def parse_namespaces(raw: str) -> list[str]:
    """Comma-separated namespace names, de-duplicated in order; the '(cluster-scoped)' sentinel
    is accepted. Raises ValueError with the offending token."""
    names: list[str] = []
    for token in (t.strip() for t in (raw or "").split(",")):
        if not token:
            continue
        if token != CLUSTER_SCOPE and not _LABEL.match(token):
            raise ValueError(f"{token!r} is not a namespace name")
        if token not in names:
            names.append(token)
    if not names:
        raise ValueError("at least one namespace is required")
    if len(names) > MAX_NAMESPACES:
        raise ValueError(f"at most {MAX_NAMESPACES} namespaces per report")
    return names


def canonical_sha256(sections: dict) -> str:
    """The hash printed in the provenance block: over the DATA only, never the timestamp."""
    return hashlib.sha256(json.dumps(sections, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def coverage(namespaces_source: dict | None, read_enabled: bool) -> dict:
    state = (namespaces_source or {}).get("state") or ("pending" if read_enabled else "off")
    notes = {
        "ok": "Every namespace on the cluster was read, so a requested namespace that does not exist is "
              "reported as such, and a namespace with no observed binding is reported as having no grants.",
        "off": "Namespaces are known only from observed bindings (rbac.namespaces is off). 'No grants observed' "
               "cannot be told from 'namespace never observed', so absence of access is NOT attested.",
        "forbidden": "The Namespace read is refused (the rbac.namespaces grant is missing), so this report "
                     "falls back to observed bindings and does not attest absence.",
        "pending": "Namespaces have not been read yet; this report falls back to observed bindings.",
    }
    return {"namespaces_read": state, "attests_absence": state == "ok", "note": notes[state],
            "observed_at": (namespaces_source or {}).get("observed_at")}


def build(store, settings, cluster, names, *, viewer, include_members, limit, now: datetime, version: dict) -> dict:
    keys = ["" if n == CLUSTER_SCOPE else n for n in names]
    cov = coverage(store.namespaces_source(cluster.name), settings.namespaces_read_enabled)
    existing = {r["name"] for r in store.cluster_namespaces(cluster.name)} if cov["namespaces_read"] == "ok" else None
    observed = {r["namespace"] for r in store.binding_namespaces(cluster.name)}
    groups = store.report_group_bindings(cluster.name, keys, limit)
    users = store.report_user_bindings(cluster.name, keys, limit)
    g_total = store.count_report_group_bindings(cluster.name, keys)
    u_total = store.count_report_user_bindings(cluster.name, keys)
    rosters = store.group_rosters(cluster.name, sorted({g["group_name"] for g in groups if g["finding"] in ("ok", "unmanaged")})) if include_members else {}
    per: dict[str, dict] = {}
    for n in names:
        per[n] = {"name": n, "exists": None if existing is None or n == CLUSTER_SCOPE else n in existing,
                  "observed": n in observed, "group_bindings": [], "user_bindings": [],
                  "findings": {k: 0 for k in ("dangling", "unresolved", "unmanaged", "direct_user")}}
    for g in groups:
        ns = g["binding_namespace"] or CLUSTER_SCOPE
        row = dict(g)
        if include_members:
            row["members"] = rosters.get(g["group_name"])
        per[ns]["group_bindings"].append(row)
        if g["finding"] in per[ns]["findings"]:
            per[ns]["findings"][g["finding"]] += 1
    for u in users:
        ns = u["binding_namespace"] or CLUSTER_SCOPE
        per[ns]["user_bindings"].append(dict(u))
        per[ns]["findings"]["direct_user"] += 1
    clusters = {c["id"]: c for c in store.clusters()}
    row = clusters.get(cluster.name) or {}
    sections = {"namespaces": [per[n] for n in names], "cluster_scoped_present": CLUSTER_SCOPE in names}
    truncated = len(groups) >= limit and g_total > limit or len(users) >= limit and u_total > limit
    return {
        "cluster": cluster.name, "api_url": cluster.api_url,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "viewer": viewer, "viewer_note": "proxy-verified (X-Forwarded-User)" if viewer else "no authenticated viewer (proxy off)",
        "dashboard": {"version": version.get("version"), "commit": version.get("commit"), "dirty": version.get("dirty")},
        "requested_namespaces": names, "coverage": cov,
        "freshness": {"last_poll": row.get("last_poll"), "poll_status": row.get("status"), "poll_error": row.get("message"),
                      "binding_interval_seconds": settings.binding_interval_seconds,
                      "users_source": (store.users_source(cluster.name) or {}).get("state") or "pending"},
        "include_members": include_members, "note": "direct bindings only; role rules are not evaluated — this is not an effective-permissions calculation",
        "limit": limit, "totals": {"group_bindings": g_total, "user_bindings": u_total}, "truncated": truncated,
        "sha256": canonical_sha256(sections), **sections,
    }
```
And `render_html(report, css, title) -> str`: a plain-string template (no Jinja, the `named_page` precedent) escaping every value with `html.escape`; structure per parked §6 — `<header>` provenance table (classification placeholder "Handling: internal — access review evidence", cluster + api_url, generated at UTC, generated by + note, dashboard version/commit/dirty, coverage note, freshness split snapshot/accumulated, poll-failure banner when `poll_status != "ok"`, the direct-bindings caveat verbatim, "includes membership rosters: yes/no", truncation banner, sha256) → per namespace: exists/observed line, findings summary, group-bindings table (finding, group, role, binding, reaches, members when included), direct-user table → cluster-scoped section when requested → `<footer>` with `Page X of Y` via `@page` margin boxes; one `<button class="no-print" onclick="window.print()">Print / Save as PDF</button>`; `<style>` is `report.css` inlined. A new static `local-development/gsd/static/report.css`: monochrome (`#000`/`#fff`/`#555`, 7.5:1), `@page { size: A4; margin: 18mm; @bottom-right { content: "Page " counter(page) " of " counter(pages); } }`, `table { border-collapse: collapse; page-break-inside: auto } tr { page-break-inside: avoid }`, `h2 { page-break-before: always }` per namespace, `.no-print { display: none }` under `@media print`.

#### `local-development/gsd/api.py` — four endpoints, after `direct_user_bindings`
```python
    from . import report as rpt  # top of file with the other imports
    REPORT_CSS = os.path.join(STATIC_DIR, "report.css")

    def require_report():
        if not settings.namespace_report_enabled:
            raise HTTPException(status_code=404, detail="the namespace report is not enabled on this deployment")

    def report_query(cluster_id, request, ns, include_members, limit):
        require_cluster(cluster_id)
        require_report()
        require_admin_tier(request)
        try:
            names = rpt.parse_namespaces(ns)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return rpt.build(store, settings, settings.cluster(cluster_id), names,
                         viewer=trusted_viewer(request), include_members=include_members, limit=limit,
                         now=datetime.now(UTC), version=version())

    @app.get("/api/clusters/{cluster_id}/report/namespaces/universe")
    @consistent
    def report_universe(request, cluster_id, limit: int = Query(default=1000, ge=1, le=10000, description="Maximum namespaces returned. `total` is the whole set.")) -> dict:
        """The namespaces a report can be run over, with binding counts and whether each exists.

        Observed bindings' namespaces (the store, parked design §5), unioned with every Namespace
        object when rbac.namespaces is on, plus the `(cluster-scoped)` pseudo-entry. ADMINISTRATOR
        TIER, like the report: the list itself is the binding surface's map.
        """
        require_cluster(cluster_id); require_report(); require_admin_tier(request)
        cov = rpt.coverage(store.namespaces_source(cluster_id), settings.namespaces_read_enabled)
        counts = {r["namespace"]: r for r in store.binding_namespaces(cluster_id)}
        names = set(counts)
        if cov["namespaces_read"] == "ok":
            names |= {r["name"] for r in store.cluster_namespaces(cluster_id)}
        rows = sorted(({"name": n, "exists": None if cov["namespaces_read"] != "ok" or n == rpt.CLUSTER_SCOPE else n in names - set(counts) | names,
                        "group_bindings": counts.get(n, {}).get("group_bindings", 0),
                        "user_bindings": counts.get(n, {}).get("user_bindings", 0)} for n in names),
                      key=lambda r: (r["name"] != rpt.CLUSTER_SCOPE, r["name"]))
        return {"cluster": cluster_id, "scope": "all", "viewer": trusted_viewer(request), "coverage": cov,
                "total": len(rows), "limit": limit, "truncated": len(rows) > limit, "namespaces": rows[:limit]}

    @app.get("/api/clusters/{cluster_id}/report/namespaces")
    @consistent
    def report_namespaces(request, cluster_id,
                          ns: str = Query(description="Comma-separated namespace names, at most 50; `(cluster-scoped)` for cluster-wide bindings."),
                          include_members: bool = Query(default=False, description="Expand group rosters. Off by default — a file that gets emailed has no reader log — and recorded in the provenance when on."),
                          limit: int = Query(default=2000, ge=1, le=10000, description="Maximum rows per section across the requested namespaces; `totals` and `truncated` describe the whole.")) -> dict:
        """The namespace access report as data: per namespace, every group binding classified with who it reaches, every direct user grant, findings first, deterministically sorted.

        ADMINISTRATOR TIER: this is the RBAC binding surface `/bindings/findings` refuses at self, per namespace. The `coverage` block says whether absence is attested (rbac.namespaces). 404 when the module is off.
        """
        body = report_query(cluster_id, request, ns, include_members, limit)
        body["scope"] = "all"
        return {**body, "truncated": body["truncated"]}

    @app.get("/api/clusters/{cluster_id}/report/namespaces.html", response_class=HTMLResponse)
    @consistent
    def report_namespaces_html(request, cluster_id, ns: str = Query(description="As for the JSON form."),
                               include_members: bool = Query(default=False, description="As for the JSON form."),
                               limit: int = Query(default=2000, ge=1, le=10000, description="As for the JSON form."),
                               download: bool = Query(default=False, description="Send as an attachment (the canonical .html artifact) rather than a page.")) -> Response:
        """The same report as one self-contained HTML document with a print stylesheet — the canonical artifact; 'Save as PDF' is the browser's print.

        Stylesheet inlined so the file stands alone; escaped throughout; the provenance block carries the sha256 of the data so a PDF printed from it can be tied back. Same tier and module gates as the JSON form.
        """
        body = report_query(cluster_id, request, ns, include_members, limit)
        with open(REPORT_CSS, encoding="utf-8") as fh:
            css = fh.read()
        text = rpt.render_html(body, css, TITLE)
        headers = {"Cache-Control": "no-store"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="gsd_{cluster_id}_namespace-report_{body["generated_at"].replace("-", "").replace(":", "")}.html"'
        return HTMLResponse(text, headers=headers)

    @app.get("/api/clusters/{cluster_id}/report/namespaces.pdf")
    def report_namespaces_pdf(request, cluster_id, ns: str = Query(description="As for the JSON form."),
                              include_members: bool = Query(default=False, description="As for the JSON form."),
                              limit: int = Query(default=2000, ge=1, le=10000, description="As for the JSON form.")) -> Response:
        """The report as a PDF, rendered by the optional PDF module from the .html form. 404 when the module is not deployed.

        The app asks the loopback sidecar to render, forwarding the proxy's identity headers; the sidecar fetches the .html from this app with those same headers, so the tier is decided HERE, again, on that request. Materialised, not streamed; the sidecar's memory limit bounds the render.
        """
        require_cluster(cluster_id); require_report(); require_admin_tier(request)
        if not settings.namespace_report_pdf_url:
            raise HTTPException(status_code=404, detail="the PDF module is not deployed; open the .html form and print it")
        try:
            rpt.parse_namespaces(ns)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        import httpx
        forwarded = {h: v for h, v in ((USER_HEADER, request.headers.get(USER_HEADER)), (EMAIL_HEADER, request.headers.get(EMAIL_HEADER))) if v}
        try:
            r = httpx.get(f"{settings.namespace_report_pdf_url}/render", params={"cluster": cluster_id, "ns": ns, "include_members": str(include_members).lower(), "limit": limit}, headers=forwarded, timeout=90.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"the PDF module did not answer: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=(r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else "the PDF module refused"))
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return Response(r.content, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="gsd_{cluster_id}_namespace-report_{stamp}.pdf"', "Cache-Control": "no-store"})
```
(`version()` is the existing handler function, callable directly; `report_query` counts as store calls only inside `rpt.build`, and the handlers are decorated `@consistent` regardless. The `truncated` literal keeps R3's regex honest.)

#### `index.html` — Namespace audit section

`view` gains `reportSearch: "", reportSelected: new Set(), reportIncludeMembers: false`; `data` gains `reportUniverse: null`; `applyPosition`'s cluster-switch block clears `data.reportUniverse = null; view.reportSelected = new Set();`. `SEARCH_BOXES` gains `reportSearch: { id: "f-report-search", label: "Find namespace", placeholder: "filter the report list", title: "Filters the namespaces offered to the report as you type. Escape clears.", help: "Filters the namespace list of the report card as you type. Several words are combined with AND. Press Escape to clear." }`; `renderFilters` adds `if (view.page === "nsaudit" && reportEnabled() && !narrowedReader()) html += searchBoxHtml("reportSearch");`. `refresh()` on nsaudit when `reportEnabled() && !narrowedReader()` fetches `want.reportUniverse = guard403(get(`${base}/report/namespaces/universe?limit=1000`))`, assigned and fingerprinted. `render()` gains the `#main` focus restore by id (see below). `nsAuditPage` returns `directUserGrants(ub) + namespaceReportCard()` at the wide tier.

```js
function reportEnabled() {
  const v = data.version;
  return !!(v && v.features && v.features.namespace_report === true);
}

/* The report card: a filterable checklist of switch-styled rows over the universe the server
   offers (docs/namespace-report-design.md §5 — never a wall of toggles), the roster opt-in,
   and three GET links. Selection lives in `view` so the 60 s repaint keeps it; the links are
   rendered disabled at zero selected. */
function namespaceReportCard() {
  if (!reportEnabled()) return "";
  const u = data.reportUniverse;
  if (!u) return `<section class="card" id="ns-report"><h3>Namespace access report</h3><div class="empty-note">Loading…</div></section>`;
  if (u.forbidden) return "";
  const all = u.namespaces || [];
  const shown = all.filter((n) => matchesSearch([n.name], view.reportSearch));
  const sel = view.reportSelected;
  const idFor = (name) => "ns-switch-" + name.replace(/[^a-z0-9-]/g, "_");
  const q = new URLSearchParams({ ns: [...sel].join(",") });
  if (view.reportIncludeMembers) q.set("include_members", "true");
  const base = `/api/clusters/${encodeURIComponent(view.cluster)}/report/namespaces`;
  const pdf = !!(data.version.features && data.version.features.namespace_report_pdf === true);
  const link = (id, href, label) => sel.size
    ? `<a class="btn" id="${id}" href="${esc(href)}"${id === "ns-report-open" ? ' target="_blank" rel="noopener"' : ""}>${label}</a>`
    : `<button type="button" class="btn" id="${id}" disabled title="Select at least one namespace">${label}</button>`;
  return `<section class="card" id="ns-report">
    <h3>Namespace access report</h3>
    <div class="filterbar-note" id="ns-report-coverage">${esc(u.coverage.note)}</div>
    <div class="ns-controls" style="margin-top:8px">
      <button type="button" class="linkish" id="ns-report-all">Select all (${shown.length} shown)</button>
      <button type="button" class="linkish" id="ns-report-clear">Clear</button>
      <span class="muted" id="ns-report-count">${sel.size} selected</span>
    </div>
    <ul class="switch-list" role="group" aria-label="Namespaces to report on">
      ${shown.map((n) => `<li><label class="switch" for="${idFor(n.name)}">
        <input type="checkbox" role="switch" id="${idFor(n.name)}" data-ns="${esc(n.name)}"${sel.has(n.name) ? " checked" : ""}>
        <span class="switch-name mono">${n.name === "(cluster-scoped)" ? "cluster-wide" : esc(n.name)}</span>
        <span class="muted">${n.group_bindings} group · ${n.user_bindings} direct${n.exists === false ? " · <strong class=\\"err\\">no longer exists</strong>" : ""}</span>
      </label></li>`).join("")}
    </ul>
    ${u.truncated ? `<div class="truncation-note">Showing the first ${all.length} of ${u.total} namespaces.</div>` : ""}
    <label class="filterbar-note"><input type="checkbox" id="ns-report-members"${view.reportIncludeMembers ? " checked" : ""}>
      Include membership rosters (recorded in the report's provenance)</label>
    <div class="ns-controls" style="margin-top:8px">
      ${link("ns-report-open", `${base}.html?${q}`, "Open report")}
      ${link("ns-report-html", `${base}.html?${q}&download=true`, "Download .html")}
      ${pdf ? link("ns-report-pdf", `${base}.pdf?${q}`, "Download PDF") : ""}
    </div>
    <div class="filterbar-note" style="margin-top:6px">Direct bindings only; role rules are not evaluated. The
      .html is the canonical artifact and carries a sha256 of its data; print it for a PDF.</div>
  </section>`;
}
```
`wireNsAudit` gains: switches `onchange` → add/delete in `view.reportSelected`, `render()`; `#ns-report-all` → add every shown name; `#ns-report-clear`; `#ns-report-members` → flag. `render()` edit — OLD:
```js
function render() {
  renderFilters();
  const main = $("main");
```
NEW:
```js
function render() {
  renderFilters();
  const main = $("main");
  // Focus survives the repaint for any element in #main that carries an id — renderFilters'
  // rule, extended to the page: the report switches are the first controls in #main a keyboard
  // user rests on across the 60 s poll.
  const activeInMain = document.activeElement;
  const restoreId = activeInMain && activeInMain.id && main.contains(activeInMain) ? activeInMain.id : null;
```
and before `renderScopePill();`:
```js
  if (restoreId) { const el = $(restoreId); if (el) el.focus({ preventScroll: true }); }
```
CSS (`app.css`, tokens only): `.switch-list { list-style: none; margin: 8px 0; padding: 0; max-height: 320px; overflow: auto; }`, `.switch { display: flex; align-items: center; gap: 10px; padding: 4px 0; cursor: pointer; }`, `.switch input { appearance: none; width: 34px; height: 18px; border-radius: 999px; background: var(--baseline); border: 1px solid var(--border); position: relative; margin: 0; cursor: pointer; }`, `.switch input::before { content: ""; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%; background: var(--surface-1); transition: left 120ms ease; }`, `.switch input:checked { background: var(--accent); }`, `.switch input:checked::before { left: 18px; }`, `@media (forced-colors: active) { .switch input { appearance: auto; width: auto; height: auto; } }`.

### Files (PDF module)

#### New `local-development/gsd/reportpdf.py`
```python
"""The PDF module: a loopback sidecar that renders the dashboard's own report HTML to PDF.

Its OWN image (Containerfile.report), because WeasyPrint's C libraries are a CVE surface and a
memory spike the poller must never share (docs/namespace-report-design.md §4, §10). It holds no
cluster credential and no data: every request forwards the proxy's identity headers back to the
app, which decides the tier again on that request. GET only. weasyprint is imported lazily so the
main image, which never installs it, can still import this module's tests.
"""

from __future__ import annotations

import logging
import os

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import Response

from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER

log = logging.getLogger(__name__)
VARIANTS = ("", "pdf/a-3b")


def _render_pdf(html: str, variant: str) -> bytes:
    from weasyprint import HTML  # only the sidecar image has it
    kwargs = {"pdf_variant": variant} if variant else {}
    return HTML(string=html, base_url=None).write_pdf(**kwargs)


def build_app(upstream: str, variant: str, render=_render_pdf) -> FastAPI:
    if variant not in VARIANTS:
        raise ValueError(f"GSD_REPORT_PDF_VARIANT must be one of {VARIANTS}, not {variant!r}")
    app = FastAPI(title="group-sync-dashboard report module", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/render")
    def render_report(request: Request, cluster: str = Query(...), ns: str = Query(...),
                      include_members: bool = Query(default=False),
                      limit: int = Query(default=2000, ge=1, le=10000)) -> Response:
        # The identity the proxy stamped, forwarded verbatim; the app's own gate decides.
        headers = {INTERACTION_HEADER: "1"}
        for h in (USER_HEADER, EMAIL_HEADER):
            if request.headers.get(h):
                headers[h] = request.headers[h]
        try:
            r = httpx.get(f"{upstream}/api/clusters/{cluster}/report/namespaces.html",
                          params={"ns": ns, "include_members": str(include_members).lower(), "limit": limit},
                          headers=headers, timeout=60.0)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"the dashboard did not answer: {type(exc).__name__}") from exc
        if r.status_code != 200:
            detail = r.json().get("detail") if r.headers.get("content-type", "").startswith("application/json") else "refused"
            raise HTTPException(status_code=r.status_code, detail=detail)
        return Response(render(r.text, variant), media_type="application/pdf")

    return app


def create_app() -> FastAPI:
    logging.basicConfig(level=os.environ.get("GSD_LOG_LEVEL", "INFO").upper() if os.environ.get("GSD_LOG_LEVEL", "INFO").upper() in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL") else "INFO")
    return build_app(os.environ.get("GSD_REPORT_UPSTREAM", "http://127.0.0.1:8080").rstrip("/"),
                     os.environ.get("GSD_REPORT_PDF_VARIANT", ""))
```
(`request.headers[h]` is the proxy's on an inbound that came through the proxy; the sidecar is loopback-only, exactly the app's own trust argument in `docs/ACCESS_CONTROL.md` §1.)

#### New `local-development/Containerfile.report`
Same shape as `Containerfile` (build → runner → pack → final) with these differences: the build stage also `pip install weasyprint>=63`; the pack stage `dnf install -y pango cairo gdk-pixbuf2 fontconfig harfbuzz fribidi dejavu-sans-fonts` and packs bash, coreutils (for the stamp check) plus the library closure computed by a new `report-libs.sh` (loops `ldd` over `libpango-1.0.so.0 libpangoft2-1.0.so.0 libpangocairo-1.0.so.0 libcairo.so.2 libgdk_pixbuf-2.0.so.0 libfontconfig.so.1 libharfbuzz.so.0 libfribidi.so.0` and copies every resolved path the runtime base lacks — the same "measured by ldd" rule, automated because the set is too large to list by hand); final stage copies `/install`, `/libpack/lib64`, `/usr/share/fonts/dejavu`, `/etc/fonts`, sets `ENV GSD_REPORT_UPSTREAM=http://127.0.0.1:8080 GSD_REPORT_PDF_VARIANT=""` plus the stamp env, `USER 65532`, and proves itself with `report-image-proof.py` (imports `gsd.reportpdf`, `weasyprint`, renders `<p>ok</p>` to PDF and asserts `%PDF` in the first bytes; pip must not import), `EXPOSE 8090`, `CMD ["python3.14","-m","uvicorn","gsd.reportpdf:create_app","--factory","--host","127.0.0.1","--port","8090","--workers","1"]`. `.containerignore` unchanged. `tests/test_publish_paths.py` extended to scan both Containerfiles (`for cf in (CONTAINERFILE, CONTAINERFILE_REPORT)`), and `publish.yml` gains `local-development/Containerfile.report`, `report-libs.sh`, `report-image-proof.py` to `paths` and a second build step `IMAGE_NAME=group-sync-dashboard-report CONTAINERFILE=Containerfile.report ./build-and-push-external.sh [--release-tags]` (the script already reads both variables — `build-and-push-external.sh#IMAGE_NAME`). A tiny `build-and-push-report.sh` wrapper sets the two variables, rejects `--update-values`/`--deploy` (they target the main image's values) and execs the main script.

#### Chart
`values.yaml`:
```yaml
features:
  namespaceReport:
    # The namespace access report (docs/namespace-report-design.md §10): a card on Namespace audit
    # with a filterable checklist of namespaces, and GET endpoints that return the report as data
    # and as one self-contained HTML the browser prints. ADMINISTRATOR TIER — it is the binding
    # surface per namespace, which /bindings/findings already refuses at self. OFF by default: a
    # new surface and a policy choice. Requires rbac.bindings (refused otherwise). Coverage: with
    # rbac.namespaces the report attests absence; without it, it says "none observed".
    enabled: false
    pdf:
      # The OPTIONAL PDF module: a loopback sidecar on its own image (WeasyPrint and its C
      # libraries), so the CVE surface and any memory spike stay out of the poller's container.
      # It renders the same .html the dashboard serves, forwarding the viewer's identity so the
      # tier is decided by the dashboard again. OFF by default: a second image. Requires
      # features.namespaceReport.enabled (refused otherwise).
      enabled: false
      image:
        repository: quay.io/ephico2real/group-sync-dashboard-report
        tag: ""        # empty resolves Chart.appVersion, like image.tag
        digest: ""     # wins over tag, like image.digest
        pullPolicy: Always
      # "" for a plain PDF; "pdf/a-3b" for archival PDF/A-3b (open question B).
      variant: ""
      resources:
        requests: {cpu: 50m, memory: 128Mi}
        limits: {cpu: 500m, memory: 768Mi}
rbac:
  # (after identities)
  # Namespace objects, get/list, core group. OFF by default: extra RBAC. On, the poller reads them
  # on the binding cadence and the namespace report can say "this namespace exists and has no
  # grants" (attesting absence, open question C) and "this namespace no longer exists".
  namespaces: false
```
`rbac.yaml` rule `- apiGroups: [""] resources: ["namespaces"] verbs: ["get","list"]` under `{{- if .Values.rbac.namespaces }}`. `configmap.yaml`: `namespaceReportEnabled`, `namespacesReadEnabled: {{ .Values.rbac.namespaces }}`, and `{{- if .Values.features.namespaceReport.pdf.enabled }}namespaceReportPdfUrl: "http://127.0.0.1:8090"{{- end }}`. `deployment.yaml`: the two `fail` guards (pdf without report; report without `rbac.bindings`), and the sidecar container (`report-pdf`, `gsd.reportImage` helper mirroring `gsd.image`, env `GSD_REPORT_UPSTREAM`, `GSD_REPORT_PDF_VARIANT` validated by a `gsd.reportPdfVariant` helper that refuses anything but `""`/`pdf/a-3b`, `GSD_LOG_LEVEL`, the same `securityContext`, `tmp` mount, its own resources, no probes — a failing sidecar readiness would remove the whole pod from the Service, so its health is reported by the `.pdf` endpoint's 503 instead).

### Tests

- `tests/test_report.py` (new): `parse_namespaces` (dedupe, sentinel, invalid token, >50); `build()` over a seeded store — findings first, deterministic order, `exists` tri-state under `ok`/`off`/`forbidden` coverage, rosters only when `include_members`, `truncated` with a small `limit`, `sha256` stable across `generated_at`; `render_html` escapes a `<script>` group name and inlines the stylesheet; `report.css` uses no colour below 4.5:1 (only `#000`, `#fff`, `#555`).
- `tests/test_report_api.py` (new): 404 when the module is off; 403 at self with the exact `require_admin_tier` sentence; 200 at wide with R3 fields (`total`/`truncated` on universe, `totals`/`truncated` on the report); 422 on a bad `ns`; the `.html` form sets `Content-Disposition` only with `download=true`; the `.pdf` form 404s without the module and, with `namespace_report_pdf_url` set and an `httpx.MockTransport`-backed monkeypatch of `httpx.get`, forwards `X-Forwarded-User` and returns `application/pdf`; `feature_flags` reports `namespace_report`/`namespace_report_pdf`.
- `tests/test_reportpdf.py` (new): `build_app(upstream, "", render=fake)` with `httpx.MockTransport`: forwards identity + interaction headers, 403 from upstream becomes 403 with the same detail, 200 becomes `application/pdf`; bad variant raises; `pytest.importorskip("weasyprint")` test renders a real one-line PDF when the library is present.
- `tests/test_poller_users_read.py`-style `tests/test_namespaces_read.py`: 200/403/off matrix on `refresh_bindings`.
- `tests/test_chart_strategy.py`: report off renders no sidecar and `namespaceReportEnabled: false`; pdf without report fails; report without bindings fails; on → sidecar present with `127.0.0.1` host and `namespaceReportPdfUrl`; `rbac.namespaces` rule off/on, core group, `get,list`; variant validation.
- `tests/test_ui.py`: a `report_server` fixture (`namespace_report_enabled=True`, proxy on, `_TierByName`, seeded `replace_namespaces` for the `exists` states): the card renders for `root` with switch rows whose `role="switch"`; typing in `#f-report-search` filters rows; "Select all (N shown)" honours the filter; links are disabled buttons at zero and become GET links naming `ns=`; a focused switch keeps focus across `render()`; the `.html` opened in a new page has the provenance block (cluster, generated-at ending `Z`, viewer `root`, coverage note, sha256) and `@page` rule; `page.emulate_media(media="print")` hides `.no-print`; `alice` sees no card and `/report/namespaces?ns=prod-ns` answers 403; `page.pdf()` on the report page produces bytes starting `%PDF` (Chromium's print path, the browser-print design proven).
- `tests/test_api_contract.py`, `tests/test_storage_seam.py`, `tests/test_no_duplicate_methods.py`, `tests/test_read_snapshot_scope.py`, `tests/test_publish_paths.py`, `tests/test_docs_citations.py` run unchanged and must stay green.

### Docs, changelog, chart

- `docs/namespace-report-design.md`: the PARKED banner becomes `> **IMPLEMENTED — application 0.15.0, chart 0.14.0.** The five §9 questions were answered in §10 below…`; "Status: proposed, not built" becomes "Status: built; §1–§9 are the record of the design, §10 the decisions"; new §10 with the table above, the architecture comparison, the switch interactions, the alternative for E, and the CronJob requirements for A, citing `gsd/report.py#build`, `gsd/api.py#report_namespaces`, `gsd/reportpdf.py#build_app`, `charts/group-sync-dashboard/values.yaml#namespaceReport`, `local-development/Containerfile.report`.
- `README.md`: the docs table row loses **PARKED** ("per-namespace access reports as HTML/PDF, the answer on `--openshift-sar`, and the PDF module"); "Not built yet" drops the report and keeps "unattended/scheduled reports".
- `docs/ACCESS_CONTROL.md` §3 gains the row `| Namespace report | *For administrators only* | all | all |`; §4 the four endpoints at **403** self / all wide; `docs/reference-architecture.md` RBAC table gains `namespaces` (core, only when `rbac.namespaces`).
- `local-development/API.md`: the four paths with field meanings (`coverage.attests_absence`, `sha256`, `include_members`).
- `docs/CHANGELOG.md` `Application 0.15.0 — chart 0.14.0`: the module, the answers, migration 9, the second image and its tag scheme.
- Chart README rows: `features.namespaceReport.enabled`, `.pdf.enabled`, `.pdf.image.*`, `.pdf.variant`, `.pdf.resources`, `rbac.namespaces`.
- `Chart.yaml`: `version: 0.14.0`, `appVersion: "0.15.0"`, comment: MINOR — a new optional sidecar container, two new grants-adjacent values, two guards.

### Verification

```
./.venv/bin/python -m pytest tests/test_report.py tests/test_report_api.py tests/test_reportpdf.py tests/test_namespaces_read.py tests/test_api_contract.py tests/test_storage_seam.py tests/test_migrations.py -q
./.venv/bin/python -m pytest tests/test_ui.py -q -k "NamespaceReport"
./.venv/bin/python -m pytest tests/test_chart_strategy.py -q -k "Report or Namespaces"
IMAGE_NAME=group-sync-dashboard-report CONTAINERFILE=Containerfile.report ./build-and-push-external.sh --build-only   # proof step prints "report image OK"
helm template t charts/group-sync-dashboard --set ingress.host=t --set features.namespaceReport.pdf.enabled=true                 # -> Error: requires features.namespaceReport.enabled
curl -H "Authorization: Bearer $(oc whoami -t)" "https://<route>/api/clusters/crc-local/report/namespaces?ns=prod-ns" | jq .coverage   # needs apiTokenAccess; self tier -> 403 "For administrators only…"
```

### Risks

- The report widens a tier → every endpoint calls `require_admin_tier`; the sidecar forwards, never asserts, identity; tested at self.
- The PDF sidecar OOMs → its own container and limit; the poller is untouched; `.pdf` answers 503.
- The library closure in `Containerfile.report` drifts with the base → computed by `ldd` at build and proven by a real render before the image ships.
- A report attests absence it cannot → `coverage.attests_absence` is false unless `rbac.namespaces` read `ok`, and the note prints in every rendering.

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
