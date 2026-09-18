# Review — PR #177, binding_event: the bindings' membership history, with a first-observation baseline

Adversarial second-opinion pass, 2026-09-17, on the ten-claim brief for #177 (`docs/DESIGN_binding_events.md`
applied). Codex (gpt-5.6-sol, xhigh) had a shell; Cursor (Grok 4.6 high fast, ask mode, shell blocked) traced
from source. Cursor's first launch on Fable-xhigh hit the account's monthly limit; its Grok run twice died
with a 0-byte output when launched from the scratch directory with `nohup … &`, and a one-line probe from
the repository root came back clean — the review ran from the root as a managed background task. Codex's
`out.txt` was 0 bytes: its "leave the scratch directory empty" step deleted the `tee` target it shared with
the launcher; the transcript was recovered byte-identical (25,265 bytes) from the harness's own capture of
the same process. Every verdict was re-checked here before a decision.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 role-only compare; a role change is one removed + one added | CONFIRMED — two-row probe `{'added': 1, 'removed': 1} [('removed','alice','view'), ('added','alice','admin')]` | CONFIRMED | — |
| C2 baseline only on the first observation; wipe-then-recreate is not baseline | CONFIRMED — `('added',1), ('removed',0), ('added',0)`; "retention can erase that evidence and reopen the baseline; covered by the C4 fix" | CONFIRMED | semantics kept; the mechanism changed under C4 |
| C3 diff and replace in one `_write()` transaction | CONFIRMED — fault injection at the INSERT: `post_rollback current= 0 events= 0` | CONFIRMED | — |
| C4 `sync_members` baseline read before mutation; empty first poll leaves no marker | **REFUTED** — `first_empty= 0 event_rows= 0 second_nonempty= 1 second_baseline= 1`: "the second poll is not the cluster's first observation and should be a real addition; the empty first poll must consume the baseline" | CONFIRMED (accepted the edge as debt) | **accepted; fixed** — `observation_state`, migration 14 |
| C5 `viewer_groups=[]` → viewer's own User rows only; `viewer=None` → everything | CONFIRMED — three SQL traces quoted | CONFIRMED | — |
| C6 self branch orders require_viewer → user_groups → binding_events; `@consistent`; no viewer refused | CONFIRMED — AST probe `strict_order= True … consistent= True`; loopback `no_header_status= 403` | CONFIRMED | — |
| C7 metric is the cartesian product per enabled cluster; no name can become a label | CONFIRMED — `forbidden_cluster_present= False labels= ['change','cluster','subject_kind']` | CONFIRMED | — |
| C8 migration 13 on v12 and on fresh; only the one tolerated ALTER error | CONFIRMED — fresh `version= 13 binding_cols= 13`; v12 upgrade `preserved_value= 0` | CONFIRMED | — (now 14; the v12 fixture test pins it) |
| C9 prune through `_prune_history` with its guards; three tables reported | CONFIRMED — `nonpositive= 0 invalid= "not a history table" bounded= 2 keys= [3 tables]` | CONFIRMED | — |
| C10 `signals=None` keyword; `_note_binding_changes` never raises | CONFIRMED — both None cases probed; the no-`signals` caller test passed | CONFIRMED | — |

## C4 — refuted, fixed

**Finding (Codex).** The first cut inferred "first observation" from the rows: `baseline = 1` when the
cluster had no current rows and no events of that kind. A first poll that returns nothing writes no rows,
so the *second* poll satisfies the same test and its rows — real additions — are flagged as the baseline.
Retention that empties a stream reopens the baseline the same way. Codex's fix: a per-(cluster, stream)
marker table consumed once, independent of rows; two tests that fail before and pass after
(`BEFORE membership_test=FAIL baseline= 1 … AFTER … PASS baseline= 0`).

**Re-check.** Reproduced with the new tests against the committed head before applying anything:
`test_an_empty_first_poll_consumes_the_baseline` and `test_an_empty_first_binding_refresh_consumes_the_baseline`
fail on `1f55cb1` with `baseline == 1`, pass on the fix. The retention case
(`test_retention_does_not_reopen_the_baseline`) — prune to zero rows, then a new row — fails before, passes after.
Traced the helper: it runs on the caller's transaction connection inside `_write()`, so a rolled-back refresh
does not spend the marker (C3's fault injection applies unchanged).

**Decision.** Accepted on the fact and on the snippet, with one deviation: Codex rewrote migration 13; the
running CRC store already carries `user_version 13` (measured below), and `_migrate` never re-runs an applied
target — so the table and its backfill are **migration 14**. The backfill seeds a marker for every cluster
with rows in `group_member`, `membership_event`, `rbac_group_binding`, `user_binding` or `binding_event`, so an
upgrade writes no baseline rows; a cluster with nothing anywhere is, honestly, unobserved. Recorded in the
design's notes; `docs/CHANGELOG.md` and `local-development/API.md` state the marker rule.

## Not asked, and what happened to it

- **Codex: the self-scope group list exceeds SQLite's variable limit.** `binding_events` built one placeholder
  per viewer group; `self_scope_before= OperationalError too many SQL variables` for a viewer in more groups than
  `SQLITE_LIMIT_VARIABLE_NUMBER`. Fix: `subject_name IN (SELECT value FROM json_each(?))` with the list bound as
  one JSON parameter; test forces the limit to 16 with `setlimit` and reads through 21 groups. Re-checked: the
  test raises on the old query and returns `[('Group','g-mine')]` on the new. **Applied.** (Cursor had judged the
  >32766 case on the write side only; Codex measured that side too — `replace= {'added': 32767}` passes.)
- Cursor: `_HISTORY_TABLES` and `Poller._prune_history` still said "two tables" — **applied**, both comments.
- Cursor: four preservation-only tests — is_platform-only produces 0 events; wipe-then-recreate is not
  baseline; a true v12 `membership_event` (no `baseline` column) opened by `Store`; `binding_event_by_time`
  in the retention-indexes test — **applied**, all four (`tests/test_binding_events.py::TestDiff`,
  `::TestUpgrade`, `tests/test_history_retention.py`).
- Cursor: ClusterRoleBinding `''` vs RoleBinding of the same name; same subject in two namespaces — both in
  the key; **no change**, the existing namespace-filter test stores both. Codex's transcript does not address
  either prompt; Cursor's source trace stands alone on these two.
- Cursor's accepted debt (empty first observation; retention reopening the baseline) — **superseded** by the
  C4 fix; the debt note in the design was replaced by the marker rule.

## Re-check — the live cluster, not the tests (before the fixes)

The branch was built, pushed and deployed to CRC (`0.24.0-1f55cb14ad`; the first attempt exited 125 because
the client-certificate kubeconfig has no `oc whoami -t` — a token session fixed it, recorded in memory).
Measured on the running pod:

- `PRAGMA user_version` **13**; `binding_event` has its 13 columns; `membership_event.baseline` present.
- Zero `binding_event` rows after the upgrade with **407 / 95** current rows — correct: an upgraded store
  is not a first observation (C2, C8).
- `gsd_binding_changes_total` pre-seeded: eight series, two clusters × {added, removed} × {Group, User},
  every label bounded (C7).
- The pod loopback without `X-Forwarded-User` answered **403** — the self tier fails closed (C6).
- A real change: two RoleBindings created in a throw-away namespace at `02:52:06Z`. The `02:57:18Z`
  refresh recorded **three** `added` rows, `baseline = 0` — the Group binding, the User binding, and the
  namespace's own `system:image-pullers` binding the platform created with the namespace. The metric moved
  to `added/Group 2.0`, `added/User 1.0`; the poller logged the same two lines (C1, C3, C10).
- Through the route as kubeadmin: `scope: all`, `count: 3`, `baseline_rows: 0`,
  `retention.retained_since = 2026-09-18T02:57:18Z`; `?namespace=binding-event-check` returns the three (C5).
- The namespace was then deleted. The `03:03:18Z` refresh recorded the **three** matching `removed`
  rows, `baseline = 0`; the counters read `added` Group 2.0 / User 1.0 and `removed` Group 2.0 / User 1.0
  — the full cycle, symmetric, with nothing invented on either side (C1, C2, C7).

## Re-validation after the fixes — the 13→14 upgrade on CRC

Commit `c59fddd` built, pushed and rolled out as `0.24.0-c59fddd970` (`release-crc exit=0`, token session). Measured on
the new pod:

- The log line `schema migration 14 applied: observation_state …` at `23:42:09 -0400`; `PRAGMA user_version` **14**.
- `observation_state` holds **nine** rows — `crc-local`, `mock` and `prod-east` (the lingering removed cluster of #96,
  which still holds rows) × `membership`, `binding:Group`, `binding:User`: the backfill seeded every cluster with rows.
- **Zero** `baseline = 1` rows in either table after the upgrade, with **407 / 95 / 184** current rows (group bindings,
  user bindings, group members): an upgraded store is not a first observation.
- The six real events from the first pass are intact (`added` Group 2 / User 1, `removed` Group 2 / User 1, all
  `baseline = 0`); `gsd_binding_changes_total` is pre-seeded again — eight series, counters at 0 after the restart, as
  in-memory counters are.
- Through the route as kubeadmin: `scope: all`, `count: 6`, `baseline_rows: 0`,
  `retention.retained_since = 2026-09-18T02:57:18Z` — the `json_each` clause serves the wide tier unchanged; the pod
  loopback without a viewer header still answers 403.

The second pass on this head (Codex, Grok, and OB1 — Fable 5.1 through the Agent tool, standing in for Cursor's Fable
while its usage limit is exhausted) follows.

## Second pass — the fixed head `c59fddd`

Eight claims (S1–S8) on the marker, migration 14, the `json_each` clause and the streams' independence, plus the
next real use. Cursor's Fable tier was still at its monthly limit (measured: `ActionRequiredError: You've hit your
usage limit`), so the third reviewer was **OB1 — Fable 5.1 through the Agent tool**, the same brief, read-only.

| Claim | Codex | Grok | OB1 — Fable 5.1, Claude Code Agent | Decision |
|---|---|---|---|---|
| S1 marker consumed on the caller's transaction; a failed INSERT rolls it back | CONFIRMED — fault injection after the marker INSERT: `observation_state` `[]` after rollback, next refresh `baseline=[1]` | CONFIRMED — `BEFORE INSERT … RAISE(ABORT)` triggers on both tables and inside `poll_snapshot`: marker `[]` after every rollback, next refresh `baseline 1` | CONFIRMED (source: `_first_observation` 1638–1650, `_write` 1050–1067, `_tx` 1194–1198) | pending | — |
| S2 migration 14 seeds every cluster with rows; the next refresh writes `baseline = 0` | CONFIRMED — a v13 file built with `HEAD~1`, opened by HEAD: markers `missing=[] extra=[]`, six fixture cases all `baseline 0` | CONFIRMED — fixture from `1f55cb1`'s `store.py` (`has observation_state: False`) opened by HEAD: five markers, every next change `baseline 0`; a Group stream never seen on v13 stays baseline 1 | CONFIRMED (the five `INSERT OR IGNORE … SELECT DISTINCT`, 874–886) | pending | — |
| S3 no rows anywhere → no marker → the next non-empty refresh is baseline | **REFUTED** — the premise is false: a successful poll writes `groupsync_presence` (+ `poll_outcome` ok) in the same transaction even with zero groups; `next_events=[('never',1),('polled-group',1),('polled-none',1)]` — right for never-polled, wrong for polled-empty | premise REFUTED the same way — `v13 tables holding a row for 'nil': ['poll_outcome']`; for the binding streams nothing proves it, so "unobserved" is the honest call there | CONFIRMED, "right call" (polled-empty is indistinguishable from never-polled in those tables; seeding from `poll_outcome` would mark streams never observed — binding refresh does not `record_poll`) | pending | — |
| S4 fresh DB ends at the latest version; one tolerated DDL error; no gap or duplicate target | CONFIRMED — `targets=[1..14]`, only `duplicate column name` on a fresh replay | CONFIRMED — 13 tolerated errors on the replay, all that message | CONFIRMED | pending | — |
| S5 `sync_members` consumes on `{}`; `existing` read first; two empty polls consume once | CONFIRMED — `[0,0]`, one marker after each, later add `('added',0)` | CONFIRMED — `_first_observation` calls `(…,1), (…,0)` | CONFIRMED | pending | — |
| S6 `json_each(?)` exact match, `[]`/`None` unchanged, `import json` at module top; (d) index use | (a)(b)(c) CONFIRMED — `g'quote`, `g\\slash`, `grüp-雪`, `literal%name` matched exactly, `literalXname` excluded; **(d) REFUTED** — `EXPLAIN QUERY PLAN`: `SEARCH … USING INDEX binding_event_by_time (cluster_id=?)` then `SCAN json_each`; the OR defeats `binding_event_by_subject` | (a)(b)(c) CONFIRMED — 13 hostile names incl. `g' OR 1=1 --`, 5001 groups under `setlimit 16`; **(d) REFUTED and measured** — no `ANALYZE` anywhere, so the OR walks the cluster and sorts: **306.82 ms** at 300k rows vs **1.80 ms** for `UNION ALL`, identical rows | CONFIRMED (a)(b)(c); (d) PLAUSIBLE without `EXPLAIN` | pending | — |
| S7 streams independent; two refreshes write events only on change | CONFIRMED — a real `refresh_bindings`: `2→2` unchanged, `2→4` on change | CONFIRMED — each replace in its own `_tx`, each stream its own marker | CONFIRMED | pending | — |
| S8 nothing removes a marker; #96 retires, never deletes; no new consequence | CONFIRMED — no `DELETE` names the table; `retire_absent_clusters` is `UPDATE … enabled=0` | CONFIRMED — the one future consequence: a "forget cluster" that clears the per-table rows must clear the marker too | CONFIRMED — the only new footgun is a future forget-cluster that omits the table | pending | — |

**Grok, volunteered — V1, accepted, applied as migration 15.** Migration 14 seeds `membership` from `group_member`
and `membership_event` but not from `group_state`. A v13 cluster whose groups were all polled with zero members has
`group_state` rows and nothing in the other two (the v13 empty `sync_members` wrote nothing), so after 13→14 its first
join reads as a first observation — C4 across the cut. Re-check: `poller.py:272` (`replace_group_state`) and `:339`
(`sync_members`) run in the same cycle before `record_poll(OK)` at `:347`, so `group_state` rows do prove a membership
observation. Grok's own note applied: 14 has already run on CRC, so the seed is a **new target 15**, not a rewrite.
Test `test_groups_polled_without_members_are_still_an_observation` — **fails before** (`assert [] == ['membership']`),
passes after. Grok's fixture (a hand-built v13 `group_state` table) was replaced by rewinding a real store to
`user_version 14` with the marker deleted, which exercises the same migration on the real schema.

**Grok, debt named — applied.** The stale `sync_members` comment ("only a cluster with neither members nor events is at
baseline") now states the marker rule; `_Recording` in `tests/test_history_retention.py` wraps `prune_binding_events`
and the order test asserts all three prunes (the poller's order: membership, sync, binding); both prune tests are
parametrised over the third table. **Accepted as is:** polled-empty ≡ never-polled (S3).

**Grok, not asked.** Backup and report snapshots are `VACUUM INTO` of the whole file — no table list to miss;
`Snapshot` inventories `sqlite_master` and never reads the marker; a v13 backup opened by HEAD migrates; a v14 one
does not re-seed. `_HISTORY_TABLES` is a closed tuple — prune and `history_retained_since` cannot touch the marker.

**Codex, S3 refuted — accepted; migration 15 extended.** Re-check: `replace_groupsync_state` writes the one-row
`groupsync_presence` inside the same `poll_snapshot()` as `replace_group_state`, `sync_members` and
`record_poll(OK)` (`poller.py:259–347`), so a presence row is durable proof the membership stream was observed —
even when the cluster returned no Group at all, which is the shape Grok's `group_state` seed cannot see. Migration 15
now seeds `membership` from both; Codex's test (a real store polled empty through `poll_snapshot`, rewound to
`user_version 14` with the marker deleted) fails before the seed (`baseline == 1`) and passes after. The stream is
still honestly unobserved for a cluster with nothing in any of those tables.

**Codex, S6(d) refuted — accepted on the fact, snippet rejected.** The plan is as Codex measured: the `OR` between
the User and Group halves keeps SQLite on `binding_event_by_time (cluster_id=?)` and scans the cluster's rows. What
that costs: one pass over one cluster's events within the retention window — rows that are appended only when a
binding changes, which the first pass measured at six for a whole namespace's lifecycle. Codex's `UNION ALL` rewrite
makes both halves hit `binding_event_by_subject` at the price of a 20-line function becoming 50 with two parameter
lists, for a read nobody has measured slow. Review fixes stay simple; the finding is recorded here and the rewrite
is the first thing to apply if a self-tier read is ever measured slow. `binding_event_by_subject` stays — #174's
per-user and per-group histories are its readers.

**OB1, S3 and V1 — accepted; the seed moved to every open.** OB1 reached Codex's refutation independently
(`poll_outcome` is the one v13 table holding a row for a polled-empty cluster) and then measured the gap no
numbered migration can close: `1f55cb1`, the build first deployed to the lab, has no marker; run against a
v14 store (a rollback) it writes rows for a new cluster with no marker, and `user_version` stays 14 so
migration 14 never re-runs — that cluster's next real additions would be flagged baseline. The drafted
migration 15 was dropped; `_OBSERVATION_SEEDS` (the five sources, plus `group_state`, `groupsync_presence`
and `poll_outcome status='ok'` for membership) runs inside migration 14 and again from `Store.__init__` at
every open. Idempotent and index-led; a no-op in normal operation. OB1's two tests are in
`tests/test_migrations.py` (an OK poll marks, a failed poll does not; rows written without a marker are
marked at the next open) beside Codex's and Grok's, all rewound to `user_version 14`.

**OB1, S6(d) — accepted, and the earlier "rewrite rejected" decision reversed.** Codex's refutation named the
plan; OB1 measured it: 306.82 ms per self-tier read at 300k rows against 1.80 ms for two index-served halves,
the same rows back, and no `ANALYZE` anywhere in the store to let the planner find the OR-optimisation on
its own. The landing page (#158) will run this read for every viewer on every load. OB1's version of the
`UNION ALL` form is applied — the User half is always index-served and the Group half is added only when
the viewer has groups — with its plan test (`EXPLAIN QUERY PLAN` must show `binding_event_by_subject`
twice and `binding_event_by_time` never). What changed my mind is the number; the reason for the earlier
rejection ("nobody has measured it slow") no longer holds.

**OB1, V2 — accepted.** The `_harden` docstring said the store uses no SQL JSON functions — false since
`a7b155c`, and this change added a fourth `json_each`; it now states what is used and why the CVE's
malformed-document path stays unreachable (the JSON is serialised here from Python lists of strings).
