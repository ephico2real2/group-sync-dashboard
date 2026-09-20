"""The Kyverno policy module (#165, #170): the reader, the store, the API, the metrics, the poller.

The shapes here are the lab's (docs/design/kyverno-discovery-2026-09-20.md): reports named by the
resource's UID and labelled `managed-by` only; a result's `source` telling the family — `kyverno` for the
deprecated one, `KyvernoValidatingPolicy` for CEL — and `rule` empty for CEL; `kyverno_breaker_total`
served, `kyverno_breaker_drops` absent until a drop.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd.api import build_app
from gsd.kube import FORBIDDEN, PAGE_SIZE, UNREACHABLE, ClusterClient, ClusterError
from gsd.kpi import Context
from gsd.kpi.render_prom import render as render_prom
from gsd.kyverno import CEL_KINDS, CONTROLLED_KINDS
from gsd.kyverno.definitions import KYVERNO_KPIS, _results
from gsd.kyverno.reader import BreakerView, KyvernoRead, PolicyView, ResultView, parse_breaker, policy_view, read, result_views
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
            # the shape the lab gives (`oc get validatingpolicies … -o json | jq .status`, 2026-09-20): readiness lives in
            # `conditionStatus`; `message` there is the VAP-generation note, not a readiness note
            "status": {"conditionStatus": {"ready": ready, "message": "skip generating ValidatingAdmissionPolicy: not enabled.",
                                           "conditions": [{"type": "WebhookConfigured", "status": "True", "message": "Webhook configured."}]},
                       "generated": False}}


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
        # every CEL kind was asked for — the cluster collection and its namespaced twin; the ones the cluster
        # lacks answered 404 and are simply absent
        assert sum(1 for c in client.calls if "/apis/policies.kyverno.io/v1/" in c) == 2 * len(CEL_KINDS)
        assert out.breaker is None

    def test_read_lists_a_namespaced_twin_as_the_family_kind_and_joins_its_rows(self):
        # 09-19 §5: a NamespacedValidatingPolicy in klt-pass-both writes `source: KyvernoValidatingPolicy` with the
        # policy namespace-qualified. The first cut listed the five cluster collections only (review of #228,
        # Grok and Codex): a cluster using namespaced policies alone read "policies: 0" beside its rows.
        table = _lab_table()
        table["/apis/policies.kyverno.io/v1/namespacedvalidatingpolicies"] = {"items": [
            {**_policy("require-owner"), "metadata": {"name": "require-owner", "namespace": "klt-pass-both"}}]}
        table["/apis/wgpolicyk8s.io/v1alpha2/policyreports"]["items"].append(
            _report("ConfigMap", "cm-1", [_result("klt-pass-both/require-owner", "fail")], namespace="klt-pass-both", uid="u9"))
        out = read(_FakeClient(table))
        assert out.policy_kinds_served == ("ValidatingPolicy",), "the twin is the family's kind, listed once"
        assert sorted((p.kind, p.namespace or "", p.name) for p in out.policies) == [
            ("ValidatingPolicy", "", "restrict-nco-config-writers"), ("ValidatingPolicy", "klt-pass-both", "require-owner")]
        import tempfile, os
        s = Store(os.path.join(tempfile.mkdtemp(), "n.db")); s.upsert_cluster("c1", "https://x", True)
        s.replace_kyverno("c1", out, NOW)
        joined = {p["policy"]: p["results"]["fail"] for p in s.kyverno_policies("c1")}
        assert joined["klt-pass-both/require-owner"] == 1, joined

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
        # a ValidatingPolicy and a MutatingPolicy may share a name: `kind` with `policy` names one (Codex)
        r = read(_FakeClient(_lab_table()))
        r.results.append(ResultView("MutatingPolicy", "restrict-nco-config-writers", "Namespace", "", "n", "u8", "v1", "fail", "", "", "", "admission review", 1, False))
        store.replace_kyverno("c1", r, NOW)
        assert c.get("/api/clusters/c1/kyverno?policy=restrict-nco-config-writers", headers=H("root")).json()["total"] == 2
        assert c.get("/api/clusters/c1/kyverno?policy=restrict-nco-config-writers&kind=MutatingPolicy", headers=H("root")).json()["total"] == 1
        assert [p["name"] for p in body["policies_list"]] == ["restrict-nco-config-writers"] and body["policies_list"][0]["results"]["pass"] == 1

    def test_no_metric_label_can_carry_a_resource_name_or_namespace(self, client):
        c, store = client
        store.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
        for k in KYVERNO_KPIS:
            assert k.privacy == "public" and set(k.labels) <= {"cluster", "kind", "policy_kind", "result"}, k.name
        text = _text(store, ("c1", "c2"))
        assert 'gsd_kyverno_results{cluster="c1",policy_kind="ValidatingPolicy",result="fail"} 1.0' in text
        assert store.kyverno_result_counts("c1") == {("ValidatingPolicy", "pass"): 1, ("ValidatingPolicy", "fail"): 1,
                                                    ("ValidatingPolicy", "warn"): 1, ("other", "fail"): 1}   # one aggregate per scrape, never the rows
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


# ══ OB3's review of #228 (docs/REVIEW_kyverno_module.md) — the harness that measured M2–M6/M10 and the pin behind each
# fix, kept as they were written: each F-test failed on 0989e4b and passes with its fix. ═══════════════════════════════

# ── M2: discovery and paging ────────────────────────────────────────────────────────────────────

class _RaisingClient(_FakeClient):
    """A path mapped to a ClusterError instance raises it as-is (a 503, a non-JSON body...)."""

    def _get(self, client, path, params):
        self.calls.append((path, dict(params or {})))
        v = self.table.get(path)
        if isinstance(v, ClusterError):
            raise v
        return super()._get(client, path, params)


def test_m2_a_non_404_on_the_discovery_get_is_raised_never_read_as_absent():
    table = _lab_table()
    table["/apis/openreports.io/v1alpha1"] = ClusterError(UNREACHABLE, "HTTP 503 on /apis/openreports.io/v1alpha1: apiserver overloaded")
    with pytest.raises(ClusterError) as exc:
        read(_RaisingClient(table))
    assert exc.value.outcome == UNREACHABLE and "503" in exc.value.message


def test_m2_a_403_on_one_policy_kind_is_raised_not_skipped():
    table = _lab_table()
    table["/apis/policies.kyverno.io/v1/mutatingpolicies"] = FORBIDDEN
    with pytest.raises(ClusterError) as exc:
        read(_FakeClient(table))
    assert exc.value.outcome == FORBIDDEN


def test_m2_a_403_on_the_namespaced_report_collection_is_raised():
    table = _lab_table()
    table["/apis/wgpolicyk8s.io/v1alpha2/policyreports"] = FORBIDDEN
    with pytest.raises(ClusterError) as exc:
        read(_FakeClient(table))
    assert exc.value.outcome == FORBIDDEN


class _PagingClient(ClusterClient):
    """The REAL _list_all over a fake _get that hands out continue tokens: proves every LIST pages."""

    def __init__(self, table, pages: dict[str, list[list[dict]]]):
        from gsd.config import ClusterConfig
        super().__init__(ClusterConfig("c1", "https://api.example:6443", token_env="X"))
        self.table, self.pages, self.calls = table, pages, []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _client(self): return self._Ctx()

    def _get(self, client, path, params):
        self.calls.append((path, dict(params or {})))
        if path in self.pages:
            chunks = self.pages[path]
            i = int(params.get("continue") or 0)
            meta = {"continue": str(i + 1)} if i + 1 < len(chunks) else {}
            return {"kind": "List", "items": chunks[i], "metadata": meta}
        if path not in self.table:
            raise ClusterError(UNREACHABLE, f"HTTP 404 on {path}: not found")
        return self.table[path]


def test_m2_every_list_follows_continue_tokens_with_the_real_list_all():
    base = "/apis/wgpolicyk8s.io/v1alpha2"
    reports = [_report("Namespace", f"ns-{i}", [_result("p", "fail")], uid=f"u{i}") for i in range(7)]
    pages = {f"{base}/clusterpolicyreports": [reports[:3], reports[3:6], reports[6:]],
             f"{base}/policyreports": [[], []],
             "/apis/policies.kyverno.io/v1/validatingpolicies": [[_policy("a")], [_policy("b")]]}
    client = _PagingClient({base: {"kind": "APIResourceList"}}, pages)
    out = read(client)
    assert out.reports == 7 and len(out.results) == 7 and [p.name for p in out.policies] == ["a", "b"]
    lists = [(p, q) for p, q in client.calls if "limit" in q]
    assert all(q["limit"] == PAGE_SIZE for _, q in lists)
    assert [q.get("continue") for p, q in lists if p.endswith("/clusterpolicyreports")] == [None, "1", "2"]
    assert [q.get("continue") for p, q in lists if p.endswith("/validatingpolicies")] == [None, "1"]
    # the discovery GETs: openreports first (404 here), then wgpolicy — one call each, no params
    assert client.calls[:2] == [("/apis/openreports.io/v1alpha1", {}), (base, {})] and client.calls.count((base, {})) == 1


def test_m2_a_served_but_empty_openreports_group_masks_the_wgpolicy_reports():
    """RISK: both groups served (the openreports CRDs installed by another tool, Kyverno still writing
    wgpolicyk8s.io because --openreportsEnabled=false): the reader picks the first that answers and
    reads an empty group — 'installed, 0 reports, 0 results' on a cluster carrying 115 reports."""
    table = _lab_table()
    table["/apis/openreports.io/v1alpha1"] = {"kind": "APIResourceList"}
    table["/apis/openreports.io/v1alpha1/clusterreports"] = {"items": []}
    table["/apis/openreports.io/v1alpha1/reports"] = {"items": []}
    out = read(_FakeClient(table))
    assert out.reports == 5 and len(out.results) == 4, f"api_group={out.api_group} reports={out.reports}"


# ── M3: the store ───────────────────────────────────────────────────────────────────────────────

def _store(tmp_path):
    s = Store(str(tmp_path / "k.db")); s.upsert_cluster("c1", "https://x", True); return s


def _rv(policy, uid, result, *, kind="Namespace", name="n", pk="ValidatingPolicy", ns=""):
    return ResultView(pk, policy, kind, ns, name, uid, "v1", result, "", "", "msg", "background scan", 1, kind in ("Pod", "ReplicaSet", "Job"))


def test_m3_a_recreated_resource_is_a_cleared_and_an_appeared_never_a_silent_carry_over(tmp_path):
    s = _store(tmp_path)
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "uid-old", "fail", name="web")]), NOW)
    stats = s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "uid-new", "fail", name="web")]), "2026-09-20T12:05:00Z")
    assert stats == {"appeared": 1, "cleared": 1}
    ev = s.kyverno_events("c1")
    assert [(e["change"], e["resource_name"]) for e in ev] == [("appeared", "web"), ("cleared", "web")] or \
           [(e["change"], e["resource_name"]) for e in ev] == [("cleared", "web"), ("appeared", "web")]


def test_m3_a_policy_renamed_and_a_report_moving_collections(tmp_path):
    s = _store(tmp_path)
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("old-name", "u1", "fail")]), NOW)
    assert s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("new-name", "u1", "fail")]), "2026-09-20T12:05:00Z") == {"appeared": 1, "cleared": 1}
    # the collection a report sits in is not part of the key: the same (policy, uid) is no transition
    assert s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("new-name", "u1", "fail", ns="moved")]), "2026-09-20T12:10:00Z") == {"appeared": 0, "cleared": 0}


def test_m3_a_worsening_warn_to_fail_records_nothing(tmp_path):
    """Observation, not a claim in the brief: warn→fail on one key is neither appeared nor cleared."""
    s = _store(tmp_path)
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "warn")]), NOW)
    assert s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail")]), "2026-09-20T12:05:00Z") == {"appeared": 0, "cleared": 0}


def test_m3_the_worse_result_rule_with_every_pair(tmp_path):
    s = _store(tmp_path)
    order = ["error", "fail", "warn", "pass", "skip"]
    for i, a in enumerate(order):
        for b in order[i:]:
            for first, second in ((a, b), (b, a)):
                s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u", first), _rv("p", "u", second)]), NOW)
                rows, total = s.kyverno_results("c1", problems_only=False)
                assert total == 1 and rows[0]["result"] == a, (first, second, rows[0]["result"])


def test_m3_absent_then_present_again_is_a_fresh_baseline(tmp_path):
    s = _store(tmp_path)
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail")]), NOW)
    s.replace_kyverno("c1", None, "2026-09-20T12:05:00Z")
    assert s.kyverno_summary("c1")["present"] is False and s.kyverno_results("c1", problems_only=False)[1] == 0
    assert s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail")]), "2026-09-20T12:10:00Z") == {"appeared": 0, "cleared": 0}


def test_m3_replace_is_one_transaction(tmp_path):
    s = _store(tmp_path)
    first = read(_FakeClient(_lab_table()))
    s.replace_kyverno("c1", first, NOW)
    before = (s.kyverno_summary("c1"), s.kyverno_policies("c1"), s.kyverno_results("c1", problems_only=False))

    class Boom(Exception): ...

    class _Explodes(list):
        """Iterated AFTER the presence upsert and the policy DELETE have run (the executemany rows are built then)."""
        def __iter__(self): raise Boom("mid-transaction failure")
    bad = KyvernoRead("g2", policies=_Explodes(), results=[_rv("p", "u2", "fail")], reports=9, legacy_results=0)
    with pytest.raises(Boom):
        s.replace_kyverno("c1", bad, "2026-09-20T12:05:00Z")
    after = (s.kyverno_summary("c1"), s.kyverno_policies("c1"), s.kyverno_results("c1", problems_only=False))
    assert after == before, "state moved although the write failed half-way: not one transaction"


def test_m3_query_plans_are_index_seeks(tmp_path):
    s = _store(tmp_path)
    s.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
    conn = s._conn
    plans = {
        "results/problems": ("SELECT * FROM kyverno_result WHERE cluster_id=? AND result IN ('fail','warn','error') ORDER BY CASE result WHEN 'error' THEN 0 ELSE 4 END, policy LIMIT 500", ("c1",)),
        "results/policy": ("SELECT COUNT(*) FROM kyverno_result WHERE cluster_id=? AND policy=?", ("c1", "p")),
        "policies/per-policy counts": ("SELECT result, COUNT(*) FROM kyverno_result WHERE cluster_id=? AND policy_kind=? AND policy=? GROUP BY result", ("c1", "ValidatingPolicy", "p")),
        "summary/counts": ("SELECT result, COUNT(*) FROM kyverno_result WHERE cluster_id=? GROUP BY result", ("c1",)),
        "events": ("SELECT * FROM kyverno_result_event WHERE cluster_id=? ORDER BY observed_at DESC, id DESC LIMIT 200", ("c1",)),
        "prune": ("SELECT id FROM kyverno_result_event WHERE cluster_id=? AND observed_at < ? ORDER BY observed_at LIMIT 5000", ("c1", "x")),
        "retained_since": ("SELECT MIN(observed_at) FROM kyverno_result_event WHERE cluster_id=?", ("c1",)),
        "presence": ("SELECT * FROM kyverno_presence WHERE cluster_id=?", ("c1",)),
    }
    for name, (sql, params) in plans.items():
        plan = " | ".join(r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params))
        print(f"PLAN {name:28s} {plan}")
        assert "SCAN kyverno_result " not in plan + " " and "SCAN kyverno_result_event" not in plan and "SCAN kyverno_presence" not in plan, (name, plan)


# ── M5: the API ────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path):
    db = str(tmp_path / "gsd.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        yield c, app.state.store


def test_m5_events_newest_first_and_truncated_iff_rows_lt_total(client):
    c, store = client
    store.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail")]), NOW)
    store.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail"), _rv("p", "u2", "fail")]), "2026-09-20T12:05:00Z")
    store.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u2", "fail")]), "2026-09-20T12:10:00Z")
    body = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
    assert [(e["observed_at"], e["change"]) for e in body["events"]] == [("2026-09-20T12:10:00Z", "cleared"), ("2026-09-20T12:05:00Z", "appeared")]
    assert body["total"] == 1 and body["truncated"] is False
    body = c.get("/api/clusters/c1/kyverno?limit=1&controlled=true&problems=false", headers=H("root")).json()
    assert body["total"] == 1 and len(body["rows"]) == 1 and body["truncated"] is False
    store.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail"), _rv("p", "u2", "fail")]), "2026-09-20T12:15:00Z")
    body = c.get("/api/clusters/c1/kyverno?limit=1", headers=H("root")).json()
    assert body["total"] == 2 and len(body["rows"]) == 1 and body["truncated"] is True


def test_m5_self_tier_gets_403_with_no_names_and_a_namespaced_policy_string_is_accepted(client):
    c, store = client
    store.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
    r = c.get("/api/clusters/c1/kyverno", headers=H("alice"))
    assert r.status_code == 403 and "restrict-nco" not in r.text and "baseline-prod" not in r.text
    r = c.get("/api/clusters/c1/kyverno?policy=" + "n" * 63 + "/" + "p" * 253, headers=H("root"))
    print("namespaced wire string of 317 chars ->", r.status_code)
    assert r.status_code == 200, "a namespaced policy's wire string can be 63+1+253 chars; max_length=253 refuses it"


def test_m5_the_switched_off_payload_says_enabled_false(tmp_path):
    db = str(tmp_path / "gsd.db"); _seed(db)
    app = build_app(_settings(db, kyverno_enabled=False), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        body = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
    assert body["enabled"] is False and body["present"] is None


# ── M6: the metrics ────────────────────────────────────────────────────────────────────────────

def _prom_text(store, clusters):
    from prometheus_client import CollectorRegistry, generate_latest
    fams = list(render_prom(KYVERNO_KPIS, Context(component="dashboard", store=store, cluster_ids=tuple(clusters))))

    class _C:
        def collect(self): return fams
    reg = CollectorRegistry(); reg.register(_C())
    return generate_latest(reg).decode()


def test_m6_every_kind_x_result_is_preseeded_and_breaker_drops_only_when_read(tmp_path):
    s = _store(tmp_path)
    from gsd.kyverno.reader import BreakerView
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail")], breaker=BreakerView(total=10, drops=None)), NOW)
    text = _prom_text(s, ("c1",))
    combos = [l for l in text.splitlines() if l.startswith("gsd_kyverno_results{")]
    assert len(combos) == 6 * 5, len(combos)
    assert 'gsd_kyverno_results{cluster="c1",policy_kind="DeletingPolicy",result="skip"} 0.0' in text
    assert "gsd_kyverno_report_breaker_drops" not in "\n".join(l for l in text.splitlines() if not l.startswith("#"))
    s.replace_kyverno("c1", KyvernoRead("g", results=[], breaker=BreakerView(total=10, drops=0)), NOW)
    assert 'gsd_kyverno_report_breaker_drops{cluster="c1"} 0.0' in _prom_text(s, ("c1",)), "a READ zero is emitted"
    s.replace_kyverno("c1", KyvernoRead("g", results=[], breaker=None), NOW)
    assert "gsd_kyverno_report_breaker_drops{" not in _prom_text(s, ("c1",)), "not scraped: absent"
    # the switched-off / never-polled cluster emits nothing
    assert 'cluster="c2"' not in _prom_text(s, ("c1", "c2"))



# ── M10 (d): the breaker is the SUM over the three endpoints, and one failed endpoint is "unknown" ──

def test_m10_the_breaker_sums_every_endpoint_and_a_failed_one_makes_the_cycle_unknown(monkeypatch):
    import httpx

    class _R:
        def __init__(self, text): self.text = text
        def raise_for_status(self): pass
    scrapes = {"http://a/metrics": 'kyverno_breaker_total{circuit_name="admission reports"} 5\n',
               "http://b/metrics": 'kyverno_breaker_total{circuit_name="background scan reports"} 7\nkyverno_breaker_drops{circuit_name="background scan reports"} 2\n',
               "http://c/metrics": 'kyverno_breaker_total{circuit_name="background-scan reports"} 1\nkyverno_breaker_drops{circuit_name="background-scan reports"} 3\n'}
    monkeypatch.setattr(httpx, "get", lambda url, timeout: _R(scrapes[url]))
    out = read(_FakeClient(_lab_table()), "http://a/metrics,http://b/metrics http://c/metrics")
    assert (out.breaker.total, out.breaker.drops) == (13, 5), out.breaker

    def flaky(url, timeout):
        if url == "http://b/metrics":
            raise httpx.ConnectError("refused")
        return _R(scrapes[url])
    monkeypatch.setattr(httpx, "get", flaky)
    assert read(_FakeClient(_lab_table()), "http://a/metrics,http://b/metrics,http://c/metrics").breaker is None, "one endpoint down: unknown, not a partial sum"


REPO = Path(__file__).resolve().parents[2]




# F1 ────────────────────────────────────────────────────────────────────────────────────────────
def test_f1_both_served_groups_are_read_and_api_group_names_the_one_that_carried_reports():
    table = _lab_table()
    table["/apis/openreports.io/v1alpha1"] = {"kind": "APIResourceList"}
    table["/apis/openreports.io/v1alpha1/clusterreports"] = {"items": []}
    table["/apis/openreports.io/v1alpha1/reports"] = {"items": []}
    out = read(_FakeClient(table))
    assert out.reports == 5 and len(out.results) == 4 and out.legacy_results == 2
    assert out.api_group == "wgpolicyk8s.io/v1alpha2", "the group Kyverno wrote to, not the first served"
    # openreports carrying the reports: read from there, wgpolicy empty
    table = _lab_table(openreports=True)
    table["/apis/wgpolicyk8s.io/v1alpha2"] = {"kind": "APIResourceList"}
    table["/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports"] = {"items": []}
    table["/apis/wgpolicyk8s.io/v1alpha2/policyreports"] = {"items": []}
    out = read(_FakeClient(table))
    assert out.reports == 5 and out.api_group == "openreports.io/v1alpha1"
    # neither carrying anything yet: the first served is named, and it is still "installed"
    table = {"/apis/wgpolicyk8s.io/v1alpha2": {"kind": "APIResourceList"},
             "/apis/wgpolicyk8s.io/v1alpha2/clusterpolicyreports": {"items": []}, "/apis/wgpolicyk8s.io/v1alpha2/policyreports": {"items": []}}
    out = read(_FakeClient(table))
    assert out is not None and out.reports == 0 and out.api_group == "wgpolicyk8s.io/v1alpha2"


# F2 ────────────────────────────────────────────────────────────────────────────────────────────
def _ns_policy(ns, name):
    p = _policy(name); p["metadata"]["namespace"] = ns; return p


def test_f2_a_namespaced_twin_is_listed_under_its_family_kind_and_joined_by_namespace_slash_name(tmp_path):
    """The 09-19 record measured a NamespacedValidatingPolicy writing source KyvernoValidatingPolicy with
    policy `klt-pass-both/step0-probe-require-owner` (results.go:97, MetaNamespaceKeyFunc)."""
    table = _lab_table()
    table["/apis/policies.kyverno.io/v1/namespacedvalidatingpolicies"] = {"items": [_ns_policy("klt-pass-both", "step0-probe-require-owner")]}
    table["/apis/wgpolicyk8s.io/v1alpha2/policyreports"]["items"].append(
        _report("ConfigMap", "cm-1", [_result("klt-pass-both/step0-probe-require-owner", "fail")], namespace="klt-pass-both", uid="u9"))
    out = read(_FakeClient(table))
    twins = [p for p in out.policies if p.namespace]
    assert [(p.kind, p.namespace, p.name) for p in twins] == [("ValidatingPolicy", "klt-pass-both", "step0-probe-require-owner")]
    assert out.policy_kinds_served == ("ValidatingPolicy",)
    s = Store(str(tmp_path / "k.db")); s.upsert_cluster("c1", "https://x", True)
    s.replace_kyverno("c1", out, NOW)
    joined = next(p for p in s.kyverno_policies("c1") if p["namespace"])
    assert joined["policy"] == "klt-pass-both/step0-probe-require-owner" and joined["results"]["fail"] == 1


def test_f2_the_api_accepts_a_namespaced_wire_string_of_317_chars(tmp_path):
    db = str(tmp_path / "gsd.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False); app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        app.state.store.replace_kyverno("c1", read(_FakeClient(_lab_table())), NOW)
        assert c.get("/api/clusters/c1/kyverno?policy=" + "n" * 63 + "/" + "p" * 253, headers=H("root")).status_code == 200
        assert c.get("/api/clusters/c1/kyverno?policy=" + "p" * 318, headers=H("root")).status_code == 422


# F3 ────────────────────────────────────────────────────────────────────────────────────────────
def test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release():
    log = (REPO / "docs" / "CHANGELOG.md").read_text()
    chart = re.search(r"^version: (\d+\.\d+\.\d+)", (REPO / "charts/group-sync-dashboard/Chart.yaml").read_text(), re.M).group(1)
    headings = [l for l in log.splitlines() if l.startswith("## ")]
    if headings[0] != "## Unreleased":
        pytest.skip("no Unreleased section")
    released = re.search(r"chart (\d+\.\d+\.\d+)", headings[1]).group(1)
    unreleased = log.split("\n## Unreleased\n", 1)[1].split("\n## ", 1)[0]   # the heading LINE, not the intro's mention of it
    if chart != released:
        assert f"chart {chart}" in unreleased, f"Chart.yaml is {chart} (last released {released}) and no Unreleased entry names it"


# F4 ────────────────────────────────────────────────────────────────────────────────────────────
def test_f4_the_breaker_url_is_scraped_for_the_host_cluster_only(tmp_path, monkeypatch):
    from gsd.config import ClusterConfig
    from gsd.poller import kyverno_metrics_url_for
    s = Store(str(tmp_path / "p.db"))
    host, remote = ClusterConfig("host", "https://api.host:6443", token_env="X"), ClusterConfig("remote", "https://api.remote:6443", token_env="Y")
    for c in (host, remote):
        s.upsert_cluster(c.name, c.api_url, True)
    seen: dict[str, str] = {}

    class _Client(_FakeClient):
        def __init__(self, cfg, timeout=15.0):
            super().__init__(_lab_table(), cfg.name)
        def fetch_bindings(self): return []
        def fetch_user_bindings(self): return []
        def fetch_operator_configs(self): return None
        def fetch_kyverno(self, metrics_url=""):
            seen[self.cluster.name] = metrics_url
            return KyvernoRead("wgpolicyk8s.io/v1alpha2")
    monkeypatch.setattr("gsd.poller.ClusterClient", _Client)
    settings = _settings(str(tmp_path / "gsd.db"), kyverno_metrics_url="http://kyverno-reports-controller-metrics.kyverno.svc:8000/metrics")
    settings.clusters[:] = [host, remote]
    for c in (host, remote):
        refresh_bindings(s, c, 15.0, kyverno=True, kyverno_metrics_url=kyverno_metrics_url_for(settings, c))
    assert seen == {"host": settings.kyverno_metrics_url, "remote": ""}, seen


# F6 ────────────────────────────────────────────────────────────────────────────────────────────
def _lab_policy(ready=True, conditions=None, message="skip generating ValidatingAdmissionPolicy: not enabled."):
    """The shape the lab writes (oc get validatingpolicies -o json, 2026-09-20): status.conditionStatus only."""
    return {"metadata": {"name": "restrict-nco-config-writers"},
            "spec": {"evaluation": {"admission": {"enabled": True}, "background": {"enabled": False}}, "validationActions": ["Audit"], "failurePolicy": "Fail"},
            "status": {"autogen": {}, "generated": False,
                       "conditionStatus": {"ready": ready, "message": message, "conditions": conditions if conditions is not None else [
                           {"type": "WebhookConfigured", "status": "True", "reason": "Succeeded", "message": "Webhook configured."},
                           {"type": "RBACPermissionsGranted", "status": "True", "reason": "Succeeded", "message": "Background scanning disabled; reporting permissions not required."}]}}}


def test_f6_the_note_is_a_failing_condition_never_the_vap_generation_message():
    ok = policy_view("ValidatingPolicy", _lab_policy())
    assert ok.ready is True and ok.note == "", "the VAP-generation message is not a readiness note (the CRD: 'details about the generation of ValidatingAdmissionPolicy')"
    gap = policy_view("ValidatingPolicy", _lab_policy(ready=False, conditions=[
        {"type": "WebhookConfigured", "status": "True", "reason": "Succeeded", "message": "Webhook configured."},
        {"type": "RBACPermissionsGranted", "status": "False", "reason": "Failed",
         "message": "reports-controller is missing RBAC to list/watch groups.user.openshift.io — grant it via reportsController.rbac.clusterRole.extraResources"}]))
    assert gap.ready is False
    assert gap.note.startswith("RBACPermissionsGranted: reports-controller is missing RBAC"), gap.note
    # not ready with no failing condition: the top-level message is the only word there is
    stuck = policy_view("ValidatingPolicy", _lab_policy(ready=False, conditions=[], message="failed to generate ValidatingAdmissionPolicy: x"))
    assert stuck.note == "failed to generate ValidatingAdmissionPolicy: x"


# F7 ────────────────────────────────────────────────────────────────────────────────────────────
def test_f7_the_payload_says_whether_a_breaker_scrape_is_configured(tmp_path):
    db = str(tmp_path / "gsd.db"); _seed(db)
    for url, expect in (("", False), ("http://kyverno-reports-controller-metrics.kyverno.svc:8000/metrics", True)):
        app = build_app(_settings(db, kyverno_metrics_url=url), run_poller=False); app.state.tier_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            app.state.store.replace_kyverno("c1", KyvernoRead("g", results=[], breaker=None), NOW)
            body = c.get("/api/clusters/c1/kyverno", headers=H("root")).json()
            assert body["breaker_configured"] is expect and body["breaker_total"] is None, body


# F8 ────────────────────────────────────────────────────────────────────────────────────────────
def test_f8_the_results_family_does_not_materialise_the_rows(tmp_path, monkeypatch):
    s = Store(str(tmp_path / "k.db")); s.upsert_cluster("c1", "https://x", True)
    s.replace_kyverno("c1", KyvernoRead("g", results=[_rv("p", "u1", "fail"), _rv("p", "u2", "pass", pk="other")]), NOW)

    def refuse(*a, **k): raise AssertionError("kyverno_results() called from the metrics collector")
    monkeypatch.setattr(s, "kyverno_results", refuse)
    samples = _results(Context(component="dashboard", store=s, cluster_ids=("c1",)))
    assert len(samples) == 30
    assert {tuple(x.labels): x.value for x in samples}[("c1", "ValidatingPolicy", "fail")] == 1
    assert {tuple(x.labels): x.value for x in samples}[("c1", "other", "pass")] == 1
