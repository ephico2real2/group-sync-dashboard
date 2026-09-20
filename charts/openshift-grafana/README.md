# openshift-grafana

An **isolated Grafana instance in your own namespace**, wired to OpenShift's user-workload
monitoring through the Thanos querier, managed by grafana-operator v5. Nothing in it is specific to
any application: a team installs it, then attaches its own dashboards. Deploy it **before** a chart
that ships a `GrafanaDashboard` CR.

```sh
helm repo add group-sync-dashboard https://ephico2real2.github.io/group-sync-dashboard
helm install obs group-sync-dashboard/openshift-grafana -n my-team --create-namespace --timeout 15m
```

`--timeout 15m` because Helm waits for the post-install gate only up to its own timeout (5m by
default) while the gate counts `wait.waitSeconds` (600 s) plus the Job's own 120 s: on a cluster
that pulls the operator and Grafana images cold, the default would mark the release failed while
the gate was still counting (measured: a warm CRC install took 45 s; the gate's ceiling is 12 min).

One `helm install`, no operator pre-installed, returns a Grafana whose Thanos datasource reports
*"Successfully queried the Prometheus API"* (measured on CRC, OpenShift 4.22, grafana-operator
v5.24.0).

## The one cluster-admin prerequisite

User-workload monitoring must be on, once per cluster — without it Thanos serves no user metrics:

```sh
oc -n openshift-monitoring create configmap cluster-monitoring-config \
  --from-literal=config.yaml='enableUserWorkload: true'
```

(or add `enableUserWorkload: true` to the existing ConfigMap's `config.yaml`).

The other cluster-scoped step is the **first install on a cluster with no grafana-operator**: Helm
creates the four CRDs under `crds/` when they are absent, and a CustomResourceDefinition is
cluster-scoped — that needs the right to create CRDs, which a project Role does not carry. Once the
CRDs exist (this chart's first install, or any grafana-operator already on the cluster), everything
else lives in the namespace the chart installs into, and with the default `thanos.scope: namespace`
a team installs and upgrades it with ordinary project rights. The gate **verifies** the prerequisite
after every install with no grant at all — it resolves `prometheus-user-workload.openshift-user-workload-monitoring.svc`,
a Service the platform creates only when user-workload monitoring is on (measured on 4.22) — and
**reports** it in the Job's log with the command for the OpenShift engineers; it never fails the
install on it, and nothing needs re-installing once they run it.

## How the install order works

Helm resolves every kind in a release before it applies anything, so a `Grafana` CR in the manifest
would be refused while the operator's CRDs are absent. The chart ships copies of the four CRDs it
and its consumers use under `crds/` (`Grafana`, `GrafanaDatasource`, `GrafanaDashboard`,
`GrafanaFolder`, from grafana-operator v5.24.0): Helm installs them first, only when absent, and
never upgrades or deletes them; OLM then installs the operator and adopts the identical CRDs. On a
cluster where the operator already runs, the copies are skipped. Argo CD applies `crds/` like any
manifest; the `argocd.argoproj.io/sync-wave` annotations order the OperatorGroup (−2), the
Subscription (−1), the instance (1), the datasource (2) and the wait Job (3).

The post-install **wait Job** blocks `helm install` until the operator's CSV succeeds (when
installed here), the Grafana instance reports its reconcile complete with a ready replica, and the
datasource reports synchronised — so the command returns a working Grafana or a failure that names
what to inspect.

## Two install shapes

| | `operator.install: true` (default) | `operator.install: false` |
|---|---|---|
| What renders | OperatorGroup (own namespace), Subscription, the instance | the instance only |
| Who runs the operator | this namespace's own grafana-operator, serving this namespace | a platform team's AllNamespaces operator |
| Rights needed | create OperatorGroup and Subscription — not in the `admin` ClusterRole (measured: it holds no `create` on operatorgroups), so a cluster-admin or a Role that grants it; plus the CRDs on the very first install (above) | project rights only |

`operatorGroup.create: false` reuses an OperatorGroup the namespace already has (OLM allows one per
namespace) — make sure it targets this namespace. grafana-operator v5.24.0 supports OwnNamespace,
SingleNamespace, MultiNamespace and AllNamespaces (measured on its CSV), so both shapes are real.

## Thanos access — least privilege by default

| `thanos.scope` | Port | Sees | Authorised by | Objects outside the namespace |
|---|---|---|---|---|
| `namespace` (default) | 9092, the tenancy port | this namespace's metrics (`namespace=<release namespace>` on every query) | a `view` RoleBinding **in the release's namespace**, created by the chart | none |
| `cluster` | 9091 | every metric on the cluster | a RoleBinding to `cluster-monitoring-view` in `openshift-monitoring`, created by the chart | that RoleBinding — a privileged step, for a central observability Grafana |

Two details the reference architecture gets wrong and this chart gets right, both measured:

- **GET, not POST.** The tenancy port's kube-rbac-proxy authorises the HTTP method as the RBAC verb;
  Grafana's default POSTed query was refused as `create pods` (`403 Forbidden (verb=create,
  resource=pods)`). The datasource uses `httpMethod: GET`, which is `get pods`, which `view` grants.
- **The service CA, not `tlsSkipVerify`.** thanos-querier's certificate chains to OpenShift's service
  CA; the chart annotates a ConfigMap with `service.beta.openshift.io/inject-cabundle: "true"` and the
  datasource reads the bundle from it (`tlsAuthWithCACert`). The bearer token comes from the
  ServiceAccount's token Secret the same way — through `valuesFrom` — so the rendered manifest
  carries neither a token nor a certificate, and a rotation of either reaches Grafana with no render.

## After a restart

Grafana's database is an `emptyDir` unless `grafana.persistence.enabled` is on, so a pod restart (a
config change, a node drain) empties it: the datasource and every provisioned board are gone until
the operator's next resync re-applies them. Measured on CRC: ten minutes of "No data" at the
operator's default. The chart sets `thanos.datasource.resyncPeriod: 2m`; set the same
`spec.resyncPeriod` on your `GrafanaDashboard`, or turn persistence on where a StorageClass exists.

## Attaching your dashboard

The datasource's **name and uid are both fixed** (`thanos.datasource.name` — *OpenShift Thanos* —
and `.uid` — `openshift-thanos`). A dashboard that hard-codes a uid binds by uid. A dashboard exported
with an input (`${DS_PROMETHEUS}`) is bound through `GrafanaDashboard.spec.datasources[]`, whose
`datasourceName` the operator substitutes **verbatim** into the panels' `uid` fields — so give it the
**uid**: measured on CRC, the name rendered in the browser (a name fallback) while Grafana's query API
answered *Data source not found*.

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: my-board
spec:
  instanceSelector:
    matchLabels:
      app.kubernetes.io/instance: obs        # your release name
  datasources:
    - inputName: DS_PROMETHEUS
      datasourceName: openshift-thanos      # the uid, see above
  configMapRef:
    name: my-board
    key: my-board.json
```

`grafana.labels` adds labels to the instance for a selector of your own (the reference
architecture's `dashboards: grafana`).

## Values

| Key | Default | Meaning |
|---|---|---|
| `operator.install` | `true` | install grafana-operator here through OLM; `false` reuses a platform operator |
| `operator.channel` / `.source` / `.sourceNamespace` | `v5` / `community-operators` / `openshift-marketplace` | the catalog entry |
| `operator.installPlanApproval` | `Automatic` | `Manual` keeps upgrades for a human, but the first install then needs an approval this chart does not automate |
| `operator.startingCSV` | `""` | pin a CSV for change control |
| `operatorGroup.create` | `true` | `false` reuses the namespace's existing OperatorGroup |
| `grafana.labels` | `{}` | extra labels on the instance, for consumers' selectors |
| `grafana.admin.existingSecret` | `""` | your Secret with `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`; empty lets the operator generate `<name>-admin-credentials` |
| `grafana.config` | log/auth basics | Grafana's `config.ini`, as the operator's sections map |
| `grafana.persistence.enabled` / `.size` / `.storageClassName` | `false` / `2Gi` / `""` | persist Grafana's own database |
| `grafana.route.enabled` / `.host` | `true` / `""` | the Route (reencrypt to the proxy under the OpenShift login; edge to Grafana under `mode: grafana`), the router naming it when the host is empty; it carries the chart's labels in either mode, so an application in the namespace can discover Grafana's URL by `app.kubernetes.io/name=openshift-grafana` |
| `grafana.resources` | 100m / 256Mi, limit 512Mi | the container's resources |
| `thanos.scope` | `namespace` | `namespace` or `cluster`, above |
| `thanos.datasource.name` / `.uid` / `.isDefault` / `.timeInterval` | `OpenShift Thanos` / `openshift-thanos` / `true` / `30s` | the datasource as dashboards bind to it |
| `networkPolicy.enabled` / `.extraFrom` | `true` / `[]` | who may reach Grafana: the routers and this namespace, plus your peers |
| `wait.enabled` / `.waitSeconds` / `.intervalSeconds` | `true` / `600` / `10` | the post-install gate |
| `wait.image.repository` / `.tag` | `registry.redhat.io/openshift4/ose-cli` / `latest` | the `oc` image both hook Jobs run (the gate and the secrets mint) |
| `wait.resources` | `50m` / `64Mi` requests, `256Mi` limit | for both hook Jobs — a namespace whose ResourceQuota requires requests refuses a pod without them and the install fails at the hook |

## Argo CD, Flux, Kustomize — what each renderer does with this chart

Three things in this chart depend on *how* it is rendered, and each of the three tools renders
differently (read from their sources on 2026-09-19: argo-cd `util/helm/cmd.go`, `controller/state.go`,
`reposerver/cache/cache.go`; helm-controller `internal/action/install.go`).

| | Helm / **Flux** (a real install through the Helm SDK) | **Argo CD** (`helm template --api-versions <live list> --include-crds`, no cluster) | **Kustomize `helmCharts`** (bare `helm template`) |
|---|---|---|---|
| `crds/` | installed first | rendered (`--include-crds`), applied with the rest | rendered only with `includeCRDs: true` |
| the wait gate (`helm.sh/hook` + `argocd.argoproj.io/hook: Sync`) | a Helm hook | an Argo Sync hook, in the Subscription's wave | a plain Job, applied once |
| the generated Secrets (`<name>-admin`, `<name>-oauth-cookie`) — **minted on the cluster by a hook Job, only if absent; never in the manifest** | a pre-install/pre-upgrade hook | a PreSync hook | a plain Job, applied once (delete it before re-applying a changed chart: a Job's template is immutable) |

The Secrets used to be the trap. The first draft rendered them with Helm's `lookup` reusing what
existed; `lookup` is always empty under `helm template` — what Argo CD and Kustomize run — so every
render minted new values, the Application drifted permanently, and every sync rotated Grafana's admin
password and signed every session out. Now a hook Job (`<name>-secrets`: pre-install/pre-upgrade,
PreSync under Argo) creates each Secret on the cluster **only if it does not exist**, and the manifest
never carries a value: nothing to diff, nothing to rotate, nothing to `ignoreDifferences`. Its Role
holds `get` on the two names and `create` on secrets in the namespace (`create` cannot be
name-scoped); nothing else runs as that identity. Bringing your own works the same in every tool:
`grafana.admin.existingSecret` (keys `GF_SECURITY_ADMIN_USER` / `GF_SECURITY_ADMIN_PASSWORD`) and
`grafana.auth.oauthProxy.cookieSecret` switch the corresponding mint off.

The one Application entry the chart still needs is the Route's router-written status:

```yaml
spec:
  ignoreDifferences:
    - group: route.openshift.io
      kind: Route
      name: obs-openshift-grafana
      jsonPointers: ["/status"]                  # the router writes status; argo-cd#2370
```

Nothing in the chart reads the cluster at render time: the OAuth redirect is a *reference* to the
Route (`serviceaccounts.openshift.io/oauth-redirectreference.primary`), resolved by the OAuth server,
not a host the render must know — the failure mode a `lookup` of the apps domain had under Argo on
2026-09-03 (the application chart's README, "Deploying with ArgoCD").

## Reading the result

```sh
oc get grafana,grafanadatasource -n my-team
oc extract secret/obs-openshift-grafana-admin -n my-team --to=-      # minted on the cluster by the secrets hook
oc get route -n my-team -l app.kubernetes.io/instance=obs
```

The datasource's health, through Grafana's API: `GET /api/datasources/uid/openshift-thanos/health`
answers `{"status":"OK"}` when Thanos accepts the token and the CA.
