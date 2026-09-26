# #389 on the lab — the onboarding example applied and removed, 2026-09-26

The committed example `examples/cluster-onboarding/configmap.yaml` was applied to the CRC lab with `oc apply`. Only
three values were changed, to make it a throwaway that the lab can reach (`cm.yaml`):
- the map's name, to `cluster-onboarding-389`;
- the cluster's name, to `gitops-example-389`;
- `apiUrl`, to `https://api.crc.testing:6443`.

The dashboard ran image `group-sync-dashboard:0.36.0-667b3c4a62` (the lab's Argo CD `targetRevision`), with
`discoveryIntervalSeconds: 300` and `clusterSecretsWritesEnabled: true`, read from the release's ConfigMap. The example
files are not in the image; what is measured here is that the committed example works against the shipped reader.

| File | What it holds |
|---|---|
| `cm.yaml` | the ConfigMap applied |
| `step1-created.out` | the generated Secret's annotations and the dashboard's log lines for the cluster; the revoked session's token hash is redacted |
| `step2-deleted.out` | the delete, the time to the prune, the log lines, and the PVC comparison |
| `pvc-before.txt`, `pvc-after.txt` | the kept PVCs' UIDs before the apply and after the delete |

## Step 1 — applied at 16:49:44Z; the Secret was generated 286 s later

- `gsd-cluster-gitops-example-389` was created at 16:54:37Z. Its annotations: `managed-by: configmap-onboarding`,
  `source-configmap: cluster-onboarding-389`, `lookup-account: ocp-oauth-bind-serviceid`.
- The log shows one fleet login (`tls=trusted-bundle`), then the session revoked (`outcome=revoked`),
  `cluster-secret-created … by=sa-token-lookup`, `polling started`, and 61 users recorded.
- 286 s is within one 300 s discovery interval.

## Step 2 — deleted at 16:54:54Z; the Secret was pruned 287 s later

- `cluster-secret-deleted secret=gsd-cluster-gitops-example-389 … by=configmap-onboarding` at 12:59:37 (local time,
  UTC−4), then `removed=gitops-example-389`, then "its Secret is gone; the poll thread stops (history kept)".
- `oc get secret gsd-cluster-gitops-example-389` returned NotFound.
- The PVC UIDs are unchanged: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.

The retired cluster row `gitops-example-389` stays in the lab database as history, as #293's cleanup rule states.
