"""The namespace endpoints (#167): every namespace the poller sees, with its labels and the two
counts; one namespace with who reaches it, through which group, the grants naming a person, its
siblings and its history — self-scoped to the viewer's own paths, refused before any lookup.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, PlatformNamespaces, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

ROOT = {"X-Forwarded-User": "root"}
ALICE = {"X-Forwarded-User": "alice"}
KEYS = ("company.net/mnemonic", "company.net/app-environment", "company.net/oud-group")


def _seed(db: str) -> None:
    s = Store(db)
    now = now_iso()
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_poll("crc", "ok", None)
    s.replace_group_state("crc", [
        {"name": "demo-devs", "member_count": 2, "sync_provider": "ldap", "group_synced_at": now, "ldap_uid": None},
        {"name": "ops-admins", "member_count": 1, "sync_provider": "ldap", "group_synced_at": now, "ldap_uid": None},
    ], now)
    s.sync_members("crc", {"demo-devs": ["alice", "bob"], "ops-admins": ["carol"]}, {}, now)
    s.replace_namespaces("crc", [
        {"name": "demo-prod", "created_at": now, "phase": "Active",
         "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}},
        {"name": "demo-qa", "created_at": now, "phase": "Active",
         "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "qa"}},
        {"name": "legacy-payments", "created_at": now, "phase": "Active", "metadata": {}},
        {"name": "quiet-ns", "created_at": now, "phase": "Active",
         "metadata": {"company.net/mnemonic": "quiet", "company.net/app-environment": "prod"}},
    ], now)
    s.replace_bindings("crc", [
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-prod", "binding_name": "devs-edit",
         "role_kind": "ClusterRole", "role_name": "edit", "group_name": "demo-devs"},
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-qa", "binding_name": "devs-edit",
         "role_kind": "ClusterRole", "role_name": "edit", "group_name": "demo-devs"},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ops-cluster-admin",
         "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": "ops-admins"},
        {"binding_kind": "RoleBinding", "binding_namespace": "vanished-ns", "binding_name": "old-rb",
         "role_kind": "ClusterRole", "role_name": "view", "group_name": "demo-devs"},
        # virtual groups: real access, no person — classified, folded, never dropped (the CRC walk of #167)
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "basic-users",
         "role_kind": "ClusterRole", "role_name": "basic-user", "group_name": "system:authenticated"},
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-prod", "binding_name": "system:image-pullers",
         "role_kind": "ClusterRole", "role_name": "system:image-puller", "group_name": "system:serviceaccounts:demo-prod"},
    ], now)
    s.replace_user_bindings("crc", [
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-prod", "binding_name": "dave-admin",
         "role_kind": "ClusterRole", "role_name": "admin", "user_name": "dave", "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy-payments", "binding_name": "pullers",
         "role_kind": "ClusterRole", "role_name": "system:image-puller",
         "user_name": "system:serviceaccount:legacy-payments:default", "is_platform": 1},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy-payments", "binding_name": "alice-view",
         "role_kind": "ClusterRole", "role_name": "view", "user_name": "alice", "is_platform": 0},
        # erin is in no group: her one path is a ClusterRoleBinding, the row the namespace page dropped
        # before the review of #167 (Grok F4) — every namespace's page must name her
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "erin-view-all",
         "role_kind": "ClusterRole", "role_name": "view", "user_name": "erin", "is_platform": 0},
    ], now)
    s.close()


class _Map:
    def __init__(self, tiers):
        self.tiers = tiers

    def resolve(self, viewer):
        return self.tiers.get(viewer, "self")


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("ns") / "gsd.db")
    _seed(path)
    return path


@pytest.fixture(scope="module")
def client(db):
    settings = Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                        db_path=db, oauth_proxy_enabled=True, namespace_metadata_labels=KEYS)
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _Map({"root": "all"})
    with TestClient(app) as c:
        yield c


class TestTheList:
    def test_every_namespace_the_poller_sees_with_labels_and_counts(self, client):
        body = client.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["scope"] == "all" and body["count"] == 4
        assert body["source"]["state"] == "ok" and body["label_keys"] == list(KEYS)
        by = {n["name"]: n for n in body["namespaces"]}
        assert by["demo-prod"]["labels"] == {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}
        assert (by["demo-prod"]["via_groups"], by["demo-prod"]["direct_grants"]) == (1, 1), \
            "demo-devs; the virtual group is bound here but is no group of people — on the page, badged, out of the count"
        assert (by["legacy-payments"]["via_groups"], by["legacy-payments"]["direct_grants"]) == (0, 1), "the platform grant is not counted"
        assert (by["quiet-ns"]["via_groups"], by["quiet-ns"]["direct_grants"]) == (0, 0), "a namespace with nothing is a result, not an absence"
        # cluster-wide bindings reach every namespace and are counted once, on the envelope
        assert body["cluster_wide_groups"] == 1 and body["cluster_wide_grants"] == 1, "ops-admins, and erin by name — system:authenticated is virtual and left out"

    def test_a_refused_namespace_read_is_reported_not_hidden(self, db, client):
        s = Store(db)
        try:
            s.mark_namespaces_unavailable("crc", now_iso())
            assert client.get("/api/clusters/crc/namespaces", headers=ROOT).json()["source"]["state"] == "forbidden"
        finally:
            s.replace_namespaces("crc", [
                {"name": "demo-prod", "created_at": None, "phase": "Active",
                 "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}},
                {"name": "demo-qa", "created_at": None, "phase": "Active",
                 "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "qa"}},
                {"name": "legacy-payments", "created_at": None, "phase": "Active", "metadata": {}},
                {"name": "quiet-ns", "created_at": None, "phase": "Active",
                 "metadata": {"company.net/mnemonic": "quiet", "company.net/app-environment": "prod"}},
            ], now_iso())
            s.close()

    def test_the_self_tier_sees_only_the_namespaces_its_own_paths_reach(self, client):
        body = client.get("/api/clusters/crc/namespaces", headers=ALICE).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        by = {n["name"]: (n["via_groups"], n["direct_grants"]) for n in body["namespaces"]}
        # demo-devs (alice's group) reaches demo-prod and demo-qa; her own binding reaches legacy-payments;
        # dave's grant on demo-prod and the platform grant are other people's and do not count
        assert by == {"demo-prod": (1, 0), "demo-qa": (1, 0), "legacy-payments": (0, 1)}
        assert (body["cluster_wide_groups"], body["cluster_wide_grants"]) == (0, 0), "her own cluster-wide paths: none"

    def test_a_cluster_wide_path_puts_every_namespace_in_the_self_tier_list(self, client):
        # carol's only path is the cluster-wide ops-admins binding. `namespace_reach` opens every namespace
        # for her (a real name 200s, a fake one 404s), so the LIST says the same — a reader whose one grant
        # is cluster-admin cannot be shown an empty list (review of #167, OB1 F2; Grok F3 named the copy)
        body = client.get("/api/clusters/crc/namespaces", headers={"X-Forwarded-User": "carol"}).json()
        assert body["scope"] == "self" and body["count"] == 4, "every namespace, through the cluster-wide binding"
        assert all((n["via_groups"], n["direct_grants"]) == (0, 0) for n in body["namespaces"]), \
            "the columns still count what is bound IN each namespace by her own paths"
        assert (body["cluster_wide_groups"], body["cluster_wide_grants"]) == (1, 0), \
            "her own cluster-wide path is reported, so the card can say why every namespace is listed"
        assert body["source"]["state"] == "ok"

    def test_the_list_counts_agree_with_each_detail(self, client):
        rows = client.get("/api/clusters/crc/namespaces", headers=ROOT).json()["namespaces"]
        for row in rows:
            d = client.get(f"/api/clusters/crc/namespaces/{row['name']}", headers=ROOT).json()
            assert len({g["group_name"] for g in d["via_groups"] if not g["is_platform"]}) == row["via_groups"], row["name"]
            assert len([x for x in d["direct_grants"] if not x["is_platform"]]) == row["direct_grants"], row["name"]


def test_a_platform_identity_cluster_wide_path_still_lists_every_namespace(tmp_path):
    """The detail's reach counts every binding naming the viewer, a platform identity's included; the
    list's switch counted only non-platform grants, so kubeadmin at the self tier opened any namespace
    and saw an empty list (review of #167, pass 2, Codex)."""
    db = str(tmp_path / "platform-viewer.db")
    now = now_iso()
    s = Store(db)
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_poll("crc", "ok", None)
    s.replace_namespaces("crc", [{"name": "one", "created_at": now, "phase": "Active", "metadata": {}},
                                 {"name": "two", "created_at": now, "phase": "Active", "metadata": {}}], now)
    s.replace_user_bindings("crc", [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "kubeadmin-ca",
                                     "role_kind": "ClusterRole", "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1}], now)
    s.close()
    app = build_app(Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                             db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})   # everyone is self
    with TestClient(app) as client:
        headers = {"X-Forwarded-User": "kubeadmin"}
        body = client.get("/api/clusters/crc/namespaces", headers=headers).json()
        detail = client.get("/api/clusters/crc/namespaces/one", headers=headers)
    assert detail.status_code == 200
    assert body["count"] == 2 and body["cluster_wide_path"] is True
    assert (body["cluster_wide_groups"], body["cluster_wide_grants"]) == (0, 0), "platform identities stay out of the counts"
    assert all((n["via_groups"], n["direct_grants"]) == (0, 0) for n in body["namespaces"])


def test_a_platform_identity_in_namespace_path_is_listed_where_the_detail_opens(tmp_path):
    """Pass 2's A made the cluster-wide half of the list follow the reach; the in-namespace half still kept a
    row only for a non-platform grant, so a platform identity whose one path is a RoleBinding in a namespace got
    an empty list while the detail opened that namespace (OB1, pass 3). The row is listed, with the review's
    counts — (0, 0), platform identities out of the count — and nothing else opens."""
    db = str(tmp_path / "platform-in-namespace.db")
    now = now_iso()
    s = Store(db)
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_poll("crc", "ok", None)
    s.replace_namespaces("crc", [{"name": "one", "created_at": now, "phase": "Active", "metadata": {}},
                                 {"name": "two", "created_at": now, "phase": "Active", "metadata": {}}], now)
    s.replace_user_bindings("crc", [{"binding_kind": "RoleBinding", "binding_namespace": "one", "binding_name": "kubeadmin-admin",
                                     "role_kind": "ClusterRole", "role_name": "admin", "user_name": "kubeadmin", "is_platform": 1}], now)
    s.close()
    app = build_app(Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                             db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})   # everyone is self
    with TestClient(app) as client:
        headers = {"X-Forwarded-User": "kubeadmin"}
        body = client.get("/api/clusters/crc/namespaces", headers=headers).json()
        one = client.get("/api/clusters/crc/namespaces/one", headers=headers)
        two = client.get("/api/clusters/crc/namespaces/two", headers=headers)
    assert (one.status_code, two.status_code) == (200, 403), "the detail's reach: the one namespace the binding names"
    assert [n["name"] for n in body["namespaces"]] == ["one"] and body["count"] == 1, "the list says the same"
    assert body["cluster_wide_path"] is False and (body["cluster_wide_groups"], body["cluster_wide_grants"]) == (0, 0)
    assert (body["namespaces"][0]["via_groups"], body["namespaces"][0]["direct_grants"]) == (0, 0), "platform identities stay out of the count"


class TestClusterWideCounts:
    """Review of #167 (Codex, OB1): the envelope's `cluster_wide_groups` says GROUPS, and every row's
    `via_groups` is COUNT(DISTINCT group_name) — the envelope must count the same thing."""

    def test_the_envelope_counts_distinct_groups_bound_cluster_wide(self, tmp_path):
        db = str(tmp_path / "cw.db")
        s = Store(db)
        now = now_iso()
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.record_poll("crc", "ok", None)
        s.replace_namespaces("crc", [{"name": "only-ns", "created_at": now, "phase": "Active", "metadata": {}}], now)
        # ONE group, TWO ClusterRoleBindings — the common cluster-admin + view pair
        s.replace_bindings("crc", [
            {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ops-cluster-admin",
             "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": "ops-admins"},
            {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ops-view",
             "role_kind": "ClusterRole", "role_name": "view", "group_name": "ops-admins"},
        ], now)
        s.close()
        settings = Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                            db_path=db, oauth_proxy_enabled=True, namespace_metadata_labels=KEYS)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        with TestClient(app) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
            d = c.get("/api/clusters/crc/namespaces/only-ns", headers=ROOT).json()
        assert len(d["cluster_wide_groups"]) == 2, "the detail lists both bindings"
        assert body["cluster_wide_groups"] == 1, "the envelope counts the group once, as every row's via_groups would"


class TestTheDetail:
    def test_who_reaches_it_and_through_which_group(self, client):
        d = client.get("/api/clusters/crc/namespaces/demo-prod", headers=ROOT).json()
        assert d["present"] and d["scope"] == "all"
        assert [(g["group_name"], g["role_name"], g["member_count"], g["is_platform"]) for g in d["via_groups"]] == [
            ("demo-devs", "edit", 2, 0), ("system:serviceaccounts:demo-prod", "system:image-puller", 0, 1)], "real groups first, the virtual one labelled"
        assert [(g["group_name"], g["role_name"], g["is_platform"]) for g in d["cluster_wide_groups"]] == [
            ("ops-admins", "cluster-admin", 0), ("system:authenticated", "basic-user", 1)]
        assert [(x["user_name"], x["role_name"], x["is_platform"]) for x in d["direct_grants"]] == [("dave", "admin", 0)]
        assert [(x["user_name"], x["role_name"]) for x in d["cluster_wide_grants"]] == [("erin", "view")]
        # alice, bob (demo-devs), carol (ops-admins, cluster-wide), dave (direct) and erin (cluster-wide by name)
        assert d["people"] == 5
        assert d["sibling_key"] == "company.net/mnemonic" and d["siblings"] == ["demo-qa"]
        assert "retention" in d and isinstance(d["changes"], list)

    def test_a_namespace_without_the_first_label_has_no_siblings(self, client):
        d = client.get("/api/clusters/crc/namespaces/legacy-payments", headers=ROOT).json()
        assert d["sibling_key"] is None and d["siblings"] == []
        # people first, platform identities last — the row a review acts on leads
        assert [(x["user_name"], x["is_platform"]) for x in d["direct_grants"]] == [
            ("alice", 0), ("system:serviceaccount:legacy-payments:default", 1)]

    def test_a_namespace_the_store_no_longer_holds_is_a_detour_not_a_dead_end(self, client):
        d = client.get("/api/clusters/crc/namespaces/vanished-ns", headers=ROOT).json()
        assert d["present"] is False and [g["group_name"] for g in d["via_groups"]] == ["demo-devs"]

    def test_nothing_names_it_is_a_404(self, client):
        assert client.get("/api/clusters/crc/namespaces/never-heard-of", headers=ROOT).status_code == 404

    def test_the_self_tier_sees_its_own_paths_only(self, client):
        d = client.get("/api/clusters/crc/namespaces/demo-prod", headers=ALICE).json()
        assert d["scope"] == "self"
        assert [g["group_name"] for g in d["via_groups"]] == ["demo-devs"]
        assert d["cluster_wide_groups"] == [] and d["direct_grants"] == [] and d["cluster_wide_grants"] == [], \
            "other people's grants are not hers"
        assert d["people"] is None

    def test_the_self_tier_refusal_is_the_same_for_a_real_and_a_nonexistent_namespace(self, client):
        real = client.get("/api/clusters/crc/namespaces/quiet-ns", headers=ALICE)      # exists, she has no path
        fake = client.get("/api/clusters/crc/namespaces/never-heard-of", headers=ALICE)
        assert real.status_code == fake.status_code == 403
        assert real.json() == fake.json(), "a different answer would be an existence oracle"

    def test_a_person_named_cluster_wide_reaches_every_namespace_on_the_page(self, client):
        # quiet-ns has no binding in it at all: the page still names carol (ops-admins, cluster-wide) and
        # erin (by name, cluster-wide), and counts both — the list's envelope counted erin once already
        d = client.get("/api/clusters/crc/namespaces/quiet-ns", headers=ROOT).json()
        assert d["via_groups"] == [] and d["direct_grants"] == [], "a cluster-wide grant is not a grant IN the namespace"
        assert [(x["user_name"], x["role_name"], x["is_platform"]) for x in d["cluster_wide_grants"]] == [("erin", "view", 0)]
        assert d["people"] == 2, "carol through ops-admins and erin by name"

    def test_a_cluster_wide_path_reaches_every_namespace_at_the_self_tier(self, client, db):
        # carol's only path is the cluster-wide ops-admins binding: every namespace is in her view,
        # through that binding, and nothing else
        d = client.get("/api/clusters/crc/namespaces/quiet-ns", headers={"X-Forwarded-User": "carol"}).json()
        assert d["scope"] == "self" and d["via_groups"] == []
        assert [g["group_name"] for g in d["cluster_wide_groups"]] == ["ops-admins"]


class TestPlatformNamespacesAreClassifiedAndCounted:
    """#257: the index listed every namespace the poller sees, and on the reference cluster 67 of
    106 were platform ones — `openshift-*`, `kube-*` and the five named — so two thirds of the
    largest section on the page was noise under a five-row worklist.

    The classification is the one `gsd/home.py` already ships and the Home page already uses; the
    point of deciding it server-side is that the page cannot drift into a second definition of
    "platform". The rows stay in the payload — export, search and the drill must still reach a
    hidden namespace — so what the envelope adds is the ability to SAY how many are hidden."""

    @staticmethod
    def _seeded(tmp_path, names: list[str], grants: list[dict] | None = None) -> TestClient:
        db = str(tmp_path / "platform.db")
        s = Store(db)
        now = now_iso()
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.record_poll("crc", "ok", None)
        s.replace_namespaces("crc", [{"name": n, "created_at": now, "phase": "Active", "metadata": {}}
                                     for n in names], now)
        if grants:
            s.replace_user_bindings("crc", grants, now)
        settings = Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                            db_path=db, oauth_proxy_enabled=True, namespace_metadata_labels=KEYS)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        return TestClient(app)

    def test_every_row_says_whether_it_is_platform_by_the_shipped_rule(self, tmp_path):
        with self._seeded(tmp_path, ["openshift-monitoring", "kube-system", "default", "openshift",
                                     "kube-public", "kube-node-lease", "demo-prod", "legacy-payments"]) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        by_name = {n["name"]: n["platform"] for n in body["namespaces"]}
        assert by_name == {
            "openshift-monitoring": True,   # prefix
            "kube-system": True,            # both a prefix and a named one
            "default": True, "openshift": True, "kube-public": True, "kube-node-lease": True,
            "demo-prod": False, "legacy-payments": False,
        }, by_name

    def test_the_envelope_counts_them_so_the_page_can_say_how_many_it_hid(self, tmp_path):
        with self._seeded(tmp_path, ["openshift-a", "kube-b", "demo-prod"]) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_count"] == 2
        assert body["count"] == 3, "the rows stay in the payload — hiding is the page's job, not a drop"
        assert len(body["namespaces"]) == 3

    def test_a_cluster_with_no_platform_namespace_counts_zero(self, tmp_path):
        """The control must have nothing to offer rather than claiming an empty filter."""
        with self._seeded(tmp_path, ["demo-prod", "legacy-payments"]) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_count"] == 0
        assert body["platform_with_findings"] == 0

    def test_a_hidden_namespace_that_holds_a_finding_is_counted_separately(self, tmp_path):
        """The one case where hiding costs the reader something. "67 hidden" is noise removed;
        "67 hidden, 1 with a direct grant" is a different sentence, and the page must be able to
        say it without the reader toggling to find out."""
        grants = [{"binding_kind": "RoleBinding", "binding_namespace": "openshift-monitoring",
                   "binding_name": "dana-edit", "role_kind": "ClusterRole", "role_name": "edit",
                   "user_name": "dana.lee", "is_platform": 0}]
        with self._seeded(tmp_path, ["openshift-monitoring", "openshift-quiet", "demo-prod"], grants) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_count"] == 2
        assert body["platform_with_findings"] == 1, body


class TestTheConfiguredRuleReachesTheIndex:
    """#255 on top of #257: the stanza is only worth having if the page uses it. Measured on the
    reference cluster, the shipped rule leaves seven infrastructure namespaces among the workloads;
    an estate that names them must see the index hide them."""

    @staticmethod
    def _client(tmp_path, platform) -> TestClient:
        db = str(tmp_path / f"cfg-{id(platform)}.db")
        s = Store(db)
        now = now_iso()
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.record_poll("crc", "ok", None)
        s.replace_namespaces("crc", [{"name": n, "created_at": now, "phase": "Active", "metadata": {}}
                                     for n in ("openshift-monitoring", "cert-manager-operator",
                                               "kyverno", "demo-prod")], now)
        settings = Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                            db_path=db, oauth_proxy_enabled=True, namespace_metadata_labels=KEYS,
                            platform_namespaces=platform)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        return TestClient(app)

    def test_the_shipped_default_still_misses_the_estates_own_platform(self, tmp_path):
        with self._client(tmp_path, PlatformNamespaces()) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_count"] == 1, "only openshift-monitoring, by prefix"
        assert {n["name"] for n in body["namespaces"] if n["platform"]} == {"openshift-monitoring"}

    def test_the_estates_own_rule_reaches_the_page(self, tmp_path):
        estate = PlatformNamespaces(additional_suffixes=("-operator",),
                                    additional_names=frozenset({"kyverno"}))
        with self._client(tmp_path, estate) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
        assert body["platform_count"] == 3
        assert {n["name"] for n in body["namespaces"] if n["platform"]} == {
            "openshift-monitoring", "cert-manager-operator", "kyverno"}
        assert {n["name"] for n in body["namespaces"] if not n["platform"]} == {"demo-prod"}, \
            "a workload must stay a workload"
