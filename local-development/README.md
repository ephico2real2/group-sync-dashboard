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
| `prepare-release.py` | the four version fields, the Chart.yaml history line, the changelog heading, the branch and the commit, from `--app`/`--chart` and a reason; runs the version test first (`../docs/RELEASING.md`) |
| `clusters.example.yaml` | template for `clusters.yaml`, the local poller config |
| `clusters.yaml` | your local config. Gitignored |
| `crc-ca.crt` | CRC's CA, extracted from kubeconfig. Gitignored, regenerable |
| [`API.md`](API.md) | every endpoint, what each field means, and the ones routinely misread |

## Renaming the dashboard

The name is one constant, `TITLE` in `gsd/__init__.py`. The page title, the header, the
signed-out page and the API docs read it, and `tests/test_title.py` holds the README heading to
it. Change it there, then recapture the screenshots, which are the only copies that cannot follow.

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

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q                 # everything hermetic, browser tests included
./.venv/bin/python -m playwright install chromium      # once, for tests/test_ui.py
./.venv/bin/python -m pytest tests/test_ui.py -q       # the browser tests alone
```

`tests/test_ui.py` starts the real application on a free port with a seeded store and the poller
off, then drives it with Playwright (`tests/test_ui.py#server`). Its `dash` fixture turns any
uncaught page error into an immediate failure, which is how a stray backtick that blanked the whole
page was found. CI runs the file in a job of its own (`.github/workflows/ci.yml#ui`), on the
interpreter the image ships, with the Playwright package pinned so the browser is; screenshots and
traces are uploaded only when a test fails. Repository variable `CI_UI_TESTS=false` turns that job
off — for a fork or a runner that cannot download browsers — and leaves every other job as it is.

`tests/test_live_smoke.py` is the one file no CI job runs: it needs a cluster. See below.

## The image

`Containerfile` builds on the Red Hat Hardened Images: `hi/python:3.14-builder` to resolve the wheel
tree, `hi/python:3.14` to run, both on the floating minor tag so a rebuild takes Red Hat's current
3.14. The runtime base has **no shell**; a `pack` stage installs bash, `curl`, `jq` and a handful of
coreutils with `dnf` and copies them in with the libraries they need, so `oc exec … -- sh -c` and
the stamp check in the release scripts work. Two copies sit beside it, both built by nothing:
`Containerfile.annotated`, the same instructions with the full reasoning and every measurement
beside each step (a test holds the two identical), and `Containerfile.ubi`, the previous UBI9
recipe. `docs/DESIGN_hardened_image.md` has the design and the measurements;
`docs/image-vulnerability-scan.md` has the scan.

What is in the pod's shell: `sh`, `bash`, `curl`, `jq`, `cat`, `ls`, `base64`, `mkdir`, `chgrp`,
`chmod`, `rm`. What is not: `head`, `wc`, `grep`, `id`, `pip`, `rpm`, `dnf`. A command that needs
one of those fails with "command not found".

Scan locally the way CI does — Grype, because Trivy does not recognise the base's OS:

```bash
podman build --target pack -t gsd:pack -f Containerfile .
podman save --format docker-archive -o /tmp/gsd.tar group-sync-dashboard:<tag>
grype docker-archive:/tmp/gsd.tar --only-fixed --fail-on high
```

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

## Reading the API from outside the cluster

```bash
read -rs GSD_PASSWORD && export GSD_PASSWORD
./cluster-report.py --clusters prod,staging --domain example.com --ldap-user svc-reporter
```

Credentials are exchanged for a short-lived token against each cluster's own OAuth server, so
no `oc` and no kubeconfig are involved. Needs `oauthProxy.apiTokenAccess.enabled` on the chart,
and the calling account must hold cluster-wide RBAC read (`cluster-reader` or equivalent) —
because `/api` reports the cluster's whole binding surface, not just group membership.

curl and Postman recipes, and the two Postman defaults that break the flow:
[`docs/api-access.md`](../docs/api-access.md).

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

* **the Ingress host**, only when `--set ingress.enabled=true` is passed — derived from the
  cluster's apps domain, because without it the chart's own guard aborts, since a hostless
  Ingress produces no Route at all on OpenShift. The default Route needs no host and no lookup;
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
