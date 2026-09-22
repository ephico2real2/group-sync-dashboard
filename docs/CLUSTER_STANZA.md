# The cluster stanza — every accepted combination, measured

What a `clusters[]` entry in `values.yaml` may contain, what each combination does, and what is
refused with which message. **Nothing here is written from reading the source**: every row was
produced by rendering the chart with that stanza (`helm template`) and by loading the same stanza in
the pod's own loader. The script is `local-development/tests/test_cluster_stanza_matrix.py`, which
fails the build if the table below stops being true.

There are three ways to declare a cluster and they are equal paths — the values stanza below, a
labelled Secret (`docs/specs/SPEC_S1_cluster_secrets.md`), and the Cluster Configurations tab. The
same keys mean the same thing in each. This document is the values path; the differences for a
Secret are in [§6](#6-the-same-stanza-as-a-secret).

## 1. The keys

Exactly these, and nothing else — an unknown key is refused by name rather than ignored, because a
typo that silently does nothing is how a cluster ends up unpolled with no one the wiser.

| key | type | meaning |
|---|---|---|
| `name` | string, required | the cluster id. **Renaming retires the old cluster** — 33 observation tables key on it, and nothing migrates. No `/`. |
| `apiUrl` | string, required | `http://` or `https://`, trailing slash stripped |
| `tokenEnv` | string | the environment variable holding the token |
| `tokenFile` | string | a file the chart mounts, re-read on every use so a rotated token needs no restart |
| `caBundleFile` | string | a PEM file to verify the API server against |
| `insecureSkipVerify` | bool | verification off. Mutually exclusive with `caBundleFile` |
| `enabled` | bool | `true` or `false` as a **word**, never a quoted `"yes"` |
| `visibility` | enum | `inherit` · `self-only` · `hidden` · `remote-sar` |
| `identity` | enum | `same-as-host` · `none` |
| `dashboardController` | bool | this pod's own cluster. Exactly one enabled entry |
| `saTokenLookup` | bool | connection mode: log in as the fleet account, read the poller SA's token |
| `userSelfLogin` | bool | connection mode: poll as the fleet account itself |
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster |

## 2. The credential — exactly one source

A stanza carries a credential **or** declares a mode that will obtain one. Never both: two sources of
truth for one credential is a stanza whose author meant one of them.

| what the stanza carries | `credential_kind` | polled? |
|---|---|---|
| `tokenFile` = the SA path | `in-cluster` | yes |
| `tokenEnv` or `tokenFile` | `file` | yes |
| `saTokenLookup: true` | `remote-lookup` | **after the lookup** — the dashboard logs in as the fleet account, reads the poller SA's token on the target and writes `gsd-cluster-<name>`, which then polls (SPEC_S4b); needs `clusterConfig.secrets.writes.enabled` |
| `userSelfLogin: true` | `self-login` | **no — pending** |
| a Secret's `bearerToken` | `bearer` | yes |
| a Secret's `oauth {username, password}` | `oauth` | **no — pending (#119 P2)** |

A *pending* cluster is listed on the Cluster Configurations tab with the reason, and is **not
polled** — deliberately, so it is never reported as `auth_failed` for a credential that was never
presented. The connection itself is S3b and is not built; S3a ships the keys.

## 3. TLS — how the API server is verified

Resolved in this order, first match wins:

| stanza | mode |
|---|---|
| `insecureSkipVerify: true` | `insecure` — verification off |
| a Secret's `tlsClientConfig.caData` | `caData` |
| `caBundleFile` = the pod's SA CA path | `serviceAccount` |
| any other `caBundleFile` | `caBundleFile` |
| none of the above | `trusted-bundle` — the chart's `trustedCA` bundles plus the system store |

## 4. Accepted combinations — measured

Each rendered and loaded. All twelve are accepted by both readers.

| # | stanza | effect |
|---|---|---|
| 1 | host with `dashboardController: true`, SA token + SA CA | the shipped default |
| 2 | remote + `tokenEnv` | polled, `trusted-bundle` TLS |
| 3 | remote + `tokenFile` | polled, token re-read per use |
| 4 | remote + `tokenEnv` + `caBundleFile` | polled, pinned CA |
| 5 | remote + `tokenEnv` + `insecureSkipVerify` | polled, verification off |
| 6 | remote + `saTokenLookup` | retrieved on the next discovery cycle, then polled through its written Secret; renders only with `clusterConfig.secrets.writes.enabled` |
| 7 | remote + `userSelfLogin` | listed, pending, not polled |
| 8 | remote + `saTokenLookup` + `ldapConnectionBootstrap` | as 6, with a per-cluster bootstrap account |
| 9 | remote + `visibility: self-only` | every viewer is the self tier there |
| 10 | remote + `visibility: hidden` | polled, never served through `/api` |
| 11 | remote + `visibility: remote-sar` + `identity: same-as-host` | that cluster's own RBAC decides |
| 12 | remote + `enabled: false` | kept in the config, not polled |

## 5. Refusals — measured, and WHERE each one fires

This is the part worth reading twice. Fourteen refusals fail `helm template`, so a bad stanza never
reaches a cluster. **Four do not** — they render cleanly and the pod refuses them at startup, which
after a green upgrade looks like an outage rather than a config error.

| refused | `helm template` | pod startup |
|---|---|---|
| both connection modes | **refused** | refused |
| a mode beside `tokenEnv`/`tokenFile` | **refused** | refused |
| neither a credential nor a mode | **refused** | refused |
| `ldapConnectionBootstrap` without a mode | **refused** | refused |
| `ldapConnectionBootstrap` not a username | **refused** | refused |
| a connection mode on the hosting cluster | **refused** | refused |
| two `dashboardController` entries | **refused** | refused |
| `dashboardController` with `enabled: false` | **refused** | refused |
| `visibility: hidden` on the host | **refused** | refused |
| `visibility: remote-sar` on the host | **refused** | refused |
| `remote-sar` without `identity: same-as-host` | **refused** | refused |
| a `visibility` typo (`self_only`) | **refused** | refused |
| an `identity` typo (`Same-As-Host`) | **refused** | refused |
| `enabled: "yes"` | **refused** | refused |
| **an unknown key** | *renders* | **refused** |
| **a duplicate `name`** | *renders* | **refused** |
| **`apiUrl` without a scheme** | *renders* | **refused** |
| **`insecureSkipVerify` + `caBundleFile`** | *renders* | **refused** |
| `saTokenLookup` without `clusterConfig.secrets.writes.enabled` | **refused** | starts; the tab reports `fleet-write-disabled` (a Secret-declared mode reaches this half) |
| `saTokenLookup` without `clusterConfig.secrets.enabled` | **refused** | starts; the cluster stays pending |
| `saTokenLookup` with `replicaCount > 1` | **refused** | starts (one retriever per estate, SPEC_S4 §6) |
| `saTokenLookup` with `visibility: remote-sar` | **refused** | starts; the write would be refused `visibility-invalid` |

The chart's guard covers the connection-mode and host rules; the remaining four are the loader's
alone, because `templates/configmap.yaml` passes `clusters` through with `toYaml` and the pod is
the first thing to read them. Closing that gap is tracked separately — until then, a `helm template`
that succeeds is not proof the stanza loads.

### Why some refusals read strangely

- **`enabled` is read as a word.** `bool("false")` is `True` in Python, so a templated
  `enabled: "false"` once enabled a cluster — and the first enabled entry used to be the
  authorization host.
- **A bootstrap refusal never repeats the value**, in case something other than a username was
  written into it.
- **The host-only rules run in a second pass**, after every entry is read: the host is not known
  until then, and checking inline against "the first enabled entry" once accepted `hidden` on the
  declared controller — the one cluster the rule exists to protect.

## 6. The same stanza as a Secret

A labelled Secret carries the same connection keys under `config`, so one declaration has two
readers. The differences:

- `dashboardController` is **refused by name** — a Secret-sourced cluster is remote by definition.
- The credential is `bearerToken` or `oauth {username, password}` rather than `tokenEnv`/`tokenFile`.
- TLS is `tlsClientConfig.caData` or `.insecure`.
- Argo CD's own keys are refused **by name with the reason** (`username`/`password`,
  `execProviderConfig`, `awsAuthConfig`, `proxyUrl`, `disableCompression`, `certData`, `keyData`,
  `serverName`), so a Secret copied from an Argo cluster entry says what is not supported.
- A refused Secret is a **finding on the tab**, never a crashed pod.

A key name is a place a credential can land, so a refusal repeats a key only when it is one this
contract already knows; anything else is described by its length.

## 7. Worked example

`charts/group-sync-dashboard/example-production.yaml` is a production values file using these
combinations, with the reasoning inline.
