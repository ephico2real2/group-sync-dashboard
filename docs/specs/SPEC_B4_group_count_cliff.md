# SPEC B4 — Group-count cliff alert with read-only silencing

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | B — alerts |
| Release | R2 — Alerts, retention, Grafana |
| Version on release | app 0.12.0, chart 0.11.0 |
| Issue | [#58](https://github.com/ephico2real2/group-sync-dashboard/issues/58) |
| Status | in progress |
| Source | design agent output `abe89ca84ad184702`; two messages; the first ended inside a ```python fence with a partial `def test_env_overrides_the_file` and the second re-emitted that test from its first line under a new fence opener, so the partial tail and the duplicate opener were dropped and the code continues inside the original fence |

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

- First feature of R2: app 0.12.0, chart 0.11.0, schema migration 8 (as in the body). The index `membership_event_by_time` is defined here and reused by B2.
- Before the spec is applied, measure on CRC whether the group-sync-operator preserves a foreign annotation on a synced Group (annotate, force a sync, read back); the README's recommended silence path follows the measurement.
- The B3 half of the same design lands after this one; the shared `Chart.yaml` history comment in B4.8 that mentions `monitoring.grafanaDashboard` is written here for the cliff alert only, and B3 extends it.

- Routed here from the A3 review (PR #71): this is the first PR to edit `charts/group-sync-dashboard/Chart.yaml` after `local-development/prepare-release.py` landed. Correct the preamble sentence that says nothing but a human writes the file: the release script writes the version fields and the history lines from two arguments; the reasoning is still typed by the operator as the reason.

- Deviations recorded at implementation (PR for #58), each a defect in the body's own code or test found by running it: (1) `_cliff_settings` split the ConfigMap's comma-joined silence list without stripping, so `"a, b"` yielded `" b"`; stripped now, as the list branch already did. (2) `test_a_group_count_cliff_is_withheld_at_self_and_full_at_wide` called `_client` a second time AFTER seeding the cliff rows, and `_client` re-seeds with `replace_group_state`, wiping them; both clients are built first now. (3) `test_no_settings_means_module_off_on_the_collector` asserted the kind's name absent from the whole exposition while the body's own HELP text names it; the assertion is on a series (`kind="group_count_cliff`) now. (4) The body cites `docs/DESIGN_grafana_dashboard_and_group_count_cliff.md`, a design record that was never written; every reference points at this spec instead, and the README docs-table row for that file is not added (the programme row already covers `docs/specs/`). (5) The body's rule reads `monitoring.prometheusRule.for.groupCountCliff` but never adds the value; `groupCountCliff: 15m` is added to the `for:` block after `configError`, with the chart README's documented `15m`. (6) `test_migration_8…` uses try/finally: `Store` is not a context manager, as the body itself anticipated.

- MEASURED on CRC (2026-09-04T22:28Z): `oc annotate group app-ocp-rbac-abcd-ns-superuser groupsync-dashboard.io/silence-group-count-cliff=until=2026-12-31`; the GroupSync CR `app-ocp-rbac-group-groupsync` (schedule `*/30 * * * *`) synced at 22:30:07Z and the Group's annotation was still present afterwards, beside the operator's own `sync-time` and `ldap.uid`. The group-sync-operator PRESERVES foreign annotations, so the annotation is a durable silence and the README recommends it as designed (risk 1 closed).

- Deviation recorded at implementation: the body's `.silence-tag` rule set `font-size: 11px`; `tests/test_type_scale.py` requires a `--text-*` token, so it is `var(--text-xs)` (11px on the scale).

- Found in review (PR #72, Cursor Grok 4.6): the body's `drop < cliff.drop_ratio * before` is a float compare, and `0.07 * 100` is 7.000000000000001 as a double, so a drop of exactly seven in a hundred at ratio 0.07 — the boundary the values promise fires — stayed silent. Measured by brute force: 141 such boundaries among two-decimal ratios and group sizes up to 1000. The compare is exact now: `Fraction(drop, before) < Fraction(str(cliff.drop_ratio))`. (Cursor's own example, `0.1 * 30`, is exactly 3.0 on this interpreter, as were my first two; the class of defect is real and the examples had to be measured.) Also from that pass: the rule's summary hardcoded "half"; it names the configured ratio as a percentage. Measured myself: `EXPLAIN QUERY PLAN` uses `membership_event_by_time`; and `Store.group_detail` lacked `cliff_silence`, so the detail row could disagree with the list — added.

- Found in review (PR #72, Codex gpt-5.6-sol xhigh): (1) `group_count_changes` summed events with `observed_at >= since`; events stamped exactly at the boundary were written by the poll that defines the window's start, so the inclusive bound rewound that poll and reported the state BEFORE it (a real Store sequence: 20 → 5 → 8 in the boundary second reconstructed 20, not 8). Strictly after now, with the docstring saying why; the body's `test_a_deleted_group_records_its_departures` set `since` equal to the adds' timestamp and moves it one second earlier. (2) `cliff_silence` parsed `until=` with `date.fromisoformat` alone, which accepts the compact `20260905` that the documented grammar calls malformed; a `YYYY-MM-DD` shape check precedes the parse.

- Found in the second review pass (PR #72, Codex xhigh, on the fixed head): a `windowHours` shorter than the poll interval was accepted by the app and the chart; the window is reconstructed from polls, so such a window has no observation at its start and a cliff inside it vanished before the rule's `for: 15m` (measured: alert at 12:00, gone at 12:07 with a 6-minute window and an hourly poll). Both now refuse a window shorter than `pollIntervalSeconds`. The reviewer's further comparison of the window against the rule's `for:` duration was rejected: its Helm snippet calls a duration-parsing helper that does not exist and it supplied none.

## Batch preamble (verbatim from the design)

I have read everything the design needs. Here is the complete design document.

---

# DESIGN — B3 Grafana dashboard shipped with the chart, B4 group-count cliff alert with read-only silencing

**Status: specification.** Written from the code as it is on 2026-09-04 (application 0.11.0, chart 0.10.0). Every claim below is grounded in a file that was read; citations are `path#anchor`. Save this file as `docs/DESIGN_grafana_dashboard_and_group_count_cliff.md`.

## 0. Ground truth the design rests on

| Fact | Where |
|---|---|
| Metrics are collected from the store at scrape time by one collector; series are per cluster and per CR only, never per group or user, because `/metrics` is unauthenticated | `gsd/metrics.py` module docstring (`CARDINALITY IS DELIBERATELY BOUNDED`), `gsd/metrics.py#DashboardCollector` |
| The emittable alert-kind vocabulary is `gsd/metrics.py#ALERT_KINDS`; `tests/test_metrics.py#test_every_alert_kind_a_rule_references_is_one_the_collector_can_emit` holds it to every `kind="..."` literal in `state.py`, and every `gsd_alerts_total{kind="..."}` matcher in the rendered PrometheusRule to it | `gsd/metrics.py#ALERT_KINDS` |
| Every metric a rule references must be DECLARED (HELP line) by a bare `DashboardCollector(store, grace, None)` | `tests/test_metrics.py#test_every_metric_an_alert_references_is_declared_by_the_collector` |
| `gsd_alerts_total` promises parity with `/api/alerts` at the wide tier: both call `gsd/state.py#compute_alerts` with the same store reads; a degraded cluster reports one critical alert with its poll outcome as the kind and none of the computed kinds | `gsd/metrics.py#Kept in step with the /api/alerts call site`, `gsd/api.py#list_alerts`, `docs/DESIGN_metrics_refresh.md` §5.2 |
| Alerts are DERIVED at request time, never stored | `docs/reference-architecture.md#Derived, never stored` |
| `Alert` is a frozen dataclass `(cluster, kind, subject, detail, severity="warning")` with `as_dict()` | `gsd/state.py#Alert` |
| `compute_alerts` docstring still says the group-count cliff is EXCLUDED ("needs a tuned floor as well as a ratio, PLAN §8"); README says the same under `Not built yet` | `gsd/state.py#compute_alerts`, `README.md#Not built yet` |
| The self tier receives only the kinds in `SELF_ALERT_DETAILS`; a kind that names groups from the self-scoped Groups tab (`empty_group`, `unattributed`, `stale_group`) is withheld; a new kind defaults to withheld | `gsd/api.py#SELF_ALERT_DETAILS`, `gsd/api.py#_alerts_for_self` |
| `group_state` is REPLACED wholesale each poll (`DELETE` then `INSERT`) and holds `member_count` for the current poll only — no history | `gsd/store.py#Store.replace_group_state` |
| `membership_event` is append-only, one row per `(group, user, added|removed)` with our `observed_at`; a group that disappears upstream has every member recorded as `removed`; it has NO retention by design | `gsd/store.py#Store.sync_members`, `gsd/metrics.py#gsd_retention_rows_deleted_total` HELP ("membership_event and sync_event deliberately have none") |
| The poller builds group rows from `GroupView` (`name, member_count, sync_provider, group_synced_at, ldap_uid, members`); `_group_view` reads exactly two annotations, `SYNC_TIME_ANNOTATION` and `LDAP_UID_ANNOTATION` | `gsd/kube.py#GroupView`, `gsd/kube.py#_group_view`, `gsd/poller.py#poll_once` |
| The read-only precedent for something an administrator sets on a cluster object: `UNMANAGED_EXCEPTION_ANNOTATION` on bindings is read in `kube.py` and carried as the `exception` column; the dashboard writes nothing back | `gsd/kube.py#UNMANAGED_LABEL`, `gsd/audit.py#StampPlan` ("The discovery IS the deliverable — there is no write") |
| Schema changes go through `_MIGRATIONS` keyed by `PRAGMA user_version`; the latest is 7; a fresh DB gets `SCHEMA` and then replays every step, so `ALTER TABLE ADD COLUMN` must tolerate `duplicate column name` | `gsd/store.py#_MIGRATIONS`, `gsd/store.py#_migrate`, `tests/test_migrations.py#test_a_fresh_database_lands_on_the_latest_migration` |
| Settings come from the ConfigMap's `clusters.yaml` via `load_settings`, env overriding through `_bool_setting` / `_num_setting`; a `ConfigError` refuses to start | `gsd/config.py#load_settings`, `gsd/config.py#_bool_setting`, `gsd/config.py#_num_setting` |
| The chart's monitoring objects are gated by `monitoring.serviceMonitor.enabled` / `monitoring.prometheusRule.enabled`, both default false because the CRDs may be absent; under Argo they carry `SkipDryRunOnMissingResource=true` | `charts/group-sync-dashboard/templates/monitoring.yaml`, `charts/group-sync-dashboard/values.yaml#monitoring:` |
| Alert thresholds live in values: `overdueSeconds 7200`, `notPollingSeconds 600`, `walMiB 256`, `captureStalledSeconds 1800`, `backupStaleSeconds 43200` | `charts/group-sync-dashboard/values.yaml#prometheusRule:` |
| Chart tests shell out to `helm template` via a `render(**values)` helper and skip when helm is absent | `tests/test_chart_strategy.py#render` |
| The Overview renders alerts in one function; the UI test asserts every `.alert-row .badge` label is `critical` or `warning` | `gsd/static/index.html#function alertsCard`, `tests/test_ui.py#test_alerts_use_severity_words_not_cr_state_words` |
| Chart changes bump `Chart.yaml` `version` with a `# CHART x.y.z (date), KIND: reason` line above it; `appVersion` must equal `pyproject.toml` and `gsd/__init__.py` | `charts/group-sync-dashboard/Chart.yaml`, `tests/test_chart_versions.py` |
| `docs/CHANGELOG.md` has no `## Unreleased` heading today — one is added | `docs/CHANGELOG.md` |
| Doc citations must resolve (`path#anchor`; `.json` is not a citable extension, so the dashboard file is referred to by plain path) | `tests/test_docs_citations.py#CITATION` |

---


## Design (verbatim)

# FEATURE B4 — Group-count cliff alert, with read-only silencing

## B4.1 Goal

Report a group whose membership fell by a large fraction within a window — the "half the team lost access overnight" event that a directory-side change or a mis-resolved LDAP filter produces, which today raises nothing (`empty_group` fires only at zero). Ship it as alert kind `group_count_cliff`, on `/api/alerts`, `gsd_alerts_total`, a PrometheusRule and the Overview card, with two read-only ways for an administrator to silence a known cliff without hiding it.

## B4.2 Switch, default, why

`config.alerts.groupCountCliff.{enabled: true, minMembers: 10, dropRatio: 0.5, windowHours: 24, silence: []}`.

**Default ON**, by the house rule's test: it is cheap (one indexed aggregate query per cluster per read, no new table), safe (read-only; no write to any cluster), needs no RBAC or credential beyond the Group list the poller already holds, and has no side effect (the annotation is READ, never written). The only cost of ON is a warning-severity alert row, and the floor is what keeps that honest:

- `minMembers: 10` — below ten, a fifty-percent drop is one or two people, which is ordinary churn (a two-member group going to one is a 50% cliff by arithmetic and a non-event in practice). Ten is where "half" starts to mean "a population", and it is the number this repo's own README parked the feature on: "needs a floor as well as a ratio".
- `dropRatio: 0.5` — half. Smaller fires on a large team's normal weekly turnover; larger misses the LDAP-filter regression that drops a third of a directory tree.
- `windowHours: 24` — one business day: a cliff that happens over several polls is still one event, and a directory that fixes itself within a day still deserved the row (it is reported for the rest of the window, then clears). Hours rather than polls, because `membership_event.observed_at` is a timestamp and polls are not guaranteed evenly spaced.

An operator with a small directory raises nothing; one with a 50k-member directory lowers `dropRatio` or raises the floor. Both are values.

## B4.3 Detection — where the numbers come from

**Decision: derive at read time from `membership_event`, inside `gsd/state.py#compute_alerts`, from a new one-query store read. No sample table.**

The alternatives considered:

1. *Compare with the previous poll's count.* `group_state` is replaced wholesale (`gsd/store.py#Store.replace_group_state`); there is no previous count. It would need a new `group_count_sample` table, a migration, a retention loop tied to the window, and it only sees single-poll cliffs — a drain across three polls is invisible.
2. *A compact `group_count_sample(cluster_id, group, observed_at, member_count)` table written on change.* Honest and cheap to write, but it is a SECOND COPY of what `membership_event` already records exactly: every added/removed row IS a count delta with our timestamp, retained forever by design. `gsd/metrics.py`'s own opening argument — do not mirror the source of truth into a second structure that can drift — applies.
3. *Derive from `membership_event`.* For a group present in `group_state` with current count `after`, the count at the window's start is exactly `before = after + removed − added`, summing the group's events with `observed_at >= now − window`. That is the count a poll `window` ago would have recorded, because `sync_members` writes one event per member transition and none otherwise. No new table; one aggregate `GROUP BY group_name` per cluster; one new index `(cluster_id, observed_at)` so the window bounds the scan.

Option 3 is the cheaper honest one. Boundaries it gets right by construction:

- A brand-new group with 50 members seen for the first time inside the window: `before = 50 − 50 + 0 = 0 < minMembers` — no alert.
- A group that dropped 20→5 and recovered to 20 inside the window: `before = 20 − 15 + 15 = 20`, `after = 20` — no alert (net, which is what a reader wants).
- A group deleted upstream: absent from `group_state`, so not evaluated; `DanglingRoleBinding`/`dangling_binding` already own that case.
- A degraded cluster: `list_alerts` and the collector skip `compute_alerts` entirely (existing behaviour), so no stale cliff is reported.

Read-time placement keeps the `gsd_alerts_total` ↔ `/api/alerts` parity contract untouched: both call sites pass the same two new arguments. "Detection on the poll thread" in the brief is satisfied in substance — the poll thread WRITES the observations (`sync_members` events, and now the silence annotation) and performs no second computation that could disagree with the read.

## B4.4 Silencing — read-only, two sources, never hidden

1. **Group annotation** `groupsync-dashboard.io/silence-group-count-cliff`, value `"true"` or `until=YYYY-MM-DD` (inclusive, UTC calendar date; expired ⇒ not silenced; any other value ⇒ not silenced). Read by `gsd/kube.py#_group_view` from the Group objects the poller already lists — the same read-only pattern as `UNMANAGED_EXCEPTION_ANNOTATION` on bindings — carried into `group_state` as ONE new column `cliff_silence` (this annotation only, not all annotations). The dashboard never writes it; an administrator does with `oc annotate group <name> groupsync-dashboard.io/silence-group-count-cliff=until=2026-10-01`.
2. **Values** `config.alerts.groupCountCliff.silence: [names or fnmatch globs]`, e.g. `["app-ocp-rbac-contractors-*"]`.

A silenced cliff is still computed and reported: kind `group_count_cliff_silenced`, severity `warning`, `silenced: true`, `silenced_by: "annotation" | "values"`. On `/metrics` it counts under `gsd_alerts_total{kind="group_count_cliff_silenced"}` — a second KIND value rather than a `silenced` label, so the label set of `gsd_alerts_total` is unchanged for every existing rule and the cardinality bound stays "per cluster × fixed vocabulary". The PrometheusRule matches `kind="group_count_cliff"` only, so a silenced cliff never pages; the Overview shows it dimmed with a "silenced by …" tag, never removed.

## B4.5 Interactions

| With | Behaviour |
|---|---|
| `monitoring.prometheusRule.enabled` | the `GroupSyncGroupCountCliff` rule renders only when BOTH it and `config.alerts.groupCountCliff.enabled` are true. With the module off the kind is never emitted, and a rule on an unemittable kind is the exact "can never fire" trap of `docs/DESIGN_metrics_refresh.md` §5.2 — so it is derived away, not shipped inert |
| Self tier | both cliff kinds name groups from the self-scoped Groups tab, so they are NOT in `gsd/api.py#SELF_ALERT_DETAILS` — withheld, like `empty_group`. A narrowed reader loses nothing they could act on |
| Degraded cluster | skipped with every other computed kind (existing behaviour) |
| `rbac.*` | none needed; Groups are already listed |
| Invalid values | `dropRatio` outside `(0, 1]`, `minMembers < 1`, `windowHours <= 0` refuse at `helm template` (helper `gsd.groupCountCliff`) and at startup (`ConfigError`) — a threshold that can never or always fire is a misconfiguration, not a preference |
| Group row on the wire | `/api/clusters/{id}/groups` rows gain `cliff_silence` (nullable) — additive; documented in `API.md` |

## B4.6 Files — complete code

### `local-development/gsd/kube.py`

Old:
```python
SYNC_TIME_ANNOTATION = "group-sync-operator.redhat-cop.io/sync-time"
LDAP_UID_ANNOTATION = "openshift.io/ldap.uid"
```
New:
```python
SYNC_TIME_ANNOTATION = "group-sync-operator.redhat-cop.io/sync-time"
LDAP_UID_ANNOTATION = "openshift.io/ldap.uid"
# READ, NEVER WRITTEN — the exception-annotation pattern above, applied to the group-count
# cliff alert (docs/DESIGN_grafana_dashboard_and_group_count_cliff.md). An administrator sets
# it on the Group with `oc annotate`; the value is "true" or "until=YYYY-MM-DD" (inclusive,
# UTC). The dashboard carries it to group_state.cliff_silence and decides in state.py. It is
# the ONE annotation carried beyond the two above: not "all annotations", because the store
# would then hold whatever anybody writes on a Group.
CLIFF_SILENCE_ANNOTATION = "groupsync-dashboard.io/silence-group-count-cliff"
```

Old (`GroupView`):
```python
    members: list[str]
    """The usernames themselves, not just the count.

    A count answers "is this group empty?"; only the names answer "why does this person have
    access?" — which is the question an operator actually arrives with."""
```
New:
```python
    members: list[str]
    """The usernames themselves, not just the count.

    A count answers "is this group empty?"; only the names answer "why does this person have
    access?" — which is the question an operator actually arrives with."""
    cliff_silence: str | None = None
    """CLIFF_SILENCE_ANNOTATION's raw value, or None. Last and defaulted so the positional
    constructors in tests keep working."""
```

Old (`_group_view` return):
```python
        group_synced_at=annotations.get(SYNC_TIME_ANNOTATION),
        ldap_uid=annotations.get(LDAP_UID_ANNOTATION),
        members=members,
    )
```
New:
```python
        group_synced_at=annotations.get(SYNC_TIME_ANNOTATION),
        ldap_uid=annotations.get(LDAP_UID_ANNOTATION),
        members=members,
        cliff_silence=annotations.get(CLIFF_SILENCE_ANNOTATION),
    )
```

### `local-development/gsd/poller.py`

Old:
```python
                    "group_synced_at": g.group_synced_at,
                    "ldap_uid": g.ldap_uid,
                }
                for g in groups
            ],
            observed_at,
        )
```
New:
```python
                    "group_synced_at": g.group_synced_at,
                    "ldap_uid": g.ldap_uid,
                    # The silence annotation, carried as observed. Read-only: see kube.py.
                    "cliff_silence": g.cliff_silence,
                }
                for g in groups
            ],
            observed_at,
        )
```

### `local-development/gsd/store.py`

Schema — old:
```sql
CREATE TABLE IF NOT EXISTS group_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    member_count        INTEGER NOT NULL,
    sync_provider       TEXT,
    group_synced_at     TEXT,           -- the group's OWN sync-time annotation
    ldap_uid            TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name)
);
```
New:
```sql
CREATE TABLE IF NOT EXISTS group_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    member_count        INTEGER NOT NULL,
    sync_provider       TEXT,
    group_synced_at     TEXT,           -- the group's OWN sync-time annotation
    ldap_uid            TEXT,
    observed_at         TEXT NOT NULL,
    cliff_silence       TEXT,           -- kube.CLIFF_SILENCE_ANNOTATION, raw; migration 8
    PRIMARY KEY(cluster_id, name)
);
```

Index on `membership_event` — old:
```sql
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);
```
New:
```sql
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);
-- The group-count cliff sums a cluster's events inside a time window (Store.group_count_changes);
-- without this the read scans every event the cluster has ever recorded, and the table has no
-- retention by design. Migration 8.
CREATE INDEX IF NOT EXISTS membership_event_by_time
    ON membership_event(cluster_id, observed_at);
```

Migration — old (end of `_MIGRATIONS`):
```python
            # On a FRESH database SCHEMA has already created both tables in this shape; the DROP then
            # removes an empty table and the CREATE puts it back, which is harmless and keeps the
            # replay idempotent (_migrate tolerates exactly one error, and this raises none).
        ],
    ),
]
```
New:
```python
            # On a FRESH database SCHEMA has already created both tables in this shape; the DROP then
            # removes an empty table and the CREATE puts it back, which is harmless and keeps the
            # replay idempotent (_migrate tolerates exactly one error, and this raises none).
        ],
    ),
    (
        8,
        "group_state carries the cliff-silence annotation; membership_event indexed by time",
        [
            # ADD COLUMN replays with "duplicate column name" on a fresh database, which _migrate
            # tolerates. Nullable: an upgraded cluster's rows are NULL (not silenced) until its
            # next poll rewrites group_state, which is one interval away.
            "ALTER TABLE group_state ADD COLUMN cliff_silence TEXT",
            "CREATE INDEX IF NOT EXISTS membership_event_by_time "
            "ON membership_event(cluster_id, observed_at)",
        ],
    ),
]
```

`replace_group_state` — old:
```python
            conn.executemany(
                """INSERT INTO group_state(cluster_id, name, member_count, sync_provider,
                       group_synced_at, ldap_uid, observed_at)
                   VALUES(:cluster_id,:name,:member_count,:sync_provider,
                          :group_synced_at,:ldap_uid,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )
```
New:
```python
            conn.executemany(
                """INSERT INTO group_state(cluster_id, name, member_count, sync_provider,
                       group_synced_at, ldap_uid, observed_at, cliff_silence)
                   VALUES(:cluster_id,:name,:member_count,:sync_provider,
                          :group_synced_at,:ldap_uid,:observed_at,:cliff_silence)""",
                # cliff_silence defaults to NULL so every existing caller (and every fixture) that
                # builds rows without it keeps working; the poller always supplies it.
                [{"cliff_silence": None, **r, "cluster_id": cluster_id, "observed_at": observed_at}
                 for r in rows],
            )
```

`groups()` — both SELECTs gain the column. Old:
```python
            sql = ("""SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at,
                            g.ldap_uid, g.observed_at
                       FROM group_state g
```
New:
```python
            sql = ("""SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at,
                            g.ldap_uid, g.observed_at, g.cliff_silence
                       FROM group_state g
```
Old:
```python
        sql = ("""SELECT name, member_count, sync_provider, group_synced_at, ldap_uid,
                        observed_at
                   FROM group_state WHERE cluster_id=?"""
```
New:
```python
        sql = ("""SELECT name, member_count, sync_provider, group_synced_at, ldap_uid,
                        observed_at, cliff_silence
                   FROM group_state WHERE cluster_id=?"""
```

New method — insert directly after `membership_events` (before `def user_groups`):

```python
    def group_count_changes(self, cluster_id: str, since: str) -> dict[str, dict]:
        """Per group, how many members were added and removed at or after ``since``.

        The group-count cliff's only store read (state.py#compute_alerts). ``since`` is a
        timeutil-format timestamp, compared lexicographically like every other timestamp
        here. The count at the window's start is exactly ``current + removed - added``
        because sync_members writes one event per member transition and nothing else — so
        this is the per-poll history the cliff needs without a second table holding a copy
        of it. Groups with no events in the window are absent from the result.
        """
        rows = self._rows(
            """SELECT group_name,
                      SUM(CASE WHEN change = 'added'   THEN 1 ELSE 0 END) AS added,
                      SUM(CASE WHEN change = 'removed' THEN 1 ELSE 0 END) AS removed
                 FROM membership_event
                WHERE cluster_id = ? AND observed_at >= ?
                GROUP BY group_name""",
            (cluster_id, since),
        )
        return {
            r["group_name"]: {"added": int(r["added"] or 0), "removed": int(r["removed"] or 0)}
            for r in rows
        }
```

### `local-development/gsd/storage.py`

Old:
```python
    def membership_events(
        self,
        cluster_id: str,
        group_name: str | None = None,
        user_name: str | None = None,
        limit: int = 200,
    ) -> list[dict]: ...
```
New:
```python
    def membership_events(
        self,
        cluster_id: str,
        group_name: str | None = None,
        user_name: str | None = None,
        limit: int = 200,
    ) -> list[dict]: ...
    def group_count_changes(self, cluster_id: str, since: str) -> dict[str, dict]: ...
```

### `local-development/gsd/state.py`

Imports — old:
```python
from datetime import UTC, datetime, timedelta
```
(verify the exact existing import line; add `date` and `fnmatch`):
```python
import fnmatch
from datetime import UTC, date, datetime, timedelta
```

`Alert` — old:
```python
    severity: str = "warning"

    def as_dict(self) -> dict:
        return {
            "cluster": self.cluster,
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "severity": self.severity,
        }
```
New:
```python
    severity: str = "warning"
    # A silenced alert is still an alert: reported with the reason, never dropped. Only the
    # group-count cliff sets these today; every other kind carries the defaults on the wire so
    # the shape is uniform.
    silenced: bool = False
    silenced_by: str | None = None

    def as_dict(self) -> dict:
        return {
            "cluster": self.cluster,
            "kind": self.kind,
            "subject": self.subject,
            "detail": self.detail,
            "severity": self.severity,
            "silenced": self.silenced,
            "silenced_by": self.silenced_by,
        }
```

Insert after `stale_group_threshold` (before `compute_alerts`):

```python
@dataclass(frozen=True)
class CliffPolicy:
    """config.alerts.groupCountCliff, as the pure layer sees it. None means the module is off."""

    min_members: int = 10
    drop_ratio: float = 0.5
    window_hours: float = 24.0
    silence: tuple[str, ...] = ()

    def since(self, now: datetime) -> str:
        """The window's start in timeutil's fixed-width UTC format — the store compares
        observed_at lexicographically, so the format must be the poller's exactly."""
        return (now - timedelta(hours=self.window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")


def cliff_policy(settings) -> CliffPolicy | None:
    """Settings -> CliffPolicy, or None when the module is off or no settings were given.

    Duck-typed on purpose: this module imports nothing from config.py (it is the pure
    layer), and the metrics collector is legitimately built without settings in tests.
    """
    if settings is None or not getattr(settings, "group_count_cliff_enabled", False):
        return None
    return CliffPolicy(
        min_members=int(settings.group_count_cliff_min_members),
        drop_ratio=float(settings.group_count_cliff_drop_ratio),
        window_hours=float(settings.group_count_cliff_window_hours),
        silence=tuple(settings.group_count_cliff_silence),
    )


def cliff_silence(
    annotation: str | None, silence: tuple[str, ...], group: str, now: datetime
) -> str | None:
    """Why a cliff on ``group`` is silenced: "annotation", "values", or None.

    The annotation (kube.CLIFF_SILENCE_ANNOTATION) is "true" or "until=YYYY-MM-DD"; the
    date is inclusive and read as a UTC calendar date, and an expired or unparseable value
    un-silences rather than silencing — the direction that reports rather than hides.
    Values patterns are fnmatch globs, case-sensitive like group names.
    """
    if annotation is not None:
        word = annotation.strip().lower()
        if word == "true":
            return "annotation"
        if word.startswith("until="):
            try:
                until = date.fromisoformat(word[len("until="):].strip())
            except ValueError:
                until = None
            if until is not None and now.date() <= until:
                return "annotation"
    for pattern in silence:
        if fnmatch.fnmatchcase(group, pattern):
            return "values"
    return None
```

`compute_alerts` signature and docstring — old:
```python
    user_bindings: list[dict] | None = None,
    groupsync_present: bool | None = None,
) -> list[Alert]:
    """Compute the PLAN §8 conditions the first slice has data for.

    Excluded: dangling bindings (needs RBAC outside the first slice, PLAN §14) and the group
    count cliff (needs a tuned floor as well as a ratio, PLAN §8).
    """
```
New:
```python
    user_bindings: list[dict] | None = None,
    groupsync_present: bool | None = None,
    count_changes: dict[str, dict] | None = None,
    cliff: CliffPolicy | None = None,
) -> list[Alert]:
    """Compute the PLAN §8 conditions the first slice has data for.

    Excluded: dangling bindings (needs RBAC outside the first slice, PLAN §14). The group
    count cliff, once excluded for want of a floor, is computed when ``cliff`` is given:
    ``count_changes`` is store.group_count_changes for the policy's window
    (docs/DESIGN_grafana_dashboard_and_group_count_cliff.md).
    """
```

Insert after the `for group in groups:` loop (i.e. directly before `    for cr in groupsyncs:`):

```python
    # THE GROUP-COUNT CLIFF. before = the count at the window's start, reconstructed exactly
    # from the membership events inside the window (state is replaced each poll; the events
    # are the history). Evaluated only for groups that still exist — a deleted group is the
    # dangling-binding finding's job — and only above the floor: below ten members, half is
    # one or two people, which is churn, not a cliff. Silenced cliffs are STILL reported,
    # under their own kind, so a reader sees "known" rather than "nothing".
    if cliff is not None and count_changes:
        for group in groups:
            change = count_changes.get(group["name"])
            if not change:
                continue
            after = int(group.get("member_count") or 0)
            before = after + int(change.get("removed") or 0) - int(change.get("added") or 0)
            if before < cliff.min_members:
                continue
            drop = before - after
            if drop <= 0 or drop < cliff.drop_ratio * before:
                continue
            by = cliff_silence(group.get("cliff_silence"), cliff.silence, group["name"], now)
            detail = (
                f"members {before} -> {after} within the last {cliff.window_hours:g}h "
                f"({drop / before:.0%} drop; floor {cliff.min_members}, ratio "
                f"{cliff.drop_ratio:g}) — a directory-side change, or a sync that resolved "
                f"fewer member DNs; compare the group's LDAP entry with its CR's last sync"
            )
            if by == "annotation":
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff_silenced",
                        subject=group["name"],
                        detail=detail + "; silenced by the Group's silence annotation",
                        silenced=True,
                        silenced_by="annotation",
                    )
                )
            elif by == "values":
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff_silenced",
                        subject=group["name"],
                        detail=detail + "; silenced by config.alerts.groupCountCliff.silence",
                        silenced=True,
                        silenced_by="values",
                    )
                )
            else:
                alerts.append(
                    Alert(
                        cluster=cluster,
                        kind="group_count_cliff",
                        subject=group["name"],
                        detail=detail,
                    )
                )
```

(Both `kind="..."` literals are written out in full so `tests/test_metrics.py`'s regex over `state.py` sees both.)

### `local-development/gsd/config.py`

`Settings` — insert after `unmanaged_audit_max_per_cycle: int = 20`:

```python
    # The group-count cliff alert (docs/DESIGN_grafana_dashboard_and_group_count_cliff.md).
    # ON by default: read-only, no RBAC beyond the Group list the poll already makes, one
    # indexed query per cluster per read. The floor is what keeps ON quiet — below ten
    # members, half is one or two people. Validated in load_settings: a ratio outside (0, 1],
    # a floor below 1 or a non-positive window refuses to start, because an alert that can
    # never or always fire is a misconfiguration rather than a preference.
    group_count_cliff_enabled: bool = True
    group_count_cliff_min_members: int = 10
    group_count_cliff_drop_ratio: float = 0.5
    group_count_cliff_window_hours: float = 24.0
    # Exact names or fnmatch globs. A match is reported as silenced, never dropped.
    group_count_cliff_silence: tuple[str, ...] = ()
```

New helper — insert before `def load_settings`:

```python
def _cliff_settings(raw: dict) -> dict:
    """config.alerts.groupCountCliff, validated. Refuses rather than clamps: unlike the
    SQLite knobs, a threshold that cannot fire (ratio > 1) or always fires (ratio <= 0) is
    not a degraded-but-running state, it is an alert lying in one direction."""
    enabled = _bool_setting(raw, "GSD_GROUP_COUNT_CLIFF_ENABLED", "groupCountCliffEnabled", True)
    min_members = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_MIN_MEMBERS", "groupCountCliffMinMembers", 10, int)
    ratio = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_DROP_RATIO", "groupCountCliffDropRatio", 0.5, float)
    window = _num_setting(
        raw, "GSD_GROUP_COUNT_CLIFF_WINDOW_HOURS", "groupCountCliffWindowHours", 24.0, float)
    if not 0 < ratio <= 1:
        raise ConfigError(f"groupCountCliffDropRatio must be in (0, 1]; got {ratio!r}")
    if min_members < 1:
        raise ConfigError(f"groupCountCliffMinMembers must be >= 1; got {min_members!r}")
    if window <= 0:
        raise ConfigError(f"groupCountCliffWindowHours must be > 0; got {window!r}")
    source = os.environ.get("GSD_GROUP_COUNT_CLIFF_SILENCE")
    if source is None:
        source = raw.get("groupCountCliffSilence", "")
    if isinstance(source, (list, tuple)):
        patterns = [str(p).strip() for p in source]
    else:
        patterns = str(source or "").split(",")
    return {
        "group_count_cliff_enabled": enabled,
        "group_count_cliff_min_members": min_members,
        "group_count_cliff_drop_ratio": ratio,
        "group_count_cliff_window_hours": window,
        "group_count_cliff_silence": tuple(p for p in patterns if p),
    }
```

`load_settings` — old:
```python
        unmanaged_audit_mode=_audit_mode_setting(raw),
        unmanaged_audit_max_per_cycle=_num_setting(
            raw, "GSD_UNMANAGED_AUDIT_MAX_PER_CYCLE", "unmanagedAuditMaxPerCycle", 20, int
        ),
```
New:
```python
        unmanaged_audit_mode=_audit_mode_setting(raw),
        unmanaged_audit_max_per_cycle=_num_setting(
            raw, "GSD_UNMANAGED_AUDIT_MAX_PER_CYCLE", "unmanagedAuditMaxPerCycle", 20, int
        ),
        **_cliff_settings(raw),
```

### `local-development/gsd/api.py`

`SELF_ALERT_DETAILS` comment — old:
```python
#   * `empty_group`, `unattributed`, `stale_group` name groups from the self-scoped Groups
#     tab (and an empty group can never contain the viewer);
```
New:
```python
#   * `empty_group`, `unattributed`, `stale_group`, `group_count_cliff` and
#     `group_count_cliff_silenced` name groups from the self-scoped Groups tab (and an empty
#     group can never contain the viewer);
```

`list_alerts` — old:
```python
        viewer, scope = viewer_scope(request)
        now = datetime.now(UTC)
        alerts: list[dict] = []
        for row in store.clusters():
            cluster_id = row["id"]
            if row["status"] and row["status"] != "ok":
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                    }
                )
```
New:
```python
        viewer, scope = viewer_scope(request)
        now = datetime.now(UTC)
        # The cliff policy, or None with the module off. Kept in step with the metrics
        # collector's call (gsd/metrics.py#DashboardCollector._gather) — the parity contract.
        policy = st.cliff_policy(settings)
        alerts: list[dict] = []
        for row in store.clusters():
            cluster_id = row["id"]
            if row["status"] and row["status"] != "ok":
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                        "silenced": False,
                        "silenced_by": None,
                    }
                )
```
Old:
```python
                groupsync_present=store.groupsync_present(cluster_id),
                now=now,
                grace=grace,
            )
            alerts.extend(a.as_dict() for a in computed)
```
New:
```python
                groupsync_present=store.groupsync_present(cluster_id),
                now=now,
                grace=grace,
                count_changes=(
                    store.group_count_changes(cluster_id, policy.since(now)) if policy else None
                ),
                cliff=policy,
            )
            alerts.extend(a.as_dict() for a in computed)
```
Old (dangling row):
```python
                        "severity": "critical",
                    }
                )
        if scope == "self":
```
New:
```python
                        "severity": "critical",
                        "silenced": False,
                        "silenced_by": None,
                    }
                )
        if scope == "self":
```

### `local-development/gsd/metrics.py`

Old:
```python
ALERT_KINDS = (
    "groupsync_crd_absent", "unattributed", "empty_group", "invalid_schedule",
    "sync_stopped", "overdue", "reconcile_error", "stale_group",
    "config_reconcile_error", "direct_user_binding",
    "dangling_binding",
    "auth_failed", "forbidden", "unreachable",
)
```
New:
```python
ALERT_KINDS = (
    "groupsync_crd_absent", "unattributed", "empty_group", "invalid_schedule",
    "sync_stopped", "overdue", "reconcile_error", "stale_group",
    "config_reconcile_error", "direct_user_binding",
    "dangling_binding",
    # The group-count cliff, and the same cliff an administrator silenced (annotation or
    # values). Two KIND values rather than a `silenced` label, so the label set of
    # gsd_alerts_total — and every rule written against it — is unchanged, and the shipped
    # rule matches the unsilenced kind alone. Kind only: the group's name never reaches
    # /metrics (module docstring).
    "group_count_cliff", "group_count_cliff_silenced",
    "auth_failed", "forbidden", "unreachable",
)
```

HELP — old:
```python
        alerts = GaugeMetricFamily(
            "gsd_alerts_total",
            "Alerts as /api/alerts serves them at the wide tier, by kind and severity. A "
            "failing cluster reports its poll outcome as one critical alert and none of "
            "the computed kinds (those would come from stale cache); dangling bindings "
            "count under kind=dangling_binding.",
            labels=["cluster", "kind", "severity"],
        )
```
New:
```python
        alerts = GaugeMetricFamily(
            "gsd_alerts_total",
            "Alerts as /api/alerts serves them at the wide tier, by kind and severity. A "
            "failing cluster reports its poll outcome as one critical alert and none of "
            "the computed kinds (those would come from stale cache); dangling bindings "
            "count under kind=dangling_binding; a group-count cliff an administrator "
            "silenced counts under kind=group_count_cliff_silenced, never under "
            "group_count_cliff.",
            labels=["cluster", "kind", "severity"],
        )
```

Collector call — old:
```python
                else:
                    for alert in st.compute_alerts(
                        cluster=cluster,
                        groupsyncs=cluster_groupsyncs,
                        operator_configs=self.store.operator_configs(cluster)["configs"],
                        user_bindings=self.store.direct_user_bindings(cluster),
                        groups=self.store.groups(cluster, "all"),
                        groupsync_present=self.store.groupsync_present(cluster),
                        now=now,
                        grace=self.grace,
                    ):
```
New:
```python
                else:
                    # Same policy the API derives (gsd/api.py#list_alerts): None when the
                    # module is off OR when this collector was built without settings.
                    policy = st.cliff_policy(self.settings)
                    for alert in st.compute_alerts(
                        cluster=cluster,
                        groupsyncs=cluster_groupsyncs,
                        operator_configs=self.store.operator_configs(cluster)["configs"],
                        user_bindings=self.store.direct_user_bindings(cluster),
                        groups=self.store.groups(cluster, "all"),
                        groupsync_present=self.store.groupsync_present(cluster),
                        now=now,
                        grace=self.grace,
                        count_changes=(
                            self.store.group_count_changes(cluster, policy.since(now))
                            if policy else None
                        ),
                        cliff=policy,
                    ):
```

### `local-development/gsd/static/index.html`

Old (`function alertsCard`, whole function):
```javascript
function alertsCard() {
  const a = data.alerts;
  const body = a.length === 0
    ? `<div class="empty-note">No alerts. Nothing overdue, empty, unattributed, stale, or failing.</div>`
    : a.map((x) => `<div class="alert-row sev-${x.severity === "critical" ? "critical" : "warning"}">
        ${sevBadge(x.severity)}
        <div class="who">${esc(x.subject)}<div class="muted" style="font-weight:400;font-size:11px">${esc(x.cluster)} · ${esc(x.kind)}</div></div>
        <div class="what">${esc(x.detail)}</div>
      </div>`).join("");
  return `<section class="card">
    <div class="hero">
      <div class="value">${a.length}</div>
      <div class="label">${a.length === 1 ? "alert" : "alerts"} across ${data.clusters.length} cluster${data.clusters.length === 1 ? "" : "s"}</div>
    </div>
    ${body}
  </section>`;
}
```
New:
```javascript
/* A silenced alert is shown, not hidden: the row stays, dimmed, with a tag naming what
   silenced it (the Group's annotation or the chart's values), and the hero counts only the
   active ones. Hiding it would train readers that "0 alerts" means healthy when it means
   "somebody chose not to look". The severity badge stays a severity word — the UI test
   holds badge labels to critical|warning — so "silenced" is a separate tag, not a badge. */
function alertsCard() {
  const a = data.alerts;
  const active = a.filter((x) => !x.silenced);
  const quiet = a.length - active.length;
  const body = a.length === 0
    ? `<div class="empty-note">No alerts. Nothing overdue, empty, unattributed, stale, collapsed, or failing.</div>`
    : a.map((x) => `<div class="alert-row sev-${x.severity === "critical" ? "critical" : "warning"}${x.silenced ? " silenced" : ""}">
        ${sevBadge(x.severity)}
        <div class="who">${esc(x.subject)}<div class="muted" style="font-weight:400;font-size:11px">${esc(x.cluster)} · ${esc(x.kind)}</div></div>
        <div class="what">${x.silenced ? `<span class="silence-tag">silenced by ${esc(x.silenced_by)}</span> ` : ""}${esc(x.detail)}</div>
      </div>`).join("");
  return `<section class="card">
    <div class="hero">
      <div class="value">${active.length}</div>
      <div class="label">${active.length === 1 ? "alert" : "alerts"} across ${data.clusters.length} cluster${data.clusters.length === 1 ? "" : "s"}${quiet ? ` · ${quiet} silenced` : ""}</div>
    </div>
    ${body}
  </section>`;
}
```

### `local-development/gsd/static/app.css`

Old:
```css
.alert-row .who { min-width: 190px; font-weight: 500; word-break: break-all; }
.alert-row .what { color: var(--text-secondary); }
```
New:
```css
.alert-row .who { min-width: 190px; font-weight: 500; word-break: break-all; }
.alert-row .what { color: var(--text-secondary); }
/* Silenced: present and legible, visibly de-emphasised, never removed. The dashed edge is the
   second channel beside opacity, for the same colour-independence reason .badge has a glyph. */
.alert-row.silenced { opacity: 0.65; border-left-style: dashed; }
.silence-tag {
  display: inline-block; font-size: 11px; line-height: 1.4; padding: 0 6px; margin-right: 6px;
  border: 1px solid var(--status-unknown); border-radius: 3px; color: var(--text-muted);
  white-space: nowrap;
}
```

### `charts/group-sync-dashboard/values.yaml` — new `config.alerts` block

Old (end of the `config.userActivity` block, immediately before the `# DEBUG | INFO | WARNING` comment):
```yaml
    # Aggregation already bounds the table, so this is a backstop for a long-lived
    # deployment rather than the growth control a request log would need. 0 disables it.
    retentionDays: 400

# DEBUG | INFO | WARNING | ERROR | CRITICAL. Case does not matter; anything else refuses to render.
```
New:
```yaml
    # Aggregation already bounds the table, so this is a backstop for a long-lived
    # deployment rather than the growth control a request log would need. 0 disables it.
    retentionDays: 400

  # Computed alerts with a tunable threshold. Every kind /api/alerts serves is derived at
  # read time from what the poll stored (docs/reference-architecture.md, "Derived, never
  # stored"); this block holds the ones that carry a number.
  alerts:
    # THE GROUP-COUNT CLIFF: a group whose membership fell by dropRatio or more, from a
    # count of at least minMembers, within windowHours — reconstructed exactly from the
    # membership events the poll records, so no extra table and no extra RBAC. Kind
    # `group_count_cliff`, severity warning; gsd_alerts_total{kind="group_count_cliff"};
    # PrometheusRule GroupSyncGroupCountCliff (rendered only while this is enabled, because a
    # rule on a kind that is never emitted can never fire).
    #
    # DEFAULT ON. Read-only, one indexed query per cluster per read, no side effect. What
    # keeps ON quiet is the floor: below ten members, half is one or two people — churn,
    # not a cliff. Raise minMembers or lower dropRatio for a large directory; the values
    # are refused at render if the ratio leaves (0, 1], the floor drops below 1 or the
    # window is not positive.
    #
    # SILENCING IS READ-ONLY, from two places an administrator controls, and a silenced
    # cliff is still REPORTED (kind `group_count_cliff_silenced`, `silenced: true`, dimmed on
    # the Overview) — never hidden:
    #   1. the Group annotation groupsync-dashboard.io/silence-group-count-cliff, value
    #      "true" or "until=YYYY-MM-DD" (inclusive, UTC; expired un-silences), e.g.
    #        oc annotate group app-ocp-rbac-contractors-ns-view \
    #          groupsync-dashboard.io/silence-group-count-cliff=until=2026-10-31
    #      The dashboard READS it on every poll and writes nothing back.
    #   2. `silence` below: exact names or fnmatch globs.
    groupCountCliff:
      enabled: true
      minMembers: 10
      dropRatio: 0.5
      windowHours: 24
      silence: []
      # e.g.
      # silence:
      #   - app-ocp-rbac-contractors-*
      #   - app-ocp-rbac-seasonal-ns-view

# DEBUG | INFO | WARNING | ERROR | CRITICAL. Case does not matter; anything else refuses to render.
```

### `charts/group-sync-dashboard/templates/_helpers.tpl` — validation helper (append)

```
{{/*
config.alerts.groupCountCliff, validated at render so a threshold that can never or always
fire is refused here rather than discovered as silence. Emits nothing; include it for effect.
*/}}
{{- define "gsd.groupCountCliff" -}}
{{- $c := ((.Values.config | default dict).alerts | default dict).groupCountCliff | default dict -}}
{{- $ratio := $c.dropRatio | float64 -}}
{{- if or (le $ratio 0.0) (gt $ratio 1.0) -}}
{{- fail (printf "config.alerts.groupCountCliff.dropRatio must be in (0, 1]; got %v" $c.dropRatio) -}}
{{- end -}}
{{- if lt ($c.minMembers | int) 1 -}}
{{- fail (printf "config.alerts.groupCountCliff.minMembers must be >= 1; got %v" $c.minMembers) -}}
{{- end -}}
{{- if le ($c.windowHours | float64) 0.0 -}}
{{- fail (printf "config.alerts.groupCountCliff.windowHours must be > 0; got %v" $c.windowHours) -}}
{{- end -}}
{{- end -}}
```

### `charts/group-sync-dashboard/templates/configmap.yaml`

Old:
```yaml
    unmanagedAuditMode: {{ .Values.config.unmanagedAudit.mode | quote }}
    unmanagedAuditMaxPerCycle: {{ .Values.config.unmanagedAudit.maxPerCycle }}
```
New:
```yaml
    unmanagedAuditMode: {{ .Values.config.unmanagedAudit.mode | quote }}
    unmanagedAuditMaxPerCycle: {{ .Values.config.unmanagedAudit.maxPerCycle }}
    {{- include "gsd.groupCountCliff" . }}
    # The group-count cliff alert (values.yaml config.alerts.groupCountCliff). The silence
    # list is joined like loginCaptureHtpasswdProviders: the app splits on commas.
    groupCountCliffEnabled: {{ .Values.config.alerts.groupCountCliff.enabled }}
    groupCountCliffMinMembers: {{ .Values.config.alerts.groupCountCliff.minMembers }}
    groupCountCliffDropRatio: {{ .Values.config.alerts.groupCountCliff.dropRatio }}
    groupCountCliffWindowHours: {{ .Values.config.alerts.groupCountCliff.windowHours }}
    groupCountCliffSilence: {{ .Values.config.alerts.groupCountCliff.silence | join "," | quote }}
```

### `charts/group-sync-dashboard/templates/monitoring.yaml` — new rule

Insert after the `GroupSyncDashboardConfigReconcileError` rule (before the `# Both of the following are SILENT failures` comment):

```yaml
        {{- if .Values.config.alerts.groupCountCliff.enabled }}
        # A group lost config.alerts.groupCountCliff.dropRatio of at least minMembers members
        # within windowHours. The unsilenced kind ONLY: a cliff an administrator silenced (the
        # Group annotation or the values list) is exported as kind=group_count_cliff_silenced
        # and must not page. Rendered only while the module is on — a rule on a kind the
        # collector never emits can never fire (docs/DESIGN_metrics_refresh.md §5.2).
        - alert: GroupSyncGroupCountCliff
          expr: gsd_alerts_total{kind="group_count_cliff"} > 0
          for: {{ .Values.monitoring.prometheusRule.for.groupCountCliff }}
          labels: {severity: warning}
          annotations:
            summary: "{{ `{{ $value }}` }} group(s) on {{ `{{ $labels.cluster }}` }} lost at least half their members"
            description: >-
              A synced group's membership fell by the configured ratio within the window.
              The dashboard's Overview names the group and the before/after counts; compare
              the group's LDAP entry with its GroupSync CR's last sync. If the drop is
              expected, annotate the Group with
              groupsync-dashboard.io/silence-group-count-cliff=until=YYYY-MM-DD — the
              alert then reports as silenced instead of firing.
        {{- end }}
```

## B4.7 Tests

### `local-development/tests/test_state.py` — new class (append)

```python
class TestGroupCountCliff:
    """docs/DESIGN_grafana_dashboard_and_group_count_cliff.md B4: before = after + removed - added."""

    NOW = t("2026-09-04T12:00:00")
    POLICY = st.CliffPolicy(min_members=10, drop_ratio=0.5, window_hours=24.0)

    def _group(self, name="app-ocp-rbac-team-ns-view", member_count=5, **kw):
        return {"name": name, "member_count": member_count, "sync_provider": "ldap-groupsync_ldap",
                "group_synced_at": "2026-09-04T11:00:00Z", **kw}

    def _alerts(self, groups, changes, policy=POLICY):
        return [a for a in st.compute_alerts("crc", [], groups, self.NOW, GRACE,
                                             count_changes=changes, cliff=policy)
                if a.kind.startswith("group_count_cliff")]

    def test_fires_exactly_at_the_floor_and_the_ratio(self):
        # before = 5 + 5 - 0 = 10 (the floor), drop 5/10 = 0.5 (the ratio): both boundaries inclusive.
        got = self._alerts([self._group(member_count=5)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
        assert [a.kind for a in got] == ["group_count_cliff"]
        assert got[0].severity == "warning" and not got[0].silenced and got[0].silenced_by is None
        assert "members 10 -> 5" in got[0].detail and "24h" in got[0].detail

    def test_one_below_the_floor_is_silent(self):
        # before = 4 + 5 = 9 < 10, even though the ratio (5/9) clears 0.5.
        assert self._alerts([self._group(member_count=4)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}) == []

    def test_just_under_the_ratio_is_silent(self):
        # before = 11 + 9 = 20, drop 9/20 = 0.45 < 0.5.
        assert self._alerts([self._group(member_count=11)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 9}}) == []

    def test_a_recovered_group_nets_out(self):
        # 20 -> 5 -> 18 inside the window: before = 18 + 15 - 13 = 20, drop 2/20.
        assert self._alerts([self._group(member_count=18)], {"app-ocp-rbac-team-ns-view": {"added": 13, "removed": 15}}) == []

    def test_a_brand_new_group_has_no_before(self):
        # Every member was `added` inside the window: before = 50 - 50 = 0.
        assert self._alerts([self._group(member_count=50)], {"app-ocp-rbac-team-ns-view": {"added": 50, "removed": 0}}) == []

    def test_a_group_with_no_events_or_no_state_is_not_evaluated(self):
        assert self._alerts([self._group(member_count=5)], {}) == []
        # events for a deleted group (absent from group_state) are the dangling finding's job
        assert self._alerts([], {"gone": {"added": 0, "removed": 40}}) == []

    def test_module_off_computes_nothing(self):
        assert self._alerts([self._group(member_count=0)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 40}}, policy=None) == []

    def test_silenced_by_annotation_true_is_reported_not_dropped(self):
        got = self._alerts([self._group(member_count=5, cliff_silence="true")], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
        assert [(a.kind, a.silenced, a.silenced_by) for a in got] == [("group_count_cliff_silenced", True, "annotation")]
        assert "members 10 -> 5" in got[0].detail, "the numbers stay; only the kind changes"

    def test_silenced_until_a_future_or_todays_date(self):
        for value in ("until=2026-09-04", "until=2026-12-31", " UNTIL=2026-09-05 "):
            got = self._alerts([self._group(member_count=5, cliff_silence=value)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
            assert got[0].kind == "group_count_cliff_silenced", value

    def test_an_expired_or_malformed_until_unsilences(self):
        for value in ("until=2026-09-03", "until=yesterday", "maybe", ""):
            got = self._alerts([self._group(member_count=5, cliff_silence=value)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
            assert got[0].kind == "group_count_cliff", value

    def test_silenced_by_values_glob(self):
        policy = st.CliffPolicy(min_members=10, drop_ratio=0.5, window_hours=24.0,
                                silence=("app-ocp-rbac-team-*",))
        got = self._alerts([self._group(member_count=5)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert (got[0].kind, got[0].silenced_by) == ("group_count_cliff_silenced", "values")
        other = self._alerts([self._group(name="app-ocp-rbac-ops-ns-view", member_count=5)], {"app-ocp-rbac-ops-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert other[0].kind == "group_count_cliff", "globs are exact and case-sensitive"

    def test_annotation_wins_over_values_in_the_reason(self):
        policy = st.CliffPolicy(silence=("*",))
        got = self._alerts([self._group(member_count=5, cliff_silence="true")], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert got[0].silenced_by == "annotation"

    def test_since_is_in_the_pollers_timestamp_format(self):
        assert self.POLICY.since(self.NOW) == "2026-09-03T12:00:00Z"

    def test_as_dict_carries_the_silence_fields_for_every_kind(self):
        plain = st.Alert("crc", "overdue", "x", "y", "critical").as_dict()
        assert plain["silenced"] is False and plain["silenced_by"] is None
```

### `local-development/tests/test_store_poller.py` — append

```python
class TestGroupCountChanges:
    def _store(self):
        s = Store(":memory:")
        s.upsert_cluster("crc", "https://x", True)
        return s

    def test_sums_added_and_removed_inside_the_window_only(self):
        s = self._store()
        try:
            s.sync_members("crc", {"g": [f"u{i}" for i in range(12)]}, {}, "2026-09-01T00:00:00Z")
            s.sync_members("crc", {"g": [f"u{i}" for i in range(12, 15)]}, {}, "2026-09-04T00:00:00Z")
            inside = s.group_count_changes("crc", "2026-09-03T00:00:00Z")
            assert inside == {"g": {"added": 3, "removed": 12}}
            everything = s.group_count_changes("crc", "2026-08-01T00:00:00Z")
            assert everything == {"g": {"added": 15, "removed": 12}}
            assert s.group_count_changes("crc", "2026-09-05T00:00:00Z") == {}
        finally:
            s.close()

    def test_a_deleted_group_records_its_departures(self):
        s = self._store()
        try:
            s.sync_members("crc", {"g": ["a", "b"]}, {}, "2026-09-04T00:00:00Z")
            s.sync_members("crc", {}, {}, "2026-09-04T00:01:00Z")
            assert s.group_count_changes("crc", "2026-09-04T00:00:00Z") == {"g": {"added": 2, "removed": 2}}
        finally:
            s.close()

    def test_cliff_silence_is_stored_and_served_and_defaults_to_null(self):
        s = self._store()
        try:
            s.replace_group_state("crc", [
                {"name": "a", "member_count": 1, "sync_provider": None, "group_synced_at": None,
                 "ldap_uid": None, "cliff_silence": "until=2026-12-31"},
                {"name": "b", "member_count": 1, "sync_provider": None, "group_synced_at": None,
                 "ldap_uid": None},
            ], "2026-09-04T00:00:00Z")
            by_name = {g["name"]: g["cliff_silence"] for g in s.groups("crc", "all")}
            assert by_name == {"a": "until=2026-12-31", "b": None}
        finally:
            s.close()


class TestPollCarriesTheSilenceAnnotation:
    def test_poll_once_writes_the_annotation_it_read(self, tmp_path, monkeypatch):
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import GroupView

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch(self):
                return [], [GroupView("app-ocp-rbac-a-ns-view", 1, "gs_ldap", None, None, ["alice"],
                                      cliff_silence="true"),
                            GroupView("app-ocp-rbac-b-ns-view", 1, "gs_ldap", None, None, ["bob"])]
            def fetch_access_group_dn(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        store = Store(str(tmp_path / "t.db"))
        try:
            store.upsert_cluster("c1", "https://x", True)
            assert poller.poll_once(store, ClusterConfig("c1", "https://x", token_env="T"), timeout=5) == "ok"
            rows = {g["name"]: g["cliff_silence"] for g in store.groups("c1", "all")}
            assert rows == {"app-ocp-rbac-a-ns-view": "true", "app-ocp-rbac-b-ns-view": None}
        finally:
            store.close()
```

### `local-development/tests/test_kube_reader.py` — append

```python
def test_group_view_reads_exactly_the_silence_annotation():
    from gsd.kube import CLIFF_SILENCE_ANNOTATION, _group_view
    obj = {"metadata": {"name": "g", "annotations": {
        CLIFF_SILENCE_ANNOTATION: "until=2026-10-01", "somebody.else/note": "ignored"}},
        "users": ["a"]}
    view = _group_view(obj)
    assert view.cliff_silence == "until=2026-10-01"
    assert _group_view({"metadata": {"name": "g"}, "users": None}).cliff_silence is None
    assert CLIFF_SILENCE_ANNOTATION == "groupsync-dashboard.io/silence-group-count-cliff"
```

### `local-development/tests/test_migrations.py` — append

```python
def test_migration_8_adds_cliff_silence_and_the_time_index_to_an_older_database(tmp_path):
    """A pre-0.12 group_state has no cliff_silence; opening it must add the column (NULL for
    every existing row) and the membership_event time index, and land on the latest version."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE group_state (
            cluster_id TEXT NOT NULL, name TEXT NOT NULL, member_count INTEGER NOT NULL,
            sync_provider TEXT, group_synced_at TEXT, ldap_uid TEXT, observed_at TEXT NOT NULL,
            PRIMARY KEY(cluster_id, name));
        INSERT INTO group_state VALUES ('crc','g',3,NULL,NULL,NULL,'2026-09-01T00:00:00Z');
        PRAGMA user_version = 7;
    """)
    conn.commit()
    conn.close()

    from gsd.store import _MIGRATIONS
    with Store(path) as store:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(group_state)")}
        assert "cliff_silence" in cols
        assert store._conn.execute("SELECT cliff_silence FROM group_state").fetchone()[0] is None
        indexes = {r[1] for r in store._conn.execute("PRAGMA index_list(membership_event)")}
        assert "membership_event_by_time" in indexes
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 8
```

(If `Store` is not a context manager in this codebase — `test_migrations.py` uses `with Store(...) as store` at its existing tests, which the implementer should confirm and mirror; otherwise use try/finally with `store.close()`.)

### `local-development/tests/test_config.py` — append

```python
class TestGroupCountCliff:
    def test_defaults_are_on_with_the_documented_floor(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert s.group_count_cliff_enabled is True
        assert (s.group_count_cliff_min_members, s.group_count_cliff_drop_ratio,
                s.group_count_cliff_window_hours, s.group_count_cliff_silence) == (10, 0.5, 24.0, ())

    def test_configmap_keys_load_and_the_silence_list_splits_on_commas(self, tmp_path):
        cfg = BASE + ("groupCountCliffEnabled: false\ngroupCountCliffMinMembers: 25\n"
                      "groupCountCliffDropRatio: 0.3\ngroupCountCliffWindowHours: 6\n"
                      "groupCountCliffSilence: \"app-ocp-rbac-contractors-*, app-ocp-rbac-x-ns-view\"\n")
        s = load_settings(write(tmp_path, cfg))
        assert s.group_count_cliff_enabled is False
        assert (s.group_count_cliff_min_members, s.group_count_cliff_drop_ratio, s.group_count_cliff_window_hours) == (25, 0.3, 6.0)
        assert s.group_count_cliff_silence == ("app-ocp-rbac-contractors-*", "app-ocp-rbac-x-ns-view")

    @pytest.mark.parametrize("line", [
        "groupCountCliffDropRatio: 0\n", "groupCountCliffDropRatio: 1.5\n",
        "groupCountCliffMinMembers: 0\n", "groupCountCliffWindowHours: 0\n",
    ])
    def test_a_threshold_that_cannot_or_always_fires_is_refused(self, tmp_path, line):
        with pytest.raises(ConfigError):
            load_settings(write(tmp_path, BASE + line))

    def test_env_overrides_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_GROUP_COUNT_CLIFF_ENABLED", "false")
        monkeypatch.setenv("GSD_GROUP_COUNT_CLIFF_SILENCE", "a-*,b")
        try:
            s = load_settings(write(tmp_path, BASE + "groupCountCliffEnabled: true\n"))
        finally:
            monkeypatch.delenv("GSD_GROUP_COUNT_CLIFF_ENABLED", raising=False)
            monkeypatch.delenv("GSD_GROUP_COUNT_CLIFF_SILENCE", raising=False)
        assert s.group_count_cliff_enabled is False
        assert s.group_count_cliff_silence == ("a-*", "b")
```

### `local-development/tests/test_view_scoping.py` — append

Uses the file's existing `_client`, `_admin`, `AS_VIEWER` and `Store` imports. The `_seed` helper writes `c1`; this test adds a cliff on top with `now_iso()`-relative timestamps (the file already imports `now_iso`, per its `replace_operator_configs` test).

```python
def test_a_group_count_cliff_is_withheld_at_self_and_full_at_wide(tmp_path):
    """Both cliff kinds name a group from the self-scoped Groups tab, so they follow
    empty_group/unattributed: absent at self (gsd/api.py#SELF_ALERT_DETAILS), full at wide —
    including the silenced one, which is reported rather than hidden."""
    c = _client(tmp_path)
    store = Store(str(tmp_path / "t.db"))
    old = "2026-01-01T00:00:00Z"
    store.sync_members("c1", {"big-a": [f"u{i}" for i in range(20)],
                              "big-b": [f"v{i}" for i in range(20)]}, {}, old)
    store.sync_members("c1", {"big-a": ["u0"], "big-b": ["v0"]}, {}, now_iso())
    store.replace_group_state("c1", [
        {"name": "big-a", "member_count": 1, "sync_provider": "gs_ldap", "group_synced_at": None, "ldap_uid": None},
        {"name": "big-b", "member_count": 1, "sync_provider": "gs_ldap", "group_synced_at": None,
         "ldap_uid": None, "cliff_silence": "true"},
    ], now_iso())
    store.close()

    wide = _client(tmp_path, tier_resolver=_admin).get("/api/alerts", headers=AS_VIEWER).json()
    by_subject = {a["subject"]: a for a in wide["alerts"] if a["kind"].startswith("group_count_cliff")}
    assert by_subject["big-a"]["kind"] == "group_count_cliff" and by_subject["big-a"]["silenced"] is False
    assert by_subject["big-b"]["kind"] == "group_count_cliff_silenced"
    assert by_subject["big-b"]["silenced"] is True and by_subject["big-b"]["silenced_by"] == "annotation"

    body = c.get("/api/alerts", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert not [a for a in body["alerts"] if a["kind"].startswith("group_count_cliff")]
    assert "big-a" not in repr(body) and "big-b" not in repr(body)
```

Note: `replace_group_state` after `sync_members` is deliberate — the seed's group rows are replaced wholesale, so this test rewrites `c1`'s group state to exactly the two cliff groups; the assertions do not depend on the seed's original groups.

### `local-development/tests/test_metrics.py` — append

```python
class TestGroupCountCliffMetric:
    def _store(self, silence=None):
        now = datetime.now(UTC)
        store = Store(":memory:")
        store.upsert_cluster("crc", "https://x", True)
        store.record_poll("crc", "ok", None)
        store.sync_members("crc", {"big": [f"u{i}" for i in range(20)]}, {}, "2026-01-01T00:00:00Z")
        store.sync_members("crc", {"big": ["u0"]}, {}, _iso(now))
        store.replace_group_state("crc", [{"name": "big", "member_count": 1, "sync_provider": "gs",
                                           "group_synced_at": None, "ldap_uid": None,
                                           "cliff_silence": silence}], _iso(now))
        return store

    def test_kind_only_never_the_group_name(self):
        from gsd.config import Settings
        store = self._store()
        try:
            text = generate_latest(build_registry(store, GRACE, settings=Settings())).decode()
        finally:
            store.close()
        assert series(text, "gsd_alerts_total")[
            'gsd_alerts_total{cluster="crc",kind="group_count_cliff",severity="warning"}'] == 1
        assert "big" not in text.replace("gsd_build_info", ""), "a group name reached /metrics"

    def test_silenced_counts_under_its_own_kind(self):
        from gsd.config import Settings
        store = self._store(silence="true")
        try:
            text = generate_latest(build_registry(store, GRACE, settings=Settings())).decode()
        finally:
            store.close()
        got = series(text, "gsd_alerts_total")
        assert got['gsd_alerts_total{cluster="crc",kind="group_count_cliff_silenced",severity="warning"}'] == 1
        assert 'kind="group_count_cliff",' not in text

    def test_no_settings_means_module_off_on_the_collector(self):
        """A bare DashboardCollector(store, grace) claims no cliff: the policy derives from
        settings, and None is the off state — the same rule as the event families."""
        store = self._store()
        try:
            text = generate_latest(build_registry(store, GRACE)).decode()
        finally:
            store.close()
        assert "group_count_cliff" not in text

    def test_the_rule_renders_with_defaults_and_is_derived_away_when_the_module_is_off(self):
        import subprocess
        from pathlib import Path
        chart = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

        def rules(*sets):
            args = ["helm", "template", "t", str(chart), "-n", "x", "--set", "ingress.host=h",
                    "--set", "monitoring.prometheusRule.enabled=true", *sum((["--set", s] for s in sets), [])]
            try:
                done = subprocess.run(args, capture_output=True, text=True, timeout=120)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pytest.skip("helm not available")
            assert done.returncode == 0, done.stderr
            return done.stdout

        on = rules()
        assert "alert: GroupSyncGroupCountCliff" in on
        assert 'gsd_alerts_total{kind="group_count_cliff"} > 0' in on
        assert 'kind="group_count_cliff_silenced"' not in on, "a silenced cliff must never page"
        off = rules("config.alerts.groupCountCliff.enabled=false")
        assert "GroupSyncGroupCountCliff" not in off
```

`series()` is the file's existing helper. `Settings()` with no clusters is valid (the dataclass defaults everything) and carries the cliff defaults.

### `local-development/tests/test_chart_strategy.py` — append

```python
class TestGroupCountCliffValues:
    def test_configmap_carries_the_keys_and_joins_the_silence_list(self):
        ok, out = render(**{
            "config__alerts__groupCountCliff__minMembers": 25,
            "config__alerts__groupCountCliff__silence[0]": "app-ocp-rbac-a-*",
            "config__alerts__groupCountCliff__silence[1]": "app-ocp-rbac-b-ns-view",
        })
        assert ok, out
        cfg = _config_data(out)
        assert cfg["groupCountCliffEnabled"] is True
        assert (cfg["groupCountCliffMinMembers"], cfg["groupCountCliffDropRatio"],
                cfg["groupCountCliffWindowHours"]) == (25, 0.5, 24)
        assert cfg["groupCountCliffSilence"] == "app-ocp-rbac-a-*,app-ocp-rbac-b-ns-view"

    @pytest.mark.parametrize("key,value", [
        ("config__alerts__groupCountCliff__dropRatio", "0"),
        ("config__alerts__groupCountCliff__dropRatio", "1.5"),
        ("config__alerts__groupCountCliff__minMembers", "0"),
        ("config__alerts__groupCountCliff__windowHours", "0"),
    ])
    def test_a_threshold_that_cannot_or_always_fires_refuses_the_render(self, key, value):
        ok, out = render(**{key: value})
        assert not ok
        assert "config.alerts.groupCountCliff" in out
```

(`render` builds `--set key=value`; `[0]`-style keys are Helm's list syntax and pass through `key.replace('__', '.')` unchanged.)

### `local-development/tests/test_ui.py` — append

Reuses the file's `_free_port`, `build_app`, `Settings`, `ClusterConfig`, `Store`, `uvicorn`, `httpx`, `threading`, `time` imports.

```python
@pytest.fixture(scope="module")
def cliff_server(tmp_path_factory):
    """Its own store: one active cliff and one silenced, so the Overview's two renderings can
    be asserted without changing the shared seed's alert list."""
    db = str(tmp_path_factory.mktemp("gsd") / "cliff.db")
    now = datetime.now(UTC)
    store = Store(db)
    store.upsert_cluster("crc-local", "https://api.crc.testing:6443", True)
    store.record_poll("crc-local", "ok", None)
    store.sync_members("crc-local", {"app-ocp-rbac-loud-ns-view": [f"u{i}" for i in range(20)],
                                     "app-ocp-rbac-quiet-ns-view": [f"v{i}" for i in range(20)]},
                       {}, "2026-01-01T00:00:00Z")
    store.sync_members("crc-local", {"app-ocp-rbac-loud-ns-view": ["u0"],
                                     "app-ocp-rbac-quiet-ns-view": ["v0"]}, {}, _iso(now))
    store.replace_group_state("crc-local", [
        {"name": "app-ocp-rbac-loud-ns-view", "member_count": 1, "sync_provider": "gs_ldap",
         "group_synced_at": None, "ldap_uid": None},
        {"name": "app-ocp-rbac-quiet-ns-view", "member_count": 1, "sync_provider": "gs_ldap",
         "group_synced_at": None, "ldap_uid": None, "cliff_silence": "until=2099-01-01"},
    ], _iso(now))
    store.close()
    settings = Settings(clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
                        db_path=db, view_restrictions_enabled=False)
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(build_app(settings, run_poller=False), host="127.0.0.1",
                                        port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestGroupCountCliffOnTheOverview:
    def test_silenced_is_shown_dimmed_and_counted_apart(self, page, cliff_server):
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(cliff_server)
        page.wait_for_selector(".alert-row", timeout=10_000)
        assert not errors, errors
        rows = page.locator(".alert-row")
        silenced = page.locator(".alert-row.silenced")
        assert silenced.count() == 1
        assert "app-ocp-rbac-quiet-ns-view" in silenced.first.inner_text()
        assert "silenced by annotation" in silenced.first.locator(".silence-tag").inner_text()
        # The active cliff has no tag and the hero counts it alone (2 empty_group rows are
        # also active: both groups now have one member, not zero — so exactly 1 active row).
        active_rows = [rows.nth(i).inner_text() for i in range(rows.count())
                       if "silenced by" not in rows.nth(i).inner_text()]
        assert any("app-ocp-rbac-loud-ns-view" in t for t in active_rows)
        assert page.locator(".hero .value").first.inner_text().strip() == str(len(active_rows))
        assert "1 silenced" in page.locator(".hero .label").first.inner_text()
        labels = {page.locator(".alert-row .badge").nth(i).inner_text().strip()
                  for i in range(page.locator(".alert-row .badge").count())}
        assert labels <= {"critical", "warning"}, "silenced is a tag, not a severity"
```

(`_iso` exists in `test_ui.py`'s seed helper per its `group_synced_at: _iso(now - ...)` usage; if it is named differently there, use that name.)

## B4.8 Docs, CHANGELOG, chart README, Chart.yaml, version bumps

**`local-development/API.md`** — `GET /api/alerts`, old:
```
Kinds: `overdue`, `invalid_schedule`, `sync_stopped`, `empty_group`, `unattributed`,
`stale_group`, `reconcile_error`, `dangling_binding`, `groupsync_crd_absent`, plus the poll
outcome for a degraded cluster.
```
New:
```
Kinds: `overdue`, `invalid_schedule`, `sync_stopped`, `empty_group`, `unattributed`,
`stale_group`, `reconcile_error`, `dangling_binding`, `groupsync_crd_absent`,
`config_reconcile_error`, `direct_user_binding`, `group_count_cliff`,
`group_count_cliff_silenced`, plus the poll outcome for a degraded cluster.

Every row carries `silenced` (boolean) and `silenced_by` (`"annotation"` | `"values"` | `null`).
Only the group-count cliff sets them: a group whose membership fell by
`config.alerts.groupCountCliff.dropRatio` from at least `minMembers` within `windowHours`,
reconstructed from `membership_event` (`gsd/state.py#compute_alerts`,
`gsd/store.py#Store.group_count_changes`). A cliff silenced by the Group annotation
`groupsync-dashboard.io/silence-group-count-cliff` (`"true"` or `until=YYYY-MM-DD`) or by the
chart's `silence` list is reported under `group_count_cliff_silenced` with the same detail —
reported, never dropped. Both kinds are withheld at the self tier, like `empty_group`.
```

Also in `API.md`, the `/api/clusters/{id}/groups` row description gains: "`cliff_silence` — the raw silence annotation, or `null`."

**`docs/reference-architecture.md#Derived, never stored`** — append a third bold paragraph after the grace paragraph:
```
**The group-count cliff is reconstructed, not sampled.** `group_state` holds one count per
group, replaced each poll; the count at the window's start is `after + removed − added` over
the window's `membership_event` rows (`gsd/store.py#Store.group_count_changes`), which is exact
because `sync_members` writes one event per member transition. No sample table, so nothing to
drift and nothing to retain. Silencing is read from the Group annotation the poller carries
into `group_state.cliff_silence` or from values; a silenced cliff is still computed and served
(`gsd/state.py#cliff_silence`).
```

**`README.md#Not built yet`** — old:
```
Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), retention on the accumulated history, per-namespace PDF reports
```
New:
```
Effective-permission expansion, log-scrape enrichment, retention on the accumulated history,
per-namespace PDF reports
```

**`README.md`** docs table — add a row after the `DESIGN_session_and_signout.md` row:
```
| [`docs/DESIGN_grafana_dashboard_and_group_count_cliff.md`](docs/DESIGN_grafana_dashboard_and_group_count_cliff.md) | the shipped Grafana dashboard (a sidecar ConfigMap that follows the ServiceMonitor's switch) and the group-count cliff alert — reconstructed from membership events, silenced read-only by a Group annotation or values, reported even when silenced |
```

**`charts/group-sync-dashboard/README.md`**:
- `| \`monitoring.prometheusRule.enabled\` | \`false\` | **eleven** alerts — see below |` → `**twelve**`.
- `#### The eleven alerts` → `#### The twelve alerts`; add a row after `GroupSyncDashboardConfigReconcileError`:
```
| `GroupSyncGroupCountCliff` | `gsd_alerts_total{kind="group_count_cliff"} > 0` — a group lost `dropRatio` of at least `minMembers` members within `windowHours`. Rendered only while `config.alerts.groupCountCliff.enabled`; silenced cliffs count under `group_count_cliff_silenced` and never fire | `for.groupCountCliff`, `15m` |
```
- Values rows, after the `config.requestTimeoutSeconds` row:
```
| `config.alerts.groupCountCliff.enabled` | `true` | read-only, no extra RBAC, one indexed query per cluster per read. Off removes the kind and the rule together |
| `config.alerts.groupCountCliff.minMembers` / `.dropRatio` / `.windowHours` | `10` / `0.5` / `24` | the floor is what keeps the default quiet — below ten, half is one or two people. Ratio outside `(0, 1]`, floor below 1 or non-positive window refuse the render |
| `config.alerts.groupCountCliff.silence` | `[]` | exact names or fnmatch globs. Silenced cliffs are still reported (`group_count_cliff_silenced`), dimmed on the Overview. The other silence is the Group annotation `groupsync-dashboard.io/silence-group-count-cliff=true` or `=until=YYYY-MM-DD`, read on every poll, never written |
```
- The "Three values move together" paragraph is unchanged.

**`docs/CHANGELOG.md`** — under the `## Unreleased` heading created in B3.7, add before the chart bullet:
```
- **Group-count cliff alert, with read-only silencing.** A group whose membership fell by
  `config.alerts.groupCountCliff.dropRatio` (0.5) from at least `minMembers` (10) within
  `windowHours` (24) is alert kind `group_count_cliff`, severity warning — reconstructed from the
  membership events the poll already records, so no new table. Silence it read-only with the Group
  annotation `groupsync-dashboard.io/silence-group-count-cliff` (`true` or `until=YYYY-MM-DD`) or the
  chart's `silence` globs; a silenced cliff is still reported as `group_count_cliff_silenced`, dimmed
  on the Overview, counted under its own kind on `/metrics`, and never pages. New
  `GroupSyncGroupCountCliff` rule (the twelfth). `/api/alerts` rows gain `silenced` and
  `silenced_by`; group rows gain `cliff_silence`; schema migration 8. Both cliff kinds are withheld
  at the self tier. Default on, and the README's "needs a floor as well as a ratio" is answered by
  the floor. (design `DESIGN_grafana_dashboard_and_group_count_cliff.md`)
```

**`charts/group-sync-dashboard/Chart.yaml`** — insert above `version: 0.10.0`, then move the version:
```
# CHART 0.11.0 (2026-09-04), MINOR: two new modules, one of them default-on, and appVersion moves
# to application 0.12.0 (below). `config.alerts.groupCountCliff` (default true) adds five
# ConfigMap keys, a render guard on its thresholds, and a twelfth PrometheusRule alert,
# GroupSyncGroupCountCliff, rendered only while the module is on. `monitoring.grafanaDashboard`
# (default "" = follow monitoring.serviceMonitor.enabled) adds a sidecar-labelled ConfigMap
# carrying dashboards/group-sync-dashboard.json byte-for-byte. A default upgrade therefore
# gains the ConfigMap keys and, if the rules are on, one alert; nothing else changes shape.
version: 0.11.0
```
and `appVersion: "0.11.0"` → `appVersion: "0.12.0"`, with an application history line above it:
```
# 0.12.0 (2026-09-04). The group-count cliff alert (kinds group_count_cliff and
# group_count_cliff_silenced), `silenced`/`silenced_by` on every /api/alerts row, `cliff_silence` on
# group rows, schema migration 8. Additive on the wire; a consumer enumerating kinds sees two new
# ones. MINOR.
```

**Version bumps**: `local-development/pyproject.toml` `version = "0.12.0"`; `local-development/gsd/__init__.py` `__version__ = "0.12.0"`; `Chart.yaml` `appVersion: "0.12.0"`, `version: 0.11.0`. `tests/test_chart_versions.py` holds the three together; `image.tag` stays empty.

## B4.9 Verification

1. `local-development/.venv/bin/python -m pytest local-development/tests -q` — in particular `test_metrics.py` (the ALERT_KINDS ↔ state.py ↔ rules triad now includes both cliff kinds), `test_storage_seam.py` (`group_count_changes` declared with a matching signature), `test_migrations.py` (latest version 8), `test_docs_citations.py` (new anchors `gsd/state.py#cliff_silence`, `gsd/store.py#Store.group_count_changes`, `gsd/api.py#SELF_ALERT_DETAILS` resolve), `test_chart_versions.py`.
2. `helm template t charts/group-sync-dashboard --set monitoring.prometheusRule.enabled=true | grep -A3 GroupSyncGroupCountCliff`; then `--set config.alerts.groupCountCliff.enabled=false` shows no such alert; `--set config.alerts.groupCountCliff.dropRatio=2` fails naming the key.
3. On the reference cluster: `oc annotate group <g> groupsync-dashboard.io/silence-group-count-cliff=until=$(date -d tomorrow +%F)`; after one poll `/api/clusters/<c>/groups` shows `cliff_silence`; `oc annotate group <g> groupsync-dashboard.io/silence-group-count-cliff-` clears it after the next poll. Confirm `oc get group <g> -o yaml` still carries the annotation after the operator's next sync (see risk 1).
4. `curl -s .../metrics | grep group_count_cliff` shows only `kind=` labels, no group names.

## B4.10 Risks

1. **The group-sync-operator may overwrite Group annotations on its next sync.** It writes `sync-time` and `ldap.uid`; whether it preserves foreign annotations must be measured live before this is documented as the recommended silence. If it strips them, the values list is the durable silence and the annotation is documented as "until the next sync" — or the README recommends the values path only. **Operator-only question.**
2. **`membership_event` has no retention**, so the windowed query's cost is bounded only by the new `(cluster_id, observed_at)` index; on a very large directory the index build in migration 8 runs once at startup inside the writer's transaction — expected seconds, not minutes, but measure on the largest deployed database before release.
3. **A poll gap longer than the window** (dashboard down for two days) makes every change inside the gap land in one event batch at restart; a genuine cliff inside the gap is still caught (events are dated at observation), and nothing false is produced.
4. **Existing group rows on upgrade** are `cliff_silence: NULL` for one poll interval; a cliff already silenced by annotation reports as unsilenced for that interval. Acceptable and documented in the migration comment.
5. The `severity_rank` sort in `list_alerts` leaves silenced rows among warnings; they are visually dimmed rather than moved. If readers want them last, add `a.get("silenced", False)` to the sort key — a one-line follow-up, deliberately not done now to keep the wire order stable for existing consumers.


## Batch closing sections (verbatim)

## Operator-only questions

- Which namespace does your Grafana sidecar watch, and which label/annotation is it configured for? (Sets `monitoring.grafanaDashboard.labels`/`folder`, or whether to install beside Grafana.)
- grafana-operator v5 in use? If so, the `instanceSelector` labels for the `GrafanaDashboard` CR recipe.
- Does the group-sync-operator preserve a foreign annotation on the Group objects it syncs? (Risk 1 above.)
- Directory scale: is a floor of 10 and ratio 0.5 right for your largest groups, or should `minMembers` start higher?

### Critical Files for Implementation
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/state.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/metrics.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/monitoring.yaml
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/values.yaml
