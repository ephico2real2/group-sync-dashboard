"""The report service's API (docs/specs/SPEC_C3_reporting_microservice.md §9.7): its own contract, the doors
(ticket, service token), the run lifecycle and the usage feed."""
from __future__ import annotations

import inspect
import sqlite3
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
# Tickets are minted at T0, and EVERY app under test runs on a clock frozen at T0 + 10 — the fixture's
# and the ad-hoc ones alike. Measured 2026-09-11: the full suite collects this module at session start
# and reaches it after the 300 s ticket TTL, and the three tests that built their app on the real
# clock then answered 401 to every request (a KeyError on "id"), green whenever the module ran alone.
T0 = int(time.time())
FROZEN = datetime.fromtimestamp(T0 + 10, UTC)


def _settings(snapshots, artifacts, **over) -> ReportSettings:
    base = dict(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=True, pdf_variant="pdf/a-2b",
                font_regular=FONTS[0], font_bold=FONTS[1], login_capture_enabled=True)
    base.update(over)
    return ReportSettings(**base)


@pytest.fixture()
def service(tmp_path):
    snapshots, artifacts = seeded_dirs(tmp_path)
    clock = {"now": FROZEN}
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
        app = build_report_app(_settings(snapshots, artifacts, pdf_enabled=False, pdf_variant="", enabled_reports=("groups",)), secret=SECRET, clock=lambda: FROZEN)
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
        app = build_report_app(_settings(snapshots, artifacts, max_queued_runs=1), secret=SECRET, clock=lambda: FROZEN)
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
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 503
        (tmp_path / "two").mkdir()
        snapshots2, artifacts2 = seeded_dirs(tmp_path / "two")
        app = build_report_app(_settings(snapshots2, artifacts2), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 200
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "namespace-access", "cluster": CLUSTER, "params": {"namespaces": "prod-ns"}, "formats": ["html"]}, headers=_viewer())
            _wait_done(client, r.json()["id"], _viewer())
            text = client.get(f"{REPORT_PREFIX}/metrics").text
            assert 'gsd_report_runs_finished_total{report="namespace-access",status="done"} 1.0' in text
            assert "root" not in text and "gsd_report_snapshot_age_seconds" in text


class TestCellBounds:
    @pytest.mark.parametrize("group_name", ["\n" * 600, "界" * 600, "x" * 600, "W" * 600])
    def test_a_run_finishes_on_a_group_name_no_cell_can_draw_and_the_other_formats_are_lossless(self, tmp_path, group_name):
        """Codex and Cursor, review C3 second pass, through the catalogue rather than the renderer: a
        600-newline group name failed the run on the first-pass head (a 600-line row). The PDF renders,
        and the HTML and the JSON carry the name whole."""
        from reporting_seed import NOW, _iso, seed_store, write_snapshot
        snapshots, artifacts = tmp_path / "s", tmp_path / "a"
        snapshots.mkdir(); artifacts.mkdir()
        writer = seed_store(str(tmp_path / "writer.db"))
        try:
            writer.replace_group_state(CLUSTER, [{"name": group_name, "member_count": 0, "sync_provider": "corp_ldap",
                                                  "group_synced_at": _iso(NOW), "ldap_uid": None}], _iso(NOW))
            write_snapshot(writer, snapshots)
        finally:
            writer.close()
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["html", "pdf"]}, headers=_viewer())
            assert r.status_code == 202, r.text
            run = _wait_done(client, r.json()["id"], _viewer())
            assert run["status"] == "done", run.get("error")
            got = {fmt: client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": fmt}, headers=_viewer()) for fmt in ("json", "html", "pdf")}
            assert all(g.status_code == 200 for g in got.values()), {k: v.status_code for k, v in got.items()}
            assert got["pdf"].content.startswith(b"%PDF")
            assert group_name in got["html"].text
            # The JSON escapes newlines and non-ASCII, so look for the value, not its spelling.
            def holds(node, needle) -> bool:
                if node == needle:
                    return True
                if isinstance(node, dict):
                    return any(holds(v, needle) for v in node.values())
                return isinstance(node, list) and any(holds(v, needle) for v in node)
            assert holds(got["json"].json(), group_name)


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

    def test_prune_does_not_delete_a_queued_run_still_in_the_index(self, tmp_path):
        """Cursor, review C3: finish order is not id order. A 202'd run that is still queued must
        survive prune — deleting its directory made GET /runs/{id} a 404 and the worker skip it."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        def make(run_id, status):
            return Run(id=run_id, report="groups", cluster="c1", params={}, formats=["html"], generated_by="root",
                       generated_by_note="n", schedule=None, requested_at="2026-09-06T12:00:00Z", status=status)
        queued, done = make("20260906T120000.000000Z-0001", "queued"), make("20260906T120001.000000Z-0002", "done")
        store.create(queued); store.create(done)
        store.prune(days=0, max_runs=1, now=now)
        assert store.get(queued.id) is not None and store.get(done.id) is not None
        assert store.write(queued.id, "html", b"<p>") == 3, "write recreates a directory prune may have taken"

    def test_usage_does_not_advance_past_an_in_flight_older_run(self, tmp_path):
        """Cursor, review C3: a QueueFull failure has the newest id and finishes at once; publishing it
        while older runs are in flight moved the dashboard's MAX(id) watermark past them for ever."""
        from gsd.store import Store
        arts = ArtifactStore(str(tmp_path / "a"))
        def make(run_id, status, error=None):
            return Run(id=run_id, report="groups", cluster="c1", params={}, formats=["html"], generated_by="root",
                       generated_by_note="n", schedule=None, requested_at="2026-09-06T12:00:00Z", status=status, error=error,
                       finished_at="2026-09-06T12:00:01Z" if status == "failed" else None)
        older = make("20260906T120000.000000Z-0001", "queued")
        newer = make("20260906T120001.000000Z-0002", "failed", "the render queue is full; try again shortly")
        arts.create(older); arts.create(newer)
        assert [r.id for r in arts.since(None, 500)] == [], "a finished run newer than an in-flight run is not visible yet"
        db = Store(str(tmp_path / "w.db"))
        db.record_report_runs([r.public() for r in arts.since(None, 500)], "2026-09-06T12:00:02Z")
        assert db.report_runs_watermark() is None
        older.status, older.finished_at = "done", "2026-09-06T12:00:10Z"
        arts.update(older)
        page = arts.since(None, 500)
        assert [r.id for r in page] == [older.id, newer.id]
        db.record_report_runs([r.public() for r in page], "2026-09-06T12:00:11Z")
        assert db.report_runs_watermark() == newer.id
        db.close()


class TestRequestHygiene:
    def test_a_cluster_id_that_could_inject_a_header_is_refused(self, service):
        """Cursor, review C3: the artefact's Content-Disposition carries the cluster id; a quote or a
        newline in it is header injection unless the id is constrained. It is."""
        client, _, _ = service
        for bad in ('crc"; x="y', "crc\r\nX-Injected: 1", "", "a" * 64, "/etc"):
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": bad, "formats": ["html"]}, headers=_viewer())
            assert r.status_code == 422, (bad, r.status_code)

    def test_probes_close_the_snapshot_they_open(self, service):
        """Cursor, review C3: an open copy pins the file the writer wants to prune; the probes open
        and close within the request."""
        import gc
        from gsd.reporting import snapshot as snapmod
        client, _, _ = service
        opened = []
        real_init = snapmod.Snapshot.__init__
        def counting_init(self, path):
            real_init(self, path); opened.append(self)
        snapmod.Snapshot.__init__ = counting_init
        try:
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 200
            assert client.get(f"{REPORT_PREFIX}/api/snapshot", headers=_viewer()).status_code == 200
            assert client.get(f"{REPORT_PREFIX}/metrics").status_code == 200
        finally:
            snapmod.Snapshot.__init__ = real_init
        assert len(opened) >= 3
        for snap in opened:
            with pytest.raises(sqlite3.ProgrammingError):        # closed connection
                snap._conn.execute("SELECT 1")
