"""A full poll_once + refresh_bindings + TierResolver cycle against the mock (DESIGN §8.1).

Drives the poller's real entry points over real TLS into a real Store, then resolves each
persona's tier through the real TierResolver — the deepest integration the mock enables.
"""

from __future__ import annotations

import pytest

from gsd.kube import TIER_ALL, TIER_SELF, TierResolver
from gsd.poller import poll_once, refresh_bindings
from gsd.store import Store


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "gsd.db"))
    s.upsert_cluster("mock", "https://placeholder", True)
    return s


def test_poll_once_persists_the_reference_rows(mock_cluster, store):
    # "ok" is satisfied by valid-but-empty responses (review #118 C5); assert the rows actually landed.
    cfg = mock_cluster.cluster_config(name="mock")
    assert poll_once(store, cfg, timeout=5.0, identities_read=True) == "ok"
    assert store.groupsync_present("mock") is True
    assert [g["name"] for g in store.groupsyncs("mock")] == ["ldap-sync"]
    assert {g["name"] for g in store.groups("mock")} == {
        "app-ocp-rbac-demo-cluster-admin", "cluster-readers", "platform-team-cluster-admin",
        "acme-app-viewers", "empty-team", "legacy-ops"}
    assert [m["user_name"] for m in store.group_members("mock", "app-ocp-rbac-demo-cluster-admin")] == ["kubeadmin"]
    assert {u["user_name"] for u in store.users("mock")} == {"kubeadmin", "dana.lee", "lateef.o", "jane.smith"}


def test_refresh_bindings_persists_the_feeds(mock_cluster, store):
    cfg = mock_cluster.cluster_config(name="mock")
    assert poll_once(store, cfg, timeout=5.0) == "ok"
    assert refresh_bindings(store, cfg, timeout=5.0, namespaces_read=True,
                            namespace_metadata_labels=["team"]) == "ok"
    assert "app-ocp-rbac-demo-cluster-admin" in {row["group_name"] for row in store.all_bindings("mock")}
    assert store.namespaces_source("mock")["state"] == "ok"
    assert store.operator_configs("mock")["present"] is True


def _resolver(cfg, verb: str) -> TierResolver:
    return TierResolver(
        cfg, verb=verb, resource="clusterrolebindings",
        api_group="rbac.authorization.k8s.io", namespace="", subresource="",
        ttl_seconds=60.0,
    )


@pytest.mark.parametrize("persona,wide,usage", [
    ("kubeadmin", TIER_ALL, TIER_ALL),
    ("dana.lee", TIER_ALL, TIER_SELF),
    ("lateef.o", TIER_SELF, TIER_SELF),
    ("jane.smith", TIER_SELF, TIER_SELF),
])
def test_tier_resolver_personas(mock_cluster, persona, wide, usage):
    cfg = mock_cluster.cluster_config(name="mock")
    assert _resolver(cfg, "list").tier_for(persona) == wide
    assert _resolver(cfg, "update").tier_for(persona) == usage


def test_tier_resolver_fails_closed_on_no_viewer(mock_cluster):
    cfg = mock_cluster.cluster_config(name="mock")
    assert _resolver(cfg, "list").tier_for(None) == TIER_SELF
