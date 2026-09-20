# Review record — the session key and the report token minted on the cluster (#212 item 1, PR #215)

Branch `feat/212-minted-secrets`, base `main`. Head reviewed: `b669d11` (the branch moved on under the
pass — `a0000ad` the renderer test, `b89791a` Grok's findings, `0a48b05` Codex's; OB3 re-measured its
findings against those heads). Three reviewers on one brief of ten claims (`review_brief_215.md` in the
session scratchpad; restated in the table): Grok 4.6 (Cursor, ask mode — from the source), Codex
(GPT-5.6, xhigh — 16 render combinations, the script driven with real `oc --dry-run=client`, main-vs-head
render diff), OB3 (Opus 5 — the script under an `oc` shim backed by an on-disk store seeded with hostile
values, the Helm order read off release 15's live events, the Argo order read off the sibling chart's
recorded `syncResult`, every selector against every pod template, the live PDB and endpoints). Every
verdict was re-checked on the branch before a decision. Line numbers are those of `b669d11`.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| M1 | Nothing generated is rendered; no `lookup` survives | CONFIRMED (Secrets); three `lookup` calls remain, none feeding a Secret | REFUTED on the letter — proposes removing the apps-domain lookup, the auditors' Group guard and the NOTES lookup | CONFIRMED (Secrets); "no lookup" false as worded, *no change warranted* — none feeds a Secret, all on `main` | **Codex's removal rejected.** The defect was a `lookup` that changes a manifest silently when empty; the two that remain do the opposite (the apps-domain read fails the render naming GitOps as case 1 — the 2026-09-03 finding; the auditors' guard runs only for `createLocal` groups and the ArgoCD section now says Argo cannot run it). `tests/test_chart_renderers.py` pins exactly those two, one call each. |
| M2 | Hook ordering, Helm and Argo | REFUTED — identity at Argo's default wave 0, Job at −1: a first Argo install starts the Job with no SA | REFUTED — the same | CONFIRMED with a precision: Argo takes `helm.sh/hook-weight` as the wave when no `sync-wave` is set — measured on the grafana Application's `syncResult` (SA, Role, RoleBinding, then the Job, in PreSync) | **Wave −2 on the identity, both charts (`b89791a`)** — the annotation is right, my first comment's rationale ("would be applied after") was wrong and OB3's measurement replaced it (`N5`). Test: the identity's wave below the Job's. |
| M3 | The transition carries values byte for byte | CONFIRMED for the rendered charset; **N2** a trailing newline is stripped by `$(…)`; **N6** a read error on the legacy name reads as "absent" and mints | REFUTED — `A+/=tail\n` lost its `\n` | REFUTED at the edges — the same two, measured with hostile legacy values; the `b89791a` version passes the same harness (`identical=True` for both newline cases; Forbidden → `FAIL … could not read secret`) | **Accepted (`b89791a`).** The copy goes through a file and `--from-file`; `existing()` returns present/absent/error and an error fails the Job (retried). Found on the way: an `exit` inside `$(…)` only leaves the subshell — the harness caught it, return codes replaced it. |
| M4 | Idempotence, the race | CONFIRMED | CONFIRMED (executed: kept ×2; AlreadyExists ×2 → kept; Forbidden → exit 1) | CONFIRMED | Holds; **Grok N1** `random()` ended in `head -c N`, which closes the pipe — under `pipefail` a SIGPIPE'd `tr` fails the mint. `cut` as the last stage, both charts. |
| M5 | RBAC: four `get` names, `create`, one subject; the application's grants unchanged | CONFIRMED | CONFIRMED (`git diff main` empty for the application's RBAC) | CONFIRMED (per audit mode) | Holds. |
| M6 | The mint pod outside the Service's and PDB's selectors | CONFIRMED (from the template) | PLAUSIBLE (no live read) | CONFIRMED (every selector vs every pod template; live PDB `disruptionsAllowed 1`, one endpoint) | Holds — found by the full suite before the pass (`e7d8010`). |
| M7 | The image and what plain Kubernetes must set | CONFIRMED; the README did not say so | PLAUSIBLE | REFUTED on the README half at `b669d11` | **Accepted (`b89791a`)**: the README row says an image with `oc`. |
| M8 | Behaviour preservation | **REFUTED — `report-cronjob.yaml` still mounts `-token`**; every scheduled report fails after the upgrade | REFUTED — the same (27 other objects identical) | REFUTED — the same | **Accepted (`b89791a`).** The range scope is `$`, my rename on `.` skipped it, and no default render has a CronJob. The mounts test renders a schedule now. The one regression in the PR; all three found it. |
| M9 | Docs current | CONFIRMED | REFUTED — the reference architecture's cookie paragraph and the reporting design's service-credential paragraph describe the `lookup` era as current | REFUTED — those two, a values comment ("generated once, reused"), and the rendered alert's `-report-token` | **Accepted** (`b89791a` the alert, `0a48b05` the two docs, this head the values line), with Codex's regression test. |
| M10 | Tests | CONFIRMED | CONFIRMED (main: 7 failed; head: 7 passed; suite 3701/13) | CONFIRMED | Holds. |

## Volunteered, besides the above

- **OB3 N2** — `oauthProxy.cookieSecret` set on a release, then cleared: the rendered `-oauth-session`
  is Helm-owned, so clearing it makes Helm delete it in the same apply that rolls the Deployment onto
  it; `--wait` never ends. Accepted: `helm.sh/resource-policy: keep` (and `Prune=false,Delete=false`
  under Argo) on the rendered Secret, so the hook finds and keeps it; the README says the reverse
  switch (a value onto a minted release) needs the Secret deleted first and signs everyone out once.
- **OB3 N3** — `helm uninstall` leaves the two minted Secrets and the hook identity behind (Helm never
  owned them). Accepted: the Uninstall section lists both delete commands; test.
- **OB3 N4** — a test comment misdescribed its render. Fixed.
- **OB3 N7** — the CHANGELOG now says the schedule Jobs' mount moved too.
- **OB3 N6** (observation, no fix) — the identity is re-created on every upgrade seconds before its pod
  pulls from the internal registry; OpenShift attaches the pull credential to a new SA asynchronously.
  Three CRC runs pulled within a second; a cold multi-node pull was not measurable here. The pattern
  is the one all three charts share.

## Rejected

- Codex M1 — removing the two remaining `lookup`s (above).

## Validation

`tests/test_chart_secrets_mint.py` 12, `tests/test_chart_renderers.py` 6 (the Kustomize cases skip
without a Helm 3 locally; CI runs them), `tests/test_chart_openshift_grafana.py` 34; `helm lint` both
charts clean; full hermetic suite . Live on CRC, three upgrades
in a row through the hook: the first carried both values over (sha1 of `.data` identical, the old
names gone, a pre-upgrade session still signed in, the usage pull 200), the next two KEPT
(resourceVersions unchanged), PDB `disruptionsAllowed=1` — `reports/2026-09-20_deployer-compat-212/`.

## Owed

An OB2 (Fable 5.1) re-review when the quota resets — tracked in #210.
