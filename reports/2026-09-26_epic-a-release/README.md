# Epic A (#381) released and deployed — chart 0.58.3, 2026-09-26

Chart 0.58.3 (release PR #402, merge `2b2c744`) was published by `helm.yaml` at 19:12:57Z and deployed to the CRC lab
with `local-development/release-crc.sh --argocd main`: the chart at `main` and the published image. Argo CD reported
**Synced/Healthy** at 19:14:46Z (`walk/release-tail.log`). The dashboard runs `group-sync-dashboard-0.58.3` with
`quay.io/ephico2real/group-sync-dashboard:0.36.0` (`walk/walk.out`). The kept PVCs have the same UIDs before and after
(`walk/pvc-before.txt`, `walk/pvc-after.txt`).

The walk (`walk/walk.sh`, output `walk/walk.out`) added a cluster through the committed GitOps example
(`examples/cluster-onboarding/configmap.yaml`, #389) and removed it again, capturing the Cluster Configurations tab
each time. Three values were changed to make it a throwaway the lab can reach (`walk/cm.yaml`): the map's name
(`cluster-onboarding-epic-a`), the cluster's name (`gitops-example-389`) and `apiUrl` (`https://api.crc.testing:6443`).
It also captured the docs index (#319) as GitHub renders it at `2b2c744`.

| Screenshot | What it shows |
|---|---|
| `screenshots/1-before-retired-card.png` | Before the apply: `gitops-example-389` is already a **disabled** row, "its Secret is gone — the history is kept, the cluster is disabled", last reachable 16:59. That row is the retired cluster from #389's own lab check (`reports/2026-09-26_gitops-examples-389/`). |
| `screenshots/2a-page-top-gitops-cluster-active.png` | The top of the tab while the GitOps cluster is active: 22 clusters, the ConfigMap selector `groupsync-dashboard.io/config-type in (onboard,sideload)`, and the version `v0.36.0 · 667b3c4a62`. **By source** reads `ConfigMap 0` (see the finding below). |
| `screenshots/2b-gitops-cluster-card.png` | The cluster added by the example: **enabled**; its credential "managed by ConfigMap cluster-onboarding-epic-a — edit the stanza there"; TLS **verified** (`ca: trusted-bundle`); connection **ok**, reachable 19:19; and "declared in ConfigMap cluster-onboarding-epic-a — remove the stanza there; its Secret is cleaned up automatically". |
| `screenshots/3-after-removal-card.png` | After the ConfigMap was deleted: **disabled** again, "its Secret is gone — the history is kept", last reachable 19:24. |
| `screenshots/4-docs-index.png` | `docs/README.md` (#319) at `2b2c744`: operator guides first, then development records by kind. GitHub's sticky header clips the page's top edge in the capture. |

## Timings (`walk/walk.out`)

- Applied at 19:15:06Z; the generated Secret existed 257 s later, annotated `managed-by: configmap-onboarding`.
- Deleted at 19:19:52Z; the Secret was gone 272 s later.
- Both are within one 300 s discovery interval.

## Finding: the "by source" count misses a ConfigMap-declared cluster once its Secret exists

While `gitops-example-389` was active and declared by the ConfigMap, the header read `ConfigMap 0`, and the cluster
was counted under `Secret`. The count comes from `ccSourceKind` in `local-development/gsd/static/index.html`, which
reads the cluster's current `source`. After the lookup writes the Secret, the source is `secret:gsd-cluster-…`
(`cluster-resolved … source=secret:gsd-cluster-gitops-example-389` in #389's lab log). The card's own chip says
`Secret gsd-cluster-gitops-example-389` while its credential line says "managed by ConfigMap". Filed as #404
(Epic D); this release does not change it.
