"""priorityClassName is exposed per Deployment (#97) so an operator can protect the app pods from
preemption on a saturated node. Measured on CRC (2026-09-14): the report pod was Preempted 29x in
~3h at 99% node CPU requests, evicted by OLM collect-profiles (openshift-user-critical) and a
marketplace catalog pod (system-cluster-critical). A PodDisruptionBudget does not stop preemption; a
priority does. Default empty, rendered only when set, mirroring the chart's nodeSelector/tolerations/
affinity guards.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _deploy(docs: list[dict], name: str) -> dict:
    exact = [d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"] == name]
    assert len(exact) == 1, [d["metadata"]["name"] for d in docs if d.get("kind") == "Deployment"]
    return exact[0]


def _prio(deploy: dict):
    return deploy["spec"]["template"]["spec"].get("priorityClassName")


@needs_helm
class TestPriorityClassName:
    def test_absent_by_default_on_both_deployments(self):
        docs = _render()
        assert _prio(_deploy(docs, "t-group-sync-dashboard")) is None
        assert _prio(_deploy(docs, "t-group-sync-dashboard-report")) is None

    def test_dashboard_opt_in_does_not_touch_the_report_pod(self):
        docs = _render("priorityClassName=high-dashboard")
        assert _prio(_deploy(docs, "t-group-sync-dashboard")) == "high-dashboard"
        assert _prio(_deploy(docs, "t-group-sync-dashboard-report")) is None

    def test_report_opt_in_does_not_touch_the_dashboard_pod(self):
        docs = _render("reporting.priorityClassName=high-report")
        assert _prio(_deploy(docs, "t-group-sync-dashboard-report")) == "high-report"
        assert _prio(_deploy(docs, "t-group-sync-dashboard")) is None
