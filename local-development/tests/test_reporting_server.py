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
        for path in (f"{REPORT_PREFIX}/api/reports", f"{REPORT_PREFIX}/api/runs", f"{REPORT_PREFIX}/api/snapshot",
                     f"{REPORT_PREFIX}/api/usage", f"{REPORT_PREFIX}/api/namespace-count?cluster=x"):
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

    def test_the_manifest_loader_defaults_origin_and_tolerates_unknown_keys(self, tmp_path):
        """P4 (design §5): origin defaults to 'viewer' for a manifest written before the field existed,
        and an UNKNOWN key from a newer binary's manifest is dropped on load — NOT TypeError'd into the
        run being lost from the index (the rollback downgrade trap #131 named)."""
        import json as _json
        root = tmp_path / "a"
        old = Run(id="20260906T120000.000000Z-0001", report="groups", cluster="c1", params={}, formats=["html"],
                  generated_by="root", generated_by_note="n", schedule=None, requested_at="2026-09-06T12:00:00Z",
                  status="done")
        ArtifactStore(str(root)).create(old)
        man = _json.loads((root / old.id / "run.json").read_text())
        assert "origin" in man, "a run written now carries origin"
        del man["origin"]                                   # a pre-P4 manifest
        man["a_future_field"] = {"nested": 1}               # a newer binary's extra key
        (root / old.id / "run.json").write_text(_json.dumps(man))
        r = ArtifactStore(str(root)).get(old.id)
        assert r is not None, "the run is not dropped from the index"
        assert r.origin == "viewer", "no origin defaults to viewer (never mistaken for automated)"

    def test_a_persisted_schedule_origin_round_trips(self, tmp_path):
        root = tmp_path / "a"
        run = Run(id="20260906T120000.000000Z-0002", report="groups", cluster="c1", params={}, formats=["html"],
                  generated_by="svc", generated_by_note="n", schedule="nightly", requested_at="2026-09-06T12:00:00Z",
                  status="done", origin="schedule")
        ArtifactStore(str(root)).create(run)
        assert ArtifactStore(str(root)).get(run.id).origin == "schedule"


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


class TestNamespaceSelectorsOnTheCatalogue:
    """B3 (#117 C1): list_reports carries per-cluster {label, values} for the namespace-access
    multi-select. B3 is the first caller to open a snapshot from the catalogue, so a missing,
    unreadable or CORRUPT copy must degrade to an empty map and a 200 — never a 500 that takes the
    whole Reports tab down. The suite had no test hitting namespaceSelectors before this."""

    def test_the_catalogue_gathers_the_selector_values_in_one_query(self, tmp_path, monkeypatch):
        # V4-F1 (2nd pass): the per-cluster-per-key gather was N+1; the batched dimensions read the whole
        # estate in ONE cluster_namespace_label query, however many clusters and dimensions.
        from gsd.store import Store
        from gsd.reporting.snapshot import Snapshot
        snapshots, artifacts = tmp_path / "snap", tmp_path / "art"
        snapshots.mkdir(); artifacts.mkdir()
        store = Store(str(tmp_path / "w.db"))
        for i in range(12):
            cid = f"c{i}"
            store.upsert_cluster(cid, f"https://api.{cid}:6443", True)
            store.replace_namespaces(cid, [
                {"name": f"{cid}-a", "created_at": None, "phase": "Active",
                 "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}}],
                "2026-09-14T00:00:00Z")
        assert store.snapshot(str(snapshots), keep=2); store.close()
        app = build_report_app(
            _settings(snapshots, artifacts,
                      namespace_selector_labels=("company.net/mnemonic", "company.net/app-environment")),
            secret=SECRET, clock=lambda: FROZEN)
        calls = []
        real_rows = Snapshot._rows
        monkeypatch.setattr(Snapshot, "_rows", lambda self, sql, params=(): (calls.append(sql), real_rows(self, sql, params))[1])
        with TestClient(app) as client:
            body = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()
        assert len(body["namespaceSelectorDimensions"]) == 12 and len(body["namespaceSelectors"]) == 12
        assert sum("FROM cluster_namespace_label" in sql for sql in calls) == 1, calls

    def test_per_cluster_label_and_values_when_the_selector_is_configured(self, tmp_path):
        from gsd.store import Store
        snapshots, artifacts = tmp_path / "snap", tmp_path / "art"
        snapshots.mkdir(); artifacts.mkdir()
        label = "company.net/mnemonic"
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc-local", "https://api.crc.testing:6443", True)
        store.upsert_cluster("prod-east", "https://api.prod-east:6443", True)
        store.replace_namespaces("crc-local", [
            {"name": "beta-ns", "created_at": None, "phase": "Active", "metadata": {label: "beta"}},
            {"name": "demo-ns", "created_at": None, "phase": "Active", "metadata": {label: "demo"}},
        ], "2026-09-14T00:00:00Z")
        store.replace_namespaces("prod-east", [
            {"name": "gamma-ns", "created_at": None, "phase": "Active", "metadata": {label: "gamma"}},
        ], "2026-09-14T00:00:00Z")
        assert store.snapshot(str(snapshots), keep=2)
        store.close()
        app = build_report_app(_settings(snapshots, artifacts, namespace_selector_labels=(label,)),
                               secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            r = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer())
            assert r.status_code == 200
            sel = r.json()["namespaceSelectors"]
            assert sel["crc-local"] == {"label": label, "values": ["beta", "demo"]}
            assert sel["prod-east"] == {"label": label, "values": ["gamma"]}

    def test_empty_label_yields_empty_values_not_a_query(self, tmp_path):
        # The default deployment configures no selector label: every cluster is present with an
        # empty value list, so the GUI hides the control rather than guessing a key.
        snapshots, artifacts = seeded_dirs(tmp_path)
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            sel = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()["namespaceSelectors"]
            assert sel[CLUSTER] == {"label": "", "values": []}

    def test_missing_snapshot_directory_is_200_with_an_empty_map(self, tmp_path):
        artifacts = tmp_path / "art"; artifacts.mkdir()
        app = build_report_app(_settings(tmp_path / "no-such-snap", artifacts),
                               secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            r = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer())
            assert r.status_code == 200
            assert r.json()["namespaceSelectors"] == {}
            assert r.json()["namespaceSelectorDimensions"] == {}   # degrade both maps (review #129 N5)

    def test_a_corrupt_snapshot_is_200_with_an_empty_map_not_500(self, tmp_path):
        # A file named like a copy (passes the stamp check) but not a SQLite database. Snapshot's
        # PRAGMA read raises sqlite3.DatabaseError, which is neither SnapshotError nor OSError; before
        # the C1 fix that escaped list_reports as a 500. Snapshot.__init__ now translates it to
        # SnapshotError at the backend boundary (the storage seam keeps sqlite3 out of server.py), so
        # the catalogue's existing except (SnapshotError, OSError) degrades to an empty map.
        snapshots, artifacts = tmp_path / "snap", tmp_path / "art"
        snapshots.mkdir(); artifacts.mkdir()
        (snapshots / "gsd-20260914T000000.000000Z.db").write_bytes(b"this is not a sqlite database")
        app = build_report_app(_settings(snapshots, artifacts, namespace_selector_labels=("company.net/mnemonic",)),
                               secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer())
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["namespaceSelectors"] == {}
            assert body["namespaceSelectorDimensions"] == {}   # degrade both maps (review #129 N5)
            assert len(body["reports"]) == 11

    @pytest.mark.parametrize("needle", ["FROM cluster c", "FROM cluster_namespace_label"])
    def test_a_table_read_after_a_clean_open_that_fails_is_200_not_500(self, tmp_path, monkeypatch, needle):
        # #117 second pass (Codex D1): a copy can pass Snapshot.__init__ (connect/PRAGMA/sqlite_master
        # all read cleanly) and then raise sqlite3.Error from a TABLE read — partial b-tree damage on a
        # copy that rotted on disk after it was written. The __init__ wrap does not see that; the gather
        # must. Snapshot.namespace_selector_dimensions wraps the clusters() and cluster_namespace_label
        # reads, so the catalogue still degrades to {} and 200. Forcing the specific read to raise proves
        # it (500 before the gather was moved behind SnapshotError). The seam holds: no sqlite3 in server.py.
        from gsd.reporting.snapshot import Snapshot
        snapshots, artifacts = seeded_dirs(tmp_path)
        real_rows = Snapshot._rows

        def failing_rows(self, sql, params=()):
            if needle in sql:
                raise sqlite3.OperationalError("simulated post-open snapshot damage")
            return real_rows(self, sql, params)

        monkeypatch.setattr(Snapshot, "_rows", failing_rows)
        app = build_report_app(_settings(snapshots, artifacts, namespace_selector_labels=("company.net/mnemonic",)),
                               secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app, raise_server_exceptions=False) as client:
            r = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer())
            assert r.status_code == 200, r.text
            assert r.json()["namespaceSelectors"] == {}
            assert r.json()["namespaceSelectorDimensions"] == {}   # degrade both maps (review #129 N5)


class TestNamespaceCountPreview:
    """P2 #107: the read-only GET count of namespaces the selectors expand to, shown beside Generate."""

    def _app(self, tmp_path):
        from gsd.store import Store
        snapshots, artifacts = tmp_path / "snap", tmp_path / "art"
        snapshots.mkdir(); artifacts.mkdir()
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc-local", "https://k8s", True)
        store.replace_namespaces("crc-local", [
            {"name": "demo-prod", "created_at": None, "phase": "Active",
             "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"}},
            {"name": "demo-qa", "created_at": None, "phase": "Active",
             "metadata": {"company.net/mnemonic": "demo", "company.net/app-environment": "qa"}},
            {"name": "beta-prod", "created_at": None, "phase": "Active",
             "metadata": {"company.net/mnemonic": "beta", "company.net/app-environment": "prod"}},
        ], "2026-09-14T00:00:00Z")
        assert store.snapshot(str(snapshots), keep=2); store.close()
        return build_report_app(
            _settings(snapshots, artifacts, enabled_reports=("namespace-access",),
                      namespace_selector_labels=("company.net/mnemonic", "company.net/app-environment")),
            secret=SECRET, clock=lambda: FROZEN)

    def test_count_for_a_two_dimension_selection(self, tmp_path):
        import json as _json
        with TestClient(self._app(tmp_path)) as client:
            sel = _json.dumps({"company.net/mnemonic": ["demo"], "company.net/app-environment": ["prod"]})
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": sel}, headers=_viewer())
            assert r.status_code == 200, r.text
            assert r.json() == {"namespaces": 1, "names": ["demo-prod"]}          # only demo-prod
            sel2 = _json.dumps({"company.net/app-environment": ["prod"]})
            r2 = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                            params={"cluster": "crc-local", "selectors": sel2}, headers=_viewer())
            assert r2.json() == {"namespaces": 2, "names": ["beta-prod", "demo-prod"]}   # sorted

    def test_null_for_empty_or_malformed_selection(self, tmp_path):
        with TestClient(self._app(tmp_path)) as client:
            for bad in ("", "notjson", "{}", '{"company.net/mnemonic": []}'):
                r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                               params={"cluster": "crc-local", "selectors": bad}, headers=_viewer())
                assert r.status_code == 200 and r.json() == {"namespaces": None}, (bad, r.text)

    def test_null_for_a_string_value_or_unconfigured_label(self, tmp_path):
        import json as _json
        with TestClient(self._app(tmp_path)) as client:
            for bad in ({"company.net/mnemonic": "demo"}, {"company.net/not-configured": ["demo"]}):
                r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                               params={"cluster": "crc-local", "selectors": _json.dumps(bad)}, headers=_viewer())
                assert r.status_code == 200 and r.json() == {"namespaces": None}, (bad, r.text)

    def test_a_table_read_after_a_clean_open_is_null_not_500(self, tmp_path, monkeypatch):
        # The count path calls namespaces_for_selectors, which now wraps sqlite3.Error -> SnapshotError
        # so a post-open table read degrades to null, not a 500 (review #129 C6; the #117 D1 scar).
        from gsd.reporting.snapshot import Snapshot
        real_rows = Snapshot._rows

        def failing_rows(self, sql, params=()):
            if "FROM cluster_namespace_label" in sql:
                raise sqlite3.OperationalError("simulated post-open snapshot damage")
            return real_rows(self, sql, params)

        monkeypatch.setattr(Snapshot, "_rows", failing_rows)
        with TestClient(self._app(tmp_path), raise_server_exceptions=False) as client:
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": '{"company.net/mnemonic": ["demo"]}'},
                           headers=_viewer())
            assert r.status_code == 200 and r.json() == {"namespaces": None}, r.text

    def test_an_unknown_selector_label_is_422_not_a_failed_run(self, tmp_path):
        # create_run refuses an unconfigured selector label up front (review #129 N1) — no stored failed run.
        with TestClient(self._app(tmp_path)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs",
                            json={"report": "namespace-access", "cluster": "crc-local",
                                  "params": {"selectors": {"company.net/nope": ["x"]}}, "formats": ["html"]},
                            headers=_viewer())
            assert r.status_code == 422, r.text
            assert "not configured" in r.json()["detail"]
            assert client.get(f"{REPORT_PREFIX}/api/runs", headers=_viewer()).json()["total"] == 0

    def test_create_run_still_202s_mnemonics_namespaces_and_valid_selectors(self, tmp_path):
        # The subset check must NOT refuse the three legitimate selection shapes (review #129 2nd pass, V1).
        with TestClient(self._app(tmp_path)) as client:
            h = _viewer()
            for params in ({"namespaces": "demo-prod"}, {"mnemonics": ["demo"]},
                           {"selectors": {"company.net/mnemonic": ["demo"], "company.net/app-environment": ["prod"]}}):
                r = client.post(f"{REPORT_PREFIX}/api/runs", json={
                    "report": "namespace-access", "cluster": "crc-local", "params": params, "formats": ["html"]}, headers=h)
                assert r.status_code == 202, (params, r.text)

    def test_a_configured_label_matching_nothing_counts_zero_not_null(self, tmp_path):
        import json as _json
        with TestClient(self._app(tmp_path)) as client:
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": _json.dumps({"company.net/mnemonic": ["no-such"]})},
                           headers=_viewer())
            assert r.status_code == 200 and r.json() == {"namespaces": 0, "names": []}, r.text

    def test_a_match_names_the_namespaces_and_null_paths_carry_no_names_key(self, tmp_path):
        # #143: the count names what it counts, sorted (namespaces_for_selectors' order); every null
        # path stays byte-identical to #107 — {"namespaces": None} with NO names key.
        import json as _json
        with TestClient(self._app(tmp_path)) as client:
            sel = _json.dumps({"company.net/mnemonic": ["demo", "beta"], "company.net/app-environment": ["prod"]})
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": sel}, headers=_viewer())
            assert r.status_code == 200, r.text
            assert r.json() == {"namespaces": 2, "names": ["beta-prod", "demo-prod"]}
            for bad in ("notjson", "{}", '{"company.net/not-configured": ["demo"]}'):
                r2 = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                                params={"cluster": "crc-local", "selectors": bad}, headers=_viewer())
                assert r2.json() == {"namespaces": None} and "names" not in r2.json(), (bad, r2.text)

    def test_the_names_are_capped_while_the_count_stays_full(self, tmp_path):
        # #143: past NAMESPACE_PREVIEW_NAMES_CAP the body carries the first CAP sorted names while
        # `namespaces` keeps the FULL length, so the form can say "… and N more not shown".
        import json as _json
        from gsd.reporting.server import NAMESPACE_PREVIEW_NAMES_CAP as CAP
        from gsd.store import Store
        snapshots, artifacts = tmp_path / "snap", tmp_path / "art"
        snapshots.mkdir(); artifacts.mkdir()
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc-local", "https://k8s", True)
        store.replace_namespaces("crc-local", [
            {"name": f"demo-{i:04d}", "created_at": None, "phase": "Active",
             "metadata": {"company.net/mnemonic": "demo"}} for i in range(CAP + 3)
        ], "2026-09-14T00:00:00Z")
        assert store.snapshot(str(snapshots), keep=2); store.close()
        app = build_report_app(
            _settings(snapshots, artifacts, enabled_reports=("namespace-access",),
                      namespace_selector_labels=("company.net/mnemonic",)),
            secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": _json.dumps({"company.net/mnemonic": ["demo"]})},
                           headers=_viewer())
            body = r.json()
            assert body["namespaces"] == CAP + 3                                # the FULL count
            assert len(body["names"]) == CAP
            assert body["names"] == [f"demo-{i:04d}" for i in range(CAP)]       # sorted, the first CAP

    def test_json_recursion_error_is_null_not_500(self, tmp_path, monkeypatch):
        # json.loads answers deeply-nested input with RecursionError (not a ValueError), which escaped the
        # endpoint's catch as a 500 against its "bad input returns null" contract (review, Fable F1). httpx
        # rejects a 100k-char query URL before the app sees it, so the wire payload is simulated at the
        # decoder (Codex: the TestClient path can't carry it; monkeypatch json.loads instead).
        from gsd.reporting import server as report_server
        real_loads = report_server.json.loads

        def loads(value, *args, **kwargs):
            if value == "trip-recursion":
                raise RecursionError("simulated decoder depth guard")
            return real_loads(value, *args, **kwargs)

        monkeypatch.setattr(report_server.json, "loads", loads)
        with TestClient(self._app(tmp_path), raise_server_exceptions=False) as client:
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": "trip-recursion"}, headers=_viewer())
            assert r.status_code == 200 and r.json() == {"namespaces": None}, r.text

    def test_a_pre_capture_snapshot_returns_unknown_not_zero(self, tmp_path):
        # A copy with no cluster_namespace_label table (an older dashboard's copy) must answer null, not
        # an attested 0 (review, Fable N3 / Codex).
        app = self._app(tmp_path)
        copy = next((tmp_path / "snap").glob("gsd-*.db"))
        with sqlite3.connect(copy) as db:
            db.execute("DROP TABLE cluster_namespace_label")
            db.execute("PRAGMA user_version = 11")
        with TestClient(app) as client:
            r = client.get(f"{REPORT_PREFIX}/api/namespace-count",
                           params={"cluster": "crc-local", "selectors": '{"company.net/mnemonic": ["demo"]}'},
                           headers=_viewer())
            assert r.status_code == 200 and r.json() == {"namespaces": None}, r.text


class TestReportingWindowGate:
    """The create_run reporting-window gate (design §5): automated origins (schedule/service) are
    refused OUTSIDE the window with 409 + Retry-After; a human's viewer run is never gated; the refusal
    is counted (no names). Fixed clocks + tickets minted at the same instant keep it deterministic."""

    SAT_0300 = datetime(2026, 9, 19, 3, 0, tzinfo=UTC)     # Saturday 03:00 — outside a Mon-Fri 09-17 window
    MON_1000 = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)    # Monday 10:00 — inside

    def _app(self, tmp_path, clock_dt):
        from gsd.reporting.window import ReportingWindow
        snapshots, artifacts = seeded_dirs(tmp_path)
        w = ReportingWindow.from_strings(enabled=True, timezone="UTC", start="09:00", end="17:00",
                                         days=["Mon", "Tue", "Wed", "Thu", "Fri"])
        return build_report_app(_settings(snapshots, artifacts, window=w), secret=SECRET, clock=lambda: clock_dt)

    def test_service_outside_window_is_409_with_retry_after_and_is_counted(self, tmp_path):
        with TestClient(self._app(tmp_path, self.SAT_0300)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs",
                            json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 409, r.text
            assert int(r.headers["Retry-After"]) > 0
            m = client.get(f"{REPORT_PREFIX}/metrics").text
            line = next(l for l in m.splitlines()
                        if l.startswith('gsd_report_runs_outside_window_total{origin="schedule"}'))
            assert float(line.split()[-1]) >= 1

    def test_a_bare_service_run_with_no_schedule_is_also_gated(self, tmp_path):
        with TestClient(self._app(tmp_path, self.SAT_0300)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs",
                            json={"report": "groups", "cluster": CLUSTER}, headers=SERVICE)   # no schedule
            assert r.status_code == 409, "a service curl with no schedule is still automated (gate on origin, not body.schedule)"

    def test_a_viewer_is_never_gated(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(self.SAT_0300.timestamp())),
                  USER_HEADER: "root"}
        with TestClient(self._app(tmp_path, self.SAT_0300)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs",
                            json={"report": "groups", "cluster": CLUSTER}, headers=ticket)
            assert r.status_code == 202, r.text          # admitted despite being outside the window

    def test_service_inside_window_is_admitted(self, tmp_path):
        with TestClient(self._app(tmp_path, self.MON_1000)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs",
                            json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 202, r.text
            assert r.json()["origin"] == "schedule"      # origin is persisted on the run

    def test_a_service_schedule_label_is_bounded_to_a_dns_label(self, tmp_path):
        # A service token must not put a person's name into the public /metrics label
        # gsd_report_schedule_last_success_timestamp{schedule=...} (review of P4, C7).
        with TestClient(self._app(tmp_path, self.MON_1000)) as client:
            bad = client.post(f"{REPORT_PREFIX}/api/runs",
                              json={"report": "groups", "cluster": CLUSTER, "schedule": "Alice Smith"}, headers=SERVICE)
            assert bad.status_code == 422 and "DNS label" in bad.json()["detail"]
            ok = client.post(f"{REPORT_PREFIX}/api/runs",
                             json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            assert ok.status_code == 202

    def test_the_gate_id_and_requested_at_come_from_one_instant(self, tmp_path):
        # C3: one now() call feeds the gate, the id and requested_at, so a clock advancing between
        # separate calls cannot admit a run in-window and then stamp it from a later instant.
        import itertools
        from datetime import timedelta
        from gsd.reporting.window import ReportingWindow
        snapshots, artifacts = seeded_dirs(tmp_path)
        w = ReportingWindow.from_strings(enabled=True, timezone="UTC", start="09:00", end="17:00",
                                         days=["Mon", "Tue", "Wed", "Thu", "Fri"])
        base = datetime(2026, 9, 14, 10, 0, 0, tzinfo=UTC)
        ticks = itertools.count()
        app = build_report_app(_settings(snapshots, artifacts, window=w), secret=SECRET,
                               clock=lambda: base + timedelta(seconds=next(ticks)))
        with TestClient(app) as client:
            run = client.post(f"{REPORT_PREFIX}/api/runs",
                              json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"},
                              headers=SERVICE).json()
        id_hhmmss = run["id"].split("-")[0][9:15]                 # HHMMSS of %Y%m%dT%H%M%S.%fZ
        req_hhmmss = run["requested_at"][11:19].replace(":", "")  # HHMMSS of HH:MM:SS
        assert id_hhmmss == req_hhmmss, (run["id"], run["requested_at"])


class TestWorkerWindowRecheck:
    """The worker's belt (design §5): a queued automated run whose requested_at was never inside the
    window is failed at render with a reason and counted outside-window. It entered through submit()
    (counted SUBMITTED), so the recheck failure must count it FINISHED too, or
    gsd_report_runs_submitted_total minus finished_total reads as one run in flight for ever (P4, C5)."""

    def test_a_recheck_failed_run_is_counted_finished(self, tmp_path):
        from gsd.reporting.window import ReportingWindow
        snapshots, artifacts = seeded_dirs(tmp_path)
        w = ReportingWindow.from_strings(enabled=True, timezone="UTC", start="09:00", end="17:00",
                                         days=["Mon", "Tue", "Wed", "Thu", "Fri"])
        calls = []

        class Recorder:
            def note_submitted(self, report): calls.append(("submitted", report))
            def note_finished(self, report, status, seconds, size): calls.append(("finished", report, status))
            def note_outside_window(self, origin): calls.append(("outside", origin))
            def note_schedule_success(self, schedule, when): calls.append(("schedule_success", schedule))

        store = ArtifactStore(str(artifacts))
        rm = RunManager(_settings(snapshots, artifacts, window=w), store, Recorder(),
                        clock=lambda: datetime(2026, 9, 19, 3, 5, tzinfo=UTC))
        run = Run(id="20260919T030000.000000Z-0001", report="groups", cluster=CLUSTER, params={},
                  formats=["html"], generated_by="schedule:nightly",
                  generated_by_note="unattended (service token)", schedule="nightly",
                  requested_at="2026-09-19T03:00:00Z", origin="schedule")   # Saturday: never inside Mon-Fri 09-17
        rm.submit(run)
        rm._render(store.get(run.id))
        failed = store.get(run.id)
        assert failed.status == "failed" and "outside the reporting window" in failed.error
        assert failed.finished_at is not None
        assert ("submitted", "groups") in calls and ("outside", "schedule") in calls
        assert not any(c[0] == "schedule_success" for c in calls)
        assert ("finished", "groups", "failed") in calls, "a recheck-failed run must balance submitted/finished"


class TestScheduleLastSuccessSurvivesRestart:
    """F4: the last-success gauge is process-local; a fresh app must re-arm it from the durable run
    manifests (the newest DONE run per schedule), or the §5 evidence-gap monitor goes blind after a
    restart until the next success."""

    def test_the_gauge_is_seeded_from_the_index(self, tmp_path):
        snapshots, artifacts = seeded_dirs(tmp_path)
        store = ArtifactStore(str(artifacts))
        def mk(rid, status, sched, fin):
            return Run(id=rid, report="groups", cluster=CLUSTER, params={}, formats=["html"],
                       generated_by=f"schedule:{sched}", generated_by_note="n", schedule=sched,
                       requested_at="2026-09-14T00:00:00Z", status=status, finished_at=fin, origin="schedule")
        store.create(mk("20260914T090000.000000Z-0001", "done", "nightly", "2026-09-14T09:00:03Z"))
        store.create(mk("20260915T090000.000000Z-0002", "done", "nightly", "2026-09-15T09:00:05Z"))   # newest done
        store.create(mk("20260916T090000.000000Z-0003", "failed", "nightly", "2026-09-16T09:00:00Z"))  # newer, failed
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            m = client.get(f"{REPORT_PREFIX}/metrics").text
        line = next(l for l in m.splitlines()
                    if l.startswith('gsd_report_schedule_last_success_timestamp{schedule="nightly"}'))
        expect = datetime(2026, 9, 15, 9, 0, 5, tzinfo=UTC).timestamp()   # the newest DONE run's finished_at
        assert abs(float(line.split()[-1]) - expect) < 1.0, line
