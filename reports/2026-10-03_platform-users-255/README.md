# Platform users per estate on the CRC lab: the SPEC_G2 §5 walk (#255)

Walked 2026-10-03, 05:55 to 06:22 UTC, on CRC (OpenShift 4.22.7), after PR #556 merged as `8fd1180c5a`
(application 3.2.0, chart 0.66.0), by `scripts/run.sh`. Its record is `walk.log`, and it exited 0.

- **How it changed the lab.** Only the lab's values file changed. Three walk commits on `lab/g2-platform-users-walk`
  (never merged, deleted at the end) reached Argo CD through `release-crc.sh --argocd`. Each one rolled the dashboard
  pod through its `checksum/config`.
- **Where the numbers come from.** They are the dashboard's own:
  - `GET /api/clusters/dashboard/user-bindings`, read through the pod's loopback as `developer`, which passed the
    wide tier under the walk's labelled grant (`scripts/grant.yaml`: `list` and `update` on clusterrolebindings);
  - the poller's refresh line;
  - the public `/metrics`.

## The numbers

| Stage | Refresh line | `total` | `excluded_platform` | `platform_users_unmatched` | unmanaged (`/metrics`) |
|---|---|---|---|---|---|
| Before: the 3.2.0 pod's startup refresh, 05:57:27Z | 35 bindings, 11 naming a person | 11 | 24 | `{}` | 57 |
| Add `tmp-contractor-9931` | 36, 11 | 11 | **25** | `{}` | 57 |
| Stale `ghost-9931` beside it | 36, 11 | 11 | 25 | **`{"additionalNames": ["ghost-9931"]}`** | 57 |
| Removed (values back to the merge's) | 36, 12 | 12 | 24 | `{}` | 58 |
| The grant gone, pod restarted (`grant-measured-out.log`) | 35, 11 | — | — | — | 57 |

**Reading the table: the walk's own grant is in the last four rows.**
- **Why.** The grant is a direct ClusterRoleBinding to the user `developer`. It was created after the 3.2.0 pod's
  startup refresh (05:57:27Z), so "before" does not count it. Every later stage started a new pod, whose startup
  refresh does: 36 bindings, not 35. Bindings refresh hourly (`bindingIntervalSeconds: 3600`) and at each pod start.
- **The confirmation.** With the grant deleted, a pod restart read 35 / 11 / 57 again, the "before" numbers
  (`grant-measured-out.log`).
- **Against the grant-inclusive baseline** (12 naming a person, unmanaged 58), the walk shows exactly what SPEC_G2 §5
  predicts:
  - **Add:** one person fewer (11), one platform identity more (25), one unmanaged fewer (57), nothing stale.
  - **Stale:** `ghost-9931` named in `platform_users_unmatched`, and the three numbers unmoved.
  - **Remove:** 12, 24 and 58, the baseline again.
- **The spec's predicted absolutes** (total 11 → 10, unmanaged 53 → 52) were measured on 2026-10-01. The lab has since
  gained bindings (unmanaged 57 before this walk), and §5 says the dashboard's own numbers are the ones recorded.

## The page

`scripts/shots.py` captured the Namespace audit tab on `dashboard` during the stale stage, as `developer`, at 375, 768
and 1280 px, light and dark (`screenshots/nsaudit-platform-users-<width>-<theme>.png`). On all six:
- the estate note is present: "… the shipped defaults, plus this estate's `platformUsers.additionalNames`";
- the ⚠ line is present: "`additionalNames`: `ghost-9931` is not currently matched by any User subject on a binding
  in this cluster";
- `scrollWidth - clientWidth` = 0;
- there were no page errors.

## After

- The Application is back on `main` at `8fd1180c`, Synced and Healthy.
- The walk branch is deleted, the grant is deleted, and nothing carries the run's label.
- The PVC UIDs are unchanged:
  - data `f065b7a4-535c-4ef1-868c-58f5afee4953`
  - report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`
  - offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`

## Redaction

The screenshots show the lab's seeded user names (`developer`, `jdoe`, `asmith` and others). Nothing is masked.
macOS Vision OCR of the six PNGs recognised 278 lines:
- 0 match `password|token|sha256~`;
- the positive control, `ghost-9931`, is found 6 times.
