"""restore-db.py (#302), driven as the recovery pod runs it: `python /dev/stdin <command>` with the helper on stdin,
against a temporary /data, /offsite and /proc. docs/specs/SPEC_E3_restore_db.md §4 maps each test to its case."""
from __future__ import annotations

import ast
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN

LOCAL_DEV = Path(__file__).resolve().parents[1]
HELPER = LOCAL_DEV / "restore-db.py"
OFFSITE_SCRIPT = LOCAL_DEV.parent / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py"
RECOVERY_SCRIPT = LOCAL_DEV.parent / "charts" / "group-sync-dashboard" / "scripts" / "recovery_mode.py"
TABLES = ("membership_event", "sync_event", "binding_event")
STAMPS = ("20261001T051103.798578Z", "20261001T111104.000930Z", "20260925T064601.385120Z", "20260930T180002.104233Z")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_db(path: Path, rows: int, version: int) -> None:
    """A database with the three history tables (ids AUTOINCREMENT, as in gsd/store.py's SCHEMA)."""
    conn = sqlite3.connect(path)
    for table in TABLES:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)")
        conn.executemany(f"INSERT INTO {table}(v) VALUES (?)", [(str(i),) for i in range(rows)])
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def vacuum_copy(source: Path, target: Path) -> None:
    """A copy the way Store._vacuum_into and _pre_upgrade_copy take one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(source)
    conn.execute(f"VACUUM INTO '{target}'")
    conn.close()


def sidecar(path: Path, digest: str | None = None) -> None:
    path.with_name(path.name + ".sha256").write_text(f"{digest or sha(path)}  {path.name}\n")


def kill_writer_after(db: Path, rows: int) -> None:
    """Commit `rows` sync_event rows into the -wal and die before any checkpoint, as a killed pod does."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0')\n"
            "c.execute('BEGIN')\n"
            f"[c.execute('INSERT INTO sync_event(v) VALUES (?)', ('wal',)) for _ in range({rows})]\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(db)], check=False)


def count(db: Path, table: str = "sync_event") -> int:
    """Rows as SQLite reads the file with whatever sits beside it, from a scratch copy so nothing here folds it."""
    scratch = Path(tempfile.mkdtemp())
    for side in ("", "-wal", "-shm", "-journal"):
        if Path(f"{db}{side}").exists():
            shutil.copy2(f"{db}{side}", scratch / f"gsd.db{side}")
    conn = sqlite3.connect(scratch / "gsd.db")
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()
        shutil.rmtree(scratch)


class Pod:
    """A temporary recovery pod: /data, /offsite, /proc and $TMPDIR, and the helper run as `oc exec` runs it."""

    def __init__(self, root: Path, uvicorn: bool = False) -> None:
        self.root = root
        self.data, self.offsite, self.proc, self.tmp = (root / n for n in ("data", "offsite", "proc", "tmp"))
        self.backup, self.pre_upgrade, self.pre_restore = (self.data / n for n in ("backup", "pre-upgrade", "pre-restore"))
        for d in (self.backup, self.pre_upgrade, self.offsite, self.proc / "1", self.tmp):
            d.mkdir(parents=True)
        argv = (["/usr/bin/qemu-x86_64-static", "/usr/sbin/python3.14", "-m", "uvicorn", "gsd.api:create_app"] if uvicorn
                else ["python3.14", "/scripts/recovery_mode.py", "--release", "group-sync-dashboard"])
        (self.proc / "1" / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        self.db = self.data / "gsd.db"
        self.ttl_left(7200.0)

    def ttl_left(self, seconds: float, boot: str | None = None) -> None:
        """SPEC_E2's record of the TTL in the pod's /tmp, `seconds` from now on the node's monotonic clock."""
        if boot is None:
            boot_file = Path("/proc/sys/kernel/random/boot_id")
            boot = boot_file.read_text().strip() if boot_file.exists() else ""
        now, mono = time.time(), time.monotonic()
        record = {"ttl": "2h", "started": "", "started_epoch": now, "deadline": "", "deadline_epoch": now + seconds,
                  "deadline_monotonic": mono + seconds, "boot_id": boot}
        (self.tmp / "gsd-recovery.json").write_text(json.dumps(record))

    def run(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PYTHONPATH": str(LOCAL_DEV), "GSD_RECOVERY_MODE": "true",
                       "GSD_DB_PATH": str(self.db), "GSD_BACKUP_DIR": str(self.backup), "TMPDIR": str(self.tmp),
                       **(env or {})}
        # A pipe, as `oc exec -i` gives the pod: a file as stdin makes Linux resolve /dev/stdin to it, so
        # sys.path[0] would be local-development/ and its gsd would shadow PYTHONPATH (macOS does not resolve it).
        return subprocess.run([sys.executable, "/dev/stdin", *args, "--offsite", str(self.offsite),
                               "--proc", str(self.proc), "--group", str(os.getgid())],
                              input=HELPER.read_text(), capture_output=True, text=True, env=environment, timeout=120)


@pytest.fixture
def pod(tmp_path: Path) -> Pod:
    """Live: 40 rows a table at KNOWN, then 500 sync_event rows only in its -wal. Copies: two backups at KNOWN
    (taken before the -wal rows), a pre-upgrade copy at KNOWN - 1 with its sidecar, an offsite copy with its."""
    p = Pod(tmp_path)
    make_db(p.db, 40, KNOWN)
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[1]}.db")
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    pre = p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-group-sync-dashboard-abc12-xyz34.db"
    vacuum_copy(older, pre)
    sidecar(pre)
    off = p.offsite / f"gsd-{STAMPS[3]}.db"
    vacuum_copy(p.db, off)
    sidecar(off)
    kill_writer_after(p.db, 500)
    return p


def ids(result: subprocess.CompletedProcess) -> list[str]:
    return re.findall(r"^(\S+-\d{8}T\d{6}\.\d{6}Z)\s", result.stdout, re.M)


def row(result: subprocess.CompletedProcess, rid: str) -> str:
    return next(line for line in result.stdout.splitlines() if line.startswith(rid + " "))


def tree(*dirs: Path) -> dict[str, tuple[int, str, int]]:
    return {str(p): (p.stat().st_size, sha(p), p.stat().st_mtime_ns)
            for d in dirs for p in sorted(d.rglob("*")) if p.is_file()}


def test_t302_1_list_shows_every_copy_with_its_id_schema_source_sidecar_and_verdict(pod: Pod) -> None:
    result = pod.run("list")
    assert result.returncode == 0, result.stderr
    assert sorted(ids(result)) == sorted([f"{KNOWN}-{STAMPS[0]}", f"{KNOWN}-{STAMPS[1]}", f"{KNOWN - 1}-{STAMPS[2]}",
                                         f"{KNOWN}-{STAMPS[3]}"])
    assert re.search(rf"^{KNOWN}-{STAMPS[0]}\s+{KNOWN}\s+2026-10-01T05:11:03Z\s+[\d.]+ MiB\s+backup\s+none\s+yes$",
                     result.stdout, re.M), result.stdout
    assert re.search(rf"\s+pre-upgrade\s+ok\s+yes, migrates {KNOWN - 1} -> {KNOWN} on start$",
                     row(result, f"{KNOWN - 1}-{STAMPS[2]}"))
    assert re.search(r"\s+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[3]}"))
    assert f"live     {pod.db} · user_version {KNOWN}" in result.stdout
    assert f"image    understands schema {KNOWN} and older" in result.stdout


def test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused(pod: Pod) -> None:
    twin = pod.offsite / f"gsd-{STAMPS[0]}.db"
    shutil.copy2(pod.backup / twin.name, twin)
    sidecar(twin)
    result = pod.run("list")
    assert ids(result).count(f"{KNOWN}-{STAMPS[0]}") == 1 and len(ids(result)) == len(set(ids(result)))
    assert re.search(r"\s+backup\+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[0]}"))

    other = pod.root / "other.db"
    make_db(other, 7, KNOWN)
    twin.unlink()
    vacuum_copy(other, twin)
    result = pod.run("list")
    assert ids(result).count(f"{KNOWN}-{STAMPS[0]}") == 1
    assert f"# {KNOWN}-{STAMPS[0]}: " in result.stdout and "differ; --from-version refuses this ID" in result.stdout
    before = tree(pod.data)
    refused = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert refused.returncode == 3
    assert str(pod.backup / twin.name) in refused.stderr and str(twin) in refused.stderr
    assert sha(pod.backup / twin.name) in refused.stderr and sha(twin) in refused.stderr
    assert tree(pod.data) == before


def test_t302_3_a_copy_newer_than_this_image_is_listed_as_not_understood(pod: Pod) -> None:
    newer = pod.root / "newer.db"
    make_db(newer, 5, KNOWN + 1)
    vacuum_copy(newer, pod.backup / "gsd-20261003T150002.513647Z.db")
    result = pod.run("list")
    assert row(result, f"{KNOWN + 1}-20261003T150002.513647Z").endswith(f"no ({KNOWN + 1} > {KNOWN})")


def test_t302_5_a_uvicorn_process_or_a_missing_env_is_refused_in_the_pod(tmp_path: Path) -> None:
    serving = Pod(tmp_path / "a", uvicorn=True)
    make_db(serving.db, 3, KNOWN)
    before = tree(serving.data)
    result = serving.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "uvicorn is running here (pid 1)" in result.stderr
    assert tree(serving.data) == before
    plain = Pod(tmp_path / "b")
    result = plain.run("list", env={"GSD_RECOVERY_MODE": ""})
    assert result.returncode == 2 and "GSD_RECOVERY_MODE is not true" in result.stderr


def test_t302_6_an_unknown_id_is_refused_and_nothing_is_touched(pod: Pod) -> None:
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN}-20200101T000000.000000Z")
    assert result.returncode == 3 and "no copy has the ID" in result.stderr
    assert tree(pod.data) == before


def test_t302_7_a_copy_newer_than_this_image_is_refused_with_both_numbers(pod: Pod) -> None:
    newer = pod.root / "newer.db"
    make_db(newer, 5, KNOWN + 1)
    vacuum_copy(newer, pod.backup / "gsd-20261003T150002.513647Z.db")
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN + 1}-20261003T150002.513647Z")
    assert result.returncode == 3
    assert f"database schema {KNOWN + 1} is newer than this dashboard understands ({KNOWN})" in result.stderr
    assert f"--from-version {KNOWN}-{STAMPS[1]}" in result.stderr          # the newest copy it does understand
    assert tree(pod.data) == before


def test_t302_8_a_truncated_copy_is_refused_by_integrity_check(pod: Pod) -> None:
    big = pod.root / "big.db"
    make_db(big, 5000, KNOWN)
    bad = pod.backup / "gsd-20261001T171103.000001Z.db"
    vacuum_copy(big, bad)
    bad.write_bytes(bad.read_bytes()[: bad.stat().st_size // 2])
    garbage = pod.backup / "gsd-20261001T171104.000002Z.db"
    garbage.write_bytes(b"not a database " * 300)
    listed = pod.run("list")
    assert row(listed, "?-20261001T171104.000002Z").endswith("no (not a database)")
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN}-20261001T171103.000001Z")
    assert result.returncode == 3 and "integrity_check said" in result.stderr, result.stderr
    result = pod.run("restore", "?-20261001T171104.000002Z")
    assert result.returncode == 3 and "is not a database SQLite can open" in result.stderr, result.stderr
    assert tree(pod.data) == before


def test_t302_9_a_sidecar_naming_another_digest_is_refused_with_both(pod: Pod) -> None:
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    sidecar(pre, "0" * 64)
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 3 and sha(pre) in result.stderr and "0" * 64 in result.stderr
    assert tree(pod.data) == before


def test_t302_10_check_prints_the_loss_window_and_the_rows_inserted_after_the_copy(pod: Pod) -> None:
    # Retention pruned 25 of the rows the copy still has; the copy's highest id is 40.
    conn = sqlite3.connect(pod.db)
    conn.execute("DELETE FROM membership_event WHERE id <= 25")
    conn.commit()
    conn.close()
    files = [n for n in ("gsd.db", "gsd.db-wal") if (pod.data / n).exists()]
    before = {n: sha(pod.data / n) for n in files}
    result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert "loss window  2026-10-01T05:11:03Z -> " in result.stdout
    assert re.search(r"membership_event\s+15\s+40\s+0$", result.stdout, re.M), result.stdout
    assert re.search(r"sync_event\s+540\s+40\s+500$", result.stdout, re.M)
    assert re.search(r"binding_event\s+40\s+40\s+0$", result.stdout, re.M)
    # check writes nothing: the database and its -wal are byte-identical (-shm is the index SQLite rebuilds on any open)
    assert {n: sha(pod.data / n) for n in files} == before
    assert not pod.pre_restore.exists()


def test_t302_12_the_live_set_is_kept_whole_with_its_wal(pod: Pod) -> None:
    assert count(pod.db) == 540                                    # 40, and 500 committed only to the -wal
    result = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    assert {"gsd.db", "gsd.db-wal"} <= {p.name for p in kept.iterdir()}
    assert count(kept / "gsd.db") == 540


def test_t302_14_the_copy_replaces_the_database_with_no_journal_and_the_group_set(pod: Pod) -> None:
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 0, result.stderr
    assert sha(pod.db) == sha(pre)
    assert sorted(p.name for p in pod.data.iterdir() if p.is_file()) == ["gsd.db"]
    mode = pod.db.stat().st_mode
    assert pod.db.stat().st_gid == os.getgid() and (mode & 0o070) == (mode & 0o700) >> 3    # chgrp, chmod g=u
    assert f"user_version {KNOWN} -> {KNOWN - 1}" in result.stdout


def test_t302_15_the_sources_are_only_read(pod: Pod) -> None:
    before = tree(pod.backup, pod.pre_upgrade, pod.offsite)
    assert pod.run("list").returncode == 0
    assert pod.run("restore", f"{KNOWN}-{STAMPS[3]}").returncode == 0
    after = tree(pod.backup, pod.pre_upgrade, pod.offsite)
    assert {k: v[:2] for k, v in after.items()} == {k: v[:2] for k, v in before.items()}


def test_t302_16_a_second_restore_is_refused_while_one_runs(pod: Pod) -> None:
    lock = pod.tmp / "gsd-restore.lock"
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write("started 2026-10-01T09:48:17Z, pid 4242, 20-x\n")
        fh.flush()
        before = tree(pod.data)
        result = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "started 2026-10-01T09:48:17Z" in result.stderr
    assert tree(pod.data) == before
    assert pod.run("restore", f"{KNOWN}-{STAMPS[0]}").returncode == 0     # released with its holder


def test_t302_18_a_copy_for_a_schema_this_image_lacks_gets_the_move_aside_note(pod: Pod) -> None:
    stuck = pod.pre_upgrade / f"pre-upgrade-20261003T090002.208311Z-schema-{KNOWN}-to-{KNOWN + 1}-pod-new.db"
    vacuum_copy(pod.backup / f"gsd-{STAMPS[1]}.db", stuck)
    sidecar(stuck)
    result = pod.run("restore", f"{KNOWN}-20261003T090002.208311Z")
    assert result.returncode == 0, result.stderr
    assert f"note: {stuck} was taken before an upgrade to schema {KNOWN + 1}" in result.stdout
    assert "This script moves nothing." in result.stdout and stuck.exists()


def test_t302_21_migrations_say_they_are_one_way_and_name_the_way_back() -> None:
    source = (LOCAL_DEV / "gsd" / "store.py").read_text()
    above = source.split("\n_MIGRATIONS: list[", 1)[0].rsplit("\n\n", 1)[-1]
    assert "ONE-WAY" in above and "pre-upgrade" in above and "restore-db.sh" in above


# --- T302-13: a kill after each step, as SIGKILL leaves it (no cleanup runs) -------------------------------------

DRIVER = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
step, when = sys.argv[2], sys.argv[3]       # when: before/after (the rename), or the call to kill after
if step == "rename":                       # the rename onto gsd.db: killed just before it, or just after it
    real = os.replace
    def rename(src, dst):
        if str(dst).endswith("gsd.db"):
            if when == "after":
                real(src, dst)
            os._exit(9)
        return real(src, dst)
    os.replace = rename
else:                                      # killed as soon as that call to the step returns
    real, calls = getattr(m, step), []
    def killed(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append(1)
        if len(calls) == (1 if when == "after" else int(when)):
            os._exit(9)
        return result
    setattr(m, step, killed)
sys.exit(m.main(sys.argv[4:]))
'''


def _driven(pod: Pod, *argv: str) -> subprocess.CompletedProcess:
    """The helper in a process of its own, with one of its steps replaced as DRIVER-like code says."""
    env = {**os.environ, "PYTHONPATH": str(LOCAL_DEV), "GSD_RECOVERY_MODE": "true", "GSD_DB_PATH": str(pod.db),
           "GSD_BACKUP_DIR": str(pod.backup), "TMPDIR": str(pod.tmp)}
    return subprocess.run([sys.executable, "-c", *argv[:1], str(HELPER), *argv[1:], "--offsite", str(pod.offsite),
                           "--proc", str(pod.proc), "--group", str(os.getgid())],
                          env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("step, when", [("write", "after"), ("copy_file", "2"), ("keep", "after"),
                                        ("fold", "after"), ("rename", "before"), ("rename", "after")],
                         ids=["after-write", "mid-keep", "after-keep", "after-fold", "before-rename", "after-rename"])
def test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one(pod: Pod, step: str, when: str) -> None:
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    copy = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    killed = _driven(pod, DRIVER, step, when, "restore", rid)
    assert killed.returncode == 9, killed.stderr
    side = [n for n in ("gsd.db-wal", "gsd.db-journal") if (pod.data / n).exists()]
    if sha(pod.db) == sha(copy):
        assert not side, "the restored file sits beside a journal it did not write"
    else:
        assert count(pod.db) == 540                                  # the old database, whole
    for kept in [d for d in pod.pre_restore.glob("*") if d.is_dir() and not d.name.endswith(".tmp")]:
        assert count(kept / "gsd.db") == 540                         # a finished keep is the whole live set
    rerun = pod.run("restore", rid)                                  # and the next run finishes the job
    assert rerun.returncode == 0, rerun.stderr
    assert sha(pod.db) == sha(copy) and not list(pod.data.glob("*.tmp")) and not list(pod.pre_restore.glob("*.tmp"))


FAILING_RENAME = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real = os.replace
def rename(src, dst):
    if str(dst).endswith("gsd.db"):
        raise OSError(28, "No space left on device")
    return real(src, dst)
os.replace = rename
sys.exit(m.main(sys.argv[2:]))
'''


def test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole(pod: Pod) -> None:
    result = _driven(pod, FAILING_RENAME, "restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 1
    assert "the restore failed at the step swap" in result.stderr and "whole, without its -wal" in result.stderr
    assert count(pod.db) == 540 and not (pod.data / "gsd.db-wal").exists()
    assert not (pod.data / "gsd.db.restore.tmp").exists()


CHANGED_SOURCE = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real = m.copy_file
def copy_file(source, target):
    if str(target).endswith(".restore.tmp"):                 # the copy changed after it was checked
        source = next(m.Path(os.environ["GSD_BACKUP_DIR"]).glob("gsd-*.db"))
    return real(source, target)
m.copy_file = copy_file
sys.exit(m.main(sys.argv[2:]))
'''


def test_a_copy_that_changed_after_its_check_is_not_swapped_in(pod: Pod) -> None:
    before = sha(pod.db)
    result = _driven(pod, CHANGED_SOURCE, "restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 1 and "the restore failed at the step write" in result.stderr, result.stderr
    assert "it changed while it was read" in result.stderr and sha(pod.db) == before
    assert not (pod.data / "gsd.db.restore.tmp").exists() and count(pod.db) == 540


# --- added by the research and the design ---------------------------------------------------------------------

SIDECARS = [
    ("{d}  {n}\n", True), ("{d}  {n}", True), ("{d}\t{n}\r\n", True), ("{D}  {n}\n", True),
    ("{d}\n{n}\n", False), ("{d}  other.db\n", False), ("", False), ("{d}  {n}\n{d}  {n}\n", False),
    ("not-a-digest  {n}\n", False), ("{d}  {n} \n", False),
]


@pytest.mark.parametrize("text, valid", SIDECARS, ids=[f"case{i}" for i in range(len(SIDECARS))])
def test_the_sidecar_parser_is_the_offsite_scripts(tmp_path: Path, text: str, valid: bool) -> None:
    helper, offsite = _load(HELPER, "restore_db"), _load(OFFSITE_SCRIPT, "offsite_backup")
    assert helper.SIDECAR_LINE.pattern == offsite.SIDECAR_LINE.pattern
    name, digest = "gsd-20261001T051103.798578Z.db", "ab" * 32
    side = tmp_path / (name + ".sha256")
    side.write_text(text.format(d=digest, D=digest.upper(), n=name), newline="")
    assert helper.sidecar_expected(side, name) == offsite.sidecar_expected(side, name)
    assert (helper.sidecar_expected(side, name) == digest) is valid


def _pods(env: dict, *, start: str, running: bool = True, count: int = 1, image: str = "q/gsd:2.0.0") -> dict:
    pod = {"metadata": {"name": "group-sync-dashboard-6c5d8f7b9d-q2x7m"},
           "spec": {"containers": [{"name": "dashboard", "image": image,
                                    "env": [{"name": k, "value": v} for k, v in env.items()]},
                                   {"name": "oauth-proxy", "image": "proxy"}]},
           "status": {"startTime": start,
                      "containerStatuses": [{"name": "dashboard", "state": {"running": {}} if running else
                                             {"waiting": {"reason": "CrashLoopBackOff"}}}]}}
    return {"items": [pod] * count}


def test_preflight_bounds_the_ttl_by_the_pods_start_not_the_containers_restart() -> None:
    helper = _load(HELPER, "restore_db")
    now = 1_790_000_000.0
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
    env = {"GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}
    name, image, left = helper.preflight(_pods(env, start=start), "r", "n", now)
    assert (name, image, left) == ("group-sync-dashboard-6c5d8f7b9d-q2x7m", "q/gsd:2.0.0", 3600)
    with pytest.raises(helper.Refused) as late:
        helper.preflight(_pods({**env, "GSD_RECOVERY_MODE_TTL": "1h5m"}, start=start), "r", "n", now)
    assert late.value.code == 2 and "at most 5m of recovery.ttl 1h5m is left" in str(late.value)
    with pytest.raises(helper.Refused, match="not running"):
        helper.preflight(_pods(env, start=start, running=False), "r", "n", now)


def test_the_go_durations_recovery_ttl_takes() -> None:
    helper = _load(HELPER, "restore_db")
    assert [helper.ttl_seconds(t) for t in ("2h", "90m", "1h30m", "1.5h", "abc", "7200", "0s")] == \
        [7200.0, 5400.0, 5400.0, 5400.0, None, None, 0.0]
    assert [helper.span(s) for s in (7200, 5400, 45, 0, -3)] == ["2h", "1h30m", "45s", "0s", "0s"]
    if RECOVERY_SCRIPT.is_file():                                   # #303's script, once it is on the branch
        recovery = _load(RECOVERY_SCRIPT, "recovery_mode")
        for text in ("2h", "90m", "1h30m", "1.5h", "500ms", "abc", "7200", "-5m", "0s"):
            assert helper.ttl_seconds(text) == recovery.ttl_seconds(text), text


def test_an_image_older_than_known_schema_version_reads_it_from_the_migrations(tmp_path: Path) -> None:
    package = tmp_path / "old" / "gsd"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "store.py").write_text("_MIGRATIONS = [(1, 'a', []), (17, 'b', []), (9, 'c', [])]\n")
    p = Pod(tmp_path / "pod")
    make_db(p.db, 1, 17)
    result = p.run("list", env={"PYTHONPATH": str(tmp_path / "old")})
    assert result.returncode == 0, result.stderr
    assert "image    understands schema 17 and older" in result.stdout


def test_the_backup_directory_is_read_from_the_config_when_the_env_does_not_set_it(pod: Pod) -> None:
    config = pod.root / "clusters.yaml"
    config.write_text(f'backupDir: "{pod.backup}"\nbackupKeep: 4\n')
    result = pod.run("list", env={"GSD_BACKUP_DIR": "", "GSD_CONFIG": str(config)})
    assert f"{KNOWN}-{STAMPS[0]}" in ids(result)
    off = pod.run("list", env={"GSD_BACKUP_DIR": "", "GSD_CONFIG": str(pod.root / "absent.yaml")})
    assert f"{KNOWN}-{STAMPS[0]}" not in ids(off) and "# backup: config.backup is off" in off.stdout


def test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back(pod: Pod, monkeypatch) -> None:
    """wal.html §4: open and close is the safe way to remove a -wal. After it the old file alone holds the
    500 rows, so a kill between the removal and the rename loses nothing (T302-13 after-fold)."""
    helper = _load(HELPER, "restore_db")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    removed = helper.fold(helper.Layout(pod.offsite))
    assert not (pod.data / "gsd.db-wal").exists() and not (pod.data / "gsd.db-shm").exists()
    assert removed == [] and count(pod.db) == 540


def test_the_helper_parses_on_the_oldest_python_it_meets() -> None:
    """The laptop's python3 runs preflight; the pod's python3.14 runs the rest."""
    ast.parse(HELPER.read_text(), feature_version=(3, 9))


def test_the_wrapper_is_executable() -> None:
    assert os.access(LOCAL_DEV / "restore-db.sh", os.X_OK)


# --- added by the review (2026-10-01) ------------------------------------------------------------------------------

HOLDER = r'''
import sqlite3, sys, time
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
c.execute("PRAGMA user_version").fetchone()
print("ready", flush=True)
time.sleep(60)
'''


def test_the_fold_removes_nothing_sqlite_did_not_fold(pod: Pod) -> None:
    """Another process with the live file open (a --list or check in a second session): SQLite's close then folds
    nothing and says nothing. The restore must stop at the fold with the old database whole, not remove the -wal
    and leave /data/gsd.db without its 500 rows (§3.6; measured in §2.1)."""
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(pod.db)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    finally:
        holder.kill()
        holder.wait()
    assert result.returncode == 1, result.stderr
    assert "the restore failed at the step fold" in result.stderr and "SQLite did not fold gsd.db-wal" in result.stderr
    assert (pod.data / "gsd.db-wal").exists() and count(pod.db) == 540
    assert not (pod.data / "gsd.db.restore.tmp").exists()


def test_the_fold_folds_a_database_a_newer_image_wrote(pod: Pod, monkeypatch) -> None:
    """The rollback case: the newer image's last transaction put rows and a schema entry this SQLite cannot parse
    into the -wal. Opening and closing reads no schema, so the fold still writes the -wal back (§2.1)."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('PRAGMA writable_schema=ON'); c.execute('BEGIN')\n"
            "[c.execute('INSERT INTO sync_event(v) VALUES (?)', ('newer',)) for _ in range(100)]\n"
            "c.execute(\"INSERT INTO sqlite_schema(type, name, tbl_name, rootpage, sql) VALUES "
            "('table', 'future', 'future', 0, 'CREATE TABLE future(a FUTURE_SYNTAX(')\")\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(pod.db)], check=False)
    helper = _load(HELPER, "restore_db")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    assert helper.fold(helper.Layout(pod.offsite)) == [] and not (pod.data / "gsd.db-wal").exists()
    conn = sqlite3.connect(pod.db)
    conn.execute("PRAGMA writable_schema=ON")
    try:
        assert conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 640
    finally:
        conn.close()


def test_a_live_file_that_is_not_a_database_is_replaced_around(pod: Pod) -> None:
    """A live gsd.db SQLite cannot open at all is no reason to refuse: the set was kept first (fold's docstring).
    SQLite cannot open it when nothing beside it holds page 1: here its -wal holds rows rewritten in place only, so
    the open raises DatabaseError, which the fold takes as "not a database" (a fold that let it through refuses).
    Over a -wal that holds page 1, SQLite opens such a file through the -wal instead (the next test)."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('BEGIN')\n"
            "c.execute(\"UPDATE sync_event SET v = 'Z' || substr(v, 2) WHERE id <= 40\")\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(pod.db)], check=False)
    assert (pod.data / "gsd.db-wal").stat().st_size                # bytes no file but the lost one can take
    pod.db.write_bytes(b"not a database " * 1000)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 0, result.stderr
    assert sha(pod.db) == sha(next(pod.pre_upgrade.glob("pre-upgrade-*.db")))
    assert sorted(p.name for p in pod.data.iterdir() if p.is_file()) == ["gsd.db"]


def test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so(tmp_path: Path) -> None:
    """A gsd.db cut short beside the -wal its writer left, page 1 among its frames: SQLite opens it through the -wal
    and raises nothing, and its close cannot write the -wal back (an explicit checkpoint says `database disk image is
    malformed`). The fold stops with nothing removed, and its message names damage and the manual path, not only a
    session or a permission (review of the spec, 2026-10-01; SPEC_E3 §2.1)."""
    p = Pod(tmp_path)
    make_db(p.db, 40, KNOWN)
    conn = sqlite3.connect(p.db)
    conn.execute("CREATE TABLE pad (v BLOB)")
    conn.executemany("INSERT INTO pad VALUES (?)", [(os.urandom(4000),) for _ in range(400)])
    conn.commit()
    conn.close()
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    vacuum_copy(older, p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-pod-a.db")
    kill_writer_after(p.db, 500)
    p.db.write_bytes(p.db.read_bytes()[: p.db.stat().st_size // 2])
    wal = (p.data / "gsd.db-wal").read_bytes()
    result = p.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 1 and "the restore failed at the step fold" in result.stderr, result.stderr
    assert "damaged" in result.stderr and "section 4a" in result.stderr, result.stderr
    assert (p.data / "gsd.db-wal").read_bytes() == wal and not (p.data / "gsd.db.restore.tmp").exists()


def test_check_counts_every_history_table_the_store_keeps(tmp_path: Path) -> None:
    """The store keeps five AUTOINCREMENT event tables (Store._HISTORY_TABLES, and login_event, pruned on its own);
    a restore discards the rows added to each after the copy, so `check` counts each."""
    from gsd import store
    helper = _load(HELPER, "restore_db")
    assert set(store.Store._HISTORY_TABLES) | {"login_event"} <= set(helper.HISTORY)
    p = Pod(tmp_path)
    conn = sqlite3.connect(p.db)
    conn.executescript(store.SCHEMA)
    conn.execute(f"PRAGMA user_version = {KNOWN}")
    conn.commit()
    conn.close()
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    conn = sqlite3.connect(p.db)
    conn.executemany("INSERT INTO login_event(cluster_id, pod_name, user_name, outcome, at, observed_at) "
                     "VALUES ('c', 'n', ?, 'success', '2026-10-01T12:00:00Z', '2026-10-01T12:00:01Z')",
                     [(f"u{i}",) for i in range(7)])
    conn.executemany("INSERT INTO kyverno_result_event(cluster_id, policy_kind, policy, resource_kind, resource_name, "
                     "change, result, observed_at) VALUES ('c', 'ValidatingPolicy', 'p', 'Pod', ?, 'appeared', 'fail', "
                     "'2026-10-01T12:00:00Z')", [(f"r{i}",) for i in range(3)])
    conn.commit()
    conn.close()
    result = p.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert re.search(r"login_event\s+7\s+0\s+7$", result.stdout, re.M), result.stdout
    assert re.search(r"kyverno_result_event\s+3\s+0\s+3$", result.stdout, re.M), result.stdout


def confirmation(result: subprocess.CompletedProcess) -> tuple[str, str, str]:
    (line,) = re.findall(r"^confirmation sha256=([0-9a-f]{64}) size=(\d+) live-sha256=([0-9a-f]{64})$", result.stdout, re.M)
    return line


def test_restore_refuses_a_copy_or_a_live_set_other_than_the_ones_check_showed(pod: Pod) -> None:
    """restore-db.sh asks between two sessions: `check` prints the copy's sha256 and size and the live set's
    fingerprint, and `restore` refuses either changed before anything is written (review of the spec, F1/F4)."""
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    copy = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    digest, size, live = confirmation(pod.run("check", rid))
    assert (digest, int(size)) == (sha(copy), copy.stat().st_size)
    before = tree(pod.data)
    for wrong in (("0" * 64, size, live), (digest, str(int(size) + 1), live), (digest, size, "0" * 64)):
        refused = pod.run("restore", rid, "--expected-sha256", wrong[0], "--expected-size", wrong[1],
                          "--expected-live-sha256", wrong[2])
        assert refused.returncode == 3 and "after the check you answered" in refused.stderr, refused.stderr
    partial = pod.run("restore", rid, "--expected-sha256", digest)
    assert partial.returncode == 3 and "all three" in partial.stderr
    assert tree(pod.data) == before
    assert pod.run("restore", rid, "--expected-sha256", digest, "--expected-size", size,
                   "--expected-live-sha256", live).returncode == 0


def test_the_live_fingerprint_ignores_the_shm_a_reader_rewrites(pod: Pod) -> None:
    """Any open between `check` and `restore`, a --list among them, may rewrite the -shm index (§2.2): not a change."""
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    digest, size, live = confirmation(pod.run("check", rid))
    shm = Path(f"{pod.db}-shm")
    before = shm.read_bytes()
    shm.write_bytes(b"\0" * len(before))
    assert shm.read_bytes() != before
    assert pod.run("restore", rid, "--expected-sha256", digest, "--expected-size", size,
                   "--expected-live-sha256", live).returncode == 0


@pytest.mark.parametrize("left, boot", [(300.0, None), (7200.0, "a-boot-that-is-not-this-one"), (None, None),
                                        (float("nan"), None)],
                         ids=["too-little-left", "the-node-restarted", "no-record", "not-a-finite-number"])
def test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it(pod: Pod, left, boot) -> None:
    """SPEC_E2's own answer, read in the pod as the restore starts: deadline_monotonic minus the clock, 0 on another
    boot, unknown without the record; each refuses with exit 2 and writes nothing (review of the spec, E2 rework)."""
    if left is None:
        (pod.tmp / "gsd-recovery.json").unlink()
    else:
        pod.ttl_left(left, boot)
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 2, result.stderr
    assert ("cannot be read" if left is None or left != left else "of the recovery TTL is left in this pod") in result.stderr
    assert tree(pod.data) == before and not pod.pre_restore.exists()


def test_list_keeps_a_long_source_apart_from_its_sidecar(pod: Pod) -> None:
    """A pre-upgrade copy #304 has shipped offsite lists as `pre-upgrade+offsite`, 19 characters."""
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    (pod.offsite / pre.name).write_bytes(pre.read_bytes())
    result = pod.run("list")
    assert re.search(rf"\s+pre-upgrade\+offsite\s+ok\s+yes, migrates {KNOWN - 1} -> {KNOWN} on start$",
                     row(result, f"{KNOWN - 1}-{STAMPS[2]}")), result.stdout


def test_the_runbooks_undo_folds_the_kept_set_into_one_whole_file(pod: Pod) -> None:
    """The way back is the kept set; its gsd.db copied alone counts 40 of 540. Runbook §4's "Undo a restore" folds
    it first: run as the runbook prints it, the kept gsd.db alone holds all 540."""
    assert pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}").returncode == 0
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    match = re.search(r"python3\.14 -c '([^']+)' /data/pre-restore/<stamp>/gsd\.db", runbook)
    assert match, "runbook §4 has no command that folds the kept set"
    subprocess.run([sys.executable, "-c", match.group(1), str(kept / "gsd.db")], check=True)
    alone = pod.root / "alone"
    alone.mkdir()
    shutil.copy2(kept / "gsd.db", alone / "gsd.db")
    assert count(alone / "gsd.db") == 540 and not (kept / "gsd.db-wal").exists()


def test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written(pod: Pod) -> None:
    """Runbook §4's "Undo a restore", run as printed after a restore that stopped at the fold (a gsd.db the pod
    cannot write): §4a's commands keep the live set and remove its -wal, so the copy they put in its place must
    already sit beside gsd.db under a temporary name. Removed first and written after, gsd.db read 40 of 540 rows
    when the write was refused (the blocks of 159deef8; review of the spec, 2026-10-01)."""
    if os.geteuid() == 0:
        pytest.skip("root writes a 0444 file")
    pod.db.chmod(0o444)
    stopped = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert stopped.returncode == 1 and "the restore failed at the step fold" in stopped.stderr, stopped.stderr
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    fold = re.search(r"python3\.14 -c '([^']+)' /data/pre-restore/<stamp>/gsd\.db", runbook).group(1)
    subprocess.run([sys.executable, "-c", fold, str(kept / "gsd.db")], check=True)
    lines = runbook.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c '"))
    body = "\n".join(lines[start + 1:lines.index("'", start + 1)])
    script = (body.replace("/data/backup/gsd-….db", f"/data/pre-restore/{kept.name}/gsd.db").replace("/data", str(pod.data))
              .replace("python3.14", sys.executable).replace("chgrp 0 ", f"chgrp {os.getgid()} "))
    subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
    assert count(pod.db) == 540                                      # the old database whole, put back from the keep


def test_no_refusal_offers_a_way_but_the_values_file(pod: Pod) -> None:
    """The operator's rule as SPEC_E2 applies it (its notes 5 and 16): every message a program prints names the
    release's values file as the way to extend or leave recovery mode, and a pod's deletion is not offered as one.
    The three TTL refusals: the container not running, too little left by the pod spec, and as SPEC_E2 counts it."""
    helper = _load(HELPER, "restore_db")
    now = 1_790_000_000.0
    env = {"GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7000))
    said = []
    for doc in (_pods(env, start=start), _pods(env, start=start, running=False)):
        with pytest.raises(helper.Refused) as refused:
            helper.preflight(doc, "r", "n", now)
        said.append(str(refused.value))
    pod.ttl_left(100.0)
    said.append(pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}").stderr)
    for text in said:
        assert "values file" in text and "oc delete" not in text, text


def test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go() -> None:
    """Runbook §4a, §4b and the S3 note write the copy beside gsd.db under a temporary name and rename it after the
    old side files are removed, so a write that fails (a full volume, a gsd.db the pod cannot write) stops before
    anything is removed (confirmation pass of the spec, F1: removed first and written after, gsd.db read 40 of 540)."""
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("\n## 4.", 1)[1].split("\n## 5.", 1)[0]
    assert not re.search(r"> /data/gsd\.db['\s]", section), "a manual path writes the copy onto /data/gsd.db itself"
    assert section.count("> /data/gsd.db.restore.tmp") == 3            # §4a, §4b and the S3 note


def test_the_runbook_removes_every_journal_it_keeps() -> None:
    """Runbook §4's manual paths keep the live set, -journal included, and must remove all three side files before
    a copy takes the name: a hot -journal left beside it is rolled back into the copy (howtocorrupt §1.4)."""
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("\n## 4.", 1)[1].split("\n## 5.", 1)[0]
    removes = re.findall(r"rm -f /data/gsd\.db-wal\s+/data/gsd\.db-shm[^\n`]*", section)
    assert len(removes) == 3 and all("/data/gsd.db-journal" in line for line in removes), removes
    assert section.count("for name in (") == 2                       # §4a and §4b keep the set first


def test_the_s3_note_counts_the_lines_it_names() -> None:
    """Runbook §4b's S3 note names three lines to finish with (the ownership line, the rm -f line, the rename):
    the copy is already streamed in under the temporary name, so §4b's `cat /offsite/… > …restore.tmp` line,
    the fourth from the end, must not be run again. The count has to match what it names."""
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    note = runbook.split("For an S3 copy:", 1)[1].split("\n\n", 1)[0]
    assert "finish with the last three lines above" in note, note
    assert "last four lines" not in note
