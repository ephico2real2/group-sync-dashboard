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
