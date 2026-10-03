# Release 4.0.0 (Epic G) on the lab: the post-release e2e walk, 2026-10-03

**Outcome.** The lab served application 4.0.0 at commit `15613ccb95` (release PR #564), with Argo CD Synced and
Healthy at main `94f5ebbb`, before and after the walk (`evidence/run.log`).
- **The main pass passed 84 of 84 steps** (`results.json`): the login path, all 14 tabs, the lookup, the Reports
  catalogue, and each of the 11 reports' form and status.
- **The second pass passed 24 of 24** (`extra/results_extra.json`).
- **All 11 reports were generated, downloaded and checked** as PDF, HTML and JSON (`reports/`: 11 of each). All 11
  passed the integrity check (`integrity.jsonl`): the recomputed sha256 equals the JSON's field, the run record and
  the PDF metadata, and the HTML and PDF/A markers are present.
- **The 4.0.0 surfaces** were captured view-only by `scripts/surfaces_400.py` (`surfaces-400.json`, all ok):
  - the Library's Clean up card (#542);
  - a run drawer offering "Delete this run", not pressed (#542);
  - the KPI page's Database copies card (#542);
  - the Namespace audit tab's acknowledged grants, opened, 2 rows (#503);
  - its platform identities note (#255).
- **Read with `oc` after the walk:**
  - `group-sync-dashboard-recovery` is at 0 replicas (#532);
  - the Role `group-sync-dashboard-leases` holds the Lease rule, and the ClusterRole has 0 Lease rules (#420);
  - the PVC UIDs are unchanged.

The walk document is `doc/e2e_walk.html`. Its PDF was sent to the operator and is not committed (the operator's rule
for walk documents).

## How it ran

- **Who walked.** The walker was `developer`, CRC's htpasswd account, logged in through the route.
- **The grant.** It walked under a labelled grant, `scripts/grant.yaml`: `update clusterrolebindings`, the
  cluster-admin tier, which the wide tier also consults. Created at 20:08:17Z, deleted after 227 s. The exit trap
  found nothing left carrying `walk.gsd.lab/run=release-400-e2e-2026-10-03`, and `can-i` then answered `no`.
- **The tools.** `scripts/run.sh` drove the repository's `local-development/e2e-walk/run_walk.sh` (capture, second
  pass, integrity, env facts, document) and `scripts/surfaces_400.py`. Both read the UI password from the
  environment only.
- **Run 1 did not walk.** It stopped before the main pass: `run_walk.sh` needs the venv under its own repository, and
  the worktree has none (`evidence/run1-no-venv.log`). Run 2 called the tool from the main checkout, on the same
  commit with identical e2e tools.

## What the walk did not establish

- **The precheck.** The no-grant precheck read `developer` as `scope: all, cluster_admin: true`. That reading came 27 s
  after run 1's grant was deleted, inside the dashboard's 70 s tier cache, so it does not show what `developer` gets
  without a grant. The 2026-09-30 walk records that properly.
- **The Overview capture.** `05-tab-overview.png` caught the GroupSync CRs section while it still read "Loading…". The
  step passed; the capture came before that section painted.

## Redaction

The screenshots show the lab's seeded user names, and nothing is masked. The fleet account's name is not treated as
sensitive, per the operator's ruling of 2026-09-30. macOS Vision OCR of all 80 PNGs recognised 15,272 lines
(`evidence/ocr-all.txt`):
- 0 contain `sha256~`;
- 5 contain "password", every one of them a label or help text: the login form's "Password *" field (three captures)
  and the Logins tab's explanation of LDAP bind results (two lines);
- the positive control, "Overview", is found 45 times.

## What is here

| Path | Contents |
|---|---|
| `NN-*.png` (44) | the main pass, in step order |
| `extra/` | the second pass: the second cluster, the light theme, every HTML report opened, page 1 of every PDF |
| `screenshots/s400-*.png` (5) | the 4.0.0 surfaces |
| `reports/` (33) | each report's `.pdf`, `.html` and `.json`, downloaded through the page |
| `results.json`, `extra/results_extra.json`, `integrity.jsonl`, `env.json`, `surfaces-400.json` | the walk's own records |
| `doc/e2e_walk.html` | the walk document |
| `evidence/` | `run.log` (the facts, the grant, the 4.0.0 objects), both tools' output, the OCR text, run 1's log |
| `scripts/` | `run.sh`, `surfaces_400.py`, `grant.yaml` |
