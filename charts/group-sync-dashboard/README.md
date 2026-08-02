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
| `oauthProxy.image` | the cluster's own oauth-proxy, via the internal registry | confirm with `oc adm release info --image-for=oauth-proxy` |
| `oauthProxy.imagePullPolicy` | `IfNotPresent` | the image is already on the node as an imagestream |
| `oauthProxy.port` | `8443` | |
| `oauthProxy.cookieSecret` | `""` | generated once and reused across upgrades |
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

### Application

| Key | Default | Notes |
|---|---|---|
| `clusters` | the local cluster | add entries for multi-cluster |
| `config.pollIntervalSeconds` | `60` | also the error bar on "when did this person lose access?" — a membership change has no upstream timestamp, so `observed_at` is ours |
| `config.scheduleGraceSeconds` | `120` | stops the state flapping `late` every cycle. Must stay **above** `pollIntervalSeconds` |
| `config.bindingIntervalSeconds` | `300` | bindings are listed across every namespace, so deliberately slower. Must stay above the group poll |
| `config.requestTimeoutSeconds` | `15` | per-request timeout against a cluster's API server |
| `logLevel` | `INFO` | `DEBUG` adds per-poll timing, HTTP request lines, page counts and the binding-refresh countdown |
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
| `monitoring.serviceMonitor.enabled` | `false` | needs the Prometheus Operator CRDs |
| `monitoring.serviceMonitor.interval` / `.scrapeTimeout` | `30s` / `10s` | every series is recomputed from SQLite on scrape and each scrape takes a read snapshot. Faster buys no resolution — the data only changes once per poll |
| `monitoring.serviceMonitor.labels` | `{}` | extra metadata labels. Usually how a cluster's Prometheus selects which ServiceMonitors it owns |
| `monitoring.prometheusRule.enabled` | `false` | **eight** alerts — see below |
| `monitoring.prometheusRule.labels` | `{}` | as above, for rule selection |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | a GroupSync has not synced for this long |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot. **Must stay above ~2× `config.pollIntervalSeconds`** or it fires continuously on a healthy deployment |
| `monitoring.prometheusRule.walMiB` | `256` | MiB. 25% of the default 1Gi PVC. Raise it with `persistence.size` |
| `monitoring.prometheusRule.for.*` | see below | the `for:` duration on each alert |

The RBAC grant is conditional in two places. `coordination.k8s.io/leases`
(`get`, `create`, `update`) renders only when `leaderElection.enabled`, and `patch` on
bindings renders only when `config.unmanagedAudit.mode: annotate`. Everything else is
`get`/`list`.

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

### Unmanaged-grant audit stamping

| Key | Default | Notes |
|---|---|---|
| `config.unmanagedAudit.mode` | `"off"` | `off` \| `log` \| `annotate`. **The chart renders the `patch` RBAC grant only in `annotate`.** Anything unrecognised is treated as `off` |
| `config.unmanagedAudit.maxPerCycle` | `20` | stamps per 300s refresh. Healing (label removal) is never capped |

This is the dashboard's **only write to any cluster**, and it is off by default. When enabled
it stamps bindings it has classified `unmanaged` — a hand-made grant on an operator-synced
group, outside the policy system — so they can be found from the objects themselves rather
than only in this UI:

```bash
oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true
```

| Key written | Kind | Meaning |
|---|---|---|
| `rbac.ocp.io/unmanaged: "true"` | label | *currently* classified unmanaged — this is what the CLI selects on |
| `rbac.ocp.io/unmanaged-detected-at` | annotation | first detection, **never overwritten** — "how long has this existed unacknowledged" |
| `rbac.ocp.io/unmanaged-detected-by` | annotation | `group-sync-dashboard` |

Nothing else is ever written: not subjects, not `roleRef`, not any other key.

#### The three modes

* **`off`** — no write-path code executes at all.
* **`log`** — computes the full stamp plan and logs it, patching nothing. This is the
  rehearsal mode, and it needs **zero write access**. Useful on every cluster.
* **`annotate`** — actually patches, and `rbac.yaml` grants `patch` on
  rolebindings/clusterrolebindings only in this mode.

Roll out in that order. Sit in `log` for at least one full refresh cycle and check the
planned stamps against what you expect before enabling `annotate`.

#### Two things to know before enabling `annotate`

**1. Kubernetes caps it, and not in a way more RBAC can fix.** Privilege-escalation
prevention means that to patch an RBAC object — even a metadata-only merge patch touching
no rule and no subject — the writer must already hold every permission that object grants.
So the dashboard cannot stamp a binding granting `cluster-admin` unless it *is*
cluster-admin, which inverts what a read-only auditing tool should be. It fails safe: each
refusal is a logged warning, the refresh continues, and the finding stays visible in the UI
and at `GET /api/clusters/{id}/bindings/findings`. In practice `annotate` stamps the
low-privilege grants and skips exactly the ones you care about most.

Note that `oc auth can-i` will tell you this works — `SelfSubjectAccessReview` returns
`allowed: true` because the RBAC grant is genuinely correct. The escalation check runs
afterwards and refuses anyway.

**2. There is no annotations-only patch scope in Kubernetes RBAC.** `annotate` mode
therefore grants `patch` on bindings, and a subject holding that verb can technically modify
what a binding grants. The application never does — the patch body is built in one function
and contains only the three keys above — but the *capability* is real, and an attacker who
compromised the pod would inherit it. That is why the default is `off` and why `log` exists.

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

Set `argocd.enabled=true`. It adds annotations for two problems that each cost you
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
  # Without this, the injected CA bundle is reverted on every sync.
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
```

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
