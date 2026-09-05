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

* OpenShift 4.x — the chart uses a `Route`, `service-ca` and the OAuth proxy. On plain
  Kubernetes, set `route.enabled=false`, `ingress.enabled=true`, `oauthProxy.enabled=false`,
  `trustedCA.injected.enabled=false`, `loginCapture.enabled=false` (its Role lives in
  `openshift-authentication`) and supply `ingress.host` and `ingress.className` yourself.
* A default StorageClass, or set `persistence.storageClass` / `persistence.existingClaim`.
* Cluster admin **once**, to create the ClusterRole. The dashboard needs no admin at runtime.
* The Prometheus Operator CRDs, only if you enable `monitoring.serviceMonitor` or `monitoring.prometheusRule`. The Grafana dashboard (`monitoring.grafanaDashboard`) is a plain ConfigMap and needs no CRD.

## Values

### Image

| Key | Default | Notes |
|---|---|---|
| `image.repository` | `quay.io/ephico2real/group-sync-dashboard` | written by `build-and-push-external.sh --update-values` |
| `image.tag` | `""` | empty resolves `Chart.appVersion`; set it to pin an exact build |
| `image.digest` | `""` | **wins over `tag`.** The only immutable pin — a tag is a name that can be repointed, a digest is the content. Renders `repository@sha256:…`; a malformed value fails the render |
| `image.pullPolicy` | `Always` | pure overhead when `digest` is set, since the content cannot change |
| `image.pullSecrets` | `[]` | leave empty for a public repo — an empty secret *reference* fails scheduling rather than falling back to anonymous pull |

### Authentication

| Key | Default | Notes |
|---|---|---|
| `oauthProxy.enabled` | `true` | **leave it on.** With it off the route is unauthenticated and exposes group membership |
| `oauthProxy.image` | `registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.15` | needs registry.redhat.io credentials, which the cluster's global pull secret normally already carries. Override to the internal imagestream or a mirror if not — see `values.yaml` |
| `oauthProxy.imagePullPolicy` | `IfNotPresent` | the image is already on the node as an imagestream |
| `oauthProxy.port` | `8443` | |
| `oauthProxy.cookieSecret` | `""` | generated once and reused across upgrades |
| `oauthProxy.cookie.expire` | `4h` | absolute session cap, a Go duration. There is deliberately no `refresh` key: measured on `provider=openshift`, `-cookie-refresh` force-clears the session at every interval instead of sliding it, so the chart refuses a values file that sets it |
| `oauthProxy.proxyPrefix` | `/oauth` | the prefix everything the proxy serves lives under; the app composes its sign-out link from it |
| `oauthProxy.logoutUrl` | `""` | where the browser lands after sign-out; empty means this dashboard's own unauthenticated `/signed-out` page |
| `oauthProxy.skipAuthRegex` | `^/(healthz\|readyz\|metrics)$` | the health paths **must** stay, or kubelet gets a 302 and kills a healthy pod |
| `oauthProxy.sar` | `""` | empty = authentication only. Set a SubjectAccessReview to also require a permission |
| `oauthProxy.skipProviderButton` | `false` | `false` shows an explicit **Log In** button. `true` skips straight to the OAuth server — one fewer click, but any mid-flow failure then lands on the proxy's own page headed "403 Permission Denied", which reads as *you are not allowed in* rather than *your session expired*. Observed here after a rollout landed between redirect and callback |
| `oauthProxy.requestLogging` | `false` | opt-in: the proxy logs the complete request URI, query string included, so the OAuth callback's authorization code would land in the pod log; enable only behind query-string redaction |
| `oauthProxy.resources` | 10m/64Mi → 200m/256Mi | |
| *(no `redirectMode` key)* | — | the ServiceAccount's OAuth callback form follows what exposes the dashboard and cannot be set separately: `oauth-redirectreference` naming the chart's Route with the default `route.enabled`, `oauth-redirecturi` with a literal URL when the Ingress is used instead. A `redirectMode` key existed once, read by nothing; it is gone |

Enabling it also switches the Ingress to `reencrypt`, binds the app to `127.0.0.1`, and
moves the probes behind the proxy. All automatic.

### Trusted CAs

| Key | Default | Notes |
|---|---|---|
| `trustedCA.injected.enabled` | `true` | empty ConfigMap OpenShift fills from `proxy/cluster.spec.trustedCA` |
| `trustedCA.existingConfigMap.enabled` | `false` | a ConfigMap you create out of band |
| `trustedCA.existingConfigMap.name` | `enterprise-ca` | |
| `trustedCA.existingConfigMap.key` | `ca-bundle.crt` | |
| `trustedCA.existingConfigMap.subjectHash` | `""` | `openssl x509 -noout -subject_hash` of that CA, optionally with a `.N` collision suffix; when set, it is also mounted as `/etc/pki/tls/certs/<hash>.0` (or `.N`) so curl in the pod trusts it |
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

**curl inside the pod** reads none of the above; measured in the image, it trusts only the base's
own bundle. So the chart gives curl its own configuration: a ConfigMap mounted at `/etc/curl`
with a `.curlrc` that curl finds through `CURL_HOME`, naming the injected bundle as `cacert`
(when injected is on) and OpenSSL's hashed directory `/etc/pki/tls/certs` as `capath`. A file
rather than `CURL_CA_BUNDLE` and `SSL_CERT_DIR`, because curl ignores the second whenever the
first is set (measured on curl 7.76 and 8.22), so the variables could never name both stores.
Only the curl tool reads that file; the dashboard's own TLS is untouched. Two consequences worth
knowing: the injected ConfigMap is empty until OpenShift fills it, moments after creation, and
curl fails with exit 77 for every URL while it is — the dashboard's own polling does not read
`.curlrc` and is unaffected; and the manual ConfigMap is never curl's `cacert`, because it
carries only the extra CA and one `cacert` replaces the default bundle. Without the hash below,
an in-pod curl to a URL signed by that CA takes `--cacert`. With it, the manual CA is mounted
into the hashed directory as well, the way Hummingbird's Python guidance describes:

```bash
openssl x509 -noout -subject_hash -in /path/to/ingress-ca.pem      # e.g. c275f070
helm upgrade ... --set trustedCA.existingConfigMap.enabled=true \
  --set trustedCA.existingConfigMap.subjectHash=c275f070      # or c275f070.1 on a collision
```

With that, curl, `urllib` and the dashboard's fallback context all trust it. One address stays
outside both: the in-cluster API (`https://kubernetes.default.svc`) is signed by the cluster's
own CA, which is in the ServiceAccount's `ca.crt` and not in the injected bundle — measured on
CRC — so an in-pod curl to it takes
`--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt`, as it always did; the dashboard
names that file explicitly for the local cluster. Enforced by
`test_chart_strategy.py::TestCurlInThePodTrustsWhatTheAppTrusts`.

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
| `config.alerts.groupCountCliff.enabled` | `true` | read-only, no extra RBAC, one indexed query per cluster per read. Off removes the kind and the rule together |
| `config.alerts.groupCountCliff.minMembers` / `.dropRatio` / `.windowHours` | `10` / `0.5` / `24` | the floor is what keeps the default quiet — below ten, half is one or two people. Ratio outside `(0, 1]`, floor below 1 or non-positive window refuse the render |
| `config.alerts.groupCountCliff.silence` | `[]` | exact names or fnmatch globs. Silenced cliffs are still reported (`group_count_cliff_silenced`), dimmed on the Overview. The other silence is the Group annotation `groupsync-dashboard.io/silence-group-count-cliff=true` or `=until=YYYY-MM-DD`, read on every poll, never written |
| `logLevel` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL`, and nothing else — see [Dashboard log verbosity](#dashboard-log-verbosity--loglevel) for what each promises and which look-alike values are refused |
| `ui.export.enabled` | `true` | CSV/JSON download of the table on screen, built in the browser from what the server served this reader; the file says when the page was partial. Off removes the control |
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
cover corruption, a bad migration and accidental deletion — not loss of the volume. The other
half is `backup.offsite` below: a CronJob mounting the same claim read-only. The dashboard
itself never grows credentials for object storage.

### Off-volume backup — `backup.offsite`

**Off by default** — it needs a destination the chart cannot choose for you. Once on, the copy is
hashed, opened and integrity-checked before it counts, and the Job fails loudly otherwise.
Restore and verification: [`docs/RUNBOOK_backup_restore.md`](../../docs/RUNBOOK_backup_restore.md).

| Key | Default | Notes |
|---|---|---|
| `backup.offsite.enabled` | `false` | renders a CronJob, a ConfigMap with `scripts/offsite_backup.py`, a grant-less ServiceAccount, and (type `pvc`, no `existingClaim`) a second PVC. **Refused** with `persistence.enabled=false`, `config.backup.enabled=false`, a `config.backup.dir` outside `/data/`, or a `ReadWriteOncePod` data volume |
| `backup.offsite.schedule` | `"15 */6 * * *"` | cron; match `config.backup.intervalHours`. The app's backups run on a timer from pod start, so there is nothing to align to |
| `backup.offsite.concurrencyPolicy` | `Forbid` | a slow copy must not overlap the next |
| `backup.offsite.successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | `3` / `3` | |
| `backup.offsite.startingDeadlineSeconds` | `900` | a slot missed by more than this is skipped |
| `backup.offsite.activeDeadlineSeconds` | `1800` | wall clock on the attempt, Pending included |
| `backup.offsite.backoffLimit` | `1` | the script is idempotent, so a retry is safe |
| `backup.offsite.resources` | 50m/64Mi – 500m/256Mi | |
| `backup.offsite.destination.type` | `pvc` | `pvc` \| `s3` |
| `backup.offsite.destination.pvc.existingClaim` | `""` | empty creates `<fullname>-backup-offsite` with `helm.sh/resource-policy: keep`. **Refused** if it names the data claim |
| `backup.offsite.destination.pvc.size` | `5Gi` | `keep` × roughly the database size |
| `backup.offsite.destination.pvc.storageClass` | `""` | use a **different** class from `persistence.storageClass` — a second claim on the same failing storage is not off it |
| `backup.offsite.destination.pvc.accessMode` | `""` | empty derives `ReadWriteOnce` |
| `backup.offsite.destination.pvc.keep` | `14` | copies kept at the destination, newest first; `0` keeps everything; sidecars go with their copies |
| `backup.offsite.destination.s3.existingSecret` | `""` | **required for `s3`.** Keys `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`; optional `S3_ENDPOINT`, `S3_PREFIX`, `AWS_DEFAULT_REGION`, `AWS_CA_BUNDLE`. Give it `PutObject` only and prune with a bucket lifecycle rule — there is deliberately no `keep` for `s3` |
| `backup.offsite.destination.s3.image.repository` / `.tag` / `.pullPolicy` | `""` / `""` / `IfNotPresent` | **required for `s3`**: an image with an S3 CLI. The default command is for the AWS CLI |
| `backup.offsite.destination.s3.command` | `[]` | replaces the default upload command; the verified copy and its `.sha256` are under `/stage` |
| `backup.offsite.destination.s3.stagingSizeLimit` | `2Gi` | the emptyDir between the verify and upload containers |

Under a `ReadWriteOnce` data volume the CronJob pod is pinned to the dashboard's node (required
`podAffinity`); under `ReadWriteMany` it runs anywhere. The pod does **not** carry the Service's
selector labels, so it never receives dashboard traffic while it copies. With
`persistence.existingClaim`, set `persistence.accessMode` to that claim's mode — the chart cannot
read the live claim and refuses to guess.

**Enable without `--wait`.** On a `WaitForFirstConsumer` StorageClass the destination claim binds
when the first Job mounts it, up to one schedule slot later; `helm upgrade --wait` times out on
that, and a timed-out upgrade is a failed revision whose objects Helm does not own until the next
successful one. Run the copy by hand right after enabling (the runbook's §2) and the claim binds
in a minute; Argo CD shows it Progressing until then.

### Retention on the history

| Key | Default | Notes |
|---|---|---|
| `config.retention.membershipEventsDays` | `0` | `0` keeps forever — one row per join/leave, ~1 MB/year, and the answer to "when did this person lose access?". Set a window only as a deliberate policy |
| `config.retention.syncEventsDays` | `730` | one row per observed sync per CR (~52k/year per ten-minute CR); names CRs and counts, never a person. `0` keeps forever |

The leader prunes **after** the cycle's backup and never before one has succeeded in its own
life — with `config.backup.enabled=false` nothing is ever deleted — 5,000 rows per table per cycle, counted into `gsd_retention_rows_deleted_total{table}`. The
API and the page state the cut (`retention.retained_since`), so a timeline that begins at the edge
is read as cut there, not started there.

A `membershipEventsDays` window shorter than `config.alerts.groupCountCliff.windowHours` does not get to
delete the rows the cliff still reads: the membership cutoff is the earlier of the two edges. A membership
window also makes a person who has left every group and never logged in unresolvable — `/users/{name}`
answers `404 unknown user` once their rows are gone, so `retention` cannot explain that absence. The default
is forever for both reasons.

**Before you restore an old `gsd-*.db` onto the live claim, set both windows to `0`.** The first
leader cycle after the new process's first successful backup releases the prune, and the default
window then deletes `sync_event` rows older than 730 days, 5,000 per cycle. The copy just taken under
`config.backup.dir` still holds the pre-prune file; the live API will not, unless the windows stay at
`0` until you have read what you restored.

### Dashboard usage tracking

Powers the **Usage** tab and `GET /api/dashboard/activity`.

| Key | Default | Notes |
|---|---|---|
| `config.userActivity.enabled` | `true` | **requires `oauthProxy.enabled`.** With the proxy off nothing is recorded whatever this says — there is no authentication, so `X-Forwarded-User` would be whatever the caller typed, and recording it would manufacture an audit trail rather than keep one. The mismatch is logged at startup |
| `config.userActivity.visibility` | `self` | `self` \| `all`. `self` means each authenticated user sees only their own rows; `all` is the blunt override that widens it to everyone, and it **wins over** the usage tier below. Anything unrecognised is treated as `self` — an unrecognised value must never be the one that widens access to a personnel dataset. Passing the WIDE `visibility.adminSar` does **not** widen this view; the separate, stricter `visibility.usageAdminSar` (below) does |
| `config.userActivity.flushSeconds` | `60` | buffered in memory and written once per interval; a write per request would put every API call behind the SQLite writer lock. An ungraceful kill loses up to this many seconds of counts |
| `config.userActivity.retentionDays` | `400` | `0` disables. A backstop for a long-lived deployment, not the growth control a request log would need — the table is aggregated to one row per user per UTC day |

`self` is the default because the response is identifiable personnel data — who was present,
on which days, between which times, how often. The argument that carries the rest of this
dashboard, "you could read the groups with `oc` anyway", is true of group membership and
false of who looked at it.

This tab now HAS an "admins only" tier — but a **stricter** one than the wide view, and that
distinction is the whole point (superseded design kept as the record of WHY). The reasoning that
first argued for *no* tier still holds and is exactly why the bar is higher: this dataset is about
the dashboard's own *readers*, not the cluster, so handing it to the wide `visibility.adminSar`
would let every `cluster-reader` — the deliberate auditor persona — browse colleagues' presence
records. Everything else the wide tier serves can be reproduced with `oc` by anyone who passes it;
Usage cannot, because it lives only in the dashboard's own database. So Usage is gated by its own
`visibility.usageAdminSar` check (below), whose default asks a *write* permission — the one thing
that separates a full `cluster-admin` from a read-only `cluster-reader`. The `all` override above
still widens it for everyone if that is what you want; and an admins-only door for the *whole*
dashboard is still `oauthProxy.sar`.

Note it cannot see logins. The proxy owns the session; the app only ever observes requests
that are already authenticated, so "session" here means the first-to-last-seen window on a
day. Above one replica it is per-pod, like the rest of the history.

### Per-user visibility

Restricted by default: an admitted reader sees only what belongs to them — their own
profile, groups, grants and login attempts — unless a SubjectAccessReview, asked by the app
as its own ServiceAccount and naming the reader and their groups, passes the check below.
An indeterminate review (API error, timeout) always yields the narrow view, never the wide
one, and a revoked administrator keeps the wide view for at most the tier cache TTL (60s)
plus one in-flight page.

| Key | Default | Notes |
|---|---|---|
| `visibility.enabled` | `true` | reaches the app as `GSD_ENABLE_VIEW_RESTRICTIONS` on the Deployment — one wire, and the spelling is load-bearing. **`false` restores everyone-sees-everything**: a deliberate, recorded choice, since it re-exposes the full RBAC binding surface and every person's login failures to any account that can log in. Requires `oauthProxy.enabled` — the chart refuses to render a per-user control with no trusted identity |
| `visibility.tierTtlSeconds` | `60` | how long a **decided** tier is cached, per viewer, in whole seconds; serves both thresholds, each with its own cache. Larger means a reader removed from an admin group keeps the wide view for up to that long — the fail-open direction, and why the default is a minute. Smaller means a SubjectAccessReview plus a group read per reader per request, measured at 97ms on the 65-group reference cluster. `0` disables caching. An **error** is never cached, so this never extends an API-server outage. A fractional or negative value fails the render, because the app would cast it with `int()`, fall back to 60, and leave your values file describing a cache that is not running |
| `visibility.adminSar.apiGroup` / `.resource` / `.verb` | `rbac.authorization.k8s.io` / `clusterrolebindings` / `list` | the check a reader must pass to see everything. The default admits `cluster-admin` and `cluster-reader`; `list` `rolebindings.rbac.authorization.k8s.io` also admits cluster-wide `admin`; `edit`/`view` pass no cluster-scoped list at all, and `cluster-edit`/`cluster-view` do not exist as roles. A miscased or versioned shape fails the render — RBAC matching is exact and lowercase, so it would not error at runtime, it would silently demote every administrator |
| `visibility.adminSar.namespace` | `""` | empty = a cluster-scoped check, the normal case. Set it only for a deliberately namespaced threshold such as `get` `pods/log` in `openshift-authentication` |
| `visibility.usageAdminSar.apiGroup` / `.resource` / `.verb` | `rbac.authorization.k8s.io` / `clusterrolebindings` / `update` | the SECOND, STRICTER check, for the **Usage tab alone**. The Usage dataset lives only in the dashboard's own database — unreproducible with `oc` — so it must not fall to the wide tier that `cluster-reader` also passes. No *read* check separates `cluster-admin` from `cluster-reader` (the latter may read everything), so the default asks a *write* verb, which `cluster-admin` holds and `cluster-reader` does not. **The dashboard never writes; a SubjectAccessReview only asks whether the subject could.** Independent of `adminSar`: separate review, separate cache. Same exact-lowercase render guard — a miscased or versioned shape fails the render |
| `visibility.usageAdminSar.namespace` | `""` | empty = a cluster-scoped check, the normal case, which `update clusterrolebindings` is |

Grant the wide view through your normal RBAC process, never a chart value:

### Workload

| Key | Default | Notes |
|---|---|---|
| `replicaCount` | `1` | **1 is the recommendation.** See [Scaling](#scaling) — above one, each pod keeps its own database and history diverges |
| `strategy` | `""` | derived: `Recreate` at one replica, `RollingUpdate` above. Set explicitly to override |
| `leaderElection.enabled` | `true` | only the lease holder polls. **Best-effort, not a write fence** — see [Leader election](#leader-election). Must be `false` above one replica; the chart refuses to render otherwise |
| `leaderElection.leaseName` | `group-sync-dashboard` | the `coordination.k8s.io` Lease object's name, in the release namespace. Two releases in one namespace must not share it |
| `podDisruptionBudget.enabled` | `true` | on one replica this governs **drains**, not availability — see below |
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
| `route.enabled` | `true` | an OpenShift Route the chart owns, named like the Service. **Needs no host at render time**: the router names it from `spec.subdomain` and reports it in `status`, so it renders under ArgoCD, Flux and plain `helm template` with no cluster and no per-cluster value — see [Deploying with ArgoCD](#deploying-with-argocd). Both flags on fails the render, as a policy: one front door |
| `route.host` | derived | `<fullname>.<cluster apps domain>` — the release name, **never the namespace**. Set it only to pin the name, e.g. for a second release in another namespace, which would otherwise be refused with `HostAlreadyClaimed`. An `ingress.host` carried over from an older values file is honoured too, so an upgrade never moves a pinned URL |
| `route.termination` | `edge` | `spec.tls.termination`. Forced to `reencrypt` when the proxy is on |
| `route.insecureEdgeTerminationPolicy` | `Redirect` | `spec.tls.insecureEdgeTerminationPolicy`. Omitted when empty |
| `route.annotations` | `{}` | |
| `ingress.enabled` | `false` | the alternative for plain Kubernetes; on OpenShift `ingress-to-route` converts it. **Needs the host at render time** (a hostless Ingress produces no Route at all), so with `ingress.host` empty it reads the cluster's apps domain and refuses to render with no cluster — which is every GitOps renderer, and why it is no longer the default |
| `ingress.host` | derived | `<fullname>.<cluster apps domain>` by `lookup` of `ingresses.config/cluster`. Required under `helm template` |
| `ingress.className` | `openshift-default` | |
| `ingress.termination` | `edge` | carried as `route.openshift.io/termination`, since Ingress has no field for it. Forced to `reencrypt` when the proxy is on |
| `ingress.insecureEdgeTerminationPolicy` | `Redirect` | carried as `route.openshift.io/insecureEdgeTerminationPolicy`. Omitted from the Ingress when empty |
| `ingress.annotations` | `{}` | merged after the two route annotations above, so it can override them |
| `ingress.tls` | `[]` | a standard Ingress `spec.tls` block. On OpenShift the Route annotations above are what actually take effect |
| `service.type` / `service.port` | `ClusterIP` / `8080` | the port stays 8080 in both modes; only `targetPort` moves to the proxy |

### RBAC and monitoring

| Key | Default | Notes |
|---|---|---|
| `serviceAccount.create` / `.name` / `.annotations` | `true` / derived / `{}` | with the proxy on, the SA also carries the annotation that makes it an OAuth client — no `OAuthClient` object to register. `oauth-redirectreference` (the chart's Route, by name, resolved at login time) with the default Route; `oauth-redirecturi` (a literal callback URL) otherwise |
| `rbac.create` | `true` | ClusterRole + binding, read-only, no `watch` |
| `rbac.bindings` | `true` | adds `get`/`list` on rolebindings/clusterrolebindings, powering the Access-granted, RBAC-policy and Namespace-audit views. Disable and the dashboard degrades to group data only |
| `authLogLevel.manage` | `false` | lets this chart own `spec.logLevel` on the authentication **operator** CR (`authentications.operator.openshift.io/cluster`) — not the OAuth CR, and not `operatorLogLevel`. Off by default — turning it on is what transfers ownership |
| `authLogLevel.enabled` | `false` | with `manage`, sets `Debug` (login lines appear) or `Normal`. The Job runs for **both** values: Helm does not run a Job you merely stopped rendering, so a one-way enable would strand the cluster in Debug |
| `authLogLevel.revertOnUninstall` | `true` | **leave on.** A pre-delete Job puts the level back, or removing the dashboard leaves the OAuth server naming every person who authenticates with nothing left watching |
| `authLogLevel.waitSeconds` / `.activeDeadlineSeconds` / `.revertDeadlineSeconds` | `180` / `300` / `120` | the Job polls the Deployment's `observedGeneration` rather than using `oc rollout status`, which returned success ~30s **before** the rollout began. A wait timeout is not a failure — the patch has landed |
| `rbac.users` | `true` | adds `get`/`list` on `users`. The User objects are the **source of the Users tab**: OpenShift creates one at first login, so the tab counts people who have logged in, with group membership as an attribute. Also supplies `fullName` for every member surface. Switchable off; the poll still succeeds, but the Users tab then has no source and says so by name rather than showing an empty list |
| `rbac.identities` | `false` | adds `get`/`list` on `identities.user.openshift.io` — one Identity per (provider, id), created by OpenShift at the first successful login for `mappingMethod: claim`/`add` (by an administrator beforehand for `lookup`), so its creation time is the first login where the User's is approximate; the page labels it `identity`, never "exact". Also the app's read switch (`identitiesReadEnabled`). Requires `rbac.users`; the chart refuses the pair otherwise. Off by default: a grant the chart does not otherwise need |
| `monitoring.serviceMonitor.enabled` | `false` | needs the Prometheus Operator CRDs (OpenShift ships them; the install fails on the unknown kind where they are absent). Off by default because the reference cluster runs no Prometheus; rendering with it on is verified |
| `monitoring.serviceMonitor.interval` / `.scrapeTimeout` | `30s` / `10s` | every series is recomputed from SQLite on scrape and each scrape takes a read snapshot. Faster buys no resolution — the data only changes once per poll |
| `monitoring.serviceMonitor.labels` | `{}` | extra metadata labels. Usually how a cluster's Prometheus selects which ServiceMonitors it owns |
| `monitoring.prometheusRule.enabled` | `false` | **twelve** alerts, fourteen with `backup.offsite.enabled` — see below |
| `monitoring.prometheusRule.labels` | `{}` | as above, for rule selection |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | a GroupSync has not synced for this long |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot. **Must stay above ~2× `config.pollIntervalSeconds`** or it fires continuously on a healthy deployment |
| `monitoring.prometheusRule.walMiB` | `256` | MiB. 25% of the default 1Gi PVC. Raise it with `persistence.size` |
| `monitoring.prometheusRule.captureStalledSeconds` | `1800` | seconds without a successful oauth-log read before login capture counts as stalled. Capture rides the poll thread, so this **must stay well above `config.pollIntervalSeconds`** — same reasoning as `notPollingSeconds` |
| `monitoring.prometheusRule.backupStaleSeconds` | `43200` | seconds since the newest backup file before the copy counts as stale. Keep at ~2× `config.backupIntervalHours` × 3600 — one missed backup is a blip, two is a broken mechanism |
| `monitoring.prometheusRule.offsiteBackupStaleSeconds` | `43200` | seconds since the off-volume CronJob last succeeded (`kube_cronjob_status_last_successful_time`, kube-state-metrics). Two slots of `backup.offsite.schedule`. Rendered only with `backup.offsite.enabled` |
| `monitoring.prometheusRule.for.*` | see below | the `for:` duration on each alert |
| `monitoring.grafanaDashboard.enabled` | `""` | `""` **follows `monitoring.serviceMonitor.enabled`**; `true`/`false` are explicit; anything else refuses to render. A ConfigMap labelled `grafana_dashboard: "1"` carrying `dashboards/group-sync-dashboard.json` byte-for-byte — no CRD, cannot fail an install |
| `monitoring.grafanaDashboard.folder` | `""` | written as the `grafana_folder` annotation the sidecar's `folderAnnotation` reads |
| `monitoring.grafanaDashboard.labels` / `.annotations` | `{}` / `{}` | extra metadata, e.g. a sidecar configured with a non-default label |

### Dashboard log verbosity — `logLevel`

**Five accepted values, and nothing else.** Case does not matter (`debug` works); anything outside
this list is refused at `helm template`, and refused again at startup if it reaches the container
some other way — it then runs at `INFO` and logs a warning rather than failing to start.

| value | the promise it makes |
|---|---|
| `CRITICAL` | the process cannot serve truthfully. Exactly one line in the codebase can emit it — a poll failed *and* the store could not record the failure, so the dashboard reports healthy while serving frozen data. Expect never to see it |
| `ERROR` | an operator must act; something advertised is broken and will not self-heal. Lease RBAC missing, a PVC that cannot support shared memory |
| `WARNING` | degraded but scoped or self-healing: one poll failed, one cluster unreachable, or a feature configured but inert — capture enabled without the RBAC to read pod logs |
| `INFO` | **the default.** One line per completed unit of work or state change; readable at steady state |
| `DEBUG` | this app's own reasoning: per-pod login-capture accounting, poll timing and the binding-refresh countdown, row counts per read, which replica holds the Lease and how stale its renewal is, why a reader was put on the narrow tier |

**Two things `logLevel` does not control**, both deliberate:

- **Inbound request lines.** uvicorn logs one per request on its own loggers, which carry
  `propagate=False` and their own handlers at `INFO`, so this value cannot raise or lower them. At
  `CRITICAL` you still get a line per request and lose every application diagnostic.
- **Outbound request lines.** `httpx` logs `HTTP Request: GET <url> "200 OK"` at `INFO` itself, so
  they are present at the default. The transport layer beneath it (`httpcore`, socket and TLS
  events) is pinned to `WARNING`, because unpinned it was 97% of `DEBUG` output — measured in a live
  pod, 356 framing lines per 10 of the app's own. Set `GSD_DEBUG_HTTP=true` to restore it when
  diagnosing a handshake against a corporate CA.

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

#### The twelve alerts (fourteen with `backup.offsite`)

| Alert | Fires on | `for` |
|---|---|---|
| `GroupSyncOverdue` | a CR has not synced for `overdueSeconds` | `for.overdue`, `10m` |
| `DanglingRoleBinding` | a binding grants a group that was operator-managed and has vanished | `for.dangling`, `15m` |
| `GroupSyncDashboardNotPolling` | the dashboard's own poll loop has stopped. `/healthz` is unconditional and `/readyz` only reads the store, so neither probe can see this | `for.notPolling`, `5m` |
| `GroupSyncClusterUnreachable` | `gsd_cluster_up == 0` | `for.unreachable`, `15m` |
| `GroupSyncDashboardDirectUserGrants` | bindings still name people rather than LDAP groups | `for.directUserGrants`, `1h` — long, because this is a migration backlog, not an incident |
| `GroupSyncDashboardConfigReconcileError` | a `NamespaceConfig`/`GroupConfig` is failing, so RBAC has silently stopped reconciling | `for.configError`, `10m` |
| `GroupSyncGroupCountCliff` | `gsd_alerts_total{kind="group_count_cliff"} > 0` — a group lost `dropRatio` of at least `minMembers` members within `windowHours`. Rendered only while `config.alerts.groupCountCliff.enabled`; silenced cliffs count under `group_count_cliff_silenced` and never fire | `for.groupCountCliff`, `15m` |
| `GroupSyncDashboardWalGrowing` | `gsd_sqlite_wal_bytes` above `walMiB` — checkpoint starvation | `for.walGrowing`, `30m` |
| `GroupSyncDashboardWalDisabled` | `gsd_sqlite_wal_enabled == 0` — the filesystem refused WAL | `for.walDisabled`, `10m` |
| `GroupSyncDashboardVisibilityChecksFailing` | the SubjectAccessReview behind per-user visibility is erroring, so readers are silently served the self view fail-closed | `for.visibilityFailing`, `15m` |
| `GroupSyncDashboardLoginCaptureStalled` | no successful oauth-log read for `captureStalledSeconds` while capture is enabled — the Logins page silently freezes | `for.captureStalled`, `15m` |
| `GroupSyncDashboardBackupStale` | the newest file in `backupDir` is older than `backupStaleSeconds` — the only copy of the un-refetchable history has stopped being taken | `for.backupStale`, `30m` |
| `GroupSyncDashboardOffsiteBackupStale` | *(`backup.offsite.enabled` only)* the CronJob last succeeded more than `offsiteBackupStaleSeconds` ago — nothing newer is off the volume | `for.offsiteBackupStale`, `30m` |
| `GroupSyncDashboardOffsiteBackupUnobserved` | *(`backup.offsite.enabled` only)* `kube_cronjob_status_last_successful_time` has no series for the CronJob: it has never succeeded, or kube-state-metrics is not scraped here — in which case the stale alert can never fire and this is the only signal | `for.offsiteBackupUnobserved`, `1h` |

The WAL pair and the last three are the ones with no other symptom: the pod stays Ready,
every other metric looks normal, and the first visible sign is a full volume, a latency
cliff, a narrowed view nobody reported, a frozen login record, or a backup that is not
there when the PVC dies.

#### The Grafana dashboard

`monitoring.grafanaDashboard` ships `dashboards/group-sync-dashboard.json` as a ConfigMap with the
`grafana_dashboard: "1"` label that Grafana's dashboard sidecar watches. Which namespaces the sidecar
watches is its `searchNamespace` setting: current kube-prometheus-stack defaults it to `ALL`, older
releases and the Grafana chart on its own default to the sidecar's own namespace — check your values.
A folder annotation or an extra label cannot widen that scope; they matter only once the sidecar already
sees the ConfigMap. If it watches only its own namespace, do one of:

1. install this chart in the same namespace as Grafana;
2. copy the ConfigMap into Grafana's namespace;
3. point the sidecar at every namespace (the Grafana subchart's key, nested under `grafana:` in
   kube-prometheus-stack). The `folder` value is read only where `sidecar.dashboards.folderAnnotation`
   is set to `grafana_folder` (and `provider.foldersFromFilesStructure: true`); neither is a default:

```yaml
grafana:
  sidecar:
    dashboards:
      searchNamespace: ALL
```

The board's thresholds equal the defaults above and are held to them by a test; edit them in Grafana if
you tune the rules. Panel datasource uids are `${DS_PROMETHEUS}`: Dashboards → Import resolves that
through `__inputs`; a sidecar or the operator leaves `__inputs` alone and the board's own `DS_PROMETHEUS`
variable (type datasource) selects a Prometheus datasource instead, so both paths work.

Running grafana-operator v5? It reads this ConfigMap directly. Keep the `GrafanaDashboard` in the
ConfigMap's namespace; `allowCrossNamespaceImport: true` is what lets it match a Grafana instance in
another namespace (this is the recipe that was validated on the reference cluster):

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: group-sync-dashboard
spec:
  allowCrossNamespaceImport: true
  instanceSelector:
    matchLabels:
      dashboards: grafana        # whatever your Grafana CR is labelled
  configMapRef:
    name: group-sync-dashboard-grafana-dashboard   # <fullname>-grafana-dashboard
    key: group-sync-dashboard.json
  # Bind the board's DS_PROMETHEUS input to YOUR Prometheus datasource by name. Without this the
  # provisioned board's datasource variable starts empty and Grafana picks the first Prometheus
  # datasource it has — the wrong one, silently, when there are two.
  datasources:
    - inputName: DS_PROMETHEUS
      datasourceName: Prometheus
```

The chart does not ship that CR: the operator's CRD has two incompatible API versions in the wild
and the `instanceSelector` is yours to know.

### ArgoCD

| Key | Default | Notes |
|---|---|---|
| `argocd.enabled` | `true` | adds the `argocd.argoproj.io/sync-options` annotations below, and nothing else — measured. Kubernetes ignores them without Argo, so a plain `helm install` is unaffected; under Argo, forgetting them costs the PVC on the first prune. Off only if you object to the metadata |
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
| `config.users.providers` | `[]` | identity-provider names the Users tab lists; empty means all. Applied when the tab is read; the page says which providers are shown; the never-logged-in line is not narrowed. Names must match the OAuth CR's provider `name:` — OpenShift's rule and nothing stricter: not `.` or `..`, no `:`, `/` or `%`; spaces and commas are legal and travel intact (the ConfigMap key is a list) |
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
whoever operates the cluster. The budget's selector matches the Deployment's pods only: the
`authLogLevel` hook Job pods carry `app.kubernetes.io/name`, `instance` and `component` but not
the `app` selector label, because a matched pod whose owner has no scale subresource fails the
whole budget (`SyncFailed`, `DisruptionAllowed=False`, every drain blocked — measured on the
reference cluster before the labels were split). Kubernetes reports `DisruptionAllowed=False` when it is
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
error. Measured in the deployment image (then UBI9, SQLite 3.34.1) against a lock held by another
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

**Nothing to set for the host.** The default Route needs no per-cluster value.

Chart versions before 0.8.0 exposed the dashboard through an Ingress, and under Argo the sync
failed at render time with `ingress.host is not set and the cluster apps domain could not be
read`. The reason was structural, not a bug to wait out: an Ingress must carry a host — a
hostless Ingress produces no Route on OpenShift — so with `ingress.host` empty the chart read the
cluster's apps domain with Helm's `lookup`. A plain `helm install` has a cluster and that works.
ArgoCD's repo-server renders with `helm template` and **no cluster connection**, so the lookup
returned nothing, every time, on every cluster. Argo does not support `lookup` at all
([argo-cd#5202](https://github.com/argoproj/argo-cd/issues/5202)).

The Route moves host generation onto the cluster, where the information actually is:

| | `route.enabled` (default) | `ingress.enabled` |
|---|---|---|
| host known at | admission: the router composes `<fullname>.<apps domain>` from `spec.subdomain` and reports it in `status.ingress[].host` | render time (`ingress.host` or `lookup`) |
| under `helm template` | renders | refuses to render without a host |
| OAuth callback on the SA | `oauth-redirectreference`, the Route by name, resolved at login | `oauth-redirecturi`, a literal URL |
| URL on CRC | `group-sync-dashboard.apps-crc.testing` | `group-sync-dashboard.apps-crc.testing` — the same |
| `spec` fields the server fills in | none — `spec.host` stays empty, measured on 4.18.2, so there is nothing for Argo to diff | none |

`spec.subdomain` rather than an empty `spec.host`, deliberately. Both let the cluster pick the
name, but a hostless Route gets `spec.host` **written by the API server** on create, as
`<name>-<namespace>.<domain>` — the namespace appended, and a field in the live object that git
does not carry, so Argo reports the Route OutOfSync until an `ignoreDifferences` on `/spec/host`
is added ([argo-cd#20305](https://github.com/argoproj/argo-cd/issues/20305) is exactly that
report). With `subdomain`, `spec.host` stays empty on create and on re-apply, and the host lives
only in `status`. Two caveats from the Route API: an ingress controller may ignore the suggested
subdomain and report what it assigned, and a server that does not support `subdomain` (before
OpenShift 4.11) populates `spec.host` itself, which works but brings that drift back. Login is
unaffected either way, because the redirect reference resolves against the host in `status`.

`route.host` pins the name when you need to — a second release in another namespace, which
would otherwise be refused with `HostAlreadyClaimed` in its status (Helm still reports success,
so check `oc get route`). It is never *required*.

Upgrading from the Ingress default does not trip that refusal: the controller-generated Route
carries path `/` and the chart's Route carries none, and the router's uniqueness check is per
host *and* path, so both are admitted for the moment they coexist and the old one goes with its
Ingress. Measured on CRC: same hostname before and after, no refusal recorded.

Verified end to end on CRC 4.18.2 with a release applied from plain `helm template` output,
which is ArgoCD's render: the Route was admitted with `spec.host` empty, the proxy's
`/oauth/start` redirected to the OAuth server with the router-assigned host as `redirect_uri`,
the OAuth server served its login page for that request, and the same request with a foreign
`redirect_uri` was refused with `400 invalid_request`.

The full reasoning, the platform precedent (Red Hat's own Jenkins template uses the same
reference form) and every source are in
[`docs/DESIGN_route_exposure.md`](../../docs/DESIGN_route_exposure.md).

`argocd.enabled` is on by default (since 0.8.0). It adds annotations for two problems that
each cost you something real if unhandled.

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
        # Nothing here is specific to one cluster, and nothing Argo needs is missing: the
        # default Route needs no host at render time — the router names it
        # <fullname>.<apps domain> and the ServiceAccount references the Route by name —
        # and the Argo sync-option annotations are on by default. Both values below are
        # already the chart's defaults; they are stated so that the intent is in git.
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
    # The router writes status.ingress — the assigned host, the admitting router, and a
    # lastTransitionTime that moves — once it admits the Route. None of it is in git, and
    # Routes are an aggregated API rather than a CRD, so Argo's default status-ignore for
    # CRDs does not cover them (argo-cd#2370 is this exact drift). Nothing in SPEC is
    # server-populated (see above), so this is the only entry the Route needs.
    - group: route.openshift.io
      kind: Route
      name: group-sync-dashboard
      jsonPointers:
        - /status
    # With the Ingress instead (route.enabled=false, ingress.enabled=true), replace the Route
    # entry with this one: the ingress-to-route controller writes status.loadBalancer once a
    # Route exists.
    # - group: networking.k8s.io
    #   kind: Ingress
    #   name: group-sync-dashboard
    #   jsonPointers:
    #     - /status
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
helm upgrade group-sync-dashboard . -n group-sync-dashboard -f my-values.yaml
```

**Which image that deploys, and how to choose.** From chart 0.5.0 the chart ships `image.tag: ""`
and resolves `appVersion` — so an upgrade with no tag override deploys the application version the
chart declares. Two consequences worth knowing before you run it:

- **`--reuse-values` keeps whatever tag the release already has.** A release installed from chart
  0.4.4 or earlier carries a pinned `<appVersion>-<sha>`, and `--reuse-values` preserves it, so the
  cluster keeps that exact image and never adopts the fallback. That is a legitimate choice — it is
  byte-pinned — but it is a choice, and it is easy to make by accident. Clear it deliberately with
  `--set image.tag=""` if you want the chart's default.
- **A values FILE is the better habit anyway.** Helm reuses the previous release's values only when
  you pass neither `-f` nor `--set`; the moment either appears it resets to chart defaults plus what
  this invocation supplied. Measured on this chart: one `helm upgrade --set logLevel=DEBUG` turned
  `oauthProxy.apiTokenAccess` off and reported `STATUS: deployed`.

Pin an exact build when you need byte-identical rollbacks — `appVersion` is republished when the
application version changes, and `imagePullPolicy: Always` means every container creation
re-resolves it:

```bash
helm upgrade group-sync-dashboard . -n group-sync-dashboard -f my-values.yaml \
  --set image.tag=0.7.0-db8a90510f
```

**Or pin the digest, which is the stronger form.** The `<appVersion>-<sha>` tag above is immutable
*by convention* — this project never repoints one — but it is still a name, and whoever controls the
registry can move a name. A digest is a hash of the content, so no registry can serve different
bytes under it:

```bash
skopeo inspect --no-tags docker://quay.io/ephico2real/group-sync-dashboard:0.7.0 | grep Digest
helm upgrade group-sync-dashboard . -n group-sync-dashboard -f my-values.yaml \
  --set image.digest=sha256:aa6a7f5463c6b39f8d2647ba24ae756f4e7a0b101fe05c8e5bb58d05de016a68
```

`digest` wins over `tag`, so a leftover tag in your values file cannot override it. With a digest set
you may as well drop to `--set image.pullPolicy=IfNotPresent`: re-pulling content that cannot have
changed buys nothing.

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
