"""#321: audit-only migration, retained history and refusal of retired values."""
from __future__ import annotations

import itertools
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd import auditlog, logincapture
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterClient
from gsd.metrics import build_registry
from gsd.store import Store
from datetime import timedelta

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "charts/group-sync-dashboard"


def render_file(tmp_path, values):
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump(values))
    return subprocess.run(["helm", "template", "t", str(CHART), "-f", str(path)],
                          capture_output=True, text=True, timeout=120)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_removed_values_refuse_even_when_false_or_capture_disabled(tmp_path):
    # A single migration matrix also covers unknown nested keys: no retired map may be ignored.
    for enabled in (True, False):
        for retired in ({"manage": False}, {"enabled": False}, {"manage": True},
                        {"revertOnUninstall": False}, {"waitSeconds": 1}, {"unknown": False},
                        {}, False, None):
            result = render_file(tmp_path, {"authLogLevel": retired,
                                          "loginCapture": {"enabled": enabled}})
            assert result.returncode != 0, (enabled, retired, result.stdout)
            assert "authLogLevel" in result.stderr and "remove" in result.stderr
            assert "audit-log" in result.stderr and "Normal" in result.stderr
        for source in ("pod-log", "both", "typo", "AUDIT-LOG"):
            result = render_file(tmp_path, {"loginCapture": {"enabled": enabled, "source": source}})
            assert result.returncode != 0 and "loginCapture.source" in result.stderr
            assert "audit-log" in result.stderr
        result = render_file(tmp_path, {"loginCapture": {"enabled": enabled, "namespace": "ns"}})
        assert result.returncode != 0 and "remove" in result.stderr


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_no_oauth_debug_objects_or_grants_for_the_surviving_switch_matrix(tmp_path):
    # Removed values above fail. Every combination of the relevant surviving gates renders
    # either audit RBAC or no capture RBAC, never an OAuth writer or a pods/log reader.
    defaults = yaml.safe_load((CHART / "values.yaml").read_text())
    assert "authLogLevel" not in defaults  # baseline fails before any matrix render
    for capture, rbac, pinned in itertools.product((True, False), repeat=3):
        values = {"loginCapture": {"enabled": capture, "auditLog": {
                      "nodeNames": ["master-0"] if pinned else []}}, "rbac": {"create": rbac}}
        result = render_file(tmp_path, values)
        assert result.returncode == 0, result.stderr
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        assert not any("auth-loglevel" in d.get("metadata", {}).get("name", "") for d in docs)
        for d in docs:
            for rule in d.get("rules", []):
                assert "pods/log" not in rule.get("resources", [])
                assert not ("operator.openshift.io" in rule.get("apiGroups", [])
                            and "authentications" in rule.get("resources", []))
        audit = [d for d in docs if d.get("kind") == "ClusterRole"
                 and d["metadata"]["name"].endswith("-login-capture-audit")]
        assert len(audit) == int(capture)
        if capture:
            proxy = next(r for r in audit[0]["rules"] if r["resources"] == ["nodes/proxy"])
            assert proxy["verbs"] == ["get"]
            assert proxy.get("resourceNames", []) == (["master-0"] if pinned else [])
            assert any(r["resources"] == ["nodes"] for r in audit[0]["rules"]) == (not pinned)


def test_audit_default_reads_stored_pod_history_over_api_and_metrics_after_reopen(tmp_path):
    db = str(tmp_path / "history.db")
    s = Store(db)
    s.upsert_cluster("c", "https://example", True)
    s.record_login_events("c", [{"pod_name": "oauth-old", "user_name": "alice",
        "outcome": "bad_password", "at": "2026-09-20T10:00:00.000000Z", "provider": "ldap",
        "ldap_result_code": 49, "detail": "data 775", "observed_at": "2026-09-20T10:01:00Z"}])
    s.close()
    settings = Settings(clusters=[ClusterConfig("c", "https://example")], db_path=db,
                        login_capture_enabled=True, oauth_proxy_enabled=True)
    with TestClient(build_app(settings, run_poller=False, tier_resolver=lambda viewer: "all")) as client:
        result = client.get("/api/clusters/c/logins?kind=all", headers={"X-Forwarded-User": "root"})
        assert result.status_code == 200
        body = result.json()
        assert body["source"] == "audit-log"  # baseline incorrectly describes the live reader as pod-log
        row, = body["attempts"]
        assert (row["source"], row["pod_name"], row["ldap_result_code"], row["detail"]) == (
            "pod-log", "oauth-old", 49, "data 775")
        assert row["outcome"] == "bad_password" and row["kind"] == "credential"
    reopened = Store(db)
    try:
        assert len(reopened.login_events("c")) == 1
        text = generate_latest(build_registry(reopened, timedelta(seconds=120), settings=settings)).decode()
        assert 'gsd_login_capture_source_info{cluster="c",source="audit-log"} 1.0' in text
    finally:
        reopened.close()


def test_the_default_dispatches_to_audit_and_disabled_capture_reads_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(auditlog, "capture_once", lambda *a: calls.append(a) or 7)
    cfg = ClusterConfig("c", "https://example")
    settings = Settings(clusters=[cfg], login_capture_enabled=True)
    assert logincapture.capture_once(None, cfg, settings) == 7
    assert len(calls) == 1
    from dataclasses import replace
    settings = replace(settings, login_capture_enabled=False)
    assert logincapture.capture_once(None, cfg, settings) == 0
    assert len(calls) == 1
    assert not hasattr(ClusterClient, "fetch_pod_log")
    assert not hasattr(ClusterClient, "fetch_oauth_pods")


class _EmptyAuditNode:
    """The four calls auditlog.capture_once makes, for one node whose audit file is empty."""

    def fetch_nodes(self, selector):
        return ["master-0"]

    def fetch_oauth_providers(self):
        return ["ldap"]

    def list_node_log_files(self, node, directory):
        return [auditlog.AUDIT_FILE]

    def fetch_node_log_file(self, node, path, offset=0, max_bytes=8 << 20):
        from gsd.kube import NodeLogRead
        return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=False)


class _Elector:
    def __init__(self, leader):
        self.is_leader = leader


@pytest.mark.parametrize(("retention_days", "leader", "kept"), (
    (400, True, ["recent"]),               # Decision 3: normal retention still ages out history
    (0, True, ["ancient", "recent"]),      # 0 disables retention, as before
    (400, False, ["ancient", "recent"]),   # a standby never prunes
))
def test_stored_pod_log_history_keeps_its_retention_under_the_audit_only_poller(
        tmp_path, monkeypatch, retention_days, leader, kept):
    # The pod-log loop tests that pinned login_event retention are deleted with the loop; the
    # audit path now owns the prune, so the same three outcomes are pinned through it.
    from datetime import UTC, datetime
    db = str(tmp_path / "retention.db")
    store = Store(db)
    try:
        store.upsert_cluster("c", "https://example", True)
        now = datetime.now(UTC)
        store.record_login_events("c", [
            {"pod_name": "oauth-old", "user_name": name, "outcome": "bad_password",
             "at": (now - timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
             "provider": "ldap", "ldap_result_code": 49, "detail": None,
             "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
            for name, age in (("ancient", 500), ("recent", 1))])
        monkeypatch.setattr(auditlog, "ClusterClient", lambda *a, **kw: _EmptyAuditNode())
        cfg = ClusterConfig("c", "https://example")
        settings = Settings(clusters=[cfg], db_path=db, login_capture_enabled=True,
                            login_retention_days=retention_days,
                            login_capture_audit_node_names=("master-0",))
        logincapture.capture_once(store, cfg, settings, elector=_Elector(leader))
        assert sorted(r["user_name"] for r in store.login_events("c")) == kept
        assert all(r["source"] == "pod-log" for r in store.login_events("c"))
    finally:
        store.close()
