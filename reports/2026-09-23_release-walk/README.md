# The 2026-09-23 release, walked — main @ `7f1856a920`, then `e3b3731b78`

Walked 2026-09-23 against the CRC lab (OpenShift 4.22.7), deployed through `local-development/release-crc.sh
--argocd`: Argo CD Application `group-sync-dashboard` at `targetRevision=7f1856a920`, Synced/Healthy, image
`0.31.0-7f1856a920`, the commit verified in-pod. `7f1856a920` is main after eight merges that day: #331 (a test
race), #324 (the Namespace audit mock), #325 (SPEC S4c), and #326–#330 (#261 parts 2 and 3, and two defects the
review found). After #333 (#332, below) the same path redeployed `e3b3731b78`, also verified in-pod.

## Outcome

| What | Result |
|---|---|
| main walk — login through the route, the 14-tab strip (13 opened; Reports is exercised by the report steps), the lookup, 11 reports × generate + `.pdf`/`.html`/`.json` | **84 / 84** steps |
| second pass — the other cluster, the light theme, every HTML report opened | **24 / 24** steps, plus page 1 of each PDF rendered: **11 / 11** |
| integrity — per report, the recomputed sha256 = the JSON's field = the run record = the PDF metadata; the HTML prefix; the PDF/A marker | **11 / 11** reports |
| the release's own changes — `validate_release.py` | **15 / 15** checks |

The first run of the walk failed one step (80/81): the namespace-access report was refused with *"select at least
one namespace, by selector, mnemonic or explicit name"*. That was the walk, not the product: since #143/#149 the
report's `namespaces` parameter is a picker inside the form's Advanced section, and `e2e_capture.py` skipped a
parameter whose text field it could not find and submitted the form empty. The walk now drives the picker and fails
on a missing control (this PR); the numbers above are the re-run against the same deployment. The first run's
results are not in this folder — `findings.json` keeps the note.

## What the release changed, checked on the deployed page

`validate_release.py` logs in through the route with the walk's own login and step recording
(`local-development/e2e-walk/e2e_capture.py`) and records each check with its screenshot in
`results_release.json` (run against `7f1856a920`). Three of those checks proved less than they claimed — #320
accepted the oauth-proxy's `session` row, #330 counted rows across every table, #328 recorded the tile's presence
but not its value — so they were measured again precisely (`measurements.json`), the script was corrected, and the
corrected script was re-run against `7e68a93565`: **15 / 15**, in `results_release_7e68a93.json`.

| Change | On the lab's data |
|---|---|
| #320 — login capture from the oauth-server audit log, the default source | every route login is stored as a `credential` row (the OAuth form) then a `session` row (the oauth-proxy, ~15 ms later), `source=audit-log`, read from the store: four logins at 16:52:28, 16:53:21, 16:53:28 and 16:53:42Z. No Debug level anywhere. |
| #326 — the platform line names a hidden namespace that still holds a finding | *"67 platform namespaces hidden — 1 of them has a direct grant. This hides rows, never findings: `openshift-console-user-settings` is still ranked in Exposure by namespace above."* |
| #327 — the cluster scope is its own card; the worklist drills | "Cluster-wide direct grants · 3" above the worklist; 4 worklist namespaces, 4 drills, the first opens its page |
| #328 — the reach becomes a tile and a disclosure | `legacy-payments`: the tile reads **53** (`results_release_7e68a93.json`), the toggle `aria-expanded` false → true, 16 subjects listed |
| #329 — names separated; the scope note | the copied text reads `asmith · bwilliams · jdoe`; the note shows while Find namespace holds a query and goes with Escape |
| #330 — the risk tint on even rows; index-row ids | 3 High rows on even rows of their table, all tinted (measured per `tbody`, the scope of the CSS's `nth-child`); index drills carry `ns-row-<name>` |

`dashboard` and `shared-rnd` are the same CRC, declared twice on purpose to exercise the remote-cluster path, so
every per-cluster record is stored once under each.

## Finding

**#332 — a keyboard-focused picker option was hidden under the sticky Generate bar** (WCAG 2.2 SC 2.4.11). Seen in
this walk's capture of the namespace-access form, then measured at 1440×900: 16 of 40 focused options had the bar on
top of their centre. Fixed in #333 — scroll-padding sized by a ResizeObserver to the bar's real height (44 px on a
desktop, up to 160.5 px at 320 px wide) — and re-measured on the redeployed `e3b3731b78`: **0 of 40**.

## What is here

| Path | What |
|---|---|
| `e2e-walk.html` | the walk document, every screenshot embedded (the PDF build is not committed, for size) |
| `results.json`, `results_extra.json`, `integrity.jsonl`, `env.json` | the walk's own results — every number in the document is read from these |
| `results_release.json`, `measurements.json`, `results_release_7e68a93.json` | the release checks as first run, the three precise re-measurements, and the corrected checks re-run |
| `findings.json` | the findings the document carries |
| `screenshots/` | the release checks (`release-*.png`) and the namespace-access report after the walk's fix (`walk-23-*.png`). The walk's own 75 captures (44 main, 20 second pass, 11 PDF page 1) are not committed as PNGs: `e2e-walk.html` embeds them as downscaled JPEGs |
| `artefacts/` | the 11 reports as HTML and JSON, downloaded through the page (the PDFs are not committed, for size) |
| `validate_release.py` | the release checks |

## How to repeat

```sh
S=<a scratch directory>; export KUBECONFIG=<a kubeconfig with a token session on the lab>
export GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password)
local-development/e2e-walk/run_walk.sh --base https://group-sync-dashboard.apps-crc.testing \
  --login-user kubeadmin --out "$S/walk"
E2E_WALK_DIR=local-development/e2e-walk local-development/.venv/bin/python \
  reports/2026-09-23_release-walk/validate_release.py \
  --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin --out "$S/release"
```
