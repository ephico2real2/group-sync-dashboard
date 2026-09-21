"""The Flux example (`examples/flux/helmrelease.yaml`, #212) holds against the charts it names.

Flux is not on the lab, so the apply is not measured; what CI can hold offline is the shape the
helm-controller docs and source require, the two settings a real install depends on, and that each
release's `values` renders with its chart — the dashboard's with the Grafana API served, as it is
once the grafana release is Ready — into a CR that selects the instance and datasource the grafana
release creates. Parsed and rendered, never grepped.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "flux" / "helmrelease.yaml"
CHARTS = REPO / "charts"
GRAFANA_API = "grafana.integreatly.org/v1beta1"
_UNIT = {"ms": 0.001, "s": 1, "m": 60, "h": 3600}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _docs() -> list[dict]:
    return [d for d in yaml.safe_load_all(EXAMPLE.read_text()) if d]


def _releases() -> dict[str, dict]:
    return {d["metadata"]["name"]: d for d in _docs() if d["kind"] == "HelmRelease"}


def _seconds(duration: str) -> float:
    """A Go duration as the CRD's pattern admits it: `15m`, `5m30s`, `600s`."""
    parts = re.findall(r"([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)", duration)
    assert parts and "".join(n + u for n, u in parts) == duration, duration
    return sum(float(n) * _UNIT[u] for n, u in parts)


def _render(release: dict, *extra: str) -> list[dict]:
    spec = release["spec"]["chart"]["spec"]
    args = ["helm", "template", release["spec"]["releaseName"], str(CHARTS / spec["chart"]),
            "-n", release["metadata"]["namespace"], "--values", "-", *extra]
    done = subprocess.run(args, input=yaml.safe_dump(release["spec"].get("values") or {}),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def test_the_four_objects_are_the_shape_helm_controller_reads():
    docs = _docs()
    assert [(d["apiVersion"], d["kind"]) for d in docs] == [
        ("v1", "Namespace"),
        ("source.toolkit.fluxcd.io/v1", "HelmRepository"),
        ("helm.toolkit.fluxcd.io/v2", "HelmRelease"),
        ("helm.toolkit.fluxcd.io/v2", "HelmRelease"),
    ]
    namespace = docs[0]["metadata"]["name"]
    repo = docs[1]
    assert repo["metadata"]["namespace"] == namespace
    for release in docs[2:]:
        spec = release["spec"]
        assert release["metadata"]["namespace"] == namespace
        assert spec["chart"]["spec"]["sourceRef"] == {"kind": "HelmRepository", "name": repo["metadata"]["name"]}, "the sourceRef must name the HelmRepository beside it, in its namespace"
        assert (CHARTS / spec["chart"]["spec"]["chart"] / "Chart.yaml").is_file(), spec["chart"]["spec"]["chart"]
        assert re.fullmatch(r"\d+\.\d+\.\d+", str(spec["chart"]["spec"]["version"])), "pin an exact version: helm-controller resolves a range on every reconcile"
        shipped = yaml.safe_load((CHARTS / spec["chart"]["spec"]["chart"] / "Chart.yaml").read_text())["version"]
        assert tuple(map(int, spec["chart"]["spec"]["version"].split("."))) <= tuple(map(int, shipped.split("."))), f"{spec['chart']['spec']['chart']} pins {spec['chart']['spec']['version']}, ahead of the tree's {shipped}"


def test_the_dashboard_depends_on_the_grafana_release():
    releases = _releases()
    assert releases["group-sync-dashboard"]["spec"]["dependsOn"] == [{"name": "grafana"}], (
        "helm-controller re-renders a deployed release only on a chart or values change, never on the "
        "interval (internal/reconcile/state.go): a CR the first install could not render never appears "
        "by itself, so the dashboard must wait for the grafana release to be Ready")


def test_the_grafana_release_leaves_the_crds_to_helms_default_and_outwaits_the_gate():
    grafana = _releases()["grafana"]["spec"]
    for action in ("install", "upgrade"):
        assert "crds" not in grafana.get(action, {}), (
            f"{action}.crds is set: the chart's crds/ are copies of the operator's for the first install, "
            "OLM owns them once the operator is in, and CreateReplace re-applies the copies over OLM's "
            "on every Helm upgrade (charts/openshift-grafana/README.md, 'only when absent')")
    values = yaml.safe_load((CHARTS / "openshift-grafana" / "values.yaml").read_text())
    ceiling = values["wait"]["waitSeconds"] + 120  # the gate's activeDeadlineSeconds (41-wait-job.yaml)
    assert "timeout" in grafana, "helm-controller waits for each hook Job only up to spec.timeout, 5m by default; the gate can count longer"
    assert _seconds(grafana["timeout"]) >= ceiling, f"timeout {grafana['timeout']} is under the gate's ceiling of {ceiling}s"


def test_each_values_block_renders_and_the_dashboard_cr_selects_what_the_grafana_release_creates():
    releases = _releases()
    grafana_docs = _render(releases["grafana"])
    dashboard_docs = _render(releases["group-sync-dashboard"], "--api-versions", GRAFANA_API)
    instances = [d for d in grafana_docs if d["kind"] == "Grafana"]
    datasources = [d for d in grafana_docs if d["kind"] == "GrafanaDatasource"]
    boards = [d for d in dashboard_docs if d["kind"] == "GrafanaDashboard"]
    assert len(instances) == 1 and len(datasources) == 1 and len(boards) == 1
    label = "app.kubernetes.io/instance"
    assert boards[0]["spec"]["instanceSelector"]["matchLabels"][label] == instances[0]["metadata"]["labels"][label]
    assert [ds["datasourceName"] for ds in boards[0]["spec"]["datasources"]] == [datasources[0]["spec"]["uid"]]
    assert not [d for d in _render(releases["group-sync-dashboard"]) if d["kind"] == "GrafanaDashboard"], "no CR where the API is not served"
