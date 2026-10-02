"""Safety regressions found by Codex's review of SPEC E3 (#302, 2026-10-01): the confirmed plan bound to the bytes,
the snapshot checked before the live set changes, a failed fold that removes nothing, one helper operation at a
time, the whole loss plan, one action per call, and a way back from the kept set. Each failed on the spec's first
blocks (docs/specs/SPEC_E3_restore_db.md §4.2)."""
from __future__ import annotations

import fcntl
import importlib.util
import os
import shlex
import sqlite3
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN
from test_restore_db import STAMPS, Pod, make_db, sha, vacuum_copy
from test_restore_db_wrapper import RECOVERY, lab, pods  # noqa: F401 (lab is a fixture)

LOCAL_DEV = Path(__file__).resolve().parents[1]
HELPER = LOCAL_DEV / "restore-db.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("review_restore_db", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_that_moves_after_check(lab, source: Path, target: Path) -> None:
    """`oc` as the wrapper tests stub it, which also replaces `target` with `source` once `check` has returned."""
    stub = lab.log.parent / "bin" / "oc"
    stub.write_text(f'''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_LOG"
case "$1" in
  get) cat "$STUB_PODS" ;;
  exec)
    while [ "$#" -gt 0 ] && [ "$1" != /dev/stdin ]; do shift; done
    shift
    "$STUB_PYTHON" /dev/stdin "$@" --offsite "$STUB_OFFSITE" --proc "$STUB_PROC" --group "$STUB_GROUP"
    rc=$?
    if [ "${{1:-}}" = check ]; then mv {shlex.quote(str(source))} {shlex.quote(str(target))}; fi
    exit "$rc" ;;
esac
''')
    stub.chmod(0o755)


def test_confirmed_candidate_bytes_are_bound_to_the_restore(lab, tmp_path: Path) -> None:
    """Replace the copy under the same ID after the wrapper's check returns and before its restore."""
    candidate = lab.pod.backup / f"gsd-{STAMPS[0]}.db"
    replacement = tmp_path / "replacement.db"
    make_db(replacement, 1, KNOWN)
    stub_that_moves_after_check(lab, replacement, candidate)
    before = sha(lab.pod.db)
    restored = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert restored.returncode == 3, "same ID but unconfirmed bytes were restored"
    assert "changed after the check you answered" in restored.stderr
    assert sha(lab.pod.db) == before and not lab.pod.pre_restore.exists()


def test_confirmed_live_set_is_bound_to_the_loss_plan(lab, tmp_path: Path) -> None:
    """A second restore or a hand change between the question and the restore makes the plan shown wrong."""
    changed_live = tmp_path / "changed-live.db"
    make_db(changed_live, 99, KNOWN)
    stub_that_moves_after_check(lab, changed_live, lab.pod.db)
    changed_sha = sha(changed_live)
    restored = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert restored.returncode == 3
    assert "live database set changed after the check you answered" in restored.stderr
    assert sha(lab.pod.db) == changed_sha and not lab.pod.pre_restore.exists()


def test_written_snapshot_schema_is_checked_before_the_live_set_changes(tmp_path: Path, monkeypatch) -> None:
    """Replace the copy after its header was read but before it is hashed: the snapshot's own schema refuses."""
    helper = load_helper()
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 20, KNOWN)
    candidate = pod.backup / f"gsd-{STAMPS[0]}.db"
    vacuum_copy(pod.db, candidate)
    newer = tmp_path / "newer.db"
    make_db(newer, 1, KNOWN + 1)
    before = sha(pod.db)
    real_schema = helper.schema_of
    replaced = False

    def replace_after_header(path: Path):
        nonlocal replaced
        result = real_schema(path)
        if Path(path) == candidate and not replaced:
            replaced = True
            os.replace(newer, candidate)
        return result

    monkeypatch.setattr(helper, "schema_of", replace_after_header)
    monkeypatch.setenv("GSD_RECOVERY_MODE", "true")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    monkeypatch.setenv("TMPDIR", str(pod.tmp))
    rc = helper.main(["restore", f"{KNOWN}-{STAMPS[0]}", "--offsite", str(pod.offsite),
                      "--proc", str(pod.proc), "--group", str(os.getgid())])
    assert rc == 3
    assert sha(pod.db) == before and not pod.pre_restore.exists()
    assert not (pod.data / "gsd.db.restore.tmp").exists()


def test_fold_failure_preserves_the_live_journal(tmp_path: Path, monkeypatch) -> None:
    """SQLite cannot open the old file at all (OperationalError) and a -wal with bytes is beside it: nothing goes."""
    helper = load_helper()
    pod = Pod(tmp_path / "pod")
    pod.db.write_bytes(b"not a sqlite database")
    wal = Path(f"{pod.db}-wal")
    wal.write_bytes(b"committed bytes that must not be unlinked")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    monkeypatch.setattr(helper.sqlite3, "connect",
                        lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("cannot open")))
    with pytest.raises(sqlite3.Error):
        helper.fold(helper.Layout(pod.offsite))
    assert wal.read_bytes() == b"committed bytes that must not be unlinked"


def test_loss_plan_names_all_append_only_history_and_other_rolled_back_state(tmp_path: Path) -> None:
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 2, KNOWN)
    conn = sqlite3.connect(pod.db)
    for table in ("login_event", "kyverno_result_event"):
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)")
        conn.executemany(f"INSERT INTO {table}(v) VALUES (?)", [("copy",), ("copy",)])
    conn.execute("CREATE TABLE kpi_daily(day TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO kpi_daily VALUES ('2026-10-01', 'copy')")
    conn.commit()
    conn.close()
    vacuum_copy(pod.db, pod.backup / f"gsd-{STAMPS[0]}.db")
    conn = sqlite3.connect(pod.db)
    for table in ("login_event", "kyverno_result_event"):
        conn.execute(f"INSERT INTO {table}(v) VALUES ('live')")
    conn.execute("UPDATE kpi_daily SET v='live'")
    conn.commit()
    conn.close()
    result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert "login_event" in result.stdout and "kyverno_result_event" in result.stdout
    assert "kpi_daily" in result.stdout and "report_run" in result.stdout
    assert "estimate" in result.stdout.lower()


@pytest.mark.parametrize("order", ["list-first", "restore-first"])
def test_wrapper_rejects_two_actions(lab, order: str) -> None:
    actions = [["--list"], ["--from-version", f"{KNOWN}-{STAMPS[0]}"]]
    args = actions[0] + actions[1] if order == "list-first" else actions[1] + actions[0]
    result = lab(*args, "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 64
    assert not lab.pod.pre_restore.exists() and not lab.log.exists()


def test_check_cannot_open_the_live_database_during_a_restore(tmp_path: Path) -> None:
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 2, KNOWN)
    vacuum_copy(pod.db, pod.backup / f"gsd-{STAMPS[0]}.db")
    with (pod.tmp / "gsd-restore.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "another restore or database inspection" in result.stderr


def test_runbook_explains_how_to_recover_a_kept_live_set() -> None:
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("**Undo a restore.**", 1)[1].split("\n\n", 1)[0]
    assert all(word in section for word in ("gsd.db", "-wal", "-shm", "-journal", "integrity_check", ".tmp"))
    assert runbook.count("rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal") >= 2
