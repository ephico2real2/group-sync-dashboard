"""restore-db.sh (#302), driven end to end with `oc` stubbed on PATH, as tests/test_release_crc.py drives its
script. The stub answers `oc get pods` from a file and runs `oc exec ... python3.14 /dev/stdin <args>` here, with
the streamed helper on stdin, against a temporary pod (tests/test_restore_db.py's). docs/specs/SPEC_E3_restore_db.md
§4 maps each test to its case."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN
from test_restore_db import STAMPS, Pod, count, kill_writer_after, make_db, sidecar, vacuum_copy

LOCAL_DEV = Path(__file__).resolve().parents[1]
WRAPPER = LOCAL_DEV / "restore-db.sh"

STUB = r'''#!/usr/bin/env bash
# Every call is logged as one line. `oc get pods` answers from STUB_PODS; `oc exec` runs the streamed helper here.
printf '%s\n' "$*" >> "$STUB_LOG"
case "$1" in
  get) cat "$STUB_PODS" ;;
  exec)
    while [ "$#" -gt 0 ] && [ "$1" != /dev/stdin ]; do shift; done
    shift
    exec "$STUB_PYTHON" /dev/stdin "$@" --offsite "$STUB_OFFSITE" --proc "$STUB_PROC" --group "$STUB_GROUP" ;;
esac
'''


def pods(pod_env: dict, *, started_ago: float = 600, n: int = 1) -> dict:
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - started_ago))
    item = {"metadata": {"name": "group-sync-dashboard-6c5d8f7b9d-q2x7m"},
            "spec": {"containers": [{"name": "dashboard", "image": "quay.io/ephico2real/group-sync-dashboard:2.0.0",
                                     "env": [{"name": k, "value": v} for k, v in pod_env.items()]}]},
            "status": {"startTime": start, "containerStatuses": [{"name": "dashboard", "state": {"running": {}}}]}}
    return {"items": [item] * n}


RECOVERY = {"GSD_DB_PATH": "/data/gsd.db", "GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}


@pytest.fixture
def lab(tmp_path: Path):
    """A temporary pod with copies (as tests/test_restore_db.py's), the stub on PATH, and a runner."""
    p = Pod(tmp_path / "pod")
    make_db(p.db, 40, KNOWN)
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    pre = p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-pod-a.db"
    vacuum_copy(older, pre)
    sidecar(pre)
    kill_writer_after(p.db, 500)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "oc").write_text(STUB)
    (bin_dir / "oc").chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    log, pods_file = tmp_path / "oc.log", tmp_path / "pods.json"

    def run(*args: str, pod_list: dict, answer: str = "") -> subprocess.CompletedProcess:
        pods_file.write_text(json.dumps(pod_list))
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(log),
               "STUB_PODS": str(pods_file), "STUB_PYTHON": sys.executable, "STUB_OFFSITE": str(p.offsite),
               "STUB_PROC": str(p.proc), "STUB_GROUP": str(os.getgid()), "PYTHONPATH": str(LOCAL_DEV),
               "GSD_RECOVERY_MODE": "true", "GSD_DB_PATH": str(p.db), "GSD_BACKUP_DIR": str(p.backup),
               "TMPDIR": str(p.tmp)}
        return subprocess.run(["bash", str(WRAPPER), *args], input=answer, capture_output=True, text=True,
                              env=env, timeout=120)

    run.pod, run.log, run.pre = p, log, pre
    return run


def calls(lab) -> list[str]:
    return lab.log.read_text().splitlines() if lab.log.exists() else []


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t302_4_outside_recovery_mode_it_refuses_names_the_value_and_never_execs(lab) -> None:
    result = lab("--list", pod_list=pods({"GSD_DB_PATH": "/data/gsd.db"}))
    assert result.returncode == 2
    assert "is not in recovery mode" in result.stderr
    assert "Set recovery.enabled: true and recovery.ttl: 2h in this release's values file" in result.stderr
    assert "applications.argoproj.io" not in result.stderr and "helm upgrade" not in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_t532_7_the_pods_are_listed_from_both_workloads(lab) -> None:
    """The recovery pod is app=<release>-recovery from chart 0.65.0 and app=<release> before it; both are listed,
    so an app pod still terminating beside the recovery pod makes two and is refused (#532)."""
    lab("--list", pod_list=pods(RECOVERY))
    (listed,) = [c for c in calls(lab) if c.startswith("get pods")]
    assert "-l app in (group-sync-dashboard,group-sync-dashboard-recovery)" in listed, listed


@pytest.mark.parametrize("n", [0, 2])
def test_t302_5_none_or_two_pods_are_refused_before_any_exec(lab, n: int) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY, n=n))
    assert result.returncode == 2 and f"{n} pods match app=group-sync-dashboard" in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_t302_5_uvicorn_in_the_pod_is_refused_by_the_helper_and_nothing_is_written(lab) -> None:
    (lab.pod.proc / "1" / "cmdline").write_bytes(b"python3.14\0-m\0uvicorn\0gsd.api:create_app\0")
    before = digest(lab.pod.db)
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 2 and "uvicorn is running here" in result.stderr
    assert digest(lab.pod.db) == before and not lab.pod.pre_restore.exists()


def test_t302_10_answering_no_writes_nothing_after_the_loss_window_is_shown(lab) -> None:
    before = {n: digest(lab.pod.data / n) for n in ("gsd.db", "gsd.db-wal")}
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", pod_list=pods(RECOVERY), answer="n\n")
    assert result.returncode == 4 and "not confirmed" in result.stderr
    assert "loss window  2026-10-01T05:11:03Z -> " in result.stdout and "[y/N]" in result.stdout
    assert "sync_event" in result.stdout and result.stdout.count("discarded") >= 1
    assert [c.split(" -- ")[1] for c in calls(lab) if c.startswith("exec")] == [
        f"python3.14 /dev/stdin check {KNOWN}-{STAMPS[0]}"]
    assert {n: digest(lab.pod.data / n) for n in ("gsd.db", "gsd.db-wal")} == before
    assert not lab.pod.pre_restore.exists()


def test_t302_11_yes_restores_without_asking(lab) -> None:
    result = lab("--from-version", f"{KNOWN - 1}-{STAMPS[2]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert "[y/N]" not in result.stdout
    assert f"user_version {KNOWN} -> {KNOWN - 1}" in result.stdout
    assert digest(lab.pod.db) == digest(lab.pre)
    (kept,) = [d for d in lab.pod.pre_restore.iterdir() if d.is_dir()]
    assert count(kept / "gsd.db") == 540
    assert [c.split(" -- ")[1].split()[2] for c in calls(lab) if c.startswith("exec")] == ["check", "restore"]


def test_t302_17_too_little_ttl_left_is_refused_from_the_pod_spec_alone(lab) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes",
                 pod_list=pods(RECOVERY, started_ago=2 * 3600 - 300))
    assert result.returncode == 2
    assert "of recovery.ttl 2h is left, less than the 10m a restore keeps in hand" in result.stderr
    assert "a longer recovery.ttl" in result.stderr and "oc delete" not in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_list_prints_the_pod_the_image_and_the_rows(lab) -> None:
    result = lab("--list", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("pod      group-sync-dashboard-6c5d8f7b9d-q2x7m · recovery mode, at least 1h49m")
    assert "image    quay.io/ephico2real/group-sync-dashboard:2.0.0" in result.stdout
    assert f"{KNOWN - 1}-{STAMPS[2]}" in result.stdout


def test_usage_errors_exit_64(lab) -> None:
    for args in ((), ("--from-version",), ("--bogus",), ("--namespace", "")):
        assert lab(*args, pod_list=pods(RECOVERY)).returncode == 64, args


def test_the_restore_is_bound_to_what_check_showed(lab) -> None:
    """The question sits between two sessions; `restore` gets check's confirmation line and refuses anything else."""
    result = lab("--from-version", f"{KNOWN - 1}-{STAMPS[2]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert f"confirmation sha256={digest(lab.pre)} size={lab.pre.stat().st_size} live-sha256=" in result.stdout
    restore = [c.split(" -- ")[1] for c in calls(lab) if c.startswith("exec")][-1].split()
    assert restore[:4] == ["python3.14", "/dev/stdin", "restore", f"{KNOWN - 1}-{STAMPS[2]}"]
    assert restore[4:8] == ["--expected-sha256", digest(lab.pre), "--expected-size", str(lab.pre.stat().st_size)]
    assert restore[8] == "--expected-live-sha256" and len(restore[9]) == 64
