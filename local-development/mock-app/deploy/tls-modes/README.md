# The TLS-modes rig — three copies of the mock API, one per way of trusting a cluster

A Secret-declared cluster (`docs/specs/SPEC_S1_cluster_secrets.md`, #230) trusts its API server's
certificate one of three ways, and each is proven here against a copy of the mock OpenShift API that is
identical to `mock-openshift` except for **who signed its serving certificate**. The rig is repeatable
(`deploy-tls-modes.sh`) and stays deployed on the lab: S2's Cluster Configurations walk shows it.

| copy | its serving certificate | the Secret under test | proves |
|---|---|---|---|
| `mock-trusted` | signed by the ClusterIssuer `ldap-enterprise-ca` — the one CA in `proxy/cluster.spec.trustedCA`, so in the dashboard's injected `GSD_TRUSTED_CA_FILE` bundle | a bearer token and **no** `tlsClientConfig` | **mode 1, the default**: the dashboard's own trust store verifies it; `tls: {insecure: false, ca: "trusted-bundle"}`, `status: ok` |
| `mock-privateca` | signed by a new self-signed CA (`mock-privateca-ca`) that nothing trusts | first the same as above; then `tlsClientConfig.caData` = that CA's PEM (base64) | **mode 1 fails** with the x509 error as the poll outcome (the finding an operator reads to learn they need mode 2), then **mode 2**: `tls.ca: "caData"`, `status: ok` |
| `mock-selfsigned` | a bare self-signed leaf (the `selfSigned` issuer directly on the Certificate) | `tlsClientConfig.insecure: true` | **mode 3**: `tls: {insecure: true, ca: null}`, `status: ok` |
| (`mock-selfsigned` again) | — | `caData` **and** `insecure: true` | **the refusal**: the finding `insecure-with-ca` naming both fields, no cluster listed, the dashboard pod alive |

Every copy runs the same image (`mock-openshift:test`) and the same fixture ConfigMap (`mock-fixture`),
so the three clusters show the fixture's GroupSyncs and groups beside `crc-local` once polled — the
witness that the connection works end to end, not only the handshake.

## Files

- `workload.yaml.tmpl` — the Service and Deployment, rendered per NAME (the TLS Secret is `<NAME>-tls`).
- `pki-trusted.yaml`, `pki-privateca.yaml`, `pki-selfsigned.yaml` — the three cert-manager shapes.
- `cluster-secret.yaml.tmpl` — the labelled Secret, rendered with the fixture's `meta.token` and the
  `config` JSON for the mode; the private CA's PEM is filled from the cert-manager CA Secret by the
  script, never committed.
- `deploy-tls-modes.sh` — deploy, then prove (`--prove` to re-run the proofs; `--down` to remove the
  Secrets and workloads, keeping the PKI).

## Prerequisites

cert-manager with the lab's `ldap-enterprise-ca` ClusterIssuer (the enterprise root the trusted bundle
carries — `proxy/cluster.spec.trustedCA` → `openshift-config/ldap-enterprise-ca-bundle`); the mock
image pushed by `../deploy-mock.sh`; the dashboard deployed with `clusterConfig.secrets.enabled` (the
default). The run of 2026-09-20 is recorded in `reports/2026-09-20_cluster-secrets-230/README.md`.
