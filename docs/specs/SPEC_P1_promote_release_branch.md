# SPEC P1 — build once and promote: `promote.yml` writes the `release` branch, and the lab's Argo CD tracks it (#598)

| | |
|---|---|
| Programme | Release safety, part B (#598, split from #410 on 2026-10-04; part A is SPEC_E8, merged as `c825182c`). Rewritten on 2026-10-04 against today's `main` from the reviewed but never merged SPEC_P1 of 2026-09-27 (tag `archive/feat/410-promote-release-branch`, `0388448c`), which is reference only |
| Batch | P — promotion |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 5.2.0, chart 0.70.3 |
| Version note | `local-development/README.md` is an image input (.github/workflows/publish.yml:84), and this change edits its `--argocd main` sentence, so `check-app-version-bump.py` requires the next application MINOR after main's 5.1.0: 5.2.0 (`docs/RELEASING.md`, "MINOR per merged issue changing the image"). No other image input changes. The chart moves only because `appVersion` moves: no template, value or RBAC change, so a PATCH, 0.70.2 to 0.70.3, as 0.70.2 was for 5.1.0. W1 stays `specified` at chart 0.71.0, above 0.70.3. Read on `6421cff7` (application 5.1.0, chart 0.70.2). A release that lands first makes the version blocks (37 to 41) fail their check; the implementing pull request corrects them here first |
| Issue | [#598](https://github.com/ephico2real2/group-sync-dashboard/issues/598) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-04 (implementer seat), from #598 and #410, the old SPEC_P1 and its two review rounds (`bb1f8b91`, `dc027eda`), the code read on `6421cff7`, read-only `gh` and `oc get` against GitHub and the lab, and the upstream documents in §2.1. No cluster, branch, ruleset or GitHub setting was changed. §7's 41 blocks were cut from a working copy and proved against a clean copy of `6421cff7` with this spec in it (§4.3) |

## How to read this spec

The plain point first. Today the lab's Argo CD Application follows `main`. A release merge changes the chart's
`appVersion` on `main` at once, but `publish.yml` needs a minute or two to build and push the image of that version.
Argo CD can sync in between, and then the pods ask for an image that does not exist yet (`ErrImagePull`). This was
measured at 4.1.0, 4.4.0 and 5.1.0 (§2.3).

The fix is "build once and promote". `main` stays the source. A new workflow, `promote.yml`, builds nothing. Once the
images of `main`'s version exist, it reads them back from the registry, writes their digests into a small values file
(`promotion.yaml`), and commits that file, with the chart and `environments/`, to a branch called `release`. The
lab's Argo CD Application follows `release` instead of `main`. So Argo CD only ever sees a chart whose images were
already checked, and it pulls them by digest.

§1 is the mandate. §2 is the research: the sources, the code, the measurements. §2a lists the alternatives. §3 is the
design, one rule per subsection, with the operator's one-time steps in §3.5. §4 maps each Definition-of-Done item to a
test and records the proof. §5 is the lab check. §6 is what a reader sees. §7 is the change as implementation blocks
(`docs/specs/README.md`, "Implementation blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_P1_promote_release_branch.md . --apply

Line citations into the code at `6421cff7` are file:line in plain text inside tables and quoted output; prose cites
`path#anchor`. This spec's index row and its header's Status move by hand: the implementing commit sets both to
`merged`.

## Orchestrator's notes

1. **What was kept from the old SPEC_P1, and what was dropped.** Kept, because both review rounds settled them:
   the `release` branch holding only the chart, `environments/` and `promotion.yaml`; the pin by digest; the
   Application listing `promotion.yaml` last; the label read on every Linux image (round 1 F1); the signature from
   `publish.yml` on `main`; `--argocd main` refused and `--argocd release` reading the pinned digests back (round 1
   F2, F5); a rollback as a manual run with `rollback` checked. Dropped, because today's `main` makes them
   unnecessary:
   - **`local-development/promote.py` (238 lines) and its runs-API search for "the tree's image".** Since #427 a pull
     request that changes the image must move the application to the next MINOR or MAJOR
     (local-development/check-app-version-bump.py:128-151, a required check, `ci.yml` "App image changes bump the
     app version"). So for any commit on `main`, `:<appVersion>` is the image of the last image change, and its
     version label says so. The search, the runs API and `actions: read` are no longer needed. The whole step is
     inline bash in `promote.yml`, tested by running it (§4).
   - **`docs/CICD.md` and its figure** (215 + 155 lines). The flow is one section of `docs/RELEASING.md`.
   - **The 17-block rename of the test branch.** The fixture's branch is renamed once, and ten calls follow it.
2. **The research does not overturn the operator's design.** The common advice is "do not use a branch per
   environment" (Kostis Kapelonis: "Promotion is never a simple Git merge"), because people merge between environment
   branches and the branches drift. Here there is one environment, and `release` is never merged into: each
   promotion writes the whole tree as a copy, from one `main` commit, by one writer. That is the shape of Argo CD
   Image Updater's git write-back to a separate branch (§2.1). The approved design stands.
3. **Correction to the brief: 5.0.0 did not race.** Argo CD started the 5.0.0 deploy at 12:50:41Z, after both 5.0.0
   images were pushed (12:47:53Z and 12:48:23Z). The races measured are 4.1.0 (recorded with pod timings), 4.4.0 and
   5.1.0 (§2.3, table 1). The 4.4.0 race was not found in any recorded report; it is measured here from the
   Application's history and the publish run's step times.
4. **"Only the promote workflow writes `release`" is possible, with a deploy key.** A ruleset on a user-owned
   repository cannot name GitHub Actions as a bypass actor (measured 422, .github/workflows/publish.yml:14-19), which
   is why the old spec left "a person can push to `release` by hand" as a residual. Rulesets can name **deploy
   keys** as a bypass actor (GitHub REST, `actor_type: DeployKey`). So the push uses a deploy key stored as a secret
   of a `release` environment that admits `main` only, and the ruleset restricts creations, updates and deletions
   to deploy keys and blocks force pushes (§3.5). **Not measured:** whether the repository's ruleset form lists
   "Deploy keys" in its bypass list for this user-owned repository (the REST reference documents the type; the
   operator's step 4 shows it). If it does not, the fallback is the old spec's ruleset (Restrict deletions and Block
   force pushes only) and the residual returns; the workflow does not change.
5. **The version blocks mirror `prepare-release.py`, by hand.** `prepare-release.py --app 5.2.0 --no-commit` was run
   on a copy. It wrote the Chart.yaml, `pyproject.toml` and `gsd/__init__.py` lines that Blocks 37 to 40 carry. It
   also turned `## Unreleased` into `## Application 5.2.0 — chart 0.70.3`, which would file SPEC_F7's unreleased
   5.1.0 entry under 5.2.0, and moved SPEC_F7 to `released`. So, as SPEC_F7 did, the CHANGELOG entry goes under
   `## Unreleased` (Block 41) and nothing else is moved.
6. **The index row.** #598 is above every issue in the rows before it (F7 is #592), so the row needs no exclusion in
   `local-development/tests/test_specs_index.py`'s rising-number assert; the index count moves from 59 to 60.
7. **A notice, not a red run, while main's version is still being published.** On a release merge the push trigger
   (the chart changed) starts `promote.yml` while `publish.yml` is still building. That run writes nothing and says
   so in a notice; the publish run's green completion promotes `main`. A failed publish is already a red run of its
   own, and the lab stays on the last promotion. Any failure of the read-back itself is red (§3.2).
   The cost: if the promotion of a published version fails (a red run), later push runs print the same notice
   until that run is re-run, because they promote only the version `release` already runs. The red run is the
   signal.
8. **A pinned tag must be signed too.** A tag pinned in `values.yaml` is not checked against `appVersion` (as in
   `helm.yaml` and `release-crc.sh`), but on the promotion path its signature is checked like any other image. Today
   no tag is pinned (charts/group-sync-dashboard/values.yaml:32, :1255).
9. **A side effect to know.** A job that names an environment creates a GitHub deployment record per run. It shows
   under the repository's Deployments; it writes nothing to the repository.
10. **The Application keeps the words `targetRevision: main` in a comment.** A walk report cites that anchor
    (reports/2026-09-29_fleet-gate-481-walk/README.md:5, "synced from `main` by Argo CD"), and
    `local-development/tests/test_docs_citations.py` failed on the first proof without it. The comment says when
    and why the Application stopped tracking `main` (Block 4), which is also the history a reader needs.

Open questions for the operator:

1. Step 4 of §3.5: confirm that "Deploy keys" is offered in the ruleset's bypass list (note 4).
2. The Grafana Application (`gitops/argocd-application-grafana.yaml`) still tracks `main`. It deploys a chart with no
   image of this repository, so it is outside #598 and is left alone.

## 1. The mandate, and what is out of scope

**#598 (the operator, 2026-10-04: "let us finish #598").** "Build once and promote", as approved on 2026-09-27:

- `main` stays the source;
- a `promote` workflow commits the verified artefact to a `release` branch;
- the lab's Argo CD Application tracks `release`.

#410's part-B list is the Definition of Done (items 4 to 9): `promote.yml` writes `release` only after reading both
images back (labels, digest, and the signature when signing is on); a failed publish is never promoted; a chart-only
merge carries the last built image; `release-crc.sh --argocd main` is refused and `--argocd release` re-reads the
pinned digests before it writes the Application; the operator's one-time steps; the lab's Application tracks
`release`, its pods run the pinned digests, and the PVC UIDs are unchanged; the release docs say what each gate
refuses and what to do.

**Out of scope:** `publish.yml` (its paths, tags, alias rule, signing, SBOM, `:latest`); every published tag;
`helm.yaml` and part A's gate; the chart's templates, values and RBAC; the published Helm chart, which still resolves
`:<appVersion>` for installs outside the lab; `release-crc.sh`'s Helm mode, its build path, and `--argocd <branch>`
for a branch under test; the Grafana Application.

## 2. Research, measured

### 2.1 Primary sources

| Source | What it says | What this spec takes |
|---|---|---|
| GitHub, [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), `workflow_run` | "This event will only trigger a workflow run if the workflow file exists on the default branch." `GITHUB_SHA` is the "Last commit on default branch". The `branches` filter names "what branches the triggering workflow must run on". At most three levels of chaining | §3.1: push → publish → promote is two levels; `github.event.workflow_run.head_sha` names the publish run's commit |
| GitHub, [Triggering a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow) | "events triggered by the `GITHUB_TOKEN` will not create a new workflow run", except `workflow_dispatch` and `repository_dispatch` | not relied on: the push is made with a deploy key, and `release` has no `.github/workflows/`, so no push to it runs a workflow (a push runs the workflows in the pushed commit) |
| GitHub REST, [Create a repository ruleset](https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28#create-a-repository-ruleset) | bypass `actor_type` is one of Integration, OrganizationAdmin, RepositoryRole, Team, DeployKey, User; rules `creation`, `update`, `deletion` "Only allow users with bypass permission"; `non_fast_forward` "Prevent users with push access from force pushing" | §3.5 step 4 |
| GitHub, [Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | "Only branches and tags that match your specified name patterns can deploy to the environment"; environment secrets are "only available to workflow jobs that reference the environment"; deployment branches "are available for all public repositories" | §3.5 step 2: the key is usable only by a job on `main` |
| `actions/checkout` README, `ssh-key` | "The SSH key is configured with the local git config, which enables your scripts to run authenticated git commands. The post-job step removes the SSH key." "The public key for github.com is always implicitly added." | §3.4: `git push` uses the key; no extra action |
| Argo CD v3.5.3, docs/user-guide/tracking_strategies.md:46-48 | "Argo CD will continually compare live state against the resource manifests defined at the tip of the specified branch" | §3.7 |
| Argo CD v3.5.3, docs/user-guide/helm.md:48, :64, :150-157 | "Order of precedence is `parameters > valuesObject > values > valueFiles > helm repository values.yaml`"; a values path is "relative to the root directory of the Helm chart"; "the relative order between entries is preserved … `final.yaml` # passed last, highest precedence" | §3.7: `promotion.yaml` last |
| Kostis Kapelonis, [Stop using branches for deploying to different GitOps environments](https://octopus.com/blog/stop-using-branches-deploying-different-gitops-environments) | "Promotion is never a simple Git merge"; environments as folders or files, not branches | Orchestrator's notes 2: `release` is never merged into |
| Argo CD Image Updater, [Update methods](https://argocd-image-updater.readthedocs.io/en/stable/basics/update-methods/) | git write-back stores the overrides in Git, and can "create a new branch from the base branch, and push to this new branch instead … useful when the default branch is protected" | Orchestrator's notes 2; §2a A2 |
| The old SPEC_P1 (`0388448c`) and its reviews `bb1f8b91`, `dc027eda` | the design, nine questions, two review rounds | Orchestrator's notes 1 |

### 2.2 The code, read on `6421cff7`

| Fact | Where |
|---|---|
| The lab's Application tracks `main` with automated sync, prune and selfHeal; one values file | gitops/argocd-application-dashboard.yaml:35, :39-40, :52-55 |
| `publish.yml` runs on a push to `main` that touches an image input; `local-development/README.md` is one | .github/workflows/publish.yml:52-93 (README at :84) |
| One publish at a time, never cancelled | .github/workflows/publish.yml:101-103 |
| It signs each digest keyless and reads the signature back as `publish.yml@refs/heads/main`, with cosign v3.1.3 | .github/workflows/publish.yml:455-456, :458-462, :483-486 |
| An image change must move the application to the next MINOR or MAJOR (required check) | local-development/check-app-version-bump.py:128-151; .github/workflows/ci.yml:169-186 |
| Part A: `helm.yaml` reads the version label of every Linux image of both images before it copies anything; a pinned tag is not checked | .github/workflows/helm.yaml:145, :171-189 (the `reporting.image.tag` reader), :195-210 (`image_versions`), :251-279 |
| Both images are labelled with the version and the 10-character commit they were built from | local-development/Containerfile:184-185; local-development/build-and-push-external.sh:132 |
| The chart renders `repository@digest` when `image.digest` / `reporting.image.digest` is set, and the digest wins over the tag | charts/group-sync-dashboard/templates/_helpers.tpl:85-90, :753-758; charts/group-sync-dashboard/values.yaml:54, :1256 |
| The chart reads no file outside its directory: no symlink under `charts/`, and `.Files.Get` names `scripts/` and `dashboards/` only | `find charts -type l` (empty); templates/backup-offsite.yaml:78, grafana-dashboard.yaml:32, recovery.yaml:14 |
| `release-crc.sh`'s mode table; `--argocd <branch>` reads both `:<appVersion>` images back before it writes the Application; the Application is written once, merged locally | local-development/release-crc.sh:20-47, :218-278, :282-292, :171-191 |
| `--argocd` without `--values` leaves `valueFiles` to the Application file | local-development/release-crc.sh:121-128, :181-182 |
| The docs that say `--argocd main` | local-development/README.md:86; .claude/skills/epic/SKILL.md:63, :141-148; local-development/release-crc.sh:50, :281 |
| CI's hermetic test selection | .github/workflows/ci.yml:238 (`pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py`) |

### 2.3 The measurements

All read-only, on 2026-10-04.

**Table 1 — the race, release by release.** Argo CD's deploy start is the lab Application's `status.history`
(`oc get applications.argoproj.io group-sync-dashboard -n openshift-gitops -o jsonpath='{range .status.history[*]}…'`).
The push times are the publish run's "Build and push the image" and "Build and push the report image" steps
(`gh run view <id> --json jobs`). Each merge moved the application version (`git show <sha>:…pyproject.toml`
against its first parent).

| Release (merge) | Argo CD deploy started | dashboard image pushed | report image pushed | Raced? |
|---|---|---|---|---|
| 4.1.0 (`a38c3b0c`) | not in the Application's history (it keeps 10) | 21:56:19Z | 21:56:48Z | yes, recorded: pods in `ErrImagePull`; containers started 21:56:40Z and 21:57:31Z (`reports/2026-10-03_data-only-seal-270/README.md`, "Before the check") |
| 4.4.0 (`451ff688`) | 05:26:10Z | 05:26:17Z | 05:26:49Z | yes: deploy 7 s and 39 s before the pushes |
| 4.5.0 (`d5ca0f54`) | 07:32:22Z | 07:28:08Z | 07:28:37Z | no |
| 4.6.0 (`a92399d5`) | 08:16:41Z | 08:14:31Z | 08:14:59Z | no |
| 4.7.0 (`1d008176`) | 09:20:23Z | 09:16:33Z | 09:17:10Z | no |
| 5.0.0 (`704943a1`) | 12:50:41Z | 12:47:53Z | 12:48:23Z | no (Orchestrator's notes 3) |
| 5.1.0 (`93079676`) | 17:28:10Z | 17:29:06Z | 17:29:39Z | yes: deploy 56 s and 89 s before the pushes |

**The lab** (`KUBECONFIG=…/kc-crc`, read-only):

    $ oc get applications.argoproj.io group-sync-dashboard -n openshift-gitops -o jsonpath='…'
    main ["../../environments/crc.yaml"] {"prune":true,"selfHeal":true} | Synced 6421cff7716621aa69869ac3ec702b6de03c0476 Healthy
    $ oc get csv -n openshift-gitops-operator
    openshift-gitops-operator.v1.22.0         Succeeded
    $ oc -n openshift-gitops exec deploy/openshift-gitops-server -- argocd version --client --short
    argocd: v3.5.3+c9c369e

**GitHub** (`gh api`, read-only): the repository is `owner.type: User`, public, default branch `main`; its branches
are `main` and `gh-pages` (`git ls-remote`); it has no ruleset (`/rulesets` is `[]`), no deploy key (`/keys` is 0)
and one environment, `github-pages`. `main`'s classic protection: `enforce_admins: true`, `allow_force_pushes:
false`, `allow_deletions: false`, reviews required, seven required checks.

**The images of 5.1.0** (`oc image info quay.io/ephico2real/<image>:5.1.0 --filter-by-os='linux/.*' --show-multiarch -o json`):

    sha256:e5f4536a91cc20b17358b37216e4e1e13e1f836cfc096a7b827411e982d0ecfc  5.1.0 930796769f   (group-sync-dashboard)
    sha256:a77de47602b949e2c1018be5bbff451b07c13fb4fab5e01beb329fe5e2f67a7b  5.1.0 930796769f   (group-sync-dashboard-report)

Both are single manifests (no list digest), labelled with the version and the release merge's commit.

**`helm.yaml` has never been red on a release merge in the window read:** its last 40 runs on `main`, 2026-09-28 to
2026-10-04, are all `success` (`gh run list --workflow helm.yaml -L 40`), because it first calls `ci.yml` and reaches
its label step after `publish.yml` has finished (e.g. 5.1.0: publish 17:28:07Z → 17:30:44Z, helm 17:28:07Z →
17:40:24Z).

**The chart with a promotion file** (`helm template … -f environments/crc.yaml -f promotion.yaml`, digests
`sha256:0…01` and `sha256:0…02`): every dashboard and report container image renders as `repository@sha256:…`
(four dashboard and five report references), and no `:<appVersion>` reference to either image remains.

## 2a. Alternatives considered

| | Option | Taken? | Why |
|---|---|---|---|
| A1 | A `release` branch written by a workflow, pins by digest in `promotion.yaml`, the Application tracking it | **yes** | the operator's approved design (#410, 2026-09-27); Argo CD sees only checked images; one environment, never merged (Orchestrator's notes 2) |
| A2 | Argo CD Image Updater writes the digests back | no | a second controller to install and run on the lab, and an Argo-specific mechanism; the repository's rule is Helm first, Argo CD a conduit |
| A3 | Keep `main`; Argo CD's sync waits (a sync window, or manual sync) | no | still syncs whatever `main` says once the window opens; nothing checks the image |
| A4 | Fast-forward `release` to the checked `main` commit (no `promotion.yaml`) | no | the lab would still pull `:<appVersion>`, a tag that can move after the check; "commits the verified artefact" is a pin |
| A5 | Pin the immutable `<appVersion>-<sha10>` tag instead of the digest | no | a tag the registry can repoint; the chart already prefers a digest (values.yaml:54) |
| B1 | Find the image through the runs API (the old `promote.py`) | no | #427's required check makes `:<appVersion>` the image of the last image change (Orchestrator's notes 1) |
| B2 | The step inline in `promote.yml`, run by tests | **yes** | the repository's own pattern for `helm.yaml`'s label step (local-development/tests/test_supply_chain.py, `TestTheChartPublishLabelGate`) |
| C1 | Trigger on `publish` completion, on a push to the chart or `environments/`, and by hand | **yes** | covers an image release, a chart-only merge, a values-only merge and a rollback |
| C2 | Trigger on `helm.yaml`'s completion instead of a push | no | `helm.yaml` waits for the whole `ci.yml` (about 12 minutes, §2.3) and does not run for `environments/` |
| D1 | A notice when `main`'s version is still being published | **yes** | the expected state for a minute on every release merge (Orchestrator's notes 7) |
| D2 | A red run in that state | no | a false alarm on every release merge |
| E1 | Push with a deploy key from a `release` environment; ruleset bypass "Deploy keys" | **yes** | the only way on a user-owned repository to let the workflow, and nothing else, write `release` (Orchestrator's notes 4) |
| E2 | Push with `GITHUB_TOKEN` (`contents: write`); ruleset without Restrict updates | fallback | the old design; leaves a hand push possible |
| F1 | Copy `helm.yaml`'s two readers, held equal by a test | **yes** | one rule in three places, the way `helm.yaml` and `release-crc.sh` already share the `reporting.image.tag` reader |
| F2 | Move the readers into a shared script | no | it changes part A's `helm.yaml`, outside #598 |

## 3. The design

### 3.1 When it runs, and what it promotes

`promote.yml` runs on three triggers (Block 1):

- `workflow_run` of `publish`, completed, on `main`; the job runs only when the conclusion is `success`;
- a push to `main` touching `charts/group-sync-dashboard/**`, `environments/**` or `promote.yml` itself;
- `workflow_dispatch`, with `sha` (empty means `main`'s tip) and `rollback`.

Every run promotes `main`'s tip, unless `sha` is given. Runs are one at a time (`concurrency: promote-release`, never
cancelled). A pending run that GitHub replaces loses nothing, because the next run reads `main`'s tip again.

### 3.2 The ready rule, and the checks

1. **Ready.** The run knows one application version whose images exist: the version at the publish run's commit
   (`workflow_run`), the version `release` already runs (`push`), or the version asked for (`workflow_dispatch`). If
   `main`'s `appVersion` is another version, its publish run is still going: the run prints a notice, writes
   nothing, and exits 0. That publish run's completion promotes `main`.
2. **Where.** The commit must be on `main`. If `release` already holds a later commit, the run is refused unless
   `rollback` is checked.
3. **Each image** (the dashboard, then the report), at its pin in `values.yaml` or at `:<appVersion>`: the digest
   is read once (`skopeo inspect --format '{{.Digest}}'`). An unpinned image must carry `appVersion` as its
   `org.opencontainers.image.version` label on every Linux image behind that digest (`helm.yaml`'s
   `image_versions`, verbatim). With signing on (`SUPPLY_CHAIN_SIGNING` is not `false`), `cosign verify` must find a
   signature from `publish.yml@refs/heads/main` on that digest. Any failure is a red run that writes nothing.

### 3.3 What `release` holds

One commit per promotion, on top of what `release` held (a fast-forward, never forced), with the subject
`promote: main <full sha>`. Its tree is exactly:

- `charts/group-sync-dashboard/` at that `main` commit (the chart reads nothing outside itself, §2.2);
- `environments/` at that commit;
- `promotion.yaml`: a comment naming the commit, then `image.repository`, `image.digest`,
  `reporting.image.repository` and `reporting.image.digest`.

The tree is built in a scratch index (`git read-tree --prefix`, `git write-tree`, `git commit-tree`), so the
checkout is untouched. If the tree equals the one on `release`, nothing is pushed.

### 3.4 One writer

The job holds `contents: read`. The checkout is made with `ssh-key: ${{ secrets.RELEASE_DEPLOY_KEY }}`, so the
`git push` at the end uses the deploy key. The secret belongs to the `release` environment, which only `main` can
deploy to. A first step fails, with the setup pointer, when the secret is missing.

### 3.5 The operator's one-time steps

These are GitHub settings, not code. In this order, before the first promotion (also in `docs/RELEASING.md`,
"Promotion to the lab", Block 31):

1. **The deploy key.** On a laptop: `ssh-keygen -t ed25519 -N '' -C promote-release -f promote-release`. Add
   `promote-release.pub` under Settings → Deploy keys, with **Allow write access**.
2. **The environment.** Settings → Environments → New environment `release`. Deployment branches and tags:
   **Selected branches and tags**, rule `main`. Add the environment secret `RELEASE_DEPLOY_KEY`, the content of
   `promote-release` (the private half). Delete both files from the laptop.
3. **The branch, empty.** `git commit-tree "$(git hash-object -t tree /dev/null)" -m "release starts empty"` prints
   a commit; `git push origin <that commit>:refs/heads/release`.
4. **The ruleset.** Settings → Rules → Rulesets → New branch ruleset `release`: Enforcement **Active**; target the
   branch `release`; **Restrict creations**, **Restrict updates**, **Restrict deletions**, **Block force pushes**;
   Bypass list: **Deploy keys**, Always (Orchestrator's notes 4, open question 1).
5. **The first promotion.** It runs on its own when the implementing pull request's publish run is green (§5);
   at any other time, Actions → promote → Run workflow on `main`, no inputs. Check:
   `git ls-remote origin refs/heads/release` prints one commit, and
   `git log -1 --format=%s origin/release` prints `promote: main <sha>`.
6. **The lab.** `local-development/release-crc.sh --argocd release` (§5).

Until steps 1 to 3 are done, every promote run is red and names this section.

### 3.6 `release-crc.sh`

- `--argocd main` and `--argocd refs/heads/main` exit 2 before any fetch or cluster call (Block 8).
- `--argocd release` requires `promotion.yaml` on `origin/release`, reads both pinned `repository@digest` back with
  the same `oc image info --filter-by-os='linux/.*'` check as today, and writes `valueFiles:
  [../../environments/crc.yaml, ../../promotion.yaml]` (Blocks 10 to 14). With `--values X`, X comes first.
- Every other Argo mode now names `valueFiles` (`../../environments/crc.yaml`, or X) explicitly, because the
  Application file's default ends with `promotion.yaml`, which only `release` has (Block 9). This is what those modes
  already sent: the file's default was `crc.yaml` alone.

### 3.7 The Application

`targetRevision: release`, and `valueFiles: [../../environments/crc.yaml, ../../promotion.yaml]` (Blocks 2 to 5).
Argo CD keeps the order and the last file wins (helm.md:150-157), so the digests win over anything in `crc.yaml`.
`valuesObject` (the `clusters` override) still outranks both and names no image. Merging this file changes nothing on
the lab: the live Application is written only by `release-crc.sh`.

### 3.8 The guarantee, and what stays outside it

**The guarantee:** with the one-time steps done, Argo CD syncs only trees that `promote.yml` wrote after reading both
images back, and it pulls exactly the digests it read. `release-crc.sh --argocd release` reads them back again before
it writes the Application.

**Outside it:** a person with the deploy key's private half (it is deleted from the laptop in step 2); a hand edit
of the live Application (`oc edit`); a digest deleted from quay.io after promotion (a missing image, never a wrong
one; published images are never deleted); with `SUPPLY_CHAIN_SIGNING=false`, labels are not proof of origin;
`--argocd <branch>`, bare `--argocd` and Helm mode, which are for testing; the published Helm chart, which still
resolves `:<appVersion>` (part A's gate guards it).

### 3.9 What does not change, and the test that holds it

| Unchanged | Held by |
|---|---|
| `publish.yml`, `helm.yaml`, every published tag | no block edits them; `test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with` (no copy, no build in `promote.yml`) |
| the chart's templates, values and RBAC | RBAC rendered before and after with `crc.yaml`: 30 rule and binding lines each, REMOVED 0, ADDED 0 (§4.3) |
| `--argocd <branch>`: the alias read-back, a pin honoured, the waiter | the existing `test_release_crc.py` tests, on a branch named `pr-test` |
| bare `--argocd` and `--argocd --values X` | `test_argocd_writes_the_application_once_with_everything_in_it`, unchanged |
| `helm.yaml`'s two readers | `test_the_label_readers_are_helm_yamls` holds the copies equal |

## 4. Tests

### 4.1 One test per Definition-of-Done item

| Definition of Done (#410 part B) | Test |
|---|---|
| 6: `release` written only after both images are read back; both pinned by digest; signature checked; `release` holds only the chart, `environments/` and `promotion.yaml` | `test_promote.py::test_a_publish_completion_promotes_main_with_both_images_pinned_by_digest` |
| 6: a failed or unfinished publish is never promoted | `test_a_run_promotes_nothing_while_mains_version_is_still_being_published`; `test_an_image_that_is_not_mains_application_is_refused[stale-dashboard-alias, stale-report-alias, stale-arm64-child]`; `test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_cosign` |
| 6: a chart-only merge carries the last built image | `test_a_chart_only_merge_carries_the_images_release_already_runs` |
| rollback; one at a time; nothing written twice | `test_an_older_commit_needs_rollback_and_the_same_tree_twice_changes_nothing`; `test_one_promotion_at_a_time_read_only_token_and_the_deploy_key_from_the_release_environment` |
| only `main` is promoted; no `release` means a red run | `test_a_commit_that_is_not_on_main_is_refused`; `test_without_a_release_branch_nothing_is_promoted`; `test_it_runs_after_a_successful_publish_on_main_and_after_a_chart_or_environment_merge` |
| a pinned tag is promoted as pinned | `test_a_pinned_tag_is_promoted_as_pinned` |
| nothing builds; the cosign publish.yml signs with | `test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with` |
| one label rule in three places | `test_the_label_readers_are_helm_yamls` |
| 8: the Application tracks `release` with `promotion.yaml` last | `test_the_application_and_release_crc_name_the_file_promote_writes` |
| 7: `--argocd main` refused | `test_release_crc.py::test_argocd_main_is_refused_before_anything_is_fetched_or_written[main, refs/heads/main]` |
| 7: `--argocd release` re-reads the pinned digests, lists `promotion.yaml` last, refuses a missing pin and a wrong digest | `test_argocd_release_reads_the_pinned_digests_back_and_lists_promotion_yaml_last`; `test_argocd_release_without_a_promotion_is_refused_before_anything_is_written`; `test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release` |
| 7: every other Argo mode names `valueFiles` | `test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit` (edited) |
| 8: the lab tracks `release`, pods on the pinned digests, PVC UIDs unchanged | §5, on the lab |
| 9: the release docs | `docs/RELEASING.md` "Promotion to the lab" and five troubleshooting rows (Blocks 31, 32) |

### 4.2 Each test fails without the change, and why

- `test_promote.py` on `6421cff7`: every test fails, because `.github/workflows/promote.yml` does not exist (§4.3).
- Each check of the step was switched off in a copy of the applied tree, one at a time, and the tests that name it
  failed (§4.3, the mutation runs): the label check (3 tests), the ready rule (1), the ancestry check (1), the
  signature check (2), and carrying an extra directory into `release` (1).
- `test_release_crc.py` with `6421cff7`'s script (`RELEASE_CRC_UNDER_TEST`): the four new tests (five cases) and the
  edited `valueFiles` test fail; the other 31 pass (§4.3).

### 4.3 The proof
Every command ran on 2026-10-04 with the repository's venv (Python 3.14, `PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=$PWD` from `local-development`). "Main" is a copy of `6421cff7` with this spec, its index row and the
index count; "applied" is the same copy after `apply-spec-blocks.py --apply`. Python 3.11, CI's other leg, was not
run here.

| Check | Command | Result |
|---|---|---|
| the blocks | `python3 local-development/apply-spec-blocks.py docs/specs/SPEC_P1_promote_release_branch.md .`, then `--apply`, in a clean git copy | `41 blocks check out across 13 files`; each of the 13 files byte-equal (`cmp`) to the working copy the blocks were cut from |
| CI's hermetic selection, main | `pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` (.github/workflows/ci.yml:238) | `7630 passed, 23 skipped, 698 deselected, 5 xfailed, 2 warnings in 397.53s` |
| the same, applied | the same | `7651 passed, 23 skipped, 698 deselected, 5 xfailed, 2 warnings in 410.82s` (21 more: `test_promote.py`'s 16 and five new `test_release_crc.py` cases) |
| the new tests on main's code | `test_promote.py` and `test_release_crc.py` copied onto main | `5 failed, 11 errors` (`FileNotFoundError`: no `promote.yml`); `6 failed, 31 passed` (the five new cases and the edited `valueFiles` test) |
| the same, applied | `pytest tests/test_promote.py tests/test_release_crc.py` | `16 passed`; `37 passed` |
| each check held (mutation) | one check switched off in a copy of the applied `promote.yml`, then `test_promote.py` | label check off: 3 failed (the three stale cases); ready rule off: 1 failed; ancestry check off: 1 failed; signature check off: 2 failed; `local-development/` carried into `release`: 1 failed |
| the workflows | actionlint v1.7.12 | nothing in `promote.yml`; the repository's other 2 findings are main's (2 before, 2 after) |
| the scripts | `bash -n` and `shellcheck -S warning` on `release-crc.sh` and on the promotion step extracted from the YAML | clean |
| RBAC | Roles, ClusterRoles and their bindings rendered with `environments/crc.yaml`, before and after, one line per rule or binding | 30 and 30; REMOVED 0, ADDED 0 |
| the render with a promotion file | `helm template … -f environments/crc.yaml -f promotion.yaml` | every dashboard and report image is `repository@sha256:…` (§2.3) |
| Markdown | `markdownlint-cli2` on the five edited `.md` files | 8 findings before, 8 after: none new |

## 5. On the lab (the implementing pull request)

Nothing here was run for this spec. The implementer runs it with the lab's kubeconfig, after review and after the
operator's steps 1 to 4 (§3.5):

1. Record the UIDs of the `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` PVCs.
2. Before the merge, pause the dashboard Application's auto-sync. This pull request moves `appVersion` to 5.2.0 on
   `main` while the lab still tracks `main`: the race one last time.
3. After the merge: `gh run list --workflow publish.yml -L 1` and `gh run list --workflow promote.yml -L 3`. Expected:
   publish `success`; the push-triggered promote green with the notice "whose images publish.yml has not finished";
   the `workflow_run` promote green, with two `image   : … -> sha256:…` lines and `promoted: main <sha> -> release`.
4. Read `release`: `git ls-tree --name-only origin/release` prints `charts`, `environments`, `promotion.yaml`, and
   each digest in `git show origin/release:promotion.yaml` equals `oc image info quay.io/ephico2real/<image>:5.2.0`'s.
5. `local-development/release-crc.sh --argocd release`. Expected: `the digests in promotion.yaml`, two
   `image   : …@sha256:… is application 5.2.0` lines, then Synced/Healthy at `release`'s tip. The pods' image IDs end
   in the pinned digests: `oc get pods -n group-sync-dashboard -o jsonpath='{..imageID}'`.
6. `local-development/release-crc.sh --argocd main` exits 2 and changes nothing.
7. The first chart-only merge that follows is promoted by its push run, at once, with the same digests.
8. Record the PVC UIDs again; they must be unchanged. The evidence goes under `reports/<date>_<slug>/` and on #598,
   pinned to the full merge sha.

## 6. What a reader sees, and what it costs

- **The lab** runs a release only once its images are published and checked. Between the merge and the promotion
  (about the publish run's 2.5 minutes, §2.3) the lab keeps running the previous release, instead of sitting in
  `ErrImagePull`.
- **The Actions tab** gains `promote` runs: one per publish run, one per chart or `environments/` merge, each about
  half a minute (not measured: no run exists yet). A release merge shows one green notice run and one promoting run.
- **The repository** gains one branch, `release`, one commit per promotion, a deploy key, an environment, a ruleset
  and a GitHub deployment record per run.
- **Registry calls per promotion:** for each image, one digest read, one raw-manifest read and one config read per
  Linux image, and one `cosign verify`. Nothing is copied, tagged or deleted.
- **What does not change:** the image, its tags and signatures; the published chart; the dashboard's RBAC; any
  install outside the lab.

## 7. Implementation blocks

Forty-one blocks over thirteen files, in apply order: the workflow, the Application, `release-crc.sh`, the tests,
the docs, the versions, the CHANGELOG. Lines added / removed per file (the proof tree): `promote.yml` +234,
`test_promote.py` +289, `test_release_crc.py` +84 −19, `release-crc.sh` +40 −14, `docs/RELEASING.md` +55,
`docs/CHANGELOG.md` +13, `.claude/skills/epic/SKILL.md` +9 −10, `gitops/argocd-application-dashboard.yaml` +8 −5,
`Chart.yaml` +5 −2, `local-development/README.md` +3 −2, `gitops/README.md` +1, `pyproject.toml` and
`gsd/__init__.py` +1 −1 each.

### Block 1 — `.github/workflows/promote.yml`: the workflow: three triggers, the ready rule, the read-back, the commit to `release`

<!-- block: .github/workflows/promote.yml | create -->

```yaml
# Promote main to the `release` branch the lab's Argo CD tracks (#598, docs/RELEASING.md "Promotion to the lab").
#
# BUILD ONCE, PROMOTE THE ARTEFACT. publish.yml builds and signs each image once; this workflow builds
# nothing. It reads both images back (the version label on every Linux image, the signature when signing is
# on), pins them by digest in `promotion.yaml`, and commits that file with the chart and environments/ at that
# main commit to `release`. Argo CD syncs `release`, so it never sees a chart whose images are not published
# yet: on main, a release merge moved appVersion before publish.yml had pushed the image, and the pods sat in
# ErrImagePull (4.1.0, 4.4.0, 5.1.0).
#
# THE ONLY WRITER. The push uses the deploy key in the `release` environment, the one bypass actor of the
# branch's ruleset; the job holds `contents: read`. That environment admits `main` only.
name: promote

on:
  # A publish run's completion: the images of the version it published now exist and are signed.
  workflow_run:
    workflows: [publish]
    types: [completed]
    branches: [main]
  # A merge publish.yml skips (the chart or environments/ only) still reaches the lab.
  push:
    branches: [main]
    paths:
      - 'charts/group-sync-dashboard/**'
      - 'environments/**'
      - '.github/workflows/promote.yml'
  # A re-run, the first promotion after `release` is created, or a rollback to an older commit on main.
  workflow_dispatch:
    inputs:
      sha:
        description: The commit on main to promote (empty = main's tip)
        required: false
        default: ''
      rollback:
        description: Allow a commit older than the one release holds
        type: boolean
        default: false

# One promotion at a time. A replaced pending run loses nothing: every run promotes main as it finds it.
concurrency:
  group: promote-release
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  promote:
    if: >-
      github.repository == 'ephico2real2/group-sync-dashboard'
      && github.ref == 'refs/heads/main'
      && (github.event_name != 'workflow_run' || github.event.workflow_run.conclusion == 'success')
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: release    # RELEASE_DEPLOY_KEY lives here; its deployment branch policy admits main only
    steps:
      - name: Check the release deploy key is configured
        shell: bash
        env:
          KEY_SET: ${{ secrets.RELEASE_DEPLOY_KEY != '' }}
        run: |
          if [ "${KEY_SET}" != true ]; then
            echo "::error::RELEASE_DEPLOY_KEY is not set in the release environment, so nothing can be promoted."
            echo "::error::The operator's one-time steps are in docs/RELEASING.md, \"Promotion to the lab\"."
            exit 1
          fi

      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: main
          fetch-depth: 0
          ssh-key: ${{ secrets.RELEASE_DEPLOY_KEY }}

      - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
        if: vars.SUPPLY_CHAIN_SIGNING != 'false'
        with:
          cosign-release: v3.1.3   # the cosign publish.yml signs with

      - name: Read both images back and promote
        shell: bash
        env:
          REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
          REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
          SIGNING: ${{ vars.SUPPLY_CHAIN_SIGNING }}
          EVENT: ${{ github.event_name }}
          RUN_SHA: ${{ github.event.workflow_run.head_sha }}
          SHA: ${{ inputs.sha }}
          ROLLBACK: ${{ inputs.rollback }}
          IDENTITY: https://github.com/${{ github.repository }}/.github/workflows/publish.yml@refs/heads/main
          ISSUER: https://token.actions.githubusercontent.com
        run: |
          set -euo pipefail
          CHART=charts/group-sync-dashboard/Chart.yaml
          VALUES=charts/group-sync-dashboard/values.yaml
          REPO="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
          # helm.yaml's appVersion form, so the two read one Chart.yaml the same way.
          app_version_at() {
            git show "$1:${CHART}" 2>/dev/null | sed -n 's/^appVersion: "\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)"$/\1/p' | head -1 || true
          }
          # helm.yaml's reader of the version label of every Linux image behind a reference, verbatim
          # (tests/test_promote.py holds it equal).
          image_versions() {
            python3 - "$1" "$2" <<'PY'
          import json, subprocess, sys
          repo, reference = sys.argv[1], sys.argv[2]
          def raw(*args):
              done = subprocess.run(["skopeo", "inspect", "--raw", *args], capture_output=True, text=True)
              if done.returncode != 0:
                  sys.exit(done.stderr.strip() or "skopeo inspect --raw " + " ".join(args) + " failed")
              return json.loads(done.stdout)
          top = raw(f"docker://{repo}{reference}")
          refs = ([f"docker://{repo}@{m['digest']}" for m in top["manifests"] if (m.get("platform") or {}).get("os") == "linux"]
                  if "manifests" in top else [f"docker://{repo}{reference}"])
          images = [{"config": raw("--config", ref)} for ref in refs]
          print(", ".join(sorted({(i.get("config", {}).get("config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "") for i in images})))
          PY
          }

          git fetch -q origin "+refs/heads/main:refs/remotes/origin/main"
          if ! git fetch -q origin "+refs/heads/release:refs/remotes/origin/release"; then
            echo "::error::origin has no release branch, so nothing was promoted. The operator creates it once"
            echo "::error::(docs/RELEASING.md, \"Promotion to the lab\"), then runs this workflow by hand."
            exit 1
          fi
          target=$(git rev-parse --verify "${SHA:-origin/main}^{commit}")
          if ! git merge-base --is-ancestor "${target}" origin/main; then
            echo "::error::${target} is not on main; only a commit on main is promoted."
            exit 1
          fi
          from=$(git log -1 --format=%s origin/release | sed -n 's/^promote: main \([0-9a-f]\{40\}\)$/\1/p')
          if [ -n "${from}" ] && ! git merge-base --is-ancestor "${from}" "${target}" && [ "${ROLLBACK}" != true ]; then
            echo "::error::release holds main ${from}, and ${target} is not a later commit. To deploy an older"
            echo "::error::commit, run this workflow with its sha and rollback checked."
            exit 1
          fi

          # The images are known to be published for one application version: the one the triggering publish run
          # built, the one release already runs (a push), or the one asked for by hand. Any other version is still
          # being published, and that run's completion promotes main.
          app_version=$(app_version_at "${target}")
          case "${EVENT}" in
            workflow_run) ready=$(app_version_at "${RUN_SHA}") ;;
            push)         ready=$(app_version_at origin/release) ;;
            *)            ready="${app_version}" ;;
          esac
          if [ -z "${app_version}" ]; then
            echo "::error::cannot read appVersion from ${CHART} at ${target}."
            exit 1
          fi
          if [ "${app_version}" != "${ready}" ]; then
            echo "::notice::main ${target:0:10} is application ${app_version}, whose images publish.yml has not finished;"
            echo "::notice::its completion promotes main. Nothing was promoted by this run."
            exit 0
          fi

          values=$(mktemp)
          git show "${target}:${VALUES}" > "${values}"
          PINNED=$(sed -n 's/^  tag: "\(.*\)"[[:blank:]]*$/\1/p' "${values}" | head -1)
          # helm.yaml's reporting.image.tag reader, verbatim but for the file it reads (tests/test_promote.py).
          REPORT_PINNED=$(python3 -c '
          import sys
          in_reporting = in_image = False
          for raw in sys.stdin.read().splitlines():
              line = raw.split("#", 1)[0].rstrip()
              if line == "reporting:":
                  in_reporting, in_image = True, False
                  continue
              if in_reporting and line and not line.startswith(" "):
                  in_reporting = in_image = False
              if in_reporting and line == "  image:":
                  in_image = True
                  continue
              if in_image and line.startswith("    tag:"):
                  print(line.split(":", 1)[1].strip().strip("\"'\''"))
                  break
              if in_image and line.startswith("  ") and not line.startswith("    "):
                  in_image = False
          ' < "${values}")
          promotion="# Written by .github/workflows/promote.yml for main ${target}: the images it read back, by digest."
          for spec in "${REPO}|${PINNED}|image:" "${REPO}-report|${REPORT_PINNED}|reporting:"; do
            IFS='|' read -r name this_pin key <<< "${spec}"
            tag="${this_pin:-${app_version}}"
            if ! digest=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${name}:${tag}"); then
              echo "::error::cannot read ${name}:${tag} (skopeo's message is above), so nothing was promoted."
              echo "::error::Re-run this workflow once the registry answers, or once publish.yml is green."
              exit 1
            fi
            # A pinned tag is the operator's choice for that image and is not checked against appVersion, as in
            # helm.yaml; its signature still is.
            if [ -z "${this_pin}" ]; then
              if ! version=$(image_versions "${name}" "@${digest}"); then
                echo "::error::cannot read the labels of ${name}@${digest}, so nothing was promoted."
                exit 1
              fi
              if [ "${version}" != "${app_version}" ]; then
                echo "::error::${name}:${tag} is application ${version:-unknown}, not ${app_version} (#410), so nothing"
                echo "::error::was promoted. Wait for publish.yml on the release merge, then re-run this workflow."
                exit 1
              fi
            fi
            if [ "${SIGNING}" != false ]; then
              if ! cosign verify --certificate-identity "${IDENTITY}" --certificate-oidc-issuer "${ISSUER}" \
                   "${name}@${digest}" > /dev/null; then
                echo "::error::${name}@${digest} carries no signature from publish.yml on main, so nothing was promoted."
                exit 1
              fi
            fi
            echo "image   : ${name}:${tag} -> ${digest}"
            if [ "${key}" = "image:" ]; then
              promotion+=$'\n'"image:"$'\n'"  repository: ${name}"$'\n'"  digest: ${digest}"
            else
              promotion+=$'\n'"reporting:"$'\n'"  image:"$'\n'"    repository: ${name}"$'\n'"    digest: ${digest}"
            fi
          done

          # The release tree: the chart and environments/ at that commit, and promotion.yaml. Built in a scratch
          # index, so nothing in this checkout changes, and committed on top of release: a fast-forward.
          export GIT_INDEX_FILE
          GIT_INDEX_FILE="$(mktemp -d)/index"
          git read-tree --empty
          git read-tree --prefix=charts/group-sync-dashboard/ "${target}:charts/group-sync-dashboard"
          git read-tree --prefix=environments/ "${target}:environments"
          blob=$(printf '%s\n' "${promotion}" | git hash-object -w --stdin)
          git update-index --add --cacheinfo "100644,${blob},promotion.yaml"
          tree=$(git write-tree)
          unset GIT_INDEX_FILE
          if [ "${tree}" = "$(git rev-parse 'origin/release^{tree}')" ]; then
            echo "release already holds this chart and these digests; nothing to promote."
            exit 0
          fi
          commit=$(git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
            commit-tree "${tree}" -p origin/release -m "promote: main ${target}" -m "Application ${app_version}, read back by promote.yml.")
          git push origin "${commit}:refs/heads/release"
          echo "promoted: main ${target} -> release ${commit}"
```


### Block 2 — `gitops/argocd-application-dashboard.yaml` (1 of 4): the header names `release` and `promotion.yaml`

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->

```yaml
# The dashboard chart installed by OpenShift GitOps from THIS git repository — charts/group-sync-dashboard
# on main with environments/crc.yaml — as release `group-sync-dashboard` into group-sync-dashboard, the
# same namespace and release name the Helm loop used. One instance, not two: the chart's ClusterRoles
# and ClusterRoleBindings are named by the release, so a second release of the same name elsewhere
```

```yaml
# The dashboard chart installed by OpenShift GitOps from THIS git repository — charts/group-sync-dashboard
# on the `release` branch with environments/crc.yaml and promotion.yaml, the digests promote.yml read back
# (#598, docs/RELEASING.md "Promotion to the lab") — as release `group-sync-dashboard` into group-sync-dashboard, the
# same namespace and release name the Helm loop used. One instance, not two: the chart's ClusterRoles
# and ClusterRoleBindings are named by the release, so a second release of the same name elsewhere
```


### Block 3 — `gitops/argocd-application-dashboard.yaml` (2 of 4): iterating on a branch: crc.yaml alone

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->

```yaml
# owned them), so history, sessions and tickets carry over; the first sync adopts the rest.
#
# Iterating on a branch: point targetRevision at it, or pause (`argocd app set group-sync-dashboard
# --sync-policy none`) and use release-crc.sh — never both at once, Argo's prune and selfHeal would
# undo a hand-installed release.
#
# What this instance does NOT have: the lab's mock cluster — crc.yaml lists it, but its credentials
```

```yaml
# owned them), so history, sessions and tickets carry over; the first sync adopts the rest.
#
# Iterating on a branch: `release-crc.sh --argocd <branch>` points targetRevision at it with crc.yaml alone
# (only `release` has promotion.yaml), or pause (`argocd app set group-sync-dashboard --sync-policy none`) and
# use release-crc.sh — never both at once, Argo's prune and selfHeal would undo a hand-installed release.
#
# What this instance does NOT have: the lab's mock cluster — crc.yaml lists it, but its credentials
```


### Block 4 — `gitops/argocd-application-dashboard.yaml` (3 of 4): `targetRevision: release`, and why

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->

```yaml
  source:
    repoURL: https://github.com/ephico2real2/group-sync-dashboard.git
    targetRevision: main
    path: charts/group-sync-dashboard
    helm:
```

```yaml
  source:
    repoURL: https://github.com/ephico2real2/group-sync-dashboard.git
    # targetRevision: main until #598, when Argo CD synced release merges before their images were pushed.
    targetRevision: release
    path: charts/group-sync-dashboard
    helm:
```


### Block 5 — `gitops/argocd-application-dashboard.yaml` (4 of 4): `promotion.yaml` last

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->

```yaml
      valueFiles:
        - ../../environments/crc.yaml
      valuesObject:
        clusters:
```

```yaml
      valueFiles:
        - ../../environments/crc.yaml
        - ../../promotion.yaml          # last, so the promoted digests win
      valuesObject:
        clusters:
```


### Block 6 — `local-development/release-crc.sh` (1 of 11): the mode table's two `release` rows

<!-- block: local-development/release-crc.sh | edit -->

```bash
#   --argocd <branch> --values X    Argo     GitHub @ <branch>   same                  [../../X]          X present at
#                                                                                                         origin/<branch>
#   --build-only                    (none)   —                   built, NOT pushed     —                  —
#   --allow-dirty --argocd          REFUSED: Argo deploys a commit and a dirty tree has none — the image
```

```bash
#   --argocd <branch> --values X    Argo     GitHub @ <branch>   same                  [../../X]          X present at
#                                                                                                         origin/<branch>
#   --argocd release                Argo     GitHub @ release    the digests in        crc.yaml, then     promotion.yaml
#                                                                promotion.yaml, read  promotion.yaml     on origin/release
#                                                                back again
#   --argocd release --values X     Argo     GitHub @ release    same                  X, then            X present at
#                                                                                      promotion.yaml     origin/release
#   --build-only                    (none)   —                   built, NOT pushed     —                  —
#   --allow-dirty --argocd          REFUSED: Argo deploys a commit and a dirty tree has none — the image
```


### Block 7 — `local-development/release-crc.sh` (2 of 11): `--argocd main` refused in the table; the typical loop ends with `--argocd release`

<!-- block: local-development/release-crc.sh | edit -->

```bash
#   --build-only --argocd|--values  REFUSED: neither applies to a build (measured by review: `--argocd main
#                                   --build-only` ran the cutover with nothing built).
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd main. The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298) — a guarantee
# about the RELEASE COMMIT, not about the tag on quay, which the branch path reads back (below).
```

```bash
#   --build-only --argocd|--values  REFUSED: neither applies to a build (measured by review: `--argocd main
#                                   --build-only` ran the cutover with nothing built).
#   --argocd main                   REFUSED: the lab runs what promote.yml read back (#598); deploy
#                                   --argocd release.
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd release once promote.yml is green. The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298) — a guarantee
# about the RELEASE COMMIT, not about the tag on quay, which the branch path reads back (below).
```


### Block 8 — `local-development/release-crc.sh` (3 of 11): `--argocd main` and `refs/heads/main` exit 2 before anything is fetched

<!-- block: local-development/release-crc.sh | edit -->

```bash
  exit 2
fi

# The values file, repository-relative (this script runs in local-development/). Helm reads it from
```

```bash
  exit 2
fi
# Syncing main is what let Argo CD pull a chart whose image was not published yet (#598).
case "$ARGO_REVISION" in
  main|refs/heads/main)
    echo "ERROR: --argocd main is refused: the lab runs what promote.yml read back. Deploy --argocd release" >&2
    echo "       (docs/RELEASING.md, \"Promotion to the lab\"); --argocd <branch> still deploys a branch to test." >&2
    exit 2 ;;
esac

# The values file, repository-relative (this script runs in local-development/). Helm reads it from
```


### Block 9 — `local-development/release-crc.sh` (4 of 11): every Argo mode names its values file

<!-- block: local-development/release-crc.sh | edit -->

```bash
else
  RELEASE_VALUES="${RELEASE_VALUES:-../environments/crc.yaml}"
  ARGO_VALUES=""                                       # the Application's own default
fi

```

```bash
else
  RELEASE_VALUES="${RELEASE_VALUES:-../environments/crc.yaml}"
  ARGO_VALUES="../../environments/crc.yaml"            # named every time: the file's default ends with promotion.yaml
fi

```


### Block 10 — `local-development/release-crc.sh` (5 of 11): `release` lists `promotion.yaml` after it

<!-- block: local-development/release-crc.sh | edit -->

```bash
    {"name": "reporting.image.repository", "value": image[2]}, {"name": "reporting.image.tag", "value": image[3]},
] if image else []}
if values:
    helm["valueFiles"] = [values]
print(json.dumps({"spec": {"source": {"targetRevision": revision, "helm": helm}}}))
PY
```

```bash
    {"name": "reporting.image.repository", "value": image[2]}, {"name": "reporting.image.tag", "value": image[3]},
] if image else []}
helm["valueFiles"] = [values] + (["../../promotion.yaml"] if revision == "release" else [])
print(json.dumps({"spec": {"source": {"targetRevision": revision, "helm": helm}}}))
PY
```


### Block 11 — `local-development/release-crc.sh` (6 of 11): the read-back's comment and locals

<!-- block: local-development/release-crc.sh | edit -->

```bash
# list is refused without --filter-by-os, and this workstation's OS is not the node's), and every one
# must carry the label. A repository overridden in values, or a digest pin, is not resolved: the
# default repository is checked.
published_image_is_the_release() {
  local revision="$1" chart values app_version pinned report_pinned repo spec name this_pin ref version
  chart=$(git show "${revision}:charts/group-sync-dashboard/Chart.yaml") || return 1
  values=$(git show "${revision}:charts/group-sync-dashboard/values.yaml") || return 1
```

```bash
# list is refused without --filter-by-os, and this workstation's OS is not the node's), and every one
# must carry the label. A repository overridden in values, or a digest pin, is not resolved: the
# default repository is checked. On `release` the images are the digests promote.yml pinned in
# promotion.yaml, read back again here; a `release` without that file is refused.
published_image_is_the_release() {
  local revision="$1" chart values app_version pinned report_pinned repo spec this_pin ref version promoted="" refs
  chart=$(git show "${revision}:charts/group-sync-dashboard/Chart.yaml") || return 1
  values=$(git show "${revision}:charts/group-sync-dashboard/values.yaml") || return 1
```


### Block 12 — `local-development/release-crc.sh` (7 of 11): on `release`, the refs are the pinned digests; no `promotion.yaml` is refused

<!-- block: local-development/release-crc.sh | edit -->

```bash
    return 1
  fi
  for spec in "${repo}|${pinned}" "${repo}-report|${report_pinned}"; do
    name="${spec%%|*}" this_pin="${spec#*|}"
    if [ -n "$this_pin" ]; then
      echo "image   : ${name}:${this_pin} (pinned in values.yaml; not checked against appVersion)"
      continue
    fi
    ref="${name}:${app_version}"
    # oc answers one object for a single manifest and an array for a list; a mixed list prints both.
    if ! version=$(oc image info "$ref" --filter-by-os='linux/.*' --show-multiarch -o json 2>/dev/null | python3 -c '
```

```bash
    return 1
  fi
  refs=("${repo}:${app_version}|${pinned}" "${repo}-report:${app_version}|${report_pinned}")
  if [ "$ARGO_REVISION" = release ]; then
    if ! promoted=$(git show "${revision}:promotion.yaml" 2>/dev/null); then
      echo "ERROR: origin/release has no promotion.yaml: promote.yml has not promoted anything yet." >&2
      return 1
    fi
    # promote.yml writes this file: image.* two spaces deep, reporting.image.* four.
    refs=("$(printf '%s\n' "$promoted" | sed -n 's/^  repository: //p' | head -1)@$(printf '%s\n' "$promoted" | sed -n 's/^  digest: //p' | head -1)|"
          "$(printf '%s\n' "$promoted" | sed -n 's/^    repository: //p' | head -1)@$(printf '%s\n' "$promoted" | sed -n 's/^    digest: //p' | head -1)|")
  fi
  for spec in "${refs[@]}"; do
    ref="${spec%%|*}" this_pin="${spec#*|}"
    if [ -n "$this_pin" ]; then
      echo "image   : ${ref%:*}:${this_pin} (pinned in values.yaml; not checked against appVersion)"
      continue
    fi
    # oc answers one object for a single manifest and an array for a list; a mixed list prints both.
    if ! version=$(oc image info "$ref" --filter-by-os='linux/.*' --show-multiarch -o json 2>/dev/null | python3 -c '
```


### Block 13 — `local-development/release-crc.sh` (8 of 11): a missing pinned digest says what it is

<!-- block: local-development/release-crc.sh | edit -->

```bash
print(", ".join(sorted({(i.get("config", {}).get("config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "") for i in images})))'); then
      echo "ERROR: ${ref} is not in the registry, or cannot be read. Argo CD would pull it." >&2
      echo "       publish.yml pushes the :${app_version} aliases on the merge that moved pyproject's version;" >&2
      echo "       wait for that run, or publish them by hand: ./build-and-push-external.sh --release-tags" >&2
```

```bash
print(", ".join(sorted({(i.get("config", {}).get("config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "") for i in images})))'); then
      echo "ERROR: ${ref} is not in the registry, or cannot be read. Argo CD would pull it." >&2
      [ -n "$promoted" ] && echo "       It is a digest promote.yml read back: never delete a published image." >&2
      echo "       publish.yml pushes the :${app_version} aliases on the merge that moved pyproject's version;" >&2
      echo "       wait for that run, or publish them by hand: ./build-and-push-external.sh --release-tags" >&2
```


### Block 14 — `local-development/release-crc.sh` (9 of 11): the branch path says which images it hands Argo CD

<!-- block: local-development/release-crc.sh | edit -->

```bash

# --argocd <branch> with no build: point the Application at that branch and its chart's default
# image, e.g. `--argocd main` after a merge. Any other --argocd use builds this commit first.
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  echo "argocd  : ${APP_NAME} -> revision ${ARGO_REVISION} (${EXPECTED_REVISION:0:10}), the chart's default image"
  published_image_is_the_release "$EXPECTED_REVISION" || exit 1
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
```

```bash

# --argocd <branch> with no build: point the Application at that branch and its chart's default
# image, or at `release` and its promoted digests after a merge. Any other --argocd use builds this commit first.
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  images="the chart's default image"
  [ "$ARGO_REVISION" = release ] && images="the digests in promotion.yaml"
  echo "argocd  : ${APP_NAME} -> revision ${ARGO_REVISION} (${EXPECTED_REVISION:0:10}), ${images}"
  published_image_is_the_release "$EXPECTED_REVISION" || exit 1
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
```


### Block 15 — `local-development/release-crc.sh` (10 of 11): the values line prints only for `--values` (the branch path)

<!-- block: local-development/release-crc.sh | edit -->

```bash
    helm uninstall "${IMAGE}" -n "${NAMESPACE}" --wait --timeout 5m
  fi
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$ARGO_REVISION"
  exec ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "${EXPECTED_REVISION}"
```

```bash
    helm uninstall "${IMAGE}" -n "${NAMESPACE}" --wait --timeout 5m
  fi
  [ -n "$VALUES_FILE" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$ARGO_REVISION"
  exec ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "${EXPECTED_REVISION}"
```


### Block 16 — `local-development/release-crc.sh` (11 of 11): the values line prints only for `--values` (the build path)

<!-- block: local-development/release-crc.sh | edit -->

```bash
  fi
  echo "argocd  : ${APP_NAME} -> revision ${COMMIT}, image ${TAG}"
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$COMMIT" "${INTERNAL%:*}" "$TAG" "${REPORT_INTERNAL%:*}" "$TAG"
  ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "$(git rev-parse HEAD)"
```

```bash
  fi
  echo "argocd  : ${APP_NAME} -> revision ${COMMIT}, image ${TAG}"
  [ -n "$VALUES_FILE" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$COMMIT" "${INTERNAL%:*}" "$TAG" "${REPORT_INTERNAL%:*}" "$TAG"
  ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "$(git rev-parse HEAD)"
```


### Block 17 — `local-development/tests/test_promote.py`: the promotion step, run against stubs

<!-- block: local-development/tests/test_promote.py | create -->

```python
"""promote.yml: the lab's `release` branch holds only what was read back from the registry (#598, SPEC_P1).

The promotion step is RUN, as GitHub runs `shell: bash`, in a real git repository with a bare `origin`, against
test_supply_chain.py's stub skopeo and a stub cosign. Real git writes the `release` commit; only the registry and
Sigstore are replaced. The workflow's shape (its triggers, its scopes, its one writer) is read from the YAML.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess

import pytest
import yaml

from test_supply_chain import APP, CHART_FILE, DASHBOARD, HELM, PUBLISH, REPORT, SKOPEO_STUB, VALUES_FILE, _jobs, _push, _released, _step

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTE = REPO / ".github" / "workflows" / "promote.yml"
APPLICATION = REPO / "gitops" / "argocd-application-dashboard.yaml"
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"
STEP = "Read both images back and promote"
IDENTITY = "https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main"

COSIGN_STUB = r'''#!/usr/bin/env bash
printf 'cosign %s\n' "$*" >> "$STUB_LOG"
for ref in $STUB_UNSIGNED; do [ "${@: -1}" = "$ref" ] && { echo "no signatures found" >&2; exit 1; }; done
exit 0
'''


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: pathlib.Path, message: str, files: dict[str, str]) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    _git(repo, "push", "-q", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def _chart(version: str) -> str:
    return CHART_FILE.read_text().replace(f'\nappVersion: "{APP}"\n', f'\nappVersion: "{version}"\n', 1)


@pytest.fixture
def lab(tmp_path: pathlib.Path):
    """main with the real chart files, environments/ and files release must not carry; origin's `release` is the
    operator's one-time orphan commit with an empty tree."""
    repo, origin = tmp_path / "repo", tmp_path / "origin.git"
    repo.mkdir()
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))
    _commit(repo, "base", {
        "charts/group-sync-dashboard/Chart.yaml": _chart("0.0.1"),
        "charts/group-sync-dashboard/values.yaml": VALUES_FILE.read_text(),
        "charts/group-sync-dashboard/templates/x.yaml": "kind: ConfigMap\n",
        "charts/openshift-grafana/Chart.yaml": "name: openshift-grafana\n",
        "environments/crc.yaml": "logLevel: DEBUG\n",
        "local-development/app.py": "print('code')\n",
        ".github/workflows/ci.yml": "name: ci\n",
    })
    empty = _git(repo, "hash-object", "-t", "tree", "-w", "/dev/null")
    start = _git(repo, "commit-tree", empty, "-m", "release starts empty")
    _git(repo, "push", "-q", "origin", f"{start}:refs/heads/release")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool, stub in (("skopeo", SKOPEO_STUB), ("cosign", COSIGN_STUB)):
        (bindir / tool).write_text(stub)
        (bindir / tool).chmod(0o755)
    (tmp_path / "step.sh").write_text(_step(_jobs(PROMOTE)["promote"], STEP)["run"])
    return {"repo": repo, "origin": origin, "tmp": tmp_path, "bin": bindir, "start": start}


def promote(lab, registry: dict, *, event: str = "dispatch", run_sha: str = "", sha: str = "", rollback: bool = False,
            signing: str = "", unsigned: str = "") -> tuple[subprocess.CompletedProcess, str]:
    state, log = lab["tmp"] / "registry.json", lab["tmp"] / "calls.log"
    state.write_text(json.dumps(registry))
    log.write_text("")
    env = {**os.environ, "PATH": f"{lab['bin']}:{os.environ['PATH']}", "STUB_REGISTRY": str(state), "STUB_LOG": str(log),
           "STUB_UNREACHABLE": "", "STUB_UNSIGNED": unsigned, "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example",
           "SIGNING": signing, "EVENT": event, "RUN_SHA": run_sha, "SHA": sha, "ROLLBACK": "true" if rollback else "false",
           "IDENTITY": IDENTITY, "ISSUER": "https://token.actions.githubusercontent.com"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "step.sh")],
                          cwd=lab["repo"], env=env, capture_output=True, text=True)
    return done, log.read_text()


def release(lab) -> str:
    return _git(lab["origin"], "rev-parse", "refs/heads/release")


def promotion(lab) -> dict:
    return yaml.safe_load(_git(lab["origin"], "show", "release:promotion.yaml"))


def _main_at(lab, version: str) -> str:
    return _commit(lab["repo"], f"application {version}", {"charts/group-sync-dashboard/Chart.yaml": _chart(version),
                                                           "local-development/app.py": f"print('{version}')\n"})


# ── What a promotion writes ───────────────────────────────────────────────────────────────────


def test_a_publish_completion_promotes_main_with_both_images_pinned_by_digest(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    done, log = promote(lab, registry, event="workflow_run", run_sha=tip)
    assert done.returncode == 0, done.stdout + done.stderr
    head = release(lab)
    assert _git(lab["origin"], "log", "-1", "--format=%s", head) == f"promote: main {tip}"
    assert _git(lab["origin"], "rev-parse", f"{head}^") == lab["start"], "a fast-forward of what release held"
    assert _git(lab["origin"], "ls-tree", "--name-only", head).split() == ["charts", "environments", "promotion.yaml"]
    assert _git(lab["origin"], "ls-tree", "--name-only", f"{head}:charts").split() == ["group-sync-dashboard"]
    assert _git(lab["origin"], "show", f"{head}:charts/group-sync-dashboard/Chart.yaml") == _chart(APP).rstrip("\n")
    pins = promotion(lab)
    assert pins == {"image": {"repository": DASHBOARD, "digest": registry["tags"][f"{DASHBOARD}:{APP}"]},
                    "reporting": {"image": {"repository": REPORT, "digest": registry["tags"][f"{REPORT}:{APP}"]}}}
    for name, digest in ((DASHBOARD, pins["image"]["digest"]), (REPORT, pins["reporting"]["image"]["digest"])):
        assert f"cosign verify --certificate-identity {IDENTITY} --certificate-oidc-issuer " \
               f"https://token.actions.githubusercontent.com {name}@{digest}" in log


def test_a_run_promotes_nothing_while_mains_version_is_still_being_published(lab) -> None:
    """The race #598 removes: a release merge moves appVersion before publish.yml has pushed it."""
    older = _main_at(lab, "0.9.0")
    tip = _main_at(lab, APP)
    for event, run_sha in (("push", ""), ("workflow_run", older)):
        done, log = promote(lab, {"tags": {}, "manifests": {}, "blobs": {}}, event=event, run_sha=run_sha)
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"main {tip[:10]} is application {APP}" in done.stdout and "Nothing was promoted" in done.stdout
        assert "skopeo" not in log and release(lab) == lab["start"]


def test_a_chart_only_merge_carries_the_images_release_already_runs(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    assert promote(lab, registry, event="workflow_run", run_sha=tip)[0].returncode == 0
    pins = promotion(lab)
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    done, _ = promote(lab, registry, event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {chart_only}"
    assert _git(lab["origin"], "show", "release:charts/group-sync-dashboard/templates/x.yaml") == "kind: Secret"
    assert promotion(lab) == pins


# ── What is refused, and changes nothing ──────────────────────────────────────────────────────


@pytest.mark.parametrize("image, versions", [(DASHBOARD, ("0.24.0",)), (REPORT, ("0.24.0",)), (DASHBOARD, (APP, "0.24.0"))],
                         ids=["stale-dashboard-alias", "stale-report-alias", "stale-arm64-child"])
def test_an_image_that_is_not_mains_application_is_refused(lab, image, versions) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    _push(registry, image, APP, *versions)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"{image}:{APP} is application" in done.stdout and "0.24.0" in done.stdout
    assert release(lab) == lab["start"]


def test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_cosign(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    report = f"{REPORT}@{registry['tags'][f'{REPORT}:{APP}']}"
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, unsigned=report)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"{report} carries no signature from publish.yml on main" in done.stdout
    assert release(lab) == lab["start"]
    done, log = promote(lab, registry, event="workflow_run", run_sha=tip, signing="false", unsigned=report)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "cosign" not in log


def test_an_older_commit_needs_rollback_and_the_same_tree_twice_changes_nothing(lab) -> None:
    older = _main_at(lab, "0.9.0")
    tip = _main_at(lab, APP)
    registry = _released()
    _push(registry, DASHBOARD, "0.9.0", "0.9.0")
    _push(registry, REPORT, "0.9.0", "0.9.0")
    assert promote(lab, registry)[0].returncode == 0
    promoted = release(lab)
    done, _ = promote(lab, registry)
    assert done.returncode == 0 and "nothing to promote" in done.stdout and release(lab) == promoted
    done, _ = promote(lab, registry, sha=older)
    assert done.returncode == 1 and "rollback checked" in done.stdout and release(lab) == promoted
    done, _ = promote(lab, registry, sha=older, rollback=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {older}"
    assert promotion(lab)["image"]["digest"] == registry["tags"][f"{DASHBOARD}:0.9.0"]
    assert tip != older


def test_a_commit_that_is_not_on_main_is_refused(lab) -> None:
    _main_at(lab, APP)
    _git(lab["repo"], "checkout", "-qb", "topic")
    (lab["repo"] / "environments" / "crc.yaml").write_text("logLevel: INFO\n")
    _git(lab["repo"], "commit", "-qam", "topic")
    _git(lab["repo"], "push", "-q", "origin", "topic")
    done, _ = promote(lab, _released(), sha=_git(lab["repo"], "rev-parse", "HEAD"))
    assert done.returncode == 1 and "is not on main" in done.stdout
    assert release(lab) == lab["start"]


def test_without_a_release_branch_nothing_is_promoted(lab) -> None:
    _main_at(lab, APP)
    _git(lab["origin"], "update-ref", "-d", "refs/heads/release")
    done, log = promote(lab, _released())
    assert done.returncode == 1 and "origin has no release branch" in done.stdout
    assert "skopeo" not in log


def test_a_pinned_tag_is_promoted_as_pinned(lab) -> None:
    values = VALUES_FILE.read_text().replace('\n  tag: ""\n', '\n  tag: "1.4.0"\n', 1)
    _commit(lab["repo"], "pin", {"charts/group-sync-dashboard/values.yaml": values})
    _main_at(lab, APP)
    registry = _released()
    pinned = _push(registry, DASHBOARD, "1.4.0", "1.4.0")
    _push(registry, DASHBOARD, APP, "0.24.0")          # the unpinned alias is not what the chart deploys
    done, _ = promote(lab, registry)
    assert done.returncode == 0, done.stdout + done.stderr
    assert promotion(lab)["image"]["digest"] == pinned


# ── The workflow's shape ──────────────────────────────────────────────────────────────────────


def _workflow() -> dict:
    return yaml.safe_load(PROMOTE.read_text())


def test_it_runs_after_a_successful_publish_on_main_and_after_a_chart_or_environment_merge() -> None:
    wf = _workflow()
    on = wf.get("on", wf.get(True))
    assert on["workflow_run"] == {"workflows": ["publish"], "types": ["completed"], "branches": ["main"]}
    assert on["push"]["branches"] == ["main"]
    assert on["push"]["paths"] == ["charts/group-sync-dashboard/**", "environments/**", ".github/workflows/promote.yml"]
    assert set(on["workflow_dispatch"]["inputs"]) == {"sha", "rollback"}
    condition = " ".join(wf["jobs"]["promote"]["if"].split())
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.event.workflow_run.conclusion == 'success'" in condition


def test_one_promotion_at_a_time_read_only_token_and_the_deploy_key_from_the_release_environment() -> None:
    wf = _workflow()
    job = wf["jobs"]["promote"]
    assert wf["concurrency"] == {"group": "promote-release", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read"} and "permissions" not in job
    assert job["environment"] == "release"
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["ssh-key"] == "${{ secrets.RELEASE_DEPLOY_KEY }}"


def test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with() -> None:
    text = PROMOTE.read_text()
    for word in ("podman", "docker build", "buildah", "build-and-push", "cosign sign", "skopeo copy"):
        assert word not in text, word
    installer = re.compile(r"uses: (sigstore/cosign-installer@\S+)[\s\S]*?cosign-release: (v[\d.]+)")
    assert installer.search(text).groups() == installer.search(PUBLISH.read_text()).groups()
    assert f"IDENTITY: https://github.com/${{{{ github.repository }}}}/.github/workflows/publish.yml@refs/heads/main" in text


def test_the_label_readers_are_helm_yamls() -> None:
    """One rule in three places, as release-crc.sh and helm.yaml already hold it (#410)."""
    ours, theirs = _step(_jobs(PROMOTE)["promote"], STEP)["run"], _step(_jobs(HELM)["release"], "Label the image")["run"]
    function = re.compile(r"^image_versions\(\) \{\n.*?^\}$", re.M | re.S)
    walker = re.compile(r"^REPORT_PINNED=\$\(python3 -c '\n(.*?)^' < ", re.M | re.S)
    assert function.search(ours).group(0) == function.search(theirs).group(0)
    assert walker.search(ours).group(1) == walker.search(theirs).group(1)


def test_the_application_and_release_crc_name_the_file_promote_writes() -> None:
    source = yaml.safe_load(APPLICATION.read_text())["spec"]["source"]
    assert source["targetRevision"] == "release"
    assert source["helm"]["valueFiles"] == ["../../environments/crc.yaml", "../../promotion.yaml"]
    assert "git update-index --add --cacheinfo \"100644,${blob},promotion.yaml\"" in PROMOTE.read_text()
    script = RELEASE_CRC.read_text()
    assert '"../../promotion.yaml"' in script and 'git show "${revision}:promotion.yaml"' in script
```


### Block 18 — `local-development/tests/test_release_crc.py` (1 of 13): the fixture's branch is `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
        "image:\n  repository: quay.io/example/group-sync-dashboard\n  tag: \"\"\n"
        "reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: \"\"\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
```

```python
        "image:\n  repository: quay.io/example/group-sync-dashboard\n  tag: \"\"\n"
        "reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: \"\"\n")
    _git(repo, "init", "-q", "-b", "pr-test")   # --argocd main is refused (#598); a test branch stands in
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
```


### Block 19 — `local-development/tests/test_release_crc.py` (2 of 13): the fixture pushes `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    bindir = tmp_path / "bin"
    bindir.mkdir()
```

```python
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "pr-test")
    bindir = tmp_path / "bin"
    bindir.mkdir()
```


### Block 20 — `local-development/tests/test_release_crc.py` (3 of 13): the fetch-failure and single-branch tests use `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
def test_argocd_branch_fetch_failure_is_fatal(lab):
    _git(lab["repo"], "remote", "set-url", "origin", str(lab["tmp"] / "gone.git"))
    r = run(lab, "--argocd", "main", "--values", "environments/crc.yaml")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "branch main is not on origin, or origin is unreachable" in r.stderr
    assert "helm" not in calls(lab) and "oc" not in calls(lab)


def test_argocd_branch_works_in_a_single_branch_clone(lab):
    _git(lab["repo"], "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
    _git(lab["repo"], "checkout", "-qb", "topic")
    (lab["repo"] / "environments" / "topic.yaml").write_text("x: 1\n")
```

```python
def test_argocd_branch_fetch_failure_is_fatal(lab):
    _git(lab["repo"], "remote", "set-url", "origin", str(lab["tmp"] / "gone.git"))
    r = run(lab, "--argocd", "pr-test", "--values", "environments/crc.yaml")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "branch pr-test is not on origin, or origin is unreachable" in r.stderr
    assert "helm" not in calls(lab) and "oc" not in calls(lab)


def test_argocd_branch_works_in_a_single_branch_clone(lab):
    _git(lab["repo"], "config", "remote.origin.fetch", "+refs/heads/pr-test:refs/remotes/origin/pr-test")
    _git(lab["repo"], "checkout", "-qb", "topic")
    (lab["repo"] / "environments" / "topic.yaml").write_text("x: 1\n")
```


### Block 21 — `local-development/tests/test_release_crc.py` (4 of 13): the values-on-origin test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 1\n")
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "other")   # committed, NOT pushed
    r = run(lab, "--argocd", "main", "--values", "environments/other.yaml")
    assert r.returncode == 1 and "does not exist on origin/main" in r.stderr


```

```python
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 1\n")
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "other")   # committed, NOT pushed
    r = run(lab, "--argocd", "pr-test", "--values", "environments/other.yaml")
    assert r.returncode == 1 and "does not exist on origin/pr-test" in r.stderr


```


### Block 22 — `local-development/tests/test_release_crc.py` (5 of 13): the branch-path test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
def test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
```

```python
def test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "pr-test")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
```


### Block 23 — `local-development/tests/test_release_crc.py` (6 of 13): the branch path names `valueFiles`; the waiter test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": []}}
    # the branch moved on origin but the Application's `main` did not: the old status must not satisfy the waiter
    synced_status(lab, "0" * 40)
    r = run(lab, "--argocd", "main", ARGOCD_WAIT_INTERVAL="1")
    assert r.returncode == 1, "the waiter accepted a status for a commit that is not origin/main"


```

```python
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "pr-test",
                                        "helm": {"parameters": [], "valueFiles": ["../../environments/crc.yaml"]}}
    # the branch moved on origin but the Application's `main` did not: the old status must not satisfy the waiter
    synced_status(lab, "0" * 40)
    r = run(lab, "--argocd", "pr-test", ARGOCD_WAIT_INTERVAL="1")
    assert r.returncode == 1, "the waiter accepted a status for a commit that is not origin/pr-test"


```


### Block 24 — `local-development/tests/test_release_crc.py` (7 of 13): the stale-dashboard test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard", "0.24.0")
    r = run(lab, "--argocd", "main")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is application 0.24.0, not {_version()} (#410)" in r.stderr
```

```python
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard", "0.24.0")
    r = run(lab, "--argocd", "pr-test")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is application 0.24.0, not {_version()} (#410)" in r.stderr
```


### Block 25 — `local-development/tests/test_release_crc.py` (8 of 13): the stale-report test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard-report", "0.24.0")
    r = run(lab, "--argocd", "main")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application 0.24.0" in r.stderr
```

```python
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard-report", "0.24.0")
    r = run(lab, "--argocd", "pr-test")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application 0.24.0" in r.stderr
```


### Block 26 — `local-development/tests/test_release_crc.py` (9 of 13): the not-pushed-yet test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
def test_argocd_branch_refuses_an_alias_publish_has_not_pushed_yet(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main", STUB_IMAGES="")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is not in the registry" in r.stderr
```

```python
def test_argocd_branch_refuses_an_alias_publish_has_not_pushed_yet(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "pr-test", STUB_IMAGES="")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is not in the registry" in r.stderr
```


### Block 27 — `local-development/tests/test_release_crc.py` (10 of 13): the pin helper returns to `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
        f'reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: "{report_tag}"\n')
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", branch); _git(lab["repo"], "push", "-q", "origin", branch)
    _git(lab["repo"], "checkout", "-q", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", branch))

```

```python
        f'reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: "{report_tag}"\n')
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", branch); _git(lab["repo"], "push", "-q", "origin", branch)
    _git(lab["repo"], "checkout", "-q", "pr-test")
    synced_status(lab, _git(lab["repo"], "rev-parse", branch))

```


### Block 28 — `local-development/tests/test_release_crc.py` (11 of 13): the deploy test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
def test_argocd_branch_deploys_when_both_aliases_are_the_release(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
```

```python
def test_argocd_branch_deploys_when_both_aliases_are_the_release(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "pr-test")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
```


### Block 29 — `local-development/tests/test_release_crc.py` (12 of 13): the shipped-values test uses `pr-test`

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    shipped = (REPO / "charts" / "group-sync-dashboard" / "values.yaml").read_text()
    (lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml").write_text(shipped.replace("quay.io/ephico2real/", "quay.io/example/"))
    _git(lab["repo"], "commit", "-qam", "shipped values"); _git(lab["repo"], "push", "-q", "origin", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", "HEAD"))
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application {_version()}" in r.stdout
```

```python
    shipped = (REPO / "charts" / "group-sync-dashboard" / "values.yaml").read_text()
    (lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml").write_text(shipped.replace("quay.io/ephico2real/", "quay.io/example/"))
    _git(lab["repo"], "commit", "-qam", "shipped values"); _git(lab["repo"], "push", "-q", "origin", "pr-test")
    synced_status(lab, _git(lab["repo"], "rev-parse", "HEAD"))
    r = run(lab, "--argocd", "pr-test")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application {_version()}" in r.stdout
```


### Block 30 — `local-development/tests/test_release_crc.py` (13 of 13): the manifest-list test uses `pr-test`; the `release` and `main` tests (#598)

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python
    synced_status(lab, lab["full"])
    oci = _manifest_list(lab["tmp"] / "oci", arm64_version or _version())
    r = run(lab, "--argocd", "main", STUB_OCI_DIR=str(oci), STUB_REAL_OC=REAL_OC)
    assert (r.returncode == 0) is deploys, r.stdout + r.stderr
    if not deploys:
        assert "0.24.0" in next(line for line in r.stderr.splitlines() if "is application" in line)
        assert "oc apply" not in calls(lab)


```

```python
    synced_status(lab, lab["full"])
    oci = _manifest_list(lab["tmp"] / "oci", arm64_version or _version())
    r = run(lab, "--argocd", "pr-test", STUB_OCI_DIR=str(oci), STUB_REAL_OC=REAL_OC)
    assert (r.returncode == 0) is deploys, r.stdout + r.stderr
    if not deploys:
        assert "0.24.0" in next(line for line in r.stderr.splitlines() if "is application" in line)
        assert "oc apply" not in calls(lab)


# --- the lab deploys what promote.yml read back (#598) -------------------------------------------

DASHBOARD_DIGEST, REPORT_DIGEST = "sha256:" + "a" * 64, "sha256:" + "b" * 64


def _release_branch(lab, promotion: str | None) -> None:
    """origin/release as promote.yml writes it: the chart, environments/ and promotion.yaml (or none)."""
    _git(lab["repo"], "checkout", "-qb", "release")
    if promotion is not None:
        (lab["repo"] / "promotion.yaml").write_text(promotion)
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-q", "--allow-empty", "-m", "promote: main")
    _git(lab["repo"], "push", "-q", "origin", "release")
    _git(lab["repo"], "checkout", "-q", "pr-test")
    synced_status(lab, _git(lab["repo"], "rev-parse", "release"))


PROMOTION = (f"image:\n  repository: quay.io/example/group-sync-dashboard\n  digest: {DASHBOARD_DIGEST}\n"
             f"reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    digest: {REPORT_DIGEST}\n")


@pytest.mark.parametrize("revision", ["main", "refs/heads/main"])
def test_argocd_main_is_refused_before_anything_is_fetched_or_written(lab, revision):
    r = run(lab, "--argocd", revision)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "--argocd main is refused" in r.stderr and "--argocd release" in r.stderr
    assert calls(lab) == ""


def test_argocd_release_without_a_promotion_is_refused_before_anything_is_written(lab):
    _release_branch(lab, None)
    r = run(lab, "--argocd", "release")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "origin/release has no promotion.yaml" in r.stderr
    log = calls(lab)
    assert "helm uninstall" not in log and "oc patch" not in log and "oc apply" not in log, log


def test_argocd_release_reads_the_pinned_digests_back_and_lists_promotion_yaml_last(lab):
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}={_version()} "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}={_version()}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the digests in promotion.yaml" in r.stdout
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST} {LINUX_IMAGES}" in log
    assert f"oc image info quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST} {LINUX_IMAGES}" in log
    assert f":{_version()} " not in log, "the aliases are not what release deploys"
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "release", "helm": {
        "parameters": [], "valueFiles": ["../../environments/crc.yaml", "../../promotion.yaml"]}}


def test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release(lab):
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}={_version()} "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}=0.24.0")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report@{REPORT_DIGEST} is application 0.24.0" in r.stderr
    assert "oc apply" not in calls(lab)


```


### Block 31 — `docs/RELEASING.md` (1 of 2): "Promotion to the lab" and the operator's one-time steps

<!-- block: docs/RELEASING.md | edit -->

```markdown
carry a MINOR bump, so their merges publish both the immutable tag and the version alias. The
publisher's release-alias decision and `<appVersion>-<10-char sha>` tag scheme are unchanged.

---
```

```markdown
carry a MINOR bump, so their merges publish both the immutable tag and the version alias. The
publisher's release-alias decision and `<appVersion>-<10-char sha>` tag scheme are unchanged.

---

## Promotion to the lab

The lab's Argo CD Application tracks the `release` branch, not `main` (#598). `main` stays the source; `release`
holds only what `.github/workflows/promote.yml` read back from the registry. Before this, a release merge moved
`appVersion` on `main` before `publish.yml` had pushed the new image, and the lab's pods sat in `ErrImagePull` until
it existed (4.1.0, 4.4.0 and 5.1.0).

`promote.yml` builds nothing. It runs after a green `publish.yml` on `main`, after a merge to
`charts/group-sync-dashboard/` or `environments/`, or by hand (Run workflow, with `sha` and `rollback`). Each run:

1. Takes `main`'s tip (or the `sha` given) and its `appVersion`.
2. Promotes nothing, with a notice, when that version's images are still being published: the version is neither
   the one the triggering publish run built nor, on a push, the one `release` already runs. That publish run
   promotes `main` when it is green.
3. Reads both images back, at the pin in `values.yaml` or `:<appVersion>`: the version label on every Linux image,
   as `helm.yaml` checks it, and a signature from `publish.yml` on `main` (unless `SUPPLY_CHAIN_SIGNING` is
   `false`). Any failure is a red run that writes nothing.
4. Commits `charts/group-sync-dashboard/`, `environments/` and `promotion.yaml` to `release`, as a fast-forward.
   `promotion.yaml` pins both images by digest, and the Application lists it last, so the digests win.
5. Argo CD syncs `release`.

- **What `release` holds.** The chart and `environments/` at one `main` commit, and `promotion.yaml`. The commit's
  subject is `promote: main <sha>`. Nothing on `release` has a workflow, so nothing runs or builds there.
- **One writer.** The push uses a deploy key held in the `release` environment, which admits `main` only. The
  branch's ruleset lets only deploy keys create, update or delete it, and blocks force pushes. The job's token is
  `contents: read`.
- **Rollback.** Actions → promote → Run workflow, with an older `main` commit as `sha` and `rollback` checked. The
  same checks run. It holds until the next promotion; revert on `main` to keep it.
- **Deploy and check.** `local-development/release-crc.sh --argocd release` reads both pinned digests back again
  before it writes the Application, and refuses a `release` without `promotion.yaml`. `--argocd main` is refused.
  `--argocd <branch>` still deploys a branch for testing, with the chart's default images.

**The operator's one-time steps** (in this order, before the first promotion):

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
6. Point the lab at it: `local-development/release-crc.sh --argocd release`.

---
```


### Block 32 — `docs/RELEASING.md` (2 of 2): five troubleshooting rows

<!-- block: docs/RELEASING.md | edit -->

```markdown
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<chartVersion> is application <chartVersion>'s own alias` | the chart's version equals an application version that already has its alias, and the copy would overwrite it. Nothing was copied | bump `version` in `charts/group-sync-dashboard/Chart.yaml`, in a pull request, to a version no application release has used |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
| a new pod runs different bits than its neighbour | somebody republished an alias between the two container creations | pin `image.tag` to the sha form |
```

```markdown
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<chartVersion> is application <chartVersion>'s own alias` | the chart's version equals an application version that already has its alias, and the copy would overwrite it. Nothing was copied | bump `version` in `charts/group-sync-dashboard/Chart.yaml`, in a pull request, to a version no application release has used |
| promote run says `whose images publish.yml has not finished` and promotes nothing | main's `appVersion` moved and that version's publish run is still going | nothing to do: its green completion promotes main. If that publish run is red, fix it; the lab stays on the last promotion |
| promote run is red with `is application X, not <appVersion>` or `carries no signature from publish.yml on main` | the tag names another build, or the digest was not signed by `publish.yml` on `main`. Nothing was written to `release` | wait for `publish.yml` to finish green, then Run workflow on promote. Never edit `release` by hand |
| promote run is red with `origin has no release branch` or `RELEASE_DEPLOY_KEY is not set` | the operator's one-time steps are not done | "Promotion to the lab", steps 1 to 5 |
| promote run is red with `is not a later commit` | a Run workflow named a commit older than the one `release` holds | check `rollback` to deploy it on purpose |
| `release-crc.sh --argocd release` says `origin/release has no promotion.yaml` | no promotion has run yet | run promote (step 5 above) |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
| a new pod runs different bits than its neighbour | somebody republished an alias between the two container creations | pin `image.tag` to the sha form |
```


### Block 33 — `gitops/README.md`: the dashboard Application's row

<!-- block: gitops/README.md | edit -->

```markdown
| `argocd-rbac-kubeadmin.yaml` | a patch for the `openshift-gitops` ArgoCD CR: OpenShift GitOps' default policy grants `role:admin` to the *groups* `system:cluster-admins` / `cluster-admins`, but Dex's OpenShift connector puts only `system:authenticated` in a token's `groups` (kubeadmin's cluster-admin membership is a virtual group Dex never sees — measured on CRC 2026-09-19: `PermissionDenied` on every list, an empty UI). This matches the `name` claim too and grants `kubeadmin` admin. On a cluster where a `cluster-admins` Group object exists this is not needed |
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |

```

```markdown
| `argocd-rbac-kubeadmin.yaml` | a patch for the `openshift-gitops` ArgoCD CR: OpenShift GitOps' default policy grants `role:admin` to the *groups* `system:cluster-admins` / `cluster-admins`, but Dex's OpenShift connector puts only `system:authenticated` in a token's `groups` (kubeadmin's cluster-admin membership is a virtual group Dex never sees — measured on CRC 2026-09-19: `PermissionDenied` on every list, an empty UI). This matches the `name` claim too and grants `kubeadmin` admin. On a cluster where a `cluster-admins` Group object exists this is not needed |
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-dashboard.yaml` | the dashboard chart from the `release` branch, with `environments/crc.yaml` and then `promotion.yaml`, the digests `promote.yml` read back (`docs/RELEASING.md`, "Promotion to the lab"). `local-development/release-crc.sh --argocd release` writes it on the lab; `--argocd main` is refused (#598) |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |

```


### Block 34 — `local-development/README.md`: the typical loop ends with `--argocd release`

<!-- block: local-development/README.md | edit -->

```markdown
`main` in between. Nothing is written back into the tree — `helm get values`, or the Application's
spec, records what is deployed. The typical loop: iterate with the bare script (or `--values` for
a local variant), `--argocd` on the pushed head before the PR is called ready, `--argocd main`
after a merge once the app release is cut. `./argocd-wait.sh` is the waiter the Argo modes use: it
accepts Synced/Healthy/Succeeded only once the status was computed for the current spec
(`status.sync.comparedTo.source`) and for the expected commit, and names the failed hook or
```

```markdown
`main` in between. Nothing is written back into the tree — `helm get values`, or the Application's
spec, records what is deployed. The typical loop: iterate with the bare script (or `--values` for
a local variant), `--argocd` on the pushed head before the PR is called ready, `--argocd release`
after a merge once `promote.yml` is green (`--argocd main` is refused, #598; `docs/RELEASING.md`, "Promotion to
the lab"). `./argocd-wait.sh` is the waiter the Argo modes use: it
accepts Synced/Healthy/Succeeded only once the status was computed for the current spec
(`status.sync.comparedTo.source`) and for the expected commit, and names the failed hook or
```


### Block 35 — `.claude/skills/epic/SKILL.md` (1 of 2): the epic's Definition of Done deploys `--argocd release`

<!-- block: .claude/skills/epic/SKILL.md | edit -->

```markdown
      heading; the release PR merged; `.github/workflows/helm.yaml` published the chart;
      `.github/workflows/publish.yml` published the application image when `--app` was used.
- [ ] The published release deployed to CRC through `release-crc.sh --argocd main`, walked, PVC UIDs unchanged.
- [ ] The branches this epic used are deleted, each proven merged first.
- [ ] The session changelog records the epic.
```

```markdown
      heading; the release PR merged; `.github/workflows/helm.yaml` published the chart;
      `.github/workflows/publish.yml` published the application image when `--app` was used.
- [ ] The published release deployed to CRC through `release-crc.sh --argocd release`, walked, PVC UIDs unchanged.
- [ ] The branches this epic used are deleted, each proven merged first.
- [ ] The session changelog records the epic.
```


### Block 36 — `.claude/skills/epic/SKILL.md` (2 of 2): the deploy step

<!-- block: .claude/skills/epic/SKILL.md | edit -->

```markdown
   change". The tag is the **chart** version just cut, not the
   application version: `gh release edit group-sync-dashboard-<chart-version> --notes-file <file>`.
3. **Deploy.** After those workflows are green, deploy the published release with
   `local-development/release-crc.sh --argocd main`. That mode uses the chart on GitHub at `main` and the published
   quay image (the mode table in the `release-crc.sh` header and in `local-development/README.md`). Bare
   `--argocd` builds HEAD and pins that image, so it is not the published release. The branch path refuses to hand Argo an image whose
   `org.opencontainers.image.version` label is not the chart's appVersion, or that is not in the registry (#410): a
   refusal means publish.yml has not moved the `:<appVersion>` aliases yet, or a chart-version label already occupied
   that tag. Wait for the publish run; never retag by hand. The lab's Application auto-syncs `main`, so it can deploy
   before this script runs; #410 tracks that race. Walk it, and record the two PVC
   UIDs before and after; they must be unchanged.

Then:
```

```markdown
   change". The tag is the **chart** version just cut, not the
   application version: `gh release edit group-sync-dashboard-<chart-version> --notes-file <file>`.
3. **Deploy.** After those workflows and `promote.yml` are green, deploy the published release with
   `local-development/release-crc.sh --argocd release`. That mode uses the chart on the `release` branch and the two
   digests `promote.yml` pinned in `promotion.yaml`, and reads both back before it writes the Application (the mode
   table in the `release-crc.sh` header; `docs/RELEASING.md`, "Promotion to the lab"). `--argocd main` is refused.
   Bare `--argocd` builds HEAD and pins that image, so it is not the published release. A refusal names the digest:
   re-run promote once publish.yml is green; never edit `release` or retag by hand. The lab's Application
   auto-syncs `release`, so it can deploy before this script runs, and only what promote read back. Walk it, and
   record the two PVC UIDs before and after; they must be unchanged.

Then:
```


### Block 37 — `charts/group-sync-dashboard/Chart.yaml` (1 of 2): chart 0.70.3 and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# CHART 0.70.2 (2026-10-04), PATCH: appVersion moves to application 5.1.0 (below); the reports' clock is the
# snapshot's (#592, #607, #593; SPEC_F7). No template, default or RBAC change.
version: 0.70.2
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```

```yaml
# CHART 0.70.2 (2026-10-04), PATCH: appVersion moves to application 5.1.0 (below); the reports' clock is the
# snapshot's (#592, #607, #593; SPEC_F7). No template, default or RBAC change.
# CHART 0.70.3 (2026-10-04), PATCH: appVersion moves to application 5.2.0 (below); The lab deploys
# only what promote.yml read back (#598).
version: 0.70.3
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```


### Block 38 — `charts/group-sync-dashboard/Chart.yaml` (2 of 2): application 5.2.0's history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# 5.0.0 (2026-10-04). Epic F: reports, honest seals, more formats, diffs and delivery (#386). MAJOR.
# 5.1.0 (2026-10-04). A report's windows, cutoffs and overdue states end at the snapshot's stamp, not the generation time (#592); compliance-snapshot and login-activity keep the last poll's and the last read's instants out of their sealed sections (#607); the Reports form starts with only HTML ticked (#593). MINOR.
appVersion: "5.1.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
```

```yaml
# 5.0.0 (2026-10-04). Epic F: reports, honest seals, more formats, diffs and delivery (#386). MAJOR.
# 5.1.0 (2026-10-04). A report's windows, cutoffs and overdue states end at the snapshot's stamp, not the generation time (#592); compliance-snapshot and login-activity keep the last poll's and the last read's instants out of their sealed sections (#607); the Reports form starts with only HTML ticked (#593). MINOR.
# 5.2.0 (2026-10-04). The lab deploys only what promote.yml read back (#598). MINOR.
appVersion: "5.2.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
```


### Block 39 — `local-development/pyproject.toml`: application 5.2.0

<!-- block: local-development/pyproject.toml | edit -->

```toml
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.1.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
```

```toml
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.2.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
```


### Block 40 — `local-development/gsd/__init__.py`: application 5.2.0

<!-- block: local-development/gsd/__init__.py | edit -->

```python
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.1.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
```

```python
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.2.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
```


### Block 41 — `docs/CHANGELOG.md`: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

```markdown

## Unreleased

- **The reports' clock is the snapshot's (#592, #607, #593, `docs/specs/SPEC_F7_snapshot_clock.md`; application 5.1.0,
```

```markdown

## Unreleased

- **The lab deploys only what `promote.yml` read back (#598, `docs/specs/SPEC_P1_promote_release_branch.md`;
  application 5.2.0, chart 0.70.3).** A new workflow, `promote.yml`, runs after a green `publish.yml` on `main`, after
  a merge to the chart or `environments/`, or by hand. It builds nothing. It reads both images back (the version
  label on every Linux image, as `helm.yaml` does, and the signature from `publish.yml` on `main` when signing is
  on), pins them by digest in `promotion.yaml`, and commits that file with the chart and `environments/` to the
  `release` branch as a fast-forward. A merge whose application version is still being published promotes nothing
  until that publish run is green. The lab's Application (`gitops/argocd-application-dashboard.yaml`) tracks
  `release` with `promotion.yaml` as its last values file, so Argo CD no longer syncs a chart whose image is not
  pushed yet (the `ErrImagePull` seen at 4.1.0, 4.4.0 and 5.1.0). `release-crc.sh --argocd release` reads the pinned
  digests back before it writes the Application; `--argocd main` is refused. The `release` branch, its ruleset and
  the deploy key are the operator's one-time steps (`docs/RELEASING.md`, "Promotion to the lab"). The application
  moves only because `local-development/README.md` is an image input; no code, template, value or RBAC change.

- **The reports' clock is the snapshot's (#592, #607, #593, `docs/specs/SPEC_F7_snapshot_clock.md`; application 5.1.0,
```

