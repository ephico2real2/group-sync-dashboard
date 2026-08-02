"""SQLite locking and WAL behaviour.

These assert against REAL contention rather than against the PRAGMA values, because reading
back a pragma only proves it was accepted — not that it changes what happens when two
connections actually collide.

The contention that matters here is CROSS-CONNECTION, not cross-thread. Store serialises its
own threads with `self._lock`, so poller threads never race each other on the write lock.
What busy_timeout protects is the case that lock cannot see:

  * the `Recreate` rollover, where the outgoing pod still holds the write lock while the
    incoming one starts and opens its own connection to the same file, and
  * the checkpoint, which contends with the per-thread reader connections.
"""

from __future__ import annotations

import sqlite3
import threading
import time

import pytest

from gsd.store import Store


def _hold_write_lock(db_path: str) -> sqlite3.Connection:
    """An independent connection holding the write lock, as a second pod would."""
    # check_same_thread=False because one test releases the lock from a timer thread.
    other = sqlite3.connect(db_path, check_same_thread=False)
    other.execute("BEGIN IMMEDIATE")
    other.execute(
        "INSERT INTO poll_outcome(cluster_id, observed_at, status, message) "
        "VALUES('other-pod', '2026-01-01T00:00:00Z', 'ok', NULL)"
    )
    return other


class TestBusyTimeout:
    def test_zero_timeout_fails_immediately(self, tmp_path):
        """The control. This is SQLite's DEFAULT, and the bug being fixed."""
        db = str(tmp_path / "gsd.db")
        store = Store(db, busy_timeout_ms=0)
        other = _hold_write_lock(db)
        try:
            started = time.monotonic()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                store.record_poll("mine", "ok", None)
            # Not merely that it failed, but that it did not even try to wait.
            assert time.monotonic() - started < 0.2
        finally:
            other.rollback()
            other.close()
            store.close()

    def test_timeout_waits_for_the_lock_and_then_succeeds(self, tmp_path):
        """The fix: the same collision resolves instead of raising."""
        db = str(tmp_path / "gsd.db")
        store = Store(db, busy_timeout_ms=5000)
        other = _hold_write_lock(db)

        hold_for = 0.5

        def release_later():
            time.sleep(hold_for)
            other.commit()
            other.close()

        releaser = threading.Thread(target=release_later)
        releaser.start()
        try:
            started = time.monotonic()
            store.record_poll("mine", "ok", None)  # must WAIT, not raise
            waited = time.monotonic() - started

            assert waited >= hold_for * 0.8, f"returned in {waited:.2f}s; it did not wait"
            assert waited < 5.0
            rows = store._rows("SELECT cluster_id FROM poll_outcome ORDER BY cluster_id")
            assert [r["cluster_id"] for r in rows] == ["mine", "other-pod"]
        finally:
            releaser.join()
            store.close()

    def test_readers_get_their_own_shorter_timeout(self, tmp_path):
        """Connection state, not database state — the writer's value does not reach readers."""
        db = str(tmp_path / "gsd.db")
        store = Store(db, busy_timeout_ms=5000, reader_busy_timeout_ms=2000)
        try:
            assert store._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            assert store._reader().execute("PRAGMA busy_timeout").fetchone()[0] == 2000
        finally:
            store.close()


class TestWal:
    def test_wal_is_verified_not_assumed(self, tmp_path):
        store = Store(str(tmp_path / "gsd.db"))
        try:
            assert store.journal_mode == "wal"
        finally:
            store.close()

    def test_memory_reports_its_own_mode_without_an_error(self, tmp_path):
        """`:memory:` cannot do WAL and that is not a misconfiguration."""
        store = Store(":memory:")
        try:
            assert store.journal_mode == "memory"
            assert store.wal_bytes() == 0
            assert store.maybe_checkpoint() is None
        finally:
            store.close()

    def test_checkpoint_is_skipped_below_the_threshold(self, tmp_path):
        store = Store(str(tmp_path / "gsd.db"), wal_checkpoint_mb=1024)
        try:
            store.record_poll("c", "ok", None)
            assert store.maybe_checkpoint() is None
        finally:
            store.close()

    def test_checkpoint_truncates_a_grown_wal(self, tmp_path):
        """The reason this exists: without it the WAL grows and the volume fills."""
        db = str(tmp_path / "gsd.db")
        store = Store(db, wal_checkpoint_mb=0.05)  # 50 KiB, reached in a few hundred writes
        try:
            for i in range(400):
                store.record_poll(f"cluster-{i}", "ok", "x" * 200)
            grown = store.wal_bytes()
            assert grown > store.wal_checkpoint_bytes, f"WAL only reached {grown} bytes"

            result = store.maybe_checkpoint()
            assert result is not None
            busy, _frames, _moved = result
            assert busy == 0, "no reader was open, so the checkpoint should not be blocked"
            assert store.wal_bytes() < grown

            # The data survived the truncation — a checkpoint moves pages into the database,
            # it does not discard them.
            rows = store._rows("SELECT COUNT(*) AS n FROM poll_outcome")
            assert rows[0]["n"] == 400
        finally:
            store.close()

    def test_a_blocked_checkpoint_is_counted_not_raised(self, tmp_path):
        """Starvation must be observable, because it has no other symptom until the disk fills."""
        db = str(tmp_path / "gsd.db")
        store = Store(db, wal_checkpoint_mb=0.05)
        try:
            for i in range(400):
                store.record_poll(f"cluster-{i}", "ok", "x" * 200)

            # A reader pinned to an older snapshot is exactly what starves a checkpoint.
            reader = sqlite3.connect(db)
            reader.execute("BEGIN")
            reader.execute("SELECT COUNT(*) FROM poll_outcome").fetchone()
            store.record_poll("after-snapshot", "ok", None)
            try:
                result = store.maybe_checkpoint()
                assert result is not None
                busy, _frames, _moved = result
                assert busy == 1, "the open snapshot should have blocked the truncation"
                assert store.checkpoint_busy_total == 1
            finally:
                reader.rollback()
                reader.close()
        finally:
            store.close()


class TestSynchronous:
    def test_normal_is_the_default(self, tmp_path):
        store = Store(str(tmp_path / "gsd.db"))
        try:
            assert store._conn.execute("PRAGMA synchronous").fetchone()[0] == 1  # NORMAL
        finally:
            store.close()

    def test_full_is_honoured(self, tmp_path):
        store = Store(str(tmp_path / "gsd.db"), synchronous="FULL")
        try:
            assert store._conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        finally:
            store.close()

    def test_an_injection_attempt_falls_back_rather_than_executing(self, tmp_path):
        """PRAGMA takes no bound parameters, so the value is interpolated and must be checked."""
        store = Store(str(tmp_path / "gsd.db"), synchronous="NORMAL; DROP TABLE cluster")
        try:
            assert store._conn.execute("PRAGMA synchronous").fetchone()[0] == 1
            store._rows("SELECT * FROM cluster")  # table still exists
        finally:
            store.close()
