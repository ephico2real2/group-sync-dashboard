"""The Kyverno policy module (#165, #170): the reader, the store, the API, the metrics, the poller.

The shapes here are the lab's (docs/design/kyverno-discovery-2026-09-20.md): reports named by the
resource's UID and labelled `managed-by` only; a result's `source` telling the family — `kyverno` for the
deprecated one, `KyvernoValidatingPolicy` for CEL — and `rule` empty for CEL; `kyverno_breaker_total`
served, `kyverno_breaker_drops` absent until a drop.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd.api import build_app
from gsd.kube import FORBIDDEN, ClusterClient, ClusterError
from gsd.kpi import Context
from gsd.kpi.render_prom import render as render_prom
from gsd.kyverno import CEL_KINDS, CONTROLLED_KINDS
from gsd.kyverno.definitions import KYVERNO_KPIS
from gsd.kyverno.reader import BreakerView, KyvernoRead, PolicyView, ResultView, parse_breaker, read, result_views
from gsd.poller import refresh_bindings
from gsd.store import Store
from test_visibility import H, _MapResolver, _seed, _settings

NOW = "2026-09-20T12:00:00Z"


def _text(store, clusters) -> str:
    """The module's families as a scrape would print them."""
    from prometheus_client import CollectorRegistry
    families = list(render_prom(KYVERNO_KPIS, Context(component="dashboard", store=store, cluster_ids=tuple(clusters))))

    class _C:
        def collect(self): return families
    reg = CollectorRegistry(); reg.register(_C())
    return generate_latest(reg).decode()


def _report(kind, name, results, *, namespace=None, managed=True, uid="0000"):
    meta = {"name": uid, "labels": {"app.kubernetes.io/managed-by": "kyverno"} if managed else {}}
    if namespace:
        meta["namespace"] = namespace
    scope = {"apiVersion": "v1", "kind": kind, "name": name, "uid": uid}
    if namespace:
        scope["namespace"] = namespace
    return {"apiVersion": "wgpolicyk8s.io/v1alpha2", "kind": "ClusterPolicyReport", "metadata": meta, "scope": scope,
            "results": results}


def _result(policy, result, *, source="KyvernoValidatingPolicy", rule=None, process="admission review", message="m", seconds=1789901502):
    return {"policy": policy, "result": result, "source": source, "rule": rule, "message": message, "severity": "high",
            "category": "Multi-Tenancy", "scored": True, "properties": {"process": process}, "timestamp": {"seconds": seconds, "nanos": 0}}


class _FakeClient(ClusterClient):
    """The ClusterClient with its HTTP layer replaced by a path table: a path missing from the table is a 404
    (the message shape `_get` produces), a path mapped to FORBIDDEN raises the 403 outcome."""

    def __init__(self, table: dict, name="c1"):
        from gsd.config import ClusterConfig
        super().__init__(ClusterConfig(name, "https://api.example:6443", token_env="X"))
        self.table = table
        self.calls: list[str] = []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _client(self):
        return self._Ctx()

    def _get(self, client, path, params):
        self.calls.append(path)
        if path not in self.table:
            raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")
        if self.table[path] is FORBIDDEN:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {path} — the ServiceAccount lacks list permission here")
        return self.table[path]

    def _list_all(self, client, path):
        payload = self._get(client, path, {})
        return list(payload.get("items") or [])


def _policy(name, *, background=False, actions=("Audit",), ready=True):
    return {"metadata": {"name": name}, "spec": {"evaluation": {"admission": {"enabled": True}, "background": {"enabled": background}},
                                                 "validationActions": list(actions), "failurePolicy": "Fail"},
            "status": {"conditions": [{"type": "Ready", "status": "True" if ready else "False"}]}}


def _lab_table(*, openreports=False):
    """A cluster shaped like the lab: one ValidatingPolicy, reports carrying both families, and no VAP."""
    base = "/apis/openreports.io/v1alpha1" if openreports else "/apis/wgpolicyk8s.io/v1alpha2"
    cluster_col, ns_col = ("clusterreports", "reports") if openreports else ("clusterpolicyreports", "policyreports")
    reports = [
        _report("Namespace", "openshift-controller-manager", [
            _result("namespace-oud-group-allowlist", "skip", source="kyverno", rule="validate-oud-group-known-family", process="background scan"),
            _result("rbac-standards-enforcement", "fail", source="kyverno", rule="require-rbac-labels", process="background scan"),
        ], uid="u1"),
        _report("GroupConfig", "custom-cluster-rbac", [_result("restrict-nco-config-writers", "pass")], uid="u2"),
        _report("NamespaceConfig", "baseline-prod-rbac", [_result("restrict-nco-config-writers", "fail", message="refused for x")], uid="u3"),
        _report("Pod", "web-1", [_result("restrict-nco-config-writers", "warn")], namespace="apps", uid="u4"),
        _report("ConfigMap", "stray", [_result("restrict-nco-config-writers", "pass")], managed=False, uid="u5"),
        _report("Deployment", "odd", [_result("some-policy", "fail", source="KyvernoOtherKind")], uid="u6"),
    ]
    return {
        base: {"kind": "APIResourceList"},
        f"{base}/{cluster_col}": {"items": reports[:3] + reports[4:]},
        f"{base}/{ns_col}": {"items": [reports[3]]},
        "/apis/policies.kyverno.io/v1/validatingpolicies": {"items": [_policy("restrict-nco-config-writers")]},
    }


class TestReader:
    def test_result_views_key_by_policy_and_resource_and_tell_the_family_by_source(self):
        views, legacy, other = result_views(_lab_table()["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"]["items"][0])
        assert views == [] and legacy == 2 and other == 0                      # the deprecated family: counted, never a row
        views, legacy, other = result_views(_report("Pod", "p", [_result("p1", "warn")], namespace="ns"))
        assert legacy == 0 and other == 0 and views[0].policy_kind == "ValidatingPolicy" and views[0].controlled is True
        assert views[0].resource_namespace == "ns" and views[0].at == 1789901502
        views, _, other = result_views(_report("Deployment", "d", [_result("p", "fail", source="KyvernoOtherKind")]))
        assert other == 1 and views[0].policy_kind == "other"                    # an unknown CEL source is kept, never dropped
        bad = result_views(_report("Deployment", "d", [_result("p", "unexpected")]))[0][0]
        assert bad.result == "error"                                            # a word outside the vocabulary is an error, not a pass
        # a generated admission policy's rows are the policy's own (discovery §3): the source names the VAP, the
        # policy carries the vpol- prefix, and the row lands under the ValidatingPolicy, prefix stripped
        gen = result_views(_report("ConfigMap", "c", [_result("vpol-require-owner", "fail", source="ValidatingAdmissionPolicy")], namespace="ns"))[0][0]
        assert (gen.policy_kind, gen.policy, gen.resource_uid) == ("ValidatingPolicy", "require-owner", "0000")
        assert result_views(_report("X", "x", [_result("p", "pass", source="KyvernoDeletingPolicy")]))[2] == 1, "no such source in v1.19.1: other, never dropped"

    def test_parse_breaker_reads_total_and_treats_an_absent_drops_family_as_unobserved(self):
        scrape = ('# HELP kyverno_breaker_total track number of times the breaker was invoked\n'
                  'kyverno_breaker_total{circuit_name="background scan reports",otel_scope_name="kyverno"} 3949\n'
                  'kyverno_policy_results_total{policy_name="x"} 3\n')
        assert parse_breaker(scrape) == BreakerView(total=3949, drops=None)
        assert parse_breaker(scrape + 'kyverno_breaker_drops{circuit_name="background scan reports"} 12\n') == BreakerView(total=3949, drops=12)
        # every circuit counts — there are three, one per controller, each a report breaker (discovery §4)
        assert parse_breaker('kyverno_breaker_total{circuit_name="admission reports"} 5\n') == BreakerView(total=5, drops=None)
        both = parse_breaker(scrape); parse_breaker('kyverno_breaker_drops{circuit_name="admission reports"} 2\n', both)
        assert both == BreakerView(total=3949, drops=2)                     # accumulated across endpoints

    def test_read_discovers_the_group_lists_every_kind_and_filters_by_label_and_source(self):
        client = _FakeClient(_lab_table())
        out = read(client)
        assert out.api_group == "wgpolicyk8s.io/v1alpha2" and out.policy_kinds_served == ("ValidatingPolicy",)
        assert [p.name for p in out.policies] == ["restrict-nco-config-writers"]
        assert out.policies[0].background is False and out.policies[0].actions == ("Audit",) and out.policies[0].ready is True
        assert out.reports == 5, "the unmanaged report is not Kyverno's"
        assert out.legacy_results == 2 and out.other_results == 1
        assert sorted((r.resource_kind, r.result) for r in out.results) == [("Deployment", "fail"), ("GroupConfig", "pass"), ("NamespaceConfig", "fail"), ("Pod", "warn")]
        # every CEL kind was asked for; the four the cluster lacks answered 404 and are simply absent
        assert sum(1 for c in client.calls if "/apis/policies.kyverno.io/v1/" in c) == len(CEL_KINDS)
        assert out.breaker is None

    def test_read_prefers_openreports_when_served_and_answers_none_when_neither_is(self):
        out = read(_FakeClient(_lab_table(openreports=True)))
        assert out.api_group == "openreports.io/v1alpha1" and out.reports == 5
        assert read(_FakeClient({"/apis/policies.kyverno.io/v1/validatingpolicies": {"items": []}})) is None

    def test_a_refused_report_list_is_the_forbidden_outcome_not_an_empty_answer(self):
        table = _lab_table(); table["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"] = FORBIDDEN
        with pytest.raises(ClusterError) as exc:
            read(_FakeClient(table))
        assert exc.value.outcome == FORBIDDEN


class TestStore:
    def _store(self, tmp_path):
        s = Store(str(tmp_path / "k.db")); s.upsert_cluster("c1", "https://x", True); return s

    def test_replace_records_presence_results_and_the_transitions_between_polls(self, tmp_path):
        s = self._store(tmp_path)
        assert s.kyverno_summary("c1") == {"present": None}                     # never looked
        first = read(_FakeClient(_lab_table()))
        assert s.replace_kyverno("c1", first, NOW) == {"appeared": 0, "cleared": 0}, "the first observation is a baseline, not a burst"
        summary = s.kyverno_summary("c1")
        assert summary["present"] is True and summary["legacy_results"] == 2 and summary["reports"] == 5
        assert summary["results"] == {"pass": 1, "fail": 2, "warn": 1, "error": 0, "skip": 0} and summary["policies"] == 1
        rows, total = s.kyverno_results("c1")
        assert total == 3 and [r["result"] for r in rows] == ["fail", "fail", "warn"]
        rows, total = s.kyverno_results("c1", include_controlled=False)
        assert total == 2 and all(not r["controlled"] for r in rows)
        # the next poll: the NamespaceConfig conforms, the Pod's report is gone with its Pod, a new failure appears
        table = _lab_table()
        table["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"]["items"][2]["results"][0]["result"] = "pass"
        table["/apis/wgpolicyk8s.io/v1alpha2/policyreports"]["items"] = []
        table["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"]["items"].append(
            _report("GroupSync", "gs-1", [_result("restrict-nco-config-writers", "fail", message="new")], namespace="group-sync-operator", uid="u7"))
        assert s.replace_kyverno("c1", read(_FakeClient(table)), "2026-09-20T12:05:00Z") == {"appeared": 1, "cleared": 2}
        events = s.kyverno_events("c1")
        assert {(e["change"], e["resource_kind"]) for e in events} == {("appeared", "GroupSync"), ("cleared", "NamespaceConfig"), ("cleared", "Pod")}
        assert s.history_retained_since("c1")["kyverno_result_event"] == "2026-09-20T12:05:00Z"
        assert s.prune_kyverno_events("c1", "2026-09-20T12:06:00Z") == 3
        # not installed: looked, absent — present False, every row gone
        s.replace_kyverno("c1", None, "2026-09-20T12:10:00Z")
        assert s.kyverno_summary("c1")["present"] is False and s.kyverno_policies("c1") == []

    def test_the_worse_result_keeps_the_row_when_two_reports_name_one_policy_and_resource(self, tmp_path):
        s = self._store(tmp_path)
        r = KyvernoRead(api_group="x", results=[
            ResultView("ValidatingPolicy", "p", "Namespace", "", "n", "u1", "v1", "pass", "", "", "", "admission review", 1, False),
            ResultView("ValidatingPolicy", "p", "Namespace", "", "n", "u1", "v1", "fail", "", "", "bad", "background scan", 2, False)])
        s.replace_kyverno("c1", r, NOW)
        rows, total = s.kyverno_results("c1", problems_only=False)
        assert total == 1 and rows[0]["result"] == "fail" and rows[0]["message"] == "bad"


class TestPoller:
    def test_the_binding_refresh_records_the_module_and_stays_inert_when_switched_off_or_absent(self, tmp_path, monkeypatch):
        s = Store(str(tmp_path / "p.db"))
        from gsd.config import ClusterConfig
        cluster = ClusterConfig("c1", "https://api.example:6443", token_env="X")
        s.upsert_cluster("c1", cluster.api_url, True)
        table = _lab_table()
        calls = {"n": 0}

        class _Client(_FakeClient):
            def __init__(self, cfg, timeout=15.0):
                super().__init__(table, cfg.name)
            def fetch(self): return [], []
            def fetch_user_bindings(self): return []
            def fetch_namespaces(self, label_keys=None): return None
            def fetch_bindings(self): return []
            def fetch_operator_configs(self): return None
            def fetch_users(self): return None
            def fetch_identities(self): return None
            def fetch_access_group_dn(self): return None
            def fetch_oauth_providers(self): return None
            def fetch_kyverno(self, metrics_url=""):
                calls["n"] += 1
                return super().fetch_kyverno(metrics_url)
        monkeypatch.setattr("gsd.poller.ClusterClient", _Client)
        refresh_bindings(s, cluster, 15.0, kyverno=False)
        assert calls["n"] == 0 and s.kyverno_summary("c1") == {"present": None}, "off means no read at all"
        refresh_bindings(s, cluster, 15.0, kyverno=True)
        assert calls["n"] == 1 and s.kyverno_summary("c1")["present"] is True
        table.clear()                                                                  # Kyverno uninstalled
        refresh_bindings(s, cluster, 15.0, kyverno=True)
        assert s.kyverno_summary("c1")["present"] is False
        # a refused read leaves the previous state and says so, like the operator configs
        table.update(_lab_table()); refresh_bindings(s, cluster, 15.0, kyverno=True)
        table["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"] = FORBIDDEN
        refresh_bindings(s, cluster, 15.0, kyverno=True)
        assert s.kyverno_summary("c1")["present"] is True


class TestApiAndMetrics:
    @pytest.fixture
    def client(self, tmp_path):
        db = str(tmp_path / "gsd.db"); _seed(db)
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            yield c, app.state.store

    def test_the_three_states_and_the_administrator_tier(self, client):
        c, store = client
        assert c.get("/api/clusters/c1/kyverno", headers=H("alice")).status_code == 403
        never = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
        assert never["present"] is None and never["enabled"] is True and "rows" not in never
        store.replace_kyverno("c1", None, NOW)
        absent = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
        assert absent["present"] is False and "rows" not in absent
        store.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
        body = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
        assert body["present"] is True and body["legacy_results"] == 2 and body["breaker_drops"] is None
        assert body["total"] == 2 and sorted(r["resource_kind"] for r in body["rows"]) == ["Deployment", "NamespaceConfig"]   # controlled off by default
        assert body["controlled_kinds"] == list(CONTROLLED_KINDS)
        assert c.get("/api/clusters/c1/kyverno?controlled=true", headers=H("root")).json()["total"] == 3
        assert c.get("/api/clusters/c1/kyverno?problems=false&limit=1", headers=H("root")).json()["truncated"] is True
        assert c.get("/api/clusters/c1/kyverno?policy=restrict-nco-config-writers", headers=H("root")).json()["total"] == 1
        assert [p["name"] for p in body["policies_list"]] == ["restrict-nco-config-writers"] and body["policies_list"][0]["results"]["pass"] == 1

    def test_no_metric_label_can_carry_a_resource_name_or_namespace(self, client):
        c, store = client
        store.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
        for k in KYVERNO_KPIS:
            assert k.privacy == "public" and set(k.labels) <= {"cluster", "kind", "policy_kind", "result"}, k.name
        text = _text(store, ("c1", "c2"))
        assert 'gsd_kyverno_results{cluster="c1",policy_kind="ValidatingPolicy",result="fail"} 1.0' in text
        assert 'gsd_kyverno_legacy_results{cluster="c1"} 2.0' in text
        assert "gsd_kyverno_report_breaker_drops{" not in text, "no drop observed: the family is absent, never 0"
        assert 'cluster="c2"' not in text, "a cluster where nothing was found emits nothing"
        for name in ("restrict-nco-config-writers", "baseline-prod-rbac", "apps", "web-1"):
            assert name not in text, f"{name!r} — a name in a public metric"

    def test_a_dashboard_with_no_report_api_served_emits_no_family_at_all(self, client):
        c, store = client
        store.replace_kyverno("c1", None, NOW)
        text = _text(store, ("c1",))
        assert not re.search(r"^gsd_kyverno_\w+\{", text, re.M), text
