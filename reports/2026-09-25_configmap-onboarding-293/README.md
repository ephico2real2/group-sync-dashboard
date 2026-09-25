# #293 on the lab — cluster stanzas from a labelled ConfigMap, 2026-09-25

Walked on the CRC lab (OpenShift 4.22.7) against main `09d5526` (#363; application 0.34.0, chart 0.55.0). It was
deployed with `local-development/release-crc.sh --argocd`: Synced/Healthy, and `09d5526cae` verified in-pod
(`walk/release-tail.log`). The kept PVCs have the same UIDs before and after (`walk/pvc-before.txt`,
`walk/pvc-after.txt`). The script that ran is `walk/proof293.sh`, reading state through `walk/state.py`; its raw output
is `walk/proof.out`. Every number below is quoted from that output.

| File | What it shows |
|---|---|
| `walk/cm-1.yaml` | the ConfigMap applied first: one labelled map, two stanzas |
| `walk/cm-2.yaml` | the same map edited: stanza B removed, a name repeated, a credential in a stanza |
| `screenshots/1-two-generated-clusters.png` | the Cluster Configurations tab after step 1: both generated clusters polling, A with TLS verified, B insecure |
| `screenshots/2-findings-duplicate-and-credential.png` | the findings after step 2: `onboarding-invalid` for the credential stanza, `duplicate-cluster-name` twice |
| `screenshots/3-removed-stanza-secret-deleted.png` | B after its stanza was removed: its Secret deleted, its history kept as a retired row |

## Step 1 — one ConfigMap, two stanzas → two generated Secrets (met after 240 s)

`cluster-onboarding`, labelled `groupsync-dashboard.io/config-type: onboard`, with `data.clusters.yaml` holding:
- `cm-demo-a`: `https://api.crc.testing:6443`, `saTokenLookup: true`;
- `cm-demo-b`: `https://192.168.127.2:6443` (the same cluster by the IP `api.crc.testing` resolves to in the pod),
  `saTokenLookup: true`, `insecureSkipVerify: true`.

Result:
- `gsd-cluster-cm-demo-a` and `gsd-cluster-cm-demo-b` were generated, each with `managed-by: configmap-onboarding`.
- Both clusters polled `ok`, with source `secret:gsd-cluster-cm-demo-*` and `onboarding_configmap: cluster-onboarding`.
- B's Secret carries `tlsClientConfig: {'insecure': True}`: the operator's ruling, end to end.

The log shows exactly **one fleet login per cluster**: `cm-demo-a tls=trusted-bundle`, `cm-demo-b tls=insecure`. Each
session was revoked straight after (`outcome=revoked`), then `cluster-secret-created`, `polling started`, and both
polled 62 groups and 919 binding rows. No person wrote a Secret.

## Step 2 — B removed, a name repeated, a credential in a stanza (met after 300 s)

- **Removal:** `gsd-cluster-cm-demo-b` was deleted. The cluster row stays as `retired: true`, its history kept, and
  `cm-demo-a` stayed `ok`.
- **A repeated name:** `cm-demo-dup` twice in the map gave two `duplicate-cluster-name` findings (sources
  `configmap:cluster-onboarding:1` and `:2`). No Secret was generated: "none loads until the conflict is removed".
- **A credential in a stanza:** the `cm-demo-cred` stanza carrying `bearerToken` gave `onboarding-invalid` ("…no
  credential or token reference…"). No Secret was generated.

## Step 3 — the ConfigMap deleted (met after 280 s)

`gsd-cluster-cm-demo-a` was deleted and both demo clusters are retired. Leftover ConfigMaps or Secrets named
`cluster-onboarding` or `cm-demo`: **none**.

## Known consequence, not a defect

While they existed, the two demo clusters were polled like any cluster, so their history stays in the database as
retired clusters, by the existing keep-history rule. That covers users, groups, bindings, and 317 login events each
(the audit log backfill). The rows age out under the configured retention. Nothing was removed from the PVCs.
