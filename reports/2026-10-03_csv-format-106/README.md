# #106 on the lab: CSV as a report format, 2026-10-03

**Outcome.** The lab served application 4.2.0, deployed by Argo CD from main at `50f89fb4` (PR #575, SPEC_F2). With
`csv` added to the lab's `reporting.formats.scheduled` (PR #576, at `43b231b6`), both of #106's checks passed.

- **A manual run through the page** (`walk.log`, run 2, as `developer` under a labelled grant, `groups` on
  `dashboard`):
  - **The form:** the CSV box is there and unticked. Ticking CSV, unticking PDF and flipping the rosters switch
    leaves the boxes as set (the review's T106-10, live). Generate posted `["html", "csv"]`.
  - **The download:** the run `20261004T000846.573126Z-6d8e` finished with a "Download .csv" button, and the page
    downloaded `artefacts/gsd_dashboard_groups_20261004T000846Z.csv` (17,136 bytes).
  - **The file:**
    - the UTF-8 BOM first, and 224 CRLF-ended records that Python's `csv` module reads;
    - `Report,Groups and membership changes`, then `sha256 of the report data,2b277b5e…`, equal to the run record;
    - page one marked `not sealed: states the run`, and the other four sections sealed;
    - four tables (Groups, Empty groups, Unattributed groups, Changes).
  - **The Library:** the card offers `.csv`.
  - **At 375 px:** no sideways scroll, and no page errors.
- **A scheduled run** (`scheduled.log`):
  - At 02:00:55Z, inside the night window, one Job was created from the CronJob `quarterly-compliance`. The schedule
    fanned out to the six clusters. All six runs are `done`, and each holds `report.csv`, `report.html`,
    `report.json` and `run.json`, with CSVs of 3,469–4,465 bytes. The Job was deleted afterwards.
- **The same snapshot, the same hash.** Run 1 (00:07:01Z) and run 2 (00:08:46Z) over one snapshot sealed the same
  sha256, `2b277b5e…`: #270's data-only seal at work.
- **PVC UIDs** were unchanged before and after both checks.

## Run 1

Run 1 (`evidence/walk-run1.log`, `evidence/run1/`) passed every check up to the download. It then stopped at the
Library step on a defect in the walk script, not the product: the script built a CSS `#id` selector from a run id
that contains a `.`. The script now uses an attribute selector. The grant was removed by the script, and `can-i`
then answered `no`.

## Found by the walk

The Generate button reads "Generate PDF · HTML · JSON" whatever boxes are ticked
(`screenshots/03-run-done-download-csv-1280.png`). Filed as #577.

## Redaction

macOS Vision OCR of the 10 PNGs recognised 939 lines (`evidence/ocr-all.txt`): 0 contain `sha256~` and 0 contain
"password". The positive control, "Reports", is found 12 times. The logs contain neither. The UI password went to
the walk through its environment only.

| Path | Contents |
|---|---|
| `screenshots/` (5) | run 2: the form unticked and ticked, the finished run, the Library card, the form at 375 px |
| `artefacts/` | the CSV run 2 downloaded through the page |
| `walk.log`, `scheduled.log` | each command and its output: the facts, the grant, the walk, the Job, the run records, the clean-up |
| `evidence/` | run 1's log, screenshots and CSV; the OCR text |
| `scripts/` | `run.sh`, `walk.py`, `grant.yaml`, `scheduled.sh` |
