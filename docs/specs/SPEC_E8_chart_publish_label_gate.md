# SPEC E8 — the chart-publish label gate: `helm.yaml` copies an image to the chart-version tag only when both default images carry the chart's appVersion, and never over another application's alias; a pull request may not number the chart like a released application (#410, PR A)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build step 7 (#410), **PR A only**: the `helm.yaml` label gate, with the `ci.yml` pull-request check that closes `publish.yml`'s write of the same tag. PR B (#430, build once and promote, SPEC_P1 on `feat/410-promote-release-branch`) is held by the operator and is not specified here |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; its own PR and its own review, carried by Epic E's release, milestone 3.0.0) |
| Version on release | no version change (workflow, tests and docs only) |
| Version note | The change touches `.github/workflows/helm.yaml`, `.github/workflows/ci.yml`, `local-development/tests/test_supply_chain.py`, `docs/guides/RELEASING.md`, `docs/design/DESIGN_supply_chain.md` and `docs/CHANGELOG.md`. None is in `publish.yml`'s `on.push.paths` (the allowlist at `.github/workflows/publish.yml#ONLY WHEN SOMETHING THAT GOES INTO THE IMAGE CHANGED` names twelve paths: `local-development/gsd/**`, `pyproject.toml`, `README.md`, `uninstall-lists.py`, `image-proof.py`, `Containerfile`, `.containerignore`, `build-and-push-external.sh`, `Containerfile.report`, `report-image-proof.py`, `build-and-push-report.sh`, and `publish.yml` itself), so `ci.yml`'s "App image changes bump the app version" asks for no application bump; and none is under `charts/`, so "Chart changes bump the chart version" asks for no chart bump. The issue's Versions box says the same for PR A. SPEC_E5's rule for specs that claim the same numbers does not apply: this spec claims none |
| Issue | [#410](https://github.com/ephico2real2/group-sync-dashboard/issues/410) |
| Status | released |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code, from the issue's body of 2026-10-01 and its "Decisions and corrections (2026-10-01)", the epic (#385) and #414's merged guard. Measured on origin/main `f1423143` (application 2.0.0, chart 0.59.25): skopeo 1.13.3 (the version the `ubuntu-latest` runner carries) and 1.22.3 run in throwaway containers, read-only against quay.io, and quay's tag API read anonymously. §7's blocks were cut from a copy of `f1423143` with the design implemented and proved against a clean tree (§4.3). Revised the same day on OB2's review of `d5d14f5e` (Orchestrator's notes, "The review of `d5d14f5e`"): Blocks 12 to 18 are OB2's, the second writer's fix moved into this spec, and the branch merged origin/main `31e4f037` (SPEC E3, E6, E7), where every block was proved again (§4.3) |

## How to read this spec

**The point in one sentence:** before the chart workflow copies `group-sync-dashboard:<appVersion>` to the
chart-version tag, it reads which application the image says it is, for the dashboard and the report image and for
every Linux image behind each tag, and stops with a red run if that is not the chart's `appVersion`; it also stops
rather than copy onto a tag that is another application's own alias. And because `publish.yml` writes the chart-version tag too, a
pull request may not give the chart a version whose tag is already a released application's (`ci.yml`).

Why it matters, in two lines. A tag is a name, and a name can point at the wrong build: on quay `:0.39.0` was
application 0.24.0 for days before application 0.39.0 existed, and today's step only asks whether the tag exists.
And chart versions and application versions share one list of tags, so a chart numbered 1.0.0 would overwrite
application 1.0.0's tag.

§1 is the mandate and what is left out. §2 is the research: each source quoted with the line it settles, and each
measurement with its command and output. §2a lists the other designs research turned up and why each was not taken,
then maps every external fact the design relies on to the line of this repository that behaves accordingly. §3 is
the design, rule by rule, with the safety property stated as a budget over the system. §4 maps each test case to a
test and shows each one failing before the change for the stated reason. §5 is what the implementing pull request
checks after it merges (there is no cluster step). §6 is what a release engineer sees and what it costs. §7 is the
whole change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E8_chart_publish_label_gate.md . --apply

Line citations into the code at `f1423143` are written as plain text, file:line, to keep them apart from the
maintained `path#anchor` citations. This spec's own row in the index moves through the lifecycle by the
orchestrator's hand; no block touches it.

## Orchestrator's notes

Decisions made on "easy to manage, best practice", and one departure from the mandate (note 1), accepted in
review. Nothing is left open for the operator.

1. **The tool: skopeo, not oc — a departure from the mandate's "the same tool", with the evidence.** The mandate
   asks the gate to reuse #414's reading of the label, "the same tool and the same comparison". The comparison is
   reused exactly; the tool cannot be without adding one to the publishing job:
   - `release-crc.sh` reads the label with `oc image info --filter-by-os='linux/.*' --show-multiarch -o json`
     (local-development/release-crc.sh:258-262), because a workstation has `oc` (measured here: `oc` 4.22.13 at
     `/opt/homebrew/bin/oc`, `skopeo not found`).
   - The `ubuntu-latest` runner has the opposite: its image README lists `Skopeo 1.13.3` and `Python 3.12.3`, and no
     `oc` or OpenShift client at all (§2.3). The step already uses skopeo for the existence check and the copy.
   - Installing `oc` in the `release` job (a download from mirror.openshift.com, or
     `redhat-actions/openshift-tools-installer`) adds a fetched binary to a job holding `contents: write` and
     `id-token: write`. §2a weighs it.

   What IS reused, and held equal by T410-16: the label key, the rule "every Linux image behind the tag", the Python
   expression that joins the labels and the comparison with `appVersion`, character for character; the walker that
   reads `reporting.image.tag`, token for token; the pin rule; and the refusal's words, `is application X, not Y
   (#410)`. So one reading in two places, fetched by the tool each place carries. Accepted as written in OB2's
   review.
2. **The second writer of `:<chartVersion>`, closed in the pull request (option ii; finder OB2, decided by the
   orchestrator).** §3.4's guard covers `helm.yaml`'s copy. But `build-and-push-external.sh --release-tags`, which
   `publish.yml` runs on every application release for both images, also copies the release to `:<chartVersion>`
   (local-development/build-and-push-external.sh:257-272). Measured on quay: `group-sync-dashboard-report:0.59.24`
   was written at 08:39:13 on 2026-09-30, two seconds after `:2.0.0`, by that script (`helm.yaml` never writes the
   report repository), and the dashboard's `:0.59.24` has two history entries, 08:38:42 (publish) and 08:47:38
   (`helm.yaml`), one digest (§2.4). So on a release merge whose chart version equals a released application
   version, `publish.yml` overwrites that alias whatever `helm.yaml` refuses. Three ways to close it were weighed:
   - **(i) the same guard in `build-and-push-external.sh`.** Rejected: it closes one writer only, at release time
     (after the merge), and the script is an image input, so it costs an application MINOR.
   - **(iii) refuse a chart version found in the version history (git tags, CHANGELOG headings).** Refuted by
     measurement: the 104 git tags on origin are 98 `group-sync-dashboard-<chart version>`, 4
     `openshift-grafana-<version>` and 2 checkpoints, so no application version; and 82 of the 123 bare-semver tags
     on quay are named by no CHANGELOG heading, among them the application aliases 1.2.0 to 1.21.0 (re-measured
     here by every `x.y.z` on a `## ` line; OB2 counted 84).
   - **(ii) a pull-request check in `ci.yml`, chosen.** The `version-bump` job (pull requests only) reads
     `:<chartVersion>`'s own label and refuses a chart version whose tag is labelled with that version, that is,
     the application's alias. Only "manifest unknown" means free; any other failure is a red check (Block 14,
     T410-22 to T410-26). It closes both writers before the version reaches `main`. Measured against quay with
     skopeo 1.13.3 (§4.3): chart 0.59.25 passes (`:0.59.25` is application 2.0.0), chart 1.0.0 is refused,
     chart 0.60.0 is free.

   In this spec, applied in the same implementing pull request as Blocks 1 to 11: the hole is #410's and the blocks
   are small and tested hermetically. `ci.yml` is not in `publish.yml`'s paths, so the version stays "no version
   change". What it does not cover: a chart version equal to an application version not released yet (the tag is
   absent, so free); that is the reverse direction the 0.37.0 history shows, where the application release later
   moves the tag to itself (§2.4).
3. **Test IDs.** The issue's T410-1 to T410-6 and T410-10 keep their IDs. T410-2 and T410-3 stay pure regression
   guards that pass on `main`, as the issue says; the new log lines they might have asserted have their own tests.
   Research added T410-11 to T410-19, and OB2's review T410-20 to T410-26 (§4.1). Suggest the issue's table gains
   them.
4. **Correction to the issue's T410-10 level.** The issue names `tests/test_docs_citations.py`; that test proves
   that citations resolve, not that a row exists. The row check is a test in `tests/test_supply_chain.py`.
5. **The dashboard's label is read at the digest, not the tag.** The step already reads `:<appVersion>`'s digest
   and compares the copied alias with it. Reading the label at `@<that digest>` binds the three: the bytes checked,
   the digest compared, the alias written. A tag that moves between the reads ends in today's digest-mismatch red
   run, never in a pass (§3.2).
6. **Unreachable is not absent, at both probes.** Before the copy the step reads `:<chartVersion>`. Only the
   registry's `manifest unknown` lets the copy create the tag; any other failure is a red run (§3.4). The same rule
   holds for the existence check of `:<appVersion>` (Block 19, the review of PR #529). Only `manifest unknown` prints
   the never-published remedy; any other failure is a red run that says "cannot tell" and asks for a re-run. Measured with skopeo
   1.13.3 and 1.22.3: the text is the same, the exit status is not (1 and 2), so the text is the signal (§2.5).
7. **A missing report image becomes a red run** (T410-14). Today the step never looks at the report image. The
   issue's decision 1 makes the gate cover it, and `release-crc.sh` already refuses a missing one; a chart whose
   report pod would sit in `ImagePullBackOff` is not published.
8. **Digest pins are not resolved**, as in `release-crc.sh` and in today's step: `image.digest` and
   `reporting.image.digest` are empty in the shipped `values.yaml`, and a pin is the operator's choice. Stated, not
   changed.
9. **The runner changes in November 2026.** The Ubuntu 24.04 README's banner: "`ubuntu-latest` label will use Ubuntu
   26.04 in November 2026". The 26.04 image lists `Skopeo 1.21.0-dev` and `Python 3.14.4`; the flags used
   (`inspect --raw`, `--config`, `--no-tags`, `--format`) were measured on 1.13.3 and 1.22.3 (§2.2, §2.5).
10. **Nothing published is deleted or retagged.** The gate reads and refuses; its messages say never to retag or
    delete by hand (the issue's "Must not change").

### The review of `d5d14f5e` (OB2), decided by the orchestrator on 2026-10-01

OB2 approved the spec and supplied Blocks 12 to 18. Each decision is applied in §7 and measured again (§4.3).

- **Accepted: Blocks 12 and 13 (finder OB2).** `_push` takes `platforms`, so a child may be non-Linux or carry no
  label. T410-20 holds note 5 (the dashboard's label is read at `@<SOURCE_DIGEST>`, never at the tag); T410-21 holds
  the Linux filter (BuildKit's `unknown/unknown` attestation child skipped, a Windows child skipped, an index with
  no Linux image refused). Neither property had a test: mutants M5 and M6 (§4.3) passed every test of `d5d14f5e`.
  The harness comment gains one line: `_push` with one version writes a bare manifest, so an index with no Linux
  child needs two children.
- **Accepted: Blocks 14 to 18, option (ii), inside this spec (finder OB2; the orchestrator moved it from a separate
  PR C into this one).** Note 2 is rewritten. The five tests take T410-22 to T410-26.
- **Accepted as written: note 1** (skopeo, not `oc`).
- **Corrected: §2.6's line** in `workflow-syntax.md` is 967, not 963 (re-read with `curl -s <raw> | nl -ba`).
- **Rebased:** origin/main `31e4f037` merged in (SPEC E3 #512, E6 #513, E7 #514); E8 is the forty-fifth index row,
  excluded by its id and pinned to #410.

### The review of PR #529 (OB2, in Codex's seat), decided by the orchestrator on 2026-10-02

OB2 reviewed head `c825182c` against the real registry: it drove the lifted steps through a read-only skopeo 1.13.3
with injected faults, and approved. Its recommended fix is accepted and applied as Blocks 19 to 23; its four
observations are recorded and change nothing. The measurements below are OB2's.

- **Accepted: F1, Blocks 19 to 23 (finder OB2).** The existence check of `:<appVersion>` (`2>/dev/null`) read an
  unreachable registry as a missing image. Run with the real skopeo and `REGISTRY=quay.invalid`, it exited 1 and
  printed `…:2.3.0 does not exist … the application release was never published …
  ./build-and-push-external.sh --release-tags`. So a quay outage prescribed the disaster-recovery push for an image
  that exists. The defect is older than this spec, but it sits in the step this spec owns, and note 6 had covered
  the second probe only.
  - The fix reuses the alias guard's `probe_err` and `grep -qi 'manifest unknown'` (Block 19). Only that text
    prints the never-published remedy; any other failure is "cannot tell … re-run".
  - There is one temporary file and one trap (Block 20 removes the alias guard's pair). A second `trap … EXIT` would
    replace the first and leak the file.
  - The fix also adds T410-27 (Block 21), a row in `docs/guides/RELEASING.md` (Block 22) and one sentence in the
    CHANGELOG (Block 23).
  - Measured after the fix: `REGISTRY=quay.invalid` exits 1 with `cannot tell whether quay.invalid/…:2.3.0 exists
    … no such host … Re-run this workflow once the registry answers.` Today's state still reaches the login with
    the same calls, and an absent `:2.4.0` keeps the never-published message.
  - §3.1, §3.6, §4.1 and note 6 are updated to match.
- **Recorded, not changed: O1 to O4.**
  - O1. `ci.yml`'s registry read runs on every pull request, docs-only ones included. `version-bump` therefore
    depends on quay answering: an outage or a 429 turns open pull requests red until they are re-run. It is one
    anonymous read, measured at 0.7 to 1.9 s. §3.7 accepts this.
  - O2. Six early application versions (0.6.0, 0.7.0, 0.8.0, 0.10.0, 0.11.0, 0.12.0) were released, but each bare
    tag already names another build. The check passes them, as §3.7's rule says: no alias is left to protect.
  - O3. `ci.yml` reads the dashboard repository only. The report repository's 42 own-alias versions are a subset of
    the dashboard's 51, so no version escapes the check today.
  - O4. A report read that fails for a reason other than `manifest unknown` keeps §3.3's annotation "is not in the
    registry, or cannot be read". skopeo's own reason is on stderr, in the run log.

## 1. The mandate, and what is out of scope

**In scope (PR A of #410).** Items 1 to 3 in `.github/workflows/helm.yaml`'s step "Label the image this chart
version deploys"; item 4 in `.github/workflows/ci.yml`:

1. Before `${REPO}:${SOURCE}` is copied to `:${CHART_VERSION}`, read the `org.opencontainers.image.version` label of
   every Linux image behind the dashboard's and the report image's `:<appVersion>` (an image whose tag is pinned in
   `values.yaml` is not checked), and refuse with a red run that names both versions when it is not `appVersion`.
   Nothing is copied and chart-releaser does not run. (Issue: What must be accomplished, A.1–A.3; decisions 1–3.)
2. Refuse to copy over a `:<chartVersion>` tag that already exists and is an application-version alias.
   (The mandate; the issue's "Where this stands": "a chart version that equals an existing application version
   would copy over that application alias".)
3. Keep what works: a matching label copies and compares digests as today; a pinned `image.tag` is copied as
   pinned; a missing image is red with today's remedy; a run without registry credentials warns and exits 0 before
   any check (decision 3).
4. In `.github/workflows/ci.yml`'s pull-request `version-bump` job, refuse a chart version whose tag on the
   dashboard repository is already that application's alias, which closes `publish.yml`'s write of
   `:<chartVersion>` too (Orchestrator's note 2).
5. The tests (T410-1 to T410-6, T410-10, and §4.1's additions), `docs/guides/RELEASING.md`'s two troubleshooting rows,
   the corrected sentence in `docs/design/DESIGN_supply_chain.md`, and the CHANGELOG entry.

**Out of scope.**

- **PR B, #430** (build once and promote: `promote.yml`, the `release` branch, the lab Application tracking it,
  `release-crc.sh --argocd main` refused). Held by the operator (epic open question 2). Not designed here, and
  branch `feat/410-promote-release-branch` is not touched.
- `publish.yml` and `build-and-push-external.sh`: the issue's "Must not change" keeps the alias rule; their write
  of `:<chartVersion>` is closed upstream, in the pull request (Orchestrator's note 2).
- `release-crc.sh`: #414's guard is the reference this gate copies, unchanged.
- Labelling the report image by chart version (`helm.yaml` still copies into the dashboard repository only).
- Any change to `charts/`, any application or chart version, any cluster or lab change.

## 2. Research, measured

Every source was fetched on 2026-10-01. Upstream lines are cited from `curl -s <raw-url> | nl -ba`.

### 2.1 What the label means: the OCI image spec

- `annotations.md`, line 27 (https://github.com/opencontainers/image-spec/blob/main/annotations.md):
  "**org.opencontainers.image.version** version of the packaged software". Settles that this key, and no tag, is
  the image's own statement of which application it is.
- `config.md`, lines 178-181: "**Labels** _object_, OPTIONAL … This field contains arbitrary metadata for the
  container. This property MUST use the annotation rules." Settles where it lives: the image config's
  `config.Labels`, which is what `skopeo inspect --config` returns and `oc image info` nests under `.config.config`.
- `image-index.md`, lines 52-65: an index entry's `platform` has a REQUIRED `os` "values listed in the Go Language
  document for GOOS". Settles the filter: an entry is a Linux image when `platform.os == "linux"`, which is what
  `oc`'s `--filter-by-os='linux/.*'` matches.

### 2.2 How skopeo answers, and where it would mislead

- skopeo-inspect(1) at v1.13.3, lines 14-16
  (https://github.com/containers/skopeo/blob/v1.13.3/docs/skopeo-inspect.1.md): "the top-level manifest
  (**Digest**), and a per-architecture/OS image matching the current run-time environment (most other values)".
  Lines 31-33: "**--config** Output configuration in OCI format". Lines 57-60: "**--raw** Output raw manifest or
  config data depending on --config option."
- Measured with skopeo 1.13.3 (`podman run --rm quay.io/skopeo/stable:v1.13.3 …`) on quay.io/skopeo/stable:v1.13.3,
  an OCI index of linux/ppc64le, linux/s390x, linux/amd64 and linux/arm64:

      inspect --raw --config docker://quay.io/skopeo/stable:v1.13.3          -> linux arm64   (the VM's platform)
      inspect --raw --config docker://quay.io/skopeo/stable@<s390x digest>   -> linux s390x
      inspect --no-tags --format '{{.Digest}}' …:v1.13.3                     -> sha256:4853591bd1d2…
      sha256 of `inspect --raw` …:v1.13.3                                    -> sha256:4853591bd1d2…

  So `--config` on a tag that is a list reads one child, the runner's (the bypass SPEC_P1's round-1 F1 named), and
  a child read by digest reads that child. The `{{.Digest}}` the step already reads is the digest of the top-level
  manifest, the same bytes `--raw` returns.
- Measured on this repository's images with the reader §3.2 specifies, run against quay with skopeo 1.13.3:

      dashboard @<:2.0.0's digest>  -> [2.0.0]        report :2.0.0  -> [2.0.0]
      dashboard :0.39.0             -> [0.24.0]       dashboard :1.0.0 -> [1.0.0]
      quay.io/skopeo/stable:v1.13.3 -> [1.13.3]       (four Linux children read, one label)
      report :0.59.25               -> "… reading manifest 0.59.25 in quay.io/ephico2real/group-sync-dashboard-report: manifest unknown", rc=1

  Today's images are single manifests (`inspect --raw` of `:2.0.0`: `application/vnd.oci.image.manifest.v1+json`;
  quay's tag API marks none of the 349 and 173 active tags `is_manifest_list`), so a list is a case the gate must
  handle, not one it meets today.

### 2.3 What the runner carries

- https://github.com/actions/runner-images/blob/main/images/ubuntu/Ubuntu2404-Readme.md (image 20260920.314.1):
  line 28 "Python 3.12.3", line 99 "Skopeo 1.13.3", line 86 "Kubectl 1.37.0"; a search of the whole file for
  `openshift`, `oc `, `crane` and `regctl` finds nothing. Line 3: "`ubuntu-latest` label will use Ubuntu 26.04 in
  November 2026".
- …/Ubuntu2604-Readme.md (image 20260920.143.1): line 27 "Python 3.14.4", line 88 "Skopeo 1.21.0-dev".
- Settles: skopeo and python3 are on the runner now and after the move; `oc` is on neither.

### 2.4 The registry today (quay.io, read-only)

Commands: quay's tag API (`/api/v1/repository/ephico2real/<repo>/tag/?onlyActiveTags=true`, paged), the tag history
(`?specificTag=<t>&onlyActiveTags=false`), skopeo 1.13.3 `inspect`, and `release-crc.sh`'s own reader
(`oc image info … --filter-by-os='linux/.*' --show-multiarch -o json` piped to its Python).

| Fact | Measured |
|---|---|
| Active tags | dashboard 349 (123 bare semver, 0.5.0 to 2.0.0); report 173 (73 bare semver, 0.18.0 to 2.0.0) |
| Application aliases above the chart's 0.59.25 | 1.0.0 to 1.21.0 and 2.0.0 in both repositories: 23 each; `:1.0.0`, `:1.21.0`, `:2.0.0` read back labelled 1.0.0, 1.21.0, 2.0.0 in both |
| The stale tag the issue found | `:0.39.0` is `sha256:b53347cf9421…`, labelled `0.24.0`, revision `a0743ef3b0`, active since 2026-09-20 08:20:38 |
| The reverse collision, as it happened | `:0.37.0` was `b53347cf9421…` (the chart-version label on application 0.24.0) from 2026-09-20 02:44:35 until 2026-09-27 00:02:40, when the application 0.37.0 release moved it to `62e231178a3a…` |
| Two writers of `:<chartVersion>` | dashboard `:0.59.24`: entries at 08:38:42 and 08:47:38 on 2026-09-30, both `fc8a5a982863…`; report `:0.59.24` (`712350d2c1b4…`) at 08:39:13, two seconds after report `:2.0.0` (08:39:11) |
| Today's pair | `:2.0.0`, `:0.59.24` and `:0.59.25` are all `fc8a5a982863…`, labelled 2.0.0; report `:0.59.25` is `manifest unknown` |

Red Hat Quay, "Working with tags"
(https://docs.redhat.com/en/documentation/red_hat_quay/3.8/html/use_red_hat_quay/working_with_tags): "To revert
the tag to a previous image, find the history line where your desired image was overwritten, and click on the
Restore link", and "By default, that value is 14 days." Settles that an overwritten alias is recoverable only by
hand and only for the Time Machine window; the gate prevents the overwrite instead.

### 2.5 What "the tag does not exist" looks like

- OCI distribution spec, line 179 (https://github.com/opencontainers/distribution-spec/blob/main/spec.md): "If
  the manifest is not found in the repository, the response code MUST be `404 Not Found`." Line 897: "`code-7` |
  `MANIFEST_UNKNOWN` | manifest unknown to registry".
- Quay's own answer, anonymous token, `GET /v2/ephico2real/group-sync-dashboard/manifests/1.0.0-does-not-exist`:
  `404` and `{"errors":[{"code":"MANIFEST_UNKNOWN","detail":{},"message":"manifest unknown"}]}`.
- containers/image v5.26.2 (the version skopeo 1.13.3's go.mod pins), docker/docker_client.go line 891:
  `fmt.Errorf("reading manifest %s in %s: %w", tagOrDigest, ref.ref.Name(), registryHTTPResponseToError(res))`;
  docker/errors.go lines 87-93 print the registry's message alone when it is the code's default.
- Measured, the same missing tag and an unresolvable host:

      skopeo 1.13.3  …:1.0.0-does-not-exist  -> "reading manifest 1.0.0-does-not-exist in …: manifest unknown"   rc=1
      skopeo 1.13.3  quay.invalid/…:1.0.0    -> "pinging container registry quay.invalid: … no such host"          rc=1
      skopeo 1.22.3  …:1.0.0-does-not-exist  -> "reading manifest 1.0.0-does-not-exist in …: manifest unknown"   rc=2

- Settles: "absent" and "could not ask" share an exit status but not the text; `manifest unknown` is the
  registry's word for absent. A registry that phrases it differently makes the gate refuse, the safe direction.

### 2.6 How GitHub Actions ends the run

- `data/reusables/actions/supported-shells.md`, line 5 (https://github.com/github/docs): `bash` runs
  `bash --noprofile --norc -eo pipefail {0}`.
- `workflow-syntax.md`, line 967: "By default, fail-fast behavior is enforced using `set -e` for both `sh` and
  `bash`. When `shell: bash` is specified, `-o pipefail` is also applied".
- `expressions.md`, line 322: "A default status check of `success()` is applied unless you include one of these
  functions." The steps after the label step ("Run chart-releaser" has no `if`; the two attestation steps' `if`
  names no status function) therefore do not run after it fails.
- `workflow-commands.md`, "Setting an error message": `::error::{message}` "Creates an error message and prints
  the message to the log." The step's existing refusals already use it, one line each.

### 2.7 This repository, at `f1423143`

- `helm.yaml` today: the credentials check exits 0 with a warning (.github/workflows/helm.yaml:158-163); the
  existence check reads only the digest of `${REPO}:${SOURCE}` (:171-180); the login (:182-183); the copy (:189);
  the digest comparison (:190-195). `REPO` is the dashboard repository only (:156). No label is read.
- `release-crc.sh`'s guard, `local-development/release-crc.sh#published_image_is_the_release`: the
  `reporting.image.tag` walker (:227-245), the loop over both images with their pins (:250-255), the `oc` read and
  the Python join (:258-262), the comparison and the refusal `is application ${version:-unknown}, not
  ${app_version} (#410).` (:269-275). Its multi-arch behaviour is proved with the real `oc` against an on-disk
  index in `local-development/tests/test_release_crc.py#test_argocd_branch_reads_every_linux_image_of_a_manifest_list`.
- The chart resolves both images through `appVersion` when no tag is pinned: `gsd.image`
  (charts/group-sync-dashboard/templates/_helpers.tpl:80) and
  `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.reportImage` (:677).
- The timing the issue records (`reports/2026-09-26_epic-b-release/walk/workflow-times.txt`): on the 0.37.0
  release merge `publish.yml` ran 00:01:34 to 00:04:19 and `helm.yaml` 00:01:34 to 00:10:12. So the label step
  normally runs after the aliases moved; when it does not, the gate turns a silent wrong copy into a red run.
- The issue's T410-1 "fails today" is reproduced by §4's harness on `f1423143`: exit 0 and `labelled:
  quay.io/example/group-sync-dashboard:0.59.25 -> 2.0.0 (sha256:…)` with a stale `:2.0.0`.

## 2a. Alternatives considered

| Option | Source | Cost here | Decision |
|---|---|---|---|
| **A. Read the label with skopeo in the existing step** (this spec) | §2.2, §2.3 | about 40 lines of bash and Python in one step; no new tool, action or permission | **Taken.** The smallest change that meets decisions 1–3; reuses #414's comparison verbatim (Orchestrator's note 1) |
| B. Install `oc` on the runner and run `release-crc.sh`'s command unchanged | runner README (§2.3); `redhat-actions/openshift-tools-installer` (v3.1, 2026-08-25, not archived) | a downloaded binary, or a new third-party action pinned by sha, in the job that holds `contents: write` and `id-token: write`; a second tool beside the skopeo the step already uses | Rejected: a supply-chain addition to the publishing job for a read skopeo already makes |
| C. One shared reader script under `local-development/`, called by both | — | both callers change (`release-crc.sh` too); the script must still call `oc` on a workstation and `skopeo` on the runner, so it shares only the Python both already share | Rejected: more moving parts than a test holding the shared lines equal (T410-16) |
| D. A registry client in Python (`urllib` and the token flow) shared by both | distribution spec | auth, token and proxy handling written by hand: a third reader | Rejected: invents what both tools already do |
| E. Chart-version labels in their own tag form (`chart-0.59.25`) | the issue's second option (2026-09-26) | changes a documented convention (`docs/guides/RELEASING.md`, "Three tags"); `build-and-push-external.sh` writes `:<chartVersion>` too (an image input, an application bump); old tags stay | Rejected by the issue's decision ("the first option … the smallest guard that closes problem 1") |
| F. Refuse at pull-request time a chart version whose tag is already that application's alias (`ci.yml`, read from the tag's label) | OB2's review | about 40 lines in the pull-request-only `version-bump` job; one anonymous registry read per pull request | **Taken as well** (Blocks 14 to 18): it closes `publish.yml`'s write of `:<chartVersion>`, which A cannot reach (Orchestrator's note 2). The same check over version history (git tags, CHANGELOG headings) is refuted there by measurement |
| G. Collision rule "refuse any existing tag at another digest" | — | also refuses today's legitimate relabel of `:<chartVersion>` (T410-13) and a pinned chart on a release merge | Rejected: wider than the defect. Only a tag that IS application `<chartVersion>` is refused |
| H. Collision rule "refuse when the tag name is in the application's version history (git)" | — | needs a list of released versions; misses a hand-pushed alias | Rejected: the registry's own label answers the question directly |

**Reconciliation: each external fact, and the line of this repository that behaves accordingly.**

- *The label is the application's version* (OCI annotations.md:27). Both builds stamp it from pyproject's version:
  `org.opencontainers.image.version="$BUILD_VERSION"` (local-development/Containerfile:185,
  local-development/Containerfile.report:120). The reader returns `2.0.0` for `:2.0.0` and `0.24.0` for `:0.39.0`
  (§2.2), and `release-crc.sh` compares the same key
  (`local-development/release-crc.sh#published_image_is_the_release`, :262).
- *Labels sit in the config's `config.Labels`* (config.md:178-181). The reader wraps each `skopeo inspect --raw
  --config` answer as `{"config": <config>}` so the expression shared with `release-crc.sh`
  (`(i.get("config", {}).get("config", {}).get("Labels") or {})`) reads the same place `oc image info` nests it
  (Block 2).
- *A list's Linux entries carry `platform.os == "linux"`* (image-index.md:62-65). The reader keeps exactly those
  (Block 2), the set `oc`'s `--filter-by-os='linux/.*'` keeps.
- *`--config` on a list answers for the runner's platform* (skopeo-inspect.1.md:14-16, measured §2.2). The reader
  never asks `--config` of a list; it reads each child by digest (Block 2), and T410-5's stub answers a list for
  linux/amd64 so a reader that trusted it would pass the stale arm64 child.
- *`{{.Digest}}` is the top-level manifest's digest* (skopeo-inspect.1.md:14, measured §2.2). The dashboard's label
  is read at `@${SOURCE_DIGEST}`, the value the existing comparison holds the alias to (helm.yaml:190-195).
- *A missing manifest is `404` / `MANIFEST_UNKNOWN`, printed `manifest unknown`* (distribution spec:179, :897;
  docker_client.go:891). The alias guard creates the tag only on that text, `grep -qi 'manifest unknown'` (Block 3).
- *`shell: bash` is `-eo pipefail`, and later steps carry the default `success()`* (supported-shells.md:5;
  expressions.md:322). Every refusal is `exit 1` before the login and the copy (Block 3), so chart-releaser
  (helm.yaml:201) and the two attestation steps (:222, :230) do not run.
- *A pull request's checks run before the merge, and `version-bump` runs on pull requests only*: the job's
  `if: github.event_name == 'pull_request'` (.github/workflows/ci.yml, `version-bump`), so Block 14's step reads
  the registry before the chart version reaches `main`, where `publish.yml` and `helm.yaml` write it. It reads with
  `skopeo inspect --raw --config` on the tag (skopeo-inspect.1.md:31-33, 57-60): on a list that answers for the
  runner's platform (§2.2), which is enough here because no published tag is a list (§2.2) and the full
  every-Linux-image reading stays `helm.yaml`'s.
- *Quay keeps an overwritten tag's history for 14 days and restores it only by hand* (Quay docs). Nothing in the
  change writes before every check has passed; the one write stays today's `skopeo copy` (helm.yaml:189).

## 3. The design

### 3.1 Where: inside the existing step, between the existence check and the login

The step keeps its order and adds two checks before anything is written (decision 3):

    read Chart.yaml and values.yaml                        (today, plus the report pin)
    no registry credentials?  -> warning, exit 0            (today, unchanged)
    does ${REPO}:${SOURCE} exist?  -> no: red run           (today; reads SOURCE_DIGEST)
                                   -> unreachable: red run  ("cannot tell", re-run: Block 19)
    NEW  label gate: both images, every Linux image         -> mismatch or unreadable: red run
    NEW  alias guard: is :<chartVersion> another app's own alias?  -> yes, or cannot tell: red run
    login, copy, read the alias back, compare digests       (today, unchanged)

Reason: every check is a read made with the anonymous access the existence check already uses; nothing is written
until all pass; and a run without credentials behaves exactly as today (T410-17).

### 3.2 The reading

`image_versions <repository> <:tag or @digest>` prints the `org.opencontainers.image.version` label of every Linux
image behind the reference, sorted and joined with `", "`:

1. `skopeo inspect --raw docker://<repository><reference>`: the top-level manifest.
2. A list (it has `manifests`): each entry with `platform.os == "linux"`, read as `<repository>@<entry digest>`. A
   single image: the reference itself.
3. `skopeo inspect --raw --config` on each: the config, wrapped as `{"config": …}` so the joining expression is
   `release-crc.sh`'s, character for character.

A list with no Linux entry prints `""`, which no `appVersion` equals. Any skopeo failure exits non-zero with
skopeo's own message on stderr. For the dashboard, when its tag is not pinned, the reference is `@${SOURCE_DIGEST}`,
the digest just read: the bytes whose label is checked are the bytes the post-copy comparison holds the alias to,
so a tag that moves between reads ends in today's "the alias is not the image" red run, never a pass.

### 3.3 The comparison and the pins

As `release-crc.sh` does it (local-development/release-crc.sh:250-276), for the dashboard (`image.tag`) and the
report image (`reporting.image.tag`, read with `release-crc.sh`'s walker):

- a pinned tag: `image   : <repo>:<pin> (pinned in values.yaml; not checked against appVersion)`, and the other
  image is still checked (T410-3, T410-19);
- unreadable or absent: red, naming the image and the two `--release-tags` commands (T410-14);
- the joined labels are not exactly `appVersion` (another version, a mixed list, or no label): red,
  `<repo>:<appVersion> is application <labels>, not <appVersion> (#410)` (T410-1, T410-4, T410-5);
- otherwise `image   : <repo>:<appVersion> is application <appVersion>`, which is the log line the issue's
  first-release check reads (T410-18).

### 3.4 The alias guard

Chart versions and application versions share each repository's tags (§2.4). Before the copy the step reads
`${REPO}:${CHART_VERSION}`:

| `:<chartVersion>` | What it is | Outcome |
|---|---|---|
| absent (`manifest unknown`) | nothing to overwrite | copied, as today |
| at `SOURCE_DIGEST` | `publish.yml`'s `--release-tags` already wrote it, or a re-run | copied again, unchanged, as today (T410-12) |
| at another digest, labels not containing `<chartVersion>` | an earlier label of this chart version, the convenience tag this step owns | relabelled, as today (T410-13) |
| at another digest, labels containing `<chartVersion>` | **application `<chartVersion>`'s own alias** | **red, nothing copied** (T410-11) |
| unreadable (any other error), or its labels unreadable | cannot tell | red, nothing copied (T410-15) |

"Containing" uses the joined labels, so a list with any child that is application `<chartVersion>` is refused: a
refusal errs toward keeping the alias. The remedy printed is a chart version no application release has used, in a
pull request; never a retag.

### 3.5 Budget over the system

**Writes to the registry by this step: at most one `skopeo copy`, to `${REPO}:${CHART_VERSION}`, per run, and only
after both images' labels equal `appVersion` (or are pinned) and `:<chartVersion>` is absent, at the source's digest,
or not application `<chartVersion>`.** Scope: `helm.yaml`'s step, per workflow run. `publish.yml`'s write of
`:<chartVersion>` (`build-and-push-external.sh --release-tags`) is bounded upstream instead: **no pull request
whose chart version's tag is labelled with that version passes `ci.yml`'s `version-bump` job** (§3.7), so on a
protected `main` neither writer meets an application's alias. Not covered: a hand push, a chart version equal to an
application version not yet released (§3.7), or two `helm.yaml` runs interleaving (no `concurrency` group,
unchanged).

| Situation (the run's registry) | Calls today | Calls after | Copies today | Copies after | Outcome after |
|---|---|---|---|---|---|
| released pair, `:<chartVersion>` absent | 4 | 9 | 1 | 1 | green |
| released pair, `:<chartVersion>` at the same digest | 4 | 9 | 1 | 1 | green |
| stale `:<appVersion>` (another application) | 4 | 3 | 1 | **0** | red |
| list with a stale arm64 child | 4 | 4 | 1 | **0** | red |
| chart 1.0.0 over application 1.0.0's alias | 4 | 8 | 1 | **0** | red |
| no credentials | 0 | 0 | 0 | 0 | warning, exit 0 |

Calls counted from the harness's stub log (§4.3): "after" is the digest read, two reads per image (raw, then one
config per Linux image), the `:<chartVersion>` probe (plus two reads when it exists at another digest), the login,
the copy and the read-back. Every added call is a read. A refusal retries nothing: the run ends, and a re-run is a
person's choice (`workflow_dispatch`, or the next chart merge).

### 3.6 What does not change

`publish.yml`, `build-and-push-external.sh` and the `<appVersion>-<sha>` tags; `ci.yml`'s existing two steps of
`version-bump` and every other job; the step's name, its credentials
condition and its existing messages, except the existence check's, which now tells an unreachable registry
from a missing image (Block 19); the copy command and the digest comparison; chart-releaser and the
attestations; every published tag.

### 3.7 The pull-request check (Block 14; Orchestrator's note 2)

A new step at the end of `ci.yml`'s `version-bump` job (pull requests only, after "A change under charts/ requires a
new Chart.yaml version"), "The chart version is not a released application version":

| `:<chartVersion>` on the dashboard repository | Outcome |
|---|---|
| absent (`manifest unknown`) | passes: the version is free |
| labelled another version (today: `:0.59.25` is application 2.0.0) | passes: the tag is this chart's own label |
| labelled `<chartVersion>`: that application's own alias | **red**, with the remedy: a version no application release has used; never retag or delete |
| any other read failure | **red**: cannot tell |

One anonymous read per pull request (`skopeo inspect --raw --config`), no write, no credential: the repository is
public, as `helm.yaml`'s existence check already relies on. A chart version equal to an application version not
released yet is free here (its tag is absent); when that application is released later, `publish.yml` moves the
tag to the application, the direction the 0.37.0 history shows (§2.4), and `helm.yaml`'s label gate reads the
labels, not the version numbers.

## 4. Tests

### 4.1 One test per case

All in `local-development/tests/test_supply_chain.py`: T410-1 to T410-21 and T410-27 in class
`TestTheChartPublishLabelGate` (Blocks 7, 13 and 21), T410-22 to T410-26 in class `TestTheChartVersionIsNeverAReleasedApplicationVersion` (Block 18).
Each step's `run` is lifted from the parsed workflow and run with `bash --noprofile --norc -eo pipefail` in a tree
carrying the real `Chart.yaml` and `values.yaml`, against a stub `skopeo` that answers from a JSON registry and logs
each call.

| ID | Test | Given | Then | On `f1423143` |
|---|---|---|---|---|
| T410-1 | `test_t410_1_a_stale_dashboard_alias_is_refused_before_anything_is_copied` | `:2.0.0` labelled 0.24.0 | exit 1, `… is application 0.24.0, not 2.0.0 (#410)`, no login, no copy | **fails**: exit 0, copied |
| T410-2 | `test_t410_2_matching_labels_copy_and_compare_the_digest_as_today` | both labelled 2.0.0 | the copy, the alias at the source digest, `labelled:` | passes (regression guard) |
| T410-3 | `test_t410_3_a_pinned_dashboard_tag_is_copied_as_pinned` | `image.tag: "1.4.0"`, the unpinned `:2.0.0` stale | `:1.4.0` copied | passes (regression guard) |
| T410-4 | `test_t410_4_a_stale_report_alias_is_refused` | report `:2.0.0` labelled 1.9.0 | exit 1 naming the report image, no copy | **fails**: exit 0 |
| T410-5 | `test_t410_5_every_linux_image_behind_a_list_carries_the_label` (two cases) | a list, amd64 2.0.0, arm64 2.0.0 or 1.9.0 | green / exit 1 with `is application 1.9.0, 2.0.0` | `every-child` passes; `stale-arm64-child` **fails**: exit 0 |
| T410-6 | `test_t410_6_a_missing_image_is_still_red_with_today_s_remedy` | `:2.0.0` absent | exit 1, today's message and two commands | passes (regression guard) |
| T410-10 | `test_t410_10_the_release_guide_says_what_the_label_refusal_means` | `docs/guides/RELEASING.md` | a row for each refusal | **fails**: no row |
| T410-11 | `test_t410_11_a_chart_version_that_is_an_application_alias_is_never_copied_over` | chart 1.0.0, `:1.0.0` is application 1.0.0 | exit 1, alias untouched | **fails**: copied over it |
| T410-12 | `test_t410_12_a_chart_version_tag_publish_already_made_is_copied_again_unchanged` | `:0.59.25` already at the source digest | copied | passes (regression guard) |
| T410-13 | `test_t410_13_a_chart_version_tag_on_another_build_is_relabelled_as_today` | `:0.59.25` labelled 1.21.0 | relabelled | passes (regression guard) |
| T410-14 | `test_t410_14_a_missing_report_image_is_red_with_the_remedy` | report `:2.0.0` absent | exit 1, the remedy | **fails**: exit 0 |
| T410-15 | `test_t410_15_a_chart_version_tag_that_cannot_be_read_is_not_taken_as_absent` | the `:0.59.25` probe fails with "no such host" | no copy, exit 1, `cannot tell` | **fails**: copied |
| T410-16 | `test_t410_16_the_label_is_read_and_compared_as_release_crc_sh_reads_it` | both files | the joining expression identical; the walker identical token for token; the refusal's words | **fails**: `helm.yaml` has neither |
| T410-17 | `test_t410_17_without_credentials_the_step_still_warns_and_reads_nothing` | no credentials | exit 0, the warning, no registry call | passes (regression guard) |
| T410-27 | `test_t410_27_an_unreachable_registry_is_not_a_missing_image` (OB2, the review of PR #529) | the `:<appVersion>` existence probe fails with "no such host" | exit 1, `cannot tell whether … exists` with the registry's words; no `does not exist`, no `--release-tags`, no login, no copy | **fails** on `c825182c`: the step prints `does not exist` and the `--release-tags` remedy |
| T410-18 | `test_t410_18_the_run_log_names_the_label_compared_for_both_images` | both labelled 2.0.0 | both `is application 2.0.0` lines, read before the copy | **fails**: no such line |
| T410-19 | `test_t410_19_a_pin_on_the_dashboard_leaves_the_report_checked` | dashboard pinned, report stale | exit 1 naming the report | **fails**: exit 0 |
| T410-20 | `test_t410_20_the_dashboard_label_is_read_at_the_digest_the_copy_is_held_to` (OB2) | the released pair | the raw and config reads name `@<SOURCE_DIGEST>`, never `:2.0.0` | **fails**: no label read |
| T410-21 | `test_t410_21_only_linux_children_are_read_as_release_crc_sh_filters_them` (OB2; three cases) | a report index with an `unknown/unknown` attestation child, a Windows child, or no Linux child | green, green, exit 1 `is application unknown` | the two skipped-child cases pass (today copies anyway; they hold the reader's filter, M6); `no-linux-child-refused` **fails**: exit 0 |
| T410-22 | `test_t410_22_the_check_runs_in_the_pull_request_only_job_after_the_bump_check` | `ci.yml` | the step is in `version-bump` (`if: github.event_name == 'pull_request'`), after the bump check | **fails**: no such step |
| T410-23 | `test_t410_23_a_chart_version_that_is_a_released_application_version_is_refused` | chart 1.0.0, `:1.0.0` is application 1.0.0 | exit 1, `chart version 1.0.0 is a released application version` | **fails**: no such step |
| T410-24 | `test_t410_24_a_chart_version_tag_that_is_this_chart_s_own_label_passes` | `:0.59.25` at application 2.0.0's digest | exit 0 | **fails**: no such step |
| T410-25 | `test_t410_25_an_absent_tag_is_a_free_version` | `:0.59.25` absent | exit 0, `the chart version is free` | **fails**: no such step |
| T410-26 | `test_t410_26_unreachable_is_not_free` | the probe fails with "no such host" | exit 1, `cannot tell` | **fails**: no such step |

T410-7, T410-8 and T410-9 belong to PR B (#430) and are not this spec's.

### 4.2 Each test fails without the change, for the stated reason

Measured in a throwaway worktree at `f1423143` with Blocks 4 to 7 (the tests alone) applied, `pytest -q --tb=line
tests/test_supply_chain.py -k TestTheChartPublishLabelGate`; each failure's first line (the step's stdout, which the
assertion prints, ends at `labelling it` and then copies):

| Test | Fails on `f1423143` with |
|---|---|
| T410-1 | `AssertionError: chart 0.59.25 deploys 2.0.0; labelling it` (`returncode == 1` is false: the step exited 0) |
| T410-18 | `assert 'quay.io/example/group-sync-dashboard:2.0.0 is application 2.0.0' in 'chart 0.59.25 deploys 2.0.0; labelling it\nlabelled: quay.io/example/group-sync-dashboard:0.59.25 -> 2.0.0 (sha256:d5b61e14…)\n'` |
| T410-19 | `AssertionError: chart 0.59.25 deploys 1.4.0; labelling it` (exit 0) |
| T410-4 | `AssertionError: chart 0.59.25 deploys 2.0.0; labelling it` (exit 0) |
| T410-5 `stale-arm64-child` | `AssertionError: chart 0.59.25 deploys 2.0.0; labelling it` (exit 0) |
| T410-11 | `AssertionError: chart 1.0.0 deploys 2.0.0; labelling it` (exit 0: application 1.0.0's alias overwritten) |
| T410-14 | `AssertionError: chart 0.59.25 deploys 2.0.0; labelling it` (exit 0) |
| T410-15 | `AssertionError: skopeo inspect --no-tags --format {{.Digest}} docker://quay.io/example/group-sync-dashboard:2.0.0` (the stub log, which holds the `skopeo copy`) |
| T410-16 | `assert ('print(", ".join(sorted({(i.get("config", {})…' in <release-crc.sh> and … in <the step>)`: the step has no such line |
| T410-10 | `AssertionError:` (no row in `docs/guides/RELEASING.md` names the refusal) |

`10 failed, 7 passed, 34 deselected`. The seven that pass are the regression guards named in §4.1 (T410-2, T410-3, T410-5 `every-child`, T410-6, T410-12,
T410-13, T410-17).

**Measured again on origin/main `31e4f037`** (the revision), with every test block (4 to 7, 12, 13, 15 to 18) applied
and no workflow change, `-k "TestTheChartPublishLabelGate or TestTheChartVersionIsNever"`: `17 failed, 9 passed,
34 deselected`. The ten above fail as listed; the new ones:

| Test | Fails on `31e4f037` with |
|---|---|
| T410-20 | `AssertionError: skopeo inspect --no-tags --format {{.Digest}} docker://quay.io/example/group-sync-dashboard:2.0.0` (the stub log: no `--raw` read at the digest) |
| T410-21 `no-linux-child-refused` | `AssertionError: chart 0.59.25 deploys 2.0.0; labelling it` (exit 0) |
| T410-22 | `ValueError: list.index(x): x not in list` (no such step in `version-bump`) |
| T410-23 to T410-26 | `AssertionError: expected one step matching 'The chart version is not a released application version', found 0` |

The nine that pass: the seven guards above and T410-21's two skipped-child cases (today's step reads no label, so
it copies; the cases bite the reader's filter, M6 below).

### 4.3 The proof

On a clean worktree at origin/main `31e4f037` (the revision; the first version was proved the same way at
`f1423143` with its eleven blocks):

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E8_chart_publish_label_gate.md <tree>
    -> 18 blocks check out across 6 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E8_chart_publish_label_gate.md <tree> --apply
    cd <tree>/local-development
    PYTHONPATH=<tree>/local-development <venv>/bin/python -m pytest -q tests/test_supply_chain.py

Measured on that tree after `--apply`:

    tests/test_supply_chain.py -k "TestTheChartPublishLabelGate or TestTheChartVersionIsNever"
                                                                 -> 26 passed           (before: 17 failed, 9 passed)
    tests/test_supply_chain.py tests/test_ci_charts.py tests/test_workflow_pins.py tests/test_publish_paths.py
                                                                 -> 77 passed
    the hermetic suite, as ci.yml runs it (`pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py`)
                                                                 -> 6415 passed, 26 skipped, 655 deselected, 5 xfailed
    the ci.yml file applied is byte-identical to the one the review measured (OB2's Block 14)

`shellcheck -s bash` on both steps' `run`, lifted from the parsed YAML ("Label the image this chart version
deploys" and "The chart version is not a released application version"), is clean.

**The pull-request check against quay**, read-only and anonymous, the lifted step run with skopeo 1.13.3
(`podman run --rm quay.io/skopeo/stable:v1.13.3`) in a tree whose `Chart.yaml` carries only the version:

    chart 0.59.25  rc=0  "quay.io/ephico2real/group-sync-dashboard:0.59.25 is application 2.0.0, not application 0.59.25's alias"
    chart 1.0.0    rc=1  "::error file=charts/group-sync-dashboard/Chart.yaml::chart version 1.0.0 is a released application version:"
    chart 0.60.0   rc=0  "quay.io/ephico2real/group-sync-dashboard:0.60.0 does not exist: the chart version is free"

**Mutants of the applied workflows** (both classes run after each, then the file restored):

| Mutant | Caught by |
|---|---|
| M1: the reader asks `--config` of the tag instead of each Linux child | T410-5 `stale-arm64-child` and T410-21 `no-linux-child-refused` (`2 failed, 24 passed`) |
| M2: any failure of the `:<chartVersion>` probe taken as absent | T410-15 (`1 failed, 25 passed`) |
| M3: the alias guard's `case` never matches | T410-11 (`1 failed, 25 passed`) |
| M4: `ci.yml`'s check never refuses | T410-23 (`1 failed, 25 passed`) |
| M5 (OB2): the dashboard's label read at `:<appVersion>`, not `@<SOURCE_DIGEST>` | T410-20 (`1 failed, 25 passed`); the seventeen tests of `d5d14f5e` all pass it (`17 passed`) |
| M6 (OB2): the Linux filter dropped | T410-21, all three cases (`3 failed, 23 passed`); the seventeen tests of `d5d14f5e` all pass it (`17 passed`) |

At `f1423143`, with seventeen tests, M1, M2 and M3 each failed exactly one (`1 failed, 16 passed`).

**The index pin** (`local-development/tests/test_specs_index.py#test_issue_numbers_are_unique_and_follow_the_implementation_order`):
with E8's row and header both mistyped as #510, the test fails `AssertionError: ('E8 is #410', '510')`; with the
pin line removed and E8 still excluded by its id, the same mutant passes (`96 passed`), which is why the pin is there.
Measured on the forty-five-row index of the revision.

## 5. After the merge (no cluster step)

There is nothing to deploy: the change is a workflow, its tests and docs, and no PVC, Application or cluster object
is touched. The implementing pull request:

1. CI green on its head (the `validate` job runs `ci.yml`, whose tests job runs `tests/test_supply_chain.py`).
2. Reads the registry the gate will meet, read-only, and records it on the PR (development check):

       skopeo inspect --raw --config docker://quay.io/ephico2real/group-sync-dashboard:<appVersion>
       skopeo inspect --raw --config docker://quay.io/ephico2real/group-sync-dashboard-report:<appVersion>

   (measured now for 2.0.0: both labelled `2.0.0`.)
3. Shows the pull-request check's line in its own `version-bump` run: `…:<chartVersion> does not exist: the chart
   version is free`, or `… is application <appVersion>, not application <chartVersion>'s alias`.
4. After the first chart release that follows, posts on #410 the `helm.yaml` run's lines
   `image   : …group-sync-dashboard:<appVersion> is application <appVersion>` and the report's, and the
   `labelled:` line: the issue's first-release check.

## 6. What an operator sees, and what it costs

**A release engineer** sees one of three new things in "Label the image this chart version deploys":

- Normally, two extra log lines naming the label compared for each image, then today's `labelled:` line.
- A red run, `<image>:<appVersion> is application X, not <appVersion> (#410)`: the alias has not moved yet, or
  names an old build. Wait for `publish.yml` on the release merge, then re-run (`docs/guides/RELEASING.md`, the new row).
- A red run, `<image>:<chartVersion> is application <chartVersion>'s own alias`: give the chart an unused version
  in a pull request. Never retag or delete.

**A pull-request author** sees one more line in "Chart changes bump the chart version", and a red check,
`chart version X is a released application version`, when the chart is numbered like a released application;
the fix is a version no application release has used.

**A platform team installing the chart** gets a chart whose default `:<appVersion>` tags were checked, at publish
time, to be that application. **Cluster administrators, auditors, readers:** no change.

**Cost:** five more registry reads per chart release (single-arch images), three more when `:<chartVersion>`
already exists at another digest; one read per pull request; no new tool, action, secret, permission, or version.

## 7. Implementation blocks

Twenty-three blocks, in the order `apply-spec-blocks.py` applies them. Blocks 1 to 3 are the `helm.yaml` change; 4
to 7 the tests; 8 to 11 the documentation; 12 and 13 OB2's two guard tests (T410-20, T410-21); 14 the `ci.yml`
pull-request check; 15 to 18 its harness changes and tests (T410-22 to T410-26); 19 to 23 the review of PR #529
(the existence check's "cannot tell", T410-27, its RELEASING.md row and CHANGELOG sentence). No block touches `charts/`, an image
input or this spec's index row.

### Block 1 — .github/workflows/helm.yaml: why the step now reads the label, in the step's comment

<!-- block: .github/workflows/helm.yaml | edit -->
```yaml
      # run, not a silent skip.
      - name: Label the image this chart version deploys
```

```yaml
      # run, not a silent skip.
      #
      # AN IMAGE THAT EXISTS IS NOT YET THE RIGHT ONE (#410, SPEC_E8). `:<appVersion>` is a tag, and a tag can
      # name another build: `:0.39.0` was a chart-version label on application 0.24.0 before application 0.39.0
      # existed, and the existence check above passed on it. So before anything is copied, both images the chart
      # resolves through appVersion must carry it as their org.opencontainers.image.version label, on every Linux
      # image behind the tag: the reading and the comparison release-crc.sh makes before it hands a branch to
      # Argo CD (#414), made here with skopeo, because the runner carries skopeo and not oc. A pinned tag is the
      # operator's choice for that image and is not checked, as there. And because chart versions and application
      # versions share this repository's tags, the copy never lands on a tag that is another application's own
      # alias: chart 1.0.0 would otherwise overwrite application 1.0.0's `:1.0.0`. Both refusals are red runs
      # that copy nothing, so chart-releaser and the attestation, which run only after a green step, publish
      # nothing either.
      - name: Label the image this chart version deploys
```

### Block 2 — .github/workflows/helm.yaml: the report pin and the reader, beside the dashboard's

<!-- block: .github/workflows/helm.yaml | edit -->
```yaml
          REPO="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"

```

```yaml
          REPO="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
          # reporting.image.tag, walked with release-crc.sh's own code (tests/test_supply_chain.py holds the two
          # equal): four spaces deep with a trailing comment, where a 4-space sed would meet secretsMint's tag first.
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
          ' < "$VALUES")

          # The org.opencontainers.image.version label of every Linux image behind <repository><:tag or @digest>,
          # sorted and joined: what release-crc.sh reads with `oc image info --filter-by-os='linux/.*'`.
          # `skopeo inspect --config` on a list answers for the runner's platform alone, so a list is walked child
          # by child, by digest. A list with no Linux image prints "", which no appVersion equals.
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

```

### Block 3 — .github/workflows/helm.yaml: the label gate and the alias guard, between the existence check and the login

<!-- block: .github/workflows/helm.yaml | edit -->
```yaml
            echo "::error::  cd local-development && ./build-and-push-report.sh --release-tags"
            exit 1
```

```yaml
            echo "::error::  cd local-development && ./build-and-push-report.sh --release-tags"
            exit 1
          fi

          # Both images, each against its own pin. The dashboard's label is read at the digest just read, which
          # is the digest the copy below must reproduce, so the image checked is the image aliased even if the
          # tag moves between the two reads.
          for spec in "${REPO}|${PINNED}" "${REPO}-report|${REPORT_PINNED}"; do
            name="${spec%%|*}" this_pin="${spec#*|}"
            if [ -n "${this_pin}" ]; then
              echo "image   : ${name}:${this_pin} (pinned in values.yaml; not checked against appVersion)"
              continue
            fi
            reference=":${APP_VERSION}"
            if [ "${name}" = "${REPO}" ]; then
              reference="@${SOURCE_DIGEST}"
            fi
            if ! version=$(image_versions "${name}" "${reference}"); then
              echo "::error::${name}:${APP_VERSION} is not in the registry, or cannot be read, so chart"
              echo "::error::${CHART_VERSION} is NOT published. publish.yml pushes the :${APP_VERSION} aliases of both"
              echo "::error::images on the merge that moved pyproject's version: wait for that run, then re-run this"
              echo "::error::workflow. If that run is red, from a clean checkout of the release commit run:"
              echo "::error::  cd local-development && ./build-and-push-external.sh --release-tags"
              echo "::error::  cd local-development && ./build-and-push-report.sh --release-tags"
              exit 1
            fi
            if [ "${version}" != "${APP_VERSION}" ]; then
              echo "::error::${name}:${APP_VERSION} is application ${version:-unknown}, not ${APP_VERSION} (#410), so"
              echo "::error::chart ${CHART_VERSION} is NOT published and nothing was copied. The tag exists but names"
              echo "::error::another build: an alias publish.yml has not moved yet, or a chart-version label on an"
              echo "::error::old image. Wait for publish.yml on the release merge, then re-run this workflow. Never"
              echo "::error::retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it."
              exit 1
            fi
            echo "image   : ${name}:${APP_VERSION} is application ${version}"
          done

          # Never over another application's alias. A tag that does not exist yet is created; one at the source's
          # digest is copied again unchanged (publish.yml's --release-tags writes :<chartVersion> too); one that
          # names some other build is relabelled, as before. Only a tag that IS application <chartVersion> is
          # refused. Unreachable is not absent: only the registry's "manifest unknown" lets the copy create it.
          probe_err=$(mktemp)
          trap 'rm -f "${probe_err}"' EXIT
          if TARGET_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${REPO}:${CHART_VERSION}" 2>"${probe_err}"); then
            if [ "${TARGET_DIGEST}" != "${SOURCE_DIGEST}" ]; then
              if ! target_version=$(image_versions "${REPO}" "@${TARGET_DIGEST}"); then
                echo "::error::${REPO}:${CHART_VERSION} exists at ${TARGET_DIGEST} and its label cannot be read, so"
                echo "::error::this run cannot tell whether it is application ${CHART_VERSION}'s own alias. Nothing"
                echo "::error::was copied. Re-run this workflow once the registry answers."
                exit 1
              fi
              case ", ${target_version}, " in
                *", ${CHART_VERSION}, "*)
                  echo "::error::${REPO}:${CHART_VERSION} is application ${CHART_VERSION}'s own alias (labelled"
                  echo "::error::${target_version}), and chart ${CHART_VERSION} would copy ${SOURCE} over it (#410):"
                  echo "::error::chart and application versions share this repository's tags. Nothing was copied"
                  echo "::error::and the chart is NOT published. Give the chart a version no application release"
                  echo "::error::has used (the version field of charts/group-sync-dashboard/Chart.yaml, in a pull"
                  echo "::error::request). Never retag or delete the existing tag: something may pin it."
                  exit 1 ;;
              esac
            fi
          elif ! grep -qi 'manifest unknown' "${probe_err}"; then
            echo "::error::cannot tell whether ${REPO}:${CHART_VERSION} exists, so nothing was copied:"
            echo "::error::$(head -c 400 "${probe_err}")"
            echo "::error::Re-run this workflow once the registry answers."
            exit 1
```

### Block 4 — local-development/tests/test_supply_chain.py: the module says which class is run

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
defect that a green run hid (#34, #37, the unpinned Grype). These read the real YAML and the real
script rather than restating either.

```

```python
defect that a green run hid (#34, #37, the unpinned Grype). These read the real YAML and the real
script rather than restating either. The exceptions are #410's two registry checks, the chart-publish
label gate and the pull-request version check: their refusals are decisions over registry answers, so
those steps are RUN, against a stub skopeo (TestTheChartPublishLabelGate,
TestTheChartVersionIsNeverAReleasedApplicationVersion).

```

### Block 5 — local-development/tests/test_supply_chain.py: the imports the harness uses

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
import pathlib
import re
import subprocess

import yaml
```

```python
import hashlib
import io
import json
import os
import pathlib
import re
import subprocess
import tokenize

import pytest
import yaml
```

### Block 6 — local-development/tests/test_supply_chain.py: the two files the new tests read

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
INSTALL_GUIDE = REPO / "charts" / "group-sync-dashboard" / "docs" / "HELM_DOWNLOAD_AND_INSTALL.md"

```

```python
INSTALL_GUIDE = REPO / "charts" / "group-sync-dashboard" / "docs" / "HELM_DOWNLOAD_AND_INSTALL.md"
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"   # the deploy-side label guard (#414)
RELEASING = REPO / "docs" / "guides" / "RELEASING.md"

```

### Block 7 — local-development/tests/test_supply_chain.py: the harness and the tests (T410-1 to T410-19)

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
        assert "Forks do not sign under this workflow" in section
```

```python
        assert "Forks do not sign under this workflow" in section


# ── The chart-publish label gate (#410, SPEC_E8) ─────────────────────────────────────────────────
#
# AN EXECUTED CLASS (with the pull-request check's, below). The label step's `run:` is lifted from the parsed
# helm.yaml and run by bash
# with the flags GitHub gives `shell: bash`, against a stub `skopeo` that answers from a registry kept in a JSON file
# and logs every call — the real step, the real Chart.yaml and values.yaml, only the registry replaced (the harness
# test_release_crc.py uses for the same guard's other half). The stub answers `inspect --config` on a manifest list
# for linux/amd64, as the real skopeo answers for the runner's platform, so a reader that trusted that answer would
# pass the stale-arm64 case below. `_push` with one version writes a bare manifest, not an index, so an index with no
# Linux child needs two children.

LABEL_STEP = "Label the image this chart version deploys"
REGISTRY_NS = "quay.io/example"
DASHBOARD = f"{REGISTRY_NS}/group-sync-dashboard"
REPORT = f"{REGISTRY_NS}/group-sync-dashboard-report"
CHART_FILE = REPO / "charts" / "group-sync-dashboard" / "Chart.yaml"
VALUES_FILE = REPO / "charts" / "group-sync-dashboard" / "values.yaml"
APP = re.search(r'^appVersion: "(\d+\.\d+\.\d+)"$', CHART_FILE.read_text(), re.M).group(1)
CHART = re.search(r"^version: (\d+\.\d+\.\d+)$", CHART_FILE.read_text(), re.M).group(1)

SKOPEO_STUB = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write("skopeo " + " ".join(args) + "\n")
state = json.load(open(os.environ["STUB_REGISTRY"]))


def resolve(ref):
    ref = ref.removeprefix("docker://")
    if ref in os.environ.get("STUB_UNREACHABLE", "").split():
        sys.exit(f'pinging container registry {ref.split("/")[0]}: dial tcp: lookup: no such host')
    if "@" in ref:
        repo, digest = ref.split("@", 1)
    else:
        repo, tag = ref.rsplit(":", 1)
        digest = state["tags"].get(f"{repo}:{tag}")
    if f"{repo}@{digest}" not in state["manifests"]:
        sys.exit(f"reading manifest {ref} in {repo}: manifest unknown")
    return repo, digest, state["manifests"][f"{repo}@{digest}"]


if args[0] == "login":
    sys.stdin.read()
elif args[0] == "copy":
    _, digest, _ = resolve(args[-2])
    state["tags"][args[-1].removeprefix("docker://")] = digest
    json.dump(state, open(os.environ["STUB_REGISTRY"], "w"))
elif args[0] == "inspect":
    repo, digest, manifest = resolve(args[-1])
    if "--format" in args:
        print(digest)
    elif "--config" in args:
        if "manifests" in manifest:
            amd64 = next(m["digest"] for m in manifest["manifests"] if m["platform"] == {"architecture": "amd64", "os": "linux"})
            manifest = state["manifests"][f"{repo}@{amd64}"]
        print(json.dumps(state["blobs"][f'{repo}@{manifest["config"]["digest"]}']))
    else:
        print(json.dumps(manifest))
else:
    sys.exit(f"stub skopeo: unexpected call {args}")
'''


def _digest(obj: dict) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _push(registry: dict, repo: str, tag: str, *versions: str) -> str:
    """Push `repo:tag`: one version is one linux/amd64 image; two are a linux/amd64 + linux/arm64 index."""
    children = []
    for arch, version in zip(("amd64", "arm64"), versions):
        config = {"architecture": arch, "os": "linux", "rootfs": {"type": "layers", "diff_ids": []},
                  "config": {"Labels": {"org.opencontainers.image.version": version}}}
        registry["blobs"][f"{repo}@{_digest(config)}"] = config
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": _digest(config)},
                    "layers": []}
        registry["manifests"][f"{repo}@{_digest(manifest)}"] = manifest
        children.append({"mediaType": manifest["mediaType"], "digest": _digest(manifest),
                         "platform": {"architecture": arch, "os": "linux"}})
    top = registry["manifests"][f'{repo}@{children[0]["digest"]}'] if len(children) == 1 else {
        "schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json", "manifests": children}
    registry["manifests"][f"{repo}@{_digest(top)}"] = top
    registry["tags"][f"{repo}:{tag}"] = _digest(top)
    return _digest(top)


def _released() -> dict:
    """The registry as publish.yml leaves it after the release merge: both aliases carry the appVersion."""
    registry: dict = {"tags": {}, "manifests": {}, "blobs": {}}
    _push(registry, DASHBOARD, APP, APP)
    _push(registry, REPORT, APP, APP)
    return registry


def _label(tmp_path: pathlib.Path, registry: dict, *, chart_version: str = CHART, pin: str = "",
           credentials: bool = True, unreachable: str = "") -> tuple[subprocess.CompletedProcess, str, dict]:
    """Run the label step as GitHub runs `shell: bash`, in a tree carrying the real chart files."""
    tree = tmp_path / "tree"
    (tree / "charts" / "group-sync-dashboard").mkdir(parents=True)
    (tree / "charts" / "group-sync-dashboard" / "Chart.yaml").write_text(
        CHART_FILE.read_text().replace(f"\nversion: {CHART}\n", f"\nversion: {chart_version}\n", 1))
    values = VALUES_FILE.read_text()
    if pin:
        values = values.replace('\n  tag: ""\n', f'\n  tag: "{pin}"\n', 1)
    (tree / "charts" / "group-sync-dashboard" / "values.yaml").write_text(values)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "skopeo").write_text(SKOPEO_STUB)
    (bindir / "skopeo").chmod(0o755)
    state, log = tmp_path / "registry.json", tmp_path / "calls.log"
    state.write_text(json.dumps(registry))
    log.write_text("")
    script = tmp_path / "step.sh"
    script.write_text(_step(_jobs(HELM)["release"], LABEL_STEP)["run"])
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "STUB_REGISTRY": str(state), "STUB_LOG": str(log),
           "STUB_UNREACHABLE": unreachable, "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example",
           "REGISTRY_USERNAME": "robot" if credentials else "", "REGISTRY_PASSWORD": "not-a-secret" if credentials else ""}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(script)], cwd=tree, env=env,
                          capture_output=True, text=True)
    return done, log.read_text(), json.loads(state.read_text())


class TestTheChartPublishLabelGate:
    def test_t410_1_a_stale_dashboard_alias_is_refused_before_anything_is_copied(self, tmp_path) -> None:
        """#410 as measured on quay: `:0.39.0` existed before application 0.39.0 and was application 0.24.0."""
        registry = _released()
        _push(registry, DASHBOARD, APP, "0.24.0")
        done, log, after = _label(tmp_path, registry)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{DASHBOARD}:{APP} is application 0.24.0, not {APP} (#410)" in done.stdout
        assert "skopeo copy" not in log and "skopeo login" not in log, log
        assert f"{DASHBOARD}:{CHART}" not in after["tags"]

    def test_t410_2_matching_labels_copy_and_compare_the_digest_as_today(self, tmp_path) -> None:
        done, log, after = _label(tmp_path, _released())
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"skopeo copy --all --preserve-digests docker://{DASHBOARD}:{APP} docker://{DASHBOARD}:{CHART}" in log
        assert after["tags"][f"{DASHBOARD}:{CHART}"] == after["tags"][f"{DASHBOARD}:{APP}"]
        assert f"labelled: {DASHBOARD}:{CHART} -> {APP}" in done.stdout

    def test_t410_3_a_pinned_dashboard_tag_is_copied_as_pinned(self, tmp_path) -> None:
        registry = _released()
        _push(registry, DASHBOARD, "1.4.0", "1.4.0")
        _push(registry, DASHBOARD, APP, "0.24.0")      # the unpinned alias is not what the chart deploys
        done, log, after = _label(tmp_path, registry, pin="1.4.0")
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"skopeo copy --all --preserve-digests docker://{DASHBOARD}:1.4.0 docker://{DASHBOARD}:{CHART}" in log
        assert after["tags"][f"{DASHBOARD}:{CHART}"] == registry["tags"][f"{DASHBOARD}:1.4.0"]

    def test_t410_18_the_run_log_names_the_label_compared_for_both_images(self, tmp_path) -> None:
        """The issue's first-release check reads this log: both labels compared, each read before the copy."""
        done, log, _ = _label(tmp_path, _released())
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"{DASHBOARD}:{APP} is application {APP}" in done.stdout
        assert f"{REPORT}:{APP} is application {APP}" in done.stdout
        assert log.index(f"skopeo inspect --raw docker://{REPORT}:{APP}") < log.index("skopeo copy")

    def test_t410_19_a_pin_on_the_dashboard_leaves_the_report_checked(self, tmp_path) -> None:
        """image.tag is the operator's choice for the dashboard only; the report still resolves appVersion, as
        release-crc.sh's test_argocd_branch_still_checks_report_when_only_the_dashboard_tag_is_pinned holds."""
        registry = _released()
        _push(registry, DASHBOARD, "1.4.0", "1.4.0")
        _push(registry, REPORT, APP, "0.24.0")
        done, log, _ = _label(tmp_path, registry, pin="1.4.0")
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{DASHBOARD}:1.4.0 (pinned in values.yaml; not checked against appVersion)" in done.stdout
        assert f"{REPORT}:{APP} is application 0.24.0, not {APP} (#410)" in done.stdout
        assert "skopeo copy" not in log

    def test_t410_4_a_stale_report_alias_is_refused(self, tmp_path) -> None:
        registry = _released()
        _push(registry, REPORT, APP, "1.9.0")
        done, log, _ = _label(tmp_path, registry)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{REPORT}:{APP} is application 1.9.0, not {APP} (#410)" in done.stdout
        assert "skopeo copy" not in log

    @pytest.mark.parametrize("arm64, published", [(APP, True), ("1.9.0", False)], ids=["every-child", "stale-arm64-child"])
    def test_t410_5_every_linux_image_behind_a_list_carries_the_label(self, tmp_path, arm64, published) -> None:
        registry = _released()
        _push(registry, DASHBOARD, APP, APP, arm64)
        done, log, _ = _label(tmp_path, registry)
        assert (done.returncode == 0) is published, done.stdout + done.stderr
        assert ("skopeo copy" in log) is published
        if not published:
            assert f"{DASHBOARD}:{APP} is application 1.9.0, {APP}, not {APP} (#410)" in done.stdout

    def test_t410_6_a_missing_image_is_still_red_with_today_s_remedy(self, tmp_path) -> None:
        registry = _released()
        del registry["tags"][f"{DASHBOARD}:{APP}"]
        done, log, _ = _label(tmp_path, registry)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{DASHBOARD}:{APP} does not exist" in done.stdout
        assert "./build-and-push-external.sh --release-tags" in done.stdout
        assert "./build-and-push-report.sh --release-tags" in done.stdout
        assert "skopeo copy" not in log

    def test_t410_11_a_chart_version_that_is_an_application_alias_is_never_copied_over(self, tmp_path) -> None:
        """Chart and application versions share one tag namespace: chart 1.0.0 would overwrite application 1.0.0's
        alias, which a cluster, a mirror or a Helm release may pin (measured on quay: `:1.0.0` is application 1.0.0)."""
        registry = _released()
        alias = _push(registry, DASHBOARD, "1.0.0", "1.0.0")
        done, log, after = _label(tmp_path, registry, chart_version="1.0.0")
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{DASHBOARD}:1.0.0 is application 1.0.0's own alias" in done.stdout
        assert "skopeo copy" not in log
        assert after["tags"][f"{DASHBOARD}:1.0.0"] == alias

    def test_t410_12_a_chart_version_tag_publish_already_made_is_copied_again_unchanged(self, tmp_path) -> None:
        """publish.yml's --release-tags copies the release to `:<chartVersion>` too (measured: `:0.59.24` written at
        08:38:42 and again by helm.yaml at 08:47:38, one digest): the same digest is not a collision."""
        registry = _released()
        registry["tags"][f"{DASHBOARD}:{CHART}"] = registry["tags"][f"{DASHBOARD}:{APP}"]
        done, log, _ = _label(tmp_path, registry)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "skopeo copy" in log

    def test_t410_13_a_chart_version_tag_on_another_build_is_relabelled_as_today(self, tmp_path) -> None:
        """A `:<chartVersion>` that names some other application (an earlier label of this chart version) is the
        convenience tag this step owns; only another application's own alias is refused."""
        registry = _released()
        _push(registry, DASHBOARD, CHART, "1.21.0")
        done, log, after = _label(tmp_path, registry)
        assert done.returncode == 0, done.stdout + done.stderr
        assert after["tags"][f"{DASHBOARD}:{CHART}"] == after["tags"][f"{DASHBOARD}:{APP}"]

    def test_t410_14_a_missing_report_image_is_red_with_the_remedy(self, tmp_path) -> None:
        registry = _released()
        del registry["tags"][f"{REPORT}:{APP}"]
        done, log, _ = _label(tmp_path, registry)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"{REPORT}:{APP} is not in the registry, or cannot be read" in done.stdout
        assert "./build-and-push-report.sh --release-tags" in done.stdout
        assert "skopeo copy" not in log

    def test_t410_15_a_chart_version_tag_that_cannot_be_read_is_not_taken_as_absent(self, tmp_path) -> None:
        """Unreachable is not absent: only the registry's `manifest unknown` lets the copy create the tag."""
        done, log, _ = _label(tmp_path, _released(), unreachable=f"{DASHBOARD}:{CHART}")
        assert "skopeo copy" not in log, log
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"cannot tell whether {DASHBOARD}:{CHART} exists" in done.stdout

    def test_t410_16_the_label_is_read_and_compared_as_release_crc_sh_reads_it(self) -> None:
        """One reading, two tools: helm.yaml asks skopeo (oc is not on the runner), release-crc.sh asks oc (skopeo is
        not on a workstation), and both hand the same Python the same shape — the label set of every Linux image,
        joined — and walk reporting.image.tag with the same code. Compared token by token, comments dropped."""
        def code(text: str, start: str) -> str:
            body = text.split(start, 1)[1]
            body = body[:min(i for i in (body.find("\n'"), body.find("\nPY")) if i >= 0)]
            tokens = tokenize.generate_tokens(io.StringIO(body.replace("'\\''", "'")).readline)
            return " ".join(t.string for t in tokens if t.type not in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                                                                       tokenize.INDENT, tokenize.DEDENT))
        crc, run = RELEASE_CRC.read_text(), _step(_jobs(HELM)["release"], LABEL_STEP)["run"]
        compare = 'print(", ".join(sorted({(i.get("config", {}).get("config", {}).get("Labels") or {}).get("org.opencontainers.image.version", "") for i in images})))'
        assert compare in crc and compare in run
        walker = "in_reporting = in_image = False"
        assert code(crc, walker) == code(run, walker)
        assert 'echo "ERROR: ${ref} is application ${version:-unknown}, not ${app_version} (#410)."' in crc
        assert 'is application ${version:-unknown}, not ${APP_VERSION} (#410)' in run

    def test_t410_17_without_credentials_the_step_still_warns_and_reads_nothing(self, tmp_path) -> None:
        done, log, _ = _label(tmp_path, _released(), credentials=False)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "registry credentials are not set" in done.stdout
        assert log == "", "no registry call is made without credentials, as today"

    def test_t410_10_the_release_guide_says_what_the_label_refusal_means(self) -> None:
        table = RELEASING.read_text().split("## What can go wrong, and what it looks like", 1)[1]
        row = next((line for line in table.splitlines() if "is application" in line and "(#410)" in line), "")
        assert "Label the image this chart version deploys" in row, row
        assert "never retag" in row.lower() and "re-run" in row, row
        collision = next((line for line in table.splitlines() if "own alias" in line), "")
        assert "Chart.yaml" in collision, collision
```

### Block 8 — docs/guides/RELEASING.md: the chart flow draws the two refusals

<!-- block: docs/guides/RELEASING.md | edit -->
```markdown
        |          success while publishing nothing.
        |
       yes
        |
```

```markdown
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
```

### Block 9 — docs/guides/RELEASING.md: what each refusal means and what to do

<!-- block: docs/guides/RELEASING.md | edit -->
```markdown
| chart release run is red at "Label the image this chart version deploys" | the image the chart resolves was never published, so there is nothing to retag | run `./build-and-push-external.sh --release-tags` and `./build-and-push-report.sh --release-tags` from a clean checkout, then re-run the release |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
```

```markdown
| chart release run is red at "Label the image this chart version deploys" | the image the chart resolves was never published, so there is nothing to retag | run `./build-and-push-external.sh --release-tags` and `./build-and-push-report.sh --release-tags` from a clean checkout, then re-run the release |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<chartVersion> is application <chartVersion>'s own alias` | the chart's version equals an application version that already has its alias, and the copy would overwrite it. Nothing was copied | bump `version` in `charts/group-sync-dashboard/Chart.yaml`, in a pull request, to a version no application release has used |
| `helm search repo` shows the old chart after a merge | `Chart.yaml` `version` was not bumped, so chart-releaser skipped it | bump it. `ci.yml`'s version-bump check exists to stop this reaching main |
```

### Block 10 — docs/design/DESIGN_supply_chain.md: helm.yaml now reads the report image, and still copies nothing there

<!-- block: docs/design/DESIGN_supply_chain.md | edit -->
```markdown
label or resolve the report image by chart version —
`.github/workflows/helm.yaml#Label the image this chart version deploys` names the dashboard
repository only, and the chart resolves the report image at appVersion, so
`group-sync-dashboard-report:<chartVersion>` exists only from application releases. The first
```

```markdown
label or resolve the report image by chart version —
`.github/workflows/helm.yaml#Label the image this chart version deploys` copies into the dashboard
repository only (since #410 it reads the report image's version label before that copy, and copies
nothing there), and the chart resolves the report image at appVersion, so
`group-sync-dashboard-report:<chartVersion>` exists only from application releases. The first
```

### Block 11 — docs/CHANGELOG.md: the entry under Unreleased

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased

```

```markdown
## Unreleased

- **The chart is published only when its default images are the application it names (#410, PR A, SPEC_E8).**
  `helm.yaml`'s "Label the image this chart version deploys" read only whether `:<appVersion>` existed, so a tag
  naming another build (`:0.39.0` was application 0.24.0) passed and was copied to the chart-version tag. It now reads
  the `org.opencontainers.image.version` label of every Linux image behind both images' `:<appVersion>` (a pinned tag
  stays the operator's) and refuses a mismatch, as `release-crc.sh` does before a deploy (#414); and it never copies
  over a `:<chartVersion>` that is another application's own alias. Both refusals are red runs that copy and publish
  nothing. `publish.yml` copies every application release to `:<chartVersion>` too, so `ci.yml`'s version-bump job
  now refuses, in the pull request, a chart version whose tag is already that application's alias (read from the
  tag's own label; only `manifest unknown` means free). Workflows, tests and docs only: no application or chart
  version.

```

### Block 12 — local-development/tests/test_supply_chain.py: the stub pushes an index with any platforms, and a child without the label (OB2)

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
def _push(registry: dict, repo: str, tag: str, *versions: str) -> str:
    """Push `repo:tag`: one version is one linux/amd64 image; two are a linux/amd64 + linux/arm64 index."""
    children = []
    for arch, version in zip(("amd64", "arm64"), versions):
        config = {"architecture": arch, "os": "linux", "rootfs": {"type": "layers", "diff_ids": []},
                  "config": {"Labels": {"org.opencontainers.image.version": version}}}
        registry["blobs"][f"{repo}@{_digest(config)}"] = config
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": _digest(config)},
                    "layers": []}
        registry["manifests"][f"{repo}@{_digest(manifest)}"] = manifest
        children.append({"mediaType": manifest["mediaType"], "digest": _digest(manifest),
                         "platform": {"architecture": arch, "os": "linux"}})
```

```python
def _push(registry: dict, repo: str, tag: str, *versions: str, platforms: tuple = (("amd64", "linux"), ("arm64", "linux"))) -> str:
    """Push `repo:tag`: one version is one image on the first platform; two are an index of the first two.
    A version of None is a child without the label (BuildKit's unknown/unknown attestation manifests)."""
    children = []
    for (arch, os_), version in zip(platforms, versions):
        config = {"architecture": arch, "os": os_, "rootfs": {"type": "layers", "diff_ids": []},
                  "config": {"Labels": {} if version is None else {"org.opencontainers.image.version": version}}}
        registry["blobs"][f"{repo}@{_digest(config)}"] = config
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": _digest(config)},
                    "layers": []}
        registry["manifests"][f"{repo}@{_digest(manifest)}"] = manifest
        children.append({"mediaType": manifest["mediaType"], "digest": _digest(manifest),
                         "platform": {"architecture": arch, "os": os_}})
```

### Block 13 — local-development/tests/test_supply_chain.py: T410-20 and T410-21, the two properties no test held (OB2)

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
        collision = next((line for line in table.splitlines() if "own alias" in line), "")
        assert "Chart.yaml" in collision, collision
```

```python
        collision = next((line for line in table.splitlines() if "own alias" in line), "")
        assert "Chart.yaml" in collision, collision

    def test_t410_20_the_dashboard_label_is_read_at_the_digest_the_copy_is_held_to(self, tmp_path) -> None:
        """Orchestrator's note 5: the bytes whose label is checked are the bytes the post-copy comparison holds the
        alias to, so a tag that moves between the reads ends in the digest-mismatch red run, never a pass."""
        registry = _released()
        done, log, _ = _label(tmp_path, registry)
        assert done.returncode == 0, done.stdout + done.stderr
        digest = registry["tags"][f"{DASHBOARD}:{APP}"]
        assert f"skopeo inspect --raw docker://{DASHBOARD}@{digest}\n" in log, log
        assert f"skopeo inspect --raw --config docker://{DASHBOARD}@{digest}\n" in log, log
        assert f"--raw docker://{DASHBOARD}:{APP}\n" not in log, log

    @pytest.mark.parametrize("platforms, versions, published", [
        ((("amd64", "linux"), ("unknown", "unknown")), (APP, None), True),      # BuildKit's attestation child: not an image
        ((("amd64", "linux"), ("amd64", "windows")), (APP, "1.9.0"), True),     # a non-Linux child is not what the chart runs
        ((("amd64", "windows"), ("arm64", "windows")), ("1.9.0", "1.9.0"), False),   # an index with no Linux image: "" is not appVersion
    ], ids=["attestation-child-skipped", "windows-child-skipped", "no-linux-child-refused"])
    def test_t410_21_only_linux_children_are_read_as_release_crc_sh_filters_them(self, tmp_path, platforms, versions, published) -> None:
        """`oc image info --filter-by-os='linux/.*'` keeps the Linux entries alone; the reader keeps the same set, so an
        index that carries BuildKit's unknown/unknown attestation manifest (no config labels) is not a red run, and
        an index with no Linux image is."""
        registry = _released()
        _push(registry, REPORT, APP, *versions, platforms=platforms)
        done, log, _ = _label(tmp_path, registry)
        assert (done.returncode == 0) is published, done.stdout + done.stderr
        assert ("skopeo copy" in log) is published, log
        if not published:
            assert f"{REPORT}:{APP} is application unknown, not {APP} (#410)" in done.stdout
```

### Block 14 — .github/workflows/ci.yml: the chart version is never a released application version (OB2; option ii, Orchestrator's note 2)

<!-- block: .github/workflows/ci.yml | edit -->
```yaml
          exit $status

  app-version-bump:
```

```yaml
          exit $status

      # A CHART VERSION IS NEVER A RELEASED APPLICATION VERSION (#410, SPEC_E8). Chart versions and
      # application versions share the dashboard repository's tags: publish.yml copies every
      # application release to `:<chartVersion>` as well as `:<appVersion>`, and helm.yaml labels
      # `:<chartVersion>` on every chart release. A chart numbered like a released application (chart
      # 1.0.0 beside application 1.0.0) would therefore overwrite that application's own alias on the
      # next release merge, by publish.yml, whatever helm.yaml's alias guard refuses. Refused here,
      # before the version reaches main, by reading the tag's own version label (the repository is
      # public; the read is anonymous, as helm.yaml's existence check is). Only the registry's
      # "manifest unknown" means the tag is free; any other failure is a red check, not a pass.
      # `skopeo inspect --config` on a manifest list answers for this runner's platform: the full
      # every-Linux-image reading stays helm.yaml's; no published tag is a list today (measured).
      - name: The chart version is not a released application version
        env:
          REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
          REGISTRY_NAMESPACE: ${{ vars.REGISTRY_NAMESPACE || 'ephico2real' }}
        run: |
          set -euo pipefail
          CHART=charts/group-sync-dashboard/Chart.yaml
          CHART_VERSION=$(sed -n 's/^version: \([0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*\)[[:blank:]]*$/\1/p' "$CHART" | head -1)
          REPO="${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard"
          probe_err=$(mktemp)
          trap 'rm -f "${probe_err}"' EXIT
          if config=$(skopeo inspect --raw --config "docker://${REPO}:${CHART_VERSION}" 2>"${probe_err}"); then
            label=$(printf '%s' "${config}" | python3 -c 'import json, sys; print((json.load(sys.stdin).get("config", {}).get("Labels") or {}).get("org.opencontainers.image.version", ""))')
            if [ "${label}" = "${CHART_VERSION}" ]; then
              echo "::error file=${CHART}::chart version ${CHART_VERSION} is a released application version:"
              echo "::error file=${CHART}::${REPO}:${CHART_VERSION} is labelled ${label}, and the next release merge would"
              echo "::error file=${CHART}::copy another image over that alias (#410). Give the chart a version no"
              echo "::error file=${CHART}::application release has used. Never retag or delete the existing tag:"
              echo "::error file=${CHART}::something may pin it."
              exit 1
            fi
            echo "${REPO}:${CHART_VERSION} is application ${label:-unknown}, not application ${CHART_VERSION}'s alias"
          elif grep -qi 'manifest unknown' "${probe_err}"; then
            echo "${REPO}:${CHART_VERSION} does not exist: the chart version is free"
          else
            echo "::error::cannot tell whether ${REPO}:${CHART_VERSION} is a released application version:"
            echo "::error::$(head -c 400 "${probe_err}")"
            exit 1
          fi

  app-version-bump:
```

### Block 15 — local-development/tests/test_supply_chain.py: ci.yml beside the other workflows

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
HELM = REPO / ".github" / "workflows" / "helm.yaml"
```

```python
HELM = REPO / ".github" / "workflows" / "helm.yaml"
CI = REPO / ".github" / "workflows" / "ci.yml"
```

### Block 16 — local-development/tests/test_supply_chain.py: the harness runs any step of any workflow

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
def _label(tmp_path: pathlib.Path, registry: dict, *, chart_version: str = CHART, pin: str = "",
           credentials: bool = True, unreachable: str = "") -> tuple[subprocess.CompletedProcess, str, dict]:
    """Run the label step as GitHub runs `shell: bash`, in a tree carrying the real chart files."""
```

```python
def _label(tmp_path: pathlib.Path, registry: dict, *, chart_version: str = CHART, pin: str = "",
           credentials: bool = True, unreachable: str = "",
           step: tuple[pathlib.Path, str, str] = (HELM, "release", LABEL_STEP)) -> tuple[subprocess.CompletedProcess, str, dict]:
    """Run `step` (the label step unless told otherwise) as GitHub runs `shell: bash`, in a tree carrying the
    real chart files."""
```

### Block 17 — local-development/tests/test_supply_chain.py: the step lifted is the one asked for

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
    script.write_text(_step(_jobs(HELM)["release"], LABEL_STEP)["run"])
```

```python
    script.write_text(_step(_jobs(step[0])[step[1]], step[2])["run"])
```

### Block 18 — local-development/tests/test_supply_chain.py: the pull-request check, run against the stub (T410-22 to T410-26)

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
        if not published:
            assert f"{REPORT}:{APP} is application unknown, not {APP} (#410)" in done.stdout
```

```python
        if not published:
            assert f"{REPORT}:{APP} is application unknown, not {APP} (#410)" in done.stdout


class TestTheChartVersionIsNeverAReleasedApplicationVersion:
    """The second writer of `:<chartVersion>` (SPEC_E8, Orchestrator's note 2): publish.yml's --release-tags
    copies every application release there too, so a chart numbered like a released application overwrites
    that application's alias on the release merge whatever helm.yaml refuses. ci.yml refuses the version in
    the pull request instead. The step is lifted from the parsed ci.yml and run against the stub skopeo."""

    STEP = (CI, "version-bump", "The chart version is not a released application version")

    def test_t410_22_the_check_runs_in_the_pull_request_only_job_after_the_bump_check(self) -> None:
        job = _jobs(CI)["version-bump"]
        assert job["if"] == "github.event_name == 'pull_request'"
        names = [s.get("name") for s in job["steps"]]
        assert names.index("A change under charts/ requires a new Chart.yaml version") < names.index(self.STEP[2])

    def test_t410_23_a_chart_version_that_is_a_released_application_version_is_refused(self, tmp_path) -> None:
        registry = _released()
        _push(registry, DASHBOARD, "1.0.0", "1.0.0")
        done, log, _ = _label(tmp_path, registry, chart_version="1.0.0", step=self.STEP)
        assert done.returncode == 1, done.stdout + done.stderr
        assert "chart version 1.0.0 is a released application version" in done.stdout
        assert "skopeo copy" not in log and "skopeo login" not in log

    def test_t410_24_a_chart_version_tag_that_is_this_chart_s_own_label_passes(self, tmp_path) -> None:
        """`:0.59.25` is application 2.0.0's bytes (measured on quay): the tag is the chart's, not an alias."""
        registry = _released()
        registry["tags"][f"{DASHBOARD}:{CHART}"] = registry["tags"][f"{DASHBOARD}:{APP}"]
        done, _, _ = _label(tmp_path, registry, step=self.STEP)
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"{DASHBOARD}:{CHART} is application {APP}, not application {CHART}'s alias" in done.stdout

    def test_t410_25_an_absent_tag_is_a_free_version(self, tmp_path) -> None:
        done, _, _ = _label(tmp_path, _released(), step=self.STEP)
        assert done.returncode == 0, done.stdout + done.stderr
        assert f"{DASHBOARD}:{CHART} does not exist: the chart version is free" in done.stdout

    def test_t410_26_unreachable_is_not_free(self, tmp_path) -> None:
        done, _, _ = _label(tmp_path, _released(), unreachable=f"{DASHBOARD}:{CHART}", step=self.STEP)
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"cannot tell whether {DASHBOARD}:{CHART} is a released application version" in done.stdout
```

### Block 19 — .github/workflows/helm.yaml: the existence check tells an unreachable registry from a missing image (OB2, the review of PR #529, F1)

<!-- block: .github/workflows/helm.yaml | edit -->
```yaml
          if ! SOURCE_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${REPO}:${SOURCE}" 2>/dev/null); then
```

```yaml
          # Unreachable is not absent (Orchestrator's note 6) here too: only the registry's "manifest unknown" means
          # the image was never published. Any other failure (DNS, 401, 429, a timeout) is "cannot tell", and the
          # remedy is a re-run, never the disaster-recovery push the message below prescribes.
          probe_err=$(mktemp)
          trap 'rm -f "${probe_err}"' EXIT
          if ! SOURCE_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${REPO}:${SOURCE}" 2>"${probe_err}"); then
            if ! grep -qi 'manifest unknown' "${probe_err}"; then
              echo "::error::cannot tell whether ${REPO}:${SOURCE} exists, so chart ${CHART_VERSION} is NOT published"
              echo "::error::and nothing was copied:"
              echo "::error::$(head -c 400 "${probe_err}")"
              echo "::error::Re-run this workflow once the registry answers."
              exit 1
            fi
```

### Block 20 — .github/workflows/helm.yaml: one temporary file and one trap for both probes (OB2, the review of PR #529, F1)

<!-- block: .github/workflows/helm.yaml | edit -->
```yaml
          probe_err=$(mktemp)
          trap 'rm -f "${probe_err}"' EXIT
          if TARGET_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${REPO}:${CHART_VERSION}" 2>"${probe_err}"); then
```

```yaml
          if TARGET_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${REPO}:${CHART_VERSION}" 2>"${probe_err}"); then
```

### Block 21 — local-development/tests/test_supply_chain.py: T410-27, an unreachable registry is not a missing image (OB2, the review of PR #529, F1)

<!-- block: local-development/tests/test_supply_chain.py | edit -->
```python
        assert log == "", "no registry call is made without credentials, as today"
```

```python
        assert log == "", "no registry call is made without credentials, as today"

    def test_t410_27_an_unreachable_registry_is_not_a_missing_image(self, tmp_path) -> None:
        """Unreachable is not absent for the first probe either (OB2's review of c825182c, measured with
        REGISTRY=quay.invalid): the existence check must not read a DNS failure, a 401 or a 429 as "the application
        release was never published" and prescribe the --release-tags push for a transient outage."""
        done, log, _ = _label(tmp_path, _released(), unreachable=f"{DASHBOARD}:{APP}")
        assert done.returncode == 1, done.stdout + done.stderr
        assert f"cannot tell whether {DASHBOARD}:{APP} exists" in done.stdout
        assert "no such host" in done.stdout, "the registry's own words are in the annotation"
        assert "does not exist" not in done.stdout and "--release-tags" not in done.stdout, done.stdout
        assert "skopeo copy" not in log and "skopeo login" not in log, log
```

### Block 22 — docs/guides/RELEASING.md: what "cannot tell whether <image>:<appVersion> exists" means (OB2, the review of PR #529, F1)

<!-- block: docs/guides/RELEASING.md | edit -->
```markdown
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
```

```markdown
| chart release run is red at "Label the image this chart version deploys" with `cannot tell whether <image>:<appVersion> exists` | the registry did not answer "manifest unknown": DNS, a 401, a 429, a timeout. Nothing was copied and no chart was published; the image may well exist | re-run the release once the registry answers. Do not run the `--release-tags` scripts for this: that route is for an image that was never published |
| chart release run is red at "Label the image this chart version deploys" with `<image>:<appVersion> is application X, not <appVersion> (#410)` | the tag exists but names another build: `publish.yml` has not moved the alias yet on the release merge, or the tag is a chart-version label on an old image (`:0.39.0` was application 0.24.0). Nothing was copied and no chart was published | wait for `publish.yml` on the release merge to finish green, then re-run the release. Never retag or delete the old tag by hand: a cluster, a mirror or a Helm release may pin it |
```

### Block 23 — docs/CHANGELOG.md: the entry names the existence check's new answer (OB2, the review of PR #529, F1)

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
  tag's own label; only `manifest unknown` means free). Workflows, tests and docs only: no application or chart
  version.
```

```markdown
  tag's own label; only `manifest unknown` means free). The step's existence check now tells an unreachable
  registry from a missing image: only `manifest unknown` prints the never-published remedy, anything else is
  "cannot tell, re-run". Workflows, tests and docs only: no application or chart version.
```
