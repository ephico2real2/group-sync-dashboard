"""A run manifest's keys this build does not know survive a read and a rewrite (#600).

A newer build may write a field into `run.json` that this build's `Run` lacks. On a rollback the loader used to keep
only the known fields, so the field vanished from the index and, the first time this build rewrote the manifest (a
restart marks an in-flight run failed; the worker updates its status), from the file too: rolled forward again, the
newer build found it gone. The loader now keeps the unknown keys beside the run and writes them back; the API, which
serves `Run.public()`, is unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

from gsd.reporting.artifacts import ArtifactStore

RUN_ID = "20261006T120000-abcdef"


def _manifest(root: Path, **extra) -> Path:
    d = root / RUN_ID
    d.mkdir(parents=True)
    path = d / "run.json"
    path.write_text(json.dumps({
        "id": RUN_ID, "report": "group-inventory", "cluster": "c1", "params": {}, "formats": ["html"],
        "generated_by": "alice", "generated_by_note": "", "schedule": None,
        "requested_at": "2026-10-06T12:00:00Z", "status": "running", **extra,
    }))
    return path


def test_a_restart_rewrites_an_in_flight_run_and_keeps_the_keys_it_does_not_know(tmp_path):
    """The restart path: a run still `running` is marked failed and its manifest rewritten."""
    path = _manifest(tmp_path, future_field={"from": "a newer build"}, future_count=3)
    ArtifactStore(str(tmp_path))
    written = json.loads(path.read_text())
    assert written["status"] == "failed"
    assert written["future_field"] == {"from": "a newer build"}
    assert written["future_count"] == 3


def test_an_update_keeps_them_too(tmp_path):
    path = _manifest(tmp_path, status="done", future_field="kept")
    store = ArtifactStore(str(tmp_path))
    run = store.get(RUN_ID)
    run.error = "edited by this build"
    store.update(run)
    written = json.loads(path.read_text())
    assert written["future_field"] == "kept" and written["error"] == "edited by this build"


def test_the_api_view_of_a_run_is_unchanged(tmp_path):
    """`public()` is what the report API serves: the unknown keys are the file's, not the API's."""
    _manifest(tmp_path, status="done", future_field="kept")
    public = ArtifactStore(str(tmp_path)).get(RUN_ID).public()
    assert "future_field" not in public
    assert not any(key.startswith("unknown") for key in public)


def test_a_manifest_with_only_known_keys_is_written_as_before(tmp_path):
    path = _manifest(tmp_path)
    ArtifactStore(str(tmp_path))
    written = json.loads(path.read_text())
    assert set(written) == {"id", "report", "cluster", "params", "formats", "generated_by", "generated_by_note",
                            "schedule", "requested_at", "status", "started_at", "finished_at", "error", "sha256",
                            "snapshot_stamp", "bytes", "pdf_variant", "render_seconds", "origin"}
