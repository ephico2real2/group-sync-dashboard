"""The cluster-admin tier (#322, SPEC_T2): one SubjectAccessReview — `update clusterrolebindings` on the
host — gates the KPI page and the whole Cluster Configurations tab, and a reader who passes it is granted
every tier the host decides. A case per Definition-of-Done item, through the seams build_app publishes
(app.state.tier_resolver, .usage_tier_resolver, .cluster_admin_resolver, .remote_tier_resolvers), stubbed
per persona so no cluster is needed.

The personas mirror the reference cluster (SPEC_T1, "The problem, measured", and the mock cluster's SAR
oracle): `root` is cluster-admin and passes every question; `auditor` is cluster-reader — passes
`list clusterrolebindings`, the wide question, and fails `update`, this one — the NEGATIVE CONTROL of every
case; `alice` is a plain reader.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings, _cluster_admin_sar_setting
from test_visibility import H, _MapResolver, _seed, _settings

KPI = "/api/kpi"
CONFIGS = "/api/clusterconfigs"
SENTENCE = "For cluster administrators only."


class _Explodes:
    def resolve(self, viewer):
        raise RuntimeError("the API server said no such luck")


def _app(db, *, wide=None, usage=None, cluster_admin=None, **kw):
    """The three host seams stubbed apart. `None` leaves the resolver build_app made, which cannot reach
    the configured cluster and fails closed — the live shape of "the check did not come back"."""
    _seed(db)
    app = build_app(_settings(db, **kw), run_poller=False)
    app.state.tier_resolver = _MapResolver(wide or {})
    app.state.usage_tier_resolver = _MapResolver(usage or {})
    if cluster_admin is not None:
        app.state.cluster_admin_resolver = cluster_admin
    return app


def _writes(c, who):
    body = {"name": "west", "server": "https://api.west.example:6443",
            "credential": {"kind": "bearerToken", "token": "sha256~a-long-enough-token"}}
    return [c.post(CONFIGS, json=body, headers=H(who)),
            c.put(f"{CONFIGS}/east/credential", json={"token": "t"}, headers=H(who)),
            c.delete(f"{CONFIGS}/east", headers=H(who)),
            c.post(f"{CONFIGS}/test", json=body, headers=H(who))]


class TestTheFourSurfaces:
    """Each surface the issue names, and the negative control on each: a cluster-reader passes the wide
    question and is refused."""

    @pytest.fixture
    def client(self, tmp_path):
        app = _app(str(tmp_path / "gsd.db"), wide={"root": "all", "auditor": "all"},
                   cluster_admin=_MapResolver({"root": "all"}), cluster_secrets_writes_enabled=True)
        with TestClient(app) as c:
            yield c

    def test_the_kpi_page_is_the_tier_and_a_cluster_reader_is_refused(self, client):
        assert client.get("/api/clusters/c1/groups", headers=H("auditor")).json()["scope"] == "all"   # wide, as measured
        refused = client.get(KPI, headers=H("auditor"))
        assert refused.status_code == 403
        assert refused.json()["detail"].startswith(SENTENCE)
        assert client.get(KPI, headers=H("root")).status_code == 200
        assert client.get(KPI, headers=H("alice")).status_code == 403

    def test_the_cluster_configurations_view_is_the_tier_and_a_cluster_reader_is_refused(self, client):
        refused = client.get(CONFIGS, headers=H("auditor"))
        assert refused.status_code == 403 and refused.json()["detail"].startswith(SENTENCE)
        body = client.get(CONFIGS, headers=H("root")).json()
        assert body["scope"] == "all" and body["can"] == {"view": True, "manage": True}

    def test_the_cluster_configurations_writes_are_the_tier_and_a_cluster_reader_is_refused(self, client):
        assert [r.status_code for r in _writes(client, "auditor")] == [403, 403, 403, 403]
        assert all(r.json()["detail"].startswith(SENTENCE) for r in _writes(client, "auditor"))
        # root reaches the writer (the test probe fails on the made-up server, which is past the gate)
        assert all(r.status_code != 403 for r in _writes(client, "root"))

    def test_whoami_withholds_both_tabs_from_a_cluster_reader(self, client):
        auditor = client.get("/api/whoami", headers=H("auditor")).json()["visibility"]
        assert auditor["scope"] == "all" and auditor["cluster_admin"] is False
        root = client.get("/api/whoami", headers=H("root")).json()["visibility"]
        assert root["scope"] == "all" and root["cluster_admin"] is True
        assert "clusterconfig" not in client.get("/api/whoami", headers=H("root")).json()

    def test_the_refusal_names_no_role_grant_value_or_route(self, client):
        for path in (KPI, CONFIGS):
            detail = client.get(path, headers=H("auditor")).json()["detail"]
            for word in ("cluster-admin", "clusterrolebindings", "clusterAdminSar", "update", "/api", "c1", "secrets"):
                assert word not in detail, (path, word)

    def test_the_mutant_reverting_a_route_to_the_wide_tier_admits_the_auditor(self, client):
        """The kill: everyone here passes the wide tier, so `require_admin_tier` on either route answers 200."""
        for path in (KPI, CONFIGS):
            assert client.get(path, headers=H("auditor")).status_code == 403, path


class TestTheHierarchy:
    """The top tier grants every host-decided tier, one way only; per-cluster policies still apply."""

    @pytest.fixture
    def rig(self, tmp_path):
        """The wide and Usage stubs deny EVERYONE — the case the issue names: adminSar and usageAdminSar
        pointed at checks the cluster-admin fails. Only clusterAdminSar admits root."""
        db = str(tmp_path / "gsd.db"); _seed(db)
        token = tmp_path / "token"; token.write_bytes(b"t" * 48 + b"\n")
        settings = Settings(
            clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X"),
                      ClusterConfig("c2", "https://api.c2.example.com:6443", token_env="Y", visibility="inherit"),
                      ClusterConfig("far", "https://api.far.example.com:6443", token_env="Z"),          # remote-sar, by default
                      ClusterConfig("solo", "https://api.solo.example.com:6443", token_env="W",
                                    visibility="self-only", identity="same-as-host")],
            # A report service configured, so /api/dashboard/reports reaches usage_scope rather than
            # answering its reporting-off `self` before any tier is asked.
            db_path=db, oauth_proxy_enabled=True, reporting_url="https://gsd-report.ns.svc:8443",
            reporting_token_file=str(token))
        app = build_app(settings, run_poller=False)
        wide, usage, far = _MapResolver({}), _MapResolver({}), _MapResolver({})
        app.state.tier_resolver = wide
        app.state.usage_tier_resolver = usage
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        app.state.remote_tier_resolvers = {"far": far}
        with TestClient(app) as c:
            yield c, wide, usage, far

    def test_a_cluster_admin_is_wide_on_the_host_and_on_inherit_clusters(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/c1/groups", headers=H("root")).json()["scope"] == "all"
        assert c.get("/api/clusters/c2/groups", headers=H("root")).json()["scope"] == "all"
        who = c.get("/api/whoami", headers=H("root")).json()["visibility"]
        assert who["scope"] == "all" and who["clusters"]["c1"]["scope"] == "all" and who["clusters"]["c2"]["scope"] == "all"
        assert wide.calls == 0, "the wide question is never asked of a cluster-admin"

    def test_a_cluster_admin_is_wide_on_usage_whatever_the_usage_question_answers(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/dashboard/activity", headers=H("root")).json()["scope"] == "all"
        assert c.get("/api/dashboard/reports", headers=H("root")).json()["scope"] == "all"
        assert usage.calls == 0, "the Usage question is never asked of a cluster-admin"

    def test_a_remote_sar_cluster_still_asks_its_own_api(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/far/groups", headers=H("root")).json()["scope"] == "self"
        assert far.calls >= 1, "the remote decided, not the host's top tier"
        assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["clusters"]["far"]["scope"] == "self"

    def test_a_self_only_cluster_stays_self(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/solo/groups", headers=H("root")).json()["scope"] == "self"
        assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["clusters"]["solo"]["scope"] == "self"

    def test_it_works_one_way_only(self, tmp_path):
        """Wide by adminSar, self on Usage by usageAdminSar, and refused the tier: passing the two lower
        questions implies nothing about this one."""
        app = _app(str(tmp_path / "one-way.db"), wide={"auditor": "all"}, usage={"auditor": "all"},
                   cluster_admin=_MapResolver({}))
        with TestClient(app) as c:
            assert c.get("/api/clusters/c1/groups", headers=H("auditor")).json()["scope"] == "all"
            assert c.get("/api/dashboard/activity", headers=H("auditor")).json()["scope"] == "all"
            assert c.get(KPI, headers=H("auditor")).status_code == 403
            assert c.get(CONFIGS, headers=H("auditor")).status_code == 403
            assert c.get("/api/whoami", headers=H("auditor")).json()["visibility"]["cluster_admin"] is False

    def test_a_plain_reader_stays_self_everywhere(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/c1/groups", headers=H("alice")).json()["scope"] == "self"
        assert c.get("/api/dashboard/activity", headers=H("alice")).json()["scope"] == "self"
        assert c.get(KPI, headers=H("alice")).status_code == 403


class TestFailClosed:
    def test_visibility_off_still_asks_the_tier(self, tmp_path):
        """`visibility.enabled: false` widens the wide views by design; it must not hand KPI or the
        fleet's wiring to every proxy-admitted reader (the issue: "for KPI this is a change"), and a
        cluster-admin keeps Usage through the tier."""
        app = _app(str(tmp_path / "off.db"), cluster_admin=_MapResolver({"root": "all"}),
                   view_restrictions_enabled=False)
        with TestClient(app) as c:
            for who in ("auditor", "alice"):
                assert c.get("/api/clusters/c1/groups", headers=H(who)).json()["scope"] == "all"   # restrictions off
                assert c.get(KPI, headers=H(who)).status_code == 403
                assert c.get(CONFIGS, headers=H(who)).status_code == 403
                assert c.get("/api/dashboard/activity", headers=H(who)).json()["scope"] == "self"
                assert c.get("/api/whoami", headers=H(who)).json()["visibility"]["cluster_admin"] is False
            assert c.get(KPI, headers=H("root")).status_code == 200
            assert c.get(CONFIGS, headers=H("root")).status_code == 200
            assert c.get("/api/dashboard/activity", headers=H("root")).json()["scope"] == "all"
            assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["cluster_admin"] is True

    def test_with_the_proxy_off_there_is_no_one_to_ask_about(self, tmp_path):
        app = _app(str(tmp_path / "noproxy.db"), cluster_admin=_MapResolver({"root": "all"}),
                   oauth_proxy_enabled=False, view_restrictions_enabled=False)
        with TestClient(app) as c:
            assert c.get(KPI, headers=H("root")).status_code == 403
            assert c.get(CONFIGS, headers=H("root")).status_code == 403

    @pytest.mark.parametrize("stub", [None, _Explodes(), _MapResolver({"root": "ALL"}), _MapResolver({"root": "yes"})],
                             ids=["no-resolver", "raises", "miscased", "junk"])
    def test_an_indeterminate_answer_refuses(self, tmp_path, stub):
        app = _app(str(tmp_path / "ind.db"), wide={"root": "all"}, cluster_admin=stub)
        with TestClient(app) as c:
            assert c.get(KPI, headers=H("root")).status_code == 403
            assert c.get(CONFIGS, headers=H("root")).status_code == 403
            assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["cluster_admin"] is False

    def test_no_identity_refuses(self, tmp_path):
        app = _app(str(tmp_path / "anon.db"), cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            assert c.get(KPI).status_code == 403
            assert c.get(CONFIGS).status_code == 403


class TestTheResolverAndItsSetting:
    def test_build_app_makes_one_resolver_apart_from_the_wide_switch_and_the_usage_cache(self, tmp_path):
        db = str(tmp_path / "gsd.db"); _seed(db)
        for restrictions in (True, False):
            app = build_app(_settings(db, view_restrictions_enabled=restrictions), run_poller=False)
            r = app.state.cluster_admin_resolver
            assert r is not None, f"restrictions={restrictions}: the tier is asked in both states"
            assert r._attributes == {"verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
        on = build_app(_settings(db), run_poller=False)
        assert on.state.cluster_admin_resolver is not on.state.usage_tier_resolver
        assert on.state.cluster_admin_resolver._cache is not on.state.usage_tier_resolver._cache
        assert on.state.cluster_admin_resolver._kube.cluster.name == "c1", "asked on the host"

    def test_the_default_is_the_usage_question_as_its_own_setting(self):
        """The mock cluster's oracle (mock-app/tests/test_sar_personas.py, `USAGE`) answers this exact
        question `no` for `dana.lee` (cluster-reader) and `yes` for `kubeadmin` — the negative control
        at the SAR itself."""
        s = Settings(clusters=())
        assert {"verb": s.visibility_cluster_admin_sar_verb, "resource": s.visibility_cluster_admin_sar_resource,
                "group": s.visibility_cluster_admin_sar_api_group} == {
            "verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
        assert (s.visibility_usage_admin_sar_verb, s.visibility_usage_admin_sar_resource) == ("update", "clusterrolebindings")
        assert s.visibility_cluster_admin_sar_namespace == "" == s.visibility_cluster_admin_sar_subresource

    def test_the_configmap_keys_parse_whole_or_default(self):
        custom = {"visibilityClusterAdminSarApiGroup": "example.io", "visibilityClusterAdminSarResource": "fleets/admin",
                  "visibilityClusterAdminSarVerb": "approve", "visibilityClusterAdminSarNamespace": "ops"}
        assert _cluster_admin_sar_setting(custom) == ("example.io", "fleets", "admin", "approve", "ops")
        assert _cluster_admin_sar_setting({}) == ("rbac.authorization.k8s.io", "clusterrolebindings", "", "update", "")
        # one unusable field takes the WHOLE default, never half a custom question
        assert _cluster_admin_sar_setting({**custom, "visibilityClusterAdminSarVerb": "Approve"}) == (
            "rbac.authorization.k8s.io", "clusterrolebindings", "", "update", "")

    def test_the_threshold_label_is_pre_seeded_and_counts_the_tier(self, tmp_path):
        app = _app(str(tmp_path / "m.db"), cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            before = c.get("/metrics").text
            assert 'gsd_visibility_decisions_total{threshold="cluster_admin",tier="all"} 0.0' in before
            assert "clusterconfig_view" not in before and "clusterconfig_manage" not in before
            c.get(KPI, headers=H("root"))
            after = c.get("/metrics").text
            assert 'gsd_visibility_decisions_total{threshold="cluster_admin",tier="all"} 1.0' in after


def test_cluster_configuration_help_describes_the_single_tier(tmp_path):
    """The shipped page must not advertise the removed view/manage authorization split."""
    app = _app(str(tmp_path / "copy.db"), cluster_admin=_MapResolver({"root": "all"}))
    with TestClient(app) as client:
        response = client.get("/", headers=H("root"))
        assert response.status_code == 200
        html = response.text
    assert "clusterconfig:view" not in html
    assert "clusterconfig:manage" not in html
    assert "Only cluster administrators see this page." in html
