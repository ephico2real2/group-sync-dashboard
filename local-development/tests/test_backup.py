"""Backups of the one thing that cannot be re-fetched.

The accumulated sync and membership history exists only because this process observed it.
Every other table is a cache the next poll rebuilds. Before this, a corrupted or deleted
PVC lost it outright — the single existential risk in the system, and it had no mitigation.
"""

from __future__ import annotations

import pathlib
import re
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


def test_a_snapshot_is_never_visible_under_its_final_name_before_it_is_complete(tmp_path):
    """C3: the report pod lists gsd-*.db and opens the newest; a half-written file must not match.
    VACUUM INTO writes to a .tmp name and os.replace renames it — asserted by recording what the
    directory held at the instant of the rename."""
    import os as _os
    from gsd.store import Store as _Store
    store = _Store(str(tmp_path / "gsd.db"))
    store.upsert_cluster("c", "https://x", True)
    seen = {}
    real_replace = _os.replace
    def recording_replace(src, dst):
        seen["src"] = str(src); seen["dst"] = str(dst)
        seen["visible_before"] = sorted(p.name for p in (tmp_path / "report").glob("gsd-*.db"))
        return real_replace(src, dst)
    import gsd.store as store_module
    store_module.os.replace = recording_replace
    try:
        path = store.snapshot(str(tmp_path / "report"), keep=2)
    finally:
        store_module.os.replace = real_replace
        store.close()
    assert path and seen["src"].endswith(".db.tmp") and seen["dst"] == path
    assert seen["visible_before"] == [], "nothing matched gsd-*.db until the rename"
    assert not list((tmp_path / "report").glob("*.tmp"))


# -- #391: above one replica, every pod writes into one config.backup.dir -----------------------------------
#
# Each replica has its own database (/data/$POD_NAME/gsd.db) and the chart gives every pod the same backupDir.
# These drive the poller, which is where the pod's identity (POD_NAME, Settings.replica_count) meets
# Store.backup, and they read a copy's owner from its CONTENTS, never from the file name under test.
# test_history_retention.py and test_offsite_backup_script.py import the three helpers.

REPO = pathlib.Path(__file__).resolve().parents[2]


class _Replica(Store):
    """One replica's database, marked with its pod, recording every path backup() returned."""

    def __init__(self, root: pathlib.Path, pod: str) -> None:
        super().__init__(str(root / pod / "gsd.db"))
        self.pod = pod
        self.returned: list[str | None] = []
        with self._write() as conn:
            conn.execute("CREATE TABLE replica_marker(pod TEXT)")
            conn.execute("INSERT INTO replica_marker VALUES(?)", (pod,))

    def backup(self, *args, **kwargs):
        path = super().backup(*args, **kwargs)
        self.returned.append(path)
        return path


def replicas_sharing_one_directory(root: pathlib.Path, pods: tuple[str, ...], keep: int):
    """(the shared backup directory, [(pod, its store, its poller)]), as the chart runs len(pods) replicas."""
    from gsd.config import Settings
    from gsd.poller import Poller

    shared = root / "backup"
    replicas = []
    for pod in pods:
        store = _Replica(root, pod)
        settings = Settings(clusters=[], db_path=store.path, backup_dir=str(shared), backup_keep=keep,
                            replica_count=len(pods))
        replicas.append((pod, store, Poller(store, settings, None)))
    return shared, replicas


def backup_cycle(replicas, monkeypatch) -> None:
    """One scheduled backup per replica, in order, each run as its own pod (POD_NAME, as the chart sets it)."""
    for pod, _store, poller in replicas:
        monkeypatch.setenv("POD_NAME", pod)
        poller._next_backup = 0.0
        poller._maybe_backup()


def copy_owners(directory: pathlib.Path) -> list[str]:
    """The pod each gsd-*.db in `directory` is a copy of, read from inside the copy."""
    owners = []
    for path in sorted(directory.glob("gsd-*.db")):
        conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
        try:
            owners.append(conn.execute("SELECT pod FROM replica_marker").fetchone()[0])
        finally:
            conn.close()
    return owners


def _close(replicas) -> None:
    for _pod, store, _poller in replicas:
        store.close()


def test_two_replicas_sharing_one_directory_each_keep_their_own_keep(tmp_path, monkeypatch):
    """T391-1. Measured on main dd51b91f: with keep 4 each replica kept 2 of its own, because every rotation
    deleted by the bare gsd-*.db pattern across the shared directory. Six cycles, so each pod's own rotation
    runs too."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a", "pod-b"), keep=4)
    try:
        for _ in range(6):
            backup_cycle(replicas, monkeypatch)
        owners = copy_owners(shared)
        assert {pod: owners.count(pod) for pod, _, _ in replicas} == {"pod-a": 4, "pod-b": 4}
        assert all(pathlib.Path(store.returned[-1]).exists() for _, store, _ in replicas)
    finally:
        _close(replicas)


def test_no_replica_deletes_a_copy_it_did_not_write(tmp_path, monkeypatch):
    """T391-2. Three replicas, keep 2, one cycle: A, then B, then C. On main C's rotation deleted A's only copy
    after backup() had returned it: {'pod-a': False, 'pod-b': True, 'pod-c': True}."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a", "pod-b", "pod-c"), keep=2)
    try:
        backup_cycle(replicas, monkeypatch)
        assert {pod: pathlib.Path(store.returned[-1]).exists() for pod, store, _ in replicas} == {
            "pod-a": True, "pod-b": True, "pod-c": True}
        assert sorted(copy_owners(shared)) == ["pod-a", "pod-b", "pod-c"]
    finally:
        _close(replicas)


def test_one_replica_keeps_the_name_and_the_rotation(tmp_path, monkeypatch):
    """T391-4, a regression guard: at one replica the name carries no pod even with POD_NAME set, and keep
    bounds the directory (test_generations_are_bounded, store.py's gsd-<stamp>.db)."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a",), keep=3)
    try:
        for _ in range(6):
            backup_cycle(replicas, monkeypatch)
        names = sorted(p.name for p in shared.glob("gsd-*.db"))
        assert len(names) == 3
        assert all(re.fullmatch(r"gsd-\d{8}T\d{6}\.\d{6}Z\.db", name) for name in names), names
    finally:
        _close(replicas)


def test_report_snapshots_keep_their_name_with_a_pod_set(tmp_path, monkeypatch):
    """T391-5, a regression guard: Store.snapshot shares _vacuum_into, and the report service reads its files
    by _STAMP. The pod in the name is backup()'s alone."""
    from gsd.reporting.snapshot import _STAMP

    monkeypatch.setenv("POD_NAME", "pod-a")
    store = Store(str(tmp_path / "gsd.db"))
    try:
        written = [store.snapshot(str(tmp_path / "report"), keep=2) for _ in range(2)]
    finally:
        store.close()
    assert all(written)
    assert all(_STAMP.match(pathlib.Path(path).name) for path in written), written


def test_a_pod_is_its_whole_name_not_a_suffix_of_another(tmp_path):
    """#391, from the research (borg prune: a pattern "foo*" also matches "foobar"): the owner is the whole
    field after the stamp, so pod-b neither counts nor rotates x-pod-b's copies or a one-replica copy."""
    from gsd.storage import backup_copies

    shared = tmp_path / "backup"
    shared.mkdir()
    names = ("gsd-20261001T000000.000000Z.db", "gsd-20261001T010000.000000Z-x-pod-b.db",
             "gsd-20261001T020000.000000Z-pod-b.db")
    for name in names:
        (shared / name).write_bytes(b"not a database")
    assert [p.name for p in backup_copies(shared, "pod-b")] == ["gsd-20261001T020000.000000Z-pod-b.db"]
    assert [p.name for p in backup_copies(shared, None)] == list(names)
    store = Store(str(tmp_path / "gsd.db"))
    try:
        mine = store.backup(str(shared), keep=1, owner="pod-b")
    finally:
        store.close()
    assert sorted(p.name for p in shared.glob("gsd-*.db")) == sorted([*names[:2], pathlib.Path(mine).name])


def test_the_docs_say_where_each_replicas_copies_are(tmp_path):
    """T391-9: the runbook, the chart README's Scaling section and the values comment on config.backup each
    say where a replica's copies are and that keep applies per replica. On main the runbook names one
    directory and one keep, and Scaling says nothing about backups."""
    def words(text: str) -> str:
        return " ".join(text.replace("#", " ").split())

    runbook = words((REPO / "docs" / "RUNBOOK_backup_restore.md").read_text())
    readme = (REPO / "charts" / "group-sync-dashboard" / "README.md").read_text()
    scaling = words(readme[readme.index("\n## Scaling\n"):readme.index("\n## Storage\n")])
    values = (REPO / "charts" / "group-sync-dashboard" / "values.yaml").read_text()
    comment = words(values[:values.index("\n  backup:\n    enabled: true")].rsplit("\n\n", 1)[-1])
    for name, text in (("runbook", runbook), ("Scaling", scaling)):
        assert "gsd-<UTC stamp>Z-<pod name>.db" in text, name
        assert "`keep` applies per replica" in text, name
    assert "gsd-<stamp>-<pod>.db" in comment and "keep applies per replica" in comment
