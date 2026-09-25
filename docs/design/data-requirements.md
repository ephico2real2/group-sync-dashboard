# Data requirements for the redesigned pages

**Status: the analysis of 2026-09-17, kept as the record of what was planned; not maintained.** The ✅ / 📋 / ❌
marks below are as of that date. The mocks it analyses are all **Implemented** (`docs/design/README.md`), and
the issues it names say what shipped. Read a mark here as "was a gap on 2026-09-17", never as current state.

What each mock in this folder renders, where that number comes from today, and what has to be
built before the page can be real. Read against `local-development/gsd/` (API, store, metrics,
`state.py`) and the issues filed on 2026-09-17. Nothing here is inferred from the mocks alone —
every source was located in code or measured on CRC.

**Legend** — ✅ exists (endpoint, table or metric named) · 🔧 derived client-side from existing
data · 📋 planned, issue named · ❌ gap: nothing collects or exposes it yet.

## Inventory of what exists

- **API** (`api.py`): `/api/clusters`, `/clusters/{c}/groupsyncs`, `…/groupsyncs/{n}/events`,
  `…/groups`, `…/groups/{n}`, `…/users`, `…/users/{n}`, `…/logins`, `…/cluster-access`,
  `…/bindings/findings`, `…/user-bindings`, `…/operator-configs` (admin), `…/membership-changes`,
  `/api/alerts`, `/api/whoami`, `/api/dashboard/activity`, `/api/dashboard/reports`,
  `/api/report/ticket`; report service: `list_runs` (filter `report`, limit/offset), `namespace_count`.
- **Store** (27 tables): append-only `sync_event`, `membership_event`, `login_event`, `report_run`;
  replaced-per-poll `group_state`, `rbac_group_binding`, `user_binding`, `operator_config_state`;
  `ocp_user` (with `has_identity`, `identity_created_at`), `group_member`, `cluster_namespace`,
  `cluster_namespace_label`, `dashboard_user_activity`, `kpi_daily` — **not yet** (📋 #156).
- **Derivations** (`state.py`, per request, never stored): `compute_state` → `ok/late/overdue/unknown`,
  `next_expected` (croniter, anchored on now), `reconcile_error_is_current` (`error_at > success_at`),
  `compute_alerts` (16 kinds).
- **Metrics**: 29 dashboard families + 10 report-service families (list in `metrics.py` /
  `reporting/metrics.py`). Public by decision; **no name may appear in any label**.

## Cluster Overview — `cluster-overview-mock.html` (#157 split: page unchanged, relayout)

| shown | source | status |
|---|---|---|
| per-cluster tile: id, api_url, status, last_poll, error, groupsync_count, operator present, group_count, empty, unattributed, dangling+unresolved, operator_configs{total,failing}, oldest_last_sync, visibility | `/api/clusters` (payload measured 2026-09-17) | ✅ |
| alerts: cluster, kind, subject, detail, severity, silenced, silenced_by, count | `/api/alerts` | ✅ |
| alert paging (8/page, worst first) | client-side over the full list | 🔧 |
| GroupSync CRs: name, ns, state, schedule, group_count, last_sync_at, next_expected, error_is_current | `/clusters/{c}/groupsyncs` — keys verified | ✅ |
| four-state vocabulary + consequence copy | `state.py`; copy is static | ✅ |
| Policy operator: kind, name, error_at, success_at, "failing" = ordering | `/operator-configs` (admin tier) | ✅ |
| density tiers by fleet size; cluster tile → scoped view | position `cluster` already exists | 🔧 |

**Nothing new to collect.** The page is a relayout of data the app already serves.

## Access Drill-down — `drilldown-mock.html` (#167, #153)

| shown | source | status |
|---|---|---|
| groups list: name, member_count, sync_provider | `/groups` | ✅ |
| groups list: **grants per group** column | `rbac_group_binding` grouped by `group_name` — not in the list payload today | ❌ small: add `binding_count` to `/groups` rows |
| users list: name, full name, provider, group count, first login (identity) | `/users` (`identity_created_at` now populated, `rbac.identities` on) | ✅ |
| group detail: members (+their group count, first login), grants (role, scope, binding), DN, sync time, owner | `/groups/{n}` (live page renders all of it) | ✅ |
| user detail: memberships (+owner, +grants), access direct + via group, namespaces reached, cluster-wide roles, first login | `/users/{n}` | ✅ |
| **namespaces list**: name, mnemonic, app-environment, oud-group, via-groups count, direct-grants count | tables exist (`cluster_namespace`, `cluster_namespace_label`, `rbac_group_binding.binding_namespace`, `user_binding.binding_namespace`); **no endpoint** — only `store.namespaces_source()` | ❌ **the biggest gap**: `/clusters/{c}/namespaces` (📋 #167 names the page, not yet the endpoint) |
| namespace detail: labels, who reaches it via which group, direct grants, siblings by mnemonic | same tables | ❌ same endpoint, `/namespaces/{n}` |
| namespace **history** (#167 lists it) | `rbac_group_binding` is replaced every poll; no per-namespace event table | ❌ **needs a decision**: snapshot binding changes (like `membership_event`) or drop "history" from #167 |
| cross-kind search, multi-word AND, breadcrumbs, back/forward | client-side; live model already | 🔧 |

## Your Access — `landing-access-mock.html` (#158)

| shown | source | status |
|---|---|---|
| your groups on this cluster; total across clusters ("also on …") | `group_member` per cluster, union across clusters | ✅ scalar queries to write |
| cluster-wide roles via group; namespaces reachable via group | `rbac_group_binding` (role_name, binding_namespace, group_name) joined to membership | ✅ |
| "covered by admin" | name-based rule over stock roles (admin ⊇ edit ⊇ view); rules are **not** evaluated | 🔧 **specify the rule explicitly** — it is a derivation, not data |
| direct grant, platform-namespace badge | `user_binding` (`is_platform`) | ✅ |
| what changed (30d), flapping, bulk-add, "history starts …" | `membership_event` + `history_retained_since` | ✅ |
| stale-cluster flag | `/api/clusters` last_poll | ✅ |
| sign-in activity (#158 D) | `login_event` self-scoped | ✅ not yet in the mock |
| export my access (#158 E) | report service | 📋 #158 |
| who else is in my groups (#158 G) | membership of others — names | ⏸ **needs the operator's ruling** |

## KPI page — `overview-kpi-mock.html` (#156 → #157)

| shown | source | status |
|---|---|---|
| memory used / limit, both components | cgroup v2 `memory.current`/`memory.max` — **measured today** (dashboard 19.3 % of 512Mi, report 13.8 % of 768Mi) | 📋 #156 collector + `gsd_process_memory_bytes`, `_limit_bytes` |
| CPU rate vs limit | `cpu.stat usage_usec` sampled on a monotonic clock, `cpu.max` | 📋 #156 |
| throttled % of periods, throttled seconds | `cpu.stat nr_throttled / nr_periods / throttled_usec` — **measured: dashboard 1.10 %, over the 1 % amber mark** | 📋 #156 |
| artefacts disk (11.2 Mi · 418 files) | `gsd_report_artifacts_disk_bytes` ✅ exists; file count via `artifacts.py disk_bytes()` | ✅ / 📋 |
| **data volume own bytes** (18.6 Mi) and **node disk % (84 %)** | #156 plans `statvfs` on the mount → gives the *filesystem* used/total (on hostpath that *is* the node disk) — the app's **own bytes** need a `du`-style walk | 📋 #156, **specify both**: fs-level % *and* own bytes |
| pills healthy / watch + stated thresholds | configuration | 📋 #157 |
| access posture: groups, empty, unattributed, to-review, bindings (+built-in), clusters up, leader | `/api/clusters`, `/bindings/findings`, `gsd_*_total`, `gsd_cluster_up`, `gsd_leader` | ✅ |
| trends: membership churn (joiners/leavers 30d) | `membership_event` + 📋 `gsd_membership_changes_total{cluster,change}` | ✅ series / 📋 metric |
| trends: login outcomes (% success, attempts, providers) | `login_event` + 📋 `gsd_login_attempts_total{cluster,outcome,provider}` | ✅ / 📋 |
| trends: sync cadence (3/4 ok, 1 overdue, oldest sync) | `groupsync_state` + `state.py`; `gsd_groupsync_state` | ✅ |
| trends: report volume, "timeline starts …" | `report_run` + `gsd_report_runs_finished_total` | ✅ |
| sparklines for counts **without** history (groups, bindings) | `kpi_daily` rollup by the leader | 📋 #156 |
| `history_retained_since` on every trend | `Store.history_retained_since` | ✅ |
| in-app JSON for all of the above, tier-gated, privacy class enforced | `gsd/kpi/` second renderer | 📋 #156 |
| Grafana deep link when `grafana.url` set; Observe link always | chart values | 📋 #157 / #161 / #162 |
| `gsd_grafana_up` | new nameless gauge | 📋 #160 comment |

**Numbers in the mock that must be re-measured at build time, not carried over:** the trend
figures (`14 joiners · 4 leavers`, `62 attempts · 4 providers`, `96.2 %`) were captured in an earlier
session; the system-status figures were measured on 2026-09-17 and are dated in the page.

## Reporting status — `reporting-status-mock.html` (#149)

| shown | source | status |
|---|---|---|
| service on/off, formats, 11 reports enabled | config + `/api/dashboard/reports.enabled` | ✅ partial |
| run window open/closes-in, refused-by-window count | config (`window`) + `gsd_report_runs_outside_window_total` | ❌ **no endpoint exposes the window config to the page** |
| retention 2-tier text | config (PR #154 env) | ❌ same: not served to the page |
| in flight: running / queued | `report_run.status` + `gsd_report_queue_length` | ✅ |
| schedules: name, report, cadence, retention, enabled/paused, last success, next | `values.schedules` + `gsd_report_schedule_last_success_timestamp{schedule}` + croniter; paused = the CronJob's `spec.suspend` | ❌ **needs `/api/dashboard/reports/schedules`** (config-derived; #149 says kube-state-metrics for Grafana — the page needs the app to serve it) |
| history: requested, report, cluster, by, status, sha256, artifacts; 12/page | `report_run` via `list_runs` (limit/offset) | ✅ |
| history filters marked "api" (status, cluster) server-side | `list_runs` filters only `report` today | ❌ small: add `status`, `cluster`, `origin` filters |

## Reports page + forms — `reports-page-mock.html`, `report-form-mock.html` (#149, #143)

| shown | source | status |
|---|---|---|
| catalogue: kind, name, description | reporting catalogue (live) | ✅ |
| discovered namespaces by mnemonic / app-environment / **oud-group** | `cluster_namespace_label` via `namespaceSelectorDimensions` | ✅ / oud-group 📋 #149 |
| discovered groups, users, providers, roles | `/groups`, `/users`, `ocp_user.providers`, `rbac_group_binding.role_name` | ✅ |
| type-ahead, all / clear, `N of M` | client-side | 🔧 |
| namespace preview names (Matched namespaces) | `namespace_count` + names endpoint (#143) | ✅ |
| reviewer "from your login" | `/api/whoami` | ✅ |
| subject scope by **group** on login-activity / dormant / users | ParamSpecs accept `user` text today, not a group | ❌ small: ParamSpec additions per report (#149) |
| bolder names, gradient, click-opens-in-view | presentation | 🔧 (live catalogue still at weight 400) |

## Tab redesign — `tab-redesign-mock.html` (#153)

Presentation only; every number is on the contract and served today. **No data change.**

## Kyverno — no mock yet (#165)

Everything is new: `PolicyReport`/`ClusterPolicyReport` snapshots, kube-apiserver audit-log
denials, `kyverno_breaker_drops`, runtime API discovery. Kyverno **is installed on CRC** (320 Mi,
`kyverno-cel-tutorial` namespace present), so the data-shape discovery the issue asks for can start.

## The gaps, consolidated

| # | gap | owner | size |
|---|---|---|---|
| 1 | **`/clusters/{c}/namespaces` + `/namespaces/{n}`** — the tables exist, no endpoint | #167 | medium |
| 2 | namespace **history** — no per-namespace event table; decide snapshot vs drop | #167 | decision |
| 3 | cgroup collectors, `kpi_daily`, KPI JSON renderer, new nameless metrics | #156 | the module |
| 4 | own-bytes *and* fs-level disk, both components — specify both in #156 | #156 | small |
| 5 | reporting status endpoint: window, retention, schedules with paused/last/next | #149 | medium |
| 6 | `list_runs` server-side filters: status, cluster, origin | #149 | small |
| 7 | `binding_count` on `/groups` rows | #167 / #153 | small |
| 8 | ParamSpec: group-scoped subjects on three reports | #149 | small |
| 9 | "covered by admin" rule stated explicitly | #158 | spec |
| 10 | "who else is in my groups" | #158 G | **ruling** |

## Prometheus exposure — what the pages need that `/metrics` will carry

Public, nameless, bounded labels (per #156's privacy class): `gsd_process_*{component}`,
`gsd_artifacts_disk_*`, `gsd_membership_changes_total{cluster,change}`,
`gsd_login_attempts_total{cluster,outcome,provider}`, `gsd_grafana_up`. Everything per-person or
per-group (the landing page, the drill-downs, the members lists) stays on the authenticated,
tier-gated JSON surface and **never** reaches `/metrics` — enforced by test, per #156.
