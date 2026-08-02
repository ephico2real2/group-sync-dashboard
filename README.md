# GroupSync dashboard

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

On the reference cluster it finds **9 RoleBindings granting `admin`, `view` and `edit` to
groups that have never existed** — access reaching nobody, in three namespaces, which
`oc get rolebinding` reports as perfectly healthy.

## Layout

| Where | What |
|---|---|
| [`charts/group-sync-dashboard/`](charts/group-sync-dashboard/) | the Helm chart — how you deploy it |
| [`local-development/`](local-development/README.md) | the application, tests, build tooling and raw manifests |
| [`local-development/API.md`](local-development/API.md) | every endpoint, what each field means, the ones routinely misread |

## Install

```bash
helm install group-sync-dashboard charts/group-sync-dashboard \
  --namespace group-sync-dashboard --create-namespace \
  --set oauthProxy.enabled=true
```

That is enough. The host is derived from the cluster's own apps domain, the image comes from
a public registry, and the dashboard observes the cluster it runs on using the pod's
projected ServiceAccount token — which kubelet rotates and the app re-reads every poll, so
there is no long-lived credential to mint or expire.

Every value is documented in
[`charts/group-sync-dashboard/values.yaml`](charts/group-sync-dashboard/values.yaml). The
ones most likely to matter:

| Value | Default | Why you would change it |
|---|---|---|
| `oauthProxy.enabled` | `false` | **Turn this on.** Without it the route is unauthenticated and the dashboard exposes group membership |
| `ingress.host` | derived | Set explicitly if you do not want `<name>-<ns>.<apps domain>` |
| `clusters` | the local cluster | Add entries to observe others |
| `trustedCA.*` | injected on | Corporate CAs for external clusters — see below |
| `persistence.enabled` | `true` | Leave on. The accumulated history cannot be re-fetched |
| `monitoring.serviceMonitor.enabled` | `false` | Needs the Prometheus Operator CRDs |
| `replicaCount` | `1` | Leave at 1. Above one, each pod keeps its own database and history diverges — see the chart README's Scaling section |
| `config.pollIntervalSeconds` | `60` | Poll cadence |
| `logLevel` | `INFO` | `DEBUG` adds per-poll timing and HTTP request lines |

## Authentication

`oauthProxy.enabled=true` puts cluster login in front of the dashboard, as a sidecar.

It is **authentication, not authorization**: anyone who can log into the cluster can view.
That is the OpenShift provider's documented default and it is deliberate here — the
dashboard shows nothing a user could not already read with `oc get groups`, so gating it
behind an access request adds friction without adding protection. Set `oauthProxy.sar` to a
SubjectAccessReview to restrict further.

Turning it on also switches the Ingress to `reencrypt`, binds the app to `127.0.0.1` so the
proxy cannot be bypassed from inside the cluster, and moves the probes behind
`skip-auth-regex` — all handled by the chart.

The proxy image defaults to the one that ships **with your cluster**, served from the
internal registry, so starting a pod needs no external registry and no pull secret. Confirm
the right image for any cluster with `oc adm release info --image-for=oauth-proxy`.

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

`/metrics` serves Prometheus exposition; the chart ships a ServiceMonitor and four alerting
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

The other two cover SQLite. `GroupSyncDashboardWalGrowing` catches a write-ahead log that is
not being checkpointed — checkpoints yield to open readers, so a steady read load can starve
them, and the WAL grows until the volume fills while the database file stays small.
`GroupSyncDashboardWalDisabled` catches WAL never having engaged: it is requested at startup
but a filesystem without working shared memory (NFS, EFS, SMB) refuses it silently, and reads
then block on every write. Both are failures where the pod stays Ready and nothing else looks
wrong.

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

## What it shows

**Overview** — per cluster: reachable, CR count, group count, empty and unattributed groups,
bindings needing review, oldest last sync.

**GroupSync detail** — schedule, LDAP filter, last sync, next expected (from a real cron
parser), the accumulated sync timeline, and the groups the CR owns.

**Groups** — every group, filterable to `empty` and `unattributed`. Drill in for members,
when each was first seen, the membership change log, and the access the group grants.

**Users** — the reverse lookup: every group a user belongs to and every binding that reaches
them, each row naming the group that confers it. The cluster can only answer this by scanning
every Group object by hand.

**Access granted** — every group-subject binding, classified `granted`, `dangling` (the group
was operator-managed and has disappeared), `unresolved` (names a group that has never
existed), or `built_in` (Kubernetes virtual groups, expected). Filterable, defaulting to what
needs review.

Direct bindings only. Role rules are never fetched or expanded, and the UI says so — an
incomplete effective-permission calculation could show access as absent when it is not, and a
false negative there gets an incident closed wrongly.

## Two things to know before reading a screen

**The API keeps no history.** A CR carries one timestamp and each Group carries one of its
own, so timelines and membership changes are *accumulated* by polling. An empty timeline
means this dashboard has not seen a sync yet — not that the operator never synced.

**`ReconcileError` is sticky.** The operator never clears it on a later success, so a healthy
CR carries both `ReconcileSuccess` and `ReconcileError` at `status: True` indefinitely. An
error counts as current only when its `lastTransitionTime` is newer than the success's;
reading the condition's status alone would paint a healthy CR permanently red.

## Not built yet

Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), retention on the accumulated history, and per-cluster
authorization for the multi-cluster case — OAuth authenticates against the hosting cluster
only, so one instance holding several clusters' data can show a user membership from a
cluster they have no rights on.
