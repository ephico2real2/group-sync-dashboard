# Deleting reports and database copies from the page on the CRC lab — the SPEC_H1 §5 walk (#542)

Walked 2026-10-03 00:12–00:15 UTC on CRC (OpenShift 4.22.7), after PR #547 merged as `4e44fd02eb`.

- **The deploy.** The lab's Argo CD Application synced that revision; it reported `Synced`/`Healthy` before and after.
  The dashboard pod started at 00:10:09Z and reports application `3.1.0`, commit `4e44fd02eb`, with
  `features.housekeeping: true`. Nothing was deployed by this walk.
- **Where the record is.** `walk.log` is the full record, written by `scripts/run.sh`. `audit-lines.log` holds the audit
  lines (see "The record" below).
- **Who walked.** The walker is `developer`, CRC's htpasswd account. Deletion is cluster-admin tier only (`update
  clusterrolebindings`), so the admin steps ran under a temporary, labelled grant (`scripts/grant.yaml`). The method is
  `reports/2026-10-02_kpi-backups-306/scripts/run.sh`'s:
  - the grant was created at 00:12:13Z and deleted at 00:13:40Z, so it was held 87 s;
  - `can-i` read `no` → `yes` → `no`;
  - the exit trap found nothing left carrying the label.
- **What deleted.** The deletions were made by the product, through its page's own buttons. The only cluster writes
  by the walk itself were the grant's create and delete.

| Step | SPEC_H1 §5 | Result |
|---|---|---|
| Before | The facts | PVCs: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, offsite `7f505595-db2e-40be-a4ee-c6ed271c42b6`. `gsd_housekeeping_deleted_total` is 0 for all four kinds. The dashboard ConfigMap reads `housekeepingEnabled: true`, and the report pod has `GSD_REPORT_HOUSEKEEPING_ENABLED=true`. |
| RBAC | Nothing added or removed | Rendered with `environments/crc.yaml`, `4e44fd02^1` against `4e44fd02`: REMOVED 0, ADDED 0. |
| 1 | Delete one manual run from the Library drawer | `20260930T094935.837962Z-90e1` (cluster `dashboard`), two presses of **Delete this run**. The page notes "Run 20260930T094935.837962Z-90e1 deleted.", and its directory is gone from `/artifacts`. |
| 2 | Preview, then confirm, the retired schedule's cleanup | Scope `schedule nightly-namespace-access`, older than 0 days, keep the newest 0. The preview listed 70 runs (1.8 MB), and all 70 were still in `/artifacts` after it. After **Delete these 70 runs** the page notes "Deleted 70 runs, 1.8 MB.", and 0 runs of that schedule are left. |
| 3 | Delete one `pre-restore` copy from the KPI page | The oldest unguarded one, `pre-upgrade-20261002T012959.076526Z-schema-20-to-21-…db` (14,270,623 bytes; the walk-only schema-21 copy from #302's walk). Two presses; it is gone from the listing. |
| 4 | The newest backup is kept | `backup/gsd-20261003T001042.559760Z.db` has no button, and `DELETE /api/housekeeping/copies/backup/…` answers 409 with the guard's sentence. |
| 5 | Below the tier | After the grant's delete and 70 s, `developer` has `cluster_admin: false`. `GET /api/housekeeping/copies` and a cleanup `POST` both answer 403: "For cluster administrators only. Deleting reports and database copies is reserved to cluster administrators." The Library offers no delete and no cleanup. |
| 6 | The record | 72 audit lines: 71 `report-run-deleted` and 1 `db-copy-deleted`, each with `by=developer`. The counter after: `report-run` 71, `pre-restore` 1, `backup` 0, `pre-upgrade` 0. The 70 schedule lines sum to 1,927,540 bytes, which the page rounds to 1.8 MB. |
| After | The facts | The same three PVC UIDs. Argo CD is still `Synced`/`Healthy` on `4e44fd02`, and `can-i` reads `no`. |

## The record

`walk.log`'s step 6 printed the count (72) but not the lines themselves. Its display command used `sed -E
's/^(.{0,400}).*/\1/'`, and BSD `sed` refuses a repetition above 255 ("RE error: maximum repetition exceeds 255").
`scripts/run.sh` now uses `cut -c1-400`, and was changed after the run. The lines were then captured from the same pod
into `audit-lines.log`, with its command first.

## Before the walk: a deploy held by Argo CD

PR #547's `publish` succeeded, but the lab kept running 3.0.0. After the CRC reboot, the Application showed `Unknown`
with `ComparisonError … unable to resolve parseableType … Route`:
- the application controller had been restarted at 21:31Z;
- the `v1.route.openshift.io` APIService last became Available at 22:34:11Z, so the controller was running without
  the Route schema;
- its last sync operation was still `2d20d0fb`.

A restart after 22:34Z cleared it, and 3.1.0 was running at 00:11:08Z.

## Screenshots

| File | What it shows |
|---|---|
| `screenshots/library-drawer-confirm-1280.png` | The run drawer's two-step delete, at "Confirm delete" |
| `screenshots/library-cleanup-preview-1280.png` | The Clean up card's preview: 70 runs, 1.8 MB, one confirm button |
| `screenshots/library-cleanup-done-1280.png` | After the confirm |
| `screenshots/kpi-database-copies-1280.png` | The Database copies card: the newest backup and the newest pre-restore set marked "kept" with their reasons, no button on either |
| `screenshots/kpi-database-copies-375.png` | The same card at 375 px |
| `screenshots/library-refused-developer-1280.png` | The lower tier's Library, after the grant's delete |

The screenshots show the logged-in user name `developer`. Nothing is masked.

- **OCR check.** Every PNG was OCR'd with macOS Vision (`VNRecognizeTextRequest`, the binary earlier walks used):
  - 340 lines were recognised across the six files;
  - 0 lines match `password|token|sha256~`;
  - the positive control, `delete`, is found 18 times.
- **Text check.** `walk.log`, `audit-lines.log` and `scripts/` hold no `sha256~` value.

## Seen on the walk, filed separately

At 375 px the page does not overflow (`scrollWidth - clientWidth` = 0). The copies table scrolls inside its card,
though, so the Delete buttons are off to the right on a phone. At 1280 px, the card's directory line and its cleanup
form sit flush against the card's left edge, without the table's padding. Neither blocks #542; both are
filed as #548.
