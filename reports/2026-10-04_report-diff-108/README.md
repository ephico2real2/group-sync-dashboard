# #108 on the lab: report-diff runs, 2026-10-04

**Outcome.** The lab served application 4.3.0, deployed by Argo CD from main (PR #579, merged at `79c24a8e`; SPEC_F3).
Both of #108's checks passed, through the page's "Diff vs…" action on the Report history (`walk.log`, as `developer`
under a labelled grant during each page step).
- **Over the same data, "No change"** (phase 1):
  - Two `namespace-access` runs of `demo-qa` by `dana.lee`, five seconds apart: `…032332…-06ea` (A) and
    `…032337…-8a16` (B). Both sealed `be5b69f70586…`.
  - "Diff vs…" on B pre-selected A, the newest earlier finished run. The diff `20261004T032457.350234Z-2c21` read
    `{"blocks_changed": 0, "rows_added": 0, "rows_removed": 0}`.
- **A planted RoleBinding, exactly** (phase 2):
  - At 03:25:02Z the walk planted `walk-108-planted-view` in `demo-qa`: the synced group
    `app-ocp-rbac-demo-ns-admin` → ClusterRole `view` (`scripts/planted.yaml`).
  - The dashboard's binding refresh counted it at 04:20:23Z: `gsd_bindings_total{finding="unmanaged"}` went 58 → 59.
  - After one snapshot interval, a third run C (`…042556…-5f49`) was diffed against B. "Diff vs…" pre-selected B.
  - The diff `20261004T042719.705865Z-d981` showed two changed blocks:
    - the binding added: `UNMANAGED — synced group granted by hand, no policy operator source`,
      `app-ocp-rbac-demo-ns-admin`, `ClusterRole/view`, `walk-108-planted-view`;
    - the namespace's Findings count moved: `unmanaged: 0` removed, `unmanaged: 1` added, under the same key.

    Nothing else changed.
  - The binding was removed at 04:27:23Z. `demo-qa` holds its five original bindings again.
- **Clean-up and integrity:**
  - The grant existed only during the two page steps. Afterwards `can-i` answered `no`, and nothing labelled
    `walk.gsd.lab/run=report-diff-108-2026-10-04` remained.
  - No page errors in either phase.
  - PVC UIDs were unchanged.
  - Argo CD read Synced and Healthy at the end.

## Redaction

macOS Vision OCR of the 4 PNGs recognised 539 lines (`evidence/ocr-all.txt`): 0 contain `sha256~` and 0 contain
"password". The positive control, "Report", is found 8 times. `walk.log` names the password only as its placeholder
(`GSD_UI_PASSWORD=<from crc console --credentials>`). The report ticket went to the report pod on stdin only.

| Path | Contents |
|---|---|
| `screenshots/` (4) | each phase: the picker with the base pre-selected, and the finished diff with its downloads |
| `artefacts/` (2) | each diff's `.json`, downloaded through the page |
| `walk.log` | each command and its output: the facts, the runs, the grant, the plant, the refresh, the clean-up |
| `evidence/ocr-all.txt` | the OCR text |
| `scripts/` | `run.sh`, `walk.py`, `in_pod.py`, `grant.yaml`, `planted.yaml` |
