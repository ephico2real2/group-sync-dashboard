# Docs content audit, batch 5 of 6: the reference architecture

Phase 2 of the documents pass, fifth batch. `docs/guides/reference-architecture.md` (1731 lines) was read
in full, and every checkable claim — prose, tables and the ten mermaid diagrams, node by node and edge by
edge — was measured against main at 037332c9 (application 5.5.0, chart 0.70.8). The evidence comes from:

- the chart, rendered with `helm template` (Helm v4.3.0): the defaults, and one render per guard or
  derived value the page names;
- the application under `local-development/gsd/`, read at the cited symbol and, where the claim is about
  behaviour, run in place (a fresh `Store`, `provider_keys_for`);
- the workflows under `.github/workflows/`, the tests under `local-development/tests/`, and git history for
  removed files;
- the lab (CRC, namespace `group-sync-dashboard`), read-only with `oc get`: PVCs, Leases and Routes. No
  Secret was read.

Batches 1-4 already measured what the access, write, release and tag facts are; where this page repeats
one, it now says what those guides say (`DOCS_AUDIT_2026-10-05_b2_chart_reference.md`,
`DOCS_AUDIT_2026-10-05_b3_access_guides.md`, `DOCS_AUDIT_2026-10-05_b4_release_build.md`). Line numbers
are given outside backticks and are those of 037332c9.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the page now says what the evidence shows.
- **NOT MEASURED**: a historical measurement or an upstream behaviour that could not be re-measured here
  without a cluster write or another tool. It was left unchanged.
- **CODE-SUSPECT**: the page describes the intended behaviour and the code does not do it. The page was
  left unchanged and the finding is reported below.

Many of the page's citations are `file#anchor`. `tests/test_docs_citations.py` proves an anchor exists; it
cannot prove the anchor names the code the sentence is about. Twenty-five did not: they named a neighbouring
function (`membership_changes` for the Usage view's 403, `list_events` for "role rules are never
expanded", `__all__` for the reader's busy timeout). Each was traced to the symbol that holds the rationale
and repointed. Those are the "FIXED (citation)" rows below. A row whose verdict reads "CORRECT; FIXED" had a
correct claim and a wrong citation; the totals count it as fixed.

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `docs/guides/reference-architecture.md` | 259 | 80 | 19 | 1 |

## `docs/guides/reference-architecture.md`

### Preamble and §1

| claim | verdict | evidence |
|---|---|---|
| "read out of the code on `feat/operator-config-health`"; "the file and line that decides it is cited" | FIXED | the citations are names, not lines (`tests/test_docs_citations.py` forbids line numbers), and the page was last checked against main by this record. Now names the date, the versions and this record |
| GroupSync is `redhatcop.redhat.io/v1alpha1`; NamespaceConfig and GroupConfig share the group | CORRECT | `local-development/gsd/kube.py` lines 30, 88-89 |
| polls both, every RoleBinding and ClusterRoleBinding; SQLite on a PV; single-page UI and JSON API | CORRECT | `gsd/kube.py` lines 90-94; render: PVC `group-sync-dashboard-data` mounted at `/data` |
| binding views are direct bindings only, and the API says so in its payload | CORRECT | `gsd/api.py` `group_detail`, lines 1874-1876 ("DIRECT bindings only. Role rules are never fetched or expanded"); no `roles`/`clusterroles` path in `gsd/` |
| no ClusterRole write verb on a GroupSync, Group or binding at any setting | CORRECT | default render: reader ClusterRole verbs `get`/`list` only; `templates/rbac.yaml` lines 76-95; `test_chart_strategy.py` write-verb tests pass |
| "the only object the dashboard writes anywhere is its own leader-election Lease" | FIXED | default render: Role `group-sync-dashboard-leases` (`get`, `create`, `update`), ClusterRoleBinding `group-sync-dashboard-auth-delegator` to `system:auth-delegator` (SubjectAccessReviews, `gsd/kube.py` line 1379); lab: Lease `gsd-fleet-666f1ba7f2fdead0` beside `group-sync-dashboard`; Secrets with `clusterConfig.secrets.writes.enabled` (batch 2); fleet login and revoke (`gsd/fleetlogin.py`). Now lists all of them, as the root README's "What it writes" does **Found by Codex's review:** the list still lacked the oauth-proxy's TokenReviews (`templates/rbac.yaml`, `system:auth-delegator`), the secrets-mint hook's Secrets under its own ServiceAccount (`templates/secrets-mint.yaml`), and the remote logins' OAuth tokens: fleet lookup and Rejoin revoke theirs (`gsd/fleetlogin.py`), `userSelfLogin` keeps, renews and revokes the superseded one (`gsd/selflogin.py`), Rejoin asks a SelfSubjectAccessReview (`gsd/rejoin.py`). Now all named. |

### §1a The whole workflow

| claim | verdict | evidence |
|---|---|---|
| "The nine diagrams that follow" | CORRECT | ten mermaid blocks; nine after this one |
| governed path: LDAP → GroupSync → Group (sync-provider label) → NamespaceConfig/GroupConfig → RoleBinding (config-source label) | CORRECT | `gsd/kube.py` line 308 (`SYNC_PROVIDER_LABEL`); `config-source` read as `managed_source` (`gsd/kube.py` line 1876) |
| dashboard box "read-only, one replica" | FIXED | `replicaCount: 1` (`values.yaml` line 97); "read-only" is true only of what it observes (row above). Now "read-only on what it observes" |
| "Poll 60s CRs and groups, 3600s bindings" | CORRECT | `values.yaml` lines 281, 302 |
| findings f1-f3 (dangling, unmanaged, direct user grant) | CORRECT | `gsd/store.py` `_FINDING_CASE` (line 2837); `gsd/state.py` alert `direct_user_binding` (line 508) |
| f4 "operator stopped reconciling — both conditions still report True" | CORRECT | `gsd/state.py` alert `sync_stopped` (line 407); `reconcile_error_is_current` (line 113) |
| f5 "group synced empty / CR overdue / schedule unparseable" | CORRECT | `gsd/state.py` alerts `empty_group`, `overdue`, `invalid_schedule` (lines 310, 428, 393) |
| "UI — eight tabs" | FIXED | `gsd/static/index.html` lines 1222-1235 render up to fourteen (`home` … `clusters`), five of them conditional. Now "up to fourteen tabs" |
| "/api — JSON, bearer token, per cluster"; "Log — WARNING per finding UNMANAGED GRANT DISCOVERED" | CORRECT | `apiTokenAccess.enabled: true`; `gsd/poller.py` line 858 at `log.warning` |
| a2: an `unmanaged-exception` annotation takes the finding out of all three outputs | CORRECT | `_FINDING_CASE`: `b.exception IS NULL` gates `unmanaged`; the log, `/bindings/findings` and the tab read the same classification |
| step 3 "Reads only — CRs and groups every 60s, bindings every `bindingIntervalSeconds`" | CORRECT | `poll_once` and `refresh_bindings` issue only GET/list (`gsd/poller.py` lines 330-583, 645-890) |
| step 6 "The dashboard holds no write verb" | FIXED | it holds `create`/`update` on its Leases (above). Now "no write verb on any of these objects" |
| step 7 "the log says `unmanaged grant RESOLVED`" when a finding closes | FIXED | the line is emitted only for an object carrying `rbac.ocp.io/unmanaged=true` (`gsd/audit.py` `plan_audit_stamps`, the `unstamp` list; `gsd/poller.py` line 876). Now says so |
| the aggregator "hosts nothing, stores nothing" | CORRECT | §8a; `local-development/cluster-report.py` keeps no database |

### §2 Component map

| claim | verdict | evidence |
|---|---|---|
| Browser → Route (default) or Ingress → Route | CORRECT | `route.enabled: true`, `ingress.enabled: false`; render: Route `spec.subdomain: group-sync-dashboard` |
| Prometheus → **Route**, "/metrics, unauthenticated" | FIXED | the ServiceMonitor scrapes the Service endpoints (render: `port: http`, `scheme: https`, `serverName: group-sync-dashboard.group-sync-dashboard.svc`), not the Route; §8 says Prometheus dials the pod IP. The edge now ends at the proxy |
| oauth-proxy `:8443` HTTPS; app binds `127.0.0.1:8080`; `-upstream=http://127.0.0.1:8080` | CORRECT | render: `-https-address=:8443`, `--host 127.0.0.1 --port 8080`, `-upstream=http://127.0.0.1:8080` |
| Poller one thread per cluster; LeaderElector renews a Lease; ActivityRecorder buffered; Store `/data/gsd.db` + WAL; `VACUUM INTO` to `/data/backup` | CORRECT | `gsd/poller.py` line 1406 (`poll-<name>`); `gsd/leader.py` line 261; `gsd/activity.py` line 271; env `GSD_DB_PATH=/data/gsd.db`; fresh `Store`: `journal_mode` `wal`; `config.backup.dir: /data/backup` |
| "list — read-only" to the cluster; "Lease get/create/update" | CORRECT | as §1; render: Role `-leases` verbs |
| "The Lease arrow is the whole of the system's write surface" | FIXED | SubjectAccessReviews and, with writes on, Secrets (above). Now says the Lease is not the whole write surface and names the rest **Found by Codex's review:** now also names the TokenReviews, the hook's Secrets and the remote logins. |
| `gsd/config.py`, `poller.py`, `leader.py`, `storage.py`, `state.py`, `audit.py`, `activity.py`, `metrics.py`, `api.py` rows | CORRECT | each module's docstring; `gsd/state.py` imports only stdlib and `croniter`; `gsd/storage.py` `open_backend` (line 426) |
| `gsd/kube.py` "Read-only REST client" | FIXED | it POSTs one SubjectAccessReview (`ClusterClient.create_subject_access_review`, line 1349; `client.post` line 1379, the only write call in the file). Now says so **Found by Codex's review:** "the only write call in the file" is the SAR's `client.post`, but the `_send` seam carries the fleet-Lease, cluster-Secret and Rejoin SelfSubjectAccessReview writes (`gsd/fleetstate.py`, `gsd/clusterconfig/writer.py`, `gsd/rejoin.py`). The row now says "Kubernetes REST client" and names them. |
| `gsd/store.py` "The only module containing SQL or the string `sqlite3`" | FIXED | `gsd/reporting/snapshot.py` imports `sqlite3` and speaks SQL (`tests/test_storage_seam.py` line 30 allows both); the same table already calls snapshot.py "the second". Now "the dashboard's only module … `reporting/snapshot.py` is the other" |
| `gsd/loginlog.py` "Parses oauth-server log text into login attempts" | FIXED | its docstring: "This legacy parser and outcome vocabulary remain for historical-row fixtures and API/KPI consumers. The live pod-log reader is removed; auditlog.py is the only live input." Now says that |
| `gsd/logincapture.py` "Reads the oauth-server's logs" | FIXED | its docstring: "Audit login capture entry point and bounded retention"; the reader is `gsd/auditlog.py` (the oauth-server audit log). Now names both |
| `gsd/timeutil.py` "`now_iso()`, and nothing else" | CORRECT | one function, line 19 |
| `gsd/reporting/*`: own app, `snapshot.py` second SQL module, eleven reports, own pod and image, the dashboard imports only `ticket` and the prefix | CORRECT | `gsd/reporting/catalogue/` has eleven report modules; render: Deployment `-report` with `gsd.reporting.server:create_report_app`; `gsd/api.py` lines 45-46 are the only imports of `reporting` outside the package |
| `gsd/static/index.html` "The entire frontend — one file, no build step, strict CSP" | FIXED | the stylesheet is `gsd/static/app.css` (`index.html` line 28); no `Content-Security-Policy` header or meta anywhere in `gsd/` or the chart (case-insensitive grep), and the live `/healthz` response carries none. Now "one file of vanilla JS, with its stylesheet in `app.css`, no build step" |
| `state.py`/`audit.py` I/O-free, so the invariants are plain unit tests | CORRECT | neither imports an I/O module; `gsd/audit.py` docstring |

### §3 How a poll flows

| claim | verdict | evidence |
|---|---|---|
| one thread per enabled cluster, so a black-holed cluster cannot hold the others hostage | CORRECT | `gsd/poller.py` lines 7-8 and 1405-1406 |
| groups every `pollIntervalSeconds` (60s); bindings and operator-config health every `bindingIntervalSeconds` (3600s) | CORRECT | `values.yaml` lines 281, 302 (and Kyverno, line 298) |
| ~154 paged requests at 100× reference scale | CORRECT | `gsd/config.py` lines 634-642 (`Settings`) |
| diagram: a non-leader stands by and re-checks in 5s | CORRECT | `STANDBY_RECHECK_SECONDS = 5` (`gsd/poller.py` line 264), used at line 1288 |
| diagram: list groupsyncs, list groups (paged) | CORRECT | `ClusterClient.fetch`; `_list_all` follows continue tokens |
| diagram: `record_sync_event` committed first, outside the snapshot | CORRECT | `gsd/poller.py` lines 462-491 |
| diagram: inside `poll_snapshot()` — `upsert_reconcile_error`, `replace_groupsync_state`, `replace_group_state`, `record_managed_groups`, `sync_members`, `record_poll(ok)` | CORRECT | `gsd/poller.py` lines 491-579 (the login-gate group is also set there; the diagram does not claim to be exhaustive) |
| diagram: `maintain()` then `backup()`, poll thread only | CORRECT | `Poller._after_poll`, lines 1104-1105 |
| diagram: the binding refresh drawn outside the leader branch | FIXED | `_run_cluster` `continue`s on a non-leader (line 1289) before the binding refresh (line 1363), so only the leader refreshes. The block now sits inside the leader branch (`opt`) |
| diagram: binding refresh lists RB/CRB and the operator configs, replaces three tables, and `log` mode classifies with no cluster call | CORRECT | `refresh_bindings`, lines 668-879 |
| "the whole cycle is one transaction"; 11,598 torn reads of 19,208; `record_poll` last | CORRECT | `Store.poll_snapshot` docstring (line 1514); `gsd/poller.py` lines 482-579 |
| "It used to be nine" | NOT MEASURED | historical; `Store.poll_snapshot` and `Store._write` say nine, the comment in `poll_once` says seven (reported below) |
| `record_sync_event` outside, `INSERT OR IGNORE`, cited to `Store._write` | FIXED (citation) | the reasoning is `Store.poll_snapshot`'s docstring; `_write` is the join mechanism. Repointed |
| `membership_event` inside, self-heals, cited to `Store._write` | FIXED (citation) | same docstring. Repointed |
| the self-heal error bar is `values.yaml#pollIntervalSeconds` | CORRECT | `values.yaml` lines 269-273 |
| a binding-refresh failure does not mark the cluster unreachable, cited to `STANDBY_RECHECK_SECONDS` | FIXED (citation) | the rationale is `refresh_bindings`' docstring (line 660); the constant is the standby tick. Repointed |
| a 200 without `items` is refused; 60 groups wiped, 120 false events | CORRECT; NOT MEASURED (numbers) | `ClusterClient._list_all`, lines 675-688; the numbers are the comment's historical measurement |
| the sync-provider label is `<groupsync-name>_<provider-name>`; declared names are reconstructed and intersected with observation | CORRECT | `provider_keys_for`, lines 297-299 |
| with no declared provider names, prefix matching "awarding a label to the longest matching CR name" | CODE-SUSPECT | finding 1 below. Page unchanged |
| same-name CRs in two namespaces are detected and logged | CORRECT | `ambiguous_attribution` (line 306), logged at lines 366-372 |

### §4 How a request flows

| claim | verdict | evidence |
|---|---|---|
| diagram: "/healthz, /readyz, /metrics pass through unauthenticated" | FIXED | `oauthProxy.skipAuthRegex: ^/(healthz|readyz|metrics|signed-out|static/(app\.css|favicon\.svg))$` (`values.yaml`). The note now lists all of them |
| diagram: bearer on `/api` only with `apiTokenAccess.enabled`; TokenReview + SAR on `list clusterrolebindings` | CORRECT | render: `-openshift-delegate-urls={"/api":{"resource":"clusterrolebindings",…,"verb":"list"}}` |
| diagram: delegate-urls applies only to bearer tokens and client certs | NOT MEASURED | upstream oauth-proxy behaviour; not re-read here (batch 3 relied on the same statement) |
| diagram: usage recorded only with `X-Gsd-Interaction` | CORRECT | `record_dashboard_use`, `gsd/api.py` line 955 |
| diagram: tier cached; else groups fetched fresh and a SAR with `spec.groups`; any failure → self, not cached | CORRECT | `gsd/kube.py` `TierResolver` docstring and `tier_for` (lines 1411-1560) |
| diagram: administrator view for a self reader → 403 named refusal | CORRECT | `require_admin_tier` (line 817) |
| diagram: `@consistent` then `count_direct_user_bindings`, `direct_user_bindings`, `user_bindings_by_namespace`, `platform_user_binding_count`; JSON with `scope`, `viewer` | CORRECT | `direct_user_bindings` handler, lines 2677-2713 |
| `@consistent` only on multi-call handlers; 60.38% → 3.00% | CORRECT | `consistent` in `build_app` (line 966); `Store.read_snapshot` docstring |
| "a snapshot holds a WAL read-mark", cited to `Store.poll_snapshot` | FIXED (citation) | that reasoning is `Store.read_snapshot`'s docstring (line 1557). Repointed |
| `tests/test_read_snapshot_scope.py` enforces the synchronous rule | CORRECT | the file exists and passes |
| `collect()` gathers inside a snapshot, then yields | CORRECT | `DashboardCollector.collect` docstring (line 300) |
| "The page polls itself every 30s" | FIXED | `const POLL_INTERVAL_MS = 60000` (`index.html` line 8872, "60s, not 30s"). Now 60s, with the citation |
| one real session read 722 | NOT MEASURED | historical; `gsd/activity.py` comment |
| the browser stamps `X-Gsd-Interaction` once per user refresh, cited to `EMAIL_HEADER` | FIXED (citation) | the comment is on `INTERACTION_HEADER` (`gsd/activity.py` line 66). Repointed |
| "The three unauthenticated paths are excluded explicitly" | FIXED | `SKIP_AUTH_PATHS` has four (line 92) plus every path under `/static/` (`identity_is_trustworthy`, line 102). Count dropped, citation repointed |
| "One self-contained file … strict CSP"; "Eight tabs" | FIXED | as §2; fourteen tab calls. Now "Up to fourteen tabs …; the root `README.md` describes each. Seven of them:" |
| the seven rows' reads (Overview, Groups, Users, Access granted, RBAC policy, Usage) | CORRECT | `refresh()` in `index.html` lines 8238-8399; `myAccessFetch` reads `.../users/{viewer}` (line 8149) |
| Namespace audit reads `/user-bindings` | FIXED | it also reads `.../namespaces` or `.../namespaces/{name}` (lines 8337-8342). Added, with what they show |
| `/` carries `Cache-Control: no-cache, must-revalidate` | CORRECT | `index` → `named_page`, `gsd/api.py` line 3489 |
| "the whole app is this one file" | FIXED | the code is; the stylesheet is not. Now "the whole app's code" |
| the Namespace audit filter is server-side, cited to `index.html#every-grant` | FIXED (citation) | `every-grant` is a DOM id; the reasoning is the comment at line 8332. Repointed to its text |

### §5 Data model

| claim | verdict | evidence |
|---|---|---|
| "Fifteen tables" | FIXED | a fresh `Store` (`PYTHONPATH=. python`, `sqlite_master`): 35 tables, `user_version` 20. Now "Thirty-five tables …; this section is about fifteen of them" **Found by Codex's review:** `sqlite_master` holds 36 table rows; the 36th is SQLite's own `sqlite_sequence`. Now "Thirty-five application tables (thirty-six rows in `sqlite_master` …)". |
| "`sync_event` and `membership_event` … Everything else is a cache the next poll rebuilds" | FIXED | `binding_event` and `kyverno_result_event` are diff histories (retention windows, `Poller._prune_history` lines 1037-1050) and `managed_group_seen` is append-only (this page, below); none is rebuilt by a poll. Now names them and limits the cache statement to the current-state tables |
| the ER diagram's fourteen tables and their relations | CORRECT | every name is in the fresh database; `groupsync_provider` and `reconcile_error` key on the CR |
| "`dashboard_user_activity` is the fifteenth and belongs to no cluster" | FIXED | of 35, only `cluster` and `dashboard_user_activity` have no `cluster_id` (same run; batch 1 measured the same). "the fifteenth" dropped |
| `managed_group_seen` append-only; `groupsync_provider` a table; `group_member` keeps `first_seen_at`; `operator_config_presence` stores absence; `dashboard_user_activity` aggregated, ~110k rows | CORRECT | `gsd/store.py` `SCHEMA` comments (lines 131-147, 385-387); `fetch_operator_configs` returns `None` vs `[]` (line 1278) |
| CR state, `next_expected`, `interval_seconds`, `error_is_current` and alerts are computed at request time | CORRECT | `gsd/state.py` `compute_state`, `next_expected`, `compute_alerts` |
| `ReconcileError` is sticky; ordering decides | CORRECT | `reconcile_error_is_current` (lines 113-126) |
| grace: 3-14s after the cron minute; `scheduleGraceSeconds` above `pollIntervalSeconds` | CORRECT | `values.yaml` lines 283-289 (120 > 60) |
| the cliff is reconstructed from `membership_event`; silence from the annotation or values; a silenced cliff is still served | CORRECT | `Store.group_count_changes` (line 2447); `cliff_silence` returns `"annotation"`/`"values"`; `gsd/state.py` alert `group_count_cliff_silenced` |
| one SQL `CASE` decides five tiers in order dangling, built_in, unresolved, unmanaged, ok | CORRECT | `_FINDING_CASE` (line 2837); a second `built_in` arm for non-Group platform subjects sits before `unmanaged`, as the table's `built_in` row says |
| the `built_in` row (system: groups, platform ServiceAccounts, the two controller bindings, `system:` users, kubeadmin) | CORRECT | `_FINDING_CASE` comments; `is_platform` from `_binding_is_platform` (`gsd/poller.py` line 614) |
| 110 of 149, 119 findings of which 9 matter, 92% | NOT MEASURED | historical; `Store.binding_findings` docstring |
| the Group `unmanaged` gate is "over Group-subject bindings other than this chart's own (#354)" | FIXED | `PROVENANCE_ONLY_CONFIG_SOURCES = (CHART_CONFIG_SOURCE, OPERATOR_CHART_CONFIG_SOURCE)` (`gsd/kube.py` line 323, #503). Now names both charts |
| SA and User subjects: no gate, the label or the annotation silences them | CORRECT | `_FINDING_CASE` `unmanaged` arm |
| the three "group does not exist" tiers, first match wins | CORRECT | `_FINDING_CASE` arms 1-3 |
| only `dangling` alerts (the quoted comment) | CORRECT | `gsd/api.py` lines 2960-2962, verbatim |
| the nine `klt-*` bindings on the reference cluster | NOT MEASURED | historical reference-cluster data |
| the bounded-reads table: limits and maxima, and what each reports | CORRECT | `/users` 1000/10000 (line 1886), `/user-bindings` 200/5000 + `offset` (line 2622), events 200/2000 (line 1736), `membership-changes` 100/1000 (line 2791), activity 500/5000 (line 3207); each reports the fields listed (some report more) |
| `/user-bindings` pages the flat list and not the rollup; ordering before the limit | CORRECT | `direct_user_bindings` docstring (lines 2652-2659); `Store.user_bindings_by_namespace` |

### §6 Concurrency and storage

| claim | verdict | evidence |
|---|---|---|
| SQLite is single-writer; WAL needs one host | CORRECT | `Store.__init__` comment (lines 1451-1458) |
| "four Helm `fail` guards" exist because of it | FIXED | the count does not hold: `deployment.yaml` has three replica/access-mode guards (lines 2, 5, 16) and reporting adds an RWX one (`_helpers.tpl` `gsd.reportingGuards`). §8 itself says counts rot. Now "the Helm `fail` guards on replicas and access modes" |
| `storage-coupling.md` §3.4: Postgres makes it dead weight | CORRECT | `docs/design/storage-coupling.md` line 126 |
| `StorageBackend` is a `runtime_checkable` Protocol; `open_backend` the one place an engine is named; `build_app` the one place a backend is built | CORRECT | `gsd/storage.py` lines 78-79, 426; the only call is `gsd/api.py` line 345 |
| the AST check: "no SQL outside `store.py`" | FIXED | `BACKENDS = {"store.py", "reporting/snapshot.py"}` (`tests/test_storage_seam.py` line 30). Now names both |
| `test_no_module_imports_a_database_driver[api.py]` | CORRECT | the test is parametrized with `ids=p.name` |
| `maintain()` and `health()`; the `gsd_sqlite_*` names stay | CORRECT | `gsd/storage.py` lines 90, 104; `gsd/metrics.py` lines 391-415 |
| `runtime_checkable` checks method names only | CORRECT | Python's documented behaviour for `typing.runtime_checkable` |
| threads diagram: an `RLock` serialises transactions; writer `busy_timeout` 5000 ms, `synchronous` NORMAL; thread-local readers at 2000 ms | CORRECT | `Store.__init__` (lines 1424-1476); `Store._reader` (line 1667); `values.yaml` `config.sqlite.*` |
| uvicorn `--workers 1`; every handler a plain `def` | CORRECT | render: `--workers 1`; the only `async def` in `gsd/api.py` are the static-files class, `lifespan` and the middleware |
| readers never take the write lock; 0.92s; cited to `Store._tx` | FIXED (citation) | the measurement is `Store._reader`'s docstring. Repointed |
| shorter reader timeout, cited to `store.py#__all__` | FIXED (citation) | the comment is in `Store.__init__` (lines 1418-1421). Repointed |
| `:memory:` reuses the writer | CORRECT | `Store._reader` line 1660 |
| transaction depth is per thread | CORRECT | `Store.__init__` comment (lines 1426-1429); `_depth` |
| nesting `_tx()` raises; `phase-one`; eleven call sites | CORRECT | `Store._tx` docstring |
| `_write()` is the deliberate join, cited to `Store.__init__` | FIXED (citation) | `Store._write` (line 1494). Repointed |
| a leaked read snapshot fails loudly; 2,000 vs 4,000 | CORRECT | `Store.read_snapshot` (line 1586) |
| `journal_mode` read back, ERROR logged, exported as `gsd_sqlite_wal_enabled` | CORRECT | `Store.__init__` lines 1459-1468; `gsd/metrics.py` line 415 |
| PASSIVE auto-checkpoint; TRUNCATE past `walCheckpointMb` from the poll thread; busy counted, cited to `Store._reader` | FIXED (citation) | `Store._checkpoint` (line 1685); `walCheckpointMb: 8`. Repointed |
| the report pod reads a `VACUUM INTO` copy under `/data/report`, `.tmp` then rename, `immutable=1&mode=ro`, outside the retention gate | CORRECT | `Store.snapshot` (lines 1784-1795); `gsd/config.py` line 950; `gsd/reporting/snapshot.py` line 10; render: the report pod mounts `/data` read-only |
| `CREATE TABLE IF NOT EXISTS` no-ops on an existing database; `user_version` is the cursor; replay tolerates `duplicate column name` | CORRECT | `gsd/store.py` lines 686-690, 1319-1331 |
| `config.backup` on by default; `VACUUM INTO`, not a copy, cited to `Store._checkpoint` | CORRECT; FIXED (citation) | `values.yaml` `config.backup.enabled: true`; the torn-file reasoning is `Store.backup`'s docstring (lines 1735-1738). Repointed |
| backups from the poll thread only; `keep` bounds the directory | CORRECT | `Poller._maybe_backup` docstring (line 980) |
| the offsite CronJob mounts the claim read-only, ships the newest `gsd-*.db` by name, hashes, `immutable=1` `integrity_check`, `.sha256`, prunes; a second pass for the pre-upgrade copy; `PutObject`-only credential; two rules on `kube_cronjob_status_last_successful_time` | CORRECT | `charts/group-sync-dashboard/scripts/offsite_backup.py` lines 9-15, 49, 108-119, 187; render: `readOnly: true`; `values.yaml` line 1138; `templates/monitoring.yaml` lines 311-334 |
| retention: `membershipEventsDays` 0, `syncEventsDays` 730; after the backup, never before one succeeds; 5,000 rows per table per cycle; id-IN-subselect; `(cluster_id, observed_at)` indexes | CORRECT | `values.yaml` lines 384-385; `Poller._prune_history` (lines 1016-1100); `HISTORY_PRUNE_BATCH = 5000`; `Store.prune_membership_events` docstring; `SCHEMA` lines 67, 215 |
| "until application 0.13.0" | CORRECT | `docs/CHANGELOG.md` line 1246, under "Application 0.13.0" |
| "four history responses carry `retention`" | FIXED | eight responses call `history_retention(` (`gsd/api.py` lines 1768, 1855, 1873, 2014, 2538, 2601, 2825, 2876). Now eight |

### §7.1 The ServiceAccount is read-only

| claim | verdict | evidence |
|---|---|---|
| the reader ClusterRole grants `get` and `list` and nothing else | CORRECT | default render: every rule's verbs are `get`, `list` or `list` alone |
| the table's seven rows and their switches | CORRECT | `templates/rbac.yaml` lines 13-113; `rbac.users: true`, `rbac.identities: false`, `rbac.namespaces: false`, `rbac.bindings: true` |
| the table is the whole role | FIXED | two rendered rules were missing: `config.openshift.io/oauths`, `resourceNames: [cluster]`, `get`, when `clusterAccess.discoverFromOAuth` (lines 61-75), and the Kyverno report and policy kinds, `list`, when `kyverno.enabled` (lines 114-131). Both on by default; rows added |
| the `-leases` Role and RoleBinding: `get`, `create`, `update`, rendered with election or a fleet account, only with `rbac.create`; `<fullname>-leases` | CORRECT | render; `templates/rbac.yaml` line 146; `TestTheLeaseGrantIsDescribedWhereItLives` passes |
| the code reads and writes Leases in its own namespace only | CORRECT | `gsd/leader.py` `own_namespace` (line 36), `LeaderElector._namespace` (line 83) |
| login capture: `get nodes/proxy`, optional `resourceNames`, `list nodes` only when unpinned, on by default, audit log at default verbosity, no `pods/log` | CORRECT | `templates/login-capture-rbac.yaml` lines 10-35; render; `loginCapture.source: audit-log` |
| the auth-loglevel Jobs and patch grant are removed; the README has the migration note | CORRECT | no such template; chart README "OAuth Debug migration" (line 644) |
| "No `watch`" | FIXED | the default render's `-cluster-secrets` Role grants `get`, `list`, `watch` on ConfigMaps and Secrets in the release namespace (`templates/cluster-secrets-rbac.yaml` lines 21-27); the code sends no watch (no `watch` request in `gsd/`). Now "No `watch` in the reader ClusterRole", with the Role named **Found by Codex's review:** the sentence after it, "the only thing the ServiceAccount can change", now says the reviews persist nothing, the hook uses its own ServiceAccount and remote logins use the configured account. |
| with the defaults, the Leases are the only thing the ServiceAccount can change | CORRECT | default render: the only write verbs bound to it are the Leases' and `system:auth-delegator`'s `create` on reviews, which persist nothing; Secret writes need `writes.enabled` (default false) |
| zero `patch` at every `unmanagedAudit.mode` | CORRECT | `test_chart_strategy.py` write-verb tests over the modes pass |
| `users` is the Users tab's source; manual accounts; `fullName`; membership from Groups | CORRECT | `templates/rbac.yaml` lines 30-44; `poll_once` lines 380-447 |
| `rbac.users=false` → 403 → `None` → `mark_users_unavailable`; `/users` says `source: forbidden` | CORRECT | `gsd/poller.py` lines 396-405; `/users` docstring (line 1914) |
| 62 User objects, 61 with an identity; 11 members, 8 with a User | NOT MEASURED | historical (2026-09-03) |
| `roles`/`clusterroles` deliberately not requested; `basic-user` already grants them | CORRECT | `templates/rbac.yaml` lines 99-102; the reader role has no such rule |
| the operator-config grant kept for a quiet 404 | CORRECT | `templates/rbac.yaml` lines 16-22 |

### §7.2 Authentication

| claim | verdict | evidence |
|---|---|---|
| the three proxy-on effects: `127.0.0.1`, the Service targets the proxy, `oauthProxyEnabled` in the ConfigMap | CORRECT | render: `--host 127.0.0.1`; Service `targetPort: oauth-proxy`; with the proxy off `targetPort: http` and `oauthProxyEnabled: false` |
| the app must not infer authentication from `X-Forwarded-User` | CORRECT | `gsd/config.py` line 709 (`Settings`) |
| `/api/dashboard/activity` 403 with the flag false, cited to `membership_changes` | CORRECT; FIXED (citation) | `dashboard_activity` lines 3239-3243. Repointed |
| `/api/whoami` `authenticated: false`, cited to `direct_user_bindings` | CORRECT; FIXED (citation) | `whoami` line 3131. Repointed |
| activity recording off with the flag false, and the mismatch logged | CORRECT | `gsd/api.py` lines 387 and 392 |
| `oauthProxy.sar` requires a permission | CORRECT | `values.yaml` `oauthProxy.sar: ""` |
| the earlier wrong sentence; 229 bindings read with `list groups` | NOT MEASURED | historical |
| the API review demands `list clusterrolebindings` | CORRECT | render (§4 row) |
| per-cluster `visibility`/`identity`, `remote-sar`, `self-only`, `hidden`, inherit | CORRECT | `CLUSTER_VISIBILITIES` (`gsd/config.py` line 50), `Settings.cluster_policy` (line 1001) |
| "Three paths bypass the proxy" | FIXED | the regex (above) also passes `/signed-out`, `/static/app.css` and `/static/favicon.svg`. Now names them |
| `/metrics` emits no group or user name; the active-users gauge was removed | CORRECT | `gsd/metrics.py` line 8; `_gather` line 423 |
| activity self-only by default; `visibility: all`; unrecognised → self, cited to `membership_changes` | CORRECT; FIXED (citation) | `config.userActivity.visibility: self`; `_visibility_setting` (line 1261); repointed to `dashboard_activity` |
| there is an administrator tier, cached | CORRECT | §7.5 rows |

### §7.3 Unmanaged-grant discovery

| claim | verdict | evidence |
|---|---|---|
| `mode` "default `off`" | FIXED | `values.yaml` line 456 `mode: "log"` (the comment: "DEFAULTS TO `log`"); the application alone falls back to `off` (`_audit_mode_setting`, line 1050). Now says both |
| unrecognised → `off`; `annotate` → `log` with a warning | CORRECT | `_audit_mode_setting` lines 1052-1072 |
| the `annotate` history: 4 planned, 0 landed, 175 rule sets, `can-i` said yes | NOT MEASURED | historical; consistent with `templates/rbac.yaml` lines 83-90 and `gsd/kube.py` lines 560-571 |
| the removed client methods "(86 lines, `gsd/kube.py#UNREACHABLE` records what and why)" | FIXED (citation); NOT MEASURED (86) | the record is the comment "NO WRITE METHOD ON THIS CLIENT" (lines 560-571); `UNREACHABLE` is an outcome constant. Repointed |
| `docs/design/unmanaged-audit-design.md` | CORRECT | the file exists |
| the summary line's text | CORRECT | `gsd/poller.py` lines 836-838 |
| WARNING per finding, its text | CORRECT | lines 858-860 |
| "the role and the group"; "Only the groups … a binding can name two groups" | FIXED | since #353 a finding's subjects are groups, ServiceAccounts or users (`subject_label`, `gsd/audit.py` line 15). Now "subjects" |
| `maxPerCycle` default 20 | CORRECT | `values.yaml` line 470 |
| "the true total"; remainder "counted as 'not yet listed'" | FIXED | the first number is every finding awaiting acknowledgement (`gsd/poller.py` lines 826-838) and the line says `held back by the per-cycle cap`; `AuditLogProgress` (`gsd/audit.py` line 116) lists new findings first and rotates the rest. Now says so |
| resolutions are never capped | CORRECT | `plan_audit_stamps` docstring; `AuditLogProgress.plan` keeps every `unstamp` |
| RESOLVED at INFO only for a labelled object, naming the `oc label` | CORRECT | `gsd/poller.py` lines 876-882 |
| `oc annotate … unmanaged-exception` suppresses it in all outputs | CORRECT | `_FINDING_CASE` |
| `mode: annotate` runs as `log` with a warning, not `off` | CORRECT | `_audit_mode_setting` lines 1054-1070 |

### §7.4 Credentials and trust

| claim | verdict | evidence |
|---|---|---|
| "Tokens are never in the config data model … re-read from the mounted file" | FIXED | a cluster Secret's `bearerToken` is held as `ClusterConfig.token_value` (`repr=False`, `gsd/config.py` line 393); a values entry's `tokenFile`/`tokenEnv` is resolved on demand (`resolve_token`, lines 467-517). Now says which is which |
| no token is returned by the API | CORRECT | `gsd/api.py` never reads `token_value` or `resolve_token`; `credential_kind` "Never the value" |
| up to two CA sources, colon-separated `GSD_TRUSTED_CA_FILE`, loaded in turn; cache keyed on the value and each file's inode, mtime, size; a null result not cached | CORRECT | `_trusted_ca_context` (lines 83-150) |
| a per-cluster `caBundleFile` always wins | CORRECT | `ClusterConfig.verify` lines 532-556 |
| non-root, read-only root, capabilities dropped, `RuntimeDefault` | CORRECT | render: `runAsNonRoot: true`, `seccompProfile: RuntimeDefault`, `readOnlyRootFilesystem: true`, `drop: [ALL]` |
| extension loading off on every connection, cited to `_MIGRATIONS` | CORRECT; FIXED (citation) | `_harden` (line 1339), called on the writer and on every reader. Repointed |

### §7.5 Who sees what

| claim | verdict | evidence |
|---|---|---|
| "two tiers" (heading, table) | FIXED | three: `require_cluster_admin` (line 796) gates the KPI page, the Cluster Configurations tab and the deletions (lines 1132, 1222, 1460, 3067); `docs/guides/ACCESS_CONTROL.md` §2 ("The three thresholds"). Third row added; heading now "three tiers" |
| cluster data and usage resolvers, both default `self`; the usage tier is not derived from the wide one; `userActivity.visibility: all` still wins | CORRECT | `viewer_scope` (line 606), `usage_scope` (line 675); `values.yaml` `visibility: self` |
| GroupSync CRs ungated because `/metrics` serves `gsd_groupsync_state` | CORRECT | `gsd/metrics.py` line 471; `skipAuthRegex` |
| binding findings gated: 236 rows, 21 naming an admin role | CORRECT; NOT MEASURED (numbers) | `require_admin_tier` (line 817); the numbers are historical |
| the narrowed tier sees its own path; membership checked before existence | CORRECT | `group_detail` docstring (lines 1815-1821) |
| the decision is a SAR the app makes, cached per viewer; `spec.groups` required; groups fresh; malformed reviews answer `false` silently | CORRECT | `TierResolver` docstring; `create_subject_access_review` docstring (lines 1352-1360) |
| everything indeterminate is `self`, not cached; only `all` widens | CORRECT | `tier_for` |
| "The TTL is a single constant" | FIXED | `visibility.tierTtlSeconds: 60` (`values.yaml` line 2277) feeds `TierResolver(ttl_seconds=…)`, which has no default "precisely" so the value is wired (`gsd/kube.py` lines 1464-1470). Now names the value, with the constant as its default |
| a revoked reader keeps the wider view at most one TTL; single-flight with takeover | CORRECT | `TierResolver` docstring and `tier_for` |
| a refusal names itself only | CORRECT | `index.html` `refusalCard` exists |
| the chart refuses `visibility.enabled=true` with the proxy off | CORRECT | render: `visibility.enabled=true requires oauthProxy.enabled=true` |

### §8 Deployment topology

| claim | verdict | evidence |
|---|---|---|
| ServiceAccount with `oauth-redirectreference` (`oauth-redirecturi` with the Ingress) | CORRECT | default render; with `route.enabled=false,ingress.enabled=true` the render has `oauth-redirecturi.primary` |
| reader ClusterRole + Binding; ConfigMaps `-config` and `-trusted-ca` (injected); Secret `-oauth-session`; Secret `-tls` from service-ca | CORRECT | render: `config.openshift.io/inject-trusted-cabundle: "true"`; `serving-cert-secret-name: group-sync-dashboard-tls` |
| Deployment replicas 1, `Recreate`; PVC `-data` `keep`; Service `:8080 → oauth-proxy`; Route or Ingress; Leases via `-leases` | CORRECT | render; lab: `group-sync-dashboard-data` `keep` |
| PDB "optional"; ServiceMonitor + PrometheusRule "optional" | CORRECT | switches exist (`podDisruptionBudget.enabled`, `monitoring.*`), all on by default |
| `-report` Deployment 1 replica `Recreate`; Service `:8443` service-ca; `-shared-token` and `-ticket-key` mounted in both pods; NetworkPolicy from the dashboard, the schedule Jobs and monitoring | CORRECT | render: `/etc/gsd/report` and `/etc/gsd/report-ticket` in both; the NetworkPolicy's two `from` blocks |
| PVC `-report-artifacts` "no keep annotation" | FIXED | `templates/report-pvc.yaml` line 16 sets `helm.sh/resource-policy: keep` unconditionally; render; lab: `group-sync-dashboard-report-artifacts keep`. The node now says `keep` |
| the dashboard proxies `/report/`; the report pod reads `/data/report` read-only | CORRECT | render: `-upstream=https://group-sync-dashboard-report…:8443/report/`; report mount `/data` `readOnly: true` |
| the Grafana ConfigMap follows the ServiceMonitor switch | CORRECT | render: one with defaults, none with `monitoring.serviceMonitor.enabled=false` |
| "It said 'four' while the chart had grown to seven" | NOT MEASURED | historical |
| guard rows 1-3, 5, 6 (replicas with election, replicas with non-RWX, RollingUpdate at one replica whatever the mode, `cookie.expire`, `cookie.refresh`) | CORRECT | renders refused at `deployment.yaml` lines 2, 5, 16, 91, 94 |
| guard row 4: `visibility.enabled=true` with the proxy off | CORRECT | `deployment.yaml` line 29 |
| reporting rows (proxy off, persistence off, replicas > 1, `rbac.bindings=false`, non-RWX claim, interval < 60, TTL outside 30..3600, a bad PDF variant, `loginActivity` with capture off) | CORRECT | each render refused by `gsd.reportingGuards`, e.g. `reporting.enabled=true requires rbac.bindings=true: nine of the eleven reports …`, `reporting.reports.loginActivity.enabled=true requires loginCapture.enabled=true` |
| "`skipAuthRegex` no longer covering `/signed-out` while `logoutUrl` is set" | FIXED | the guard fires when `oauthProxy.logoutUrl` is EMPTY (`deployment.yaml` line 96): the render with a regex lacking `signed-out` is refused, and the same regex with `logoutUrl` set renders. Its reason is that the reader "arrives back signed in", not on the login page. Both corrected |
| the offsite guards and "refuse only an explicit true" | CORRECT | batch 2's renders of the same guards; `_helpers.tpl` lines 233-241, `gsd.offsiteBlocker` |
| "`_helpers.tpl` carries ten more … nine that check the two SAR definitions" | FIXED | `_helpers.tpl` has 112 `fail` calls (stanza, reporting, offsite among them), and three SAR definitions are checked (`adminSar` lines 382-420, `usageAdminSar` 441-479, `clusterAdminSar` 505). The count is dropped and "three" named |
| the malformed-SAR measurement (`dana.lee`, 201 with `allowed: false`) | NOT MEASURED | historical lab measurement |
| `strategy` derived: `Recreate` at one replica, `RollingUpdate` above | CORRECT | renders at 1 and 2 replicas |
| `accessMode` empty derives RWOP at one, RWX above; the shipped default is RWX | CORRECT | render with `persistence.accessMode=`: `[ReadWriteOncePod]`; `values.yaml` line 1024 |
| `GSD_DB_PATH` `/data/gsd.db`, `/data/$(POD_NAME)/gsd.db` above one | CORRECT | renders |
| `ingress.host` derived by `lookup`, fails under `helm template`; the Route uses `spec.subdomain`; `route.host` is used as given | CORRECT | render `route.enabled=false,ingress.enabled=true`: `ingress.host is not set and the cluster apps domain could not be read`; `route.host=gsd.example.com` renders `host: gsd.example.com` |
| the mint hook: pre-/post-install and -upgrade, `-oauth-session`, `-shared-token`, `-ticket-key` since 0.69.0 (#392), legacy names copied at 0.37.0; `cookieSecret` renders the Secret directly | CORRECT | render: Job hooks `pre-install,pre-upgrade,post-install,post-upgrade`; `docs/CHANGELOG.md` (#392, "application 4.6.0, chart 0.69.0"; chart 0.37.0, #212); `test_current_docs_describe_the_minted_secrets_not_the_lookup_era` passes |
| probes 5s; readiness 15s; liveness 300s, `failureThreshold` 2 | CORRECT | render |
| the ~4h outage | NOT MEASURED | historical |
| neither probe gated on a reachable cluster, cited to `list_alerts` | CORRECT; FIXED (citation) | `readyz` docstring (lines 3375-3380); `healthz` returns a constant. Repointed |
| `GroupSyncDashboardNotPolling` covers the frozen-data gap | CORRECT | `templates/monitoring.yaml` line 150 |
| scrape: `https`, `ca` from `openshift-service-ca.crt`, `serverName <fullname>.<namespace>.svc`; the table of both proxy settings | CORRECT | renders with the proxy on and off |
| the `curl --resolve` verification | NOT MEASURED | historical |
| leader election best-effort, cited to `refresh_bindings` | FIXED (citation) | the rationale is the comment in `Poller.__init__` ("BEST-EFFORT admission control, NOT a write fence", lines 907-926). Repointed |
| "nothing re-checks it during the writes that follow" | FIXED | `_prune_history` and `_after_poll` re-check before the prune and the report tail (lines 1064, 1074, 1118, 1122); the poll's own writes are not re-checked. Now says so |
| two pods for up to `renew_seconds`; own clocks | CORRECT | `gsd/leader.py` line 68; the same comment |
| outside a cluster the elector sets itself leader | CORRECT | `LeaderElector.start` (lines 254-260) |
| a non-leader re-checks every 5s, cited to `poller.py#log` | FIXED (citation) | `STANDBY_RECHECK_SECONDS` and its comment (lines 1278-1288). Repointed |
| scaling: election off and RWX above one replica; aggregate with `max()` or `gsd_leader` | CORRECT | renders; `gsd/metrics.py` lines 338-347 |
| GitOps onboarding: the ConfigMap, `writes.enabled`, pruning, the `saTokenLookup` warning | CORRECT | as batch 1 measured `CLUSTER_STANZA.md`; both links resolve |

### §8a, §8b

| claim | verdict | evidence |
|---|---|---|
| per-cluster URL `https://group-sync-dashboard.apps.<cluster>…/api` | CORRECT | the Route's `spec.subdomain` is the fullname, `group-sync-dashboard` for that release name |
| PKCE code exchange; `X-Csrf-Token`; redirects not followed | CORRECT | `local-development/cluster-report.py` lines 108-187 |
| `apiTokenAccess.enabled` adds delegate-urls and binds `system:auth-delegator` to the proxy's ServiceAccount; callers do not need it | CORRECT | render: ClusterRoleBinding `-auth-delegator`, subject `group-sync-dashboard` |
| the review demands `list clusterrolebindings`; grant `cluster-reader` to a group | CORRECT | render; not a chart value |
| `cluster-report.py` falls back to `oc port-forward` | CORRECT | `cluster-report.py` lines 35-51 |
| stored times UTC with `Z`; displayed in the container's zone (`timezone`, default `America/New_York`), reported at `/api/version`; `Intl.DateTimeFormat`; logs carry `%z` | CORRECT | `gsd/timeutil.py` `now_iso`; `values.yaml` line 668; `/api/version` `timezone` (lines 3348-3369); three `Intl.DateTimeFormat` uses; `gsd/api.py` line 3573 |
| the image proves `ZoneInfo('America/New_York')` | CORRECT | `local-development/image-proof.py` line 55, run by the Containerfile (line 249) |
| UBI9-minimal stripped zoneinfo | NOT MEASURED | historical |

### §8c How a release is produced

| claim | verdict | evidence |
|---|---|---|
| two workflows, each behind a path filter; a docs-only merge publishes nothing | CORRECT | `publish.yml` `on.push.paths` (lines 81-93); `helm.yaml` `charts/**` (line 25); `docs/guides/` is in neither |
| "publish.yml — the image (writes to NOTHING in this repo)" | FIXED | two images; the `attest` job writes provenance to the attestation store with signing on, and `sbom` uploads an artifact (batch 4). Now "the images (commits NOTHING to this repo)" |
| the image path filter "gsd/**, pyproject.toml, README.md, Containerfile, .containerignore, build script" | FIXED | twelve entries (batch 4). The node now lists them |
| `--release-tags` "ALSO pushes `:<appVersion>`" | FIXED | it also writes `:<chartVersion>` (`build-and-push-external.sh` lines 262-277, batch 4). Added |
| the sha tag "immutable, every merge" | FIXED | a rebuild of the commit re-pushes it (batch 4). Now "sha tag … a rebuild re-pushes it" |
| the chart path: `charts/**`, `ci.yml` first, `skopeo copy`, chart-releaser skips released versions, `gh-pages` | CORRECT | `helm.yaml` lines 25, 35-46, 318, 330; `https://ephico2real2.github.io/group-sync-dashboard/index.yaml` answers 200 |
| the image is a merge commit and the tag records it; `<appVersion>-<sha>` from `pyproject.toml`; `test_chart_versions.py` holds appVersion and `__version__` | CORRECT | `tests/test_chart_versions.py` lines 46 and 136-150 |
| (added) two images since application 0.18.0 | FIXED | `docs/guides/RELEASING.md` "Since application 0.18.0 a release is two images"; `publish.yml` header |
| "Nothing in `publish.yml` writes to this repository" | FIXED | as batch 4: commits nothing; the provenance and the SBOM artifact named |
| #34, #37, branch protection; `contents: read` asserted | CORRECT; NOT MEASURED (history) | `publish.yml` lines 1-21; `test_the_publish_job_can_write_to_nothing_but_the_registry` |
| `<appVersion>-<sha>` "is immutable" | FIXED | it names the same source; a rebuild re-pushes it (batch 4). Qualified |
| the alias moves only on a version bump; `imagePullPolicy: Always` | CORRECT | `values.yaml` line 60; `test_an_ordinary_merge_does_not_move_the_alias` |
| "this project never repoints `<appVersion>-<sha>`" | FIXED | a rebuild re-pushes it. Now "never moves … to another commit, but a rebuild re-pushes it" |
| `image.digest` wins and renders `repository@sha256:…`; ships empty | CORRECT | `values.yaml` line 54; batch 4's render |
| "`<chartVersion>` is stamped by `helm.yaml`, not `publish.yml`" | FIXED | `publish.yml`'s `--release-tags` also writes it on a release merge (batch 4). Qualified |
| "The pinned tag is not necessarily HEAD … the pin still names" | FIXED | there is no pin: `image.tag: ""` (`values.yaml` line 32), removed in f9fa8967. Now "the newest sha tag" |
| `test_publish_paths.py` holds the filter to the Containerfile's `COPY`/`ADD`; `.containerignore` included | CORRECT | the test's docstring; `publish.yml` line 88 |
| "Why the pin is written onto the fetched tip … The step now fetches … `tests/test_publish_pin_step.py` reads the step" | FIXED | the pin step and that test (610 lines) were deleted in f9fa8967 ("stop writing the image pin to main"); the file does not exist. Now past tense, naming the removal; the test reference dropped |
| the 2026-08-09/10 `CONFLICT` failures; `0.6.0-6f88f2a9aa` | NOT MEASURED | historical |
| chart-releaser's skip is "the one failure mode of this path" | FIXED | `helm.yaml` also turns red on a missing image or a mislabelled one (batch 4, lines 228-309); the skip is the silent one. Now "the one silent failure mode" |
| `helm install gsd gsd/group-sync-dashboard --set ingress.host=…` | FIXED | the default is a Route and needs no host (§8 and §11 of this page); the flag is dropped |

### §9, §10, §11, §12

| claim | verdict | evidence |
|---|---|---|
| §9 rows' facts | CORRECT | each matches the rows above |
| §9 "Readers on their own connections" cited to `Store._tx` | FIXED (citation) | `Store._reader`. Repointed |
| §9 "Leader election is best-effort" cited to `refresh_bindings` | FIXED (citation) | the `Poller.__init__` comment. Repointed |
| §9 "Activity self-scoped" cited to `membership_changes` | FIXED (citation) | `dashboard_activity`. Repointed |
| §9 "Role rules are never expanded" cited to `list_events` | FIXED (citation) | `group_detail` (line 1874). Repointed |
| §9 "Every unbounded list is capped" cited to `list_events`, `400-406` | FIXED (citation) | the "silently truncated audit list is worse than a slow one" reasoning is `direct_user_bindings` (line 2659); `400-406` was a stale line range. Repointed |
| §10 metric names, alert, `oc get lease`, `trustedCA`, the `_list_all` guard, the collision log, the `off` row, the annotation and label rows, `/api/version` reporting commit, branch and `dirty` | CORRECT | `gsd/metrics.py` lines 391-438; `templates/monitoring.yaml` line 150; lab Lease `group-sync-dashboard` held by `group-sync-dashboard-6b4bd865f6-944cc`; `gsd/api.py` lines 3360-3362 |
| §11 SQL only in `store.py`; `_write()` joins; `@consistent` rules; `limit`/`total`/`truncated` | CORRECT | as above |
| §11 a chart value threads through `configmap.yaml`, `load_settings`, `Settings`; `_bool_setting`; `_visibility_setting`; `_audit_mode_setting` downgrades to `log` | CORRECT | `gsd/config.py` lines 1509, 1261, 1042, 1864 |
| §11 the naming collision, cited to `Store.replace_user_bindings` | FIXED (citation) | the record is `Store.direct_user_bindings`' docstring (lines 4005-4009). Repointed |
| §11 "ambient one … gives six meaningless collection errors" | NOT MEASURED | not run with the system interpreter |
| §11 "with `--set ingress.enabled=true` it also needs `--set ingress.host`" | FIXED | with the default Route on, that render fails: `route.enabled and ingress.enabled are both true` (`_helpers.tpl` line 127). Now `--set route.enabled=false --set ingress.enabled=true` plus the host |
| §12 every link | CORRECT | every relative link resolves (a link check over the page) |
| §12 `REVIEW_*.md` and `OAUTH_LOGLEVEL_REVIEW.md` are under `docs/` | CORRECT | `docs/reviews/` (87 `REVIEW_*`), `docs/research/OAUTH_LOGLEVEL_REVIEW.md` |
| (missing) housekeeping, on by default in the chart | FIXED | **Found by Codex's review.** `housekeeping.enabled: true` (`values.yaml` lines 1179-1180); the delete routes in `gsd/api.py` (lines 1511-1588) are behind the cluster-admin tier; `gsd/housekeeping.py` never deletes the newest copy in each directory; `gsd/reporting/artifacts.py` refuses a queued or running run. A short paragraph added to §1 |

## Diagrams

Every block was rendered after the edits. `mermaid-ascii` 1.6.1 (downloaded to the scratch directory)
renders all ten, rc=0. The six edited blocks (§1a, §2, §3, §4, §8, §8c) were also rendered to SVG with
`npx @mermaid-js/mermaid-cli@11`, the tool the CI `diagrams` job uses: rc=0, no `Syntax error` text in any
SVG. `tests/test_docs_diagrams.py` passes.

## Findings for the orchestrator

1. **CODE-SUSPECT: the prefix fallback in `provider_keys_for` does not award a label to the longest CR
   name.** `local-development/gsd/poller.py`, `provider_keys_for` (lines 267-303). Its docstring and §3
   of this page say that, for a CR whose spec declares no provider names, "it now yields a label to the
   LONGEST matching CR name". The function sees one CR at a time and returns every label starting with
   `<name>_`, so a shorter CR still claims a longer CR's groups. Run on this head:
   `provider_keys_for(cr("corp"), [corp_extra_ldap, corp_ldap])` returns `['corp_extra_ldap',
   'corp_ldap']`, and `cr("corp_extra")` returns `['corp_extra_ldap']`: one group, two owners, counted in
   both CRs' `group_count`. `tests/test_store_poller.py` covers the declared-names path (line 268) and the
   prefix path for a single CR (line 286), not two prefix-related CRs without declared names. The page was
   left as it is.
2. **Comment drift in the code** (not behaviour; outside this batch's scope, so unchanged):
   `gsd/api.py` `record_dashboard_use` (line 945) and `gsd/activity.py` (line 58) say the page polls every
   30s (`index.html` line 8872 is 60s); `gsd/config.py`'s module docstring (line 3) says the token is kept
   out of the data model, while `ClusterConfig.token_value` holds a Secret's `bearerToken`; `poll_once`'s
   comment says the poll was "seven separate commits" where `Store.poll_snapshot` and `Store._write` say
   nine.
3. **`/api/clusters/{id}/groups` has no `limit`** (`gsd/api.py` line 1772). §5 says "every list endpoint
   that can grow with the size of the directory … is bounded" and §9 "every unbounded list is capped". The
   number of groups is set by the GroupSync filters, so whether it "grows with the directory" is a
   judgement; the sentence was left unchanged and the question is the orchestrator's.
