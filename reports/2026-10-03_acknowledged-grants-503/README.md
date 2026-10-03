# Acknowledged direct grants on the CRC lab: the SPEC_G3 §5 walk (#503)

Walked 2026-10-03, 14:04 to 14:08 UTC, on CRC (OpenShift 4.22.7), after PR #558 merged as `aecc1c0564`
(application 3.3.0, chart 0.66.1), by `scripts/run.sh`. It exited 0.

- **Why the walk deployed an older commit.** Argo CD deployed #558 before the walk began. So the walk pointed the
  Application at `lab/g3-before-walk`, a branch on `983df2ff` (main just before #558, application 3.2.0), for the
  "before" reads. It then pointed it back at `main` for the "after" reads. The branch is deleted.
- **Where the reads come from.** They are the dashboard's own, through the pod's loopback: `dana.lee`
  (`cluster-reader`, the wide tier) for the numbers, and `developer` (the self tier) for §5 step 5.
- **The records.** `walk.log` is the run. `reads-corrected.log` holds three reads repeated after it, because the
  walk's `jq` named fields the answer does not have (`name`, `namespace`, `user`), and its metric pattern missed the
  alert series' `severity` label. Same lab, same revision, right names.

## Before and after

| Read (as `dana.lee`, cluster `dashboard`) | Before (3.2.0) | After (3.3.0) | SPEC_G3 §5 |
|---|---|---|---|
| `total` (direct user grants) | 11 | 9 | 11 → 9 |
| `excluded_platform` | 24 | 24 | 24, unchanged |
| `acknowledged` | `null` (the field is new) | 2 | 2 |
| the acknowledged rows | — | both `ocp-oauth-bind-serviceid`, `managed_source` `group-sync-operator-helm`: the ClusterRoleBinding `group-sync-dashboard-cluster-poller`, and the RoleBinding `group-sync-dashboard-cluster-poller-token-reader` in `group-sync-operator` (`reads-corrected.log`) | both naming `ocp-oauth-bind-serviceid`, `group-sync-operator-helm` |
| the alert's subject | "11 direct user grants" | "9 direct user grants" | 11 → 9 |
| `cluster_wide_grants` | 3 | 2 | 3 → 2 |
| `platform_with_findings` | 2 | 1 (`openshift-console-user-settings` keeps its two console grants) | 2 → 1 |
| `group-sync-operator`'s `direct_grants` | 1 | 0 | 1 → 0 |
| `gsd_alerts_total{cluster="dashboard",kind="direct_user_binding"}` | not captured (the walk's pattern missed the `severity` label) | 1.0 (`reads-corrected.log`) | still 1.0 |
| `gsd_bindings_total{finding="unmanaged"}` on `dashboard`, `shared-rnd`, `shared-qa` | 57, 57, 57 | 57, 57, 57 | unchanged |

- **The unmanaged series.** It is unchanged, as §5 says: the acknowledged grants remain unmanaged findings, and only
  the direct-user view and alert count them apart. The spec's absolute value (53) is from 2026-10-01, and the lab has
  gained bindings since.
- **The self tier (§5 step 5).** As `developer`, at 14:08:54Z, after its 70 s tier cache expired following the
  screenshot grant's delete:
  - `scope` `self`, `total` 1: `developer`'s own console RoleBinding
    `user-settings-d46d9fe1-…-rolebinding` in `openshift-console-user-settings`;
  - `acknowledged`, `acknowledged_bindings` and `acknowledged_truncated` all `null`.

  The walk's own self read, at 14:06:33Z before any grant existed, gave the same `scope`, `total` and `null`s.

## The page

`scripts/shots.py` captured the Namespace audit tab on `dashboard`, with the acknowledged disclosure closed and open,
at 375, 768 and 1280 px, light and dark: 12 files, `screenshots/nsaudit-acknowledged-<state>-<width>-<theme>.png`.
- On every open capture, `aria-expanded` is `true` and the table has its 2 rows. On every closed one it is `false`.
- `scrollWidth - clientWidth` is 0 on all 12, and there were no page errors.
- They were taken as `developer` under a short labelled grant (`scripts/grant.yaml`, `list` and `update` on
  clusterrolebindings), created after every read so that it is in no number, and deleted after. The spec names
  `dana.lee`, but that account's UI password is in no seed.

## After

- The Application is on `main` at `aecc1c05`, Synced and Healthy.
- The grant is deleted, and nothing carries the run's label.
- The PVC UIDs are unchanged:
  - data `f065b7a4-535c-4ef1-868c-58f5afee4953`
  - report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`
  - offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`

## Redaction

The screenshots show the lab's seeded user names. Nothing is masked. macOS Vision OCR of the 12 PNGs recognised
550 lines:
- 8 lines match `password|token|sha256~`. Every one is part of the resource name
  `group-sync-dashboard-cluster-poller-token-reader`, the Role and RoleBinding the page lists; none is a credential.
- No line contains `sha256~` or `password`.
- The positive control, `ocp-oauth-bind`, is found 4 times.
