# Docs content audit, batch 4 of 6: the release, build and repository guides

Phase 2 of the documents pass, fourth batch. The four release and build guides under `docs/guides/`,
the root `README.md` and `local-development/README.md` were read in full, and every checkable claim was
measured against main at 999c102b (application 5.4.0, chart 0.70.7). The evidence comes from:

- the workflows (`.github/workflows/publish.yml`, `helm.yaml`, `promote.yml`, `ci.yml`) and the scripts
  they call (`local-development/build-and-push-external.sh`, `build-and-push-report.sh`,
  `prepare-release.py`, `check-app-version-bump.py`, `release-crc.sh`, `render-manifests.sh`,
  `vendor-assets.sh`, `cluster-report.py`), read at the cited lines;
- `prepare-release.py --help`, and `prepare-release.py --app 5.5.0 "Probe issue" --no-commit` run in a
  throwaway clone under the scratch directory, never in the worktree;
- `ci.yml`'s chart-bump check run by hand in that clone on an `appVersion`-only commit;
- `vendor-assets.sh` (offline) and `vendor-assets.sh --outdated` run in that clone;
- the chart, rendered with `helm template` (Helm v4.3.0);
- GitHub, read with GET calls only: deploy keys (id, title, `read_only`, creation time; no key material),
  environments, the `release` environment's branch policies and secret names, ruleset 24475607, branches,
  the `release` branch's commits and tree, Actions variables and secret names, and `gh run list` /
  `gh run view` for `publish.yml`, `helm.yaml` and `promote.yml`;
- quay.io's public tag API (`/api/v1/repository/ephico2real/group-sync-dashboard/tag/`), anonymous;
- the lab (CRC), read-only with `oc get`: Argo CD Applications, Routes, pods, Secret names (no data),
  the cluster version's overrides, the monitoring namespaces and the release namespace's monitoring objects.

No workflow was run, nothing was pushed, and no cluster object was written. Line numbers are given outside
backticks and are those of 999c102b.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the document now says what the evidence shows.
- **NOT MEASURED**: no measurement was possible here (a historical value, a past measurement, a
  third-party behaviour, or a write). It was left unchanged.
- **CODE-SUSPECT**: the document describes what the code is meant to do and the code does not do it.
  The document was left as it is; the finding is below, with two more code findings no document claim
  carried.

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `docs/guides/RELEASING.md` | 47 | 12 | 3 | 1 |
| `docs/guides/RELEASE_BRANCH_SETUP.md` | 19 | 1 | 5 | 0 |
| `docs/guides/image-vulnerability-scan.md` | 19 | 3 | 4 | 0 |
| `docs/guides/updating-vendored-assets.md` | 17 | 4 | 2 | 0 |
| `README.md` | 29 | 6 | 4 | 0 |
| `local-development/README.md` | 27 | 6 | 4 | 0 |

`local-development/README.md` is an image input (`publish.yml` line 84), so this change takes application
5.5.0 and chart 0.70.8, in the shape #619 used: the version fields, their two `Chart.yaml` history lines
and one bullet under `## Unreleased`.

## The `--no-commit` question, settled by running it

RELEASING.md's "Neither" section said `prepare-release.py --app X.Y.Z "…" --no-commit` "prepares the matching
version fields and release notes for review". Run in a throwaway clone on a branch (`--app 5.5.0 "Probe issue"
--no-commit`), it printed `edited :` for seven files and exited 0:

- `local-development/pyproject.toml`, `local-development/gsd/__init__.py` and `Chart.yaml`'s `appVersion`, each 5.5.0;
- `Chart.yaml` `version` 0.70.7 to 0.70.8, with `# CHART 0.70.8 …` above it and `# 5.5.0 … MINOR.` above `appVersion`;
- `docs/CHANGELOG.md`: `## Unreleased` replaced by `## Application 5.5.0 — chart 0.70.8 — 2026-10-05` with
  `- **Probe issue.**` as its first bullet;
- `docs/specs/README.md`, `SPEC_F7_snapshot_clock.md` and `SPEC_P1_promote_release_branch.md`: Status `merged`
  to `released` (`promote_merged_specs`, `prepare-release.py` lines 232-260, called at line 385).

It ran `tests/test_chart_versions.py` and committed nothing (`done : --no-commit, …`). The issue PRs that carried a
bump kept less: `06431584` (#598) and `4eee95e4` (#616) added one bullet under `## Unreleased` and changed no spec
status from `merged`; `86c118f0^2` (#619) changed exactly `Chart.yaml` (both history lines), `pyproject.toml`,
`gsd/__init__.py` and one `## Unreleased` bullet. The guide now names every edit the flag makes and what an issue PR
keeps, and the migration paragraph says the application heading stays there (the schema line needs it,
`tests/test_migration_needs_app_release.py`).

## `docs/guides/RELEASING.md`

| claim | verdict | evidence |
|---|---|---|
| The model: app MINOR per image-changing issue, MAJOR per epic; chart version per template/default change; quay.io and gh-pages | CORRECT | `check-app-version-bump.py` lines 128-151; `helm.yaml` chart-releaser with `packages_with_index`; `gh api …/branches`: `gh-pages`, `main`, `release` |
| `appVersion` held to `pyproject.toml` by `tests/test_chart_versions.py` | CORRECT | `test_appversion_equals_the_application_version` |
| Cut with `prepare-release.py`; lower components reset to zero | CORRECT | `kind_of_bump` refuses a move that leaves a lower component non-zero (lines 85-102) |
| The app-bump job: `on.push.paths` allowlist, merge ref vs base SHA, next MINOR/MAJOR only, bad base fails, version lines are not content, the README is an input | CORRECT | `check-app-version-bump.py` lines 32-55, 99-151; `ci.yml` job `app-version-bump` |
| The PR gate's jobs and the two named checks | CORRECT | `ci.yml` jobs `tests` (3.11, 3.14), `ui`, `chart`, `diagrams`, `image`, `version-bump`, `app-version-bump`; branch protection requires seven of them (`gh api …/branches/main/protection`) |
| "fans out to two independent workflows" | FIXED | `promote.yml` also runs after a merge (`workflow_run` of publish, and a chart or `environments/` push, lines 15-29). Now names it |
| `publish.yml` "writes to nothing in this repository" | FIXED | the `attest` job holds `attestations: write` "to store the provenance statement in this repository's attestation store" (lines 422-427). Now: commits nothing; its one write there is the provenance |
| The image inputs: `gsd/** · pyproject.toml · README.md · Containerfile · .containerignore · build script` | FIXED | `publish.yml` `on.push.paths` (lines 81-93) has twelve entries, including `Containerfile.report`, `build-and-push-report.sh`, `uninstall-lists.py`, both proofs and `publish.yml`. Now lists them |
| The release decision: version moved → immutable tag and alias; unchanged → immutable only; cannot tell → immutable only with a `::warning::` naming `--release-tags` | CORRECT | `publish.yml` lines 196-238 |
| A release push publishes `:<appVersion>` (the diagram's `yes` branch) | FIXED | `build-and-push-external.sh --release-tags` copies to `${VERSION}` and `${CHART_VERSION}` (lines 262-277); quay: `0.70.7` and `5.4.0` both `sha256:9f6ed6458b16…`. The branch now shows `:<chartVersion>` too |
| Tag scheme `<appVersion>-<10-char sha>` | CORRECT | `COMMIT="${COMMIT:0:10}"` (line 133); quay tag `5.4.0-86c118f093` |
| `sbom`, `attest`, `latest` jobs; `:latest` on main only, after `attest` or after `publish` with signing off | CORRECT | `publish.yml` lines 334-638; run 37297540505: six jobs, all `success` |
| `helm.yaml`: `charts/**` filter; missing image is a red run naming the manual commands; label check per image through appVersion, a pin not checked; the own-alias refusal; retag by `skopeo copy`; chart-releaser skips a released version; attestation only for a new one | CORRECT | `helm.yaml` lines 25-26, 228-246, 251-279, 285-309, 318, 330-334, 351-372 |
| Image-changing issue PRs carry a MINOR, so their merges publish both tags | CORRECT | #619 merged as application 5.4.0; quay `5.4.0` and `5.4.0-86c118f093` at one digest |
| During development the lab tracks `main` | CORRECT | lab: Application `group-sync-dashboard` `targetRevision: main`, synced at 999c102b |
| The `ErrImagePull` race "measured at 4.1.0, 4.4.0 and 5.1.0" | NOT MEASURED | historical |
| `--argocd release` removes it; `--argocd main` switches back; the epic walk runs on `release` (`.claude/skills/epic/SKILL.md` section 6) | CORRECT | `release-crc.sh` lines 42-46 and 255-300; the skill's section 6, item 3 |
| A second install needs its own release name, because cluster-scoped objects are named by release | CORRECT | `helm template` as `group-sync-dashboard` and `group-sync-dashboard-dev`: seven cluster-scoped objects each, no name shared |
| `promote.yml`'s triggers, the five steps, what `release` holds, the commit subject, no workflow on `release` | CORRECT | `promote.yml` lines 15-38, 140-282; `gh api …/git/trees/release`: `charts`, `environments`, `promotion.yaml`; the tip's subject `promote: main 86c118f0…` |
| One writer: the deploy key in the `release` environment (main only); a ruleset only deploy keys bypass, force pushes blocked; the job token `contents: read` | CORRECT | `gh api`: environment `release` `custom_branch_policies: true`, one rule `main` of type `branch`; ruleset 24475607 rules `creation`, `update`, `deletion`, `non_fast_forward`, bypass `DeployKey` `always`; `promote.yml` line 46 |
| Rollback, and `release-crc.sh --argocd release` refusing a `release` without `promotion.yaml` | CORRECT | `promote.yml` lines 145-150; `release-crc.sh` lines 260-264 |
| The operator's one-time steps | CORRECT | they match `RELEASE_BRANCH_SETUP.md` and the live settings above |
| The four tags, including `:latest` (#425) | CORRECT | quay: `5.4.0`, `0.70.7`, `5.4.0-86c118f093` and `latest` all at `sha256:9f6ed6458b16…`; `test_the_docs_say_what_latest_names` passes |
| `image.digest` wins; a malformed digest fails the render and names `skopeo inspect` | CORRECT | `helm template --set image.digest=sha256:abc`: `image.digest "sha256:abc" is not a digest …` with `skopeo inspect --no-tags docker://…:5.4.0` |
| `image.tag: ""` and `default .Chart.AppVersion` | CORRECT | `values.yaml` line 32; `_helpers.tpl` `gsd.image`; render `quay.io/ephico2real/group-sync-dashboard:5.4.0` |
| `imagePullPolicy` is `Always` | CORRECT | `values.yaml` line 60; render |
| "Every pushed image is signed and attested" | FIXED | `attest` runs only on `refs/heads/main` (`publish.yml` line 420); a dispatch from another branch pushes unsigned images (D9). Now "every image `publish.yml` pushes from `main`" |
| Two repository variables turn the modules off; unset means on | CORRECT | `gh api …/actions/variables`: none set; `publish.yml` lines 342, 419 |
| Steps 1-3 and 5 of an application release | CORRECT | `prepare-release.py` lines 350-367; the `--no-commit` run above |
| Step 4: "`ci.yml` fails the PR if the version did not move" | FIXED | `ci.yml`'s check drops `Chart.yaml` from the changed set (`grep -v '/Chart.yaml$'`). Run on an `appVersion`-only commit in the clone: `changed=[]`, so the check prints "no chart content changed" and passes. Now says CI does not catch it. The consequence is finding 2 |
| Step 6 lists the changelog edits only | FIXED | the script also moves every `merged` spec to `released` (the `--no-commit` run). Added |
| Step 7: the test runs, a failure commits nothing and leaves the edits | CORRECT | `prepare-release.py` lines 391-396 |
| The refusals: dirty tree, no advance, lower component, existing branch | FIXED | it also refuses a checkout other than `main` unless `--no-commit` (lines 295-300). Added |
| Commits to `release/app-X.Y.Z`, sole author, never touches `main` | CORRECT | lines 319, 413-415; no trailer |
| "All the edits land in one PR, or CI is red" | FIXED | not for the chart `version` (step 4). Qualified |
| `--pr` opens the pull request | CODE-SUSPECT | finding 1 |
| The schema line's text, `N` and `M`, the shallow-clone refusal naming `fetch-depth: 0` | CORRECT | `SCHEMA_LINE`, `schema_since_app_release` (lines 168-195); `test_t300_8_releasing_md_states_the_line_and_when_it_appears` passes |
| CI enforces it since `2e7d33be`, then application 2.3.0; 3.0.0 and 4.0.0 stayed at schema 20 | CORRECT | `highest_migration` read with `git show`: `2e7d33be` 2.3.0 → 20; HEAD 5.4.0 → 20 |
| The chart-only release | FIXED | it also moves `merged` specs to `released` (same function; `promote_merged_specs` runs for `--chart` too). Added |
| "Neither": `--no-commit` "prepares the matching version fields and release notes" | FIXED | the section above. Now names every edit and what an issue PR keeps |
| A migration is never "neither"; the test fails such a PR; commit the bump after the migration | CORRECT | `tests/test_migration_needs_app_release.py` `assert_schema_released` |
| The migration paragraph's "commit the edits" | FIXED | the test requires the version's own application heading when the schema rises (`assert_release_schema_notes`); the paragraph now says that heading stays |
| When Actions is down: the three commands, `--release-tags` off by default and refusing a dirty tree, two images since 0.18.0, the recovery `publish.yml` names | CORRECT | `build-and-push-external.sh` lines 55-63, 233-279; `build-and-push-report.sh`; `publish.yml` lines 221-226 |
| `--update-values` is the local path; CI never uses it | CORRECT | `publish.yml` lines 259-271 |
| The troubleshooting table's messages | CORRECT | each string is in the code: `helm.yaml` lines 232, 238, 271, 295; `promote.yml` lines 64, 136, 147, 162, 207, 223, 239, 244, 251; `release-crc.sh` line 262; `publish.yml` lines 589, 617-633 |
| `:0.39.0` was application 0.24.0; the report repository's first publish (2026-09-11) | NOT MEASURED | historical |
| #34 and #37 | NOT MEASURED | historical; `publish.yml`'s header records them |

## `docs/guides/RELEASE_BRANCH_SETUP.md`

| claim | verdict | evidence |
|---|---|---|
| "Until now that branch was `main`" | FIXED | the lab's Application still tracks `main` (above), as step 6 says. Now "During development that branch is `main` (step 6)" |
| A merge reaches the lab before its image | NOT MEASURED | historical (RELEASING.md's 4.1.0, 4.4.0, 5.1.0) |
| `promote.yml` reads both images back and pins their digests in `promotion.yaml`; nothing else may write `release` | CORRECT | `promote.yml` lines 202-261; ruleset 24475607; one deploy key on the repository |
| The four settings | CORRECT | `gh api`: key `promote-release`, environment `release`, branch `release`, ruleset `release` |
| Three branches on purpose | CORRECT | `gh api …/branches`: `gh-pages`, `main`, `release` |
| Step 3 before step 4, because the ruleset blocks creation | CORRECT | ruleset rule `creation` |
| Step 1's check: `promote-release`, `read_only` `false` | CORRECT | `gh api …/keys`: id 165382583, `promote-release`, `false`, 2026-10-05T00:54:42Z |
| Step 2's checks: `custom_branch_policies: true`, one rule `main` of type `branch`, the secret | CORRECT | `gh api …/environments`, `…/deployment-branch-policies`, `…/environments/release/secrets` (`RELEASE_DEPLOY_KEY`, 2026-10-05T00:58:04Z) |
| The API needs the secret encrypted first | NOT MEASURED | GitHub API behaviour |
| The web UI cannot create an empty branch | NOT MEASURED | GitHub UI behaviour |
| `4b825dc…` is git's empty tree | CORRECT | `git hash-object -t tree /dev/null` prints `4b825dc642cb6eb9a060e54bf8d69288fbee4904` |
| Step 4's ruleset body | CORRECT | `gh api …/rulesets/24475607` returns that body |
| A hand push is refused with `GH013` | NOT MEASURED | a push is a write |
| Step 5: the first promotion ran on its own after #614 | CORRECT | `gh run list --workflow promote.yml`: run 37252414796, `workflow_run`, `success`, on `cb832a6a`; `release` commit `2cca5d78` `promote: main cb832a6a…` |
| `git ls-tree --name-only origin/release` lists `charts`, `environments`, `promotion.yaml` | CORRECT | `gh api …/git/trees/release` |
| Step 6's two commands | CORRECT | `release-crc.sh` `--argocd release` / `--argocd main` |
| The record: key, secret, branch `1f3c3303f62d` "release starts empty", ruleset 24475607 | CORRECT | the `gh api` reads above; the oldest of the seven `release` commits is `1f3c3303f62d`, "release starts empty" |
| Which commands ran on that day | NOT MEASURED | historical |
| Upkeep: `gh repo deploy-key delete`; "the key is missing" is a promote message | CORRECT | `gh repo deploy-key delete --help`; `promote.yml` line 64 |

## `docs/guides/image-vulnerability-scan.md`

| claim | verdict | evidence |
|---|---|---|
| The recipe and its two bases | CORRECT | `local-development/Containerfile` lines 26, 54, 62 |
| `DESIGN_hardened_image.md` is the design record | CORRECT | `docs/design/DESIGN_hardened_image.md` exists |
| Grype 0.118.0 and Syft 1.51.1 | CORRECT | `ci.yml` `grype-version: v0.118.0` on every scan step; `publish.yml` `syft-version: v1.51.1`; `test_the_sbom_is_produced_by_the_syft_the_scan_document_measured` passes |
| The Trivy table, `/etc/os-release`, the finding counts, the CVEs, the sizes, the package versions | NOT MEASURED | the measurements of 2026-09-04, dated in the guide |
| "CI gates on it" | FIXED | the scans carry `fail-build: false` under "ADVISORY, NOT A GATE (operator decision 2026-09-16)" (`ci.yml` `image` job); `image` is not a required check. Now "scans with it, as an advisory report since 2026-09-16" |
| The action's default Grype was v0.110.0 on 2026-09-04 | NOT MEASURED | historical; the action is now pinned by commit (v7.4.2) |
| The blindness check fails the job "rather than passing on nothing"; "the gates matched no OS package" | FIXED | the check is right (`ci.yml` step "Grype identified the distribution"); the scans it guards are no longer gates. "gates" now "scans" |
| `libuuid`, `python3-pip`, `python-pip-wheel` uninstalled: records in the pack stage, files in the runtime stage | CORRECT | `Containerfile` lines 102-125 and 240 |
| The database ships 46 packages, down from 49 | NOT MEASURED | needs the image |
| `uuid` proven on every build | CORRECT | `Containerfile` (the runtime proof, from line 250); `image-proof.py` |
| The pack stage: the builder after `dnf update`; `bash`, `curl`, `jq`, `coreutils` copied as files | CORRECT | `Containerfile` lines 62-100 |
| Exactly twelve libraries, named | CORRECT | the `cp -L` list (lines 83-94): twelve |
| `libcurl` swapped for `libcurl-minimal` | CORRECT | `dnf swap -y libcurl libcurl-minimal` (line 69) |
| CI scans both the shipped image and the pack stage | CORRECT | `ci.yml` `image` job |
| `sqlite3.enable_load_extension(False)` on every connection; `gsd/store.py#Store.sync_members` | CORRECT | `store.py` lines 1372 and 2278 |
| SQLite 3.53.4 and the measured features | NOT MEASURED | needs the image |
| "The gate is in CI … It fails only on findings somebody can act on" | FIXED | advisory (above); the medium-and-above inventory is uploaded as SARIF; only the two distribution checks fail the job. Now says so, and names the report image's two scans |
| Floating tags; nothing pins a snapshot; `workflow_dispatch` forces a rebuild | CORRECT | the `FROM` lines carry no digest; `publish.yml` line 96 |
| Every pushed image carries the SBOM as an attestation and an artifact; `grype sbom:sbom.spdx.json` | CORRECT | `publish.yml` `sbom` and `attest` jobs; the install guide's "The SBOM" paragraph writes `sbom.spdx.json` |

The limits and the previous analysis are records of their dates and were not re-measured.

## `docs/guides/updating-vendored-assets.md`

| claim | verdict | evidence |
|---|---|---|
| `/api` and `/api/redoc` render from `gsd/static/vendor/` | CORRECT | `local-development/gsd/api.py` lines 3387-3397 |
| The directory holds the Swagger UI and ReDoc copies | FIXED | it also holds six woff2 typefaces and two DejaVu Sans faces, from the same `ASSETS` array and lock, and `--outdated` lists all five packages. Added one sentence, because `--upgrade` moves them too |
| The four commands and what each touches | CORRECT | `vendor-assets.sh` header; offline run: eleven `✓`, "All assets match. Nothing was downloaded."; `--outdated` left `git status` empty |
| CI and `tests/test_vendored_assets.py` run the offline check | CORRECT | `test_the_script_verifies_offline`; CI's `tests` job runs the suite |
| "~2.5MB in git" | FIXED | measured: the API-docs files are 2,827,977 bytes, the whole directory 4,396,633. Now "about 2.8 MB … (4.4 MB with the fonts)" |
| FastAPI's stock handlers load from `cdn.jsdelivr.net`; the favicon from `fastapi.tiangolo.com` | NOT MEASURED | third-party behaviour (`api.py` lines 925-926 says the same of the CDN) |
| The integrity method: npm's `dist.integrity`, sha512, then sha256 | CORRECT | `vendor-assets.sh` lines 36-38 and 107-121 |
| The example outputs | CORRECT | the live `--outdated` prints the same form (`↑ redoc 2.5.3 → 2.5.4 available`) |
| Step 4: `helm upgrade … --set ingress.host=<host>` | FIXED | `ingress.enabled` defaults to `false` and `route.enabled` to `true` with an empty `route.host` (`values.yaml` lines 1922-1990), so the flag set a value nothing renders. Removed |
| Step 4: `POD=$(oc get pods … -o name \| head -1)` | FIXED | on the lab the first pod is `grafana-openshift-grafana-deployment-…`, which has no `dashboard` container. Now selects `app.kubernetes.io/name=group-sync-dashboard`, which matches the dashboard pod alone |
| The site-packages path | CORRECT | `pip install --prefix=/install` and `PYTHONPATH=/install/lib/python3.14/site-packages` (`Containerfile` lines 45-46) |
| What the test checks | CORRECT | `test_vendored_assets.py`: seven tests, as listed |
| `tests/test_api_contract.py` asserts no CDN when the bundles are present | CORRECT | line 105 |
| `package-data` is `static/*, static/vendor/*` | CORRECT | `pyproject.toml` line 75 |
| The `ASSETS` array; versions in the lock | CORRECT | `vendor-assets.sh` lines 53-81; `ASSETS.lock` `# version` lines |
| The fallback warns and uses a CDN when the directory is absent | CORRECT | `api.py` lines 3398-3402 |
| The history items | NOT MEASURED | historical |

## `README.md`

| claim | verdict | evidence |
|---|---|---|
| The heading | CORRECT | `test_title.py` |
| It never creates or edits a GroupSync CR | CORRECT | the application's write calls (`kube.py` line 1379, `leader.py`, `fleetstate.py`, `clusterconfig/writer.py`, `fleetlogin.py`, `rejoin.py`, the report service's own API) touch no GroupSync |
| The reference cluster's figures and the screenshots' captions (9 RoleBindings, 12 alerts, 202 bindings, 62 groups) | NOT MEASURED | they describe captures; reading them again needs a login |
| The screenshots, `capture-screenshots.py` and its `--login-user` / `--provider` | CORRECT | the files exist; the script's arguments |
| The Layout and design tables' paths; eleven reports; seven API rules; the 4-hour cap | CORRECT | every path exists; `docs/reports/README.md` lists eleven; `api-contract.md` R1-R7; render `-cookie-expire=4h` |
| "thirteen modules specified" | FIXED | `docs/specs/README.md` indexes sixty specifications, "the original programme has thirteen modules". Now says both |
| Install, the values-file advice, Helm's reset semantics | CORRECT | `helm upgrade --help` (`--reuse-values` merges only when asked) |
| "That is enough": the host, the public image, the proxy, the projected token re-read every poll | CORRECT | `route.host` empty and the Route's `spec.subdomain`; `ClusterSpec.resolve_token` re-reads `tokenFile` (`config.py` lines 467-503) on each call (`poller.py` line 241) |
| The values table | CORRECT | `values.yaml`, every row; `test_the_root_readme_rows_state_the_real_defaults` passes |
| `oauthProxy.sar`; the API's delegated review on `list clusterrolebindings` | CORRECT | `values.yaml` `oauthProxy.sar`; render `-openshift-delegate-urls={"/api":{…"verb":"list"}}` |
| "Verified: an identity without it gets 403" | NOT MEASURED | needs a token |
| The proxy switches the Route or Ingress to `reencrypt`, binds the app to `127.0.0.1`, probes behind `skip-auth-regex`; the proxy image | CORRECT | render: Route `termination: reencrypt`; with the Ingress on, `route.openshift.io/termination: "reencrypt"`; `--host 127.0.0.1`; `-skip-auth-regex=…`; `ose-oauth-proxy-rhel9:v4.15` |
| The `trustedCA` block's keys and defaults | CORRECT | `values.yaml` |
| 148 certificates | NOT MEASURED | historical |
| A cluster's own `caBundleFile` wins | CORRECT | `config.py` "An explicit per-cluster bundle always wins" (line 532) |
| Monitoring: "twelve alerting rules (fourteen with the off-volume backup CronJob on), both off by default", "the reference cluster runs no Prometheus" | FIXED | default render: 20 alerts; 18 with `backup.offsite.enabled=false`; the chart README says three need reporting; `monitoring.serviceMonitor.enabled` and `monitoring.prometheusRule.enabled` are `true`; the lab runs Prometheus (below). Now twenty, on by default, and the `GrafanaDashboard` CR (render with `--api-versions grafana.integreatly.org/v1beta1`: one) |
| Cardinality "per cluster and per GroupSync CR only, never per group or per user" | FIXED | the label names in `gsd/` also include `finding`, `kind`, `report`, `schedule`, `node`, `threshold`; none names a group or a user. Now says so |
| The timestamp metric; `GroupSyncDashboardNotPolling`; `/healthz` unconditional, `/readyz` reads the store; the two WAL alerts | CORRECT | render; `api.py` lines 3019-3021, 3373-3385 |
| "The remaining five … The chart README lists all eight" | FIXED | twenty (above). Now "Five more … all twenty" |
| Building and shipping: the tag, the stamp, `/api/version`, the dirty-tree refusal | CORRECT | `build-and-push-external.sh` lines 131-166 |
| `publish.yml` "writes nothing back to this repository" | FIXED | the provenance write (above). Now "commits nothing back" |
| The secrets and variables table | CORRECT | `gh api`: secrets `REGISTRY_PASSWORD`, `REGISTRY_USERNAME`; `publish.yml` defaults; `ci.yml` `vars.CI_UI_TESTS != 'false'` (line 267) |
| The robot account example | NOT MEASURED | an example name |
| Re-running a commit is safe; secrets in step `env`, checked in a step | CORRECT | `build-and-push-external.sh` aliases by `skopeo copy`; `publish.yml` lines 146-168 |
| What it shows: up to fourteen tabs and the cited functions | CORRECT | `test_access_declaration.py` and `test_docs_citations.py` pass |
| What it writes | FIXED | the five places are right (batch 2's evidence). The section did not name the SubjectAccessReviews the tiers create (`kube.py` `SAR_API`, line 1379) or the fleet login's token, which `fleetlogin.py` revokes when done. One sentence added |
| `ReconcileError` is sticky; current only when newer than the success | CORRECT | `state.py` lines 114-126; `api.py` line 1098 |
| `cluster-report.py`: the flags, `GSD_PASSWORD`, PKCE, `UNREACHABLE`, the default URL | CORRECT | `--help`; lines 157-166, 468-493, 428 |
| Per-cluster authorization shipped in 0.19.0; `ACCESS_CONTROL.md` §11 | CORRECT | `docs/CHANGELOG.md` application 0.19.0; §11 "Several clusters in one instance" |

## `local-development/README.md`

| claim | verdict | evidence |
|---|---|---|
| The chart is the source; `render-manifests.sh` generates the YAML | CORRECT | `render-manifests.sh` header |
| `release-crc.sh` targets CRC's registry | CORRECT | its header |
| `prepare-release.py`: "the Chart.yaml history line", "runs the version test first" | FIXED | it writes two history lines and moves `merged` specs (above), and runs the test after the edits, before the commit. Now says so |
| `restore-db.sh` and the runbook's section 4 | CORRECT | `RUNBOOK_backup_restore.md` "## 4. Restore" |
| `clusters.yaml` and `crc-ca.crt` gitignored | CORRECT | `git check-ignore -v`: `.gitignore` lines 14 and 24 |
| `TITLE` and `tests/test_title.py` | CORRECT | `gsd/__init__.py`; the test |
| Running against CRC: the venv, `crc-ca.crt`, `GSD_TOKEN_CRC`, `gsd.api:create_app --factory` | CORRECT | `clusters.example.yaml` lines 12-16; `api.py` lines 3571-3603 |
| The release table's rows | CORRECT | `release-crc.sh` header (lines 20-52); `test_the_matrix_rows_match_the_script` passes |
| The table has no `--argocd release` rows | FIXED | the header has `--argocd release` and `--argocd release --values X` (lines 42-46) and says anything not in the table is refused. Both rows added |
| Tags reused when both exist; one without the other rebuilt | CORRECT | `release-crc.sh` lines 354-378 |
| `argocd-wait.sh` | CORRECT | it exists; the Argo modes call it |
| The test commands; `tests/test_ui.py#server`; the `ui` job on 3.14 with pinned Playwright, evidence on failure only; `CI_UI_TESTS` | CORRECT | `ci.yml` lines 251-309 |
| `test_live_smoke.py` runs in no CI job | CORRECT | deselected in `ci.yml` |
| The image's bases, the `pack` stage, `Containerfile.annotated` (held identical) and `Containerfile.ubi` | CORRECT | `Containerfile`; both files exist; `tests/test_containerfile.py` |
| What is in the pod's shell | FIXED | the pack also copies `rmdir` (`Containerfile` line 80). Added |
| "Scan locally the way CI does" with `--fail-on high` | FIXED | CI's scans are advisory (`fail-build: false`, above). Now says CI only reports and the flag makes the local run fail |
| The API docs routes | CORRECT | `api.py` lines 931, 3405, 3418, 3428 |
| `cluster-report.py` needs the API token access and cluster-wide RBAC read | CORRECT | the delegated review on `list clusterrolebindings` |
| `render-manifests.sh`: `deploy/`, gitignored, never applies; the Ingress host only with `ingress.enabled=true` | CORRECT | the script; `.gitignore` line 68 |
| The oauth cookie secret: "the chart mints a fresh `randAlpha 32` whenever it cannot find an existing Secret", and the script reuses the live value | FIXED | since chart 0.37.0 the key is minted on the cluster by the secrets-mint hook as `<fullname>-oauth-session` (`templates/oauth-secret.yaml` header, `secrets-mint.yaml`); the default render carries no `session_secret`; the lab has `group-sync-dashboard-oauth-session` and no `-oauth-cookie`. Now describes that, and what the script still does. The script's own message is finding 3 |
| `helm upgrade --install` remains the supported deploy | CORRECT | the script's header |
| `test_live_smoke.py` skipped unless `GSD_LIVE_CONFIG` | CORRECT | its skip condition |
| Forcing a sync by a spec change; `60-force-groupsync.sh` | NOT MEASURED | historical, and in another repository |
| "Monitoring is disabled at the CVO level … `openshift-monitoring` has no pods" | FIXED | lab, 2026-10-05: the cluster version's overrides do not name `cluster-monitoring-operator` or `monitoring`; `openshift-monitoring` runs `prometheus-k8s-0` and eleven other pods; `cluster-monitoring-config` holds `enableUserWorkload: true`; `prometheus-user-workload-0` runs; PrometheusRule `group-sync-dashboard` and ServiceMonitors `group-sync-dashboard`, `group-sync-dashboard-report` exist. Now says so, and keeps the earlier state as history |
| The podman VM and `*.crc.testing` | NOT MEASURED | the workstation's VM |
| `podman pull -q` and `podman manifest inspect` | NOT MEASURED | the workstation's podman |
| `/tmp` not shared into the podman VM | NOT MEASURED | the workstation's VM |

The `release-crc.sh` matrix test guards two phrases here ("built, **not** pushed" and no "built + pushed");
both are unchanged.

## Findings for the orchestrator (no change made)

1. **`prepare-release.py --pr` cannot open a pull request.** The script creates `release/app-X.Y.Z` locally and then
   runs `gh pr create --base main --head <branch>` (`local-development/prepare-release.py` lines 419-432) without
   pushing the branch. `gh pr create --help` (gh 2.102.0): "Use `--head` to explicitly skip any forking or pushing
   behavior." The branch is not on the remote, so the request should be refused, and the script then reports
   "gh pr create failed (the branch and commit exist)". Not measured end to end: it needs a push and a PR.
   RELEASING.md's `--pr` line still says it opens the pull request, as the code intends.
2. **An application release that forgets the chart `version` passes CI and relabels the previous chart's image.**
   `ci.yml`'s chart check removes `Chart.yaml` from the changed files, so an `appVersion`-only change passes (run in the
   clone: `changed=[]`). On the merge, `helm.yaml`'s "Label the image this chart version deploys" step has no
   `if: steps.plan.outputs.new == 'true'` (line 145): once the new `:<appVersion>` exists it copies that image onto
   `:<old chartVersion>`, a tag whose current label is the previous application, so the own-alias guard does not
   refuse it (lines 285-303); chart-releaser then skips the release. That is the "tag lies" case `helm.yaml`'s own
   comment rules out (lines 117-119). `prepare-release.py` always bumps the chart, so this needs a hand bump. Not
   measured end to end.
3. **`render-manifests.sh` reads the cookie Secret by its pre-0.37.0 name.** It reads
   `${RELEASE}-oauth-cookie` (`local-development/render-manifests.sh` lines 100-117). The chart has minted
   `<fullname>-oauth-session` on the cluster since 0.37.0, and the lab has no `-oauth-cookie`, so the script always
   takes the "not found" branch and prints "NEWLY GENERATED … applying this will sign out any existing sessions",
   though the render then holds no session Secret. Its header comment still describes the `randAlpha 32` render.
