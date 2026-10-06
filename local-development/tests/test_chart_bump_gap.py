"""A missed chart `version` bump is refused in the pull request and never relabels a published chart (#625).

ci.yml's bump check left `Chart.yaml` out of the changed files (bumping the version IS a change under charts/),
so a pull request that moved `appVersion` and forgot `version` passed. After the merge helm.yaml's label step
ran anyway and copied the new `:<appVersion>` over the already-published chart's `:<chartVersion>`. The check
now counts a `Chart.yaml` change outside its `version:` line and comments as chart content, and helm.yaml labels
only when the app chart's own version is new. Both scripts are lifted from the parsed workflows and run in a
throwaway git repository.
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
HELM = REPO / ".github" / "workflows" / "helm.yaml"
BUMP_STEP = "A change under charts/ requires a new Chart.yaml version"
PLAN_STEP = "Report what this run will publish"
LABEL_STEP = "Label the image this chart version deploys"

# How GitHub runs a `run:` block with the default shell: -e and pipefail are on.
GITHUB_BASH = ("bash", "--noprofile", "--norc", "-eo", "pipefail", "-c")

GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}

CHART_YAML = """apiVersion: v2
name: group-sync-dashboard
# history: chart 0.1.0
version: 0.1.0
appVersion: "1.0.0"
"""


def _step(workflow: pathlib.Path, job: str, name: str) -> dict:
    steps = yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]
    return next(s for s in steps if s.get("name") == name)


def _git(repo: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, env=GIT_ENV, capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    chart = tmp_path / "charts" / "group-sync-dashboard"
    (chart / "templates").mkdir(parents=True)
    (chart / "Chart.yaml").write_text(CHART_YAML)
    (chart / "templates" / "a.yaml").write_text("kind: ConfigMap\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _edit_and_check(repo: pathlib.Path, chart_yaml: str, template: str | None = None) -> subprocess.CompletedProcess:
    base = _git(repo, "rev-parse", "HEAD").strip()
    chart = repo / "charts" / "group-sync-dashboard"
    (chart / "Chart.yaml").write_text(chart_yaml)
    if template is not None:
        (chart / "templates" / "a.yaml").write_text(template)
    _git(repo, "commit", "-qam", "change")
    return subprocess.run([*GITHUB_BASH, _step(CI, "version-bump", BUMP_STEP)["run"]], cwd=repo,
                          env={**GIT_ENV, "BASE": base}, capture_output=True, text=True, check=False)


def test_an_app_version_change_without_a_chart_bump_is_refused(repo: pathlib.Path) -> None:
    done = _edit_and_check(repo, CHART_YAML.replace('appVersion: "1.0.0"', 'appVersion: "1.1.0"'))
    assert done.returncode == 1, done.stdout + done.stderr
    assert "chart content changed but version is still 0.1.0" in done.stdout


def test_an_app_version_change_with_a_chart_bump_passes(repo: pathlib.Path) -> None:
    done = _edit_and_check(repo, CHART_YAML.replace('appVersion: "1.0.0"', 'appVersion: "1.1.0"')
                           .replace("version: 0.1.0", "version: 0.1.1"))
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_version_bump_with_its_history_comment_needs_no_second_bump(repo: pathlib.Path) -> None:
    done = _edit_and_check(repo, CHART_YAML.replace("# history: chart 0.1.0\nversion: 0.1.0",
                                                    "# history: chart 0.1.0\n# history: chart 0.1.1\nversion: 0.1.1"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "no chart content changed" in done.stdout


def test_a_template_change_without_a_bump_is_still_refused(repo: pathlib.Path) -> None:
    done = _edit_and_check(repo, CHART_YAML, template="kind: Secret\n")
    assert done.returncode == 1, done.stdout + done.stderr


def _plan(repo: pathlib.Path) -> dict[str, str]:
    out = repo / "github_output"
    out.write_text("")
    subprocess.run([*GITHUB_BASH, _step(HELM, "release", PLAN_STEP)["run"]], cwd=repo,
                   env={**GIT_ENV, "GITHUB_OUTPUT": str(out)}, capture_output=True, text=True, check=True)
    return dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)


def test_the_plan_says_whether_the_app_chart_s_own_version_is_new(repo: pathlib.Path) -> None:
    assert _plan(repo)["app_new"] == "true"
    _git(repo, "tag", "group-sync-dashboard-0.1.0")
    assert _plan(repo)["app_new"] == "false"


def test_a_new_second_chart_does_not_make_the_app_chart_new(repo: pathlib.Path) -> None:
    """`new` is true when ANY chart is new; the label step must key on the app chart alone."""
    other = repo / "charts" / "openshift-grafana"
    other.mkdir()
    (other / "Chart.yaml").write_text("apiVersion: v2\nname: openshift-grafana\nversion: 0.2.0\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second chart")
    _git(repo, "tag", "group-sync-dashboard-0.1.0")
    plan = _plan(repo)
    assert (plan["new"], plan["app_new"]) == ("true", "false")


def test_the_label_step_runs_only_for_a_new_app_chart_version() -> None:
    assert _step(HELM, "release", LABEL_STEP).get("if") == "steps.plan.outputs.app_new == 'true'"
