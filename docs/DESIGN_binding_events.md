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

**Identity** of a row for the diff is `(binding_kind, binding_namespace, binding_name, subject)`;
the compared value is `(role_kind, role_name)`. A role change is therefore one `removed` and one
`added` — no third verb.

## The baseline rule (the part designed, not copied)

Measured on CRC: `membership_event` held **76 / 87 / 5** `added` rows in one instant per cluster
— each cluster's first observation — and the 87 (prod-east, `2026-09-14T00:18:18Z`) had been read
as "a bulk onboarding". A first observation is not a change anyone made.

Rule, for both tables: when a cluster has **no current rows and no events of that kind**, the
refresh is its first observation and every `added` row is written with `baseline = 1`. The rows
are still written — `first_seen_at`, `original_first_seen_at` (a `MIN` over `added` events) and
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
