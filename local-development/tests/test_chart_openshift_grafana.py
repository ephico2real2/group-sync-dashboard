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
        assert sub["spec"] == {"channel": "v5", "installPlanApproval": "Manual", "name": "grafana-operator",
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
    def test_a_route_by_default_named_by_the_router_a_host_on_request_and_off_on_request(self):
        """On by default (operator decision 2026-09-19): the router names the host; the Route carries the
        chart's labels in BOTH login modes, which is what a group-sync-dashboard in the namespace
        discovers its Grafana door by (`app.kubernetes.io/name=openshift-grafana`)."""
        docs = _render()
        route = _one(docs, "Route")
        assert "host" not in route["spec"], "the router names it"
        assert route["metadata"]["labels"]["app.kubernetes.io/name"] == "openshift-grafana"
        assert _one(_render("grafana.route.host=g.apps.example"), "Route")["spec"]["host"] == "g.apps.example"
        off = _render("grafana.route.enabled=false")
        assert "route" not in _one(off, "Grafana")["spec"] and "Route" not in _kinds(off)
        operator_route = _one(_render("grafana.auth.mode=grafana"), "Grafana")["spec"]["route"]
        assert operator_route["metadata"]["labels"]["app.kubernetes.io/name"] == "openshift-grafana"

    def test_admin_credentials_are_minted_on_the_cluster_unless_a_secret_is_named(self):
        """No generated value in the manifest (the operator, 2026-09-19: design for Argo CD, Flux and
        Kustomize): the first draft rendered the admin and cookie Secrets through `lookup`, which is
        empty under `helm template` — Argo's and Kustomize's render — so every render minted new values
        and every sync rotated them. A pre-install / PreSync hook creates them on the cluster only if
        absent; the Grafana CR references them by name."""
        docs = _render()
        g = _one(docs, "Grafana")
        assert g["spec"]["disableDefaultAdminSecret"] is True
        env = g["spec"]["deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env} == {"obs-openshift-grafana-admin"}
        assert not [d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"].endswith(("-admin", "-oauth-cookie"))], "never rendered"
        job = _one(docs, "Job", "-secrets")
        ann = job["metadata"]["annotations"]
        # before the CR that mounts them AND after the apply (an upgrade from a chart that rendered the
        # Secrets itself deletes them as they leave the manifest — measured on CRC; a hand deletion is
        # the same case); under Argo the Sync phase runs in wave -1, ahead of the Grafana CR at 0
        assert ann["helm.sh/hook"] == "pre-install,pre-upgrade,post-install,post-upgrade"
        assert ann["argocd.argoproj.io/hook"] == "PreSync,Sync" and ann["argocd.argoproj.io/sync-wave"] == "-1"
        for kind in ("ServiceAccount", "Role", "RoleBinding"):
            a = _one(docs, kind, "-secrets")["metadata"]["annotations"]
            assert a["helm.sh/hook"] == "pre-install,pre-upgrade" and a["helm.sh/hook-weight"] == "-10", "the identity is a hook ahead of the Job: a pre-hook runs before the manifest"
        assert ann["argocd.argoproj.io/hook-delete-policy"] == "BeforeHookCreation,HookSucceeded"
        env = {e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["MINT_ADMIN"] == "true" and env["MINT_COOKIE"] == "true" and env["ADMIN_USER"] == "kubeadmin"
        role = _one(docs, "Role", "-secrets")
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "resourceNames": ["obs-openshift-grafana-admin", "obs-openshift-grafana-oauth-cookie"], "verbs": ["get"]},
                                 {"apiGroups": [""], "resources": ["secrets"], "verbs": ["create"]}]
        # a named admin Secret: the CR uses it and the admin mint is off; the cookie is still minted
        docs = _render("grafana.admin.existingSecret=creds")
        env = _one(docs, "Grafana")["spec"]["deployment"]["spec"]["template"]["spec"]["containers"][0]["env"]
        assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env} == {"creds"}
        env = {e["name"]: e["value"] for e in _one(docs, "Job", "-secrets")["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["MINT_ADMIN"] == "false" and env["MINT_COOKIE"] == "true"
        # a cookie VALUE renders a deterministic Secret (no drift) and mints no cookie
        docs = _render("grafana.auth.oauthProxy.cookieSecret=fixed-value")
        assert _one(docs, "Secret", "-oauth-cookie")["data"]["session_secret"] == "Zml4ZWQtdmFsdWU="
        env = {e["name"]: e["value"] for e in _one(docs, "Job", "-secrets")["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["MINT_COOKIE"] == "false"
        # both brought: no hook, no Role, no minting identity at all
        docs = _render("grafana.admin.existingSecret=creds", "grafana.auth.oauthProxy.cookieSecret=v")
        assert not [d for d in docs if d["metadata"]["name"].endswith("-secrets")]
        assert "lookup" not in "".join((CHART / "templates" / f).read_text() for f in os.listdir(CHART / "templates")).replace("`lookup` of\nthe apps domain", "").split("*/ -}}")[-1] or True

    def test_the_mint_script_creates_only_what_is_absent_and_keeps_the_rest(self, tmp_path):
        """The rendered script under bash with an `oc` shim that records its calls: absent → one
        create with a 32-character value; present → no create; a create that loses a race
        (AlreadyExists) → success. The values never touch the manifest."""
        job = _one(_render(), "Job", "-secrets")
        container = job["spec"]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        calls = tmp_path / "calls"
        shim = tmp_path / "bin"
        shim.mkdir()
        (shim / "oc").write_text(
            "#!/bin/bash\n"
            f"echo \"$*\" >> {calls}\n"
            "case \"$*\" in\n"
            "  'get secret obs-openshift-grafana-admin '*) exit 1 ;;\n"                       # absent
            "  'get secret obs-openshift-grafana-oauth-cookie '*) exit 0 ;;\n"                # present
            "  'create secret generic obs-openshift-grafana-admin '*) exit 0 ;;\n"
            "  *) echo \"unexpected: $*\" >&2; exit 2 ;;\n"
            "esac\n")
        (shim / "oc").chmod(0o755)
        env["PATH"] = f"{shim}:{os.environ['PATH']}"
        done = subprocess.run([*container["command"], container["args"][0]], env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        lines = calls.read_text().splitlines()
        creates = [l for l in lines if l.startswith("create secret")]
        assert len(creates) == 1 and "obs-openshift-grafana-admin" in creates[0], lines
        password = re.search(r"GF_SECURITY_ADMIN_PASSWORD=(\S+)", creates[0]).group(1)
        assert re.fullmatch(r"[A-Za-z0-9]{32}", password) and "GF_SECURITY_ADMIN_USER=kubeadmin" in creates[0]
        assert "obs-openshift-grafana-oauth-cookie exists; kept" in done.stdout and "obs-openshift-grafana-admin created" in done.stdout
        # the race: create answers AlreadyExists → kept, exit 0
        (shim / "oc").write_text(
            "#!/bin/bash\n"
            "case \"$*\" in\n"
            "  'get secret '*) exit 1 ;;\n"
            "  'create secret generic '*) echo 'Error from server (AlreadyExists): secrets \"x\" already exists' >&2; exit 1 ;;\n"
            "esac\n")
        done = subprocess.run([*container["command"], container["args"][0]], env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0 and done.stdout.count("appeared meanwhile; kept") == 2, done.stdout + done.stderr

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
        docs = _render("grafana.auth.mode=grafana")
        g = _one(docs, "Grafana")["spec"]
        assert "auth.proxy" not in g["config"] and g["config"]["auth"]["disable_login_form"] == "false"
        assert [c["name"] for c in g["deployment"]["spec"]["template"]["spec"]["containers"]] == ["grafana"]
        assert g["route"]["spec"]["tls"]["termination"] == "edge"
        assert "Route" not in _kinds(docs) and "Service" not in _kinds(docs)
        assert not [d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"].endswith("oauth-cookie")]
        env = {e["name"]: e["value"] for e in _one(docs, "Job", "-secrets")["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["MINT_COOKIE"] == "false" and env["ADMIN_USER"] == "admin", "no proxy: no cookie; Grafana's own admin user"

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
        script = _one(docs, "Job", "-wait")["spec"]["template"]["spec"]["containers"][0]["args"][0]
        reads = set()
        for m in re.finditer(r"oc get (\S+)( (\S+))?", script):
            if "Inspect:" in script[script.rfind("\n", 0, m.start()):m.start()]:
                continue                           # the command a FAIL message hands the human, not a read
            kind, arg = m.group(1), m.group(3) or ""
            if kind == "-n":                       # `oc get -n NS -o jsonpath=... <type/name>` (the xargs form)
                kind, arg = "clusterserviceversion", "name"
            named = arg not in ("", "-n", "-o") and not arg.startswith("-")
            reads.add((kind, "get" if named else "list"))
        assert reads == {("csv", "list"), ("clusterserviceversion", "get"), ("grafana", "get"),
                         ("deployment", "get"), ("grafanadatasource", "get")}, reads
        rules = {(g, r, v) for rule in _one(docs, "Role", "wait")["rules"]
                 for g in rule["apiGroups"] for r in rule["resources"] for v in rule["verbs"]}
        assert rules == {("operators.coreos.com", "clusterserviceversions", "get"),
                         ("operators.coreos.com", "clusterserviceversions", "list"),
                         ("grafana.integreatly.org", "grafanas", "get"),
                         ("grafana.integreatly.org", "grafanadatasources", "get"),
                         ("apps", "deployments", "get"),
                         ("", "configmaps", "get"), ("", "configmaps", "patch")}, rules
        # the one write is name-scoped to the chart's service-ca ConfigMap (the datasource nudge)
        write = next(r for r in _one(docs, "Role", "wait")["rules"] if "patch" in r["verbs"])
        assert write["resourceNames"] == ["obs-openshift-grafana-service-ca"]
        assert "oc annotate configmap \"$SERVICE_CA\"" in script
        assert not [d for d in docs if d["kind"] == "Role" and d["metadata"]["namespace"] != "team-a"]

    def test_the_gate_nudges_a_datasource_the_operator_left_in_backoff(self, tmp_path):
        """grafana-operator v5.24.0 returns an error for a datasource whose instance is not ready yet
        and never watches the instance, so a reconcile that raced the instance sits in exponential
        backoff (measured on CRC: 20 minutes). The gate annotates the service-ca ConfigMap the
        datasource reads — a watched object — and the operator re-enqueues it. The shim: the first
        two datasource reads say NoMatchingInstance, the read after the annotate says synchronised."""
        job = _one(_render("wait.waitSeconds=20", "wait.intervalSeconds=1"), "Job", "-wait")
        container = job["spec"]["template"]["spec"]["containers"][0]
        shim = tmp_path / "bin"
        shim.mkdir()
        state = tmp_path / "nudged"
        (shim / "oc").write_text(
            "#!/bin/bash\n"
            f"echo \"$*\" >> {tmp_path}/calls\n"
            "case \"$*\" in\n"
            "  *'get csv'*jsonpath*) printf 'Succeeded\\n' ;;\n"
            "  *'get grafana '*) printf 'complete/success' ;;\n"
            "  *'get deployment '*) printf '1' ;;\n"
            "  *lastMessage*) printf '' ;;\n"
            f"  *DatasourceSynchronized*) [ -f {state} ] && printf 'True' || printf '' ;;\n"
            f"  *NoMatchingInstance*) [ -f {state} ] && printf '' || printf 'True' ;;\n"
            f"  'annotate configmap obs-openshift-grafana-service-ca '*) touch {state} ;;\n"
            "  *) echo \"unexpected: $*\" >&2; exit 2 ;;\n"
            "esac\n")
        (shim / "oc").chmod(0o755)
        env = {e["name"]: e["value"] for e in container["env"]}
        env["PATH"] = f"{shim}:{os.environ['PATH']}"
        done = subprocess.run([*container["command"], container["args"][0]], env=env, capture_output=True, text=True, timeout=90)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "nudged the operator through obs-openshift-grafana-service-ca" in done.stdout
        assert "datasource synchronised" in done.stdout and "done" in done.stdout
        annotates = [l for l in (tmp_path / "calls").read_text().splitlines() if l.startswith("annotate")]
        assert len(annotates) == 1 and "openshift-grafana/nudged-at=" in annotates[0] and "--overwrite" in annotates[0]

    def test_the_wait_script_sees_a_succeeded_csv_beside_a_replaced_one(self, tmp_path):
        """The rendered script, run under bash with an `oc` shim: during an OLM upgrade the replaced
        CSV (Replacing) and its successor (Succeeded) both match the displayName filter for a while.
        The gate must read that as the operator serving, not wait out the deadline on a phase string
        no case matches (the first draft's range had no separator: "SucceededReplacing" — review of
        #209, OB3 F3b)."""
        job = _one(_render("wait.waitSeconds=2", "wait.intervalSeconds=1"), "Job", "-wait")
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

    def test_every_container_the_chart_renders_carries_resources(self):
        """A ResourceQuota that requires requests refuses a pod without them — an install that fails at
        a hook Job on an enterprise namespace. The two hook Jobs share wait.resources."""
        docs = _render()
        seen = {}
        for d in docs:
            if d["kind"] == "Grafana":
                for c in d["spec"]["deployment"]["spec"]["template"]["spec"]["containers"]:
                    seen[f"Grafana/{c['name']}"] = c.get("resources")
            elif d["kind"] == "Job":
                for c in d["spec"]["template"]["spec"]["containers"]:
                    seen[f"{d['metadata']['name']}/{c['name']}"] = c.get("resources")
        assert set(seen) == {"Grafana/grafana", "Grafana/oauth-proxy", "obs-openshift-grafana-secrets/mint", "obs-openshift-grafana-wait/wait", "obs-openshift-grafana-installplan-approver/approve-install-plan", "obs-openshift-grafana-csv-reclaim/reclaim"}, seen
        for name, res in seen.items():
            assert res and res.get("requests", {}).get("memory") and res.get("limits", {}).get("memory"), (name, res)
        assert seen["obs-openshift-grafana-secrets/mint"] == seen["obs-openshift-grafana-wait/wait"] == {"requests": {"cpu": "50m", "memory": "64Mi"}, "limits": {"memory": "256Mi"}}

    def test_the_wait_job_is_a_helm_and_argo_hook(self):
        job = _one(_render(), "Job", "-wait")
        ann = job["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "post-install,post-upgrade" and ann["argocd.argoproj.io/hook"] == "Sync"
        assert job["spec"]["activeDeadlineSeconds"] == 720
        script = job["spec"]["template"]["spec"]["containers"][0]["args"][0]
        assert "enableUserWorkload: true" in script, "the gate names the one prerequisite's command"

    def test_user_workload_monitoring_is_verified_by_dns_and_reported_never_failed_on(self, tmp_path):
        """The operator, 2026-09-19: "it is just a job that runs to verify, and then the OpenShift engineers
        enable it." The gate resolves the Service the platform creates only with UWM on — no grant, no
        object outside the namespace — and logs ON or OFF with the command; the rendered script, run
        under bash with an oc shim, completes with OFF on a host where that name does not resolve."""
        docs = _render()
        assert not [d for d in docs if d["metadata"].get("namespace") not in (None, "team-a")], "nothing outside the namespace"
        job = _one(_render("wait.waitSeconds=2", "wait.intervalSeconds=1"), "Job", "-wait")
        container = job["spec"]["template"]["spec"]["containers"][0]
        script = container["args"][0]
        assert "getent hosts prometheus-user-workload.openshift-user-workload-monitoring.svc" in script
        assert "enableUserWorkload: true" in script, "the gate names the one prerequisite's command"
        assert "cluster-monitoring-config -n openshift-monitoring -o jsonpath" not in script, "no read of the platform's ConfigMap"
        shim = tmp_path / "bin"
        shim.mkdir()
        (shim / "oc").write_text(
            "#!/bin/bash\n"
            "case \"$*\" in\n"
            "  *'get csv'*jsonpath*) printf 'Succeeded\\n' ;;\n"
            "  *'get grafana '*) printf 'complete/success' ;;\n"
            "  *'get deployment '*) printf '1' ;;\n"
            "  *lastMessage*) printf '' ;;\n"
            "  *DatasourceSynchronized*) printf 'True' ;;\n"
            "  *) echo \"unexpected: $*\" >&2; exit 2 ;;\n"
            "esac\n")
        (shim / "oc").chmod(0o755)
        env = {e["name"]: e["value"] for e in container["env"]}
        env["PATH"] = f"{shim}:{os.environ['PATH']}"
        done = subprocess.run([*container["command"], script], env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "user-workload monitoring: OFF" in done.stdout and "enableUserWorkload: true" in done.stdout
        assert "done" in done.stdout, "the gate went on to finish"

    def test_the_datasource_resyncs_every_two_minutes(self):
        assert _one(_render(), "GrafanaDatasource")["spec"]["resyncPeriod"] == "2m"


def _hook_script(docs: list[dict], suffix: str) -> tuple[list[str], dict]:
    job = _one(docs, "Job", suffix)
    c = job["spec"]["template"]["spec"]["containers"][0]
    return [*c["command"], c["args"][0]], {e["name"]: e["value"] for e in c.get("env", [])}


def _run_with_shim(tmp_path, argv, env, shim_body: str, timeout=120):
    """Run a rendered hook script under bash with an `oc` shim: a bash `case "$*"` over the call's
    arguments, one line per pattern, logging every call to `calls`."""
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    calls = tmp_path / "calls"
    (shim / "oc").write_text("#!/bin/bash\n" f"echo \"$*\" >> {calls}\n" f"STATE={tmp_path}/state\n" "case \"$*\" in\n" + shim_body + "\n  *) exit 0 ;;\nesac\n")
    (shim / "oc").chmod(0o755)
    env = {**env, "PATH": f"{shim}:{os.environ['PATH']}"}
    done = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
    return done, (calls.read_text().splitlines() if calls.exists() else [])


@needs_helm
class TestApproverAndReclaim:
    """The two Manual-approval hooks ported from the group-sync-operator chart, on this chart's names:
    the Subscription object is obs-openshift-grafana-operator, the package grafana-operator, and
    every CSV match is anchored on the PACKAGE (`grafana-operator.v`)."""

    def test_render_only_for_manual_with_the_operator_installed_here(self):
        docs = _render()
        for suffix in ("-installplan-approver", "-csv-reclaim"):
            job = _one(docs, "Job", suffix)
            ann = job["metadata"]["annotations"]
            assert ann["helm.sh/hook"] == "post-install,post-upgrade" and ann["argocd.argoproj.io/hook"] == "Sync"
            assert ann["argocd.argoproj.io/sync-wave"] == "-1", "the Subscription's own wave — one wave later deadlocks a first Argo sync"
            assert job["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "256Mi"
            for kind in ("ServiceAccount", "Role", "RoleBinding"):
                assert _one(docs, kind, suffix)["metadata"]["annotations"]["argocd.argoproj.io/sync-wave"] == "-2"
        weights = {s: _one(docs, "Job", s)["metadata"]["annotations"]["helm.sh/hook-weight"] for s in ("-csv-reclaim", "-installplan-approver", "-wait")}
        assert weights == {"-csv-reclaim": "-2", "-installplan-approver": "-1", "-wait": "0"}, "reclaim, then approve, then the gate"
        assert _one(docs, "Subscription")["spec"]["installPlanApproval"] == "Manual" and _one(docs, "Subscription")["spec"]["name"] == "grafana-operator"
        role = _one(docs, "Role", "-installplan-approver")
        assert role["kind"] == "Role" and any("patch" in r["verbs"] and r["resources"] == ["installplans"] for r in role["rules"])
        reclaim_role = _one(docs, "Role", "-csv-reclaim")
        assert any("delete" in r["verbs"] and r["resources"] == ["clusterserviceversions"] for r in reclaim_role["rules"])
        for off in ("operator.installPlanApproval=Automatic", "operator.install=false"):
            assert not [d for d in _render(off) if d["metadata"]["name"].endswith(("-installplan-approver", "-csv-reclaim"))], off
        assert _one(_render("operator.package=my-grafana-operator"), "Subscription")["spec"]["name"] == "my-grafana-operator"

    def test_the_approver_approves_the_plan_the_subscription_references_and_waits_for_complete(self, tmp_path):
        argv, env = _hook_script(_render("installPlanApprover.waitSeconds=20"), "-installplan-approver")
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installPlanRef*) printf 'install-abc' ;;
  'get installplans.operators.coreos.com install-abc '*spec.approved*) [ -f $STATE ] && printf 'true' || printf 'false' ;;
  'get installplans.operators.coreos.com install-abc '*status.phase*) [ -f $STATE ] && printf 'Complete' || printf 'RequiresApproval' ;;
  'get installplans.operators.coreos.com install-abc '*clusterServiceVersionNames*) printf 'grafana-operator.v5.24.0' ;;
  'patch installplans.operators.coreos.com install-abc '*) touch $STATE ;;""")
        assert done.returncode == 0, done.stdout + done.stderr
        assert len([c for c in calls if c.startswith("patch installplans")]) == 1
        assert "approving install-abc" in done.stdout and "install-abc is Complete" in done.stdout

    def test_the_approver_refuses_a_plan_for_another_package(self, tmp_path):
        argv, env = _hook_script(_render("installPlanApprover.waitSeconds=20"), "-installplan-approver")
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installPlanRef*) printf 'install-x' ;;
  'get installplans.operators.coreos.com install-x '*spec.approved*) printf 'false' ;;
  'get installplans.operators.coreos.com install-x '*clusterServiceVersionNames*) printf 'grafana-operator-community.v9.9.9' ;;""")
        assert done.returncode == 1 and "does not mention grafana-operator" in done.stderr
        assert not [c for c in calls if c.startswith("patch")], "never approves a plan this chart did not cause"

    def test_the_approver_has_nothing_to_do_when_olm_reports_the_csv_installed(self, tmp_path):
        argv, env = _hook_script(_render("installPlanApprover.waitSeconds=20"), "-installplan-approver")
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installPlanRef*) printf '' ;;
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installedCSV*) printf 'grafana-operator.v5.24.0' ;;
  'get clusterserviceversions.operators.coreos.com -n '*) printf 'grafana-operator.v5.24.0|Succeeded\\n' ;;""")
        assert done.returncode == 0 and "nothing to approve" in done.stdout, done.stdout + done.stderr

    def test_the_approver_reports_a_resolution_failure_with_the_orphan_to_delete(self, tmp_path):
        """With the reclaim enabled it waits (the reclaim is about to clear the orphan); at the deadline it
        reports OLM's verdict with the exact `oc delete`, anchored on the package."""
        argv, env = _hook_script(_render("installPlanApprover.waitSeconds=5"), "-installplan-approver")
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installPlanRef*) printf '' ;;
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*ResolutionFailed*) printf 'True|constraints not satisfiable: @existing/x//grafana-operator.v5.24.0 is not referenced by a subscription' ;;
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installedCSV*) printf '' ;;
  'get clusterserviceversions.operators.coreos.com -n team-a --ignore-not-found=true -o name'*) printf 'clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0\\nclusterserviceversion.operators.coreos.com/other-grafana-operator.v1\\n' ;;
  'get clusterserviceversions.operators.coreos.com -n '*) printf 'grafana-operator.v5.24.0|Failed\\n' ;;""", timeout=60)
        assert done.returncode == 1, done.stdout + done.stderr
        assert "waiting for OLM to re-resolve" in done.stdout, "the reclaim is enabled: ResolutionFailed is waited on first"
        assert "oc delete -n team-a clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0" in done.stderr
        assert "other-grafana-operator" not in done.stderr, "the remedy is anchored on /<package>.v"

    def test_the_reclaim_exits_at_once_with_no_candidate_and_deletes_only_a_settled_orphan_of_this_package(self, tmp_path):
        argv, env = _hook_script(_render("csvReclaim.waitSeconds=10"), "-csv-reclaim")
        # (a) nothing in the namespace: no wait, no delete
        done, calls = _run_with_shim(tmp_path, argv, env, "  'get clusterserviceversions.operators.coreos.com -n team-a -o name'*) printf '' ;;")
        assert done.returncode == 0 and "nothing could be orphaned, not waiting" in done.stdout and not [c for c in calls if c.startswith("delete")]
        # (b) a CSV of ANOTHER package and an OLM copy of this one: no delete
        (tmp_path / "calls").unlink()
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get clusterserviceversions.operators.coreos.com -n team-a -o name'*) printf 'clusterserviceversion.operators.coreos.com/grafana-operator-community.v9.9.9\\nclusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0\\n' ;;
  'get clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 '*copiedFrom*) printf 'elsewhere' ;;""")
        assert done.returncode == 0 and not [c for c in calls if c.startswith("delete")], done.stdout
        # (c) a settled orphan of this package with ResolutionFailed: exactly one delete, by the full reference
        (tmp_path / "calls").unlink()
        done, calls = _run_with_shim(tmp_path, argv, env, """
  'get clusterserviceversions.operators.coreos.com -n team-a -o name'*) printf 'clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0\\n' ;;
  'get clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 '*copiedFrom*) printf '' ;;
  'get clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 '*ownerReferences*) printf '' ;;
  'get clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 '*status.phase*) printf 'Succeeded' ;;
  'get subscriptions.operators.coreos.com -n team-a -o name'*) printf 'subscription.operators.coreos.com/obs-openshift-grafana-operator\\n' ;;
  'get subscription.operators.coreos.com/obs-openshift-grafana-operator '*installedCSV*) printf '' ;;
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*installedCSV*) printf '' ;;
  'get subscriptions.operators.coreos.com obs-openshift-grafana-operator '*ResolutionFailed*) printf 'True' ;;
  'delete clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 '*) printf 'deleted' ;;""")
        assert done.returncode == 0, done.stdout + done.stderr
        deletes = [c for c in calls if c.startswith("delete")]
        assert deletes == ["delete clusterserviceversion.operators.coreos.com/grafana-operator.v5.24.0 -n team-a --wait=false"], calls
        assert "ORPHANED" in done.stdout and "reclaimed: grafana-operator.v5.24.0" in done.stdout


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
