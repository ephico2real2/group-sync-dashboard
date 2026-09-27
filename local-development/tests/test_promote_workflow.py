"""promote.yml, and the three places that name the promoted artifact, agree (#410, SPEC_P1)."""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO / ".github" / "workflows"
PROMOTE = WORKFLOWS / "promote.yml"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text())


def _on(workflow: dict) -> dict:
    return workflow.get("on") or workflow[True]   # YAML 1.1 reads `on` as True


def test_it_runs_after_publish_and_promotes_only_a_success():
    on = _on(_load(PROMOTE))
    assert on["workflow_run"] == {"workflows": [_load(WORKFLOWS / "publish.yml")["name"]], "types": ["completed"], "branches": ["main"]}
    job = _load(PROMOTE)["jobs"]["promote"]
    assert "github.event.workflow_run.conclusion == 'success'" in job["if"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "github.repository == 'ephico2real2/group-sync-dashboard'" in job["if"]


def test_a_chart_only_merge_triggers_it_and_a_dispatch_can_roll_back():
    on = _on(_load(PROMOTE))
    assert on["push"]["branches"] == ["main"]
    assert {"charts/group-sync-dashboard/**", "environments/**"} <= set(on["push"]["paths"])
    assert set(on["workflow_dispatch"]["inputs"]) == {"sha", "rollback"}


def test_one_promotion_at_a_time_and_only_the_scopes_it_needs():
    wf = _load(PROMOTE)
    assert wf["concurrency"] == {"group": "promote-release", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["promote"]["permissions"] == {"contents": "write", "actions": "read"}


def test_nothing_in_it_builds():
    text = PROMOTE.read_text()
    for builder in ("podman", "docker build", "build-and-push", "buildx"):
        assert builder not in text, builder


def test_it_verifies_with_the_cosign_publish_signs_with():
    def installer(path: pathlib.Path) -> tuple[str, str]:
        steps = [s for job in _load(path)["jobs"].values() for s in job["steps"] if "cosign-installer" in (s.get("uses") or "")]
        return steps[0]["uses"], steps[0]["with"]["cosign-release"]
    assert installer(PROMOTE) == installer(WORKFLOWS / "publish.yml")


def test_the_application_script_and_workflow_name_one_pin_file_on_release():
    app = _load(REPO / "gitops" / "argocd-application-dashboard.yaml")["spec"]["source"]
    assert app["targetRevision"] == "release"
    assert app["helm"]["valueFiles"] == ["../../environments/crc.yaml", "../../promotion.yaml"], "the pin must come last to win"
    assert re.search(r'^PIN = "promotion.yaml"$', (REPO / "local-development" / "promote.py").read_text(), re.M)
    assert re.search(r"^PIN=promotion.yaml$", (REPO / "local-development" / "release-crc.sh").read_text(), re.M)


def test_the_guide_and_figure_state_what_is_optional_and_what_is_required():
    guide = (REPO / "docs" / "CICD.md").read_text()
    figure = (REPO / "docs" / "diagrams" / "cicd" / "source.html").read_text()
    assert "the revision label is the commit" not in guide and "10-character sha" in guide
    assert "SUPPLY_CHAIN_SIGNING=false" in guide and "`--argocd main` is refused" in guide
    for text in (">pushes<", "on by default", "signature if on", "rollback checked"):
        assert text in figure, text
