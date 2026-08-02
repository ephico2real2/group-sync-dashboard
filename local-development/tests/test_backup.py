"""Backups of the one thing that cannot be re-fetched.

The accumulated sync and membership history exists only because this process observed it.
Every other table is a cache the next poll rebuilds. Before this, a corrupted or deleted
PVC lost it outright — the single existential risk in the system, and it had no mitigation.
"""

from __future__ import annotations

import pathlib
import sqlite3

import pytest

from gsd.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "gsd.db"))
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_sync_event("crc", "corp", "ns", "2026-08-02T09:00:00Z",
                        "2026-08-02T09:00:30Z", "0 * * * *", 41)
    yield s
    s.close()


class TestBackup:
    def test_the_copy_is_a_real_restorable_database(self, store, tmp_path):
        path = store.backup(str(tmp_path / "b"))
        assert path
        conn = sqlite3.connect(path)
        try:
            rows = conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0]
        finally:
            conn.close()
        assert rows == 1, "the history did not survive into the backup"

    def test_it_is_consistent_while_the_poller_writes(self, store, tmp_path):
        """VACUUM INTO takes a read transaction, so the output is one point in time. A
        plain file copy with a live WAL yields a torn file that opens fine and is missing
        the newest commits — a backup that restores."""
        for i in range(50):
            store.record_sync_event("crc", "corp", "ns", f"2026-08-02T10:{i:02d}:00Z",
                                    "2026-08-02T10:00:30Z", "0 * * * *", i)
        path = store.backup(str(tmp_path / "b"))
        conn = sqlite3.connect(path)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 51
        finally:
            conn.close()

    def test_generations_are_bounded(self, store, tmp_path):
        """Backups live on the PVC they protect; unbounded, they fill it."""
        for _ in range(6):
            store.backup(str(tmp_path / "b"), keep=3)
        assert len(list((tmp_path / "b").glob("gsd-*.db"))) == 3

    def test_two_in_the_same_second_do_not_collide(self, store, tmp_path):
        """VACUUM INTO refuses to overwrite — 'output file already exists' — so a
        second-resolution timestamp made rapid backups fail. Caught by this test first."""
        first = store.backup(str(tmp_path / "b"), keep=10)
        second = store.backup(str(tmp_path / "b"), keep=10)
        assert first and second and first != second

    def test_a_failure_returns_none_rather_than_raising(self, store):
        """A failed backup must never take down the poll thread."""
        assert store.backup("/proc/nonexistent-and-unwritable") is None

    def test_memory_databases_are_skipped(self):
        s = Store(":memory:")
        try:
            assert s.backup("/tmp/whatever") is None
        finally:
            s.close()
