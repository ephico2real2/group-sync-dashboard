---
name: e2e-walk
description: End-to-end walk of the DEPLOYED dashboard through its route with Playwright — login as a cluster user, every tab, every report in the catalogue generated as PDF and HTML and downloaded, a four-way integrity check on the artefacts, cluster facts measured with oc/helm, and a walk document with the screenshots embedded. Outputs are committed under reports/<date>_<slug>/. Invoke when the operator asks for screenshots, an end-to-end test, or evidence that a release works on a cluster.
---

# End-to-end walk — evidence that the deployed product works, with the pictures

The operator's ask, verbatim (2026-09-14): *"screenshot the group sync dashboard and the reporting
features etc. Do an end to end take. Use Playwright to take screenshots as you see fit. Send pictures
for successful test and also them in a format doc with embedded pictures … and pdf files"*, then
*"create a folder reports and add the generated reports inside and the full-resolution screenshots
and commit it"*, then *"document it so that we can invoke it again."* Everything below was run that
day against CRC (application 0.19.0, chart 0.21.0) and produced `reports/2026-09-14_e2e-walk/`.

## What one invocation produces

| Output | Made by |
|---|---|
| `NN-*.png` — the login path, every tab, each report's form and status, the recent-runs table | `e2e_capture.py` |
| `reports/` — every report's `.pdf` (PDF/A), `.html`, `.json`, downloaded through the page's own buttons | `e2e_capture.py` |
| `extra/` — the second cluster, the light theme, every HTML report opened in Chromium, page 1 of every PDF | `e2e_extra.py` |
| `integrity.jsonl` — per report: recomputed sha256 = the JSON's field = the run record = the PDF metadata; HTML prefix; PDF/A marker | `integrity_check.py` |
| `env.json` — pods, images, chart revision, OpenShift version, node CPU requests, preemption count | `env_facts.sh` (oc, helm) |
| `results.json`, `extra/results_extra.json` — every step with time, verdict, detail, screenshot, API bodies, run records, sizes | the two capture scripts |
| `doc/e2e_walk.pdf` and `.html` — the walk document; every number read from the files above | `build_doc.py` |

The tools live in `local-development/e2e-walk/`; `run_walk.sh` runs the five in order.

## Step 0 — pre-flight, with the RIGHT kubeconfig

`KUBECONFIG` must point at the cluster the route serves. On the lab that is the separate kubeadmin
kubeconfig in the session scratchpad, never the default `oc` context, which has pointed at another
cluster (poc1) for weeks. Then, before spending six minutes on a walk:

```sh
oc get pods -n group-sync-dashboard            # both Deployments Running, the report pod 1/1
oc get route group-sync-dashboard -n group-sync-dashboard -o jsonpath='{.status.ingress[0].host}'
helm list -n group-sync-dashboard              # the chart and app versions the document will name
```

The password comes from the environment only — `GSD_UI_PASSWORD=$(cat
~/.crc/machines/crc/kubeadmin-password)` for kubeadmin, never an argument (argv is visible to every
process on the host). The identity provider is `developer` for kubeadmin on the lab; an LDAP persona
needs `--provider ldap-local`. The Playwright browser must be installed in the venv
(`./.venv/bin/python -m playwright install chromium`, once).

## Step 1 — run it

```sh
S=<scratchpad>; OUT="$S/e2e/$(date +%Y-%m-%d)"
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) KUBECONFIG=<the cluster's kubeconfig> \
  local-development/e2e-walk/run_walk.sh \
    --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin --out "$OUT"
```

Six minutes on CRC (75 steps: 5 login/API, 8 tabs, 11 reports × form + generate + 3 downloads, the
runs table). Exit 0 only when every step and every integrity check passed; the document is built either
way so a failing walk still leaves the evidence. Options: `--provider`, `--namespaces` (for the
namespace-access report, which has no default), `--namespace`/`--release` for the cluster facts,
`--skip-env` when there is no kubeconfig (then write `env.json` by hand — and say so in the document).

What the scripts refuse: a page with an uncaught JavaScript error or a visible "Dashboard API error"
is recorded as a failed step, not screenshotted as if it worked (the rule from
`local-development/capture-screenshots.py`, which this borrows its login sequence from: interstitial →
provider chooser → form → optional consent). A report that reaches no terminal state in 120 s fails.

## Background work — never poll it

The operator's rule, verbatim (2026-09-17): *"Pls dont poll background jobs and waste tokens. Pls use watcher
and ask them to notify you or wake up when the done."* A walk takes six minutes on CRC; a suite ten; a review
pass twenty. Run each with the Bash tool's `run_in_background` (or arm a `Monitor` whose filter matches BOTH
the success and the failure marker) and act only on its completion notification. Reading or tailing the
output file before that notification is a full model round-trip that re-bills the whole conversation for
one "not yet" — and a `… 2>&1 | tail -N` output file stays empty until the command exits, so the early read
tells you nothing anyway. One status check when something looks wrong (is the pid alive, did the file
appear) is fine; the *loop* of checks is the waste. Reviewers launched as agents notify on completion too:
never predict or paraphrase their result before the notification arrives.

## Step 2 — look before you send

Read two or three captures (the Overview, one report status, one `pdf-page1-*.png`) with the Read
tool before building anything on them: a screenshot of a broken page looks like a design choice. Then
`grep FAIL` the run output and explain every failure — a failed step is either a defect in the walk
(fix the script, re-run) or a product finding (Step 5). Never edit a results file.

## Step 3 — findings into the document, then build

If the walk found something about the product, write `<out>/findings.json` — a list of
`{"title", "severity": "defect" | "note", "text"}` — with the measurement in the text (the status
code, the count, the timestamp, the mechanism from the source), and re-run the last stage alone:

```sh
local-development/.venv/bin/python local-development/e2e-walk/build_doc.py "$OUT" "$OUT/env.json"
```

The document says "No product finding was recorded from this walk" when the file is absent. It never
carries a number the results files do not; if a count is needed that the scripts did not measure
(files in a folder, say), measure it with `ls | wc -l` and quote that, not a derived total — the one
miscount on 2026-09-14 was a caption that added counts instead of counting files (56 said, 66 real).

## Step 4 — deliver

Send with the file tool, as they are produced, not in one batch at the end: the walk PDF (render),
two or three key PNGs (render), then a zip of the report artefacts and a zip of all screenshots
(attach). The caption states the counts measured in Step 3.

## Step 5 — commit the evidence, file the findings

- `reports/YYYY-MM-DD_<slug>/` on a branch from main: `artefacts/` (the service's files), `screenshots/`
  (main walk `NN-*.png`, second pass `extra-NN-*.png`, `pdf-page1-*.png`), `e2e-walk.pdf`, the four
  results files, and a `README.md` (outcome line, what is here with counts, findings with issue
  numbers, how to repeat). The README at the top of the reports folder (PR #98) holds the folder
  convention and a row per walk — add the row. The two READMEs are scanned by the docs citation test: a backticked `.md`/`.py` path must
  resolve; name a file that will exist only after another PR merges in plain words.
- Every product finding becomes an issue with the measurement and the mechanism from the source
  (2026-09-14: #96, a removed cluster lingering as ok; #97, the report pod preempted on the
  saturated node). The README and the document cite the issue numbers.
- The session change log gets the walk under its own Part, with the numbers
  (see the `changelog` skill).

## Gotchas — all seen on 2026-09-14

- **The route host is not in `spec.host`.** The chart lets the router name it; read
  `.status.ingress[0].host`.
- **The second cluster may be a ghost.** A cluster removed from `clusters:` stays in
  `/api/clusters` as ok with frozen data and 404s when selected (#96). The walk records it as a failed
  step; that is a finding, not a script defect — do not "fix" the script to skip it.
- **The report pod can be preempted mid-walk on a saturated node** (#97: 29 times in three hours on
  CRC at 99% CPU requests). A run that fails with the pod gone is re-run once; if it recurs, the
  document says so and the preemption count from `env.json` is the measurement.
- **The runs table is cumulative.** "Recent runs" lists every run the service still holds, not only
  this walk's; the document states the count it listed, not "eleven".
- **macOS renders PDF page 1 with `sips`**; on Linux substitute `pdftoppm -png -r 80 -f 1 -l 1` in
  `e2e_extra.py`. Chromium prints the document to PDF with `page.pdf()`; images are downscaled JPEGs
  inside the document, the originals stay in the folder.
- **Playwright runs headless.** Whether the Claude Code session is a terminal or the desktop app changes
  nothing about the captures — same Chromium, same viewport (1440×900, device scale 1), same fonts;
  only the viewer differs (a terminal cannot show the PNGs, the app renders the file cards inline).
  Use `device_scale_factor=2` in `e2e_capture.py` for HiDPI-crisp images at four times the bytes.
