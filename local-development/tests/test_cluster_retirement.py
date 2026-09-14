"""#96 — a cluster removed from the configuration is RETIRED (enabled=0, history kept), not left
lingering as `ok` with frozen data and stale alerts. Removed and disabled are treated the same: gone
from the selector, the alert feed and the metrics; a direct per-cluster request 404s; the DB rows and
their history stay so a report can still read them. The poller reconciles this on every start (a config
change rolls the pod), so add/remove works on the fly."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store

ROOT = {"X-Forwarded-User": "root"}


class _Map:
    def __init__(self, tiers):
        self.tiers = tiers

    def resolve(self, viewer):
        return self.tiers.get(viewer, "self")


def _seed_two(db: str) -> None:
    """crc (kept) and gone (to be removed) — both polled, gone left with a poll failure so it would
    raise a stale alert if it were still served."""
    store = Store(db)
    for cid in ("crc", "gone"):
        store.upsert_cluster(cid, f"https://api.{cid}:6443", True)
        store.record_poll(cid, "ok", None)
    store.record_poll("gone", "unreachable", "the removed remote timed out")
    store.close()


class TestRetireAbsentClusters:
    def test_absent_is_retired_present_is_kept_rows_stay(self, tmp_path):
        db = str(tmp_path / "r.db")
        _seed_two(db)
        store = Store(db)
        assert store.retire_absent_clusters(["crc"]) == 1
        rows = {r["id"]: r["enabled"] for r in store.clusters()}
        assert rows == {"crc": 1, "gone": 0}          # gone retired, crc kept, BOTH rows still present
        store.close()

    def test_empty_config_retires_all(self, tmp_path):
        db = str(tmp_path / "e.db")
        _seed_two(db)
        store = Store(db)
        assert store.retire_absent_clusters([]) == 2
        assert all(r["enabled"] == 0 for r in store.clusters())
        store.close()

    def test_idempotent_and_history_kept(self, tmp_path):
        db = str(tmp_path / "i.db")
        _seed_two(db)
        store = Store(db)
        store.retire_absent_clusters(["crc"])
        assert store.retire_absent_clusters(["crc"]) == 0        # already retired — no-op
        gone = next(r for r in store.clusters() if r["id"] == "gone")
        assert gone["status"] == "unreachable" and gone["last_poll"]   # its poll history is retained
        store.close()


class TestRetiredClusterIsNotServed:
    @pytest.fixture
    def client(self, tmp_path):
        db = str(tmp_path / "s.db")
        _seed_two(db)
        store = Store(db)
        store.retire_absent_clusters(["crc"])        # gone -> enabled=0, as the poller does at start
        store.close()
        settings = Settings(
            clusters=[ClusterConfig("crc", "https://api.crc:6443", token_env="X")],
            db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {}
        with TestClient(app) as c:
            yield c

    def test_clusters_list_omits_the_retired_one(self, client):
        ids = [c["id"] for c in client.get("/api/clusters", headers=ROOT).json()]
        assert ids == ["crc"]

    def test_alerts_exclude_the_retired_cluster(self, client):
        alerts = client.get("/api/alerts", headers=ROOT).json()["alerts"]
        assert all(a["cluster"] != "gone" for a in alerts)

    def test_a_direct_request_for_the_retired_cluster_404s(self, client):
        assert client.get("/api/clusters/gone/groupsyncs", headers=ROOT).status_code == 404

    def test_metrics_do_not_emit_the_retired_cluster(self, client):
        text = client.get("/metrics").text
        assert 'cluster="gone"' not in text
        assert 'cluster="crc"' in text

    def test_retired_cluster_absent_from_whoami(self, client):
        who = client.get("/api/whoami", headers=ROOT).json()["visibility"]
        assert set(who["clusters"]) == {"crc"}


class TestRetiredClusterLeavesTheMetricRegistry:
    """The process-local signal series (poll duration, unmatched audit) are cluster-keyed and, before
    the #96 review fix, outlived a retirement in the SAME registry — every /metrics family must drop a
    retired id, not only the store-backed ones."""

    def test_process_signal_series_disappear_when_retired(self, tmp_path):
        from datetime import timedelta

        from prometheus_client import generate_latest

        from gsd.metrics import RuntimeSignals, build_registry

        signals = RuntimeSignals()
        signals.note_poll_duration("gone", 1.25)
        signals.note_audit_unmatched("gone", "failed", 4)
        store = Store(str(tmp_path / "m.db"))
        try:
            store.upsert_cluster("gone", "https://gone:6443", True)
            reg = build_registry(store, timedelta(seconds=120), signals=signals)
            assert 'cluster="gone"' in generate_latest(reg).decode()
            store.retire_absent_clusters([])            # gone -> enabled=0
            assert 'cluster="gone"' not in generate_latest(reg).decode()
        finally:
            store.close()


class TestDisabledClusterIsAlsoNotServed:
    @pytest.fixture
    def client(self, tmp_path):
        # crc enabled, off disabled in config — the poller upserts off as enabled=0.
        db = str(tmp_path / "d.db")
        store = Store(db)
        store.upsert_cluster("crc", "https://api.crc:6443", True)
        store.record_poll("crc", "ok", None)
        store.upsert_cluster("off", "https://api.off:6443", False)
        store.record_poll("off", "unreachable", "the disabled remote timed out")   # would alert if served
        store.close()
        settings = Settings(clusters=[
            ClusterConfig("crc", "https://api.crc:6443", token_env="X"),
            ClusterConfig("off", "https://api.off:6443", token_env="X", enabled=False),
        ], db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {}
        with TestClient(app) as c:
            yield c

    def test_disabled_cluster_is_omitted_and_404s(self, client):
        ids = [c["id"] for c in client.get("/api/clusters", headers=ROOT).json()]
        assert ids == ["crc"]
        assert client.get("/api/clusters/off/groupsyncs", headers=ROOT).status_code == 404

    def test_disabled_cluster_is_absent_from_whoami(self, client):
        # A disabled cluster must not appear in visibility.clusters either (#96) — no cluster the
        # selector and every tab omit.
        who = client.get("/api/whoami", headers=ROOT).json()["visibility"]
        assert set(who["clusters"]) == {"crc"}

    def test_disabled_cluster_raises_no_alert_and_no_metric(self, client):
        alerts = client.get("/api/alerts", headers=ROOT).json()["alerts"]
        assert all(a["cluster"] != "off" for a in alerts)     # its stale unreachable is not fed
        text = client.get("/metrics").text
        assert 'cluster="off"' not in text
