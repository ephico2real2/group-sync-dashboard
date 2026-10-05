# SPEC P1 — build once and promote: `promote.yml` keeps a `release` branch of checked images; the lab tracks `main` during development and `release` when chosen (#598)

| | |
|---|---|
| Programme | Release safety, part B (#598, split from #410 on 2026-10-04; part A is SPEC_E8, merged as `c825182c`). Rewritten on 2026-10-04 against today's `main` from the reviewed but never merged SPEC_P1 of 2026-09-27 (tag `archive/feat/410-promote-release-branch`, `0388448c`), which is reference only |
| Batch | P — promotion |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 5.2.0, chart 0.70.3 |
| Version note | `local-development/README.md` and `local-development/build-and-push-external.sh` are image inputs (.github/workflows/publish.yml:84, :89), and this change edits both, so `check-app-version-bump.py` requires the next application MINOR after main's 5.1.0: 5.2.0 (`docs/RELEASING.md`, "MINOR per merged issue changing the image"). The script change makes its existing `<sha10>` contract exactly ten characters; no tag name changes unless Git would otherwise have lengthened an ambiguous abbreviation. No other image input changes. The chart moves only because `appVersion` moves: no template, value or RBAC change, so a PATCH, 0.70.2 to 0.70.3, as 0.70.2 was for 5.1.0. W1 stays `specified` at chart 0.71.0, above 0.70.3. Read on `6421cff7` (application 5.1.0, chart 0.70.2). A release that lands first makes the version blocks (17 to 21) fail their check; the implementing pull request corrects them here first. |
| Issue | [#598](https://github.com/ephico2real2/group-sync-dashboard/issues/598) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-04 (implementer seat), from #598 and #410, the old SPEC_P1 and its two review rounds (`bb1f8b91`, `dc027eda`), the code read on `6421cff7`, read-only `gh` and `oc get` against GitHub and the lab, and the upstream documents in §2.1. No cluster, branch, ruleset or GitHub setting was changed. Revised the same day on the operator's decisions "main by default; release optional" and the two-namespace end state (Orchestrator's notes 10, 11), then on the confirmation review's exact-sha10 finding. §7's 22 blocks check against a clean copy of `6421cff7` with this spec in it (§4.3) |

## How to read this spec

The plain point first. Today the lab's Argo CD Application follows `main`. A release merge changes the chart's
`appVersion` on `main` at once, but `publish.yml` needs a minute or two to build and push the image of that version.
Argo CD can sync in between, and then the pods ask for an image that does not exist yet (`ErrImagePull`). This was
measured at 4.1.0, 4.4.0 and 5.1.0 (§2.3).

The fix is "build once and promote". `main` stays the source. A new workflow, `promote.yml`, builds nothing. Once the
images of `main`'s version exist, it reads them back from the registry, writes their digests into a small values file
(`promotion.yaml`), and commits that file, with the chart and `environments/`, to a branch called `release`. An
Argo CD Application that follows `release` only ever sees a chart whose images were already checked, and it pulls
them by digest.

**During development the lab still follows `main`** (the operator: "main by default; release optional"). So the race
remains on `main`, and heals on its own. `release-crc.sh --argocd release` points the lab at `release` whenever that
is chosen, and `--argocd main` points it back. `release` is kept current on every green publish either way. The end
state is two namespaces on one cluster: `group-sync-dashboard-dev` on `main`, `group-sync-dashboard` on `release`
(Orchestrator's notes 11); this change is that design with one namespace.

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
   the `release` branch holding only the chart, `environments/` and `promotion.yaml`; the pin by digest;
   `promotion.yaml` as the last values file when the lab tracks `release`; the label read on every Linux image
   (round 1 F1); the signature from `publish.yml` on `main`; `--argocd release` reading the pinned digests back and
   refusing a `release` without them (round 1 F2); a rollback as a manual run with `rollback` checked. Round 1 F5
   (`--argocd main` refused) is reversed by the operator's decision (note 10). Dropped, because today's `main` makes
   them unnecessary:
   - **`local-development/promote.py` (238 lines) and its runs-API search for "the tree's image".** Its
     source-binding property is kept another way (note 14, F2): the step finds the last first-parent commit
     touching `publish.yml`'s image inputs, reads the immutable `<appVersion>-<sha10>` image built for that commit,
     and requires `:<appVersion>` to resolve to the same digest. No runs API, no `actions: read`. The whole step is
     inline bash in `promote.yml`, tested by running it (§4).
   - **`docs/CICD.md` and its figure** (215 + 155 lines). The flow is one section of `docs/RELEASING.md`.
   - **The 17-block rename of the test branch.** `--argocd main` keeps today's behaviour, so no test changes branch.
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
   on a copy. It wrote the Chart.yaml, `pyproject.toml` and `gsd/__init__.py` lines that Blocks 17 to 20 carry. It
   also turned `## Unreleased` into `## Application 5.2.0 — chart 0.70.3`, which would file SPEC_F7's unreleased
   5.1.0 entry under 5.2.0, and moved SPEC_F7 to `released`. So, as SPEC_F7 did, the CHANGELOG entry goes under
   `## Unreleased` (Block 21) and nothing else is moved.
6. **The index row.** #598 is above every issue in the rows before it (F7 is #592), so the row needs no exclusion in
   `local-development/tests/test_specs_index.py`'s rising-number assert; the index count moves from 59 to 60.
7. **A notice, not a red run, while main's exact image is still being published.** On a release merge the push
   trigger starts while `publish.yml` is building. It probes the immutable tag for main's last image-input commit; if
   that tag or its matching version alias is not ready, it writes nothing and says so. Once they are ready, any later
   push can promote them. This matters because GitHub concurrency keeps only one pending run: a chart push may
   replace the publish-completion run, and must not strand an already-published `main` (note 14, F1). A failed
   publish is already a red run of its own, and `release` stays on the last promotion. A completed publish whose
   alias differs from its immutable image is red (§3.2).
8. **A pinned tag must be signed too.** A tag pinned in `values.yaml` is not checked against `appVersion` (as in
   `helm.yaml` and `release-crc.sh`), but on the promotion path its signature is checked like any other image. Today
   no tag is pinned (charts/group-sync-dashboard/values.yaml:32, :1255).
9. **A side effect to know.** A job that names an environment creates a GitHub deployment record per run. It shows
   under the repository's Deployments; it writes nothing to the repository.
10. **The operator's decision: main by default, release optional (2026-10-04).** Verbatim: *"So during our dev
    development phase. The game plan will be ability to deploy from main."* Then, asked which the lab tracks by
    default: *"main by default; release optional"*. What changed from the first revision of this spec:
    - `gitops/argocd-application-dashboard.yaml` is not edited: it stays on `targetRevision: main` with
      `environments/crc.yaml` alone (the first revision's four blocks are gone).
    - `release-crc.sh --argocd main` is not refused; it keeps today's behaviour and is how the lab returns to `main`
      (the first revision's refusal, its test and the test-branch rename are gone).
    - `release-crc.sh --argocd release` is the opt-in: it reads the pinned digests back, then writes the Application
      at `release` with `promotion.yaml` last. Every other mode sends what it sent before.
    - `promote.yml`, the ready rule, `promotion.yaml`, the deploy key, the environment, the ruleset and the
      operator's one-time steps are unchanged: `release` is kept current on every green publish, so it is ready
      whenever it is chosen.
    - The consequence, said plainly in `docs/RELEASING.md`, `gitops/README.md`, `local-development/README.md` and
      the epic skill: while the lab tracks `main`, the image race remains there (measured at 4.1.0, 4.4.0 and
      5.1.0, §2.3); it heals on its own, and `--argocd release` removes it whenever chosen.
11. **The end state (2026-10-04, not built here).** The operator, verbatim: *"Ideally once our lab is built
    completely with a full openshift cluster. Im going to have two namespaces and a proper promotion simplified that
    group-sync-dashboard-dev (uses main?) and group-sync-dashboard (argocd uses release branch)"*. So:
    `group-sync-dashboard-dev` tracks `main`; `group-sync-dashboard` tracks `release` with `promotion.yaml` last.
    The development phase is the same design with one namespace. Measured (§2.3, "two-namespace readiness"): the
    chart installs twice in one cluster without a collision only when the second Helm release has its own name
    (`group-sync-dashboard-dev`); under the same release name, nine objects collide. Nothing in this change ties
    `release` to a namespace: `promote.yml` and `promotion.yaml` name no namespace, and `--argocd release` takes the
    destination from the Application file as every Argo mode does. The follow-ups the end state needs are in §2.3.
12. **The version, rechecked after the revision.** `local-development/README.md` still changes (note 10), and the
    exact-sha10 fix changes `local-development/build-and-push-external.sh`; both are image inputs
    (.github/workflows/publish.yml:84, :89), so the next application MINOR is still required: 5.2.0, with the chart
    PATCH 0.70.3 because `appVersion` moves. Every other file this change edits is outside `publish.yml`'s paths and
    outside `charts/`.
13. **The epic-release routine (the operator, 2026-10-04: "Yes I love that your plan").** While the CRC has no room
    for a second environment, the lab follows `main` day to day, and at each epic release the post-release walk runs
    on the promoted path: `release-crc.sh --argocd release`, the walk, then `release-crc.sh --argocd main`. Written
    into `.claude/skills/epic/SKILL.md` section 6, step 3 "Deploy", and its Definition of Done (Blocks 15, 16), and
    into `docs/RELEASING.md` (Block 11). The room, as the orchestrator measured it: CPU requests 86% of 11.8 cores,
    memory requests 89% of 27.6 GiB, memory used 79%. Re-read for this spec, read-only (`oc describe nodes`,
    `oc adm top nodes`): requests `cpu 10222m (86%)` and `memory 24758Mi (89%)` of allocatable `cpu=11800m`,
    `mem=28216052Ki`; usage `3549m` CPU (30%) and `21371Mi` memory (77%).
14. **The spec review of PR #613 (Codex, gpt-5.6-sol, xhigh, 2026-10-04): three findings, all accepted.**
    - **F1 (P0): a replaced pending run could strand a published `main`.** A push took its readiness from the version
      `release` already ran, so a chart push that replaced a pending publish-completion run, or any chart push after
      a rollback, exited with a notice and nothing was left to promote. **F2 (P0): the version label did not bind the
      digest to the promoted tree.** Two PRs from one base can both take the same next MINOR; the second's image then
      sits only at its immutable tag, and the old step pinned the first image under the second tree. One mechanism
      fixes both (§3.2, Block 1): read each unpinned image at the immutable `:<appVersion>-<sha10>` of the target's
      last first-parent image-input commit (the list held equal to `publish.yml`'s paths by a test), and require
      `:<appVersion>` at the same digest. A push, or a publish completion overtaken by a newer image commit, treats
      "not ready" as a green notice; the successful completion for that exact image commit treats a missing or
      different alias as red. Every Linux-label and cosign check stays. Measured on F2's premise: `main`'s
      protection is `strict: true` with `enforce_admins: true` and seven required checks (§2.3), which today makes a
      PR re-run its checks against the newest `main`; the binding is now intrinsic to the promotion, so it no longer
      depends on that setting.
    - **The regression tests, on the reviewed workflow and on this one** (`test_promote.py`):

      | Test | Reviewed workflow (`51e28a81`'s Block 1) | This spec |
      |---|---|---|
      | `test_a_push_after_publish_completion_promotes_if_the_workflow_run_was_replaced` | FAILED: `'release starts empty' == 'promote: main <tip>'` | passed |
      | `test_a_chart_merge_after_a_rollback_returns_release_to_main` | FAILED: release stayed `promote: main <older>` | passed |
      | `test_an_older_publish_completion_cannot_promote_a_later_same_version_image_change` | FAILED: it printed `promoted: main <later>` with the older digest | passed |
      | `test_a_same_version_image_whose_alias_names_another_build_is_red` (added here, for the alias rule) | FAILED: it promoted | passed |
      | `test_the_image_input_list_is_publish_ymls_and_the_immutable_tag_is_source_bound` (shape) | FAILED: no list | passed |

      The whole file on the reviewed workflow: `6 failed, 15 passed` (the five above and the reworded notice test);
      on this spec's: `21 passed`.
    - **F3 (P1): the hermetic count was off by one.** The new fenced code in the docs adds a case to
      `test_docs_diagrams.py`. The counts in §4.3 are re-measured on this spec's final tree.
15. **The confirmation pass (Codex, gpt-5.6-sol, xhigh, 2026-10-04): F1, F2 and F3 confirmed closed; one new
    finding, F4 (P1), accepted.**
    - **Confirmed closed:** the replaced-pending, post-rollback and overtaken-publish orders, and four more Codex
      tried (a revert, a first-parent merge, an older `sha` without `rollback`, an image-only merge). Main by default
      holds, and the two-namespace table re-renders as stated.
    - **The defect:** the publisher names its immutable tag with `git rev-parse --short=10`, a unique abbreviation of
      at least ten characters that Git lengthens when another object shares the prefix. The promoter asks for exactly
      ten (`${image_commit:0:10}`), so in that case the published image could never be found, and the release
      would stay stranded.
    - **The fix (Block 22):** the publisher takes the full id and slices exactly ten characters. Today's tags are
      unchanged unless a prefix collides. Matching the other way, `--short=10` in the promoter, is rejected: the
      abbreviation depends on which objects each checkout holds.
    - **The test:** the source-binding shape test holds both sides to the same rule and refuses a return to
      `--short=10`. It failed on the 21-block tree and passes on this one.
    - **The version:** the publisher script is an image input, and this change already moves the application to
      5.2.0, so the version is unchanged.
    - **Found by the orchestrator's full hermetic run** on a clean `6421cff7` with the 22 blocks applied:
      `test_build_and_push_report.py::test_release_tags_cannot_inherit_the_dashboards_image_name` failed (1 failed,
      7654 passed). Its fake `git` answered only `rev-parse --short=10 HEAD`. Block 23 makes it answer the full id;
      the first ten characters, and so every expected tag, are unchanged.

16. **The review of the implementation (PR #614, head `06431584`: OB2, Fable 5.1 high, and Codex, gpt-5.6-sol xhigh,
    2026-10-04).** Five changes, as Blocks R1 to R16.
    - **Block 13 missing (OB2 F1, Codex F2): the orchestrator's commit error, not a spec defect.** The row was
      applied in the tree and left out of the commit. No block changes. Test (R14):
      `test_the_gitops_readme_names_the_dashboard_application_main_by_default_and_the_opt_in`, which fails on
      `06431584` and passes.
    - **Codex F1, accepted: the deploy key isolated (R1, R2, R5).**
      - The defect: checkout took `ssh-key` with `persist-credentials` at its default, so the key sat in git's config
        through the cosign installer and the registry read-back.
      - The fix: checkout keeps no credential (`persist-credentials: false`, no key; the repository is public, so
        fetches are anonymous). The read-back step prepares the commit under `refs/promote/release` and
        `refs/promote/target`, clearing both first. A last step, `Push release`, alone takes the key. It turns xtrace
        off, writes the key to a temporary file and pins GitHub's published Ed25519 host key (SHA256
        `+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`, from docs.github.com "GitHub's SSH key fingerprints" and
        `api.github.com/meta`, fingerprint checked with `ssh-keygen -lf`). It pushes without force and removes both
        files on exit.
      - One change from Codex's patch: the push is `git -c url.git@github.com:.pushInsteadOf=https://github.com/
        push origin`, not a `PUSH_REMOTE` variable. Measured: it rewrites only the push URL (`git remote get-url
        --push origin` gives `git@github.com:ephico2real2/group-sync-dashboard`; the fetch URL stays https). A test's
        origin, a local path, is pushed to as it is, so the workflow carries no variable that only tests set.
      - The tests: the harness now runs `Push release` after every green promotion (R11). The checkout test asserts
        checkout's three inputs exactly, and `test_the_deploy_key_is_loaded_only_by_the_push_step` holds the key's
        one step, the host key, no force, and the push-only rewrite (R13). Both fail on `06431584`.
    - **The disagreement, and its decision.** OB2 (C2) judged the persisted key necessary: the push ran in a later
      `run` step, which needs the key persisted. Codex (F1) required the key to exist for the push alone. The
      orchestrator decided for Codex: a push step that loads the key itself removes the need to persist it. OB2's
      premise held only for the single-step design.
    - **OB2 F2, accepted: unreachable is not absent (R3, R4).** `probe` keeps skopeo's stderr, and `absent` greps it
      for "manifest unknown", as helm.yaml's "Label the image" step does. Only an absent name gives the notice, on the
      push and overtaken paths. Any other failure is red, with the first 400 bytes of skopeo's message.
      `test_a_chart_push_during_a_registry_outage_is_red_not_a_green_notice` fails on the tree without `absent`
      ("a registry outage was reported as a green notice") and passes now; a genuinely absent tag still gets the
      notice.
    - **OB2 F3, accepted: `--argocd release` honours a pin (R6).** The release refs carry `values.yaml`'s pins, so a
      digest `promote.yml` pinned for a pinned tag deploys as pinned. Test (R15):
      `test_argocd_release_deploys_a_pinned_tag_as_promote_yml_pinned_it`. Before:
      `ERROR: …@sha256:aaaa… is application 0.24.0, not 5.2.0`, exit 1. After: passes, and the unpinned report image
      is still read back.
    - **OB2's other orders, kept as permanent tests (R12).** A `release` that moved after the fetch refuses the push;
      a hand-run publish at a commit that changed no image input promotes nothing; a green publish that pushed nothing
      is red; an identical chart at a new target writes a new commit. They pass before and after: they hold
      behaviour. The hand-run order gets a troubleshooting row in `docs/RELEASING.md` (R16).
    - **The version:** no R block touches an image input or `charts/`, so 5.2.0 and 0.70.3 stand.
    - **Proofs** (the repository's venv, Python 3.14):
      - the oracle: `git archive 51fbb781` + this spec + the index row, all 39 blocks applied, equals the worktree:
        `diff -r` prints nothing (`__pycache__` excluded);
      - the full suite, `pytest tests/` (browser tests included): `8357 passed, 27 skipped, 5 xfailed`;
      - CI's hermetic selection: `7663 passed, 23 skipped, 698 deselected, 5 xfailed`, against `7655` on `06431584`.
        The +8 are `test_promote.py`'s seven new tests and `test_release_crc.py`'s one;
      - the new tests on `06431584`: `test_promote.py` 3 failed and 20 errors (no `Push release` step), and the
        pinned-tag test fails;
      - actionlint 1.7.12 (`GOFLAGS=-mod=mod go run …@v1.7.12`): exit 0 on `promote.yml`; the repository's other two
        findings are main's (`ci.yml`, `mock-cluster.yml`);
      - shellcheck `-S warning`: the three extracted `run` steps, `release-crc.sh`, `argocd-wait.sh` and
        `build-and-push-external.sh` are clean;
      - RBAC rendered with `environments/crc.yaml`: 30 rule and binding lines before and after; REMOVED 0, ADDED 0.

17. **The one-time setup, done and recorded (2026-10-05).** The operator created the deploy key and the `release`
    environment with its secret (steps 1 and 2). The orchestrator, with the operator's go-ahead, created the empty
    branch and the ruleset (steps 3 and 4) through the API.
    - **Open question 1 is settled:** GitHub accepted `actor_type: DeployKey` as the bypass on this user-owned
      repository (ruleset `24475607`).
    - **The lock is proven:** a hand push on top of `release` was refused with `GH013 … Cannot update this protected
      ref`.
    - **The runbook:** at the operator's request, `docs/RELEASE_BRANCH_SETUP.md` (Block R17) records the steps for a
      junior engineer. For each step it gives what it does and why, the web and `gh` ways, a check, the record of
      the setup, upkeep, and a glossary. RELEASING points to it (Block R18).
    - **It is written with indented code samples,** because a fenced sample inside a block's fence would end the
      block early in `apply-spec-blocks.py`.
    - **Found by CI** on `c87dd349` (both Python legs): `test_docs_index` requires each `docs/` page to be linked from
      `docs/README.md`. Block R19 adds the link.

Open questions for the operator:

1. Step 4 of §3.5: confirm that "Deploy keys" is offered in the ruleset's bypass list (note 4).
2. The Grafana Application (`gitops/argocd-application-grafana.yaml`) still tracks `main`. It deploys a chart with no
   image of this repository, so it is outside #598 and is left alone.
3. The end state's follow-ups (§2.3): a second Application file and values file for `group-sync-dashboard-dev`, with
   release name `group-sync-dashboard-dev`; a fixed Grafana board uid; the shared fleet account; `release-crc.sh`
   choosing which Application file it writes. Each is its own issue when the full cluster exists.

## 1. The mandate, and what is out of scope

**#598 (the operator, 2026-10-04: "let us finish #598").** "Build once and promote", as approved on 2026-09-27:

- `main` stays the source;
- a `promote` workflow commits the verified artefact to a `release` branch;
- the lab's Argo CD Application tracks `release`.

The operator's decision of the same day amends the last line for the development phase: the lab tracks `main` by
default and `release` is optional (Orchestrator's notes 10).

#410's part-B list is the Definition of Done (items 4 to 9): `promote.yml` writes `release` only after reading both
images back (labels, digest, and the signature when signing is on); a failed publish is never promoted; a chart-only
merge carries the last built image; `release-crc.sh --argocd release` re-reads the pinned digests before it writes
the Application (item 7's "`--argocd main` is refused" is withdrawn by the decision); the operator's one-time steps;
the lab's Application tracks `release` when chosen, its pods then run the pinned digests, and the PVC UIDs are
unchanged; the release docs say what each gate refuses and what to do.

**Out of scope:** `publish.yml` (its paths, alias rule, signing, SBOM, `:latest`); every published tag except making
the existing `<appVersion>-<sha10>` suffix exactly ten characters (Block 22);
`helm.yaml` and part A's gate; the chart's templates, values and RBAC; the published Helm chart, which still resolves
`:<appVersion>` for installs outside the lab; `release-crc.sh`'s Helm mode, its build path, and `--argocd <branch>`
for a branch under test, and `--argocd main`; the committed Application file; the Grafana Application; the end
state's second namespace (Orchestrator's notes 11).

## 2. Research, measured

### 2.1 Primary sources

| Source | What it says | What this spec takes |
|---|---|---|
| GitHub, [Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), `workflow_run` | "This event will only trigger a workflow run if the workflow file exists on the default branch." `GITHUB_SHA` is the "Last commit on default branch". The `branches` filter names "what branches the triggering workflow must run on". At most three levels of chaining | §3.1: push → publish → promote is two levels; `github.event.workflow_run.head_sha` names the publish run's commit |
| GitHub, [Triggering a workflow](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow) | "events triggered by the `GITHUB_TOKEN` will not create a new workflow run", except `workflow_dispatch` and `repository_dispatch` | not relied on: the push is made with a deploy key, and `release` has no `.github/workflows/`, so no push to it runs a workflow (a push runs the workflows in the pushed commit) |
| GitHub REST, [Create a repository ruleset](https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28#create-a-repository-ruleset) | bypass `actor_type` is one of Integration, OrganizationAdmin, RepositoryRole, Team, DeployKey, User; rules `creation`, `update`, `deletion` "Only allow users with bypass permission"; `non_fast_forward` "Prevent users with push access from force pushing" | §3.5 step 4 |
| GitHub, [Deployments and environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments) | "Only branches and tags that match your specified name patterns can deploy to the environment"; environment secrets are "only available to workflow jobs that reference the environment"; deployment branches "are available for all public repositories" | §3.5 step 2: the key is usable only by a job on `main` |
| `actions/checkout` README, `ssh-key` | "The SSH key is configured with the local git config, which enables your scripts to run authenticated git commands. The post-job step removes the SSH key." "The public key for github.com is always implicitly added." | superseded by the review of #614: checkout runs with `persist-credentials: false` and no key, so the key never sits in git's config (§3.4, Orchestrator's notes 16) |
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
| Both images are labelled with the version and the exact first 10 characters of the commit they were built from | local-development/Containerfile:184-185; local-development/build-and-push-external.sh:132-133 after Block 22 |
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
false`, `allow_deletions: false`, reviews required, seven required checks including "App image changes bump the app
version", and `required_status_checks.strict: true` (`gh api repos/ephico2real2/group-sync-dashboard/branches/main/protection`
gives `{"checks":7,"enforce_admins":true,"strict":true}`), so a PR must be up to date with `main` before it merges.
The promotion's source binding does not rely on that setting (Orchestrator's notes 14).

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

**Two-namespace readiness** (the end state, Orchestrator's notes 11). Three renders of `6421cff7`'s chart, each
with `-f environments/crc.yaml`, 49 objects each:

    A: helm template group-sync-dashboard     … -n group-sync-dashboard
    B: helm template group-sync-dashboard     … -n group-sync-dashboard-dev
    C: helm template group-sync-dashboard-dev … -n group-sync-dashboard-dev

Every object A renders outside its own namespace, and whether it collides when installed beside B or C (the same
kind, namespace and name):

| Object (render A) | Scope | Collides with B (same release name) | Collides with C (`group-sync-dashboard-dev`) |
|---|---|---|---|
| ClusterRole `group-sync-dashboard-reader` | cluster | yes | no (`group-sync-dashboard-dev-reader`) |
| ClusterRole `group-sync-dashboard-login-capture-audit` | cluster | yes | no |
| ClusterRole `group-sync-dashboard-report-auditor` | cluster | yes | no |
| ClusterRoleBinding `group-sync-dashboard-reader` | cluster | yes | no |
| ClusterRoleBinding `group-sync-dashboard-login-capture-audit` | cluster | yes | no |
| ClusterRoleBinding `group-sync-dashboard-auth-delegator` | cluster | yes | no |
| ClusterRoleBinding `group-sync-dashboard-ra-b78c05817c9d` | cluster | yes | no |
| Role and RoleBinding `group-sync-dashboard-fleet-account` | `openshift-config` | yes (both) | no |
| no CRD, webhook configuration, SCC, ConsoleLink or OAuthClient is rendered | — | — | — |

The fixed names and shared state read in the same renders:

| Item | A | C | Collides? |
|---|---|---|---|
| Route | `spec.subdomain: group-sync-dashboard` | `spec.subdomain: group-sync-dashboard-dev` | B: yes (one host, two namespaces); C: no |
| OAuth client | the ServiceAccount's `oauth-redirectreference` annotation, naming its own namespace's Route | the same, in its namespace | no |
| Leader Lease | `leaderLeaseName: "group-sync-dashboard"` | the same name | no: the Lease Role is in the release namespace (`-leases`), so each install's Lease is in its own namespace |
| Fleet password Secret | `openshift-config/ldap-oauth-bind-secret`, `get` by `resourceNames` | the same Secret | no collision (read-only); but both installs would log in as the same fleet account (`environments/crc.yaml`, `clusterConfig.fleetAccount`) with their own gate Lease each, so the directory sees both installs' attempts |
| Grafana board | `uid: gsd-group-sync-dashboard` (charts/group-sync-dashboard/dashboards/group-sync-dashboard.json) | the same uid | yes, in one Grafana instance, when both boards are imported |
| Recovery mode's release name | `--release "group-sync-dashboard"` | `--release "group-sync-dashboard-dev"` | no |

**Follow-ups the end state needs** (none is a one-line value here, so none is changed by this spec): (1) a second
Application file for `group-sync-dashboard-dev`, with `releaseName: group-sync-dashboard-dev`,
`targetRevision: main` and its own values file; (2) a values file for the dev install that does not share the fleet
account, or a decision that it may; (3) a per-release Grafana board uid; (4) `release-crc.sh` naming which
Application file it writes (today it always patches `gitops/argocd-application-dashboard.yaml`, local-development/release-crc.sh:186).

## 2a. Alternatives considered

| | Option | Taken? | Why |
|---|---|---|---|
| A1 | A `release` branch written by a workflow, pins by digest in `promotion.yaml`, an Application that can track it | **yes** | the operator's approved design (#410, 2026-09-27); Argo CD sees only checked images; one environment, never merged (Orchestrator's notes 2) |
| A2 | Argo CD Image Updater writes the digests back | no | a second controller to install and run on the lab, and an Argo-specific mechanism; the repository's rule is Helm first, Argo CD a conduit |
| A3 | Keep `main`; Argo CD's sync waits (a sync window, or manual sync) | no | still syncs whatever `main` says once the window opens; nothing checks the image |
| A4 | Fast-forward `release` to the checked `main` commit (no `promotion.yaml`) | no | the lab would still pull `:<appVersion>`, a tag that can move after the check; "commits the verified artefact" is a pin |
| A5 | Pin the immutable `<appVersion>-<sha10>` tag instead of the digest | no | a tag the registry can repoint; the chart already prefers a digest (values.yaml:54) |
| B1 | Find the image through the runs API (the old `promote.py`) | no | the immutable `<appVersion>-<sha10>` tag identifies the last image-input commit without API permission (Orchestrator's notes 1, 14) |
| B2 | The step inline in `promote.yml`, run by tests | **yes** | it binds the source through the immutable tag, then applies `helm.yaml`'s every-Linux-version-label check; the repository's own pattern for `helm.yaml`'s label step (local-development/tests/test_supply_chain.py, `TestTheChartPublishLabelGate`) |
| C1 | Trigger on `publish` completion, on a push to the chart or `environments/`, and by hand | **yes** | covers an image release, a chart-only merge, a values-only merge and a rollback |
| C2 | Trigger on `helm.yaml`'s completion instead of a push | no | `helm.yaml` waits for the whole `ci.yml` (about 12 minutes, §2.3) and does not run for `environments/` |
| D1 | A notice when `main`'s version is still being published | **yes** | the expected state for a minute on every release merge (Orchestrator's notes 7) |
| D2 | A red run in that state | no | a false alarm on every release merge |
| E1 | Push with a deploy key from a `release` environment; ruleset bypass "Deploy keys" | **yes** | the only way on a user-owned repository to let the workflow, and nothing else, write `release` (Orchestrator's notes 4) |
| E2 | Push with `GITHUB_TOKEN` (`contents: write`); ruleset without Restrict updates | fallback | the old design; leaves a hand push possible |
| F1 | Copy `helm.yaml`'s two readers, held equal by a test | **yes** | one rule in three places, the way `helm.yaml` and `release-crc.sh` already share the `reporting.image.tag` reader |
| F2 | Move the readers into a shared script | no | it changes part A's `helm.yaml`, outside #598 |
| G1 | The lab tracks `main` by default; `--argocd release` is the opt-in | **yes** | the operator's decision for the development phase (Orchestrator's notes 10) |
| G2 | The lab tracks `release` by default; `--argocd main` refused | no | the first revision of this spec; withdrawn by the same decision |

## 3. The design

### 3.1 When it runs, and what it promotes

`promote.yml` runs on three triggers (Block 1):

- `workflow_run` of `publish`, completed, on `main`; the job runs only when the conclusion is `success`;
- a push to `main` touching `charts/group-sync-dashboard/**`, `environments/**` or `promote.yml` itself;
- `workflow_dispatch`, with `sha` (empty means `main`'s tip) and `rollback`.

Every run promotes `main`'s tip, unless `sha` is given. Runs are one at a time (`concurrency: promote-release`, never
cancelled). GitHub may replace an older pending run; the replacement loses nothing, because every push can promote
`main` once the exact immutable image and its version alias are ready.

### 3.2 The ready rule, and the checks

1. **Ready and source-bound.** From the target's first-parent history and `publish.yml`'s image-input allowlist,
   find the last commit that must have built an image. An unpinned image is read at
   `:<appVersion>-<that commit's first 10 hex characters>`; `:<appVersion>` must exist at the same digest. A push, or
   an older publish completion overtaken by a newer image-input commit, prints a notice and writes nothing while
   those names are not ready. A successful publish completion for that exact commit treats a missing or different
   alias as red. A publish completion whose commit is not `main`'s version prints a notice too. Thus a replacement
   pending push, a chart merge after a rollback, and a chart merge after publication can promote, while two
   same-version image merges cannot cross their artefacts.
2. **Where.** The commit must be on `main`. If `release` already holds a later commit, the run is refused unless
   `rollback` is checked.
3. **Each image** (the dashboard, then the report), at its pin in `values.yaml` or at the immutable tag above: the digest
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

The job holds `contents: read`. The secret belongs to the `release` environment, which only `main` can deploy to. A
first step fails, with the setup pointer, when the secret is missing. Since the review of #614 (Orchestrator's notes
16, Blocks R1, R2, R5) the key exists in one step only: checkout runs with `persist-credentials: false` and no key
(the repository is public, so every fetch is anonymous), the read-back step prepares the commit under
`refs/promote/release` and `refs/promote/target`, and the last step, `Push release`, writes the key to a temporary
file, pins GitHub's published Ed25519 host key, pushes over SSH without force, and removes both files on exit.

### 3.5 The operator's one-time steps

These are GitHub settings, not code. In this order, before the first promotion (also in `docs/RELEASING.md`,
"Promotion to the lab", Block 11):

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
6. **The lab, optional.** `local-development/release-crc.sh --argocd release` points it at `release`; `--argocd main`
   points it back (§5).

Until steps 1 to 3 are done, every promote run is red and names this section.

### 3.6 `release-crc.sh`, and the docs that name `--argocd main`

- `--argocd release` requires `promotion.yaml` on `origin/release`, reads both pinned `repository@digest` back with
  the same `oc image info --filter-by-os='linux/.*'` check as today, and writes `targetRevision: release` with
  `valueFiles: [../../environments/crc.yaml, ../../promotion.yaml]` (Blocks 4 to 8). With `--values X`, X comes first.
- `--argocd main` is unchanged: the chart's default images, read back as `:<appVersion>` (#414), and no `valueFiles`
  in the patch, so the Application file's own `crc.yaml` returns. That is how the lab leaves `release`.
- Every other mode sends what it sent before; the mode table gains the two `release` rows (Blocks 2, 3).
- `local-development/README.md`, `gitops/README.md`, `docs/RELEASING.md` and the epic skill say that during
  development the lab tracks `main`, that the race remains there and heals on its own, and that `--argocd release`
  removes it (Blocks 11 to 16). The epic skill's deploy step walks each epic release on `release` and then returns the lab to `main` (Orchestrator's notes 13).

### 3.7 The Application

`gitops/argocd-application-dashboard.yaml` is not edited: `targetRevision: main`, `valueFiles:
[../../environments/crc.yaml]`. When `--argocd release` writes the live Application, Argo CD keeps the order of
`valueFiles` and the last file wins (helm.md:150-157), so the digests win over anything in `crc.yaml`.
`valuesObject` (the `clusters` override) still outranks both and names no image.

### 3.8 The guarantee, and what stays outside it

**The guarantee, while the lab tracks `release`:** with the one-time steps done, Argo CD syncs only trees that
`promote.yml` wrote after reading both images back, and it pulls exactly the digests it read.
`release-crc.sh --argocd release` reads them back again before it writes the Application.

**While the lab tracks `main` (the development default):** no new guarantee. A release merge can still sync before
its image is pushed, and the pods wait in `ErrImagePull` until it is (§2.3, table 1).

**Outside it:** a person with the deploy key's private half (it is deleted from the laptop in step 2); a hand edit
of the live Application (`oc edit`); a digest deleted from quay.io after promotion (a missing image, never a wrong
one; published images are never deleted); with `SUPPLY_CHAIN_SIGNING=false`, labels are not proof of origin;
`--argocd main`, `--argocd <branch>`, bare `--argocd` and Helm mode; the published Helm chart, which still
resolves `:<appVersion>` (part A's gate guards it).

### 3.9 What does not change, and the test that holds it

| Unchanged | Held by |
|---|---|
| `publish.yml`, `helm.yaml`, aliases and signatures | no block edits the workflows; Block 22 only makes the immutable suffix's existing sha10 contract exact; `test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with` (no copy, no build in `promote.yml`) |
| the chart's templates, values and RBAC | RBAC rendered before and after with `crc.yaml`: 30 rule and binding lines each, REMOVED 0, ADDED 0 (§4.3) |
| `--argocd main` and `--argocd <branch>`: the alias read-back, a pin honoured, the waiter, no `valueFiles` in the patch | the existing `test_release_crc.py` tests, unchanged; `test_argocd_main_after_release_returns_to_the_files_values_and_the_aliases` |
| the committed Application | `test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes` |
| bare `--argocd` and `--argocd --values X` | `test_argocd_writes_the_application_once_with_everything_in_it`, unchanged |
| `helm.yaml`'s two readers | `test_the_label_readers_are_helm_yamls` holds the copies equal |

## 4. Tests

### 4.1 One test per Definition-of-Done item

| Definition of Done (#410 part B) | Test |
|---|---|
| 6: `release` written only after both images are read back; both pinned by digest; signature checked; `release` holds only the chart, `environments/` and `promotion.yaml` | `test_promote.py::test_a_publish_completion_promotes_main_with_both_images_pinned_by_digest` |
| 6: a failed or unfinished publish is never promoted | `test_a_run_promotes_nothing_while_mains_version_is_still_being_published`; `test_an_image_that_is_not_mains_application_is_refused[stale-dashboard-alias, stale-report-alias, stale-arm64-child]`; `test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_cosign` |
| 6: a chart-only merge carries the last built image | `test_a_chart_only_merge_carries_the_images_release_already_runs` |
| 6: a replaced pending publish completion, or a rollback, cannot strand a ready `main` | `test_a_push_after_publish_completion_promotes_if_the_workflow_run_was_replaced`; `test_a_chart_merge_after_a_rollback_returns_release_to_main` |
| 6: two same-version image merges cannot cross a tree and an older artefact | `test_an_older_publish_completion_cannot_promote_a_later_same_version_image_change`; `test_a_same_version_image_whose_alias_names_another_build_is_red` |
| rollback; one at a time; nothing written twice | `test_an_older_commit_needs_rollback_and_the_same_tree_twice_changes_nothing`; `test_one_promotion_at_a_time_read_only_token_and_the_deploy_key_from_the_release_environment` |
| only `main` is promoted; no `release` means a red run | `test_a_commit_that_is_not_on_main_is_refused`; `test_without_a_release_branch_nothing_is_promoted`; `test_it_runs_after_a_successful_publish_on_main_and_after_a_chart_or_environment_merge` |
| a pinned tag is promoted as pinned | `test_a_pinned_tag_is_promoted_as_pinned` |
| nothing builds; the cosign publish.yml signs with | `test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with` |
| one label rule in three places | `test_the_label_readers_are_helm_yamls` |
| the immutable image is the last image-input commit's, its suffix is exactly that commit's first ten characters in publisher and promoter, and its alias is the same digest | `test_the_image_input_list_is_publish_ymls_and_the_immutable_tag_is_source_bound` |
| 8 (amended): the lab tracks `main` by default; `release-crc.sh` names the file `promote.yml` writes | `test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes` |
| 7: `--argocd release` re-reads the pinned digests, lists `promotion.yaml` last, refuses a missing pin and a wrong digest | `test_release_crc.py::test_argocd_release_reads_the_pinned_digests_back_and_lists_promotion_yaml_last`; `test_argocd_release_without_a_promotion_is_refused_before_anything_is_written`; `test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release` |
| 7 (amended): `--argocd main` switches back with the file's values and the aliases | `test_argocd_main_after_release_returns_to_the_files_values_and_the_aliases` (a regression guard: it passes on main too) |
| 8: when chosen, the lab tracks `release`, pods on the pinned digests; PVC UIDs unchanged | §5, on the lab |
| 9: the release docs | `docs/RELEASING.md` "Promotion to the lab" and five troubleshooting rows (Blocks 11, 12) |

### 4.2 Each test fails without the change, and why

- `test_promote.py` on `6421cff7`: all 21 cases fail or error, because `.github/workflows/promote.yml` does not exist
  (§4.3). On the reviewed workflow, the five tests of Orchestrator's notes 14 fail for the reasons given there.
- Each check was switched off in a copy of the applied tree, one at a time, and the tests that name it failed
  (§4.3, the mutation row): the label check, the publish-completion version rule, the immutable-tag source binding,
  the exact-ten-character publisher suffix, the alias digest equality, the ancestry check, the signature check,
  carrying an extra directory into `release`, and in `release-crc.sh` the digest read-back and `promotion.yaml` in
  the values.
- `test_release_crc.py` with `6421cff7`'s script (`RELEASE_CRC_UNDER_TEST`): the three new `release` tests fail;
  the fourth new test, `--argocd main` after `release`, passes there too, because it guards today's behaviour (§4.3).

### 4.3 The proof

Every command ran on 2026-10-04 with the repository's venv (Python 3.14, `PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=$PWD` from `local-development`). "Main" is `git archive 6421cff7` with this spec, its index row and the
index count; "applied" is the same tree after `apply-spec-blocks.py --apply`. Python 3.11, CI's other leg, was not
run here.

| Check | Command | Result |
|---|---|---|
| the blocks | `python3 local-development/apply-spec-blocks.py docs/specs/SPEC_P1_promote_release_branch.md .`, then `--apply`, in a clean git copy | `22 blocks check out across 13 files`; the untouched Application remains byte-equal (`cmp`) |
| CI's hermetic selection, main | `pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` (.github/workflows/ci.yml:238) | `7630 passed, 23 skipped, 698 deselected, 5 xfailed, 2 warnings in 423.12s` |
| the same, applied | the same | `7655 passed, 23 skipped, 698 deselected, 5 xfailed, 2 warnings in 446.65s`: +25, the collection's difference (row below) |
| the new tests on main's code | `test_promote.py` and `test_release_crc.py` copied onto `6421cff7` | `6 failed, 15 errors` (no `promote.yml`); `3 failed, 33 passed` (the three `release` tests) |
| the new tests on the reviewed workflow | `test_promote.py` against `51e28a81`'s Block 1 | `6 failed, 15 passed` (Orchestrator's notes 14) |
| the same, applied | `pytest tests/test_promote.py`, `pytest tests/test_release_crc.py` | `21 passed`; `36 passed` |
| collection | `pytest tests/ -q --collect-only --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | main `7658/8356`, applied `7683/8381` (698 deselected each): +25, which is `test_promote.py`'s 21 and `test_release_crc.py`'s 32 → 36 (per-file diff of the collection) |
| each check held (mutation) | one check switched off in a copy of the applied tree, then the test file | label check: 3 failed; publish-completion version rule: 1; immutable-tag source binding: 3; publisher still using minimum-length `--short=10`: 1; alias digest equality: 2; ancestry check: 1; signature check: 2; `local-development/` carried into `release`: 1; `--argocd release` not reading the pinned digests: 3; `promotion.yaml` left out of its `valueFiles`: 1 |
| the workflows | actionlint v1.7.12 | nothing in `promote.yml`; the repository's other 2 findings are main's (2 before, 2 after) |
| the scripts | `bash -n` and `shellcheck -S warning` on `release-crc.sh` and on the promotion step extracted from the YAML | clean |
| RBAC | Roles, ClusterRoles and their bindings rendered with `environments/crc.yaml`, before and after, one line per rule or binding | 30 and 30; REMOVED 0, ADDED 0 |
| the render with a promotion file | `helm template … -f environments/crc.yaml -f promotion.yaml` | every dashboard and report image is `repository@sha256:…` (§2.3) |
| two-namespace readiness | three `helm template` renders (§2.3) | under one release name, 9 objects collide; with `group-sync-dashboard-dev`, none |
| Markdown | `markdownlint-cli2` on the five edited `.md` files | 8 findings before, 8 after: none new |

## 5. On the lab (the implementing pull request)

Nothing here was run for this spec. The implementer runs it with the lab's kubeconfig, after review and after the
operator's steps 1 to 4 (§3.5):

1. Record the UIDs of the `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` PVCs.
2. Before the merge, pause the dashboard Application's auto-sync, or accept the race: this pull request moves
   `appVersion` to 5.2.0 on `main`, which the lab tracks.
3. After the merge: `gh run list --workflow publish.yml -L 1` and `gh run list --workflow promote.yml -L 3`. Expected:
   publish `success`; the push-triggered promote green with the notice "immutable image … is not ready";
   the `workflow_run` promote green, with two `image   : … -> sha256:…` lines and `promoted: main <sha> -> release`.
4. Read `release`: `git ls-tree --name-only origin/release` prints `charts`, `environments`, `promotion.yaml`, and
   each digest in `git show origin/release:promotion.yaml` equals `oc image info quay.io/ephico2real/<image>:5.2.0`'s.
5. `local-development/release-crc.sh --argocd release`. Expected: `the digests in promotion.yaml`, two
   `image   : …@sha256:… is application 5.2.0` lines, then Synced/Healthy at `release`'s tip. The pods' image IDs end
   in the pinned digests: `oc get pods -n group-sync-dashboard -o jsonpath='{..imageID}'`.
6. `local-development/release-crc.sh --argocd main`. Expected: the two `:5.2.0` aliases read back, then
   Synced/Healthy at `main`'s tip, with `valueFiles` back to `crc.yaml` alone
   (`oc get applications.argoproj.io group-sync-dashboard -n openshift-gitops -o jsonpath='{.spec.source.helm.valueFiles}'`).
   The lab stays on `main`, the development default.
7. The first chart-only merge that follows is promoted by its push run, at once, with the same digests.
8. Record the PVC UIDs again; they must be unchanged. The evidence goes under `reports/<date>_<slug>/` and on #598,
   pinned to the full merge sha.

## 6. What a reader sees, and what it costs

- **The lab, by default (`main`)**: nothing changes during development. A release merge can still reach it before
  its image is pushed, and the pods wait in `ErrImagePull` until it is (they heal on their own).
- **The lab, on `release` (`--argocd release`)**: it runs a release only once its images are published and checked.
  Between the merge and the promotion (about the publish run's 2.5 minutes, §2.3) it keeps running the previous
  release, instead of sitting in `ErrImagePull`.
- **The end state**: `group-sync-dashboard-dev` on `main`, `group-sync-dashboard` on `release`; this change is the
  same design with one namespace (Orchestrator's notes 11).
- **The Actions tab** gains `promote` runs: one per publish run, one per chart or `environments/` merge, each about
  half a minute (not measured: no run exists yet). A release merge shows one green notice run and one promoting run.
- **The repository** gains one branch, `release`, one commit per promotion, a deploy key, an environment, a ruleset
  and a GitHub deployment record per run.
- **Registry calls per promotion:** for each unpinned image, two digest reads (the immutable tag and the version alias), one raw-manifest read and one config read per
  Linux image, and one `cosign verify`. Nothing is copied, tagged or deleted.
- **What does not change:** the image, its tags and signatures; the published chart; the dashboard's RBAC; any
  install outside the lab.

## 7. Implementation blocks

Twenty-two blocks over thirteen files, in apply order: the workflow, `release-crc.sh`, the tests, the docs, the versions,
the CHANGELOG, and the publisher's exact sha10 derivation. `gitops/argocd-application-dashboard.yaml` is not edited (Orchestrator's notes 10). Lines added /
removed per file (the proof tree): `promote.yml` +270, `test_promote.py` +371, `test_release_crc.py` +67,
`release-crc.sh` +32 −10, `docs/RELEASING.md` +71, `docs/CHANGELOG.md` +14, `.claude/skills/epic/SKILL.md` +11 −10,
`Chart.yaml` +5 −2, `local-development/README.md` +4 −1, `gitops/README.md` +1, `pyproject.toml` and
`gsd/__init__.py` +1 −1 each, `build-and-push-external.sh` +2 −1.

The review of the implementation (PR #614) adds sixteen review blocks, R1 to R16, after Block 23
(Orchestrator's notes 16).

### Block 1 — `.github/workflows/promote.yml`: the workflow: three triggers, the source-bound ready rule, the read-back, the commit to `release`

<!-- block: .github/workflows/promote.yml | create -->

```yaml
# Promote main to the `release` branch (#598, docs/RELEASING.md "Promotion to the lab").
#
# BUILD ONCE, PROMOTE THE ARTEFACT. publish.yml builds and signs each image once; this workflow builds
# nothing. It reads both images back (the version label on every Linux image, the signature when signing is
# on), pins them by digest in `promotion.yaml`, and commits that file with the chart and environments/ at that
# main commit to `release`. An Argo CD Application on `release` never sees a chart whose images are not
# published yet; one on main can (4.1.0, 4.4.0, 5.1.0: ErrImagePull until publish.yml pushed the image). During
# development the lab tracks main and `release-crc.sh --argocd release` is the opt-in, so `release` is kept
# current on every green publish.
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
          # publish.yml's image-input allowlist. The first-parent path history identifies the merge commit whose
          # immutable <appVersion>-<sha> images the target tree must run. A test holds this list equal to publish.yml.
          IMAGE_INPUTS=(
            'local-development/gsd/**' 'local-development/pyproject.toml' 'local-development/README.md'
            'local-development/uninstall-lists.py' 'local-development/image-proof.py'
            'local-development/Containerfile' 'local-development/.containerignore'
            'local-development/build-and-push-external.sh' 'local-development/Containerfile.report'
            'local-development/report-image-proof.py' 'local-development/build-and-push-report.sh'
            '.github/workflows/publish.yml'
          )
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

          # A workflow_run may safely carry later chart/environment-only commits, but not a later application
          # version. Push runs prove readiness below from the immutable build tag instead of assuming that release's
          # current version is the only ready one: GitHub concurrency may replace a pending workflow_run with a later
          # push, and a push must then be able to promote the already-published artefact.
          app_version=$(app_version_at "${target}")
          if [ -z "${app_version}" ]; then
            echo "::error::cannot read appVersion from ${CHART} at ${target}."
            exit 1
          fi
          if [ "${EVENT}" = workflow_run ] && [ "${app_version}" != "$(app_version_at "${RUN_SHA}")" ]; then
            echo "::notice::main ${target:0:10} is application ${app_version}, whose images publish.yml has not finished;"
            echo "::notice::its completion promotes main. Nothing was promoted by this run."
            exit 0
          fi
          image_commit=$(git log --first-parent -1 --format=%H "${target}" -- "${IMAGE_INPUTS[@]}")
          if [ -z "${image_commit}" ]; then
            echo "::error::cannot find the last publish.yml image-input commit at ${target}."
            exit 1
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
            tag="${this_pin:-${app_version}-${image_commit:0:10}}"
            if ! digest=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${name}:${tag}"); then
              if [ -z "${this_pin}" ] && { [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; }; then
                echo "::notice::main ${target:0:10}'s immutable image ${name}:${tag} is not ready;"
                echo "::notice::its successful publish run promotes main. Nothing was promoted by this run."
                exit 0
              fi
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
              if ! alias_digest=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${name}:${app_version}"); then
                if [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; then
                  echo "::notice::${name}:${app_version} has not reached ${tag}; publish.yml is still running."
                  echo "::notice::Nothing was promoted by this run."
                  exit 0
                fi
                echo "::error::cannot read ${name}:${app_version} after its publish run succeeded, so nothing was promoted."
                exit 1
              fi
              if [ "${alias_digest}" != "${digest}" ]; then
                if [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; then
                  echo "::notice::${name}:${app_version} does not yet name ${tag}; publish.yml is still running."
                  echo "::notice::Nothing was promoted by this run."
                  exit 0
                fi
                echo "::error::${name}:${app_version} resolves to ${alias_digest}, not ${digest}, the image built at"
                echo "::error::${image_commit}. A same-version image change reached main; cut the next application version."
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


### Block 2 — `local-development/release-crc.sh` (1 of 7): the mode table's two `release` rows

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


### Block 3 — `local-development/release-crc.sh` (2 of 7): the typical loop: `--argocd main`, or `--argocd release` to deploy only what promote.yml read back

<!-- block: local-development/release-crc.sh | edit -->

```bash
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd main. The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298) — a guarantee
# about the RELEASE COMMIT, not about the tag on quay, which the branch path reads back (below).
```

```bash
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd main, or --argocd release to deploy only what
# promote.yml read back (#598; --argocd main switches back). The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298) — a guarantee
# about the RELEASE COMMIT, not about the tag on quay, which the branch path reads back (below).
```


### Block 4 — `local-development/release-crc.sh` (3 of 7): `release` lists `promotion.yaml` last

<!-- block: local-development/release-crc.sh | edit -->

```bash
    {"name": "reporting.image.repository", "value": image[2]}, {"name": "reporting.image.tag", "value": image[3]},
] if image else []}
if values:
    helm["valueFiles"] = [values]
print(json.dumps({"spec": {"source": {"targetRevision": revision, "helm": helm}}}))
```

```bash
    {"name": "reporting.image.repository", "value": image[2]}, {"name": "reporting.image.tag", "value": image[3]},
] if image else []}
if revision == "release":   # the promoted digests last, so they win (#598)
    helm["valueFiles"] = [values or "../../environments/crc.yaml", "../../promotion.yaml"]
elif values:
    helm["valueFiles"] = [values]
print(json.dumps({"spec": {"source": {"targetRevision": revision, "helm": helm}}}))
```


### Block 5 — `local-development/release-crc.sh` (4 of 7): the read-back's comment and locals

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


### Block 6 — `local-development/release-crc.sh` (5 of 7): on `release`, the refs are the pinned digests; no `promotion.yaml` is refused

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


### Block 7 — `local-development/release-crc.sh` (6 of 7): a missing pinned digest says what it is

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


### Block 8 — `local-development/release-crc.sh` (7 of 7): the branch path says which images it hands Argo CD

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
# image, e.g. `--argocd main` after a merge, or at `release` and its promoted digests. Any other --argocd use
# builds this commit first.
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  images="the chart's default image"
  [ "$ARGO_REVISION" = release ] && images="the digests in promotion.yaml, last in valueFiles"
  echo "argocd  : ${APP_NAME} -> revision ${ARGO_REVISION} (${EXPECTED_REVISION:0:10}), ${images}"
  published_image_is_the_release "$EXPECTED_REVISION" || exit 1
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
```


### Block 9 — `local-development/tests/test_promote.py`: the promotion step, run against stubs, with the review's race and source-binding cases

<!-- block: local-development/tests/test_promote.py | create -->

```python
"""promote.yml: the `release` branch holds only what was read back from the registry (#598, SPEC_P1).

The promotion step is RUN, as GitHub runs `shell: bash`, in a real git repository with a bare `origin`, against
test_supply_chain.py's stub skopeo and a stub cosign. Real git writes the `release` commit; only the registry and
Sigstore are replaced. The workflow's shape (its triggers, its scopes, its one writer) is read from the YAML.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import subprocess

import pytest
import yaml

from test_supply_chain import APP, CHART_FILE, DASHBOARD, HELM, PUBLISH, REPORT, SKOPEO_STUB, VALUES_FILE, _jobs, _push, _released, _step

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTE = REPO / ".github" / "workflows" / "promote.yml"
APPLICATION = REPO / "gitops" / "argocd-application-dashboard.yaml"
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"
PUBLISHER = REPO / "local-development" / "build-and-push-external.sh"
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
        "local-development/README.md": "base image input\n",
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
            signing: str = "", unsigned: str = "", mirror_immutable: bool = True) -> tuple[subprocess.CompletedProcess, str]:
    state, log = lab["tmp"] / "registry.json", lab["tmp"] / "calls.log"
    # publish.yml always writes <appVersion>-<10-char sha>. Most tests start from the release aliases, so mirror
    # those exact digests under the immutable names the workflow now resolves. A race test disables this to model
    # main moving past the publish run that just completed.
    if mirror_immutable:
        target = sha or _git(lab["repo"], "rev-parse", "origin/main")
        image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", target, "--",
                            "local-development/README.md")
        version = re.search(r'appVersion: "([0-9.]+)"', _git(lab["repo"], "show", f"{target}:charts/group-sync-dashboard/Chart.yaml")).group(1)
        for image in (DASHBOARD, REPORT):
            digest = registry["tags"].get(f"{image}:{version}")
            if digest:
                registry["tags"][f"{image}:{version}-{image_commit[:10]}"] = digest
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
                                                           "local-development/README.md": f"application {version}\n"})


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
        assert tip[:10] in done.stdout and "Nothing was promoted" in done.stdout
        assert ("skopeo" in log) is (event == "push")
        assert release(lab) == lab["start"]


def test_a_push_after_publish_completion_promotes_if_the_workflow_run_was_replaced(lab) -> None:
    """GitHub concurrency keeps one pending run; a later push may replace the publish completion (review of #613, F1)."""
    tip = _main_at(lab, APP)
    done, _ = promote(lab, _released(), event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {tip}"


def test_a_chart_merge_after_a_rollback_returns_release_to_main(lab) -> None:
    """A rollback must not make later chart-only promotions stick on the rolled-back version (review of #613, F1)."""
    older = _main_at(lab, "0.9.0")
    _main_at(lab, APP)
    registry = _released()
    _push(registry, DASHBOARD, "0.9.0", "0.9.0")
    _push(registry, REPORT, "0.9.0", "0.9.0")
    assert promote(lab, registry)[0].returncode == 0
    assert promote(lab, registry, sha=older, rollback=True)[0].returncode == 0
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    done, _ = promote(lab, registry, event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {chart_only}"
    assert promotion(lab)["image"]["digest"] == registry["tags"][f"{DASHBOARD}:{APP}"]


def test_an_older_publish_completion_cannot_promote_a_later_same_version_image_change(lab) -> None:
    """Two PRs that chose the same next MINOR: the older image must not ride the later tree (review of #613, F2)."""
    first = _main_at(lab, APP)
    second = _commit(lab["repo"], "parallel PR reused the version",
                     {"local-development/README.md": "a second image at the same version\n"})
    registry = _released()
    for image in (DASHBOARD, REPORT):
        registry["tags"][f"{image}:{APP}-{first[:10]}"] = registry["tags"][f"{image}:{APP}"]
    done, _ = promote(lab, registry, event="workflow_run", run_sha=first, mirror_immutable=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Nothing was promoted" in done.stdout and second[:10] in done.stdout
    assert release(lab) == lab["start"]


def test_a_same_version_image_whose_alias_names_another_build_is_red(lab) -> None:
    """The second PR's own publish completion: its immutable image exists, but `:<appVersion>` is the first's."""
    _main_at(lab, APP)
    second = _commit(lab["repo"], "parallel PR reused the version",
                     {"local-development/README.md": "a second image at the same version\n"})
    registry = _released()
    for image in (DASHBOARD, REPORT):
        _push(registry, image, f"{APP}-{second[:10]}", APP, APP)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=second, mirror_immutable=False)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "A same-version image change reached main" in done.stdout
    assert release(lab) == lab["start"]


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
    assert image in done.stdout and "is application" in done.stdout and "0.24.0" in done.stdout
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
    for word in ("podman", "docker build", "buildah", "./build-and-push", "cosign sign", "skopeo copy"):
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


def test_the_image_input_list_is_publish_ymls_and_the_immutable_tag_is_source_bound() -> None:
    run = _step(_jobs(PROMOTE)["promote"], STEP)["run"]
    array = shlex.split(re.search(r"IMAGE_INPUTS=\(\n(.*?)^\)", run, re.M | re.S).group(1))
    assert array == yaml.safe_load(PUBLISH.read_text()).get(True)["push"]["paths"]
    assert 'git log --first-parent -1 --format=%H "${target}" -- "${IMAGE_INPUTS[@]}"' in run
    assert 'tag="${this_pin:-${app_version}-${image_commit:0:10}}"' in run
    assert 'if [ "${alias_digest}" != "${digest}" ]; then' in run
    publisher = PUBLISHER.read_text()
    assert "COMMIT=$(git rev-parse HEAD)" in publisher
    assert 'COMMIT="${COMMIT:0:10}"' in publisher
    assert "git rev-parse --short=10 HEAD" not in publisher


def test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes() -> None:
    """The operator, 2026-10-04: "main by default; release optional". `--argocd release` is the opt-in."""
    source = yaml.safe_load(APPLICATION.read_text())["spec"]["source"]
    assert source["targetRevision"] == "main"
    assert source["helm"]["valueFiles"] == ["../../environments/crc.yaml"]
    assert "git update-index --add --cacheinfo \"100644,${blob},promotion.yaml\"" in PROMOTE.read_text()
    script = RELEASE_CRC.read_text()
    assert '"../../promotion.yaml"' in script and 'git show "${revision}:promotion.yaml"' in script
```


### Block 10 — `local-development/tests/test_release_crc.py`: the `release` opt-in and `--argocd main` switching back

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python


# --- the waiter on its own ----------------------------------------------------------------------

```

```python


# --- the opt-in: the lab deploys what promote.yml read back (#598) --------------------------------

DASHBOARD_DIGEST, REPORT_DIGEST = "sha256:" + "a" * 64, "sha256:" + "b" * 64
PROMOTION = (f"image:\n  repository: quay.io/example/group-sync-dashboard\n  digest: {DASHBOARD_DIGEST}\n"
             f"reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    digest: {REPORT_DIGEST}\n")


def _release_branch(lab, promotion: str | None) -> None:
    """origin/release as promote.yml writes it: the chart, environments/ and promotion.yaml (or none)."""
    _git(lab["repo"], "checkout", "-qb", "release")
    if promotion is not None:
        (lab["repo"] / "promotion.yaml").write_text(promotion)
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-q", "--allow-empty", "-m", "promote: main")
    _git(lab["repo"], "push", "-q", "origin", "release")
    _git(lab["repo"], "checkout", "-q", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", "release"))


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


def test_argocd_main_after_release_returns_to_the_files_values_and_the_aliases(lab):
    """main stays the dev-phase default (#598): switching back sends no promotion.yaml and reads the aliases."""
    _release_branch(lab, PROMOTION)
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard:{_version()} {LINUX_IMAGES}" in log
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": []}}


# --- the waiter on its own ----------------------------------------------------------------------

```


### Block 11 — `docs/RELEASING.md` (1 of 2): "Promotion to the lab": main by default, release optional, the end state and the operator's one-time steps

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
6. Optional: point the lab at it with `local-development/release-crc.sh --argocd release`.

---
```


### Block 12 — `docs/RELEASING.md` (2 of 2): five troubleshooting rows

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
| promote run says `whose images publish.yml has not finished`, `immutable image … is not ready` or the version alias `does not yet name` it, and promotes nothing | main's exact image is still publishing | nothing to do: its green completion, or a later chart/environment push, promotes main. If publish is red, fix it; `release` stays on the last promotion |
| promote run says a same-version image change reached `main` | two PRs chose the same next application version, so the immutable image and `:<appVersion>` alias differ | cut the next MINOR or MAJOR and let `publish.yml` finish green; never retag by hand |
| promote run is red with `is application X, not <appVersion>` or `carries no signature from publish.yml on main` | the tag names another build, or the digest was not signed by `publish.yml` on `main`. Nothing was written to `release` | wait for `publish.yml` to finish green, then Run workflow on promote. Never edit `release` by hand |
| promote run is red with `origin has no release branch` or `RELEASE_DEPLOY_KEY is not set` | the operator's one-time steps are not done | "Promotion to the lab", steps 1 to 5 |
| promote run is red with `is not a later commit` | a Run workflow named a commit older than the one `release` holds | check `rollback` to deploy it on purpose |
| `release-crc.sh --argocd release` says `origin/release has no promotion.yaml` | no promotion has run yet | run promote (step 5 above) |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
| a new pod runs different bits than its neighbour | somebody republished an alias between the two container creations | pin `image.tag` to the sha form |
```


### Block 13 — `gitops/README.md`: the dashboard Application's row: main by default, the race, the opt-in

<!-- block: gitops/README.md | edit -->

```markdown
| `argocd-rbac-kubeadmin.yaml` | a patch for the `openshift-gitops` ArgoCD CR: OpenShift GitOps' default policy grants `role:admin` to the *groups* `system:cluster-admins` / `cluster-admins`, but Dex's OpenShift connector puts only `system:authenticated` in a token's `groups` (kubeadmin's cluster-admin membership is a virtual group Dex never sees — measured on CRC 2026-09-19: `PermissionDenied` on every list, an empty UI). This matches the `name` claim too and grants `kubeadmin` admin. On a cluster where a `cluster-admins` Group object exists this is not needed |
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |

```

```markdown
| `argocd-rbac-kubeadmin.yaml` | a patch for the `openshift-gitops` ArgoCD CR: OpenShift GitOps' default policy grants `role:admin` to the *groups* `system:cluster-admins` / `cluster-admins`, but Dex's OpenShift connector puts only `system:authenticated` in a token's `groups` (kubeadmin's cluster-admin membership is a virtual group Dex never sees — measured on CRC 2026-09-19: `PermissionDenied` on every list, an empty UI). This matches the `name` claim too and grants `kubeadmin` admin. On a cluster where a `cluster-admins` Group object exists this is not needed |
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-dashboard.yaml` | the dashboard chart from `main` with `environments/crc.yaml`, the default while the project is in development. `main`'s image race remains: a release merge can sync before `publish.yml` has pushed its image, and the pods wait in `ErrImagePull` until it exists (measured at 4.1.0, 4.4.0, 5.1.0). `local-development/release-crc.sh --argocd release` removes the race: it points this Application at the `release` branch with `promotion.yaml`, the digests `promote.yml` read back, as the last values file; `--argocd main` switches back (#598; `docs/RELEASING.md`, "Promotion to the lab") |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |

```


### Block 14 — `local-development/README.md`: the typical loop: the race on `main`, and `--argocd release`

<!-- block: local-development/README.md | edit -->

```markdown
spec, records what is deployed. The typical loop: iterate with the bare script (or `--values` for
a local variant), `--argocd` on the pushed head before the PR is called ready, `--argocd main`
after a merge once the app release is cut. `./argocd-wait.sh` is the waiter the Argo modes use: it
accepts Synced/Healthy/Succeeded only once the status was computed for the current spec
(`status.sync.comparedTo.source`) and for the expected commit, and names the failed hook or
```

```markdown
spec, records what is deployed. The typical loop: iterate with the bare script (or `--values` for
a local variant), `--argocd` on the pushed head before the PR is called ready, `--argocd main`
after a merge once the app release is cut. During development the lab tracks `main`, and a release merge can still
reach it before its image is pushed (`ErrImagePull` until it is). `--argocd release` deploys only what `promote.yml`
read back, pinned by digest, and `--argocd main` switches back (#598; `docs/RELEASING.md`, "Promotion to the
lab"). `./argocd-wait.sh` is the waiter the Argo modes use: it
accepts Synced/Healthy/Succeeded only once the status was computed for the current spec
(`status.sync.comparedTo.source`) and for the expected commit, and names the failed hook or
```


### Block 15 — `.claude/skills/epic/SKILL.md` (1 of 2): the epic's Definition of Done: walk on `release`, then back to `main`

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
- [ ] The published release walked on CRC through `release-crc.sh --argocd release`, then the lab returned to `main` with
      `release-crc.sh --argocd main`; PVC UIDs unchanged.
- [ ] The branches this epic used are deleted, each proven merged first.
- [ ] The session changelog records the epic.
```


### Block 16 — `.claude/skills/epic/SKILL.md` (2 of 2): the deploy step: `--argocd release`, the walk, `--argocd main`

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
3. **Deploy.** After those workflows and `promote.yml` are green, walk the release on the promoted path:
   `local-development/release-crc.sh --argocd release` (the chart on `release` and the two digests `promote.yml`
   pinned in `promotion.yaml`, read back before the Application is written), walk it, then
   `local-development/release-crc.sh --argocd main` to return the lab to `main`, its day-to-day branch (#598;
   `docs/RELEASING.md`, "Promotion to the lab"). Bare `--argocd` builds HEAD and pins that image, so it is not the
   published release. Both modes refuse an image whose `org.opencontainers.image.version` label is not the release's
   (#410): wait for `publish.yml` and `promote.yml`, then re-run; never retag or edit `release` by hand. Between
   epics the lab tracks `main`, which can sync a release merge before its image is pushed (`ErrImagePull` until it
   is). Record the two PVC UIDs before and after; they must be unchanged.

Then:
```


### Block 17 — `charts/group-sync-dashboard/Chart.yaml` (1 of 2): chart 0.70.3 and its history line

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


### Block 18 — `charts/group-sync-dashboard/Chart.yaml` (2 of 2): application 5.2.0's history line

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


### Block 19 — `local-development/pyproject.toml`: application 5.2.0

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


### Block 20 — `local-development/gsd/__init__.py`: application 5.2.0

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


### Block 21 — `docs/CHANGELOG.md`: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

```markdown

## Unreleased

- **The reports' clock is the snapshot's (#592, #607, #593, `docs/specs/SPEC_F7_snapshot_clock.md`; application 5.1.0,
```

```markdown

## Unreleased

- **The lab deploys only what `promote.yml` read back (#598, `docs/specs/SPEC_P1_promote_release_branch.md`;
  application 5.2.0, chart 0.70.3).** A new workflow, `promote.yml`, runs after a green `publish.yml` on `main`, after
  a merge to the chart or `environments/`, or by hand. It builds nothing. For each unpinned image it reads the
  immutable `<appVersion>-<sha10>` of main's last image-input commit, requires `:<appVersion>` at the same digest,
  checks every Linux image's version label and the signature from `publish.yml` on `main`, then pins the digest in
  `promotion.yaml` and commits that file with the chart and `environments/` to the `release` branch as a
  fast-forward. A merge whose exact image is still being published promotes nothing until it is ready. During development the lab's Application still tracks `main` (the operator,
  2026-10-04: "main by default; release optional"), so the `ErrImagePull` race seen at 4.1.0, 4.4.0 and 5.1.0 remains
  there and heals on its own. `release-crc.sh --argocd release` removes it: it reads the pinned digests back, then
  points the Application at `release` with `promotion.yaml` as its last values file; `--argocd main` switches back.
  The `release` branch, its ruleset and the deploy key are the operator's one-time steps (`docs/RELEASING.md`,
  "Promotion to the lab"). The application moves because `local-development/README.md` and the publisher's exact-sha10
  derivation are image inputs; no application code, template, value or RBAC change.

- **The reports' clock is the snapshot's (#592, #607, #593, `docs/specs/SPEC_F7_snapshot_clock.md`; application 5.1.0,
```

### Block 22 — `local-development/build-and-push-external.sh`: make `<sha10>` exactly ten characters

`git rev-parse --short=10` asks for a unique abbreviation of at least ten characters; Git may lengthen it when two
objects share that prefix. Promotion names the immutable tag with the literal first ten characters, so the publisher
must do the same. This changes no current tag and makes the documented tag contract stable as the object database grows.

<!-- block: local-development/build-and-push-external.sh | edit -->

```bash
COMMIT=$(git rev-parse --short=10 HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)
```

```bash
COMMIT=$(git rev-parse HEAD)
COMMIT="${COMMIT:0:10}"
BRANCH=$(git rev-parse --abbrev-ref HEAD)
```

### Block 23 — `local-development/tests/test_build_and_push_report.py`: the fake `git` answers the full id (Block 22)

Block 22 makes the script ask `git rev-parse HEAD` instead of `--short=10`. This test's fake `git` answered only the
old call, so the script failed (found by the orchestrator's full hermetic run on the applied tree). The fake now answers
a full forty-character id whose first ten characters are the same `0123456789`, so every tag the test expects is
unchanged.

<!-- block: local-development/tests/test_build_and_push_report.py | edit -->
```python
  "rev-parse --short=10 HEAD") echo 0123456789 ;;
```

```python
  "rev-parse HEAD") echo 0123456789abcdef0123456789abcdef01234567 ;;
```

### Block R1 — `.github/workflows/promote.yml` (1 of 5): checkout keeps no credential (`persist-credentials: false`, no key) (review of #614)

<!-- block: .github/workflows/promote.yml | edit -->

```yaml
          ref: main
          fetch-depth: 0
          ssh-key: ${{ secrets.RELEASE_DEPLOY_KEY }}

      - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
```

```yaml
          ref: main
          fetch-depth: 0
          # The repository is public: no credential stays in git's config. The deploy key exists only in "Push release".
          persist-credentials: false

      - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
```


### Block R2 — `.github/workflows/promote.yml` (2 of 5): each run clears the refs it prepares for the push step (review of #614)

<!-- block: .github/workflows/promote.yml | edit -->

```yaml
        run: |
          set -euo pipefail
          CHART=charts/group-sync-dashboard/Chart.yaml
          VALUES=charts/group-sync-dashboard/values.yaml
```

```yaml
        run: |
          set -euo pipefail
          # "Push release" pushes only what this run prepares; a ref left by an earlier run on this checkout is not that.
          git update-ref -d refs/promote/release 2>/dev/null || true
          git update-ref -d refs/promote/target 2>/dev/null || true
          CHART=charts/group-sync-dashboard/Chart.yaml
          VALUES=charts/group-sync-dashboard/values.yaml
```


### Block R3 — `.github/workflows/promote.yml` (3 of 5): `probe` and `absent`: only "manifest unknown" is not published yet (OB2 F2) (review of #614)

<!-- block: .github/workflows/promote.yml | edit -->

```yaml
          ' < "${values}")
          promotion="# Written by .github/workflows/promote.yml for main ${target}: the images it read back, by digest."
          for spec in "${REPO}|${PINNED}|image:" "${REPO}-report|${REPORT_PINNED}|reporting:"; do
            IFS='|' read -r name this_pin key <<< "${spec}"
            tag="${this_pin:-${app_version}-${image_commit:0:10}}"
            if ! digest=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${name}:${tag}"); then
              if [ -z "${this_pin}" ] && { [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; }; then
                echo "::notice::main ${target:0:10}'s immutable image ${name}:${tag} is not ready;"
                echo "::notice::its successful publish run promotes main. Nothing was promoted by this run."
                exit 0
              fi
              echo "::error::cannot read ${name}:${tag} (skopeo's message is above), so nothing was promoted."
              echo "::error::Re-run this workflow once the registry answers, or once publish.yml is green."
              exit 1
```

```yaml
          ' < "${values}")
          promotion="# Written by .github/workflows/promote.yml for main ${target}: the images it read back, by digest."
          # Unreachable is not absent (helm.yaml, "Label the image"): only the registry's "manifest unknown" means a
          # name is not published yet. Any other failure is "cannot tell", a red run on every path, never a notice.
          probe_err=$(mktemp)
          trap 'rm -f "${probe_err}"' EXIT
          probe() { skopeo inspect --no-tags --format '{{.Digest}}' "docker://$1" 2>"${probe_err}"; }
          absent() { grep -qi 'manifest unknown' "${probe_err}"; }
          for spec in "${REPO}|${PINNED}|image:" "${REPO}-report|${REPORT_PINNED}|reporting:"; do
            IFS='|' read -r name this_pin key <<< "${spec}"
            tag="${this_pin:-${app_version}-${image_commit:0:10}}"
            if ! digest=$(probe "${name}:${tag}"); then
              if absent && [ -z "${this_pin}" ] && { [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; }; then
                echo "::notice::main ${target:0:10}'s immutable image ${name}:${tag} is not ready;"
                echo "::notice::its successful publish run promotes main. Nothing was promoted by this run."
                exit 0
              fi
              echo "::error::cannot read ${name}:${tag}, so nothing was promoted: $(head -c 400 "${probe_err}")"
              echo "::error::Re-run this workflow once the registry answers, or once publish.yml is green."
              exit 1
```


### Block R4 — `.github/workflows/promote.yml` (4 of 5): the alias probe: a notice only when absent; otherwise red with skopeo's message (review of #614)

<!-- block: .github/workflows/promote.yml | edit -->

```yaml
                exit 1
              fi
              if ! alias_digest=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${name}:${app_version}"); then
                if [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; then
                  echo "::notice::${name}:${app_version} has not reached ${tag}; publish.yml is still running."
                  echo "::notice::Nothing was promoted by this run."
                  exit 0
                fi
                echo "::error::cannot read ${name}:${app_version} after its publish run succeeded, so nothing was promoted."
                exit 1
              fi
```

```yaml
                exit 1
              fi
              if ! alias_digest=$(probe "${name}:${app_version}"); then
                if absent && { [ "${EVENT}" = push ] || { [ "${EVENT}" = workflow_run ] && [ "${image_commit}" != "${RUN_SHA}" ]; }; }; then
                  echo "::notice::${name}:${app_version} has not reached ${tag}; publish.yml is still running."
                  echo "::notice::Nothing was promoted by this run."
                  exit 0
                fi
                echo "::error::cannot read ${name}:${app_version}, so nothing was promoted: $(head -c 400 "${probe_err}")"
                echo "::error::Re-run this workflow once the registry answers, or once publish.yml is green."
                exit 1
              fi
```


### Block R5 — `.github/workflows/promote.yml` (5 of 5): the commit is prepared under local refs; the `Push release` step alone loads the key (Codex F1) (review of #614)

<!-- block: .github/workflows/promote.yml | edit -->

```yaml
          commit=$(git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
            commit-tree "${tree}" -p origin/release -m "promote: main ${target}" -m "Application ${app_version}, read back by promote.yml.")
          git push origin "${commit}:refs/heads/release"
          echo "promoted: main ${target} -> release ${commit}"
```

```yaml
          commit=$(git -c user.name='github-actions[bot]' -c user.email='41898282+github-actions[bot]@users.noreply.github.com' \
            commit-tree "${tree}" -p origin/release -m "promote: main ${target}" -m "Application ${app_version}, read back by promote.yml.")
          git update-ref refs/promote/release "${commit}"
          git update-ref refs/promote/target "${target}"
          echo "prepared: main ${target} -> release ${commit}"

      # The deploy key bypasses the release ruleset, so it lives in this step alone (review of #614): not in checkout,
      # the cosign installer or the registry read-back above.
      - name: Push release
        shell: bash
        env:
          RELEASE_DEPLOY_KEY: ${{ secrets.RELEASE_DEPLOY_KEY }}
        run: |
          set +x
          set -euo pipefail
          if ! commit=$(git rev-parse --verify --quiet 'refs/promote/release^{commit}'); then
            echo "nothing was prepared for release; no push is needed."
            exit 0
          fi
          target=$(git rev-parse --verify 'refs/promote/target^{commit}')
          key=$(mktemp)
          known_hosts=$(mktemp)
          trap 'rm -f "${key}" "${known_hosts}"' EXIT
          printf '%s\n' "${RELEASE_DEPLOY_KEY}" > "${key}"
          chmod 600 "${key}"
          # GitHub's published Ed25519 host key (docs.github.com "GitHub's SSH key fingerprints", api.github.com/meta).
          printf '%s\n' 'github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl' > "${known_hosts}"
          export GIT_SSH_COMMAND="ssh -i ${key} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o CheckHostIP=no -o UserKnownHostsFile=${known_hosts}"
          # origin is checkout's https URL; only this push goes over SSH with the key. Never forced: a moved release refuses it.
          git -c url.git@github.com:.pushInsteadOf=https://github.com/ push origin "${commit}:refs/heads/release"
          echo "promoted: main ${target} -> release ${commit}"
```


### Block R6 — `local-development/release-crc.sh`: `--argocd release` deploys a pinned tag's digest as pinned (OB2 F3) (review of #614)

<!-- block: local-development/release-crc.sh | edit -->

```bash
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
```

```bash
    fi
    # promote.yml writes this file: image.* two spaces deep, reporting.image.* four.
    refs=("$(printf '%s\n' "$promoted" | sed -n 's/^  repository: //p' | head -1)@$(printf '%s\n' "$promoted" | sed -n 's/^  digest: //p' | head -1)|${pinned}"
          "$(printf '%s\n' "$promoted" | sed -n 's/^    repository: //p' | head -1)@$(printf '%s\n' "$promoted" | sed -n 's/^    digest: //p' | head -1)|${report_pinned}")
  fi
  for spec in "${refs[@]}"; do
    ref="${spec%%|*}" this_pin="${spec#*|}"
    if [ -n "$this_pin" ]; then
      # promote.yml pinned the digest of that tag without a label check (SPEC_P1 note 8); deploy it as pinned.
      if [ -n "$promoted" ]; then
        echo "image   : ${ref} (pinned in values.yaml as ${this_pin}; not checked against appVersion)"
      else
        echo "image   : ${ref%:*}:${this_pin} (pinned in values.yaml; not checked against appVersion)"
      fi
      continue
    fi
```


### Block R7 — `local-development/tests/test_promote.py` (1 of 8): the docstring: the push step is run too (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
"""promote.yml: the `release` branch holds only what was read back from the registry (#598, SPEC_P1).

The promotion step is RUN, as GitHub runs `shell: bash`, in a real git repository with a bare `origin`, against
test_supply_chain.py's stub skopeo and a stub cosign. Real git writes the `release` commit; only the registry and
Sigstore are replaced. The workflow's shape (its triggers, its scopes, its one writer) is read from the YAML.
"""

```

```python
"""promote.yml: the `release` branch holds only what was read back from the registry (#598, SPEC_P1).

The promotion step and the push step are RUN, as GitHub runs `shell: bash`, in a real git repository with a bare
`origin`, against test_supply_chain.py's stub skopeo and a stub cosign. Real git writes and pushes the `release`
commit; only the registry and Sigstore are replaced. The workflow's shape (its triggers, its scopes, its one writer)
is read from the YAML.
"""

```


### Block R8 — `local-development/tests/test_promote.py` (2 of 8): the imports (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
import re
import shlex
import subprocess

```

```python
import re
import shlex
import shutil
import subprocess

```


### Block R9 — `local-development/tests/test_promote.py` (3 of 8): the README path and the push step's name (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"
PUBLISHER = REPO / "local-development" / "build-and-push-external.sh"
STEP = "Read both images back and promote"
IDENTITY = "https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main"

```

```python
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"
PUBLISHER = REPO / "local-development" / "build-and-push-external.sh"
GITOPS_README = REPO / "gitops" / "README.md"
STEP = "Read both images back and promote"
PUSH_STEP = "Push release"
IDENTITY = "https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main"

```


### Block R10 — `local-development/tests/test_promote.py` (4 of 8): the fixture extracts the push step (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
        (bindir / tool).chmod(0o755)
    (tmp_path / "step.sh").write_text(_step(_jobs(PROMOTE)["promote"], STEP)["run"])
    return {"repo": repo, "origin": origin, "tmp": tmp_path, "bin": bindir, "start": start}


def promote(lab, registry: dict, *, event: str = "dispatch", run_sha: str = "", sha: str = "", rollback: bool = False,
            signing: str = "", unsigned: str = "", mirror_immutable: bool = True) -> tuple[subprocess.CompletedProcess, str]:
    state, log = lab["tmp"] / "registry.json", lab["tmp"] / "calls.log"
    # publish.yml always writes <appVersion>-<10-char sha>. Most tests start from the release aliases, so mirror
```

```python
        (bindir / tool).chmod(0o755)
    (tmp_path / "step.sh").write_text(_step(_jobs(PROMOTE)["promote"], STEP)["run"])
    (tmp_path / "push.sh").write_text(_step(_jobs(PROMOTE)["promote"], PUSH_STEP)["run"])
    return {"repo": repo, "origin": origin, "tmp": tmp_path, "bin": bindir, "start": start}


def promote(lab, registry: dict, *, event: str = "dispatch", run_sha: str = "", sha: str = "", rollback: bool = False,
            signing: str = "", unsigned: str = "", mirror_immutable: bool = True, unreachable: str = "",
            extra_path: str = "") -> tuple[subprocess.CompletedProcess, str]:
    state, log = lab["tmp"] / "registry.json", lab["tmp"] / "calls.log"
    # publish.yml always writes <appVersion>-<10-char sha>. Most tests start from the release aliases, so mirror
```


### Block R11 — `local-development/tests/test_promote.py` (5 of 8): the harness runs the push step after a green promotion, with an outage and a PATH shim when asked (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
    state.write_text(json.dumps(registry))
    log.write_text("")
    env = {**os.environ, "PATH": f"{lab['bin']}:{os.environ['PATH']}", "STUB_REGISTRY": str(state), "STUB_LOG": str(log),
           "STUB_UNREACHABLE": "", "STUB_UNSIGNED": unsigned, "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example",
           "SIGNING": signing, "EVENT": event, "RUN_SHA": run_sha, "SHA": sha, "ROLLBACK": "true" if rollback else "false",
           "IDENTITY": IDENTITY, "ISSUER": "https://token.actions.githubusercontent.com"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "step.sh")],
                          cwd=lab["repo"], env=env, capture_output=True, text=True)
    return done, log.read_text()

```

```python
    state.write_text(json.dumps(registry))
    log.write_text("")
    path = f"{extra_path}:" if extra_path else ""
    env = {**os.environ, "PATH": f"{path}{lab['bin']}:{os.environ['PATH']}", "STUB_REGISTRY": str(state), "STUB_LOG": str(log),
           "STUB_UNREACHABLE": unreachable, "STUB_UNSIGNED": unsigned, "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example",
           "SIGNING": signing, "EVENT": event, "RUN_SHA": run_sha, "SHA": sha, "ROLLBACK": "true" if rollback else "false",
           "IDENTITY": IDENTITY, "ISSUER": "https://token.actions.githubusercontent.com"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "step.sh")],
                          cwd=lab["repo"], env=env, capture_output=True, text=True)
    if done.returncode == 0:   # Actions runs "Push release" only after the step above succeeded
        pushed = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "push.sh")],
                                cwd=lab["repo"], env={**env, "RELEASE_DEPLOY_KEY": "test-only"},
                                capture_output=True, text=True)
        done = subprocess.CompletedProcess(done.args, pushed.returncode, done.stdout + pushed.stdout,
                                           done.stderr + pushed.stderr)
    return done, log.read_text()

```


### Block R12 — `local-development/tests/test_promote.py` (6 of 8): the orders the reviews tried, as permanent tests (OB2) (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python


# ── The workflow's shape ──────────────────────────────────────────────────────────────────────

```

```python


def _mirror(lab, registry: dict, target: str) -> str:
    image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", target, "--", "local-development/README.md")
    for image in (DASHBOARD, REPORT):
        registry["tags"][f"{image}:{APP}-{image_commit[:10]}"] = registry["tags"][f"{image}:{APP}"]
    return image_commit


def test_a_chart_push_during_a_registry_outage_is_red_not_a_green_notice(lab) -> None:
    """Review of #614 (OB2 F2): a chart-only merge has no publish run coming, so unreachable must not read as absent."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    assert promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)[0].returncode == 0
    promoted = release(lab)
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", chart_only, "--", "local-development/README.md")
    for ref in (f"{DASHBOARD}:{APP}-{image_commit[:10]}", f"{DASHBOARD}:{APP}"):
        done, _ = promote(lab, registry, event="push", unreachable=ref, mirror_immutable=False)
        assert done.returncode == 1, f"{ref}: a registry outage was reported as a green notice:\n{done.stdout}{done.stderr}"
        assert "cannot read" in done.stdout and "no such host" in done.stdout, done.stdout
        assert "Nothing was promoted by this run" not in done.stdout
        assert release(lab) == promoted
    registry["tags"].pop(f"{DASHBOARD}:{APP}-{image_commit[:10]}")   # genuinely absent: still the notice
    done, _ = promote(lab, registry, event="push", mirror_immutable=False)
    assert done.returncode == 0 and "is not ready" in done.stdout, done.stdout + done.stderr


def test_a_release_that_moved_after_the_fetch_refuses_the_push(lab) -> None:
    """Review of #614 (OB2): the push is a plain fast-forward; a hand commit that landed meanwhile stands."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    real_git = shutil.which("git")
    stranger = _git(lab["repo"], "commit-tree", _git(lab["repo"], "hash-object", "-t", "tree", "-w", "/dev/null"),
                    "-p", lab["start"], "-m", "a hand commit on release")
    _git(lab["repo"], "push", "-q", "origin", f"{stranger}:refs/heads/by-hand")   # the object reaches origin
    shim = lab["tmp"] / "shim"
    shim.mkdir()
    (shim / "git").write_text(f"""#!/usr/bin/env bash
for arg in "$@"; do
  if [ "$arg" = push ]; then {real_git} --git-dir="{lab['origin']}" update-ref refs/heads/release {stranger}; break; fi
done
exec {real_git} "$@"
""")
    (shim / "git").chmod(0o755)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False, extra_path=str(shim))
    assert done.returncode != 0, done.stdout + done.stderr
    assert "rejected" in done.stderr or "failed to update ref" in done.stderr, done.stderr
    assert release(lab) == stranger, "the hand commit stands; nothing was forced over it"


def test_a_dispatch_rebuild_at_a_commit_that_changed_no_image_input_promotes_nothing(lab) -> None:
    """Review of #614 (OB2): publish.yml run by hand at such a tip tags that tip's sha; promote needs the
    image-input commit's own tag (docs/RELEASING.md, its troubleshooting row)."""
    image = _main_at(lab, APP)
    tip = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    registry = _released()
    for name in (DASHBOARD, REPORT):   # the rebuild's tag, and no tag for the image-input commit
        registry["tags"][f"{name}:{APP}-{tip[:10]}"] = registry["tags"][f"{name}:{APP}"]
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)
    assert done.returncode == 0 and "is not ready" in done.stdout, done.stdout + done.stderr
    assert release(lab) == lab["start"] and image != tip


def test_a_green_publish_that_pushed_nothing_is_a_red_promotion(lab) -> None:
    """Review of #614 (OB2): publish.yml is green with REGISTRY_* unset; its completion reaches the strict path."""
    tip = _main_at(lab, APP)
    done, _ = promote(lab, {"tags": {}, "manifests": {}, "blobs": {}}, event="workflow_run", run_sha=tip,
                      mirror_immutable=False)
    assert done.returncode == 1 and "cannot read" in done.stdout, done.stdout + done.stderr
    assert release(lab) == lab["start"]


def test_an_identical_chart_at_a_new_target_writes_a_new_release_commit(lab) -> None:
    """Review of #614 (OB2): promotion.yaml's first line names the target, so "nothing to promote" holds only for the
    same commit; the new commit changes that one line."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    assert promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)[0].returncode == 0
    first = release(lab)
    workflow = _commit(lab["repo"], "promote.yml itself", {".github/workflows/promote.yml": "name: promote\n"})
    done, _ = promote(lab, registry, event="push", mirror_immutable=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert release(lab) != first and _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {workflow}"
    assert _git(lab["origin"], "diff", "--stat", first, "release").strip().endswith("1 file changed, 1 insertion(+), 1 deletion(-)")


# ── The workflow's shape ──────────────────────────────────────────────────────────────────────

```


### Block R13 — `local-development/tests/test_promote.py` (7 of 8): checkout's inputs; only the push step holds the key; the pinned host key; only the push goes over SSH (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python
    assert job["environment"] == "release"
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"]["ssh-key"] == "${{ secrets.RELEASE_DEPLOY_KEY }}"


```

```python
    assert job["environment"] == "release"
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"] == {"ref": "main", "fetch-depth": 0, "persist-credentials": False}


def test_the_deploy_key_is_loaded_only_by_the_push_step(tmp_path) -> None:
    """Review of #614 (Codex F1): the key bypasses the release ruleset, so no other step may hold it."""
    job = _workflow()["jobs"]["promote"]
    push = _step(job, PUSH_STEP)
    assert job["steps"][-1] is push
    assert push["env"] == {"RELEASE_DEPLOY_KEY": "${{ secrets.RELEASE_DEPLOY_KEY }}"}
    assert [s.get("name") or s.get("uses") for s in job["steps"] if "RELEASE_DEPLOY_KEY" in str(s.get("with", "")) + str(s.get("env", ""))] == [
        "Check the release deploy key is configured", PUSH_STEP]   # the first only asks whether it is set
    assert "git push" not in _step(job, STEP)["run"]
    run = push["run"]
    assert run.startswith("set +x\n") and "-o StrictHostKeyChecking=yes" in run and "--force" not in run and "+${commit}" not in run
    # GitHub's published Ed25519 host key (SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU)
    assert "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" in run
    # only the push goes over SSH: checkout's https origin keeps its fetch URL
    option = re.search(r"git -c (url\.\S+) push origin", run).group(1)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", "https://github.com/ephico2real2/group-sync-dashboard"], check=True)
    url = lambda *args: subprocess.run(["git", "-C", str(tmp_path), "-c", option, "remote", "get-url", *args, "origin"],  # noqa: E731
                                       capture_output=True, text=True, check=True).stdout.strip()
    assert url("--push") == "git@github.com:ephico2real2/group-sync-dashboard"
    assert url() == "https://github.com/ephico2real2/group-sync-dashboard"


```


### Block R14 — `local-development/tests/test_promote.py` (8 of 8): the gitops README row (Block 13; OB2 F1, Codex F2) (review of #614)

<!-- block: local-development/tests/test_promote.py | edit -->

```python


def test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes() -> None:
    """The operator, 2026-10-04: "main by default; release optional". `--argocd release` is the opt-in."""
```

```python


def test_the_gitops_readme_names_the_dashboard_application_main_by_default_and_the_opt_in() -> None:
    """SPEC_P1 Block 13 (review of #614: OB2 F1, Codex F2, the row the first commit left out)."""
    rows = [line for line in GITOPS_README.read_text().splitlines() if line.startswith("| `argocd-application-dashboard.yaml`")]
    assert len(rows) == 1, "gitops/README.md has no row for the dashboard Application (SPEC_P1 Block 13)"
    assert "`main`" in rows[0] and "--argocd release" in rows[0] and "promotion.yaml" in rows[0] and "--argocd main" in rows[0]


def test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes() -> None:
    """The operator, 2026-10-04: "main by default; release optional". `--argocd release` is the opt-in."""
```


### Block R15 — `local-development/tests/test_release_crc.py`: the pinned-tag test for `--argocd release` (OB2 F3) (review of #614)

<!-- block: local-development/tests/test_release_crc.py | edit -->

```python


def _version() -> str:
    import re
```

```python


def test_argocd_release_deploys_a_pinned_tag_as_promote_yml_pinned_it(lab):
    """Review of #614 (OB2 F3): promote.yml pins a values.yaml tag's digest without a label check (SPEC_P1 note 8), so
    `--argocd release` must deploy that digest as pinned, and still read the unpinned report image back."""
    values = lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml"
    pinned = values.read_text().replace('\n  tag: ""\n', '\n  tag: "1.4.0"\n', 1)
    assert 'tag: "1.4.0"' in pinned
    values.write_text(pinned)
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}=0.24.0 "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}={_version()}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pinned in values.yaml" in r.stdout and DASHBOARD_DIGEST in r.stdout, r.stdout
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}" not in log
    assert f"oc image info quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST} {LINUX_IMAGES}" in log


def _version() -> str:
    import re
```


### Block R16 — `docs/RELEASING.md`: the dispatch-rebuild row; the notice row names both notices (review of #614)

<!-- block: docs/RELEASING.md | edit -->

```markdown
| promote run says `whose images publish.yml has not finished`, `immutable image … is not ready` or the version alias `does not yet name` it, and promotes nothing | main's exact image is still publishing | nothing to do: its green completion, or a later chart/environment push, promotes main. If publish is red, fix it; `release` stays on the last promotion |
| promote run says a same-version image change reached `main` | two PRs chose the same next application version, so the immutable image and `:<appVersion>` alias differ | cut the next MINOR or MAJOR and let `publish.yml` finish green; never retag by hand |
| promote run is red with `is application X, not <appVersion>` or `carries no signature from publish.yml on main` | the tag names another build, or the digest was not signed by `publish.yml` on `main`. Nothing was written to `release` | wait for `publish.yml` to finish green, then Run workflow on promote. Never edit `release` by hand |
| promote run is red with `origin has no release branch` or `RELEASE_DEPLOY_KEY is not set` | the operator's one-time steps are not done | "Promotion to the lab", steps 1 to 5 |
```

```markdown
| promote run says `whose images publish.yml has not finished`, `immutable image … is not ready` or the version alias `does not yet name` it, and promotes nothing | main's exact image is still publishing | nothing to do: its green completion, or a later chart/environment push, promotes main. If publish is red, fix it; `release` stays on the last promotion |
| promote run says a same-version image change reached `main` | two PRs chose the same next application version, so the immutable image and `:<appVersion>` alias differ | cut the next MINOR or MAJOR and let `publish.yml` finish green; never retag by hand |
| promote run says `immutable image … is not ready` after a publish run started by hand (Run workflow), and nothing promotes `main` | the image-input commit's own publish run did not push its images, and the hand run built a later commit that changed no image input: that image is tagged with the later commit's sha, while promote reads the tag of the last image-input commit | re-run the failed publish run of the image-input commit (Re-run jobs), so its own `<appVersion>-<sha10>` exists; its green completion promotes `main` |
| promote run is red with `is application X, not <appVersion>` or `carries no signature from publish.yml on main` | the tag names another build, or the digest was not signed by `publish.yml` on `main`. Nothing was written to `release` | wait for `publish.yml` to finish green, then Run workflow on promote. Never edit `release` by hand |
| promote run is red with `origin has no release branch` or `RELEASE_DEPLOY_KEY is not set` | the operator's one-time steps are not done | "Promotion to the lab", steps 1 to 5 |
```

### Block R17 — `docs/RELEASE_BRANCH_SETUP.md`: the one-time setup runbook (the operator's request, 2026-10-05)

<!-- block: docs/RELEASE_BRANCH_SETUP.md | create -->
```markdown
# The `release` branch: one-time setup, checks and upkeep

This page is for whoever sets up or looks after the `release` branch. Each step says what it does and why, then gives
two ways to do it (the GitHub web pages, and the `gh` command line) and a check. How promotion itself works is in
`docs/RELEASING.md`, "Promotion to the lab" (#598).

## In one minute

The lab runs the dashboard from a branch. Until now that branch was `main`. A merge to `main` can reach the lab a
minute before its image has been built, and the pods wait in `ErrImagePull` until the image exists.

`release` is a branch that only receives a version **after its images are proven to exist**. The workflow
`.github/workflows/promote.yml` reads both images back from the registry and writes their exact digests into
`promotion.yaml`. Then it moves `release` forward. Nothing else may write `release`.

    main  --(merge)-->  publish.yml builds the images  -->  promote.yml checks them
                                                             |
                                                             v
                          release  <--(writes chart + promotion.yaml, digests pinned)

Four GitHub settings make "nothing else may write `release`" true. They are done once:

| Step | What it creates | Why it is needed |
|---|---|---|
| 1 | a **deploy key** with write access | the one credential allowed to push to `release` |
| 2 | an **environment** `release`, holding that key as a secret | only workflows running from `main` can read the key |
| 3 | the **branch** `release`, empty | promote.yml moves an existing branch forward; it never creates one |
| 4 | a **ruleset** on `release` | blocks every push except the deploy key's, and blocks force pushes and deletion |

The repository then has three branches on purpose: `main` (the source), `gh-pages` (the Helm repository) and
`release`.

## Before you start

- You need admin rights on `ephico2real2/group-sync-dashboard`, and the `gh` command line signed in (`gh auth status`).
- Steps 1 and 2 handle a **private key**. Run them in your own terminal, delete the key files afterwards, and never
  paste the private half anywhere else.
- Do the steps in order. Step 3 must come before step 4, because the ruleset blocks creating the branch.

## Step 1: the deploy key

**What it does.** It creates an SSH key pair. GitHub keeps the public half as a "deploy key" for this one repository,
with write access. The private half becomes the secret in step 2. The promote workflow uses it to push to `release`,
and nothing else uses it.

**On the web.**
1. On your laptop, make the key pair (see the first two commands below).
2. Settings → Deploy keys → Add deploy key.
3. Title `promote-release`, paste the content of `promote-release.pub`, tick **Allow write access**, and save.

**With `gh`.**

    cd "$(mktemp -d)"
    ssh-keygen -t ed25519 -N '' -C promote-release -f promote-release
    gh repo deploy-key add promote-release.pub -R ephico2real2/group-sync-dashboard --allow-write --title promote-release

The raw API does the same:

    gh api -X POST repos/ephico2real2/group-sync-dashboard/keys -f title=promote-release -f key="$(cat promote-release.pub)" -F read_only=false

**Check.**

    gh api repos/ephico2real2/group-sync-dashboard/keys --jq '.[] | [.id, .title, .read_only] | @tsv'

You should see `promote-release` with `read_only` `false`. Keep the terminal open for step 2.

## Step 2: the `release` environment and its secret

**What it does.** A GitHub environment is a named place to keep secrets, with rules about who may read them. This one,
`release`, accepts deployments only from the `main` branch. So the key is readable only by a workflow running from
`main`, never from a pull request or another branch.

**On the web.**
1. Settings → Environments → New environment, named `release`.
2. Under **Deployment branches and tags**, choose **Selected branches and tags**, add the rule `main`, and save.
3. Under **Environment secrets** → Add secret: name `RELEASE_DEPLOY_KEY`, value the whole content of the file
   `promote-release` (the private half, not the `.pub`).

**With `gh`.**

    gh api -X PUT repos/ephico2real2/group-sync-dashboard/environments/release --input - <<'EOF'
    {"deployment_branch_policy": {"protected_branches": false, "custom_branch_policies": true}}
    EOF
    gh api -X POST repos/ephico2real2/group-sync-dashboard/environments/release/deployment-branch-policies -f name=main -f type=branch
    gh secret set RELEASE_DEPLOY_KEY --env release -R ephico2real2/group-sync-dashboard < promote-release

Use `gh secret set` for the secret rather than the raw API. The API needs the value encrypted first, and `gh` does
that for you.

**Then delete the key files:**

    rm -f promote-release promote-release.pub

**Check** (names and rules only; GitHub never shows a secret's value):

    gh api repos/ephico2real2/group-sync-dashboard/environments/release --jq '.deployment_branch_policy'
    gh api repos/ephico2real2/group-sync-dashboard/environments/release/deployment-branch-policies --jq '.branch_policies[] | [.name, .type] | @tsv'
    gh api repos/ephico2real2/group-sync-dashboard/environments/release/secrets --jq '.secrets[].name'

You should see `custom_branch_policies: true`, one rule `main` of type `branch`, and the secret `RELEASE_DEPLOY_KEY`.

## Step 3: the empty `release` branch

**What it does.** It creates the branch `release` holding one commit with no files. `promote.yml` only ever moves an
existing branch forward, so the branch must exist before the first promotion. It starts empty so that its first real
content is a promotion.

**On the web.** Not possible. The web page creates a branch as a copy of another branch, files and all. Use `git` or
`gh` below.

**With `git`.**

    c=$(git commit-tree "$(git hash-object -t tree /dev/null)" -m "release starts empty")
    git push origin "${c}:refs/heads/release"

**With `gh`** (the same, through the API). `4b825dc…` is git's fixed id for an empty tree:

    c=$(gh api -X POST repos/ephico2real2/group-sync-dashboard/git/commits -f message="release starts empty" -f tree=4b825dc642cb6eb9a060e54bf8d69288fbee4904 --jq .sha)
    gh api -X POST repos/ephico2real2/group-sync-dashboard/git/refs -f ref=refs/heads/release -f sha="${c}"

**Check.**

    git ls-remote origin refs/heads/release
    git fetch origin release && git ls-tree origin/release | wc -l

You should see one commit, and `0` files.

## Step 4: the ruleset that locks `release`

**What it does.** A ruleset is a set of branch protections. This one refuses every creation, update and deletion of
`release`, and every force push, except from a **deploy key**. So people cannot push to `release`, even with admin
rights, and the promote workflow can.

**On the web.**
1. Settings → Rules → Rulesets → New branch ruleset, named `release`.
2. Enforcement status: **Active**.
3. Target branches → Add target → Include by pattern: `release`.
4. Rules: tick **Restrict creations**, **Restrict updates**, **Restrict deletions**, **Block force pushes**.
5. Bypass list → Add bypass → **Deploy keys**, mode **Always**. Save.

**With `gh`.**

    gh api -X POST repos/ephico2real2/group-sync-dashboard/rulesets --input - <<'EOF'
    {
      "name": "release",
      "target": "branch",
      "enforcement": "active",
      "conditions": {"ref_name": {"include": ["refs/heads/release"], "exclude": []}},
      "rules": [{"type": "creation"}, {"type": "update"}, {"type": "deletion"}, {"type": "non_fast_forward"}],
      "bypass_actors": [{"actor_id": null, "actor_type": "DeployKey", "bypass_mode": "always"}]
    }
    EOF

**Check.**

    gh api repos/ephico2real2/group-sync-dashboard/rulesets --jq '.[] | [.id, .name, .enforcement] | @tsv'

You should see `release`, `active`.

**Prove it holds.** Push a throwaway commit on top of `release` with your own credentials. It must be refused:

    c=$(git commit-tree "$(git hash-object -t tree /dev/null)" -p origin/release -m "probe: a hand push must be refused")
    git push origin "${c}:refs/heads/release"

GitHub answers `GH013: Repository rule violations … Cannot update this protected ref`, and `release` does not move.

## After the setup

**Step 5: the first promotion.** It runs on its own once the change that adds `promote.yml` (#614) is merged and its
`publish.yml` run is green. At any other time: Actions → promote → Run workflow on `main`, with no inputs. Then:

    git fetch origin release
    git log -1 --format=%s origin/release          # promote: main <sha>
    git ls-tree --name-only origin/release         # charts, environments, promotion.yaml

**Step 6: point the lab at `release` (optional).** During development the lab follows `main`. To use `release`, and
to switch back:

    local-development/release-crc.sh --argocd release
    local-development/release-crc.sh --argocd main

Each epic's post-release walk runs on `release`, then switches back.

## The record of this setup (2026-10-05, UTC)

| Step | Done by | Result |
|---|---|---|
| 1 | the operator | deploy key `promote-release`, `read_only=false`, created 00:54:42Z |
| 2 | the operator | environment `release`, one branch rule `main`; secret `RELEASE_DEPLOY_KEY` updated 00:58:04Z |
| 3 | the orchestrator | branch `release` at `1f3c3303f62d`, "release starts empty", 0 files |
| 4 | the orchestrator | ruleset `24475607` `release`, active, bypass `DeployKey`; GitHub accepted the deploy-key bypass on this user-owned repository, which settles SPEC_P1's open question 1 |
| proof | the orchestrator | a hand push was refused with `GH013 … Cannot update this protected ref`; `release` stayed at `1f3c3303f62d` |

Which commands were run against the repository on that day:
- **For real:** the ruleset `POST` and the hand-push proof (step 4), and `gh secret set` (step 2).
- **As harmless probes:**
  - the deploy-key `POST` (a read-only key, added and deleted at once);
  - the environment `PUT` (its own settings sent again);
  - the branch-policy `POST` (the existing `main` rule, not duplicated);
  - the empty-commit `POST` (a commit no branch points at).
- **Not run:** the `git/refs` call in step 3. The branch was created with the `git` form instead.

## Upkeep

- **Rotate the deploy key** (yearly, or if it may have leaked):
  1. Make a new pair and add it as in step 1, with a new title such as `promote-release-2027`.
  2. Run step 2's `gh secret set` with the new private half.
  3. Delete the old key: `gh api repos/ephico2real2/group-sync-dashboard/keys` lists the ids, then
     `gh repo deploy-key delete <id> -R ephico2real2/group-sync-dashboard`.
  4. Run the promote workflow by hand, to prove the new key works.
- **A promote run says the key is missing.** The environment or its secret is gone. Repeat step 2.
- **A promote run's push is refused.** The ruleset's bypass list has lost **Deploy keys**. Check step 4.
- **Undo the whole setup.** First point the lab at `main` (`release-crc.sh --argocd main`). Then delete, in this
  order:
  1. the ruleset (`gh api -X DELETE repos/ephico2real2/group-sync-dashboard/rulesets/<id>`);
  2. the branch;
  3. the environment;
  4. the deploy key.

## Words used on this page

- **Deploy key.** An SSH key that GitHub ties to one repository, not to a person.
- **Environment.** A GitHub setting that holds secrets and limits which branches' workflows may read them.
- **Ruleset.** A set of branch protections. Its **bypass list** names who may break them; here, only deploy keys.
- **Force push.** A push that rewrites a branch's history. It is blocked on `release`.
- **Digest.** The fixed fingerprint of an image (`sha256:…`). Unlike a tag, it can never point at a different
  image.
```

### Block R18 — `docs/RELEASING.md`: point the one-time steps at the runbook

<!-- block: docs/RELEASING.md | edit -->
```markdown
**The operator's one-time steps** (in this order, before the first promotion):
```

```markdown
**The operator's one-time steps** (in this order, before the first promotion). The runbook with each command, its
check, the record of the setup on 2026-10-05, key rotation and undoing it is `docs/RELEASE_BRANCH_SETUP.md`:
```

### Block R19 — `docs/README.md`: link the runbook in the docs index

`tests/test_docs_index.py` requires every page in `docs/` to be linked from `docs/README.md`. Found by CI on `c87dd349`.

<!-- block: docs/README.md | edit -->
```markdown
- [RELEASING.md](RELEASING.md) — application and chart release procedures and version ownership.
```

```markdown
- [RELEASING.md](RELEASING.md) — application and chart release procedures and version ownership.
- [RELEASE_BRANCH_SETUP.md](RELEASE_BRANCH_SETUP.md) — the `release` branch's one-time GitHub setup (deploy key, environment, branch, ruleset), its checks and upkeep.
```
