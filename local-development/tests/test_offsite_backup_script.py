"""The chart's copy script, against a real VACUUM INTO backup.

Loaded from the chart directory rather than installed: it is shipped as a ConfigMap, and the
test must exercise the exact bytes that ship. Stdlib only, so it also runs here without the
image.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sqlite3

import pytest

from gsd.store import Store

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("offsite_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def source(tmp_path):
    """A backup directory with one real backup in it, made the way the app makes them."""
    store = Store(str(tmp_path / "gsd.db"))
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    for i in range(5):
        store.record_sync_event("crc", "corp", "ns", f"2026-08-02T10:{i:02d}:00Z",
                                "2026-08-02T10:00:30Z", "0 * * * *", i)
    backups = tmp_path / "backup"
    assert store.backup(str(backups), keep=10)
    yield backups, store
    store.close()


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestShip:
    def test_copies_the_newest_with_a_sidecar_and_verifies_it(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "3"]) == 0
        (copy,) = sorted(dest.glob("gsd-*.db"))
        sidecar = dest / (copy.name + ".sha256")
        digest, name = sidecar.read_text().split()
        assert name == copy.name and digest == _sha(copy)
        conn = sqlite3.connect(f"file:{copy}?immutable=1", uri=True)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 5
        finally:
            conn.close()
        out = capsys.readouterr().out
        assert "integrity_check ok" in out and "sync_event rows 5" in out
        assert not list(dest.glob("*.part"))

    def test_picks_the_newest_by_name(self, script, source, tmp_path):
        backups, store = source
        store.record_sync_event("crc", "corp", "ns", "2026-08-02T11:00:00Z",
                                "2026-08-02T11:00:30Z", "0 * * * *", 9)
        newest = store.backup(str(backups), keep=10)
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert [p.name for p in dest.glob("gsd-*.db")] == [pathlib.Path(newest).name]

    def test_a_second_run_is_a_no_op_that_still_succeeds(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (copy,) = dest.glob("gsd-*.db")
        before = copy.stat().st_mtime_ns
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert copy.stat().st_mtime_ns == before
        assert "already shipped" in capsys.readouterr().out

    def test_prunes_the_destination_to_keep_with_sidecars(self, script, source, tmp_path):
        backups, store = source
        dest = tmp_path / "offsite"
        for _ in range(4):
            store.backup(str(backups), keep=10)
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "2"]) == 0
        copies = sorted(dest.glob("gsd-*.db"))
        assert len(copies) == 2
        assert sorted(p.name[:-7] for p in dest.glob("*.sha256")) == [c.name for c in copies]
        assert copies[-1].name == sorted(backups.glob("gsd-*.db"))[-1].name

    def test_keep_zero_keeps_everything(self, script, source, tmp_path):
        backups, store = source
        dest = tmp_path / "offsite"
        for _ in range(3):
            store.backup(str(backups), keep=10)
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "0"]) == 0
        assert len(list(dest.glob("gsd-*.db"))) == 3


class TestFailures:
    def test_a_copy_that_is_not_a_database_fails_and_leaves_nothing(self, script, tmp_path, capsys):
        backups = tmp_path / "backup"
        backups.mkdir()
        (backups / "gsd-20260904T000000.000000Z.db").write_bytes(b"not a database" * 100)
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 1
        assert "ERROR" in capsys.readouterr().err
        assert not list(dest.glob("gsd-*")) and not list(dest.glob("*.part"))

    def test_a_corrupt_copy_fails(self, script, source, tmp_path, capsys):
        backups, _ = source
        (victim,) = backups.glob("gsd-*.db")
        data = bytearray(victim.read_bytes())
        data[4096:4096 + 512] = b"\xff" * 512          # scribble on the first data page
        victim.write_bytes(bytes(data))
        assert script.main(["--source", str(backups), "--dest", str(tmp_path / "offsite")]) == 1
        err = capsys.readouterr().err
        assert "ERROR:" in err and ("integrity_check" in err or "cannot open" in err), err

    def test_an_empty_source_fails_with_the_reason(self, script, tmp_path, capsys):
        backups = tmp_path / "backup"
        backups.mkdir()
        assert script.main(["--source", str(backups), "--dest", str(tmp_path / "o")]) == 1
        assert "has not written a backup yet" in capsys.readouterr().err

    def test_a_missing_source_fails_with_the_reason(self, script, tmp_path, capsys):
        assert script.main(["--source", str(tmp_path / "nope"), "--dest", str(tmp_path / "o")]) == 1
        assert "is config.backup.dir mounted here" in capsys.readouterr().err

    def test_the_source_as_destination_is_refused(self, script, source, tmp_path, capsys):
        backups, _ = source
        assert script.main(["--source", str(backups), "--dest", str(backups)]) == 1
        assert "not off the volume" in capsys.readouterr().err


class TestCheck:
    def test_check_reports_and_compares_the_sidecar(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (copy,) = dest.glob("gsd-*.db")
        assert script.main(["--check", str(copy)]) == 0
        out = capsys.readouterr().out
        assert "integrity_check ok" in out and "sidecar matches" in out and "user_version" in out

    def test_check_fails_on_a_sidecar_mismatch(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (sidecar,) = dest.glob("*.sha256")
        sidecar.write_text("0" * 64 + "  x\n")
        (copy,) = dest.glob("gsd-*.db")
        assert script.main(["--check", str(copy)]) == 1
        assert "does not match sidecar" in capsys.readouterr().err
