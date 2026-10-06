# SPEC Q1 — the query planner's statistics: the store keeps them current and its readers use them (#626)

| | |
|---|---|
| Programme | After Epic F: a defect found on 2026-10-05 while answering the operator's question about the Groups list's reliability ("business logic … making it reliable and that it won't break"), under the operator's bound that a cluster never has 1,000 groups |
| Batch | Q — query performance |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 5.7.0, chart 0.70.11 |
| Version note | Image content (`local-development/gsd/store.py` and `local-development/gsd/storage.py`, under `publish.yml`'s `local-development/gsd/**`), so the next application MINOR; the chart's PATCH moves with `appVersion` |
| Issue | [#626](https://github.com/ephico2real2/group-sync-dashboard/issues/626) |
| Status | merged |
| Source | The orchestrator's research of 2026-10-05, posted on #626: SQLite's documentation (`lang_analyze.html`, `pragma.html#pragma_optimize`, `queryplanner-ng.html`), the code, measurements on SQLite 3.53.4 (the image's version, read in the pod) and a read-only copy of the lab's database. The orchestrator wrote this spec and its code; the reviews are recorded under the orchestrator's notes |

## How to read this spec

The plain point first. SQLite chooses how to run a query from statistics about the tables, which `ANALYZE` gathers.
The dashboard's database has never had any. Without them SQLite guesses from the shape of the indexes, and for two
reads it guesses badly: it narrows only to the cluster and then reads the cluster's whole table once for every row
it returns. The Groups list counts each group's bindings that way, and a group's detail page finds each member's
first-seen date that way. Both get slower as bindings and history grow.

The fix is SQLite's own recommendation: the store runs `PRAGMA optimize` when it opens and after every poll cycle,
and it costs nothing when nothing has changed. One more step is needed, because a connection that is already open
never loads new statistics. The store's API reads use long-lived connections, so each one reconnects on its next
read after the statistics change.

§1 is the mandate. §2 is the research. §2a lists the alternatives and why each was not chosen. §3 is the design.
§4 maps each check to its test. §5 is the audit of every other read. §6 is the lab check. §7 is the change as
implementation blocks (`docs/specs/README.md`, "Implementation blocks").

## 1. Mandate

The operator, 2026-10-05: "we can never have 1000 groups per cluster. but how best can make this work better as per
it being a business logic?", then "pls create an issue for this", then "Go ahead and do your research", then
"Documents this search in the issue and then create a solution yourself and then have codex astra and cursor grok
review it as per our skills. Then give it to ob2 to review and ads enhancement while you orchestrate and merge all
from file into code."

Done means:

1. The Groups list and a group's detail page use an index that narrows past the cluster, at the operator's bound
   (fewer than 1,000 groups per cluster), with the same rows as today.
2. Statistics stay current as the data grows, with no operator action.
3. The API's long-lived readers use the new statistics without a restart.
4. No other read gets slower or returns different rows.
5. No schema change and no new setting.

## 2. Research

Posted in full on #626 (2026-10-05). The facts this design rests on:

**2.1 The database has no statistics.** The lab's `gsd.db` has no `sqlite_stat1` (read in the pod, `mode=ro`), and
`local-development/gsd/store.py` says so where #177 worked around the same cause: "this store never runs ANALYZE".
Without statistics the planner judges indexes by shape alone (`queryplanner-ng.html`).

**2.2 The two plans.**

| read | plan today | plan with statistics |
|---|---|---|
| `Store.groups`, the per-group binding count | `SEARCH b USING COVERING INDEX sqlite_autoindex_rbac_group_binding_1 (cluster_id=?)` | `SEARCH b USING INDEX rbac_binding_by_group (cluster_id=? AND group_name=?)` |
| `Store.group_members`, each member's first-seen | `SEARCH e USING INDEX membership_event_by_time (cluster_id=?)` | `SEARCH e USING INDEX membership_event_by_user (cluster_id=? AND user_name=?)` |

**2.3 Measured on SQLite 3.53.4** with 999 groups, 50,000 bindings and 300,000 membership events (added and removed,
spread over months); median of 5; the same rows in every case:

| | groups list | group detail (25 members) | one-off cost |
|---|---|---|---|
| no statistics (today) | 2,502 ms | 5,459 ms | |
| `ANALYZE` | 20.2 ms | 1.0 ms | 86.5 ms |
| `PRAGMA optimize=0x10002` | 19.8 ms | 0.9 ms | 85.2 ms |
| `PRAGMA analysis_limit=1000` + `PRAGMA optimize=0x10002` | 20.3 ms | 1.2 ms | 7.1 ms |
| covering indexes, no statistics | 1.3 ms | 0.0 ms | 205 ms, plus a schema migration |

**2.4 The lab today.** 26 clusters; `rbac_group_binding` 11,105 rows, `membership_event` 1,843. In the pod, the
Groups list takes about 100 ms on a cluster with about 1,000 bindings (`dashboard`: 66 groups, 1,042 bindings,
103 ms) and about 14 ms with 199. The same query on a copy of the same database took 2.3 ms on the orchestrator's
machine, about 45 times faster. The pod's container is limited to 500m CPU, which fits, but the cause of the ratio
was not measured. Group detail is about 1 ms on the lab, which has about 95 events per cluster.

**2.5 SQLite's guidance.** "Applications that use long-lived database connections should run `PRAGMA
optimize=0x10002;` when the connection is first opened, and then also run `PRAGMA optimize;` periodically, perhaps
once per day" (`lang_analyze.html` §2.1; `pragma.html#pragma_optimize`, the recommended form since 3.46.0). "set
`PRAGMA analysis_limit=N` for N between 100 and 1000" (§5). The mask `0x10002` does not include `0x10`, the bit that
applies a temporary analysis limit, which is why it measured as a full `ANALYZE` (85 ms) and the explicit
`analysis_limit` brought it to 7 ms with the same plans.

**2.6 Measured behaviour of `PRAGMA optimize`.**

- On empty tables it records nothing.
- Once a table has rows and no statistics, the next run analyses it.
- Afterwards it re-analyses a table only when its size changes by about an order of magnitude: +10 % did nothing,
  ×10 did.
- When nothing changed it costs 0.0 ms.
- Its debug form, `PRAGMA optimize(0x10003)`, lists the `ANALYZE` statements it would run and runs none.

**2.7 An open connection never loads new statistics.** "The query planner loads the content of the statistics tables
into memory when the schema is read" (`lang_analyze.html` §3). `ANALYZE` does not change `PRAGMA schema_version`, so
a connection that was already open kept its old plan after another connection analysed the database. That held with
`cached_statements=0` too, so it is not Python's statement cache. A new connection got the new plan. The
documented reload, `ANALYZE sqlite_schema`, is a write: on a read-only connection it fails with "attempt to write a
readonly database", and while the writer holds a write lock it fails with "database is locked" (both measured).

**2.8 The store's connections** (`Store.__init__`, `Store._reader`): one writer connection for the life of the
process, and one reader connection per thread, also for the life of the process. Inside `Store.read_snapshot` a
thread's reader holds an open read transaction across several statements. The report service reads an immutable
copy of the file, which carries the copy's statistics with it.

## 2a. Alternatives

1. **Rewrite the two queries** (one `GROUP BY` instead of a correlated count). Measured: 2,546 ms to 20.5 ms, the
   same rows. Not chosen: it fixes two instances of a cause that has now appeared three times (#177 was the first),
   and the next query written against an unanalysed database meets it again.
2. **Covering indexes.** The fastest (1.3 ms and 0.0 ms), but a schema migration, and with it a pre-upgrade copy
   and the migration test for every install, to fix a planner that already has the right indexes and lacks only
   the statistics to choose them.
3. **`INDEXED BY` hints.** The checklist's last resort (`queryplanner-ng.html`). They pin a plan the data may later
   prove wrong, and fail the query outright if an index is renamed.
4. **`ANALYZE sqlite_schema` on each reader after a refresh.** It is a write (§2.7), so an API read would queue
   behind the poll's writer, which is what the per-thread readers exist to prevent.

## 3. Design

**3.1 At open.** The writer sets `PRAGMA analysis_limit=1000` (connection state; it governs every `PRAGMA optimize`
this connection runs), then, after the schema and migrations, runs the refresh of §3.2. On a fresh install the
tables are empty and the refresh does nothing.

**3.2 The refresh** (`Store._refresh_statistics`). Under the write lock and never inside a transaction, the writer
asks `PRAGMA optimize(0x10003)` what it would analyse. An empty list ends it there, which is the common case and
measured at 0.0 ms. Otherwise it runs `PRAGMA optimize=0x10002`, commits, increments a statistics epoch, and logs
the tables it analysed at INFO.

**3.3 After every write cycle.** `Store.maintain()`, which the leader's poll thread calls after each cycle and never
from a request, runs the WAL checkpoint and then the refresh. The storage seam's description of `maintain()` says
so. No other engine is affected: the seam's contract is unchanged.

**3.4 The readers.** Each per-thread reader remembers the epoch it was opened under. On its next read, if the epoch
has moved and the thread is not inside a `read_snapshot` and the connection is not in a transaction, it closes the
connection and opens a new one, which loads the new statistics. Inside a snapshot it keeps the connection: the
snapshot's consistency is what the caller asked for, and the read after it reconnects. `:memory:` stores share the
writer's connection, as they do today.

**3.5 What does not change.** Every row every read returns (§5); the schema; the settings; the storage seam's
contract; the report service. #177's `UNION ALL` stays: it is index-served with or without statistics, and
statistics appear only once a table has rows. Its comment now says so.

## 4. Tests

`local-development/tests/test_store_statistics.py`, against a database at the operator's bound written straight to
the tables (999 groups, 50,000 bindings, a 25-member group, 100,000 membership events), with no statistics in it.
Each plan is read from the SQL the store itself runs: the reader's trace callback gives it with its values bound.

| done-means | test | fails before the change |
|---|---|---|
| 1 | `test_open_gathers_statistics_and_both_reads_use_their_index` | yes |
| 1 | `test_both_reads_stay_inside_a_budget_at_the_operator_s_bound` (0.5 s and 0.2 s; measured about 2.5 s and 1.8 s without statistics on this data) | yes |
| 1, 4 | `test_the_rows_are_the_same_with_and_without_statistics` | no: it holds on both sides, by design |
| 2, 3 | `test_a_reader_opened_before_a_refresh_reconnects_and_uses_the_new_statistics` | yes |
| 2 | `test_nothing_changed_means_no_refresh_and_no_reconnect` | yes |
| 3 | `test_a_reader_inside_a_read_snapshot_is_not_replaced_until_the_snapshot_ends` | yes |
| 3 | `test_a_reader_on_another_thread_reconnects_too` | yes |

Measured on the branch: 7 passed. Against the unchanged `store.py` and `storage.py`: 6 failed, 1 passed (the rows
test). The full hermetic suite and CI run on the PR.

## 5. The audit of every other read

Statistics change the plan of any query, not only these two. Every public read-only method of `Store` (75, found by
inspection: methods that read through `_rows`/`_row` and write nothing) was called on a read-only copy of the lab's
database, with each optional scope both off and on, and every statement it ran was traced. Each of the 127
statements was then run on two copies of the database, one never opened by the changed store (no statistics) and
one analysed by it, comparing rows, plan and time:

- rows identical for all 127 statements;
- plans changed for 14 statements (`groups` twice, `ungoverned_login_users`, `user_bindings`, `namespaces`,
  `group_bindings`, `namespace_reach`, `group_members`, `memberships_by_cluster`, `login_without_access`,
  `count_login_without_access`, `cluster_access_summary`, `membership_events`, `user_groups`), each faster or equal;
- no statement slower by more than 1.5 times and 1 ms.

The lab's tables are small, so the times there are small; the plans are what the audit establishes.

## 6. Lab check

After the deploy, on the lab, read-only:

1. `sqlite_stat1` exists in `gsd.db`.
2. The dashboard's log shows `query planner statistics refreshed`.
3. The Groups list's query on the `dashboard` cluster uses `rbac_binding_by_group`, and its time drops from about
   100 ms.
4. The pods are ready and the PVC UIDs are unchanged.

## 7. The change

The implementation blocks follow, in order. Applied to a clean `main` with `local-development/apply-spec-blocks.py`,
they reproduce the branch exactly, apart from this file.

## Orchestrator's notes

1. The research, this spec and its code were written by the orchestrator, at the operator's instruction (§1). The
   reviews follow the adversarial-review skill: Codex Astra and Cursor Grok first, then OB2 for a review and
   enhancements; each reviewer writes a findings file, and the orchestrator decides and applies from those files.
