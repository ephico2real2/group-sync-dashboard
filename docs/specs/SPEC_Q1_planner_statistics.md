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
| Source | The orchestrator's research of 2026-10-05, posted on #626: SQLite's documentation ([lang_analyze](https://www.sqlite.org/lang_analyze.html), [pragma_optimize](https://www.sqlite.org/pragma.html#pragma_optimize), [queryplanner-ng](https://www.sqlite.org/queryplanner-ng.html)), the code, measurements on SQLite 3.53.4 (the image's version, read in the pod) and a read-only copy of the lab's database. The orchestrator wrote this spec and its code; the reviews are recorded under the orchestrator's notes |

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
Without statistics the planner judges indexes by shape alone ([queryplanner-ng](https://www.sqlite.org/queryplanner-ng.html)).

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
once per day" ([lang_analyze](https://www.sqlite.org/lang_analyze.html) §2.1; [pragma_optimize](https://www.sqlite.org/pragma.html#pragma_optimize), the recommended form since 3.46.0). "set
`PRAGMA analysis_limit=N` for N between 100 and 1000" (§5). Two bits of the mask matter here. `0x10000` makes the
pragma consider every table, not only the ones this connection has queried since it opened: measured on 3.53.4 (OB2),
a table analysed at 2,000 rows and grown to 202,000 is skipped by `optimize(0x03)` from a connection that never queried
it and listed by `optimize(0x10003)`. The writer is exactly such a connection at open and after a poll, since it writes
those tables and never reads them through the planner, so without that bit the refresh would gather nothing. The mask
does not include `0x10`, the bit that applies a temporary analysis limit, which is why it measured as a full `ANALYZE`
(85 ms) and the explicit `analysis_limit` brought it to 7 ms with the same plans. The `0x10000` bit is SQLite 3.46.0's;
the image ships 3.53.4 (§2.1).

**2.6 Measured behaviour of `PRAGMA optimize`.**

- On empty tables it records nothing.
- Once a table has rows and no statistics, the next run analyses it.
- Afterwards it re-analyses a table only when its size changes by about an order of magnitude: +10 % did nothing,
  ×10 did.
- When nothing changed it costs 0.0 ms.

The debug form, `PRAGMA optimize(0x10003)`, lists the ANALYZE statements it would run and runs none. It is still a
write: with two or more tables to check it takes the database's write lock. SQLite's source file pragma.c starts
a write operation regardless of the debug bit; with another connection holding the lock, the measured result was
"database is locked" after busy_timeout. It also expires the connection's prepared statements, which cost about
2 µs per statement to prepare again.

**2.7 An open connection can retain old statistics.** SQLite loads statistics when it reads the schema
([lang_analyze](https://www.sqlite.org/lang_analyze.html) §3). The first ANALYZE can create statistics tables and change `PRAGMA schema_version`,
causing existing readers to reload the schema. Once those tables exist, a later ANALYZE need not change
`schema_version`: an already-open connection can keep its old plan, even with `cached_statements=0`.
A new connection reads the updated statistics, so reconnecting after each successful refresh covers both cases.
The documented reload, `ANALYZE sqlite_schema`, requires a writable connection and can contend with the writer;
the store therefore reconnects readers outside their snapshots instead.

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
3. **`INDEXED BY` hints.** The checklist's last resort ([queryplanner-ng](https://www.sqlite.org/queryplanner-ng.html)). They pin a plan the data may later
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
the tables it analysed at INFO. A failed refresh never raises: it is logged at WARNING with the traceback, the
epoch stays unchanged, and it is retried after the next poll. Statistics are an optimisation; allowing the error
to escape would stop Store() opening and, from maintain(), record a successful poll as `unreachable` and skip its
backup, as measured on b65ce09d.

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
The whole module, including the image-proof test, skips below SQLite 3.46.0 locally and in CI;
`local-development/image-proof.py` proves the refresh and Groups plan on the image's own SQLite as the runtime
user at every build, refusing versions below 3.46.0. Its small seed is three groups with one binding each:
on 3.53.4, one and two retain the cluster-only index, while three use the group-binding index.

| done-means | test | fails before the change |
|---|---|---|
| 1, 2 | `test_image_proof_planner_statistics` | yes: the image proof requires statistics for the group-binding index and the traced Groups query to use it |
| 1 | `test_open_gathers_statistics_and_both_reads_use_their_index` | yes |
| 1 | `test_both_reads_stay_inside_a_budget_at_the_operator_s_bound` (0.5 s and 0.2 s; measured about 2.2 s and 0.6 s without statistics, about 15 ms and 0.5 ms with them on this data) | yes |
| 1, 4 | `test_the_rows_are_the_same_with_and_without_statistics` | no: it holds on both sides, by design |
| 2, 3 | `test_a_reader_opened_before_a_refresh_reconnects_and_uses_the_new_statistics` | yes |
| 2 | `test_nothing_changed_means_no_refresh_and_no_reconnect` | yes |
| 3 | `test_a_reader_inside_a_read_snapshot_is_not_replaced_until_the_snapshot_ends` | yes |
| 3 | `test_a_reader_on_another_thread_reconnects_too` | yes |
| 3 | `test_reader_recovers_after_reconnect_failure` | yes: a failed reconnect leaves a closed reader cached |
| 2 | `test_refresh_failure_is_optional_at_open_and_maintain` | yes: a refresh failure aborts open or upkeep |
| 2, 3 | `test_a_refresh_of_existing_statistics_reaches_a_reader_opened_before_it` | yes; without the reconnect, it fails at the plan |
| 2 | `test_the_refresh_never_commits_an_enclosing_transaction` | no: main has no refresh; it guards the refresh's transaction check |
| 2 | `test_a_failed_refresh_leaves_a_successful_poll_ok_and_its_backup_written` | no: main has no refresh; on b65ce09d the poll was recorded `unreachable` |

Measured on the branch: 13 passed, including the image proof. Before adding that proof, against the unchanged
`local-development/gsd/store.py` and `local-development/gsd/storage.py` of main 730158d4: 9 failed,
3 passed (the rows test, the enclosing-transaction test, and the successful-poll/backup test; main has no refresh
to fail). The full hermetic suite and CI run on the PR.

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

1. `sqlite_stat1` exists in `gsd.db`, and its row for `rbac_group_binding` / `rbac_binding_by_group` is recorded
   (the estimate the Groups list's plan rests on).
2. The dashboard's log shows `query planner statistics refreshed`, and after three or more poll cycles it shows it
   at most twice (at open, and after the first poll if a table crossed the threshold) and never `query planner
   statistics refresh failed`: one refresh per cycle would mean the threshold is re-armed every cycle, which §2.6
   measured not to happen and this step confirms on real polls.
3. The Groups list's query on the `dashboard` cluster uses `rbac_binding_by_group`, and its time drops from about
   100 ms.
4. The pod's SQLite is 3.46.0 or later (`python3 -c 'import sqlite3; print(sqlite3.sqlite_version)'` in the pod;
   3.53.4 expected), recorded in the walk.
5. The pods are ready and the PVC UIDs are unchanged.

## 7. The change

The implementation blocks follow, in order. Applied to a clean `main` with `local-development/apply-spec-blocks.py`,
they reproduce the branch exactly, apart from this file.

### Block 1 — `.github/workflows/ci.yml`

<!-- block: .github/workflows/ci.yml | edit -->

```text
        run: |
          python -m pip install --upgrade pip
          pip install -e '.[dev]' || pip install -e .
      - name: Install promtool, the PromQL parser the dashboard test needs
        # tests/test_chart_grafana_dashboard.py parses every panel expression of the shipped
        # Grafana board with promtool. Locally the test skips when promtool is absent; in CI it
```

```text
        run: |
          python -m pip install --upgrade pip
          pip install -e '.[dev]' || pip install -e .
          # The store relies on PRAGMA optimize=0x10002 (SQLite 3.46.0; #626). The interpreter links the runner's
          # system SQLite, so the version is a fact of the runner, printed here where a failing plan test can be
          # read against it.
          python -c 'import sqlite3; print("SQLite", sqlite3.sqlite_version)'
      - name: Install promtool, the PromQL parser the dashboard test needs
        # tests/test_chart_grafana_dashboard.py parses every panel expression of the shipped
        # Grafana board with promtool. Locally the test skips when promtool is absent; in CI it
```

### Block 2 — `README.md`

<!-- block: README.md | edit -->

```markdown
| [`docs/guides/TUTORIAL_mermaid_diagrams.md`](docs/guides/TUTORIAL_mermaid_diagrams.md) | tutorial: how the diagrams are derived from code, written in Mermaid, checked in half a second and rendered in CI — with two built from scratch |
| [`docs/design/DESIGN_reporting_service.md`](docs/design/DESIGN_reporting_service.md) | the report service: eleven access-review reports as HTML and PDF/A from a separate pod, its data path, its tickets |
| [`docs/design/namespace-report-design.md`](docs/design/namespace-report-design.md) | superseded — per-namespace and access-review reports as HTML/PDF from a separate report service; the definitive answer on `--openshift-sar` |
| [`docs/specs/README.md`](docs/specs/README.md) | **the feature programme** — sixty specifications, starting from the original thirteen modules, each specified with its complete code before any is implemented, one GitHub issue and milestone each, released strictly one at a time; the index, the version ladder and the definition of done |

## Install

```

```markdown
| [`docs/guides/TUTORIAL_mermaid_diagrams.md`](docs/guides/TUTORIAL_mermaid_diagrams.md) | tutorial: how the diagrams are derived from code, written in Mermaid, checked in half a second and rendered in CI — with two built from scratch |
| [`docs/design/DESIGN_reporting_service.md`](docs/design/DESIGN_reporting_service.md) | the report service: eleven access-review reports as HTML and PDF/A from a separate pod, its data path, its tickets |
| [`docs/design/namespace-report-design.md`](docs/design/namespace-report-design.md) | superseded — per-namespace and access-review reports as HTML/PDF from a separate report service; the definitive answer on `--openshift-sar` |
| [`docs/specs/README.md`](docs/specs/README.md) | **the feature programme** — sixty-one specifications, starting from the original thirteen modules, each specified with its complete code before any is implemented, one GitHub issue and milestone each, released strictly one at a time; the index, the version ladder and the definition of done |

## Install

```

### Block 3 — `charts/group-sync-dashboard/Chart.yaml`

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# app used its default for "80%"), outside (0, 100], or, for memory, CPU and disk, at or below 1, a ratio
# (#627); the unit is stated in values.yaml. The default render is unchanged apart from this version;
# no RBAC change; appVersion unchanged.
version: 0.70.10
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

```yaml
# app used its default for "80%"), outside (0, 100], or, for memory, CPU and disk, at or below 1, a ratio
# (#627); the unit is stated in values.yaml. The default render is unchanged apart from this version;
# no RBAC change; appVersion unchanged.
# CHART 0.70.11 (2026-10-05), PATCH: appVersion moves to application 5.7.0 (below); #626: the store
# keeps the query planner's statistics current.
version: 0.70.11
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

### Block 4 — `charts/group-sync-dashboard/Chart.yaml`

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# the lab (docs audit, batch 4). MINOR.
# 5.6.0 (2026-10-05). #625: four code defects the docs audit found (chart-bump gap, prefix
# attribution, prepare-release --pr, render-manifests cookie step). MINOR.
appVersion: "5.6.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
home: https://github.com/ephico2real2/group-sync-dashboard
```

```yaml
# the lab (docs audit, batch 4). MINOR.
# 5.6.0 (2026-10-05). #625: four code defects the docs audit found (chart-bump gap, prefix
# attribution, prepare-release --pr, render-manifests cookie step). MINOR.
# 5.7.0 (2026-10-05). #626: the store keeps the query planner's statistics current. MINOR.
appVersion: "5.7.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
home: https://github.com/ephico2real2/group-sync-dashboard
```

### Block 5 — `docs/CHANGELOG.md`

<!-- block: docs/CHANGELOG.md | edit -->

```markdown

## Unreleased

- **KPI thresholds are checked at render, and their unit is stated (#627; chart 0.70.10).** `kpi.thresholds.*` are
  percentages: `80` means 80 %, not `0.8`. The render now refuses a non-number (such as `"80%"`), a value outside
  `(0, 100]`, and a memory, CPU or disk value at or below `1`, which can only be a ratio written by mistake, naming the
```

```markdown

## Unreleased

- **The store keeps the query planner's statistics current (#626, `docs/specs/SPEC_Q1_planner_statistics.md`;
  application 5.7.0, chart 0.70.11).** `gsd.db` had never been analysed, so SQLite planned from index shape alone, and
  two reads read a cluster's whole table once per row: the Groups list's binding count (2.5 s at 999 groups and 50,000
  bindings) and group detail's first-seen (5.5 s at 300,000 membership events). The store now runs SQLite's
  recommended `PRAGMA optimize` (with `analysis_limit`) at open and after every write cycle, and each per-thread
  reader reconnects after a refresh, because an open connection never loads new statistics: 20 ms and 1 ms, the same
  rows. On the lab's own database, all 75 read methods return the same rows; 14 statements change plan, each faster,
  none slower. No schema change.

- **KPI thresholds are checked at render, and their unit is stated (#627; chart 0.70.10).** `kpi.thresholds.*` are
  percentages: `80` means 80 %, not `0.8`. The render now refuses a non-number (such as `"80%"`), a value outside
  `(0, 100]`, and a memory, CPU or disk value at or below `1`, which can only be a ratio written by mistake, naming the
```

### Block 6 — `docs/specs/README.md`

<!-- block: docs/specs/README.md | edit -->

```markdown
# Feature programme 2026-09 — the specifications

Sixty specifications are indexed below. The original programme has thirteen modules, each specified with its complete code **before** any of them is implemented,
each tracked by one GitHub issue inside one GitHub milestone, and each implemented, released,
validated and audited **strictly one at a time**. This directory is the only source the
implementation is applied from: nothing is implemented from memory, and a specification is
```

```markdown
# Feature programme 2026-09 — the specifications

Sixty-one specifications are indexed below. The original programme has thirteen modules, each specified with its complete code **before** any of them is implemented,
each tracked by one GitHub issue inside one GitHub milestone, and each implemented, released,
validated and audited **strictly one at a time**. This directory is the only source the
implementation is applied from: nothing is implemented from memory, and a specification is
```

### Block 7 — `docs/specs/README.md`

<!-- block: docs/specs/README.md | edit -->

```markdown
  one `local-development/prepare-release.py` cuts — is what a spec's `released` status names
  (below).

## The sixty specifications

| Id | Specification | Batch | Milestone | Version on release | Issue | Status |
|---|---|---|---|---|---|---|
```

```markdown
  one `local-development/prepare-release.py` cuts — is what a spec's `released` status names
  (below).

## The sixty-one specifications

| Id | Specification | Batch | Milestone | Version on release | Issue | Status |
|---|---|---|---|---|---|---|
```

### Block 8 — `docs/specs/README.md`

<!-- block: docs/specs/README.md | edit -->

```markdown
| F6 | [`SPEC_F6_ticket_signing_key.md`](SPEC_F6_ticket_signing_key.md) — the ticket signing key: a viewer's ticket is signed with HMAC-SHA256 under `<reportName>-ticket-key`, a Secret the secrets-mint hook creates once (48 random characters, never carried over, never overwritten) and only the dashboard and the report pod mount, never a schedule CronJob, so the service token no longer signs a ticket naming anybody; tickets become `v2.<payload>.<sig>`, a version-1 ticket is answered 401 so an open page mints again, one signed with the token 403; a rotation moves the key to `previous`, which the report pod verifies with until one ticket lifetime after the dashboard's restart (the chart README's two commands, tested); the service token, the probes and every other door unchanged; RBAC REMOVED 0, ADDED 1 | F — reports (Epic F #386, step 6 of 6) | — | app 4.6.0, chart 0.69.0 | [#392](https://github.com/ephico2real2/group-sync-dashboard/issues/392) | released |
| F7 | [`SPEC_F7_snapshot_clock.md`](SPEC_F7_snapshot_clock.md) — the reports' clock is the snapshot's: a report's windows, cutoffs and overdue states end at the snapshot's stamp, not the generation time (`RunContext.snapshot_at`), so two runs over one snapshot hash the same at any clock while page one's "Generated at" stays the generation time (#592); compliance-snapshot's sealed Sync pipeline keeps the poll's status and its WHEN answer the capture's start, and login-activity's Window drops "Last log read", both instants staying on page one, so a diff across snapshots shows only data (#607); the Reports form starts with only HTML ticked, reading "Generate HTML · JSON" (#593); the test seed's snapshot is stamped at its `NOW`; compliance-snapshot's, login-activity's and groupsync-health's sha256 change once, groups' and dormant-access's only where the window's edge moves a row, the other six never | F — reports (after Epic F #386: #592, #607, #593) | — | app 5.1.0, chart 0.70.2 | [#592](https://github.com/ephico2real2/group-sync-dashboard/issues/592) | merged |
| P1 | [`SPEC_P1_promote_release_branch.md`](SPEC_P1_promote_release_branch.md) — build once and promote: `promote.yml` runs after a green `publish.yml` on `main`, after a chart or `environments/` merge, or by hand; it builds nothing, reads each image at the immutable `<appVersion>-<sha10>` of `main`'s last image-input commit and requires `:<appVersion>` at the same digest (a notice while it is still publishing), checks the version label on every Linux image and the signature from `publish.yml` on `main`, pins both by digest in `promotion.yaml` and fast-forwards the `release` branch (the chart, `environments/`, `promotion.yaml`) with a deploy key only `main` can use; during development the lab tracks `main` (the operator: "main by default; release optional") and `release-crc.sh --argocd release` is the opt-in, used for each epic release's walk, with `--argocd main` to switch back; the end state is `group-sync-dashboard-dev` on `main` and `group-sync-dashboard` on `release` | P — promotion (release safety, part B of #410) | — | app 5.2.0, chart 0.70.3 | [#598](https://github.com/ephico2real2/group-sync-dashboard/issues/598) | merged |

The rows are in **implementation order**, which is also the version ladder. Status moves
`specified → in progress → merged → released`: `in progress` while some of the spec is on
```

```markdown
| F6 | [`SPEC_F6_ticket_signing_key.md`](SPEC_F6_ticket_signing_key.md) — the ticket signing key: a viewer's ticket is signed with HMAC-SHA256 under `<reportName>-ticket-key`, a Secret the secrets-mint hook creates once (48 random characters, never carried over, never overwritten) and only the dashboard and the report pod mount, never a schedule CronJob, so the service token no longer signs a ticket naming anybody; tickets become `v2.<payload>.<sig>`, a version-1 ticket is answered 401 so an open page mints again, one signed with the token 403; a rotation moves the key to `previous`, which the report pod verifies with until one ticket lifetime after the dashboard's restart (the chart README's two commands, tested); the service token, the probes and every other door unchanged; RBAC REMOVED 0, ADDED 1 | F — reports (Epic F #386, step 6 of 6) | — | app 4.6.0, chart 0.69.0 | [#392](https://github.com/ephico2real2/group-sync-dashboard/issues/392) | released |
| F7 | [`SPEC_F7_snapshot_clock.md`](SPEC_F7_snapshot_clock.md) — the reports' clock is the snapshot's: a report's windows, cutoffs and overdue states end at the snapshot's stamp, not the generation time (`RunContext.snapshot_at`), so two runs over one snapshot hash the same at any clock while page one's "Generated at" stays the generation time (#592); compliance-snapshot's sealed Sync pipeline keeps the poll's status and its WHEN answer the capture's start, and login-activity's Window drops "Last log read", both instants staying on page one, so a diff across snapshots shows only data (#607); the Reports form starts with only HTML ticked, reading "Generate HTML · JSON" (#593); the test seed's snapshot is stamped at its `NOW`; compliance-snapshot's, login-activity's and groupsync-health's sha256 change once, groups' and dormant-access's only where the window's edge moves a row, the other six never | F — reports (after Epic F #386: #592, #607, #593) | — | app 5.1.0, chart 0.70.2 | [#592](https://github.com/ephico2real2/group-sync-dashboard/issues/592) | merged |
| P1 | [`SPEC_P1_promote_release_branch.md`](SPEC_P1_promote_release_branch.md) — build once and promote: `promote.yml` runs after a green `publish.yml` on `main`, after a chart or `environments/` merge, or by hand; it builds nothing, reads each image at the immutable `<appVersion>-<sha10>` of `main`'s last image-input commit and requires `:<appVersion>` at the same digest (a notice while it is still publishing), checks the version label on every Linux image and the signature from `publish.yml` on `main`, pins both by digest in `promotion.yaml` and fast-forwards the `release` branch (the chart, `environments/`, `promotion.yaml`) with a deploy key only `main` can use; during development the lab tracks `main` (the operator: "main by default; release optional") and `release-crc.sh --argocd release` is the opt-in, used for each epic release's walk, with `--argocd main` to switch back; the end state is `group-sync-dashboard-dev` on `main` and `group-sync-dashboard` on `release` | P — promotion (release safety, part B of #410) | — | app 5.2.0, chart 0.70.3 | [#598](https://github.com/ephico2real2/group-sync-dashboard/issues/598) | merged |
| Q1 | [`SPEC_Q1_planner_statistics.md`](SPEC_Q1_planner_statistics.md) — the query planner's statistics: the store runs SQLite's recommended `PRAGMA optimize` (with `analysis_limit`) at open and after every write cycle, and each per-thread reader reconnects after a refresh, because an open connection never loads new statistics; the Groups list's binding count and a group's first-seen dates stop reading a cluster's whole table once per row (2.5 s and 5.5 s to 20 ms and 1 ms at the operator's bound), with the same rows from every read | Q — query performance | — | app 5.7.0, chart 0.70.11 | [#626](https://github.com/ephico2real2/group-sync-dashboard/issues/626) | merged |

The rows are in **implementation order**, which is also the version ladder. Status moves
`specified → in progress → merged → released`: `in progress` while some of the spec is on
```

### Block 9 — `local-development/gsd/__init__.py`

<!-- block: local-development/gsd/__init__.py | edit -->

```python
# pod is running a version it is not — the same failure appVersion had, and quieter, because the
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.6.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
# the API docs all read this; the README heading is held to it by tests/test_title.py. It used
```

```python
# pod is running a version it is not — the same failure appVersion had, and quieter, because the
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.7.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
# the API docs all read this; the README heading is held to it by tests/test_title.py. It used
```

### Block 10 — `local-development/gsd/storage.py`

<!-- block: local-development/gsd/storage.py | edit -->

```python
are replaced by two engine-neutral operations:

* ``maintain()`` — "do whatever periodic upkeep your engine needs". SQLite truncates the
  WAL; Postgres would do nothing and return an empty dict.
* ``health()`` — a free-form dict of engine-reported facts, which the collector turns into
  metrics without knowing what produced them.

```

```python
are replaced by two engine-neutral operations:

* ``maintain()`` — "do whatever periodic upkeep your engine needs". SQLite truncates the
  WAL and refreshes the query planner's statistics (#626); Postgres would do nothing and return an
  empty dict.
* ``health()`` — a free-form dict of engine-reported facts, which the collector turns into
  metrics without knowing what produced them.

```

### Block 11 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
        self.reader_busy_timeout_ms = reader_busy_timeout_ms
        self.wal_checkpoint_bytes = int(wal_checkpoint_mb * 1024 * 1024)
        self._checkpoint_busy_total = 0
        self._lock = threading.RLock()
        self._local = threading.local()
        # Transaction depth is PER THREAD, not per Store. A plain attribute here was a
```

```python
        self.reader_busy_timeout_ms = reader_busy_timeout_ms
        self.wal_checkpoint_bytes = int(wal_checkpoint_mb * 1024 * 1024)
        self._checkpoint_busy_total = 0
        # Bumped each time the writer refreshes the planner's statistics; a reader opened before it
        # reconnects on its next read, because only a new connection loads them (#626, _reader).
        self._stats_epoch = 0
        self._lock = threading.RLock()
        self._local = threading.local()
        # Transaction depth is PER THREAD, not per Store. A plain attribute here was a
```

### Block 12 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
        # 50k-row refresh. Set GSD_SQLITE_SYNCHRONOUS=FULL if that trade is wrong for you.
        self._conn.execute(f"PRAGMA synchronous={_safe_pragma_word(synchronous, 'NORMAL')}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        _migrate(self._conn)
        _seed_observation_markers(self._conn)
        self._conn.commit()

    def close(self) -> None:
        # Under the lock: closing while another thread is mid-transaction would
```

```python
        # 50k-row refresh. Set GSD_SQLITE_SYNCHRONOUS=FULL if that trade is wrong for you.
        self._conn.execute(f"PRAGMA synchronous={_safe_pragma_word(synchronous, 'NORMAL')}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        # An approximate ANALYZE, as lang_analyze.html §5 advises: a scan of at most ~1000 rows per index, 7 ms
        # where the full one took 85 ms at 50,000 bindings, and the same plans (#626). Connection state: it governs
        # every PRAGMA optimize this writer runs.
        self._conn.execute("PRAGMA analysis_limit=1000")
        self._conn.executescript(SCHEMA)
        _migrate(self._conn)
        _seed_observation_markers(self._conn)
        self._conn.commit()
        self._refresh_statistics()

    def close(self) -> None:
        # Under the lock: closing while another thread is mid-transaction would
```

### Block 13 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
        if self.path == ":memory:":
            return self._conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            _harden(conn)
```

```python
        if self.path == ":memory:":
            return self._conn
        conn = getattr(self._local, "conn", None)
        if (conn is not None and getattr(self._local, "stats_epoch", 0) != self._stats_epoch
                and not getattr(self._local, "read_depth", 0) and not conn.in_transaction):
            # The writer refreshed the planner's statistics, and an open connection never loads them: it keeps
            # the plans it made (#626). A new connection does. Never inside a read_snapshot, whose transaction
            # is the consistency the caller asked for; the next read after it reconnects.
            conn.close()
            self._local.conn = None
            conn = None
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            _harden(conn)
```

### Block 14 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
            # property of the database, so the writer's setting does not reach these.
            conn.execute(f"PRAGMA busy_timeout={int(self.reader_busy_timeout_ms)}")
            self._local.conn = conn
        return conn

    def _wal_bytes(self) -> int:
        """Size of the -wal sidecar, or 0 when there is none (`:memory:`, or rollback mode)."""
        if self.path == ":memory:":
```

```python
            # property of the database, so the writer's setting does not reach these.
            conn.execute(f"PRAGMA busy_timeout={int(self.reader_busy_timeout_ms)}")
            self._local.conn = conn
            self._local.stats_epoch = self._stats_epoch
        return conn

    def _refresh_statistics(self) -> None:
        """Keep the query planner's statistics current, as SQLite recommends (#626).

        Without statistics SQLite plans from the shape of the indexes alone, and two reads chose one that narrows
        only to cluster_id: the Groups list's binding count read every binding on the cluster once per group
        (2.5 s at 999 groups and 50,000 bindings), and group detail's first-seen read the cluster's whole
        membership history once per member (5.5 s at 300,000 events). With statistics they use
        rbac_binding_by_group and membership_event_by_user: 20 ms and 1 ms, the same rows. The call is
        lang_analyze.html §2.1's for a long-lived connection, `PRAGMA optimize=0x10002`: it analyses only the
        tables with no statistics or whose size has changed by about an order of magnitude, so it is nothing
        when nothing changed (measured 0.0 ms) and runs at open and after every write cycle (maintain).

        Its debug form lists what it would analyse; an empty list is the common case and changes nothing, so the
        readers are only told to reconnect when the statistics actually moved. Under the write lock and never
        inside a transaction: ANALYZE writes sqlite_stat1 and commits.
        Optional refresh failures are logged and retried after the next poll, keeping the old statistics.
        """
        with self._lock:
            if self._conn.in_transaction:
                return
            try:
                pending = [row[0] for row in self._conn.execute("PRAGMA optimize(0x10003)").fetchall()]
                if not pending:
                    return
                self._conn.execute("PRAGMA optimize=0x10002")
                self._conn.commit()
            except sqlite3.Error:
                if self._conn.in_transaction:
                    self._conn.rollback()
                log.warning("query planner statistics refresh failed; will retry after a poll", exc_info=True)
                return
            self._stats_epoch += 1
        log.info("query planner statistics refreshed: %s", "; ".join(pending))

    def _wal_bytes(self) -> int:
        """Size of the -wal sidecar, or 0 when there is none (`:memory:`, or rollback mode)."""
        if self.path == ":memory:":
```

### Block 15 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
        return int(self._rows(sql, params)[0]["n"])

    def maintain(self) -> None:
        """Periodic upkeep after a write cycle. For SQLite, a WAL checkpoint.

        Returns nothing. It briefly returned a dict describing the checkpoint, which the
        only caller discarded — a contract that implied a signal it did not deliver. The
```

```python
        return int(self._rows(sql, params)[0]["n"])

    def maintain(self) -> None:
        """Periodic upkeep after a write cycle. For SQLite, a WAL checkpoint, then the planner's statistics
        (#626, _refresh_statistics), which cost nothing unless a table's size changed by an order of magnitude.

        Returns nothing. It briefly returned a dict describing the checkpoint, which the
        only caller discarded — a contract that implied a signal it did not deliver. The
```

### Block 16 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
        through health() where a scrape can read it.
        """
        self._checkpoint()

    def health(self) -> StorageHealth:
        """Engine-reported operational facts, namespaced under the engine that produced them.
```

```python
        through health() where a scrape can read it.
        """
        self._checkpoint()
        self._refresh_statistics()

    def health(self) -> StorageHealth:
        """Engine-reported operational facts, namespaced under the engine that produced them.
```

### Block 17 — `local-development/gsd/store.py`

<!-- block: local-development/gsd/store.py | edit -->

```python
                f"SELECT {columns} FROM binding_event WHERE {where} ORDER BY id DESC LIMIT ?",
                [*scope, limit],
            )
        # Two index-served halves under UNION ALL, not one OR: this store never runs ANALYZE, and
        # without statistics SQLite plans the OR as a walk of the cluster's rows plus a sort —
        # measured 306 ms at 300k rows against 1.8 ms for the union, the same rows back (OB1,
        # review 2 of #177). The groups ride as ONE bound JSON parameter: a viewer in more groups
```

```python
                f"SELECT {columns} FROM binding_event WHERE {where} ORDER BY id DESC LIMIT ?",
                [*scope, limit],
            )
        # Two index-served halves under UNION ALL, not one OR: written when this store never ran ANALYZE (it
        # keeps statistics since #626, but they appear only once a table has rows), and
        # without statistics SQLite plans the OR as a walk of the cluster's rows plus a sort —
        # measured 306 ms at 300k rows against 1.8 ms for the union, the same rows back (OB1,
        # review 2 of #177). The groups ride as ONE bound JSON parameter: a viewer in more groups
```

### Block 18 — `local-development/pyproject.toml`

<!-- block: local-development/pyproject.toml | edit -->

```toml
# reconcile_error alert's `detail` is replaced there. A self-tier consumer parsing either field
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.6.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
# FLOORS ARE A SECURITY CONTROL, not just a compatibility statement. These were set once
```

```toml
# reconcile_error alert's `detail` is replaced there. A self-tier consumer parsing either field
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.7.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
# FLOORS ARE A SECURITY CONTROL, not just a compatibility statement. These were set once
```

### Block 19 — `local-development/tests/test_specs_index.py`

<!-- block: local-development/tests/test_specs_index.py | edit -->

```python
    assert all(rows[fid]["release"] == "—" for fid in post), "a post-programme row carries `—`"
    # the count catches an index row dropped silently; it moves by one per new spec (E1 #229, S1 #230, T1 #239, G1 #239, E2 #303, G2 #255, E4 #391, G3 #503, E5 #304, E3 #302, E6 #306, E7 #300, E8 #410, E9 #425, G4 #420, W1 #426, E10 #533, H1 #542, E11 #532, F1 #270, F2 #106, F3 #108, F4 #109, F5 #140, F6 #392, F7 #592, P1 #598)
    # a design's STEP carries the design's id and a letter (S4a, #283): the same slot, not a fifth design
    assert len(rows) == 60, f"expected sixty index rows, including D3 (#311), S4e (#432), D4 (#316), D5 (#244), D6 (#465), S4f (#481), G1 (#239), E2 (#303), G2 (#255), E4 (#391), G3 (#503), E5 (#304), E3 (#302), E6 (#306), E7 (#300), E8 (#410), E9 (#425), G4 (#420), W1 (#426), E10 (#533), H1 (#542), E11 (#532), A4 (#534), F1 (#270), F2 (#106), F3 (#108), F4 (#109), F5 (#140), F6 (#392), F7 (#592) and P1 (#598); matched {sorted(rows)}"
    return rows


```

```python
    assert all(rows[fid]["release"] == "—" for fid in post), "a post-programme row carries `—`"
    # the count catches an index row dropped silently; it moves by one per new spec (E1 #229, S1 #230, T1 #239, G1 #239, E2 #303, G2 #255, E4 #391, G3 #503, E5 #304, E3 #302, E6 #306, E7 #300, E8 #410, E9 #425, G4 #420, W1 #426, E10 #533, H1 #542, E11 #532, F1 #270, F2 #106, F3 #108, F4 #109, F5 #140, F6 #392, F7 #592, P1 #598)
    # a design's STEP carries the design's id and a letter (S4a, #283): the same slot, not a fifth design
    assert len(rows) == 61, f"expected sixty-one index rows, including D3 (#311), S4e (#432), D4 (#316), D5 (#244), D6 (#465), S4f (#481), G1 (#239), E2 (#303), G2 (#255), E4 (#391), G3 (#503), E5 (#304), E3 (#302), E6 (#306), E7 (#300), E8 (#410), E9 (#425), G4 (#420), W1 (#426), E10 (#533), H1 (#542), E11 (#532), A4 (#534), F1 (#270), F2 (#106), F3 (#108), F4 (#109), F5 (#140), F6 (#392), F7 (#592) P1 (#598) and Q1 (#626); matched {sorted(rows)}"
    return rows


```

### Block 20 — `local-development/tests/test_specs_index.py`

<!-- block: local-development/tests/test_specs_index.py | edit -->

```python
    assert ROWS["F6"]["issue"] == "392", ("F6 is #392", ROWS["F6"]["issue"])
    # F7 (#592, with #607 and #593) is above every issue in the rows it follows, so it rises with them: no exclusion.
    # P1 (#598) is above F7's #592, so it rises with the rows before it: no exclusion either.
    issues = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid not in ("D5", "G1", "E2", "G2", "E4", "G3", "E5", "E3", "E6", "E7", "E8", "E9", "G4", "W1", "E10", "F1", "F2", "F3", "F4", "F5", "F6")]
    assert issues == sorted(issues), issues
    programme = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if not fid.startswith("S") and fid != "G1"]
```

```python
    assert ROWS["F6"]["issue"] == "392", ("F6 is #392", ROWS["F6"]["issue"])
    # F7 (#592, with #607 and #593) is above every issue in the rows it follows, so it rises with them: no exclusion.
    # P1 (#598) is above F7's #592, so it rises with the rows before it: no exclusion either.
    # Q1 (#626) is above P1's #598, so it rises too: no exclusion.
    issues = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid not in ("D5", "G1", "E2", "G2", "E4", "G3", "E5", "E3", "E6", "E7", "E8", "E9", "G4", "W1", "E10", "F1", "F2", "F3", "F4", "F5", "F6")]
    assert issues == sorted(issues), issues
    programme = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if not fid.startswith("S") and fid != "G1"]
```

### Block 21 — `local-development/tests/test_store_statistics.py` (new)

<!-- block: local-development/tests/test_store_statistics.py | create -->

```python
"""The store keeps the query planner's statistics current, and its readers use them (#626).

Without statistics SQLite plans from the shape of the indexes alone. Two reads chose an index that narrows only to
cluster_id and so read a cluster's whole table once per row: the Groups list's binding count (2.5 s at 999 groups
and 50,000 bindings) and group detail's first-seen (5.5 s at 300,000 membership events). The store now runs
SQLite's recommended `PRAGMA optimize` at open and after every write cycle (`maintain`), and a reader opened before
a refresh reconnects, because an open connection never loads new statistics. The bound is the operator's: a
cluster never has 1,000 groups.

The plans are read from the SQL the store itself runs (the reader's trace callback gives it with its values bound),
so a test cannot pass on a copy of a query that has drifted from the real one.
"""

from __future__ import annotations

import pathlib
import random
import shutil
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from gsd.store import Store

GROUPS, BINDINGS, EVENTS, MEMBERS = 999, 50_000, 100_000, 25
BIG = "g0000"


@pytest.fixture(scope="module")
def seeded(tmp_path_factory) -> pathlib.Path:
    """A database at the operator's bound, written straight to the tables, with no statistics in it."""
    path = tmp_path_factory.mktemp("stats") / "seed.db"
    store = Store(str(path))
    store.upsert_cluster("c", "https://x", True)
    conn = store._conn
    names = [f"g{i:04d}" for i in range(GROUPS)]
    rnd = random.Random(626)
    conn.executemany("INSERT INTO group_state(cluster_id, name, member_count, sync_provider, observed_at) "
                     "VALUES ('c', ?, 25, 'gs_ldap', '2026-10-05T00:00:00Z')", [(n,) for n in names])
    conn.executemany("INSERT INTO rbac_group_binding(cluster_id, binding_kind, binding_namespace, binding_name, role_kind, "
                     "role_name, subject_kind, group_name, observed_at) VALUES ('c', 'RoleBinding', ?, ?, 'ClusterRole', "
                     "'view', 'Group', ?, '2026-10-05T00:00:00Z')",
                     [(f"ns{j % 500}", f"b{j}", rnd.choice(names)) for j in range(BINDINGS)])
    conn.executemany("INSERT INTO group_member(cluster_id, group_name, user_name, first_seen_at, last_seen_at) "
                     "VALUES ('c', ?, ?, 't', 't')", [(BIG, f"u{i}") for i in range(MEMBERS)])
    conn.executemany("INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at) VALUES ('c', ?, ?, ?, ?)",
                     [(rnd.choice(names), f"u{rnd.randrange(5000)}", rnd.choice(("added", "removed")),
                       f"2026-{1 + j % 9:02d}-{1 + j % 28:02d}T00:00:00Z") for j in range(EVENTS)])
    conn.commit()
    conn.execute("DROP TABLE IF EXISTS sqlite_stat1")
    conn.commit()
    store.close()
    return path


@pytest.fixture()
def db(seeded, tmp_path) -> pathlib.Path:
    path = tmp_path / "gsd.db"
    shutil.copy(seeded, path)
    return path


def _traced(store: Store, read) -> list[str]:
    """The SQL a store read runs on this thread's reader, values bound."""
    seen: list[str] = []
    conn = store._reader()
    conn.set_trace_callback(seen.append)
    try:
        read()
    finally:
        conn.set_trace_callback(None)
    return seen


def _plan(store: Store, sql: str) -> str:
    return " | ".join(row[3] for row in store._reader().execute("EXPLAIN QUERY PLAN " + sql))


def _timed(read) -> float:
    start = time.perf_counter()
    read()
    return time.perf_counter() - start


def test_open_gathers_statistics_and_both_reads_use_their_index(db):
    store = Store(str(db))
    try:
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        (members_sql,) = _traced(store, lambda: store.group_members("c", BIG))
        assert "SEARCH b USING INDEX rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql)
        assert "SEARCH e USING INDEX membership_event_by_user (cluster_id=? AND user_name=?)" in _plan(store, members_sql)
    finally:
        store.close()


def test_both_reads_stay_inside_a_budget_at_the_operator_s_bound(db):
    """Measured without statistics on this data: about 2.2 s and 0.6 s. With them: about 15 ms and 0.5 ms."""
    store = Store(str(db))
    try:
        assert len(store.groups("c", "all")) == GROUPS
        assert len(store.group_members("c", BIG)) == MEMBERS
        assert _timed(lambda: store.groups("c", "all")) < 0.5
        assert _timed(lambda: store.group_members("c", BIG)) < 0.2
    finally:
        store.close()


def test_the_rows_are_the_same_with_and_without_statistics(db, tmp_path):
    bare = tmp_path / "bare.db"
    shutil.copy(db, bare)
    raw = sqlite3.connect(bare)
    raw.row_factory = sqlite3.Row
    store = Store(str(db))
    try:
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        (members_sql,) = _traced(store, lambda: store.group_members("c", BIG))
        assert not raw.execute("SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat1'").fetchone()[0]
        for sql in (groups_sql, members_sql):
            assert sorted(map(tuple, raw.execute(sql))) == sorted(map(tuple, store._reader().execute(sql)))
    finally:
        raw.close()
        store.close()


def test_a_reader_opened_before_a_refresh_reconnects_and_uses_the_new_statistics(tmp_path, seeded):
    """An open connection keeps the plans it made: the planner loads statistics when a connection reads the
    schema, and ANALYZE does not change it (lang_analyze.html §3; measured). The reader reconnects instead."""
    path = tmp_path / "gsd.db"
    store = Store(str(path))   # a fresh install: empty tables, so open gathers nothing
    try:
        store.upsert_cluster("c", "https://x", True)
        before = store._reader()
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        epoch = store._stats_epoch
        src = sqlite3.connect(seeded)
        for table in ("group_state", "rbac_group_binding"):
            store._conn.execute(f"DELETE FROM {table}")
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            store._conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        store._conn.commit()
        src.close()
        assert "rbac_binding_by_group" not in _plan(store, groups_sql)
        store.maintain()
        assert store._stats_epoch == epoch + 1
        after = store._reader()
        assert after is not before
        assert "rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql)
    finally:
        store.close()


def test_nothing_changed_means_no_refresh_and_no_reconnect(db):
    store = Store(str(db))
    try:
        reader, epoch = store._reader(), store._stats_epoch
        store.maintain()
        store.maintain()
        assert store._stats_epoch == epoch
        assert store._reader() is reader
    finally:
        store.close()


def test_a_reader_inside_a_read_snapshot_is_not_replaced_until_the_snapshot_ends(db):
    store = Store(str(db))
    try:
        reader = store._reader()
        with store.read_snapshot():
            store._stats_epoch += 1          # a refresh lands while this thread holds a snapshot
            assert store._reader() is reader
            store.groups("c", "all")
        assert store._reader() is not reader
    finally:
        store.close()


def test_a_reader_on_another_thread_reconnects_too(db):
    """Readers are per thread; the epoch is read by each, so an API worker's reader reconnects as the poller's does."""
    store = Store(str(db))
    try:
        replaced: list[bool] = []

        def worker():
            first = store._reader()
            store._stats_epoch += 1
            replaced.append(store._reader() is not first)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert replaced == [True]
    finally:
        store.close()


def test_reader_recovers_after_reconnect_failure(tmp_path):
    store = Store(str(tmp_path / "reader.db"))
    try:
        store.upsert_cluster("c", "https://x", True)
        store.clusters()
        store._stats_epoch += 1
        with patch("gsd.store.sqlite3.connect", side_effect=sqlite3.OperationalError(
                "unable to open database file")):
            try:
                store.clusters()
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("injected connect failure did not happen")
        assert [row["id"] for row in store.clusters()] == ["c"]
    finally:
        store.close()


def test_refresh_failure_is_optional_at_open_and_maintain(tmp_path):
    import gsd.store as module

    path = str(tmp_path / "optional.db")
    store = Store(path)
    store.upsert_cluster("c", "https://x", True)
    store.close()
    harden = module._harden

    def deny_analysis(action, arg1, arg2, database, source):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ANALYZE else sqlite3.SQLITE_OK

    def harden_and_deny(conn):
        harden(conn)
        conn.set_authorizer(deny_analysis)

    with patch.object(module, "_harden", harden_and_deny):
        store = Store(path)
    try:
        epoch = store._stats_epoch
        store.maintain()
        assert store._stats_epoch == epoch
        assert not store._conn.in_transaction
        assert [row["id"] for row in store.clusters()] == ["c"]
        store._conn.set_authorizer(None)
        store.maintain()
        assert store._stats_epoch == epoch + 1
        assert not store._conn.in_transaction
    finally:
        store.close()


def test_a_refresh_of_existing_statistics_reaches_a_reader_opened_before_it(tmp_path):
    """The case the reconnect is for. The first refresh creates sqlite_stat1, a schema change, so an open connection
    reloads on its next query without help; a later refresh only rewrites rows of sqlite_stat1, the schema stays the
    same, and an open connection keeps the statistics it loaded (lang_analyze.html §3). Statistics gathered on one
    group make the binding count read the cluster's covering index; growth of 250 times re-arms optimize, and only a
    reader that reconnects plans with the new ones."""
    store = Store(str(tmp_path / "gsd.db"))
    try:
        store.upsert_cluster("c", "https://x", True)

        def add(groups: list[str], first: int, count: int) -> None:
            store._conn.executemany("INSERT INTO group_state(cluster_id, name, member_count, sync_provider, observed_at) "
                                    "VALUES ('c', ?, 1, 'gs_ldap', 't')", [(g,) for g in groups])
            store._conn.executemany("INSERT INTO rbac_group_binding(cluster_id, binding_kind, binding_namespace, "
                                    "binding_name, role_kind, role_name, subject_kind, group_name, observed_at) VALUES "
                                    "('c', 'RoleBinding', ?, ?, 'ClusterRole', 'view', 'Group', ?, 't')",
                                    [(f"ns{j % 50}", f"b{j}", groups[j % len(groups)]) for j in range(first, first + count)])
            store._conn.commit()

        add([BIG], 0, 200)
        store.maintain()                                   # the first statistics: sqlite_stat1 is created
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        version = store._reader().execute("PRAGMA schema_version").fetchone()[0]
        assert "rbac_binding_by_group" not in _plan(store, groups_sql)      # one group: the covering index wins
        epoch = store._stats_epoch
        add([f"g{i:04d}" for i in range(1, GROUPS)], 200, BINDINGS)
        store.maintain()                                   # a re-analysis: rows of sqlite_stat1 only
        assert store._stats_epoch == epoch + 1
        assert store._reader().execute("PRAGMA schema_version").fetchone()[0] == version
        # A new statement text, so neither connection can answer from Python's statement cache.
        assert "rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql + " ")
    finally:
        store.close()


def test_the_refresh_never_commits_an_enclosing_transaction(db):
    """The writer is shared, so a refresh inside a transaction leaves the boundary to its owner: run inside a poll
    snapshot that then fails, it must not have committed the snapshot's rows."""
    store = Store(str(db))
    try:
        with pytest.raises(RuntimeError, match="the cycle failed"):
            with store.poll_snapshot():
                store.replace_namespaces("c", [{"name": f"ns{i}"} for i in range(500)], "t")   # a table to analyse
                store.maintain()
                raise RuntimeError("the cycle failed")
        assert not store._rows("SELECT name FROM cluster_namespace WHERE cluster_id = 'c'")
    finally:
        store.close()


def _refuse_analyze(action, *rest):
    """An authorizer that refuses ANALYZE: a deterministic stand-in for any error inside the refresh."""
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ANALYZE else sqlite3.SQLITE_OK


def test_a_failed_refresh_leaves_a_successful_poll_ok_and_its_backup_written(tmp_path, monkeypatch):
    """maintain() is the first call of the poll's upkeep tail (Poller._after_poll): raised from it, a refresh error
    recorded a successful poll `unreachable` / `internal poller error` and skipped the cycle's backup on b65ce09d."""
    from gsd import poller as poller_module
    from gsd.config import ClusterConfig, Settings

    store = Store(str(tmp_path / "gsd.db"))
    cluster = ClusterConfig("c1", "https://api.c1.example:6443", token_env="GSD_TEST_TOKEN")
    store.upsert_cluster("c1", cluster.api_url, True)
    store._conn.set_authorizer(_refuse_analyze)
    poller = poller_module.Poller(
        store=store,
        settings=Settings(clusters=[cluster], db_path=store.path,
                          backup_dir=str(tmp_path / "backup"), backup_keep=3),
        elector=None,
    )

    def a_successful_poll(st, cl, *args, **kwargs):    # it leaves a table for the refresh to analyse
        st.replace_namespaces(cl.name, [{"name": f"ns{i}"} for i in range(500)], "2026-10-05T00:00:00Z")
        st.record_poll(cl.name, "ok", None)
        return "ok"

    monkeypatch.setenv("GSD_TEST_TOKEN", "token")
    monkeypatch.setattr(poller_module, "poll_once", a_successful_poll)
    monkeypatch.setattr(poller_module, "capture_once", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller_module, "refresh_bindings", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller, "_discover_doors", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller, "_wait_cycle", lambda *args, **kwargs: poller._stop.set())
    try:
        poller._run_cluster(cluster)
        assert next(r for r in store.clusters() if r["id"] == "c1")["status"] == "ok"
        assert list((tmp_path / "backup").glob("gsd-*.db"))
    finally:
        store.close()
```

## Orchestrator's notes

1. The research, this spec and its code were written by the orchestrator, at the operator's instruction (§1). The
   reviews follow the adversarial-review skill: Codex Astra and Cursor Grok first, then OB2 for a review and
   enhancements; each reviewer writes a findings file, and the orchestrator decides and applies from those files.
2. **Round 1.** Cursor was out of usage, so OB3 took Cursor Grok's seat (the operator's rule of 2026-09-30) beside Codex
   Astra. Both found that an error inside the refresh stopped `Store()` opening and, from `maintain()`, recorded a
   successful poll `unreachable` and skipped its backup: accepted, the refresh never raises. Codex Astra also found
   that a failed reconnect left a closed connection cached on the thread (accepted) and that §2.7 overstated
   `schema_version` (accepted on the wording; its test pinning the spec's prose was declined: a test on wording guards
   no behaviour). OB3 also found two test gaps, measured by mutation (a re-analysis reaching an open reader; the
   refresh never committing an enclosing transaction), a test that a refused `ANALYZE` leaves a real poll `ok` with
   its backup written, and that the debug form is itself a write (§2.6): all accepted. Its duplicate failure test and
   its equivalent `_refresh_statistics` body were declined. Codex Astra implemented every accepted item as a patch.
3. **Round 2, OB2 (review and enhancements).** It confirmed the code, both rounds' fixes, and a six-thread stress run
   (no error across repeated refreshes), and found that §7 had not yet been regenerated after the review commits
   (it was regenerated last, as planned). Accepted: printing the runner's SQLite version in CI's Install step (E1),
   §2.5's account of the `0x10000` bit (E3) and a fuller §6 lab check (E4). Decided by CI's measured SQLite version: a
   module gate on these tests below 3.46.0 (E2). Later: refresh counters in the storage seam's `health()` (E5), since
   no alert would consume them yet. Declined, with OB2's reasons: a log line per reconnect, removing the no-op commit,
   widening the time budgets, rate-limiting the failure warning.
4. **CI SQLite and the image proof.** PR #630's Install step measured SQLite 3.45.1 on GitHub's ubuntu-24.04
   runner, image 20260927.320.1. Five statistics tests failed there: the plans stayed unchanged and the budget
   test took 3.2–3.7 s. The all-tables optimize bit requires SQLite 3.46.0; the image ships 3.53.4. Decision:
   adapt OB2's E2 to skip the entire statistics test module below 3.46.0, locally and in CI, with the version and
   requirement in the reason. Do not raise in CI. The behaviour matters on the SQLite that ships, so
   `local-development/image-proof.py` now proves the store's refresh and traced Groups plan on the finished
   image's own interpreter as its runtime user, before cleaning every file from /data. It refuses SQLite below
   3.46.0 and fails the build if statistics or the required plan are missing. CI's image job and every publish
   build run that proof; `local-development/tests/test_store_statistics.py` also executes the proof directly.
   This keeps runner-version differences from failing CI while still checking the real library in every image.
