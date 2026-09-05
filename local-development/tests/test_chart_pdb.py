"""The PodDisruptionBudget, on by default since chart 0.14.0, must select the Deployment's pods and
nothing else.

Measured on the reference cluster (2026-09-05): the `authLogLevel` hook Job pods carried the same
selector labels as the dashboard pod, the disruption controller resolved a matched pod to a Job,
and the budget failed outright — `SyncFailed: jobs.batch does not implement the scale subresource`,
`DisruptionAllowed=False`, `disruptionsAllowed: 0`. With `maxUnavailable: 1` that is a blocked drain,
the exact failure the values comment says the default avoids. The same labels also made the Service
match a running hook pod (no readiness probe, so Ready as soon as its container starts).
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


def _one(docs: list[dict], kind: str, name_part: str = "") -> dict:
    hits = [d for d in docs if d.get("kind") == kind and name_part in d["metadata"]["name"]]
    assert len(hits) == 1, f"{kind} {name_part!r}: {[d['metadata']['name'] for d in hits]}"
    return hits[0]


def _matches(selector: dict, labels: dict) -> bool:
    return all(labels.get(k) == v for k, v in selector.items())


@needs_helm
class TestThePdbSelectsTheDeploymentOnly:
    def test_on_by_default_and_permissive(self):
        pdb = _one(_render(), "PodDisruptionBudget")
        assert pdb["spec"]["maxUnavailable"] == 1
        assert "minAvailable" not in pdb["spec"]

    def test_off_removes_it(self):
        assert not [d for d in _render("podDisruptionBudget.enabled=false")
                    if d.get("kind") == "PodDisruptionBudget"]

    def test_min_available_replaces_max_unavailable(self):
        pdb = _one(_render("podDisruptionBudget.minAvailable=1"), "PodDisruptionBudget")
        assert pdb["spec"].get("minAvailable") == 1 and "maxUnavailable" not in pdb["spec"]

    def test_the_selector_matches_the_dashboard_pod_and_no_hook_pod(self):
        docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true")
        selector = _one(docs, "PodDisruptionBudget")["spec"]["selector"]["matchLabels"]
        deployment = _one(docs, "Deployment")
        assert _matches(selector, deployment["spec"]["template"]["metadata"]["labels"])
        jobs = [d for d in docs if d.get("kind") == "Job"]
        assert len(jobs) == 2, [d["metadata"]["name"] for d in jobs]
        for job in jobs:
            labels = job["spec"]["template"]["metadata"]["labels"]
            assert not _matches(selector, labels), (
                f"{job['metadata']['name']}: a Job-owned pod in the budget fails it "
                f"(jobs.batch has no scale subresource) and blocks every drain"
            )
            # Still identifiable as this release's pod, just not as the workload.
            assert labels["app.kubernetes.io/instance"] == "t"
            assert labels["app.kubernetes.io/component"].startswith("auth-loglevel")

    def test_a_pod_label_that_collides_with_a_selector_label_is_refused(self):
        """Second-pass review (Cursor): `podLabels.app=x` used to win by last-key-wins, so the
        API server rejected the Deployment and the PDB and Service would have matched no pod.
        Refused by name; a harmless extra label still renders."""
        for key in ("app", "app.kubernetes.io/name", "app.kubernetes.io/instance"):
            escaped = key.replace(".", "\\.")  # Helm --set: a literal dot inside a key
            args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                    "--set", f"podLabels.{escaped}=x"]
            done = subprocess.run(args, capture_output=True, text=True, timeout=120)
            assert done.returncode != 0, key
            assert "podLabels must not set" in done.stderr and key in done.stderr, done.stderr
        docs = _render("podLabels.team=platform")
        labels = _one(docs, "Deployment")["spec"]["template"]["metadata"]["labels"]
        assert labels["team"] == "platform"
        assert _matches(_one(docs, "PodDisruptionBudget")["spec"]["selector"]["matchLabels"], labels)

    def test_the_service_does_not_route_to_a_hook_pod_either(self):
        docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true")
        selector = _one(docs, "Service", "group-sync-dashboard")["spec"]["selector"]
        assert _matches(selector, _one(docs, "Deployment")["spec"]["template"]["metadata"]["labels"])
        for job in (d for d in docs if d.get("kind") == "Job"):
            assert not _matches(selector, job["spec"]["template"]["metadata"]["labels"])
