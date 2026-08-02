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
| `replicaCount` | `1` | **keep at 1.** The poller owns a SQLite file with no leader election, so extra replicas are concurrent writers on one database |
| `strategy` | `Recreate` | same reason |
| `persistence.enabled` | `true` | **keep on.** The accumulated history cannot be re-fetched from the API |
| `persistence.size` / `.storageClass` / `.accessMode` / `.existingClaim` | `1Gi` / cluster default / `ReadWriteOnce` / `""` | |
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
| `IgnoreExtraneous` (`argocd.ignoreExtraneousPVC`) | permanent OutOfSync — a bound PVC is mutated by the storage class, so it drifts from the manifest forever and invites someone to "fix" it with a sync |

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
    - group: ""
      kind: ConfigMap
      name: group-sync-dashboard-trusted-ca
      jsonPointers:
        - /data
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
