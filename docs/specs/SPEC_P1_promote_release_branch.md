# SPEC P1 — build once, promote the artifact: the lab's Argo CD tracks a `release` branch that only a read-back promotion writes (#410)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety |
| Batch | P — promotion |
| Release | — (post-programme; Epic E) |
| Version on release | app 1.1.0, chart 0.59.3 |
| Issue | [#410](https://github.com/ephico2real2/group-sync-dashboard/issues/410) |
| Status | specified |
| Source | OB1-lite's specification of 2026-09-27, written before any code from issue #410 in full (the body, OB2's PreSync input, the operator's direction and go-ahead of 2026-09-27), main `05e32c8` (application 1.0.0, chart 0.59.2), the upstream documents cited in §3, and read-only measurements of quay.io, GitHub and the lab. §8's blocks were cut from a copy of `05e32c8` with the design implemented, and applied back to a clean copy for the proof in §6. No cluster, branch or GitHub setting was changed |

## How to read this spec

Read §1 and §2 first: they say what is being built and define every word. §4 answers the nine design questions, one
line each, with the reason and the source. §5 says where the safety guarantee is enforced and what it does not cover.
§6 is the test table, before and after. §7 is the lab procedure for the implementing pull request. §8 is the whole
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_P1_promote_release_branch.md . --apply

Line citations are plain text, file:line, at `05e32c8`. This spec's index row and its header's Status move by hand:
the implementing commit sets both to `merged` beside the applied blocks.

## Orchestrator's notes

None yet.

## 1. The requirement

**In one sentence:** the lab must deploy only an artifact that was built once and checked, never `main` directly.

The operator, 2026-09-27: *"We shouldn't be rebuilding and syncing argo on main branches. We should have a release or
promote branch that does not do any build. So if we have a true CI/CD github action. Our main argo should be tracking
a release or promote branch that only contains our finished artifact."* Then: *"1 to 3 suggestion is the best == do
this now."* The three steps:

1. `main` stays the source. `publish.yml` keeps building `<appVersion>-<sha10>`, unchanged.
2. A `promote` workflow runs only after `publish.yml` succeeds. It reads both images back, then commits to a `release`
   branch the chart at that commit plus the pinned artifact, and nothing else. No workflow builds on `release`.
3. The lab's Argo CD Application tracks `release`, and `release-crc.sh --argocd` points at it.

**Why:** the lab's Application tracks `main` with automated sync (gitops/argocd-application-dashboard.yaml:35 and
:52-55). A merge that moves `appVersion` lets Argo sync a chart whose `:<appVersion>` image is not pushed yet, or is a
stale tag. At the 0.37.0 release the sync landed 95 s after the image; a slower publish would have pulled an
application 0.24.0 image onto a schema-20 database (issue #410, comment of 2026-09-27 00:44, with its evidence in
PR #412). Measured today: publishing `05e32c8` took 2 min 22 s (run 36312105709, 10:18:23 → 10:20:45 UTC).

**Must not change:** `publish.yml` (its path filter, tag scheme, alias rule, signing and SBOM); every published tag;
`helm.yaml`; the chart's templates, values and RBAC; `release-crc.sh`'s Helm mode, its build path, and
`--argocd <branch>` for a branch without `promotion.yaml`.

## 2. Words

| Word | Meaning in this spec |
|---|---|
| promote | copy a finished, checked artifact to the place a deployment reads; here, a commit to `release` |
| `release` branch | a branch with only `charts/group-sync-dashboard/`, `environments/` and `promotion.yaml`; only `promote.yml` writes it |
| `promotion.yaml` | a Helm values file on `release` that sets `image.*` and `reporting.image.*`: repository, tag and digest |
| immutable tag | `<appVersion>-<sha10>`, built once per commit by `publish.yml` |
| alias | `:<appVersion>`; `publish.yml` moves it when the application version changes, so it can name different images over time |
| digest | `sha256:…`, the hash of the image manifest; the registry cannot serve other bytes under it |
| read back | ask the registry what a tag is now (labels, digest) and check it, instead of trusting what the build said |
| `workflow_run` | the GitHub Actions trigger that starts a workflow when another workflow's run completes |
| image input | a file in `publish.yml`'s `on.push.paths` list: a change to it changes the image |
| first-parent line | the chain of merge commits on `main` (`git log --first-parent`); every commit `publish.yml` builds is on it |
| the tree's image | for a commit T on main: the image built from the newest first-parent commit at or before T that changed an image input |

## 3. Read and measured

### 3.1 The repository at `05e32c8`

| Fact | Source |
|---|---|
| `publish.yml` runs on a push to `main` only when an image input changes; `charts/**` is deliberately absent | .github/workflows/publish.yml:77-89, the comment at :74-76 |
| It builds both images tagged `<appVersion>-<sha10>`; the sha is `git rev-parse --short=10 HEAD` | local-development/build-and-push-external.sh:128, :143 |
| It moves `:<appVersion>` only when `pyproject.toml`'s version changed since `github.event.before` | publish.yml:192-234 |
| It signs each digest keyless and reads the signature back with the identity `publish.yml@refs/heads/main` | publish.yml:451, :471-483 |
| One publish at a time: `concurrency: publish-main`, `cancel-in-progress: false` | publish.yml:97-99 |
| Both images carry `org.opencontainers.image.version` and `org.opencontainers.image.revision` labels | local-development/Containerfile:184-185, Containerfile.report:119-120 |
| `helm.yaml` publishes the chart to GitHub Pages on `charts/**` changes and labels the image with the chart version | .github/workflows/helm.yaml:25-26, :133-196 |
| The chart renders `repository@digest` when `image.digest` / `reporting.image.digest` is set; the digest wins over the tag | charts/group-sync-dashboard/templates/_helpers.tpl:72-82, :668-679; values.yaml:54, :1142 |
| The chart reads no file outside its directory: no symlinks under `charts/`, and `.Files.Get` names `dashboards/` and `scripts/` only | `find charts -type l` (empty); grafana-dashboard.yaml:32, backup-offsite.yaml:88 |
| `release-crc.sh --argocd <branch>` reads `:<appVersion>` back before handing a branch to Argo (#414) | local-development/release-crc.sh:218-278, :282-292 |
| The Application is written once from the committed file, merged locally | release-crc.sh:171-191 |
| The workflow tests parse the YAML and hold the path filter to the Containerfiles | local-development/tests/test_publish_paths.py, test_supply_chain.py, test_workflow_pins.py |

### 3.2 Upstream documents

| Claim | Source (quoted) |
|---|---|
| `workflow_run` runs the workflow file on the default branch | GitHub, [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows): "This event will only trigger a workflow run if the workflow file exists on the default branch." `GITHUB_SHA`/`GITHUB_REF`: "Last commit on default branch". The `branches` filter names "what branches the triggering workflow must run on". Chains stop at three levels; this is two (push → publish → promote) |
| A push runs the workflow file in the pushed commit | GitHub, [Workflows](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflows): "Workflows are defined in the `.github/workflows` directory in a repository." and "Each workflow run will use the version of the workflow that is present in the associated commit SHA or Git ref of the event." So a `release` tree with no `.github/workflows/` runs nothing on push |
| A push made with `GITHUB_TOKEN` starts no workflow | GitHub, [Triggering a workflow](https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow): "events triggered by the `GITHUB_TOKEN` will not create a new workflow run", except `workflow_dispatch` and `repository_dispatch` |
| Concurrency keeps one running and one pending; a newer pending run replaces the older | GitHub, [Control workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency): "By default, any existing `pending` job or workflow in the same concurrency group will be canceled and the new queued job or workflow will take its place." |
| The runs API filters by commit and needs `actions: read` | GitHub REST, [List workflow runs for a workflow](https://docs.github.com/en/rest/actions/workflow-runs?apiVersion=2022-11-28#list-workflow-runs-for-a-workflow): `head_sha` "Only returns workflow runs that are associated with the specified head_sha"; fine-grained tokens and `GITHUB_TOKEN` need `actions: read` |
| Rulesets: what each rule blocks | GitHub, [Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets): "Restrict updates: Only users with bypass permissions can push"; "Block force pushes"; "Restrict deletions". A user-owned repository cannot make GitHub Actions a bypass actor: measured 422 (publish.yml:14-19) |
| Argo CD syncs the tip of a branch named in `targetRevision` | Argo CD, [Tracking strategies](https://argo-cd.readthedocs.io/en/stable/user-guide/tracking_strategies/): "Argo CD will continually compare live state against the resource manifests defined at the tip of the specified branch" |
| Several `valueFiles`: the last wins; parameters beat all files | Argo CD, [Helm](https://argo-cd.readthedocs.io/en/stable/user-guide/helm/): "the last file listed has the highest precedence"; "Order of precedence is `parameters > valuesObject > values > valueFiles > helm repository values.yaml`"; paths are relative to the chart directory |
| `skopeo inspect` prints `Digest` (the top-level manifest's) and `Labels` | [skopeo-inspect(1)](https://github.com/containers/skopeo/blob/main/docs/skopeo-inspect.1.md) |
| Keyless verify takes `--certificate-identity` and `--certificate-oidc-issuer` | [Sigstore, Verifying signatures](https://docs.sigstore.dev/cosign/verifying/verify/); the same flags publish.yml:479-482 uses |
| The Ubuntu runner has `skopeo` 1.13.3, `gh` 2.101.0 and python 3.12.3, and PyYAML is not listed | [runner-images, Ubuntu 24.04](https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md); so the script reads `publish.yml`'s path list as text, and a test holds that reading to the parsed YAML |

### 3.3 Measured, read-only

- **Both 1.0.0 images are single OCI manifests carrying the labels the promotion checks** (`oc image info`, quay.io):
  `group-sync-dashboard:1.0.0-05e32c8394` → `sha256:b08c0e8f…cdcd`, `application/vnd.oci.image.manifest.v1+json`,
  version `1.0.0`, revision `05e32c8394`; `:1.0.0` is the same digest. The report image: `sha256:06ee6b4e…e030`, the
  same labels. By digest, release-crc.sh's new check prints `1.0.0/05e32c8394`.
- **The runs API answers per commit:** `head_sha=05e32c83…` → one run, `push`, `main`, `completed`, `success`
  (id 36312105709). `head_sha=b6797011…` (#422, docs and chart only) → `total_count` 0: a chart-only merge has no
  publish run, which is why §4(c) exists.
- **The tree's-image rule on real history** (`git log --first-parent -1 <T> -- <publish paths>`): `05e32c8` → itself;
  `b679701` and `13208ea` → `602a1c4`, whose publish run 36306896467 succeeded.
- **The lab** (`oc get applications.argoproj.io`, read-only): `targetRevision: main`, `automated {prune, selfHeal}`
  **on**, Synced/Healthy at `05e32c8`; OpenShift GitOps operator `1.21.4`. The issue's "auto-sync paused" is no longer
  the state: the race is live for the next merge until this ships.
- **`main`'s protection** (`gh api …/branches/main/protection`): `allow_force_pushes: false`, `enforce_admins: true`,
  pull-request reviews required. So `main`'s first-parent line only moves forward, which §4(h) relies on. The
  repository is user-owned (`owner.type: User`).
- **Rendered** with `-f environments/crc.yaml -f promotion.yaml`: every dashboard and report container image is
  `repository@sha256:…`; no `:<appVersion>` reference remains. RBAC rendered before and after with `crc.yaml`:
  70 rules and bindings each, REMOVED 0, ADDED 0.

## 4. Design

The whole flow, in order:

1. A merge lands on `main`.
2. If it changed an image input, `publish.yml` builds, pushes and signs, exactly as today.
3. `promote.yml` starts: after every completed publish run (it continues only on `success`), after a push to `main`
   that touches the chart or `environments/`, or by hand.
4. It runs `local-development/promote.py`, which picks `main`'s tip (or the commit given), finds the tree's image,
   reads both images back, and commits `charts/group-sync-dashboard/`, `environments/` and `promotion.yaml` to
   `release` as a fast-forward.
5. Argo CD syncs `release`. `promotion.yaml` is the Application's last values file, so the digests win.

The nine questions:

| | Question | Answer | Why, and the source |
|---|---|---|---|
| a | What `release` contains | `charts/group-sync-dashboard/`, `environments/`, `promotion.yaml`; nothing else, and no `.github/` | Argo reads the chart path and `../../environments/crc.yaml` only; the chart reads nothing outside itself (§3.1). A push runs only workflows in the pushed commit, and a `GITHUB_TOKEN` push runs none (§3.2): two independent reasons nothing runs on `release`. `test_a_code_merge_is_promoted_with_both_images_pinned_by_digest` asserts the tree |
| b | Pin by tag or digest | digest, with the tag written beside it for people | A tag is a name that can move (#410's `:0.39.0` was application 0.24.0); a digest is the content. The chart renders `repository@digest` and prefers it over the tag (_helpers.tpl:72-82, :668-679), measured in the render (§3.3) |
| c | A chart-only merge | pinned to the tree's image: the newest first-parent commit at or before T that changed an image input; any first-parent commit from there to T that `publish.yml` built on `main` with success has the same inputs; the newest such run wins | Deterministic, from git and the runs API. The issue's example, "the newest `<appVersion>-<sha10>` whose sha is an ancestor", is unsafe: if the last publish failed it picks an older image that lacks that merge's code. Measured on `b679701` → `602a1c4` (§3.3) |
| d | A failed publish | never promoted | The job's `if` requires `workflow_run.conclusion == 'success'`; and the script requires a successful run for the tree's image, or refuses (`test_a_failed_publish_is_never_promoted_even_when_an_older_image_exists`) |
| e | Rollback | Run workflow with `sha` = an older commit on `main` and `rollback` checked; the same read-back runs | A hand-made revert on `release` would skip the read-back. The rollback holds until the next promotion; revert on `main` to keep it |
| f | #414's guard and `release-crc.sh --argocd` | `--argocd release` re-reads the pinned digests (version and revision labels) before pointing the lab at `release`; `--argocd <branch>` keeps #414's alias check for a branch with no `promotion.yaml`; bare `--argocd` still builds the pushed head | The operator's step 3. Every Argo mode now states `valueFiles` explicitly, because the committed default ends with `promotion.yaml`, which exists only on `release`, and a missing file fails the render. Alternative reading for review: bare `--argocd` could mean `release`; not taken, because it would remove the documented pre-merge gate on a pushed head |
| g | How the Application switches | `targetRevision: release`, `valueFiles: [../../environments/crc.yaml, ../../promotion.yaml]`; applied on the lab by `release-crc.sh --argocd release` after the first promotion | Argo: the last values file wins (§3.2). `test_the_application_script_and_workflow_name_one_pin_file_on_release` holds the three places that name the file together |
| h | Two merges in a row | one promotion at a time (`concurrency: promote-release`, no cancel); each run promotes the tip it fetches; a commit that does not descend from the one on `release` is refused unless `rollback`; the push is a fast-forward, never forced | A replaced pending run loses nothing, because the later run fetches a tip at least as new, and `main` never rewinds (§3.3). `test_an_older_commit_needs_rollback_and_a_second_run_changes_nothing` |
| i | `:latest` (#425) | not used, not blocked | The lab pins by digest, so moving any tag changes nothing it runs |

**Three ways in, and why each exists:**

| Trigger | Covers | What happens if the image is not ready |
|---|---|---|
| `workflow_run` of `publish` on `main`, `completed` | every image build | only `success` runs the job |
| push to `main` touching `charts/group-sync-dashboard/**`, `environments/**`, `promote.yml` or `promote.py` | a chart-only merge, which publish skips | a publish run still going: exit 0 with a notice, and that run's completion promotes; none successful and none running: red |
| `workflow_dispatch` (`sha`, `rollback`) | a re-run, a rollback | the same checks |

**Permissions:** `contents: read` at the top; the job adds `contents: write` (the push to `release`) and
`actions: read` (the runs API). `id-token` is not needed: the job verifies signatures and makes none.

**Setup, once, by the operator** (a GitHub-visible action this spec does not perform): create `release` as an orphan
branch with one empty commit, then a ruleset on `release` with Restrict deletions and Block force pushes only
(docs/CICD.md, "Rollback and setup"). Restrict updates is not set: it would block `promote.yml` (§3.2). Until the
branch exists, `promote.yml` is red and says so.

## 5. The budget

**The guarantee:** the lab's Argo CD never syncs an image that does not exist, or whose version and revision labels do
not match the pinned version and commit, **through any path this repository automates.**

| Path to the lab | What enforces it | Where |
|---|---|---|
| Argo auto-sync of `release` | `release` only holds trees `promote.py` wrote after reading both images back (labels, digest, and the cosign signature when signing is on); the pin is a digest, so what was read is what is pulled | promote.py `read_back`, `verify_signature`, `commit_release`; promote.yml `if`; the Application's last values file |
| `release-crc.sh --argocd release` | re-reads each pinned digest's labels before writing the Application | release-crc.sh `promoted_images_are_the_release` |
| `release-crc.sh --argocd <branch>` | #414's alias read-back, unchanged | release-crc.sh `published_image_is_the_release` |
| `release-crc.sh`, Helm mode and bare `--argocd` | builds its own image and verifies the commit stamp in the pod, unchanged | release-crc.sh:354-488 |

**Residuals, stated:**

1. **A person with write access can push to `release` by hand**, and Argo would sync it. A ruleset cannot restrict
   updates without also blocking `promote.yml` on a user-owned repository (§3.2). `--argocd release` re-checks when
   it is used; an auto-sync of a hand push is not checked.
2. **A pinned digest deleted from quay.io** after promotion gives ImagePullBackOff: a missing image, never a wrong one.
   Published images are never deleted (the operator's rule).
3. **With `SUPPLY_CHAIN_SIGNING=false`**, the check is labels and digest only; labels are not proof of origin.
4. **A hand edit of the Application** (`oc edit`) bypasses all of this.
5. **The race on the push trigger:** if a chart-and-code merge's push-triggered run starts before its publish run is
   registered, it is red for that minute; the publish run's completion promotes. A wrong image is never pinned.
6. **The published Helm chart** (`helm.yaml`, for installs outside the lab) still resolves `:<appVersion>`, and its
   existence gate still passes on a stale tag. The issue's first Definition-of-Done box (a chart release whose default
   image is another application version is refused) is not delivered by steps 1-3.

## 6. Tests, before and after

Three new or changed test files; no other test is edited. "Before" is `05e32c8` with this spec plus §8's three test
blocks only; "after" is the same tree with every block applied. Where "before" fails only because a new file is
missing, the right-hand column adds a mutation run on the "after" tree: one rule of `promote.py` switched off, or
`release-crc.sh` put back to `05e32c8`, to show the test fails for the reason it names.

| Definition of Done | Test | Before | After |
|---|---|---|---|
| (a)(b) `release` holds only the chart, `environments/` and `promotion.yaml`; both images pinned by digest; the signature is verified | `test_promote.py::test_a_code_merge_is_promoted_with_both_images_pinned_by_digest` | FAILED: `promote.py` does not exist | passed; FAILED when `.github` is carried, and when the signature check is off |
| (c) a chart-only merge carries the image of the last image-input commit | `test_a_chart_only_merge_carries_the_image_of_the_last_image_input_commit` | FAILED: no `promote.py` | passed |
| (d) a failed publish is never promoted, though an older image exists | `test_a_failed_publish_is_never_promoted_even_when_an_older_image_exists` | FAILED: no `promote.py` | passed; FAILED under the issue's "newest ancestor" rule |
| a publish still running: green, nothing written | `test_a_publish_still_running_waits_for_its_own_completion` | FAILED: no `promote.py` | passed; FAILED when a running publish counts as failed |
| a wrong version or revision label is refused | `test_an_image_whose_labels_are_not_this_build_is_refused[version]`, `[revision]` | FAILED: no `promote.py` | passed; both FAILED with the label check off |
| a signature that does not verify is refused; signing off skips cosign | `test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_it` | FAILED: no `promote.py` | passed; FAILED with the signature check off |
| (e)(h) an older commit needs `rollback`; the same tree twice is a no-op | `test_an_older_commit_needs_rollback_and_a_second_run_changes_nothing` | FAILED: no `promote.py` | passed; FAILED with the ancestry check off |
| no `release` branch: refused with the setup step | `test_without_a_release_branch_nothing_is_promoted` | FAILED: no `promote.py` | passed |
| the text reader of `publish.yml`'s paths equals the parsed YAML | `test_the_image_input_reader_is_publish_ymls_path_filter` | FAILED: `FileNotFoundError` | passed |
| promote.yml: after publish, `success` only, `main` only, this repository only | `test_promote_workflow.py::test_it_runs_after_publish_and_promotes_only_a_success` | FAILED: `promote.yml` does not exist | passed |
| promote.yml: chart-only push trigger; dispatch `sha` and `rollback` | `test_a_chart_only_merge_triggers_it_and_a_dispatch_can_roll_back` | FAILED: no `promote.yml` | passed |
| (h) one at a time; `contents: write` and `actions: read` only | `test_one_promotion_at_a_time_and_only_the_scopes_it_needs` | FAILED: no `promote.yml` | passed |
| nothing in promote.yml builds | `test_nothing_in_it_builds` | FAILED: no `promote.yml` | passed |
| the same cosign as publish.yml | `test_it_verifies_with_the_cosign_publish_signs_with` | FAILED: no `promote.yml` | passed |
| (g) the Application tracks `release` with `promotion.yaml` last; one file name in three places | `test_the_application_script_and_workflow_name_one_pin_file_on_release` | FAILED: `'main' == 'release'` | passed |
| (f) `--argocd <branch>` states `valueFiles` without the pin | `test_release_crc.py::test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit` (edited) | FAILED: no `valueFiles` in the patch | passed |
| (f) `--argocd release` re-reads both pinned digests and lists the pin last | `test_argocd_release_reads_the_pinned_digests_back_and_adds_the_pin_last` | FAILED: no `promote.py` | passed; FAILED with `05e32c8`'s script (it reads the `:1.1.0` alias, which the stub registry does not hold) |
| (f) a pinned digest of another build, unlabelled or absent is refused before anything is written | `test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release[other-build]`, `[unlabelled]`, `[absent]` | FAILED: no `promote.py` | passed; FAILED with `05e32c8`'s script (its message names the alias, not the digest) |

Before: `21 failed, 30 passed` over the three files. After, the three files: `51 passed`.

The gates, on the applied copy:

| Gate | Command | Result |
|---|---|---|
| the blocks | `apply-spec-blocks.py docs/specs/SPEC_P1_promote_release_branch.md <copy>`, then `--apply` | `34 blocks check out across 18 files`; the applied files are byte-equal to the proof tree's |
| the hermetic suite, before | `pytest -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` on `05e32c8` | `5409 passed, 20 skipped, 610 deselected` |
| the hermetic suite, after | the same, on the applied copy | `5434 passed, 19 skipped, 610 deselected` |
| the workflows | actionlint v1.7.12 | no finding in `promote.yml`; the other files' findings are unchanged from `05e32c8` (mock-cluster.yml, SC2034) |
| the script | `bash -n` and `shellcheck -S warning` on `release-crc.sh` | clean |
| the render | `helm template … -f environments/crc.yaml -f promotion.yaml` | every dashboard and report image is `repository@sha256:…` |
| RBAC | Roles, ClusterRoles and their bindings, rendered with `crc.yaml`, before and after | 70 and 70; REMOVED 0, ADDED 0 |
| the figure | `docs/diagrams/render.py … promotion-pipeline` | two PNGs written; `375 px viewport: scrollWidth 375` |
| Markdown | `markdownlint-cli2` on every edited `.md` | no new finding (the counts per file equal `05e32c8`'s) |

## 7. On the lab, for the implementing pull request

Nothing here was run for this spec. The implementer runs it, with the lab's kubeconfig, after review:

1. Record the UIDs of the `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` PVCs.
2. Ask the operator to create `release` and its ruleset (§4, Setup). Check: `git ls-remote origin refs/heads/release`
   prints one line.
3. Pause the dashboard Application's auto-sync before the merge. This PR moves `appVersion` to 1.1.0 on `main`, and
   the lab still tracks `main` until step 6: that is the race this spec removes, one last time.
4. After the merge: `gh run list --workflow publish.yml -L 1` and `gh run list --workflow promote.yml -L 3`. Expected:
   publish `success`; the push-triggered promote green with "still being published"; the `workflow_run` promote
   green, with two `image : … (signature verified)` lines.
5. Read `release`: its top level is exactly `charts`, `environments`, `promotion.yaml`, and each pinned digest equals
   `oc image info quay.io/ephico2real/<image>:1.1.0-<sha10>`'s digest.
6. `local-development/release-crc.sh --argocd release`. Expected: two `image : …@sha256:… is application 1.1.0`
   lines, then Synced/Healthy at `release`'s tip. The pods' `imageID`s end in the pinned digests
   (`oc get pods -n group-sync-dashboard -o jsonpath='{..imageID}'`).
7. Prove §4(c) with the first chart-only merge that follows: its promotion pins the previous image, at once.
8. Record the PVC UIDs again; they must be unchanged. The evidence goes under `reports/<date>_<slug>/`.

## 8. Implementation blocks

Thirty-four blocks over eighteen files, in apply order: the workflow, the script, the Application, `release-crc.sh`,
the tests, the figure's page, the docs, the versions, the CHANGELOG. Lines added / removed per file (§6's proof
tree): `promote.yml` +75, `promote.py` +229, `test_promote.py` +215, `test_promote_workflow.py` +64,
`docs/CICD.md` +201, `docs/diagrams/cicd/source.html` +150; `release-crc.sh` +50 −9, `test_release_crc.py` +51 −3,
`gitops/argocd-application-dashboard.yaml` +9 −5, the chart README +18, `RELEASING.md` +9 −1, the CHANGELOG +13,
`Chart.yaml` +5 −2, `local-development/README.md` +3 −2, `docs/README.md` +1, `gitops/README.md` +1,
`pyproject.toml` and `gsd/__init__.py` +1 −1 each.

The pipeline figure's PNGs cannot be blocks. With the blocks applied, render them from the repository root and read
both before committing:

    local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/cicd/source.html docs/diagrams/cicd promotion-pipeline

It exits non-zero on a page error, a font that did not load, a name/figure mismatch, or sideways scroll at 375 px.

<!-- block: .github/workflows/promote.yml | create -->
```yaml
# Promote what publish.yml built to the `release` branch the lab's Argo CD tracks (#410).
# Nothing here builds. docs/CICD.md is the operator guide; SPEC_P1 is the design.
name: promote

on:
  # After every publish run; only a successful one promotes (the job's `if`).
  workflow_run:
    workflows: [publish]
    types: [completed]
    branches: [main]
  # Chart-only merges: publish.yml skips them, so nothing else would deploy them.
  push:
    branches: [main]
    paths:
      - 'charts/group-sync-dashboard/**'
      - 'environments/**'
      - '.github/workflows/promote.yml'
      - 'local-development/promote.py'
  # A re-run, or a rollback to an older commit on main.
  workflow_dispatch:
    inputs:
      sha:
        description: The commit on main to promote (empty = main's tip)
        required: false
        default: ''
      rollback:
        description: Allow a commit older than the one on release
        type: boolean
        default: false

# One promotion at a time; each run promotes main's tip as it finds it, so a replaced pending run loses nothing.
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
    permissions:
      contents: write   # the push to release
      actions: read     # publish.yml's runs, looked up by commit
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: main
          fetch-depth: 0

      - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
        if: vars.SUPPLY_CHAIN_SIGNING != 'false'
        with:
          cosign-release: v3.1.3   # the cosign publish.yml signs with

      - name: Read both images back and promote
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
          REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
          REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
          SUPPLY_CHAIN_SIGNING: ${{ vars.SUPPLY_CHAIN_SIGNING }}
          SHA: ${{ inputs.sha }}
          ROLLBACK: ${{ inputs.rollback }}
        run: |
          set -euo pipefail
          args=()
          if [ -n "${SHA}" ]; then args+=(--sha "${SHA}"); fi
          if [ "${ROLLBACK}" = true ]; then args+=(--rollback); fi
          python3 local-development/promote.py "${args[@]}"
```

<!-- block: local-development/promote.py | create -->
```python
#!/usr/bin/env python3
"""Promote a commit on main to the `release` branch that the lab's Argo CD tracks (#410).

    python3 local-development/promote.py                           # main's tip (what the workflow runs)
    python3 local-development/promote.py --sha <commit>            # a commit on main
    python3 local-development/promote.py --sha <commit> --rollback # even one older than what is promoted
    python3 local-development/promote.py --dry-run                 # read everything back, push nothing

The design, and every rule below, is docs/specs/SPEC_P1_promote_release_branch.md.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

RELEASE = "release"
PIN = "promotion.yaml"
CARRIED = ("charts/group-sync-dashboard", "environments")
IMAGES = ("group-sync-dashboard", "group-sync-dashboard-report")
PUBLISH = ".github/workflows/publish.yml"
ISSUER = "https://token.actions.githubusercontent.com"
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


class Refused(Exception):
    """Nothing is promoted; the message says why."""


def run(*cmd: str, cwd: str | None = None, data: bytes | None = None) -> str:
    done = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).decode(errors="replace").strip()
        raise Refused(f"`{' '.join(cmd[:4])}` failed: {detail}")
    return done.stdout.decode()


def git(*args: str) -> str:
    return run("git", *args).strip()


def image_inputs(publish_yml: str) -> list[str]:
    """publish.yml's on.push.paths. Read as text because the runner's python3 has no PyYAML."""
    lines = publish_yml.splitlines()
    try:
        start = lines.index("    paths:", lines.index("  push:"))
    except ValueError:
        raise Refused(f"{PUBLISH} has no on.push.paths list") from None
    paths = []
    for line in lines[start + 1:]:
        m = re.match(r"      - '([^']+)'", line)
        if not m:
            break
        paths.append(m.group(1))
    if not paths:
        raise Refused(f"{PUBLISH}'s on.push.paths list is empty")
    return paths


def image_candidates(target: str, first_parent: list[str], publish_yml: str) -> list[str]:
    """The main commits whose image is `target`'s image, newest first."""
    specs = [f":(glob){p}" for p in image_inputs(publish_yml)]
    changed = git("log", "--first-parent", "-1", "--format=%H", target, "--", *specs)
    if not changed:
        raise Refused(f"no commit at or before {target[:10]} changed an image input")
    line = first_parent[first_parent.index(target):]
    return line[:line.index(changed) + 1]


def built_image(repo: str, candidates: list[str]) -> tuple[str, int] | None:
    """(commit, run id) of the newest candidate publish.yml built on main; None while a run is still going."""
    running = False
    for sha in candidates:
        out = run("gh", "api", "-X", "GET", f"repos/{repo}/actions/workflows/publish.yml/runs",
                  "-f", f"head_sha={sha}", "-f", "per_page=100")
        runs = [r for r in json.loads(out)["workflow_runs"] if r.get("head_branch") == "main"]
        good = [r for r in runs if r.get("conclusion") == "success"]
        if good:
            return sha, good[0]["id"]
        running = running or any(r.get("status") != "completed" for r in runs)
    if running:
        return None
    raise Refused(f"no successful publish.yml run on main built this tree's image (tried "
                  f"{', '.join(c[:10] for c in candidates)}); an older image is not this tree's")


def read_back(ref: str, version: str, revision: str) -> str:
    """The digest of `ref`, or a refusal when its labels are not this version and commit."""
    info = json.loads(run("skopeo", "inspect", "--no-tags", f"docker://{ref}"))
    labels = info.get("Labels") or {}
    got = (labels.get("org.opencontainers.image.version"), labels.get("org.opencontainers.image.revision"))
    if got != (version, revision):
        raise Refused(f"{ref} is labelled version {got[0]!r}, revision {got[1]!r}; expected {version!r}, {revision!r}")
    digest = info.get("Digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise Refused(f"{ref} reported no sha256 digest (got {digest!r})")
    return digest


def verify_signature(image: str, digest: str, repo: str) -> None:
    identity = f"https://github.com/{repo}/.github/workflows/publish.yml@refs/heads/main"
    run("cosign", "verify", "--certificate-identity", identity, "--certificate-oidc-issuer", ISSUER, f"{image}@{digest}")


def field(text: str, pattern: str, what: str) -> str:
    m = re.search(pattern, text, re.M)
    if not m:
        raise Refused(f"cannot read {what}")
    return m.group(1)


def render_pin(source: str, image_commit: str, run_id: int, pins: list[tuple[str, str, str]]) -> str:
    (dash, dash_tag, dash_digest), (report, report_tag, report_digest) = pins
    return (
        "# Written by .github/workflows/promote.yml after both images were read back. Do not edit.\n"
        f"# source: {source}\n"
        f"# images: {image_commit} (publish.yml run {run_id})\n"
        "image:\n"
        f"  repository: {dash}\n"
        f'  tag: "{dash_tag}"\n'
        f'  digest: "{dash_digest}"\n'
        "reporting:\n"
        "  image:\n"
        f"    repository: {report}\n"
        f'    tag: "{report_tag}"\n'
        f'    digest: "{report_digest}"\n'
    )


def promoted_source() -> str | None:
    """The main commit `release` carries now; None before the first promotion."""
    if not git("ls-tree", "--name-only", f"origin/{RELEASE}", PIN):
        return None
    return field(git("show", f"origin/{RELEASE}:{PIN}"), r"^# source: ([0-9a-f]{40})$", f"the source in {RELEASE}:{PIN}")


def commit_release(target: str, pin: str, message: str, dry_run: bool) -> str | None:
    """Make `release` the carried paths at `target` plus the pin, and push it as a fast-forward."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = str(pathlib.Path(tmp) / RELEASE)
        git("worktree", "add", "-q", "--detach", tree, f"origin/{RELEASE}")
        try:
            run("git", "rm", "-rq", "--ignore-unmatch", ".", cwd=tree)
            run("tar", "-x", "-C", tree, data=subprocess.run(["git", "archive", target, *CARRIED],
                                                            capture_output=True, check=True).stdout)
            pathlib.Path(tree, PIN).write_text(pin)
            run("git", "add", "-A", cwd=tree)
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=tree).returncode == 0:
                return None
            if dry_run:
                print(run("git", "diff", "--cached", "--stat", cwd=tree))
                return None
            run("git", "-c", f"user.name={BOT[0]}", "-c", f"user.email={BOT[1]}", "commit", "-qm", message, cwd=tree)
            # No --force: a push that is not a fast-forward is refused, never overwritten.
            run("git", "push", "-q", "origin", f"HEAD:refs/heads/{RELEASE}", cwd=tree)
            return run("git", "rev-parse", "HEAD", cwd=tree).strip()
        finally:
            git("worktree", "remove", "--force", tree)


def promote(sha: str | None, rollback: bool, dry_run: bool) -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    registry = f"{os.environ.get('REGISTRY') or 'quay.io'}/{os.environ.get('REGISTRY_NAMESPACE') or 'ephico2real'}"
    signing = os.environ.get("SUPPLY_CHAIN_SIGNING", "") != "false"
    git("fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main")
    try:
        git("fetch", "-q", "origin", f"+refs/heads/{RELEASE}:refs/remotes/origin/{RELEASE}")
    except Refused:
        raise Refused(f"origin has no `{RELEASE}` branch; create it once (docs/CICD.md, Rollback and setup)") from None
    first_parent = git("rev-list", "--first-parent", "origin/main").split()
    target = git("rev-parse", "--verify", f"{sha or first_parent[0]}^{{commit}}")
    if target not in first_parent:
        raise Refused(f"{target[:10]} is not on main's first-parent line; only what main merged is promoted")

    chosen = built_image(repo, image_candidates(target, first_parent, git("show", f"{target}:{PUBLISH}")))
    if chosen is None:
        print(f"::notice::the image of {target[:10]} is still being published; that run's completion promotes it")
        return 0
    image_commit, run_id = chosen
    version = field(git("show", f"{image_commit}:local-development/pyproject.toml"), r'^version = "(.+?)"$',
                    "pyproject.toml's version")
    app_version = field(git("show", f"{target}:charts/group-sync-dashboard/Chart.yaml"), r'^appVersion: "(.+?)"$',
                        "Chart.yaml's appVersion")
    if version != app_version:
        raise Refused(f"the chart at {target[:10]} deploys appVersion {app_version}, the image is {version}")
    short = git("rev-parse", "--short=10", image_commit)
    tag = f"{version}-{short}"
    pins = []
    for name in IMAGES:
        image = f"{registry}/{name}"
        digest = read_back(f"{image}:{tag}", version, short)
        if signing:
            verify_signature(image, digest, repo)
        pins.append((image, tag, digest))
        print(f"image   : {image}:{tag} -> {digest}{' (signature verified)' if signing else ''}")

    promoted = promoted_source()
    if promoted and promoted != target and not rollback \
            and subprocess.run(["git", "merge-base", "--is-ancestor", promoted, target]).returncode != 0:
        raise Refused(f"{RELEASE} carries {promoted[:10]}, which {target[:10]} does not descend from;"
                      " dispatch with rollback to move the lab back on purpose")
    message = (f"promote main@{target[:10]}: {tag}\n\nsource: {target}\nimages: {image_commit} (publish.yml run {run_id})\n"
               + "".join(f"{image}@{digest}\n" for image, _, digest in pins))
    pushed = commit_release(target, render_pin(target, image_commit, run_id, pins), message, dry_run)
    print(f"release : {pushed or 'unchanged'} (main@{target[:10]}, {tag}{', dry run' if dry_run else ''})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--sha", help="the commit on main to promote (default: main's tip)")
    parser.add_argument("--rollback", action="store_true", help="allow a commit older than the one promoted")
    parser.add_argument("--dry-run", action="store_true", help="read back and show the change; push nothing")
    args = parser.parse_args(argv)
    try:
        return promote(args.sha, args.rollback, args.dry_run)
    except Refused as exc:
        print(f"::error::not promoted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->
```yaml
# on main with environments/crc.yaml — as release `group-sync-dashboard` into group-sync-dashboard, the
```

```yaml
# on `release` with environments/crc.yaml — as release `group-sync-dashboard` into group-sync-dashboard, the
```

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->
```yaml
# Iterating on a branch: point targetRevision at it, or pause (`argocd app set group-sync-dashboard
# --sync-policy none`) and use release-crc.sh — never both at once, Argo's prune and selfHeal would
# undo a hand-installed release.
```

```yaml
# `release` holds only what .github/workflows/promote.yml committed after reading both images back
# (docs/CICD.md). promotion.yaml, last in valueFiles, pins both images by digest and exists only there.
#
# Iterating on a branch: `release-crc.sh --argocd <branch>` (it drops promotion.yaml from valueFiles),
# or pause (`argocd app set group-sync-dashboard --sync-policy none`) and use release-crc.sh — never both
# at once, Argo's prune and selfHeal would undo a hand-installed release.
```

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->
```yaml
    targetRevision: main
```

```yaml
    targetRevision: release
```

<!-- block: gitops/argocd-application-dashboard.yaml | edit -->
```yaml
        - ../../environments/crc.yaml
      valuesObject:
```

```yaml
        - ../../environments/crc.yaml
        - ../../promotion.yaml
      valuesObject:
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
#                                                                                                         origin/<branch>
#   --build-only                    (none)   —                   built, NOT pushed     —                  —
```

```bash
#                                                                                                         origin/<branch>
#   --argocd release                Argo     GitHub @ release    promotion.yaml's      default +          a promotion on
#                                                                digests, read back    promotion.yaml     origin/release
#   --build-only                    (none)   —                   built, NOT pushed     —                  —
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
# --argocd on the pushed head; after a merge, --argocd main. The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298) — a guarantee
# about the RELEASE COMMIT, not about the tag on quay, which the branch path reads back (below).
```

```bash
# --argocd on the pushed head; after a merge, promote.yml deploys it through `release`, and
# --argocd release hands the lab back to that (docs/CICD.md). --argocd main still works and reads
# the :<appVersion> alias back (below); it is for testing, the lab tracks release.
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
  ARGO_VALUES="../../${VALUES_FILE}"
else
  RELEASE_VALUES="${RELEASE_VALUES:-../environments/crc.yaml}"
  ARGO_VALUES=""                                       # the Application's own default
fi
```

```bash
else
  RELEASE_VALUES="${RELEASE_VALUES:-../environments/crc.yaml}"
fi
# Always stated: the Application's default ends with promotion.yaml, which exists only on release.
ARGO_VALUES="../../${VALUES_FILE:-environments/crc.yaml}"
PIN=promotion.yaml
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
if values:
    helm["valueFiles"] = [values]
```

```bash
helm["valueFiles"] = values.split(",")
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
  chart=$(git show "${revision}:charts/group-sync-dashboard/Chart.yaml") || return 1
  values=$(git show "${revision}:charts/group-sync-dashboard/values.yaml") || return 1
```

```bash
  chart=$(git show "${revision}:charts/group-sync-dashboard/Chart.yaml") || return 1
  if git cat-file -e "${revision}:${PIN}" 2>/dev/null; then
    promoted_images_are_the_release "$revision" "$chart"
    return
  fi
  values=$(git show "${revision}:charts/group-sync-dashboard/values.yaml") || return 1
```

<!-- block: local-development/release-crc.sh | edit -->
```bash

# --argocd <branch> with no build: point the Application at that branch and its chart's default
```

```bash

# release: the digests promote.yml pinned, read back again, because Argo will pull exactly these.
promoted_images_are_the_release() {
  local revision="$1" chart="$2" app_version rows repo tag digest commit labels
  app_version=$(printf '%s\n' "$chart" | sed -n 's/^appVersion: "\([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)"$/\1/p' | head -1)
  # A variable, not a process substitution: a pin that does not parse must stop the deploy.
  if ! rows=$(git show "${revision}:${PIN}" | python3 -c '
import re, sys
rows = re.findall(r"^ +repository: (\S+)\n +tag: \"([^\"]+)\"\n +digest: \"(sha256:[0-9a-f]{64})\"$", sys.stdin.read(), re.M)
if len(rows) != 2:
    sys.exit("expected two pinned images")
for row in rows:
    print(*row)'); then
    echo "ERROR: cannot read the two pinned images from ${PIN} on origin/${revision}." >&2
    return 1
  fi
  while read -r repo tag digest; do
    commit="${tag#"${app_version}"-}"
    if ! labels=$(oc image info "${repo}@${digest}" --filter-by-os='linux/.*' --show-multiarch -o json 2>/dev/null | python3 -c '
import json, sys
images = json.load(sys.stdin)
images = [images] if isinstance(images, dict) else images
labels = [(i.get("config", {}).get("config", {}).get("Labels") or {}) for i in images]
print(" ".join(sorted({l.get("org.opencontainers.image.version", "") + "/" + l.get("org.opencontainers.image.revision", "") for l in labels})))'); then
      echo "ERROR: ${repo}@${digest}, pinned in ${PIN} on origin/${revision}, is not in the registry." >&2
      return 1
    fi
    if [ "$labels" != "${app_version}/${commit}" ]; then
      echo "ERROR: ${repo}@${digest} is ${labels:-unlabelled}, not ${app_version}/${commit} (${PIN} on origin/${revision})." >&2
      return 1
    fi
    echo "image   : ${repo}@${digest} is application ${app_version}, commit ${commit}"
  done <<< "$rows"
}

# --argocd <branch> with no build: point the Application at that branch and its chart's default
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
  published_image_is_the_release "$EXPECTED_REVISION" || exit 1
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
```

```bash
  published_image_is_the_release "$EXPECTED_REVISION" || exit 1
  git cat-file -e "${EXPECTED_REVISION}:${PIN}" 2>/dev/null && ARGO_VALUES="${ARGO_VALUES},../../${PIN}"
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
  fi
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$ARGO_REVISION"
```

```bash
  fi
  echo "values  : ${ARGO_VALUES} (the Application's valueFiles)"
  apply_application "$ARGO_REVISION"
```

<!-- block: local-development/release-crc.sh | edit -->
```bash
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
```

```bash
  echo "values  : ${ARGO_VALUES} (the Application's valueFiles)"
```

<!-- block: local-development/tests/test_promote.py | create -->
```python
"""promote.py end to end: real git with a bare origin, stubs for gh, skopeo and cosign (#410, SPEC_P1)."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess

import pytest
import yaml

LOCAL_DEV = pathlib.Path(__file__).resolve().parents[1]
REPO = LOCAL_DEV.parent
SCRIPT = LOCAL_DEV / "promote.py"
PUBLISH = REPO / ".github" / "workflows" / "publish.yml"

STUB = r'''#!/usr/bin/env bash
# One line per call in STUB_LOG; answers come from JSON files the test writes.
printf '%s %s\n' "$(basename "$0")" "$*" >> "$STUB_LOG"
case "$(basename "$0")" in
  gh)
    all="$*"; sha="${all##*head_sha=}"; sha="${sha%% *}"
    python3 -c 'import json,sys; print(json.dumps({"workflow_runs": json.load(open(sys.argv[1])).get(sys.argv[2], [])}))' "$STUB_RUNS" "$sha" ;;
  skopeo)
    ref="${!#}"; ref="${ref#docker://}"
    python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(1) if sys.argv[2] not in d else print(json.dumps(d[sys.argv[2]]))' "$STUB_REGISTRY" "$ref" ;;
  cosign) exit "${STUB_COSIGN_RC:-0}" ;;
esac
'''

GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _load():
    spec = importlib.util.spec_from_file_location("promote", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, capture_output=True, text=True)
    assert done.returncode == 0, f"git {args}: {done.stderr}"
    return done.stdout.strip()


class Lab:
    def __init__(self, tmp: pathlib.Path):
        self.tmp, self.origin, self.src, self.runner = tmp, tmp / "origin.git", tmp / "src", tmp / "runner"
        self.runs, self.registry, self.log = tmp / "runs.json", tmp / "registry.json", tmp / "calls.log"
        self.runs.write_text("{}")
        self.registry.write_text("{}")
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp, "init", "-q", "-b", "main", str(self.src))
        git(self.src, "remote", "add", "origin", str(self.origin))
        self.commit({".github/workflows/publish.yml": PUBLISH.read_text(), ".github/workflows/ci.yml": "name: ci\n",
                     "charts/group-sync-dashboard/Chart.yaml": 'name: group-sync-dashboard\nversion: 0.1.0\nappVersion: "1.1.0"\n',
                     "charts/group-sync-dashboard/values.yaml": 'image:\n  tag: ""\n',
                     "environments/crc.yaml": "logLevel: DEBUG\n", "docs/notes.md": "notes\n",
                     "local-development/pyproject.toml": 'version = "1.1.0"\n', "local-development/gsd/app.py": "v = 0\n"})
        git(self.src, "checkout", "-q", "--orphan", "release")
        git(self.src, "rm", "-rqf", ".")
        git(self.src, "commit", "-q", "--allow-empty", "-m", "the promotion branch")
        git(self.src, "push", "-q", "origin", "release")
        git(self.src, "checkout", "-q", "main")
        git(tmp, "clone", "-q", str(self.origin), str(self.runner))
        bindir = tmp / "bin"
        bindir.mkdir()
        for tool in ("gh", "skopeo", "cosign"):
            (bindir / tool).write_text(STUB)
            (bindir / tool).chmod(0o755)
        self.env = {**os.environ, **GIT_ENV, "PATH": f"{bindir}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
                    "STUB_RUNS": str(self.runs), "STUB_REGISTRY": str(self.registry), "GITHUB_REPOSITORY": "o/r",
                    "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example"}
        self.env.pop("SUPPLY_CHAIN_SIGNING", None)

    def commit(self, files: dict[str, str], message: str = "change") -> str:
        for path, text in files.items():
            (self.src / path).parent.mkdir(parents=True, exist_ok=True)
            (self.src / path).write_text(text)
        git(self.src, "add", "-A")
        git(self.src, "commit", "-qm", message)
        git(self.src, "push", "-q", "origin", "main")
        return git(self.src, "rev-parse", "HEAD")

    def publish(self, sha: str, conclusion: str | None = "success", version: str = "1.1.0", revision: str | None = None) -> None:
        """A publish.yml run for `sha`; with a conclusion of success, both images in the registry."""
        runs = json.loads(self.runs.read_text())
        runs.setdefault(sha, []).append({"id": len(runs) + 1, "head_branch": "main", "status": "completed" if conclusion else "in_progress",
                                         "conclusion": conclusion})
        self.runs.write_text(json.dumps(runs))
        if conclusion == "success":
            registry = json.loads(self.registry.read_text())
            for name in ("group-sync-dashboard", "group-sync-dashboard-report"):
                registry[f"quay.io/example/{name}:{version}-{sha[:10]}"] = {
                    "Digest": "sha256:" + (sha + name).encode().hex()[:64],
                    "Labels": {"org.opencontainers.image.version": version, "org.opencontainers.image.revision": revision or sha[:10]}}
            self.registry.write_text(json.dumps(registry))

    def promote(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(SCRIPT), *args], cwd=self.runner, env={**self.env, **env}, capture_output=True, text=True)

    def release(self) -> str:
        return git(self.src, "ls-remote", "origin", "refs/heads/release").split()[0]

    def pin(self) -> str:
        git(self.src, "fetch", "-q", "origin", "release")
        return git(self.src, "show", "FETCH_HEAD:promotion.yaml")


@pytest.fixture
def lab(tmp_path: pathlib.Path) -> Lab:
    return Lab(tmp_path)


def test_a_code_merge_is_promoted_with_both_images_pinned_by_digest(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote()
    assert r.returncode == 0, r.stdout + r.stderr
    pin = lab.pin()
    assert f"# source: {a}" in pin and f'tag: "1.1.0-{a[:10]}"' in pin
    assert pin.count('digest: "sha256:') == 2
    tree = git(lab.src, "ls-tree", "-r", "--name-only", "FETCH_HEAD").split()
    assert sorted({p.split("/")[0] for p in tree}) == ["charts", "environments", "promotion.yaml"], tree
    assert "cosign verify" in lab.log.read_text(), "signing is on unless SUPPLY_CHAIN_SIGNING is false"


def test_a_chart_only_merge_carries_the_image_of_the_last_image_input_commit(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    b = lab.commit({"charts/group-sync-dashboard/values.yaml": 'image:\n  tag: ""\nnew: 1\n'})
    r = lab.promote()
    assert r.returncode == 0, r.stdout + r.stderr
    pin = lab.pin()
    assert f"# source: {b}" in pin and f'tag: "1.1.0-{a[:10]}"' in pin
    assert "new: 1" in git(lab.src, "show", "FETCH_HEAD:charts/group-sync-dashboard/values.yaml")


def test_a_failed_publish_is_never_promoted_even_when_an_older_image_exists(lab):
    old = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(old)
    a = lab.commit({"local-development/gsd/app.py": "v = 2\n"})
    lab.publish(a, conclusion="failure")
    lab.commit({"environments/crc.yaml": "logLevel: INFO\n"})
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 1 and "no successful publish.yml run" in r.stderr, r.stdout + r.stderr
    assert lab.release() == before


def test_a_publish_still_running_waits_for_its_own_completion(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a, conclusion=None)
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 0 and "still being published" in r.stdout, r.stdout + r.stderr
    assert lab.release() == before


@pytest.mark.parametrize("version, revision", [("0.24.0", None), ("1.1.0", "0123456789")], ids=["version", "revision"])
def test_an_image_whose_labels_are_not_this_build_is_refused(lab, version, revision):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a, revision=revision)
    if version != "1.1.0":
        registry = json.loads(lab.registry.read_text())
        for entry in registry.values():
            entry["Labels"]["org.opencontainers.image.version"] = version
        lab.registry.write_text(json.dumps(registry))
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 1 and "is labelled version" in r.stderr, r.stdout + r.stderr
    assert lab.release() == before


def test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_it(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote(STUB_COSIGN_RC="1")
    assert r.returncode == 1 and "cosign verify" in r.stderr, r.stdout + r.stderr
    lab.log.write_text("")
    r = lab.promote(SUPPLY_CHAIN_SIGNING="false")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cosign" not in lab.log.read_text()


def test_an_older_commit_needs_rollback_and_a_second_run_changes_nothing(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    b = lab.commit({"local-development/gsd/app.py": "v = 2\n"})
    lab.publish(b)
    assert lab.promote().returncode == 0
    promoted = lab.release()
    assert lab.promote().returncode == 0 and lab.release() == promoted, "promoting the same tree again is a no-op"
    r = lab.promote("--sha", a)
    assert r.returncode == 1 and "does not descend from" in r.stderr, r.stdout + r.stderr
    r = lab.promote("--sha", a, "--rollback")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"# source: {a}" in lab.pin()


def test_without_a_release_branch_nothing_is_promoted(lab):
    git(lab.src, "push", "-q", "origin", "--delete", "release")
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote()
    assert r.returncode == 1 and "origin has no `release` branch" in r.stderr, r.stdout + r.stderr


def test_the_image_input_reader_is_publish_ymls_path_filter():
    parsed = yaml.safe_load(PUBLISH.read_text())
    assert _load().image_inputs(PUBLISH.read_text()) == (parsed.get("on") or parsed[True])["push"]["paths"]
```

<!-- block: local-development/tests/test_promote_workflow.py | create -->
```python
"""promote.yml, and the three places that name the promoted artifact, agree (#410, SPEC_P1)."""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
PROMOTE = WORKFLOWS / "promote.yml"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text())


def _on(workflow: dict) -> dict:
    return workflow.get("on") or workflow[True]   # YAML 1.1 reads `on` as True


def test_it_runs_after_publish_and_promotes_only_a_success():
    on = _on(_load(PROMOTE))
    assert on["workflow_run"] == {"workflows": [_load(WORKFLOWS / "publish.yml")["name"]], "types": ["completed"], "branches": ["main"]}
    job = _load(PROMOTE)["jobs"]["promote"]
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "github.repository == 'ephico2real2/group-sync-dashboard'" in job["if"]


def test_a_chart_only_merge_triggers_it_and_a_dispatch_can_roll_back():
    on = _on(_load(PROMOTE))
    assert on["push"]["branches"] == ["main"]
    assert {"charts/group-sync-dashboard/**", "environments/**"} <= set(on["push"]["paths"])
    assert set(on["workflow_dispatch"]["inputs"]) == {"sha", "rollback"}


def test_one_promotion_at_a_time_and_only_the_scopes_it_needs():
    wf = _load(PROMOTE)
    assert wf["concurrency"] == {"group": "promote-release", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["promote"]["permissions"] == {"contents": "write", "actions": "read"}


def test_nothing_in_it_builds():
    text = PROMOTE.read_text()
    for builder in ("podman", "docker build", "build-and-push", "buildx"):
        assert builder not in text, builder


def test_it_verifies_with_the_cosign_publish_signs_with():
    def installer(path: pathlib.Path) -> tuple[str, str]:
        steps = [s for job in _load(path)["jobs"].values() for s in job["steps"] if "cosign-installer" in (s.get("uses") or "")]
        return steps[0]["uses"], steps[0]["with"]["cosign-release"]
    assert installer(PROMOTE) == installer(WORKFLOWS / "publish.yml")


def test_the_application_script_and_workflow_name_one_pin_file_on_release():
    app = _load(REPO / "gitops" / "argocd-application-dashboard.yaml")["spec"]["source"]
    assert app["targetRevision"] == "release"
    assert app["helm"]["valueFiles"] == ["../../environments/crc.yaml", "../../promotion.yaml"], "the pin must come last to win"
    assert re.search(r'^PIN = "promotion.yaml"$', (REPO / "local-development" / "promote.py").read_text(), re.M)
    assert re.search(r"^PIN=promotion.yaml$", (REPO / "local-development" / "release-crc.sh").read_text(), re.M)
```

<!-- block: local-development/tests/test_release_crc.py | edit -->
```python
  "oc image info "*)     # the registry: STUB_IMAGES is "<ref>=<org.opencontainers.image.version> ..."; an unlisted ref is absent
      # STUB_OCI_DIR: the real oc reads a manifest list from its on-disk registry instead, same flags.
      [ -n "${STUB_OCI_DIR:-}" ] && exec "$STUB_REAL_OC" image info --dir "$STUB_OCI_DIR" file://review/multi:good "${@:4}"
      for entry in $STUB_IMAGES; do
        case "$entry" in "${3}="*) printf '{"digest":"sha256:stub","config":{"config":{"Labels":{"org.opencontainers.image.version":"%s"}}}}\n' "${entry#*=}"; exit 0 ;; esac
```

```python
  "oc image info "*)     # the registry: STUB_IMAGES is "<ref>=<version>[/<revision>] ..."; an unlisted ref is absent
      # STUB_OCI_DIR: the real oc reads a manifest list from its on-disk registry instead, same flags.
      [ -n "${STUB_OCI_DIR:-}" ] && exec "$STUB_REAL_OC" image info --dir "$STUB_OCI_DIR" file://review/multi:good "${@:4}"
      for entry in $STUB_IMAGES; do
        case "$entry" in "${3}="*) v="${entry#*=}"; r=""; [ "$v" != "${v%/*}" ] && r="${v#*/}"
          printf '{"digest":"sha256:stub","config":{"config":{"Labels":{"org.opencontainers.image.version":"%s","org.opencontainers.image.revision":"%s"}}}}\n' "${v%%/*}" "$r"; exit 0 ;; esac
```

<!-- block: local-development/tests/test_release_crc.py | edit -->
```python
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": []}}
```

```python
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": [], "valueFiles": ["../../environments/crc.yaml"]}}
```

<!-- block: local-development/tests/test_release_crc.py | edit -->
```python

# --- the waiter on its own ----------------------------------------------------------------------
```

```python

# --- the release branch promote.yml writes (#410) ------------------------------------------------

def _promotion(lab, dashboard: str, report: str) -> str:
    """origin/release as promote.py leaves it: the chart, environments/ and promotion.yaml; `dashboard` and
    `report` are the labels the registry reports for the two pinned digests (`<version>/<revision>`)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("promote", LOCAL_DEV / "promote.py")
    promote = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(promote)
    tag = f"{_version()}-{lab['full'][:10]}"
    pins = [(f"quay.io/example/{name}", tag, "sha256:" + f"{n}" * 64) for n, name in enumerate(("group-sync-dashboard", "group-sync-dashboard-report"), 1)]
    _git(lab["repo"], "checkout", "-q", "--orphan", "release")
    (lab["repo"] / "promotion.yaml").write_text(promote.render_pin(lab["full"], lab["full"], 1, pins))
    _git(lab["repo"], "add", "promotion.yaml", "charts", "environments")
    _git(lab["repo"], "commit", "-qm", "promote"); _git(lab["repo"], "push", "-q", "origin", "release")
    release = _git(lab["repo"], "rev-parse", "HEAD")
    _git(lab["repo"], "checkout", "-qf", "main")
    lab["env"]["STUB_IMAGES"] = f"{pins[0][0]}@{pins[0][2]}={dashboard} {pins[1][0]}@{pins[1][2]}={report}"
    synced_status(lab, release)
    return release


def test_argocd_release_reads_the_pinned_digests_back_and_adds_the_pin_last(lab):
    good = f"{_version()}/{lab['full'][:10]}"
    _promotion(lab, good, good)
    r = run(lab, "--argocd", "release")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert "oc image info quay.io/example/group-sync-dashboard@sha256:1111" in log
    assert "oc image info quay.io/example/group-sync-dashboard-report@sha256:2222" in log
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    source = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])["spec"]["source"]
    assert source == {"targetRevision": "release",
                      "helm": {"parameters": [], "valueFiles": ["../../environments/crc.yaml", "../../promotion.yaml"]}}


@pytest.mark.parametrize("report", ["0.24.0/0123456789", "", "absent"], ids=["other-build", "unlabelled", "absent"])
def test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release(lab, report):
    _promotion(lab, f"{_version()}/{lab['full'][:10]}", report)
    if report == "absent":
        lab["env"]["STUB_IMAGES"] = lab["env"]["STUB_IMAGES"].split()[0]
    r = run(lab, "--argocd", "release")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "group-sync-dashboard-report@sha256:2222" in r.stderr
    assert "oc apply" not in calls(lab) and "helm uninstall" not in calls(lab)


# --- the waiter on its own ----------------------------------------------------------------------
```

<!-- block: docs/diagrams/cicd/source.html | create -->
```html
<title>Build Once, Promote</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f5f6f8; --surface: #ffffff; --ink: #18212c; --muted: #58636f; --rule: #d7dce3; --lane: #f0f2f5;
  --build: #a55a0b; --build-wash: #fbf1e4; --ship: #0e6f68; --ship-wash: #e3f3f1;
  --gap: #b3261e; --gap-wash: #fbe9e7; --none: #6b7684; --none-wash: #eef0f3;
  --font-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
    --build: #f0a53c; --build-wash: #2a2014; --ship: #3fcfc0; --ship-wash: #122a28;
    --gap: #f2857c; --gap-wash: #2d1614; --none: #9aa5b3; --none-wash: #1b232d;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --ground: #0e131a; --surface: #151c25; --ink: #e5e9ef; --muted: #9aa5b3; --rule: #2a3440; --lane: #111821;
  --build: #f0a53c; --build-wash: #2a2014; --ship: #3fcfc0; --ship-wash: #122a28;
  --gap: #f2857c; --gap-wash: #2d1614; --none: #9aa5b3; --none-wash: #1b232d;
}
* { box-sizing: border-box; }
body { background: var(--ground); color: var(--ink); font-family: var(--font-body); font-size: 15px; line-height: 1.55; margin: 0; }
.page { max-width: 1160px; margin: 0 auto; padding-inline: 16px; padding-block: 32px 56px; display: grid; gap: 28px; }
header { display: grid; gap: 10px; }
.eyebrow { font-family: var(--font-mono); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
h1 { font-size: clamp(24px, 4vw, 34px); line-height: 1.15; margin: 0; font-weight: 700; text-wrap: balance; }
p { margin: 0; max-width: 72ch; }
code { font-family: var(--font-mono); font-size: .9em; }
figure { margin: 0; display: grid; gap: 10px; }
.fig-scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--rule); border-radius: 10px; padding: 12px; }
.fig-scroll svg { display: block; width: 100%; min-width: 760px; height: auto; color: var(--ink); }
figcaption { font-size: 13.5px; color: var(--muted); max-width: 80ch; }
</style>

<div class="page">
  <header>
    <div class="eyebrow">group-sync-dashboard · CI/CD · #410</div>
    <h1>From a pull request to the cluster: build once, promote the artifact</h1>
    <p>Main is the source. <code>publish.yml</code> builds the images once. <code>promote.yml</code> reads them back
      and commits the chart with the images pinned by digest to the <code>release</code> branch. Argo CD syncs only
      <code>release</code>.</p>
  </header>

  <figure>
    <div class="fig-scroll">
      <svg viewBox="0 0 1100 720" role="img" aria-label="The pipeline in five lanes, time flowing down. A pull request passes ci.yml and is merged to main. publish.yml builds, pushes and signs the image 1.1.0 dash sha10 on quay.io, and moves the 1.1.0 alias only on a version bump. If publish fails, nothing is promoted. When publish succeeds, or a chart-only merge lands, promote.yml reads both images back from quay.io, checking labels, digest and signature, then commits the chart and promotion.yaml with the digests to the release branch. Argo CD syncs release and pulls the images by digest. A rollback is a manual run of promote.yml with an older commit.">
        <defs>
          <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="currentColor"/></marker>
          <marker id="ah-ship" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--ship)"/></marker>
          <marker id="ah-build" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--build)"/></marker>
          <marker id="ah-gap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="var(--gap)"/></marker>
        </defs>
        <!-- lanes: one trust boundary each -->
        <g fill="var(--lane)">
          <rect x="0" y="0" width="220" height="720"/><rect x="440" y="0" width="220" height="720"/><rect x="880" y="0" width="220" height="720"/>
        </g>
        <g stroke="var(--rule)"><line x1="220" y1="0" x2="220" y2="720"/><line x1="440" y1="0" x2="440" y2="720"/><line x1="660" y1="0" x2="660" y2="720"/><line x1="880" y1="0" x2="880" y2="720"/></g>
        <g font-family="IBM Plex Mono, monospace" font-size="12.5" font-weight="600" fill="var(--muted)" text-anchor="middle">
          <text x="110" y="30">GITHUB · PULL REQUEST</text>
          <text x="330" y="30">GITHUB · MAIN</text>
          <text x="550" y="30">QUAY.IO</text>
          <text x="770" y="30">RELEASE BRANCH</text>
          <text x="990" y="30">CLUSTER · ARGO CD</text>
        </g>
        <text x="1090" y="706" text-anchor="end" font-family="IBM Plex Sans, sans-serif" font-size="12" fill="var(--muted)">time flows down</text>

        <g font-family="IBM Plex Sans, sans-serif" font-size="12.5" fill="currentColor" text-anchor="middle">
          <!-- pull request -->
          <rect x="15" y="60" width="190" height="40" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="110" y="85" font-weight="600">you open a pull request</text>
          <rect x="15" y="124" width="190" height="72" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="110" y="146" font-weight="600">ci.yml checks the PR</text>
          <text x="110" y="164">tests · chart · image scan</text>
          <text x="110" y="182">chart change → version bump</text>
          <rect x="15" y="214" width="190" height="44" rx="6" fill="none" stroke="var(--none)" stroke-dasharray="5 4" stroke-width="1.2"/>
          <text x="110" y="232" fill="var(--none)">image changed → app version</text>
          <text x="110" y="249" fill="var(--none)">bumped (#427, planned)</text>
          <line x1="110" y1="100" x2="110" y2="120" stroke="currentColor" stroke-width="1.2" marker-end="url(#ah)"/>
          <path d="M110,196 L110,210" stroke="var(--none)" stroke-dasharray="3 3" fill="none"/>
          <path d="M110,258 L110,292 L231,292" stroke="currentColor" stroke-width="1.2" fill="none" marker-end="url(#ah)"/>
          <text x="118" y="284" text-anchor="start" fill="var(--muted)">reviewed, merged</text>

          <!-- main: merge, publish -->
          <rect x="235" y="272" width="190" height="40" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="330" y="297" font-weight="600">merge to main</text>
          <rect x="265" y="344" width="130" height="64" rx="6" fill="var(--build-wash)" stroke="var(--build)" stroke-width="1.5"/>
          <text x="330" y="368" font-weight="600" fill="var(--build)">publish.yml</text>
          <text x="330" y="386">runs if an image</text>
          <text x="330" y="401">input changed</text>
          <line x1="330" y1="312" x2="330" y2="340" stroke="currentColor" stroke-width="1.2" marker-end="url(#ah)"/>

          <!-- quay: the build, and the failure branch -->
          <rect x="455" y="328" width="190" height="96" rx="6" fill="var(--build-wash)" stroke="var(--build)" stroke-width="1.5"/>
          <text x="550" y="350" font-weight="600" fill="var(--build)">1.1.0-&lt;sha10&gt;</text>
          <text x="550" y="367">immutable, every build</text>
          <text x="550" y="386" font-weight="600" fill="var(--build)">:1.1.0 alias</text>
          <text x="550" y="403">moves on a version bump</text>
          <text x="550" y="418" fill="var(--muted)">signed · SBOM attached</text>
          <line x1="395" y1="368" x2="451" y2="368" stroke="var(--build)" stroke-width="1.5" marker-end="url(#ah-build)"/>
          <text x="423" y="360" fill="var(--build)" font-size="11.5">builds</text>
          <rect x="455" y="264" width="190" height="44" rx="6" fill="var(--gap-wash)" stroke="var(--gap)" stroke-dasharray="5 4" stroke-width="1.3"/>
          <text x="550" y="283" font-weight="600" fill="var(--gap)">publish failed</text>
          <text x="550" y="300" fill="var(--gap)">nothing is promoted</text>
          <path d="M395,352 L451,300" stroke="var(--gap)" stroke-dasharray="4 3" stroke-width="1.3" fill="none" marker-end="url(#ah-gap)"/>

          <!-- main: promote, and its three ways in -->
          <rect x="235" y="540" width="190" height="64" rx="6" fill="var(--ship-wash)" stroke="var(--ship)" stroke-width="1.5"/>
          <text x="330" y="563" font-weight="600" fill="var(--ship)">promote.yml</text>
          <text x="330" y="581">reads both images back,</text>
          <text x="330" y="597">then commits</text>
          <line x1="330" y1="408" x2="330" y2="536" stroke="var(--ship)" stroke-width="1.5" marker-end="url(#ah-ship)"/>
          <text x="322" y="500" text-anchor="end" fill="var(--ship)">succeeds</text>
          <path d="M250,312 L250,536" stroke="currentColor" stroke-dasharray="5 4" stroke-width="1.2" fill="none" marker-end="url(#ah)"/>
          <text x="258" y="440" text-anchor="start" fill="var(--muted)">chart-only</text>
          <text x="258" y="455" text-anchor="start" fill="var(--muted)">merge</text>
          <path d="M500,424 L410,536" stroke="var(--ship)" stroke-width="1.3" fill="none" marker-end="url(#ah-ship)"/>
          <text x="505" y="470" text-anchor="start" fill="var(--ship)">read back: labels,</text>
          <text x="505" y="486" text-anchor="start" fill="var(--ship)">digest, signature</text>
          <rect x="235" y="650" width="190" height="44" rx="6" fill="none" stroke="currentColor" stroke-dasharray="5 4" stroke-width="1.2"/>
          <text x="330" y="669">rollback: run promote.yml</text>
          <text x="330" y="686">with an older sha</text>
          <line x1="330" y1="650" x2="330" y2="608" stroke="currentColor" stroke-dasharray="5 4" stroke-width="1.2" marker-end="url(#ah)"/>

          <!-- release, then the cluster -->
          <rect x="675" y="532" width="190" height="80" rx="6" fill="var(--ship-wash)" stroke="var(--ship)" stroke-width="1.5"/>
          <text x="770" y="554" font-weight="600" fill="var(--ship)">release</text>
          <text x="770" y="572">chart + environments/</text>
          <text x="770" y="590">promotion.yaml: digests</text>
          <text x="770" y="606" fill="var(--muted)">no workflows, no builds</text>
          <line x1="425" y1="572" x2="671" y2="572" stroke="var(--ship)" stroke-width="1.5" marker-end="url(#ah-ship)"/>
          <text x="548" y="566" fill="var(--ship)">commits the pinned artifact</text>
          <rect x="895" y="532" width="190" height="80" rx="6" fill="var(--surface)" stroke="currentColor" stroke-width="1.2"/>
          <text x="990" y="556" font-weight="600">Argo CD syncs release</text>
          <text x="990" y="576">pulls both images</text>
          <text x="990" y="594">by digest</text>
          <line x1="865" y1="572" x2="891" y2="572" stroke="var(--ship)" stroke-width="1.5" marker-end="url(#ah-ship)"/>
        </g>
      </svg>
    </div>
    <figcaption>Only <code>promote.yml</code> writes to <code>release</code>, and only after both images are read back.
      A failed publish never reaches it. A chart-only merge reuses the image of the last commit that changed an image
      input. <code>helm.yaml</code>'s chart release to the Helm repository is not drawn: the lab does not read it.</figcaption>
  </figure>
</div>
```

<!-- block: docs/CICD.md | create -->
```markdown
# CI/CD: from a pull request to the cluster

This page follows one change from "I opened a pull request" to "it is running on the cluster". The rule behind it:
**build once, then promote the artifact.** The image is built one time, from `main`. What the cluster runs is that
same image, checked and pinned, never a rebuild and never a moving tag.

## The short version

1. You open a pull request. `ci.yml` tests it.
2. It is reviewed and merged to `main`.
3. `publish.yml` builds the two images and pushes them to quay.io, signed.
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

*Figure 1. Five lanes, time flowing down. `publish.yml` builds on quay.io; `promote.yml` reads back and commits to
`release`; Argo CD syncs `release`. A failed publish stops the line. A chart-only merge goes straight to
`promote.yml` and reuses the last image. A rollback is a manual run of `promote.yml`. The app-version check is dashed
because it is #427's, not built yet.*

````text
GITHUB PR            GITHUB MAIN          QUAY.IO               RELEASE BRANCH        CLUSTER (ARGO CD)
open a PR
ci.yml checks
(#427 app-version
 check: planned)
    | merged
    +----------------> merge to main
                         |          \ chart-only merge (skips publish)
                       publish.yml --builds--> 1.1.0-<sha10>
                         |    \                :1.1.0 on a version bump
                         |     \               signed, SBOM
                         |      `--fails--> "publish failed: nothing is promoted"
                         | succeeds
                       promote.yml <--reads back: labels, digest, signature--
                         |
                         +--commits the pinned artifact--> release: chart,
                         ^                                 environments/,
                         |                                 promotion.yaml ----syncs----> pulls both
                  rollback: run promote.yml                                              images by digest
                  with an older sha
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
| `image` | builds the image and scans it for CVEs; not a required check, and the CVE report is advisory |

Planned, #427: a check that a change to the image also bumps the application version. It is not built yet.

### 2. The merge

A merge to `main` starts the workflows below. Nobody pushes to `main` directly; it is branch protected.

### 3. Publish: build once

`publish.yml` runs only when a file that goes into the image changed (its `paths:` list). It then:

1. builds both images and tags them `<appVersion>-<sha10>`, for example `1.1.0-0123456789`;
2. moves the alias `:<appVersion>` only if the merge changed the application version;
3. signs each image by digest with cosign, attaches an SBOM, and reads the signature back.

A merge that changes only the chart, the environments or the docs builds nothing.

### 4. Promote: read back, then commit

`promote.yml` starts in three ways:

| Trigger | When |
|---|---|
| after `publish.yml` | every publish run; only a successful one is promoted |
| a push to `main` touching `charts/group-sync-dashboard/` or `environments/` | a chart-only merge, which `publish.yml` skipped |
| Run workflow (manual) | a re-run, or a rollback |

It always promotes a commit on `main`, by default the newest. For that commit it:

1. finds the tree's image: the build of the last commit that changed an image input;
2. checks that `publish.yml` succeeded for it. If publish failed, it stops: an older image is not this code;
3. reads both images back: the version label is the chart's `appVersion`, the revision label is the commit, and the
   signature verifies against `publish.yml` on `main`;
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
then points the Application at `release`. `--argocd <branch>` still deploys a branch for testing; it leaves
`promotion.yaml` out.

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
```

<!-- block: docs/README.md | edit -->
```markdown
- [RELEASING.md](RELEASING.md) — application and chart release procedures and version ownership.
- [api-contract.md](api-contract.md) — documentation and schema rules for new API endpoints.
```

```markdown
- [RELEASING.md](RELEASING.md) — application and chart release procedures and version ownership.
- [CICD.md](CICD.md) — the pipeline from a pull request to the cluster: checks, publish, promotion to `release`, rollback.
- [api-contract.md](api-contract.md) — documentation and schema rules for new API endpoints.
```

<!-- block: docs/RELEASING.md | edit -->
```markdown
human changed the application version.

```

```markdown
human changed the application version.

## Promotion: what the lab deploys

The lab does not deploy `main`. After `publish.yml` succeeds, `promote.yml` reads both images back and commits
the chart with the images pinned by digest to the `release` branch, which the lab's Argo CD tracks. A chart-only
merge is promoted with the image of the last commit that changed an image input; a failed publish is never
promoted. [CICD.md](CICD.md) is the walk-through, with the picture, the rollback and the one-time setup.

```

<!-- block: docs/RELEASING.md | edit -->
```markdown
appVersion. That is the deliberate-release model: merging is not shipping.
```

```markdown
appVersion. That is the deliberate-release model: merging is not shipping. The lab is the exception: it
tracks `release`, and `promote.yml` deploys the new image there ([CICD.md](CICD.md)).
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown

## Deploying with Flux or Kustomize
```

```markdown

### Track a promoted branch, not `main`

This repository's lab Application (`gitops/argocd-application-dashboard.yaml`) sets `targetRevision: release`, not
`main`. `release` is written only by the `promote` workflow, after both images are read back from the registry. It
carries this chart, `environments/`, and `promotion.yaml`, which sets `image.digest` and `reporting.image.digest`.
List it last in `valueFiles`, because the last file wins:

````yaml
    targetRevision: release
    helm:
      valueFiles:
        - ../../environments/crc.yaml
        - ../../promotion.yaml
````

Tracking `main` lets Argo CD sync a chart whose `:<appVersion>` image is not pushed yet (#410 measured a sync only 95 s
after the image was pushed). The whole pipeline is in [docs/CICD.md](../../docs/CICD.md).

## Deploying with Flux or Kustomize
```

<!-- block: local-development/README.md | edit -->
```markdown
| `--argocd <branch> --values X` | Argo | GitHub at `<branch>` | same | `[../../X]` | `X` present at `origin/<branch>` |
| `--build-only` | untouched | — | built, **not** pushed (no credentials needed) | — | — |
```

```markdown
| `--argocd <branch> --values X` | Argo | GitHub at `<branch>` | same | `[../../X]` | `X` present at `origin/<branch>` |
| `--argocd release` | Argo | GitHub at `release` | the digests in `promotion.yaml`, read back first | `[../../environments/crc.yaml, ../../promotion.yaml]` | a promotion on `origin/release` ([CICD.md](../docs/CICD.md)) |
| `--build-only` | untouched | — | built, **not** pushed (no credentials needed) | — | — |
```

<!-- block: local-development/README.md | edit -->
```markdown
a local variant), `--argocd` on the pushed head before the PR is called ready, `--argocd main`
after a merge once the app release is cut. `./argocd-wait.sh` is the waiter the Argo modes use: it
```

```markdown
a local variant), `--argocd` on the pushed head before the PR is called ready; after a merge,
`promote.yml` deploys through `release`, and `--argocd release` hands the lab back to it. `./argocd-wait.sh` is the waiter the Argo modes use: it
```

<!-- block: gitops/README.md | edit -->
```markdown
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |
```

```markdown
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-dashboard.yaml` | the dashboard chart from the `release` branch, which only `promote.yml` writes (`docs/CICD.md`): the chart, `environments/crc.yaml`, and `promotion.yaml` pinning both images by digest. Apply it with `local-development/release-crc.sh --argocd release`, which reads the digests back first |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |
```

<!-- block: local-development/pyproject.toml | edit -->
```toml
version = "1.0.0"
```

```toml
version = "1.1.0"
```

<!-- block: local-development/gsd/__init__.py | edit -->
```python
__version__ = "1.0.0"
```

```python
__version__ = "1.1.0"
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
version: 0.59.2
```

```yaml
# CHART 0.59.3 (2026-09-27), PATCH: appVersion moves to application 1.1.0 (below); the README's ArgoCD
# section names the `release` branch the lab tracks (#410, SPEC_P1). No template, value or RBAC change.
version: 0.59.3
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
appVersion: "1.0.0"
```

```yaml
# 1.1.0 (2026-09-27). The lab deploys the promoted artifact from `release` (#410, Epic E). MINOR.
appVersion: "1.1.0"
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
which `local-development/prepare-release.py` does when the release is cut.

```

```markdown
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Build once, promote the artifact: the lab tracks `release` (#410, Epic E, `docs/specs/SPEC_P1_promote_release_branch.md`;
  app 1.1.0, chart 0.59.3).** A new workflow, `promote.yml`, runs after a successful `publish.yml` and after a
  chart-only merge. It reads both images back (version and revision labels, digest, cosign signature), then
  commits the chart, `environments/` and `promotion.yaml` (both images pinned by digest) to the `release` branch,
  which holds no workflows and builds nothing. The lab's Application tracks `release`, so Argo CD can no longer
  sync a chart before its image exists: the race #410 measured, where a sync landed 95 s after the image. A failed
  publish is never promoted; a rollback is a manual run with an older commit. `release-crc.sh --argocd release`
  reads the pinned digests back before pointing the lab at `release`; `--argocd <branch>` keeps working for tests.
  New operator guide: `docs/CICD.md`, with the pipeline figure. The `release` branch is created once by hand
  (`docs/CICD.md`, Rollback and setup).

```
