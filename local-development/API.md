# API reference

Every endpoint is **read-only**. None returns a token, none accepts one from the browser,
and none mutates cluster state — the dashboard observes and never writes (§9, §11).

FastAPI serves interactive docs from the running instance, generated from the code rather
than from this file, so they cannot drift:

| | |
|---|---|
| `/docs` | Swagger UI — try requests against the live instance |
| `/redoc` | ReDoc |
| `/openapi.json` | the raw schema, for client generation |

This document adds the part a schema cannot express: what each field *means*, and which ones
are routinely misread.

## Clusters

### `GET /api/clusters`

One entry per configured cluster.

```json
[{
  "id": "crc-local",
  "api_url": "https://kubernetes.default.svc",
  "enabled": true,
  "reachable": true,
  "status": "ok",
  "last_poll": "2026-08-02T00:14:32Z",
  "error": null,
  "groupsync_count": 2,
  "group_count": 62,
  "empty_groups": 0,
  "unattributed_groups": 0,
  "oldest_last_sync": "2026-08-02T00:00:11Z",
  "dangling_bindings": 0,
  "unresolved_bindings": 9,
  "builtin_bindings": 145
}]
```

`reachable` is **`null`, not `false`, when the cluster has never been polled.** A
never-polled cluster and an unreachable one are different states, and rendering the first as
`false` would report a failure that has not happened.

`status` distinguishes `ok` / `auth_failed` / `forbidden` / `unreachable`. `forbidden`
matters most: a ServiceAccount that can list GroupSyncs but not Groups produces a
half-populated view that otherwise looks exactly like a cluster with no groups.

## GroupSync CRs

### `GET /api/clusters/{cluster_id}/groupsyncs`

```json
[{
  "name": "ldap-groupsync",
  "namespace": "group-sync-operator",
  "schedule": "*/30 * * * *",
  "ldap_filter": "(&(objectClass=groupOfNames)(cn=app-ocp-rbac-*))",
  "last_sync_at": "2026-08-02T00:00:11Z",
  "generation": 2,
  "group_count": 41,
  "state": "ok",
  "next_expected": "2026-08-02T00:30:00Z",
  "interval_seconds": 1800,
  "schedule_valid": true,
  "error_at": "2026-07-30T15:16:17Z",
  "error_message": "failed calling webhook …",
  "error_is_current": false
}]
```

**`error_is_current` is the field to read, not `error_at`.** The operator never clears
`ReconcileError` on a later success, so a perfectly healthy CR carries a months-old error
indefinitely. `error_at` alone would paint it permanently red; `error_is_current` compares
the error's transition time against the success's (§2.1).

`state` is computed on read, never stored:

```text
ok        age <= 1 interval + grace
late      age >  1 interval + grace
overdue   age >  2 intervals + grace
unknown   unreachable, never synced, or an unparseable schedule
```

`grace` (default 120s) exists because the literal thresholds flap: a sync lands 3–14s after
its cron minute and is observed up to a poll interval later, so a healthy CR exceeds one
interval for ~70s of *every* cycle.

`unknown` is not a synonym for healthy. A CR with an unparseable schedule sits in `unknown`
forever, so `/api/alerts` reports `invalid_schedule` and `sync_stopped` separately — without
those, a CR that stopped syncing days ago would be entirely silent.

`next_expected` comes from a real cron parser. `0 * * * *` and `*/30 * * * *` both look
hourly if you only measure gaps between events; they differ only at `:30`.

### `GET /api/clusters/{cluster_id}/groupsyncs/{name}/events`

Query: `since` (RFC3339), `limit` (1–2000, default 200).

The accumulated sync timeline. `synced_at` is the operator's timestamp; `observed_at` is
ours, and the difference is **our** polling lag, not the operator's. Conflating them would
blame the operator for our latency.

**An empty list means this dashboard has not seen a sync yet** — not that the operator never
synced. The API keeps no history, so the timeline only covers the period since the dashboard
started (§2). The response says so in a `note` field.

## Groups

### `GET /api/clusters/{cluster_id}/groups`

Query: `state` = `all` (default) | `empty` | `unattributed`.

The two filters are **mutually exclusive by design**. `empty` means *synced, zero members* —
an operator-managed group whose members vanished, which points at LDAP. A hand-made group
with no members is `unattributed`, a different fault with a different fix. Reporting it as
both says the wrong thing twice.

### `GET /api/clusters/{cluster_id}/groups/{name}`

Adds `members`, `changes` and `bindings`.

Each member carries two dates:

* `first_seen_at` — start of the current unbroken membership
* `original_first_seen_at` — the first time we ever saw them in this group

They differ when a user left and rejoined. Showing only the first would tell an auditor that
access is newer than it is.

**A deleted group returns 200, not 404**, when history exists for it. "This group is gone,
here is who was in it" is the answer to that click; 404 strands the reader. `deleted: true`
marks it.

## Users

### `GET /api/clusters/{cluster_id}/users`

Every user with a group count.

### `GET /api/clusters/{cluster_id}/users/{name}`

The reverse lookup: every group the user is in, every binding that reaches them, and their
membership history. Each binding row carries `via_group`, because "why do they have this?"
is the next question after "do they have it".

**A user with no current groups returns 200, not 404**, if any history exists. "They are in
nothing now" is the answer, not an error. 404 only when the user has never been seen.

### `GET /api/clusters/{cluster_id}/membership-changes`

Query: `limit` (1–1000, default 100). Joins and departures cluster-wide.

Each change carries `group_synced_at` — the group's own sync-time when the change was seen.
That distinguishes *"the operator did this"* from *"someone edited the object"*: a change
stamped with a stale sync-time did not come from a sync.

## RBAC

### `GET /api/clusters/{cluster_id}/bindings/findings`

Every group-subject binding, classified. Despite the path, this returns **all** bindings,
including healthy ones — the caller filters.

```json
{
  "total": 228,
  "counts": {"ok": 74, "dangling": 0, "unresolved": 9, "built_in": 145},
  "ok": [], "dangling": [], "unresolved": [], "built_in": []
}
```

| Tier | Meaning | Alerts? |
|---|---|---|
| `ok` | the group exists; access reaches its members | no |
| `dangling` | the group **was** operator-managed and has disappeared | **yes, critical** |
| `unresolved` | names a group that has never existed here | no |
| `built_in` | `system:*` virtual group; no object expected | no |

`unresolved` deliberately does not alert: a group never observed cannot be distinguished
from one that simply has not synced yet. It is still worth reading — those bindings grant
nobody — which is why the UI shows them even though nothing pages.

Classification tests **provenance before the `system:` prefix**. The reverse order silently
downgraded a genuinely dangling binding to `built_in` whenever a managed group carried that
prefix — a grants-nobody binding with no alert.

Direct bindings only. Role rules are never fetched or expanded, so this is not an
effective-permission calculation and must not be presented as one.

## Alerts

### `GET /api/alerts`

Computed on read across all clusters, sorted critical first.

Kinds: `overdue`, `invalid_schedule`, `sync_stopped`, `empty_group`, `unattributed`,
`stale_group`, `reconcile_error`, `dangling_binding`, plus the poll outcome for a degraded
cluster.

A degraded cluster's group-level alerts are **skipped entirely**, because its cached rows are
stale by definition and would report yesterday's state as today's.

## Operational

| Endpoint | Notes |
|---|---|
| `GET /healthz` | liveness. Unconditional |
| `GET /readyz` | readiness. **Not** gated on a reachable cluster — an unreachable cluster is a thing this dashboard exists to display, so failing readiness for one would take it down exactly when it has something to report |
| `GET /api/version` | `{version, commit, branch, dirty}` from the build stamp. `dirty: true` means no commit reproduces the running image |
| `GET /metrics` | Prometheus exposition. Unauthenticated so a ServiceMonitor can scrape it, which is why it emits counts and states only — never a group or user name |

## Trying it

```bash
ROUTE=$(oc get route group-sync-dashboard -n group-sync-dashboard -o jsonpath='{.spec.host}')

curl -sk "https://$ROUTE/api/clusters" | python3 -m json.tool
curl -sk "https://$ROUTE/api/clusters/crc-local/bindings/findings" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['counts'])"
curl -sk "https://$ROUTE/api/version"
```

Locally, `http://127.0.0.1:8099` and `/docs` for the interactive version.
