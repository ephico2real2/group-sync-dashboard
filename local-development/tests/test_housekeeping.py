"""SPEC_H1 (#542): deleting report runs and database copies from the page — the API's half.

The dashboard decides the cluster-admin tier and records who deleted what; a report run is deleted by the report
service at the dashboard's request, with the service token; a database copy is file work on the dashboard's own
data volume. Every case runs against the real report app, reached through the `app.state.report_client` seam,
and a data volume laid out the way the lab's is (docs/specs/SPEC_H1_gui_cleanup.md §2): scheduled backups, two
pre-upgrade copies with their sidecars, and in pre-restore/ two kept sets (one stamped by restore-db.py, one by
the runbook's manual keep), a copy moved aside with its sidecar, and a keep that never finished.

Personas: `jane.admin` passes the cluster-admin tier; `auditor` passes the wide tier and fails this one (the
negative control); `alice` passes neither.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd import housekeeping
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.server import build_report_app
from test_visibility import _MapResolver

SECRET = b"h" * 48
SENTENCE = "For cluster administrators only."
ADMIN = "jane.admin"
SCHEDULE = "nightly-namespace-access"
NOW = datetime.now(UTC)


def H(user: str | None, *, page: bool = True) -> dict:
    """The proxy's identity header, and the custom header the page sends with every write."""
    headers = {"X-Forwarded-User": user} if user else {}
    return {**headers, "X-GSD-Interaction": "1"} if page else headers


def _stamp(days: float, *, micro: bool = True) -> str:
    return (NOW - timedelta(days=days)).strftime("%Y%m%dT%H%M%S.%fZ" if micro else "%Y%m%dT%H%M%SZ")


def _run(rid: str, *, days: float, schedule: str | None = None, status: str = "done", report: str = "groups") -> Run:
    finished = (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Run(id=rid, report=report, cluster="c1", params={}, formats=["html"],
               generated_by=f"schedule:{schedule}" if schedule else "jane.smith", generated_by_note="n",
               schedule=schedule, requested_at=finished, started_at=finished,
               finished_at=finished if status in ("done", "failed") else None, status=status,
               bytes={"json": 100, "html": 200} if status == "done" else {})


def _file(path: Path, data: bytes = b"SQLite format 3\x00copy", *, sidecar: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if sidecar:
        path.with_name(path.name + ".sha256").write_text(f"{'0' * 64}  {path.name}\n")
    return path


@dataclasses.dataclass
class Rig:
    client: TestClient
    app: object
    report_app: object
    data: Path

    @property
    def runs(self) -> set[str]:
        return set(self.report_app.state.store._runs)

    def names(self, kind: str) -> set[str]:
        return {c.name for c in housekeeping.list_copies(str(self.data / "gsd.db"), str(self.data / "backup"))
                if c.kind == kind}


def _layout(data: Path) -> None:
    """The lab's shapes, measured 2026-10-02 (SPEC_H1 §2.6): ages in days before now."""
    _file(data / "backup" / f"gsd-{_stamp(20)}.db")
    _file(data / "backup" / f"gsd-{_stamp(10)}.db")
    _file(data / "backup" / f"gsd-{_stamp(1)}.db")                       # the newest: guarded
    _file(data / "pre-upgrade" / f"pre-upgrade-{_stamp(40)}-schema-19-to-20-pod-a.db", sidecar=True)
    _file(data / "pre-upgrade" / f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db", sidecar=True)   # guarded
    _file(data / "pre-restore" / _stamp(30) / "gsd.db")                 # restore-db.py's keep
    _file(data / "pre-restore" / _stamp(30) / "gsd.db-wal", b"wal")
    _file(data / "pre-restore" / _stamp(3, micro=False) / "gsd.db")     # the runbook's manual keep: guarded
    _file(data / "pre-restore" / f"pre-upgrade-{_stamp(2)}-schema-21-to-22-pod-c.db", sidecar=True)   # moved aside
    _file(data / "pre-restore" / f"{_stamp(1)}.tmp" / "gsd.db")         # a keep that never finished: never listed


def _rig(tmp_path: Path, **over) -> tuple[TestClient, object, object, Path]:
    data, artifacts, snapshots = tmp_path / "data", tmp_path / "artifacts", tmp_path / "snapshots"
    for d in (data, artifacts, snapshots):
        d.mkdir()
    token = tmp_path / "token"
    token.write_bytes(SECRET)
    _layout(data)
    report_app = build_report_app(ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts),
                                                 pdf_enabled=False, housekeeping_enabled=True), secret=SECRET)
    store = report_app.state.store
    for run in (_run("20260101T000000.000000Z-m0ld", days=10), _run("20260102T000000.000000Z-mnew", days=1),
                *(_run(f"2026010{i}T000000.000000Z-s00{i}", days=5.5 - i, schedule=SCHEDULE) for i in range(1, 5)),
                _run("20260109T000000.000000Z-qued", days=0, status="queued"),
                _run("20260109T000001.000000Z-runn", days=0, schedule=SCHEDULE, status="running")):
        store.create(run)
        if run.status == "done":
            store.write(run.id, "html", b"<p>run</p>")
    settings = dict(clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X")],
                    db_path=str(data / "gsd.db"), backup_dir=str(data / "backup"), oauth_proxy_enabled=True,
                    housekeeping_enabled=True, reporting_url="http://report", reporting_token_file=str(token))
    settings.update(over)
    app = build_app(Settings(**settings), run_poller=False)
    app.state.tier_resolver = _MapResolver({ADMIN: "all", "auditor": "all"})
    app.state.cluster_admin_resolver = _MapResolver({ADMIN: "all"})
    app.state.report_client = TestClient(report_app, base_url="http://report")
    return app, report_app, data


@pytest.fixture
def rig(tmp_path):
    app, report_app, data = _rig(tmp_path)
    with TestClient(app) as client:
        yield Rig(client, app, report_app, data)


def _five(c: TestClient, who: dict) -> list:
    """Every housekeeping route once, as `who`."""
    return [c.get("/api/housekeeping/copies", headers=who),
            c.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=who),
            c.post("/api/housekeeping/copies/cleanup", json={}, headers=who),
            c.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=who),
            c.post("/api/housekeeping/reports/cleanup", json={}, headers=who)]


class TestT542_1_TheTier:
    """T542-1: the API refuses every route below the cluster-admin tier with the tier's own sentence, and refuses
    a request with no proxy-verified identity to record; nothing is deleted. Fails without the change: the
    routes do not exist (404 for each, not the refusal)."""

    @pytest.mark.parametrize("user", ["auditor", "alice"])
    def test_below_the_tier_every_route_refuses_with_the_tiers_sentence(self, rig, user):
        before = (rig.runs, rig.names("backup"))
        answers = _five(rig.client, H(user))
        assert [r.status_code for r in answers] == [403] * 5
        assert all(r.json()["detail"].startswith(SENTENCE) for r in answers)
        assert (rig.runs, rig.names("backup")) == before

    def test_no_identity_is_refused_with_the_reason(self, rig):
        answers = _five(rig.client, H(None))
        assert [r.status_code for r in answers] == [403] * 5
        assert all("needs an authenticated identity" in r.json()["detail"] for r in answers)

    def test_with_restrictions_off_nobody_can_delete(self, tmp_path):
        app, _, _ = _rig(tmp_path, view_restrictions_enabled=False)
        with TestClient(app) as c:
            assert [r.status_code for r in _five(c, H(ADMIN))] == [403] * 5

    def test_the_tier_lists_the_copies_with_the_guard_said(self, rig):
        body = rig.client.get("/api/housekeeping/copies", headers=H(ADMIN)).json()
        guarded = {c["kind"]: c["name"] for c in body["copies"] if c["guarded"]}
        assert guarded == {"backup": f"gsd-{_stamp(1)}.db",
                           "pre-upgrade": f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db",
                           "pre-restore": _stamp(3, micro=False)}
        assert [c["at"] for c in body["copies"]] == sorted((c["at"] for c in body["copies"]), reverse=True)
        assert body["directories"]["backup"] == str(rig.data / "backup")


class TestT542_2_ThePreviewBindsTheConfirm:
    """T542-2: a confirm deletes exactly the set its preview showed, or nothing: a set that changed in between is
    refused with 409 and the set as it is now. Fails without the change: the routes do not exist (404)."""

    def test_report_runs(self, rig):
        body = {"scope": f"schedule:{SCHEDULE}", "older_than_days": 0, "keep_newest": 0}
        preview = rig.client.post("/api/housekeeping/reports/cleanup", json=body, headers=H(ADMIN)).json()
        assert preview["preview"] is True and preview["count"] == 4 and preview["bytes"] == 1200
        assert rig.runs >= {i["id"] for i in preview["items"]}                      # a preview deletes nothing
        rig.report_app.state.store.create(_run("20260105T000000.000000Z-s005", days=0.5, schedule=SCHEDULE))
        stale = rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": preview["digest"]},
                                headers=H(ADMIN))
        assert stale.status_code == 409
        assert stale.json()["detail"]["preview"]["count"] == 5
        assert "20260105T000000.000000Z-s005" in rig.runs and len(rig.runs) == 9   # nothing deleted
        fresh = stale.json()["detail"]["preview"]["digest"]
        done = rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": fresh},
                               headers=H(ADMIN)).json()
        assert done["preview"] is False and done["count"] == 5
        assert not any(r.startswith("2026010") and r.endswith(("s001", "s002", "s003", "s004", "s005"))
                       for r in rig.runs)
        assert {"20260109T000001.000000Z-runn", "20260101T000000.000000Z-m0ld"} <= rig.runs

    def test_database_copies(self, rig):
        body = {"kinds": ["backup"], "older_than_days": 0}
        preview = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()
        assert {i["name"] for i in preview["items"]} == {f"gsd-{_stamp(20)}.db", f"gsd-{_stamp(10)}.db"}
        assert [k["name"] for k in preview["kept"]] == [f"gsd-{_stamp(1)}.db"]
        _file(rig.data / "backup" / f"gsd-{_stamp(0)}.db")      # a scheduled backup lands between the two
        stale = rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": preview["digest"]},
                                headers=H(ADMIN))
        assert stale.status_code == 409 and stale.json()["detail"]["preview"]["count"] == 3
        assert len(rig.names("backup")) == 4                                       # nothing deleted
        done = rig.client.post("/api/housekeeping/copies/cleanup",
                               json={**body, "confirm": stale.json()["detail"]["preview"]["digest"]},
                               headers=H(ADMIN)).json()
        assert done["count"] == 3 and done["failed"] == []
        assert rig.names("backup") == {f"gsd-{_stamp(0)}.db"}

    def test_a_digest_of_another_set_never_deletes(self, rig):
        r = rig.client.post("/api/housekeeping/copies/cleanup", json={"confirm": "0" * 64}, headers=H(ADMIN))
        assert r.status_code == 409 and len(rig.names("backup")) == 3


class TestT542_3_TheGuard:
    """T542-3: the newest copy in each directory is never deleted from the page, so restore-db.sh --list keeps a
    backup to restore, the last upgrade keeps its way back and the last restore its undo. Fails without the
    change: the routes do not exist (404)."""

    @pytest.mark.parametrize("kind, name", [
        ("backup", lambda: f"gsd-{_stamp(1)}.db"),
        ("pre-upgrade", lambda: f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db"),
        ("pre-restore", lambda: _stamp(3, micro=False)),
    ])
    def test_the_newest_of_each_directory_is_refused(self, rig, kind, name):
        r = rig.client.delete(f"/api/housekeeping/copies/{kind}/{name()}", headers=H(ADMIN))
        assert r.status_code == 409 and r.json()["detail"] == housekeeping.GUARDS[kind]
        assert name() in rig.names(kind)

    def test_the_widest_cleanup_leaves_the_guarded_copies_and_what_is_not_a_copy(self, rig):
        body = {"kinds": list(housekeeping.COPY_KINDS), "older_than_days": 0}
        digest = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()["digest"]
        done = rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": digest},
                               headers=H(ADMIN)).json()
        assert done["count"] == 5
        assert rig.names("backup") == {f"gsd-{_stamp(1)}.db"}
        assert sorted(p.name for p in (rig.data / "pre-upgrade").iterdir()) == sorted(
            [f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db", f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db.sha256"])
        # the moved-aside copy went with its sidecar; the guarded set and the unfinished keep stayed
        assert sorted(p.name for p in (rig.data / "pre-restore").iterdir()) == sorted(
            [_stamp(3, micro=False), f"{_stamp(1)}.tmp"])
        assert (rig.data / "gsd.db").is_file()

    def test_the_only_backup_is_kept(self, rig):
        for name in (f"gsd-{_stamp(20)}.db", f"gsd-{_stamp(10)}.db"):
            assert rig.client.delete(f"/api/housekeeping/copies/backup/{name}", headers=H(ADMIN)).status_code == 200
        only = f"gsd-{_stamp(1)}.db"
        assert rig.client.delete(f"/api/housekeeping/copies/backup/{only}", headers=H(ADMIN)).status_code == 409
        assert rig.names("backup") == {only}


class TestT542_4_InFlightRunsStay:
    """T542-4: a queued or running run is never deleted, by the per-run delete (409) or by any cleanup. Fails
    without the change: the routes do not exist (404)."""

    @pytest.mark.parametrize("rid, status", [("20260109T000000.000000Z-qued", "queued"),
                                             ("20260109T000001.000000Z-runn", "running")])
    def test_the_per_run_delete_refuses(self, rig, rid, status):
        r = rig.client.delete(f"/api/housekeeping/reports/{rid}", headers=H(ADMIN))
        assert r.status_code == 409 and f"is {status}" in r.json()["detail"]
        assert rid in rig.runs

    def test_the_widest_cleanup_leaves_them(self, rig):
        body = {"scope": "all", "older_than_days": 0, "keep_newest": 0}
        preview = rig.client.post("/api/housekeeping/reports/cleanup", json=body, headers=H(ADMIN)).json()
        assert preview["count"] == 6
        rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": preview["digest"]},
                        headers=H(ADMIN))
        assert rig.runs == {"20260109T000000.000000Z-qued", "20260109T000001.000000Z-runn"}

    def test_keep_newest_and_the_age_apply_together(self, rig):
        body = {"scope": "all", "older_than_days": 3, "keep_newest": 1}
        ids = {i["id"] for i in rig.client.post("/api/housekeeping/reports/cleanup", json=body,
                                                 headers=H(ADMIN)).json()["items"]}
        # manual: m0ld (10 d) goes, mnew is the newest of its group; scheduled: s001 (4.5 d) and s002 (3.5 d) go,
        # s003 (2.5 d, not older than 3 days) and s004 (the newest) stay
        assert ids == {"20260101T000000.000000Z-m0ld", "20260101T000000.000000Z-s001",
                       "20260102T000000.000000Z-s002"}


class TestT542_5_NoPathFromTheRequest:
    """T542-5: a name is matched against the directory's own listing, never joined onto a path: a dot-dot, an
    encoded slash, the live database's name and a symlink named like a copy are all 404, and nothing outside
    the three directories changes. Fails without the change: the routes do not exist (404 too, so the test also
    asserts that a real copy IS deletable through the same route)."""

    def test_traversal_and_symlinks_are_not_copies(self, rig):
        live = rig.data / "gsd.db"
        assert live.is_file()
        (rig.data / "backup" / f"gsd-{_stamp(-1)}.db").symlink_to(live)          # named like the newest copy
        (rig.data / "pre-restore" / _stamp(-1)).symlink_to(rig.data, target_is_directory=True)
        before = sorted(p.name for p in rig.data.rglob("*"))
        for kind, name in (("backup", "%2E%2E"), ("backup", "..%2Fgsd.db"), ("backup", "gsd.db"),
                           ("pre-restore", "%2E%2E"), ("backup", f"gsd-{_stamp(-1)}.db"),
                           ("pre-restore", _stamp(-1)), ("..", "gsd.db"), ("data", "gsd.db")):
            r = rig.client.delete(f"/api/housekeeping/copies/{kind}/{name}", headers=H(ADMIN))
            assert r.status_code in (404, 405), (kind, name, r.status_code)
        assert sorted(p.name for p in rig.data.rglob("*")) == before and live.is_file()
        listed = rig.client.get("/api/housekeeping/copies", headers=H(ADMIN)).json()["copies"]
        assert not any(c["name"] == _stamp(-1) or c["name"] == f"gsd-{_stamp(-1)}.db" for c in listed)
        r = rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        assert r.status_code == 200 and r.json()["deleted"]["name"] == f"gsd-{_stamp(20)}.db"


class TestT542_6_TheAuditLine:
    """T542-6: one `event-name key=value` line per deleted item, naming the viewer (who), the item (what); the
    log record's time is when. Fails without the change: no route, so no line."""

    def test_one_line_per_item(self, rig, caplog):
        caplog.set_level(logging.INFO, logger="gsd.api")
        rig.client.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
        rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        body = {"kinds": ["pre-restore"], "older_than_days": 0}
        digest = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()["digest"]
        rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": digest}, headers=H(ADMIN))
        lines = [r.getMessage() for r in caplog.records if r.name == "gsd.api"]
        assert ("report-run-deleted run=20260101T000000.000000Z-m0ld report=groups cluster=c1 bytes=300 "
                f"by={ADMIN}") in lines
        assert f"db-copy-deleted kind=backup copy=gsd-{_stamp(20)}.db directory={rig.data / 'backup'} bytes=20 by={ADMIN}" in lines
        assert sum(1 for line in lines if line.startswith("db-copy-deleted kind=pre-restore ")) == 2
        assert all(line.endswith(f"by={ADMIN}") for line in lines if "-deleted " in line)


class TestT542_7_TheMetricNamesNoOne:
    """T542-7: gsd_housekeeping_deleted_total counts by kind, pre-seeded to 0, and the public /metrics carries no
    viewer, run id or copy name. Fails without the change: the family does not exist."""

    def test_counted_by_kind_and_nothing_else(self, rig):
        assert 'gsd_housekeeping_deleted_total{kind="pre-upgrade"} 0.0' in rig.client.get("/metrics").text
        rig.client.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
        rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        text = rig.client.get("/metrics").text
        assert 'gsd_housekeeping_deleted_total{kind="report-run"} 1.0' in text
        assert 'gsd_housekeeping_deleted_total{kind="backup"} 1.0' in text
        for secret in (ADMIN, "m0ld", _stamp(20)):
            assert secret not in text, secret


class TestT542_9_TheSwitchAndTheContract:
    """T542-9: `housekeeping_enabled` off (the code's default) registers no route on either service, so R6's
    GET-only default holds; on, the writes are exactly these four and the report service's two. Fails without
    the change: the setting does not exist."""

    WRITES = ["DELETE /api/housekeeping/copies/{kind}/{name}", "DELETE /api/housekeeping/reports/{run_id}",
              "POST /api/housekeeping/copies/cleanup", "POST /api/housekeeping/reports/cleanup"]

    @staticmethod
    def _writes(app) -> list[str]:
        return sorted(f"{m.upper()} {p}" for p, ops in app.openapi()["paths"].items() for m in ops
                      if m.lower() not in ("get", "head", "options") and p.startswith("/api/housekeeping"))

    def test_the_dashboard(self, tmp_path):
        on, _, _ = _rig(tmp_path)
        assert self._writes(on) == self.WRITES
        off = build_app(Settings(clusters=[], db_path=str(tmp_path / "off.db")), run_poller=False)
        assert self._writes(off) == [] and "/api/housekeeping/copies" not in off.openapi()["paths"]
        with TestClient(off) as c:
            assert c.get("/api/version").json()["features"]["housekeeping"] is False
            assert c.delete("/api/housekeeping/reports/x", headers=H(ADMIN)).status_code in (404, 405)

    def test_the_report_service(self, tmp_path):
        def non_get(app):
            return sorted((m, r.path) for r in app.routes if hasattr(r, "methods")
                          for m in r.methods - {"GET", "HEAD", "OPTIONS"})
        base = dict(snapshot_dir=str(tmp_path), artifact_dir=str(tmp_path / "a"), pdf_enabled=False)
        off = build_report_app(ReportSettings(**base), secret=SECRET)
        on = build_report_app(ReportSettings(**base, housekeeping_enabled=True), secret=SECRET)
        assert non_get(off) == [("POST", f"{REPORT_PREFIX}/api/preview"), ("POST", f"{REPORT_PREFIX}/api/runs")]
        assert non_get(on) == sorted(non_get(off) + [("DELETE", f"{REPORT_PREFIX}/api/runs/{{run_id}}"),
                                                     ("POST", f"{REPORT_PREFIX}/api/runs/cleanup")])

    def test_a_viewers_ticket_cannot_delete_on_the_report_service(self, rig):
        from gsd.reporting import TICKET_HEADER
        from gsd.reporting.ticket import mint
        direct = TestClient(rig.report_app)
        ticket = {TICKET_HEADER: mint(SECRET, ADMIN, "all", 300), "X-Forwarded-User": ADMIN}
        r = direct.delete(f"{REPORT_PREFIX}/api/runs/20260101T000000.000000Z-m0ld", headers=ticket)
        assert r.status_code == 403 and "20260101T000000.000000Z-m0ld" in rig.runs


class TestT542_10_TheCustomHeader:
    """T542-10: every write needs the X-GSD-Interaction header the page sends (OWASP's custom-request-header
    defence), and a body a cross-site form can send is not read as JSON. Fails without the change: 404."""

    def test_a_write_without_the_header_is_refused(self, rig):
        answers = _five(rig.client, H(ADMIN, page=False))
        assert answers[0].status_code == 200                                   # the GET listing needs no header
        assert [r.status_code for r in answers[1:]] == [403] * 4
        assert all("X-GSD-Interaction" in r.json()["detail"] for r in answers[1:])

    def test_a_form_body_is_not_json(self, rig):
        r = rig.client.post("/api/housekeeping/copies/cleanup", content=b'{"older_than_days": 0}',
                            headers={**H(ADMIN), "Content-Type": "text/plain"})
        assert r.status_code == 422


class TestT542_11_TheReportServicesAnswers:
    """T542-11: with reporting off the report routes say so (404); an unreachable report service is a 502 that
    names it. Fails without the change: 404 for every case, with no such sentence."""

    def test_reporting_off(self, tmp_path):
        app, _, _ = _rig(tmp_path, reporting_url="")
        with TestClient(app) as c:
            r = c.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
            assert r.status_code == 404 and r.json()["detail"] == "reporting is not enabled on this deployment"

    def test_unreachable(self, tmp_path):
        import httpx
        app, _, _ = _rig(tmp_path)

        def refuse(request):
            raise httpx.ConnectError("connection refused", request=request)

        app.state.report_client = httpx.Client(base_url="http://report", transport=httpx.MockTransport(refuse))
        with TestClient(app) as c:
            r = c.post("/api/housekeeping/reports/cleanup", json={}, headers=H(ADMIN))
            assert r.status_code == 502 and r.json()["detail"] == "the report service could not be reached: ConnectError"


class TestT542_13_TheChart:
    """T542-13: `housekeeping.enabled` reaches both pods — the dashboard's ConfigMap key and the report pod's
    environment — on by default and off when set; it adds no RBAC (§4.3 diffs every rendered rule). Fails without
    the change: neither the key nor the variable is rendered."""

    @pytest.mark.parametrize("sets, word", [((), "true"), (("housekeeping.enabled=false",), "false")])
    def test_both_pods_read_the_value(self, sets, word):
        from test_chart_pdb import _render
        docs = _render(*sets)
        config = next(d for d in docs if d.get("kind") == "ConfigMap" and "clusters.yaml" in (d.get("data") or {}))
        assert f"housekeepingEnabled: {word}" in config["data"]["clusters.yaml"]
        report = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report"))
        env = {e["name"]: e.get("value") for e in report["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["GSD_REPORT_HOUSEKEEPING_ENABLED"] == word
