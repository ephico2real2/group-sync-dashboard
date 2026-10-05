# Release 2.0.0 (Epic D) on the lab — the post-release walk, 2026-09-30

**Outcome.** The lab served application 2.0.0 at commit `b40b5cf82a` before and after the walk
(`evidence/before-version.txt` at 09:47:17Z, `evidence/after-version.txt` at 09:51:15Z,
`evidence/p2-after-version.txt` at 09:55:37Z). That is release PR #495's merge commit (`evidence/release-commit.txt`). Both Deployments carried the
label `helm.sh/chart: group-sync-dashboard-0.59.25`, the chart of PR #496 (`evidence/release-commit.txt`; `evidence/before-chart.txt`,
`evidence/after-chart.txt`). Argo CD reported the dashboard Application `Synced` at revision
`eebc2f3647b21bfcbb1fbc68fb5717035e851edf`, which is PR #496's merge (`evidence/before-argo.txt`).

The walker was `developer`, CRC's htpasswd account. It logged in through the route. The e2e walk's main pass passed
84 of 84 steps and its second pass 24 of 24 (`results.json`, `results_extra.json`). All 14 tabs were opened
(`results.json`, step `tab strip`). All 11 reports in the catalogue were generated as PDF and HTML and downloaded
with their JSON. All 11 passed the four-way integrity check, and all 11 PDFs carry the PDF/A marker
(`integrity.jsonl`, `evidence/integrity-check.txt`).

Epic D's own surfaces were read on the Cluster Configurations tab at 1280 px and 375 px
(`evidence/walk-live.txt`). Refresh was pressed once on `mock-privateca`. It answered `unreachable` because the
lab's mock serves no `/version` (finding 2 below). No cluster Secret changed
(`evidence/refresh-mock-privateca.json`).

`epicd.py live` recorded one failed expectation, and that expectation was the walk's own error: it expected
`Refresh: connected`. So `run.sh` exited 1 (`evidence/run-exit.txt`), and the second and third windows exited 0
(`evidence/p2-run-exit.txt`, `evidence/p3-run-exit.txt`). Nothing carrying the label
`walk.gsd.lab/run=release-200-2026-09-30` was left at the end (`evidence/p3-after-label-check.txt`: `No resources
found`).

**The first commit of this folder leaked the fleet account's name in one screenshot.** The orchestrator's OCR read
it in `screenshots/e2e-13-tab-logins.png` and in that image's copy inside `e2e-walk.html`: the mask had covered a
sibling span, not the name. The Logins tab was re-captured with a corrected mask in a third grant window, the
document was rebuilt, and an OCR pass now finds the name 0 times in all 88 PNGs and all 65 embedded images, against
positive controls that find it (see Redaction below).

## Why the grant was taken, and for how long

Without a grant, `developer` is a self-tier reader (`evidence/P-precheck.json`, read at 09:47:25Z):

- `whoami` gave `cluster_admin: false` and host scope `self`.
- The tab bar offered 12 tabs, with neither KPIs nor Cluster Configurations.
- `GET /api/clusterconfigs` answered `403`, `For cluster administrators only. …`.
- The Reports tab painted `Withheld, not empty. … For administrators only.` in place of the catalogue
  (screenshot `screenshots/00-1280-precheck-reports-without-grant.png`).

So the catalogue needed the grant as well as the two cluster-admin tabs. `update clusterrolebindings` is enough for
all three. That verb is the cluster-admin tier's question, and the wide tier consults that tier first
(`local-development/gsd/api.py#_cluster_admin_granted`). With the grant, `whoami` answered `cluster_admin: true` and
host scope `all`, and 14 tabs were offered (`evidence/walk-live.txt`). The grant is
`scripts/grant.yaml`: one ClusterRole with `update` on `clusterrolebindings`, and one ClusterRoleBinding to
`developer`, both labelled.

| Window | Created | Deleted | Seconds | Evidence |
|---|---|---|---|---|
| 1: Epic D pass, e2e main pass, e2e second pass | 09:47:25Z | 09:51:14Z | 229 | `evidence/grant-create.txt`, `evidence/delete-grant.txt` |
| 2: KPIs and Cluster Configurations once painted (finding 1) | 09:54:17Z | 09:55:36Z | 79 | `evidence/p2-grant-create.txt`, `evidence/p2-delete-grant.txt` |
| 3: the Logins tab re-captured with the corrected mask (Redaction) | 10:10:18Z | 10:11:37Z | 79 | `evidence/p3-grant-create.txt`, `evidence/p3-delete-grant.txt` |

The grant stood for 387 s in total (229 + 79 + 79 s, from `evidence/grant-create.txt` and `evidence/delete-grant.txt` and their `p2-` and `p3-` twins; the sum is in `evidence/timeline.txt`). `oc auth can-i update clusterrolebindings --as=developer` answered as follows:

- window 1: `no` at 09:47:19Z, `yes` at 09:48:35Z, `no` at 09:51:15Z (`evidence/before-cani.txt`,
  `evidence/during-cani.txt`, `evidence/after-cani.txt`);
- window 2: `no` at 09:54:16Z, `yes` at 09:55:27Z, `no` at 09:55:36Z (`evidence/p2-before-cani.txt`,
  `evidence/p2-during-cani.txt`, `evidence/p2-after-cani.txt`);
- window 3: `no` at 10:10:17Z, `yes` at 10:11:28Z, `no` at 10:11:37Z (`evidence/p3-before-cani.txt`,
  `evidence/p3-during-cani.txt`, `evidence/p3-after-cani.txt`).

Each login came at least 70 s after the grant was created (`evidence/timeline.txt`). Each run's exit trap found
nothing left to delete (`evidence/trap-delete.txt`, `evidence/p2-trap-delete.txt`, `evidence/p3-trap-delete.txt`:
`No resources found` twice each). Window 3 took the grant because the leaking capture was the wide view the grant
gives, and the replacement had to show the same page.

## Tabs

The e2e main pass opened all 14 tabs at 1440 px in the dark theme (`results.json`). The screenshots are
`screenshots/e2e-04-tab-home.png` to `screenshots/e2e-16-tab-cluster-configurations.png`.

| Tab | Result | Evidence |
|---|---|---|
| Home | **PASS**, heading `What changed last 30 days` | `results.json`, `screenshots/e2e-04-tab-home.png` |
| Overview | **PASS**, heading `dashboard` | `screenshots/e2e-05-tab-overview.png` |
| KPIs | **PASS** once painted, 1.6 s after the click: `System status`, `Access posture`, `Trends`, `Clusters`. The e2e capture shows `Loading…` (finding 1). | `evidence/tabs-painted.json`, `screenshots/11-1440-tab-kpis-painted.png` |
| Groups | **PASS**, `Groups · 66 shown` | `screenshots/e2e-07-tab-groups.png` |
| Users | **PASS**, `Users · 61 shown` | `screenshots/e2e-08-tab-users.png` |
| Access granted | **PASS**, first heading `Dangling · 0` | `screenshots/e2e-09-tab-access-granted.png` |
| RBAC policy | **PASS** | `screenshots/e2e-10-tab-rbac-policy.png` |
| Kyverno | **PASS**, `Kyverno · the CEL policy family` | `screenshots/e2e-11-tab-kyverno.png` |
| Namespace audit | **PASS** | `screenshots/e2e-12-tab-namespace-audit.png` |
| Logins | **PASS**, `Login attempts`. The screenshot is the 10:11Z re-capture (Redaction). | `results.json`, `evidence/walk-recapture-logins.txt`, `screenshots/e2e-13-tab-logins.png` |
| Usage | **PASS**, `Dashboard usage` | `screenshots/e2e-14-tab-usage.png` |
| Reports | **PASS**: 11 reports in the catalogue, 11 enabled, PDF on, variant `pdf/a-2b` | `screenshots/e2e-21-reports-catalogue.png` |
| Library | **PASS**, `Library 57 runs · 3 schedules · 1 paused` | `screenshots/e2e-15-tab-library.png` |
| Cluster Configurations | **PASS** once painted, 1.2 s after the click: `Cluster Configurations 38 clusters`. The e2e capture shows `Loading…` (finding 1). | `evidence/tabs-painted.json`, `screenshots/12-1440-tab-cluster-configurations-painted.png` |

The lookup steps passed too (`results.json`):

- `demo` found `Groups · 6 of 66 / Namespaces · 7 of 118`.
- The drill opened `demo-prod`.
- The Groups also-line read `also matching demo: 7 namespaces — see all matches`.
- At 375 px the page did not scroll sideways.

The screenshots are `screenshots/e2e-17-lookup-demo.png` to `screenshots/e2e-20-lookup-375.png`.

The second pass (`results_extra.json`) switched the Overview to `mock-privateca`
(`screenshots/extra-04-overview-cluster-mock-privateca.png`). It captured the light theme
(`screenshots/extra-09-overview-light-theme.png`) and opened each downloaded HTML report in Chromium
(`screenshots/extra-10-*` to `screenshots/extra-20-*`). Its `Reports tab on mock-privateca` step recorded
`no report form`, with the page text in its detail, as a recorded step and not a check.

## Reports

Each report ran with the parameters `local-development/e2e-walk/e2e_capture.py#required_params` gives: the namespaces
`group-sync-dashboard,openshift-monitoring` for namespace-access, and a campaign, a due date and the reviewer
`developer` for access-certification (`results.json`). Every run finished `done`, with formats `html` and `pdf`.

| Report | Generated in | sha256 (first 16) | Integrity (4 ways + PDF/A) | Artefacts committed |
|---|---|---|---|---|
| namespace-access | 4.8 s | `23585c079be7181a` | **PASS** | PDF, HTML, JSON |
| access-matrix | 5.1 s | `18d77b30685e4d45` | **PASS** | no: names the fleet account |
| privileged-access | 3.5 s | `a4c01a9e82cbba8c` | **PASS** | PDF, HTML, JSON |
| binding-findings | 6.7 s | `f1bc63e15dd25829` | **PASS** | no: names the fleet account |
| groups | 8.3 s | `4d861f9ab7e3e6a8` | **PASS** | no: names the fleet account |
| users | 5.0 s | `e7497030b5c58b1c` | **PASS** | no: names the fleet account |
| login-activity | 3.3 s | `df1e95b0301a3a69` | **PASS** | PDF, HTML, JSON |
| dormant-access | 3.3 s | `12f9998e2d7a920d` | **PASS** | no: names the fleet account |
| groupsync-health | 3.3 s | `e486dd5a307ea0d5` | **PASS** | PDF, HTML, JSON |
| compliance-snapshot | 3.3 s | `f3c82817d9d0750a` | **PASS** | PDF, HTML, JSON |
| access-certification | 8.5 s | `e4fe971b203001f9` | **PASS** | no: names the fleet account |

The times and hashes come from `results.json`, each report's `generate` step. The integrity rows come from
`integrity.jsonl`: `recomputed_matches`, `run_matches`, `sha_in_pdf_metadata`, `sha_in_html` and `pdfa_marker` are
all `true` for all 11. The integrity check ran on all 11 before any file was left out. The first page of every PDF
rendered (`results_extra.json`, `pdf_page1`: 11 of 11). None of those first pages names the fleet account, so all
11 are committed (`screenshots/pdf-page1-*.png`). The Recent runs table recorded `1 runs listed of 68`
(`results.json`, `screenshots/e2e-44-reports-recent-runs.png`).

## Epic D on the Cluster Configurations tab

Read with the page's own fetch and the painted cards (`evidence/walk-live.txt`, `evidence/clusterconfigs-1280.json`,
`evidence/cards-1280.json`, `evidence/cards-375.json`):

| Surface | Result | Evidence |
|---|---|---|
| The shared-API-URL banner | **PASS**. The API's `warnings` held one entry, code `shared-api-url`, clusters `shared-qa` and `shared-rnd`. The page painted one banner: `⚠️ Shared API URL. shared-qa, shared-rnd declare the same API URL: https://api.crc.testing:6443. Each entry is still polled and counted on its own.` Both cards carry the `shared API URL` chip. At 375 px the same banner is painted. | `evidence/clusterconfigs-1280.json`, `evidence/cards-1280.json`, `evidence/tabs-painted.json`, `evidence/cards-375.json`, `screenshots/01-1280-head-and-banner.png`, `screenshots/08-375-head-and-banner.png` |
| `mock-privateca`, the TLS row (caData, reachable) | **PASS**: the green `verified` chip, `ca: caData`, `store secret:gsd-cluster-mock-privateca/tlsClientConfig.caData · 1 certificate CN=mock-privateca-root · issuer CN=mock-privateca-root · 2031-09-19T16:54:01Z`. The expiry equals the API's `trust.certificates[].notAfter`. | `evidence/cards-1280.json`, `evidence/clusterconfigs-1280.json`, `screenshots/02-1280-mock-privateca-card.png`, `screenshots/09-375-mock-privateca-card.png` |
| `mock-selfsigned`, the TLS row | **PASS**: the chips are exactly `insecure` (`badge warning`), at 1280 px and at 375 px | `evidence/cards-1280.json`, `evidence/cards-375.json`, `screenshots/03-1280-mock-selfsigned-card.png`, `screenshots/10-375-mock-selfsigned-card.png` |
| `mock-trusted`, `shared-rnd`, `shared-qa` (recorded only) | `verified`, `ca: trusted-bundle`, `store /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt · 152 certificates`. `shared-qa` was read and photographed, never clicked. | `evidence/walk-live.txt`, `screenshots/04-1280-mock-trusted-card.png`, `screenshots/05-1280-shared-rnd-card.png`, `screenshots/06-1280-shared-qa-card.png` |
| Refresh, pressed once on `mock-privateca` | **Recorded**. It answered `Refresh: unreachable · 2026-09-30T09:48:46Z — HTTP 404 on /version: {"detail":"Not Found"}` on its own card. One POST was sent, and the route guard blocked no other write. Every cluster Secret kept its resourceVersion across the press, read at 09:48:46Z before and after: `gsd-cluster-mock-privateca` stayed at `995049` and `gsd-cluster-shared-qa` at `2981054`. The pod logged one `cluster-refreshed cluster=mock-privateca credential=bearer by=developer outcome=unreachable` line and 0 `fleet-login` lines. The walk expected `connected`, and that expectation was wrong (finding 2). | `evidence/refresh-mock-privateca.json`, `evidence/after-podlog.txt`, `screenshots/07-1280-mock-privateca-after-refresh.png` |
| 375 px | **PASS**: `scrollWidth 375 = innerWidth 375` | `evidence/cards-375.json` |
| Rejoin | Not pressed, as the brief says. The route guard would have aborted it. | `scripts/epicd.py` |

The header counts 38 clusters, and the retired rows `w244-exp`, `w244-fail` and `w492-fail` (throwaways of earlier walks) are among them. They are
history from those walks and were not read here (`evidence/clusterconfigs-1280.json`, `retired`; the count is in `evidence/tabs-painted.json`).

## Findings

`findings.json` holds the same three notes for the walk document. No product defect was found.

1. **The e2e tool photographed KPIs and Cluster Configurations while they were loading.** Both tab steps passed
   on their heading. Both captures show the card reading `Loading…`, 900 px tall
   (`screenshots/e2e-06-tab-kpis.png`, `screenshots/e2e-16-tab-cluster-configurations.png`).
   `local-development/e2e-walk/e2e_capture.py#walk_tabs` waits for any `h2` plus 700 ms, and the loading card has an
   `h2`. The second window's `scripts/tabs_loaded.py` waited for `Loading…` to leave `#main`: 1.6 s for KPIs and
   1.2 s for Cluster Configurations (`evidence/tabs-painted.json`). This is a gap in the walk tool, not in the
   product. Not changed here.
2. **Refresh on `mock-privateca` answers `unreachable`, because the mock serves no `/version`.**
   `local-development/gsd/clusterconfig/writer.py#_probe` asks `/version` first. The mock app registers no such
   route (`local-development/mock-app/mock_app/app.py`). The 2026-09-28 walk recorded the same answer on all three
   mocks (`reports/2026-09-28_batch-1110-walk/evidence/walk-output.txt`). The card above the answer still shows the last poll's
   `verified` chip and `ok · reachable`. That is the split the runbook describes since #496: the card's connection
   row and TLS chip are the last poll's, not Refresh's (`charts/group-sync-dashboard/docs/RUNBOOK.md`, section 1).
3. **Six of the eleven reports name the fleet account, so their artefacts are not committed.** On this lab the
   fleet account is a real user, so users, groups, access-matrix, access-certification, binding-findings and
   dormant-access list it. Their PDF, HTML and JSON are left out, and `integrity.jsonl` keeps their hashes and
   verdicts. Every screenshot masks the account wherever the page named it:
   - `evidence/mask-log.jsonl` records the walk's 77 screenshots in its first 77 lines;
   - on 32 of them the page's text named the account;
   - each of those 32 had at least one masked element;
   - one of those masks missed the name itself (Redaction below).

## Before and after

| What | Before | After | Evidence |
|---|---|---|---|
| `/api/version` | `2.0.0`, `b40b5cf82a` | the same, three times | `evidence/before-version.txt`, `evidence/after-version.txt`, `evidence/p2-after-version.txt`, `evidence/p3-after-version.txt` |
| Chart label on both Deployments | `group-sync-dashboard-0.59.25` | the same | `evidence/before-chart.txt`, `evidence/after-chart.txt` |
| Dashboard pod | `group-sync-dashboard-7b9485f499-66q2z`, started 09:38:21Z, restarts `0,0` | the same | `evidence/before-pod.txt`, `evidence/after-pod.txt` |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` | the same | `evidence/before-pvcs.txt`, `evidence/after-pvcs.txt`, `evidence/p2-after-pvcs.txt`, `evidence/p3-after-pvcs.txt` |
| `gsd-cluster-shared-qa` | resourceVersion `2981054` | `2981054` | `evidence/before-sharedqa.txt`, `evidence/after-sharedqa.txt`, `evidence/p2-after-sharedqa.txt`, `evidence/p3-after-sharedqa.txt` |
| Every cluster Secret | six, resourceVersions as listed | the same six, the same resourceVersions | `evidence/before-secrets.txt`, `evidence/after-secrets.txt`, `evidence/p2-after-secrets.txt`, `evidence/p3-after-secrets.txt` |
| Fleet Lease | one, resourceVersion `7043788`, holder `""` | the same | `evidence/before-lease.txt`, `evidence/after-lease.txt`, `evidence/p2-after-lease.txt`, `evidence/p3-after-lease.txt` |
| Argo CD Application | `Synced`, `Degraded`, `eebc2f3647b21bfcbb1fbc68fb5717035e851edf` | the same | `evidence/before-argo.txt`, `evidence/after-argo.txt`, `evidence/p2-after-argo.txt`, `evidence/p3-after-argo.txt` |
| Anything labelled `walk.gsd.lab/run=release-200-2026-09-30` | `No resources found` | `No resources found`, four times | `evidence/before-label-check.txt`, `evidence/after-label-check.txt`, `evidence/p2-after-label-check.txt`, `evidence/end-label-check.txt`, `evidence/p3-after-label-check.txt` |

**Argo CD's `Degraded` is known and was only recorded.** The only resource that is not Healthy is the CronJob
`group-sync-dashboard-report-nightly-namespace-access`, with `CronJob has not completed its last execution
successfully` (`evidence/before-argo.txt`). Its last schedule was 2026-09-30T02:00:00Z and its last success
2026-09-29T02:00:11Z (`evidence/before-cronjob.txt`). That run's Job failed with `DeadlineExceeded`, "Job was active longer than specified deadline", at 02:15:01Z
(`evidence/cronjob-failed-run.txt`, read in the review of #497); why it ran past its deadline is not measured here. Its schedule is `0 22 * * *` America/New_York.

The pod log was read for each window (`evidence/after-podlog.txt`, from 09:47:17Z, 172 lines;
`evidence/p2-after-podlog.txt`, 43 lines; `evidence/p3-after-podlog.txt`, 39 lines). Each held 0 `fleet-lookup`, `fleet-ping`, `fleet-login`,
`fleet-login-refused`, `fleet-login-failed` and `fleet-logout` lines. Each also held 0 lines naming the fleet
account, 0 `Traceback` lines and 0 lines containing `ERROR`. The first window has the one `cluster-refreshed` line.

`env.json` has an empty `chart` because `local-development/e2e-walk/env_facts.sh` reads `helm list`, and Argo CD
owns this release, not Helm. The chart is the Deployment label above. It records OpenShift 4.22.7, node `crc` at
`9643m (81%)` CPU requests, and 0 preemptions (`env.json`).

## What is here

- `README.md`: this file.
- `e2e-walk.html`: the walk document, built by `local-development/e2e-walk/build_doc.py`, with 65 of the captures
  embedded as JPEG. It was rebuilt after the Logins re-capture from this folder's own files, laid out as the tool
  reads a run: `results.json`, `results_extra.json`, `integrity.jsonl`, `env.json`, `findings.json`, the screenshots
  under their captured names, and `artefacts/` as the run's `reports/`. So its "Files delivered" table lists the 15
  committed artefacts, where the first build listed all 33 downloads. The PDF copy is not committed.
- `results.json`, `results_extra.json`, `integrity.jsonl`, `env.json`, `findings.json`: the e2e tools' outputs.
  Rows passed `scripts/e2e_masked.py`'s cleaner before they were written.
- `artefacts/`: 15 files, the PDF, HTML and JSON of the five reports that do not name the fleet account.
- `screenshots/`: 88 PNGs, all full resolution:
  - `00-*` to `12-*`: the precheck, the Epic D pass and the painted tabs;
  - `e2e-NN-*`: the e2e main pass, 44 files;
  - `extra-NN-*`: the second pass, 20 files;
  - `pdf-page1-*`: 11 files.

  `evidence/mask-log.jsonl` names the main and second-pass shots `e2e/NN-*` and `extra/NN-*`, as they were
  captured; they were renamed on copy. Its last four lines are the window-3 re-capture: its three login pages, which
  are not committed, and the new `e2e/13-tab-logins.png`.
- `evidence/`: the captures named above, the walkers' output and the timeline.
- `scripts/`:
  - `run.sh`, `run2.sh` and `run3.sh`: the three windows;
  - `epicd.py`: the precheck and the Epic D pass;
  - `e2e_masked.py`: runs the repo's `e2e_capture.py` and `e2e_extra.py` with the fleet mask and the cleaner;
  - `tabs_loaded.py`: the painted tabs;
  - `recapture_logins.py`: the Logins re-capture;
  - `ocr-redaction.sh`: the OCR redaction check;
  - `mask_fix_offline.py`: the offline proof of the corrected mask;
  - `capture.sh`: the read-only captures, including `redaction`;
  - `grant.yaml`: the grant.

  They were adapted from `reports/2026-09-30_chip-492-walk/README.md`'s scripts and
  `reports/2026-09-28_batch-1110-walk/README.md`'s Refresh helper.

## Redaction

Tokens, passwords, `sha256~` values and the fleet account's name must not be in this folder. CA subjects, dates and
fingerprints are public PKI and are kept.

- **Text.** `evidence/end-redaction.txt` counts 0 files with a `sha256~` value and 0 files naming the fleet account.
  It also counts 0 of the 5 committed PDFs naming it in their extracted text.
- **Pixels: what went wrong.** A text grep cannot read a screenshot. In the first commit, the Logins capture showed
  the name in the "Allowed to log in, holds no access" table. That row is
  `<td class="mono">NAME <span class="muted">· FULL NAME</span></td>`
  (`local-development/gsd/static/index.html`), and the full name also contains the account. `get_by_text` returns
  the smallest element whose text matches, so it masked only the span. The mask covered x 362–564, and the name,
  from x 167 to 355, stayed readable.
- **The fix.** `scripts/e2e_masked.py` now also draws an opaque box over the client rects of every matched substring
  of every text node (`TEXT_BOXES_JS`), whatever element holds it. `mask-log.jsonl` counts those boxes as
  `text_boxes`.
- **What it still does not cover (reviews of #497, Grok and Codex).** A name split across elements (the Lookup
  highlighter's `<mark>` around part of it) or held in an `<input>`/`<textarea>` value is not boxed. This folder is not
  affected — the OCR check below reads every PNG and embedded image — and the script stays the one that produced it;
  the gap is the walk tooling's to close, and the OCR check stays the gate.
- **Proved offline first.** `scripts/mask_fix_offline.py` puts a copy of that markup, with a made-up name, below the
  fold of a local page, outside the repo. OCR read the name once in the old mask's capture and 0 times in the new
  one's (`evidence/mask-fix-offline.txt`).
- **The re-capture.** The Logins tab was re-captured with the fix in window 3, at 10:11:37Z
  (`evidence/walk-recapture-logins.txt`; `mask-log.jsonl`'s last line: 1 element and 2 text boxes). The new PNG
  replaced `screenshots/e2e-13-tab-logins.png`, and `e2e-walk.html` was rebuilt so its embedded copy is the
  re-captured one. Nothing was painted by hand.
- **The pixel check.** `scripts/ocr-redaction.sh` runs macOS Vision OCR over every PNG in the folder and every image
  embedded in `e2e-walk.html`. It counts the recognised lines naming the account, by its full name or its middle
  fragment, in any case. `evidence/ocr-redaction.txt` has the result:
  - 88 PNGs: 0 lines;
  - 65 embedded images: 0 lines;
  - positive controls, kept outside the repo and deleted afterwards: the original leaking PNG and its embedded
    copy from the first commit's `e2e-walk.html` each hit once.
- **Epic D and painted-tab captures.** `epicd.py` and `tabs_loaded.py` still mask by element only. The OCR pass
  finds 0 lines on their 13 captures as well.

## How to repeat

```sh
GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_release-2.0.0-walk/scripts/run.sh
GSD_WALK_TMP=<the same directory> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_release-2.0.0-walk/scripts/run2.sh
GSD_WALK_TMP=<the same directory> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_release-2.0.0-walk/scripts/capture.sh redaction end   # after the README is written
OCR=<a macOS Vision OCR binary> GSD_WALK_TMP=<the same directory> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_release-2.0.0-walk/scripts/ocr-redaction.sh [<positive-control image> ...]
```

The e2e run's raw output lands in `$GSD_WALK_TMP/e2e`, and the committed files are copied from there.
