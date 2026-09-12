"""The poller's reporting tail (docs/specs/SPEC_C3_reporting_microservice.md §9.8): the snapshot on its own
cadence, the usage PULL against a mocked report service, and the leadership re-checks."""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from gsd.config import ClusterConfig, Settings
from gsd.metrics import RuntimeSignals
from gsd.poller import Poller
from gsd.store import Store

SECRET = b"p" * 48


def _poller(tmp_path, *, reporting=True, keep=2, interval=300) -> tuple[Poller, Store]:
    token = tmp_path / "token"; token.write_bytes(SECRET)
    settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=str(tmp_path / "t.db"),
                        reporting_url="https://gsd-report.ns.svc:8443" if reporting else "", reporting_token_file=str(token),
                        reporting_snapshot_dir=str(tmp_path / "report"), reporting_snapshot_interval_seconds=interval, reporting_snapshot_keep=keep)
    store = Store(settings.db_path)
    store.upsert_cluster("c1", "https://x", True)
    return Poller(store, settings, None, signals=RuntimeSignals()), store


def _mock_service(monkeypatch, handler):
    """Route the poller's httpx.Client through a MockTransport, keeping its base_url and headers."""
    real = httpx.Client
    class Client(real):
        def __init__(self, *a, **kw):
            kw["transport"] = httpx.MockTransport(handler)
            kw.pop("verify", None)
            super().__init__(*a, **kw)
    monkeypatch.setattr(httpx, "Client", Client)


def _run(i, by="root"):
    return {"id": f"20260906T12000{i}.000000Z-000{i}", "report": "groups", "cluster": "c1", "generated_by": by, "generated_by_note": "n",
            "status": "done", "requested_at": f"2026-09-06T12:00:0{i}Z", "sha256": "ab" * 32, "formats": ["html"], "bytes": {"json": 1}}


class TestTheSnapshot:
    def test_written_at_most_once_per_interval_and_keeps_n(self, tmp_path):
        poller, store = _poller(tmp_path, keep=2, interval=300)
        try:
            poller._maybe_report_snapshot()
            poller._maybe_report_snapshot()
            assert len(list((tmp_path / "report").glob("gsd-*.db"))) == 1, "the second call is inside the interval"
            poller._next_report_snapshot = 0.0
            poller._maybe_report_snapshot()
            poller._next_report_snapshot = 0.0
            poller._maybe_report_snapshot()
            files = sorted((tmp_path / "report").glob("gsd-*.db"))
            assert len(files) == 2 and not list((tmp_path / "report").glob("*.tmp"))
        finally:
            store.close()

    def test_no_op_with_reporting_off(self, tmp_path):
        poller, store = _poller(tmp_path, reporting=False)
        try:
            poller._maybe_report_snapshot(); poller._pull_report_usage()
            assert not (tmp_path / "report").exists() and poller.signals.snapshot()["report_pulls"] == {}
        finally:
            store.close()


class TestThePull:
    def test_records_rows_advances_the_watermark_and_pages(self, tmp_path, monkeypatch):
        poller, store = _poller(tmp_path)
        seen = []
        def handler(request):
            seen.append((request.url.path, dict(request.url.params), request.headers.get("authorization")))
            since = request.url.params.get("since_id")
            if since is None:
                return httpx.Response(200, json={"runs": [_run(0), _run(1)], "next_since_id": _run(1)["id"], "truncated": True})
            if since == _run(1)["id"]:
                return httpx.Response(200, json={"runs": [_run(2, "alice")], "next_since_id": _run(2)["id"], "truncated": False})
            return httpx.Response(200, json={"runs": [], "next_since_id": since, "truncated": False})
        _mock_service(monkeypatch, handler)
        try:
            poller._pull_report_usage()
            assert [p for p, _, _ in seen] == ["/report/api/usage", "/report/api/usage"]
            assert seen[0][2] == f"Bearer {SECRET.decode()}"
            assert store.count_report_runs(user_name=None) == 3 and store.report_runs_watermark() == _run(2)["id"]
            poller._pull_report_usage()
            assert seen[-1][1]["since_id"] == _run(2)["id"], "the next pull starts at the watermark"
            assert poller.signals.snapshot()["report_pulls"] == {"ok": 2}
        finally:
            store.close()

    @pytest.mark.parametrize("status,outcome", [(401, "refused"), (403, "refused"), (500, "error")])
    def test_a_refusal_or_error_is_counted_and_never_raises(self, tmp_path, monkeypatch, status, outcome):
        poller, store = _poller(tmp_path)
        _mock_service(monkeypatch, lambda request: httpx.Response(status, text="no"))
        try:
            poller._pull_report_usage()
            assert poller.signals.snapshot()["report_pulls"] == {outcome: 1}
        finally:
            store.close()

    def test_an_unreachable_service_is_counted_unreachable(self, tmp_path, monkeypatch):
        poller, store = _poller(tmp_path)
        def handler(request):
            raise httpx.ConnectError("refused")
        _mock_service(monkeypatch, handler)
        try:
            poller._pull_report_usage()
            assert poller.signals.snapshot()["report_pulls"] == {"unreachable": 1}
        finally:
            store.close()

    def test_a_reachable_service_answering_garbage_is_an_error_not_unreachable(self, tmp_path, monkeypatch):
        """Codex, review C3: `unreachable` is the Service or TLS; a 200 whose body is not the feed's shape
        is `error`, as the alert's description promises."""
        poller, store = _poller(tmp_path)
        _mock_service(monkeypatch, lambda request: httpx.Response(200, content=b"{not-json"))
        try:
            poller._pull_report_usage()
            assert poller.signals.snapshot()["report_pulls"] == {"error": 1}
        finally:
            store.close()

    def test_a_missing_token_is_an_error_not_a_crash(self, tmp_path, monkeypatch):
        poller, store = _poller(tmp_path)
        (tmp_path / "token").unlink()
        try:
            poller._pull_report_usage()
            assert poller.signals.snapshot()["report_pulls"] == {"error": 1}
        finally:
            store.close()


def test_reporting_tail_rechecks_leadership_after_the_poll():
    poller = Poller.__new__(Poller)
    poller.store = SimpleNamespace(maintain=Mock())
    poller.elector = SimpleNamespace(is_leader=False)
    poller._maybe_backup = Mock(); poller._prune_history = Mock()
    poller._maybe_report_snapshot = Mock(); poller._pull_report_usage = Mock()
    poller._after_poll(SimpleNamespace(name="crc-local"))
    poller.store.maintain.assert_called_once_with()
    poller._maybe_backup.assert_called_once_with()
    poller._prune_history.assert_called_once()
    poller._maybe_report_snapshot.assert_not_called()
    poller._pull_report_usage.assert_not_called()


def test_the_tail_runs_both_steps_for_the_leader():
    poller = Poller.__new__(Poller)
    poller.store = SimpleNamespace(maintain=Mock())
    poller.elector = SimpleNamespace(is_leader=True)
    poller._maybe_backup = Mock(); poller._prune_history = Mock()
    poller._maybe_report_snapshot = Mock(); poller._pull_report_usage = Mock()
    poller._after_poll(SimpleNamespace(name="crc-local"))
    poller._maybe_report_snapshot.assert_called_once_with()
    poller._pull_report_usage.assert_called_once_with()
