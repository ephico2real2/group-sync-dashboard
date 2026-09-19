"""charts/openshift-grafana (#162): an isolated Grafana on user-workload monitoring, for any team.

Rendered with a real `helm template` — the chart's whole contract is what it renders under each
switch, and the four operator/OperatorGroup combinations, the two Thanos scopes and the opt-in
Route are the ones a consuming team will actually choose between.
"""

from __future__ import annotations

import os
import re
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
    def test_no_route_by_default_and_a_named_host_on_request(self):
        docs = _render()
        assert "route" not in _one(docs, "Grafana")["spec"] and "Route" not in _kinds(docs)
        route = _one(_render("grafana.route.enabled=true", "grafana.route.host=g.apps.example"), "Route")
        assert route["spec"]["host"] == "g.apps.example"

    def test_admin_credentials_are_the_charts_secret_unless_one_is_named(self):
        docs = _render()
        g = _one(docs, "Grafana")
        assert g["spec"]["disableDefaultAdminSecret"] is True
        env = g["spec"]["deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env} == {"obs-openshift-grafana-admin"}
        assert _one(docs, "Secret", "-admin")["data"]["GF_SECURITY_ADMIN_USER"] == "a3ViZWFkbWlu"   # kubeadmin: the proxied identity that is admin
        g = _one(_render("grafana.admin.existingSecret=creds"), "Grafana")
        env = g["spec"]["deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env} == {"creds"}

    def test_openshift_login_is_the_default_and_the_header_is_trusted_from_the_loopback_only(self):
        """The click from the KPI page lands on the cluster's login; the OpenShift identity is the
        Grafana user. Measured on CRC: a forged X-Forwarded-User on 3000 from a same-namespace pod
        answers 401, and an unauthenticated request through the proxy is a 302 to the OAuth server."""
        docs = _render("grafana.route.enabled=true")
        g = _one(docs, "Grafana")["spec"]
        assert g["config"]["auth.proxy"] == {"enabled": "true", "header_name": "X-Forwarded-User", "header_property": "username",
                                             "auto_sign_up": "true", "whitelist": "127.0.0.1"}
        assert g["config"]["auth"]["disable_login_form"] == "true"
        containers = {c["name"]: c for c in g["deployment"]["spec"]["template"]["spec"]["containers"]}
        args = containers["oauth-proxy"]["args"]
        assert "-provider=openshift" in args and "-upstream=http://127.0.0.1:3000" in args
        assert '-openshift-sar={"resource":"namespaces","verb":"get","name":"team-a"}' in args
        assert "-openshift-service-account=obs-openshift-grafana-sa" in args
        ref = g["serviceAccount"]["metadata"]["annotations"]["serviceaccounts.openshift.io/oauth-redirectreference.primary"]
        assert '"name":"obs-openshift-grafana"' in ref
        assert "route" not in g, "the operator's edge Route is off; the chart's reencrypt Route fronts the proxy"
        route = _one(docs, "Route")
        assert route["spec"]["to"]["name"] == "obs-openshift-grafana-proxy" and route["spec"]["tls"]["termination"] == "reencrypt"
        svc = _one(docs, "Service")
        assert svc["metadata"]["annotations"]["service.beta.openshift.io/serving-cert-secret-name"] == "obs-openshift-grafana-proxy-tls"
        np = _one(docs, "NetworkPolicy")["spec"]["ingress"]
        router = [r for r in np if any("namespaceSelector" in f for f in r["from"])][0]
        assert [p["port"] for p in router["ports"]] == [8443], "the router reaches the proxy only"

    def test_grafana_login_mode_renders_no_proxy(self):
        docs = _render("grafana.auth.mode=grafana", "grafana.route.enabled=true")
        g = _one(docs, "Grafana")["spec"]
        assert "auth.proxy" not in g["config"] and g["config"]["auth"]["disable_login_form"] == "false"
        assert [c["name"] for c in g["deployment"]["spec"]["template"]["spec"]["containers"]] == ["grafana"]
        assert g["route"]["spec"]["tls"]["termination"] == "edge"
        assert "Route" not in _kinds(docs) and "Service" not in _kinds(docs)
        assert not [d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"].endswith("oauth-cookie")]

    def test_the_networkpolicy_admits_the_routers_and_the_namespace_only(self):
        """Both router topologies (review of #209, OB3 G5): pod-network routers arrive from
        openshift-ingress, HostNetwork routers (bare metal, CRC) from the node, which OVN-Kubernetes
        labels through the openshift-host-network namespace — the pair the ingress operator's own
        canary policy admits. A policy that names only the first works on a single node (a policy
        never blocks the resident node) and refuses the Route from every other node of a multi-node
        HostNetwork cluster."""
        routers = [{"namespaceSelector": {"matchLabels": {"policy-group.network.openshift.io/ingress": ""}}},
                   {"namespaceSelector": {"matchLabels": {"policy-group.network.openshift.io/host-network": ""}}}]
        np = _one(_render("grafana.auth.mode=grafana"), "NetworkPolicy")
        # the operator's own pod label (`app: <Grafana name>`, measured on v5.24.0) — a selector that
        # matches no pod protected nothing on the first CRC install
        assert np["spec"]["podSelector"] == {"matchLabels": {"app": "obs-openshift-grafana"}}
        [rule] = np["spec"]["ingress"]
        assert rule["from"] == [*routers, {"podSelector": {}}]
        assert rule["ports"] == [{"port": 3000, "protocol": "TCP"}]
        # with the OpenShift login the routers reach the proxy's port only; Grafana's own port stays
        # for this namespace
        proxy, own = _one(_render(), "NetworkPolicy")["spec"]["ingress"]
        assert proxy["from"] == routers and proxy["ports"] == [{"port": 8443, "protocol": "TCP"}]
        assert own["from"] == [{"podSelector": {}}] and {p["port"] for p in own["ports"]} == {3000, 8443}
        assert "NetworkPolicy" not in _kinds(_render("networkPolicy.enabled=false"))

    def test_the_wait_role_grants_exactly_the_reads_the_script_makes(self):
        """Every `oc get` in the script, read off the rendered Job, against the Role's rules: a read the
        Role lacks fails the gate at runtime; a grant the script never uses is a grant for nothing
        (review of #209, Codex G2 / OB3 F3a)."""
        docs = _render()
        script = _one(docs, "Job")["spec"]["template"]["spec"]["containers"][0]["args"][0]
        reads = set()
        for m in re.finditer(r"oc get (\S+)( (\S+))?", script):
            if "Inspect:" in script[script.rfind("\n", 0, m.start()):m.start()]:
                continue                           # the command a FAIL message hands the human, not a read
            kind, arg = m.group(1), m.group(3) or ""
            if kind == "-n":                       # `oc get -n NS -o jsonpath=... <type/name>` (the xargs form)
                kind, arg = "clusterserviceversion", "name"
            named = arg not in ("", "-n", "-o") and not arg.startswith("-")
            reads.add((kind, "get" if named else "list"))
        # the one read outside the namespace — cluster-monitoring-config — is behind
        # wait.verifyUserWorkloadMonitoring and its own Role in openshift-monitoring
        assert reads == {("csv", "list"), ("clusterserviceversion", "get"), ("grafana", "get"),
                         ("deployment", "get"), ("grafanadatasource", "get"), ("configmap", "get")}, reads
        rules = {(g, r, v) for rule in _one(docs, "Role", "wait")["rules"]
                 for g in rule["apiGroups"] for r in rule["resources"] for v in rule["verbs"]}
        assert rules == {("operators.coreos.com", "clusterserviceversions", "get"),
                         ("operators.coreos.com", "clusterserviceversions", "list"),
                         ("grafana.integreatly.org", "grafanas", "get"),
                         ("grafana.integreatly.org", "grafanadatasources", "get"),
                         ("apps", "deployments", "get")}, rules
        assert not [d for d in docs if d["kind"] == "Role" and d["metadata"]["namespace"] == "openshift-monitoring"]
        uwm = _one(_render("wait.verifyUserWorkloadMonitoring=true"), "Role", "uwm-check")
        assert uwm["metadata"]["namespace"] == "openshift-monitoring"
        assert uwm["rules"] == [{"apiGroups": [""], "resources": ["configmaps"], "resourceNames": ["cluster-monitoring-config"], "verbs": ["get"]}]

    def test_the_wait_script_sees_a_succeeded_csv_beside_a_replaced_one(self, tmp_path):
        """The rendered script, run under bash with an `oc` shim: during an OLM upgrade the replaced
        CSV (Replacing) and its successor (Succeeded) both match the displayName filter for a while.
        The gate must read that as the operator serving, not wait out the deadline on a phase string
        no case matches (the first draft's range had no separator: "SucceededReplacing" — review of
        #209, OB3 F3b)."""
        job = _one(_render("wait.waitSeconds=2", "wait.intervalSeconds=1"), "Job")
        container = job["spec"]["template"]["spec"]["containers"][0]
        shim = tmp_path / "bin"
        shim.mkdir()
        (shim / "oc").write_text(
            "#!/bin/bash\n"
            "case \"$*\" in\n"
            "  *'get csv'*jsonpath*) printf 'Succeeded\\nReplacing\\n' ;;\n"      # what the range prints, one per line
            "  *'get grafana '*) printf 'complete/success' ;;\n"
            "  *'get deployment '*) printf '1' ;;\n"
            "  *lastMessage*) printf '' ;;\n"
            "  *DatasourceSynchronized*) printf 'True' ;;\n"
            "  *) echo \"unexpected: $*\" >&2; exit 2 ;;\n"
            "esac\n")
        (shim / "oc").chmod(0o755)
        env = {e["name"]: e["value"] for e in container["env"]}
        env["PATH"] = f"{shim}:{os.environ['PATH']}"
        done = subprocess.run([*container["command"], container["args"][0]], env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "csv Succeeded" in done.stdout and "done" in done.stdout

    def test_the_wait_job_is_a_helm_and_argo_hook(self):
        job = _one(_render(), "Job")
        ann = job["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "post-install,post-upgrade" and ann["argocd.argoproj.io/hook"] == "Sync"
        assert job["spec"]["activeDeadlineSeconds"] == 720
        script = job["spec"]["template"]["spec"]["containers"][0]["args"][0]
        assert "enableUserWorkload: true" in script, "the gate names the one prerequisite's command"

    def test_verifying_user_workload_monitoring_is_a_cluster_admin_opt_in(self):
        assert not [d for d in _render() if d["metadata"]["name"].endswith("uwm-check")]
        docs = _render("wait.verifyUserWorkloadMonitoring=true")
        role = [d for d in docs if d["kind"] == "Role" and d["metadata"]["name"].endswith("uwm-check")][0]
        assert role["metadata"]["namespace"] == "openshift-monitoring"
        assert role["rules"] == [{"apiGroups": [""], "resources": ["configmaps"], "resourceNames": ["cluster-monitoring-config"], "verbs": ["get"]}]

    def test_the_datasource_resyncs_every_two_minutes(self):
        assert _one(_render(), "GrafanaDatasource")["spec"]["resyncPeriod"] == "2m"


class TestReadme:
    """Two README statements that a template cannot back are held here (review of #209, OB3 G1/F4):
    the install command's timeout and the rights the default shape needs."""

    def test_the_install_example_gives_helm_a_timeout_above_the_gate(self):
        """Helm waits for a hook only up to --timeout (5m by default) while the gate allows
        wait.waitSeconds + 120s: an install that is still pulling images at 5m would be reported failed
        by a README that omitted the flag."""
        readme = (CHART / "README.md").read_text()
        install = re.search(r"helm install .*?(?=\n```)", readme, re.S).group(0)
        timeout = re.search(r"--timeout (\d+)m", install)
        assert timeout, install
        gate = yaml.safe_load((CHART / "values.yaml").read_text())["wait"]["waitSeconds"] + 120
        assert int(timeout.group(1)) * 60 >= gate, (timeout.group(0), gate)

    def test_the_readme_does_not_promise_project_rights_for_the_default_shape(self):
        """On a cluster with no operator the default shape creates cluster-scoped CRDs and an
        OperatorGroup, neither within a project admin's rights (measured on 4.22: the `admin`
        ClusterRole holds no `create` on operatorgroups)."""
        readme = (CHART / "README.md").read_text()
        assert "installs it with ordinary project rights" not in readme
        row = next(l for l in readme.splitlines() if l.startswith("| Rights needed"))
        assert "cluster-admin" in row.split("|")[2], row


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


@needs_helm
class TestTheAppChartsDoors:
    """The app chart refuses a door URL that is not an http(s) URL at RENDER time (review of #209,
    Grok N4): the app's own guard runs at process start, after a successful `helm upgrade`."""

    APP = REPO / "charts" / "group-sync-dashboard"

    def _render(self, *sets: str) -> subprocess.CompletedProcess:
        args = ["helm", "template", "t", str(self.APP)]
        for s in sets:
            args += ["--set", s]
        return subprocess.run(args, capture_output=True, text=True, timeout=120)

    def test_bad_door_urls_refuse_the_render_and_good_ones_pass(self):
        for bad in ("grafana.url=javascript:alert(1)", "console.url=grafana.example.com", "grafana.url=https://g.example/?x=1"):
            done = self._render(bad)
            assert done.returncode != 0 and "must be an http(s) URL" in done.stderr, bad
        assert self._render("grafana.url=https://g.example/grafana", "console.url=https://c.example").returncode == 0
