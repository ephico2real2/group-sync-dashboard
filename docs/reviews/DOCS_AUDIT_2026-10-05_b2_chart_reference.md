# Docs content audit, batch 2 of 6: the chart README and the backup/restore runbook

Phase 2 of the documents pass, second batch. The chart's reference page,
`charts/group-sync-dashboard/README.md`, and `charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md`
were read in full, and every checkable claim was measured against main at ef482dbf (application 5.3.0,
chart 0.70.5). The evidence comes from:

- the chart's values and templates, rendered with `helm template` (Helm v4.3.0);
- the application under `local-development/gsd/`, run in place where a claim is about its behaviour (the
  loader `load_settings` on a rendered ConfigMap, `Store.backup`, the offsite script, the runbook's own
  Python snippets on a local database);
- the tree;
- the lab (CRC, namespace `group-sync-dashboard`), read-only with `oc get`.

No restore step was run: they are cluster writes. What only a live restore could prove is marked NOT
MEASURED. Line numbers are given outside backticks and are those of ef482dbf.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the page now says what the evidence shows.
- **NOT MEASURED**: no measurement was possible here (a historical value, a tool that is not installed, or a
  step that needs a cluster write). It was left unchanged.
- **CODE-SUSPECT**: the page is right and the code is not. This batch found none.

The repository has no `values.schema.json`, so value types and defaults were read from
`charts/group-sync-dashboard/values.yaml`. Every default in the README's tables was compared, key by key,
with a flattened `values.yaml` (338 leaves). All of them match. Of the counts the README states, two do
not: the reports row and the number of stanza refusals (below).

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `README.md` (chart) | 120 | 15 | 12 | 0 |
| `RUNBOOK_backup_restore.md` | 58 | 8 | 7 | 0 |

## `charts/group-sync-dashboard/README.md`

| claim | verdict | evidence |
|---|---|---|
| defaults install with `oauthProxy.enabled=true` | CORRECT | `values.yaml`: `oauthProxy.enabled: true` |
| plain Kubernetes: the listed switches render a working install | FIXED | With only the listed switches, the render failed. Measured with `--set route.enabled=false,ingress.enabled=true,oauthProxy.enabled=false,trustedCA.injected.enabled=false,loginCapture.enabled=false,ingress.host=…`: `reporting.enabled=true requires oauthProxy.enabled=true`. With `reporting.enabled=false` added: `visibility.enabled=true requires oauthProxy.enabled=true`. With both added, rc=0. The page now names both switches |
| `loginCapture.enabled=false` because "its Role lives in `openshift-authentication`" | FIXED | The default render has no object in `openshift-authentication`. Capture is a ClusterRole, `group-sync-dashboard-login-capture-audit`, with `get nodes/proxy` and `list nodes`, reading the OAuth server's audit log (`loginCapture.source: audit-log`). The page now gives that reason |
| ServiceMonitor and PrometheusRule are on by default; the Grafana board is a plain ConfigMap | CORRECT | `values.yaml` `monitoring.*`. The render has `ServiceMonitor` ×2, `PrometheusRule` ×1, and ConfigMap `group-sync-dashboard-grafana-dashboard` |
| `oc logs job/<release>-openshift-grafana-wait`; Route label `app.kubernetes.io/name=openshift-grafana` | CORRECT | `helm template grafana charts/openshift-grafana`: Job `grafana-openshift-grafana-wait`, and a Route labelled `app.kubernetes.io/name: openshift-grafana` |
| "Seventeen bad stanzas fail `helm template`", four refused only at startup | FIXED | `docs/CLUSTER_STANZA.md` §5, which this paragraph summarises, has 21 rows refused at render (batch 1 corrected the guide to twenty-one). Now: twenty-one |
| the links to the cluster guides, `example-production.yaml`, the examples and the design pages | CORRECT | every relative link and every `#anchor` resolves (a link checker over both pages) |
| the image table's defaults; digest wins over tag; a malformed digest fails the render | CORRECT | `values.yaml` `image.*`; `charts/group-sync-dashboard/templates/_helpers.tpl` lines 84-93 (batch 1) |
| `build-and-push-external.sh --update-values` writes `image.repository` | CORRECT | `local-development/build-and-push-external.sh` lines 14, 61 and 301 |
| the authentication table's defaults (proxy image, port, `cookie.expire`, `proxyPrefix`, `skipAuthRegex`, resources) | CORRECT | `values.yaml` `oauthProxy.*`, `session.idleTimeout.*` |
| `cookieSecret` set: the Secret renders with `keep`, and `Prune=false,Delete=false` under Argo | CORRECT | render: Secret `group-sync-dashboard-oauth-session` with `{'helm.sh/resource-policy': 'keep', 'argocd.argoproj.io/sync-options': 'Prune=false,Delete=false'}` and the key `session_secret` |
| a values file that sets `oauthProxy.cookie.refresh` is refused | CORRECT | render: `oauthProxy.cookie.refresh has been removed and must not be set` |
| the idle timeout: refused without the proxy, with minutes not under the cap, or warningSeconds below 5 or not under the window | CORRECT | four renders, each refused with its message (`templates/deployment.yaml` lines 19, 25 and 148) |
| no `redirectMode` key | CORRECT | `values.yaml` has no such key; setting it renders without error, as the page implies ("read by nothing") |
| with the proxy on: the Ingress is `reencrypt`, the app binds `127.0.0.1`, the probes go to the proxy | CORRECT | render: `route.openshift.io/termination: "reencrypt"` (`edge` with the proxy off); `--host 127.0.0.1`; liveness `httpGet` on port 8443, `HTTPS` |
| the trusted-CA table's defaults; `subjectHash` mounts `/etc/pki/tls/certs/<hash>.0` | CORRECT | `values.yaml` `trustedCA.*`; with `subjectHash=c275f070`, the render mounts `/etc/pki/tls/certs/c275f070.0` |
| the bundles reach the proxy as `-openshift-ca` paths | CORRECT | render: three `-openshift-ca=` arguments (the ServiceAccount CA, injected, enterprise) |
| curl: `.curlrc` under `CURL_HOME=/etc/curl`, `cacert` = injected, `capath` = `/etc/pki/tls/certs` | CORRECT | rendered ConfigMap `group-sync-dashboard-curlrc`; env `CURL_HOME: /etc/curl` |
| the tests `TestCurlInThePodTrustsWhatTheAppTrusts` and `TestTheProxyTrustsTheSameCAsTheApp` exist | CORRECT | `local-development/tests/test_chart_strategy.py` lines 926 and 354 |
| curl 7.76/8.22 ignore `SSL_CERT_DIR` with `CURL_CA_BUNDLE` set | NOT MEASURED | historical measurement |
| the application table's defaults (intervals, timeout, cliff, `kpi`, `grafana`, `console`, log levels, `ui.export`) | CORRECT | `values.yaml`, key by key |
| `clusters[].visibility` and `identity` defaults for a remote | CORRECT | `local-development/gsd/config.py` `remote_policy`: neither key gives `remote-sar` + `same-as-host`; `identity: none` alone gives `self-only`. Loaded through `load_settings`: `hidden` and `remote-sar` on the host are refused, and `remote-sar` + `identity: none` is refused |
| the 0.53.0 upgrade note | CORRECT | `docs/CHANGELOG.md` line 863 (application 0.32.0, chart 0.53.0) |
| the cliff: a ratio outside `(0, 1]`, a floor below 1 or a non-positive window refuse the render | CORRECT | renders with 0, 1.1, `minMembers=0` and `windowHours=0` are refused; 1 renders |
| `kpi.thresholds.*` outside `(0, 100]` "refuses the render" | FIXED | The chart has no guard: `--set kpi.thresholds.diskPercent=101` (and `=0`) render with rc=0. The pod refuses it: the rendered ConfigMap loaded through `load_settings` raises `ConfigError kpiDiskWarnPercent must be a percentage in (0, 100]; got 101.0` (`local-development/gsd/config.py` lines 1599-1601), and 100 loads. Now: it renders, and the pod refuses it at startup |
| `grafana.url` / `console.url`: a `javascript:` or scheme-less value, or a query, refuses the render | CORRECT | renders refused: `grafana.url must be an http(s) URL with a host and no query or fragment` |
| `logLevel`: five values, any case, anything else refused at render; at startup an invalid value runs at INFO with a warning | CORRECT | `logLevel=debug` renders; `TRACE` and `WARN` are refused. `local-development/gsd/api.py` `_resolve_log_level` (line 3578) returns INFO and a complaint |
| `httpLogLevel` is governed separately; `GSD_DEBUG_HTTP=true` restores `httpcore` | CORRECT | `local-development/gsd/api.py` lines 3697-3699; the env vars `GSD_LOG_LEVEL` and `GSD_HTTP_LOG_LEVEL` are on the rendered Deployment |
| `clusterConfigLogLevels`: `root` is refused, and a bad entry is skipped with a warning rather than failing | CORRECT | it renders (`root=DEBUG`, rc=0); `local-development/gsd/api.py` line 3773: "`root=…` is skipped with a complaint" |
| exactly one line can emit CRITICAL | CORRECT | the only `log.critical(` under `local-development/gsd/` is `poller.py` line 1354 |
| the 1 082 of 1 784 lines, and 356 framing lines per 10 | NOT MEASURED | historical lab measurements |
| `nameOverride`/`fullnameOverride` rename the PVC | CORRECT | the PVC name is `<fullname>-data` |
| `config.backup.enabled=false` omits `backupDir`/`backupIntervalHours`/`backupKeep` | CORRECT | the rendered `clusters.yaml` has the three keys when on and none when off |
| backups are taken on the poll thread and once at startup; `VACUUM INTO` | CORRECT | `local-development/gsd/poller.py` lines 948 (`_next_backup = 0.0`) and 977-1011; `local-development/gsd/store.py` line 1794 |
| the pre-upgrade copy: taken whether backups are on or off, the newest three kept | CORRECT | `local-development/gsd/store.py` lines 1185 (`PRE_UPGRADE_KEEP = 3`) and 1229-1315, called from `Store.__init__` before any migration |
| housekeeping: the cluster-admin tier, the audit lines, the metric; off registers no delete route | CORRECT | `local-development/gsd/api.py` lines 1500 and 1507 (`report-run-deleted`, `db-copy-deleted`) and 1511 (`if settings.housekeeping_enabled`); `local-development/gsd/metrics.py` line 730 |
| `backup.offsite.enabled` as a word: empty renders nothing (and fails nothing) in each of the five listed cases; `true` refuses each one; `false` or `"false"` is off; any other word is refused | CORRECT | Renders: with `persistence.enabled=false`, `config.backup.enabled=false`, an empty `config.backup.dir`, `/var/backup`, `persistence.existingClaim` with `accessMode` empty, or `ReadWriteOncePod`, the empty value renders no CronJob, and `true` is refused with the reason. `yes` is refused. `false` and the quoted `"false"` render no CronJob |
| the offsite table's defaults | CORRECT | `values.yaml` `backup.offsite.*`; the rendered CronJob has schedule `15 */6 * * *`, `Forbid`, 3/3, 900, 1800 and `backoffLimit: 1` |
| `existingClaim` naming the data claim is refused; s3 needs a Secret and an image | CORRECT | renders: `… is the data claim itself`; `type=s3 requires …existingSecret`; `requires an image with an S3 CLI` |
| the bind Job: `<fullname>-backup-offsite-bind-<hash>`, the dashboard image, fails after 600 s; an Argo `Sync` hook in wave 0, deleted on success; the CronJob in wave 1; no bind Job with `existingClaim` | CORRECT | render: Job `group-sync-dashboard-backup-offsite-bind-7fa08e0c`, `activeDeadlineSeconds: 600`, `argocd.argoproj.io/hook: Sync`, wave `"0"`, `BeforeHookCreation,HookSucceeded`; CronJob wave `"1"`; with `existingClaim=mine`, no bind Job |
| the CronJob pod is pinned by required `podAffinity` under RWO, runs anywhere under RWX, and does not carry the Service's selector | CORRECT | RWX render: `affinity: null`. RWO: `requiredDuringScheduling…` on `kubernetes.io/hostname`. The pod's labels have no `app`, and the Service selects `app: group-sync-dashboard` |
| the pre-upgrade pass ships to `/offsite/pre-upgrade` at one replica with `pvc`, keeping three | CORRECT | render: `--pre-upgrade-source /data/pre-upgrade` only when `replicaCount` is 1 (`templates/backup-offsite.yaml` line 294); `charts/group-sync-dashboard/scripts/offsite_backup.py` lines 53-54 |
| retention defaults; the prune runs after a successful backup, 5,000 rows per table per cycle, counted in `gsd_retention_rows_deleted_total{table}` | CORRECT | `local-development/gsd/poller.py` lines 891 and 1038-1062; `local-development/gsd/metrics.py` line 713 |
| the membership cutoff is the earlier of the window and the cliff's edge | CORRECT | `local-development/gsd/poller.py` lines 1080-1082 |
| before restoring an old copy, "set both windows to `0`" | FIXED | The same backup-gated loop also prunes `kyverno_result_event` on `kyverno.eventsRetentionDays` (default 90; `local-development/gsd/poller.py` line 1050), and `local-development/gsd/logincapture.py` line 69 prunes `login_event` on `loginCapture.retentionDays` (400) with no backup gate. Both would cut an old copy's history. The paragraph now names both |
| the usage-tracking defaults; an unrecognised `visibility` reads as `self` | CORRECT | `values.yaml` `config.userActivity.*`; `local-development/gsd/config.py` lines 1270-1275 |
| `visibility.enabled` reaches the app as `GSD_ENABLE_VIEW_RESTRICTIONS`, and with the proxy off the render is refused | CORRECT | the env var is on the rendered Deployment; the proxy-off render is refused (above) |
| `tierTtlSeconds`: a fractional or negative value fails the render; 0 renders | CORRECT | renders with 1.5 and -1 are refused; 0 renders |
| the three SAR defaults; a miscased or versioned shape fails the render | CORRECT | renders refused for `ClusterRoleBindings`, `rbac.authorization.k8s.io/v1` and `Update` |
| `clusterConfigViewSar` / `clusterConfigManageSar` are refused by name | CORRECT | render: `visibility.clusterConfigViewSar was removed in chart 0.57.0 (#322)` |
| the cluster-admin tier gates the tab and the KPI page; "Rejoin (#316) when it lands" | FIXED | Rejoin has landed: `local-development/gsd/api.py` line 1403 registers `POST /api/clusterconfigs/{name}/rejoin` behind `_writes_gate`, which calls `require_cluster_admin` (line 1222). Now: "Rejoin (#316) too" |
| the `auth-delegator` binding renders whenever the proxy is on, `visibility.enabled` false included | CORRECT | render with `visibility.enabled=false`: 1; with the proxy off: 0 |
| eleven reports | CORRECT | the render's refusal lists eleven catalogue names: `access-certification … users` |
| "`true` for nine; `loginActivity` `""`" | FIXED | `values.yaml` lines 1403-1414: ten reports default `true`, and `loginActivity` defaults to `""`. The count was nine from the commit that added it (49da17da). Now: ten |
| reporting is refused with the proxy off, `persistence.enabled=false`, `replicaCount>1`, `rbac.bindings=false`, or a data claim that is not RWX | CORRECT | five renders, each refused with its message |
| the reporting table's defaults; an unknown PDF variant, a snapshot interval below 60, and a ticket TTL outside 30..3600 are refused | CORRECT | `values.yaml` `reporting.*`. Renders: `pdf/a-9` is refused. Snapshot interval 59 is refused, 60 renders. Ticket TTL 29 and 3601 are refused, 30 and 3600 render |
| `loginActivity=true` with capture off is refused; any other word is refused | CORRECT | renders: `…loginActivity.enabled=true requires loginCapture.enabled=true`; `yes` and `groups=""` are refused |
| `pdf` in the scheduled formats, in a schedule's `formats` or as `attach` refuses the render; an unknown manual format refuses startup | CORRECT | the three renders are refused with `PDF is for manual runs`. `formats.manual=[html,xml]` renders, and `local-development/gsd/reporting/config.py` lines 90-92 exit at startup |
| a schedule with `enabled: false` is suspended; the report must be an enabled catalogue name; the name must be a DNS label; a webhook needs `webhookUrlSecret.name` | CORRECT | render: `spec.suspend: True`; three renders refused with their messages |
| the schedule Job's pods are `component: report-schedule`, and the NetworkPolicy is `policyTypes: [Ingress]` | CORRECT | rendered CronJob pod labels; rendered NetworkPolicy |
| the token Secret `<reportName>-shared-token`, minted by the hook, never rendered | CORRECT | the hook's Role `resourceNames` and `templates/secrets-mint.yaml` lines 242-244; no Secret in the default render |
| the ticket key: `<reportName>-ticket-key`, key `key`, 48 characters; the report pod verifies `previous`; a schedule Job never mounts it | CORRECT | `templates/secrets-mint.yaml` line 244 (`key 48`). The dashboard mounts `items: [key]`, and the report pod mounts the whole Secret. The schedule Job's volumes have the token only. `local-development/gsd/reporting/server.py` line 95 logs `ticket key loaded` / `; a previous key too: a rotation is open` |
| the rotation commands | NOT MEASURED | they write a Secret; the names they use match the render |
| `-upstream-ca` is present in `ose-oauth-proxy-rhel9:v4.15` | NOT MEASURED | needs an exec into the proxy; the render passes `-upstream-ca=/etc/gsd/service-ca/service-ca.crt` |
| the workload table's defaults (replicas, strategy, election, PDB, SQLite, persistence, resources, probes, security context) | CORRECT | `values.yaml`; the render has `strategy: Recreate` at one replica |
| `recovery.enabled`: the app to 0 and `<fullname>-recovery` to 1, the same pod spec and `/data`, no probes, no Service selects it; refused with `replicaCount` other than 1 or without persistence | CORRECT | `--set recovery.enabled=true`: replicas 0 and 1. The recovery pod runs `python3.14 /scripts/recovery_mode.py`, has no probes and carries `app: group-sync-dashboard-recovery`, which the Service selector (`app: group-sync-dashboard`) does not match. `replicaCount` 2 and 0, and `persistence.enabled=false`, are refused |
| each pod is scheduled only once the other's is gone | CORRECT | required pod anti-affinity in both directions on the rendered pods |
| `recovery.ttl`: refused when not a duration or zero | CORRECT | with `recovery.enabled=true`: `two`, `0s` and `0` are refused, `1h30m` renders (the guard runs only while recovery is on) |
| the TTL is kept in `/tmp`, on the monotonic clock; a node restart counts as reached; exit 1 at the TTL | CORRECT | `charts/group-sync-dashboard/scripts/recovery_mode.py` lines 15-19, 124-133 and 136-146 |
| the recovery Deployment and ConfigMap render on every release at 0 replicas; `/offsite` is mounted read-only | CORRECT | default render: Deployment `group-sync-dashboard-recovery` with replicas 0, and ConfigMap `group-sync-dashboard-recovery`; the recovery pod mounts `/offsite` with `readOnly: True`. Lab: `deployment.apps/group-sync-dashboard-recovery 0/0` |
| `ReportSnapshotStale` fires after four snapshot intervals plus `for` (about 50 minutes) | CORRECT | rendered rule: `gsd_report_snapshot_age_seconds > 1200`, `for: 30m` |
| the networking table; both flags on fails the render | CORRECT | `values.yaml` `route.*`, `ingress.*` and `service.*`; render: `route.enabled and ingress.enabled are both true` |
| the Route has no host at render; on CRC `group-sync-dashboard.apps-crc.testing`; `spec.host` stays empty | CORRECT | lab: `host=[] subdomain=[group-sync-dashboard] status=[group-sync-dashboard.apps-crc.testing] term=[reencrypt]` |
| the SA's OAuth annotation: `oauth-redirectreference` with the Route, `oauth-redirecturi` otherwise | CORRECT | lab ServiceAccount carries `serviceaccounts.openshift.io/oauth-redirectreference.primary`; the Ingress render carries `oauth-redirecturi` |
| `rbac.create` renders the ClusterRole, its binding and the `-leases` Role/RoleBinding, and `false` none of them; the Role renders with election or a fleet account | CORRECT | renders: with `rbac.create=false` none of the four. With `leaderElection.enabled=false` and no fleet, no `-leases`. With `clusterConfig.fleetAccount.username=svc` it renders. Its rule is `get`, `create`, `update` on `leases` |
| every rule in the ClusterRole is `get`/`list`; bindings and users rules follow their switches; `namespaceconfigs`/`groupconfigs` are unconditional; no `roles`/`clusterroles` | CORRECT | the rendered `group-sync-dashboard-reader` rules. With `rbac.bindings=false,rbac.users=false`, those two rules go and `namespaceconfigs`/`groupconfigs` stay |
| no `"patch"` renders at any `unmanagedAudit.mode` | CORRECT | `off`, `log` and `annotate` all give 0 matches |
| the audit grant: `get nodes/proxy`, plus `list nodes` unless `nodeNames` pins them | CORRECT | default render: both rules. With `nodeNames=[n1]`, `nodes/proxy` is limited to `resourceNames: ["n1"]` and there is no `list nodes` |
| `rbac.identities` requires `rbac.users`; the auditor role's switches are exclusive | CORRECT | renders refused with their messages |
| the auditor ClusterRole's resources; the default group binding | CORRECT | render: `users`, `groups`, `roles`, `rolebindings`, `clusterroles` and `clusterrolebindings` with `get`/`list`; ClusterRoleBinding to Group `app-ocp-rbac-groupsync-ns-auditor` |
| the kyverno grant: `list` on the report groups and the CEL kinds with their namespaced twins | CORRECT | render: `wgpolicyk8s.io` and `openreports.io` reports, and ten `policies.kyverno.io` resources (five, and their namespaced twins) |
| `namespaceMetadata.labels` and `namespaceGroupLabel` need `rbac.namespaces`; the selector must be a subset | CORRECT | three renders refused with their messages |
| `writes.enabled`: "its only write anywhere is its own leader Lease" | FIXED | The dashboard also writes the fleet account's Lease (#285): `rbac.create` renders the `-leases` Role for a fleet account, and the lab holds Lease `gsd-fleet-666f1ba7f2fdead0`. The page's own §"OAuth Debug migration" paragraph already says so. Now: its own Leases, the leader election's and a fleet account's. The same stale sentence is in `values.yaml` line 1683 (not changed here) |
| writes off registers no write route (a POST is a 405) | CORRECT | `local-development/gsd/api.py` line 1319: `if writes_on:` registers the POST/PUT/DELETE routes |
| the monitoring table's defaults; twenty alerts | CORRECT | `values.yaml` `monitoring.*`. The default render has 20 `- alert:` rules; every alert row's `for` matches `values.yaml` `for.*` |
| the Grafana dashboard ConfigMap is labelled `grafana_dashboard: "1"`, carries the JSON byte-for-byte, and the folder is an annotation | CORRECT | render: the label is `1`; `cmp` of the rendered key against `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json`: byte-identical; `folder=Ops` gives `grafana_folder: Ops` |
| `grafanaDashboard.enabled` `""` follows the ServiceMonitor; any other word is refused | CORRECT | with `serviceMonitor.enabled=false`: no ConfigMap; `maybe` is refused |
| the CR renders only with `grafana.integreatly.org/v1beta1`; an empty selector or datasource is refused | CORRECT | without `--api-versions`: 0, with: 1; `instanceSelector=null` and `datasource=` are refused |
| `argocd.enabled` "adds the `argocd.argoproj.io/sync-options` annotations below, and nothing else — measured" | FIXED | `diff` of the default render against `--set argocd.enabled=false`: besides the sync-options, the switch also removes `sync-wave: "0"` from the offsite claim, the bind Job's `hook: Sync`, `sync-wave: "0"` and `hook-delete-policy`, and the CronJob's `sync-wave: "1"`. No object is added or removed, and the `secrets-mint` hook annotations do not change. Now the row names the offsite annotations too |
| Argo CD source citations (`util/helm/cmd.go` …, read 2026-09-19) | NOT MEASURED | upstream source, not re-read |
| `authLogLevel`, `loginCapture.source: pod-log` and `loginCapture.namespace` fail the render with guidance | CORRECT | three renders refused with migration messages |
| the `<fullname>-leases` Role/RoleBinding table | CORRECT | rendered Role and RoleBinding `group-sync-dashboard-leases` |
| the 175 rule sets and the escalation measurement | NOT MEASURED | historical lab measurement |
| the platform defaults; globs, a string, an empty ConfigMap name, and a ConfigMap beside a list are refused | CORRECT | `local-development/gsd/home.py` lines 38-39; `local-development/gsd/config.py` lines 237-251. Four renders refused with their messages |
| "The dashboard's only write on any cluster is its own leader-election Lease" | FIXED | as above: the fleet account's Lease, and Secrets with `writes.enabled`. Now says both |
| `unmanaged`: the label, the annotation, the citations `store.py#Store._FINDING_CASE` and `kube.py#_user_binding_views` | CORRECT | `local-development/gsd/store.py` line 2837; `local-development/gsd/kube.py` line 1804 |
| the finding line and its WARNING level; the RESOLVED line | CORRECT | `local-development/gsd/poller.py` lines 857-863 and 875-881, worded as the page's examples |
| the summary: "The first number is how many were listed … gains `, K not yet listed (per-cycle cap)`" | FIXED | `local-development/gsd/poller.py` lines 836-843: the number is `len(plan.stamp) + plan.capped`, every finding not already labelled (the comment at lines 826-835), and the suffix is ` (N listed below, K held back by the per-cycle cap)` (commit 7ed93bc8). Now says so, and the `maxPerCycle` row's "not yet listed" became "held back by the per-cycle cap" |
| `mode` defaults to `log`; an unknown word runs `off`; `annotate` runs as `log` with a warning | CORRECT | `values.yaml` line 456; the rendered `unmanagedAuditMode: "log"`; `local-development/gsd/config.py` lines 1050-1072 |
| "The default is `off` so a fresh install is silent" | FIXED | It contradicted the row above it. The chart renders `log`. The application's own default, with the key absent, is `off` (`local-development/gsd/config.py` line 1050). Now says that |
| resolutions are never capped | CORRECT | `local-development/gsd/audit.py` `plan_audit_stamps`: `unstamp` is not truncated |
| at most four combinations are refused at template time (the Scaling table) | CORRECT | renders: `replicaCount=2` with election, `replicaCount=2` with RWO, and `RollingUpdate` at one replica (RWX or RWOP) are refused; `replicaCount=2` on RWX without election renders |
| above one replica: `/data/$POD_NAME/gsd.db`, per-pod backup names and `keep` per replica | CORRECT | `local-development/gsd/storage.py` lines 465-488 (`backup_owner`, `backup_copies`); `local-development/gsd/store.py` line 1783 |
| the lease: 30 s, renewed every 10 s; outside a cluster the elector assumes sole instance | CORRECT | `local-development/gsd/leader.py` lines 67-68 and 258 |
| `oc get lease` names the holder | CORRECT | lab: Lease `group-sync-dashboard`, holder `group-sync-dashboard-5dbcc47695-plxmq` |
| the PDB selects the Deployment's pods only; the mint Job's pods lack the `app` label | CORRECT | render: the PDB selector includes `app: group-sync-dashboard`; the mint pod's labels are `name`, `instance` and `component` |
| the RWOP scheduler message; the busy_timeout timings on UBI9 SQLite 3.34.1 | NOT MEASURED | historical measurements |
| the WAL mode is read back and logged at ERROR; TRUNCATE checkpoint past `walCheckpointMb` | CORRECT | `local-development/gsd/store.py` lines 1451-1462 and 1695-1706 |
| the Route vs Ingress table, argo-cd#20305, the 4.11 caveat, verified on CRC 4.18.2 | NOT MEASURED | historical and upstream; the lab Route today matches the table (above) |
| the Application example's object names | CORRECT | they match the render (`group-sync-dashboard-trusted-ca`, `-data`, `-report-artifacts`, the ServiceAccount, the Route); the lab Application carries the same five `ignoreDifferences` entries |
| "the reference cluster has the Argo CRDs installed but no controller running" | NOT MEASURED | historical; the lab runs Argo CD today (Application `group-sync-dashboard`, `Synced Healthy`) |
| Flux and Kustomize examples: `dependsOn`, `timeout: 15m`, `includeCRDs`, `apiVersions`; `tests/test_chart_renderers.py` | CORRECT | `examples/flux/helmrelease.yaml` lines 60 and 88; `examples/kustomize/kustomization.yaml` line 24; the test exists |
| Flux ≥ 2.3; validated against the upstream CRD schemas | NOT MEASURED | Flux is not installed here |
| `--reuse-values` and the `apiTokenAccess` measurement | NOT MEASURED | needs an upgrade of a release; historical |
| the `0.7.0-db8a90510f` tag and the `skopeo inspect` digest | NOT MEASURED | historical; skopeo is not installed |
| an older chart's values without `recovery` still render | CORRECT | a copy of the chart with the `recovery:` block deleted from `values.yaml` renders, rc=0 (`templates/_helpers.tpl` line 332 reads `(.Values.recovery \| default dict)`) |
| uninstall: "The PVC is **not** removed with the release" (the data claim only) | FIXED (added) | The render gives `helm.sh/resource-policy: keep` to three claims: `-data`, `-report-artifacts` and `-backup-offsite`. The page named only the data claim, so after `oc delete pvc …-data` two claims remained. Now it names the other two |
| the minted Secrets and the hook's ServiceAccount, Role and RoleBinding survive an uninstall; their names | CORRECT | the hook objects carry `helm.sh/hook-delete-policy: before-hook-creation`; the names match the Role's `resourceNames` and the render |
| "**The dashboard never writes**; a SubjectAccessReview only asks" (the `usageAdminSar` and `clusterAdminSar` rows) | FIXED | **Found by Codex's review.** The dashboard writes its Leases and, with writes on, cluster Secrets (the rows above). Now: it never performs the `update` those reviews ask about |
| `config.unmanagedAudit.mode`: "the ServiceAccount stays read-only … its only binding verbs are `get` and `list`" | FIXED | **Found by Codex's review.** The rendered Role has `leases` `create`/`update`, the `-auth-delegator` ClusterRoleBinding grants `subjectaccessreviews` `create` (`templates/rbac.yaml` line 241), and `local-development/gsd/kube.py` posts the review (line 1379). Now: discovery uses `get`/`list`; the other verbs are the ones the unmanaged-grant section names, which now also names the SubjectAccessReviews |

## `charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md`

| claim | verdict | evidence |
|---|---|---|
| `config.backup` writes `gsd-<UTC stamp>Z.db`, and `gsd-<stamp>Z-<pod>.db` above one replica; `keep` per replica; at one replica `keep` bounds every copy | CORRECT | `local-development/gsd/store.py` line 1783; `local-development/gsd/storage.py` lines 465-488 |
| the off-volume copy carries a `.sha256` sidecar and is checked; the citation `offsite_backup.py#ship` | CORRECT | `charts/group-sync-dashboard/scripts/offsite_backup.py` line 187 and lines 233-238 (`write_sidecar_part` at line 235) |
| the pod has `sh`, `cat`, `ls`, `rm`, `chgrp`, `chmod`, `python3.14`, and no `tar` | FIXED | `local-development/Containerfile` lines 73-81 pack `bash` (as `sh`), `curl`, `jq` and the coreutils shims `cat`, `ls`, `base64`, `mkdir`, `chgrp`, `chmod`, `rm`, `rmdir`, with no `tar`. The runbook itself runs `curl` in the pod (§0, §4c), but the list left it out. Now the list includes `curl` |
| no `sleep`, no `grep`/`tail` in the pod | CORRECT | none of them is packed (same lines) |
| the citation `DESIGN_hardened_image.md#What it changed for operators` | CORRECT | `docs/design/DESIGN_hardened_image.md` line 324, §10 |
| §0: a `**Schema N → M.**` line; `prepare-release.py#SCHEMA_LINE` | CORRECT | `local-development/prepare-release.py` line 70 |
| §0: the `/metrics` grep prints `gsd_build_info{branch=…,commit=…,version=…} 1.0` and the two volume gauges | CORRECT | `local-development/gsd/metrics.py` lines 321-331 (labels `version`, `commit`, `branch`); `prometheus_client` prints them sorted (measured: `gsd_build_info{branch="main",commit="abc",version="5.3.0"} 1.0`); `local-development/gsd/kpi/definitions.py` lines 165-171 |
| §0: `from gsd.store import KNOWN_SCHEMA_VERSION` prints the image's schema | CORRECT | run here: `20` |
| §0: `StoreSchemaTooNew` and `_migrate` | CORRECT | `local-development/gsd/store.py` lines 1167 and 1317 |
| §0 step 2: `oc get cronjob $REL-backup-offsite`; the Job's log lines `copied`, `integrity_check ok; user_version`, `already shipped` | CORRECT | lab: `cronjob.batch/group-sync-dashboard-backup-offsite`. The script, run here twice on a local backup: `copied … -> …`, `integrity_check ok; user_version 20; …`, then `already shipped: … matches its sidecar; nothing to copy` |
| §0 step 3: the copy refuses to start below the database's size; `/data/<pod>/pre-upgrade` above one replica | CORRECT | `local-development/gsd/store.py` lines 1241 and 1276-1279 (`page_count × page_size`, WAL included) |
| the KPI page's Backups card and its five states (stale past two intervals) | CORRECT | `local-development/gsd/static/index.html` lines 1794-1813; `local-development/gsd/kpi/system.py` lines 246-262 |
| the screenshots and the walk scripts | CORRECT | `docs/screenshots/backup-*.png` (three) and `reports/2026-09-26_epic-b-release/walk/pre-verify.py`, `walk_epic_b.py` exist |
| the 2026-09-26 capture's numbers (the metric, the file name, application 0.36.0) | NOT MEASURED | historical |
| `backup written` is the log line | CORRECT | `local-development/gsd/store.py` line 1809 (`"%s written to %s (%d kept)"`, `what="backup"`) |
| the pre-upgrade log lines (`pre-upgrade copy written before migrating schema …`, `not taken again`, `schema migration N applied`) | CORRECT | `local-development/gsd/store.py` lines 1249, 1305 and 1333 |
| the restore-check recipe (13 checks, R1 to R4) | NOT MEASURED | it creates a pod (a cluster write) |
| §1: the Python snippet | CORRECT | run here on a fresh backup: `integrity_check: ok`, `user_version: 20`, three tables, each with `0 rows, highest id 0` |
| §1: the CronJob image's `--check` prints `integrity_check ok`, `sha256 …`, `sidecar matches`, `user_version …` | CORRECT | `charts/group-sync-dashboard/scripts/offsite_backup.py` lines 286-305; run here: the four lines (`no sidecar` for an on-volume file) |
| §1: the `oc create job --from … --dry-run=client` recipe, `containers[0]` is the script's container | CORRECT | the rendered CronJob's only container is `ship`, with `/scripts` and `/offsite` mounted. The lab has Job `verify-1790912616` `Complete`, from an earlier run of this recipe. Not re-run here (a write) |
| §1: under `s3` the script runs in the init container, under `/stage` | CORRECT | `s3` render: init container `stage` (`--dest /stage`), container `upload` |
| §2: the bind Job is listed by `-l app.kubernetes.io/component=backup-offsite`; the claim has `keep` | CORRECT | the rendered bind Job, CronJob, ServiceAccount and ConfigMap carry that label; the PVC has `helm.sh/resource-policy: keep` |
| §2: the expected log lines | FIXED (one value) | The lines match the script (`copied`, `integrity_check ok; user_version …; membership_event rows …; sync_event rows …`, `pruned 0 older copies (keep=14)`, `no pre-upgrade-*.db under /data/pre-upgrade: nothing to ship (…)`), and a local run printed them. The sample's `user_version 9` is from long ago: the image's schema is 20 (`KNOWN_SCHEMA_VERSION`, and the runbook's own captures). Now 20 |
| §2: the pre-upgrade pass, `keep=3`, `ERROR: … it is not the copy the store verified`, the passes are independent | CORRECT | `charts/group-sync-dashboard/scripts/offsite_backup.py` lines 54, 220-224, 275-283 and 324-334 (`status \|=`) |
| §2: the Job is pinned to the dashboard's node under RWO | CORRECT | the RWO render's `podAffinity` (README row above) |
| §2: the `kube_cronjob_status_last_successful_time` query; `…Unobserved` | CORRECT | the rendered rules `GroupSyncDashboardOffsiteBackupStale` and `…Unobserved` use that series |
| §3: `cat` over `oc exec`; S3 needs `GetObject` | CORRECT | the pod has no `tar`; the upload command is `aws s3 cp` only |
| §4: Argo CD risks (v3.4.7, 0.7 s, 4 min 38 s, 12 min 49 s) | NOT MEASURED | historical lab measurements |
| §4: `restore-db.sh --list` / `--from-version <ID>`, `--namespace`/`--release` defaulting to `group-sync-dashboard`, at least ten minutes of TTL | CORRECT | `local-development/restore-db.sh` lines 4-15 and 23-50; `local-development/restore-db.py` line 51 (`MARGIN_SECONDS = 600.0`) |
| §4: the script refuses a newer copy, a mismatched sidecar and a failed `integrity_check`, keeps the live set under `/data/pre-restore/<stamp>/`, writes under a temporary name with `chgrp 0`/`g=u` | CORRECT | `local-development/restore-db.py` lines 24-25, 226, 230, 461-469 and 567-569 |
| §4 "Undo a restore": the fold one-liner folds the `-wal` into `gsd.db` and removes the side files | CORRECT | measured here on a database whose writer exited without a checkpoint (500 rows only in `-wal`). Before: the copied `gsd.db` alone had `no such table`. After the one-liner: only `gsd.db` was left, and it held 500 rows. Measured with the local SQLite, not in the pod |
| §4: the KPI page's Database copies card keeps the newest of each directory | CORRECT | README row on `housekeeping` (above); `docs/specs/SPEC_H1_gui_cleanup.md` |
| §4: "The dashboard pod keeps its spec … runs the chart's recovery script" | FIXED | Since chart 0.65.0 (#532), recovery mode runs a separate pod, from the Deployment `<fullname>-recovery` (render with `recovery.enabled=true`: app replicas 0, recovery replicas 1, with the app's pod spec). Now: the recovery pod, with the app's pod spec and data volume |
| §4 steps 1-5: the app goes to 0, `$REL-recovery` to 1, `-l app=$REL-recovery`, `2/2`, `/offsite` read-only, both Deployments available | CORRECT from chart 0.65.0; FIXED for 0.60.0 to 0.64.x | the recovery render (README rows above); lab: `deployment.apps/group-sync-dashboard-recovery 0/0` |
| §4 step 2: the log starts with `RECOVERY MODE` and `the app is NOT running and no data is collected` | CORRECT | `charts/group-sync-dashboard/scripts/recovery_mode.py` lines 51 and 166 (each line is prefixed with the instant and `gsd-recovery`) |
| §4 step 4: extending the TTL, the monotonic clock, a node restart | CORRECT | `charts/group-sync-dashboard/scripts/recovery_mode.py` lines 124-146 |
| `GroupSyncDashboardReportSnapshotStale` after about 50 minutes | CORRECT | rendered rule (README row above) |
| the fallback without recovery mode: `oc wait --for=delete pod -l app=$REL` | CORRECT | the app pods carry `app: <fullname>` |
| §4a/§4b: "In recovery mode … `oc exec -n $NS deploy/$REL -c dashboard`" | FIXED | In recovery mode from chart 0.65.0, `deploy/$REL` has 0 replicas (render above), so an `oc exec` against it finds no pod. The pod is `deploy/$REL-recovery`. §4's step 3 already says so. Now both sections name `deploy/$REL-recovery`, and `deploy/$REL` before 0.65.0, as `local-development/restore-db.sh` lines 7-8 do |
| §4a: the body (keep the live set, write under a temporary name, `chgrp 0`/`g=u`, remove the side files, rename) | CORRECT (read) | read against `local-development/restore-db.py`, which implements the same order (§4's paragraph cites `docs/specs/SPEC_E3_restore_db.md`). Not run: it writes the live claim |
| §4a: `oc debug --one-container` returns; 5 min 13 s without it | NOT MEASURED | needs a debug pod (a cluster write); historical |
| §4a: the citation `Containerfile#chgrp -R 0 /data` | CORRECT | `local-development/Containerfile` line 206: `chgrp -R 0 /data /etc/gsd` |
| §4b: the helper pod's claim names | CORRECT | the render's PVCs `group-sync-dashboard-data` and `group-sync-dashboard-backup-offsite` |
| §4b: the body and the S3 path | NOT MEASURED | it writes the live claim |
| §4c: `/api/version` answers `leader` and `version`; `"leader":false` until the 30 s lease expires | CORRECT | `local-development/gsd/api.py` line 3358; `local-development/gsd/leader.py` lines 67-68 |
| §4c: the report pod waits for a new snapshot; `snapshot schema N is newer…`; the leader's log lines; the citation `poller.py#_maybe_report_snapshot` | CORRECT | `local-development/gsd/reporting/snapshot.py` line 119; `local-development/gsd/poller.py` lines 1185 and 1199-1201 |
| §4c: the `StoreSchemaTooNew` line, word for word | CORRECT | `local-development/gsd/store.py` lines 1438-1441 build exactly that text |
| §4c: the counts snippet | CORRECT | run here on a local database: three lines `… rows up to id 0` |
| §4c: the #300 walk numbers (2776, 2779, 2770) | NOT MEASURED | historical |
| "Retention after a restore": "set both windows to `0` first" | FIXED | as in the README row: `kyverno.eventsRetentionDays` prunes in the same backup-gated loop, and `loginCapture.retentionDays` prunes `login_event` with no backup gate. Now names both |
| §4d: the tracking annotation `<APP>:apps/Deployment:<namespace>/<name>` | CORRECT | lab: `group-sync-dashboard:apps/Deployment:group-sync-dashboard/group-sync-dashboard` |
| §4d steps 2-7: patch, terminate, `--core` | NOT MEASURED | cluster writes; the lab's Application today has `automated {prune, selfHeal}` and `retry {limit: 3, backoff 30s ×2 up to 5m}`, as the risks box says |
| §4d step 4: the script's acceptance line | CORRECT | `local-development/restore-db.sh` line 74 prints `recovery mode, at least %s of its TTL left` |
| §5: copy `gsd.db` only, never `-wal`/`-shm` | FIXED (added) | §4a's own measurement (#302: a kept `gsd.db` without its `-wal` counted 0 of 500 committed rows) applies to §5 too. A writer stopped without its shutdown (`local-development/gsd/api.py` line 909 closes the store only on a clean stop) leaves committed rows in `-wal`. Now §5 says to fold a `-wal` that has bytes first, with the one-liner in **Undo a restore** |
| §6: the pre-upgrade name, where, once per upgrade, kept three, verified before the upgrade, the refusal line | CORRECT | `local-development/gsd/store.py` lines 1185, 1241-1315 and 1262-1264 (the message has the same shape as the example, `free space … MiB, database … MiB`, from line 1279) |
| §6: a cluster administrator may delete an older copy from the KPI page | CORRECT | README `housekeeping` row (above) |
| the example namespace `NS=group-sync` | CORRECT | an example value the commands read from `$NS`. The lab and the script's default are `group-sync-dashboard`, and §4 step 3 says to pass `--namespace` when they differ |
| "two processes on one SQLite file corrupt rather than error" | FIXED | **Found by Codex's review.** Two WAL-mode writers with `busy_timeout` serialise: Codex measured `child_statuses=[0, 0] rows=1000 integrity_check=ok`. The real risk is the restore itself: SQLite's *How To Corrupt An SQLite Database File* §1.2 (backup or restore while a transaction is active), §1.4 (mispairing database files and hot journals), §2.5 (unlinking or renaming a database file while in use). Now cites those |
| §4 steps 2 and 3 on charts 0.60.0 to 0.64.x | FIXED | **Found by Codex's review.** The section covers chart 0.60.0 and later, but steps 2 and 3 named only `$REL-recovery`. `Chart.yaml` history: 0.60.0 runs the recovery script in the app's container with a readiness probe that cannot pass; 0.65.0 adds the `-recovery` Deployment. `local-development/restore-db.sh` lines 7-8 find `app=<name>` before 0.65.0. Now both steps give the older names |

## Findings for the orchestrator (no change made)

1. **`values.yaml` line 1683 says the same stale thing the README did.** Its comment on
   `clusterConfig.secrets.writes.enabled` says that the dashboard's "only write anywhere is its own leader
   Lease". The fleet account's Lease (#285) is a second write. Values are out of this batch's scope.
2. **No render guard on `kpi.thresholds.*`.** The page used to say a value outside `(0, 100]` refuses the
   render; the chart renders it, and the pod refuses it at startup (`ConfigError`). The sibling
   `config.alerts.groupCountCliff.*` values do have a render guard (`templates/deployment.yaml` line 148).
   The page now describes what the code does. A matching render guard would be a chart change, and that is
   the orchestrator's call.
