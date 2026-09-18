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

## What is **not** here yet

The mock's `Deployment`, `Service` (`mock-openshift:6443`) and the `mock-cluster-creds` Secret
(token + CA) are still applied to CRC out of band, not from a committed manifest. Capturing the full
mock CRC wiring as manifests is tracked separately; this file preserves the one piece that has
already bitten us — the serving certificate — so it travels in git.
