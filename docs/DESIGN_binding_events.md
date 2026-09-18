# DESIGN — binding_event: the bindings' membership history (#167, #175)

**Ruled by the operator, 2026-09-17:** build `binding_event`; "history" stays in #167; the
first-observation defect in `membership_event` (#175) is fixed in the same change, because the
two share one mechanism.

## Why

`rbac_group_binding` and `user_binding` are replaced every refresh (`Store.replace_bindings`,
`replace_user_bindings`). A RoleBinding created or deleted between two refreshes left no trace,
so (1) a namespace had no history, (2) the landing page's "what changed" was blind to the grant
that changed what a person can reach, and (3) #156 had no in-app series for bindings. The
membership side already solved the shape — `membership_event` is diff-and-append because "the
API has no history". Bindings now get the same table, written from the same rows, in the same
transaction as the replace.

## Data model

```sql
CREATE TABLE IF NOT EXISTS binding_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    subject_kind        TEXT NOT NULL,   -- Group | User
    subject_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,
    role_name           TEXT NOT NULL,
    is_platform         INTEGER NOT NULL DEFAULT 0,
    change              TEXT NOT NULL,   -- added | removed
    baseline            INTEGER NOT NULL DEFAULT 0,
    observed_at         TEXT NOT NULL
);
```
Indexes: `(cluster_id, binding_namespace, id DESC)`, `(cluster_id, subject_kind, subject_name, id DESC)`,
`(cluster_id, observed_at)` for retention. Migration **13** creates it and adds
`membership_event.baseline INTEGER NOT NULL DEFAULT 0`.

```sql
CREATE TABLE IF NOT EXISTS observation_state (   -- migration 14
    cluster_id          TEXT NOT NULL,
    stream              TEXT NOT NULL,            -- membership | binding:Group | binding:User
    PRIMARY KEY(cluster_id, stream)
);
```

Migration 14 seeds a marker for every cluster the store already holds rows for (current rows or
events of that stream), so an upgrade never re-describes existing rows as a first observation.
The marker is consumed inside the refresh's own write transaction: a rolled-back observation does
not spend it. Nothing removes it — a cluster taken out of `clusters:` keeps its rows too (#96).

**Identity** of a row for the diff is `(binding_kind, binding_namespace, binding_name, subject)`;
the compared value is `(role_kind, role_name)`. A role change is therefore one `removed` and one
`added` — no third verb.

## The baseline rule (the part designed, not copied)

Measured on CRC: `membership_event` held **76 / 87 / 5** `added` rows in one instant per cluster
— each cluster's first observation — and the 87 (prod-east, `2026-09-14T00:18:18Z`) had been read
as "a bulk onboarding". A first observation is not a change anyone made.

Rule, for both tables: a cluster's first observation of a stream — `membership`, `binding:Group`,
`binding:User` — is the refresh that consumes that stream's row in `observation_state`, **empty or
not**; every `added` row of that refresh is written with `baseline = 1`. The marker, not the rows,
decides: inferring "first" from "no current rows and no events" was an off-by-one (Codex, review
of #177 — an empty first poll left nothing behind, so the next poll read as the first observation
and its real additions were flagged), and it reopened the baseline whenever retention emptied a
stream. The rows are still written — `first_seen_at`, `original_first_seen_at` (a `MIN` over `added` events) and
the group-count cliff's window all depend on them — but a consumer renders a baseline row as
"first observed by this dashboard", never as "added". A new group or binding appearing in an
already-observed cluster is a real change and is not flagged. A refresh returning nothing for a
cluster that had rows is a real mass removal and is recorded as one; the poller never reaches
the replace on a fetch failure.

## Retention

`binding_event` joins `_HISTORY_TABLES`; `prune_binding_events` mirrors `prune_membership_events`
(after a backup, leader only, 5000/cycle). It **shares `membership_event`'s window**
(`retention.membershipEventsDays`): both answer "who could reach what, and since when", and a
second knob for the same question would be one more thing to keep equal. No chart change.

## API

`GET /api/clusters/{cluster_id}/binding-changes` — `namespace` (optional; `""` selects
ClusterRoleBindings), `limit` (1–1000). Envelope: `cluster, scope, viewer, count, limit,
truncated, baseline_rows, note, retention, changes[]`. Self tier: only rows naming the viewer
or a group the viewer belongs to (`user_groups` read at the call site, so R5 counts it).

## Metric

`gsd_binding_changes_total{cluster, change, subject_kind}` — counts only, pre-seeded per enabled
cluster × `{added, removed}` × `{Group, User}`; fed by `RuntimeSignals.note_binding_changes` from
the numbers the store returned. **No label carries a subject's name.**

## Consumers (later issues)

- #167 namespace detail: `binding_event` where `binding_namespace = ns`, merged with
  `membership_event` for the groups bound there.
- #158 "What changed": binding rows that name the viewer or their groups.
- #156 trends: the in-app bindings series; the metric above.

## Orchestrator's notes

- **Deviation from #175's first proposal ("write no events").** Silencing the first observation
  would break `original_first_seen_at`, `first_seen_at` and the existing membership tests (a
  first sync returning 2 is asserted). A `baseline` flag keeps every consumer intact and makes
  the honest rendering possible. Existing rows on an upgraded store keep `baseline = 0`.
- **Shared retention window** rather than `bindingEventsDays`: fewer knobs, same question; a
  separate window can be added without a migration if compliance ever needs it.
- **The marker replaced the inference (Codex, review of #177, C4 refuted).** The first cut decided
  "first observation" from "no current rows and no events of that kind"; Cursor had accepted the
  empty-first-poll edge as debt. Codex's probe (`first_empty=0 event_rows=0 second_nonempty=1
  second_baseline=1`) showed it is not an edge but an off-by-one: the second poll's rows are real
  additions. `observation_state` is consumed once per stream regardless of rows, which also closes
  the retention edge — a pruned stream no longer reopens its baseline. Three tests hold it.
- **One bound parameter for the viewer's groups (Codex, volunteered).** The self-scoped
  `binding_events` built one placeholder per group; a viewer in more groups than
  `SQLITE_LIMIT_VARIABLE_NUMBER` raised "too many SQL variables". The Group clause now reads
  `subject_name IN (SELECT value FROM json_each(?))` — one parameter, any group count; a test
  forces the limit to 16 with `setlimit` and reads through 21 groups.
- **Migration 14, not a rewrite of 13.** Codex's snippet rewrote migration 13 to create the marker
  table. CRC already carried `PRAGMA user_version 13` from the first deployment of this branch
  (measured on the pod), and `_migrate` skips any target at or below the current version — a
  rewritten 13 would never have run there. The marker table and its backfill are migration 14;
  the C4 semantics are Codex's unchanged.
