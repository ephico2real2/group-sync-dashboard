# The cluster stanza — every accepted combination, measured

## Cluster Configurations: findings and warnings

The tab names configuration problems and warnings separately. Only cluster administrators can open it.

| Where | Meaning | What to do |
|---|---|---|
| Findings card | A refused Secret or ConfigMap stanza names its source and reason. | Fix the source named in the finding. |
| ⚠️ banner and `shared API URL` chip | Two or more effective entries declare the same API URL. The banner names the entries and URL; each affected card names its peers. | Keep deliberate aliases. Remove an unintended duplicate from its source. |

A shared URL refuses nothing. Each enabled, ready entry still polls and contributes its own counts;
a finding on that server can therefore appear once per entry. Existing Rotate, Delete and Add controls
keep their behaviour. Refused Secrets do not contribute to the warning. Pending entries count and can
be named; a disabled entry is not polled and joins no group. Values, discovered Secrets and ConfigMap-generated entries all
participate after name precedence is resolved.

Host case, default ports and trailing slashes are normalised by the credential gate's existing URL
rule. Different URLs that reach the same physical cluster are not detected. The API exposes warnings
separately from findings; see [`GET /api/clusterconfigs`](../local-development/API.md#get-apiclusterconfigs).

## ConfigMap onboarding (#293, SPEC_S5)

The existing measured values tables below remain the values contract. The additional runtime authoring
path is a ConfigMap in the release namespace; its stanzas call the same parser as values. Example:

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: cluster-onboarding
      namespace: group-sync-dashboard
      labels:
        groupsync-dashboard.io/config-type: onboard  # sideload is an exact synonym
    data:
      clusters.yaml: |
        clusters:
          - name: ocp-east
            apiUrl: https://api.ocp-east.example.com:6443
            saTokenLookup: true
            enabled: true

Use either `groupsync-dashboard.io/config-type: onboard` or `sideload`; any number of maps may match.
`data.clusters.yaml` must contain only a `clusters` list; `clusters: []` intentionally removes all entries.
Extra data keys, `binaryData`, duplicate YAML keys and malformed YAML are refused. No token, password,
`tokenFile` or `tokenEnv` belongs in this feed. `saTokenLookup: true` is required; `userSelfLogin` is not
implemented here. The host remains values-only. Unknown stanza keys are refused, including `labels`
(the values stanza does not accept it). Custom ConfigMap metadata labels do not become Secret labels.
`insecureSkipVerify: true` is accepted and preserved in the generated Secret.
Use the existing TLS/policy keys; a `caBundleFile` must already exist in the dashboard container and
cover the API and OAuth hosts. The generated Secret is also validated before a login is attempted.

Both feeds share `clusterConfig.secrets.enabled`. Creating, updating or deleting generated Secrets
requires `clusterConfig.secrets.writes.enabled`; ConfigMaps themselves are never written by the app.
The namespace's ConfigMap writers can initiate fleet credential lookups: reserve that permission for
platform operators. The existing fleet account/password and remote token-reader grants still apply.

A name repeated in values and a valid ConfigMap stanza, within one map, across maps, or in an unrelated labelled
Secret loads neither declaration and produces a finding for each. A ConfigMap cannot disable or
replace the values host: host declarations are refused before conflict resolution.
An invalid stanza reserves its name only to hold cleanup; it never blocks a values cluster.
Secret-versus-values precedence outside this feed is unchanged.

Edit or remove the source stanza. Policy and `enabled` edits reuse the credential; connection changes
retire and prune the prior output before another lookup. Confirmed removals (including map deletion,
label removal and UID replacement) repeatedly delete only outputs owned by this generator. History
stays. Failed cleanup remains a finding and is retried, including after restart. Invalid documents
hold their outputs without polling or deleting them; a failed inventory read keeps the prior fleet.

The fleet lookup gates a password in memory (#315). A bound login failure (the password was sent and
no session came back) gates it for that account on every target; the account is the exact username, so
use one spelling per identity. The ConfigMap trigger also marks a successful session (before the token
read), for that target only (#293). A gated password is not sent again in this process, including
after a rename, policy edit, or a later read/write failure. A TLS or connect failure
before the password is written may bind again. Since #285 every login claims the fleet account's Lease
first and records its attempt there before the password is sent; a session clears it and a refusal
replaces it, so a restart, a crash or another replica does not send a refused password again; a
successful session's mark is not on the Lease, so after a restart that trigger may bind once more.
A missing output after that budget was spent stays pending with a finding; fix the
cause and rotate the credential or deliberately restart after checking the account. Routine policy
edits need neither. Do not delete an output as
a way to remove the declaration; the source is the record. Turning discovery off suspends all cleanup;
remove declarations and wait for cleanup before disabling the feed.

What a `clusters[]` entry in `values.yaml` may contain, what each combination does, and what is
refused with which message. **Nothing here is written from reading the source**: every row was
produced by rendering the chart with that stanza (`helm template`) and by loading the same stanza in
the pod's own loader. The script is `local-development/tests/test_cluster_stanza_matrix.py`, which
fails the build if the table below stops being true.

There are four authoring paths: values, a labelled Secret, the Cluster Configurations tab, and
ConfigMap onboarding (above). The values contract follows; Secret differences are in
[§6](#6-the-same-stanza-as-a-secret). A ConfigMap calls the values parser with the additional
remote-only and no-credential boundary described above.

## 1. The keys

Exactly these, and nothing else — an unknown key is refused by name rather than ignored, because a
typo that silently does nothing is how a cluster ends up unpolled with no one the wiser.

| key | type | meaning |
|---|---|---|
| `name` | string, required | the cluster id. **Renaming retires the old cluster** — 33 observation tables key on it, and nothing migrates. No `/`. |
| `apiUrl` | string, required | `http://` or `https://`, trailing slash stripped. No userinfo (`user:password@`), query or fragment (#415): the URL is served to every reader, and httpx sends userinfo as an `Authorization: Basic` header that replaces the bearer token. The refusal names the key, never the value |
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
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster. The password is still the chart's one `passwordSecret`, so name only an account whose password that Secret holds: nothing but a login can check the pairing. A wrong one is refused, and every path stands down while that password is the latest one refused; the Lease keeps one refusal, so rotating away and back can send it again (SPEC_S4e §3.5, #432) |

## 2. The credential — exactly one source

A stanza carries a credential **or** declares a mode that will obtain one. Never both: two sources of
truth for one credential is a stanza whose author meant one of them.

| what the stanza carries | `credential_kind` | polled? |
|---|---|---|
| `tokenFile` = the SA path | `in-cluster` | yes |
| `tokenEnv` or `tokenFile` | `file` | yes |
| `saTokenLookup: true` | `remote-lookup` | **after the lookup** — the dashboard logs in as the fleet account, reads the poller SA's token on the target and writes `gsd-cluster-<name>`, which then polls (SPEC_S4b); needs `clusterConfig.secrets.writes.enabled` |
| `userSelfLogin: true` | `self-login` | **on its own session** — the dashboard logs in as the fleet account on the target and polls with that session, renewed a fixed margin before it expires (SPEC_S4c §3.6); a refused password suspends every self-login cluster on the account. Refused above one replica |
| a Secret's `bearerToken` | `bearer` | yes |
| a Secret's `oauth {username, password}` | `oauth` | **no — pending (#119 P2)** |

A *pending* cluster is listed on the Cluster Configurations tab with the reason, and is **not
polled** — deliberately, so it is never reported as `auth_failed` for a credential that was never
presented. A `self-login` cluster is never pending: with no session it skips the poll, and the finding
says why.

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

Each rendered and loaded. All fourteen are accepted by both readers.

| # | stanza | effect |
|---|---|---|
| 1 | host with `dashboardController: true`, SA token + SA CA | the shipped default |
| 2 | remote + `tokenEnv` | polled, `trusted-bundle` TLS |
| 3 | remote + `tokenFile` | polled, token re-read per use |
| 4 | remote + `tokenEnv` + `caBundleFile` | polled, pinned CA |
| 5 | remote + `tokenEnv` + `insecureSkipVerify` | polled, verification off |
| 6 | remote + `saTokenLookup` | retrieved on the next discovery cycle, then polled through its written Secret; renders only with `clusterConfig.secrets.writes.enabled` |
| 7 | remote + `userSelfLogin` | polled on its own session; renewed a fixed margin before expiry |
| 8 | remote + `saTokenLookup` + `ldapConnectionBootstrap` | as 6, with a per-cluster bootstrap account |
| 9 | remote + `visibility: self-only` | every viewer is the self tier there |
| 10 | remote + `visibility: hidden` | polled, never served through `/api` |
| 11 | remote + `visibility: remote-sar` + `identity: same-as-host` | that cluster's own RBAC decides |
| 12 | remote + `enabled: false` | kept in the config, not polled |
| 13 | remote + `visibility: remote-sar` alone | as 11: `identity` resolves to `same-as-host` |
| 14 | remote + `saTokenLookup` + `visibility: remote-sar` | as 6, and the cluster's own RBAC decides through its written Secret |

A remote that states neither `visibility` nor `identity` — rows 2 to 8 and 12 — resolves to `remote-sar` +
`same-as-host`: once it is polled, its own RBAC decides (SPEC_D2b). One that states only `identity: none` keeps
`self-only`.

## 5. Refusals — measured, and WHERE each one fires

This is the part worth reading twice. Seventeen refusals fail `helm template`, so a bad stanza never
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
| `remote-sar` with `identity: none` | **refused** | refused |
| a `visibility` typo (`self_only`) | **refused** | refused |
| an `identity` typo (`Same-As-Host`) | **refused** | refused |
| `enabled: "yes"` | **refused** | refused |
| `apiUrl` with userinfo (`https://user:password@host`, also `HTTPS://` or padded with whitespace) | **refused** | refused |
| `apiUrl` with a query (`?…`) | **refused** | refused |
| `apiUrl` with a fragment (`#…`) | **refused** | refused |
| **an unknown key** | *renders* | **refused** |
| **a duplicate `name`** | *renders* | **refused** |
| **`apiUrl` without a scheme** | *renders* | **refused** |
| **`insecureSkipVerify` + `caBundleFile`** | *renders* | **refused** |
| `saTokenLookup` without `clusterConfig.secrets.writes.enabled` | **refused** | starts; the tab reports `fleet-write-disabled` (a Secret-declared mode reaches this half) |
| `saTokenLookup` without `clusterConfig.secrets.enabled` | **refused** | starts; the cluster stays pending |
| `clusterConfig.secrets.writes.enabled` with `replicaCount > 1` — a lookup is possible, stanza or not | **refused** | starts; a lookup reports `fleet-write-disabled` (one retriever per estate, SPEC_S4 §6) |
| `userSelfLogin` with `replicaCount > 1` | **refused** | starts; the cluster reports `self-login-suspended` (a session is per process, SPEC_S4c §3.8) |

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
- Once the lookup retrieves a Secret-declared cluster, its `config` keeps an explicit `ldapConnectionBootstrap` beside
  the `bearerToken`: it is the account the daily ping may use (#432). The mode keys leave, and a Secret that named no
  account gains none.

A key name is a place a credential can land, so a refusal repeats a key only when it is one this
contract already knows; anything else is described by its length.

## 7. Worked example

`charts/group-sync-dashboard/example-production.yaml` is a production values file using these
combinations, with the reasoning inline.
