"""The copy of the database taken before a migration (#301, docs/specs/SPEC_M1_pre_upgrade_copy.md).

The migration is one-way, so the database as it was before it is the only way back to the build that wrote
it. These tests hold four promises: the copy is taken before SCHEMA or any migration writes, it verifies, a
start that cannot take it does not migrate, and nothing that manages the six-hourly backups can reach it.
"""

from __future__ import annotations

import gc
import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import timedelta

import pytest

import gsd.store as store_module
from gsd.store import (KNOWN_SCHEMA_VERSION, PRE_UPGRADE_DIR, PRE_UPGRADE_KEEP, Store,
                       StorePreUpgradeCopyFailed)

OFFSITE = (pathlib.Path(__file__).resolve().parents[2]
           / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py")
COPY_NAME = re.compile(rf"^pre-upgrade-\d{{8}}T\d{{6}}\.\d{{6}}Z-schema-(\d+)-to-{KNOWN_SCHEMA_VERSION}-(.+)\.db$")


def _older_database(path: pathlib.Path, version: int = KNOWN_SCHEMA_VERSION - 1) -> None:
    """A database this build must migrate: written by the real Store, rewound to `version`, holding one sync
    event, and missing one table SCHEMA creates — so a copy taken after SCHEMA ran would show it."""
    store = Store(str(path))
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    store.record_sync_event("crc", "corp", "ns", "2026-09-26T10:00:00Z", "2026-09-26T10:00:30Z", "0 * * * *", 3)
    store.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE kyverno_result_event")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def _facts(path: pathlib.Path) -> dict:
    """Read-only, and not `immutable=1`: the live file's newest commits may still be in its -wal."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {"user_version": conn.execute("PRAGMA user_version").fetchone()[0],
                "tables": {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                "sync_events": conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0]}
    finally:
        conn.close()


def _copies(data: pathlib.Path) -> list[pathlib.Path]:
    """Every database file in the copy directory, whatever its name: the name is asserted, not assumed."""
    return sorted((data / PRE_UPGRADE_DIR).glob("*.db"))


def _fail_the_last_migration(monkeypatch) -> None:
    """This build's last migration fails after SCHEMA has run, as a broken upgrade would."""
    failing = [m for m in store_module._MIGRATIONS if m[0] != KNOWN_SCHEMA_VERSION]
    failing.append((KNOWN_SCHEMA_VERSION, "fails on purpose", ["INSERT INTO no_such_table VALUES (1)"]))
    monkeypatch.setattr(store_module, "_MIGRATIONS", failing)


def _grow_the_wal(db: pathlib.Path) -> None:
    """Commit rows to the -wal and die before any checkpoint, as a pod killed mid-run leaves its database: the
    main file is then far smaller than the database SQLite reads (SPEC_M1 §2.2)."""
    writer = subprocess.Popen([sys.executable, "-c", (
        "import sqlite3, sys, time\n"
        "c = sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_autocheckpoint=0')\n"
        "c.executemany(\"INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at)"
        " VALUES ('crc', 'g', ?, 'added', '2026-09-26T00:00:00Z')\", [(f'u{i}',) for i in range(20000)])\n"
        "c.commit(); print('ready', flush=True); time.sleep(30)\n"), str(db)], stdout=subprocess.PIPE, text=True)
    try:
        assert writer.stdout.readline().strip() == "ready"
    finally:
        writer.kill()
        writer.wait()
        writer.stdout.close()


def test_an_older_database_is_copied_before_schema_and_migrations_touch_it(tmp_path, caplog):
    db = tmp_path / "gsd.db"
    _older_database(db)
    with caplog.at_level("INFO", logger="gsd.store"):
        Store(str(db)).close()
    (copy,) = _copies(tmp_path)
    assert COPY_NAME.match(copy.name).group(1) == str(KNOWN_SCHEMA_VERSION - 1)
    facts = _facts(copy)
    assert facts["user_version"] == KNOWN_SCHEMA_VERSION - 1
    assert "kyverno_result_event" not in facts["tables"], "the copy was taken after SCHEMA ran"
    assert facts["sync_events"] == 1
    assert (copy.parent / (copy.name + ".sha256")).read_text() == (
        f"{hashlib.sha256(copy.read_bytes()).hexdigest()}  {copy.name}\n")
    assert not list(copy.parent.glob("*.tmp"))
    lines = caplog.text.splitlines()
    written = next(i for i, line in enumerate(lines) if "pre-upgrade copy written before migrating" in line)
    migrated = next(i for i, line in enumerate(lines) if f"schema migration {KNOWN_SCHEMA_VERSION} applied" in line)
    assert written < migrated
    assert f"schema {KNOWN_SCHEMA_VERSION - 1} -> {KNOWN_SCHEMA_VERSION}: {copy}" in lines[written]
    live = _facts(db)
    assert live["user_version"] == KNOWN_SCHEMA_VERSION and "kyverno_result_event" in live["tables"]


@pytest.mark.parametrize("cause", ["unwritable directory", "free space below the database",
                                   "free space for the file but not its WAL", "the rename fails"])
def test_a_copy_that_cannot_be_written_refuses_the_start(tmp_path, monkeypatch, caplog, cause):
    db = tmp_path / "gsd.db"
    _older_database(db)
    directory = tmp_path / PRE_UPGRADE_DIR
    real = shutil.disk_usage
    if cause == "unwritable directory":
        if os.geteuid() == 0:
            pytest.skip("root writes into a 0555 directory")
        directory.mkdir(mode=0o555)
    elif cause == "free space below the database":
        conn = sqlite3.connect(db)
        need = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
        conn.close()
        monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=need - 1))
    elif cause == "free space for the file but not its WAL":
        _grow_the_wal(db)
        size = db.stat().st_size
        assert (tmp_path / "gsd.db-wal").stat().st_size > size
        monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=size))
    else:
        # The last step: the copy and its sidecar are on disk, so this is the most a failure can leave behind.
        def rename_fails(src, dst):
            raise OSError("rename refused by the test")
        monkeypatch.setattr(store_module.os, "replace", rename_fails)
    try:
        with caplog.at_level("INFO", logger="gsd.store"), pytest.raises(StorePreUpgradeCopyFailed) as refused:
            Store(str(db))
        message = str(refused.value)
        assert message.startswith(
            f"schema {KNOWN_SCHEMA_VERSION - 1} -> {KNOWN_SCHEMA_VERSION}: the pre-upgrade copy of {db} could not "
            f"be written to {directory}, so the database was not migrated: ")
        if cause.startswith("free space"):
            assert re.search(r"free space [\d.]+ MiB, database [\d.]+ MiB", message)
        facts = _facts(db)
        assert facts["user_version"] == KNOWN_SCHEMA_VERSION - 1
        assert "kyverno_result_event" not in facts["tables"], "SCHEMA ran although the copy was refused"
        assert "schema migration" not in caplog.text
        assert not [p for p in directory.iterdir()], "a refused attempt left a file"
    finally:
        directory.chmod(0o755)


def test_a_database_at_the_build_version_writes_nothing(tmp_path):
    db = tmp_path / "gsd.db"
    Store(str(db)).close()
    Store(str(db)).close()
    assert not (tmp_path / PRE_UPGRADE_DIR).exists()


def test_a_fresh_file_writes_nothing(tmp_path):
    Store(str(tmp_path / "gsd.db")).close()
    assert not (tmp_path / PRE_UPGRADE_DIR).exists()


@pytest.fixture(scope="module")
def offsite():
    spec = importlib.util.spec_from_file_location("offsite_backup", OFFSITE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backup_dir", ["backup", PRE_UPGRADE_DIR],
                         ids=["chart layout", "backup.dir set to the copies"])
def test_the_six_hourly_backups_do_not_see_the_copy(tmp_path, offsite, backup_dir):
    """The regression measured on #301: a `gsd-preupgrade-*` name in the backup directory sorts after every
    `gsd-2026…` backup, and `backup(keep=2)` deleted the backup it had just written. The copy's directory keeps
    it away from every reader of config.backup.dir, and its name keeps it out of their pattern even if
    config.backup.dir pointed at that directory."""
    from types import SimpleNamespace

    from prometheus_client import generate_latest

    from gsd.kpi.system import dashboard_data_bytes
    from gsd.metrics import build_registry
    from gsd.reporting.snapshot import _STAMP

    db = tmp_path / "gsd.db"
    _older_database(db)
    store = Store(str(db))
    try:
        (copy,) = _copies(tmp_path)
        assert not _STAMP.match(copy.name), "the report service would read the copy as a snapshot"
        backups = tmp_path / backup_dir
        settings = SimpleNamespace(backup_dir=str(backups), login_capture_enabled=False)
        metric = "gsd_backup_last_success_timestamp_seconds"

        def samples() -> list[str]:
            text = generate_latest(build_registry(store, timedelta(seconds=120), settings=settings)).decode()
            return [line for line in text.splitlines() if line.startswith(metric)]

        assert samples() == [], "the backup metric counts the pre-upgrade copy"
        assert dashboard_data_bytes(str(db), str(backups))()["backups"]["count"] == 0
        written = [store.backup(str(backups), keep=2) for _ in range(3)]
        assert all(written) and pathlib.Path(written[-1]).exists()
        assert sorted(p.name for p in backups.glob("gsd-*.db")) == sorted(pathlib.Path(w).name for w in written[1:])
        assert offsite.newest_backup(backups) == pathlib.Path(written[-1])
        assert len(samples()) == 1
        assert dashboard_data_bytes(str(db), str(backups))()["backups"]["count"] == 2
        assert copy.exists() and (copy.parent / (copy.name + ".sha256")).exists()
    finally:
        store.close()


def test_a_restarted_container_does_not_copy_again(tmp_path, monkeypatch, caplog):
    """A failed attempt commits what ran before the failure: here SCHEMA's table, and on main `cbbc65a` an 18 -> 20
    upgrade whose migration 20 failed also left user_version 19 (SPEC_M1 §2.6). A second copy would be of that,
    and PRE_UPGRADE_KEEP of them would prune the clean one. Any later start of this image, a new pod included,
    does not copy again."""
    db = tmp_path / "gsd.db"
    _older_database(db)
    monkeypatch.setenv("POD_NAME", "crashing-pod")
    _fail_the_last_migration(monkeypatch)
    for _ in range(2):
        with caplog.at_level("INFO", logger="gsd.store"), \
                pytest.raises(sqlite3.OperationalError, match="no_such_table"):
            Store(str(db))
    (copy,) = _copies(tmp_path)
    assert "kyverno_result_event" not in _facts(copy)["tables"]
    assert "kyverno_result_event" in _facts(db)["tables"], "the failed attempt committed nothing to copy"
    assert f"not taken again: {copy} already exists from an earlier attempt" in caplog.text
    monkeypatch.setenv("POD_NAME", "replacement-pod")
    with pytest.raises(sqlite3.OperationalError):
        Store(str(db))
    assert [COPY_NAME.match(p.name).group(2) for p in _copies(tmp_path)] == ["crashing-pod"]


@pytest.mark.parametrize("version", [KNOWN_SCHEMA_VERSION - 1, KNOWN_SCHEMA_VERSION - 2])
def test_new_pods_in_a_crash_loop_do_not_prune_the_clean_copy(tmp_path, monkeypatch, version):
    """Review of SPEC_M1 (C3, Grok and Codex): with the copy taken once per pod, three replacement pods each copied
    the half-migrated database and PRE_UPGRADE_KEEP pruned the clean one. From N-2 the failed attempt may also
    commit migration N-1 first (SPEC_M1 §2.6), so a later start meets another version and still takes no copy."""
    db = tmp_path / "gsd.db"
    _older_database(db, version)
    _fail_the_last_migration(monkeypatch)
    for pod in ("pod-a", "pod-b", "pod-c", "pod-d"):
        monkeypatch.setenv("POD_NAME", pod)
        with pytest.raises(sqlite3.OperationalError, match="no_such_table"):
            Store(str(db))
    (kept,) = _copies(tmp_path)
    assert COPY_NAME.match(kept.name).group(2) == "pod-a"
    facts = _facts(kept)
    assert facts["user_version"] == version and "kyverno_result_event" not in facts["tables"], (
        f"keep={PRE_UPGRADE_KEEP} pruned the clean copy")


def test_the_clean_copy_restored_under_the_same_image_is_not_copied_again(tmp_path, monkeypatch, caplog):
    """After a failed upgrade the operator restores the clean copy (runbook §4a, with the dashboard scaled to zero)
    and starts the same image again, fixed, in a new pod: the copy already there is the database restored, so none
    is taken."""
    db = tmp_path / "gsd.db"
    _older_database(db)
    monkeypatch.setenv("POD_NAME", "failed-pod")
    with monkeypatch.context() as failing:
        _fail_the_last_migration(failing)
        with pytest.raises(sqlite3.OperationalError, match="no_such_table"):
            Store(str(db))
    (copy,) = _copies(tmp_path)
    gc.collect()                        # the failed attempt's connection, held by its traceback, closes here
    for leftover in ("gsd.db-wal", "gsd.db-shm"):
        (tmp_path / leftover).unlink(missing_ok=True)
    shutil.copyfile(copy, db)
    monkeypatch.setenv("POD_NAME", "restored-pod")
    with caplog.at_level("INFO", logger="gsd.store"):
        Store(str(db)).close()
    assert _copies(tmp_path) == [copy]
    assert f"not taken again: {copy} already exists from an earlier attempt" in caplog.text
    assert _facts(db)["user_version"] == KNOWN_SCHEMA_VERSION


def test_logging_stat_failure_is_named_and_cleans_up(tmp_path, monkeypatch):
    """Review of SPEC_M1 (C4, Codex F2): the success line read the copy's size outside the handler, so a failing
    stat raised a bare OSError and left the copy and its sidecar behind."""
    db = tmp_path / "gsd.db"
    _older_database(db)
    real_stat = pathlib.Path.stat

    def stat_fails(path, *args, **kwargs):
        if path.name.startswith("pre-upgrade-") and path.suffix == ".db":
            raise OSError("injected final stat I/O failure")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "stat", stat_fails)
    with pytest.raises(StorePreUpgradeCopyFailed, match="injected final stat I/O failure") as refused:
        Store(str(db))
    monkeypatch.undo()
    directory = tmp_path / PRE_UPGRADE_DIR
    assert str(refused.value).startswith(
        f"schema {KNOWN_SCHEMA_VERSION - 1} -> {KNOWN_SCHEMA_VERSION}: the pre-upgrade copy of {db} could not "
        f"be written to {directory}, so the database was not migrated: ")
    assert _facts(db)["user_version"] == KNOWN_SCHEMA_VERSION - 1
    assert not list(directory.iterdir())


def test_the_newest_copies_are_kept_and_a_killed_attempt_leaves_nothing(tmp_path):
    directory = tmp_path / PRE_UPGRADE_DIR
    directory.mkdir()
    seeds = [directory / f"pre-upgrade-2000090{i}T000000.000000Z-schema-{KNOWN_SCHEMA_VERSION - 2}-to-"
                         f"{KNOWN_SCHEMA_VERSION - 1}-pod-{i}.db" for i in range(1, 5)]
    for seed in seeds:
        seed.write_bytes(b"copy")
        (directory / (seed.name + ".sha256")).write_text("sidecar")
    stale = directory / "pre-upgrade-20000905T000000.000000Z-schema-1-to-2-killed.db.tmp"
    orphan = directory / "pre-upgrade-20000906T000000.000000Z-schema-1-to-2-killed.db.sha256"
    foreign = directory / "notes.txt"
    for path in (stale, orphan, foreign):
        path.write_text("x")
    db = tmp_path / "gsd.db"
    _older_database(db)
    Store(str(db)).close()
    kept = _copies(tmp_path)
    assert len(kept) == PRE_UPGRADE_KEEP == 3
    assert kept[:2] == seeds[2:] and COPY_NAME.match(kept[2].name)
    assert sorted(p.name for p in directory.iterdir()) == sorted(
        [p.name for p in kept] + [p.name + ".sha256" for p in kept] + [foreign.name])


def test_the_app_copies_with_backups_off_and_does_not_start_without_the_copy(tmp_path, monkeypatch):
    """The level it surfaces at: build_app is what `uvicorn gsd.api:create_app --factory` calls, and an exception
    there stops the container before it binds the port. With config.backup off the copy is still taken: its
    directory is the database's, not config.backup.dir."""
    from gsd.api import build_app
    from gsd.config import Settings

    db = tmp_path / "gsd.db"
    _older_database(db)
    real = shutil.disk_usage
    monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=0))
    with pytest.raises(StorePreUpgradeCopyFailed, match=r"free space 0\.0 MiB"):
        build_app(Settings(db_path=str(db), clusters=[], backup_dir=""), run_poller=False)
    monkeypatch.undo()
    app = build_app(Settings(db_path=str(db), clusters=[], backup_dir=""), run_poller=False)
    app.state.store.close()
    (copy,) = _copies(tmp_path)
    assert _facts(copy)["user_version"] == KNOWN_SCHEMA_VERSION - 1
