"""The publish workflow's release decision, and the property that it writes to nothing.

WHAT THIS REPLACED. `tests/test_publish_pin_step.py` was 610 lines and 17 tests, all of them about a
step that pushed a commit to `main` after every image build. That step is gone, and so are the three
defects it caused: a published chart that lagged two merges and shipped without a data-exposure fix
(#34), a release that published nothing while reporting `success` (#37), and branch protection being
impossible because CI had to write to the default branch. Its tests are gone with it — a test for
machinery that no longer exists is a test that can only fail for the wrong reason.

WHAT REPLACES THEM IS THE SAME KIND OF TEST, aimed at the one decision the workflow still makes:
does this push move the `:<appVersion>` release alias? That alias is what the chart resolves by
default, `values.yaml` sets `imagePullPolicy: Always`, and so getting it wrong means the running
binary changes on the next crash or drain while the chart version on the cluster stays put. Both
reviewers refused a version of this design where the alias moved on every merge.

These read the step out of the real YAML rather than restating it, and run its bash in a throwaway
git sandbox — no network, no registry, no runner. The step is pure git plus text, which is exactly
why it can be tested at all.
"""

from __future__ import annotations

import pathlib
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "publish.yml"
PYPROJECT = "local-development/pyproject.toml"


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def step(name_fragment: str) -> dict:
    steps = workflow()["jobs"]["publish"]["steps"]
    matched = [s for s in steps if name_fragment in (s.get("name") or "")]
    assert len(matched) == 1, f"expected one step matching {name_fragment!r}, found {len(matched)}"
    return matched[0]


GIT_ENV = {
    # Isolated from the developer's own git config: a global hooksPath or commit.gpgsign would
    # otherwise fail the run for reasons unrelated to the step under test.
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
}


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"git {' '.join(args)} failed:\n{done.stdout}\n{done.stderr}"
    return done.stdout


@pytest.fixture()
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal repo carrying only what the step reads: pyproject.toml's version line."""
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "local-development").mkdir()
    return tmp_path


def commit_version(repo: pathlib.Path, version: str, message: str) -> str:
    (repo / PYPROJECT).write_text(
        f'[project]\nname = "group-sync-dashboard"\nversion = "{version}"\n'
    )
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
        "commit", "-qm", message)
    return git(repo, "rev-parse", "HEAD").strip()


def decide(repo: pathlib.Path, before: str) -> tuple[subprocess.CompletedProcess, str]:
    """Run the release-decision step's real body; return (result, the value it wrote for is_release)."""
    out = repo / "gh_output"
    out.write_text("")
    env = {**GIT_ENV, "BEFORE": before, "GITHUB_OUTPUT": str(out)}
    done = subprocess.run(["bash", "-c", step("application release")["run"]],
                          cwd=repo, env=env, capture_output=True, text=True, check=False)
    written = ""
    for line in out.read_text().splitlines():
        if line.startswith("is_release="):
            written = line.split("=", 1)[1]
    return done, written


def test_a_version_bump_is_a_release(repo: pathlib.Path) -> None:
    """The alias moves only here: a human changed `version` in pyproject.toml."""
    before = commit_version(repo, "0.7.0", "app 0.7.0")
    commit_version(repo, "0.8.0", "app 0.8.0")

    result, is_release = decide(repo, before)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert is_release == "true", (
        f"a version bump must publish the release alias; step said {is_release!r}\n{result.stdout}"
    )
    assert "0.7.0 -> 0.8.0" in result.stdout


def test_an_ordinary_merge_does_not_move_the_alias(repo: pathlib.Path) -> None:
    """THE CASE BOTH REVIEWERS INSISTED ON. Same appVersion, so the alias must not move.

    With `imagePullPolicy: Always` and the chart resolving appVersion, moving `:0.7.0` here would
    change the running binary on the next container creation — crash, drain, liveness kill,
    scale-out — with no chart change to account for it.
    """
    before = commit_version(repo, "0.7.0", "app 0.7.0")
    (repo / "local-development" / "unrelated.py").write_text("x = 1\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
        "commit", "-qm", "a code change that is not a release")

    result, is_release = decide(repo, before)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert is_release == "false", (
        f"an ordinary merge must NOT move the release alias; step said {is_release!r}"
    )
    assert "unchanged at 0.7.0" in result.stdout


@pytest.mark.parametrize(
    "before,why",
    [("", "workflow_dispatch supplies no `before`"),
     ("0" * 40, "the all-zero sha of a first push"),
     ("deadbeef" * 5, "a sha this checkout cannot read, as after a force-push")],
)
def test_an_unreadable_base_fails_closed_and_says_so(repo: pathlib.Path, before: str, why: str) -> None:
    """Cannot-tell must mean "do not move the alias", AND must say so out loud.

    Fail-closed alone is not enough: silence would be indistinguishable from "not a release", so a
    genuine release whose base could not be read would quietly never publish its alias. The step
    warns and names the manual command instead — the immutable tag is published either way.
    """
    commit_version(repo, "0.7.0", "app 0.7.0")

    result, is_release = decide(repo, before)
    assert result.returncode == 0, f"{why}: step should not fail the job\n{result.stderr}"
    assert is_release == "false", f"{why}: must fail closed, said {is_release!r}"
    assert "::warning::" in result.stdout, f"{why}: a silent skip is the failure mode"
    assert "--release-tags" in result.stdout, (
        f"{why}: the warning must name the manual route, or a missed release has no recovery"
    )


def test_an_unreadable_version_at_head_is_a_hard_error(repo: pathlib.Path) -> None:
    """Not fail-closed: if pyproject has no version, the whole tag scheme is broken.

    The immutable tag is `<version>-<sha>`, so a missing version is not a "maybe not a release" —
    it is a build that cannot be named. That must stop the job, not proceed quietly.
    """
    (repo / PYPROJECT).write_text('[project]\nname = "x"\n')
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
        "commit", "-qm", "no version line")

    result, _ = decide(repo, "")
    assert result.returncode == 1, f"a missing version must fail the job:\n{result.stdout}"
    assert "::error::" in result.stdout


# ── The property the whole change exists for ─────────────────────────────────────────────────


def test_the_publish_job_can_write_to_nothing_but_the_registry() -> None:
    """THE LOAD-BEARING ASSERTION. `contents: read`, and no other scope.

    Every defect this change removed traces to this job holding write access to the repository. If
    a future edit needs `contents: write` or `actions: write` back, the branch protection on `main`
    breaks with it — and it breaks silently, because the release still succeeds while the pin or the
    dispatch does whatever it did before. So the scope is asserted rather than trusted.
    """
    perms = workflow()["jobs"]["publish"]["permissions"]
    assert perms == {"contents": "read"}, (
        f"publish must hold read-only repository access; it declares {perms!r}. Anything more and "
        "main cannot be branch protected — a user-owned repo cannot allowlist the Actions app "
        "(measured: two 422s, see docs/DESIGN_decouple_chart_and_app_release.md)."
    )


def test_no_step_pushes_to_the_repository() -> None:
    """A guard on the APPROACH, because the permission above could be re-widened by accident.

    Belt and braces on purpose: the scope says it cannot push, and this says nothing tries. Either
    alone would let a reviewer wave through a change that reintroduced the pin.
    """
    body = "\n".join(s.get("run") or "" for s in workflow()["jobs"]["publish"]["steps"])
    code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
    for forbidden in ("git push", "git commit", "gh workflow run", "gh pr "):
        assert forbidden not in code, (
            f"publish.yml runs {forbidden!r}. This workflow builds and pushes an image and does "
            f"nothing else to this repository; see the header for the three defects that came from "
            f"it writing to main."
        )


def test_the_release_alias_is_requested_only_on_a_release() -> None:
    """The decision has to be WIRED to the build, not merely computed.

    An earlier draft computed `is_release` and then always called the script the same way, which
    would have published the alias never — a fail-closed bug that no rendering test would catch
    because the workflow still looked correct.
    """
    build = step("Build and push the image")
    # Comments stripped before the negative assertion. The step's comments EXPLAIN why CI does not
    # pass --update-values, so a raw substring check fails on the explanation — which is how this
    # test first failed, and why the same stripping is done in the sibling test above.
    code = "\n".join(
        ln for ln in (build["run"] or "").splitlines() if not ln.strip().startswith("#")
    )
    assert "--release-tags" in code, "the build step must be able to publish the release alias"
    assert "IS_RELEASE" in (build.get("env") or {}), (
        f"the build step must consume the decision; env is {build.get('env')!r}"
    )
    assert "--update-values" not in code, (
        "CI must not rewrite the chart's image.tag — that pin is what this change removed. The "
        "flag itself stays in build-and-push-external.sh for the local and enterprise path."
    )
