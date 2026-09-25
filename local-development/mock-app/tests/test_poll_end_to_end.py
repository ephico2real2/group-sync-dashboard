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
        "acme-app-viewers", "empty-team", "legacy-ops", "app-ocp-rbac-demo-report-auditors"}
    assert [m["user_name"] for m in store.group_members("mock", "app-ocp-rbac-demo-cluster-admin")] == ["kubeadmin"]
    assert {u["user_name"] for u in store.users("mock")} == {"kubeadmin", "dana.lee", "lateef.o", "jane.smith", "developer"}


def test_refresh_bindings_persists_the_feeds(mock_cluster, store):
    cfg = mock_cluster.cluster_config(name="mock")
    assert poll_once(store, cfg, timeout=5.0) == "ok"
    assert refresh_bindings(store, cfg, timeout=5.0, namespaces_read=True,
                            namespace_metadata_labels=["team"]) == "ok"
    assert "app-ocp-rbac-demo-cluster-admin" in {row["group_name"] for row in store.all_bindings("mock")}
    assert store.namespaces_source("mock")["state"] == "ok"
    assert store.operator_configs("mock")["present"] is True


def test_refresh_bindings_captures_two_dimension_metadata(mock_cluster, store, tmp_path):
    # A poll configured with BOTH company.net/mnemonic and company.net/app-environment captures both
    # dimensions end to end through the real poller/store (design §6). `store` writes to the same
    # tmp_path/gsd.db, so a read-only connection sees exactly what the poll persisted.
    cfg = mock_cluster.cluster_config(name="mock")
    assert poll_once(store, cfg, timeout=5.0) == "ok"
    assert refresh_bindings(store, cfg, timeout=5.0, namespaces_read=True,
                            namespace_metadata_labels=["company.net/mnemonic",
                                                       "company.net/app-environment"]) == "ok"
    assert store.namespaces_source("mock")["state"] == "ok"
    import sqlite3
    conn = sqlite3.connect(f"file:{tmp_path / 'gsd.db'}?mode=ro", uri=True)
    try:
        captured = {(name, key, value) for name, key, value in conn.execute(
            "SELECT name, key, value FROM cluster_namespace_label WHERE cluster_id='mock'")}
    finally:
        conn.close()
    # An EXACT set, not membership: a regression that copied the whole label map (team,
    # kubernetes.io/metadata.name) would add rows and must fail here, not slip past `in` (review C3).
    # gsd-shared appears with ONLY its mnemonic — the missing-dimension case has no app-environment row.
    assert captured == {
        ("acme-app", "company.net/mnemonic", "acme"),
        ("acme-app", "company.net/app-environment", "prod"),
        ("group-sync-operator", "company.net/mnemonic", "gso"),
        ("group-sync-operator", "company.net/app-environment", "prod"),
        ("demo-prod", "company.net/mnemonic", "demo"),
        ("demo-prod", "company.net/app-environment", "prod"),
        ("demo-qa", "company.net/mnemonic", "demo"),
        ("demo-qa", "company.net/app-environment", "qa"),
        ("beta-rnd", "company.net/mnemonic", "beta"),
        ("beta-rnd", "company.net/app-environment", "rnd"),
        ("platform-prod", "company.net/mnemonic", "klta"),
        ("platform-prod", "company.net/app-environment", "prod"),
        ("gsd-shared", "company.net/mnemonic", "gsd"),
    }


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


def test_refresh_bindings_stores_every_subject_kind_over_tls(tmp_path, store, caplog):
    """#353 end to end: the reference fixture names Group and User subjects only, so a ServiceAccount
    subject never crossed the real reader. This adds one RoleBinding naming an account twice — once with
    no namespace (26 such entries on the lab, stored under the binding's) and once with it — and reads
    it through poll_once + refresh_bindings into the Store (OB1-lite, review of #360)."""
    import dataclasses

    from conftest import FIXTURE_DIR, MockHandle, _clear_ca_cache
    from mock_app.fixture import Binding, Fixture, RoleRef, Subject
    from mock_app.server import MockClusterServer

    base = Fixture.from_yaml(FIXTURE_DIR / "reference.yaml")
    account = Binding(name="deployer-rb", namespace="acme-app", role_ref=RoleRef(kind="Role", name="viewer"),
                      subjects=(Subject(kind="ServiceAccount", name="deployer"),
                                Subject(kind="ServiceAccount", name="deployer", namespace="acme-app")))
    fixture = dataclasses.replace(base, role_bindings=base.role_bindings + (account,))
    server = MockClusterServer(fixture, host="127.0.0.1", port=0, tls=True)
    server.start()
    try:
        ca = tmp_path / "ca.crt"
        ca.write_bytes(server.ca_pem)
        cfg = MockHandle(base_url=server.base_url, token=fixture.token, ca_file=str(ca), server=server,
                         fixture=fixture).cluster_config(name="mock")
        assert poll_once(store, cfg, timeout=5.0) == "ok"
        with caplog.at_level("INFO", logger="gsd.poller"):
            assert refresh_bindings(store, cfg, timeout=5.0, audit_mode="log") == "ok"
    finally:
        server.stop()
        _clear_ca_cache()
    rows = {(r.get("subject_kind"), r.get("subject_namespace"), r["group_name"]): r["finding"]
            for r in store.all_bindings("mock")}
    assert rows.get(("ServiceAccount", "acme-app", "deployer")) == "unmanaged", rows
    assert rows.get(("User", "", "lateef.o")) == "unmanaged", rows
    assert "refreshed 6 bindings for mock (4 Group, 1 ServiceAccount, 1 User subjects)" in caplog.text, caplog.text
    assert "grants viewer to ServiceAccount acme-app/deployer" in caplog.text, caplog.text
