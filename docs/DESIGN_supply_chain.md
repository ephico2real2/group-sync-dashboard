# Design: what is signed, what is attested, and why there is no key

The image and the chart are published by two workflows that write to nothing in this repository
(`docs/RELEASING.md#Nothing else couples them`). This record is the decisions that added signing,
an SBOM and build provenance to both without changing that property, and what an operator gets
from each. The commands are in `HELM_DOWNLOAD_AND_INSTALL.md#7. Verify what you downloaded`.

## What a consumer can now check

| Artefact | Mechanism | Where it lives | Check |
|---|---|---|---|
| each image, by digest | cosign keyless signature (Fulcio certificate, Rekor entry) | beside the image in the registry | `cosign verify` |
| each image's SBOM | Syft 1.51.1, SPDX JSON, attached with `cosign attest --type spdxjson` | beside the image; also a workflow artifact | `cosign verify-attestation` |
| each image's provenance | SLSA build provenance from `actions/attest-build-provenance` | this repository's attestation store | `gh attestation verify oci://…` |
| chart package | SLSA build provenance of the `.tgz` chart-releaser uploaded | this repository's attestation store | `gh attestation verify <file>` |

"Each image" is two since application 0.18.0: the dashboard's and the report service's (D10). One
identity for all of it: the workflow file that ran, on `main`, issued by
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
fork never gets a token for this identity — and under this workflow it does not sign at all: the
`publish` job is skipped unless `github.repository` is this repository, so a fork that wants signed
images edits that guard and then verifies against its own identity strings.

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
copied the image with its referrers (`oras cp --recursive`; `skopeo copy --all` copies an index's
platform images, not a subject's referrers) keeps cosign's attestation and loses GitHub's; the
registry copy is the one that can travel. The workflow artifact is the copy for a mirror that did
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
bundle format, or an identity string is wrong, the first run on `main` is red. Two limits of that
proof, stated: the read-back uses the cosign that signed, so it cannot stand in for a consumer on an
older cosign major (cosign 3 stores signatures as OCI 1.1 referrers, which quay.io serves — measured
2026-09-05 — and which cosign 2.x cannot read; the operator's question Q2 on #63); and `cosign sign`
runs before `cosign verify`, so a run that fails at the read-back has already written a Rekor entry
and, if the push landed, a registry referrer — a signature that verifies only for the identity that
run used, which is why the job signs only on `main` (D9).

**D8 — Two switches, modelled.** `SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`, both ON unless
the value is exactly `false`. `attest` depends on `sbom` with `!cancelled()`, attaches the SBOM
only when that job succeeded, and prints a notice naming the other outcome; the chart attestation
reads the signing switch and the new-release decision. The `publish` job reads neither.

**D10 — The report image is a second subject of the same chain, not a second chain.** C3 added a
second image (`DESIGN_reporting_service.md#3.3 Two images, one version`). It is built in the same
`publish` job right after the dashboard's push, by the same script through its wrapper, under the
same credential check and the same release decision, and it records its own digest through its own
`DIGEST_FILE` as a second pair of job outputs (`.github/workflows/publish.yml#build-report`). The
`sbom` and `attest` jobs then run as a two-leg matrix whose `include` reads those outputs — one
definition of the catalogue, the signature, the SBOM attestation and the provenance, applied to
two `<image, digest>` pairs — rather than a copy of the steps that could drift to a weaker chain for
the second image. Two consequences, stated: the job-level switches key on the dashboard's digest
alone, because `matrix` is not a context a job-level `if` may read and the report digest is written
under the same condition in the same job; and GitHub reports one `needs.<job>.result` per job, not
per leg (the contexts reference documents nothing finer; with fail-fast off a failed leg makes it
`failure`), so if either image's catalogue fails, neither leg attaches an SBOM and both say so by
name — chosen over a per-leg artifact probe, and to be confirmed on the first run with a red leg.
The report image's SBOM is the artifact `sbom-report-<sha>`, beside `sbom-<sha>`; a run holds one
artifact per name, and sbom-action names the file inside after the artifact. A report build that
fails leaves the dashboard's immutable tag pushed and the job red, which withholds both images'
catalogue and signatures: the run is the unit. On an ordinary merge a `workflow_dispatch` rebuilds
both. On a release push the dashboard's `:<appVersion>` and `:<chartVersion>` aliases have already
moved — its step ran `--release-tags` before the report step — to a digest that run never signs, and
a dispatch cannot move them (the release decision fails closed without a `before`); the recovery is a
corrective application release (a version bump, which moves both images' aliases to signed digests)
or the two-script route the release decision's warning names
(`docs/RELEASING.md#When GitHub Actions is unavailable`), which publishes unsigned aliases. A release
is two images now, and every statement of the manual route names both scripts. What nothing does:
label or resolve the report image by chart version —
`.github/workflows/helm.yaml#Label the image this chart version deploys` names the dashboard
repository only, and the chart resolves the report image at appVersion, so
`group-sync-dashboard-report:<chartVersion>` exists only from application releases. The first
version of this step sat under `sbom` reading
`steps.creds` and `steps.release`, which exist only in `publish` — step outputs are job-local, so it
could never have run (review of C3, Codex); `tests/test_publish_paths.py` now holds every step,
output and matrix reference in the three workflows to a definition, because GitHub resolves an
unknown reference to an empty string rather than an error.

## What this does not do

- It does not verify on the cluster. OpenShift's `ImagePolicy` expresses Fulcio identities as an
  e-mail subject and cannot name a GitHub Actions workflow URI, so admission-time verification of
  these signatures is a policy-engine question (Kyverno, Sigstore policy-controller) outside this
  chart. The chart adds no value for it because it could not honour one.
- It does not sign the `<appVersion>-<sha>` images of a fork or a laptop build. The DR path
  (`docs/RELEASING.md#When GitHub Actions is unavailable`) publishes an unsigned image and says
  so in its output; signing needs the workflow identity.
- It does not sign an image a `workflow_dispatch` from another branch pushed (**D9**): the
  `attest` job runs only for `refs/heads/main`, and the identity it verifies is pinned to that ref,
  because a signature under `…/publish.yml@refs/heads/<branch>` would pass the run's own read-back
  and fail the command the install guide gives. Such a dispatch pushes its immutable tags unsigned
  (both images, since D10).
- It does not sign the `:<appVersion>` alias on an ordinary merge, because nothing moved it: the
  alias is copied from the signed digest only on an application release, so between releases the
  documented `cosign verify` is run against the immutable tag the publish log names.
- It does not attest charts published before it existed.
