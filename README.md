# group-sync-dashboard Helm repository

This branch is a published artefact, written by
[chart-releaser](https://github.com/helm/chart-releaser-action) from
`.github/workflows/helm.yaml` on `main`. Do not edit it by hand — the next release overwrites it.

```sh
helm repo add group-sync-dashboard https://ephico2real2.github.io/group-sync-dashboard
helm repo update
helm install gsd group-sync-dashboard/group-sync-dashboard
```

The chart source, values reference and docs live on `main`, under `charts/group-sync-dashboard/`.
