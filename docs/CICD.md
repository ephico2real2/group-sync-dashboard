# CI/CD: from a pull request to the cluster

This page follows one change from "I opened a pull request" to "it is running on the cluster". The rule behind it:
**build once, then promote the artifact.** The image is built one time, from `main`. What the cluster runs is that
same image, checked and pinned, never a rebuild and never a moving tag.

## The short version

1. You open a pull request. `ci.yml` tests it.
2. It is reviewed and merged to `main`.
3. `publish.yml` builds the two images on a GitHub runner and pushes them to quay.io. Signing is on by default.
4. `promote.yml` reads both images back from quay.io. If they are right, it commits the chart and the image
   digests to the `release` branch.
5. Argo CD on the lab cluster syncs `release`, and pulls the images by digest.

Nothing builds on `release`, and nothing but `promote.yml` writes to it.

## Words used on this page

| Word | Meaning here |
|---|---|
| image | the container the dashboard runs; there are two, `group-sync-dashboard` and `group-sync-dashboard-report` |
| tag | a name for an image in the registry, such as `1.1.0-0123456789`; a tag can be moved to another image |
| immutable tag | `<appVersion>-<sha10>`: the application version and the first 10 characters of the commit; built once per commit |
| alias | the tag `:<appVersion>`, such as `:1.1.0`; `publish.yml` moves it when the application version changes |
| digest | `sha256:…`, the hash of an image's content; it cannot point at different bytes, unlike a tag |
| publish | `publish.yml`: build the images from `main`, push, sign |
| promote | `promote.yml`: read the images back, then commit the chart and the digests to `release` |
| revision label | `org.opencontainers.image.revision`, set at build time to the first 10 characters of the commit the image was built from |
| `release` branch | a branch holding only the chart, `environments/` and `promotion.yaml`; the lab's Argo CD tracks it |
| `promotion.yaml` | the values file on `release` that pins both images by digest |
| `workflow_run` | the GitHub Actions trigger "run this workflow after that one finishes"; it is how `promote.yml` follows `publish.yml` |

## The picture

<!-- markdownlint-disable MD033 -->
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="diagrams/cicd/promotion-pipeline.dark.png">
  <source media="(prefers-color-scheme: light)" srcset="diagrams/cicd/promotion-pipeline.light.png">
  <img alt="Only promote.yml writes to the release branch, after reading both images back from quay.io; a failed publish is never promoted, and Argo CD syncs release and pulls the images by digest" src="diagrams/cicd/promotion-pipeline.light.png">
</picture>
<!-- markdownlint-enable MD033 -->

*Figure 1. Five lanes, time flowing down. `publish.yml` builds on a GitHub runner and pushes to quay.io; `promote.yml`
reads back and commits to `release`; Argo CD syncs `release`. A failed publish stops the line. A chart-only merge goes straight to
`promote.yml` and reuses the last image. A rollback is a manual run of `promote.yml`. Thick lines are the main path,
thin grey lines an alternate path, red a failure. Signing and the SBOM are on by default and can be switched off.
Everything drawn ships.*

````text
GITHUB PR            GITHUB MAIN          QUAY.IO               RELEASE BRANCH        CLUSTER (ARGO CD)
open a PR
ci.yml checks:
tests, chart,
chart bump, app
MINOR/MAJOR bump
    | merged
    +----------------> merge to main
                         |          \ chart-only merge (skips publish)  [alternate]
                       publish.yml --pushes--> 1.1.0-<sha10>
                         |    \                :1.1.0 on a version bump
                         |     \               signing, SBOM: on by default
                         |      `--fails--> "publish failed: nothing is promoted"  [failure]
                         | succeeds
                       promote.yml <--reads back: labels, digest; signature if on--
                         |
                         +--commits the pinned artifact--> release: chart,
                         ^                                 environments/,
                         |                                 promotion.yaml ----syncs----> pulls both
                  rollback: run promote.yml  [alternate]                                 images by digest
                  with an older sha, rollback checked
````

## Step by step

### 1. The pull request

`ci.yml` runs on every pull request. `main` accepts a merge only when the required checks pass.

| Check | What it catches |
|---|---|
| `tests (3.11)`, `tests (3.14)` | the Python test suite |
| `Browser tests (Playwright, Chromium)` | the pages, in a real browser |
| `chart` | the chart must lint and render |
| `diagrams` | the diagrams must render |
| `Chart changes bump the chart version` | a change under `charts/` without a new `Chart.yaml` `version` |
| `App image changes bump the app version` | a change to an image input without exactly the next MINOR or MAJOR application version |
| `image` | builds the image and scans it for CVEs; not a required check, and the CVE report is advisory |

The app-version check (#427) reads the image inputs from `publish.yml`'s `paths:` list, so
`local-development/README.md` counts. `docs/RELEASING.md` gives its exact rules.

### 2. The merge

A merge to `main` starts the workflows below. Nobody pushes to `main` directly; it is branch protected.

### 3. Publish: build once

`publish.yml` runs only when a file that goes into the image changed (its `paths:` list). It then:

1. builds both images and tags them `<appVersion>-<sha10>`, for example `1.1.0-0123456789`;
2. moves the alias `:<appVersion>` only if the merge changed the application version;
3. signs each image by digest with cosign, attaches an SBOM, and reads the signature back.

Signing and the SBOM are on by default. The repository variable `SUPPLY_CHAIN_SIGNING=false` turns signing off, and
then promotion skips its signature check: labels and digests still have to match, but they do not prove who built the
image. `SUPPLY_CHAIN_SBOM=false` turns the SBOM off; promotion does not read it.

A merge that changes only the chart, the environments or docs outside the image inputs builds nothing.

### 4. Promote: read back, then commit

`promote.yml` starts in three ways:

| Trigger | When |
|---|---|
| after `publish.yml` | every publish run; only a successful one is promoted |
| a push to `main` touching `charts/group-sync-dashboard/` or `environments/` | a chart-only merge, which `publish.yml` skipped |
| Run workflow (manual) | a re-run, or a rollback |

It always promotes a commit on `main`, by default the newest. For that commit it:

1. finds I, the last commit on `main` that changed an image input. Every commit from I to the one promoted has the
   same image inputs;
2. takes the newest of those commits that `publish.yml` built successfully, usually I. If none, it stops: an image
   older than I does not contain I's code;
3. reads both images back, every Linux image in each: the version label must be the chart's `appVersion` and the
   revision label that commit's 10-character sha. With signing on, the signature must verify against `publish.yml`
   on `main`;
4. writes `promotion.yaml` with both digests and commits it to `release` with the chart and `environments/`.

If publish is still running, it exits green and says so: that publish run's completion starts it again.

### 5. Argo CD syncs `release`

The lab's Application (`gitops/argocd-application-dashboard.yaml`) tracks `release`. Its values files are
`environments/crc.yaml`, then `promotion.yaml`, so the pinned digests win. The pod runs exactly the digest that was
read back.

## What each kind of merge does

| The merge changes | publish.yml | promote.yml | The cluster gets |
|---|---|---|---|
| application code | builds `<appVersion>-<sha10>` | after publish succeeds | the new image and the chart |
| the application version | builds, and moves `:<appVersion>` | after publish succeeds | the new image and the chart |
| only the chart or `environments/` | nothing | at once | the new chart, with the last image of the same code |
| only docs that are not image inputs | nothing | nothing | nothing |

## Versions

| Number | Where | When it moves |
|---|---|---|
| application MAJOR | `pyproject.toml` | once per closed epic |
| application MINOR | `pyproject.toml` | once per merged issue that changes the image; docs-only is exempt |
| chart version | `Chart.yaml` `version` | every change under `charts/`; CI refuses a PR that forgets |
| `appVersion` | `Chart.yaml` | always equal to `pyproject.toml`'s version (a test holds them equal) |

`docs/RELEASING.md` has the full release procedure.

## When something goes wrong

| You see | It means | Do this |
|---|---|---|
| `promote` red: `no successful publish.yml run` | the image of this code was never published | fix and re-run `publish.yml`; its success promotes |
| `promote` red: `is labelled version` | a tag names another build | do not retag; find which run pushed it |
| `promote` red: `cosign verify` failed | the image is not signed by `publish.yml` on `main` | re-run `publish.yml`; check `SUPPLY_CHAIN_SIGNING` |
| `promote` red: `does not descend from` | a manual run named an older commit | run it again with `rollback` checked, if that is what you mean |
| `promote` red: `origin has no release branch` | the one-time setup was not done | see Setup below |
| `release-crc.sh --argocd release`: `origin/release has no promotion.yaml` | nothing has been promoted yet | let `promote.yml` run first |
| `promote` green: `still being published` | publish has not finished | nothing; publish's completion promotes |

## Rollback and setup

**Rollback.** In GitHub, Actions → promote → Run workflow. Enter the older `main` commit as `sha` and check
`rollback`. The same read-back runs. The rollback holds until the next promotion; to keep it, revert the change on
`main`.

**When Actions is down.** From a clean clone, with `gh`, `skopeo` and `cosign` installed and `GITHUB_REPOSITORY`
set: `python3 local-development/promote.py --sha <commit>`. Add `--dry-run` first to see the change without pushing.

**Setup, once.** The operator creates `release` before the first promotion:

````sh
git switch --orphan release
git commit --allow-empty -m "release: the promotion branch (#410)"
git push origin release
git switch main
````

Then, in Settings → Rules → Rulesets, protect `release` with **Restrict deletions** and **Block force pushes** only.
Do not add **Restrict updates**: GitHub Actions cannot be a bypass actor on a user-owned repository, so it would block
`promote.yml` too.

**Switching the lab to `release`.** `local-development/release-crc.sh --argocd release` reads the pinned digests back,
then points the Application at `release`. It refuses a `release` without `promotion.yaml`. `--argocd <branch>` still
deploys a test branch, with #414's older alias check and without the pin; `--argocd main` is refused. Run
`--argocd release` after testing so the lab follows promotions again.

## Chart publishing (`helm.yaml`)

`helm.yaml` is separate from promotion. When `charts/` changes on `main`, it packages the chart and publishes it to the
Helm repository on GitHub Pages, for installs outside the lab. That chart resolves `:<appVersion>` by default. The lab
does not use it.

## Diagram sources

Figure 1 is rendered from `docs/diagrams/cicd/source.html` (hand-authored SVG, light and dark palettes) by
`docs/diagrams/render.py`, which screenshots each figure in both themes and checks the page at 375 px. From the
repository root:

````sh
local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/cicd/source.html docs/diagrams/cicd promotion-pipeline
````

If this page's flow changes, change the figure, its text twin and this page together.
