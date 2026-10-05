# Releasing

Two artefacts, two cadences, and they are only related at two moments. That sentence is the whole
model, and everything below is a consequence of it.

| artefact | version | changes when | published to |
|---|---|---|---|
| the application | `pyproject.toml` `version` | MINOR per merged issue changing the image; MAJOR per closed epic | quay.io |
| the chart | `Chart.yaml` `version` | the templates or defaults change | gh-pages |

They meet only here:

- **`Chart.yaml` `appVersion`** names the application release the chart deploys. Held to
  `pyproject.toml` by `tests/test_chart_versions.py`.
- **A chart change forced by an app change** — a new value, a template that has to render something
  new. Then both move, in the same PR.

Nothing else couples them. An application release updates the chart's version fields without
requiring template changes. A template-only fix does not pretend the app changed.

The application takes exactly the next **MINOR per merged issue that changes the image**, or
the next **MAJOR per closed epic**, cut with `local-development/prepare-release.py`. Lower
components reset to zero: from `1.0.0`, those are `1.1.0` and `2.0.0`. Keep `gsd/__init__.py`
and the chart's `appVersion` in sync using the application release steps below.

CI's **App image changes bump the app version** job reads `publish.yml`'s `on.push.paths`
as the image-input allowlist. It compares the PR merge ref with the PR base SHA and requires
exactly the next MINOR or MAJOR when image content changed; unchanged, skipped, backwards,
and patch-only versions fail. An empty or unresolvable base also fails. The version assignment
lines in `pyproject.toml` and `gsd/__init__.py` themselves do not count as content; other
changes in those files do. Docs-only changes outside the allowlist need no bump, but
`local-development/README.md` is an image input and does. After another PR claims a MINOR,
merge main into the remaining PR and take the next MINOR.
A PR that moves the version without image changes (an epic's release) must also take exactly
the next MINOR or MAJOR.

---

## The whole flow

Every merge goes through one gate, then fans out to two independent workflows (`promote.yml` follows them;
"Promotion to the lab", below):

```
   pull request
        |
        |   ci.yml:  tests(3.11) · tests(3.14) · ui · chart · diagrams · image
        |            "Chart changes bump the chart version"
        |            "App image changes bump the app version"
        v
   merge to main
        |
        +---------------------------+
        |                           |
        v                           v
   publish.yml                 helm.yaml
   THE IMAGE                   THE CHART
   (below)                     (below)
```

**`publish.yml` — the image. It commits nothing to this repository; its one write there is the provenance
in the attestation store.**

```
   did an image input change?
   gsd/** · pyproject.toml · README.md · both Containerfiles · .containerignore · both build scripts
   uninstall-lists.py · both image proofs · publish.yml
        |
        +-- no --> nothing published
        |
       yes
        |
        v
   did pyproject `version` change since the previous commit?
        |
        +-- no ---> push  :0.7.0-abc1234567          IMMUTABLE, every merge.
        |                                            The dev cluster and anyone
        |                                            who wants a byte-pin.
        |
        +-- yes --> push  :0.7.0-abc1234567    and
                    push  :0.7.0                     THE ALIAS. Releases only.
                                                     This is what the chart
                                                     resolves by default.
                    push  :<chartVersion>            the chart version's label,
                                                     which helm.yaml copies again

   cannot tell? (workflow_dispatch, first push, unreadable base)
        --> immutable tag only, plus a ::warning:: naming --release-tags

   then, on the digest the registry acknowledged — one digest under every tag that run pushed:
   sbom    job   Syft -> SPDX JSON, a workflow artifact                SUPPLY_CHAIN_SBOM
   attest  job   cosign sign (keyless) · SBOM attached · SLSA          SUPPLY_CHAIN_SIGNING
                 provenance in GitHub's store — each read back
                 before the run is green
   latest  job   :latest of both images -> this run's digests, by      main only; after attest,
                 skopeo copy, then read back. Never what the chart     or after publish when
                 resolves (DESIGN_supply_chain.md D11)                 signing is off
```

**`helm.yaml` — the chart.**

```
   did charts/** change?
        |
        +-- no --> nothing published
        |
       yes
        |
        v
   does the image the chart resolves actually exist?
   (its image.tag pin if set, otherwise :<appVersion>)
        |
        +-- no --> RED RUN. Names the manual command. Deliberately not a wait:
        |          #37 was a cross-workflow timing assumption, and it reported
        |          success while publishing nothing.
        |
       yes
        |
        v
   is each image the chart resolves through appVersion that application?
   (org.opencontainers.image.version on every Linux image of the dashboard
   and the report image; a pinned tag is the operator's and is not checked)
        |
        +-- no --> RED RUN, nothing copied (#410). The tag names another build:
        |          an alias publish.yml has not moved yet, or a chart-version
        |          label on an old image. Wait for publish.yml, then re-run.
        |
       yes
        |
        v
   is :0.5.0 already another application's own alias?
   (it exists, at another digest, labelled 0.5.0)
        |
        +-- yes --> RED RUN, nothing copied (#410). Bump the chart version.
        |
        no
        |
        v
   skopeo copy  ->  :0.5.0        label the image this chart version deploys.
        |                          RETAG, never rebuild.
        v
   chart-releaser  (skips a version it has already released)
        |
        v
   gh-pages:  index.yaml + group-sync-dashboard-0.5.0.tgz
        |
        v
   attest that .tgz (SLSA provenance, GitHub's store)      SUPPLY_CHAIN_SIGNING
   only for a NEW version; a skipped version attests nothing
```

**Read the two `rel` branches carefully — they are the part people get wrong.**
The alias the chart actually resolves moves only when the application version changes. Image-changing issue PRs now
carry a MINOR bump, so their merges publish both the immutable tag and the version alias. The
publisher's release-alias decision and `<appVersion>-<10-char sha>` tag scheme are unchanged.

---

## Promotion to the lab

`main` stays the source. `.github/workflows/promote.yml` keeps a `release` branch that holds only what it read back
from the registry (#598). **During the development phase the lab tracks `main`; `release` is optional** (the
operator, 2026-10-04: "main by default; release optional"). On `main` the image race remains: a release merge moves
`appVersion` before `publish.yml` has pushed the new image, and the lab's pods sit in `ErrImagePull` until it exists.
It heals on its own, and was measured at 4.1.0, 4.4.0 and 5.1.0. `release-crc.sh --argocd release` removes it
whenever it is chosen; `--argocd main` switches back.

**At each epic release**, while the lab has no room for a second environment, the post-release walk runs on the
promoted path: `release-crc.sh --argocd release`, the walk, then `release-crc.sh --argocd main` to return to `main`
(`.claude/skills/epic/SKILL.md`, section 6).

**The end state** (the operator, 2026-10-04, once the lab is a full OpenShift cluster): two namespaces.
`group-sync-dashboard-dev` tracks `main`; `group-sync-dashboard` tracks `release`, with `promotion.yaml` as its last
values file. The development phase is the same design with one namespace: it tracks `main`, and `--argocd release`
is the opt-in. The second install needs its own Helm release name (`group-sync-dashboard-dev`), because the chart
names its cluster-scoped objects by release (SPEC_P1 §2.3, "two-namespace readiness").

`promote.yml` builds nothing. It runs after a green `publish.yml` on `main`, after a merge to
`charts/group-sync-dashboard/` or `environments/`, or by hand (Run workflow, with `sha` and `rollback`). Each run:

1. Takes `main`'s tip (or the `sha` given) and its `appVersion`.
2. Finds the last first-parent commit that touched one of `publish.yml`'s image inputs. For an unpinned image it
   reads `<appVersion>-<that commit's sha10>`, and requires `:<appVersion>` to resolve to the same digest. A push
   promotes once those exact names are ready, even if it replaced a pending publish-completion run or follows a
   rollback. While they are still being published it prints a notice and writes nothing.
3. Reads both images back: the version label on every Linux image, as `helm.yaml` checks it, and a signature from
   `publish.yml` on `main` (unless `SUPPLY_CHAIN_SIGNING` is `false`). A successful publish completion whose
   immutable tag and version alias differ is a red run; it never crosses an older image with a newer main tree.
4. Commits `charts/group-sync-dashboard/`, `environments/` and `promotion.yaml` to `release`, as a fast-forward.
   `promotion.yaml` pins both images by digest, and the Application lists it last, so the digests win.
5. When the lab tracks `release`, Argo CD syncs it.

- **What `release` holds.** The chart and `environments/` at one `main` commit, and `promotion.yaml`. The commit's
  subject is `promote: main <sha>`. Nothing on `release` has a workflow, so nothing runs or builds there.
- **One writer.** The push uses a deploy key held in the `release` environment, which admits `main` only. The
  branch's ruleset lets only deploy keys create, update or delete it, and blocks force pushes. The job's token is
  `contents: read`.
- **Rollback.** Actions → promote → Run workflow, with an older `main` commit as `sha` and `rollback` checked. The
  same checks run. It holds until the next promotion; revert on `main` to keep it.
- **Which branch the lab tracks.** `gitops/argocd-application-dashboard.yaml` tracks `main`, the default.
  `local-development/release-crc.sh --argocd release` reads both pinned digests back again, refuses a `release`
  without `promotion.yaml`, and points the Application at `release` with `promotion.yaml` as its last values file.
  `--argocd main` points it back at `main`, unchanged; `--argocd <branch>` still deploys a branch for testing.
  `release` is kept current either way, so it is ready whenever it is chosen.

**The operator's one-time steps** (in this order, before the first promotion). The runbook with each command, its
check, the record of the setup on 2026-10-05, key rotation and undoing it is `docs/guides/RELEASE_BRANCH_SETUP.md`:

1. Create the deploy key. `ssh-keygen -t ed25519 -N '' -C promote-release -f promote-release` on a laptop. Add
   `promote-release.pub` under Settings → Deploy keys, with **Allow write access**.
2. Create the environment. Settings → Environments → New environment `release`. Deployment branches and tags:
   **Selected branches and tags**, rule `main`. Add the secret `RELEASE_DEPLOY_KEY` with the content of
   `promote-release` (the private half). Delete both files from the laptop.
3. Create the branch, empty: `git commit-tree "$(git hash-object -t tree /dev/null)" -m "release starts empty"`
   prints a commit; `git push origin <that commit>:refs/heads/release`.
4. Create the ruleset. Settings → Rules → Rulesets → New branch ruleset `release`: Enforcement **Active**; target
   the branch `release`; rules **Restrict creations**, **Restrict updates**, **Restrict deletions**, **Block force
   pushes**; Bypass list **Deploy keys**, mode Always.
5. Run Actions → promote → Run workflow on `main`, with no inputs. `git ls-remote origin refs/heads/release` then
   prints a commit whose subject is `promote: main <sha>`.
6. Optional: point the lab at it with `local-development/release-crc.sh --argocd release`.

---

## Four tags, and why there are four

```
  quay.io/ephico2real/group-sync-dashboard
  ┌──────────────────────┬───────────┬──────────────────┬─────────────────────────────┐
  │ tag                  │ mutable?  │ pushed when      │ who it is for               │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.7.0-f9fa896778     │ never, by │ every merge that │ you, when you need          │
  │                      │ POLICY    │ touches an image │ byte-identical rollbacks.   │
  │ <appVersion>-<sha>   │           │ input            │ Always this exact source.   │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.7.0                │ moves on  │ only when a      │ THE CHART, by default.      │
  │                      │ an APP    │ human bumps      │ image.tag is "" and         │
  │ <appVersion>         │ release   │ pyproject version│ gsd.image resolves this.    │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ 0.6.0                │ moves on  │ at chart-release │ a human asking "which       │
  │                      │ a CHART   │ time, by retag   │ image does chart 0.6.0      │
  │ <chartVersion>       │ release   │ (never a build)  │ deploy?"                    │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ latest               │ moves on  │ every green run  │ a human or a pipeline that  │
  │                      │ EVERY     │ on main, once its│ wants the newest main build.│
  │                      │ publish   │ signature is read│ NEVER what the chart        │
  │                      │ on main   │ back (#425)      │ resolves.                   │
  └──────────────────────┴───────────┴──────────────────┴─────────────────────────────┘

  every row above is a TAG, i.e. a name. "never, by policy" is a promise this project keeps, not
  something the registry enforces — a tag's owner can always move it. If you need a guarantee
  rather than a promise, pin image.digest and skip the table entirely.

  what the chart deploys, in order of precedence:

      image.digest: "sha256:aa6a7f…"     ───►  repository@sha256:aa6a7f…
                                               IMMUTABLE BY CONSTRUCTION. a digest is a hash of
                                               the content, so nobody can repoint it.
                                               note the @ — a digest is not a tag.

      image.tag: "0.7.0-f9fa896778"      ───►  repository:0.7.0-f9fa896778
                                               immutable BY CONVENTION — this project never
                                               repoints one, but it is still a name, and a
                                               name's owner can move it.

      image.tag: ""   (the default)      ───►  repository:<appVersion>
                                               resolved via
                                               default .Chart.AppVersion .Values.image.tag
```

A malformed `image.digest` **fails the render** rather than passing through. A bad digest still forms
a reference Kubernetes accepts, so the alternative is finding out as `ImagePullBackOff` on a cluster
instead of in a pipeline; the error names `skopeo inspect` so you can get a correct one.

`values.yaml` ships `image.tag: ""`, and `gsd.image` resolves `default .Chart.AppVersion`. So the
chart deploys `:<appVersion>` unless you say otherwise.

**`imagePullPolicy` is `Always`**, which is why the distinction matters rather than being pedantry:
every container creation re-resolves the tag. On the immutable form that is a wasted round trip and
nothing else. On an alias it means a republished image is picked up on the next crash, drain,
liveness kill or scale-out. That is exactly why the alias is not republished per merge —
`docs/design/DESIGN_decouple_chart_and_app_release.md` records the review where both reviewers refused a
design that did.

**Pin when you need byte-identical rollbacks:**

```sh
helm upgrade ... --set image.tag=0.7.0-f9fa896778
```

**And verify, whichever form you pinned.** Every image `publish.yml` pushes from `main` is signed and attested by digest
under GitHub's OIDC identity — no key to fetch — and every published chart package is attested
the same way. The commands, with their outputs, are in
`HELM_DOWNLOAD_AND_INSTALL.md#7. Verify what you downloaded`; the decisions, including why there is
no GPG key, in `DESIGN_supply_chain.md`. Two repository variables turn the modules off,
`SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`; unset means on.

---

## How to cut a release

### An application release

```sh
cd local-development
./prepare-release.py --app 2.0.0 "Close the epic"          # next MAJOR: branch + commit
./prepare-release.py --app 2.0.0 "Close the epic" --pr     # ...and the pull request
```

What that does, and what you would do by hand without it:

1. Bump `version` in `local-development/pyproject.toml`.
2. Bump `__version__` in `local-development/gsd/__init__.py` to match — it is what `/api/version` and
   `gsd_build_info` report, and a test holds the two together.
3. Bump `appVersion` in `charts/group-sync-dashboard/Chart.yaml` to match.
4. Bump `Chart.yaml` `version` too, because you just changed the chart. The script derives a PATCH
   bump; pass `--chart A.B.C` when the release is more than that. CI does not catch a missed bump
   here: `ci.yml`'s chart check leaves `Chart.yaml` itself out, so an `appVersion`-only change passes it.
5. Write the `# CHART A.B.C (date), KIND: …` line above `version:` and the application paragraph
   above `appVersion:` — the file's history, newest nearest the field.
6. Turn `## Unreleased` in `docs/CHANGELOG.md` into `## Application X — chart Y — date`, with the
   reason as its first bullet, the schema line under it when the release moves the schema (below), and
   everything merged since the last release beneath it. Move every spec marked `merged` in
   `docs/specs/README.md`, and its spec's header, to `released`.
7. Run `tests/test_chart_versions.py`. The script refuses to commit if it fails, and leaves the
   edits in the tree for you to read.
8. Open the PR, merge it. `publish.yml` sees the version change and publishes both the immutable tag
   and the `:<appVersion>` alias.

The script refuses a dirty tree, a checkout other than `main` (unless `--no-commit`), a version that
does not advance, a bump that leaves a lower component non-zero, and a release branch that already
exists; it commits to `release/app-X.Y.Z` with you as the only author and never touches `main`
(`local-development/prepare-release.py#WHAT IT REFUSES`). All the edits land in one PR, or CI is red
(the chart `version` aside, step 4). That is the coupling working, not friction.

**The schema line (#300).** An application release whose image migrates the database says so, directly under
the reason:

> - **Schema N → M.** The first start on this image migrates the database one way; the pre-upgrade copy (#301) and `restore-db.sh` (#302) are the way back.

`N` is the highest `_MIGRATIONS` target at the commit that released the current application version, and `M`
the highest at HEAD, both read with `git show` before anything is edited
(`local-development/prepare-release.py#schema_since_app_release`, the helper #298's CI guard uses). The line
appears only when `M` is above `N`, and a jump of more than one says so (`Schema 20 → 22`). A chart-only release
builds no image and gets no line. A migration ships with the next MINOR in its own PR (below), so the line lands
under that issue's `## Application X.Y.0` heading, the version whose image first migrates; an epic's MAJOR then
carries none of its own, and the epic's GitHub release note lists its children's lines
(`.claude/skills/epic/SKILL.md`, section 6). Finding that commit needs the full history: on a shallow clone an
application release is refused before any edit, and the message names `actions/checkout`'s `fetch-depth: 0`
(`git fetch --unshallow` on a laptop). A version bumped by hand, without the script, gets no line: nothing else
writes it.

CI enforces the line for application releases after #300 merged (`2e7d33be`, PR #528), including hand
bumps (#543). `tests/test_migration_needs_app_release.py` reads first-parent version changes and uses
`prepare-release.py`'s highest-migration reader on each release's `store.py`. It compares successive
released images and requires exactly one `**Schema N → M.**` bullet in that version's application
section when the schema rises; a missing heading also fails. The existing hermetic CI job supplies full
history. Notes before #300 are exempt and are not rewritten: that merge introduced the schema-line
writer while the application was 2.3.0. Neither 3.0.0 nor 4.0.0 moved the schema from 20; those
headings therefore need no schema line. Releases still collected under Unreleased must retain
their own application heading when they move the schema.

### A chart-only release

Change the templates or defaults, then:

```sh
cd local-development
./prepare-release.py --chart 0.11.0 "route.tls.termination is settable"
```

Commit the template change first; the script refuses a dirty tree, so the release commit contains
only the release. It bumps `Chart.yaml` `version`, writes the history line, turns `## Unreleased` into
`## Chart A.B.C — application X.Y.Z — date`, and moves `merged` specs to `released`. Open the PR, merge. No image is built — `charts/**`
is deliberately absent from `publish.yml`'s path filter — and `helm.yaml` retags the existing image
under the new chart version.

### Neither

A docs-only or tooling PR outside `publish.yml`'s image-input paths, with no chart content change,
needs neither version bump. An image-changing issue takes the next MINOR in its PR. On its branch,
`./prepare-release.py --app X.Y.Z "Issue summary" --no-commit` makes every edit of an application
release in the tree and commits nothing: the three version fields, the chart's PATCH and both
`Chart.yaml` history lines, `## Unreleased` turned into `## Application X.Y.Z — chart A.B.C — date`
with the summary as its first bullet, and every `merged` spec moved to `released`. An issue PR
without a migration keeps the version fields, the chart version and the two history lines; it restores
`## Unreleased` with the summary as one bullet under it, and reverts the spec statuses (as `06431584`
for #598, `4eee95e4` for #616 and `86c118f0` for #619 did).

**A migration is never "neither".** A merge that adds a `_MIGRATIONS` entry (`local-development/gsd/store.py`)
without an application release leaves the chart's default image one schema behind `main`, and that image
refuses readiness on any database `main`'s code has migrated. `tests/test_migration_needs_app_release.py`
fails such a PR in CI (#298). Release the application in the same PR: on its branch, run
`./prepare-release.py --app X.Y.Z "..." --no-commit` and commit the edits, keeping the application heading
the schema line sits under. Commit the bump after the
migration: until the merge, the test takes the bump commit for the release.

---

## When GitHub Actions is unavailable

The script CI calls is the same one you run by hand, which is the point:

```sh
cd local-development
./build-and-push-external.sh                  # immutable sha tag only
./build-and-push-external.sh --release-tags    # ALSO the appVersion and chartVersion aliases
./build-and-push-report.sh --release-tags      # the report image, same flag: a release is two images
```

`--release-tags` is what makes a laptop a complete substitute for the pipeline. It is **off by
default** because a routine local build pushing `:<appVersion>` would quietly become the image every
consumer runs on their next restart. It **refuses a dirty tree**: the sha tag is honest about being
unreproducible, and an alias named for a version cannot be. Since application 0.18.0 a release is
**two images** — the chart resolves the dashboard's and the report service's at one appVersion
(`DESIGN_reporting_service.md#3.3 Two images, one version`) — so the wrapper runs with the same flag;
a release that moves one image's aliases and not the other's leaves the report pod pulling a tag that
does not exist. The same two commands are the recovery `publish.yml` names when it cannot decide
whether a push was a release, and when a release push built the dashboard image but not the report
image (`DESIGN_supply_chain.md#D10`).

`--update-values` is the other local path, and it is unrelated to releasing. It writes a pin into
your working copy of `values.yaml`, which is what you want when you build into your own registry — a
fork, an air-gapped mirror — and need the chart pointing at your image rather than ours. CI never
uses it.

---

## What can go wrong, and what it looks like

| symptom | cause | fix |
|---|---|---|
| chart release run is red at "Label the image this chart version deploys" | the image the chart resolves was never published, so there is nothing to retag | run `./build-and-push-external.sh --release-tags` and `./build-and-push-report.sh --release-tags` from a clean checkout, then re-run the release |
| chart release run is red at "Label the image this chart version deploys" with `cannot tell whether <image>:<appVersion> exists` | the registry did not answer "manifest unknown": DNS, a 401, a 429, a timeout. Nothing was copied and no chart was published; the image may well exist | re-run the release once the registry answers. Do not run the `--release-tags` scripts for this: that route is for an image that was never published |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<chartVersion> is application <chartVersion>'s own alias` | the chart's version equals an application version that already has its alias, and the copy would overwrite it. Nothing was copied | bump `version` in `charts/group-sync-dashboard/Chart.yaml`, in a pull request, to a version no application release has used |
| promote run says `whose images publish.yml has not finished`, `immutable image … is not ready` or the version alias `does not yet name` it, and promotes nothing | main's exact image is still publishing | nothing to do: its green completion, or a later chart/environment push, promotes main. If publish is red, fix it; `release` stays on the last promotion |
| promote run says a same-version image change reached `main` | two PRs chose the same next application version, so the immutable image and `:<appVersion>` alias differ | cut the next MINOR or MAJOR and let `publish.yml` finish green; never retag by hand |
| promote run says `immutable image … is not ready` after a publish run started by hand (Run workflow), and nothing promotes `main` | the image-input commit's own publish run did not push its images, and the hand run built a later commit that changed no image input: that image is tagged with the later commit's sha, while promote reads the tag of the last image-input commit | re-run the failed publish run of the image-input commit (Re-run jobs), so its own `<appVersion>-<sha10>` exists; its green completion promotes `main` |
| promote run is red with `is application X, not <appVersion>` or `carries no signature from publish.yml on main` | the tag names another build, or the digest was not signed by `publish.yml` on `main`. Nothing was written to `release` | wait for `publish.yml` to finish green, then Run workflow on promote. Never edit `release` by hand |
| promote run is red with `origin has no release branch` or `RELEASE_DEPLOY_KEY is not set` | the operator's one-time steps are not done | "Promotion to the lab", steps 1 to 5 |
| promote run is red with `is not a later commit` | a Run workflow named a commit older than the one `release` holds | check `rollback` to deploy it on purpose |
| `release-crc.sh --argocd release` says `origin/release has no promotion.yaml` | no promotion has run yet | run promote (step 5 above) |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
| a new pod runs different bits than its neighbour | somebody republished an alias between the two container creations | pin `image.tag` to the sha form |
| `ImagePullBackOff` on a fresh install | the `:<appVersion>` alias does not exist for the chart's declared appVersion — for the dashboard image, or (report pod only) for the report image | the app release was never published, or half of it was. Check `publish.yml`, then use `--release-tags` on both scripts |
| the first publish of a NEW image name (the report image was the first, 0.18.0) is red at its push, or green and then every fresh install pulls `unauthorized` for that image | quay.io creates a repository on push only if the pushing account may create one in the namespace, and creates it **private**; the chart pulls anonymously | create the repository in the quay.io UI **public**, grant the robot account write on it, then publish. Measured 2026-09-11: `group-sync-dashboard-report` did not exist before 0.18.0's first publish |
| the publish run is red at "Copy each digest to :latest, and read it back" | the registry refused the copy (the `::error::` names the image, and says that any `moved   :` line above it stands), `:latest` resolved to another digest afterwards (the `::error::` names both digests), or the read-back could not be made (the `::error::` names the image and the digest it was copied from) | the immutable tags, the aliases and the signatures are already published; at most the dashboard's `:latest` has moved ahead of the report's. Re-run the failed `latest` job; it moves both images again |
| `:latest` names an older build than the newest green publish on `main` | an older run's `latest` job was re-run after a newer run had moved the tag: a re-run copies its own run's digests | re-run the `latest` job of the newest green publish run on `main` |

**The historical failures are worth knowing, because two of them reported success.** #34 published a
chart pinning an image two merges old — including a release that was missing a data-exposure fix.
#37 published nothing at all while its run went green. Both came from CI writing the image pin back
to `main`, which is the thing this design removed. When a release step here cannot do its job it goes
**red and names the command**, deliberately, because a green run that shipped nothing is the failure
mode this repo has paid for most.
