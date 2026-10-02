# The KPI page's Backups card on the CRC lab — the SPEC_E6 §5 walk (#306)

Walked 2026-10-02 04:33–04:36 UTC on CRC (OpenShift 4.22.7), after PR #526 merged as `c57f2927`. The lab's Argo CD
Application was `Synced`/`Healthy` on that revision before and after; the dashboard pod (started 04:23:57Z) reports
application `2.3.0`, commit `c57f292707`. Nothing was deployed by this walk. The full record is `walk.log`, written
by `scripts/run.sh`.

The walker is `developer`, CRC's htpasswd account. The KPI page is cluster-admin tier only (`update
clusterrolebindings`), so the KPI step ran under a temporary, labelled grant (`scripts/grant.yaml`). The method is
the one in `reports/2026-09-30_release-2.0.0-walk/scripts/run.sh`:

- the grant is created with `oc create -f`;
- the walk waits 70 s for the tier's cache, then logs in;
- the grant is deleted, and an exit trap deletes anything still carrying the run's label;
- `can-i` is checked: `no` → `yes` → `no`.

The grant was created at 04:33:38Z and deleted at 04:35:02Z, so it was held 84 s.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | Before | `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953`, `group-sync-dashboard-report-artifacts` `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`. The ConfigMap reads `backupDir: "/data/backup"`, `backupIntervalHours: 6`, `backupKeep: 4`, `replicaCount: 1`. There are four copies in `/data/backup`; the newest is `gsd-20261002T042438.581853Z.db` (00:24:39 EDT), taken after the 2.3.0 pod started |
| 2 | The KPI page as a cluster-admin persona | `developer` had `cluster_admin: true` and was offered the KPIs tab. The page's cards, in order: System status, **Backups**, Access posture, Trends, Clusters. Heading: `on-volume · /data/backup · every 6 h · keep 4`. State: `healthy`, "last copy 2026-10-02 00:24:39 EDT; next due by 2026-10-02 06:24:39 EDT". Tiles: Last copy `00:24:39 EDT`; Copies kept `4/4`, `55Mi on the data volume` (the four files sum to 57,163,776 bytes, as the payload's `bytes`); Failures `0`, `since start 2026-10-02 00:24:04 EDT`; schema `20/20`; Pre-upgrade copy `none`. At 375, 768 and 1280 px, light and dark: the page's `scrollWidth == clientWidth` (375/375, 768/768, 1280/1280), the card's too (333/333, 726/726, 1138/1138), and no page error |
| 3 | T306-17, within the same minute | The card read at 04:34:54Z. `/metrics` was read in the pod (127.0.0.1:8080) and through the route 3.8 s later; the two agree. `[data-kpi="backup-last"] time[datetime]` = `2026-10-02T04:24:39Z` = `gsd_backup_last_success_timestamp_seconds 1.7909150792085342e+09`, truncated to the second in UTC. The Failures tile `0` = `gsd_backup_failures_total 0.0` |
| 4 | The schema and the pre-upgrade tile | 64 bytes of the newest copy by mtime (`oc exec … python3.14 -c`): the magic is `SQLite format 3\0`, offset 60 reads `20`, and the schema tile reads `20/20`. That file's mtime `1790915079.2085342` is the metric's value. `/data/pre-upgrade` exists and is empty (`[]`), the payload's `pre_upgrade` is `null`, and the tile reads `none` |
| 5 | Nothing else moved | T306-15: `git diff --name-only 53efb10b c57f2927 -- charts/` names only `charts/group-sync-dashboard/Chart.yaml`, and its changed lines are `version` 0.61.0 → 0.61.1 and `appVersion` 2.2.0 → 2.3.0 with their history comments. RBAC: `helm template` of both revisions with `-f environments/crc.yaml -f <the Application's valuesObject>` gives 44 objects each; `rbac_rules.py` gives 65 rules before and 65 after, `REMOVED 0`, `ADDED 0`. Beyond the chart and version labels and the checksums, the rendered lines that differ are seven image tags (2.2.0 → 2.3.0) and the offsite bind Job's name. That name carries a hash of the chart version and the image, by design (`templates/backup-offsite.yaml`). **Not observed:** §5's "/metrics family names before and after the deploy". The deploy happened before this walk and the mandate forbids another; T306-14 covers it in the unit suite |
| 6 | The disabled state | The browser harness's, not the lab's: the lab keeps backups on. `pytest tests/test_ui.py -k 'test_t306_8 or test_t306_13' --browser chromium` at `c57f2927` → `2 passed, 655 deselected in 2.64s` |
| 7 | After | The two UIDs of step 1, unchanged. The offsite claim `7f505595-db2e-40be-a4ee-c6ed271c42b6` is unchanged too. Argo CD is still `Synced`/`Healthy` on `c57f2927`, and the same pod has 0 restarts |
| — | The lower tier | After the grant's delete and another 70 s, `developer` had `cluster_admin: false` and was not offered the KPIs tab. `#page=kpi` renders the refusal card ("KPIs — Withheld, not empty … For administrators only."), with no Backups card. `GET /api/kpi` on the session answers `403` |

At the end, `oc auth can-i update clusterrolebindings --as=developer` answers `no`, and nothing carries the label
`walk.gsd.lab/run=kpi-backups-306-2026-10-02`.

## Two runs

`walk-run1.log` is the first run, 04:30–04:32 UTC. It had the same grant method: created 04:30:17Z, deleted
04:31:37Z, held 80 s, `can-i` `no` at the end. It stopped in step 4 on a defect in `walk.py`, not in the product:
the header read's fields were indexed one place off, so "offset 60" was compared against the mtime (`IndexError`
after a false `FAIL`). The values it logged before stopping are the same as run 2's. The card, the payload and both
`/metrics` reads agreed (`2026-10-02T04:24:39Z`, failures `0`), and the copy's offset 60 printed `20`. Its
lower-tier screenshot was overwritten by run 2's. `walk.log` is run 2, with the index fixed. The only other change
between the runs is that the context screenshot is clipped in page coordinates.

## Screenshots

- `screenshots/kpi-system-status-and-backups-1280-light.png` — the card below System status, 1280 px light
- `screenshots/kpi-backups-{375,768,1280}-{light,dark}.png` — the card alone, at each width and theme
- `screenshots/kpi-refused-developer-1280-light.png` — the lower tier's KPI page, after the grant was deleted

The screenshots show the logged-in user name `developer`. Nothing is masked. `tesseract` is not installed. Instead,
every PNG was OCR'd with macOS Vision (`VNRecognizeTextRequest`, the binary the 2026-09-30 walks used):

- 242 lines were recognised across the eight files;
- 0 lines match `password|token|sha256~`;
- the positive control, `healthy`, is found 7 times.

`walk.log`, `walk-run1.log` and `scripts/` hold no `sha256~` value. The only matches for `password` and `token` are
the environment variable's name and the redaction code.

A fixed-string search for the password's value was not used as evidence, because on CRC's default credentials that
value is not distinctive.

## Observed, outside #306

The System status card shows both components on `watch`:

- dashboard: throttled 16.36 % of periods, and the node disk 83 % full;
- report: the node disk 83 % full.

This is the lab's state (`crc status`: 132.8 GB of 160.5 GB in the VM). It is not something the Backups card
changed.
