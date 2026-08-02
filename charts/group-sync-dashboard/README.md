# group-sync-dashboard

Read-only observability for the redhat-cop group-sync-operator. See the
[repository README](../../README.md) for what it does and why.

## Install

```bash
helm install group-sync-dashboard . -n group-sync-dashboard --create-namespace \
  --set oauthProxy.enabled=true
```

Defaults reproduce the deployment that was verified on a live cluster, so an install with no
overrides is a working one.

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
| `oauthProxy.enabled` | `false` | **turn this on.** Without it the route is unauthenticated |
| `oauthProxy.image` | the cluster's own oauth-proxy, via the internal registry | confirm with `oc adm release info --image-for=oauth-proxy` |
| `oauthProxy.port` | `8443` | |
| `oauthProxy.cookieSecret` | `""` | generated once and reused across upgrades |
| `oauthProxy.skipAuthRegex` | `^/(healthz\|readyz\|metrics)$` | the health paths **must** stay, or kubelet gets a 302 and kills a healthy pod |
| `oauthProxy.sar` | `""` | empty = authentication only. Set a SubjectAccessReview to also require a permission |
| `oauthProxy.skipProviderButton` | `true` | skips an interstitial offering exactly one choice |
| `oauthProxy.requestLogging` | `false` | |

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
| `config.pollIntervalSeconds` | `60` | |
| `config.scheduleGraceSeconds` | `120` | stops the state flapping `late` every cycle |
| `config.bindingIntervalSeconds` | `300` | bindings are listed across every namespace, so deliberately slower |
| `config.requestTimeoutSeconds` | `15` | |
| `logLevel` | `INFO` | |

### Workload

| Key | Default | Notes |
|---|---|---|
| `replicaCount` | `1` | **1 is the recommendation.** See [Scaling](#scaling) — above one, each pod keeps its own database and history diverges |
| `strategy` | `""` | derived: `Recreate` at one replica, `RollingUpdate` above. Set explicitly to override |
| `leaderElection.enabled` | `true` | only the lease holder polls. Must be `false` above one replica; the chart refuses to render otherwise |
| `podDisruptionBudget.enabled` | `false` | on one replica this governs **drains**, not availability — see below |
| `config.sqlite.busyTimeoutMs` | `5000` | how long a write waits for a lock another connection holds. SQLite's own default is `0` — fail instantly, no retry |
| `config.sqlite.readerBusyTimeoutMs` | `2000` | deliberately shorter: `/readyz` reads, and the probe gives up at 5s |
| `config.sqlite.synchronous` | `NORMAL` | the documented companion to WAL. `FULL` fsyncs every commit |
| `config.sqlite.walCheckpointMb` | `8` | truncate the write-ahead log past this size |
| `persistence.enabled` | `true` | **keep on.** The accumulated history cannot be re-fetched from the API |
| `persistence.size` / `.storageClass` / `.existingClaim` | `1Gi` / cluster default / `""` | |
| `persistence.accessMode` | `ReadWriteMany` | scales without recreating the volume. `ReadWriteOncePod` gets an **enforced** single-pod guarantee at one replica; empty derives it. See [Storage](#storage) |
| `resources` | 50m/128Mi → 500m/512Mi | |
| `probes.*.timeoutSeconds` | `5` | not the 1s default — that killed a healthy process on host resume and cascaded into a ~4h outage |
| `podSecurityContext`, `securityContext` | non-root, read-only rootfs, all caps dropped | |
| `nodeSelector`, `tolerations`, `affinity`, `podAnnotations`, `podLabels` | empty | |

### Networking

| Key | Default | Notes |
|---|---|---|
| `ingress.enabled` | `true` | on OpenShift, `ingress-to-route` converts it |
| `ingress.host` | derived | `<fullname>-<namespace>.<cluster apps domain>`. A **hostless Ingress produces no Route at all**, so this is always emitted |
| `ingress.className` | `openshift-default` | |
| `ingress.termination` | `edge` | forced to `reencrypt` when the proxy is on |
| `service.type` / `service.port` | `ClusterIP` / `8080` | |

### RBAC and monitoring

| Key | Default | Notes |
|---|---|---|
| `serviceAccount.create` / `.name` / `.annotations` | `true` / derived / `{}` | |
| `rbac.create` | `true` | ClusterRole + binding, read-only, no `watch` |
| `rbac.bindings` | `true` | adds rolebindings/clusterrolebindings, powering the Access-granted view |
| `monitoring.serviceMonitor.enabled` | `false` | needs the Prometheus Operator CRDs |
| `monitoring.prometheusRule.enabled` | `false` | four alerts |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot |

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

Two combinations are refused at template time rather than deployed broken:

| Set | Refused because |
|---|---|
| `replicaCount > 1` with `leaderElection.enabled=true` | pods losing the lease stop polling but keep serving reads from their own database, which then never updates again |
| `replicaCount > 1` with a non-RWX volume | RWO binds one **node** and RWOP one **pod**, so under either the extra replicas stay Pending with no error on the Deployment |
| `ReadWriteOncePod` with `strategy: RollingUpdate` | deadlock — the incoming pod cannot schedule until the outgoing releases the claim, and RollingUpdate will not terminate the outgoing until the incoming is Ready |

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

`argocd.preservePVC` applies four protections, covering different moments:

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
