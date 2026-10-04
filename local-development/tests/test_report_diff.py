"""What changed between two runs (docs/specs/SPEC_F3_report_diff.md, #108): a `report-diff` run compares the
sealed data of two stored runs of one report on one cluster, row by row, and is itself a sealed, stored run that
renders through the ordinary renderers; the catalogue, the stored inputs and the retention of other runs stay as
they are."""
from __future__ import annotations

import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest

from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import Run
from gsd.reporting.catalogue import REGISTRY
from gsd.reporting.config import ReportSettings
from gsd.reporting.snapshot import Snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot
from test_report_seal import _other_run, _run, _page_one, snap  # noqa: F401 — `snap` is a fixture
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

DIFF = "report-diff"


def _build(base: dict, head: dict):
    from gsd.reporting.diff import build_diff   # imported here: before SPEC_F3 the module does not exist
    return build_diff(base, head, run_id="20260906T130000.000000Z-ef56", now=NOW, generated_by="alice",
                      generated_by_note="proxy-verified", settings=ReportSettings())


def _doc(report) -> dict:
    return json.loads(report.to_json())


def _changed(diff) -> set:
    summary = next(s for s in diff.sections if s.title == "Summary").blocks[0]
    return {(row[0], row[1]) for row in summary.rows}


def test_t108_1_rows_added_removed_and_no_change(snap):  # noqa: F811
    """A row only in the head is added, one only in the base removed, a changed cell is one of each, a duplicate
    row counts twice, a section on one side only is all added; identical data is "No change". Without SPEC_F3:
    ModuleNotFoundError, gsd.reporting.diff."""
    base = _doc(_run(snap, "groups"))
    same = _build(base, copy.deepcopy(base))
    assert _changed(same) == set() and same.totals == {"blocks_changed": 0, "rows_removed": 0, "rows_added": 0}
    assert any(b.kind == "note" and b.text.startswith("No change:") for s in same.sections for b in s.blocks)
    head = copy.deepcopy(base)
    inventory = next(s for s in head["sections"] if s["title"] == "Inventory")["blocks"][0]
    gone, changed = inventory["rows"][0], inventory["rows"][1]
    inventory["rows"] = [[changed[0], "another-provider", *changed[2:]], *inventory["rows"][2:], inventory["rows"][2]]
    head["sections"].append({"title": "New section", "sealed": True, "page_break": False,
                             "blocks": [{"kind": "kv", "title": "Facts", "items": [["k", "v"]]}]})
    diff = _build(base, head)
    blocks = {s.title: s.blocks for s in diff.sections}
    removed, added = blocks["Inventory — Groups"]
    assert removed.rows == sorted([gone, changed], key=lambda r: json.dumps(r, sort_keys=True))
    assert added.rows == sorted([[changed[0], "another-provider", *changed[2:]], inventory["rows"][-1]],
                                key=lambda r: json.dumps(r, sort_keys=True))
    assert blocks["New section — Facts"][1].rows == [["k", "v"]] and blocks["New section — Facts"][0].rows == []
    assert diff.totals == {"blocks_changed": 2, "rows_removed": 2, "rows_added": 3}


def test_diff_reports_stable_coverage_conclusions_without_read_cycle_noise(snap):  # noqa: F811
    """A loss of Namespace-read coverage is a material change even when every report row is equal;
    timestamps embedded in coverage notes and retention watermarks are not."""
    base = _doc(_run(snap, "groups"))
    base["coverage"]["namespaces_read"] = "ok"
    base["coverage"]["attests_absence"] = True
    moving = copy.deepcopy(base)
    moving["coverage"]["namespaces_note"] += " Read again at 2026-09-06T12:01:00Z."
    moving["coverage"]["history_retained_since"]["membership_event"] = "2026-09-06T12:01:00Z"
    assert _changed(_build(base, moving)) == set()

    head = copy.deepcopy(moving)
    head["coverage"]["namespaces_read"] = "forbidden"
    head["coverage"]["attests_absence"] = False
    diff = _build(base, head)
    assert _changed(diff) == {("Evidence coverage", "Coverage")}
    removed, added = next(s for s in diff.sections if s.title == "Evidence coverage — Coverage").blocks
    assert removed.rows == [["Attests absence", True], ["Namespace read", "ok"]]
    assert added.rows == [["Attests absence", False], ["Namespace read", "forbidden"]]


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_t108_2_two_runs_over_one_snapshot_diff_to_no_change(snap, name):  # noqa: F811
    """Every report: another viewer, run id and minute, one snapshot: nothing changed, because page one (who and
    when) is not sealed data and a report's data ends at the snapshot's stamp (#592). Without SPEC_F3:
    ModuleNotFoundError; without #592, login-activity's Window `To` moves with the minute."""
    diff = _build(_doc(_run(snap, name)), _doc(_other_run(snap, name)))
    assert _changed(diff) == set(), name


def test_access_certification_diff_ignores_a_new_snapshot_of_the_same_data(tmp_path):
    """#589: a new snapshot stamp is provenance, not a changed Campaign row."""
    store = seed_store(str(tmp_path / "writer.db"))
    directory = tmp_path / "snapshots"
    directory.mkdir()
    try:
        first = Snapshot(write_snapshot(store, directory))
        second = Snapshot(write_snapshot(store, directory, at=NOW + timedelta(minutes=5)))
    finally:
        store.close()
    try:
        base = _doc(_run(first, "access-certification"))
        head = _doc(_other_run(second, "access-certification"))
    finally:
        first.close()
        second.close()
    assert base["sealed_provenance"]["snapshot_stamp"] != head["sealed_provenance"]["snapshot_stamp"]
    assert _changed(_build(base, head)) == set()


def _a_later_poll_and_read(tmp_path: Path, monkeypatch) -> tuple[Snapshot, Snapshot, str]:
    """Two snapshots of one seeded database that differ only in the poll and login-capture read instants (#607):
    the first polled and stamped at the seed's NOW, the second five minutes later after one more successful poll
    and one more read."""
    import gsd.store
    monkeypatch.setattr(gsd.store, "now_iso", lambda: NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
    store = seed_store(str(tmp_path / "writer.db"))
    directory = tmp_path / "snapshots"
    directory.mkdir()
    later = (NOW + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        first = Snapshot(write_snapshot(store, directory))
        monkeypatch.setattr(gsd.store, "now_iso", lambda: later)
        store.record_poll(CLUSTER, "ok", None)
        store.record_login_read(CLUSTER, later)
        second = Snapshot(write_snapshot(store, directory, at=NOW + timedelta(minutes=5)))
    finally:
        store.close()
    return first, second, later


def test_t607_1_compliance_snapshot_diffs_to_no_change_across_a_new_poll_and_read(tmp_path, monkeypatch):
    """#607: the poll's and the read's instants are on page one, not in a sealed section, so two snapshots of the
    same data diff to "No change"; page one still shows both instants. Without the change the diff shows
    `Key figures — Sync pipeline` (Last poll) and `What this evidence attests — Coverage` (last read)."""
    first, second, later = _a_later_poll_and_read(tmp_path, monkeypatch)
    try:
        base, head = _run(first, "compliance-snapshot"), _other_run(second, "compliance-snapshot")
    finally:
        first.close()
        second.close()
    assert (base.provenance["last_poll"], head.provenance["last_poll"]) == ("2026-09-06T12:00:00Z", later)
    assert _changed(_build(_doc(base), _doc(head))) == set()
    page_one = head.sections[0]
    assert _page_one(head)["Last poll"] == f"{later} — ok"
    assert any(b.kind == "note" and f"(last read {later})" in b.text for b in page_one.blocks)


def test_t607_2_login_activity_shows_only_its_window_moving_across_a_new_poll_and_read(tmp_path, monkeypatch):
    """#607 and #592 together: login-activity's window ends at each snapshot's stamp, so two snapshots five minutes
    apart change its From and To and nothing else; the last log read is on page one only. Without the change the
    Window block also removes and adds `Last log read`."""
    first, second, later = _a_later_poll_and_read(tmp_path, monkeypatch)
    try:
        base, head = _run(first, "login-activity"), _other_run(second, "login-activity")
    finally:
        first.close()
        second.close()
    diff = _build(_doc(base), _doc(head))
    assert _changed(diff) == {("Summary", "Window")}
    removed, added = next(s for s in diff.sections if s.title == "Summary — Window").blocks
    assert [row[0] for row in removed.rows] == [row[0] for row in added.rows] == ["From", "To"]
    assert ["To", "2026-09-06T12:05:00Z"] in added.rows
    assert any(b.kind == "note" and f"(last read {later})" in b.text for b in head.sections[0].blocks)


def _done(client, report="groups", cluster=CLUSTER, headers=None, **body) -> dict:
    r = client.post(f"{REPORT_PREFIX}/api/runs", json={"report": report, "cluster": cluster, **body},
                    headers=headers or _viewer())
    assert r.status_code == 202, r.text
    run = _wait_done(client, r.json()["id"], headers or _viewer())
    assert run["status"] == "done", run.get("error")
    return run


def _diff(client, base: str, head: str, **body):
    return client.post(f"{REPORT_PREFIX}/api/runs", json={"report": DIFF, "cluster": CLUSTER,
                                                          "params": {"base": base, "head": head}, **body},
                       headers=_viewer())


def _files(app, run_id: str) -> dict:
    d = Path(app.state.store.root) / run_id
    return {p.name: p.read_bytes() for p in d.iterdir()}


def test_t108_4_a_stored_diff_seals_renders_and_leaves_its_inputs(service):  # noqa: F811
    """A diff run stores and serves json, html, pdf and csv with its own seal; its record names both runs and
    both sha256s; two diffs of one pair hash the same; it is a manual run; the two inputs' files are byte-equal
    afterwards. Without SPEC_F3: 404 unknown report 'report-diff'."""
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    before = {r: _files(app, r) for r in (base["id"], head["id"])}
    r = _diff(client, base["id"], head["id"], formats=["html", "pdf", "csv"])
    assert r.status_code == 202, r.text
    run = _wait_done(client, r.json()["id"], _viewer())
    assert run["status"] == "done", run.get("error")
    assert run["report"] == DIFF and run["schedule"] is None and run["retained_by"].startswith("manual:")
    assert run["params"] == {"report": "groups", "base": base["id"], "head": head["id"],
                             "base_sha256": base["sha256"], "head_sha256": head["sha256"]}
    assert set(run["bytes"]) == {"json", "html", "pdf", "csv"}
    for fmt in ("json", "html", "pdf", "csv"):
        a = client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": fmt}, headers=_viewer())
        assert a.status_code == 200 and a.headers["x-gsd-report-sha256"] == run["sha256"], fmt
    doc = json.loads(client.get(f"{REPORT_PREFIX}/api/runs/{run['id']}/artifact", params={"format": "json"},
                                headers=_viewer()).content)
    assert doc["name"] == DIFF and doc["sha256"] == run["sha256"] and doc["totals"]["blocks_changed"] == 0
    clock["now"] += timedelta(minutes=1)
    again = _wait_done(client, _diff(client, base["id"], head["id"], formats=["html"]).json()["id"], _viewer())
    assert again["sha256"] == run["sha256"], "two diffs of one pair are the same evidence"
    assert {r: _files(app, r) for r in (base["id"], head["id"])} == before, "a diff never rewrites its inputs"


def test_diff_refuses_a_base_newer_than_the_head(service):  # noqa: F811
    """#588: the API refuses a swapped pair before queuing the diff."""
    client, _, clock = service
    earlier = _done(client)
    clock["now"] += timedelta(minutes=1)
    later = _done(client)
    response = _diff(client, later["id"], earlier["id"])
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == (
        f"base {later['id']} is newer than head {earlier['id']}: "
        "a diff compares an earlier run with a later one"
    )


def test_t108_5_refusals(service):  # noqa: F811
    """422 for an unknown base, an unfinished one, another report, another cluster, a pruned .json, a diff of a
    diff, one run twice, a schedule and stray parameters. Without SPEC_F3: every request is a 404."""
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    other = _done(client, report="users")
    store = app.state.store
    queued = store.create(Run(id="20260906T000000.000000Z-0000", report="groups", cluster=CLUSTER, params={},
                              formats=[], generated_by="root", generated_by_note="", schedule=None,
                              requested_at="2026-09-06T00:00:00Z"))
    elsewhere = store.create(Run(**{**store.get(base["id"]).public(), "id": "20260906T000001.000000Z-0001",
                                    "cluster": "another-cluster"}))
    store.write(elsewhere.id, "json", store.read(base["id"], "json"))
    cases = {
        "unknown": _diff(client, "20200101T000000.000000Z-dead", head["id"]),
        "queued": _diff(client, queued.id, head["id"]),
        "report": _diff(client, other["id"], head["id"]),
        "cluster": _diff(client, elsewhere.id, head["id"]),
        "same": _diff(client, head["id"], head["id"]),
        "schedule": client.post(f"{REPORT_PREFIX}/api/runs", headers=SERVICE, json={
            "report": DIFF, "cluster": CLUSTER, "schedule": "nightly", "params": {"base": base["id"], "head": head["id"]}}),
        "params": client.post(f"{REPORT_PREFIX}/api/runs", headers=_viewer(), json={
            "report": DIFF, "cluster": CLUSTER, "params": {"base": base["id"], "head": head["id"], "x": 1}}),
    }
    diff = _wait_done(client, _diff(client, base["id"], head["id"]).json()["id"], _viewer())
    cases["diff of a diff"] = _diff(client, diff["id"], head["id"])
    (Path(store.root) / base["id"] / "report.json").unlink()
    cases["pruned"] = _diff(client, base["id"], head["id"])
    for case, r in cases.items():
        assert r.status_code == 422, (case, r.status_code, r.text)


def test_t108_6_the_worker_refuses_an_input_that_changed_or_predates_the_seal(service):  # noqa: F811
    """A base rewritten after the request, or a .json written before 4.1.0, fails the diff run with a sentence,
    and no other run. Without SPEC_F3: 404 at the request."""
    from gsd.reporting.diff import build_diff_run
    from gsd.reporting.catalogue.common import ValidationError
    client, app, clock = service
    base = _done(client)
    clock["now"] += timedelta(minutes=1)
    head = _done(client)
    store = app.state.store
    run = Run(id="20260906T000002.000000Z-0002", report=DIFF, cluster=CLUSTER, formats=[], generated_by="root",
              generated_by_note="", schedule=None, requested_at="2026-09-06T00:00:02Z",
              params={"report": "groups", "base": base["id"], "head": head["id"],
                      "base_sha256": "0" * 64, "head_sha256": head["sha256"]})
    with pytest.raises(ValidationError, match="sha256 recorded"):
        build_diff_run(store, run, ReportSettings(), NOW)

    old = json.loads(store.read(base["id"], "json"))
    tampered = copy.deepcopy(old)
    inventory = next(s for s in tampered["sections"] if s["title"] == "Inventory")["blocks"][0]
    inventory["rows"][0][0] = "edited-in-place"
    store.write(base["id"], "json", json.dumps(tampered).encode("utf-8"))
    run.params["base_sha256"] = base["sha256"]
    with pytest.raises(ValidationError, match="sha256 recorded"):
        build_diff_run(store, run, ReportSettings(), NOW)

    del old["sealed_provenance"]
    with pytest.raises(ValidationError, match="before 4.1.0"):
        _build(old, json.loads(store.read(head["id"], "json")))


def test_t108_7_the_catalogue_stays_eleven(service):  # noqa: F811
    """`report-diff` is not a catalogue entry: the catalogue lists eleven and the status counts eleven. Passes before
    and after SPEC_F3: it guards the issue's "Must not change"."""
    client, _, _ = service
    assert DIFF not in REGISTRY and len(REGISTRY) == 11
    names = [r["name"] for r in client.get(f"{REPORT_PREFIX}/api/reports", headers=_viewer()).json()["reports"]]
    assert len(names) == 11 and DIFF not in names
    assert client.get(f"{REPORT_PREFIX}/api/status", headers=_viewer()).json()["service"]["reports_enabled"] == 11


def test_t108_8_a_diff_leaves_scheduled_retention_alone(service):  # noqa: F811
    """A diff is a manual run: a scheduled run's standing is the same before and after one. Passes before and
    after SPEC_F3 for the scheduled run (the guard); the diff's own `manual:` standing is T108-4."""
    client, app, clock = service
    sched = _done(client, headers=SERVICE, schedule="nightly")
    clock["now"] += timedelta(minutes=1)
    manual = _done(client)
    standing = lambda: client.get(f"{REPORT_PREFIX}/api/runs/{sched['id']}", headers=_viewer()).json()["retained_by"]  # noqa: E731
    before = standing()
    _diff(client, manual["id"], _done(client)["id"])
    assert standing() == before
