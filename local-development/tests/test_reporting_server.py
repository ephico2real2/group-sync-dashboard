"""The report service's API (docs/specs/SPEC_C3_reporting_microservice.md §9.7): its own contract, the doors
(ticket, service token), the run lifecycle and the usage feed."""
from __future__ import annotations

import inspect
import json
import sqlite3
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd.activity import USER_HEADER
from gsd.reporting import REPORT_PREFIX, TICKET_HEADER
from gsd.reporting.artifacts import ArtifactStore, Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.runs import QueueFull, RunManager
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
        # the run POST, and the read-only preview POST beside it (#143 phase 3: build() for the totals,
        # nothing rendered, nothing stored — the one-write contract of the dashboard's API is untouched)
        assert sorted(non_get) == [("POST", f"{REPORT_PREFIX}/api/preview"), ("POST", f"{REPORT_PREFIX}/api/runs")]
        # and the module says so itself (review of #224, OB3: the docstring still claimed one and only one non-GET)
        import gsd.reporting.server as _srv
        assert "api/preview" in _srv.__doc__ and "api/runs" in _srv.__doc__

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
        assert reloaded.prune(scheduled_keep=0, scheduled_days=0, manual_days=90, manual_max_runs=0, now=now) == 1  # the January run
        assert reloaded.prune(scheduled_keep=0, scheduled_days=0, manual_days=0, manual_max_runs=2, now=now) == 1   # keep the newest two
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
        store.prune(scheduled_keep=0, scheduled_days=0, manual_days=0, manual_max_runs=1, now=now)
        assert store.get(queued.id) is not None and store.get(done.id) is not None
        assert store.write(queued.id, "html", b"<p>") == 3, "write recreates a directory prune may have taken"

    def test_a_manual_burst_never_evicts_a_scheduled_report(self, tmp_path):
        """R2, the live bug: the single run-count cap sliced ALL finished runs by id, so a burst of
        manual runs pushed a still-valid scheduled report past max_runs and deleted it. The two-tier
        prune keeps scheduled runs cap-exempt (within keepPerSchedule per (schedule, cluster) OR younger
        than scheduled_days), so the scheduled report survives the burst."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        def mk(run_id, when, schedule=None):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={},
                             formats=["html"], generated_by=(f"schedule:{schedule}" if schedule else "root"),
                             generated_by_note="n", schedule=schedule, requested_at=when, status="done"))

        # One scheduled run 40 days old (well inside scheduled days=90) ...
        mk("20260728T000000.000000Z-aaaa", "2026-07-28T00:00:00Z", schedule="quarterly-compliance")
        # ... then 600 recent manual runs (all inside manual days=3, so the run-count cap is the bound).
        base = datetime(2026, 9, 6, 0, 0, tzinfo=UTC)
        for i in range(600):
            t = base + timedelta(seconds=i)
            mk(t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-{i:04x}", t.strftime("%Y-%m-%dT%H:%M:%SZ"))

        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now)
        survivors = {r.id for r in store.list(limit=10000)[0]}
        assert "20260728T000000.000000Z-aaaa" in survivors, "the scheduled report must survive a manual burst"
        assert pruned == 100, "only the 100 manual runs beyond the 500 cap are pruned; scheduled is cap-exempt"
        assert sum(1 for r in store.list(limit=10000)[0] if not r.schedule) == 500

    def test_scheduled_keep_is_per_schedule_and_cluster_and_survives_days(self, tmp_path):
        """Newest keepPerSchedule per (schedule, cluster) survive past scheduled_days; beyond K only the
        young survive. Two clusters under one schedule keep their own newest K independently."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        def mk(run_id, when, cluster, schedule):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=cluster, params={},
                             formats=["html"], generated_by=f"schedule:{schedule}", generated_by_note="n",
                             schedule=schedule, requested_at=when, status="done"))

        # Three OLD runs (Feb, ~217 days ago, past scheduled_days=90) per cluster, one schedule.
        for ci, cluster in enumerate(("east", "west")):
            for j in range(3):
                t = datetime(2026, 2, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=ci * 10 + j)
                mk(t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-{ci}{j}", t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   cluster, "quarterly-compliance")

        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now)
        assert pruned == 2, "each cluster keeps its newest 2; the 3rd (oldest, past days) is pruned"
        kept = store.list(limit=10000)[0]
        for cluster in ("east", "west"):
            assert sum(1 for r in kept if r.cluster == cluster) == 2

    def test_a_young_scheduled_run_beyond_keep_is_not_deleted(self, tmp_path):
        """keepPerSchedule is a FLOOR, not a ceiling: beyond the newest K but younger than
        scheduled_days must still survive. Raised by the adversarial review (Cursor, C2) — the
        all-February test above would pass even for a wrong 'drop everyone past K' predicate,
        because there every beyond-K run is also past the age bound."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        def mk(run_id, when, schedule="quarterly-compliance"):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={},
                             formats=["html"], generated_by=f"schedule:{schedule}", generated_by_note="n",
                             schedule=schedule, requested_at=when, status="done"))

        # Three OLD (February, past days=90) and three YOUNG (10 days) under one (schedule, cluster).
        for j in range(3):
            t = datetime(2026, 2, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=j)
            mk(t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-o{j}", t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        young = []
        for j in range(3):
            t = datetime(2026, 8, 27, 0, 0, tzinfo=UTC) + timedelta(seconds=j)
            rid = t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-y{j}"
            young.append(rid)
            mk(rid, t.strftime("%Y-%m-%dT%H:%M:%SZ"))

        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now)
        kept = {r.id for r in store.list(limit=10000)[0]}
        assert pruned == 3, "only the three February runs are both beyond K and past days"
        assert young[0] in kept, "the oldest young run is beyond keep=2 but inside 90 days — it must survive"
        assert all(y in kept for y in young)

    def test_per_schedule_retention_override_wins(self, tmp_path):
        """overrides[name] = (keep, days) beats the globals for that schedule; another schedule inherits."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        def mk(run_id, when, schedule):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={},
                             formats=["html"], generated_by=f"schedule:{schedule}", generated_by_note="n",
                             schedule=schedule, requested_at=when, status="done"))

        # Five OLD runs under a quarterly schedule we override to keep 12; three under a schedule that
        # inherits keep=2. All are past the global days=90 so the keep bound is what decides.
        for j in range(5):
            t = datetime(2026, 2, 1, 0, 0, tzinfo=UTC) + timedelta(seconds=j)
            mk(t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-a{j}", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "quarterly-compliance")
        for j in range(3):
            t = datetime(2026, 2, 2, 0, 0, tzinfo=UTC) + timedelta(seconds=j)
            mk(t.strftime("%Y%m%dT%H%M%S.%fZ") + f"-b{j}", t.strftime("%Y-%m-%dT%H:%M:%SZ"), "biweekly-namespace-access")

        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now,
                             overrides={"quarterly-compliance": (12, 2555)})
        kept = store.list(limit=10000)[0]
        assert sum(1 for r in kept if r.schedule == "quarterly-compliance") == 5, "override keep=12 keeps all 5"
        assert sum(1 for r in kept if r.schedule == "biweekly-namespace-access") == 2, "inherits keep=2"
        assert pruned == 1

    def _done_run(self, store, run_id="20260906T120000.000000Z-0001"):
        run = Run(id=run_id, report="groups", cluster=CLUSTER, params={}, formats=["html"],
                  generated_by="root", generated_by_note="n", schedule=None,
                  requested_at="2026-09-06T12:00:00Z", status="done")
        store.create(run)
        store.write(run.id, "html", b"<p>evidence</p>")
        return run

    def test_retention_ages_a_run_from_completion_not_from_its_request(self, tmp_path):
        """#163. A manual run REQUESTED five days ago (its id says so) but FINISHED ten seconds ago must
        survive manual_days=3: retention protects an artefact, and this artefact is ten seconds old.
        On main, older_than() compared run.id[:15] against the cutoff and deleted it on the next prune."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        requested = now - timedelta(days=5)
        store.create(Run(id=requested.strftime("%Y%m%dT%H%M%S.%fZ") + "-slow", report="compliance-snapshot",
                         cluster=CLUSTER, params={}, formats=["html"], generated_by="root", generated_by_note="n",
                         schedule=None, requested_at=requested.strftime("%Y-%m-%dT%H:%M:%SZ"), status="done",
                         finished_at=(now - timedelta(seconds=10)).strftime("%Y-%m-%dT%H:%M:%SZ")))
        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now)
        assert pruned == 0, "a run whose artefact is ten seconds old is not three days old"
        assert len(store.list(limit=10)[0]) == 1

    def test_the_manual_cap_keeps_the_most_recently_completed_runs(self, tmp_path):
        """#163. Three manual runs, cap 2. `early` was requested FIRST but finished LAST (it waited in the
        queue); by completion it is the newest and must be kept, and the run that finished first is the
        one the cap drops. On main, "newest" sorted by id (request order) and dropped `early`."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)

        def mk(run_id, requested, finished):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={}, formats=["html"],
                             generated_by="root", generated_by_note="n", schedule=None,
                             requested_at=requested, status="done", finished_at=finished))

        mk("20260906T110000.000000Z-early", "2026-09-06T11:00:00Z", "2026-09-06T11:59:00Z")   # asked first, done last
        mk("20260906T110100.000000Z-fast1", "2026-09-06T11:01:00Z", "2026-09-06T11:01:05Z")   # done first -> dropped
        mk("20260906T110200.000000Z-fast2", "2026-09-06T11:02:00Z", "2026-09-06T11:02:05Z")
        pruned = store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=2, now=now)
        survivors = {r.id for r in store.list(limit=10)[0]}
        assert pruned == 1
        assert survivors == {"20260906T110000.000000Z-early", "20260906T110200.000000Z-fast2"}, \
            "the cap keeps the most recently COMPLETED runs, not the most recently requested"

    # ---- F1 (review C2 / C4; OB3 pass-1 Fix A): the exact end-of-second predicate ----------------------
    def test_completion_rounding_can_never_delete_early(self, tmp_path):
        """#163. finished_at is persisted to whole seconds. A run that finished at exactly the cutoff second
        is aged from the END of that second, so it is NOT older than the bound — deleting it would be
        deleting a run that may be up to 999 ms younger than its stamp says. One second later the end of
        its second is on the cutoff and it goes; a run stamped one second BEFORE the cutoff finished, at
        the latest, a millisecond before it, and goes at once. That second is where `<` and `<=` differ:
        with `<` a whole-second `now` kept every run one second longer than main's id-keyed prune did."""
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
        at_cutoff = now - timedelta(days=3)

        def mk(run_id, finished):
            store.create(Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={}, formats=["html"],
                             generated_by="root", generated_by_note="n", schedule=None,
                             requested_at="2026-09-01T00:00:00Z", status="done",
                             finished_at=finished.strftime("%Y-%m-%dT%H:%M:%SZ")))

        mk("20260901T000000.000000Z-edge", at_cutoff)
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now) == 0
        # One second later the end of its second is on the cutoff: older, gone.
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500,
                           now=now + timedelta(seconds=1)) == 1
        # Stamped one second before the cutoff: it finished before the cutoff by every reading, gone now.
        mk("20260901T000001.000000Z-before", at_cutoff - timedelta(seconds=1))
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now) == 1

    # ---- F2 (review C1, OB3 Fix B): a wrong-typed finished_at must not stop retention -------------------
    def test_a_hand_edited_finished_at_of_the_wrong_type_does_not_stop_retention(self, tmp_path):
        """The manifest is a hand-readable JSON file and the loader is deliberately tolerant of its shape.
        A `finished_at` that is not a string (a JSON number, say) raised TypeError out of retention_stamp,
        and _maybe_prune swallows every exception — so ONE edited manifest silently switched retention
        off for the whole store. The wrong-typed stamp is skipped like a malformed one: the run ages from
        its id, and every other run is still pruned."""
        for run_id, finished in (("20260801T000000.000000Z-edit", 1757160000),
                                 ("20260701T000000.000000Z-good", "2026-07-01T00:00:05Z")):
            run = Run(id=run_id, report="compliance-snapshot", cluster=CLUSTER, params={}, formats=["html"],
                      generated_by="root", generated_by_note="n", schedule=None,
                      requested_at="2026-08-01T00:00:00Z", status="done")
            manifest = run.public()
            manifest["finished_at"] = finished
            (tmp_path / run_id).mkdir()
            (tmp_path / run_id / "run.json").write_text(json.dumps(manifest), encoding="utf-8")
        store = ArtifactStore(str(tmp_path))
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now) == 2
        assert store.list(limit=10)[0] == []

    def test_a_hand_edited_id_does_not_stop_retention(self, tmp_path):
        """Review of #163, pass 2 (OB3, P2). `_load` never looked at the id, and `retention_stamp`'s
        fallback parses `id[:15]`, so a manifest whose id was hand-edited to something that is not a
        stamp — or not a string — raised ValueError/TypeError out of the first prune that reached it,
        `_maybe_prune` swallowed it, and no run in the store was pruned again (main's string comparison
        could not raise on it). An id that is a stamp but not its directory's name was doomed every hour
        and never left: deletion is by `_dir(run.id)`. The loader refuses all three the way it refuses
        an unreadable manifest — a warning, the directory left alone — and every other run still prunes."""
        good = "20260701T000000.000000Z-good"

        def manifest(dirname, **over):
            m = Run(id=good, report="compliance-snapshot", cluster=CLUSTER, params={}, formats=["html"],
                    generated_by="root", generated_by_note="n", schedule=None, requested_at="2026-07-01T00:00:00Z",
                    status="failed", error="the report service restarted before this run finished").public()
            m.update(over)
            (tmp_path / dirname).mkdir()
            (tmp_path / dirname / "run.json").write_text(json.dumps(m), encoding="utf-8")

        manifest("garbage", id="garbage")                                            # not a stamp
        manifest("20260801T000000.000000Z-num", id=20260801)                         # not a string
        manifest("20260801T000000.000000Z-moved", id="20260801T000000.000000Z-else")  # a stamp, not this directory
        manifest(good, status="done", error=None, finished_at="2026-07-01T00:00:05Z")
        store = ArtifactStore(str(tmp_path))
        assert [r.id for r in store.list(limit=10)[0]] == [good], "an id that is not its directory's stamp is not indexed"
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now) == 1
        assert store.list(limit=10)[0] == []
        assert sorted(p.name for p in tmp_path.iterdir()) == \
            ["20260801T000000.000000Z-moved", "20260801T000000.000000Z-num", "garbage"], \
            "the refused directories are the operator's to remove, never prune's"

    # ---- F3 (review C5, OB3 Fix C): the fallback pinned on the runs that actually take it ---------------
    def test_a_run_that_never_completed_ages_from_its_id(self, tmp_path):
        """#163's documented fallback, on the runs that take it. `finished_at` has been in every manifest
        since the first release, so the fallback is not a legacy path: it is the run the pod died under
        (`_load` marks it failed; no completion to stamp) and a run a full queue refused before this
        release stamped it. The only date either has is the request time its id encodes. (Pins, not a
        fail-before test: main aged these by the id too, which is why the PR's version of this test could
        only fail on main with an ImportError.)"""
        from gsd.reporting.artifacts import retention_stamp
        interrupted = Run(id="20260801T000000.000000Z-died", report="compliance-snapshot", cluster=CLUSTER, params={},
                          formats=["html"], generated_by="root", generated_by_note="n", schedule=None,
                          requested_at="2026-08-01T00:00:00Z", status="running", started_at="2026-08-01T00:00:01Z")
        refused = Run(id="20260802T000000.000000Z-full", report="compliance-snapshot", cluster=CLUSTER, params={},
                      formats=["html"], generated_by="root", generated_by_note="n", schedule=None,
                      requested_at="2026-08-02T00:00:00Z", status="failed",
                      error="the render queue is full; try again shortly")
        for run in (interrupted, refused):
            (tmp_path / run.id).mkdir()
            (tmp_path / run.id / "run.json").write_text(json.dumps(run.public()), encoding="utf-8")
        store = ArtifactStore(str(tmp_path))                     # the restart: 'running' becomes 'failed'
        died = store.get(interrupted.id)
        assert died.status == "failed" and died.finished_at is None
        assert retention_stamp(died) == datetime(2026, 8, 1, tzinfo=UTC)
        assert retention_stamp(store.get(refused.id)) == datetime(2026, 8, 2, tzinfo=UTC)
        now = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500, now=now) == 2

    # ---- F6 (OB3 Fix D, accepted): a queue refusal is a terminal transition — stamp it -----------------
    def test_a_run_refused_by_a_full_queue_is_stamped_finished(self, tmp_path):
        """Every terminal transition stamps finished_at — the render's `finally` and the window recheck
        (test_a_recheck_failed_run_is_counted_finished asserts it) — except the queue refusal in submit(),
        which failed the run and left the stamp None. The run finished the instant it was refused; say so, and
        retention ages it like every other failure instead of through the id fallback."""
        snapshots, artifacts = seeded_dirs(tmp_path)
        store = ArtifactStore(str(artifacts))
        clock = datetime(2026, 9, 6, 12, 0, 5, tzinfo=UTC)

        class Recorder:
            def note_submitted(self, report):
                pass

        rm = RunManager(_settings(snapshots, artifacts, max_queued_runs=1), store, Recorder(), clock=lambda: clock)

        def mk(i):
            return Run(id=f"20260906T12000{i}.000000Z-000{i}", report="groups", cluster=CLUSTER, params={},
                       formats=["html"], generated_by="root", generated_by_note="n", schedule=None,
                       requested_at=f"2026-09-06T12:00:0{i}Z")

        rm.submit(mk(0))                                   # fills the one-slot queue; the worker is never started
        with pytest.raises(QueueFull):
            rm.submit(mk(1))
        refused = store.get("20260906T120001.000000Z-0001")
        assert refused.status == "failed" and "queue is full" in refused.error
        assert refused.finished_at == "2026-09-06T12:00:05Z"

    def test_scheduled_keep_uses_completion_order(self, tmp_path):
        """#163, the scheduled tier (review of C5, Codex): keep-K holds the most recently COMPLETED
        reports per (schedule, cluster). An early request that finished last owns the one slot; the
        later request that finished first is beyond the keep and, past `days`, goes. Fails on the
        id-keyed prune, which kept the later id."""
        store = ArtifactStore(str(tmp_path))

        def mk(run_id, finished):
            store.create(Run(id=run_id, report="groups", cluster="east", params={}, formats=["html"],
                             generated_by="schedule:nightly", generated_by_note="n", schedule="nightly",
                             requested_at="2026-01-01T00:00:00Z", status="done", finished_at=finished))

        early, late = "20260101T000000.000000Z-early", "20260102T000000.000000Z-late"
        mk(early, "2026-02-02T00:00:00Z")
        mk(late, "2026-02-01T00:00:00Z")
        assert store.prune(scheduled_keep=1, scheduled_days=1, manual_days=0, manual_max_runs=0,
                           now=datetime(2026, 9, 6, tzinfo=UTC)) == 1
        assert {r.id for r in store.list(limit=10)[0]} == {early}

    def test_a_naive_now_does_not_stop_retention(self, tmp_path):
        """Review of #163 (Cursor, volunteered): the stamps are aware, so a naive `now` from an injected
        clock raised TypeError out of the comparison — and `_maybe_prune` swallows every exception, so
        retention would have switched off silently. A naive instant is read as UTC and the prune runs."""
        store = ArtifactStore(str(tmp_path))
        store.create(Run(id="20260801T000000.000000Z-old", report="compliance-snapshot", cluster=CLUSTER, params={},
                         formats=["html"], generated_by="root", generated_by_note="n", schedule=None,
                         requested_at="2026-08-01T00:00:00Z", status="done", finished_at="2026-08-01T00:00:05Z"))
        assert store.prune(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=500,
                           now=datetime(2026, 9, 6, 12, 0)) == 1

    def test_a_download_racing_prune_reads_none_instead_of_raising(self, tmp_path, monkeypatch):
        """#155: prune removes a run's files between the reader's check and its read — the reader holds
        no lock, so the check's answer is already stale. `read` must return None (the endpoint's 404)
        rather than raising FileNotFoundError out of get_artifact, which FastAPI turns into a 500."""
        store = ArtifactStore(str(tmp_path))
        run = self._done_run(store)
        assert store.read(run.id, "html") == b"<p>evidence</p>"

        # The race: the artefact is gone, but a check would still have answered "present".
        (store._dir(run.id) / "report.html").unlink()
        monkeypatch.setattr(Path, "is_file", lambda self: True)   # the stale look-before-you-leap answer
        assert store.read(run.id, "html") is None, "a download racing prune answers 404, not a 500"

    def test_a_genuine_io_error_is_not_laundered_into_a_missing_artefact(self, tmp_path, monkeypatch):
        """The catch in `read` is deliberately narrow. A permissions or disk failure must still surface
        (a 500 the operator can see), NOT be reported as 'this run has no artefact' (404) — so the
        narrow catch cannot be widened to `except OSError` later without failing this."""
        store = ArtifactStore(str(tmp_path))
        run = self._done_run(store)

        def boom(self):
            raise PermissionError("EACCES: the volume rejected the read")

        monkeypatch.setattr(Path, "read_bytes", boom)
        with pytest.raises(PermissionError):
            store.read(run.id, "html")

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

    def test_a_hand_edited_finished_at_does_not_crashloop_the_seed(self, tmp_path):
        """Review of #163, pass 2 (OB3, volunteered). The seed skips a hand-edited stamp "not a crashloop" —
        for the wrong SHAPE only: a JSON number raised TypeError out of build_report_app, so the one
        manifest retention now tolerates (F2) restarted the pod for ever when its run was done and
        scheduled. Skipped like a malformed one; the newest GOOD done run seeds the gauge."""
        snapshots, artifacts = seeded_dirs(tmp_path)

        def manifest(rid, fin):
            m = Run(id=rid, report="groups", cluster=CLUSTER, params={}, formats=["html"],
                    generated_by="schedule:nightly", generated_by_note="n", schedule="nightly",
                    requested_at="2026-09-14T00:00:00Z", status="done", origin="schedule").public()
            m["finished_at"] = fin
            (artifacts / rid).mkdir()
            (artifacts / rid / "run.json").write_text(json.dumps(m), encoding="utf-8")

        manifest("20260915T090000.000000Z-edit", 1757926805)                  # newest, a JSON number
        manifest("20260914T090000.000000Z-good", "2026-09-14T09:00:03Z")
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            m = client.get(f"{REPORT_PREFIX}/metrics").text
        line = next(l for l in m.splitlines()
                    if l.startswith('gsd_report_schedule_last_success_timestamp{schedule="nightly"}'))
        expect = datetime(2026, 9, 14, 9, 0, 3, tzinfo=UTC).timestamp()
        assert abs(float(line.split()[-1]) - expect) < 1.0, line


class TestClusterAgnosticSchedulesAndOriginFormats:
    """#149 R1 + R3: a schedule names no cluster and the service fans the run out to every enabled
    cluster in its snapshot; formats default by origin when the request names none."""

    def _client(self, tmp_path, **over):
        snapshots, artifacts = seeded_dirs(tmp_path)
        return TestClient(build_report_app(_settings(snapshots, artifacts, **over), secret=SECRET, clock=lambda: FROZEN))

    def _two_cluster_client(self, tmp_path, **over):
        from reporting_seed import seed_store, write_snapshot     # the module's own convention: CI's `pytest tests/` has no `tests` package
        snapshots, artifacts = tmp_path / "snapshots", tmp_path / "artifacts"
        snapshots.mkdir(); artifacts.mkdir()
        store = seed_store(str(tmp_path / "writer.db"))
        try:
            store.upsert_cluster("prod-east", "https://api.prod-east:6443", True)
            store.upsert_cluster("retired", "https://api.retired:6443", False)      # disabled: never a target
            write_snapshot(store, snapshots)
        finally:
            store.close()
        return TestClient(build_report_app(_settings(snapshots, artifacts, **over), secret=SECRET, clock=lambda: FROZEN))

    def test_a_schedule_without_a_cluster_fans_out_to_every_enabled_cluster(self, tmp_path):
        with self._two_cluster_client(tmp_path) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 202, r.text
            runs = r.json()["runs"]
            assert sorted(x["cluster"] for x in runs) == [CLUSTER, "prod-east"]      # `retired` is enabled=0
            assert {x["generated_by"] for x in runs} == {"schedule:nightly"}
            assert len({x["id"] for x in runs}) == 2, "one id per cluster"
            for x in runs:
                assert client.get(f"{REPORT_PREFIX}/api/runs/{x['id']}", headers=SERVICE).status_code == 200

    def test_a_fan_out_is_one_queue_slot_all_or_nothing(self, tmp_path):
        # Review of PR #220 (Codex, Grok): submitted one by one, a queue that filled mid-batch left some
        # clusters queued and answered 429, and the Job's retry duplicated them. One slot: the batch is
        # refused whole when the queue is full, and a fleet of many clusters is still one entry.
        from gsd.reporting.runs import RunManager
        with self._two_cluster_client(tmp_path, max_queued_runs=1) as client:
            app = client.app
            # fill the single slot with something the worker cannot drain in time: a paused worker
            app.state.runs._stop.set(); app.state.runs._thread.join(timeout=5)
            first = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "one"}, headers=SERVICE)
            assert first.status_code == 202
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 429, r.text
            listed = client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()
            nightly = [x for x in listed["runs"] if x["generated_by"] == "schedule:nightly"]
            assert len(nightly) == 2 and {x["status"] for x in nightly} == {"failed"}, "neither cluster of the refused batch is queued"
            assert listed["queued"] == 1
        # with one free slot, a two-cluster fan-out fits as ONE entry
        (tmp_path / "b").mkdir()
        with self._two_cluster_client(tmp_path / "b", max_queued_runs=1) as client:
            client.app.state.runs._stop.set(); client.app.state.runs._thread.join(timeout=5)
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 202 and len(r.json()["runs"]) == 2
            assert client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()["queued"] == 2   # runs waiting, not slots

    def test_a_fan_out_never_reuses_an_id_already_in_the_store(self, tmp_path, monkeypatch):
        # Review of PR #220 (Codex): the store's create overwrites silently, so a draw that repeated an
        # existing id would have replaced that run. The loop checks the store as well as the batch.
        from gsd.reporting import server as srv
        ids = iter(["20260920T000000.000000Z-aaaa", "20260920T000000.000000Z-aaaa", "20260920T000000.000000Z-bbbb",
                    "20260920T000000.000000Z-aaaa", "20260920T000000.000000Z-cccc"])
        monkeypatch.setattr(srv, "new_run_id", lambda now: next(ids))
        with self._two_cluster_client(tmp_path) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "schedule": "nightly"}, headers=SERVICE).json()
            assert sorted(x["id"] for x in r["runs"]) == ["20260920T000000.000000Z-aaaa", "20260920T000000.000000Z-bbbb"]
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "again"}, headers=SERVICE).json()
            assert r["id"] == "20260920T000000.000000Z-cccc", "the repeated aaaa was skipped: it is in the store"

    def test_an_unlistable_snapshot_directory_is_503_not_500(self, tmp_path):
        # Review of PR #220 (OB3): the resolver caught SnapshotError only; an OSError from listing the
        # directory (a lost mount permission) was a 500. A 503 like a missing snapshot.
        with self._client(tmp_path) as client:
            bad = tmp_path / "not-a-dir"; bad.write_text("x")
            object.__setattr__(client.app.state.settings, "snapshot_dir", str(bad))   # frozen: point the resolver at a file
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 503, r.text

    def test_a_pinned_cluster_keeps_the_single_run_shape(self, tmp_path):
        with self._two_cluster_client(tmp_path) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": "prod-east", "schedule": "nightly"}, headers=SERVICE)
            assert r.status_code == 202 and r.json()["cluster"] == "prod-east" and "runs" not in r.json()

    def test_a_viewer_must_name_its_cluster(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        with self._client(tmp_path) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups"}, headers=ticket)
            assert r.status_code == 422 and "names its cluster" in r.json()["detail"]

    def test_formats_default_by_origin_and_json_is_implied(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        with self._client(tmp_path) as client:
            manual = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).json()
            scheduled = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE).json()
            assert manual["formats"] == ["html", "pdf"], manual
            assert scheduled["formats"] == ["html"], scheduled          # no pdf unattended; json always written
            explicit = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly", "formats": ["pdf"]}, headers=SERVICE).json()
            assert explicit["formats"] == ["pdf"], "an explicit list overrides the origin default"

    def test_the_deployment_overrides_the_origin_defaults(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        with self._client(tmp_path, formats_scheduled=("html", "pdf"), formats_manual=("html",)) as client:
            manual = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).json()
            scheduled = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE).json()
            assert manual["formats"] == ["html"] and scheduled["formats"] == ["html", "pdf"]

    def test_a_defaulted_pdf_is_dropped_where_pdf_is_off_but_an_explicit_one_is_refused(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        with self._client(tmp_path, pdf_enabled=False) as client:
            manual = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER}, headers=ticket)
            assert manual.status_code == 202 and manual.json()["formats"] == ["html"]
            explicit = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["pdf"]}, headers=ticket)
            assert explicit.status_code == 422

    def test_the_formats_env_accepts_json_and_refuses_a_typo(self, monkeypatch):
        from gsd.reporting.config import _formats_env
        monkeypatch.setenv("GSD_REPORT_FORMATS_SCHEDULED", "html, json")
        assert _formats_env("GSD_REPORT_FORMATS_SCHEDULED", ("x",)) == ("html",)
        monkeypatch.setenv("GSD_REPORT_FORMATS_SCHEDULED", "")
        assert _formats_env("GSD_REPORT_FORMATS_SCHEDULED", ("html",)) == ("html",)
        monkeypatch.setenv("GSD_REPORT_FORMATS_SCHEDULED", "html,pfd")
        with pytest.raises(SystemExit):
            _formats_env("GSD_REPORT_FORMATS_SCHEDULED", ("html",))


class TestReportingStatus:
    """#149 R5/R6: the status endpoint's three cards from what the service already holds, and the
    history's server-side filters."""

    SCHEDULES = [
        {"name": "quarterly-compliance", "schedule": "0 6 1 1,4,7,10 *", "report": "compliance-snapshot",
         "retention": {"keepPerSchedule": 12, "days": 2555}},
        {"name": "biweekly-namespace-access", "schedule": "0 6 1,16 * *", "report": "namespace-access", "enabled": False},
        {"name": "nightly", "schedule": "0 2 * * *", "report": "groups"},
    ]

    def _client(self, tmp_path, at=None, **over):
        from gsd.reporting.window import ReportingWindow
        snapshots, artifacts = seeded_dirs(tmp_path)
        w = ReportingWindow.from_strings(enabled=True, timezone="America/New_York", start="02:00", end="06:00",
                                         days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        clock = {"now": at or datetime(2026, 9, 20, 7, 30, tzinfo=UTC)}     # 03:30 EDT: the window is open
        app = build_report_app(_settings(snapshots, artifacts, window=w, schedules=tuple(self.SCHEDULES), **over),
                               secret=SECRET, clock=lambda: clock["now"])
        return TestClient(app), clock

    def test_the_three_cards_come_from_config_window_store_and_signals(self, tmp_path):
        client, clock = self._client(tmp_path)
        with client:
            client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            for _ in range(50):
                r = client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()
                if r["runs"] and r["runs"][0]["status"] in ("done", "failed"):
                    break
                time.sleep(0.1)
            s = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()
        assert s["service"]["pdf"] == {"enabled": True, "variant": "pdf/a-2b"} and s["service"]["reports_enabled"] == 11
        assert s["service"]["formats"] == {"scheduled": ["html", "json"], "manual": ["html", "pdf", "json"]}
        assert s["window"]["open_now"] is True and s["window"]["next_change"] == "closes"
        assert s["window"]["next_change_at"] == "2026-09-20T10:00:00Z"        # 06:00 EDT
        assert s["window"]["days"] == ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        assert s["retention"] == {"scheduled": {"keepPerSchedule": 2, "days": 90}, "manual": {"days": 3, "maxRuns": 500}}
        by = {x["name"]: x for x in s["schedules"]}
        q = by["quarterly-compliance"]
        assert q["cadence"] == "Quarterly 06:00" and q["retention"] == {"keepPerSchedule": 12, "days": 2555, "overridden": True}
        assert q["next_fire"] == "2026-10-01T10:00:00Z" and q["status"] == "never"      # no run of it yet
        p = by["biweekly-namespace-access"]
        assert p["enabled"] is False and p["next_fire"] is None and p["status"] == "disabled"
        assert p["retention"] == {"keepPerSchedule": 2, "days": 90, "overridden": False}
        n = by["nightly"]
        assert n["cadence"] == "Daily 02:00" and n["last_success"] is not None and n["status"] == "ok"

    def test_a_schedule_whose_last_fire_passed_without_a_success_is_late(self, tmp_path):
        client, clock = self._client(tmp_path)
        with client:
            client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            for _ in range(50):
                r = client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()
                if r["runs"] and r["runs"][0]["status"] == "done":
                    break
                time.sleep(0.1)
            clock["now"] = clock["now"] + timedelta(days=2)      # two fires later, no new success
            s = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()
        assert {x["name"]: x["status"] for x in s["schedules"]}["nightly"] == "late"

    def test_a_disabled_window_reports_never_changing(self, tmp_path):
        snapshots, artifacts = seeded_dirs(tmp_path)
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            s = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()
        assert s["window"] == {"enabled": False, "open_now": True, "timezone": None, "start": None, "end": None,
                               "days": [], "next_change": "never", "next_change_at": None, "refused_since_start": 0}
        assert s["schedules"] == []

    def test_the_history_filters_run_across_the_whole_history(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        snapshots, artifacts = seeded_dirs(tmp_path)
        app = build_report_app(_settings(snapshots, artifacts, max_queued_runs=100), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            for i in range(3):
                client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "schedule": "nightly"}, headers=SERVICE)
            client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "users", "cluster": CLUSTER}, headers=ticket)
            for _ in range(100):
                r = client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()
                if r["total"] == 4 and all(x["status"] in ("done", "failed") for x in r["runs"]):
                    break
                time.sleep(0.1)
            sched = client.get(f"{REPORT_PREFIX}/api/runs?origin=schedule&limit=2", headers=SERVICE).json()
            assert sched["total"] == 3 and len(sched["runs"]) == 2 and sched["truncated"] is True
            person = client.get(f"{REPORT_PREFIX}/api/runs?origin=person", headers=SERVICE).json()
            assert person["total"] == 1 and person["runs"][0]["report"] == "users"
            assert client.get(f"{REPORT_PREFIX}/api/runs?status=done&cluster={CLUSTER}", headers=SERVICE).json()["total"] == 4
            assert client.get(f"{REPORT_PREFIX}/api/runs?cluster=nope", headers=SERVICE).json()["total"] == 0
            assert r["facets"] == {"reports": ["groups", "users"], "clusters": [CLUSTER]}
            assert client.get(f"{REPORT_PREFIX}/api/runs?origin=robot", headers=SERVICE).status_code == 422

    def test_the_schedules_env_is_validated(self, monkeypatch):
        from gsd.reporting.config import _schedules_env
        monkeypatch.setenv("GSD_REPORT_SCHEDULES", "")
        assert _schedules_env() == ()
        monkeypatch.setenv("GSD_REPORT_SCHEDULES", '[{"name":"n","schedule":"0 2 * * *","report":"groups"}]')
        assert _schedules_env()[0]["name"] == "n"
        monkeypatch.setenv("GSD_REPORT_SCHEDULES", '[{"name":"n"}]')
        with pytest.raises(SystemExit):
            _schedules_env()
        monkeypatch.setenv("GSD_REPORT_SCHEDULES", "not json")
        with pytest.raises(SystemExit):
            _schedules_env()


class TestDiscoveredLookups:
    """#149 R7: the discovered lookups a form offers, per cluster, on their own endpoint — never on the
    catalogue load, which stays one query for the estate (V4-F1)."""

    def test_the_lookups_come_per_cluster_and_the_catalogue_does_not_carry_them(self, tmp_path):
        snapshots, artifacts = seeded_dirs(tmp_path)
        app = build_report_app(_settings(snapshots, artifacts, namespace_selector_labels=("company.net/mnemonic",),
                                         namespace_group_label="company.net/oud-group"), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            cat = client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()
            assert "discovered" not in cat and cat["namespaceGroupLabel"] == "company.net/oud-group"
            d = client.get(f"{REPORT_PREFIX}/api/discovered?cluster={CLUSTER}", headers=_viewer()).json()
            assert d["cluster"] == CLUSTER and d["discovered"]["users"]["values"] == ["alice", "bob", "erin"]
            assert d["discovered"]["providers"]["values"] == ["corp_ldap"] and "team-a" in d["discovered"]["groups"]["values"]
            assert set(d["discovered"]) == {"providers", "roles", "users", "groups", "mnemonics", "oud-groups", "namespaces"}   # namespaces since #143
            assert client.get(f"{REPORT_PREFIX}/api/discovered?cluster=nope", headers=_viewer()).status_code == 404
            assert client.get(f"{REPORT_PREFIX}/api/discovered", headers=_viewer()).status_code == 422
            assert client.get(f"{REPORT_PREFIX}/api/discovered?cluster={CLUSTER}").status_code == 401
class TestReportingStatusReview:
    """Review of #221 (OB3): the late predicate's grace sits after the fire; the per-schedule retention
    override the page calls effective is the one the prune applies; the optional keys are validated at
    startup like the required ones."""

    NIGHTLY = ({"name": "nightly", "schedule": "0 2 * * *", "report": "groups"},)

    @staticmethod
    def _done(run_id, day, schedule="nightly"):
        return Run(id=run_id, report="groups", cluster=CLUSTER, params={}, formats=["html"], generated_by=f"schedule:{schedule}",
                   generated_by_note="unattended", schedule=schedule, origin="schedule", requested_at=f"{day}T02:00:00Z",
                   started_at=f"{day}T02:00:01Z", finished_at=f"{day}T02:02:00Z", status="done", sha256="ab" * 32)

    def _status(self, tmp_path, at, schedules=NIGHTLY, seed=(), in_flight=None, **over):
        tmp_path.mkdir(exist_ok=True)
        snapshots, artifacts = seeded_dirs(tmp_path)
        store = ArtifactStore(str(artifacts))
        for r in seed:
            store.create(r)
        app = build_report_app(_settings(snapshots, artifacts, schedules=schedules, max_queued_runs=0, **over), secret=SECRET, clock=lambda: at)
        if in_flight is not None:
            app.state.store.create(in_flight)
        with TestClient(app) as client:
            return client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()

    def test_a_schedule_that_just_fired_is_ok_while_its_run_renders_and_late_half_an_hour_on(self, tmp_path):
        # Before the fix `last_success < previous_fire - 30 min` was true the instant the fire passed
        # (yesterday's success is a day older), so every healthy schedule read `late` until its run
        # finished — measured at fire + 1 s with the run in flight, and at fire + 5 min.
        yesterday = self._done("20260919T020000.000000Z-aaaa", "2026-09-19")
        running = Run(id="20260920T020000.000000Z-bbbb", report="groups", cluster=CLUSTER, params={}, formats=["html"],
                      generated_by="schedule:nightly", generated_by_note="unattended", schedule="nightly", origin="schedule",
                      requested_at="2026-09-20T02:00:00Z", started_at="2026-09-20T02:00:01Z", status="running")
        by = lambda s: {x["name"]: x for x in s["schedules"]}["nightly"]  # noqa: E731
        just_fired = by(self._status(tmp_path / "a", datetime(2026, 9, 20, 2, 0, 1, tzinfo=UTC), seed=[yesterday], in_flight=running))
        assert just_fired["previous_fire"] == "2026-09-20T02:00:00Z" and just_fired["last_success"] == "2026-09-19T02:02:00Z"
        assert just_fired["status"] == "ok", just_fired
        assert by(self._status(tmp_path / "b", datetime(2026, 9, 20, 2, 29, tzinfo=UTC), seed=[yesterday]))["status"] == "ok"
        assert by(self._status(tmp_path / "c", datetime(2026, 9, 20, 2, 31, tzinfo=UTC), seed=[yesterday]))["status"] == "late"
        # a success after the fire is ok whatever the hour; no success ever is never
        today = self._done("20260920T020000.000000Z-cccc", "2026-09-20")
        assert by(self._status(tmp_path / "d", datetime(2026, 9, 20, 12, 0, tzinfo=UTC), seed=[yesterday, today]))["status"] == "ok"
        assert by(self._status(tmp_path / "e", datetime(2026, 9, 20, 12, 0, tzinfo=UTC)))["status"] == "never"

    def test_the_retention_override_the_page_reports_is_the_one_the_prune_applies(self, tmp_path):
        # `ArtifactStore.prune(overrides=...)` has existed since the two-tier retention and nothing passed
        # it; #221 is the first to declare an override (environments/crc.yaml) and to display it as the
        # effective policy. Three runs of a quarterly schedule, all older than the global 90 days: the
        # globals keep the newest 2, the override (12 newest, 2555 days) keeps all three.
        quarterly = ({"name": "quarterly", "schedule": "0 6 1 1,4,7,10 *", "report": "groups", "retention": {"keepPerSchedule": 12, "days": 2555}},)
        snapshots, artifacts = seeded_dirs(tmp_path)
        store = ArtifactStore(str(artifacts))
        for i, day in enumerate(("2026-01-01", "2026-04-01", "2026-07-01")):
            store.create(self._done(f"{day.replace('-', '')}T060000.000000Z-q{i:03d}", day, schedule="quarterly"))
        at = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
        settings = _settings(snapshots, artifacts, schedules=quarterly, max_queued_runs=0)
        app = build_report_app(settings, secret=SECRET, clock=lambda: at)
        with TestClient(app) as client:
            s = client.get(f"{REPORT_PREFIX}/api/status", headers=SERVICE).json()
            assert s["schedules"][0]["retention"] == {"keepPerSchedule": 12, "days": 2555, "overridden": True}
            app.state.runs._last_prune = -10**9            # the hourly gate: due now
            app.state.runs._maybe_prune()
            assert client.get(f"{REPORT_PREFIX}/api/runs", headers=SERVICE).json()["total"] == 3, "the prune applied the globals, not the override the page shows"
        from gsd.reporting.config import retention_overrides            # the one reading both sides share
        assert retention_overrides(settings) == {"quarterly": (12, 2555)}

    def test_the_schedules_env_refuses_a_malformed_retention_or_enabled_at_startup(self, monkeypatch):
        # Before: a `retention: {days: "twelve"}` passed startup and GET /report/api/status was a 500.
        from gsd.reporting.config import _schedules_env
        good = {"name": "n", "schedule": "0 2 * * *", "report": "groups"}
        for bad in ({"retention": {"days": "twelve"}}, {"retention": {"keepPerSchedule": None}}, {"retention": [1, 2]},
                    {"retention": {"days": -1}}, {"retention": {"weeks": 2}}, {"retention": {"days": True}}, {"enabled": "false"}, {"enabled": 0}):
            monkeypatch.setenv("GSD_REPORT_SCHEDULES", json.dumps([good | bad]))
            with pytest.raises(SystemExit, match="GSD_REPORT_SCHEDULES: schedule 'n'"):
                _schedules_env()
        monkeypatch.setenv("GSD_REPORT_SCHEDULES", json.dumps([good | {"retention": {"days": 12}, "enabled": False}]))
        assert _schedules_env()[0]["retention"] == {"days": 12}


class TestPreviewAndNamespacePicker:
    """#143 phases 2 and 3: the totals a run would produce, from build() alone; the discovered namespaces."""

    def test_the_preview_answers_totals_without_a_run(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        snapshots, artifacts = seeded_dirs(tmp_path)
        with TestClient(build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER}, headers=ticket)   # not this
            r = client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "namespace-access", "cluster": CLUSTER,
                                                                  "params": {"namespaces": "prod-ns,dev-ns"}}, headers=ticket)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["totals"]["namespaces"] == 2 and body["truncated"] is False and body["snapshot"]
            assert set(body) == {"report", "cluster", "totals", "truncated", "snapshot"}      # the shape docs/reports/README.md states
            listed = client.get(f"{REPORT_PREFIX}/api/runs", headers=ticket).json()
            assert all(x["report"] != "namespace-access" for x in listed["runs"]), "a preview stores no run"
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "namespace-access", "cluster": CLUSTER, "params": {"nope": 1}}, headers=ticket).status_code == 422
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "namespace-access", "cluster": CLUSTER, "params": {}}, headers=ticket).status_code == 422   # no selection
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "nope", "cluster": CLUSTER}, headers=ticket).status_code == 404
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": "nope"}, headers=ticket).status_code == 404
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}).status_code == 401

    def test_the_preview_is_503_without_a_snapshot_and_429_when_busy(self, tmp_path):
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        snapshots, artifacts = tmp_path / "s", tmp_path / "a"; snapshots.mkdir(); artifacts.mkdir()
        with TestClient(build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)) as client:
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).status_code == 503
        (tmp_path / "b").mkdir()
        snapshots, artifacts = seeded_dirs(tmp_path / "b")
        app = build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)
        with TestClient(app) as client:
            # one slot: while a preview builds, the next is refused, not queued
            import threading, time as _t
            from gsd.reporting import server as srv
            held = threading.Event()
            orig = srv.REGISTRY["groups"][1]
            def slow(snap, ctx, params):
                held.set(); _t.sleep(0.6); return orig(snap, ctx, params)
            srv.REGISTRY["groups"] = (srv.REGISTRY["groups"][0], slow)
            try:
                th = threading.Thread(target=lambda: client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket))
                th.start(); held.wait(2)
                assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).status_code == 429
                th.join()
            finally:
                srv.REGISTRY["groups"] = (srv.REGISTRY["groups"][0], orig)
            # the slot is released when the build ends (review of #224, Grok: the test never pinned it) — and on a
            # refused path too: a 422 raised inside build() must not hold it
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).status_code == 200
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "namespace-access", "cluster": CLUSTER}, headers=ticket).status_code == 422
            assert client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket).status_code == 200
            # an unconfigured selector label is refused as a run refuses it
            r = client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "namespace-access", "cluster": CLUSTER, "params": {"selectors": {"x/y": ["a"]}}}, headers=ticket)
            assert r.status_code == 422 and "not configured" in r.json()["detail"]

    def test_the_discovered_namespaces_feed_the_picker_and_a_str_is_trimmed(self, tmp_path):
        from gsd.reporting.catalogue import REGISTRY, ValidationError, validate_params as vp
        from reporting_seed import seed_store, write_snapshot
        store = seed_store(str(tmp_path / "w.db"))
        store.replace_namespaces(CLUSTER, [{"name": "prod-ns", "created_at": None, "phase": "Active", "metadata": {}},
                                          {"name": "dev-ns", "created_at": None, "phase": "Active", "metadata": {}}], "2026-09-14T00:00:00Z")
        d = tmp_path / "snap"; d.mkdir(); path = write_snapshot(store, d); store.close()
        from gsd.reporting.snapshot import Snapshot
        with Snapshot(path) as snap:
            assert snap.discovered(CLUSTER, "", "")["namespaces"]["values"] == ["dev-ns", "prod-ns"]
        cert = REGISTRY["access-certification"][0]
        assert vp(cert, {"campaign": " Q3 ", "due": "2026-10-01", "reviewer": " r "})["reviewer"] == "r"
        with pytest.raises(ValidationError, match="required"):
            vp(cert, {"campaign": "x", "due": "2026-10-01", "reviewer": "   "})

    def test_the_preview_is_503_when_the_newest_copy_is_unreadable(self, tmp_path):
        # Review of #224 (OB3): only newest_snapshot() was behind the 503; Snapshot() itself raises
        # SnapshotError for a copy the service cannot read — torn, or a schema newer than it knows (the
        # dashboard rolled first) — and that escaped the route as a 500 where readyz says 503.
        ticket = {TICKET_HEADER: mint(SECRET, "root", "all", 300, now=int(FROZEN.timestamp())), USER_HEADER: "root"}
        snapshots, artifacts = seeded_dirs(tmp_path)
        (snapshots / "gsd-20991231T235959.000000Z.db").write_bytes(b"not a database")     # newest by name, unreadable
        with TestClient(build_report_app(_settings(snapshots, artifacts), secret=SECRET, clock=lambda: FROZEN)) as client:
            r = client.post(f"{REPORT_PREFIX}/api/preview", json={"report": "groups", "cluster": CLUSTER}, headers=ticket)
            assert r.status_code == 503 and "not a readable SQLite database" in r.json()["detail"], r.text
            assert client.get(f"{REPORT_PREFIX}/readyz").status_code == 503                 # the same answer as the probe's


class TestRetentionStanding:
    """#229 (SPEC E1 §3): `store.retention()` prints the plan `prune()` deletes by — one ranking, two readers.
    Every case holds the words beside a REAL prune at `expires_at − 1 s` (kept) and at `expires_at`
    (deleted, unless the rank protects it), so the page can never say one thing and the prune do another."""
    GLOBALS = dict(scheduled_keep=2, scheduled_days=90, manual_days=3, manual_max_runs=3)

    @staticmethod
    def _mk(store, run_id, finished, *, schedule=None, status="done", cluster=CLUSTER):
        by = f"schedule:{schedule}" if schedule else "root"
        store.create(Run(id=run_id, report="groups", cluster=cluster, params={}, formats=["html"], generated_by=by,
                         generated_by_note="n", schedule=schedule, requested_at=finished, status=status, finished_at=finished))

    @staticmethod
    def _at(iso):
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)

    def _prune_keeps(self, store, at, run_id, **over):
        args = {**self.GLOBALS, **over}
        store.prune(now=at, **args)
        return store.get(run_id) is not None

    def test_a_per_schedule_override_drives_the_real_prune_boundary(self, tmp_path):
        # review of #233 (Codex): with every case on the globals, prune() passing `overrides=None` survived
        store = ArtifactStore(str(tmp_path))
        run_id = "20260101T060000.000000Z-w1"
        self._mk(store, run_id, "2026-01-01T06:00:00Z", schedule="weekly")
        over = {"overrides": {"weekly": (0, 1)}}
        standing = store.retention(**self.GLOBALS, **over)[run_id]
        assert (standing.expires_at, standing.retained_by) == ("2026-01-02T06:00:01Z", "age:1d")
        assert self._prune_keeps(store, self._at(standing.expires_at) - timedelta(seconds=1), run_id, **over)
        assert not self._prune_keeps(store, self._at(standing.expires_at), run_id, **over)

    def test_manual_within_the_cap_ages_from_completion_and_the_words_name_the_days(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        self._mk(store, "20260901T120000.000000Z-m1", "2026-09-01T12:00:00Z")
        standing = store.retention(**self.GLOBALS)["20260901T120000.000000Z-m1"]
        assert standing.retained_by == "manual:3d" and standing.expires_at == "2026-09-04T12:00:01Z"
        assert self._prune_keeps(store, self._at(standing.expires_at) - timedelta(seconds=1), "20260901T120000.000000Z-m1")
        assert not self._prune_keeps(store, self._at(standing.expires_at), "20260901T120000.000000Z-m1")

    def test_manual_beyond_the_cap_is_doomed_now_and_says_cap(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        for j in range(4):
            self._mk(store, f"20260901T12000{j}.000000Z-m{j}", f"2026-09-01T12:00:0{j}Z")
        plan = store.retention(**self.GLOBALS)
        assert plan["20260901T120000.000000Z-m0"] == (None, "manual:cap", plan["20260901T120000.000000Z-m0"].doomed_at)
        assert plan["20260901T120003.000000Z-m3"].retained_by == "manual:3d", "the newest three are within the cap"
        assert not self._prune_keeps(store, self._at("2026-09-01T12:00:05Z"), "20260901T120000.000000Z-m0"), "gone on the next prune"
        assert store.get("20260901T120001.000000Z-m1") is not None

    def test_manual_with_no_age_bound_is_held_by_the_cap_alone(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        self._mk(store, "20260901T120000.000000Z-m1", "2026-09-01T12:00:00Z")
        standing = store.retention(**{**self.GLOBALS, "manual_days": 0})["20260901T120000.000000Z-m1"]
        assert standing == (None, "manual:cap", None)
        assert self._prune_keeps(store, self._at("2036-01-01T00:00:00Z"), "20260901T120000.000000Z-m1", manual_days=0)

    def test_a_scheduled_run_among_the_newest_keep_is_kept_whatever_its_age_and_says_at_least_until(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        self._mk(store, "20260101T060000.000000Z-s1", "2026-01-01T06:00:00Z", schedule="weekly")
        self._mk(store, "20260108T060000.000000Z-s2", "2026-01-08T06:00:00Z", schedule="weekly")
        plan = store.retention(**self.GLOBALS)
        assert plan["20260108T060000.000000Z-s2"] == ("2026-04-08T06:00:01Z", f"newest:1/2 of weekly on {CLUSTER}", None)
        assert plan["20260101T060000.000000Z-s1"] == ("2026-04-01T06:00:01Z", f"newest:2/2 of weekly on {CLUSTER}", None)
        # long past both age bounds, both survive: the rank protects them
        assert self._prune_keeps(store, self._at("2027-01-01T00:00:00Z"), "20260101T060000.000000Z-s1")
        assert store.get("20260108T060000.000000Z-s2") is not None

    def test_a_scheduled_run_beyond_the_newest_keep_is_aged_and_the_words_say_so(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        for j, day in enumerate(("01", "08", "15")):
            self._mk(store, f"202601{day}T060000.000000Z-s{j}", f"2026-01-{day}T06:00:00Z", schedule="weekly")
        standing = store.retention(**self.GLOBALS)["20260101T060000.000000Z-s0"]
        assert standing.retained_by == "age:90d" and standing.expires_at == "2026-04-01T06:00:01Z"
        assert self._prune_keeps(store, self._at(standing.expires_at) - timedelta(seconds=1), "20260101T060000.000000Z-s0")
        assert not self._prune_keeps(store, self._at(standing.expires_at), "20260101T060000.000000Z-s0")
        assert store.get("20260108T060000.000000Z-s1") is not None, "the second newest stays"

    def test_a_scheduled_run_beyond_keep_with_no_age_bound_is_kept_indefinitely(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        for j, day in enumerate(("01", "08", "15")):
            self._mk(store, f"202601{day}T060000.000000Z-s{j}", f"2026-01-{day}T06:00:00Z", schedule="weekly")
        plan = store.retention(**{**self.GLOBALS, "scheduled_days": 0})
        assert plan["20260101T060000.000000Z-s0"] == (None, "age:0d", None)
        assert plan["20260115T060000.000000Z-s2"] == (None, f"newest:1/2 of weekly on {CLUSTER}", None)
        assert self._prune_keeps(store, self._at("2036-01-01T00:00:00Z"), "20260101T060000.000000Z-s0", scheduled_days=0)

    def test_a_per_schedule_override_names_its_own_keep_and_days(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        self._mk(store, "20260101T060000.000000Z-q1", "2026-01-01T06:00:00Z", schedule="quarterly")
        self._mk(store, "20260101T060000.000000Z-w1", "2026-01-01T06:00:00Z", schedule="weekly")
        plan = store.retention(**self.GLOBALS, overrides={"quarterly": (12, 2555)})
        assert plan["20260101T060000.000000Z-q1"] == ("2032-12-30T06:00:01Z", f"newest:1/12 of quarterly on {CLUSTER}", None)   # 2 555 days span two leap days
        assert plan["20260101T060000.000000Z-w1"] == ("2026-04-01T06:00:01Z", f"newest:1/2 of weekly on {CLUSTER}", None)

    def test_a_failed_run_ranks_like_a_done_one_and_a_queued_run_has_no_standing(self, tmp_path):
        store = ArtifactStore(str(tmp_path))
        self._mk(store, "20260108T060000.000000Z-f1", "2026-01-08T06:00:00Z", schedule="weekly", status="failed")
        store.create(Run(id="20260109T060000.000000Z-q1", report="groups", cluster=CLUSTER, params={}, formats=["html"],
                         generated_by="root", generated_by_note="n", schedule=None, requested_at="2026-01-09T06:00:00Z", status="queued"))
        plan = store.retention(**self.GLOBALS)
        assert plan["20260108T060000.000000Z-f1"].retained_by == f"newest:1/2 of weekly on {CLUSTER}"
        assert "20260109T060000.000000Z-q1" not in plan

    def test_the_api_carries_the_standing_on_the_list_and_on_one_run(self, service):
        client, app, clock = service
        r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": "groups", "cluster": CLUSTER, "formats": ["html"]}, headers=_viewer())
        run = _wait_done(client, r.json()["id"], _viewer())
        assert run["retained_by"] == "manual:3d" and run["expires_at"] == datetime.strptime(run["finished_at"], "%Y-%m-%dT%H:%M:%SZ") \
            .replace(tzinfo=UTC).__add__(timedelta(days=3, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        listed = client.get(f"{REPORT_PREFIX}/api/runs", headers=_viewer()).json()["runs"][0]
        assert (listed["expires_at"], listed["retained_by"]) == (run["expires_at"], run["retained_by"])
        assert "expires_at" in listed and "retained_by" in listed
