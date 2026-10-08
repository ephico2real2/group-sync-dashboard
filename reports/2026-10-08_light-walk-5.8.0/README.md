# The dashboard in the light theme, application 5.8.0 on the lab: 2026-10-08

**Outcome.** A full walk of the deployed dashboard captured in the **light** theme, for the documentation and the
introduction deck, which until now had light captures of only a few screens (the 5.0.0 walk captured every tab in
dark). The lab served application 5.8.0, and Argo CD read Synced and Healthy at main `e262c8e5` before the walk.

- **The main pass passed 84 of 84 steps** (`results.json`, theme `light`): the login path, every tab, the lookup, the
  Reports catalogue, and each of the 11 reports' form and status.
- **The second pass passed 24 of 24** (`extra/results_extra.json`): the second cluster, the HTML reports opened in
  Chromium, page one of every PDF.
- **All 11 reports were generated, downloaded and checked** as PDF, HTML and JSON (`reports/`: 11 of each). All 11
  passed the integrity check (`integrity.jsonl`). Each report's JSON names report service 5.8.0 at commit
  `665b73347b`, not dirty, snapshot schema 20.
- **The PVC UIDs were unchanged** before and after: data `f065b7a4-…`, report-artifacts `08c7d45c-…`, offsite
  `7f505595-…`.

## How it was run

`local-development/e2e-walk/e2e_capture.py` with `--theme light` (the runner, `run_walk.sh`, does not pass a theme,
so its stages were run one by one), then `e2e_extra.py`, `integrity_check.py` and `env_facts.sh`. The walk document
was built and kept on the machine that ran it, as the folder convention says.

## Redaction

Nothing is masked: the account name is not sensitive (the operator's ruling of 2026-09-30). macOS Vision OCR read
**7,028 lines** from the **75 PNGs** (`evidence/ocr-all.txt`, list in `evidence/pngs.txt`):

- 0 lines contain `sha256~` (no OpenShift token);
- the 3 lines naming a password are the login form's field label, `Password *`;
- `v5.8.0` appears 37 times, in the header of the dashboard captures.

## What is here

| Path | Contents |
|---|---|
| `01-…44-*.png` | the main pass, light theme, full page at 1440 px wide, full resolution |
| `extra/` | the second pass: the second cluster, the HTML reports, page one of each PDF |
| `reports/` | the 11 reports as PDF/A, HTML and JSON, as the report service wrote them |
| `results.json`, `extra/results_extra.json`, `integrity.jsonl`, `env.json` | every step's verdict, the integrity checks, the cluster facts |
| `evidence/` | the run logs and the OCR output |

Some captures are full-page and tall (Logins 13,525 px, Cluster Configurations 15,138 px). They are kept whole as
evidence; a slide or a document uses a screen-sized view of the part it shows.
