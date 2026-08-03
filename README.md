# OCP Access Control Dashboard

Read-only observability for the
[redhat-cop group-sync-operator](https://github.com/redhat-cop/group-sync-operator).
It observes; it never creates or edits a GroupSync CR.

Everything it surfaces is an *absence* — and absences are what a human scanning `oc get`
output does not notice. None of these raise an event or a failed reconcile:

| Failure | How it presents without this |
|---|---|
| A RoleBinding names a Group that does not exist | nothing — the binding looks healthy and grants nobody |
| Group synced but empty | nothing — a blank USERS column |
| CR not honouring its schedule | nothing until you diff timestamps by hand |
| A group silently stopped being refreshed | nothing — the CR still reports success |
| A user quietly dropped out of a group | nothing — no event, no log |
| A CR whose schedule is unparseable | nothing — it simply never runs again |
| A NamespaceConfig stopped reconciling | nothing — RBAC silently stops being templated, and both its conditions stay `True` |
| A RoleBinding names a **person** instead of a group | nothing — and it survives offboarding, because removing them from LDAP revokes nothing |
| A hand-made grant on an operator-synced group | nothing — it looks identical to one the policy system produced |

On the reference cluster it finds **9 RoleBindings granting `admin`, `view` and `edit` to
groups that have never existed** — access reaching nobody, in three namespaces, which
`oc get rolebinding` reports as perfectly healthy.

## Layout

| Where | What |
|---|---|
| [`docs/reference-architecture.md`](docs/reference-architecture.md) | **start here to operate or extend it** — components, poll and request flow, data model, concurrency, security, and the reason behind each deliberate constraint |
| [`charts/group-sync-dashboard/`](charts/group-sync-dashboard/README.md) | the Helm chart — how you deploy it, and every value |
| [`local-development/`](local-development/README.md) | the application, tests and build tooling |
| [`local-development/API.md`](local-development/API.md) | every endpoint, what each field means, the ones routinely misread |

Reading it from outside the cluster, and extending it:

| Document | What |
|---|---|
| [`docs/api-access.md`](docs/api-access.md) | calling `/api` with `curl` or Postman — the token exchange, and the two Postman defaults that break it |
| [`docs/api-contract.md`](docs/api-contract.md) | the seven rules a new endpoint must satisfy, each enforced by a test |
| [`docs/updating-vendored-assets.md`](docs/updating-vendored-assets.md) | refreshing the Swagger/ReDoc bundles and the fonts, and why they live in git |

Design notes, for the decisions that are not obvious from the code:

| Document | What |
|---|---|
| [`docs/storage-coupling.md`](docs/storage-coupling.md) | why SQLite, the storage seam, and what a second backend would have to satisfy |
| [`docs/unmanaged-audit-design.md`](docs/unmanaged-audit-design.md) | unmanaged-grant discovery, its invariants, and the live-cluster measurement that removed the write path |
| [`docs/image-vulnerability-scan.md`](docs/image-vulnerability-scan.md) | the CVE position, what is reachable, and what a rebuild cannot fix |
| [`docs/namespace-report-design.md`](docs/namespace-report-design.md) | **PARKED** — per-namespace PDF reports, and the definitive answer on `--openshift-sar` |

## Install

```bash
helm install group-sync-dashboard charts/group-sync-dashboard \
  --namespace group-sync-dashboard --create-namespace
```

For anything you will upgrade later, put the release's configuration in a file and pass it
every time — see [`environments/`](environments/README.md):

```bash
helm upgrade --install group-sync-dashboard charts/group-sync-dashboard \
  -n group-sync-dashboard -f environments/crc.yaml
```

Helm resets to chart defaults the moment `-f` or `--set` is given, keeping only what that
invocation passed, so `--set` is **not** additive across upgrades. Measured on this chart: a
later `helm upgrade --set logLevel=DEBUG` silently dropped an unrelated feature switch and
reported success.

That is enough. The host is derived from the cluster's own apps domain, the image comes from
a public registry, the OAuth proxy is on by default, and the dashboard observes the cluster
it runs on using the pod's projected ServiceAccount token — which kubelet rotates and the app
re-reads every poll, so there is no long-lived credential to mint or expire.

Every value is documented in
[`charts/group-sync-dashboard/values.yaml`](charts/group-sync-dashboard/values.yaml). The
ones most likely to matter:

| Value | Default | Why you would change it |
|---|---|---|
| `oauthProxy.enabled` | `true` | **Leave it on.** With it off the route is unauthenticated and the dashboard exposes group membership |
| `ingress.host` | derived | Set explicitly if you do not want `<name>-<ns>.<apps domain>` |
| `clusters` | the local cluster | Add entries to observe others |
| `trustedCA.*` | injected on | Corporate CAs for external clusters — see below |
| `persistence.enabled` | `true` | Leave on. The accumulated history cannot be re-fetched |
| `config.backup.enabled` | `true` | Leave on. The only protection for that history, though it lands on the same volume |
| `config.userActivity.visibility` | `self` | `all` lets everyone see everyone's dashboard usage. It is identifiable personnel data |
| `config.unmanagedAudit.mode` | `log` | `log` publishes each hand-made grant it finds to the pod log; `off` silences that log only. Writes nothing either way — see below |
| `monitoring.serviceMonitor.enabled` | `false` | Needs the Prometheus Operator CRDs |
| `replicaCount` | `1` | Leave at 1. Above one, each pod keeps its own database and history diverges — see the chart README's Scaling section |
| `config.pollIntervalSeconds` | `60` | Poll cadence, and the error bar on "when did this person lose access?" |
| `logLevel` | `INFO` | `DEBUG` adds per-poll timing and HTTP request lines |

## Authentication

`oauthProxy.enabled=true` puts cluster login in front of the dashboard, as a sidecar.

For the **UI**, it is authentication, not authorization: anyone who can log into the cluster
can view. That is the OpenShift provider's documented default. Set `oauthProxy.sar` to a
SubjectAccessReview if you need to restrict who may open it at all.

Be precise about what that exposes, because an earlier version of this paragraph was not.
It said the dashboard "shows nothing a user could not already read with `oc get groups`".
That is true of the Groups tab and of nothing else. The dashboard reports the cluster's whole
RBAC **binding** surface — every ClusterRoleBinding and RoleBinding, the role each grants,
and which subjects hold it — which reading Groups does not give you. Treat UI access as
equivalent to cluster-wide RBAC read, and set `oauthProxy.sar` accordingly if that is not
who you want looking.

The **API** is gated properly. `oauthProxy.apiTokenAccess.enabled` lets a bearer token read
`/api`, and the delegated review demands `list clusterrolebindings` cluster-wide — the honest
floor for that data. Verified: an identity without it gets `403` where it would otherwise have
read every binding on the cluster. See [`docs/api-access.md`](docs/api-access.md).

Turning the proxy on also switches the Ingress to `reencrypt`, binds the app to `127.0.0.1`
so the proxy cannot be bypassed from inside the cluster, and moves the probes behind
`skip-auth-regex` — all handled by the chart.

The proxy image is `registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.15`, an explicit
version rather than a tag whose digest tracks the cluster's release payload. It needs
registry.redhat.io credentials, which a cluster's global pull secret normally already carries;
`values.yaml` records how to check and how to fall back to the internal imagestream.

## Trusting corporate CAs

External clusters are usually signed by a corporate CA that is absent from the default trust
store. Without it, verification fails and the cluster renders as **unreachable** — a TLS
problem that presents as an outage. Two sources, either or both:

```yaml
trustedCA:
  injected:
    enabled: true          # OpenShift fills this from proxy/cluster.spec.trustedCA
  existingConfigMap:
    enabled: false         # a ConfigMap you create yourself
    name: enterprise-ca
    key: ca-bundle.crt
```

**Injected** needs nothing from you: an empty ConfigMap labelled
`config.openshift.io/inject-trusted-cabundle: "true"` is populated by the network operator
with the system trust store merged with the cluster's configured CA. Measured on a stock
cluster: 148 certificates.

**existingConfigMap** is for a CA the cluster has never been told about — a partner's
internal CA, a lab signer, an external cluster outside your corporate bundle:

```bash
oc create configmap enterprise-ca --from-file=ca-bundle.crt=/path/to/ca.pem \
  -n group-sync-dashboard
```

It is deliberately not templated from values: certificates put in `values.yaml` end up in
git, in `helm get values`, and in any CI log that echoes them.

A cluster entry naming its own `caBundleFile` always wins — that is a specific statement
about what it trusts, and silently widening it would be the wrong kind of helpful.

## Monitoring

`/metrics` serves Prometheus exposition; the chart ships a ServiceMonitor and eight alerting
rules, both off by default because they need the Prometheus Operator CRDs.

Cardinality is bounded deliberately: series are per cluster and per GroupSync CR only, never
per group or per user. That is a scale concern — 500 groups must not mean 500 series — and a
disclosure one, since `/metrics` is unauthenticated so a ServiceMonitor can reach it.

`gsd_groupsync_last_sync_timestamp_seconds` is a unix timestamp rather than a precomputed age
or boolean, so the threshold lives in the alert where it can be seen and tuned:

```promql
(time() - gsd_groupsync_last_sync_timestamp_seconds) > 7200
```

The alert worth knowing about is `GroupSyncDashboardNotPolling`. It catches a dead poll loop,
which the health endpoints structurally cannot: `/healthz` is unconditional and `/readyz`
only reads the store, so both stay green while the dashboard serves frozen data.

Two more cover SQLite, and are the other failures where the pod stays Ready and nothing else
looks wrong. `GroupSyncDashboardWalGrowing` catches a write-ahead log that is not being
checkpointed — checkpoints yield to open readers, so a steady read load can starve them, and
the WAL grows until the volume fills while the database file stays small.
`GroupSyncDashboardWalDisabled` catches WAL never having engaged: it is requested at startup
but a filesystem without working shared memory (NFS, EFS, SMB) refuses it silently, and reads
then block on every write.

The remaining five are `GroupSyncOverdue`, `DanglingRoleBinding`,
`GroupSyncClusterUnreachable`, `GroupSyncDashboardConfigReconcileError` (a `NamespaceConfig`
or `GroupConfig` has stopped reconciling, so RBAC is no longer being templated) and
`GroupSyncDashboardDirectUserGrants` (grants that still name a person — a migration backlog,
deliberately given a one-hour `for` so it is visible without paging anyone). The chart README
lists all eight with their thresholds.

## Building and shipping

```bash
cd local-development
cp .env.example .env && chmod 600 .env && $EDITOR .env
./build-and-push-external.sh --update-values     # build, push, pin the tag into values.yaml
helm upgrade --install group-sync-dashboard ../charts/group-sync-dashboard -n group-sync-dashboard
```

Images are tagged `<version>-<git-sha>`, the commit is stamped into the image and served at
`/api/version`, and the build refuses a dirty tree unless you pass `--allow-dirty`. All of
that exists because "the image was built before the fix and deployed after it" happened here,
and nothing revealed it.

Full detail, including CRC-specific traps, in
[`local-development/README.md`](local-development/README.md).

### Publishing from `main`

[`.github/workflows/publish.yml`](.github/workflows/publish.yml) runs **that same script** on
every merge to `main`, then commits the resulting tag into the chart's `values.yaml`. So the
published image is the merge commit, and the chart records which one — rather than whichever
working tree last ran the script by hand. The local path is unchanged and still does both.

Configure once, under **Settings → Secrets and variables → Actions**:

| | Name | Value |
|---|---|---|
| **Secret** | `REGISTRY_USERNAME` | Quay robot account, e.g. `ephico2real+github_ci` |
| **Secret** | `REGISTRY_PASSWORD` | that robot's token — not a personal password |
| Variable (optional) | `REGISTRY` | defaults to `quay.io` |
| Variable (optional) | `REGISTRY_NAMESPACE` | defaults to `ephico2real` |

The names deliberately match what the script already reads from `.env`, so one name means one
thing locally and in CI. Registry and namespace are **variables, not secrets** — they are not
sensitive, and as secrets they would be masked in exactly the logs where you want to see which
registry a run pushed to.

Two properties worth knowing:

- **The pin commit carries `[skip publish]`**, and the workflow skips on that marker. Without it
  the commit would retrigger the workflow, which would publish, which would commit again.
- **Re-running a commit is safe.** The tag embeds the commit sha, so the same tag can only ever
  mean the same source; a re-run pushes an identical image and the pin step finds nothing to
  change. There is no tag to accidentally overwrite with different content.

Credentials are never put on a command line — `secrets` go to the step's `env` and the script
pipes the password to `podman login --password-stdin`. That is also why the workflow checks for
the secrets in a step rather than in a job `if:`: per
[GitHub's docs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets),
"secrets cannot be directly referenced in `if:` conditionals".

## What it shows

Six tabs.

**Overview** — per cluster: reachable, CR count, group count, empty and unattributed groups,
bindings needing review, oldest last sync, and the health of the
namespace-configuration-operator's CRs. Alongside it, the computed alerts.

Drill into a CR for its schedule, LDAP filter, last sync, next expected (from a real cron
parser), the accumulated sync timeline, and the groups it owns.

**Groups** — every group, filterable to `empty` and `unattributed`. Drill in for members,
when each was first seen, the membership change log, and the access the group grants. From
any member, the reverse lookup: every group that user belongs to and every binding that
reaches them, each row naming the group that confers it. The cluster can only answer that by
scanning every Group object by hand.

**Access granted** — every group-subject binding, classified `ok`, `dangling` (the group was
operator-managed and has disappeared), `unresolved` (names a group that has never existed),
`built_in` (Kubernetes virtual groups, expected), or `unmanaged` (a hand-made grant on a
synced group, outside the policy system). Filterable, defaulting to what needs review.

**RBAC policy** — the namespace-configuration-operator's `NamespaceConfig` and `GroupConfig`
CRs beside the provenance of the bindings they template. These CRs are the other half of the
access pipeline: group-sync creates the groups, these grant them their access. A failing one
means RBAC has silently stopped reconciling — new namespaces get nothing, drift stops being
corrected, and nothing else on the cluster reports it. The tab shows nothing at all on a
cluster without the operator, which is auto-detected and deliberately distinct from
"installed with zero CRs".

**Namespace audit** — bindings that name a **person** rather than a group, ranked per
namespace by the worst privilege granted there rather than by count: one forgotten
`cluster-admin` outranks twenty `view` grants. Sortable columns, a namespace selector, and
server-side paging — the filter is applied in SQL, not by trimming a full response in the
browser. Platform identities and `kubeadmin` are excluded and the count of what was left out
is always reported.

These are the governance violation in its purest form. They survive offboarding: removing
someone from an LDAP group revokes their access everywhere at once, while a binding that
names them keeps granting until somebody remembers it exists — and no group-based access
review can see it.

**Usage** — who used the dashboard, one row per user per UTC day. Self-scoped by default;
requires the OAuth proxy, because without it there is no authenticated identity to attribute
anything to.

Every binding view is **direct bindings only**. Role rules are never fetched or expanded, and
the UI says so — an incomplete effective-permission calculation could show access as absent
when it is not, and a false negative there gets an incident closed wrongly.

## The one thing it writes

`config.unmanagedAudit.mode` is `off` by default, and off means no write-path code executes
at all. Turned on, it stamps bindings it has classified `unmanaged` so they can be found from
the objects themselves rather than only in this UI:

```bash
oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true
```

`log` mode computes and logs the full plan with **zero write access** — run that first.
`annotate` mode patches, and the chart renders the `patch` RBAC grant only in that mode.
Nothing but three metadata keys is ever written: not subjects, not `roleRef`.

Kubernetes caps it in a way more RBAC cannot fix, and `oc auth can-i` will not tell you.
Design, invariants and the live-cluster evidence:
[`docs/unmanaged-audit-design.md`](docs/unmanaged-audit-design.md).

## Two things to know before reading a screen

**The API keeps no history.** A CR carries one timestamp and each Group carries one of its
own, so timelines and membership changes are *accumulated* by polling. An empty timeline
means this dashboard has not seen a sync yet — not that the operator never synced.

**`ReconcileError` is sticky.** The operator never clears it on a later success, so a healthy
CR carries both `ReconcileSuccess` and `ReconcileError` at `status: True` indefinitely. An
error counts as current only when its `lastTransitionTime` is newer than the success's;
reading the condition's status alone would paint a healthy CR permanently red.

## Reading it across a fleet

The dashboard deploys **per cluster** and publishes its own API at a predictable hostname, so
an aggregator does not have to host or store anything — it reads each cluster and composes:

```bash
read -rs GSD_PASSWORD && export GSD_PASSWORD
local-development/cluster-report.py \
  --clusters prod,staging,dev --domain example.com --ldap-user svc-reporter
```

Credentials are exchanged for a short-lived token against each cluster's own OAuth server —
the same PKCE sequence `oc login -u -p` performs — so no `oc` and no kubeconfig are involved.
One exchange per cluster, because an OpenShift token is issued by one cluster and meaningless
to another. A cluster that cannot be reached appears in the report as `UNREACHABLE` rather
than silently missing.

Requires `oauthProxy.apiTokenAccess.enabled` and a calling account with cluster-wide RBAC
read. Recipes for `curl` and Postman: [`docs/api-access.md`](docs/api-access.md).

## Not built yet

Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), retention on the accumulated history, per-namespace PDF reports
(designed and **parked** — [`docs/namespace-report-design.md`](docs/namespace-report-design.md)),
and per-cluster authorization for the multi-cluster case: OAuth authenticates against the
hosting cluster only, so one instance holding several clusters' data can show a user
membership from a cluster they have no rights on. Deploying per cluster and aggregating
through the API, as above, avoids that entirely.
