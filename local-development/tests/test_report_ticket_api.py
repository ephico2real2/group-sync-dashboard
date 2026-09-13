"""The dashboard's two reporting endpoints (docs/specs/SPEC_C3_reporting_microservice.md §9.8): the ticket is
minted only at the administrator tier and only when reporting is on; the usage view is the usage tier's."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.reporting.ticket import TicketError, verify
from gsd.store import Store

SECRET = b"t" * 48
ADMIN = {"X-Forwarded-User": "root"}
ALICE = {"X-Forwarded-User": "alice"}


def _tier(viewer: str) -> str:
    return "all" if viewer == "root" else "self"


def _client(tmp_path, *, reporting=True, proxy=True, usage=None) -> TestClient:
    token = tmp_path / "token"
    token.write_bytes(SECRET + b"\n")
    settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=str(tmp_path / "t.db"),
                        oauth_proxy_enabled=proxy, reporting_url="https://gsd-report.ns.svc:8443" if reporting else "",
                        reporting_token_file=str(token), reporting_ticket_ttl_seconds=120)
    return TestClient(build_app(settings, run_poller=False, tier_resolver=_tier, usage_tier_resolver=usage or _tier))


class TestTheTicket:
    def test_404_when_reporting_is_off_and_the_feature_flag_says_so(self, tmp_path):
        c = _client(tmp_path, reporting=False)
        assert c.get("/api/report/ticket", headers=ADMIN).status_code == 404
        assert c.get("/api/version").json()["features"]["reporting"] is False

    def test_the_wide_tier_gets_a_ticket_bound_to_its_own_name(self, tmp_path):
        c = _client(tmp_path)
        assert c.get("/api/version").json()["features"] == {"export": True, "reporting": True, "reporting_prefix": "/report"}
        body = c.get("/api/report/ticket", headers=ADMIN).json()
        assert body["expires_in"] == 120 and body["prefix"] == "/report" and body["viewer"] == "root"
        claims = verify(SECRET, body["ticket"], "root")
        assert claims["tier"] == "all" and claims["viewer"] == "root"
        with pytest.raises(TicketError):
            verify(SECRET, body["ticket"], "alice")

    def test_below_the_wide_tier_the_gate_refuses_with_its_own_sentence(self, tmp_path):
        r = _client(tmp_path).get("/api/report/ticket", headers=ALICE)
        assert r.status_code == 403 and r.json()["detail"].startswith("For administrators only.")

    def test_an_unusable_token_is_a_startup_failure_when_reporting_is_on(self, tmp_path):
        token = tmp_path / "short"; token.write_bytes(b"tiny")
        settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=str(tmp_path / "t.db"),
                            oauth_proxy_enabled=True, reporting_url="https://r", reporting_token_file=str(token))
        with pytest.raises(RuntimeError, match="token is unusable"):
            build_app(settings, run_poller=False, tier_resolver=_tier)


class TestTheUsageView:
    def _seed(self, tmp_path):
        s = Store(str(tmp_path / "t.db"))
        s.upsert_cluster("c1", "https://x", True)
        runs = [{"id": f"20260906T12000{i}.000000Z-000{i}", "report": "groups", "cluster": "c1", "generated_by": by,
                 "generated_by_note": "n", "status": "done", "requested_at": f"2026-09-06T12:00:0{i}Z", "finished_at": None,
                 "sha256": "ab" * 32, "formats": ["html"], "bytes": {"json": 10, "html": 20}, "pdf_variant": None}
                for i, by in enumerate(("root", "alice", "root"))]
        assert s.record_report_runs(runs, "2026-09-06T12:05:00Z") == 3
        s.close()

    def test_off_is_an_enabled_false_shape(self, tmp_path):
        body = _client(tmp_path, reporting=False).get("/api/dashboard/reports", headers=ADMIN).json()
        assert body == {"enabled": False, "scope": "self", "viewer": "root", "total": 0, "limit": 200, "truncated": False, "runs": []}

    def test_self_sees_own_rows_and_the_usage_tier_sees_everyone(self, tmp_path):
        self._seed(tmp_path)
        c = _client(tmp_path)
        mine = c.get("/api/dashboard/reports", headers=ALICE).json()
        assert mine["scope"] == "self" and mine["total"] == 1 and [r["generated_by"] for r in mine["runs"]] == ["alice"]
        every = c.get("/api/dashboard/reports", headers=ADMIN).json()
        assert every["scope"] == "all" and every["total"] == 3 and every["runs"][0]["bytes_total"] == 30
        page = c.get("/api/dashboard/reports?limit=2", headers=ADMIN).json()
        assert page["total"] == 3 and page["truncated"] is True and len(page["runs"]) == 2

    def test_without_the_proxy_there_is_nobody_to_scope_to(self, tmp_path):
        assert _client(tmp_path, proxy=False).get("/api/dashboard/reports", headers=ADMIN).status_code == 403
