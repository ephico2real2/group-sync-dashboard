# Design — per-cluster connection credentials (chart-managed mounts, LDAP bind, insecure-TLS)

Status: decisions settled (2026-09-15, see the Decisions section), ready for P1 implementation.
Author-driven from the operator's 2026-09-14 request, after the #117/#118 mock-cluster integration
exposed the gap live. This is a **chart feature** (with a small Phase-2 application addition),
decomposed into its own PR(s), per the programme's design-first rule.

## 1. The problem, measured

Adding a **remote** cluster to `clusters:` today is only half-supported. Each entry names file paths
(`tokenFile`, `caBundleFile`), but the chart mounts a **fixed** set of volumes (`config`, `data`,
`tmp`, `curlrc`, `report-token` (the volume name; the Secret is `-shared-token` since 0.37.0), `service-ca`, `trusted-ca-*`, `oauth-*` — `templates/deployment.yaml`)
and provides **no per-cluster volume for a remote cluster's bearer token**. The CA has a path
(`trustedCA.existingConfigMap` → `GSD_TRUSTED_CA_FILE`, a shared fallback), but the **token does not**.
Proven during the #117 test: wiring a second cluster required a hand `oc set volumes` patch that Helm
reverts on the next upgrade. A real external cluster with its own token hits exactly this.

Two more gaps the same request names:
- **No LDAP service-account auth.** Connecting a remote cluster needs a pre-created bearer token
  (manual `oc create token`/SA). An operator would rather bind with an **LDAP service account (full DN)
  + password already synced to the remote cluster and granted cluster-admin**, and let the dashboard
  obtain a token itself — no manual token step.
- **No per-cluster insecure-TLS.** `ClusterConfig.insecure_skip_verify` exists in the app
  (`gsd/config.py`, mutually exclusive with `caBundleFile`) but is not surfaced ergonomically per cluster.

## 2. As-is (what the code already gives us)

- `ClusterConfig` (`gsd/config.py`): `name`, `api_url`, `token_file`, `token_env`, `ca_bundle_file`,
  `insecure_skip_verify` (default `False`). `load_settings` accepts `apiUrl`, `tokenFile`,
  `caBundleFile`, `insecureSkipVerify`, `tokenEnv`, `enabled`; it **requires one of `tokenFile`/`tokenEnv`**
  and **refuses `insecureSkipVerify` together with `caBundleFile`**. There is **no** username/password
  or LDAP field — LDAP auth is new application code.
- The client (`gsd/kube.py` `_client`): one `httpx.Client(verify=…)`, bearer token from the file, three
  CA-trust modes (`insecure_skip_verify` → `verify=False`; a named `ca_bundle_file`; else the shared
  `GSD_TRUSTED_CA_FILE`/system bundle).
- The chart passes `clusters:` through verbatim (`templates/configmap.yaml`:
  `clusters: {{ toYaml .Values.clusters | nindent 6 }}`), and offers a **shared** enterprise CA via
  `trustedCA.injected` (OpenShift-filled) and `trustedCA.existingConfigMap` (operator-supplied),
  colon-joined into `GSD_TRUSTED_CA_FILE`.

The insight that shapes this design: **modes 1 and 2 below need no application change.** The new
per-cluster stanza is chart *sugar* that (a) creates the per-cluster volume mounts and (b) computes the
`tokenFile` / `caBundleFile` / `insecureSkipVerify` the app already understands. Only **mode 3 (LDAP)**
touches `gsd/config.py` and `gsd/kube.py`.

## 3. The three connection modes

Every `clusters[]` entry resolves to exactly one:

1. **`inCluster` — the hosting cluster (the dashboard's own).** A full cluster; it needs no LDAP and no
   mounted secret — it uses the pod's ServiceAccount. A convenience flag auto-loads the standard SA
   paths so the operator writes neither:
   ```yaml
   - name: crc-local
     inCluster: true      # ⇒ tokenFile /var/run/secrets/kubernetes.io/serviceaccount/token,
                          #    caBundleFile /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
     enabled: true
   ```
   The explicit form (today's `tokenFile`/`caBundleFile`) stays valid and is what `inCluster: true`
   expands to. Default when a single-cluster install names no mode: `inCluster: true` for the first entry.

2. **`credentials.token` — a remote cluster via a mounted bearer token + CA.** The operator pre-creates
   a Secret (the token) and, optionally, a ConfigMap (the CA); the chart mounts them at deterministic
   paths and fills in the app fields. Chart-only.

3. **`credentials.ldap` — a remote cluster via an LDAP service account.** Bind DN + a password (from a
   pre-created Secret) synced to the remote cluster's LDAP IdP and granted the required RBAC; the
   dashboard exchanges them for a token against the remote cluster's OAuth server. **Phase 2**: new app
   code (an OAuth resource-owner-password grant in `gsd/kube.py`, a new `ClusterConfig` auth field).

## 4. The per-cluster `credentials` stanza

```yaml
clusters:
  - name: remote-prod
    apiUrl: https://api.remote-prod.example.com:6443
    enabled: true
    insecureTLS: false                    # per cluster → ClusterConfig.insecure_skip_verify
    credentials:
      # ── exactly one auth method ──────────────────────────────────────────
      token:
        secretName: remote-prod-token     # PRE-EXISTING Secret. default: <name>-secret
        key: token                        # default: token
      # ldap:                             # Phase 2
      #   bindDN: "cn=svc-gsd,ou=ServiceAccounts,dc=corp,dc=com"
      #   secretName: remote-prod-ldap    # PRE-EXISTING Secret, key `password`
      #   key: password

      # ── CA: reuse-existing; default the shared enterprise root CA ─────────
      ca:
        existingConfigMap: ""             # "" ⇒ the shared trustedCA bundle (verifies every corp endpoint)
        key: ca.crt                       # default: ca.crt
        # create-from-values is deliberately NOT offered: cert bytes in values land in git and
        # `helm get values` — the chart's standing rule (trustedCA.existingConfigMap comment).
```

**Never in values:** the token, the LDAP password, and CA bytes. The Secret and (optional) ConfigMap
**must exist before `helm install`** — the chart references them, it does not template their contents.
A missing referenced object fails the render/rollout loudly (not `optional`), the same stance as
`trustedCA.existingConfigMap`.

## 5. Deterministic mounts, and auto-resolved paths

Per cluster `<name>`, the chart adds (only for modes 2/3) volumes + mounts under one base:

| What | Source | Mount path |
|---|---|---|
| token / LDAP password | Secret `credentials.*.secretName` | `/etc/gsd/clusters/<name>/secret/token` |
| CA | ConfigMap `credentials.ca.existingConfigMap` | `/etc/gsd/clusters/<name>/config/ca.crt` |

The chart then **computes** the entry written into clusters.yaml, so the operator never hand-writes a
path:
- `tokenFile: /etc/gsd/clusters/<name>/secret/token`
- `caBundleFile: /etc/gsd/clusters/<name>/config/ca.crt` — **unless** `credentials.ca.existingConfigMap`
  is empty, in which case no `caBundleFile` is set and the entry falls back to the shared
  `GSD_TRUSTED_CA_FILE` (the enterprise root CA that verifies all corp endpoints — the default).
- `insecureSkipVerify: <insecureTLS>` — and when `true`, **no** `caBundleFile` is emitted (the app
  refuses both together; the render enforces the same).

`inCluster: true` (mode 1) mounts nothing and emits the two SA paths.

### 5.1 Per-cluster path override — the name-derived variable

The default paths above cover the common case (one shared CA for all clusters). To repoint a single
cluster without editing the base, each cluster exposes an override keyed off its **name**, upper-cased
(the operator's "camel case of the path name … in UPPER CASE"):

```yaml
# equivalent ways to override cluster "remote-prod"'s CA/token paths:
clusterOverrides:
  REMOTE_PROD:
    caPath: /etc/pki/corp/ca-bundle.crt     # e.g. reuse a CA already mounted elsewhere
    tokenPath: /etc/gsd/clusters/remote-prod/secret/token
```

An env var of the same shape (`GSD_CLUSTER_<UPPER_NAME>_CA_PATH` / `_TOKEN_PATH`) is the runtime form,
so a path can be overridden without re-rendering. **Open for review:** whether the override lives in
values (`clusterOverrides.<UPPER_NAME>`) only, or also as an env var the app honours — the values form
is simpler and sufficient for the stated use; the env form is listed so review can decide.

## 6. Chart templates this needs

- **a new templates/cluster-mounts.yaml** (new, or folded into `deployment.yaml`): iterate
  `.Values.clusters`, and for each mode-2/3 entry append a Secret volume + mount at
  `/etc/gsd/clusters/<name>/secret` and, when `credentials.ca.existingConfigMap` is set, a ConfigMap
  volume + mount at `/etc/gsd/clusters/<name>/config`.
- **`templates/configmap.yaml`**: replace the verbatim `toYaml .Values.clusters` pass-through with a
  loop that emits the **computed** entry (name, apiUrl, enabled, the resolved `tokenFile`/`caBundleFile`,
  `insecureSkipVerify`), honouring `inCluster` and `clusterOverrides`.
- **`_helpers.tpl`**: `gsd.clusterSecretName`, `gsd.clusterCaConfigMap`, `gsd.clusterTokenPath`,
  `gsd.clusterCaPath`, `gsd.clusterUpperKey` (name → `UPPER_SNAKE` for the override lookup).

No application change for modes 1–2. Mode 3 adds, in a later PR: a `ClusterConfig` auth kind, an
OAuth password-grant client in `gsd/kube.py`, token caching/refresh, and the `credentials.ldap` render.

## 7. Guards (render-time), all failing loud

- Exactly one of `inCluster` / `credentials.token` / `credentials.ldap` per entry; none ⇒ error naming
  the entry (no silent SA fallback for a remote apiUrl).
- `insecureTLS: true` **XOR** `credentials.ca` — mirror the app's mutual-exclusion so a contradiction
  fails at render, not at first poll.
- A referenced `secretName`/`existingConfigMap` name that is empty when its mode requires it ⇒ error.
- `inCluster: true` with `apiUrl` other than the in-cluster API ⇒ warn/refuse (a common copy-paste trap).
- Duplicate cluster names ⇒ error (they key the mount paths and the store).

## 8. Security stance (unchanged from the chart's existing rules)

- Credentials (token, LDAP password) and CA bytes are **never** in values.yaml, `helm get values`, or CI
  logs — always a pre-created Secret/ConfigMap referenced by name.
- LDAP mode stores only a **reference** to the password Secret; the DN is not a secret and may live in
  values. The obtained token is held in memory, never written.
- `insecureTLS: true` is loud in NOTES and the cluster row (a deliberate, visible downgrade).

## 9. Decomposition (each its own PR, each its own review)

- **P1 — chart-only:** the `credentials.token` + `ca` mounts, the `inCluster` flag (and migrating the
  default `crc-local` entry to `inCluster: true`), `insecureTLS`, the computed clusters.yaml,
  `clusterOverrides.<UPPER_NAME>` (values-only), the shared-CA default, guards, a `helm template` matrix
  test and a values-defaults update. No app change. Validated by re-running the #117 mock-cluster
  integration through pure Helm values (no `oc set volumes`).
- **P2 — LDAP bind:** `credentials.ldap`, the app's OAuth password-grant + token refresh in `gsd/kube.py`,
  a new `ClusterConfig` auth kind, guards, and a mock-app fixture that serves the OAuth token endpoint.

## 10. Verification

- `helm template` across the matrix: inCluster; token+existing-CA; token+shared-CA; insecureTLS;
  overrides; each guard's refusal.
- The mock cluster (#116/#118) is the integration rig — the #117 test already proved the *runtime* path
  (poller → mock over TLS → capture → B3); P1 proves the same reachable through **values alone**.
- `test_storage_seam`, `test_values_defaults` (every new false-default enumerated), `test_chart_versions`
  (chart bump), and the citation tests stay green.

## Decisions (settled with the operator, 2026-09-15)

The round-1 open questions are resolved; P1 is built to these.

0. **Cluster names are operator-chosen.** `name:` is arbitrary — the operator names each entry what they
   like — and EVERYTHING derives from it: the mount paths (`/etc/gsd/clusters/<name>/secret/token`,
   `…/config/ca.crt`), the Secret/ConfigMap default names (`<name>-secret`), and the override key
   (`<UPPER_NAME>` — the name upper-snake-cased). A rename is one edit; the helpers recompute the rest.
   No name is special-cased in the templates.
1. **Override surface: values-only.** `clusterOverrides.<UPPER_NAME>` in P1 (`caPath` / `tokenPath`); the
   `GSD_CLUSTER_<NAME>_*` env form is deferred — the values form is simpler and sufficient for the stated
   use, and a second runtime surface can be added later without breaking the values one.
2. **`inCluster` default: auto for the first entry** when no mode is named, so a single-cluster install
   stays a one-liner (`- {name: <chosen>, enabled: true}` ⇒ the hosting SA).
3. **Base mount path: `/etc/gsd/clusters/<name>/…`** — kept, consistent with the chart's existing
   `/etc/gsd/*` mounts, rather than a bare `/<name>/…`.
4. **P1 migrates the default `crc-local` entry to `inCluster: true`.** The values default becomes
   `- {name: crc-local, inCluster: true, enabled: true}` (the name stays operator-choosable); the explicit
   `tokenFile`/`caBundleFile` form still works and is what `inCluster: true` expands to. This is a
   values-default change consumers see, noted in the P1 CHANGELOG as such.
