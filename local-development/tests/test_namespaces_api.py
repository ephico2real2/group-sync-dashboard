"""The namespace endpoints (#167): every namespace the poller sees, with its labels and the two
counts; one namespace with who reaches it, through which group, the grants naming a person, its
siblings and its history — self-scoped to the viewer's own paths, refused before any lookup.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
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
    ], now)
    s.replace_user_bindings("crc", [
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-prod", "binding_name": "dave-admin",
         "role_kind": "ClusterRole", "role_name": "admin", "user_name": "dave", "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy-payments", "binding_name": "pullers",
         "role_kind": "ClusterRole", "role_name": "system:image-puller",
         "user_name": "system:serviceaccount:legacy-payments:default", "is_platform": 1},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy-payments", "binding_name": "alice-view",
         "role_kind": "ClusterRole", "role_name": "view", "user_name": "alice", "is_platform": 0},
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
        assert (by["demo-prod"]["via_groups"], by["demo-prod"]["direct_grants"]) == (1, 1)
        assert (by["legacy-payments"]["via_groups"], by["legacy-payments"]["direct_grants"]) == (0, 1), "the platform grant is not counted"
        assert (by["quiet-ns"]["via_groups"], by["quiet-ns"]["direct_grants"]) == (0, 0), "a namespace with nothing is a result, not an absence"
        # cluster-wide bindings reach every namespace and are counted once, on the envelope
        assert body["cluster_wide_groups"] == 1 and body["cluster_wide_grants"] == 0

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
        assert body["cluster_wide_groups"] is None and body["cluster_wide_grants"] is None

    def test_the_list_counts_agree_with_each_detail(self, client):
        rows = client.get("/api/clusters/crc/namespaces", headers=ROOT).json()["namespaces"]
        for row in rows:
            d = client.get(f"/api/clusters/crc/namespaces/{row['name']}", headers=ROOT).json()
            assert len({g["group_name"] for g in d["via_groups"]}) == row["via_groups"], row["name"]
            assert len([x for x in d["direct_grants"] if not x["is_platform"]]) == row["direct_grants"], row["name"]


class TestTheDetail:
    def test_who_reaches_it_and_through_which_group(self, client):
        d = client.get("/api/clusters/crc/namespaces/demo-prod", headers=ROOT).json()
        assert d["present"] and d["scope"] == "all"
        assert [(g["group_name"], g["role_name"], g["member_count"]) for g in d["via_groups"]] == [("demo-devs", "edit", 2)]
        assert [(g["group_name"], g["role_name"]) for g in d["cluster_wide_groups"]] == [("ops-admins", "cluster-admin")]
        assert [(x["user_name"], x["role_name"], x["is_platform"]) for x in d["direct_grants"]] == [("dave", "admin", 0)]
        # alice, bob (demo-devs), carol (ops-admins, cluster-wide) and dave (direct): four people
        assert d["people"] == 4
        assert d["sibling_key"] == "company.net/mnemonic" and d["siblings"] == ["demo-qa"]
        assert "retention" in d and isinstance(d["changes"], list)

    def test_a_namespace_without_the_first_label_has_no_siblings(self, client):
        d = client.get("/api/clusters/crc/namespaces/legacy-payments", headers=ROOT).json()
        assert d["sibling_key"] is None and d["siblings"] == []
        assert [(x["user_name"], x["is_platform"]) for x in d["direct_grants"]] == [
            ("system:serviceaccount:legacy-payments:default", 1), ("alice", 0)]

    def test_a_namespace_the_store_no_longer_holds_is_a_detour_not_a_dead_end(self, client):
        d = client.get("/api/clusters/crc/namespaces/vanished-ns", headers=ROOT).json()
        assert d["present"] is False and [g["group_name"] for g in d["via_groups"]] == ["demo-devs"]

    def test_nothing_names_it_is_a_404(self, client):
        assert client.get("/api/clusters/crc/namespaces/never-heard-of", headers=ROOT).status_code == 404

    def test_the_self_tier_sees_its_own_paths_only(self, client):
        d = client.get("/api/clusters/crc/namespaces/demo-prod", headers=ALICE).json()
        assert d["scope"] == "self"
        assert [g["group_name"] for g in d["via_groups"]] == ["demo-devs"]
        assert d["cluster_wide_groups"] == [] and d["direct_grants"] == [], "other people's grants are not hers"
        assert d["people"] is None

    def test_the_self_tier_refusal_is_the_same_for_a_real_and_a_nonexistent_namespace(self, client):
        real = client.get("/api/clusters/crc/namespaces/quiet-ns", headers=ALICE)      # exists, she has no path
        fake = client.get("/api/clusters/crc/namespaces/never-heard-of", headers=ALICE)
        assert real.status_code == fake.status_code == 403
        assert real.json() == fake.json(), "a different answer would be an existence oracle"

    def test_a_cluster_wide_path_reaches_every_namespace_at_the_self_tier(self, client, db):
        # carol's only path is the cluster-wide ops-admins binding: every namespace is in her view,
        # through that binding, and nothing else
        d = client.get("/api/clusters/crc/namespaces/quiet-ns", headers={"X-Forwarded-User": "carol"}).json()
        assert d["scope"] == "self" and d["via_groups"] == []
        assert [g["group_name"] for g in d["cluster_wide_groups"]] == ["ops-admins"]
