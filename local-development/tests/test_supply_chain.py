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
