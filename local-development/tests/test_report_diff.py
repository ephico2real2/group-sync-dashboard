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
from reporting_seed import CLUSTER, NOW
from test_report_seal import CLOCK_DERIVED, _other_run, _run, snap  # noqa: F401 — `snap` is a fixture
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

DIFF = "report-diff"
#: What the five clock-reading reports show when the clock moves two hours over one snapshot (measured, §2.3).
CLOCK_MOVED = {
    "login-activity": {("Summary", "Window")},
    "groups": set(),
    "dormant-access": set(),
    "groupsync-health": {("GroupSync CRs", "CRs"), ("Summary", "Pipeline")},
    "compliance-snapshot": {("Key figures", "Sync pipeline")},
}


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


@pytest.mark.parametrize("name", sorted(set(REGISTRY) - CLOCK_DERIVED))
def test_t108_2_two_runs_over_one_snapshot_diff_to_no_change(snap, name):  # noqa: F811
    """The six clock-free reports: another viewer, run id and minute, one snapshot: nothing changed, because page
    one (who and when) is not sealed data. Without SPEC_F3: ModuleNotFoundError."""
    diff = _build(_doc(_run(snap, name)), _doc(_other_run(snap, name)))
    assert _changed(diff) == set(), name


@pytest.mark.parametrize("name", sorted(CLOCK_DERIVED))
def test_t108_3_a_clock_reading_report_shows_what_the_clock_moved(snap, name):  # noqa: F811
    """The five reports that read the generation clock: two hours apart over one snapshot, the diff shows exactly
    the blocks computed against the clock (CLOCK_MOVED, measured), and nothing else. Without SPEC_F3:
    ModuleNotFoundError."""
    later = _run(snap, name, now=NOW + timedelta(hours=2), run_id="20260906T140000.000000Z-cd34")
    assert _changed(_build(_doc(_run(snap, name)), _doc(later))) == CLOCK_MOVED[name], name


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
