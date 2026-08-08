# group-sync-dashboard

Read-only observability for the redhat-cop group-sync-operator. See the
[repository README](../../README.md) for what it does and why.

## Install

```bash
helm install group-sync-dashboard . -n group-sync-dashboard --create-namespace
```

Defaults reproduce the deployment that was verified on a live cluster, so an install with no
overrides is a working one. That includes `oauthProxy.enabled=true` — the dashboard exposes
group membership, so it ships authenticated and you turn the proxy *off* deliberately, not on.

## Prerequisites

* OpenShift 4.x — the chart uses `Route`-via-`Ingress`, `service-ca` and the OAuth proxy.
  On plain Kubernetes, set `oauthProxy.enabled=false`, `trustedCA.injected.enabled=false`
  and supply `ingress.host` and `ingress.className` yourself.
* A default StorageClass, or set `persistence.storageClass` / `persistence.existingClaim`.
* Cluster admin **once**, to create the ClusterRole. The dashboard needs no admin at runtime.
* The Prometheus Operator CRDs, only if you enable `monitoring.*`.

## Values

### Image

| Key | Default | Notes |
|---|---|---|
| `image.repository` | `quay.io/ephico2real/group-sync-dashboard` | written by `build-and-push-external.sh --update-values` |
| `image.tag` | pinned by the build script | empty falls back to `Chart.appVersion` |
| `image.pullPolicy` | `Always` | |
| `image.pullSecrets` | `[]` | leave empty for a public repo — an empty secret *reference* fails scheduling rather than falling back to anonymous pull |

### Authentication

| Key | Default | Notes |
|---|---|---|
| `oauthProxy.enabled` | `true` | **leave it on.** With it off the route is unauthenticated and exposes group membership |
| `oauthProxy.image` | `registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.15` | needs registry.redhat.io credentials, which the cluster's global pull secret normally already carries. Override to the internal imagestream or a mirror if not — see `values.yaml` |
| `oauthProxy.imagePullPolicy` | `IfNotPresent` | the image is already on the node as an imagestream |
| `oauthProxy.port` | `8443` | |
| `oauthProxy.cookieSecret` | `""` | generated once and reused across upgrades. If supplied it must yield 16, 24 or 32 key bytes **measured the way the proxy measures them** — a value that parses as base64 is decoded first, so 32 hex characters are 24 bytes, not 32. Enforced at render time, because `-pass-access-token` makes the AES requirement unconditional |
| `oauthProxy.cookie.expire` | `4h` | absolute session cap, a Go duration. There is deliberately no `refresh` key: measured on `provider=openshift`, `-cookie-refresh` force-clears the session at every interval instead of sliding it, so the chart refuses a values file that sets it |
| `oauthProxy.proxyPrefix` | `/oauth` | the prefix everything the proxy serves lives under; the app composes its sign-out link from it |
| `oauthProxy.logoutUrl` | `""` | where the browser lands after sign-out; empty means this dashboard's own unauthenticated `/signed-out` page |
| `oauthProxy.skipAuthRegex` | `^/(healthz\|readyz\|metrics)$` | the health paths **must** stay, or kubelet gets a 302 and kills a healthy pod |
| `oauthProxy.sar` | `""` | empty = authentication only. Set a SubjectAccessReview to also require a permission |
| `oauthProxy.skipProviderButton` | `false` | `false` shows an explicit **Log In** button. `true` skips straight to the OAuth server — one fewer click, but any mid-flow failure then lands on the proxy's own page headed "403 Permission Denied", which reads as *you are not allowed in* rather than *your session expired*. Observed here after a rollout landed between redirect and callback |
| `oauthProxy.requestLogging` | `false` | |
| `oauthProxy.resources` | 10m/64Mi → 200m/256Mi | |
| `oauthProxy.redirectMode` | `redirectreference` | **currently inert.** No template reads it — `serviceaccount.yaml` always emits `serviceaccounts.openshift.io/oauth-redirecturi.primary`, because the reference form points at a Route by name and OpenShift's ingress-to-route controller generates the Route with a random suffix that cannot be known at template time |

Enabling it also switches the Ingress to `reencrypt`, binds the app to `127.0.0.1`, and
moves the probes behind the proxy. All automatic.

### Trusted CAs

| Key | Default | Notes |
|---|---|---|
| `trustedCA.injected.enabled` | `true` | empty ConfigMap OpenShift fills from `proxy/cluster.spec.trustedCA` |
| `trustedCA.existingConfigMap.enabled` | `false` | a ConfigMap you create out of band |
| `trustedCA.existingConfigMap.name` | `enterprise-ca` | |
| `trustedCA.existingConfigMap.key` | `ca-bundle.crt` | |
| `trustedCA.mountPath` | `/etc/pki/ca-trust/extracted/pem` | |

Both may be on; they are loaded in turn. A cluster entry naming its own `caBundleFile`
always wins.

**These bundles go to the oauth-proxy as well as to the dashboard**, as extra `-openshift-ca`
paths. That matters on any cluster whose `*.apps` wildcard is signed by an internal CA, and the
symptom if it is missing is specific: login returns `500 Internal Error` while the pod is
healthy, the Route is valid and RBAC is correct.

```
provider.go:671   200 GET https://172.31.0.1/.well-known/oauth-authorization-server
oauthproxy.go:661 error redeeming code: Post
    "https://oauth-openshift.apps.ocp4.company.net/oauth/token":
    tls: failed to verify certificate: x509: certificate signed by unknown authority
```

Discovery succeeds and the code exchange fails, which locates the problem exactly. Discovery
goes to the **in-cluster** API address, which the ServiceAccount CA covers; discovery then
returns the **public** issuer, so the exchange goes to the ingress-served OAuth route, signed by
a CA the ServiceAccount bundle does not carry.

If the injected bundle does not contain your ingress CA — it carries only what the cluster has
been told about, via `proxy/cluster.spec.trustedCA` or the install's `additionalTrustBundle` —
supply it yourself and both containers pick it up:

```bash
oc create configmap enterprise-ca --from-file=ca-bundle.crt=/path/to/ingress-ca.pem \
  -n group-sync-dashboard
helm upgrade ... --set trustedCA.existingConfigMap.enabled=true
```

Enforced by `test_chart_strategy.py::TestTheProxyTrustsTheSameCAsTheApp`, which also checks
every CA path handed to the proxy is actually mounted — a path it cannot read stops the
container starting, which is a louder failure than the one above but still not an obvious one.

### Application

| Key | Default | Notes |
|---|---|---|
| `clusters` | the local cluster | add entries for multi-cluster |
| `config.pollIntervalSeconds` | `60` | also the error bar on "when did this person lose access?" — a membership change has no upstream timestamp, so `observed_at` is ours |
| `config.scheduleGraceSeconds` | `120` | stops the state flapping `late` every cycle. Must stay **above** `pollIntervalSeconds` |
| `config.bindingIntervalSeconds` | `300` | bindings are listed across every namespace, so deliberately slower. Must stay above the group poll |
| `config.requestTimeoutSeconds` | `15` | per-request timeout against a cluster's API server |
| `logLevel` | `INFO` | `DEBUG` adds per-poll timing, page counts and the binding-refresh countdown. Not HTTP request lines — httpx logs those at `INFO` itself (its `Client.send` calls `logger.info`, verified in 0.28.1), so they are already present at the default |
| `nameOverride` / `fullnameOverride` | `""` / `""` | standard Helm naming overrides. Changing either after install renames every object, including the PVC — which orphans the accumulated history |

Three values move together and two of them fail loudly if you move only one:
`config.pollIntervalSeconds`, `config.scheduleGraceSeconds` and
`monitoring.prometheusRule.notPollingSeconds`. Raising the poll interval without the grace
makes every healthy CR flap to `late`; raising it without the alert threshold makes
`GroupSyncDashboardNotPolling` fire forever on a healthy deployment.

### Backups

**This is the only existential risk in the system.** Everything else the dashboard stores is
a cache the next poll rebuilds; the accumulated sync timeline and membership history exist
only because this process observed them, and nothing upstream can replay them.

| Key | Default | Notes |
|---|---|---|
| `config.backup.enabled` | `true` | leave on. Writes `backupDir`/`backupIntervalHours`/`backupKeep` into the ConfigMap; disabling omits them, and an empty `backupDir` disables backups in the app |
| `config.backup.dir` | `/data/backup` | on the PVC, so it counts against `persistence.size` |
| `config.backup.intervalHours` | `6` | taken from the poll thread, and once immediately at startup |
| `config.backup.keep` | `4` | 4 × 6h = the last day, at roughly the size of the database each |

`VACUUM INTO`, not a file copy: it holds a read transaction for the duration, so the output
is consistent even while the poller writes. Copying `gsd.db` with a live WAL produces a torn
file that opens without complaint and is missing the newest commits — a backup that restores,
which is the worst kind.

**Half an answer by design.** These land on the *same* volume they protect against, so they
cover corruption, a bad migration and accidental deletion — not loss of the volume. Ship them
off it with a CronJob mounting the same PVC read-only; the dashboard deliberately does not
grow credentials for object storage.

### Dashboard usage tracking

Powers the **Usage** tab and `GET /api/dashboard/activity`.

| Key | Default | Notes |
|---|---|---|
| `config.userActivity.enabled` | `true` | **requires `oauthProxy.enabled`.** With the proxy off nothing is recorded whatever this says — there is no authentication, so `X-Forwarded-User` would be whatever the caller typed, and recording it would manufacture an audit trail rather than keep one. The mismatch is logged at startup |
| `config.userActivity.visibility` | `self` | `self` \| `all`. `self` means each authenticated user sees only their own rows. Anything unrecognised is treated as `self` — an unrecognised value must never be the one that widens access to a personnel dataset |
| `config.userActivity.flushSeconds` | `60` | buffered in memory and written once per interval; a write per request would put every API call behind the SQLite writer lock. An ungraceful kill loses up to this many seconds of counts |
| `config.userActivity.retentionDays` | `400` | `0` disables. A backstop for a long-lived deployment, not the growth control a request log would need — the table is aggregated to one row per user per UTC day |

`self` is the default because the response is identifiable personnel data — who was present,
on which days, between which times, how often. The argument that carries the rest of this
dashboard, "you could read the groups with `oc` anyway", is true of group membership and
false of who looked at it.

There is deliberately no "admins only" tier: doing that properly means a SubjectAccessReview
from the app on every read, which makes a personal-data query depend on API-server
availability. If you need it, `oauthProxy.sar` already restricts the whole dashboard.

Note it cannot see logins. The proxy owns the session; the app only ever observes requests
that are already authenticated, so "session" here means the first-to-last-seen window on a
day. Above one replica it is per-pod, like the rest of the history.

### Workload

| Key | Default | Notes |
|---|---|---|
| `replicaCount` | `1` | **1 is the recommendation.** See [Scaling](#scaling) — above one, each pod keeps its own database and history diverges |
| `strategy` | `""` | derived: `Recreate` at one replica, `RollingUpdate` above. Set explicitly to override |
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
| `podDisruptionBudget.enabled` | `false` | on one replica this governs **drains**, not availability — see below |
| `podDisruptionBudget.maxUnavailable` / `.minAvailable` | `1` / `""` | set `minAvailable` **instead of** `maxUnavailable` to block drains. Only one is rendered; `minAvailable` wins when non-empty |
| `config.sqlite.busyTimeoutMs` | `5000` | how long a write waits for a lock another connection holds. SQLite's own default is `0` — fail instantly, no retry |
| `config.sqlite.readerBusyTimeoutMs` | `2000` | deliberately shorter: `/readyz` reads, and the probe gives up at 5s |
| `config.sqlite.synchronous` | `NORMAL` | the documented companion to WAL. `FULL` fsyncs every commit |
| `config.sqlite.walCheckpointMb` | `8` | truncate the write-ahead log past this size |
| `persistence.enabled` | `true` | **keep on.** The accumulated history cannot be re-fetched from the API |
| `persistence.size` / `.storageClass` / `.existingClaim` | `1Gi` / cluster default / `""` | |
| `persistence.accessMode` | `ReadWriteMany` | scales without recreating the volume. `ReadWriteOncePod` gets an **enforced** single-pod guarantee at one replica; empty derives it. See [Storage](#storage) |
| `resources` | 50m/128Mi → 500m/512Mi | |
| `probes.*.enabled` | `true` | set `false` to omit the probe entirely |
| `probes.liveness.path` / `probes.readiness.path` | `/healthz` / `/readyz` | both must stay inside `oauthProxy.skipAuthRegex`, or kubelet gets a 302 to the login page. Neither is gated on a reachable cluster — an unreachable cluster is a thing this dashboard exists to *display* |
| `probes.*.initialDelaySeconds` | `10` / `5` | liveness / readiness |
| `probes.*.timeoutSeconds` | `5` | not the 1s default — that killed a healthy process on host resume and cascaded into a ~4h outage |
| `probes.liveness.periodSeconds` / `.failureThreshold` | `300` / `2` | **5 min**, because being wrong here restarts the container and destroys in-flight state. 10 min of sustained failure before a restart. Raising the period without lowering the threshold is how you get a half-hour wait on a wedged pod |
| `probes.readiness.periodSeconds` / `.failureThreshold` | `15` / `3` | **15s**, because being wrong here only removes the pod from the Service and it comes straight back |
| `podSecurityContext`, `securityContext` | non-root, read-only rootfs, all caps dropped | |
| `nodeSelector`, `tolerations`, `affinity`, `podAnnotations`, `podLabels` | empty | |

### Networking

| Key | Default | Notes |
|---|---|---|
| `ingress.enabled` | `true` | on OpenShift, `ingress-to-route` converts it |
| `ingress.host` | derived | `<fullname>-<namespace>.<cluster apps domain>`. A **hostless Ingress produces no Route at all**, so this is always emitted |
| `ingress.className` | `openshift-default` | |
| `ingress.termination` | `edge` | carried as `route.openshift.io/termination`, since Ingress has no field for it. Forced to `reencrypt` when the proxy is on |
| `ingress.insecureEdgeTerminationPolicy` | `Redirect` | carried as `route.openshift.io/insecureEdgeTerminationPolicy`. Omitted from the Ingress when empty |
| `ingress.annotations` | `{}` | merged after the two route annotations above, so it can override them |
| `ingress.tls` | `[]` | a standard Ingress `spec.tls` block. On OpenShift the Route annotations above are what actually take effect |
| `service.type` / `service.port` | `ClusterIP` / `8080` | the port stays 8080 in both modes; only `targetPort` moves to the proxy |

### RBAC and monitoring

| Key | Default | Notes |
|---|---|---|
| `serviceAccount.create` / `.name` / `.annotations` | `true` / derived / `{}` | with the proxy on, the SA also carries the `oauth-redirecturi` annotation that makes it an OAuth client — no `OAuthClient` object to register |
| `rbac.create` | `true` | ClusterRole + binding, read-only, no `watch` |
| `rbac.bindings` | `true` | adds `get`/`list` on rolebindings/clusterrolebindings, powering the Access-granted, RBAC-policy and Namespace-audit views. Disable and the dashboard degrades to group data only |
| `authLogLevel.manage` | `false` | lets this chart own `spec.logLevel` on the authentication **operator** CR (`authentications.operator.openshift.io/cluster`) — not the OAuth CR, and not `operatorLogLevel`. Off by default — turning it on is what transfers ownership |
| `authLogLevel.enabled` | `false` | with `manage`, sets `Debug` (login lines appear) or `Normal`. The Job runs for **both** values: Helm does not run a Job you merely stopped rendering, so a one-way enable would strand the cluster in Debug |
| `authLogLevel.revertOnUninstall` | `true` | **leave on.** A pre-delete Job puts the level back, or removing the dashboard leaves the OAuth server naming every person who authenticates with nothing left watching |
| `authLogLevel.waitSeconds` / `.activeDeadlineSeconds` / `.revertDeadlineSeconds` | `180` / `300` / `120` | the Job polls the Deployment's `observedGeneration` rather than using `oc rollout status`, which returned success ~30s **before** the rollout began. A wait timeout is not a failure — the patch has landed |
| `rbac.users` | `true` | adds `get`/`list` on `users`, read for one field — `fullName` — so members show as `alice.cooper · Alice Cooper`. A name exists only for people who have logged in; unnamed members render exactly as before. Safe to disable, and safe to upgrade without re-applying: the call 403s and the poller keeps the names it already had |
| `monitoring.serviceMonitor.enabled` | `false` | needs the Prometheus Operator CRDs |
| `monitoring.serviceMonitor.interval` / `.scrapeTimeout` | `30s` / `10s` | every series is recomputed from SQLite on scrape and each scrape takes a read snapshot. Faster buys no resolution — the data only changes once per poll |
| `monitoring.serviceMonitor.labels` | `{}` | extra metadata labels. Usually how a cluster's Prometheus selects which ServiceMonitors it owns |
| `monitoring.prometheusRule.enabled` | `false` | **eight** alerts — see below |
| `monitoring.prometheusRule.labels` | `{}` | as above, for rule selection |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | a GroupSync has not synced for this long |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot. **Must stay above ~2× `config.pollIntervalSeconds`** or it fires continuously on a healthy deployment |
| `monitoring.prometheusRule.walMiB` | `256` | MiB. 25% of the default 1Gi PVC. Raise it with `persistence.size` |
| `monitoring.prometheusRule.for.*` | see below | the `for:` duration on each alert |

### oauth-server log verbosity

The oauth-openshift server only names the person logging in when the authentication **operator**
CR — `authentications.operator.openshift.io/cluster` — has `spec.logLevel: Debug`. Three
cluster-scoped objects have confusingly similar names, and this feature touches only the first:

| object | kind | holds |
|---|---|---|
| `authentications.operator.openshift.io/cluster` | `Authentication` (operator) | `logLevel`, `operatorLogLevel`, `managementState` |
| `authentications.config.openshift.io/cluster` | `Authentication` (config) | `type`, `serviceAccountIssuer`, `oauthMetadata` |
| `oauth.config.openshift.io/cluster` | `OAuth` | `identityProviders` — "the OAuth CR" |

`logLevel` is the **operand's** verbosity (the `oauth-server` process, which emits the login
lines); `operatorLogLevel` is the operator's own and would change nothing here. At `Normal` that line is
not emitted at all — measured: **zero** occurrences of `succeeded for login` until it is on. So
`authLogLevel.*` is the prerequisite for capturing login activity, and nothing more.

**The write does not go on the dashboard.** Patching that object is a write to a core platform
object, and `rbac.yaml` states *"NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON"* — a line
`test_docs_citations.py` pins from five places across two documents. So the grant lives on a
ServiceAccount used only by the two hook Jobs. It is two rules and nothing else:

| API group | Resources | resourceNames | Verbs |
|---|---|---|---|
| `operator.openshift.io` | `authentications` | `cluster` | get, patch |
| `apps` | `deployments` | `oauth-openshift` | get |

Both are pinned by name. That is narrowing, not isolation: `resourceNames` stops this identity
touching *other* objects in those groups, and the object it can patch is the cluster's authentication
configuration — so the grant is small but not harmless, which is why it is opt-in.

The dashboard's own role stays read-only, and `test_chart_strategy.py` fails if that stops being
true — including if the *binding* is repointed at the dashboard's ServiceAccount, or if
`serviceAccount.name` is set to collide with the Job's. Both were possible until they were tested;
the second rendered cleanly and handed the dashboard the write.

**Pass your whole value set when you enable this on an existing release.** `helm upgrade` with only
`--set authLogLevel.*` discards every other user-supplied value and reverts it to the chart default —
measured here: a release carrying `oauthProxy.apiTokenAccess.enabled=true` lost it, and API token
access broke three commands later with no obvious connection to the cause. Re-pass your values file,
or use `--reuse-values` deliberately, then confirm with `helm get values`.

**Turning it off is two steps, in this order.** `manage: false` removes the Jobs *and* the revert Job
along with them, so going straight there while `Debug` is live strands the cluster in Debug with
nothing left to put it back:

```bash
# 1. converge the cluster to Normal, with the machinery still present
helm upgrade ... -f my-values.yaml --set authLogLevel.manage=true --set authLogLevel.enabled=false
# 2. then, once the rollout has finished, stop managing it
helm upgrade ... -f my-values.yaml --set authLogLevel.manage=false
```

`helm uninstall` needs no such care — the pre-delete Job reverts first. But `helm rollback` does not
run hooks at all, so rolling back past an enable does **not** put the level back; do step 1 by hand.

**To verify it end to end**, follow `docs/LOGIN_CAPTURE_QUICKCHECK.md` — five commands that turn the
verbosity up, cause a login, and read that login back using the dashboard's own ServiceAccount token,
with the real output of each recorded. It is also the place to start when the dashboard shows no login
activity and you need to find which link is missing.

**What Debug exposes**, so this is a decision and not a shrug: the lines carry the username of
everyone who authenticates, their resolved LDAP DN, and the bind filter used. Anyone who can read pod
logs in `openshift-authentication` can read them.

Three rules in the ClusterRole are conditional. `coordination.k8s.io/leases`
(`get`, `create`, `update`) renders only when `leaderElection.enabled`,
`rolebindings`/`clusterrolebindings` (`get`, `list`) only when `rbac.bindings`, and
`users` (`get`, `list`) only when `rbac.users`. Everything
else in it is `get`/`list`, and that Lease — the dashboard's own, which grants nobody
access to anything — is the only object it writes on any cluster.

A `patch` on rolebindings/clusterrolebindings used to render here when
`config.unmanagedAudit.mode` was `annotate`. The mode and the grant are both gone; see
[Unmanaged-grant discovery](#unmanaged-grant-discovery) for the measurement that removed
them. `helm template` now emits no `"patch"` at any value of that mode, `annotate` included.

`namespaceconfigs`/`groupconfigs` are granted unconditionally, **including on clusters that
will never install the namespace-configuration-operator**. The dashboard auto-detects the
CRDs: with the grant an absent CRD returns 404 and is quietly recorded as "absent"; without
it the same call returns 403, which is treated as a refresh failure and logs a warning every
cycle.

`roles`/`clusterroles` are deliberately **not** requested, since role rules are never
evaluated. That is a statement of intent, not an isolation boundary — OpenShift binds
`basic-user` to `system:authenticated`, which already grants `get`/`list` on clusterroles to
every authenticated identity including this one.

#### The eight alerts

| Alert | Fires on | `for` |
|---|---|---|
| `GroupSyncOverdue` | a CR has not synced for `overdueSeconds` | `for.overdue`, `10m` |
| `DanglingRoleBinding` | a binding grants a group that was operator-managed and has vanished | `for.dangling`, `15m` |
| `GroupSyncDashboardNotPolling` | the dashboard's own poll loop has stopped. `/healthz` is unconditional and `/readyz` only reads the store, so neither probe can see this | `for.notPolling`, `5m` |
| `GroupSyncClusterUnreachable` | `gsd_cluster_up == 0` | `for.unreachable`, `15m` |
| `GroupSyncDashboardDirectUserGrants` | bindings still name people rather than LDAP groups | `for.directUserGrants`, `1h` — long, because this is a migration backlog, not an incident |
| `GroupSyncDashboardConfigReconcileError` | a `NamespaceConfig`/`GroupConfig` is failing, so RBAC has silently stopped reconciling | `for.configError`, `10m` |
| `GroupSyncDashboardWalGrowing` | `gsd_sqlite_wal_bytes` above `walMiB` — checkpoint starvation | `for.walGrowing`, `30m` |
| `GroupSyncDashboardWalDisabled` | `gsd_sqlite_wal_enabled == 0` — the filesystem refused WAL | `for.walDisabled`, `10m` |

The last two are the ones with no other symptom: the pod stays Ready, every other metric
looks normal, and the first visible sign is a full volume or a latency cliff.

### ArgoCD

| Key | Default | Notes |
|---|---|---|
| `argocd.enabled` | `false` | adds Argo-specific annotations. Inert noise when you are not running GitOps, and misleading metadata is worse than none |
| `argocd.preservePVC` | `true` | three sync-options on the PVC — see [Deploying with ArgoCD](#deploying-with-argocd) |
| `argocd.serverSideApplyInjectedCA` | `true` | lets the CA operator keep ownership of the `data` it writes. **Not sufficient alone** — the Application also needs an `ignoreDifferences` entry |

### Unmanaged-grant discovery

Read-only, in every mode. This feature finds hand-made access grants and reports them, and
writes nothing at all. The dashboard's only write on any cluster is its own leader-election
Lease (`templates/rbac.yaml#leases`) — its coordination object, not anything it observes.

A binding is `unmanaged` when it grants an operator-synced group access and carries neither
the policy operator's `rbac.ocp.io/config-source` label nor an
`rbac.ocp.io/unmanaged-exception` annotation — somebody granted access by hand, outside the
governance system, and nothing on the cluster reports it. The classification also requires at
least one *managed* binding to exist on that cluster, so a cluster that has never used
config-source labels reports zero rather than flagging every binding on it
(`local-development/gsd/store.py#Store.user_bindings`).

`config.unmanagedAudit.mode` defaults to `log`, so each finding is published as one
self-contained line, at **WARNING** — the HTTP client logs a line per request at INFO, so a finding at INFO
is buried by routine traffic and a log pipeline has no level to filter on:

```
UNMANAGED GRANT DISCOVERED — crc-local: ClusterRoleBinding demo-cluster-admin-crb
(cluster-wide) grants cluster-admin to group app-ocp-rbac-demo-cluster-admin, outside the
policy system (no config-source label, no exception annotation)
```

Which object, what it grants, to whom, and why that is a finding — the line is actionable
without opening the dashboard, and the fixed `UNMANAGED GRANT DISCOVERED` prefix is there to
be alerted on. Only the groups whose rows were classified unmanaged are named: a binding can
name two groups and be unmanaged for only one, and citing the managed one would send a reader
to inspect a grant that is fine.

One INFO summary line precedes them each refresh:

```
crc-local: unmanaged-grant discovery — 4 outside the policy system, 0 resolved since the
last cycle. Full detail: GET /api/clusters/crc-local/bindings/findings
```

The first number is how many were listed. When `maxPerCycle` holds some back the line gains
`, K not yet listed (per-cycle cap)`, so the remainder is accounted for rather than dropped.

The same findings are in the **RBAC policy** tab and at
`GET /api/clusters/{id}/bindings/findings`, classified alongside the other tiers. The
discovery is the deliverable.

| Key | Default | Notes |
|---|---|---|
| `config.unmanagedAudit.mode` | `"log"` | `off` \| `log`. `off` runs no discovery code at all. `log` needs **no extra RBAC** — the ServiceAccount stays read-only, which is checkable: its only binding verbs are `get` and `list`. Anything unrecognised is treated as `off`; `annotate` runs as `log` and logs a warning saying so. **The default moved from `off` to `log`** once the feature stopped writing — `off` was right while it patched cluster objects, but now the only thing it buys is a governance tool that found a hand-made `cluster-admin` grant and declined to mention it |
| `config.unmanagedAudit.maxPerCycle` | `20` | at most this many findings **listed individually** per `config.bindingIntervalSeconds` refresh. Anything beyond the cap is counted in the summary as "not yet listed" rather than dropped, so a misclassification bug costs one screenful of log per cycle instead of the whole cluster at once. Resolutions are never capped — a closed finding must not queue behind new ones |

The default is `off` so a fresh install is silent until somebody asks for the findings.

#### Suppressing a finding

A cluster admin annotates the object itself:

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```

The dashboard reads that annotation (`local-development/gsd/kube.py#_user_binding_views`) and stops
classifying the binding as unmanaged, so it leaves the log, the RBAC policy tab and the API
together. Two things follow from doing it this way. The justification lives next to the object
it describes, rather than in a dashboard-side allowlist that drifts from the cluster. And the
acknowledgement is performed by somebody who holds the privileges the binding grants — which
the dashboard deliberately does not. That is separation of duties, not a limitation.

The dashboard also **reads** the `rbac.ocp.io/unmanaged=true` label, which it never applies.
An admin or a privileged CI job that applies it by hand makes the findings selectable from the
objects themselves:

```bash
oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true
```

The dashboard then reports when one of those objects stops being a finding:

```
unmanaged grant RESOLVED — crc-local: ClusterRoleBinding demo-cluster-admin-crb
(cluster-wide) is no longer outside the policy system (adopted, annotated as an exception, or
its group left management). Its rbac.ocp.io/unmanaged label is now stale: oc label
clusterrolebinding demo-cluster-admin-crb rbac.ocp.io/unmanaged-
```

Nothing else would report that. The label was applied by a human or a pipeline, and without
this line the only signal that it has gone stale is a count going down.

#### There was an `annotate` mode, and this is why it is gone

It labelled the binding objects itself, so findings were selectable with `oc get ... -l`
without anyone having to run `oc annotate`. It was removed along with the `patch` grant
`rbac.yaml` used to render for it, because it could never work.

Measured on a live OpenShift cluster: enabling it produced `plan — stamp 4, heal 0`, and then
0 of 4 landed. Kubernetes privilege-escalation prevention requires the writer of an RBAC
object to already hold **every** permission that object grants, even for a metadata-only
patch that touches no rule and no subject. The API server enumerated what it wanted: **175
additional rule sets** to label a ClusterRoleBinding granting nothing but `view`, and a single
wildcard rule (`{APIGroups:[*], Resources:[*], Verbs:[*]}`, i.e. cluster-admin) for the
cluster-admin one. `oc auth can-i patch clusterrolebindings --as=<the SA>` answered **yes**
throughout — the RBAC grant was correct and irrelevant, because the escalation check runs
after it.

So making it work means carrying 175+ rules of Kubernetes internals per binding class, or
`escalate` on `rbac.authorization.k8s.io` (the verb that switches the check off — cluster-admin
under a smaller name), or cluster-admin outright. All three hand a read-only auditing tool the
most privilege over precisely the most dangerous grants.

**The cost of removing it, plainly:** the findings are in the log, the RBAC policy tab and the
API, and not on the objects. The label selector above returns nothing until an admin or a
privileged CI job applies the label — they legitimately hold the permissions, and the
dashboard still notices and reports `unmanaged grant RESOLVED` when such a label goes stale.

Upgrading with `mode: annotate` still set runs as `log` and warns once at startup. It
deliberately does not fall back to `off`, which would silently take the findings away from a
cluster that had asked for them.

Full design, invariants and the live-cluster evidence: [`docs/unmanaged-audit-design.md`](../../docs/unmanaged-audit-design.md).

## Scaling

**1 replica is the recommendation.** This polls every 60s and serves a handful of operators;
it is not in anyone's request path. A node drain costs one missed poll, which the next one
heals. A second replica buys HTTP uptime and pays for it in **divergent history** — and the
history is the part the Kubernetes API cannot reproduce.

Above one replica the chart switches the database to `/data/$POD_NAME/gsd.db`, one file per
pod. That is not a preference:

> SQLite WAL coordinates writers through an `mmap`'d `-shm` file that assumes every process
> is on **one host**. Sharing a single database file across a ReadWriteMany volume corrupts
> rather than errors.

A shared *volume* with unshared *files* is safe; a shared *file* is not. So each pod polls
independently and derives its own copy. Current state converges within one poll; the
`sync_event` and `membership_event` timelines do **not** — each pod only holds what it saw
while running, so the Service answers "when did this user leave?" differently depending on
which pod responds.

Four combinations are refused at template time rather than deployed broken:

| Set | Refused because |
|---|---|
| `replicaCount > 1` with `leaderElection.enabled=true` | pods losing the lease stop polling but keep serving reads from their own database, which then never updates again |
| `replicaCount > 1` with a non-RWX volume | RWO binds one **node** and RWOP one **pod**, so under either the extra replicas stay Pending with no error on the Deployment |
| `ReadWriteOncePod` with `strategy: RollingUpdate` | deadlock — the incoming pod cannot schedule until the outgoing releases the claim, and RollingUpdate will not terminate the outgoing until the incoming is Ready |
| `replicaCount: 1` with persistence and `strategy: RollingUpdate` | RollingUpdate starts the incoming pod **before** terminating the outgoing one, and at one replica both use `/data/gsd.db`. The guard above catches only `ReadWriteOncePod`, where the scheduler refuses the second pod anyway — the **default** ReadWriteMany happily mounts twice and was therefore the dangerous case, not the protected one |

### Leader election

**Best-effort admission control, not a write fence.** Read this before relying on it.

Leadership is checked once per cycle, before the poll is entered, and nothing re-checks it
during the writes that follow. No fence token reaches the store. So a pod that passes the
check and then pauses — CPU throttling, a stop-the-world GC, a partition — can lose the
lease, have another pod take over, and still complete every one of its writes on resume. Two
pods can also both believe they hold it for up to the renew interval, because expiry is
judged against each pod's own clock.

What it *does* buy: the ordinary cases — a scale-up, a slow `Recreate` rollover — do not
produce two steady-state pollers. What it does **not** buy is a guarantee that only one
process ever writes. That comes from the deployment shape: one replica, `Recreate`, one file.

Making it a true fence would mean every store write comparing a monotonic token inside the
same transaction, with a new leader advancing it first — a distributed-systems protocol
layered over SQLite, and not proportionate for a single-writer application whose primary
defence is that there is only one pod.

It is still worth leaving on at one replica: `Recreate` is not instantaneous, `kubectl scale`
is one keystroke, and a partitioned node can leave an old pod running while a new one starts.
Outside a cluster (no ServiceAccount token) the elector assumes sole instance and polls,
rather than refusing to poll and looking broken in local development.

`oc get lease -n <namespace>` names the pod currently holding it, and `gsd_leader` is 1 on
that replica. Use it to pick one replica's series — the counts are cluster facts, not per-pod
facts, so `sum()` over them is wrong.

### PodDisruptionBudget

On a single replica a PDB is a statement about **node drains**, not availability — there is
no second pod to keep serving:

| Setting | Effect |
|---|---|
| `maxUnavailable: 1` (default) | the drain proceeds; the pod moves and one poll is missed |
| `minAvailable: 1` | the drain **blocks indefinitely** — one replica can never satisfy it. Cluster admins hit this during maintenance and cannot see whose workload is stalling them |

Choose `minAvailable` only if a human must be involved before this pod moves, and tell
whoever operates the cluster. Kubernetes reports `DisruptionAllowed=False` when it is
blocking.

## Storage

`persistence.accessMode` defaults to **ReadWriteMany**, so the volume never has to be
recreated to scale and it works on the shared storage most clusters actually provide.

That trades an **enforced** guarantee for an advisory one, which is worth understanding
before you rely on it. `ReadWriteOncePod` makes two pods on one database structurally
impossible — the scheduler refuses the second, verified on the reference cluster:

> `0/1 nodes are available: 1 node has pod using PersistentVolumeClaim with the same name and
> ReadWriteOncePod access mode`

RWX gives no such refusal. At one replica both pods would share a single `/data/gsd.db`,
which is precisely the state SQLite must not be in. Three things prevent it, none enforced by
storage:

| Guard | Covers |
|---|---|
| `strategy: Recreate` at one replica (derived) | the outgoing pod is gone before the incoming one starts. This matters **more** under RWX than it did under RWOP |
| `leaderElection.enabled` | only the lease holder polls, so a brief overlap does not produce two writers |
| `config.sqlite.busyTimeoutMs` | an overlap that does happen waits for the lock rather than failing on it |

Above one replica the shared-file problem disappears: each pod gets its own
`/data/$POD_NAME/gsd.db`.

Set `persistence.accessMode: ReadWriteOncePod` to take the enforced guarantee back at one
replica — at the cost of needing a CSI driver that supports it (Kubernetes 1.29+), and of
`RollingUpdate` becoming a deadlock the chart will refuse to render.

### Watch the filesystem underneath

**RWX in practice usually means NFS, and SQLite refuses WAL there.** WAL coordinates through
an `mmap`'d `-shm` file that assumes every process is on one host, so the switch fails —
*silently* — and readers then block for the entire duration of every write.

The chart reads the journal mode back at startup, logs at ERROR when it is not WAL, and
alerts on it (`GroupSyncDashboardWalDisabled`, `gsd_sqlite_wal_enabled`). Do not ignore that
alert: block storage or a CSI RWX filesystem with real POSIX locking is fine, NFS/EFS/SMB is
not.

## SQLite locking

Three things keep reads from stalling behind the 60s bulk write, and all three must hold.

**WAL is verified, not assumed.** `PRAGMA journal_mode=WAL` returns the mode actually in
force, which is not always the one requested — on a filesystem without working shared memory
or POSIX locks (NFS, EFS, SMB) SQLite silently stays in rollback-journal mode, where a reader
blocks for the entire duration of the writer's transaction. The mode is read back, logged at
`ERROR` if it is not WAL, and exported as `gsd_sqlite_wal_enabled`.

**`busy_timeout` is set on every connection.** SQLite's default is `0`: it raises `database is
locked` the instant a lock is held, with no retry. That default is the usual cause of the
error. Measured in the deployment image (UBI9, SQLite 3.34.1) against a lock held by another
connection: `busy_timeout=0` fails in `0.000s`; `busy_timeout=1500` waits `1.512s`. The
contention this covers is cross-**connection** — the `Recreate` rollover, where the outgoing
pod still holds the lock as the incoming one opens the file. Threads inside one pod are
already serialised by a lock and never reach it.

**Checkpoints are forced past a threshold.** Auto-checkpointing runs PASSIVE and yields the
moment a reader holds an older snapshot, so a steady trickle of API reads can starve it
indefinitely. The WAL then grows without bound while the database file stays small, and the
first symptom is a **full volume** — not a database error. The poller runs a TRUNCATE
checkpoint after each cycle once the WAL passes `walCheckpointMb`, never from a request
handler, since TRUNCATE waits for readers.

Two alerts cover the cases with no other symptom:

| Alert | Fires on |
|---|---|
| `GroupSyncDashboardWalGrowing` | `gsd_sqlite_wal_bytes` above `monitoring.prometheusRule.walMiB` for 30m — checkpoint starvation |
| `GroupSyncDashboardWalDisabled` | `gsd_sqlite_wal_enabled == 0` — the filesystem refused WAL and reads now block on writes |

`gsd_sqlite_checkpoint_busy_total` distinguishes the two readings of a large WAL: rising every
cycle means starvation, flat means the checkpoint is merely lagging a burst.

## Deploying with ArgoCD

**Set `ingress.host` explicitly. This is not optional under GitOps.**

Everywhere else the host is auto-detected from the cluster's own `ingresses.config/cluster`
object, so a plain `helm install` needs no flag. ArgoCD renders with `helm template`, which
runs with **no cluster connection**, so the `lookup` returns nothing. The chart refuses to
render rather than emit a hostless Ingress — which on OpenShift produces no Route at all,
leaving a release that syncs green and is unreachable.

```yaml
# Application.spec.source.helm
parameters:
  - name: ingress.host
    value: group-sync-dashboard.apps.<your-cluster-domain>
```

Get the domain once with:

```bash
oc get ingresses.config/cluster -o jsonpath='{.spec.domain}'
```

The same applies to Flux, `helm template` by hand, and any installer whose identity cannot
read `ingresses.config/cluster` — it is cluster-scoped and an ordinary user cannot read it.

Then set `argocd.enabled=true`. It adds annotations for two problems that each cost you
something real if unhandled.

**The PVC gets pruned.** Argo reconciles manifests; it does not run Helm's uninstall path,
so `helm.sh/resource-policy: keep` does not protect it. A prune, or deleting the
Application, destroys the accumulated sync timeline and membership history — the only state
the Kubernetes API cannot reproduce.

`argocd.preservePVC` applies three protections, covering different moments:

| Annotation | Protects against |
|---|---|
| `Prune=false` | removal when the resource leaves the source |
| `Delete=false` | removal when the Application itself is deleted (cascade) |
| `PruneLast=true` | a deliberate prune taking the volume before the workload, leaving the pod running without it |

`compare-options: IgnoreExtraneous` is deliberately **not** used. Per the ArgoCD docs it is
for resources *not* declared in git — ones "generated by a tool" — and putting it on a
resource the Application itself creates defeats the purpose of tracking deployment state.
Binding drift is handled with `ignoreDifferences` on the Application instead, below.

### Other annotations the chart emits

| Resource | Annotation | Why |
|---|---|---|
| ServiceMonitor, PrometheusRule | `SkipDryRunOnMissingResource=true` | both are Prometheus Operator CRDs. Argo dry-runs every resource, and a dry-run against a CRD that is not installed **fails the entire sync** — turning "monitoring is not installed yet" into "nothing deploys" |
| trusted-CA ConfigMap | `ServerSideApply=true` | lets the operator keep ownership of the `data` it writes |

**The injected CA ConfigMap fights the operator.** The chart ships it empty and OpenShift
writes `data.ca-bundle.crt` into it. Argo sees live data the manifest lacks, reports
OutOfSync permanently, and with self-heal enabled **wipes the CA bundle** — making every
external cluster unreachable until the operator refills it.

`argocd.serverSideApplyInjectedCA` reduces that by letting the operator keep field
ownership, but it does not end it. The Application also needs an `ignoreDifferences` entry,
which cannot be set from the chart because it lives on the Application:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: group-sync-dashboard
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: https://github.com/ephico2real2/group-sync-dashboard
    path: charts/group-sync-dashboard
    helm:
      values: |
        # REQUIRED under GitOps. Argo renders with `helm template`, which has no cluster
        # connection, so the chart cannot auto-detect the apps domain and refuses to render.
        ingress:
          host: group-sync-dashboard.apps.<your-cluster-domain>
        argocd:
          enabled: true
        oauthProxy:
          enabled: true
  destination:
    namespace: group-sync-dashboard
    server: https://kubernetes.default.svc
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  ignoreDifferences:
    # Without this, the injected CA bundle is reverted on every sync.
    - group: ""
      kind: ConfigMap
      name: group-sync-dashboard-trusted-ca
      jsonPointers:
        - /data
    # A bound PVC is mutated by the storage class, so it drifts from the manifest
    # permanently and shows the Application OutOfSync — which invites someone to "fix" it.
    - group: ""
      kind: PersistentVolumeClaim
      name: group-sync-dashboard-data
      jsonPointers:
        - /spec/volumeName
        - /spec/storageClassName
    # OpenShift injects a dockercfg pull secret into every ServiceAccount. Measured on the
    # reference cluster, `managedFields` shows
    # openshift.io/image-registry-pull-secrets_service-account-controller owning `secrets`
    # and `imagePullSecrets` via Apply, while Helm owns only metadata. None of it is in git,
    # so a client-side diff reports the Application permanently OutOfSync.
    #
    # ~1 is a literal `/` inside a JSON Pointer key (RFC 6901). Without the escape the
    # pointer is parsed as a path and silently matches nothing.
    - group: ""
      kind: ServiceAccount
      name: group-sync-dashboard
      jsonPointers:
        - /secrets
        - /imagePullSecrets
        - /metadata/annotations/openshift.io~1internal-registry-pull-secret-ref
    # The ingress-to-route controller writes status.loadBalancer once a Route exists.
    - group: networking.k8s.io
      kind: Ingress
      name: group-sync-dashboard
      jsonPointers:
        - /status
```

**Both mechanisms, deliberately.** `ServerSideApply=true` on the objects addresses the
cause — the API server merges by field ownership, so fields the chart never claims are not
compared. `ignoreDifferences` addresses the symptom. They are not redundant: the first
depends on Argo computing its predicted-live state through an SSA dry-run, which is its
documented behaviour but was **not** observed here, because this cluster has the Argo CRDs
installed and no controller running. The second holds regardless of Argo's version or diff
strategy. Keep both until you have watched a sync on your own cluster.

> Verified as manifests, not at runtime: the reference cluster has the Argo CRDs installed
> but no controller running, so the annotations were checked by rendering and applying, not
> by observing a sync.

## Upgrading

```bash
helm upgrade group-sync-dashboard . -n group-sync-dashboard --reuse-values \
  --set image.tag=<new-tag>
```

The Deployment checksums the ConfigMap, so a change to intervals or the cluster list
restarts the pod. Without that the ConfigMap would update and nothing would happen, because
the process reads it at startup.

## Uninstall

```bash
helm uninstall group-sync-dashboard -n group-sync-dashboard
```

The PVC is **not** removed with the release. That is deliberate — it holds the accumulated
sync timeline and membership history, which cannot be re-fetched from the API. Delete it
explicitly when you genuinely want that gone:

```bash
oc delete pvc group-sync-dashboard-data -n group-sync-dashboard
```
