"""The report service's API (docs/specs/SPEC_C3_reporting_microservice.md §9.7): its own contract, the doors
(ticket, service token), the run lifecycle and the usage feed."""
from __future__ import annotations

import inspect
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd.activity import USER_HEADER
from gsd.reporting import REPORT_PREFIX, TICKET_HEADER
from gsd.reporting.artifacts import ArtifactStore, Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.runs import RunManager
from gsd.reporting.server import REFUSAL, UNAUTHENTICATED, build_report_app
from gsd.reporting.ticket import mint
from reporting_seed import CLUSTER, seeded_dirs

SECRET = b"s" * 48
VENDOR = Path(__file__).resolve().parents[1] / "gsd" / "static" / "vendor"
FONTS = (str(VENDOR / "DejaVuSans.ttf"), str(VENDOR / "DejaVuSans-Bold.ttf"))
T0 = int(time.time())          # tickets are minted 'now'; the fixture's clock is frozen just after


def _settings(snapshots, artifacts, **over) -> ReportSettings:
    base = dict(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=True, pdf_variant="pdf/a-2b",
                font_regular=FONTS[0], font_bold=FONTS[1], login_capture_enabled=True)
    base.update(over)
    return ReportSettings(**base)


@pytest.fixture()
def service(tmp_path):
    snapshots, artifacts = seeded_dirs(tmp_path)
    clock = {"now": datetime.fromtimestamp(T0 + 10, UTC)}
    app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: clock["now"])
    with TestClient(app) as client:
        yield client, app, clock


def _viewer(user="root"):
    return {TICKET_HEADER: mint(SECRET, user, "all", 300, now=T0), USER_HEADER: user}


SERVICE = {"Authorization": f"Bearer {SECRET.decode()}"}


def _wait_done(client, run_id, headers, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        run = client.get(f"{REPORT_PREFIX}/api/runs/{run_id}", headers=headers).json()
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.1)
    raise AssertionError(f"run {run_id} did not finish: {run}")


class TestItsOwnContract:
    def test_routes_are_documented_prefixed_and_one_is_a_post(self, service):
        client, app, _ = service
        non_get = []
        for route in app.routes:
            if not hasattr(route, "endpoint") or route.path.startswith("/openapi") or route.path.endswith("openapi.json"):
                continue
            assert route.path.startswith(REPORT_PREFIX), route.path
            doc = (route.endpoint.__doc__ or "").strip().splitlines()
            assert doc and doc[0].rstrip().endswith((".", ":")), (route.path, doc[:1])
            for method in route.methods - {"HEAD", "OPTIONS"}:
                if method != "GET":
                    non_get.append((method, route.path))
            for p in inspect.signature(route.endpoint).parameters.values():
                default = p.default
                if type(default).__name__ == "FieldInfo" or "Query" in type(default).__name__:
                    assert getattr(default, "description", None), (route.path, p.name)
        assert non_get == [("POST", f"{REPORT_PREFIX}/api/runs")]

    def test_the_unauthenticated_set_is_exactly_the_probes(self, service):
        client, _, _ = service
        for path in UNAUTHENTICATED:
            assert client.get(path).status_code in (200, 503), path
        for path in (f"{REPORT_PREFIX}/api/reports", f"{REPORT_PREFIX}/api/runs", f"{REPORT_PREFIX}/api/snapshot", f"{REPORT_PREFIX}/api/usage"):
            assert client.get(path).status_code == 401, path


class TestTheDoors:
    def test_ticket_bound_to_the_proxy_identity_and_the_service_token(self, service):
        client, _, _ = service
        assert client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).status_code == 200
        wrong_user = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=T0), USER_HEADER: "alice"}
        r = client.get(f"{REPORT_PREFIX}/api/reports", headers=wrong_user)
        assert r.status_code == 403 and r.json()["detail"] == REFUSAL
        bad_sig = {TICKET_HEADER: mint(b"z" * 48, "root", "all", 300, now=T0), USER_HEADER: "root"}
        assert client.get(f"{REPORT_PREFIX}/api/reports", headers=bad_sig).status_code == 403
        assert client.get(f"{REPORT_PREFIX}/api/reports", headers={TICKET_HEADER: "nope", USER_HEADER: "root"}).status_code == 403
        assert client.get(f"{REPORT_PREFIX}/api/usage", headers=SERVICE).status_code == 200
        assert client.get(f"{REPORT_PREFIX}/api/usage", headers=_viewer()).status_code == 403
        assert client.get(f"{REPORT_PREFIX}/api/runs", headers={"Authorization": "Bearer wrong"}).status_code == 401

    def test_an_expired_ticket_is_the_one_401_so_the_page_remints_once(self, service):
        client, _, clock = service
        clock["now"] = datetime.fromtimestamp(T0 + 301, UTC)
        r = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer())
        assert r.status_code == 401 and r.json()["detail"] == "the report ticket expired; mint a new ticket"


class TestRuns:
    def test_a_run_renders_every_format_and_the_artefacts_download(self, service):
        client, _, _ = service
        r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "namespace-access", "cluster": CLUSTER,
                                                           "params": {"namespaces": "prod-ns"}, "formats": ["html", "pdf"]}, headers=_viewer())
        assert r.status_code == 202 and r.json()["status"] == "queued"
        run_id = r.json()["id"]
        assert client.get(f"{REPORT_PREFIX}/api/runs/{run_id}/artifact", headers=_viewer()).status_code == 404, "404 before done"
        run = _wait_done(client, run_id, _viewer())
        assert run["status"] == "done", run.get("error")
        assert len(run["sha256"]) == 64 and set(run["bytes"]) == {"json", "html", "pdf"} and run["generated_by"] == "root"
        for fmt, media, magic in (("pdf", "application/pdf", b"%PDF"), ("html", "text/html", b"<!doctype html>"), ("json", "application/json", b"{")):
            a = client.get(f"{REPORT_PREFIX}/api/runs/{run_id}/artifact", params={"format": fmt}, headers=_viewer())
            assert a.status_code == 200 and a.headers["content-type"].startswith(media)
            assert a.headers["cache-control"] == "no-store" and a.headers["x-gsd-report-sha256"] == run["sha256"]
            assert a.headers["content-disposition"].startswith('attachment; filename="gsd_') and a.content.startswith(magic)
        listing = client.get(f"{REPORT_PREFIX}/api/runs", headers=_viewer()).json()
        assert listing["total"] == 1 and listing["runs"][0]["id"] == run_id

    def test_refusals_are_specific(self, service):
        client, _, _ = service
        post = lambda body, headers=None: client.post(f"{REPORT_PREFIX}/api/runs", json=body, headers=headers or _viewer())  # noqa: E731
        assert post({"report": "nope", "cluster": CLUSTER}).status_code == 404
        assert post({"report": "groups", "cluster": CLUSTER, "params": {"bogus": 1}}).status_code == 422
        assert post({"report": "groups", "cluster": CLUSTER, "formats": ["docx"]}).status_code == 422
        assert post({"report": "groups", "cluster": CLUSTER, "schedule": "weekly"}).status_code == 422, "a viewer names no schedule"
        assert post({"report": "groups", "cluster": CLUSTER, "schedule": "weekly", "formats": ["html"]}, SERVICE).status_code == 202

    def test_a_disabled_report_and_a_disabled_pdf_are_refused_by_name(self, tmp_path):
        snapshots, artifacts = seeded_dirs(tmp_path)
        app = build_report_app(_settings(snapshots, artifacts, pdf_enabled=False, pdf_variant="", enabled_reports=("groups",)), secret=SECRET)
        with TestClient(app) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "users", "cluster": CLUSTER, "formats": ["html"]}, headers=_viewer())
            assert r.status_code == 404 and "not enabled" in r.json()["detail"]
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["pdf"]}, headers=_viewer())
            assert r.status_code == 422 and "reporting.pdf.enabled" in r.json()["detail"]
            cat = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()
            assert {r["name"]: r["enabled"] for r in cat["reports"]}["users"] is False
            assert next(r for r in cat["reports"] if r["name"] == "users")["values_key"] == "reporting.reports.users.enabled"

    def test_a_full_queue_answers_429_and_records_the_run_failed(self, tmp_path, monkeypatch):
        snapshots, artifacts = seeded_dirs(tmp_path)
        gate = threading.Event()
        real_render = RunManager._render
        def blocking(self, run):
            gate.wait(timeout=20)
            return real_render(self, run)
        monkeypatch.setattr(RunManager, "_render", blocking)
        app = build_report_app(_settings(snapshots, artifacts, max_queued_runs=1), secret=SECRET)
        body = {"report": "groups", "cluster": CLUSTER, "formats": ["html"]}
        with TestClient(app) as client:
            first = client.post(f"{REPORT_PREFIX}/api/runs", json=body, headers=_viewer())
            time.sleep(0.6)   # the worker takes the first and blocks; the queue is empty again
            second = client.post(f"{REPORT_PREFIX}/api/runs", json=body, headers=_viewer())
            third = client.post(f"{REPORT_PREFIX}/api/runs", json=body, headers=_viewer())
            assert first.status_code == 202 and second.status_code == 202
            assert third.status_code == 429
            failed = client.get(f"{REPORT_PREFIX}/api/runs", headers=_viewer()).json()["runs"]
            assert any(r["status"] == "failed" and "queue is full" in (r["error"] or "") for r in failed)
            gate.set()

    def test_usage_pages_in_id_order_for_the_service_only(self, service):
        client, _, _ = service
        ids = []
        for _ in range(3):
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["html"]}, headers=_viewer())
            ids.append(r.json()["id"])
            _wait_done(client, ids[-1], _viewer())
        page = client.get(f"{REPORT_PREFIX}/api/usage", params={"limit": 2}, headers=SERVICE).json()
        assert [r["id"] for r in page["runs"]] == sorted(ids)[:2] and page["truncated"] is True
        rest = client.get(f"{REPORT_PREFIX}/api/usage", params={"since_id": page["next_since_id"], "limit": 2}, headers=SERVICE).json()
        assert [r["id"] for r in rest["runs"]] == sorted(ids)[2:] and rest["truncated"] is False

    def test_readiness_and_metrics(self, tmp_path):
        snapshots, artifacts = tmp_path / "s", tmp_path / "a"
        snapshots.mkdir(); artifacts.mkdir()
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET)
        with TestClient(app) as client:
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 503
        (tmp_path / "two").mkdir()
        snapshots2, artifacts2 = seeded_dirs(tmp_path / "two")
        app = build_report_app(_settings(snapshots2, artifacts2), secret=SECRET)
        with TestClient(app) as client:
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 200
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "namespace-access", "cluster": CLUSTER, "params": {"namespaces": "prod-ns"}, "formats": ["html"]}, headers=_viewer())
            _wait_done(client, r.json()["id"], _viewer())
            text = client.get(f"{REPORT_PREFIX}/metrics").text
            assert 'gsd_report_runs_finished_total{report="namespace-access",status="done"} 1.0' in text
            assert "root" not in text and "gsd_report_snapshot_age_seconds" in text


class TestTheArtifactStore:
    def test_a_running_manifest_is_failed_on_restart_and_prune_honours_both_bounds(self, tmp_path):
        store = ArtifactStore(str(tmp_path / "a"))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        for i, stamp in enumerate(("20260101T000000.000000Z", "20260801T000000.000000Z", "20260905T000000.000000Z", "20260906T000000.000000Z")):
            run = Run(id=f"{stamp}-{i:04x}", report="groups", cluster=CLUSTER, params={}, formats=["html"], generated_by="root",
                      generated_by_note="n", schedule=None, requested_at=stamp, status="done" if i else "running")
            store.create(run)
        reloaded = ArtifactStore(str(tmp_path / "a"))
        first = reloaded.get("20260101T000000.000000Z-0000")
        assert first.status == "failed" and "restarted" in first.error
        assert reloaded.prune(days=90, max_runs=0, now=now) == 1        # the January run
        assert reloaded.prune(days=0, max_runs=2, now=now) == 1         # keep the newest two
        assert {r.id[:8] for r, in [(x,) for x in reloaded.list()[0]]} == {"20260905", "20260906"}
