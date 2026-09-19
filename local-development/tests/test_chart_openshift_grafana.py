"""charts/openshift-grafana (#162): an isolated Grafana on user-workload monitoring, for any team.

Rendered with a real `helm template` — the chart's whole contract is what it renders under each
switch, and the four operator/OperatorGroup combinations, the two Thanos scopes and the opt-in
Route are the ones a consuming team will actually choose between.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "openshift-grafana"

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(*sets: str, namespace: str = "team-a", release: str = "obs") -> list[dict]:
    args = ["helm", "template", release, str(CHART), "-n", namespace]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _kinds(docs: list[dict]) -> list[str]:
    return sorted(d["kind"] for d in docs)


def _one(docs: list[dict], kind: str, name_contains: str = "") -> dict:
    found = [d for d in docs if d["kind"] == kind and name_contains in d["metadata"]["name"]]
    assert len(found) == 1, f"{kind} {name_contains!r}: {len(found)} rendered"
    return found[0]


@needs_helm
class TestInstallModes:
    def test_the_default_installs_the_operator_in_its_own_namespace(self):
        docs = _render()
        og, sub = _one(docs, "OperatorGroup"), _one(docs, "Subscription")
        assert og["spec"]["targetNamespaces"] == ["team-a"]
        assert sub["spec"] == {"channel": "v5", "installPlanApproval": "Automatic", "name": "grafana-operator",
                               "source": "community-operators", "sourceNamespace": "openshift-marketplace"}

    def test_reusing_a_platform_operator_renders_no_olm_objects(self):
        docs = _render("operator.install=false")
        assert "Subscription" not in _kinds(docs) and "OperatorGroup" not in _kinds(docs)
        # the instance and its wiring are still there
        for kind in ("Grafana", "GrafanaDatasource", "ServiceAccount", "Secret", "ConfigMap", "RoleBinding", "NetworkPolicy", "Job"):
            assert kind in _kinds(docs), kind

    def test_an_existing_operatorgroup_is_reused(self):
        docs = _render("operatorGroup.create=false")
        assert "OperatorGroup" not in _kinds(docs) and "Subscription" in _kinds(docs)

    def test_a_pinned_csv_reaches_the_subscription(self):
        sub = _one(_render("operator.startingCSV=grafana-operator.v5.24.0"), "Subscription")
        assert sub["spec"]["startingCSV"] == "grafana-operator.v5.24.0"


@needs_helm
class TestThanosScope:
    def test_namespace_scope_is_the_default_and_stays_in_the_namespace(self):
        """The tenancy port, a `view` RoleBinding HERE, the namespace query parameter, and GET —
        the tenancy port's kube-rbac-proxy authorises the HTTP method as the verb (measured on CRC:
        a POSTed query was refused as `create pods`)."""
        docs = _render()
        rb = _one(docs, "RoleBinding", "thanos")
        assert rb["metadata"]["namespace"] == "team-a" and rb["roleRef"]["name"] == "view"
        ds = _one(docs, "GrafanaDatasource")["spec"]["datasource"]
        assert ds["url"] == "https://thanos-querier.openshift-monitoring.svc.cluster.local:9092"
        assert ds["jsonData"]["customQueryParameters"] == "namespace=team-a"
        assert ds["jsonData"]["httpMethod"] == "GET"
        assert all(d["metadata"].get("namespace", "team-a") == "team-a" for d in docs), "nothing outside the namespace"

    def test_cluster_scope_is_opt_in_and_lands_in_openshift_monitoring(self):
        docs = _render("thanos.scope=cluster")
        rb = _one(docs, "RoleBinding", "thanos")
        assert rb["metadata"]["namespace"] == "openshift-monitoring" and rb["roleRef"]["name"] == "cluster-monitoring-view"
        ds = _one(docs, "GrafanaDatasource")["spec"]["datasource"]
        assert ds["url"].endswith(":9091") and "customQueryParameters" not in ds["jsonData"]

    def test_an_unknown_scope_refuses_the_render(self):
        with pytest.raises(AssertionError, match="thanos.scope"):
            _render("thanos.scope=everything")


@needs_helm
class TestDatasource:
    def test_name_and_uid_are_deterministic_and_the_secrets_come_through_valuesFrom(self):
        ds = _one(_render(), "GrafanaDatasource")
        assert ds["spec"]["uid"] == "openshift-thanos" and ds["spec"]["datasource"]["name"] == "OpenShift Thanos"
        refs = {(v["targetPath"], next(iter(v["valueFrom"]))) for v in ds["spec"]["valuesFrom"]}
        assert refs == {("secureJsonData.httpHeaderValue1", "secretKeyRef"), ("secureJsonData.tlsCACert", "configMapKeyRef")}
        rendered = yaml.safe_dump(ds)
        assert "BEGIN CERTIFICATE" not in rendered and "eyJ" not in rendered, "no secret and no certificate in the manifest"

    def test_tls_is_verified_against_the_service_ca_never_skipped(self):
        docs = _render()
        ds = _one(docs, "GrafanaDatasource")["spec"]["datasource"]
        assert ds["jsonData"]["tlsAuthWithCACert"] is True and "tlsSkipVerify" not in ds["jsonData"]
        cm = _one(docs, "ConfigMap")
        assert cm["metadata"]["annotations"]["service.beta.openshift.io/inject-cabundle"] == "true"

    def test_the_datasource_selects_the_instance_by_the_release_and_extra_labels(self):
        docs = _render("grafana.labels.dashboards=grafana")
        sel = _one(docs, "GrafanaDatasource")["spec"]["instanceSelector"]["matchLabels"]
        assert sel == {"app.kubernetes.io/instance": "obs", "dashboards": "grafana"}
        assert _one(docs, "Grafana")["metadata"]["labels"]["dashboards"] == "grafana"


@needs_helm
class TestInstance:
    def test_no_route_by_default_and_an_edge_route_on_request(self):
        assert "route" not in _one(_render(), "Grafana")["spec"]
        g = _one(_render("grafana.route.enabled=true", "grafana.route.host=g.apps.example"), "Grafana")
        assert g["spec"]["route"]["spec"]["host"] == "g.apps.example"
        assert g["spec"]["route"]["spec"]["tls"]["termination"] == "edge"

    def test_admin_credentials_are_the_operators_unless_a_secret_is_named(self):
        assert "disableDefaultAdminSecret" not in _one(_render(), "Grafana")["spec"]
        g = _one(_render("grafana.admin.existingSecret=creds"), "Grafana")
        assert g["spec"]["disableDefaultAdminSecret"] is True
        env = g["spec"]["deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env} == {"creds"}

    def test_the_networkpolicy_admits_the_router_and_the_namespace_only(self):
        np = _one(_render(), "NetworkPolicy")
        # the operator's own pod label (`app: <Grafana name>`, measured on v5.24.0) — a selector that
        # matches no pod protected nothing on the first CRC install
        assert np["spec"]["podSelector"] == {"matchLabels": {"app": "obs-openshift-grafana"}}
        froms = np["spec"]["ingress"][0]["from"]
        assert {"namespaceSelector": {"matchLabels": {"policy-group.network.openshift.io/ingress": ""}}} in froms
        assert {"podSelector": {}} in froms and len(froms) == 2
        assert "NetworkPolicy" not in _kinds(_render("networkPolicy.enabled=false"))

    def test_the_wait_job_is_a_helm_and_argo_hook(self):
        job = _one(_render(), "Job")
        ann = job["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "post-install,post-upgrade" and ann["argocd.argoproj.io/hook"] == "Sync"
        assert job["spec"]["activeDeadlineSeconds"] == 720


@needs_helm
class TestNothingApplicationSpecific:
    def test_no_group_sync_reference_in_anything_rendered_or_documented(self):
        """Chart.yaml's `home`/`sources` and the README's `helm repo add` name the repository the chart
        is published from — a URL, not content; every template, the values and the notes are
        application-free, and the README names no application object."""
        files = [p for p in CHART.rglob("*") if p.is_file() and p.suffix in (".yaml", ".tpl", ".txt") and p.name != "Chart.yaml"]
        text = "\n".join(p.read_text() for p in files)
        assert "group-sync" not in text and "gsd" not in text.lower()
        readme = "\n".join(l for l in (CHART / "README.md").read_text().splitlines() if "github.io" not in l and "helm repo add" not in l and "helm install" not in l)
        assert "group-sync" not in readme and "gsd" not in readme.lower()
        rendered = yaml.safe_dump_all(_render())
        assert "group-sync" not in rendered and "gsd" not in rendered.lower()

    def test_crds_are_shipped_for_the_four_kinds_the_chart_and_its_consumers_use(self):
        names = sorted(p.name for p in (CHART / "crds").glob("*.yaml"))
        assert names == ["grafanadashboards.grafana.integreatly.org.yaml", "grafanadatasources.grafana.integreatly.org.yaml",
                         "grafanafolders.grafana.integreatly.org.yaml", "grafanas.grafana.integreatly.org.yaml"]
        for p in (CHART / "crds").glob("*.yaml"):
            crd = yaml.safe_load(p.read_text())
            assert crd["kind"] == "CustomResourceDefinition" and "status" not in crd
            assert crd["metadata"]["name"] == p.name[:-5]
