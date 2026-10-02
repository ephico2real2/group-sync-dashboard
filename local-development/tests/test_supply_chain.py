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
script rather than restating either. The exceptions are #410's two registry checks, the chart-publish
label gate and the pull-request version check: their refusals are decisions over registry answers, so
those steps are RUN, against a stub skopeo (TestTheChartPublishLabelGate,
TestTheChartVersionIsNeverAReleasedApplicationVersion).

BOTH STATES. Each switch is asserted as the literal expression the workflow evaluates: unset or
anything but 'false' runs the job; 'false' skips it and leaves every other job untouched.
"""

from __future__ import annotations

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

REPO = pathlib.Path(__file__).resolve().parents[2]
PUBLISH = REPO / ".github" / "workflows" / "publish.yml"
HELM = REPO / ".github" / "workflows" / "helm.yaml"
CI = REPO / ".github" / "workflows" / "ci.yml"
SCRIPT = REPO / "local-development" / "build-and-push-external.sh"
REPORT_WRAPPER = REPO / "local-development" / "build-and-push-report.sh"   # the report image (C3)
SCAN_DOC = REPO / "docs" / "image-vulnerability-scan.md"
INSTALL_GUIDE = REPO / "docs" / "HELM_DOWNLOAD_AND_INSTALL.md"
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"   # the deploy-side label guard (#414)
RELEASING = REPO / "docs" / "RELEASING.md"


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
        assert 'skopeo copy --all --preserve-digests "docker://${REF}" "docker://${ALIAS_REF}"' in code
        assert "podman tag" not in code, "the aliases must not be re-pushed from the local store"

    def test_an_alias_that_is_not_the_signed_digest_is_refused(self) -> None:
        code = _script_code()
        assert "skopeo inspect --no-tags --format '{{.Digest}}'" in code
        assert 'if [ "${ALIAS_DIGEST}" != "${DIGEST}" ]; then' in code

    def test_the_registry_digest_is_exactly_sixty_four_hex_digits(self) -> None:
        """Review of A2 (Codex): the glob `sha256:[0-9a-f]*` accepted one hex digit followed by
        anything, and this value is what gets signed."""
        code = _script_code()
        assert '[[ ! "${DIGEST}" =~ ^sha256:[0-9a-f]{64}$ ]]' in code
        assert "sha256:[0-9a-f]*)" not in code

    def test_the_alias_copy_refuses_to_rewrite_the_manifest(self) -> None:
        """Review of A2 (Cursor): skopeo copy's default is the source manifest type WITH FALLBACKS
        (schema or compression conversion rewrites the digest), and without --all a manifest list's
        host-arch child is copied while --digestfile recorded the list. Both flags, or the digest the
        script compares can never match for reasons that are not a defect."""
        code = _script_code()
        line = next(ln for ln in code.splitlines() if "skopeo copy" in ln)
        assert "--preserve-digests" in line, line
        assert "--all" in line, line

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
            "report_digest": "${{ steps.build-report.outputs.digest }}",
            "report_image": "${{ steps.build-report.outputs.image }}",
        }

    def test_the_report_build_step_is_the_dashboards_applied_to_the_second_image(self) -> None:
        """Review of C3 (Codex): the report image's step had landed under `sbom`, where
        `steps.creds` and `steps.release` do not exist, and it recorded no digest at all — so
        nothing downstream could have catalogued or signed it. It is the dashboard's step applied
        to the second image: the same job, right after the dashboard's push, the same condition and
        release decision, its own DIGEST_FILE, its own pair of outputs."""
        publish = _jobs(PUBLISH)["publish"]
        names = [s.get("name") for s in publish["steps"]]
        assert "Build and push the report image" in names, "the report step must be in the publish job"
        assert names.index("Build and push the report image") == names.index("Build and push the image") + 1
        build = _step(publish, "Build and push the image")
        report = _step(publish, "Build and push the report image")
        assert report.get("id") == "build-report"
        assert report["if"] == build["if"]
        assert report["env"]["IS_RELEASE"] == build["env"]["IS_RELEASE"]
        assert report["env"]["DIGEST_FILE"] != build["env"]["DIGEST_FILE"], (
            "the script overwrites whatever DIGEST_FILE names; sharing the dashboard's file would "
            "hand the report digest on as the dashboard's"
        )
        code = "\n".join(ln for ln in report["run"].splitlines() if not ln.strip().startswith("#"))
        assert "./build-and-push-report.sh --release-tags" in code and "./build-and-push-report.sh\n" in code
        assert 'echo "digest=${digest}" >> "$GITHUB_OUTPUT"' in code
        # The output names the IMAGE_NAME the wrapper FORCES (second pass, Codex: a default from the
        # environment let an ambient dashboard name in) — read from the wrapper, so renaming the
        # image there without touching the workflow fails here rather than in the registry.
        forced = re.search(r'^IMAGE_NAME=([A-Za-z0-9._-]+) CONTAINERFILE=Containerfile\.report exec', REPORT_WRAPPER.read_text(), re.M)
        assert forced, "build-and-push-report.sh no longer forces IMAGE_NAME the way this test reads"
        assert f'echo "image=${{REGISTRY}}/${{REGISTRY_NAMESPACE}}/{forced.group(1)}" >> "$GITHUB_OUTPUT"' in code


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

    def test_the_downloaded_sbom_filename_is_the_one_cosign_reads(self) -> None:
        """Review of A2 (Codex): sbom-action names the file inside the artifact after `artifact-name`
        (its uploadSbomArtifact writes `${tempDir}/${artifactName}`), and download-artifact does not
        rename — `test -s sbom.spdx.json` would have failed the first run."""
        jobs = _jobs(PUBLISH)
        artifact = _step(jobs["sbom"], "Catalogue the image")["with"]["artifact-name"]
        fetch = _step(jobs["attest"], "Fetch the SBOM")
        attach = _step(jobs["attest"], "Attach the SBOM")
        assert fetch["with"] == {"name": artifact, "path": "downloaded-sbom"}
        assert attach["env"]["SBOM_FILE"] == f"downloaded-sbom/{artifact}"
        assert 'test -s "${SBOM_FILE}"' in attach["run"]
        assert '--predicate "${SBOM_FILE}"' in attach["run"]

    def test_the_chart_alias_preserves_and_checks_the_source_digest(self) -> None:
        """Review of A2 (Codex, not asked): helm.yaml's label step made an unqualified copy with no
        digest comparison — the same alias rule the build script now holds."""
        run = _step(_jobs(HELM)["release"], "Label the image this chart version deploys")["run"]
        assert "SOURCE_DIGEST=$(skopeo inspect" in run
        assert "skopeo copy --all --preserve-digests" in run
        assert '[ "${ALIAS_DIGEST}" != "${SOURCE_DIGEST}" ]' in run
        # C3: a release is two images, so the remedy the error names is two commands.
        assert "./build-and-push-external.sh --release-tags" in run
        assert "./build-and-push-report.sh --release-tags" in run

    def test_the_chart_attestation_has_the_same_switch_and_runs_only_for_a_new_release(self) -> None:
        release = _jobs(HELM)["release"]
        for fragment in ("Attest the provenance of the packaged chart", "Read the chart attestation back"):
            cond = _step(release, fragment)["if"]
            assert "vars.SUPPLY_CHAIN_SIGNING != 'false'" in cond
            assert "steps.plan.outputs.new == 'true'" in cond
        plan = _step(release, "Report what this run will publish")
        assert plan.get("id") == "plan"
        # `new` is decided across EVERY chart chart-releaser packages (review of #209: the second
        # chart was released with no provenance while the plan looked at the app chart alone).
        assert 'for chart in charts/*/; do' in plan["run"] and 'echo "new=${new}" >> "$GITHUB_OUTPUT"' in plan["run"]
        assert "new=true" in plan["run"] and "new=false" in plan["run"]


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

    def test_signing_runs_only_on_main_and_verifies_the_main_identity(self) -> None:
        """Review of A2 (Cursor): `github.ref` in the identity would let a workflow_dispatch from
        another branch sign under that branch, pass its own read-back and fail the install guide's
        command. The job is gated on main and the identity is the string the guide quotes."""
        attest = _jobs(PUBLISH)["attest"]
        assert "github.ref == 'refs/heads/main'" in attest["if"]
        assert attest["env"]["IDENTITY"].endswith("/.github/workflows/publish.yml@refs/heads/main")
        assert attest["env"]["ISSUER"] == "https://token.actions.githubusercontent.com"

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
        assert step["with"]["image"] == "${{ matrix.image }}@${{ matrix.digest }}"
        attach = _step(_jobs(PUBLISH)["attest"], "Attach the SBOM")["run"]
        assert 'cosign attest --yes --type spdxjson --predicate "${SBOM_FILE}"' in attach

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
        # every NEW package the run created and nothing else — the plan step's list (review of
        # #209: a `*.tgz` glob would also attest a changed-but-unbumped chart's package that
        # chart-releaser never uploads)
        assert chart[0]["with"]["subject-path"] == "${{ steps.plan.outputs.subjects }}"

    def test_the_install_guide_gives_the_verification_commands(self) -> None:
        text = INSTALL_GUIDE.read_text()
        assert "cosign verify " in text
        assert "cosign verify-attestation " in text
        assert "gh attestation verify " in text
        assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in text
        assert "/.github/workflows/publish.yml@refs/heads/main" in text
        assert "/.github/workflows/helm.yaml" in text
        assert "the signature travels with `skopeo copy --all`" not in text, "skopeo --all copies platforms, not referrers"
        assert "oras cp --recursive" in text
        # C3: the report image is a second subject of the same chain, and the guide says which
        # reference to substitute and which artifact holds its SBOM.
        section = text.split("## 7. Verify what you downloaded", 1)[1].split("## Quick reference", 1)[0]
        assert "group-sync-dashboard-report" in section
        assert "`sbom-report-<commit>`" in section and "`sbom-<commit>`" in section
        # Codex, second pass: "every image is signed" holds only with both switches at their defaults,
        # and the sentence that says so names them (D8), before the first command.
        opening = section.split("**The image signature.**", 1)[0]
        assert "SUPPLY_CHAIN_SIGNING" in opening and "SUPPLY_CHAIN_SBOM" in opening and "D8" in opening


# ── Two images, one chain (C3) ───────────────────────────────────────────────────────────────


class TestTwoImagesOneChain:
    """The report image gets the dashboard's catalogue, signature and provenance through the same
    definition — a two-leg matrix on `sbom` and `attest`, each leg the <image, digest> pair the
    publish job reported — rather than a second copy of the steps that could drift."""

    LEGS = {
        "dashboard": {
            "image": "${{ needs.publish.outputs.image }}",
            "digest": "${{ needs.publish.outputs.digest }}",
            "artifact": "sbom-${{ github.sha }}",           # the name the install guide gives, unchanged
        },
        "report": {
            "image": "${{ needs.publish.outputs.report_image }}",
            "digest": "${{ needs.publish.outputs.report_digest }}",
            "artifact": "sbom-report-${{ github.sha }}",
        },
    }

    @staticmethod
    def _legs(job: dict) -> dict:
        strategy = job["strategy"]
        # `.get`: an absent key is GitHub's default, fail-fast ON — the same defect as `true`.
        assert strategy.get("fail-fast") is False, "one image's failure must not cancel the other's leg"
        assert set(strategy["matrix"]) == {"include"}, "explicit legs only; a cross product would multiply them"
        legs = {entry["name"]: {k: v for k, v in entry.items() if k != "name"} for entry in strategy["matrix"]["include"]}
        assert len(legs) == len(strategy["matrix"]["include"]), "leg names must be distinct"
        return legs

    def test_sbom_and_attest_run_one_leg_per_pushed_image_from_the_same_definition(self) -> None:
        jobs = _jobs(PUBLISH)
        assert self._legs(jobs["sbom"]) == self.LEGS
        assert self._legs(jobs["attest"]) == self.LEGS, (
            "the attest job downloads the artifact the sbom job named; the two matrices must be identical"
        )

    def test_each_leg_catalogues_signs_and_attests_its_own_digest(self) -> None:
        jobs = _jobs(PUBLISH)
        catalogue = _step(jobs["sbom"], "Catalogue the image")["with"]
        assert catalogue["image"] == "${{ matrix.image }}@${{ matrix.digest }}"
        assert catalogue["artifact-name"] == "${{ matrix.artifact }}"
        assert jobs["attest"]["env"]["IMAGE"] == "${{ matrix.image }}"
        assert jobs["attest"]["env"]["DIGEST"] == "${{ matrix.digest }}"

    def test_the_job_level_conditions_do_not_read_the_matrix(self) -> None:
        """GitHub's context-availability table: `matrix` is readable by a job's `name`, `env`,
        `strategy` and its steps, but NOT by the job-level `if` — a reference there is an empty
        string, not an error, and an empty digest in a condition is a job that silently skips."""
        for name in ("sbom", "attest"):
            assert "matrix." not in _jobs(PUBLISH)[name]["if"], name

    def test_the_two_artifact_names_are_distinct(self) -> None:
        """A run holds one artifact per name, and sbom-action names the file inside after the
        artifact — two legs sharing `sbom-<sha>` would fail the second upload."""
        artifacts = [leg["artifact"] for leg in self._legs(_jobs(PUBLISH)["sbom"]).values()]
        assert len(set(artifacts)) == len(artifacts), artifacts

    def test_the_install_guide_verifies_the_tag_a_push_actually_signed(self) -> None:
        """Review of A2 (Cursor): an ordinary merge signs only `:<appVersion>-<sha>`; the alias moves
        on an application release. The guide's command names the immutable tag and says when the alias
        verifies too, or the first reader after this lands verifies yesterday's unsigned alias."""
        section = INSTALL_GUIDE.read_text().split("## 7. Verify what you downloaded", 1)[1].split("## Quick reference", 1)[0]
        # Every image command, not only the first: the second pass found verify-attestation and
        # gh attestation verify still naming the alias after the first pass fixed `cosign verify`.
        for verb in ("cosign verify \\", "cosign verify-attestation", "gh attestation verify oci://"):
            block = section.split(verb, 1)[1].split("```", 1)[0]
            assert "group-sync-dashboard:0.15.0-<sha>" in block, (verb, block)
            assert "group-sync-dashboard:0.15.0 " not in block and "group-sync-dashboard:0.15.0\n" not in block, verb
        assert "moves only on an application release" in section
        assert "Every image `publish.yml` pushes is signed" not in section, "a branch dispatch pushes unsigned (D9)"
        assert "A fork verifies against its own identity" not in section, "publish is skipped on forks"
        assert "Forks do not sign under this workflow" in section


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
{ printf 'skopeo'; printf ' %s' "$@"; printf '\\n'; } >> "${STUB_LOG}"
for arg in "$@"; do source_ref=${last_ref:-}; last_ref=$arg; done
case "$1" in
  --version) echo "skopeo version 1.13.3" ;;
  login) cat > /dev/null ;;
  copy) if [ -n "${STUB_REFUSE:-}" ] && [[ "${last_ref}" == *"${STUB_REFUSE}"* ]]; then
          echo "stub skopeo: writing manifest to ${last_ref}: denied" >&2; exit 1
        fi
        printf '%s' "${source_ref##*@}" > "${STUB_STATE}" ;;
  inspect) if [ -n "${STUB_ANSWER:-}" ]; then echo "${STUB_ANSWER}"; else cat "${STUB_STATE}"; echo; fi ;;
  *) echo "stub skopeo: unexpected $1" >&2; exit 2 ;;
esac
"""

    @classmethod
    def _job(cls) -> dict:
        return _jobs(PUBLISH)[cls.JOB]

    @classmethod
    def _run(cls, tmp_path: pathlib.Path, *, answer: str = "", digest: str = NEW, report_digest: str = NEW_REPORT,
             refuse: str = "") -> tuple[subprocess.CompletedProcess, list[str]]:
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
           credentials: bool = True, unreachable: str = "",
           step: tuple[pathlib.Path, str, str] = (HELM, "release", LABEL_STEP)) -> tuple[subprocess.CompletedProcess, str, dict]:
    """Run `step` (the label step unless told otherwise) as GitHub runs `shell: bash`, in a tree carrying the
    real chart files."""
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
    script.write_text(_step(_jobs(step[0])[step[1]], step[2])["run"])
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

    def test_t410_10_the_release_guide_says_what_the_label_refusal_means(self) -> None:
        table = RELEASING.read_text().split("## What can go wrong, and what it looks like", 1)[1]
        row = next((line for line in table.splitlines() if "is application" in line and "(#410)" in line), "")
        assert "Label the image this chart version deploys" in row, row
        assert "never retag" in row.lower() and "re-run" in row, row
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
