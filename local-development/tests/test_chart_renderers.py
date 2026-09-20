"""Both charts rendered the way each deployer renders them (#212): plain Helm/Flux (`helm template`,
no cluster knowledge), Argo CD (`helm template --api-versions <live list> --include-crds` — read from
argo-cd util/helm/cmd.go) and Kustomize (`helmCharts` with `apiVersions` and `includeCRDs`). Objects
are parsed, never grepped; what each renderer MUST and MUST NOT emit is asserted per chart.

Kustomize's inflator runs `helm version -c`, which Helm 4 removed, so with a Helm 4 on PATH the
kustomize case needs a Helm 3 binary in $HELM3 (CI's ubuntu runner ships Helm 3, where it runs
unaided); otherwise that case skips with the reason.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHARTS = {"group-sync-dashboard": REPO / "charts" / "group-sync-dashboard", "openshift-grafana": REPO / "charts" / "openshift-grafana"}
GRAFANA_API = "grafana.integreatly.org/v1beta1"
GENERATED = ("-oauth-session", "-oauth-cookie", "-report-token", "-shared-token", "-admin")
# The two `lookup`s that remain, both of which DEGRADE LOUDLY or SAFELY offline and say so in place:
# the apps-domain read on the Ingress path fails the render with a message naming GitOps as case 1
# (the 2026-09-03 finding), and the auditors' Group-collision guard only runs for createLocal groups
# (the default is bind-only) — under Argo CD that guard cannot run, which the README's ArgoCD section
# states. Anything else is a defect this test refuses.
KNOWN_LOOKUPS = {"_helpers.tpl": 1, "rbac-auditors.yaml": 1}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _helm_template(chart: str, *extra: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHARTS[chart]), "-n", "x", *extra]
    if chart == "group-sync-dashboard":
        args += ["--set", "ingress.host=h"]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def bare(chart: str) -> list[dict]:
    return _helm_template(chart)


def argo(chart: str) -> list[dict]:
    return _helm_template(chart, "--api-versions", GRAFANA_API, "--include-crds")


def kustomize(tmp_path: pathlib.Path, chart: str) -> list[dict]:
    helm = shutil.which("helm")
    version = subprocess.run([helm, "version", "--short"], capture_output=True, text=True).stdout
    if version.startswith("v4"):
        helm = os.environ.get("HELM3")
        if not helm:
            pytest.skip("kustomize's inflator needs Helm 3 (`helm version -c`); set HELM3 to a Helm 3 binary")
    if not shutil.which("kubectl"):
        pytest.skip("kubectl not installed")
    work = tmp_path / chart
    (work / "charts").mkdir(parents=True)
    shutil.copytree(CHARTS[chart], work / "charts" / chart)
    values = "\n    valuesInline:\n      ingress:\n        host: h" if chart == "group-sync-dashboard" else ""
    (work / "kustomization.yaml").write_text(
        "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\nnamespace: x\n"
        f"helmCharts:\n  - name: {chart}\n    releaseName: t\n    namespace: x\n    includeCRDs: true\n    apiVersions: [{GRAFANA_API}]{values}\n"
        "helmGlobals:\n  chartHome: charts\n")
    done = subprocess.run(["kubectl", "kustomize", "--enable-helm", "--helm-command", helm, "."], cwd=work, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _names(docs, kind):
    return sorted(d["metadata"]["name"] for d in docs if d["kind"] == kind)


@pytest.mark.parametrize("chart", list(CHARTS))
class TestEveryRenderer:
    def test_no_generated_value_and_no_lookup_in_any_renderer(self, chart, tmp_path):
        for docs in (bare(chart), argo(chart)):
            secrets = _names(docs, "Secret")
            assert not [n for n in secrets if n.endswith(GENERATED)], secrets
        found = {p.name: len(re.findall(r"\(?lookup\s+\"", p.read_text())) for p in (CHARTS[chart] / "templates").iterdir() if p.suffix in (".yaml", ".tpl")}
        found = {k: v for k, v in found.items() if v}
        assert found == (KNOWN_LOOKUPS if chart == "group-sync-dashboard" else {}), f"a lookup call survives — empty under Argo CD and Kustomize: {found}"

    def test_every_hook_carries_both_hook_annotations_with_matching_phases(self, chart):
        phase = {"pre-install": "PreSync", "pre-upgrade": "PreSync", "post-install": "Sync", "post-upgrade": "Sync", "pre-delete": "PreDelete"}
        hooks = [d for d in bare(chart) if "helm.sh/hook" in (d["metadata"].get("annotations") or {})]
        assert hooks, "no hooks rendered"
        for d in hooks:
            ann = d["metadata"]["annotations"]
            argo_hooks = set(ann["argocd.argoproj.io/hook"].split(","))
            wanted = {phase[h] for h in ann["helm.sh/hook"].split(",")}
            assert wanted <= argo_hooks | {"PostSync"} and argo_hooks <= wanted | {"PostSync"}, (d["kind"], d["metadata"]["name"], ann["helm.sh/hook"], ann["argocd.argoproj.io/hook"])

    def test_argos_render_and_kustomizes_agree_and_carry_what_the_bare_render_cannot(self, chart, tmp_path):
        a, k = argo(chart), kustomize(tmp_path, chart)
        assert {(d["kind"], d["metadata"]["name"]) for d in a} == {(d["kind"], d["metadata"]["name"]) for d in k}
        crds = _names(a, "CustomResourceDefinition")
        cr = _names(a, "GrafanaDashboard")
        if chart == "openshift-grafana":
            assert len(crds) == 4 and not _names(bare(chart), "CustomResourceDefinition"), "crds/ only with --include-crds"
        else:
            assert cr == ["t-group-sync-dashboard"] and not _names(bare(chart), "GrafanaDashboard"), "the CR only where the API is served"
