"""#174's one data addition: `binding_count` on every /groups row — the same number the group's own
detail lists, on every tier, under every state filter."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

ROOT = {"X-Forwarded-User": "root"}
ALICE = {"X-Forwarded-User": "alice"}


def _seed(db: str) -> None:
    s = Store(db)
    now = now_iso()
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_poll("crc", "ok", None)
    s.replace_group_state("crc", [
        {"name": "devs", "member_count": 2, "sync_provider": "ldap", "group_synced_at": now, "ldap_uid": None},
        {"name": "ops", "member_count": 1, "sync_provider": "ldap", "group_synced_at": now, "ldap_uid": None},
        {"name": "lonely", "member_count": 0, "sync_provider": None, "group_synced_at": None, "ldap_uid": None},
    ], now)
    s.sync_members("crc", {"devs": ["alice", "bob"], "ops": ["carol"], "lonely": []}, {}, now)
    s.replace_bindings("crc", [
        {"binding_kind": "RoleBinding", "binding_namespace": "a", "binding_name": "devs-a", "role_kind": "ClusterRole", "role_name": "edit", "group_name": "devs"},
        {"binding_kind": "RoleBinding", "binding_namespace": "b", "binding_name": "devs-b", "role_kind": "ClusterRole", "role_name": "view", "group_name": "devs"},
        # the same group bound TWICE in one namespace: two RoleBindings, one namespace — two rows, two grants
        {"binding_kind": "RoleBinding", "binding_namespace": "a", "binding_name": "devs-a-view", "role_kind": "ClusterRole", "role_name": "view", "group_name": "devs"},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ops-admin", "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": "ops"},
    ], now)
    s.close()


class _Map:
    def __init__(self, tiers):
        self.tiers = tiers

    def resolve(self, viewer):
        return self.tiers.get(viewer, "self")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("bc") / "gsd.db")
    _seed(db)
    app = build_app(Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                             db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({"root": "all"})
    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("state", ["all", "empty", "unattributed"])
def test_every_row_counts_what_its_detail_lists(client, state):
    rows = client.get(f"/api/clusters/crc/groups?state={state}", headers=ROOT).json()["groups"]
    assert rows, state
    for row in rows:
        detail = client.get(f"/api/clusters/crc/groups/{row['name']}", headers=ROOT).json()
        assert row["binding_count"] == len(detail["bindings"]), row["name"]


def test_the_counts_are_the_expected_ones(client):
    by = {r["name"]: r["binding_count"] for r in client.get("/api/clusters/crc/groups", headers=ROOT).json()["groups"]}
    assert by == {"devs": 3, "ops": 1, "lonely": 0}, "namespaced (twice in one namespace) and cluster-wide bindings both count; a group with none says 0"


def test_the_self_tier_row_carries_the_same_count(client):
    rows = client.get("/api/clusters/crc/groups", headers=ALICE).json()["groups"]
    assert [(r["name"], r["binding_count"]) for r in rows] == [("devs", 3)]
