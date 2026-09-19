"""Two charts under charts/ (#162): every workflow step that names "the chart" must cover both.

chart-releaser walks charts/ and packages every chart it finds, so a workflow step that reads only
charts/group-sync-dashboard lints, plans or attests half of what the release publishes — and says
nothing about the other half. Each step's script is run here, in a scratch checkout with two charts,
rather than grepped: the contract is what the script does, not which path it mentions (review of
#209, OB3 G10).
"""

from __future__ import annotations

import os
import pathlib
import subprocess

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
HELM = REPO / ".github" / "workflows" / "helm.yaml"
CHART_DIRS = sorted(p.parent for p in (REPO / "charts").glob("*/Chart.yaml"))


def _step(workflow: pathlib.Path, job: str, name_prefix: str) -> dict:
    steps = yaml.safe_load(workflow.read_text())["jobs"][job]["steps"]
    found = [s for s in steps if str(s.get("name", "")).startswith(name_prefix)]
    assert len(found) == 1, f"{workflow.name}: {len(found)} steps named {name_prefix!r} in job {job}"
    return found[0]


def test_there_are_two_charts_to_cover() -> None:
    assert [d.name for d in CHART_DIRS] == ["group-sync-dashboard", "openshift-grafana"]


def test_the_chart_job_lints_every_chart(tmp_path: pathlib.Path) -> None:
    """The chart job's lint step, run with a helm shim that records what it was asked to lint."""
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "helm").write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/calls"\n')
    (shim / "helm").chmod(0o755)
    script = _step(CI, "chart", "helm lint")["run"]
    subprocess.run(["bash", "-euo", "pipefail", "-c", script], cwd=REPO, check=True,
                   env={**os.environ, "PATH": f"{shim}:{os.environ['PATH']}"})
    linted = sorted(line.split()[-1].rstrip("/") for line in (tmp_path / "calls").read_text().splitlines())
    assert linted == [str(d.relative_to(REPO)) for d in CHART_DIRS], linted


def _git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@x", "HOME": str(cwd)})


def test_the_release_plan_lists_every_new_chart_package(tmp_path: pathlib.Path) -> None:
    """helm.yaml's plan step in a scratch repository: the application chart already released
    (its tag exists), the second chart new. The run must say it publishes the second chart and hand
    the attestation exactly that package — an already-released version's .tgz sits in the same
    directory and must not be attested."""
    repo = tmp_path / "repo"
    (repo / "charts" / "group-sync-dashboard").mkdir(parents=True)
    (repo / "charts" / "openshift-grafana").mkdir(parents=True)
    (repo / "charts" / "group-sync-dashboard" / "Chart.yaml").write_text("name: group-sync-dashboard\nversion: 1.2.3\n")
    (repo / "charts" / "openshift-grafana" / "Chart.yaml").write_text("name: openshift-grafana\nversion: 0.1.0\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "charts")
    _git(repo, "tag", "group-sync-dashboard-1.2.3")
    out = tmp_path / "github_output"
    script = _step(HELM, "release", "Report what this run will publish")["run"]
    done = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "GITHUB_OUTPUT": str(out)})
    assert done.returncode == 0, done.stderr
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    assert outputs["new"] == "true", (outputs, done.stdout)
    assert outputs["subjects"] == ".cr-release-packages/openshift-grafana-0.1.0.tgz", outputs
    assert outputs["version"] == "1.2.3", "the image alias still follows the application chart"
    # both new: both packages, comma-separated — the action's list form
    _git(repo, "tag", "-d", "group-sync-dashboard-1.2.3")
    done = subprocess.run(["bash", "-c", script], cwd=repo, capture_output=True, text=True,
                          env={**os.environ, "GITHUB_OUTPUT": str(out := tmp_path / "github_output2")})
    outputs = dict(line.split("=", 1) for line in out.read_text().splitlines() if "=" in line)
    assert outputs["subjects"] == ".cr-release-packages/group-sync-dashboard-1.2.3.tgz,.cr-release-packages/openshift-grafana-0.1.0.tgz", outputs


def test_the_attestation_subjects_are_the_plan_step_s_packages() -> None:
    attest = _step(HELM, "release", "Attest the provenance of the packaged chart")
    assert attest["with"]["subject-path"] == "${{ steps.plan.outputs.subjects }}"
    verify = _step(HELM, "release", "Read the chart attestation back")
    assert "steps.plan.outputs.subjects" in yaml.safe_dump(verify)
    assert "${SUBJECTS//,/ }" in verify["run"], "the verify loop walks the same list"
