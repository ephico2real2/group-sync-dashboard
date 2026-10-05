# Docs content audit, batch 3 of 6: the access-control, login-capture and API guides

Phase 2 of the documents pass, third batch. The five guides under `docs/guides/` that describe who sees
what, how logins are captured and how the API is called were read in full, and every checkable claim was
measured against main at 53116573 (application 5.3.0, chart 0.70.6). The evidence comes from:

- the chart's values and templates, rendered with `helm template` (Helm v4.3.0);
- the application under `local-development/gsd/`, read at the cited lines, and the mock cluster under
  `local-development/mock-app/`, run in place on the lab's own fixture;
- the tree and `docs/CHANGELOG.md`;
- the lab (CRC, namespace `group-sync-dashboard`), read-only with `oc get` and `oc logs`. No Secret data
  was read.

Nobody was logged in, to the cluster or to the dashboard, and no token was minted. No
SubjectAccessReview was created, not even through `oc auth can-i`: where a guide states what an identity
may do, the answer was computed from the lab's ClusterRoleBindings, RoleBindings and ClusterRoles, read
with `oc get` (the rules of aggregated roles are already filled in on those objects). A claim only a
login, a token or a request as a named person could prove is NOT MEASURED. Line numbers are given
outside backticks and are those of 53116573.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the guide now says what the evidence shows.
- **NOT MEASURED**: no measurement was possible here (a historical value, a login, a token, or a request
  made as a person). It was left unchanged.
- **CODE-SUSPECT**: the guide is right and the code is not. This batch found none.

`ACCESS_CONTROL.md` §3 and §4 are held to the code by `local-development/tests/test_access_declaration.py`
(every route, every persona, every tab), so their tables were taken as measured by that test, which passes
on this head. The prose around the tables was checked by hand.

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `ACCESS_CONTROL.md` | 57 | 18 | 5 | 0 |
| `AUDIT_LOG_CAPTURE.md` | 22 | 2 | 3 | 0 |
| `LOGIN_CAPTURE_QUICKCHECK.md` | 16 | 1 | 3 | 0 |
| `api-access.md` | 18 | 1 | 5 | 0 |
| `api-contract.md` | 16 | 4 | 3 | 0 |

## `docs/guides/ACCESS_CONTROL.md`

| claim | verdict | evidence |
|---|---|---|
| §1: the identity chain: an `ldap-local` identity, Groups annotated `openshift.io/ldap.uid` | CORRECT | lab: `User/john.doe` identities `["ldap-local:…"]`; `Group/app-ocp-rbac-demo-cluster-admin` annotated `cn=app-ocp-rbac-demo-cluster-admin,ou=Groups,dc=ephico2real,dc=com`, users `[john.doe]` |
| §1: `demo-cluster-admin-crb -> ClusterRole/cluster-admin` | FIXED | lab: `clusterrolebindings "demo-cluster-admin-crb" not found`. The binding for that Group is `app-ocp-rbac-demo-cluster-admin-crb`, ClusterRole `admin`, created 2026-09-19 by the namespace-configuration-operator (labels `rbac.ocp.io/bound-role: admin`, `rbac.ocp.io/source-kind: GroupConfig`). Now names that binding |
| §1: cluster power comes "not from anything in this chart"; the dashboard "never grants anything" | FIXED | The default render binds ClusterRole `group-sync-dashboard-report-auditor` (`get`/`list` on users, groups, roles, rolebindings, clusterroles, clusterrolebindings) to Group `app-ocp-rbac-groupsync-ns-auditor` (`rbacAuditors.enabled: true`, `values.yaml` line 2408). On the lab that binding is what gives `jane.smith` and `lateef.o` the wide tier (§9 row). Now names `rbacAuditors` as the one exception; the application itself grants nothing at runtime |
| §1: Route → oauth-proxy `:8443` → app on `127.0.0.1:8080`; the Service targets the proxy | CORRECT | render: the app runs `--host 127.0.0.1 --port 8080`; the proxy `-https-address=:8443`, `-upstream=http://127.0.0.1:8080`; Service `group-sync-dashboard` `targetPort: oauth-proxy`; the Route targets that Service |
| §1: with the proxy off there is no trusted identity — "see §7" | FIXED | §7 is "The UI never decides the tier"; proxy-off is §8. `trusted_viewer` returns None when the proxy is off (`local-development/gsd/api.py` lines 575-583). Now "see §8" |
| §2: the three thresholds and their default checks | CORRECT | `values.yaml` `visibility.adminSar` / `usageAdminSar` / `clusterAdminSar`; the rendered ConfigMap carries `list`, `update`, `update` on `clusterrolebindings`; the wide row is held by `test_values_defaults.py` |
| §2: the cluster-admin tier grants every host-decided tier; `viewer_scope` and `usage_scope` consult it first; one way only | CORRECT | `local-development/gsd/api.py` lines 664-669 (`viewer_scope`) and 707-714 (`usage_scope`) call `_cluster_admin_granted` before their own resolver |
| §2: a `remote-sar` cluster asks its own API, `self-only` stays self, `hidden` stays hidden | CORRECT | `viewer_scope` returns self for `self-only` and asks the remote's resolver for `remote-sar` before the cluster-admin check (lines 646-663); `require_cluster` 404s a hidden cluster (line 1069) |
| §2: the cluster-admin tier is asked whatever `visibility.enabled` says | CORRECT | `cluster_admin_tier` is built without the `view_restrictions_enabled` condition (lines 470-481); `_cluster_admin_granted` has no `restrict` short-circuit (lines 763-787) |
| §2: the `get`/`create secrets` pair it replaced admitted `admin` or `edit` in the release namespace | CORRECT | `docs/CHANGELOG.md` line 843 (chart 0.57.0, #322) |
| §2: "The dashboard holds no write grant on any resource" | FIXED | Default render: Role `group-sync-dashboard-leases` (`get`, `create`, `update` on leases), ClusterRoleBinding `group-sync-dashboard-auth-delegator` to `system:auth-delegator`, and with `clusterConfig.secrets.writes.enabled` the Secrets writer (`local-development/gsd/clusterconfig/writer.py` lines 293-490). The app posts reviews (`local-development/gsd/kube.py`, `SAR_API` at line 98) and writes Leases (`local-development/gsd/leader.py` lines 152 and 222, `fleetstate.py`). Now: it never performs the `update` the thresholds name, and its own writes are its Leases, the reviews, and, with writes on, cluster Secrets — the wording batch 2 gave the chart README **Found by Codex's review:** the list also needs the TokenReviews `system:auth-delegator` allows (`templates/rbac.yaml` lines 187-208; the oauth-proxy uses them). Added. |
| §2: the `cluster-admin` / `cluster-reader` table (`list groups` yes/yes, `list clusterrolebindings` yes/yes, `update clusterrolebindings` yes/no, `get secrets` yes/no) | CORRECT | computed from the lab's ClusterRole rules: `cluster-admin` all four true; `cluster-reader` `list groups` true, `list clusterrolebindings` true, `update clusterrolebindings` false, `get secrets` false |
| §2: "No *read* check can distinguish them, because `cluster-reader` is by construction 'may read everything'" | FIXED | The table under it shows a read that does (`get secrets`), and the lab's `cluster-reader` holds no rule for `secrets`, `nodes/proxy` or `nodes/log`. Now: no read on the objects these views show can distinguish them; only a write verb does, or a read `cluster-reader` excludes, such as `get secrets` |
| §2: Logins is reproducible with `oc` by `cluster-reader` (`pods/log` on the oauth-server pod, or `oc adm node-logs` with `nodes/proxy`), "still nothing the wide tier's `cluster-reader` cannot read"; "That matters for exactly one dataset" | FIXED | The pod-log reader was removed in chart 0.58.0 / application 0.36.0 (`docs/CHANGELOG.md` line 826). Lab: `authentications.operator.openshift.io/cluster` `spec.logLevel: Normal`, the operand runs `--v=2`, and the last 2,000 lines of the oauth-server pod log hold 0 `for login` lines. The audit log needs `get nodes/proxy`, which the lab's `cluster-reader` does not hold (computed: false). Now the row says **no**, and the two sentences around the table say "Logins aside". The design consequence is finding 1 below **Found by Codex's review:** the comparison table and its conclusions were measured on the lab's ClusterRoles only; they are now dated and scoped to the lab, the heading says three tiers, and the auditor sentence names the `rbacAuditors` role too. |
| §2: Usage exists only in `dashboard_user_activity` | CORRECT | `local-development/gsd/store.py` (9 references to the table) |
| §3: fourteen tabs and two pages, the reader table, the four words | CORRECT | held by `test_access_declaration.py` (T239-4, passing); 14 tab rows counted |
| §3: `charts/group-sync-dashboard/values.yaml#skipAuthRegex`; `tests/test_ui.py#TestTheDeclaredTabs` | CORRECT | `values.yaml` line 2112; `local-development/tests/test_ui.py` line 5057 |
| §3: "since 0.10.0 the tab shows it" | NOT MEASURED | historical version |
| §4: the route table (method, path, registered, gate, five personas) | CORRECT | held by `test_access_declaration.py`, passing on this head |
| §4: six rows registered `writes on`, five `housekeeping on` | CORRECT | counted in the table; `test_api_contract.py` `CLUSTER_SECRET_WRITES` has six |
| §4: "**registered** is `always`, or `writes on` for the six routes" | FIXED | The table also uses `housekeeping on` (five rows; `local-development/gsd/api.py` line 1511 registers them only `if settings.housekeeping_enabled`). Now names all three words |
| §4: `/api/report/ticket` is 404 with reporting off | CORRECT | `local-development/gsd/api.py` line 3302 |
| §4: `/report/**`: no ticket 401, a ticket for another identity 403, an earlier-format ticket 401 | CORRECT | `local-development/gsd/reporting/server.py` lines 196-213 (a `TicketError` other than expiry and `EARLIER_FORMAT` is 403) |
| §4: `/metrics` is in `skipAuthRegex` and carries `gsd_groupsync_state{groupsync=…}`, `_last_sync_timestamp_seconds`, `_groups_total` | CORRECT | rendered `-skip-auth-regex=^/(healthz\|readyz\|metrics\|signed-out\|static/(app\.css\|favicon\.svg))$`; `local-development/gsd/metrics.py` lines 463-479 |
| §4: `ldap_filter` and `error_message` omitted at self by an allowlist; `reconcile_error` replaced by a generic sentence | CORRECT | `local-development/gsd/api.py` lines 172-187 and 221-236 |
| §4: "measured: the narrowed personas fail `oc auth can-i get groupsyncs.redhatcop.redhat.io`" | NOT MEASURED | needs a review as each persona |
| §4: `operator_configs` is `null` below the wide tier and its summary is not on `/metrics` | CORRECT | `local-development/gsd/api.py` lines 1659-1660; `metrics.py` uses the configs only to count alerts |
| §4: the membership check runs before the existence lookup | CORRECT | `require_admin_tier` docstring (`local-development/gsd/api.py` from line 817) and its tests |
| §5: the decision diagram's functions; only the exact string `"all"` widens | FIXED | the diagram test passes; `_decide` (lines 585-604) and `usage_scope` widen only on `tier == TIER_ALL` **Found by Codex's review:** the `usage_scope` branch omitted the cluster-admin tier and the restrictions-off `self` (`gsd/api.py` lines 675-733). Now in order. |
| §5: the resolver cited at `kube.py` lines 1018, 99 (`TIER_TTL_SECONDS`, 60.0) and 79 (`SAR_API`) | FIXED | the lines moved: `TierResolver` is at line 1411, `TIER_TTL_SECONDS` at 142, `SAR_API` at 98, and the TTL a resolver uses is `visibility.tierTtlSeconds` (`api.py` passes `settings.visibility_tier_ttl_seconds`). Now cited by name (`gsd/kube.py#TierResolver`) and by the setting |
| §5: groups sent = "polled groups" + `VIRTUAL_AUTH_GROUPS` | FIXED | `_resolve_and_cache` sends `fetch_groups_of_user(viewer)` — a fresh Group list, not the poller's snapshot (the `TIER_TTL_SECONDS` docstring) — plus `_virtual_groups_for(viewer)`, which gives a ServiceAccount `system:serviceaccounts`, `system:serviceaccounts:<ns>` and `system:authenticated` (`local-development/gsd/kube.py` lines 124-137). Now says so |
| §5: allowed true/false cached for the TTL, a failure not cached; a revoked administrator keeps the wide view at most one minute | FIXED | `local-development/gsd/kube.py` `_resolve_and_cache` caches only a decided answer (line 1685); `VISIBILITY_TIER_TTL_DEFAULT = 60` (`config.py` line 40) **Found by Codex's review:** one minute is the default only; the TTL is `visibility.tierTtlSeconds` (`gsd/kube.py` line 1685 caches `now + self._ttl`). Now says so. |
| §5: the "Verified live" review naming `demo-cluster-admin-crb` | NOT MEASURED | a past measurement; that binding no longer exists on the lab. One clause now says it is from the lab as it was then |
| §5: `SELF_ALERT_DETAILS` is the allowlist, `SELF_ALERT_KINDS` derived from it, `dangling_binding` and `config_reconcile_error` outside it | CORRECT | `local-development/gsd/api.py` lines 172-187 |
| §6: `GSD_ENABLE_VIEW_RESTRICTIONS` from the `gsd.visibilityEnabled` helper; four ConfigMap keys per threshold | CORRECT | `templates/deployment.yaml` lines 271-272; `_helpers.tpl` line 361; rendered `visibilityAdminSar*`, `visibilityUsageAdminSar*`, `visibilityClusterAdminSar*`, four each |
| §6: the diagram names two thresholds, "ONE grant serves BOTH tiers", "two TierResolver instances", and `config.py` lines 301, 307-314, 324-328 and 338 | FIXED | There are three thresholds and three host resolvers (`local-development/gsd/api.py` lines 418, 437 and 471, published at lines 3556-3563; the wide and usage ones only with restrictions on). The `config.py` fields are now at lines 840-937. Now names the third threshold, its keys and its resolver, and cites the `Settings` fields by name |
| §6: the `auth-delegator` binding "renders whenever something needs it and disappears when nothing does" | FIXED | renders: present by default and with `visibility.enabled=false`; absent with the proxy off. It follows `oauthProxy.enabled` (`templates/rbac.yaml` line 187). Now says it renders whenever the proxy is on |
| §6: "Both thresholds therefore fail the `helm` render" on a miscased or versioned shape | FIXED | all three do: `visibility.adminSar.verb=List`, `visibility.usageAdminSar.resource=ClusterRoleBindings` and `visibility.clusterAdminSar.apiGroup=rbac.authorization.k8s.io/v1` are each refused with a message naming the key. Now "All three" |
| §6: `visibility.enabled=true` with the proxy off is refused | CORRECT | render with `oauthProxy.enabled=false,reporting.enabled=false`: `visibility.enabled=true requires oauthProxy.enabled=true … Turn the proxy on, or set visibility.enabled=false` |
| §7: the refusal card says *For administrators only.*; the pill says *Your view — name* or *Full view* | CORRECT | `local-development/gsd/static/index.html` lines 814-817 and 939 |
| §8: the four configurations; the startup warning; the usage tier not consulted with restrictions off; the cluster-admin tier still asked; no identity with the proxy off | CORRECT | `local-development/gsd/api.py` lines 536-544 (the WARNING), 715-717 (`usage_scope` returns self when not `restrict`), 763-787; render refusal above |
| §9: the pod selector `app.kubernetes.io/name=group-sync-dashboard`, `-c dashboard`, port 8080 | CORRECT | lab: one pod carries that label (the report pod is `…-report`); containers `dashboard` and `oauth-proxy` |
| §9: the example reads `/api/clusters/crc-local/groups` | FIXED | the lab's ConfigMap `group-sync-dashboard-config` names its one cluster `dashboard`, the chart's default host entry since chart 0.45.0 (`values.yaml` line 786, commit 2866218a). `crc-local` is the older lab name; it is still the name in `local-development/clusters.example.yaml` and `examples/flux/helmrelease.yaml`, which the command here does not use. Now `dashboard`. Not run: a request as a named reader records that reader's activity |
| §9: the review example as `john.doe` through `app-ocp-rbac-demo-cluster-admin`, "a group-granted admin" | FIXED | on today's lab that subject answers no (the Group's binding grants `admin`, row below). Now `lateef.o` through `app-ocp-rbac-groupsync-ns-auditor`, which the lab's bindings allow only through the Group. Not run (it creates a review) |
| §9: personas `john.doe` wide + usage, `dana.lee` wide only, `jane.smith` self, `lateef.o` self | FIXED | computed from the lab's bindings with the user's Groups plus `system:authenticated` and `system:authenticated:oauth`: `john.doe` passes none of the three questions (his Groups bind `admin`); `dana.lee` passes the wide one through ClusterRoleBinding `cluster-reader`; `jane.smith` and `lateef.o` pass the wide one through `group-sync-dashboard-ra-b78c05817c9d` (Group `app-ocp-rbac-groupsync-ns-auditor`); none passes `update clusterrolebindings`. Now the table says so, with how it was measured |
| §9: `lateef.o` has real login history | NOT MEASURED | needs the dashboard's database |
| §10: the keys; `tierTtlSeconds` default 60, `0` disables caching, `GSD_VISIBILITY_TIER_TTL_SECONDS` overrides it, a fractional or negative value fails the render; `oauthProxy.sar` | CORRECT | `values.yaml` lines 2117 (`sar: ""`) and the `visibility` block; `config.py` `_num_setting` (env first, line 1030); a TTL of 0 makes every cache entry already expired (`kube.py` line 1685); render guard measured in batch 2 |
| §11: the host is the `dashboardController: true` entry, else the first enabled | CORRECT | `local-development/gsd/config.py` lines 981-992 |
| §11: the policy table's defaults | CORRECT | `local-development/gsd/config.py` `remote_policy` (lines 61-72) and `cluster_policy` (lines 1001-1020) |
| §11: a hidden or unknown id is the same 404; the `identity: none` sentence word for word | CORRECT | `local-development/gsd/api.py` line 1070 (`unknown cluster …`) and lines 752-754 |
| §11: retired clusters are marked at poll start and skipped; `/api/alerts` with no served cluster is `self` | CORRECT | `local-development/gsd/poller.py` line 1925 (`retire_absent_clusters`); `list_alerts` (lines 2907-2924) |
| §11: one remote resolver per cluster, rebuilt on a new connection; the 30 s hold; the failure metric and alert | CORRECT | `local-development/gsd/kube.py` lines 174 and 1735 (`connection_fingerprint`); `charts/group-sync-dashboard/templates/monitoring.yaml` holds `GroupSyncDashboardVisibilityChecksFailing` |
| §11: the remote ClusterRole `group-sync-dashboard-cluster-poller` carries `create subjectaccessreviews` and `list groups` | CORRECT | lab: that ClusterRole (label `helm.sh/chart: group-sync-operator-helm-0.14.1`) has both, and `get nodes/proxy` / `list nodes` |
| §11: `/api/whoami` `visibility.clusters[id] = {policy, identity, scope}`; `/api/clusters` rows `visibility = {policy, scope}` | CORRECT | `local-development/gsd/api.py` lines 3184 and 1664 |
| §11: the behaviour before 0.19.0 | NOT MEASURED | historical |
| the cited documents (`DESIGN_remote_cluster_access.md`, `SPEC_D2b_remote_sar_for_every_join.md`, `reference-architecture.md`, `cluster-report.py`) | CORRECT | all exist |

## `docs/guides/AUDIT_LOG_CAPTURE.md`

| claim | verdict | evidence |
|---|---|---|
| the pod-log reader was removed in chart 0.58.0 / application 0.36.0 (#321); the spec and design pages | CORRECT | `docs/CHANGELOG.md` line 826; `docs/specs/SPEC_D1_audit_log_login_capture.md` and `docs/design/DESIGN_login_capture.md` exist |
| §1: the request is `GET /api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log` | CORRECT | `local-development/gsd/kube.py` line 80 (`NODE_LOG_PROXY_TMPL`) |
| §1: `oauth-server`, not `oauth-apiserver` (`gsd/auditlog.py#AUDIT_DIR`) | CORRECT | `local-development/gsd/auditlog.py` line 85 |
| §2: two rules, `list nodes` and `get nodes/proxy` | CORRECT | default render: ClusterRole `group-sync-dashboard-login-capture-audit` has exactly those |
| §2: the binding is named `<release>-login-capture-audit` | FIXED | the name is built from the chart's fullname: with release `x` the render names `x-group-sync-dashboard-…`. Now `<fullname>-login-capture-audit`, as the chart README writes it |
| §2: on other clusters the grant ships in `group-sync-dashboard-cluster-poller` | CORRECT | lab ClusterRole (row in the table above) |
| §2: `nodeNames` pins `resourceNames` and drops the `list` | CORRECT | measured in batch 2 (README row on the audit grant) |
| §2: `nodeSelector` default `node-role.kubernetes.io/master=`; OpenShift sets both labels | CORRECT | `values.yaml` line 1799; lab: node `crc` matches both `master=` and `control-plane=` |
| §3: both annotations; three kinds; consent is not a row | CORRECT | `local-development/gsd/auditlog.py` lines 154-215 |
| §3: system accounts and `kube:admin` never recorded; `ignoreIdentityPatterns` default `ou=TrustedApplications` | CORRECT | `auditlog.py` lines 117-118; `values.yaml` line 1813 |
| §3: an unknown username is still a row with `identity_match` NULL | CORRECT | `identity_match_for` returns None with no identities (`auditlog.py` lines 239-255); only ignored identities are dropped (line 573) |
| §4: the mocks are their own Services at `:6443` | CORRECT | lab: Services `mock-trusted`, `mock-privateca`, `mock-selfsigned` (and `mock-openshift`), all on 6443 |
| §4: the `TOK=$(oc get secret …)` recipe and the curl through the pod | NOT MEASURED | it reads Secret data; the Secret's shape (`config` JSON with `bearerToken`) matches `local-development/gsd/clusterconfig/parser.py` line 45 |
| §4: HTTP 200, 1,559 bytes, three records (`jane.smith` allow 302 credential, `lateef.o` deny 401 cli, `dana.lee` allow 302 session) | CORRECT | the lab's `mock-fixture` ConfigMap rendered through `mock_app.auditlog.AuditServer` here: `audit.log 200 1559`, three lines, those three users, decisions, codes and URIs; the lab log also has `mock-trusted: master-0: audit.log read 0 byte(s) from offset 1559` |
| §4: the record's `level`, `stage`, `user.username: system:anonymous` | CORRECT | same render: `Metadata`, `ResponseComplete`, `system:anonymous` on every line |
| §4: the fixture is `reference.yaml`'s `auditLog`, beside the nodes | CORRECT | lab ConfigMap keys `auditLog` (`node: master-0`, `dir: oauth-server`) and `nodes` |
| §5: rotated files ascending, then `audit.log` | FIXED | true on first sight only: once `audit.log` has a cursor it is read first, so its rotation is noticed before the rotated copy is read as a new file (`local-development/gsd/auditlog.py` lines 495-505). Now says both **Found by Codex's review:** a cursor alone is not enough; `audit.log` goes first only when its `byte_offset` is above 0 (`gsd/auditlog.py` lines 495-506). Now says so. |
| §5: whole lines, a byte cursor, 8 MiB per node per cycle, backfill bounded by `retentionDays` | CORRECT | `local-development/gsd/kube.py` line 83 (`AUDIT_READ_MAX_BYTES = 8 * 1024 * 1024`); `auditlog.py` lines 507-525 |
| §5: the log line `audit.log read 0 byte(s) from offset 1559` | CORRECT | `auditlog.py` line 574 (DEBUG); seen on the lab today, quoted above |
| §6: a deny carries no LDAP cause | CORRECT | `parse_audit_line` keeps `responseStatus.code` and `.message` only (lines 213-215) |
| §6: a locked account (LDAP 19) answers HTTP 500 | NOT MEASURED | needs a locked account and a login |
| §6: stored pod-log causes remain readable | NOT MEASURED | needs rows from before chart 0.58.0; no migration deletes `login_event` rows (the only `DELETE FROM login_event` is the retention prune, `store.py` line 3375) |

## `docs/guides/LOGIN_CAPTURE_QUICKCHECK.md`

The page has two halves: a current five-step check, and a transcript dated 2026-08-07 under a banner that
says not to run it. The transcript (its numbered sections 0 to 5, "Reading the lines correctly",
"Checking the grants directly", "If you see nothing") records the removed pod-log path and was not
re-measured; it is counted once below. Its section 6 describes the current source and was measured.

| claim | verdict | evidence |
|---|---|---|
| the Debug reader and the auth-loglevel Jobs were removed in chart 0.58.0 / app 0.36.0 | CORRECT | `docs/CHANGELOG.md` line 826 |
| the chart README's **OAuth Debug migration** section | CORRECT | `charts/group-sync-dashboard/README.md` line 644 |
| step 1: no auth-loglevel objects and no Role granting `pods/log`; the audit ClusterRole with `get nodes/proxy`, plus `list nodes` unless pinned | CORRECT | default render: 0 matches for `auth-loglevel`, no `pods/log` rule anywhere; the audit ClusterRole as above |
| step 2: the target's poller ServiceAccount needs `get nodes/proxy` and `list nodes` | CORRECT | the remote ClusterRole above |
| step 3: `/var/log/oauth-server/audit.log`; a 403 is a grant failure | CORRECT | `AUDIT_DIR`/`AUDIT_FILE` (`auditlog.py` lines 85-86) |
| step 4: a controlled `oc login` appears in the Logins tab | NOT MEASURED | needs a login |
| step 4: `GET /api/clusters/<cluster>/logins?kind=all`; the fields `source`, `status_code`, `identity_match`, `last_read_at`, `capture_started_at` | CORRECT | `local-development/gsd/api.py` lines 2051-2059 (`kind` accepts `all`) and 2165-2166; `store.py` line 906 |
| step 5: `gsd_login_capture_source_info{source="audit-log"}`, the last-read and per-node settled timestamps | CORRECT | `local-development/gsd/metrics.py` lines 496-519 |
| a deny has no LDAP code: a wrong password cannot be told from a locked account | FIXED | needs both failures; see the open question below **Settled from the code by Codex's review:** `parse_audit_line` keeps `responseStatus.code` and the message (`gsd/auditlog.py` lines 213-223) and stores no LDAP code, so the HTTP class is distinguishable but the directory cause is not proven. The guide now says that; the live locked-account response is still not re-measured. |
| existing pod-log rows remain, no migration removes them; capture off stops reads | CORRECT | the only delete is the retention prune (`store.py` line 3375); `logincapture.py` lines 43-47 return before any read when capture is off |
| the 2026-08-07 transcript (historical sections) | NOT MEASURED | historical by its own banner |
| section 6: `oc adm node-logs --path=oauth-server/…` and the `jq` filter | NOT MEASURED | runs as an administrator on the node |
| section 6: kind `session` for a re-authorisation | CORRECT | `auditlog.py` line 206 |
| section 6: the Range read answers 206 or 200, both handled | CORRECT (read) | the mock serves both (`mock_app/auditlog.py` `read`); not run against the lab, which needs a token |
| section 6: the dashboard's ServiceAccount can `get nodes/proxy` | CORRECT | computed from the lab's bindings: `group-sync-dashboard-login-capture-audit` grants it |
| section 6: it cannot `list pods` in `openshift-authentication` | CORRECT | computed: no ClusterRoleBinding or RoleBinding in that namespace gives the ServiceAccount `list pods` or `get pods/log` |

## `docs/guides/api-access.md`

| claim | verdict | evidence |
|---|---|---|
| `oauthProxy.apiTokenAccess.enabled` defaults to `true` since chart 0.14.0 | CORRECT | `values.yaml` line 2181; `local-development/tests/test_values_defaults.py` lists it among the 0.14.0 flips |
| a default install adds `-openshift-delegate-urls` for `/api` and binds `system:auth-delegator` to the ServiceAccount the proxy runs as | CORRECT | default render: `-openshift-delegate-urls={"/api":{"resource":"clusterrolebindings","group":"rbac.authorization.k8s.io","verb":"list"}}` on both proxy containers; the binding's subject is ServiceAccount `group-sync-dashboard`, which the pod runs as |
| the switch grants nothing on its own | CORRECT | with `apiTokenAccess.enabled=false` the render loses the delegate URLs and keeps the binding (it follows the proxy) |
| the application repeats the check as `visibility.adminSar`; a `cluster-reader` token is wide on cluster data and self on `/api/dashboard/activity` | CORRECT | `delegateUrls` and `adminSar` ask the same question (`values.yaml` lines 2182 and the `visibility` block); `usage_scope` asks `update clusterrolebindings`, which `cluster-reader` lacks (computed above) |
| with the switch off a bearer token gets a 403 whose body is the login page | NOT MEASURED | needs a token |
| the review demands `list clusterrolebindings` | CORRECT | `values.yaml` line 2182 |
| the `list groups` measurement (229 bindings) | NOT MEASURED | historical |
| `apiTokenAccess.readers` was removed | CORRECT | `values.yaml` line 2161 |
| a ServiceAccount's review names `system:serviceaccounts`, `system:serviceaccounts:<namespace>`, `system:authenticated` (`gsd/kube.py#_virtual_groups_for`) | CORRECT | `local-development/gsd/kube.py` lines 124-137 |
| the cited records `REVIEW_chart_defaults.md` and `SPEC_D2_per_cluster_authorization.md` | CORRECT | both exist |
| an empty ```` ```bash ```` block before "Verified after tightening" | FIXED | introduced empty by c54f8377 (2026-09-05), which replaced a paragraph and left the fence. Removed |
| "Verified after tightening": 403, 200, 403 | NOT MEASURED | needs tokens |
| §2: the PKCE flow and the curl script | NOT MEASURED | needs a login |
| the Postman notes (redirects, `X-Csrf-Token`) | NOT MEASURED | needs a login; `local-development/cluster-report.py` lines 107-130 record the same measurements |
| `./cluster-report.py --clusters … --domain … --ldap-user …`; the password only in `GSD_PASSWORD`, no `--password` | CORRECT | `local-development/cluster-report.py` lines 421-441 and 468-471; the file is executable |
| one token exchange per cluster | CORRECT (read) | `cluster-report.py` builds the token per cluster |
| the prefix map covers `/api` only | CORRECT | the rendered `delegate-urls` names `/api` alone |
| `/api` is Swagger UI, `/api/redoc`, `/api/openapi.json`, behind the same authentication | CORRECT | `local-development/gsd/api.py` lines 929-931, 3405-3424; `skipAuthRegex` does not name `/api` |

## `docs/guides/api-contract.md`

| claim | verdict | evidence |
|---|---|---|
| the schema at `/api`, `/api/docs` (redirect), `/api/redoc`, `/api/openapi.json` | CORRECT | `local-development/gsd/api.py` lines 931 and 3405-3430; the alias answers 308 to `/api` (`test_the_alias_redirects_rather_than_duplicating`) |
| `tests/test_api_contract.py` enforces every numbered rule | FIXED | it has tests for R1, R2, R3, R5, R6 and R7 and none for R4 (no `R4` and no time-zone check in the file). Now "except R4" **Found by Codex's review:** R6's fixtures use the `Settings` default, housekeeping off, so the housekeeping routes are never in the set it holds. The guide now says R6 is enforced with housekeeping off. |
| `skipAuthRegex` admits `^/(healthz\|readyz\|metrics)$` and nothing else | FIXED | `values.yaml` line 2112 and the render: `^/(healthz\|readyz\|metrics\|signed-out\|static/(app\.css\|favicon\.svg))$`. Now quotes it |
| R1 and R2 | CORRECT | held by `test_r1_*` and `test_r2_*`; `namespace` describes `'(cluster-scoped)'` (`api.py` line 2620) |
| R3: `limit`/`offset`, `total` before the limit, `truncated` | CORRECT | held by `test_r3_a_paged_response_admits_when_it_is_partial` |
| R3: the 167 and 364 days | NOT MEASURED | historical |
| R4: no endpoint returns a local time | NOT MEASURED | no test checks it, and it was not checked endpoint by endpoint here |
| R5 and `tests/test_read_snapshot_scope.py` | CORRECT | `test_r5_*`; the file exists |
| R6: "The ServiceAccount is read-only by design" | FIXED | the API registers write routes in two opt-in sets: six behind `clusterConfig.secrets.writes.enabled` (`test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on`) and the housekeeping writes behind `housekeeping.enabled` (`api.py` line 1511), which the chart turns on (`values.yaml` line 1180); the ServiceAccount also writes Leases and creates reviews (the `ACCESS_CONTROL.md` §2 row). Now: the API is read-only by design with those two opt-in exceptions **Found by Codex's review:** housekeeping is on by default in the chart (`values.yaml` lines 1179-1180), so it is not opt-in; the guide now gives both switches' defaults and the four housekeeping write routes. |
| R6: the write path was built, measured and removed over privilege-escalation prevention | CORRECT | `docs/design/unmanaged-audit-design.md` lines 53-92 |
| R7: "There is exactly one today: the `/api/docs` redirect" | FIXED | five routes carry `include_in_schema=False`: `/api`, `/api/redoc`, `/api/docs`, `/static/index.html`, `/static/signed-out.html` (`api.py` lines 3405, 3418, 3428, 3536 and 3540); `test_access_declaration.py` says five too. Now names them |
| citing code: `path#anchor`, resolved through the AST, `path:123` fails | CORRECT | `local-development/tests/test_docs_citations.py` (`CITATION`, `LINE_NUMBER_CITATION`); `Store.groups` exists (`store.py` line 4532); `templates/rbac.yaml` contains `leases` |
| the rot measurements (219 citations, eight wrong, one off by 42) | NOT MEASURED | historical |
| step 4: `pytest tests/test_api_contract.py` | CORRECT | it runs and passes from `local-development/` |
| handlers return `dict`; responses are not schema-typed | CORRECT | no `response_model` in `local-development/gsd/api.py` |
| `docs/guides/reference-architecture.md` carries the data model | CORRECT | the file exists |

## Findings for the orchestrator (no change made)

1. **The auditor persona now reads Logins that `oc` would not give it.** `ACCESS_CONTROL.md` §2 justified
   serving Logins at the wide tier on the grounds that `cluster-reader` could read the same records with
   `oc`. Since chart 0.58.0 the records come only from the oauth-server audit log, which needs
   `get nodes/proxy`; the lab's `cluster-reader` lacks it, and the oauth-server pod log at the default
   level names no login. The guide now says so. Whether Logins should stay at the wide tier is a design
   decision; the code serves it wide (`/api/clusters/{cluster_id}/logins`, gate `viewer_scope`).
2. **The chart README repeats the "no read check" sentence.** `charts/group-sync-dashboard/README.md`
   line 372 says "No *read* check separates `cluster-admin` from `cluster-reader` (the latter may read
   everything)". `get secrets` does separate them (the table in `ACCESS_CONTROL.md` §2, and the lab's
   `cluster-reader` has no `secrets` rule). Chart files are out of this batch's scope.
3. **The default auditor binding makes its members wide.** `rbacAuditors` is on by default and binds
   `get`/`list` on `clusterrolebindings` to `app-ocp-rbac-groupsync-ns-auditor`, which is the wide tier's
   default question. The chart README's `rbacAuditors.enabled` row says this is deliberate (the wide report
   tier). On the lab it moved `jane.smith` and `lateef.o` off the self tier, so the lab now has no ordinary
   LDAP persona on the self tier (`john.doe` is self, but only because his Group binds `admin`).
4. **A test gap on R6.** `test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on`
   builds the app with `Settings` defaults, where `housekeeping_enabled` is False (`config.py` line 782),
   so the housekeeping write routes the chart turns on are never in the set it holds exactly. Its file's R6
   docstring (`local-development/tests/test_api_contract.py` line 242) also says "the ServiceAccount is read-only by design".

## The open question, settled from the code

`LOGIN_CAPTURE_QUICKCHECK.md` said a wrong password cannot be told from a locked account; `AUDIT_LOG_CAPTURE.md` §6
says a locked account answers HTTP 500. The parser keeps the HTTP status and message and no LDAP code, so a 500 is
distinguishable from a 401 or 302 in stored data, but it does not by itself prove the account was locked. The quickcheck
now says that. A live locked-account login was not re-measured.
