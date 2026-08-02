# Local development

The application, its build tooling and its manifests. The repository root is kept clear for
the Helm chart that will be generated from `deploy/dashboard.yaml`.

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

It also pins the released tag into `deploy/dashboard.yaml`, which leaves the tree dirty until
you commit it. That is deliberate — `oc apply` with an unpinned manifest silently rolls the
deployment back to the older tag, which was verified with `--dry-run=server` and is very hard
to attribute after the fact.

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
