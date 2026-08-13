# Download the chart, then install from the copy on disk

Every command here was run against the published repository and a live cluster on 2026-08-12 with
`helm v3.14.0`, `oc 4.13.6` and `skopeo 1.20.0`. Where a command fails, the failure is shown rather
than described — one of them fails on purpose, and knowing which saves an afternoon.

Two exceptions, stated so the rest can be trusted: the `skopeo copy` in §6 was verified only on its
source side (`skopeo inspect` on the published image returns digest
`sha256:2afeae723caa3a2ff709272f41e6366398d2845b4d736a679657768b1cbd5541`), because there is no
internal registry here to copy into; and `--create-namespace` was not exercised, since the namespace
already existed.

**Why download first rather than `helm install` straight from the repo?** Three real reasons: you
want to read the templates before they touch a cluster; the cluster has no route to
github.io and the chart must travel on a laptop or a USB stick; or you need the exact bytes of one
version pinned in your own artefact store. If none of those apply, install from the repo directly —
`docs/reference-architecture.md` covers that path.

---

## 1. Add the repository and see what it offers

```sh
helm repo add group-sync-dashboard https://ephico2real2.github.io/group-sync-dashboard
helm repo update
helm search repo group-sync-dashboard --versions
```

```
NAME                                       CHART VERSION  APP VERSION  DESCRIPTION
group-sync-dashboard/group-sync-dashboard  0.4.4          0.7.0        Read-only observability ...
group-sync-dashboard/group-sync-dashboard  0.4.3          0.7.0        Read-only observability ...
group-sync-dashboard/group-sync-dashboard  0.4.2          0.7.0        Read-only observability ...
```

**Two version numbers, and they mean different things.** `CHART VERSION` tracks the templates and
their defaults; `APP VERSION` is the dashboard release the chart deploys. `--versions` matters
because without it `helm search` shows only the newest, and the chart version moves on every image
build — see `charts/group-sync-dashboard/Chart.yaml`, which explains why the patch component is
automated.

`helm repo update` is not optional. The local cache is a snapshot; skip the update and `helm pull`
will happily fetch a version that was current last week.

---

## 2. Download it

```sh
# The packaged chart, as published
helm pull group-sync-dashboard/group-sync-dashboard

# → group-sync-dashboard-0.4.4.tgz
```

```sh
# Into a directory you choose, rather than the working directory
helm pull group-sync-dashboard/group-sync-dashboard -d ./downloads

# A specific version, not merely the newest
helm pull group-sync-dashboard/group-sync-dashboard --version 0.4.3

# Download AND unpack in one step — this is the one you usually want
helm pull group-sync-dashboard/group-sync-dashboard --untar --untardir ./charts
```

`--untar` leaves you a plain directory:

```
charts/group-sync-dashboard/
├── Chart.yaml
├── README.md                     # the values reference, shipped inside the chart
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── ingress.yaml
    ├── oauth-secret.yaml
    ├── pdb.yaml
    ├── pvc.yaml
    ├── rbac.yaml
    ├── serviceaccount.yaml
    ├── trusted-ca.yaml
    └── ...                       # 19 files in total at 0.4.4
```

**The `.tgz` and the unpacked directory are interchangeable as a chart reference.** Anywhere below
that names `./charts/group-sync-dashboard`, `./group-sync-dashboard-0.4.4.tgz` works identically.
Unpack when you want to read or diff the templates; keep the tarball when you want the exact
published bytes.

---

## 3. Read it before you run it

All of these work on the local copy with no cluster involved:

```sh
helm show chart   ./charts/group-sync-dashboard   # name, version, appVersion, description
helm show values  ./charts/group-sync-dashboard   # every default, with the comments intact
helm show readme  ./charts/group-sync-dashboard   # the values reference
```

`helm show values` is worth the minute. This chart's `values.yaml` carries the *reasoning* for its
defaults — which SubjectAccessReview decides the wide tier, why `/metrics` is exempt from
authentication, what the unmanaged-audit modes do — and that reasoning is not repeated anywhere a
consumer can see it.

Note what version you actually downloaded, because it is the answer to "what will this install?":

```sh
grep -E '^version:|^appVersion:' ./charts/group-sync-dashboard/Chart.yaml
grep -E '^  tag:'                ./charts/group-sync-dashboard/values.yaml
```

```
version: 0.5.0
appVersion: 0.7.0
  tag: ""
```

**An empty tag is the normal case, and it means `appVersion`.** The chart resolves
`default .Chart.AppVersion .Values.image.tag`, so this chart deploys
`quay.io/ephico2real/group-sync-dashboard:0.7.0`. Confirm it rather than infer it:

```sh
helm template gsd ./charts/group-sync-dashboard --set ingress.host=x.example.com \
  | grep -m1 'image: quay'
#             image: quay.io/ephico2real/group-sync-dashboard:0.7.0
```

That `:0.7.0` alias is republished when the application version changes, and
`imagePullPolicy: Always` means every container creation re-resolves it — so it is stable for the
life of an appVersion, but it is not a byte-pin. **Pin the sha form if you need byte-identical
rollbacks:** `--set image.tag=0.7.0-<git-sha>`, which always means the same source. Either way a
running pod reports its own commit at `/api/version` and on the `gsd_build_info` metric, which is how
you confirm what the cluster is actually running.

Charts at **0.4.4 and earlier** shipped a pinned `<appVersion>-<git-sha>` in `values.yaml` instead;
if you are reading one of those, the tag is not empty and names the commit directly.

---

## 4. Render it — and the one command that fails on purpose

```sh
helm template gsd ./charts/group-sync-dashboard
```

```
Error: execution error at (group-sync-dashboard/templates/serviceaccount.yaml): ingress.host is
not set and the cluster apps domain could not be read.
```

**That is the chart working correctly.** It normally auto-detects the OpenShift apps domain by
reading `ingresses.config/cluster`, which needs a live cluster — and `helm template` has none. The
refusal is deliberate: an Ingress with no host produces no Route on OpenShift, so the alternative
is a release that installs cleanly, reports healthy, and is unreachable. The error text names all
three cases it happens in (GitOps, `helm template` by hand, and an installer that cannot read the
cluster-scoped ingress config).

Two ways forward:

```sh
# Render offline, supplying the host yourself
helm template gsd ./charts/group-sync-dashboard --set ingress.host=gsd.apps.example.com

# Or render against the live cluster, so the lookup succeeds and you need no flag
helm upgrade --install group-sync-dashboard ./charts/group-sync-dashboard \
  -n group-sync-dashboard -f environments/crc.yaml --dry-run=server
```

Prefer `--dry-run=server` when you have a cluster: it is the only form that exercises the same
`lookup` the real install will, so it catches this class of problem instead of hiding it.

---

## 5. Install from the downloaded copy

```sh
helm upgrade --install group-sync-dashboard ./charts/group-sync-dashboard \
  --namespace group-sync-dashboard --create-namespace \
  -f environments/crc.yaml
```

Verified on this cluster: revision 129, `chart=group-sync-dashboard-0.4.4`, `app=0.7.0`, and the pod
reporting `{"version":"0.7.0","commit":"db8a90510f","branch":"main","dirty":false}`.

**Always pass `-f <your values file>`, on every upgrade.** This is the sharpest trap in the whole
workflow. Helm reuses the previous release's user-supplied values when you pass *neither* `-f` nor
`--set` — but the moment you pass **either one**, it resets to chart defaults plus only what this
invocation supplied. Measured on this release: a single `helm upgrade --set logLevel=DEBUG` turned
`oauthProxy.apiTokenAccess` off, removed the delegate-urls flag from the pod, and reported
`STATUS: deployed`. Keep your values in a file, pass the file every time, and let `--set` carry only
what genuinely varies per invocation.

`environments/crc.yaml` and `environments/example-production.yaml` on `main` are worked examples.
Start from the production one.

Confirm what landed rather than trusting the exit code:

```sh
helm list -n group-sync-dashboard
oc rollout status deploy/group-sync-dashboard -n group-sync-dashboard
oc exec -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- \
  curl -s http://127.0.0.1:8080/api/version
```

The container is named `dashboard`; the pod also runs an `oauth-proxy` sidecar, and the app binds
`127.0.0.1` so it is only reachable through that proxy. If `oc exec` reports "container is not valid
for pod", you named the wrong one.

---

## 6. Air-gapped: move the chart and the image separately

The chart is one file. The image it pins is not in it — `values.yaml` references
`quay.io/ephico2real/group-sync-dashboard:<appVersion>-<sha>`, and a cluster with no route to Quay
needs that mirrored independently.

```sh
# On a connected machine
helm pull group-sync-dashboard/group-sync-dashboard --version 0.5.0
tar -xzf group-sync-dashboard-0.5.0.tgz

# WHICH image does this chart deploy? Ask the chart, do not read one field — an empty
# values.yaml tag means "appVersion", so grepping the tag alone answers "" and you would
# mirror nothing. Rendering gives the reference the cluster will actually pull.
helm template gsd ./group-sync-dashboard --set ingress.host=x.example.com \
  | grep -m1 -oE 'quay\.io/[^"]*'
#   quay.io/ephico2real/group-sync-dashboard:0.7.0

skopeo copy docker://quay.io/ephico2real/group-sync-dashboard:0.7.0 \
            docker://registry.internal.example.com/group-sync-dashboard:0.7.0
```

**Mirror the sha form instead if you want the pin.** `:0.7.0` is an alias that moves when the
application version changes; an air-gapped mirror is exactly where you may prefer a reference that
cannot:

```sh
skopeo copy docker://quay.io/ephico2real/group-sync-dashboard:0.7.0-db8a90510f \
            docker://registry.internal.example.com/group-sync-dashboard:0.7.0-db8a90510f
# then, at install time:  --set image.tag=0.7.0-db8a90510f
```

**Or by digest, which is stronger than either tag.** A tag is a name, and a name can be repointed by
whoever owns the registry — including your own internal one. A digest is a hash of the content, so it
cannot name anything else:

```sh
skopeo inspect --no-tags docker://quay.io/ephico2real/group-sync-dashboard:0.7.0 | grep Digest
#   "Digest": "sha256:aa6a7f5463c6b39f8d2647ba24ae756f4e7a0b101fe05c8e5bb58d05de016a68"

# then, at install time — note this pins the CONTENT, so it survives any retagging on either side:
helm upgrade --install group-sync-dashboard ./group-sync-dashboard -n group-sync-dashboard \
  -f my-values.yaml \
  --set image.repository=registry.internal.example.com/group-sync-dashboard \
  --set image.digest=sha256:aa6a7f5463c6b39f8d2647ba24ae756f4e7a0b101fe05c8e5bb58d05de016a68
```

**Verify the digest on your mirror rather than assuming it carried over.** A straight `skopeo copy`
does preserve it — measured on this registry, where the `:0.5.0` chart-version tag was created by
`skopeo copy` from `:0.7.0` and both report `sha256:aa6a7f5463c6…` — but a copy that converts the
manifest format produces different bytes and therefore a different digest. One command settles it:

```sh
skopeo inspect --no-tags docker://registry.internal.example.com/group-sync-dashboard:0.7.0-db8a90510f | grep Digest
```

`image.digest` wins over `image.tag`, and a malformed one fails the render rather than turning into an
`ImagePullBackOff` on the disconnected side, where debugging is most expensive.

A plain pipe, not `grep <(tar ...)`. Process substitution here gave grep no output and left tar with
a broken pipe — measured while writing this page, which is the only reason it says so.

```sh
# On the disconnected side, after copying the .tgz across
tar -xzf group-sync-dashboard-0.4.4.tgz
helm upgrade --install group-sync-dashboard ./group-sync-dashboard \
  -n group-sync-dashboard --create-namespace \
  -f my-values.yaml \
  --set image.repository=registry.internal.example.com/group-sync-dashboard
```

Override `image.repository` only, never `image.tag` — the tag is the chart's statement about which
build it deploys, and rewriting it decouples the chart from the image it was published with.

---

## Quick reference

| Goal | Command |
|---|---|
| List all published versions | `helm search repo group-sync-dashboard --versions` |
| Download the tarball | `helm pull group-sync-dashboard/group-sync-dashboard` |
| Download and unpack | `helm pull group-sync-dashboard/group-sync-dashboard --untar --untardir ./charts` |
| Pin a version | `helm pull group-sync-dashboard/group-sync-dashboard --version 0.4.3` |
| Read the defaults | `helm show values ./charts/group-sync-dashboard` |
| Render offline | `helm template gsd ./charts/group-sync-dashboard --set ingress.host=<host>` |
| Render against the cluster | `helm upgrade ... --dry-run=server` |
| Install from the copy | `helm upgrade --install group-sync-dashboard ./charts/group-sync-dashboard -n group-sync-dashboard -f <values>` |
| Confirm what is running | `oc exec ... -c dashboard -- curl -s http://127.0.0.1:8080/api/version` |
