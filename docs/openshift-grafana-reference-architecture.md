# OpenShift 4.20 Grafana Operator Reference Architecture

## Native Grafana Dashboards with OpenShift User Workload Monitoring

This document defines a GitOps-friendly architecture for deploying Grafana on OpenShift Container Platform 4.20 using:

- OpenShift User Workload Monitoring
- OpenShift Thanos Querier
- Grafana Operator v5
- Native `GrafanaDashboard` JSON
- ServiceAccount-based authentication to Thanos
- Declarative Kubernetes and OpenShift resources
- Optional namespace-scoped or cluster-wide metric access

The goal is to preserve full Grafana dashboard functionality without converting modern Grafana JSON into the OpenShift Console dashboard model.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Key Design Decisions](#2-key-design-decisions)
3. [Deployment Order](#3-deployment-order)
4. [Install the Grafana Operator](#4-install-the-grafana-operator)
5. [Enable User Workload Monitoring](#5-enable-user-workload-monitoring)
6. [Create the Grafana Thanos ServiceAccount](#6-create-the-grafana-thanos-serviceaccount)
7. [Grant Grafana Access to Thanos](#7-grant-grafana-access-to-thanos)
8. [Create Grafana Admin Credentials](#8-create-grafana-admin-credentials)
9. [Deploy the Grafana Instance](#9-deploy-the-grafana-instance)
10. [Configure the OpenShift Thanos Datasource](#10-configure-the-openshift-thanos-datasource)
11. [Deploy Native Grafana Dashboards](#11-deploy-native-grafana-dashboards)
12. [Namespace-Restricted Alternative](#12-namespace-restricted-alternative)
13. [Verification](#13-verification)
14. [Recommended Git Repository Layout](#14-recommended-git-repository-layout)
15. [Production Hardening](#15-production-hardening)
16. [Reference Architecture Summary](#16-reference-architecture-summary)
17. [References](#17-references)

---

# 1. Architecture Overview

```text
                        OpenShift 4.20
                              │
              ┌───────────────┴────────────────┐
              │                                │
     OpenShift Monitoring             User Workload Monitoring
              │                                │
              └───────────────┬────────────────┘
                              │
                       Thanos Querier
                  openshift-monitoring
                              │
                         HTTPS :9091
                              │
                       Bearer SA Token
                              │
                              ▼
                    Grafana Datasource
                              │
                              ▼
                   Grafana Operator v5
                              │
             ┌────────────────┴────────────────┐
             │                                 │
      Grafana Instance                GrafanaDashboard CRs
             │                                 │
             └────────────────┬────────────────┘
                              │
                       OpenShift Route
```

OpenShift User Workload Monitoring collects application metrics, while Thanos Querier provides a Prometheus-compatible query endpoint that Grafana can use as its datasource.

For cluster-wide queries, this design uses:

```text
https://thanos-querier.openshift-monitoring.svc.cluster.local:9091
```

---

# 2. Key Design Decisions

## 2.1 Separate metrics collection from visualization

OpenShift remains responsible for collecting and storing metrics.

Grafana is deployed only as the visualization layer.

```text
OpenShift Monitoring / UWM
          │
          ▼
      Thanos Querier
          │
          ▼
        Grafana
```

This avoids duplicating the monitoring stack.

---

## 2.2 Use native Grafana JSON

Dashboards are deployed with:

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
```

The dashboard JSON is stored directly under:

```yaml
spec:
  json: |
```

This allows existing Grafana dashboard JSON to be used without translating the layout into OpenShift Console dashboard structures.

---

## 2.3 Use Grafana Operator v5 APIs

Use the current v5 resource names and API group:

```yaml
apiVersion: grafana.integreatly.org/v1beta1
```

Primary resources:

```text
Grafana
GrafanaDatasource
GrafanaDashboard
```

The datasource kind is:

```yaml
kind: GrafanaDatasource
```

not:

```yaml
kind: GrafanaDataSource
```

---

## 2.4 Use deterministic datasource UIDs

Dashboards should reference a known datasource UID.

Example:

```yaml
spec:
  uid: openshift-thanos
```

Dashboard JSON can then reliably reference:

```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "openshift-thanos"
  }
}
```

This prevents dashboards from depending on dynamically generated Grafana datasource UIDs.

---

## 2.5 Keep Grafana in a dedicated namespace

Recommended namespace:

```text
my-grafana
```

Do not deploy the Grafana application directly into:

```text
openshift-monitoring
```

or:

```text
openshift-user-workload-monitoring
```

Those namespaces should remain dedicated to the OpenShift monitoring stack.

---

# 3. Deployment Order

Apply the resources in the following order:

```text
1. Namespace
2. OperatorGroup
3. Subscription
4. User Workload Monitoring configuration
5. Grafana ServiceAccount
6. ServiceAccount token Secret
7. Thanos RBAC
8. Grafana admin credentials
9. Grafana instance
10. GrafanaDatasource
11. GrafanaDashboard resources
```

Recommended filenames:

```text
00-namespace.yaml
01-operatorgroup.yaml
02-subscription.yaml
03-enable-user-workload-monitoring.yaml
04-grafana-thanos-serviceaccount.yaml
05-grafana-thanos-rbac.yaml
06-grafana-admin-secret.yaml
07-grafana.yaml
08-grafana-datasource.yaml
09-dashboard.yaml
```

---

# 4. Install the Grafana Operator

The Grafana Operator is installed from the OpenShift Operator catalog through OLM.

## 4.1 Namespace

### `00-namespace.yaml`

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: my-grafana
```

Apply:

```bash
oc apply -f 00-namespace.yaml
```

---

## 4.2 OperatorGroup

### `01-operatorgroup.yaml`

```yaml
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: grafana-operator-group
  namespace: my-grafana
spec:
  targetNamespaces:
    - my-grafana
```

Apply:

```bash
oc apply -f 01-operatorgroup.yaml
```

> **Important**
>
> A namespace should not contain multiple conflicting `OperatorGroup` resources.
> If the target namespace already contains an OperatorGroup, review and reuse it where appropriate.

---

## 4.3 Subscription

### `02-subscription.yaml`

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: grafana-operator
  namespace: my-grafana
spec:
  channel: v5
  installPlanApproval: Automatic
  name: grafana-operator
  source: community-operators
  sourceNamespace: openshift-marketplace
```

Apply:

```bash
oc apply -f 02-subscription.yaml
```

Do not define `startingCSV` unless the environment requires explicit CSV pinning for change-control purposes.

Allow OLM to resolve the version from the `v5` channel.

---

## 4.4 Verify the Operator installation

```bash
oc get subscription -n my-grafana
```

```bash
oc get csv -n my-grafana
```

```bash
oc get pods -n my-grafana
```

Verify the Grafana CRDs:

```bash
oc get crd | grep grafana.integreatly.org
```

Expected resources include:

```text
grafanas.grafana.integreatly.org
grafanadashboards.grafana.integreatly.org
grafanadatasources.grafana.integreatly.org
```

---

# 5. Enable User Workload Monitoring

OpenShift User Workload Monitoring is enabled through the `cluster-monitoring-config` ConfigMap in the `openshift-monitoring` namespace.

### `03-enable-user-workload-monitoring.yaml`

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-monitoring-config
  namespace: openshift-monitoring
data:
  config.yaml: |
    enableUserWorkload: true
```

Apply:

```bash
oc apply -f 03-enable-user-workload-monitoring.yaml
```

## Important GitOps warning

If `cluster-monitoring-config` already exists and contains additional monitoring configuration, do **not** blindly replace the entire ConfigMap.

Merge:

```yaml
enableUserWorkload: true
```

into the existing:

```yaml
data:
  config.yaml: |
```

configuration.

---

## 5.1 Verify User Workload Monitoring

```bash
oc get pods -n openshift-user-workload-monitoring
```

Typical components include:

```text
prometheus-operator-...
prometheus-user-workload-0
prometheus-user-workload-1
thanos-ruler-user-workload-0
thanos-ruler-user-workload-1
```

---

# 6. Create the Grafana Thanos ServiceAccount

Use a dedicated ServiceAccount for Grafana-to-Thanos authentication.

### `04-grafana-thanos-serviceaccount.yaml`

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: grafana-thanos
  namespace: my-grafana
automountServiceAccountToken: false
---
apiVersion: v1
kind: Secret
metadata:
  name: grafana-thanos-token
  namespace: my-grafana
  annotations:
    kubernetes.io/service-account.name: grafana-thanos
type: kubernetes.io/service-account-token
```

Apply:

```bash
oc apply -f 04-grafana-thanos-serviceaccount.yaml
```

Kubernetes populates the token Secret with data such as:

```text
ca.crt
namespace
token
```

Verify:

```bash
oc get secret grafana-thanos-token -n my-grafana
```

```bash
oc describe secret grafana-thanos-token -n my-grafana
```

Expected output includes:

```text
Data
====
ca.crt:
namespace:
token:
```

> **Security**
>
> Do not extract the token and commit it into Git.

---

# 7. Grant Grafana Access to Thanos

There are two supported design patterns:

```text
Cluster-wide Grafana
    Thanos :9091
    cluster-monitoring-view

Namespace-restricted Grafana
    Thanos :9092
    view RoleBinding in each permitted namespace
```

This section implements the cluster-wide pattern.

---

## 7.1 Cluster-wide Thanos access

For cluster-wide Grafana queries, bind the ServiceAccount to `cluster-monitoring-view` in the `openshift-monitoring` namespace.

### `05-grafana-thanos-rbac.yaml`

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: grafana-thanos-cluster-monitoring-view
  namespace: openshift-monitoring
subjects:
  - kind: ServiceAccount
    name: grafana-thanos
    namespace: my-grafana
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cluster-monitoring-view
```

Apply:

```bash
oc apply -f 05-grafana-thanos-rbac.yaml
```

The datasource will query:

```text
https://thanos-querier.openshift-monitoring.svc.cluster.local:9091
```

---

# 8. Create Grafana Admin Credentials

Do not store Grafana administrator credentials directly in the `Grafana` CR.

### `06-grafana-admin-secret.yaml`

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: grafana-admin-credentials
  namespace: my-grafana
type: Opaque
stringData:
  GF_SECURITY_ADMIN_USER: admin
  GF_SECURITY_ADMIN_PASSWORD: REPLACE_WITH_SECURE_PASSWORD
```

Apply:

```bash
oc apply -f 06-grafana-admin-secret.yaml
```

For production GitOps environments, replace the plaintext Secret workflow with the organization's approved secret-management platform.

Examples include:

```text
External Secrets Operator
HashiCorp Vault
SOPS
Sealed Secrets
```

---

# 9. Deploy the Grafana Instance

The Grafana instance must contain a label that `GrafanaDatasource` and `GrafanaDashboard` resources can select.

This guide uses:

```yaml
dashboards: "grafana"
```

### `07-grafana.yaml`

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: Grafana
metadata:
  name: grafana
  namespace: my-grafana
  labels:
    dashboards: "grafana"
spec:
  disableDefaultAdminSecret: true

  config:
    log:
      mode: "console"
      level: "info"

    auth:
      disable_login_form: "false"

    auth.anonymous:
      enabled: "false"

  deployment:
    spec:
      template:
        spec:
          containers:
            - name: grafana
              env:
                - name: GF_SECURITY_ADMIN_USER
                  valueFrom:
                    secretKeyRef:
                      name: grafana-admin-credentials
                      key: GF_SECURITY_ADMIN_USER

                - name: GF_SECURITY_ADMIN_PASSWORD
                  valueFrom:
                    secretKeyRef:
                      name: grafana-admin-credentials
                      key: GF_SECURITY_ADMIN_PASSWORD

  route:
    spec:
      tls:
        termination: edge
        insecureEdgeTerminationPolicy: Redirect
```

Apply:

```bash
oc apply -f 07-grafana.yaml
```

---

## 9.1 Verify the Grafana instance

```bash
oc get grafana -n my-grafana
```

```bash
oc get pods -n my-grafana
```

```bash
oc get svc -n my-grafana
```

```bash
oc get route -n my-grafana
```

Display the generated route:

```bash
oc get route -n my-grafana -o wide
```

---

# 10. Configure the OpenShift Thanos Datasource

Grafana Operator v5 uses:

```yaml
kind: GrafanaDatasource
```

The ServiceAccount token is injected into `secureJsonData` through:

```yaml
spec:
  valuesFrom:
```

This avoids manually copying tokens into the datasource resource.

### `08-grafana-datasource.yaml`

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDatasource
metadata:
  name: openshift-thanos
  namespace: my-grafana
spec:
  uid: openshift-thanos

  instanceSelector:
    matchLabels:
      dashboards: "grafana"

  valuesFrom:
    - targetPath: "secureJsonData.httpHeaderValue1"
      valueFrom:
        secretKeyRef:
          name: grafana-thanos-token
          key: token

  datasource:
    name: OpenShift Thanos
    type: prometheus
    access: proxy

    url: https://thanos-querier.openshift-monitoring.svc.cluster.local:9091

    isDefault: true
    editable: false

    jsonData:
      timeInterval: "5s"
      tlsSkipVerify: true
      httpHeaderName1: Authorization

    secureJsonData:
      httpHeaderValue1: "Bearer ${token}"
```

Apply:

```bash
oc apply -f 08-grafana-datasource.yaml
```

---

## 10.1 Datasource token flow

```text
grafana-thanos ServiceAccount
           │
           ▼
grafana-thanos-token Secret
           │
           ▼
GrafanaDatasource.spec.valuesFrom
           │
           ▼
secureJsonData.httpHeaderValue1
           │
           ▼
Authorization: Bearer <token>
           │
           ▼
OpenShift Thanos Querier
```

---

## 10.2 Why the datasource UID matters

The datasource CR explicitly defines:

```yaml
spec:
  uid: openshift-thanos
```

Dashboard JSON should reference the same UID:

```json
{
  "datasource": {
    "type": "prometheus",
    "uid": "openshift-thanos"
  }
}
```

This avoids relying on a Grafana-generated UID.

---

# 11. Deploy Native Grafana Dashboards

A dashboard can now be stored in Git as native Grafana JSON.

### `09-dashboard.yaml`

```yaml
apiVersion: grafana.integreatly.org/v1beta1
kind: GrafanaDashboard
metadata:
  name: sample-dashboard
  namespace: my-grafana
spec:
  instanceSelector:
    matchLabels:
      dashboards: "grafana"

  folder: Applications

  json: |
    {
      "id": null,
      "uid": "sample-application-dashboard",
      "title": "Sample Application Dashboard",
      "tags": [
        "openshift",
        "application"
      ],
      "timezone": "browser",
      "editable": true,
      "graphTooltip": 1,

      "panels": [
        {
          "type": "timeseries",
          "title": "HTTP Requests / Second",

          "gridPos": {
            "h": 8,
            "w": 12,
            "x": 0,
            "y": 0
          },

          "datasource": {
            "type": "prometheus",
            "uid": "openshift-thanos"
          },

          "targets": [
            {
              "refId": "A",
              "expr": "sum(rate(http_requests_total[5m]))",

              "datasource": {
                "type": "prometheus",
                "uid": "openshift-thanos"
              }
            }
          ]
        }
      ],

      "schemaVersion": 38,
      "version": 1
    }
```

Apply:

```bash
oc apply -f 09-dashboard.yaml
```

This is the core benefit of the architecture:

> Native Grafana JSON can be stored directly in Git and reconciled by the Grafana Operator without translating the dashboard into the OpenShift Console dashboard model.

---

# 12. Namespace-Restricted Alternative

Some environments should not expose cluster-wide metrics to Grafana.

In that case, use the tenant-aware Thanos endpoint:

```text
:9092
```

and grant the Grafana ServiceAccount `view` access only in approved application namespaces.

---

## 12.1 Namespace RBAC

Example target application namespace:

```text
my-application
```

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: grafana-metrics-view
  namespace: my-application
subjects:
  - kind: ServiceAccount
    name: grafana-thanos
    namespace: my-grafana
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: view
```

---

## 12.2 Namespace-scoped datasource configuration

```yaml
datasource:
  name: My Application Metrics
  type: prometheus
  access: proxy

  url: https://thanos-querier.openshift-monitoring.svc.cluster.local:9092

  jsonData:
    timeInterval: "5s"
    tlsSkipVerify: true
    httpHeaderName1: Authorization
    customQueryParameters: "namespace=my-application"
```

The resulting model is:

```text
CENTRAL OBSERVABILITY GRAFANA
─────────────────────────────
Thanos :9091
      │
cluster-monitoring-view
      │
      ▼
Cluster/User workload metrics


APPLICATION / TEAM GRAFANA
──────────────────────────
Thanos :9092
      │
view RoleBinding
      │
namespace=team-a
      │
      ▼
Team A metrics only
```

---

# 13. Verification

## 13.1 Verify Operator resources

```bash
oc get subscription,csv -n my-grafana
```

---

## 13.2 Verify Grafana custom resources

```bash
oc get grafana \
       grafanadatasource \
       grafanadashboard \
       -n my-grafana
```

---

## 13.3 Inspect datasource status

```bash
oc describe grafanadatasource openshift-thanos \
  -n my-grafana
```

---

## 13.4 Inspect dashboard status

```bash
oc describe grafanadashboard sample-dashboard \
  -n my-grafana
```

---

## 13.5 Check Grafana logs

First identify the Grafana deployment:

```bash
oc get deployment -n my-grafana
```

Then inspect the Grafana container logs:

```bash
oc logs \
  -n my-grafana \
  deployment/grafana-deployment \
  -c grafana
```

Adjust the deployment name if the Operator generates a different name.

---

## 13.6 Test Thanos authentication independently

Extract the ServiceAccount token locally:

```bash
TOKEN=$(oc get secret grafana-thanos-token \
  -n my-grafana \
  -o jsonpath='{.data.token}' | base64 -d)
```

From a pod or environment with network access to the OpenShift service:

```bash
curl -k \
  -H "Authorization: Bearer ${TOKEN}" \
  'https://thanos-querier.openshift-monitoring.svc.cluster.local:9091/api/v1/query?query=up'
```

If this succeeds but Grafana cannot query the datasource, focus troubleshooting on Grafana datasource provisioning rather than Thanos RBAC.

---

# 14. Recommended Git Repository Layout

```text
openshift-grafana/
├── README.md
│
├── base/
│   ├── 00-namespace.yaml
│   ├── 01-operatorgroup.yaml
│   ├── 02-subscription.yaml
│   │
│   ├── monitoring/
│   │   └── user-workload-monitoring.yaml
│   │
│   ├── grafana/
│   │   ├── admin-secret.yaml
│   │   ├── grafana.yaml
│   │   └── kustomization.yaml
│   │
│   ├── thanos/
│   │   ├── serviceaccount.yaml
│   │   ├── token-secret.yaml
│   │   ├── rolebinding.yaml
│   │   ├── datasource.yaml
│   │   └── kustomization.yaml
│   │
│   └── dashboards/
│       ├── application-dashboard.yaml
│       ├── platform-dashboard.yaml
│       └── kustomization.yaml
│
└── overlays/
    ├── dev/
    │   └── kustomization.yaml
    ├── stage/
    │   └── kustomization.yaml
    └── prod/
        └── kustomization.yaml
```

---

## 14.1 Example base `kustomization.yaml`

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

resources:
  - 00-namespace.yaml
  - 01-operatorgroup.yaml
  - 02-subscription.yaml
  - monitoring/user-workload-monitoring.yaml
  - grafana/
  - thanos/
  - dashboards/
```

---

# 15. Production Hardening

The base configuration is functional, but the following improvements are recommended for enterprise deployments.

---

## 15.1 Replace `tlsSkipVerify: true`

The example datasource uses:

```yaml
tlsSkipVerify: true
```

for simplicity.

For production environments, configure Grafana to trust the OpenShift service CA and validate the Thanos certificate.

Preferred end state:

```yaml
tlsSkipVerify: false
```

with the appropriate CA configured.

---

## 15.2 Add OpenShift OAuth / SSO

Local Grafana administrator authentication is useful for bootstrap and recovery but should not normally be the primary user authentication model.

A stronger enterprise design is:

```text
User
  │
  ▼
OpenShift OAuth
  │
  ▼
OAuth Proxy
  │
  ▼
Grafana
```

This allows Grafana access to use the cluster's existing identity provider.

---

## 15.3 Use enterprise secret management

Avoid storing production passwords or credentials directly in Git.

Integrate with the organization's secret-management solution.

---

## 15.4 Consider namespace-restricted Grafana instances

For teams that should only see their own metrics:

```text
Thanos :9092
+
namespace RoleBinding
+
namespace query parameter
```

is preferable to granting every Grafana instance `cluster-monitoring-view`.

---

## 15.5 Manage dashboards entirely through GitOps

Treat the Grafana UI as a visualization surface rather than the source of truth.

Recommended workflow:

```text
Grafana Dashboard JSON
        │
        ▼
Git Repository
        │
        ▼
OpenShift GitOps / Argo CD
        │
        ▼
GrafanaDashboard CR
        │
        ▼
Grafana Operator
        │
        ▼
Grafana
```

Changes should be committed through Git and reconciled into the cluster.

---

# 16. Reference Architecture Summary

The intended architecture can be summarized as follows:

> **OpenShift User Workload Monitoring remains the metrics collection and storage platform. Grafana is deployed as a separate visualization tier using Grafana Operator v5. Grafana queries OpenShift's Thanos Querier through an explicitly authorized ServiceAccount, while Grafana instances, datasources, and dashboards are managed declaratively through `Grafana`, `GrafanaDatasource`, and `GrafanaDashboard` custom resources.**

> **This separates collection from visualization, preserves the OpenShift monitoring architecture, and allows teams to use native Grafana dashboard JSON without translating dashboard layouts into OpenShift Console dashboard structures. The complete visualization layer can therefore be managed through GitOps.**

The resulting flow is:

```text
Application
    │
    ▼
ServiceMonitor / PodMonitor
    │
    ▼
OpenShift User Workload Monitoring
    │
    ▼
Prometheus User Workload
    │
    ▼
Thanos Querier
    │
    ▼
GrafanaDatasource
    │
    ▼
Grafana
    │
    ▼
GrafanaDashboard
```

---

# 17. References

1. Grafana Operator API Reference  
   https://grafana.github.io/grafana-operator/docs/api/

2. Grafana Operator Datasource Variables  
   https://grafana.github.io/grafana-operator/docs/examples/datasource/datasource_variables/readme/

3. Grafana Operator Admin Credentials Secret  
   https://grafana.github.io/grafana-operator/docs/examples/grafana/credential_secret/readme/

4. Grafana Operator Quick Start  
   https://grafana.github.io/grafana-operator/docs/quick-start/

5. Grafana Operator OpenShift OAuth Proxy Example  
   https://grafana.github.io/grafana-operator/docs/examples/grafana/openshift_oauth_proxy/readme/

6. Grafana Operator on OperatorHub  
   https://operatorhub.io/operator/grafana-operator

7. Red Hat OpenShift 4.20 User Workload Monitoring  
   https://docs.redhat.com/en/documentation/monitoring_stack_for_red_hat_openshift/4.20/html/configuring_user_workload_monitoring/preparing-to-configure-the-monitoring-stack-uwm

8. Red Hat OpenShift 4.20 Monitoring Documentation  
   https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/monitoring/

9. Red Hat Developer — Grafana with OpenShift Monitoring  
   https://developers.redhat.com/articles/2024/08/19/monitor-openshift-virtualization-using-user-defined-projects-and-grafana

10. Kubernetes ServiceAccount Administration  
    https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/

---

## Final Recommended Pattern

For a centralized observability Grafana deployment:

```text
Grafana Operator v5
        │
        ├── Grafana
        ├── GrafanaDatasource
        └── GrafanaDashboard
                 │
                 ▼
        OpenShift Thanos :9091
                 │
                 ▼
        cluster-monitoring-view
```

For application- or team-specific deployments:

```text
Grafana Operator v5
        │
        ├── Grafana
        ├── GrafanaDatasource
        └── GrafanaDashboard
                 │
                 ▼
        OpenShift Thanos :9092
                 │
                 ▼
          namespace `view`
```

This provides a clean separation between OpenShift metrics collection and Grafana visualization while preserving native Grafana dashboard capabilities and a GitOps-first operating model.
