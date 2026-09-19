# Mock cluster — CRC deployment bits

The mock OpenShift API server (`mock_app`) is added to the dashboard as a **second cluster** on
CRC so the namespace-access report and the P2 multi-dimension selector can be exercised against its
fixture namespaces. `environments/crc.yaml` wires it in as `clusters[].name: mock`
(`https://mock-openshift:6443`), reading its token and CA from the `mock-cluster-creds` Secret
mounted at `/etc/gsd/mock`.

## `certmanager-tls.yaml` — the serving certificate

The mock terminates real TLS (the dashboard verifies it with `CERT_REQUIRED` + hostname checking —
see `mock_app/tls.py` for the trust model), so it needs a serving cert whose SANs match
`mock-openshift`. Originally that was a static self-signed secret, and it **expired out from under
the dashboard** (2026-09-16), turning every mock poll into `CERTIFICATE_VERIFY_FAILED`.

`certmanager-tls.yaml` replaces it with a cert-manager PKI in the `group-sync-dashboard` namespace:

- a **stable** self-signed CA (`mock-ca`, 5-year, does **not** rotate on leaf renewal), and
- an **auto-renewing** leaf (`mock-tls`, 90-day, renewed 15 days early) carrying the mock's SANs.

Because the CA is stable, the dashboard trusts it once — its cert is copied into
`mock-cluster-creds.ca.crt` — and that trust stays valid across every leaf renewal. The mock already
mounts the `mock-tls` Secret at its serving path, so renewal is transparent.

Apply it on a cluster that has the cert-manager operator (CRC does):

```bash
oc apply -n group-sync-dashboard -f certmanager-tls.yaml
# then, once, copy the CA into the dashboard's trust for the mock cluster:
oc get secret mock-ca -n group-sync-dashboard -o jsonpath='{.data.tls\.crt}' | base64 -d \
  | oc set data secret/mock-cluster-creds -n group-sync-dashboard --from-file=ca.crt=/dev/stdin
oc rollout restart deploy/group-sync-dashboard -n group-sync-dashboard
```

## `mock-openshift.yaml` — the Deployment and Service

The mock's `Deployment` and `Service` (`mock-openshift:6443`), committed on 2026-09-18 after the move to
the new MacBook made them the thing to re-author from memory. The Deployment loads the cert-manager
chain above through `MOCK_CA_IN=/certs` (the `mock-tls` Secret carries exactly the `ca.crt`, `tls.crt`,
`tls.key` the image reads), runs under `restricted-v2`, and sets `OPENSSL_armcap=0` — CRC on Apple
Silicon advertises CPU features the hardware lacks and the `cryptography` wheel's OpenSSL dies with
SIGILL without it (measured; details in the manifest and in
`docs/handoff/macbook-migration-plan.md` §4.6).

```bash
oc apply -n group-sync-dashboard -f certmanager-tls.yaml     # first: the pod mounts the Secret it issues
oc apply -n group-sync-dashboard -f mock-openshift.yaml
```

## What is **not** here

The `mock-cluster-creds` Secret (token + CA) and the `mock-creds` volume on the dashboard Deployment are
per-install steps that Helm cannot see; `docs/handoff/macbook-migration-plan.md` §4.9 steps 4–5 are the
commands, and they are re-applied after every fresh install of the chart.
