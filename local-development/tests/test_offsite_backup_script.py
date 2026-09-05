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


class TestDurability:
    def test_an_empty_sidecar_beside_a_good_copy_means_copy_again_not_a_traceback(self, script, source, tmp_path, capsys):
        """Review of B1 (Cursor): a crash between creating and writing the sidecar leaves a 0-byte
        file; `split()[0]` raised IndexError, and every later Job failed beside a verified copy."""
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (copy,) = dest.glob("gsd-*.db")
        sidecar = dest / (copy.name + ".sha256")
        sidecar.write_text("")
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        digest, name = sidecar.read_text().split()
        assert name == copy.name and digest == _sha(copy)
        assert "copying again" in capsys.readouterr().err

    def test_the_sidecar_is_written_through_a_temporary_name_and_fsynced(self, script, source, tmp_path, monkeypatch):
        """The sidecar gets the same durability as the copy: a temp file, fsync, rename, directory fsync."""
        backups, _ = source
        dest = tmp_path / "offsite"
        synced: list[int] = []
        real_fsync = script.os.fsync
        monkeypatch.setattr(script.os, "fsync", lambda fd: (synced.append(fd), real_fsync(fd)))
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert len(synced) >= 3, "the .part, the sidecar and the directory"
        assert not list(dest.glob("*.sha256.part"))

    def test_the_destination_bytes_are_rehashed_before_publication(self, script, source, tmp_path, monkeypatch, capsys):
        """Review of B1 (Codex): the sidecar recorded the digest of what was READ; a destination that
        altered a same-length value is still a valid database and integrity_check passes it."""
        backups, _ = source
        dest = tmp_path / "offsite"
        real_copy = script.copy_hashed
        def copy_then_alter_the_destination(src, dst):
            out = real_copy(src, dst)
            data = dst.read_bytes(); before, after = b"api.crc.testing", b"api.xrc.testing"
            assert before in data
            dst.write_bytes(data.replace(before, after, 1))
            return out
        monkeypatch.setattr(script, "copy_hashed", copy_then_alter_the_destination)
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 1
        assert "the destination holds sha256" in capsys.readouterr().err
        assert not list(dest.glob("gsd-*")) and not list(dest.glob("*.part"))

    def test_a_sidecar_write_failure_leaves_no_published_copy(self, script, source, tmp_path, monkeypatch):
        """Review of B1 (Codex): publication is ordered so a copy never appears without its sidecar."""
        backups, _ = source
        dest = tmp_path / "offsite"
        real_open = pathlib.Path.open
        def fail_sidecar_open(self, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if "w" in mode and ".sha256" in self.name:
                raise OSError("simulated sidecar write failure")
            return real_open(self, *args, **kwargs)
        monkeypatch.setattr(pathlib.Path, "open", fail_sidecar_open)
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 1
        assert not list(dest.glob("gsd-*"))

    def test_prune_removes_an_old_copy_even_without_a_sidecar(self, script, tmp_path):
        """Review of B1, second pass (Cursor): a copy beyond `keep` goes whether or not it has a sidecar
        — `ship` re-sidecars only the source's newest, so a sidecar-required guard would make old
        sidecar-less copies immortal."""
        dest = tmp_path / "offsite"; dest.mkdir()
        old = dest / "gsd-20200101T000000.000000Z.db"; new = dest / "gsd-20260905T000000.000000Z.db"
        old.write_bytes(b"old"); new.write_bytes(b"new")
        (dest / (new.name + ".sha256")).write_text("0" * 64 + f"  {new.name}\n")
        assert script.prune(dest, keep=1) == 1
        assert not old.exists() and new.exists()

    def test_an_orphan_sidecar_is_pruned_with_the_transients(self, script, source, tmp_path):
        backups, _ = source
        dest = tmp_path / "offsite"; dest.mkdir()
        (dest / "gsd-20200101T000000.000000Z.db.sha256").write_text("0" * 64 + "  gsd-20200101T000000.000000Z.db\n")
        (dest / "gsd-20200101T000000.000000Z.db.sha256.part").write_text("")
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert sorted(p.name for p in dest.iterdir() if "20200101" in p.name) == []

    def test_a_stale_part_from_a_killed_run_is_removed(self, script, source, tmp_path):
        backups, _ = source
        dest = tmp_path / "offsite"; dest.mkdir()
        (dest / "gsd-20200101T000000.000000Z.db.part").write_bytes(b"half")
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert not list(dest.glob("*.part"))

    def test_a_newer_backup_landing_during_the_copy_is_shipped_in_the_same_run(self, script, source, tmp_path, capsys, monkeypatch):
        """Review of B1 (both reviewers): Store.backup runs on its own timer and can rotate the picked
        file away mid-copy (keep=1). The run re-picks, bounded, so the destination ends holding the
        newest; the first copy stays as a verified older one."""
        backups, store = source
        dest = tmp_path / "offsite"
        real_copy = script.copy_hashed
        rotated = {"done": False}
        def copy_then_rotate(src, dst):
            out = real_copy(src, dst)
            if not rotated["done"]:
                rotated["done"] = True
                store.record_sync_event("crc", "corp", "ns", "2026-08-02T12:00:00Z", "2026-08-02T12:00:30Z", "0 * * * *", 99)
                assert store.backup(str(backups), keep=1)
            return out
        monkeypatch.setattr(script, "copy_hashed", copy_then_rotate)
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        out = capsys.readouterr().out
        assert "shipping it too (attempt 2)" in out
        names = sorted(p.name for p in dest.glob("gsd-*.db"))
        assert names[-1] == max(backups.glob("gsd-*.db")).name and len(names) == 2

    def test_a_source_that_keeps_moving_stops_after_a_bounded_number_of_attempts(self, script, source, tmp_path, capsys, monkeypatch):
        backups, store = source
        dest = tmp_path / "offsite"
        real_copy = script.copy_hashed
        def copy_then_always_new(src, dst):
            out = real_copy(src, dst)
            store.record_sync_event("crc", "corp", "ns", f"2026-08-02T13:{len(list(backups.glob('gsd-*.db'))):02d}:00Z", "2026-08-02T13:00:30Z", "0 * * * *", 1)
            store.backup(str(backups), keep=20)
            return out
        monkeypatch.setattr(script, "copy_hashed", copy_then_always_new)
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        out = capsys.readouterr().out
        assert out.count("copied ") == script.REPICK_ATTEMPTS
        assert "it ships on the next run" in out


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
        (copy,) = dest.glob("gsd-*.db")
        sidecar.write_text("0" * 64 + f"  {copy.name}\n")
        assert script.main(["--check", str(copy)]) == 1
        assert "does not match sidecar" in capsys.readouterr().err
        # A sidecar naming another file, or carrying no digest, is malformed rather than a mismatch.
        sidecar.write_text("0" * 64 + "  x\n")
        assert script.main(["--check", str(copy)]) == 1
        assert "empty or malformed" in capsys.readouterr().err
