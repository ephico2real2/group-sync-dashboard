# The Tech debt sweep on the lab: application 4.7.0, chart 0.70.0, 2026-10-04

**Outcome.** The lab ran application 4.7.0, which Argo CD deployed from main at `1d008176` (PR #603). Argo CD read
Synced and Healthy, and the dashboard reported version 4.7.0, commit `1d0081766c`. `scripts/run.sh` exited 0, and
`walk.py` recorded no failure and no page error. The PVC UIDs were the same before and after. The walk's temporary
grant was removed: `can-i` reads `no`, and nothing carries its label.

## What each issue shows

### #594: scheduled reports refuse PDF
- **The chart at `1d008176`:**
  - `reporting.formats.scheduled`, a schedule's `formats` and `deliver.attach` each fail to render (exit 1), each with
    the sentence "scheduled reports store html, json or csv; PDF is for manual runs — print the HTML for a paper or
    PDF copy".
  - `reporting.formats.manual={html,json,pdf}` renders (exit 0).
- **The lab:**
  - The report pod has `GSD_REPORT_FORMATS_SCHEDULED=html,json,csv` and `GSD_REPORT_FORMATS_MANUAL=html,json,pdf`.
  - None of the five CronJobs names `pdf`. The one that delivers attaches `html`.

### #555: recovery mode's wait
The deployed recovery ConfigMap creates the pipe and the wakeup descriptor at lines 190-192, waits with
`select.select([wakeup_fd], …)` at line 179, and restores the earlier descriptor at line 200. The recovery Deployment
is at 0 replicas. The timing proof is the CI probe on the issue: 0 timeouts in 3,600 repetitions.

### #585: cron month and day names, in the deployed report pod
- `MON-FRI`, `jan,Jul` and `sun` read the same as `1-5`, `1,7` and `0`.
- `MON/2` and `1/2` both give Monday, Wednesday and Friday. This is the review fix: before it, both included Sunday.
- `FUNDAY` is refused: "day-of-week: cannot read 'FUNDAY'".

### #588: a reversed diff is refused
A diff whose base (`…081750…-2e06`) is newer than its head (`…052833…-c0f5`) got **422**, with "base … is newer than
head …: a diff compares an earlier run with a later one". The run count was 40 before and 40 after.

### #589: "Data as of" is no longer in the sealed Campaign section
One real access-certification run, `20261004T092414.302620Z-57eb`, made by `dana.lee` through the report service.
- Its Campaign section is sealed and holds Campaign, Due, Reviewer, Scope and Cluster, with no "Data as of" row.
- Page one, "Provenance and coverage", is not sealed and still shows "Data as of".
- The first pass of this walk made one more run from the same snapshot, `…092146.707529Z-1626`. Both have sha256
  `4c238cdf…`, because the seal covers the data only.

### #587, #577, #546, #548: through the page, as `developer`
- **#587:** the Reports description reads "(PDF pdf/a-2b, HTML, CSV, and JSON)" (`01`).
- **#577:** the walk ticked and unticked each of the PDF, HTML and CSV boxes in turn, and then all three together.
  After every change, the Generate label named exactly the ticked boxes plus JSON. With every box off, it read "JSON".
  Screenshot `02` shows "Generate CSV · JSON" with only CSV ticked. Nothing was generated.
- **#546:** at 375 px, the Backups heading fits its card (`scrollWidth` 333 = `clientWidth` 333) (`03`). The lab's
  directory is the short `/data/backup`, so the long-path case rests on the browser test,
  `test_backups_long_directory_heading_fits_375px`.
- **#548:** at 375 px, the Database copies card lists 10 copies, 8 with Delete and 2 with their kept reason.
  - Every row's action sits inside the viewport, and nothing scrolls sideways.
  - The note, the policy text and the cleanup form sit inside the card's padding (`04`).
  - Nothing was clicked, and no copy was deleted.

### Evidence elsewhere
**#590, #543, #591, #545 and #535** change names, CI checks, a walk option and docs. Their evidence is in their tests
and in CI on PR #603. #535's cosign measurement is on its issue.

## Redaction
macOS Vision OCR of the 4 PNGs recognised 242 lines (`evidence/ocr-all.txt`). None contains `sha256~`, "password" or
"token". The positive control, "Database copies", is found once. `walk.log` names the password only as its placeholder,
and holds no `sha256~` and no ticket. The ticket reached the report pod on stdin only.

## First pass
The walk ran twice; this folder holds the second run. The first also exited 0, with every check passing, but its
evidence fell short in two places, so `run.sh` and `walk.py` were corrected and run again:
- **The CronJob read:** it looked at each container's `args`, which are null here. The trigger's flags are in
  `command`, which `run.sh` now reads.
- **The Backups screenshot:** it was scrolled so the heading sat at the bottom edge. The walk now captures the Backups
  card itself.

| Path | Contents |
|---|---|
| `walk.log` | each command and its output |
| `screenshots/` | `01` Reports description, `02` Generate label, `03` Backups card at 375 px, `04` Database copies at 375 px |
| `evidence/ocr-all.txt` | the OCR text |
| `scripts/` | `run.sh`, `walk.py` (browser), `in_pod.py` (report pod), `grant.yaml` (the labelled temporary grant) |

To repeat: `KUBECONFIG=<the lab kubeconfig> scripts/run.sh`.
