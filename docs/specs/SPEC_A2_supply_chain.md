# SPEC A2 — SBOM, keyless signing, build and chart provenance

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | A — supply chain |
| Release | R4 — Supply chain and backup |
| Version on release | no app or chart version change (workflows and the build script only) |
| Issue | [#63](https://github.com/ephico2real2/group-sync-dashboard/issues/63) |
| Status | in progress |
| Source | design agent output `a38be666b46d57784`; one message; no seam |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- The operator answered on 2026-09-04 that public Rekor transparency-log entries are acceptable: keyless cosign through GitHub OIDC is the chosen mechanism.
- First feature of R4, before B1. Any version numbers in the body are superseded by the ladder in `docs/specs/README.md`.
- Citation corrected: the design cited the chart README with the anchor "(no `redirectMode` key)", which nests backticks that the citation grammar (path#anchor inside one backtick span) cannot express; the anchor now cites `redirectMode`, the row's own text.

- Routed here from the A3 review (PR #71, Codex C4): when this spec edits `.github/workflows/helm.yaml`, tighten the two `sed` extractors — `CHART_VERSION` to `^version: \([0-9]\+\.[0-9]\+\.[0-9]\+\)[ \t]*$` and `APP_VERSION` to `^appVersion: "\(.\+\)"$` — so they accept exactly the forms `prepare-release.py` and `build-and-push-external.sh` accept, and hold them with a test in `tests/test_workflow_pins.py`.
- Applied at implementation (PR for #63), 2026-09-05. Deviations, each with its reason: (1) the install guide's §7 examples name the current release pair (image `:0.15.0`, chart `0.16.0`) instead of the body's 0.11.0 / 0.10.0, which predate the ladder; (2) the CHANGELOG bullet lands under a new `## Unreleased` heading above `## Application 0.15.0 — chart 0.16.0`, because the body's anchor (A1's bullet followed by the 0.11.0 heading) no longer exists — the intro's convention is followed instead; and `tests/test_chart_versions.py`'s heading test, which allowed `## Unreleased` in its tuple but split the heading on ` — ` before comparing, raised on that heading — the date is now taken only from a heading that has one; (3) the routed `sed` tightening above is applied in PORTABLE basic regex — `[0-9][0-9]*` and `..*` — not the GNU-only `\+` the note prescribed: the test runs the real patterns through sed, and on macOS (BSD sed) `\+` matches nothing, which would have made the test red locally and the extractor silently empty for anyone running that step off the Ubuntu runner (measured here: the `\+` form printed nothing, the portable form printed `0.16.0`); the test lifts the patterns from `helm.yaml` and runs them against the forms they must accept and refuse; (4) every action pin was re-verified against `git/ref/tags` on 2026-09-05 (six matches, all the latest releases), the two actions' input names were read from their `action.yml` at the pinned commits, and cosign v3.1.3 and Syft v1.51.1 were confirmed as the latest releases; (5) operator questions Q2 (cosign major) and Q4 (robot scope) were unanswered when the PR opened — the defaults the body states are taken and posted on #63. (6) Files and hunks outside the body's list, all bookkeeping: this spec's notes and its header's status (`specified` → `in progress`), the same status in `docs/specs/README.md`, and `local-development/tests/test_docs_citations.py` (registers `docs/REVIEW_A2.md`, the review record). (7) From the adversarial review (`docs/REVIEW_A2.md`): the alias copy is `skopeo copy --all --preserve-digests` — skopeo's default is "the source manifest type, with fallbacks", and a fallback rewrites the digest the script just recorded; the `attest` job runs only for `refs/heads/main` and verifies the identity `…/publish.yml@refs/heads/main` (pinned, not `github.ref`), because a `workflow_dispatch` from another branch would sign under that branch, pass its own read-back and fail the install guide's command — such a dispatch pushes unsigned, which `DESIGN_supply_chain.md` states (D9); the install guide's `cosign verify` names the immutable tag, since an ordinary merge signs only `:<appVersion>-<sha>` and the alias moves on an application release; the design's D7 states the two limits of the in-run proof (the cosign major, and a signature written before a failed read-back). Measured for that review: quay.io answers the OCI 1.1 referrers endpoint for this repository (HTTP 200, an OCI index), and cosign 3.1.3 keeps `--new-bundle-format` (default true, marked deprecated, so absent from its documentation) — Q2's "one-flag change" is therefore a deprecated flag, which the note on #63 records. (8) From Codex's pass of the same review: sbom-action names the file INSIDE the artifact after `artifact-name` (its `uploadSbomArtifact` writes `${tempDir}/${artifactName}`, read at the pinned commit), so the attest job downloads to `downloaded-sbom/` and reads `sbom-<sha>` — the body's `test -s sbom.spdx.json` would have failed the first run; the build script checks the digest with `^sha256:[0-9a-f]{64}$` (the body's glob accepted one hex digit followed by anything); `helm.yaml`'s image-label step — outside the body's edits — copies with `--all --preserve-digests` and compares the alias digest, the same rule the build script holds, because that tag is one the signed digest must resolve to; the extractors use `[[:blank:]]` (BSD sed reads `\t` in a bracket as a literal `t`: the class refused a tab and accepted `1.2.3t`, measured) and the appVersion class is the semver itself, not the greedy `..*`; the install guide and design no longer say a signature "travels with `skopeo copy --all`" (that copies an index's platforms, not a subject's referrers — `oras cp --recursive` does) nor that a fork "signs as itself" (the `publish` job is skipped on forks by the repository guard). Rejected with the reason: gating the `publish` job itself on `main` (a `workflow_dispatch` from a branch may still push an unsigned immutable tag; only signing is main-only), and the diff-asserting and prose-asserting tests. (9) Second pass (`docs/REVIEW_A2.md`): the install guide's `cosign verify-attestation` and `gh attestation verify` examples name the immutable tag like the first command, its opening sentence carries the D9 caveat, and the chart example uses `<version>` (0.16.0 predates the attestation); `helm.yaml`'s label step runs under `set -euo pipefail` so a refused `skopeo copy --preserve-digests` ends the step instead of being followed by a comparison against a tag that already existed; `README.md` says the signing happens on `main`. Rejected, measured: a claim that `skopeo inspect --format '{{.Digest}}'` reports a platform child's digest for an index — on `quay.io/podman/hello:latest` (a four-platform list) under `--override-os linux --override-arch amd64` it printed the list digest, equal to the sha256 of the raw index and different from the amd64 child, so the comparison is right for a single manifest and for an index, and the proposed `--raw | sha256` replacement was not taken. (10) Codex's second pass: `prepare-release.py`'s `SEMVER` uses `[0-9]` with `re.ASCII` — `\d` accepted Arabic-Indic and full-width digits that `int()` parses and the workflows' `[0-9]` extractors refuse (measured: `١.٢.٣` passed the script and matched nothing in BSD sed); the install guide's fork paragraph says forks do not sign under this workflow (the `publish` job is skipped by the repository guard), matching D3. The review range `d0d2985..cd92020` also carries the merge of `origin/main` (464d963), which brought PR #81's release marking of C2 (`docs/specs/README.md`, `SPEC_C2_users_tab_providers_identities.md`) and nothing of A2's; Codex's diff-asserting test for that was rejected as before.

## Batch preamble (verbatim from the design)

# Design: A1 (UI tests in CI), A2 (SBOM, signing, provenance), A3 (release preparation script)

Every claim below is grounded in a file read in this session, cited as `path#anchor`. Nothing was written.

## 0. The amended house rule, applied

Each feature is a module with one switch; the default is a judgment, and the rationale is in the comment beside the switch.

| Feature | Switch | Default | Why |
|---|---|---|---|
| A1 browser tests in CI | repository variable `CI_UI_TESTS` (`ci.yml` `ui` job, `if: vars.CI_UI_TESTS != 'false'`) | **ON** | needs no credential, no cluster, no second image; only a Chromium download. The tests already exist (`local-development/tests/test_ui.py#dash`), and a green CI that skips them is the failure `ci.yml#Unit and integration tests` names. A fork or self-hosted runner that cannot fetch browsers sets it to `false`; the `tests` matrix is byte-identical either way. |
| A2 SBOM | repository variable `SUPPLY_CHAIN_SBOM` (`publish.yml` `sbom` job) | **ON** | reads the pushed image with the same registry credential the publish job already holds; produces a workflow artifact; no identity, no publication change. |
| A2 signing + provenance (image and chart) | repository variable `SUPPLY_CHAIN_SIGNING` (`publish.yml` `attest` job, `helm.yaml` chart attestation steps) | **ON** | keyless: GitHub OIDC (`id-token: write`) needs no secret. What it needs instead is stated in the workflow comment: egress to `fulcio.sigstore.dev`, `rekor.sigstore.dev`, `tuf-repo-cdn.sigstore.dev`, and a repository that is not a fork (forks are already skipped by `publish.yml#github.repository ==`). A self-hosted runner without that egress sets it to `false`. Signing changes nothing that is published — it adds referrers beside the image and records in GitHub's store. |
| A2 interaction | modelled, not left to chance | — | `attest` `needs: [publish, sbom]` with `!cancelled()`; the SBOM is attached only when `needs.sbom.result == 'success'`, and a step says by name when it is not. SBOM off + signing on: image signed, provenance attested, no SBOM attestation. SBOM on + signing off: SBOM artifact only. Chart attestation runs only when chart-releaser will publish a NEW version (`helm.yaml` `steps.plan.outputs.new`), so a skipped version attests nothing and says so. |
| A3 release script | invocation is the switch; side effects have their own: `--no-commit` (edit only), `--pr` (open the PR, off by default) | **ON** (exists; off = nobody ran it) | a script that edits a working tree and commits to a new branch has no cluster-wide side effect and never touches `main` — the `docs/RELEASING.md#Nothing else couples them` model is preserved. |

No Helm value is added by any feature. A chart value read by nothing is exactly the debt `charts/group-sync-dashboard/README.md#redirectMode` records removing, and `local-development/tests/test_environments_readme.py#test_every_key_in_the_table_still_exists_in_the_chart` would fail a README row with no key behind it. Nothing in A1–A3 runs in a pod. So the chart README values table gains no row, and Chart.yaml is not bumped (no PR touches `charts/`), which keeps `ci.yml#Chart changes bump the chart version` green without a version move.

Repository-wide conventions relied on:

- `docs/CHANGELOG.md` heading convention `## Application X — chart Y — date` (and `## Chart X — application Y — date` for chart-led releases). None of these PRs is a release, so A1 introduces a `## Unreleased` heading that A3's script converts into the release heading. The intro paragraph says so.
- `local-development/tests/test_docs_citations.py#CITATION` — every `` `path#anchor` `` in new docs below names a substring that exists in the cited file (`.py` anchors resolve through the AST or as a substring).
- Action pins: full commit of a release tag with the version in a comment (`ci.yml#ACTION PINS`). All SHAs below were resolved with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, annotated tags through `git/tags/<sha>`:

| Action | Tag | Commit | `runs.using` |
|---|---|---|---|
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | node24 |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | node24 |
| `anchore/sbom-action` | v0.24.2 (annotated → commit) | `3ad7283483fc7af8ff2b4ea19663c2d5ca935e26` | node24 |
| `sigstore/cosign-installer` | v4.1.2 | `6f9f17788090df1f26f669e9d70d6ae9567deba6` | composite |
| `actions/attest-build-provenance` | v4.2.2 | `4d101475d8b20a2381f78447822ac1eab6504dd8` | composite (wraps `actions/attest` v4.2.1, pinned inside) |
| `helm/chart-releaser-action` | v1.7.0 (annotated → commit) | `cae68fefc6b5f367a0275617c9f83181ba54714f` | composite |

`helm.yaml` today uses `helm/chart-releaser-action@v1.7.0` — a mutable tag, against the rule at `ci.yml#ACTION PINS`. A2 pins it and adds a test so it cannot regress.

Tool pins: Syft `v1.51.1` (the version `docs/image-vulnerability-scan.md#Tools:` measured identifying Hummingbird; latest release on 2026-09-04), cosign `v3.1.3` (latest release; the installer's own default is v3.0.6), playwright `1.62.0` + pytest-playwright `0.8.0` (the pair in the local venv that runs the suite today; pytest-playwright 0.9.0 exists and is not yet exercised locally).

Order of PRs: **A1 → A2 → A3.** A1 creates `## Unreleased`; A2 adds the pin test that A1's actions must already satisfy; A3 converts `## Unreleased` and is documented in RELEASING.md on top of A2's diagram.

---


## Design (verbatim)

## FEATURE A2 — SBOM, keyless image signing, SLSA provenance, chart provenance

### Goal and switches

After `publish.yml` pushes an image, a `sbom` job catalogues it by digest (Syft → SPDX JSON, workflow artifact) and an `attest` job signs the digest keyless with cosign, attaches the SBOM as a cosign attestation, and records SLSA build provenance in GitHub's attestation store — each read back before the run is green. `helm.yaml` attests the packaged chart the same way. Operators verify with `cosign verify`, `cosign verify-attestation`, and `gh attestation verify`.

Decisions, each with the reason:

1. **The digest comes from `podman push --digestfile`**, in `build-and-push-external.sh`, handed to the workflow through `DIGEST_FILE`. That is the digest the registry acknowledged, which is the only one worth signing; a locally computed manifest digest can differ after compression. Verified `podman push --help` lists `--digestfile` on this machine.
2. **The aliases are made with `skopeo copy`, not `podman tag && podman push`.** A signature is over one digest; `cosign verify quay.io/…:0.11.0` resolves the tag and must land on that digest. `podman push` re-uploads from the local store and can yield a different manifest for the same image; `skopeo copy` moves the manifest server side — the call `helm.yaml#Copy rather than pull-tag-push` already makes, and where it measured both tags reporting the same digest. The script reads the alias's digest back (`skopeo inspect --format '{{.Digest}}'`) and refuses a mismatch. skopeo shares podman's `containers/auth.json`, so no second login; it is present on ubuntu-latest (helm.yaml already calls it) and on the DR laptop (`which skopeo` → `/usr/local/bin/skopeo`).
3. **Signing runs in a separate job.** `tests/test_publish_release_decision.py#test_the_publish_job_can_write_to_nothing_but_the_registry` asserts `publish` holds exactly `{contents: read}` and calls it THE LOAD-BEARING ASSERTION. A new `attest` job holds `id-token: write` + `attestations: write` + `contents: read`; the `publish` job and its test are untouched. A new test asserts no job in the file holds `contents: write` or `actions: write`.
4. **SBOM via `anchore/sbom-action`** with `image:` and registry credentials — the action prefixes `registry:` itself when `registry-username` is set (read in its `SyftGithubAction.ts#registry:${input.image}`), so it scans the pushed image without a daemon. `syft-version: v1.51.1` is held by a test to the version `docs/image-vulnerability-scan.md` measured. SPDX JSON, `upload-artifact: true`, `upload-release-assets: false` (a push has no release), `dependency-snapshot: false`.
5. **SBOM attached with `cosign attest --type spdxjson`**, so it travels with the image in any registry (cosign falls back to tag-based storage where OCI referrers are unsupported). `actions/attest-sbom` exists (v4.1.0) but would store the SBOM only in GitHub; an air-gapped mirror that copied the image with `skopeo copy --all` keeps cosign's attestation and loses GitHub's.
6. **Provenance via `actions/attest-build-provenance`** with `subject-name`/`subject-digest`, `push-to-registry: false`: verification is `gh attestation verify`, which reads GitHub's store; pushing a second copy needs a docker login inside the action and buys no verifier anything.
7. **Chart provenance: GitHub attestation of the `.tgz`, not `helm package --sign`.** GPG needs a long-lived private key in a secret (the very thing keyless removes), a keyring distributed out of band, and `helm verify` on the consumer's side; chart-releaser can be told to sign (`CR_KEY`/`CR_KEYRING`), but then this repo would hold two signing models. Not cosign `sign-blob` either: chart-releaser publishes the tgz to gh-pages and a GitHub Release, and a `.bundle` beside it would need a second upload path and would not travel through `helm pull`. `attest-build-provenance` on `.cr-release-packages/<name>-<version>.tgz` (cr's default `--package-path`, read in `chart-releaser/cr/cmd/package.go`) is one identity for image and chart, verifiable with `gh attestation verify <file>`. It runs only when the `plan` step says the version is new — a skipped release attests nothing and says so.
8. **Rekor.** Keyless signing writes a public transparency-log entry (identity + digest). This is a public project on a public registry; the design doc says so.
9. **Every signature is read back in the same run** (`cosign verify`, `cosign verify-attestation`, `gh attestation verify`) with the exact flags the docs give operators. If Quay cannot hold cosign v3's bundle format, or the identity string is wrong, the run is red on the first day — not a consumer's cluster.

### Files

#### `local-development/build-and-push-external.sh` — edits

Edit 1 (header, after the alias paragraph). Old:
```bash
#   <chartVersion>      --release-tags, because pushing these overwrites what the last release
#                       published — see the block above the push for why that is opt-in.
#
# Configuration comes from .env (gitignored) or the environment. Credentials are never
```
New:
```bash
#   <chartVersion>      --release-tags, because pushing these overwrites what the last release
#                       published — see the block above the push for why that is opt-in.
#
# ONE DIGEST, HOWEVER MANY NAMES. The immutable tag is pushed once and podman records the digest
# the registry acknowledged (--digestfile); the aliases are then made by `skopeo copy` from that
# pushed manifest, server side, and read back — so every name this script publishes resolves to
# the same bytes and a signature over the digest covers all of them. DIGEST_FILE=<path> in the
# environment receives a copy of the digest, which is how .github/workflows/publish.yml hands it
# to the job that signs it. --release-tags therefore needs skopeo, which ships beside podman.
#
# Configuration comes from .env (gitignored) or the environment. Credentials are never
```

Edit 2 (fail fast on a missing skopeo). Old:
```bash
missing=()
[ -z "$REGISTRY" ] && missing+=(REGISTRY)
[ -z "$REGISTRY_NAMESPACE" ] && missing+=(REGISTRY_NAMESPACE)
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: missing required config: ${missing[*]}" >&2
  echo "       set them in .env (see .env.example) or in the environment" >&2
  exit 1
fi
```
New:
```bash
missing=()
[ -z "$REGISTRY" ] && missing+=(REGISTRY)
[ -z "$REGISTRY_NAMESPACE" ] && missing+=(REGISTRY_NAMESPACE)
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: missing required config: ${missing[*]}" >&2
  echo "       set them in .env (see .env.example) or in the environment" >&2
  exit 1
fi
# Checked BEFORE the build, not at the alias step forty seconds of build later. The aliases are
# server-side copies (see the release block), and skopeo is what makes them.
if [ "$RELEASE_TAGS" = true ] && ! command -v skopeo >/dev/null 2>&1; then
  echo "ERROR: --release-tags copies the aliases with skopeo, which is not on PATH." >&2
  exit 1
fi
```

Edit 3 (the push). Old:
```bash
podman push "${REF}"
echo "pushed  : ${REF}"
```
New:
```bash
# --digestfile: the digest the REGISTRY acknowledged, which is the only digest worth recording.
# `podman inspect` reports a local image ID, and a manifest digest computed before the push can
# differ from what lands after compression. Whatever signs this image signs THIS value.
DIGEST_OUT=$(mktemp)
podman push --digestfile "${DIGEST_OUT}" "${REF}"
DIGEST=$(tr -d '\r\n' < "${DIGEST_OUT}")
rm -f "${DIGEST_OUT}"
case "${DIGEST}" in
  sha256:[0-9a-f]*) ;;
  *) echo "ERROR: podman reported no sha256 digest for ${REF} (got '${DIGEST}')" >&2; exit 1 ;;
esac
echo "pushed  : ${REF}"
echo "digest  : ${DIGEST}"
if [ -n "${DIGEST_FILE:-}" ]; then
  printf '%s\n' "${DIGEST}" > "${DIGEST_FILE}"
  echo "digest  : written to ${DIGEST_FILE}"
fi
```

Edit 4 (the aliases). Old:
```bash
  for alias in "${VERSION}" "${CHART_VERSION}"; do
    ALIAS_REF="${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}:${alias}"
    podman tag "${REF}" "${ALIAS_REF}"
    podman push "${ALIAS_REF}"
    echo "pushed  : ${ALIAS_REF}  (alias of ${TAG})"
  done
```
New:
```bash
  # COPIED IN THE REGISTRY, NOT PUSHED AGAIN. A second `podman push` re-uploads from the local
  # store and can produce a different manifest digest for the same image — and then the alias
  # `:<appVersion>` would not resolve to the digest that was signed, so `cosign verify` on the
  # name every chart resolves would fail. `skopeo copy` between two tags of one repository moves
  # the manifest server side — the same call helm.yaml makes to label a chart's image — and the
  # digest is read back and compared, so an alias that is not byte-identical to the immutable
  # tag is a refusal here rather than a signature that fails on somebody's cluster.
  for alias in "${VERSION}" "${CHART_VERSION}"; do
    ALIAS_REF="${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}:${alias}"
    skopeo copy "docker://${REF}" "docker://${ALIAS_REF}"
    ALIAS_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${ALIAS_REF}")
    if [ "${ALIAS_DIGEST}" != "${DIGEST}" ]; then
      echo "ERROR: ${ALIAS_REF} resolves to ${ALIAS_DIGEST}, not ${DIGEST} — the alias is not the" >&2
      echo "       image that was pushed. Nothing else was changed; inspect both before retrying." >&2
      exit 1
    fi
    echo "pushed  : ${ALIAS_REF}  (alias of ${TAG}, ${DIGEST})"
  done
```

#### `.github/workflows/publish.yml` — edits

Edit 1 (header paragraph). Old:
```yaml
# The script also refuses a dirty tree and a placeholder password, and both guards are worth having
# in CI. It remains the disaster-recovery path — a laptop can do everything this workflow does,
# which matters on the day Actions is down.
name: publish
```
New:
```yaml
# The script also refuses a dirty tree and a placeholder password, and both guards are worth having
# in CI. It remains the disaster-recovery path — a laptop can do everything this workflow does,
# which matters on the day Actions is down.
#
# TWO JOBS FOLLOW THE PUSH, and neither touches this repository either. `sbom` catalogues the
# pushed image by digest (Syft, SPDX JSON, kept as a workflow artifact); `attest` signs that digest
# keyless with cosign through GitHub's OIDC identity, attaches the SBOM as an attestation, records
# SLSA build provenance in GitHub's attestation store, and READS EACH ONE BACK with the commands
# the install guide gives operators, so a signature nobody could verify is a red run here. They
# are separate jobs so that `publish` keeps holding exactly `contents: read` — the property
# tests/test_publish_release_decision.py calls load-bearing — while only `attest` holds
# `id-token: write`. Each has a repository-variable switch, documented on the job.
name: publish
```

Edit 2 (job outputs). Old:
```yaml
    if: github.repository == 'ephico2real2/group-sync-dashboard'
    runs-on: ubuntu-latest

    permissions:
```
New:
```yaml
    if: github.repository == 'ephico2real2/group-sync-dashboard'
    runs-on: ubuntu-latest
    # What the two jobs below need: the digest the registry acknowledged and the repository it
    # lives in. Empty when nothing was pushed, and both jobs key on that.
    outputs:
      digest: ${{ steps.build.outputs.digest }}
      image: ${{ steps.build.outputs.image }}

    permissions:
```

Edit 3 (preflight names skopeo). Old:
```yaml
          podman --version
          python3 --version
```
New:
```yaml
          podman --version
          python3 --version
          skopeo --version   # the release aliases are server-side copies made by skopeo
```

Edit 4 (the build step). Old:
```yaml
      - name: Build and push the image
        if: steps.creds.outputs.configured == 'true'
        shell: bash
        working-directory: local-development
        env:
```
New:
```yaml
      - name: Build and push the image
        id: build
        if: steps.creds.outputs.configured == 'true'
        shell: bash
        working-directory: local-development
        env:
          # Where the script writes the digest the registry acknowledged for the immutable tag.
          # The attest job signs THAT, by digest, never a tag.
          DIGEST_FILE: ${{ runner.temp }}/pushed.digest
```
and, Old:
```yaml
          if [ "${IS_RELEASE}" = "true" ]; then
            ./build-and-push-external.sh --release-tags
          else
            ./build-and-push-external.sh
          fi
```
New:
```yaml
          if [ "${IS_RELEASE}" = "true" ]; then
            ./build-and-push-external.sh --release-tags
          else
            ./build-and-push-external.sh
          fi
          digest=$(tr -d '\r\n' < "${DIGEST_FILE}")
          echo "digest=${digest}" >> "$GITHUB_OUTPUT"
          echo "image=${REGISTRY}/${REGISTRY_NAMESPACE}/group-sync-dashboard" >> "$GITHUB_OUTPUT"
```

Edit 5 (two new jobs appended at the end of the file, after the last line `          fi`):
```yaml

  # ── The SBOM ─────────────────────────────────────────────────────────────────────────────────
  #
  # SWITCH: repository variable SUPPLY_CHAIN_SBOM; anything but 'false' runs it. ON by default: it
  # reads the image that was just pushed with the credential the publish job already holds, writes
  # one file, and changes nothing that is published. Off on a runner that cannot reach the registry
  # anonymously-plus-credential, or when an SBOM is produced elsewhere.
  #
  # BY DIGEST, so the catalogue describes the bytes that were pushed and not whatever a tag
  # resolves to a minute later. Syft is pinned to the version docs/image-vulnerability-scan.md
  # measured identifying Hummingbird OS; a test holds the two together, because a Syft that does
  # not recognise the base produces an SBOM with no OS packages in it — a document that is
  # complete-looking and wrong, the failure this repo has met with Trivy and with Grype's default.
  sbom:
    name: SBOM of the pushed image
    needs: publish
    if: needs.publish.outputs.digest != '' && vars.SUPPLY_CHAIN_SBOM != 'false'
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Catalogue the image, by digest
        uses: anchore/sbom-action@3ad7283483fc7af8ff2b4ea19663c2d5ca935e26 # v0.24.2
        with:
          # The action prefixes `registry:` itself when a username is given, so Syft reads the
          # registry directly — there is no daemon on this runner holding the image.
          image: ${{ needs.publish.outputs.image }}@${{ needs.publish.outputs.digest }}
          registry-username: ${{ secrets.REGISTRY_USERNAME }}
          registry-password: ${{ secrets.REGISTRY_PASSWORD }}
          syft-version: v1.51.1
          format: spdx-json
          output-file: sbom.spdx.json
          artifact-name: sbom-${{ github.sha }}
          upload-artifact: true
          upload-artifact-retention: 90
          # A push has no release to attach assets to, and the dependency graph is for source
          # manifests, not image inventories.
          upload-release-assets: false
          dependency-snapshot: false

  # ── Signature, SBOM attestation, provenance ──────────────────────────────────────────────────
  #
  # SWITCH: repository variable SUPPLY_CHAIN_SIGNING; anything but 'false' runs it. ON by default
  # because keyless signing needs NO SECRET: the job's OIDC token (id-token: write) is exchanged
  # with Fulcio for a certificate that lives minutes, and the signature is recorded in Rekor's
  # public transparency log — which is a public entry naming this repository, the workflow and the
  # digest, appropriate for a public image. What it needs instead of a secret: egress to
  # fulcio.sigstore.dev, rekor.sigstore.dev and tuf-repo-cdn.sigstore.dev, and a run in THIS
  # repository (a fork never gets an OIDC token for this identity, and is already skipped by the
  # publish job's repository guard). A self-hosted runner without that egress sets the variable
  # to false; nothing else in the workflow changes.
  #
  # A JOB OF ITS OWN so that `publish` keeps holding exactly contents: read. Everything here signs
  # or attests the digest the publish job reported — never a tag, which is a name somebody can move.
  #
  # THE SBOM IS A DEPENDENCY, NOT A REQUIREMENT. `needs: sbom` with !cancelled() means this job
  # runs when the sbom job was skipped by its own switch; the two attach steps then do not run and
  # a step says so by name, so "signed, no SBOM attached" is a stated outcome and not a guess.
  #
  # EVERY ARTEFACT IS READ BACK before the job is green, with the flags the install guide gives
  # operators. If the registry cannot hold the bundle, or the identity string is wrong, this run
  # is red — not a consumer's `cosign verify` on a cluster.
  attest:
    name: Sign the image and attest its provenance
    needs: [publish, sbom]
    if: >-
      !cancelled()
      && needs.publish.result == 'success'
      && needs.publish.outputs.digest != ''
      && vars.SUPPLY_CHAIN_SIGNING != 'false'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      # The OIDC token Fulcio exchanges for a short-lived signing certificate.
      id-token: write
      # To store the provenance statement in this repository's attestation store.
      attestations: write
    env:
      IMAGE: ${{ needs.publish.outputs.image }}
      DIGEST: ${{ needs.publish.outputs.digest }}
      # The certificate's subject for a GitHub-issued keyless signature: this workflow FILE at
      # the ref that ran. The install guide quotes this exact string with refs/heads/main.
      IDENTITY: https://github.com/${{ github.repository }}/.github/workflows/publish.yml@${{ github.ref }}
      ISSUER: https://token.actions.githubusercontent.com
    steps:
      - uses: sigstore/cosign-installer@6f9f17788090df1f26f669e9d70d6ae9567deba6 # v4.1.2
        with:
          # Pinned: the installer's own default trails releases, and the bundle format a cosign
          # writes is what a consumer's cosign must read. Move it with the install guide.
          cosign-release: v3.1.3

      - name: Log in to the registry, for the signature push
        shell: bash
        env:
          REGISTRY: ${{ vars.REGISTRY || 'quay.io' }}
          REGISTRY_USERNAME: ${{ secrets.REGISTRY_USERNAME }}
          REGISTRY_PASSWORD: ${{ secrets.REGISTRY_PASSWORD }}
        run: |
          # --password-stdin, never on the command line — the same rule as the build script.
          printf '%s' "${REGISTRY_PASSWORD}" \
            | cosign login "${REGISTRY}" --username "${REGISTRY_USERNAME}" --password-stdin

      - name: Sign the digest, keyless
        shell: bash
        run: cosign sign --yes "${IMAGE}@${DIGEST}"

      - name: Read the signature back
        shell: bash
        run: |
          set -euo pipefail
          cosign verify \
            --certificate-identity "${IDENTITY}" \
            --certificate-oidc-issuer "${ISSUER}" \
            "${IMAGE}@${DIGEST}" > /dev/null
          echo "signature verifies for ${IMAGE}@${DIGEST} as ${IDENTITY}"

      - name: Fetch the SBOM the sbom job produced
        if: needs.sbom.result == 'success'
        uses: actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c # v8.0.1
        with:
          name: sbom-${{ github.sha }}

      - name: Attach the SBOM as an attestation, and read it back
        if: needs.sbom.result == 'success'
        shell: bash
        run: |
          set -euo pipefail
          test -s sbom.spdx.json
          cosign attest --yes --type spdxjson --predicate sbom.spdx.json "${IMAGE}@${DIGEST}"
          cosign verify-attestation --type spdxjson \
            --certificate-identity "${IDENTITY}" \
            --certificate-oidc-issuer "${ISSUER}" \
            "${IMAGE}@${DIGEST}" > /dev/null
          echo "SBOM attestation verifies for ${IMAGE}@${DIGEST}"

      - name: Say so when there is no SBOM to attach
        if: needs.sbom.result != 'success'
        shell: bash
        env:
          SBOM_RESULT: ${{ needs.sbom.result }}
        run: |
          echo "::notice::the sbom job's result is '${SBOM_RESULT}' (SUPPLY_CHAIN_SBOM off, or it failed),"
          echo "::notice::so ${IMAGE}@${DIGEST} is signed and its provenance attested, with no SBOM attached."

      - name: Attest build provenance (SLSA)
        uses: actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8 # v4.2.2
        with:
          subject-name: ${{ env.IMAGE }}
          subject-digest: ${{ env.DIGEST }}
          # GitHub's store is what `gh attestation verify` reads; a second copy in the registry
          # would need a docker login inside the action and serve no verifier this repo documents.
          push-to-registry: false

      - name: Read the provenance back
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          gh attestation verify "oci://${IMAGE}@${DIGEST}" \
            --repo "${GITHUB_REPOSITORY}" \
            --signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/publish.yml"
```

Note on step names: `tests/test_publish_release_decision.py#step` requires exactly one `publish` step whose name contains `"application release"` and one containing `"Build and push the image"`; no new step in the `publish` job uses either fragment, and the new jobs are outside `jobs.publish`.

#### `.github/workflows/helm.yaml` — edits

Edit 1 (permissions). Old:
```yaml
    permissions:
      # chart-releaser pushes the packaged chart and the index to gh-pages, and creates a
      # GitHub release per chart version. Both need write.
      contents: write
    runs-on: ubuntu-latest
```
New:
```yaml
    permissions:
      # chart-releaser pushes the packaged chart and the index to gh-pages, and creates a
      # GitHub release per chart version. Both need write.
      contents: write
      # For the chart's provenance attestation (the last two steps): the OIDC token Fulcio
      # exchanges for a signing certificate, and the store the statement is written to. Neither
      # widens what this job can do to the repository.
      id-token: write
      attestations: write
    runs-on: ubuntu-latest
```

Edit 2 (the plan step gains outputs). Old:
```yaml
      - name: Report what this run will publish
        run: |
          set -uo pipefail
          version=$(grep -E '^version:' charts/group-sync-dashboard/Chart.yaml | awk '{print $2}')
          echo "Chart.yaml version: $version"
          if git rev-parse --verify --quiet "refs/tags/group-sync-dashboard-${version}" >/dev/null; then
            # No backticks anywhere in this block: inside a run: script bash reads them as
            # command substitution, so a prose backtick around a field name becomes an attempt
            # to execute it.
            echo "::warning::group-sync-dashboard-${version} is already released, so this run will"
            echo "::warning::publish NOTHING. Bump the version field in"
            echo "::warning::charts/group-sync-dashboard/Chart.yaml to release the current chart."
          else
            echo "will publish a new release: group-sync-dashboard-${version}"
          fi
```
New:
```yaml
      - name: Report what this run will publish
        # Also the DECISION the attestation steps at the end key on: only a NEW release has a
        # package to attest, and attesting on a skipped run would claim provenance for bytes this
        # run did not publish.
        id: plan
        run: |
          set -uo pipefail
          version=$(grep -E '^version:' charts/group-sync-dashboard/Chart.yaml | awk '{print $2}')
          echo "Chart.yaml version: $version"
          echo "version=${version}" >> "$GITHUB_OUTPUT"
          if git rev-parse --verify --quiet "refs/tags/group-sync-dashboard-${version}" >/dev/null; then
            # No backticks anywhere in this block: inside a run: script bash reads them as
            # command substitution, so a prose backtick around a field name becomes an attempt
            # to execute it.
            echo "::warning::group-sync-dashboard-${version} is already released, so this run will"
            echo "::warning::publish NOTHING. Bump the version field in"
            echo "::warning::charts/group-sync-dashboard/Chart.yaml to release the current chart."
            echo "new=false" >> "$GITHUB_OUTPUT"
          else
            echo "will publish a new release: group-sync-dashboard-${version}"
            echo "new=true" >> "$GITHUB_OUTPUT"
          fi
```

Edit 3 (pin chart-releaser and add the attestation steps). Old:
```yaml
      - name: Run chart-releaser
        uses: helm/chart-releaser-action@v1.7.0
        with:
          skip_existing: true
          packages_with_index: true
        env:
          CR_TOKEN: "${{ secrets.GITHUB_TOKEN }}"
```
New:
```yaml
      - name: Run chart-releaser
        uses: helm/chart-releaser-action@cae68fefc6b5f367a0275617c9f83181ba54714f # v1.7.0
        with:
          skip_existing: true
          packages_with_index: true
        env:
          CR_TOKEN: "${{ secrets.GITHUB_TOKEN }}"

      # ── Chart provenance ──────────────────────────────────────────────────────────────────────
      #
      # A GITHUB ATTESTATION OF THE .tgz, NOT `helm package --sign`. GPG signing needs a private
      # key held as a repository secret for years, a keyring handed to every consumer out of band,
      # and `helm verify` on their side; keyless needs none of that and is the same identity the
      # image is signed with (publish.yml). Not cosign sign-blob either: chart-releaser publishes
      # the package to gh-pages and a GitHub Release, and a bundle beside it would need a second
      # upload path that `helm pull` would never fetch. `gh attestation verify <file>` is the check.
      #
      # THE SUBJECT IS THE FILE chart-releaser UPLOADED — its package directory, .cr-release-packages,
      # is where cr packages and what it copies to gh-pages — so the attestation is over the bytes
      # `helm pull` returns. Only for a NEW release (steps.plan), and only with the same switch as
      # the image signing, so one variable turns every attestation this repository makes on or off.
      - name: Attest the provenance of the packaged chart
        if: steps.plan.outputs.new == 'true' && vars.SUPPLY_CHAIN_SIGNING != 'false'
        uses: actions/attest-build-provenance@4d101475d8b20a2381f78447822ac1eab6504dd8 # v4.2.2
        with:
          subject-path: .cr-release-packages/group-sync-dashboard-${{ steps.plan.outputs.version }}.tgz

      - name: Read the chart attestation back
        if: steps.plan.outputs.new == 'true' && vars.SUPPLY_CHAIN_SIGNING != 'false'
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
          VERSION: ${{ steps.plan.outputs.version }}
        run: |
          set -euo pipefail
          gh attestation verify ".cr-release-packages/group-sync-dashboard-${VERSION}.tgz" \
            --repo "${GITHUB_REPOSITORY}" \
            --signer-workflow "${GITHUB_REPOSITORY}/.github/workflows/helm.yaml"
```

#### `local-development/tests/test_supply_chain.py` — new

```python
"""What a consumer can verify about the image and the chart, and the switches that gate it.

THE CHAIN. build-and-push-external.sh pushes the immutable tag once and records the digest the
registry acknowledged (`podman push --digestfile`); the aliases are server-side copies of that
manifest, read back and compared. publish.yml hands the digest to two jobs: `sbom` catalogues it,
`attest` signs it keyless, attaches the SBOM, records SLSA provenance — and reads every one of
those back with the commands the install guide gives operators. helm.yaml attests the packaged
chart the same way, only when a new version is actually published.

WHY TEXT TESTS. None of this can run here: no registry, no OIDC token, no Fulcio. What CAN be held
is the shape — which job holds which permission, what is gated on what, that everything names the
digest and never a tag — because every defect this repo has had in its workflows was a shape
defect that a green run hid (#34, #37, the unpinned Grype). These read the real YAML and the real
script rather than restating either.

BOTH STATES. Each switch is asserted as the literal expression the workflow evaluates: unset or
anything but 'false' runs the job; 'false' skips it and leaves every other job untouched.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
PUBLISH = REPO / ".github" / "workflows" / "publish.yml"
HELM = REPO / ".github" / "workflows" / "helm.yaml"
SCRIPT = REPO / "local-development" / "build-and-push-external.sh"
SCAN_DOC = REPO / "docs" / "image-vulnerability-scan.md"
INSTALL_GUIDE = REPO / "docs" / "HELM_DOWNLOAD_AND_INSTALL.md"


def _jobs(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text())["jobs"]


def _code(job: dict) -> str:
    body = "\n".join(s.get("run") or "" for s in job["steps"])
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


def _script_code() -> str:
    return "\n".join(ln for ln in SCRIPT.read_text().splitlines() if not ln.strip().startswith("#"))


def _step(job: dict, fragment: str) -> dict:
    matched = [s for s in job["steps"] if fragment in (s.get("name") or "")]
    assert len(matched) == 1, f"expected one step matching {fragment!r}, found {len(matched)}"
    return matched[0]


# ── The digest chain ─────────────────────────────────────────────────────────────────────────


class TestTheDigestChain:
    def test_the_script_records_the_digest_the_registry_acknowledged(self) -> None:
        code = _script_code()
        assert 'podman push --digestfile "${DIGEST_OUT}" "${REF}"' in code
        assert "DIGEST_FILE" in code, "the workflow hands the digest on through DIGEST_FILE"

    def test_the_aliases_are_copied_in_the_registry_and_never_pushed_again(self) -> None:
        """A second podman push can land a different manifest digest for the same image, and then
        the alias the chart resolves would not be the digest that was signed."""
        code = _script_code()
        assert 'skopeo copy "docker://${REF}" "docker://${ALIAS_REF}"' in code
        assert "podman tag" not in code, "the aliases must not be re-pushed from the local store"

    def test_an_alias_that_is_not_the_signed_digest_is_refused(self) -> None:
        code = _script_code()
        assert "skopeo inspect --no-tags --format '{{.Digest}}'" in code
        assert 'if [ "${ALIAS_DIGEST}" != "${DIGEST}" ]; then' in code

    def test_a_missing_skopeo_fails_before_the_build(self) -> None:
        code = _script_code()
        check = code.index("command -v skopeo")
        build = code.index("podman build")
        assert check < build, "the skopeo check must come before the build, not forty seconds in"

    def test_the_script_still_parses(self) -> None:
        done = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr

    def test_the_build_step_hands_the_digest_to_the_next_jobs(self) -> None:
        publish = _jobs(PUBLISH)["publish"]
        build = _step(publish, "Build and push the image")
        assert build.get("id") == "build"
        assert "DIGEST_FILE" in (build.get("env") or {})
        assert 'echo "digest=${digest}" >> "$GITHUB_OUTPUT"' in build["run"]
        assert publish["outputs"] == {
            "digest": "${{ steps.build.outputs.digest }}",
            "image": "${{ steps.build.outputs.image }}",
        }


# ── The switches, and how they interact ───────────────────────────────────────────────────────


class TestTheSwitches:
    def test_the_sbom_is_on_unless_told_otherwise_and_needs_a_digest(self) -> None:
        job = _jobs(PUBLISH)["sbom"]
        assert job["if"] == "needs.publish.outputs.digest != '' && vars.SUPPLY_CHAIN_SBOM != 'false'"
        assert job["needs"] == "publish"

    def test_signing_is_on_unless_told_otherwise_and_needs_a_digest(self) -> None:
        cond = _jobs(PUBLISH)["attest"]["if"]
        assert "vars.SUPPLY_CHAIN_SIGNING != 'false'" in cond
        assert "needs.publish.outputs.digest != ''" in cond
        assert "needs.publish.result == 'success'" in cond

    def test_signing_off_leaves_the_sbom_running(self) -> None:
        """One switch per module: the sbom job must not read the signing switch."""
        sbom = _jobs(PUBLISH)["sbom"]
        assert "SUPPLY_CHAIN_SIGNING" not in yaml.safe_dump(sbom)

    def test_sbom_off_leaves_signing_running_without_an_sbom_and_says_so(self) -> None:
        """MODELLED, not left to chance: attest needs sbom but tolerates it being skipped, attaches
        the SBOM only when the job succeeded, and names the other outcome."""
        attest = _jobs(PUBLISH)["attest"]
        assert attest["needs"] == ["publish", "sbom"]
        assert "!cancelled()" in attest["if"], "a skipped sbom job must not skip the signing"
        attach = _step(attest, "Attach the SBOM")
        fetch = _step(attest, "Fetch the SBOM")
        absent = _step(attest, "no SBOM to attach")
        assert attach["if"] == "needs.sbom.result == 'success'"
        assert fetch["if"] == "needs.sbom.result == 'success'"
        assert absent["if"] == "needs.sbom.result != 'success'"
        assert "::notice::" in absent["run"]

    def test_the_chart_attestation_has_the_same_switch_and_runs_only_for_a_new_release(self) -> None:
        release = _jobs(HELM)["release"]
        for fragment in ("Attest the provenance of the packaged chart", "Read the chart attestation back"):
            cond = _step(release, fragment)["if"]
            assert "vars.SUPPLY_CHAIN_SIGNING != 'false'" in cond
            assert "steps.plan.outputs.new == 'true'" in cond
        plan = _step(release, "Report what this run will publish")
        assert plan.get("id") == "plan"
        assert 'echo "new=true" >> "$GITHUB_OUTPUT"' in plan["run"]
        assert 'echo "new=false" >> "$GITHUB_OUTPUT"' in plan["run"]


# ── Permissions ──────────────────────────────────────────────────────────────────────────────


class TestPermissions:
    def test_the_publish_job_still_holds_only_read(self) -> None:
        """Restated beside the jobs that were added, so the two are reviewed together."""
        assert _jobs(PUBLISH)["publish"]["permissions"] == {"contents": "read"}

    def test_the_sbom_job_holds_only_read(self) -> None:
        assert _jobs(PUBLISH)["sbom"]["permissions"] == {"contents": "read"}

    def test_the_signing_job_holds_exactly_what_keyless_needs(self) -> None:
        assert _jobs(PUBLISH)["attest"]["permissions"] == {
            "contents": "read", "id-token": "write", "attestations": "write",
        }

    def test_no_job_in_publish_can_write_to_this_repository(self) -> None:
        """The header's whole design, extended to the jobs that joined it."""
        for name, job in _jobs(PUBLISH).items():
            perms = job.get("permissions") or {}
            assert perms.get("contents") == "read", f"job {name!r} declares {perms!r}"
            assert "actions" not in perms and "pull-requests" not in perms, f"job {name!r}: {perms!r}"
            code = _code(job)
            for forbidden in ("git push", "git commit", "gh workflow run", "gh pr "):
                assert forbidden not in code, f"job {name!r} runs {forbidden!r}"

    def test_the_chart_release_job_gained_only_the_attestation_scopes(self) -> None:
        assert _jobs(HELM)["release"]["permissions"] == {
            "contents": "write", "id-token": "write", "attestations": "write",
        }


# ── What is signed, and how ──────────────────────────────────────────────────────────────────


class TestWhatIsSignedAndHow:
    def test_everything_names_the_digest_and_never_a_tag(self) -> None:
        code = _code(_jobs(PUBLISH)["attest"])
        for verb in ("cosign sign", "cosign verify ", "cosign attest", "cosign verify-attestation",
                     "gh attestation verify"):
            lines = [ln for ln in code.splitlines() if verb in ln]
            assert lines, f"{verb!r} is not run"
        subject_lines = [ln for ln in code.splitlines() if "${IMAGE}" in ln]
        assert subject_lines and all("${IMAGE}@${DIGEST}" in ln for ln in subject_lines), (
            "every reference to the image must be by digest"
        )

    def test_the_identity_is_this_workflow_file_at_the_ref_that_ran(self) -> None:
        env = _jobs(PUBLISH)["attest"]["env"]
        assert env["IDENTITY"].endswith("/.github/workflows/publish.yml@${{ github.ref }}")
        assert env["ISSUER"] == "https://token.actions.githubusercontent.com"

    def test_every_artefact_is_read_back_with_the_documented_flags(self) -> None:
        attest = _jobs(PUBLISH)["attest"]
        for fragment in ("Read the signature back", "Attach the SBOM", "Read the provenance back"):
            run = _step(attest, fragment)["run"]
            assert "--certificate-identity" in run or "--signer-workflow" in run, fragment

    def test_the_sbom_is_produced_by_the_syft_the_scan_document_measured(self) -> None:
        """A Syft that does not know Hummingbird OS writes an SBOM with no OS packages: complete-
        looking and wrong. The version is held to the one docs/image-vulnerability-scan.md measured."""
        measured = re.search(r"\*\*Syft (\d+\.\d+\.\d+)\*\*", SCAN_DOC.read_text())
        assert measured, "docs/image-vulnerability-scan.md no longer names the Syft version it measured"
        step = _step(_jobs(PUBLISH)["sbom"], "Catalogue the image")
        assert step["with"]["syft-version"] == f"v{measured.group(1)}"

    def test_the_sbom_is_spdx_json_kept_as_an_artifact_and_attached_by_cosign(self) -> None:
        step = _step(_jobs(PUBLISH)["sbom"], "Catalogue the image")
        assert step["with"]["format"] == "spdx-json"
        assert step["with"]["upload-artifact"] is True
        assert step["with"]["upload-release-assets"] is False
        assert step["with"]["dependency-snapshot"] is False
        assert step["with"]["image"].endswith("@${{ needs.publish.outputs.digest }}")
        attach = _step(_jobs(PUBLISH)["attest"], "Attach the SBOM")["run"]
        assert "cosign attest --yes --type spdxjson --predicate sbom.spdx.json" in attach

    def test_cosign_is_pinned_to_a_release(self) -> None:
        installer = [s for s in _jobs(PUBLISH)["attest"]["steps"] if "cosign-installer" in (s.get("uses") or "")]
        assert len(installer) == 1
        assert re.fullmatch(r"v\d+\.\d+\.\d+", installer[0]["with"]["cosign-release"])

    def test_provenance_is_attested_for_the_image_and_for_the_chart(self) -> None:
        image = [s for s in _jobs(PUBLISH)["attest"]["steps"] if "attest-build-provenance" in (s.get("uses") or "")]
        assert len(image) == 1
        assert image[0]["with"]["subject-digest"] == "${{ env.DIGEST }}"
        assert image[0]["with"]["push-to-registry"] is False
        chart = [s for s in _jobs(HELM)["release"]["steps"] if "attest-build-provenance" in (s.get("uses") or "")]
        assert len(chart) == 1
        assert chart[0]["with"]["subject-path"].startswith(".cr-release-packages/group-sync-dashboard-")

    def test_the_install_guide_gives_the_verification_commands(self) -> None:
        text = INSTALL_GUIDE.read_text()
        assert "cosign verify " in text
        assert "cosign verify-attestation " in text
        assert "gh attestation verify " in text
        assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in text
        assert "/.github/workflows/publish.yml@refs/heads/main" in text
        assert "/.github/workflows/helm.yaml" in text
```

#### `local-development/tests/test_workflow_pins.py` — new

```python
"""Every third-party action is pinned by the full commit of a release, with the version beside it.

The rule is stated at the top of ci.yml and it is the form Dependabot moves. It was stated and not
held: helm.yaml carried `helm/chart-releaser-action@v1.7.0` — a mutable major-minor tag — while
the note said every action was pinned. A tag's owner can move a tag; a green run under a moved
tag proves whatever the tag now points at.

Text, not YAML: the version comment lives beside the `uses:` value on the same line, and a parser
drops comments.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.y*ml"))

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*(#.*)?$")


def _uses() -> list[tuple[str, int, str, str]]:
    out = []
    for wf in WORKFLOWS:
        for n, line in enumerate(wf.read_text().splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            m = USES.match(line)
            if m:
                out.append((wf.name, n, m.group(1), m.group(2) or ""))
    return out


def test_there_are_actions_to_check() -> None:
    assert len(_uses()) >= 20, "the `uses:` pattern has probably stopped matching"


def test_every_third_party_action_is_pinned_to_a_full_commit_with_its_version() -> None:
    offenders = []
    for wf, n, ref, comment in _uses():
        if ref.startswith("./"):
            continue  # a reusable workflow in this repository moves with the commit under test
        name, _, sha = ref.partition("@")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            offenders.append(f"{wf}:{n} {ref} — not a 40-hex commit")
        elif not re.search(r"#\s*v\d", comment):
            offenders.append(f"{wf}:{n} {ref} — no `# vX.Y.Z` comment beside it")
    assert not offenders, "unpinned or uncommented actions:\n  " + "\n  ".join(offenders)
```

#### `docs/HELM_DOWNLOAD_AND_INSTALL.md` — edit (new §7 before Quick reference; two rows added)

Old:
```markdown
Override `image.repository` only, never `image.tag` — the tag is the chart's statement about which
build it deploys, and rewriting it decouples the chart from the image it was published with.

---

## Quick reference
```
New:
```markdown
Override `image.repository` only, never `image.tag` — the tag is the chart's statement about which
build it deploys, and rewriting it decouples the chart from the image it was published with.

---

## 7. Verify what you downloaded

Every image `publish.yml` pushes is signed and attested, and every chart `helm.yaml` publishes is
attested, with GitHub's OIDC identity — no key to fetch, nothing to trust but the identity strings
below (`.github/workflows/publish.yml#attest`, `.github/workflows/helm.yaml#Attest the provenance of the packaged chart`).
The commands need `cosign` 3.x and `gh` 2.49 or newer; the outputs shown are the tools' own
wording, with the values that change per release elided as `…`.

**The image signature.** The identity is the workflow file on `main`; the issuer is GitHub's:

```sh
cosign verify \
  --certificate-identity https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  quay.io/ephico2real/group-sync-dashboard:0.11.0
```

```text
Verification for quay.io/ephico2real/group-sync-dashboard:0.11.0 --
The following checks were performed on each of these signatures:
  - The cosign claims were validated
  - Existence of the claims in the transparency log was verified offline
  - The code-signing certificate was verified using trusted certificate authority certificates
[{"critical":{"identity":{"docker-reference":"quay.io/ephico2real/group-sync-dashboard"},"image":{"docker-manifest-digest":"sha256:…"},"type":"cosign container image signature"},…}]
```

The signature is over the **digest**, so it verifies for every tag that resolves to it —
`:<appVersion>-<sha>`, `:<appVersion>` and `:<chartVersion>` are one manifest, copied server side
(`local-development/build-and-push-external.sh#skopeo copy`). On a mirror, verify the mirrored
reference the same way; the signature travels with `skopeo copy --all`.

**The SBOM.** Attached to the image as an attestation. Extract it and scan it:

```sh
cosign verify-attestation --type spdxjson \
  --certificate-identity https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  quay.io/ephico2real/group-sync-dashboard:0.11.0 \
  | jq -r '.payload | @base64d | fromjson | .predicate' > sbom.spdx.json
grype sbom:sbom.spdx.json
```

The same file is a workflow artifact named `sbom-<commit>` on the publish run, for the case where
the image was mirrored without its referrers. It is produced by Syft 1.51.1, the version
`image-vulnerability-scan.md` measured identifying the hardened base's operating system.

**Build provenance (SLSA).** Recorded in this repository's attestation store:

```sh
gh attestation verify oci://quay.io/ephico2real/group-sync-dashboard:0.11.0 \
  --repo ephico2real2/group-sync-dashboard \
  --signer-workflow ephico2real2/group-sync-dashboard/.github/workflows/publish.yml
```

```text
Loaded digest sha256:… for oci://quay.io/ephico2real/group-sync-dashboard:0.11.0
Loaded 1 attestation from GitHub API
✓ Verification succeeded!
…
- Attestation #1
  - Build repo:..... ephico2real2/group-sync-dashboard
  - Build workflow:. .github/workflows/publish.yml@refs/heads/main
  - Signer repo:.... ephico2real2/group-sync-dashboard
  - Signer workflow: .github/workflows/publish.yml@refs/heads/main
```

**The chart.** The package `helm pull` returns is the file chart-releaser uploaded, and its
provenance is attested the same way:

```sh
helm pull group-sync-dashboard/group-sync-dashboard --version 0.10.0
gh attestation verify group-sync-dashboard-0.10.0.tgz \
  --repo ephico2real2/group-sync-dashboard \
  --signer-workflow ephico2real2/group-sync-dashboard/.github/workflows/helm.yaml
```

```text
Loaded digest sha256:… for file://group-sync-dashboard-0.10.0.tgz
Loaded 1 attestation from GitHub API
✓ Verification succeeded!
```

There is no GPG signature and `helm verify` is not supported — deliberately; the reasoning is in
`DESIGN_supply_chain.md`. Charts published before this attestation existed have none, and `gh`
reports `no attestations found` for them.

**A fork verifies against its own identity.** Replace the repository in `--certificate-identity`,
`--repo` and `--signer-workflow`; the workflow file names are the same. Repository variables
`SUPPLY_CHAIN_SIGNING=false` and `SUPPLY_CHAIN_SBOM=false` turn the two modules off for a runner
that cannot reach the registry or the Sigstore services.

---

## Quick reference
```
And, Old:
```markdown
| Confirm what is running | `oc exec ... -c dashboard -- curl -s http://127.0.0.1:8080/api/version` |
```
New:
```markdown
| Confirm what is running | `oc exec ... -c dashboard -- curl -s http://127.0.0.1:8080/api/version` |
| Verify the image signature | `cosign verify --certificate-identity …/publish.yml@refs/heads/main --certificate-oidc-issuer https://token.actions.githubusercontent.com <image>` — §7 |
| Verify provenance (image or chart) | `gh attestation verify <oci://image \| file.tgz> --repo ephico2real2/group-sync-dashboard` — §7 |
```

Citation check: `.github/workflows/publish.yml#attest` (substring `attest` exists), `.github/workflows/helm.yaml#Attest the provenance of the packaged chart` (step name), `local-development/build-and-push-external.sh#skopeo copy` (present after edit 4), `DESIGN_supply_chain.md` and `image-vulnerability-scan.md` are bare paths (resolve by unique basename).

#### `docs/DESIGN_supply_chain.md` — new

```markdown
# Design: what is signed, what is attested, and why there is no key

The image and the chart are published by two workflows that write to nothing in this repository
(`docs/RELEASING.md#Nothing else couples them`). This record is the decisions that added signing,
an SBOM and build provenance to both without changing that property, and what an operator gets
from each. The commands are in `HELM_DOWNLOAD_AND_INSTALL.md#7. Verify what you downloaded`.

## What a consumer can now check

| Artefact | Mechanism | Where it lives | Check |
|---|---|---|---|
| image, by digest | cosign keyless signature (Fulcio certificate, Rekor entry) | beside the image in the registry | `cosign verify` |
| image SBOM | Syft 1.51.1, SPDX JSON, attached with `cosign attest --type spdxjson` | beside the image; also a workflow artifact | `cosign verify-attestation` |
| image provenance | SLSA build provenance from `actions/attest-build-provenance` | this repository's attestation store | `gh attestation verify oci://…` |
| chart package | SLSA build provenance of the `.tgz` chart-releaser uploaded | this repository's attestation store | `gh attestation verify <file>` |

One identity for all four: the workflow file that ran, on `main`, issued by
`https://token.actions.githubusercontent.com`. There is no signing key anywhere.

## Decisions

**D1 — The digest is what podman reports after the push, and every name is a copy of it.**
A signature is over a digest. The chart resolves `:<appVersion>` by default
(`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.image`), so that tag must resolve to the
signed digest or the documented `cosign verify` fails on the reference every consumer uses.
`build-and-push-external.sh` pushes the immutable tag once with `--digestfile`, then makes the
aliases with `skopeo copy` — server side, the call `helm.yaml` already used to label a chart's
image — and reads each alias's digest back, refusing a mismatch
(`local-development/build-and-push-external.sh#ALIAS_DIGEST`). A second `podman push` from the
local store was the alternative, and it can produce a different manifest for the same image.

**D2 — Signing is a separate job, so `publish` keeps `contents: read` and nothing else.**
`tests/test_publish_release_decision.py#test_the_publish_job_can_write_to_nothing_but_the_registry`
is the assertion that branch protection on `main` depends on. Keyless signing needs
`id-token: write`; that scope lives on the `attest` job alone, and a test now holds every job in
the file to `contents: read` (`tests/test_supply_chain.py#TestPermissions`).

**D3 — Keyless, not a key.** A key is a secret to store, rotate, and lose; keyless is a
certificate that lives minutes, bound to this repository's workflow by GitHub's OIDC token, with
the signature recorded in Rekor's public log. The cost is stated rather than hidden: a public
log entry per signature (repository, workflow, digest — nothing more), and egress to
`fulcio.sigstore.dev`, `rekor.sigstore.dev` and `tuf-repo-cdn.sigstore.dev` from the runner. A
fork never gets a token for this identity; it signs as itself, and verifies as itself.

**D4 — The chart is attested with the same mechanism, not GPG-signed.** `helm package --sign`
needs a long-lived private key in a repository secret, a keyring handed to every consumer out of
band, and `helm verify` on their side. That is a second signing model with a key at its centre,
for a file that `gh attestation verify` can already check against the same identity as the image.
cosign `sign-blob` was the third option; chart-releaser publishes the package to gh-pages and a
GitHub Release, and a bundle beside it would need a second upload path `helm pull` never fetches.
The subject is `.cr-release-packages/<name>-<version>.tgz` — chart-releaser's package directory,
which is the file it copies to gh-pages, so the attestation is over the bytes `helm pull` returns.
It runs only when the run publishes a NEW version (`.github/workflows/helm.yaml#steps.plan.outputs.new`):
a skipped version has no file this run published, and attesting the re-packaged copy would claim
provenance for bytes that may differ.

**D5 — The SBOM is attached with cosign, not only stored in GitHub.** `actions/attest-sbom`
exists and would put the SBOM beside the provenance in GitHub's store. An air-gapped mirror that
copied the image with `skopeo copy --all` keeps cosign's attestation and loses GitHub's; the
registry copy is the one that travels. The workflow artifact is the copy for a mirror that did
not copy referrers. Syft is pinned to the version `image-vulnerability-scan.md` measured
identifying Hummingbird OS, and a test holds the pin to the document
(`tests/test_supply_chain.py#test_the_sbom_is_produced_by_the_syft_the_scan_document_measured`):
an SBOM from a Syft that does not know the base lists no OS package and looks complete.

**D6 — Provenance is not pushed to the registry.** `push-to-registry: true` needs a docker login
inside the action and OCI 1.1 referrer support; the documented check, `gh attestation verify`,
reads GitHub's store either way. One copy, in the place the verifier reads.

**D7 — Every artefact is read back before the run is green**, with the exact flags the install
guide gives operators. This repository's workflow defects (#34, #37, the unpinned Grype) were
all runs that reported success for something nobody could use. If the registry cannot hold the
bundle format, or an identity string is wrong, the first run on `main` is red.

**D8 — Two switches, modelled.** `SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`, both ON unless
the value is exactly `false`. `attest` depends on `sbom` with `!cancelled()`, attaches the SBOM
only when that job succeeded, and prints a notice naming the other outcome; the chart attestation
reads the signing switch and the new-release decision. The `publish` job reads neither.

## What this does not do

- It does not verify on the cluster. OpenShift's `ImagePolicy` expresses Fulcio identities as an
  e-mail subject and cannot name a GitHub Actions workflow URI, so admission-time verification of
  these signatures is a policy-engine question (Kyverno, Sigstore policy-controller) outside this
  chart. The chart adds no value for it because it could not honour one.
- It does not sign the `<appVersion>-<sha>` images of a fork or a laptop build. The DR path
  (`docs/RELEASING.md#When GitHub Actions is unavailable`) publishes an unsigned image and says
  so in its output; signing needs the workflow identity.
- It does not attest charts published before it existed.
```

#### `docs/RELEASING.md` — edits (A2 part)

Old:
```text
   cannot tell? (workflow_dispatch, first push, unreadable base)
        --> immutable tag only, plus a ::warning:: naming --release-tags
```
```
New:
```text
   cannot tell? (workflow_dispatch, first push, unreadable base)
        --> immutable tag only, plus a ::warning:: naming --release-tags

   then, on the digest the registry acknowledged — one digest, every tag:
   sbom    job   Syft -> SPDX JSON, a workflow artifact                SUPPLY_CHAIN_SBOM
   attest  job   cosign sign (keyless) · SBOM attached · SLSA          SUPPLY_CHAIN_SIGNING
                 provenance in GitHub's store — each read back
                 before the run is green
```
```
Old:
```text
   gh-pages:  index.yaml + group-sync-dashboard-0.5.0.tgz
```
```
New:
```text
   gh-pages:  index.yaml + group-sync-dashboard-0.5.0.tgz
        |
        v
   attest that .tgz (SLSA provenance, GitHub's store)      SUPPLY_CHAIN_SIGNING
   only for a NEW version; a skipped version attests nothing
```
```
Old:
```markdown
**Pin when you need byte-identical rollbacks:**

```sh
helm upgrade ... --set image.tag=0.7.0-f9fa896778
```

---

## How to cut a release
```
New:
```markdown
**Pin when you need byte-identical rollbacks:**

```sh
helm upgrade ... --set image.tag=0.7.0-f9fa896778
```

**And verify, whichever form you pinned.** Every pushed image is signed and attested by digest
under GitHub's OIDC identity — no key to fetch — and every published chart package is attested
the same way. The commands, with their outputs, are in
`HELM_DOWNLOAD_AND_INSTALL.md#7. Verify what you downloaded`; the decisions, including why there is
no GPG key, in `DESIGN_supply_chain.md`. Two repository variables turn the modules off,
`SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`; unset means on.

---

## How to cut a release
```

#### `README.md` — edits

Old (the stale subsection; the pin commit it describes was removed by `publish.yml#So the pin is gone`):
```markdown
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) runs **that same script** on
every merge to `main`, then commits the resulting tag into the chart's `values.yaml`. So the
published image is the merge commit, and the chart records which one — rather than whichever
working tree last ran the script by hand. The local path is unchanged and still does both.

Configure once, under **Settings → Secrets and variables → Actions**:

| | Name | Value |
|---|---|---|
| **Secret** | `REGISTRY_USERNAME` | Quay robot account, e.g. `ephico2real+github_ci` |
| **Secret** | `REGISTRY_PASSWORD` | that robot's token — not a personal password |
| Variable (optional) | `REGISTRY` | defaults to `quay.io` |
| Variable (optional) | `REGISTRY_NAMESPACE` | defaults to `ephico2real` |

The names deliberately match what the script already reads from `.env`, so one name means one
thing locally and in CI. Registry and namespace are **variables, not secrets** — they are not
sensitive, and as secrets they would be masked in exactly the logs where you want to see which
registry a run pushed to.

Two properties worth knowing:

- **The pin commit carries `[skip publish]`**, and the workflow skips on that marker. Without it
  the commit would retrigger the workflow, which would publish, which would commit again.
- **Re-running a commit is safe.** The tag embeds the commit sha, so the same tag can only ever
  mean the same source; a re-run pushes an identical image and the pin step finds nothing to
  change. There is no tag to accidentally overwrite with different content.
```
New:
```markdown
[`.github/workflows/publish.yml`](.github/workflows/publish.yml) runs **that same script** on
every merge to `main` that changes an image input, and writes nothing back to this repository:
the immutable `<version>-<sha>` tag every time, the `:<version>` alias only when a human moved
`version` in `pyproject.toml`. The pushed digest is then signed and attested — keyless, under
GitHub's OIDC identity — and its SBOM kept as an artifact and attached to the image. How an
operator checks all of that: [`docs/HELM_DOWNLOAD_AND_INSTALL.md`](docs/HELM_DOWNLOAD_AND_INSTALL.md);
the release model: [`docs/RELEASING.md`](docs/RELEASING.md).

Configure once, under **Settings → Secrets and variables → Actions**:

| | Name | Value |
|---|---|---|
| **Secret** | `REGISTRY_USERNAME` | Quay robot account, e.g. `ephico2real+github_ci` |
| **Secret** | `REGISTRY_PASSWORD` | that robot's token — not a personal password |
| Variable (optional) | `REGISTRY` | defaults to `quay.io` |
| Variable (optional) | `REGISTRY_NAMESPACE` | defaults to `ephico2real` |
| Variable (optional) | `SUPPLY_CHAIN_SBOM` | `false` turns the SBOM job off; unset means on |
| Variable (optional) | `SUPPLY_CHAIN_SIGNING` | `false` turns image signing, SBOM attestation and provenance off — for a runner without egress to the Sigstore services; unset means on |
| Variable (optional) | `CI_UI_TESTS` | `false` turns the browser-test job in `ci.yml` off; unset means on |

The names deliberately match what the script already reads from `.env`, so one name means one
thing locally and in CI. Registry and namespace are **variables, not secrets** — they are not
sensitive, and as secrets they would be masked in exactly the logs where you want to see which
registry a run pushed to.

**Re-running a commit is safe.** The tag embeds the commit sha, so the same tag can only ever
mean the same source; a re-run pushes an identical image, and the aliases are server-side copies
of that manifest, so no tag can end up naming different content than the digest that was signed.
```
Old (docs index):
```markdown
| [`docs/image-vulnerability-scan.md`](docs/image-vulnerability-scan.md) | the CVE position, what is reachable, and what a rebuild cannot fix |
```
New:
```markdown
| [`docs/image-vulnerability-scan.md`](docs/image-vulnerability-scan.md) | the CVE position, what is reachable, and what a rebuild cannot fix |
| [`docs/DESIGN_supply_chain.md`](docs/DESIGN_supply_chain.md) | the image signature, SBOM and provenance, the chart attestation, and why none of it has a key |
```

#### `docs/image-vulnerability-scan.md` — edit

Old:
```markdown
4. **When util-linux 2.42.3 lands in the base**, the `libuuid` removal can stay as it is; nothing
   about it depends on the version.
```
New:
```markdown
4. **When util-linux 2.42.3 lands in the base**, the `libuuid` removal can stay as it is; nothing
   about it depends on the version.
5. **Scan the SBOM instead of the image, when that is easier.** Every pushed image carries an SPDX
   SBOM from this Syft version as a cosign attestation, also kept as a workflow artifact on the
   publish run; `grype sbom:sbom.spdx.json` reads it (`HELM_DOWNLOAD_AND_INSTALL.md#The SBOM`).
```

#### `docs/CHANGELOG.md` — edit (under `## Unreleased`)

Old:
```markdown
  was; `test_live_smoke.py` still runs nowhere but against a cluster you name.

## Application 0.11.0 — chart 0.10.0 — 2026-09-04
```
New:
```markdown
  was; `test_live_smoke.py` still runs nowhere but against a cluster you name.
- **Every pushed image is signed and attested, and every published chart package is attested.**
  The build script records the digest the registry acknowledged and makes the release aliases as
  server-side copies of that manifest, read back and compared, so one digest is every tag. Two new
  jobs follow the push: an SBOM (Syft 1.51.1, SPDX JSON, a workflow artifact) and a keyless cosign
  signature under GitHub's OIDC identity with the SBOM attached and SLSA provenance in the
  repository's attestation store — each read back before the run is green. `helm.yaml` attests the
  `.tgz` chart-releaser uploaded, for new versions only. No key anywhere; `helm verify` is
  deliberately not supported. `helm/chart-releaser-action` is pinned by commit like every other
  action, and a test now holds that rule. Variables `SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`
  turn the modules off. (design `DESIGN_supply_chain.md`)

## Application 0.11.0 — chart 0.10.0 — 2026-09-04
```

### Verification (A2)

Local, before the PR:
```sh
cd local-development
.venv/bin/python -m pytest tests/test_supply_chain.py tests/test_workflow_pins.py \
  tests/test_publish_release_decision.py tests/test_publish_paths.py tests/test_docs_citations.py -q
# expected: all pass; test_publish_release_decision is unchanged and still passes
bash -n build-and-push-external.sh && echo parses
REGISTRY=quay.io REGISTRY_NAMESPACE=ephico2real ./build-and-push-external.sh --build-only
# expected: "built   : … (stamp verified)" then "done    : --build-only, nothing pushed" — the push path is untouched for --build-only
```
First run on `main` (the PR changes `publish.yml` and the build script, both in `publish.yml#paths`, so it fires):
- `publish` job log: `digest  : sha256:…` and `digest  : written to /home/runner/work/_temp/pushed.digest`.
- `sbom` job: an artifact `sbom-<sha>` on the run.
- `attest` job: `signature verifies for quay.io/ephico2real/group-sync-dashboard@sha256:… as https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main`, `SBOM attestation verifies …`, and `✓ Verification succeeded!` from `gh attestation verify`.
- From a laptop, the four commands in §7 of the install guide against `:<appVersion>-<sha>` succeed with the outputs shown there.
- Next chart release: the `release` job shows `Attest the provenance of the packaged chart` and `✓ Verification succeeded!`; `gh attestation verify group-sync-dashboard-<v>.tgz --repo ephico2real2/group-sync-dashboard` succeeds after `helm pull`.
- OFF state, once: set `SUPPLY_CHAIN_SIGNING=false`, dispatch publish; `attest` is skipped, `sbom` runs, the image is pushed unsigned; then delete the variable and dispatch again to sign that same digest (cosign signs any digest; the immutable tag is unchanged by a rebuild only if the base did not move — re-dispatch produces a new sha tag, which is fine).

### Risks and how they close

- Quay.io and cosign v3's bundle layout: the in-run `cosign verify` (D7) makes the first run red if the registry cannot serve the signature back. Q2 below asks which cosign major consumers run.
- `skopeo inspect --format` on the runner: the ubuntu-latest skopeo already used by `helm.yaml#skopeo inspect --no-tags` supports `--format`; the script refuses rather than guesses on a mismatch.
- `gh attestation verify oci://` needs anonymous pull of the manifest: the quay repository is public (the chart pulls it with no secret by default, `charts/group-sync-dashboard/README.md#image.pullSecrets`).
- The DR path (`--release-tags` from a laptop) publishes unsigned; the design doc says so, and the alias digests are still read back.

---


## Batch closing sections (verbatim)

## Order of PRs and what each needs from the operator

1. **A1** — `ci.yml`, `test_ci_ui_job.py`, `local-development/README.md`, `RELEASING.md` (one line), `CHANGELOG.md` (intro + `## Unreleased`), `README.md` variables row for `CI_UI_TESTS` (included in A2's table rewrite; if A1 lands alone, add only that row). No `charts/` change, no version bump.
2. **A2** — build script, `publish.yml`, `helm.yaml`, `test_supply_chain.py`, `test_workflow_pins.py`, `HELM_DOWNLOAD_AND_INSTALL.md`, `DESIGN_supply_chain.md`, `RELEASING.md`, `README.md`, `image-vulnerability-scan.md`, `CHANGELOG.md`. Merging it fires `publish.yml` (paths include the script and the workflow), which is the first signed image. No `charts/` change.
3. **A3** — `prepare-release.py`, `test_prepare_release.py`, `RELEASING.md`, `local-development/README.md`, `CHANGELOG.md`. The next real release then converts `## Unreleased`.

## Questions only the operator can answer

- **Q1 (A1):** make `Browser tests (Playwright, Chromium)` a required check under branch protection after a week of green runs? (a Settings change, not a repository file).
- **Q2 (A2):** which cosign major do consumers run? The workflow signs with cosign 3.1.3 in its default bundle layout and proves the round trip against Quay in-run; if a consumer population on cosign 2.x must verify, `cosign sign --new-bundle-format=false` is the one-flag change and the install guide would say "cosign 2.x or newer".
- **Q3 (A2):** is a public Rekor entry per push acceptable? It names the repository, the workflow file and the digest — nothing else — and is the property that makes keyless verifiable offline.
- **Q4 (A2):** should the quay robot account's token be scoped to allow pushing referrer artifacts (`sha256-<digest>.sig` / `.att` tags)? A write-scoped robot already can; a tag-restricted one would fail the sign step visibly.

### Critical Files for Implementation

- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/ci.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/publish.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/helm.yaml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/build-and-push-external.sh`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/prepare-release.py` (new; conventions it edits live in `/Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/Chart.yaml` and `/Users/olasumbo/gitRepos/group-sync-dashboard/docs/CHANGELOG.md`)
