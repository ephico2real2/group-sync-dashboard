# Local development

The application and its build tooling. The Helm chart at `../charts/group-sync-dashboard` is
the single source of truth for RBAC, config and workload shape; plain YAML is **generated
from it** by `./render-manifests.sh`, never hand-written.

That direction used to be the other way round, and it is worth knowing why it changed. A
hand-maintained `deploy/dashboard.yaml` sat here for 62 commits without anyone noticing it
had gone stale. It was missing the `coordination.k8s.io/leases` grant the poller needs, so a
cluster deployed from it came up passing both probes and silently never polled — and since
every object name matched the Helm release, applying it over a live cluster stripped the
oauth-proxy sidecar off a dashboard that serves group membership. Two hand-kept copies of
RBAC cannot be kept in agreement; one generated copy is in agreement by construction.

Run everything below from **this** directory.

| File | What it is |
|---|---|
| `release-crc.sh` | build + push + deploy against **CRC's built-in registry**. Portable nowhere else |
| `clusters.example.yaml` | template for `clusters.yaml`, the local poller config |
| `clusters.yaml` | your local config. Gitignored |
| `crc-ca.crt` | CRC's CA, extracted from kubeconfig. Gitignored, regenerable |
| [`API.md`](API.md) | every endpoint, what each field means, and the ones routinely misread |

## Run the dashboard against CRC

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"

# CRC's CA, so TLS is verified rather than skipped even in development
kubectl config view --raw --minify \
  -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' \
  | base64 -d > crc-ca.crt

cp clusters.example.yaml clusters.yaml
export GSD_TOKEN_CRC=$(oc whoami -t)
GSD_CONFIG=clusters.yaml ./.venv/bin/uvicorn gsd.api:create_app --factory --port 8099
```

Then <http://127.0.0.1:8099>.

`clusters.example.yaml` points at `crc-ca.crt` and reads the token from `GSD_TOKEN_CRC`.
Prefer that over `insecureSkipVerify` — a dev habit of skipping verification is one that
follows you into a cluster that matters.

## Release to CRC's internal registry

```bash
./release-crc.sh              # build + push + deploy
./release-crc.sh --build-only
```

Same tagging and verification rules as the external script: `<version>-<git-sha>`, refuses a
dirty tree, verifies the commit stamp inside the image before pushing, and reads it back out
of the running pod afterwards.

It deploys with `helm upgrade --install`, passing the released tag with `--set`. Nothing is
written back into the tree: `helm get values` already records what is deployed, so there is
no manifest to pin and no commit to remember.

## API docs

Swagger UI at `/api` (`/api/docs` redirects there), ReDoc at `/api/redoc`, the spec at
`/api/openapi.json`. Both renderers are served from bundles committed to this repository, not
from a CDN, so they work on a cluster with no route to the internet.

Refreshing them is a five-minute job every couple of months:

```bash
./vendor-assets.sh --outdated    # anything newer?
./vendor-assets.sh --upgrade     # take it
./vendor-assets.sh               # re-check, offline
```

Full procedure and the reasoning: [`docs/updating-vendored-assets.md`](../docs/updating-vendored-assets.md).
Rules for adding an endpoint: [`docs/api-contract.md`](../docs/api-contract.md).

## Plain YAML, for reading and testing

```bash
./render-manifests.sh          # chart -> deploy/, one file per object
oc diff  -f deploy/            # what would change
oc apply -f deploy/            # if you want to apply it yourself
```

`deploy/` is generated output and is gitignored. The script never applies anything — the
folder exists so a human, a review, or a diff in a ticket sees the exact objects before the
cluster does.

Two values the chart normally reads from the live cluster are resolved by the script instead,
because `helm template` runs with no cluster connection and every `lookup` in the chart
returns empty:

* **the Ingress host**, derived from the cluster's apps domain — without it the chart's own
  guard aborts, since a hostless Ingress produces no Route at all on OpenShift;
* **the oauth cookie secret**, read back from the live Secret. This one matters: the chart
  mints a fresh `randAlpha 32` whenever it cannot find an existing Secret, so two consecutive
  renders produce two different keys and applying them in turn signs every logged-in user
  out. The script reuses the live value and says which it did.

**`helm upgrade --install` remains the supported deploy.** Applying rendered YAML leaves no
Helm release, so `helm list`, `helm rollback` and `helm diff` know nothing about it. Do not
mix the two paths against one namespace and expect Helm's stored state to stay truthful.

## Live smoke test

```bash
GSD_TOKEN_CRC=$(oc whoami -t) GSD_LIVE_CONFIG=clusters.yaml \
  ./.venv/bin/python -m pytest tests/test_live_smoke.py -q
```

Skipped unless `GSD_LIVE_CONFIG` is set, so the default suite stays hermetic. It asserts
shapes rather than counts — group counts change on every sync, and a test pinning them fails
for the wrong reason.

## Forcing a sync

The operator reconciles on **generation** change, and generation only advances when `.spec`
changes. `oc annotate` does nothing: verified on CRC, generation stayed at 2 and
`lastSyncSuccessTime` never moved, while a spec patch took it to 3 and synced within seconds.

`60-force-groupsync.sh` in the chart repo (`setup-local-ldap-testing/`) does this by toggling
`pageSize`, which is inert at this scale. It turns a 30-minute wait per iteration into about
40 seconds.

## Notes about CRC specifically

**Monitoring is disabled at the CVO level** — `cluster-monitoring-operator` and `monitoring`
are both `unmanaged=true`, and `openshift-monitoring` has no pods. So there is no Prometheus,
user-workload monitoring cannot be enabled the normal way, and the ServiceMonitor and
PrometheusRule in `deploy/` are inert here. They are still validated: `promtool check rules`
passes, and the metrics endpoint is scrapeable over the Service from inside the cluster.

**The podman VM cannot resolve `*.crc.testing`.** CRC maps those names to `127.0.0.1` in
`/etc/hosts`, which inside the VM means the VM itself. The Mac is `192.168.127.254` from
there, so pushing to CRC's registry needs a hosts entry in the VM:

```bash
REG=default-route-openshift-image-registry.apps-crc.testing
podman machine ssh "grep -q '$REG' /etc/hosts || \
  echo '192.168.127.254 $REG' | sudo tee -a /etc/hosts"
```

**`podman pull -q` and `podman manifest inspect` report failure for images that pull and run
fine.** Test a base image with `podman run`, not those.

**`/tmp` is not shared into the podman VM.** Bind-mount from under `/Users`.
