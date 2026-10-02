# SPEC E9 — `:latest` follows the newest signed `main` build: a job after `attest` copies both digests by digest, and reads them back (#425)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 8 of 9, the release-safety child that moves `:latest`. Independent of every other child; SPEC_E8 (#410, PR A, on its own branch) edits the same test file and three of the same documents, and §4.4 shows the two compose in either order |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | app 2.4.0, chart 0.61.2 |
| Version note | `publish.yml` lists itself in its own `on.push.paths` (`.github/workflows/publish.yml#this file`), so this change is an image input and takes an application MINOR (`docs/RELEASING.md#Neither`); it changes no chart template or value, and the chart moves only because `appVersion` does. Every `specified` row on origin/main `3acfda37` that claims an application version claims 2.1.0 (SPEC_G2, SPEC_E4, SPEC_E3, SPEC_E6) or 2.2.0 (SPEC_G3); SPEC_E7 and SPEC_E8 claim none, so the next free MINOR is 2.3.0. The CI gate holds the number to exactly the next MINOR of the pull request's base (`local-development/check-app-version-bump.py#check`; measured in §4.3: from `6d532178` with §7 applied it refuses 2.3.0, `expected exactly 2.1.0 (next MINOR) or 3.0.0 (next MAJOR), got 2.3.0`, and accepts 2.1.0), so the implementing pull request takes main's next MINOR when it is opened and, by SPEC_E5's rule (its Version note), moves every other `specified` row whose application version is no longer above `pyproject.toml` to the next MINOR above it, keeping each row's chart cell: if this spec merges first at 2.1.0, SPEC_G2, SPEC_E4, SPEC_E3 and SPEC_E6 move from app 2.1.0 to 2.2.0 in header and row, and SPEC_G3 (2.2.0) stays above and is left alone; if one of them merges first, its pull request moves this spec's cell instead. No block carries a version field: the implementing pull request applies §7, commits, then runs `prepare-release.py --app <main's next MINOR> --no-commit "…"`, as SPEC_E4 and SPEC_E3 do |
| Issue | [#425](https://github.com/ephico2real2/group-sync-dashboard/issues/425) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue (its "What must be accomplished", Test cases and "Decisions and corrections (2026-10-01)") and the epic's "Decisions settled (2026-10-01)". Measured on origin/main `6d532178` (application 2.0.0, chart 0.59.25) with the repository's Python 3.14 venv, helm v4.3.0, shellcheck and actionlint v1.7.12 (built from source into the scratch directory); read-only on quay.io (its public tag API, the registry's referrers endpoint and `oc image info`) and on the CRC lab (`oc get`); the last publish run, 36690887346, read with `gh run view --log`. §7's blocks were cut from a copy of `6d532178` with the design implemented and proved against a clean worktree of `6d532178` (§4.3). Before the commit origin/main moved to `eade4c2a` (SPEC_E6, #513), which changes only `docs/specs/` and the index test; the branch was fast-forwarded to it, the index row placed after E6's, and the blocks re-checked there |

## How to read this spec

**The point in one sentence: a fourth job in `publish.yml`, `latest`, runs after `attest` has signed both images and
read the signatures back, and copies each digest the `publish` job recorded to that image's `:latest` with the same
`skopeo copy --all --preserve-digests` the release aliases use, then reads `:latest` back and fails the run if it
names anything else; it runs on `main` only, and when signing is switched off it follows `publish` alone.**

Today `:latest` does not exist for either image on quay.io, and nothing in this repository resolves it: the chart
deploys `:<appVersion>`. The operator asked for it to follow the newest `<appVersion>-<sha10>` (2026-09-27). The
design is one job of about thirty lines of shell, eight tests that run the job's real text, and the documents that
list the tags.

§1 is the mandate. §2 is the research: each finding names its primary source with the exact sentence relied on, or
the command that measured it with its output. §2a weighs the alternatives and reconciles each external claim with the
line of this repository that relies on it. §3 is the design, one rule per subsection, with the budget of the one thing
it writes, a tag (§3.5). §4 maps every test case of the issue (T425-1 to T425-8) to a test, with each failing on a
tree without the change. §5 is the walk. §6 is what an operator sees and what it costs. §7 is the whole change as
implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E9_latest_tag.md . --apply

Citations into the repository use `path#anchor`; a line number, where one helps, is written as plain text against
`6d532178`, without backticks. Upstream sources are named with their URL and the commit or tag they were read at;
their line numbers come from `curl -s <raw-url> | nl -ba`.

## Orchestrator's notes

1. **The issue's decisions are followed as written** (Decisions and corrections, 2026-10-01): `:latest` moves in a
   job of its own after `attest` (decision 1), on `main` only (decision 2), with the release aliases' copy and
   read-back and no new helper (decision 3). Research confirms each (§2a, A1 to A3).
2. **A correction to the issue's budget: a re-run moves `:latest` backwards.** The issue says runs "are serialized by
   `concurrency: publish-main` … so two runs never race on `:latest`". That holds for runs that overlap (§2.7). It does
   not cover a re-run: GitHub re-runs a job with "the same `GITHUB_SHA` (commit SHA) and `GITHUB_REF` (git ref) of
   the original event" (§2.8), up to 30 days later, so re-running an older run's `latest` job after a newer run has
   moved the tag points `:latest` back at the older build. Prometheus guards its `latest` against exactly this with a
   monotonic check (§2.14). **Decided on "easy to manage, best practice": not guarded, stated, with a one-click
   remedy.** Nothing resolves `:latest` for a deployment (§2.15), so a backward move changes no cluster; re-running
   the `latest` job of the newest green run puts it right; and the guard would add a registry config read, a GitHub
   API comparison and a fourth outcome ("diverged" after a force-push) to a thirty-line job (§2a, A7). The budget
   (§3.5), `DESIGN_supply_chain.md` D11 and the RELEASING table (blocks 6 and 11) say so. **For the operator, only if
   you disagree:** the guard is A7, about fifteen lines.
3. **A second, smaller correction: the two copies are two writes.** If the second copy or read-back fails, the
   dashboard's `:latest` has moved and the report's has not, until the job is re-run. The run is red and its
   `::error::` names the image, for a refused copy as for a read-back mismatch (T425-2 holds that the step stops at
   the first failure; `test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy` holds the annotation). Ordering the copies cannot
   remove this window, because the registry has no transaction across two repositories (§2.11); it is stated in the
   budget.
4. **The version.** See the Version note above: 2.3.0 is the next free MINOR on the index today; the CI gate makes
   the implemented number main's next MINOR at the time, and the implementing pull request reconciles the index by
   SPEC_E5's rule. No chart template or value changes; the chart's version moves only with `appVersion`, through
   `prepare-release.py`.
5. **The issue-specific live checks** (Definition of Done, last item). "A `workflow_dispatch` from a branch other
   than `main` does not move `:latest`" is run by the implementing pull request from its own branch before the merge
   (§5, step 2); it pushes that branch's immutable tags unsigned, which is what such a dispatch already does (D9).
   "A run with `SUPPLY_CHAIN_SIGNING=false` moves it after the publish job" needs the repository variable set for
   one run; that is the operator's setting to change, so §5 gives it as an optional step, and T425-3's truth table is
   the hermetic proof of the same rule.
6. **The runner moves to Ubuntu 26.04 while this is in flight.** `ubuntu-latest` migrates "between October 19 and
   November 19, 2026" (§2.10). Both images carry a skopeo with the two flags (1.13.3 and 1.21.0-dev; the flags exist
   since 1.6.0), so the job keeps `runs-on: ubuntu-latest` like the three it follows, and prints `skopeo --version`
   first, as the `publish` job's preflight does.
7. **The index.** This spec's row follows SPEC_E8's in `docs/specs/README.md` (origin/main `3acfda37`, where E7 and
   E8 are rows 44 and 45), and `local-development/tests/test_specs_index.py`'s count moves from 45 to 46 ("Forty-six
   specifications are indexed below", "## The forty-six specifications"). Like E2, G2, E4, G3, E5, E3, E6, E7 and E8, E9 is
   excluded from the rising issue numbers by its id and pinned to its issue, `assert ROWS["E9"]["issue"] == "425"`.
   Measured on this branch: with the pin, E9 mistyped as #525 in its row and header fails `AssertionError: ('E9 is
   #425', '525')`; with the pin removed, the same mutant passes every index test (§4.3).
8. **Composition with SPEC_E8** (#410, PR A, merged on origin/main `3acfda37` as #515; 18 blocks). Whichever applies second commits the first spec's blocks before applying its own: `apply-spec-blocks.py` refuses a dirty tree. Both specs add a class at the
   end of `local-development/tests/test_supply_chain.py`, both edit `docs/RELEASING.md`, `docs/DESIGN_supply_chain.md`
   and `docs/CHANGELOG.md`. Their Old texts do not overlap, and the one shared anchor (the file's last line, which
   E8's block 7 edits and this spec's block 3 inserts after) occurs once before and after either is applied. This
   spec's tests define no module-level name and add no import, so E8's import edit (its block 5) and its module
   constants (`SKOPEO_STUB`, `DASHBOARD`, `REPORT`, `APP`, `CHART`) cannot collide with it. Both orders were applied
   to copies of this branch and the whole of `test_supply_chain.py` and `test_docs_citations.py` passes in each
   (§4.4). SPEC_E6 (on main, not yet implemented) shares only `docs/CHANGELOG.md` with this spec, and both insert
   under `## Unreleased` the same way, so either order applies. Whichever merges second re-runs its own `apply-spec-blocks.py` check before applying; no block needs
   to change.
9. **The review of `24084b06` (OB2, in Codex's seat), decided by the orchestrator on 2026-10-01: the patch accepted
   whole.** Each item was found by OB2 and re-measured here on origin/main `3acfda37` (§4.3, §4.4).
   - **Accepted, Block 2:** both digests are checked before either copy, so a malformed second digest no longer leaves
     the dashboard's `:latest` moved alone; a copy the registry refuses is a red run whose `::error::` names the image
     and the remedy (re-run the job), where `set -e` had ended the step with skopeo's message only (§3.3 steps 1 and
     2b, note 3, §6).
   - **Accepted, Block 3:** the refused-copy test, the digest test over both digests, and two truth-table rows
     ("signing switched off, but a dispatch from another branch" and "… but a red publish") that hold the parentheses
     around the `attest` clause by evaluation, not only by the clause-string check.
   - **Accepted, Block 11 and the prose:** the RELEASING row for a refused copy, §4.1, §4.3 (re-measured, not copied),
     §4.4 and note 8 (SPEC_E8 merged as #515 with 18 blocks, a commit between the two applies), note 7 and the Version
     note (where the colliding app-2.1.0 rows move under SPEC_E5's rule, read from main's index).
   - **Kept rejected:** A7, the guard against a re-run moving `:latest` backwards; OB2 confirmed the decision on the
     evidence (nothing resolves `:latest`; one re-run of the newest green run's job puts it right).
   - **Rebased:** origin/main `3acfda37` merged into this branch; E9 is index row 46 (note 7).
10. **Corrected for implementation on origin/main `ffe9de32` (2026-10-02): app 2.4.0, chart 0.61.2.** Main is
    application 2.3.0 and chart 0.61.1 (`local-development/pyproject.toml`, `Chart.yaml`), so
    `check-app-version-bump.py` accepts only 2.4.0, not the header's 2.6.0, and `prepare-release.py --app 2.4.0
    --no-commit` derives chart 0.61.2 (measured on a throwaway copy of `ffe9de32`: `version: 0.61.2`; its `schema  :`
    line reads `20 at c57f292707 (application 2.3.0), 20 at HEAD; no schema line`). The header and the index row say so,
    and the spec moves to `merged`. Block 12's lead names `app 2.4.0, chart 0.61.2`, because
    `local-development/tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`
    fails when no Unreleased entry names the chart version `Chart.yaml` reaches. Under SPEC_E5's rule the tree now reaches
    two `specified` rows of `docs/specs/README.md` on `ffe9de32`: SPEC_G2's app 2.4.0 moves to 2.6.0 (2.5.0 is SPEC_G3's;
    its chart 0.63.0 kept), and SPEC_G4's step 1, chart 0.61.2, moves to 0.61.4 (0.61.3 is SPEC_G3's) with its step 2
    to 0.61.5, so step 2 stays above step 1. SPEC_G3 (app 2.5.0, chart 0.61.3) and SPEC_W1 (chart 0.62.0) are above
    the new tree and stay. Note 7's index count was already applied on main (forty-eight rows); no block changes for it.
11. **The review of PR #530 (OB2, in Codex's seat, head `b06ee631`), decided by the orchestrator on 2026-10-02:
    approved, every claim confirmed, and its recommended F1 accepted.** F1: a read-back that cannot be made (the
    registry stops answering after the copy) ended the step under `set -e` with skopeo's stderr and no `::error::`,
    with the tag already moved. Measured by OB2 with a stub whose `inspect` of one name exits 1: exit 1, `copies
    made: 1` (first image) and `2` (second), `'::error::' lines: 0` in both. Block 2 now wraps the read-back in
    `if ! moved=$(…); then` with an `::error::` naming the image, the digest it was copied from and the re-run (§3.3
    step 3b); Block 3 adds the stub switch `STUB_UNREADABLE` and
    `test_a_read_back_that_cannot_be_made_is_a_red_run_naming_the_image_and_the_remedy` (§4.1); Block 11's row names
    the third cause. Re-measured on this branch: the new test against `b06ee631`'s `publish.yml` `1 failed`
    (`AssertionError`, no `::error::` in the output), with the fix `1 passed`. Observations recorded, no change asked:
    podman-remote on the review Mac writes no `--digestfile` (irrelevant to CI, which runs podman natively); the E8
    race between `helm.yaml`'s label step and `publish`'s aliases is real but bounded by `ci.yml`'s run time and is
    E8's documented red-and-re-run path, not this spec's.

## 1. The mandate, and what is out of scope

**In** (the issue's "What must be accomplished", items 1 to 5):

1. On every successful publish from `main`, `:latest` moves for both images, `group-sync-dashboard` and
   `group-sync-dashboard-report`, to the digest that run pushed as `<appVersion>-<sha10>`, by a server-side
   `skopeo copy --all --preserve-digests` (T425-1, T425-4).
2. The move is read back; a `:latest` that does not resolve to that digest is a red run (T425-2).
3. `:latest` only ever names a signed `main` build: `refs/heads/main` only, after a green `publish`, and after
   `attest` has signed the digest and read it back while signing is on (T425-3, T425-8).
4. Unchanged: the immutable `<appVersion>-<sha10>` tags, the `:<appVersion>` alias rule, the `publish` job's
   `contents: read`, and the chart, which never resolves `:latest` (T425-5, T425-6, T425-7).
5. True on quay after the merge: both `:latest` digests equal the merge's `<appVersion>-<sha10>` digests, and
   `cosign verify` of `:latest` passes with the install guide's identity (T425-8).

**Out:**

- Any change to the chart, its values or what a cluster runs. The lab keeps `:<appVersion>` (§5).
- `:latest` for a build pushed by hand. The disaster-recovery scripts sign nothing, so they leave `:latest` where the
  last green run put it; the build script's header says so (block 5).
- Deleting or retagging any existing tag. `:latest` is new on both repositories (§2.13); nothing else is touched.
- A guard against a re-run moving `:latest` backwards (Orchestrator's notes, 2).
- Signing `:latest` itself. A signature is over a digest (§2.12), and `:latest` is copied from a digest that is
  already signed, so there is nothing more to sign.

## 2. Research, measured

Fetched 2026-10-01. GitHub's documentation is read from its source repository, `github/docs` at `56fcfa81`
(`https://raw.githubusercontent.com/github/docs/56fcfa816f27bca239e5d39fff0d4f74f77ec995/<path>`), because the
rendered pages inline those files.

### 2.1 A skipped job in `needs` skips its dependants unless a status function is named

`data/reusables/actions/jobs/section-using-jobs-in-a-workflow-needs.md` line 1: *"If a job fails or is skipped, all
jobs that need it are skipped unless the jobs use a conditional expression that causes the job to continue."*
`content/actions/reference/workflows-and-actions/expressions.md` line 322: *"A default status check of `success()` is
applied unless you include one of these functions."* Line 344 recommends the form this spec uses: *"If you want to run
a job or step regardless of its success or failure, use the recommended alternative: `if: ${{ !cancelled() }}`"*.

**Settles:** `attest` is skipped when `SUPPLY_CHAIN_SIGNING` is `false`
(`.github/workflows/publish.yml#vars.SUPPLY_CHAIN_SIGNING != 'false'`), so a job that needs it must name
`!cancelled()` or it would never run with signing off. `attest` already does the same for `sbom`
(`.github/workflows/publish.yml#THE SBOM IS A DEPENDENCY, NOT A REQUIREMENT`). With `!cancelled()`, every other
requirement must be written out, which is why the condition names `needs.publish.result` and `needs.attest.result`.

### 2.2 What a job-level `if` can read, and what `needs.<job>.result` holds

`content/actions/reference/workflows-and-actions/contexts.md` line 100, the context-availability table:
*"`jobs.<job_id>.if` | `github, needs, vars, inputs` | `always, cancelled, success, failure`"*. Line 779:
*"`needs.<job_id>.result` | `string` | The result of a job that the current job depends on. Possible values are
`success`, `failure`, `cancelled`, or `skipped`."*

**Settles:** the condition may read `github.ref`, `needs.*` and `vars.*`, and not `matrix` (the existing
`test_the_job_level_conditions_do_not_read_the_matrix` holds the same for `sbom` and `attest`). `attest` is a two-leg
matrix with one result for the job (`DESIGN_supply_chain.md` D10), so a failed signature on either image makes
`needs.attest.result` `failure` and moves neither `:latest`.

### 2.3 `github.ref` on a `workflow_dispatch`, and how strings compare

`content/actions/reference/workflows-and-actions/events-that-trigger-workflows.md` line 1074, the
`workflow_dispatch` row: `GITHUB_SHA` is *"Last commit on the `GITHUB_REF` branch or tag"* and `GITHUB_REF` is
*"Branch or tag that received dispatch"*. `data/reusables/actions/ref-description.md`: *"for branches the format is
`refs/heads/<branch_name>`"*. `expressions.md` line 84: *"GitHub ignores case when comparing strings."*
`contexts.md`, the `vars` section: *"If a configuration variable has not been set, the return value of a context
referencing the variable will be an empty string."*

**Settles:** `github.ref == 'refs/heads/main'` excludes a dispatch from any other branch, as `attest`'s condition does
(`.github/workflows/publish.yml#github.ref == 'refs/heads/main'`). An unset `SUPPLY_CHAIN_SIGNING` is `''`, so
`== 'false'` is false and the job waits for `attest`; `FALSE` compares equal to `'false'`, as it already does in
`attest`'s `!= 'false'`, so the two conditions agree for every spelling (T425-3's truth table runs both).

### 2.4 A job's `permissions`

`data/reusables/actions/github-token-available-permissions.md` line 24: *"If you specify the access for any of these
permissions, all of those that are not specified are set to `none`."*

**Settles:** `permissions: {contents: read}` gives the `latest` job's token read on contents and nothing else. The
registry write is the robot credential's (`REGISTRY_USERNAME` / `REGISTRY_PASSWORD`), which the `publish` and
`attest` jobs already use; the `GITHUB_TOKEN` is not used at all.

### 2.5 The job reads `secrets` in a step `env`, as the other jobs do

`publish.yml` already passes the registry secrets into three steps' `env` (the build steps and `attest`'s login,
`.github/workflows/publish.yml#Log in to the registry, for the signature push`), and logs in with the password on
stdin. Nothing new is needed.

### 2.6 skopeo: the flags, and since when

`https://raw.githubusercontent.com/containers/skopeo/v1.13.3/docs/skopeo-copy.1.md`, lines 29 to 33: *"**--all**,
**-a** If _source-image_ refers to a list of images, instead of copying just the image which matches the current OS and
architecture …, attempt to copy all of the images in the list, and the list itself."* Lines 59 to 63:
*"**--preserve-digests** Preserve the digests during copying. Fail if the digest cannot be preserved. This option does
not change what will be copied; consider using `--all` at the same time."* `skopeo-inspect.1.md` at v1.13.3, lines 86
to 88: *"**--no-tags**, **-n** Do not list the available tags from the repository in the output."*
`skopeo-login.1.md` at v1.13.3, lines 24 to 26: *"**--password-stdin** Take the password from stdin"*.
`--preserve-digests` first appears in v1.6.0:

    $ for t in v1.5.2 v1.6.0 v1.6.1; do printf "%s " $t; curl -sfL https://raw.githubusercontent.com/containers/skopeo/$t/docs/skopeo-copy.1.md | grep -c "preserve-digests"; done
    v1.5.2 0
    v1.6.0 1
    v1.6.1 1

**Settles:** the release aliases' command pair works unchanged for `:latest`, with the source by digest; a copy that
would rewrite the manifest fails instead (the build script's reasoning,
`local-development/build-and-push-external.sh#preserve-digests: skopeo's default`).

### 2.7 Concurrency serializes the runs

`data/reusables/actions/actions-group-concurrency.md` line 3: *"there can be at most one running job or workflow in a
concurrency group at any time. … By default, any existing `pending` job or workflow in the same concurrency group will
be canceled and the new queued job or workflow will take its place."* `publish.yml` sets
`concurrency: publish-main` with `cancel-in-progress: false` at the workflow level
(`.github/workflows/publish.yml#group: publish-main`).

**Settles:** two runs never overlap, and the `latest` job of a run finishes before the next run starts. A pending run
replaced by a newer one never runs, so its build never becomes `:latest`; the newer one does. The order in which
`:latest` moves is the order of the commits on `main`, except for a re-run (§2.8).

### 2.8 A re-run keeps its run's commit

`content/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs.md` line 20: *"The workflow will also use the
same `GITHUB_SHA` (commit SHA) and `GITHUB_REF` (git ref) of the original event that triggered the workflow run."*
Line 4: *"You can re-run a workflow run, all failed jobs in a workflow run, or specific jobs in a workflow run up to 30
days after its initial run."*

**Settles:** the residual in Orchestrator's notes 2. A re-run of only the `latest` job reads the `publish` job's
outputs of that run, so it copies that run's digests; this was not measured (it would need a write to quay), and the
budget states the consequence either way: the re-run names that run's build.

### 2.9 The runner's skopeo, measured

`https://raw.githubusercontent.com/actions/runner-images/main/images/ubuntu/Ubuntu2404-Readme.md` (runner-images
`57b93f2c`), line 99: *"Skopeo 1.13.3"*. The last publish run used it:

    $ gh run view 36690887346 --log --job <publish> | grep -i "Image: ubuntu\|skopeo version"
    2026-09-30T08:37:49.4476306Z Image: ubuntu-24.04
    2026-09-30T08:37:56.6246812Z skopeo version 1.13.3

### 2.10 `ubuntu-latest` moves to 26.04 this autumn

runner-images `README.md` line 25: *"Ubuntu 24.04 … `ubuntu-latest` or `ubuntu-24.04`"*. `Ubuntu2604-Readme.md`
line 88: *"Skopeo 1.21.0-dev"*. GitHub's changelog of 2026-09-17,
`https://github.blog/changelog/2026-09-17-ubuntu-26-generally-available-and-latest-migration`: *"The `ubuntu-latest`
label will migrate from Ubuntu 24.04 to Ubuntu 26.04. This migration will roll out gradually between October 19 and
November 19, 2026."*

**Settles:** both images have a skopeo at or above 1.6.0, so `runs-on: ubuntu-latest` stays (Orchestrator's notes, 6).

### 2.11 The OCI distribution spec on tags

`https://raw.githubusercontent.com/opencontainers/distribution-spec/v1.1.1/spec.md` (tag `v1.1.1`, `b5c693e8`),
line 76: *"**Tag**: a custom, human-readable pointer to a manifest. A manifest digest may have zero, one, or many tags
referencing it."* Line 475: *"`<name>` is the namespace of the repository, and the `<reference>` MUST be either a) a
digest or b) a tag."* Line 480: *"The registry MUST store the manifest in the exact byte representation provided by
the client."*

**Settles:** moving `:latest` is a manifest `PUT` under the tag `latest`; with the bytes unchanged
(`--preserve-digests`) its digest is the source's. The specification defines no operation spanning two repositories,
so the two images' moves are two writes (Orchestrator's notes, 3).

### 2.12 cosign verifies a tag through its digest

cosign `v3.1.3` (`2f3a85b0`, the version `attest` pins), `pkg/oci/remote/digest.go` lines 21 to 35:
*"ResolveDigest returns the digest of the image at the reference. If the reference is by digest already, it simply
extracts the digest. Otherwise, it looks up the digest from the registry."* `pkg/cosign/verify.go` calls it before
looking up signatures (lines 670, 1039, 1098). `internal/ui/warnings.go` lines 17 to 21, cosign's own warning for
signing by tag: *"This can lead you to sign a different image than the intended one. Please use a digest
(example.com/ubuntu@sha256:abc123...) rather than tag (example.com/ubuntu:latest)"*. On quay, the signatures of the
2.0.0 digest are OCI referrers of the digest (read anonymously, read-only):

    $ curl -s -H "Authorization: Bearer <anonymous pull token>" -H "Accept: application/vnd.oci.image.index.v1+json" \
        https://quay.io/v2/ephico2real/group-sync-dashboard/referrers/sha256:fc8a5a98…
    application/vnd.dev.sigstore.bundle.v0.3+json sha256:24e02cd44498
    application/vnd.dev.sigstore.bundle.v0.3+json sha256:2d997db9d014

**Settles:** `cosign verify …:latest` resolves `:latest` to its digest and finds the signature the `attest` job wrote
for that digest, so T425-8's `cosign verify` passes exactly when T425-8's digests are equal and `attest` succeeded.
The job therefore needs no cosign of its own (§2a, A10), and it never signs by tag.

### 2.13 Quay: `:latest` is absent today, a moved tag keeps its history, and the aliases copy in seconds

Read-only, 2026-10-01:

    $ oc image info quay.io/ephico2real/group-sync-dashboard:latest
    error: image "quay.io/ephico2real/group-sync-dashboard:latest" not found: manifest unknown: manifest unknown
    $ oc image info quay.io/ephico2real/group-sync-dashboard-report:latest
    error: image "quay.io/ephico2real/group-sync-dashboard-report:latest" not found: manifest unknown: manifest unknown
    $ oc image info quay.io/ephico2real/group-sync-dashboard:2.0.0-b40b5cf82a | grep Digest
    Digest:        sha256:fc8a5a982863f5dcfcf1c2211635278e98343202f2e333a81c4d92c8fa444856
    $ oc image info quay.io/ephico2real/group-sync-dashboard-report:2.0.0-b40b5cf82a | grep Digest
    Digest:        sha256:712350d2c1b4b4a043cb7432d2a358226a7ffcf34c6d15ec9eb15b4e0fb52ce0

Quay's public tag API shows a moved tag as a closed history entry and a new one, both on the repository (the
chart-version alias `0.59.24`, moved twice on 2026-09-30):

    $ curl -s "https://quay.io/api/v1/repository/ephico2real/group-sync-dashboard/tag/?specificTag=0.59.24"
    0.59.24 sha256:fc8a5a982863 start 1790758058 end None
    0.59.24 sha256:fc8a5a982863 start 1790757522 end 1790758058

The newest tags of both repositories are single manifests (`is_manifest_list` false), and run 36690887346's log puts
the dashboard's alias copy and read-back at 3.1 s (`pushed  : …:2.0.0-b40b5cf82a` at 08:38:37.38,
`pushed  : …:2.0.0  (alias of 2.0.0-b40b5cf82a, sha256:fc8a5a98…)` at 08:38:40.51).

**Settles:** the repositories accept a moved tag (the aliases are moved this way on every release), `:latest` will be
new on both, each move adds one history entry per image, and the cost of the two moves is a few seconds.

### 2.14 How other projects move `latest`

- **docker/metadata-action** (`README.md` at `8e671d84`, lines 776 to 801): *"`latest` tag is handled through the
  `flavor` input. It will be generated by default (`auto` mode) for: `type=ref,event=tag` … `type=semver` …"*, and
  for a branch: *"For conditionally tagging with latest for a specific branch name … use `type=raw` with a boolean
  expression: `type=raw,value=latest,enable=${{ github.ref == format('refs/heads/{0}', 'master') }}`"* or
  *"`type=raw,value=latest,enable={{is_default_branch}}`"*. **Confirms** that `latest` following the default branch is
  a documented, supported choice; the action's default ties it to release tags instead.
- **Prometheus** (`prometheus/prometheus` `Makefile.common` at `fadf780d`, line 84:
  `DOCKER_IMAGE_TAG ?= $(subst /,-,$(shell git rev-parse --abbrev-ref HEAD))`, so `main` publishes `:main`;
  `prometheus/promci-images` `publish_release/action.yml` at `ae9365cc`, lines 54 to 68: *"Only push "latest" tags if
  this is the latest stable release"*). **Refutes** "`latest` is always the newest `main` build" as a universal
  convention, and shows a monotonic guard (Orchestrator's notes, 2). This repository's `:latest` is the operator's
  word for the newest `main` build (the issue, 2026-09-27), and the documents say so where the tags are listed.
- **Kubernetes** (`kubernetes/website` `content/en/docs/concepts/containers/images.md` at `7a1c866f`, lines 115 to
  119): *"You should avoid using the `:latest` tag when deploying containers in production as it is harder to track
  which version of the image is running and more difficult to roll back properly."* **Confirms** the issue's rule that
  the chart never resolves it.
- **Argo CD Image Updater** (`docs/basics/update-strategies.md` at `7141e805`, lines 44 to 47): *"all update
  strategies except `digest` assume tags to be *immutable* … If you want to update to *mutable* tags (e.g. the commonly
  used `latest` tag), you should use the `digest` strategy."* **Confirms** that a consumer who follows `:latest` does so
  by its digest, which is what the read-back guarantees is the signed one.

### 2.15 This repository, measured on `6d532178`

- `grep -n latest .github/workflows/publish.yml` matches only `runs-on: ubuntu-latest` (lines 111, 339, 417).
- The `publish` job records `digest`, `image`, `report_digest`, `report_image` as outputs
  (`.github/workflows/publish.yml#report_digest: ${{ steps.build-report.outputs.digest }}`), empty when the credentials
  are missing (`.github/workflows/publish.yml#Empty when nothing was pushed`).
- `attest` runs only on `main`, after a green `publish` with a digest, unless signing is off, and reads every signature
  back (`.github/workflows/publish.yml#Read the signature back`).
- The default render resolves both images at `:2.0.0` and names no `:latest` at all:

      $ helm template t charts/group-sync-dashboard | grep -n "image:"
      1693:          image: quay.io/ephico2real/group-sync-dashboard:2.0.0
      1845:          image: registry.redhat.io/openshift4/ose-oauth-proxy-rhel9:v4.15
      2036:          image: quay.io/ephico2real/group-sync-dashboard-report:2.0.0
      2836:          image: registry.redhat.io/openshift4/ose-cli-rhel9:v4.22
      $ helm template t charts/group-sync-dashboard | grep -c ":latest"
      0

- The lab runs the 2.0.0 digests (read-only, `oc get pods -n group-sync-dashboard`): the dashboard pod's `imageID` is
  `quay.io/ephico2real/group-sync-dashboard@sha256:fc8a5a98…`, the report pod's and its CronJob pods' are
  `…-report@sha256:712350d2…`. PVC UIDs: `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953`,
  `group-sync-dashboard-report-artifacts` `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (equal to the issue's).
- `actionlint` v1.7.12 on `publish.yml`: no finding on `6d532178`, none with §7 applied (shellcheck integration on);
  `shellcheck -s bash` on the new step's `run:` reports only SC2153 (info), for `IMAGE` and `DIGEST`, which the step's
  `env` sets.

## 2a. Alternatives considered

| | Option (source) | What it would cost here | Decision |
|---|---|---|---|
| A1 | **A job of its own, `needs: [publish, attest]`, `!cancelled()` and every requirement written out** (§2.1, §2.2; the issue's decision 1) | one short job and one runner start per run | **chosen**: "signed first" holds by construction, and with signing off it follows `publish` alone |
| A2 | A step at the end of the `publish` job, or a `--latest` flag in `build-and-push-external.sh` (how the release aliases move) | `:latest` would move before `attest` signs, the weakness D10 records for the aliases; a flag in the script would also put `:latest` in the disaster-recovery path, which signs nothing | rejected: breaks the issue's "Must not change: signing" |
| A3 | A step in each `attest` leg, after the read-back | `:latest` would never move with signing off, against the issue's decision 1; one leg could move its image while the other leg's signature failed, so the two `:latest` would name different runs with the run red; and the tag write would join the job that holds `id-token: write` | rejected |
| A4 | A two-leg matrix for `latest`, like `sbom` and `attest` | two runner starts instead of one, and the legs still write separately; T425-4 asks for one step with two copies | rejected; one step with a function called twice is the smaller change |
| A5 | `docker/metadata-action` with `type=raw,value=latest,enable={{is_default_branch}}` and a build-push action (§2.14) | the repository builds with podman through its script, deliberately (`.github/workflows/publish.yml#WHY THE SCRIPT AND NOT INLINE STEPS`), and the tag would be pushed at build time, before signing | rejected |
| A6 | `crane tag`, `oras tag` or `regctl image copy` | a tool the runner does not ship, to pin and verify; skopeo is preinstalled (§2.9) and already makes the aliases | rejected |
| A7 | Prometheus's monotonic guard: move only if this run's commit is newer than the one `:latest` names (§2.14) | read the current `:latest`'s commit from its config (`GSD_GIT_COMMIT`), ask GitHub's compare API whether this commit is ahead, and decide what "diverged" means after a force-push: about fifteen lines, a GitHub API dependency, a fourth outcome | rejected on "easy to manage": nothing resolves `:latest` for a deployment, and the backward move has a one-click remedy (Orchestrator's notes, 2) |
| A8 | Prometheus's naming: `:main` for the branch, `:latest` for the newest release (§2.14) | the operator asked for `:latest` to follow `<appVersion>-<sha10>` (2026-09-27), and the release is already `:<appVersion>` | not taken; the documents state what `:latest` names |
| A9 | `runs-on: ubuntu-24.04` | the job would stay on skopeo 1.13.3 after the `ubuntu-latest` migration while the jobs around it move | rejected; both images' skopeo has the flags (§2.10) |
| A10 | `cosign verify` of `:latest` inside the job | a cosign install and the Sigstore egress for a check that digest equality already implies (§2.12), and that does not exist with signing off | rejected; T425-8 runs it once after the merge |

**Reconciliation** — each external claim, and the line of this repository that behaves accordingly:

- *A skipped `needs` job skips its dependants unless a status function is named* (§2.1) — the condition opens with
  `!cancelled()` and names `needs.publish.result == 'success'` and `needs.attest.result == 'success'` itself
  (block 2, `.github/workflows/publish.yml#(needs.attest.result == 'success' || vars.SUPPLY_CHAIN_SIGNING == 'false')`),
  as `attest` does for `sbom` (`.github/workflows/publish.yml#THE SBOM IS A DEPENDENCY, NOT A REQUIREMENT`).
  T425-3's evaluator adds the implicit `success()` when no status function is named, and the mutant without
  `!cancelled()` fails its "signing switched off" case (§4.3).
- *A job-level `if` cannot read `matrix`* (§2.2) — the condition reads `needs.publish.outputs.*` only, and T425-3
  asserts `matrix.` is absent.
- *A dispatch's `github.ref` is the branch that received it* (§2.3) — `github.ref == 'refs/heads/main'`, the clause
  `attest` already carries (`.github/workflows/publish.yml#github.ref == 'refs/heads/main'`).
- *Unset variables are empty and comparisons ignore case* (§2.3) — `vars.SUPPLY_CHAIN_SIGNING == 'false'` is the exact
  complement of `attest`'s `vars.SUPPLY_CHAIN_SIGNING != 'false'`; T425-3 runs unset, `true`, `false` and `FALSE`.
- *Unlisted permissions are `none`* (§2.4) — `permissions: {contents: read}`, held by T425-7 and by
  `local-development/tests/test_supply_chain.py#TestPermissions.test_no_job_in_publish_can_write_to_this_repository`.
- *`--preserve-digests` fails rather than rewrite; `--all` copies a list and its images* (§2.6) — the copy line is the
  build script's (`local-development/build-and-push-external.sh#skopeo copy --all --preserve-digests`) with the source
  by digest, and the read-back compares with the digest `publish` recorded, as
  `local-development/build-and-push-external.sh#ALIAS_DIGEST` does.
- *`--password-stdin`* (§2.6) — `printf '%s' "${REGISTRY_PASSWORD}" | skopeo login … --password-stdin`, the build
  script's form (`local-development/build-and-push-external.sh#password-stdin, never -p`); a test holds the password
  off every command line.
- *Runs in one concurrency group never overlap* (§2.7) — the workflow-level `concurrency` covers the new job with no
  change (`.github/workflows/publish.yml#group: publish-main`).
- *cosign resolves a tag to its digest before it looks for signatures* (§2.12) — the job copies from
  `<image>@<digest>` (`needs.publish.outputs.digest`), the same value `attest` signed
  (`.github/workflows/publish.yml#DIGEST: ${{ matrix.digest }}`), so the digest `:latest` resolves to is the signed one.
- *Kubernetes advises against `:latest` in production* (§2.14) — the chart resolves `.Values.image.tag` or
  `.Chart.AppVersion` (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.image`), and the new chart test holds
  that the default render of both images is `:<appVersion>`.

## 3. The design

### 3.1 One job, after `attest`

A fourth job, `latest`, `needs: [publish, attest]`. It holds one step. Being a separate job is what makes "`:latest`
names a signed digest" true by construction: GitHub starts it only after `attest` has finished, and `attest` is green
only after `cosign verify`, `cosign verify-attestation` (when there is an SBOM) and `gh attestation verify` have
passed for both images (`.github/workflows/publish.yml#EVERY ARTEFACT IS READ BACK`). The release aliases cannot
have this property, because they move inside `publish`; this tag can, so it does.

### 3.2 The condition

    !cancelled()
    && needs.publish.result == 'success'
    && needs.publish.outputs.digest != ''
    && needs.publish.outputs.report_digest != ''
    && github.ref == 'refs/heads/main'
    && (needs.attest.result == 'success' || vars.SUPPLY_CHAIN_SIGNING == 'false')

| Clause | Why |
|---|---|
| `!cancelled()` | `attest` is skipped with signing off, and a skipped `needs` would skip this job (§2.1); a cancelled run moves nothing |
| `needs.publish.result == 'success'` | the run is the unit: a report build that failed after the dashboard's push moves neither `:latest` |
| both digests non-empty | with no credentials `publish` succeeds and pushes nothing (`.github/workflows/publish.yml#skipping publish`); both are written in the same job under the same condition, and both are checked because the step copies both |
| `github.ref == 'refs/heads/main'` | a dispatch from another branch pushes unsigned images (D9); `:latest` must not follow it |
| `attest` succeeded, or signing is off | signed and read back first; `attest`'s one result covers both legs (§2.2) |

With signing on, `attest` is skipped only when one of the other clauses is false (its own condition is a subset of
these), so "signing is on and `attest` was skipped" never moves `:latest`; T425-3's truth table holds that.

### 3.3 The copy and the read-back

For each image, in order, dashboard then report:

1. Refuse a digest that is not `sha256:` and 64 lowercase hex digits, as the build script refuses one it would record
   (`local-development/build-and-push-external.sh#Exactly 64 hex digits`). Both digests are checked before either copy,
   so nothing is copied for either image (review of the spec, OB2: checked inside the per-image function, a bad report
   digest moved the dashboard's `:latest` first).
2. `skopeo copy --all --preserve-digests docker://<image>@<digest> docker://<image>:latest`. By digest: the source is
   the value `publish` recorded and `attest` signed, never a tag that could have moved since.
2b. A copy the registry refuses is `::error::<image>:latest was not moved: the registry refused the copy of <digest>` and
   exit 1, after skopeo's own message, so the run's annotation names the image (review of the spec, OB2: measured, the
   step died on `set -e` with skopeo's stderr and no `::error::`).
3. `skopeo inspect --no-tags --format '{{.Digest}}' docker://<image>:latest`, compared with `<digest>`. A difference
   is `::error::<image>:latest resolves to <found>, not <digest>, the digest this run pushed.` and exit 1; the second
   image is not attempted.
3b. A read-back that cannot be made (the registry stopped answering after the copy) is
   `::error::<image>:latest was copied from <digest> but could not be read back …` and exit 1, after skopeo's own
   message, so the annotation names the image whose tag has moved unverified and the remedy, as 2b does (review of
   #530, OB2: measured, under `set -e` alone the step ended with skopeo's stderr and no `::error::`).
4. Print `moved   : <image>:latest -> <digest>`, the build script's log format.

The step logs in once, with the password on stdin. It prints `skopeo --version` first, so a runner image without
skopeo fails on its first line with a legible error.

### 3.4 What does not change

- `publish` is not edited: its steps, outputs and `permissions: {contents: read}` are as
  they are (T425-7; `local-development/tests/test_publish_release_decision.py#test_the_publish_job_can_write_to_nothing_but_the_registry`).
- The release decision and the `:<appVersion>` / `:<chartVersion>` aliases are untouched (T425-5 runs the existing
  tests).
- The chart: no template, value or version change of its own (T425-6 adds a render test that holds both images at
  `:<appVersion>`).
- The disaster-recovery scripts: one comment in the build script's header says they do not move `:latest`.

### 3.5 The budget: what the job writes, and its scope

**What it writes:** for each green run on `refs/heads/main` of `ephico2real/group-sync-dashboard` that pushed both
images, at most **two tags**, `quay.io/<namespace>/group-sync-dashboard:latest` and
`…/group-sync-dashboard-report:latest`, by **two** `skopeo copy` calls, each followed by one read. It deletes nothing
and touches no other tag; quay keeps each previous `:latest` as a closed history entry (§2.13).

| System shape | What holds |
|---|---|
| one green run on `main`, signing on | both `:latest` name the digests that run pushed and `attest` verified, or the run is red |
| signing off (`SUPPLY_CHAIN_SIGNING=false`) | both move after `publish`; `:latest` is as unsigned as that run's immutable tags (D8) |
| one image's signature or SBOM read-back fails | `needs.attest.result` is `failure`; neither moves |
| two pushes in quick succession | the runs are serialized (§2.7); `:latest` follows the commits in order; a replaced pending run never moves it |
| a dispatch from another branch | skipped; `:latest` unchanged |
| a fork | `publish` is skipped by its repository guard, so this job is skipped |
| the second copy or its read-back fails | **residual 1:** the dashboard's `:latest` is one run ahead of the report's until the job is re-run; the run is red and names the image |
| an older run's `latest` job re-run after a newer run | **residual 2:** `:latest` names the older run's build until the newest green run's `latest` job is re-run (§2.8; Orchestrator's notes, 2) |
| a build pushed by hand with the disaster-recovery scripts | `:latest` is not moved; the next green run moves it |

### 3.6 The documents

- `docs/DESIGN_supply_chain.md` gains decision D11 (what `:latest` names, when it moves, the two residuals).
- `docs/RELEASING.md`: the publish flow draws the `latest` job; "Three tags" becomes "Four tags" with a `latest`
  row; "What can go wrong" gains the red `latest` job and the backward move.
- `docs/HELM_DOWNLOAD_AND_INSTALL.md` §7: `:latest` is one more name for a signed digest.
- `local-development/build-and-push-external.sh`: the header says the script does not move `:latest`.
- `docs/CHANGELOG.md`: the entry under `## Unreleased`.

No chart README row or `values.yaml` comment changes: no value is added or changed.

## 4. Tests

### 4.1 One test per test case

| ID | Test | Why it fails without the change |
|---|---|---|
| T425-1 | `test_supply_chain.py::TestLatestFollowsTheNewestSignedMainBuild::test_each_image_is_copied_to_latest_from_this_runs_digest`: the step's env maps the four `needs.publish.outputs`, its code holds the copy line by digest, the read-back line and the two calls | `KeyError: 'latest'`: there is no such job |
| T425-2 | `…::test_a_latest_that_resolves_elsewhere_is_a_red_run_naming_both_digests`: runs the step's real `run:` against a stub skopeo whose read-back answers another digest; exit 1, both digests in the `::error::`, exactly one copy made | the same `KeyError` |
| T425-3 | `…::test_latest_moves_only_after_a_signed_publish_on_main`: `needs` is `[publish, attest]`, each clause is present, no `matrix.`, and the condition evaluated over thirteen contexts (signed on main; signing off, in two spellings; attest failed; attest skipped with signing on, unset or `true`; publish red; no digests; no report digest; another branch; cancelled; signing off but another branch; signing off but a red publish — the last two hold the parentheses around the `attest` clause by evaluation, since `&&` binds tighter than `\|\|`) | the same `KeyError` |
| T425-4 | `…::test_both_images_move_by_digest_and_never_by_tag`: the step run with matching answers exits 0; the stub's log holds exactly the two copies, each `@sha256:…` to `:latest`, and two reads of `:latest` | the same `KeyError` |
| T425-5 | `tests/test_publish_release_decision.py`, unchanged | a regression guard: passes before and after (§4.3) |
| T425-6 | `test_chart_image_reference.py::test_the_default_render_never_resolves_latest` (new): every container of either image in the default render ends `:<appVersion>`, and both images are present | a regression guard: passes before and after; it fails if a default ever resolved `:latest` |
| T425-7 | `…::test_the_latest_job_holds_only_read` (new) and the existing `TestPermissions` and `test_the_publish_job_can_write_to_nothing_but_the_registry` | the new test fails with the `KeyError`; the existing ones pass before and after |
| T425-8 | the registry check after the merge (§5, step 4) | measured 2026-10-01: both `:latest` are `manifest unknown` (§2.13) |

Added by the research:

| Test | Holds | Why it fails without the change |
|---|---|---|
| `…::test_the_password_reaches_skopeo_on_stdin_only` | the login uses `--password-stdin`, and the password is on no logged command line and in no output | the `KeyError` |
| `…::test_a_digest_that_is_not_sixty_four_hex_moves_nothing` | `sha256:abc` as either digest is refused before any copy | the `KeyError` |
| `…::test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy` | a copy the registry refuses is exit 1 with a `::error::` naming the image and the re-run; the earlier `moved   :` line stands | the `KeyError` |
| `…::test_a_read_back_that_cannot_be_made_is_a_red_run_naming_the_image_and_the_remedy` | a read-back that fails on its own is exit 1 with a `::error::` naming the image, the digest it was copied from and the re-run; the earlier `moved   :` line stands (review of #530, OB2) | the `KeyError`; on the first implementation (`b06ee631`), `AssertionError`: exit 1 with no `::error::` |
| `…::test_the_docs_say_what_latest_names` | D11, the RELEASING `latest` row and the flow's `latest  job` line exist | `AssertionError`: `DESIGN_supply_chain.md` has no D11 |

The harness runs the step's `run:` from the parsed YAML with `/bin/bash --noprofile --norc -eo pipefail -c`, the
flags GitHub gives `shell: bash`, with `PATH` holding only the stub's directory, `/usr/bin` and `/bin`. The stub is a
bash script that logs its argv, swallows stdin on `login`, records the digest a `copy` names as its source and answers
a read-back with it (or with `STUB_ANSWER`). The truth table evaluates the real `if:` with the grammar it uses and
refuses anything else: string literals, `==` and `!=` ignoring case, `&&`, `||`, parentheses, `!cancelled()`, unset
values as `''`, and the implicit `success()` over `needs` when no status function is named.

### 4.2 The commands

    cd local-development
    PYTHONPATH=$PWD .venv/bin/python -m pytest -q tests/test_supply_chain.py tests/test_chart_image_reference.py \
      tests/test_publish_release_decision.py tests/test_publish_paths.py tests/test_docs_citations.py

### 4.3 Before and after, measured

Re-measured for the revision on throwaway worktrees of origin/main `3acfda37` (application 2.0.0, chart 0.59.25), with
the Python 3.14 venv and `PYTHONPATH` set to the tree under test; the version-gate rows were measured on `6d532178`,
whose application and chart versions are the same.

| Step | Command | Result |
|---|---|---|
| blocks check | `apply-spec-blocks.py SPEC_E9_latest_tag.md <clean 3acfda37>` | `12 blocks check out across 8 files` |
| before: the test blocks alone applied (3 and 4) | `pytest -q` per file: `test_supply_chain.py` / `test_chart_image_reference.py` / `test_publish_release_decision.py` | `9 failed, 34 passed` / `9 passed` / `9 passed`: the nine tests of the class fail, eight with `KeyError: 'latest'` and the docs test with `AssertionError` on D11; the chart guard (T425-6) and T425-5 pass |
| before, for the two tests the review added: the corrected Block 3 over the first pass's Block 2 (`24084b06`) | `pytest -q tests/test_supply_chain.py -k Latest` | `2 failed, 7 passed`: `test_a_digest_that_is_not_sixty_four_hex_moves_nothing`, `test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy` |
| after: all twelve blocks applied | `test_supply_chain.py` / `test_chart_image_reference.py` / `test_publish_release_decision.py` / `test_publish_paths.py` / `test_docs_citations.py`; the five together | `43 passed` / `9 passed` / `9 passed` / `9 passed` / `1618 passed, 22 skipped`; together `1688 passed, 22 skipped` |
| the whole hermetic suite, after | `pytest -q` in `local-development/` | `7065 passed, 30 skipped, 5 xfailed` (536 s) |
| lint | `actionlint` v1.7.12 on `publish.yml` and `helm.yaml` (shellcheck on); `shellcheck -s bash` on the step | no finding; SC2153 (info) only, for the step's `env` names (`IMAGE`, `DIGEST`). actionlint's one note on `ci.yml` (SC2086, line 63) is on origin/main already |
| the version gate (on `6d532178`) | blocks committed, then `prepare-release.py --app 2.3.0 --no-commit`, committed, then `BASE=6d532178 check-app-version-bump.py` | exit 1: `expected exactly 2.1.0 (next MINOR) or 3.0.0 (next MAJOR), got 2.3.0` |
| | the same with `--app 2.1.0` | exit 0: `application version is the next MINOR or MAJOR; bump accepted`; chart `0.59.26` derived; `test_specs_index.py` then fails `('G2', 'app 2.1.0, chart 0.60.0', 'pyproject.toml is already 2.1.0')` until the colliding `specified` rows move (the Version note) |
| the index pin | this branch, E9 mistyped as #525 in its row and header | with the pin `1 failed, 97 passed`, `AssertionError: ('E9 is #425', '525')`; pin removed `98 passed` |

Mutants of the job, each applied alone to the applied tree and the class run (`pytest -k Latest`):

| Mutant | Result |
|---|---|
| the condition without `!cancelled()` | fails T425-3 (the clause check; with that check removed, the truth table's "signing switched off: attest skipped, follow publish" case fails too, through the implicit `success()`) |
| without `\|\| vars.SUPPLY_CHAIN_SIGNING == 'false'` | 1 failed (T425-3) |
| without `github.ref == 'refs/heads/main'` | 1 failed (T425-3) |
| the copy's source by tag, `docker://${image}:${digest}` | 4 failed (T425-1, T425-4, `test_the_password_reaches_skopeo_on_stdin_only` and `test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy`, whose runs no longer exit as expected; T425-2 still sees its exit 1) |
| the read-back's comparison removed | 1 failed (T425-2) |
| the parentheses around the `attest` clause removed | 1 failed (T425-3: the clause check; with that check also removed, the truth table alone fails it at "signing switched off, but a dispatch from another branch") |
| the digest check moved back inside `move_latest`, or the refused copy left to `set -e` | 1 failed each (`test_a_digest_that_is_not_sixty_four_hex_moves_nothing`, `test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy`) |
| without `--preserve-digests` | 2 failed (T425-1, T425-4) |
| the password on the command line (`--password`) | 1 failed (`test_the_password_reaches_skopeo_on_stdin_only`) |
| `needs: [publish]` | 1 failed (T425-3) |
| `id-token: write` added to the job | 1 failed (T425-7) |

### 4.4 Composition with SPEC_E8

SPEC_E8 as merged on origin/main (`3acfda37`, 18 blocks across 6 files) and this spec were applied to two copies of
`3acfda37`, in each order, with a commit between the two applies, because `apply-spec-blocks.py` refuses a tree with
uncommitted changes (re-measured in review, OB2; the first pass read E8 from its branch at `d5d14f5e`, 11 blocks):

    $ apply-spec-blocks.py SPEC_E8… comp-a --apply && git -C comp-a commit -qam e8 && apply-spec-blocks.py SPEC_E9… comp-a --apply
    18 blocks check out across 6 files
    12 blocks check out across 8 files
    $ apply-spec-blocks.py SPEC_E9… comp-b --apply && git -C comp-b commit -qam e9 && apply-spec-blocks.py SPEC_E8… comp-b --apply
    12 blocks check out across 8 files
    18 blocks check out across 6 files
    $ diff -r comp-a comp-b      # only the order of the two CHANGELOG entries and of the two test classes differs
    $ pytest -q tests/test_supply_chain.py tests/test_chart_image_reference.py tests/test_publish_release_decision.py \
        tests/test_publish_paths.py tests/test_docs_citations.py tests/test_release_crc.py      # in each copy
    comp-a: 1745 passed, 22 skipped
    comp-b: 1745 passed, 22 skipped
    $ actionlint publish.yml helm.yaml      # in each copy: no finding

The four shared files: `test_supply_chain.py` (E8's blocks 4 to 7 and 12 to 18 edit the docstring, the imports, the
constants, the last line and its own class; this spec inserts after the last line and adds no import and no module-level
name — which is why its tests loop rather than parametrize), `RELEASING.md`
(E8 edits the chart flow and the table's first two rows; this spec the publish flow, the tag heading and table, and
the table's last row), `DESIGN_supply_chain.md` (E8 edits D10's middle; this spec inserts after D10's last line) and
`CHANGELOG.md` (both insert under `## Unreleased`, whose line stays unique).

## 5. On the lab

The change writes nothing to the lab and changes nothing it runs. The walk proves that.

1. **Before the implementing pull request deploys (read-only, measured 2026-10-01, §2.15):** the lab runs
   `…group-sync-dashboard@sha256:fc8a5a98…` and `…-report@sha256:712350d2…`; the PVC UIDs are
   `f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.
2. **Before the merge, from the pull request's branch (the issue's first issue-specific check):** dispatch
   `publish.yml` on the branch (development: `gh workflow run publish.yml --ref <branch>`). The run's `latest` job is
   skipped (`gh run view <id> --json jobs`), and both `:latest` are unchanged (`oc image info`; still
   `manifest unknown` if this is the first time). This pushes the branch's immutable tags unsigned, as such a dispatch
   always has (D9).
3. **Optional, the operator's setting:** with `SUPPLY_CHAIN_SIGNING=false` set for one run, the `latest` job runs
   after `publish` with `attest` skipped. Set the variable back afterwards. T425-3 is the hermetic proof.
4. **After the merge (T425-8), read-only:**

       for r in group-sync-dashboard group-sync-dashboard-report; do
         oc image info quay.io/ephico2real/${r}:latest | grep Digest
         oc image info quay.io/ephico2real/${r}:<appVersion>-<sha10 of the merge> | grep Digest
         cosign verify \
           --certificate-identity https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main \
           --certificate-oidc-issuer https://token.actions.githubusercontent.com \
           quay.io/ephico2real/${r}:latest > /dev/null && echo "${r}:latest verifies"
       done

   Each pair of digests is equal and both verify. Post the output on #425 pinned to the full merge sha, with the two
   `moved   :` lines of the run's `latest` job.
5. **With the epic's release deployed:** the pods' `imageID`s are the release's digests, not `:latest`'s unless the
   two are the same build; the PVC UIDs are unchanged.

## 6. What an operator sees, and what it costs

- **In the Actions run:** a fourth job, "Move :latest to this run's digests", after the two signing legs. Its log
  shows the skopeo version and two `moved   : quay.io/…:latest -> sha256:…` lines. Red, it names the image (and both
  digests, on a mismatch), says that an earlier `moved   :` line stands, and says to re-run the job.
- **On quay:** `:latest` on both repositories, one history entry more per image per green publish. Pulling it gives
  the newest signed `main` build; `cosign verify` with the install guide's identity passes.
- **On a cluster:** nothing. The chart deploys `:<appVersion>`.
- **Cost:** one runner start per green publish on `main`, plus two copies and two reads; the alias copy and read-back
  measured 3.1 s in run 36690887346 (§2.13). The job's own duration is not measured until the first run.
- **What it adds to look after:** one job, one step. Its tests run the step itself, so a change to the step that
  breaks a refusal fails CI.

## 7. Implementation blocks

Twelve blocks across eight files. Apply with `python3 local-development/apply-spec-blocks.py
docs/specs/SPEC_E9_latest_tag.md . --apply`, commit, then run `prepare-release.py --app <main's next MINOR>
--no-commit "…"` and commit its edits (the Version note).

### Block 1 — `.github/workflows/publish.yml`: the header names the third job

<!-- block: .github/workflows/publish.yml | edit -->
```yaml
# load-bearing — while only `attest` holds `id-token: write`. Each has a repository-variable
# switch, documented on the job.
name: publish
```

```yaml
# load-bearing — while only `attest` holds `id-token: write`. Each has a repository-variable
# switch, documented on the job.
#
# A THIRD JOB, `latest`, runs once the signatures have been read back (or straight after `publish`
# when signing is switched off) and moves `:latest` of both images to the digests this run pushed,
# on `main` only (#425). It holds `contents: read` like the others.
name: publish
```

### Block 2 — `.github/workflows/publish.yml`: the `latest` job

<!-- block: .github/workflows/publish.yml | after:             --signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/publish.yml" -->
```yaml

  # ── :latest, the newest signed main build ────────────────────────────────────────────────────
  #
  # #425 (SPEC_E9). For both images, `:latest` names the digest the newest green run on `main`
  # pushed as <appVersion>-<sha>. Nothing in this repository resolves it: the chart deploys
  # `:<appVersion>` (image.tag ships "" and gsd.image falls back to .Chart.AppVersion), so moving
  # it cannot change what a cluster runs. It is for a person or a pipeline that wants the newest
  # `main` build without reading a run log; a release is still `:<appVersion>`.
  #
  # A JOB OF ITS OWN, AFTER `attest`, so `:latest` never names a digest whose signature has not
  # been written and read back. The release aliases move inside `publish`, before signing, and D10
  # records what that costs; this tag does not have to. When SUPPLY_CHAIN_SIGNING is 'false' there
  # is no `attest` to wait for, and it follows `publish` alone.
  #
  # THE CONDITION, one clause per rule:
  #   !cancelled()                 `attest` is skipped when signing is off, and a skipped job in
  #                                `needs` skips this one unless a status function is named
  #   publish succeeded            the run is the unit: a report build that failed after the
  #                                dashboard's push moves neither `:latest`
  #   both digests are non-empty   no credentials, nothing pushed, nothing to move
  #   github.ref is main           a dispatch from another branch pushes unsigned images (D9)
  #   attest succeeded, or the     signed and read back first; GitHub reports one result for
  #   signing switch is 'false'    both legs, so one image's failed signature moves neither
  #
  # BY DIGEST, NEVER BY TAG. The source is <image>@<digest> as `publish` recorded it, so a tag
  # moved in the meantime cannot be what `:latest` copies. The copy and the read-back are the
  # release aliases' (build-and-push-external.sh, "COPIED IN THE REGISTRY"): server side, the
  # manifest byte-identical or a refusal, then the name resolved and compared.
  #
  # A RE-RUN COPIES ITS OWN RUN'S DIGESTS. Re-running this job on an older run points `:latest`
  # back at that run's build; re-running it on the newest green run puts it right (SPEC_E9 §3.5).
  latest:
    name: "Move :latest to this run's digests"
    needs: [publish, attest]
    if: >-
      !cancelled()
      && needs.publish.result == 'success'
      && needs.publish.outputs.digest != ''
      && needs.publish.outputs.report_digest != ''
      && github.ref == 'refs/heads/main'
      && (needs.attest.result == 'success' || vars.SUPPLY_CHAIN_SIGNING == 'false')
    runs-on: ubuntu-latest
    permissions:
      # The registry write is the robot credential's; the job's token reads and nothing more.
      contents: read
    steps:
      - name: Copy each digest to :latest, and read it back
        shell: bash
        env:
          REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
          REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
          REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
          IMAGE: ${{ needs.publish.outputs.image }}
          DIGEST: ${{ needs.publish.outputs.digest }}
          REPORT_IMAGE: ${{ needs.publish.outputs.report_image }}
          REPORT_DIGEST: ${{ needs.publish.outputs.report_digest }}
        run: |
          set -euo pipefail
          skopeo --version
          # --password-stdin, never on the command line: the same rule as the build script.
          printf '%s' "${REGISTRY_PASSWORD}" \
            | skopeo login --username "${REGISTRY_USERNAME}" --password-stdin "${REGISTRY}" > /dev/null
          refuse_unless_digest() {
            # Exactly 64 hex digits, as the build script checks the digest it records. BOTH digests are
            # checked before EITHER copy, so a bad second digest cannot leave the first image's :latest
            # moved on its own.
            if [[ ! "$2" =~ ^sha256:[0-9a-f]{64}$ ]]; then
              echo "::error::$1: '$2' is not a sha256 digest, so neither :latest was moved."
              exit 1
            fi
          }
          move_latest() {
            local image=$1 digest=$2 moved
            if ! skopeo copy --all --preserve-digests "docker://${image}@${digest}" "docker://${image}:latest"; then
              echo "::error::${image}:latest was not moved: the registry refused the copy of ${digest} (its message is above)."
              echo "::error::Any 'moved   :' line above stands. Re-run this job; it moves both images again."
              exit 1
            fi
            # The read-back can fail on its own (the registry stopped answering after the copy): under
            # `set -e` alone that was skopeo's stderr and no annotation, with the tag already moved.
            if ! moved=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${image}:latest"); then
              echo "::error::${image}:latest was copied from ${digest} but could not be read back (skopeo's message is above), so this run cannot tell what it names."
              echo "::error::Any 'moved   :' line above stands. Re-run this job; it moves both images again."
              exit 1
            fi
            if [ "${moved}" != "${digest}" ]; then
              echo "::error::${image}:latest resolves to ${moved}, not ${digest}, the digest this run pushed."
              echo "::error::Any 'moved   :' line above stands. Inspect both, then re-run this job."
              exit 1
            fi
            echo "moved   : ${image}:latest -> ${digest}"
          }
          refuse_unless_digest "${IMAGE}" "${DIGEST}"
          refuse_unless_digest "${REPORT_IMAGE}" "${REPORT_DIGEST}"
          move_latest "${IMAGE}" "${DIGEST}"
          move_latest "${REPORT_IMAGE}" "${REPORT_DIGEST}"
```

### Block 3 — `local-development/tests/test_supply_chain.py`: T425-1 to T425-4, T425-7 and the research's tests

<!-- block: local-development/tests/test_supply_chain.py | after:         assert "Forks do not sign under this workflow" in section -->
```python


# ── :latest follows the newest signed main build (#425, SPEC_E9) ─────────────────────────────


class TestLatestFollowsTheNewestSignedMainBuild:
    """The `latest` job moves `:latest` of both images to the digests this run pushed, after
    `attest` has signed and read them back, on `main` only, by the release aliases' server-side
    copy and read-back. The shape is read from the real YAML like the rest of this file; the step's
    `run:` is also EXECUTED, by bash with the flags GitHub gives `shell: bash`, against a stub
    `skopeo` that logs every call — the real step, only the registry replaced — because its
    refusals are decisions over what the registry answers, and only a run shows them."""

    JOB = "latest"
    STEP = "Copy each digest to :latest"
    NEW = "sha256:" + "a" * 64        # the dashboard digest this run pushed
    NEW_REPORT = "sha256:" + "b" * 64  # the report digest this run pushed
    OTHER = "sha256:" + "c" * 64      # what a wrong :latest resolves to
    STUB = """#!/bin/bash
# A stand-in skopeo: logs its argv, swallows the password on stdin, remembers the digest each copy
# names as its source, and answers a read-back with it (or with STUB_ANSWER when that is set).
# A copy whose destination contains STUB_REFUSE fails, as a registry that refuses the write does.
# A read-back of a name containing STUB_UNREADABLE fails, as a registry that stopped answering does.
{ printf 'skopeo'; printf ' %s' "$@"; printf '\\n'; } >> "${STUB_LOG}"
for arg in "$@"; do source_ref=${last_ref:-}; last_ref=$arg; done
case "$1" in
  --version) echo "skopeo version 1.13.3" ;;
  login) cat > /dev/null ;;
  copy) if [ -n "${STUB_REFUSE:-}" ] && [[ "${last_ref}" == *"${STUB_REFUSE}"* ]]; then
          echo "stub skopeo: writing manifest to ${last_ref}: denied" >&2; exit 1
        fi
        printf '%s' "${source_ref##*@}" > "${STUB_STATE}" ;;
  inspect) if [ -n "${STUB_UNREADABLE:-}" ] && [[ "${last_ref}" == *"${STUB_UNREADABLE}"* ]]; then
             echo "stub skopeo: pinging container registry quay.io: 503 Service Unavailable" >&2; exit 1
           fi
           if [ -n "${STUB_ANSWER:-}" ]; then echo "${STUB_ANSWER}"; else cat "${STUB_STATE}"; echo; fi ;;
  *) echo "stub skopeo: unexpected $1" >&2; exit 2 ;;
esac
"""

    @classmethod
    def _job(cls) -> dict:
        return _jobs(PUBLISH)[cls.JOB]

    @classmethod
    def _run(cls, tmp_path: pathlib.Path, *, answer: str = "", digest: str = NEW, report_digest: str = NEW_REPORT,
             refuse: str = "", unreadable: str = "") -> tuple[subprocess.CompletedProcess, list[str]]:
        """Run the step's real `run:` with its env as GitHub would fill it; return the result and the stub's log."""
        stub_dir = tmp_path / "bin"
        stub_dir.mkdir()
        (stub_dir / "skopeo").write_text(cls.STUB)
        (stub_dir / "skopeo").chmod(0o755)
        log = tmp_path / "skopeo.log"
        env = {
            "PATH": f"{stub_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "STUB_STATE": str(tmp_path / "state"),
            "STUB_ANSWER": answer,
            "STUB_REFUSE": refuse,
            "STUB_UNREADABLE": unreadable,
            "REGISTRY": "quay.io",
            "REGISTRY_USERNAME": "ephico2real+publisher",
            "REGISTRY_PASSWORD": "not-a-real-password",
            "IMAGE": "quay.io/ephico2real/group-sync-dashboard",
            "DIGEST": digest,
            "REPORT_IMAGE": "quay.io/ephico2real/group-sync-dashboard-report",
            "REPORT_DIGEST": report_digest,
        }
        step = _step(cls._job(), cls.STEP)
        done = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", step["run"]],
                              env=env, capture_output=True, text=True, check=False)
        return done, (log.read_text().splitlines() if log.exists() else [])

    @staticmethod
    def _holds(job: dict, context: dict[str, str], *, cancelled: bool = False) -> bool:
        """The job's `if:` evaluated over a context the way GitHub evaluates this grammar: string
        literals, `==` and `!=` ignoring case, `&&`, `||`, parentheses, `!cancelled()`, an unset
        context value read as an empty string, and the implicit `success()` (every job in `needs`
        succeeded) that GitHub adds when the condition names no status function. Anything outside
        that grammar fails the guard below, so the evaluation cannot mean something the workflow
        does not."""
        condition = job["if"]
        assert re.fullmatch(r"[\w.'()!=&|/ -]+", condition), condition
        expr = condition.replace("!cancelled()", f" (not {cancelled}) ").replace("&&", " and ").replace("||", " or ")
        expr = re.sub(r"'([^']*)'", lambda m: repr(m.group(1).lower()), expr)
        expr = re.sub(r"\b(?:needs|vars|github)\.[\w.-]+", lambda m: repr(context.get(m.group(0), "").lower()), expr)
        assert "!" not in expr.replace("!=", ""), expr
        held = bool(eval(expr, {"__builtins__": {}}))   # the repository's own workflow text, guarded above
        if not re.search(r"\b(?:success|failure|always|cancelled)\(\)", condition):
            held = held and not cancelled and all(context.get(f"needs.{name}.result") == "success" for name in job["needs"])
        return held

    # T425-1
    def test_each_image_is_copied_to_latest_from_this_runs_digest(self) -> None:
        step = _step(self._job(), self.STEP)
        assert step["env"]["IMAGE"] == "${{ needs.publish.outputs.image }}"
        assert step["env"]["DIGEST"] == "${{ needs.publish.outputs.digest }}"
        assert step["env"]["REPORT_IMAGE"] == "${{ needs.publish.outputs.report_image }}"
        assert step["env"]["REPORT_DIGEST"] == "${{ needs.publish.outputs.report_digest }}"
        code = "\n".join(ln for ln in step["run"].splitlines() if not ln.strip().startswith("#"))
        assert 'skopeo copy --all --preserve-digests "docker://${image}@${digest}" "docker://${image}:latest"' in code
        assert "skopeo inspect --no-tags --format '{{.Digest}}' \"docker://${image}:latest\"" in code
        assert 'move_latest "${IMAGE}" "${DIGEST}"' in code
        assert 'move_latest "${REPORT_IMAGE}" "${REPORT_DIGEST}"' in code

    # T425-2
    def test_a_latest_that_resolves_elsewhere_is_a_red_run_naming_both_digests(self, tmp_path: pathlib.Path) -> None:
        done, log = self._run(tmp_path, answer=self.OTHER)
        assert done.returncode == 1, done.stdout + done.stderr
        assert self.OTHER in done.stdout and self.NEW in done.stdout, done.stdout
        assert "::error::" in done.stdout
        copies = [ln for ln in log if ln.startswith("skopeo copy")]
        assert len(copies) == 1, f"the run must stop at the first mismatch, not move the second image: {log}"

    # T425-3
    def test_latest_moves_only_after_a_signed_publish_on_main(self) -> None:
        job = self._job()
        assert job["needs"] == ["publish", "attest"]
        condition = job["if"]
        for clause in ("!cancelled()", "needs.publish.result == 'success'", "github.ref == 'refs/heads/main'",
                       "needs.publish.outputs.digest != ''", "needs.publish.outputs.report_digest != ''",
                       "(needs.attest.result == 'success' || vars.SUPPLY_CHAIN_SIGNING == 'false')"):
            assert clause in condition, clause
        assert "matrix." not in condition, "a job-level `if` cannot read the matrix context"
        green = {
            "needs.publish.result": "success",
            "needs.publish.outputs.digest": self.NEW,
            "needs.publish.outputs.report_digest": self.NEW_REPORT,
            "needs.attest.result": "success",
            "github.ref": "refs/heads/main",
        }
        cases = [
            ("a signed publish on main", {}, False, True),
            ("signing switched off: attest skipped, follow publish", {"vars.SUPPLY_CHAIN_SIGNING": "false", "needs.attest.result": "skipped"}, False, True),
            ("signing switched off, written in capitals", {"vars.SUPPLY_CHAIN_SIGNING": "FALSE", "needs.attest.result": "skipped"}, False, True),
            ("a signature that failed or was not read back", {"needs.attest.result": "failure"}, False, False),
            ("signing on but attest skipped", {"needs.attest.result": "skipped"}, False, False),
            ("signing on (any other word) but attest skipped", {"vars.SUPPLY_CHAIN_SIGNING": "true", "needs.attest.result": "skipped"}, False, False),
            ("a red publish", {"needs.publish.result": "failure"}, False, False),
            ("no credentials: nothing pushed", {"needs.publish.outputs.digest": "", "needs.publish.outputs.report_digest": ""}, False, False),
            ("no report digest", {"needs.publish.outputs.report_digest": ""}, False, False),
            ("a workflow_dispatch from another branch", {"github.ref": "refs/heads/feature"}, False, False),
            ("a cancelled run", {}, True, False),
            # `&&` binds tighter than `||` (the expressions reference's operator table): without the
            # parentheses, "signing off" alone would move :latest from any branch, after any publish.
            ("signing switched off, but a dispatch from another branch", {"vars.SUPPLY_CHAIN_SIGNING": "false", "needs.attest.result": "skipped", "github.ref": "refs/heads/feature"}, False, False),
            ("signing switched off, but a red publish", {"vars.SUPPLY_CHAIN_SIGNING": "false", "needs.attest.result": "skipped", "needs.publish.result": "failure"}, False, False),
        ]
        for why, change, cancelled, expected in cases:
            assert self._holds(job, {**green, **change}, cancelled=cancelled) is expected, why

    # T425-4
    def test_both_images_move_by_digest_and_never_by_tag(self, tmp_path: pathlib.Path) -> None:
        done, log = self._run(tmp_path)
        assert done.returncode == 0, done.stdout + done.stderr
        copies = [ln for ln in log if ln.startswith("skopeo copy")]
        assert copies == [
            f"skopeo copy --all --preserve-digests docker://quay.io/ephico2real/group-sync-dashboard@{self.NEW} "
            "docker://quay.io/ephico2real/group-sync-dashboard:latest",
            f"skopeo copy --all --preserve-digests docker://quay.io/ephico2real/group-sync-dashboard-report@{self.NEW_REPORT} "
            "docker://quay.io/ephico2real/group-sync-dashboard-report:latest",
        ], log
        reads = [ln for ln in log if ln.startswith("skopeo inspect")]
        assert len(reads) == 2 and all(ln.endswith(":latest") for ln in reads), log
        assert f"moved   : quay.io/ephico2real/group-sync-dashboard:latest -> {self.NEW}" in done.stdout

    def test_the_password_reaches_skopeo_on_stdin_only(self, tmp_path: pathlib.Path) -> None:
        done, log = self._run(tmp_path)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "skopeo login --username ephico2real+publisher --password-stdin quay.io" in log, log
        assert not any("not-a-real-password" in ln for ln in log), "the password was on a command line"
        assert "not-a-real-password" not in done.stdout + done.stderr

    def test_a_digest_that_is_not_sixty_four_hex_moves_nothing(self, tmp_path: pathlib.Path) -> None:
        """Both digests are checked before either copy: a bad REPORT digest must not leave the
        dashboard's :latest moved on its own (review of SPEC_E9, OB2). A loop, not parametrize:
        this file imports no pytest, and SPEC_E8 edits its import block."""
        for bad in ("digest", "report_digest"):
            (tmp_path / bad).mkdir()
            done, log = self._run(tmp_path / bad, **{bad: "sha256:abc"})
            assert done.returncode == 1, (bad, done.stdout + done.stderr)
            assert "is not a sha256 digest" in done.stdout, bad
            assert not [ln for ln in log if ln.startswith("skopeo copy")], (bad, log)

    def test_a_refused_copy_is_a_red_run_naming_the_image_and_the_remedy(self, tmp_path: pathlib.Path) -> None:
        """The two copies are two writes (SPEC_E9 §3.5, residual 1): when the registry refuses the
        second, the run is red and its `::error::` names the image and says to re-run the job — not
        only skopeo's own stderr (review of SPEC_E9, OB2: measured, the step died on `set -e` with no
        `::error::` at all)."""
        done, log = self._run(tmp_path, refuse="group-sync-dashboard-report:latest")
        assert done.returncode == 1, done.stdout + done.stderr
        assert "::error::quay.io/ephico2real/group-sync-dashboard-report:latest was not moved" in done.stdout, done.stdout
        assert "re-run this job" in done.stdout.lower(), done.stdout
        assert f"moved   : quay.io/ephico2real/group-sync-dashboard:latest -> {self.NEW}" in done.stdout

    def test_a_read_back_that_cannot_be_made_is_a_red_run_naming_the_image_and_the_remedy(self, tmp_path: pathlib.Path) -> None:
        """The read-back is a second registry call after the copy: when it fails on its own (the
        registry stopped answering), the tag has already been moved and the run must say which image
        it cannot vouch for and what to do — not only skopeo's stderr under `set -e` (review of #530,
        OB2: measured, exit 1 with no `::error::` for either image). The earlier `moved   :` line
        stands, as for a refused copy."""
        done, log = self._run(tmp_path, unreadable="group-sync-dashboard-report:latest")
        assert done.returncode == 1, done.stdout + done.stderr
        assert "::error::quay.io/ephico2real/group-sync-dashboard-report:latest was copied from" in done.stdout, done.stdout
        assert "could not be read back" in done.stdout and "re-run this job" in done.stdout.lower(), done.stdout
        assert f"moved   : quay.io/ephico2real/group-sync-dashboard:latest -> {self.NEW}" in done.stdout
        assert len([ln for ln in log if ln.startswith("skopeo copy")]) == 2, log

    # T425-7
    def test_the_latest_job_holds_only_read(self) -> None:
        assert self._job()["permissions"] == {"contents": "read"}
        assert _jobs(PUBLISH)["publish"]["permissions"] == {"contents": "read"}

    def test_the_docs_say_what_latest_names(self) -> None:
        releasing = (REPO / "docs" / "RELEASING.md").read_text()
        design = (REPO / "docs" / "DESIGN_supply_chain.md").read_text()
        assert "**D11 — `:latest` is the newest signed `main` build" in design
        assert "│ latest               │" in releasing
        assert "latest  job" in releasing
```

### Block 4 — `local-development/tests/test_chart_image_reference.py`: T425-6

<!-- block: local-development/tests/test_chart_image_reference.py | edit -->
```python
    assert "skopeo inspect" in out, (
        "the failure must say how to obtain a correct digest, or it only says 'no'"
    )
```

```python
    assert "skopeo inspect" in out, (
        "the failure must say how to obtain a correct digest, or it only says 'no'"
    )


def test_the_default_render_never_resolves_latest() -> None:
    """#425 moves `:latest` of both images on every publish from `main`, which is safe only because
    the chart never resolves it: with `image.tag` and `reporting.image.tag` empty, every container
    of either image renders `:<appVersion>`. A default that fell back to `:latest` would make each
    merge to `main` the image a cluster pulls on its next container creation (`imagePullPolicy:
    Always`), with no chart change to show for it."""
    ok, out = render()
    assert ok, out
    own = (repository(), yaml.safe_load((CHART / "values.yaml").read_text())["reporting"]["image"]["repository"])

    def images(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "image" and isinstance(value, str):
                    yield value
                else:
                    yield from images(value)
        elif isinstance(node, list):
            for item in node:
                yield from images(item)

    rendered = [image for doc in yaml.safe_load_all(out) if doc for image in images(doc)]
    ours = [image for image in rendered if image.rsplit(":", 1)[0] in own]
    assert {image.rsplit(":", 1)[0] for image in ours} == set(own), rendered
    # Only the chart's own two images: the S3 tool image's fallback tag is the operator's choice of tool, not
    # one of the images #425 moves (backup-offsite.yaml), and it does not render by default.
    assert all(image.endswith(f":{app_version()}") for image in ours), ours
```

### Block 5 — `local-development/build-and-push-external.sh`: the disaster-recovery path does not move `:latest`

<!-- block: local-development/build-and-push-external.sh | edit -->
```bash
# to the job that signs it. --release-tags therefore needs skopeo, which ships beside podman.
#
```

```bash
# to the job that signs it. --release-tags therefore needs skopeo, which ships beside podman.
#
# `:latest` IS NOT MOVED HERE. publish.yml's `latest` job moves it once the signature of the run's
# digest has been read back (#425); this script signs nothing, so it leaves `:latest` where the last
# green publish put it.
#
```

### Block 6 — `docs/DESIGN_supply_chain.md`: decision D11

<!-- block: docs/DESIGN_supply_chain.md | edit -->
```markdown
unknown reference to an empty string rather than an error.

## What this does not do
```

```markdown
unknown reference to an empty string rather than an error.

**D11 — `:latest` is the newest signed `main` build of each image, moved after its signature (#425).**
The `latest` job copies, for both images, the digest the `publish` job recorded to `:latest` with the
release aliases' `skopeo copy --all --preserve-digests`, and reads the name back, refusing a mismatch
(`.github/workflows/publish.yml#Copy each digest to :latest, and read it back`). It is a job of its own
that needs `attest`, so `:latest` never names a digest before its signature and SBOM attestation have
been read back; the release aliases, by contrast, move inside `publish` before signing (D10). It runs on
`refs/heads/main` only (D9), after a green `publish` that pushed both images, and after a green `attest`
unless `SUPPLY_CHAIN_SIGNING` is `false`: then it follows `publish` alone and `:latest` is as unsigned
as the rest of that run (D8). Nothing in this repository resolves `:latest` — the chart deploys
`:<appVersion>` (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.image`) — so moving it on every
merge changes no cluster, which is why the rule that keeps `:<appVersion>` still between releases does
not apply to it. The disaster-recovery scripts do not move it: they have no signature to wait for.
Two limits, stated: the two copies are two writes, so a failure between them leaves the dashboard's
`:latest` one build ahead of the report's until the job is re-run (the run is red and names the image);
and a re-run of an older run's `latest` job moves `:latest` back to that run's digests, because a
re-run keeps its run's commit and job outputs — re-running the newest green run's `latest` job puts it
right (`docs/RELEASING.md#What can go wrong, and what it looks like`).

## What this does not do
```

### Block 7 — `docs/HELM_DOWNLOAD_AND_INSTALL.md`: `:latest` verifies like any name of a signed digest

<!-- block: docs/HELM_DOWNLOAD_AND_INSTALL.md | edit -->
```markdown
mirror copies them with `oras cp --recursive` (or re-signs at the destination), then verifies there.
```

```markdown
mirror copies them with `oras cp --recursive` (or re-signs at the destination), then verifies there.

`:latest` is one more name for a signed digest, of either image: after every green publish on `main` it
is copied from the digest that run signed, once the signature has been read back
(`DESIGN_supply_chain.md#D11`), so the command above with `:latest` in place of `:0.15.0-<sha>` verifies
the newest `main` build. It is not a release, and the chart never resolves it.
```

### Block 8 — `docs/RELEASING.md`: the publish flow draws the `latest` job

<!-- block: docs/RELEASING.md | edit -->
```text
   attest  job   cosign sign (keyless) · SBOM attached · SLSA          SUPPLY_CHAIN_SIGNING
                 provenance in GitHub's store — each read back
                 before the run is green
```

```text
   attest  job   cosign sign (keyless) · SBOM attached · SLSA          SUPPLY_CHAIN_SIGNING
                 provenance in GitHub's store — each read back
                 before the run is green
   latest  job   :latest of both images -> this run's digests, by      main only; after attest,
                 skopeo copy, then read back. Never what the chart     or after publish when
                 resolves (DESIGN_supply_chain.md D11)                 signing is off
```

### Block 9 — `docs/RELEASING.md`: four tags

<!-- block: docs/RELEASING.md | edit -->
```markdown
## Three tags, and why there are three
```

```markdown
## Four tags, and why there are four
```

### Block 10 — `docs/RELEASING.md`: the `latest` row of the tag table

<!-- block: docs/RELEASING.md | edit -->
```text
  │ <chartVersion>       │ release   │ (never a build)  │ deploy?"                    │
  └──────────────────────┴───────────┴──────────────────┴─────────────────────────────┘
```

```text
  │ <chartVersion>       │ release   │ (never a build)  │ deploy?"                    │
  ├──────────────────────┼───────────┼──────────────────┼─────────────────────────────┤
  │ latest               │ moves on  │ every green run  │ a human or a pipeline that  │
  │                      │ EVERY     │ on main, once its│ wants the newest main build.│
  │                      │ publish   │ signature is read│ NEVER what the chart        │
  │                      │ on main   │ back (#425)      │ resolves.                   │
  └──────────────────────┴───────────┴──────────────────┴─────────────────────────────┘
```

### Block 11 — `docs/RELEASING.md`: what can go wrong with `:latest`

<!-- block: docs/RELEASING.md | edit -->
```markdown
| the first publish of a NEW image name (the report image was the first, 0.18.0) is red at its push, or green and then every fresh install pulls `unauthorized` for that image | quay.io creates a repository on push only if the pushing account may create one in the namespace, and creates it **private**; the chart pulls anonymously | create the repository in the quay.io UI **public**, grant the robot account write on it, then publish. Measured 2026-09-11: `group-sync-dashboard-report` did not exist before 0.18.0's first publish |
```

```markdown
| the first publish of a NEW image name (the report image was the first, 0.18.0) is red at its push, or green and then every fresh install pulls `unauthorized` for that image | quay.io creates a repository on push only if the pushing account may create one in the namespace, and creates it **private**; the chart pulls anonymously | create the repository in the quay.io UI **public**, grant the robot account write on it, then publish. Measured 2026-09-11: `group-sync-dashboard-report` did not exist before 0.18.0's first publish |
| the publish run is red at "Copy each digest to :latest, and read it back" | the registry refused the copy (the `::error::` names the image, and says that any `moved   :` line above it stands), `:latest` resolved to another digest afterwards (the `::error::` names both digests), or the read-back could not be made (the `::error::` names the image and the digest it was copied from) | the immutable tags, the aliases and the signatures are already published; at most the dashboard's `:latest` has moved ahead of the report's. Re-run the failed `latest` job; it moves both images again |
| `:latest` names an older build than the newest green publish on `main` | an older run's `latest` job was re-run after a newer run had moved the tag: a re-run copies its own run's digests | re-run the `latest` job of the newest green publish run on `main` |
```

### Block 12 — `docs/CHANGELOG.md`: the entry under Unreleased

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

```

```markdown
## Unreleased

- **`:latest` names the newest signed `main` build of both images (#425, SPEC_E9, app 2.4.0, chart 0.61.2).** On
  every green publish from `main`, a new `latest` job in `publish.yml` copies the digests that run pushed as
  `<appVersion>-<sha>` to `:latest` of `group-sync-dashboard` and `group-sync-dashboard-report`, once `attest` has
  signed them and read the signatures back (straight after `publish` when `SUPPLY_CHAIN_SIGNING` is `false`), with
  the release aliases' server-side `skopeo copy --all --preserve-digests`, and reads each name back: a mismatch is a
  red run. The chart never resolves `:latest`, so no cluster changes; the immutable tags, the `:<appVersion>` alias rule and the `publish` job's
  `contents: read` are unchanged. `docs/RELEASING.md` gains the fourth tag, `DESIGN_supply_chain.md` decision D11.

```
