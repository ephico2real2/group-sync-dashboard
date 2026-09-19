# openshift-grafana

An **isolated Grafana instance in your own namespace**, wired to OpenShift's user-workload
monitoring through the Thanos querier, managed by grafana-operator v5. Nothing in it is specific to
any application: a team installs it, then attaches its own dashboards. Deploy it **before** a chart
that ships a `GrafanaDashboard` CR.

```sh
helm repo add group-sync-dashboard https://ephico2real2.github.io/group-sync-dashboard
helm install obs group-sync-dashboard/openshift-grafana -n my-team --create-namespace \
  --set grafana.route.enabled=true
```

One `helm install`, no operator pre-installed, returns a Grafana whose Thanos datasource reports
*"Successfully queried the Prometheus API"* (measured on CRC, OpenShift 4.22, grafana-operator
v5.24.0).

## The one cluster-admin prerequisite

User-workload monitoring must be on, once per cluster — without it Thanos serves no user metrics:

```sh
oc -n openshift-monitoring create configmap cluster-monitoring-config \
  --from-literal=config.yaml='enableUserWorkload: true'
```

(or add `enableUserWorkload: true` to the existing ConfigMap's `config.yaml`). Everything else the
chart needs is in the namespace it installs into — with the default `thanos.scope: namespace` a team
installs it with ordinary project rights.

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
| Rights needed | OLM in this namespace | project rights only |

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

## Attaching your dashboard

The datasource's **name and uid are both fixed** (`thanos.datasource.name` — *OpenShift Thanos* —
and `.uid` — `openshift-thanos`). A dashboard exported with an input (`${DS_PROMETHEUS}`) binds by
name; one that hard-codes a uid binds by uid. Pin only one and every exported community dashboard of
the other kind silently mis-binds.

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
      datasourceName: OpenShift Thanos
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
| `grafana.route.enabled` / `.host` | `false` / `""` | an edge-terminated Route (the router names it when the host is empty) |
| `grafana.resources` | 100m / 256Mi, limit 512Mi | the container's resources |
| `thanos.scope` | `namespace` | `namespace` or `cluster`, above |
| `thanos.datasource.name` / `.uid` / `.isDefault` / `.timeInterval` | `OpenShift Thanos` / `openshift-thanos` / `true` / `30s` | the datasource as dashboards bind to it |
| `networkPolicy.enabled` / `.extraFrom` | `true` / `[]` | who may reach Grafana: the routers and this namespace, plus your peers |
| `wait.enabled` / `.waitSeconds` / `.intervalSeconds` | `true` / `600` / `10` | the post-install gate |
| `wait.image.repository` / `.tag` | `registry.redhat.io/openshift4/ose-cli` / `latest` | the gate's `oc` image |

## Reading the result

```sh
oc get grafana,grafanadatasource -n my-team
oc extract secret/obs-openshift-grafana-admin-credentials -n my-team --to=-
oc get route -n my-team -l app.kubernetes.io/instance=obs
```

The datasource's health, through Grafana's API: `GET /api/datasources/uid/openshift-thanos/health`
answers `{"status":"OK"}` when Thanos accepts the token and the CA.
