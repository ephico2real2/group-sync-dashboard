# #293 on the lab — cluster stanzas from a labelled ConfigMap, 2026-09-25

Walked on the CRC lab against `09d5526cae`, #363's merge commit (`git log`), running as image `0.34.0-09d5526cae`
with chart version 0.55.0 (`charts/group-sync-dashboard/Chart.yaml` at that commit). It was deployed with
`local-development/release-crc.sh --argocd`: Synced/Healthy, and `09d5526cae` verified in-pod
(`walk/release-tail.log`). The kept PVCs have the same UIDs before and after (`walk/pvc-before.txt`,
`walk/pvc-after.txt`).

The script that ran is `walk/proof293.sh`, reading state through `walk/state.py`; its raw output is `walk/proof.out`.
- Every number below is quoted from that output.
- The stanza fields (label, URLs, `saTokenLookup`, `insecureSkipVerify`) are quoted from `walk/cm-1.yaml` and
  `walk/cm-2.yaml`.
- What `cm-demo-b`'s URL points at is measured in `walk/resolve.out`.
- The screenshots are crops of the two full-page captures `walk/shots.sh` wrote.

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
- `cm-demo-b`: `https://192.168.127.2:6443`, `saTokenLookup: true`, `insecureSkipVerify: true`. `walk/resolve.out`
  shows it is the address `api.crc.testing` resolves to inside the dashboard pod, the same cluster by another
  target.

Result:
- `gsd-cluster-cm-demo-a` and `gsd-cluster-cm-demo-b` were generated, each with `managed-by: configmap-onboarding`.
- Both clusters polled `ok`, with source `secret:gsd-cluster-cm-demo-*` and `onboarding_configmap: cluster-onboarding`.
- B's Secret carries `tlsClientConfig: {'insecure': True}`. That is #363's rule: `insecureSkipVerify` is accepted in a
  ConfigMap stanza and kept in the generated Secret.

The log shows exactly **one fleet login per cluster**: `cm-demo-a tls=trusted-bundle`, `cm-demo-b tls=insecure`. Each
session was revoked straight after (`outcome=revoked`), then `cluster-secret-created`, `polling started`, and both
polled 62 groups and 919 binding rows. The Secrets were written by the dashboard's lookup (`by=sa-token-lookup` on
`cluster-secret-created`). The proof applied only the ConfigMap bodies in `walk/`.

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

## What remains after cleanup

The first poll of each demo cluster recorded 61 users, 62 groups, 919 binding subject rows and 317 login events
(`walk/proof.out`, the `cm-demo-a` / `cm-demo-b` poller and audit-log lines). After cleanup both demo clusters remain in
the state dump as `retired: true`, with their history kept. The kept PVCs have the same UIDs before and after.
