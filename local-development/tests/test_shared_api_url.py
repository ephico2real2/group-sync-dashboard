"""Shared targets warn without changing the effective fleet (#314)."""
import dataclasses
import logging

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.fleetlookup import CredentialGate
from gsd.poller import Poller
from gsd.store import Store
from test_clusterconfig import _secret
from test_configmap_onboarding import Host, cm

URL = "https://api.shared.example"


def api_client(poller):
    app = build_app(poller.settings, run_poller=False, cluster_admin_resolver=lambda _: "all")
    return TestClient(app, headers={"X-Forwarded-User": "root"})


@pytest.fixture
def rig(tmp_path, monkeypatch):
    host = Host([cm([{"name": "generated", "apiUrl": URL, "saTokenLookup": True}])])
    host.secrets["gsd-cluster-secret"] = _secret("gsd-cluster-secret", cluster="secret", server=URL)
    host.secrets["gsd-cluster-refused"] = _secret("gsd-cluster-refused", cluster="refused", server=URL, config={
        "bearerToken": "t", "tlsClientConfig": {"insecure": True, "caData": "eA=="}})
    settings = Settings(clusters=[ClusterConfig("host", "https://host", token_env="X"),
                                  ClusterConfig("values", URL + ":443/", token_env="X")],
                        db_path=str(tmp_path / "shared.db"), oauth_proxy_enabled=True)
    store = Store(settings.db_path)
    poller = Poller(store, settings)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    return poller, host


def test_three_sources_refused_secret_and_polling_unchanged(rig, monkeypatch):
    poller, host = rig
    poller._discover_once()
    from gsd.clusterconfig.warnings import shared_api_warnings
    warnings = shared_api_warnings(poller.settings.effective_clusters())
    assert len(warnings) == 1
    assert warnings[0]["code"] == "shared-api-url"
    assert warnings[0]["clusters"] == ["generated", "secret", "values"]
    assert URL in warnings[0]["detail"]
    assert any(f.code == "insecure-with-ca" for f in poller.settings.cluster_registry.findings())
    assert {c.name for c in poller.settings.effective_clusters()} == {"host", "values", "secret", "generated"}
    started = []
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda c: started.append(c.name))
    poller._reconcile_threads()
    assert set(started) == {"host", "values", "secret"}
    assert {row["id"] for row in poller.store.clusters()} == {"secret", "generated"}
    assert host.mutations == []


@pytest.mark.parametrize("left,right,equal", [
    ("https://API.shared.example:443/", URL, True),
    ("https://api.shared.example:6443/", URL + ":6443", True),
    ("https://bücher.example/", "https://xn--bcher-kva.example", True),
    (URL + ":6443", URL, False),
    (URL + "/Path", URL + "/path", False),
    ("https://another.example", URL, False),
])
def test_normalisation_is_the_credential_gate_rule(left, right, equal):
    from gsd.clusterconfig.warnings import shared_api_warnings
    assert (CredentialGate._target(left) == CredentialGate._target(right)) is equal
    warnings = shared_api_warnings([ClusterConfig("b", left), ClusterConfig("a", right)])
    assert len(warnings) == int(equal)
    if equal:
        assert warnings[0]["clusters"] == ["a", "b"]
        assert CredentialGate._target(left) in warnings[0]["detail"]


def test_group_logs_once_then_clears_and_reappears(rig, caplog):
    poller, host = rig
    with caplog.at_level(logging.INFO, logger="gsd.clusterconfig"):
        for _ in range(3):
            poller._discover_once()
        lines = [m for m in caplog.messages if m.startswith("shared-api-url ")]
        assert lines == [f"shared-api-url url={URL} clusters=generated,secret,values state=appeared cycle=1"]
        host.maps = []
        del host.secrets["gsd-cluster-secret"]
        poller._discover_once()
        poller._discover_once()
        lines = [m for m in caplog.messages if m.startswith("shared-api-url ")]
        assert len(lines) == 2
        assert lines[-1] == f"shared-api-url url={URL} clusters=generated,secret,values state=cleared cycle=4"
        host.secrets["gsd-cluster-secret"] = _secret("gsd-cluster-secret", cluster="secret", server=URL)
        poller._discover_once()
        lines = [m for m in caplog.messages if m.startswith("shared-api-url ")]
        assert len(lines) == 3
        assert lines[-1] == f"shared-api-url url={URL} clusters=secret,values state=appeared cycle=6"


def test_api_adds_only_warnings_and_empty_when_cleared(rig):
    poller, host = rig
    poller._discover_once()
    client = api_client(poller)
    baseline = client.get("/api/clusterconfigs").json()
    assert baseline["warnings"][0]["clusters"] == ["generated", "secret", "values"]
    assert set(baseline["warnings"][0]) == {"code", "clusters", "detail"}
    assert not any(f["code"] == "shared-api-url" for f in baseline["findings"])
    assert len(baseline["clusters"]) == 4
    before = {route: client.get(route).content for route in ["/api/clusters", "/api/alerts"]}
    client.get("/api/clusterconfigs")
    assert before == {route: client.get(route).content for route in before}
    host.maps = []
    del host.secrets["gsd-cluster-secret"]
    poller._discover_once()
    assert client.get("/api/clusterconfigs").json()["warnings"] == []


def test_shadowed_values_are_not_compared(rig):
    poller, host = rig
    host.maps = []
    host.secrets["gsd-cluster-secret"] = _secret(cluster="values", server="https://other")
    host.secrets["gsd-cluster-alone"] = _secret(cluster="alone", server=URL)
    poller._discover_once()
    client = api_client(poller)
    assert client.get("/api/clusterconfigs").json()["warnings"] == []


def test_values_only_warn_with_discovery_off(rig, monkeypatch, caplog):
    poller, _ = rig
    poller.settings = dataclasses.replace(poller.settings, cluster_secrets_enabled=False)
    poller.settings.clusters.append(ClusterConfig("alias", URL))
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda c: None)
    with monkeypatch.context() as threads, caplog.at_level(logging.INFO, logger="gsd.clusterconfig"):
        threads.setattr("threading.Thread.start", lambda self: None)
        poller.start()
    assert len([m for m in caplog.messages if m.startswith("shared-api-url ")]) == 1
    client = api_client(poller)
    assert client.get("/api/clusterconfigs").json()["warnings"][0]["clusters"] == ["alias", "values"]


def test_configmap_generated_secret_is_included(rig):
    from gsd.clusterconfig.writer import CreateRequest, MANAGED_BY_ONBOARD, secret_object
    from test_clusterconfig_tab import _as_stored
    poller, host = rig
    poller._discover_once()
    pending = poller.settings.cluster("generated")
    host.secrets["gsd-cluster-generated"] = _as_stored(secret_object(CreateRequest(
        name="generated", server=URL, credential_kind="bearerToken", token="generated-token", onboarding=pending.onboarding,
        managed_by=MANAGED_BY_ONBOARD, token_source="remote-lookup"), "ns"))
    poller._discover_once()
    generated = poller.settings.cluster("generated")
    assert generated.source == "secret:gsd-cluster-generated"
    assert generated.credential_pending is None
    assert generated.onboarding == pending.onboarding
    assert api_client(poller).get("/api/clusterconfigs").json()["warnings"][0]["clusters"] == [
        "generated", "secret", "values"]


def test_failed_inventory_keeps_the_warning_without_logging_a_clear(rig, caplog):
    poller, host = rig
    poller._discover_once()
    caplog.clear()
    host.fail_list = "/secrets"
    with caplog.at_level(logging.INFO, logger="gsd.clusterconfig"):
        poller._discover_once()
    assert not any(m.startswith("shared-api-url ") for m in caplog.messages)
    assert api_client(poller).get("/api/clusterconfigs").json()["warnings"][0]["clusters"] == [
        "generated", "secret", "values"]


def test_a_disabled_entry_is_not_a_shared_target():
    """A disabled entry is not polled, so it doubles nothing: the issue's reason for leaving refused Secrets out."""
    from gsd.clusterconfig.warnings import shared_api_urls, shared_api_warnings
    old, new = ClusterConfig("old", URL, enabled=False), ClusterConfig("new", URL + "/")
    assert shared_api_warnings([old, new]) == []
    assert shared_api_urls([old, new, ClusterConfig("alias", URL)]) == {URL: ("alias", "new")}
