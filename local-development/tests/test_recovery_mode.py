"""Recovery mode's script (#303), run as the pod runs it: a separate Python process.

The script is `charts/group-sync-dashboard/scripts/recovery_mode.py`, shipped in a ConfigMap so it
runs under the older image a rollback targets. These tests hold what the issue asks of it: it never
imports the store or sqlite3 and never touches the data directory; it says what the pod is; it ends
at the TTL saying how to extend it, through the release's values file and nothing else; it stops on
SIGTERM at once; and the TTL survives a container restart, which the kubelet performs at once after
an exit.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "scripts" / "recovery_mode.py"
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ gsd-recovery ")
IDLE = "the app is NOT running and no data is collected"
#: What the log at the TTL must never print (the operator, 2026-10-01): the values file through the release's
#: deployment pipeline is the one way to change recovery mode, so no Helm or Argo CD command line.
NOT_IN_THE_LOG = ("helm upgrade", "--set", "--reset-then-reuse-values", "--reuse-values", "argocd",
                  "applications.argoproj.io", "oc patch", "oc delete", "parameters")


def _module():
    spec = importlib.util.spec_from_file_location("recovery_mode", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _env(tmp: pathlib.Path, ttl: str, data: pathlib.Path | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GSD_")}
    env.update(TMPDIR=str(tmp), GSD_RECOVERY_MODE="true", GSD_RECOVERY_MODE_TTL=ttl, POD_NAME="gsd-recovery-test",
               GSD_DB_PATH=str((data or tmp / "data") / "gsd.db"))
    return env


def _run(env: dict[str, str], *args: str, timeout: float = 30) -> tuple[subprocess.CompletedProcess, float]:
    started = time.monotonic()
    done = subprocess.run([sys.executable, *args, str(SCRIPT), "--release", "rel",
                           "--report-every", "0.5"], env=env, capture_output=True, text=True, timeout=timeout)
    return done, time.monotonic() - started


def _start(env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(SCRIPT), "--release", "rel"], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _banner(proc: subprocess.Popen) -> list[str]:
    return [proc.stdout.readline().rstrip("\n") for _ in range(4)]


def test_t303_8_it_imports_neither_the_store_nor_sqlite3_and_touches_nothing_in_the_data_directory(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("gsd.db", "gsd.db-wal", "gsd.db-shm"):
        (data / name).write_bytes(b"live database bytes")
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in data.iterdir()}
    sealed = os.geteuid() != 0                       # root ignores the mode; the listing still holds
    if sealed:
        data.chmod(0o000)                            # any open or stat under it would now fail
    try:
        done, _ = _run(_env(tmp_path, "1s", data), "-X", "importtime")
    finally:
        data.chmod(0o755)
    imported = {line.rsplit("|", 1)[1].strip() for line in done.stderr.splitlines() if line.startswith("import time:")}
    assert imported, done.stderr                     # -X importtime ran, so the absence below means something
    assert not {"sqlite3", "_sqlite3", "gsd", "gsd.store"} & imported, sorted(imported)
    assert "Traceback" not in done.stderr and done.returncode == 1, (done.returncode, done.stderr[-2000:])
    assert "TTL 1s reached" in done.stdout
    assert {p.name: (p.stat().st_size, p.stat().st_mtime_ns) for p in data.iterdir()} == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data", "gsd-recovery.json"]


def test_t303_9_the_log_says_what_the_pod_is_then_counts_down_in_utc(tmp_path):
    done, _ = _run(_env(tmp_path, "3s"))
    lines = done.stdout.splitlines()
    stamped = [line for line in lines if not line.startswith("  ")]
    assert all(STAMP.match(line) for line in stamped), lines
    banner = "\n".join(lines[:4])
    for words in ("RECOVERY MODE", "GSD_RECOVERY_MODE=true", "GSD_RECOVERY_MODE_TTL=3s", IDLE,
                  f"data path {tmp_path / 'data' / 'gsd.db'} (not opened by this process)", "TTL 3s: ends ", "3s left"):
        assert words in banner, (words, banner)
    assert "check the time left before a restore" in lines[4] and "every process in the container stops" in lines[4]
    countdown = [line for line in lines[5:] if line.endswith(f"left; {IDLE}")]
    assert len(countdown) >= 2, lines


def test_t303_10_at_the_ttl_it_exits_1_and_says_how_to_extend_or_leave_through_the_values_file(tmp_path):
    done, took = _run(_env(tmp_path, "1s"))
    assert done.returncode == 1 and took < 1 + 1.5, (done.returncode, took)
    out = done.stdout
    assert "TTL 1s reached at " in out
    assert "set a longer recovery.ttl (for example 2s) in release rel's values file and roll it out" in out
    assert "set recovery.enabled: false in release rel's values file and roll it out" in out
    assert not [word for word in NOT_IN_THE_LOG if word in out.lower()], out
    last = out.splitlines()[-1]
    assert STAMP.match(last) and "TTL 1s reached" in last and "recovery.ttl" in last and "recovery.enabled: false" in last


def test_t303_11_sigterm_stops_it_at_once_through_its_own_handler(tmp_path):
    proc = _start(_env(tmp_path, "1h"))
    try:
        assert "TTL 1h: ends " in _banner(proc)[3]
        sent = time.monotonic()
        proc.send_signal(signal.SIGTERM)
        out, _ = proc.communicate(timeout=5)
        took = time.monotonic() - sent
    finally:
        proc.kill()
    # Exit 0 with the line, not -15: the default action would also end a child at once, so only the
    # handler's own exit proves the handler is installed, which is what a namespace's PID 1 needs.
    assert proc.returncode == 0 and took < 1.0, (proc.returncode, took)
    assert "SIGTERM: stopping (exit 0)" in out.splitlines()[-1]


def test_t303_12_every_import_is_from_the_standard_library():
    tree = ast.parse(SCRIPT.read_text(), feature_version=(3, 11))
    roots = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    roots |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert roots and roots <= set(sys.stdlib_module_names) | {"__future__"}, sorted(roots - set(sys.stdlib_module_names))
    assert not {"gsd", "sqlite3"} & roots


def test_the_ttl_survives_a_container_restart_and_an_expired_one_exits_at_once(tmp_path):
    """The kubelet restarts an exited container in the same pod at once and resets its back-off after
    ten minutes of running, so a TTL counted from each start would never end. The pod's /tmp (an
    emptyDir) outlives the container: the deadline kept there holds across restarts, and after it
    every start exits 1 at once, which is what keeps the pod in CrashLoopBackOff."""
    env = _env(tmp_path, "2s")
    first = _start(env)
    try:
        banner = _banner(first)
        first.send_signal(signal.SIGTERM)
        first.communicate(timeout=5)
    finally:
        first.kill()
    state = json.loads((tmp_path / "gsd-recovery.json").read_text())
    assert f"ends {state['deadline']}," in banner[3] and state["ttl"] == "2s"
    second = _start(env)                                    # a restarted container, the same pod's /tmp
    try:
        again = _banner(second)
    finally:
        second.kill()
        second.communicate()
    ends_again = datetime.fromisoformat(re.search(r"ends (\S+),", again[3]).group(1)).timestamp()
    assert abs(ends_again - state["deadline_epoch"]) <= 1.0, (again, state)
    assert f"kept from this pod's first start at {state['started']}" in again[3], again
    time.sleep(max(0.0, state["deadline_epoch"] - time.time()) + 0.2)
    third, took = _run(env)
    assert third.returncode == 1 and took < 1.0, (third.returncode, took)
    assert "0s left (kept from this pod's first start" in third.stdout and "TTL 2s reached" in third.stdout.splitlines()[-1]


def _record(tmp_path: pathlib.Path, **fields) -> None:
    """A deadline record as the script writes it, on this machine's clocks, with `fields` replaced."""
    module = _module()
    now, mono = time.time(), time.monotonic()
    record = {"ttl": "1h", "started": module.instant(now), "started_epoch": now, "deadline": module.instant(now + 3600),
              "deadline_epoch": now + 3600, "deadline_monotonic": mono + 3600, "boot_id": module.boot_id()}
    record.update(fields)
    (tmp_path / "gsd-recovery.json").write_text(json.dumps(record))


def test_a_backward_wall_clock_step_cannot_lengthen_the_ttl(tmp_path):
    """Codex F1: the time left came from the wall clock, so setting it back gave the pod more time. It now
    comes from the node's monotonic clock: a record whose wall-clock deadline is an hour away but whose
    monotonic deadline has passed is expired at once, and the arithmetic never returns more than the TTL."""
    module = _module()
    record, kept = module.deadline(tmp_path / "state.json", 60.0, "1m", wall=1000.0, monotonic=5000.0, boot="b")
    assert not kept and module.remaining(record, 60.0, 5010.0, "b") == 50.0    # 10 s on: 50 s left, whatever the wall says
    assert module.remaining({**record, "deadline_monotonic": 9999.0}, 60.0, 5010.0, "b") == 60.0
    _record(tmp_path, deadline_monotonic=time.monotonic() - 1)
    done, took = _run(_env(tmp_path, "1h"))
    assert done.returncode == 1 and took < 1.5 and "TTL 1h reached" in done.stdout.splitlines()[-1], done.stdout


def test_a_node_restart_under_the_pod_counts_as_the_ttl_reached(tmp_path):
    _record(tmp_path, boot_id="a-boot-that-is-not-this-one")
    done, took = _run(_env(tmp_path, "1h"))
    assert done.returncode == 1 and took < 1.5, (done.returncode, took)
    assert "the node restarted since this pod's first start" in done.stdout


def test_the_suggested_ttl_is_a_positive_duration_for_a_subsecond_ttl(tmp_path):
    """Codex: a 250ms TTL suggested `0s`, which the chart refuses."""
    done, _ = _run(_env(tmp_path, "250ms"))
    assert done.returncode == 1 and "set a longer recovery.ttl (for example 1s)" in done.stdout


@pytest.mark.parametrize("ttl", ["", "abc", "0s", "-5m", "7200"])
def test_a_ttl_that_is_not_a_positive_duration_exits_2(tmp_path, ttl):
    done, _ = _run(_env(tmp_path, ttl))
    assert done.returncode == 2 and "is not a positive Go duration" in done.stdout
    assert not (tmp_path / "gsd-recovery.json").exists()


@pytest.mark.parametrize("bad", ["{not json", json.dumps({"deadline_epoch": 1.0, "started_epoch": 1.0, "boot_id": ""}),
                                 json.dumps({"deadline_epoch": 1.0, "started_epoch": 1.0, "deadline_monotonic": "NaN",
                                             "boot_id": ""})], ids=["not-json", "no-monotonic-deadline", "nan"])
def test_a_deadline_file_that_cannot_be_read_exits_2_rather_than_restart_the_clock(tmp_path, bad):
    (tmp_path / "gsd-recovery.json").write_text(bad)
    done, _ = _run(_env(tmp_path, "1h"))
    assert done.returncode == 2 and "cannot be used" in done.stdout and "Delete the pod" in done.stdout
    assert (tmp_path / "gsd-recovery.json").read_text() == bad


def test_the_duration_grammar_and_the_printed_spans():
    module = _module()
    assert [module.ttl_seconds(t) for t in ("2h", "90m", "1h30m", "1.5s", "250ms")] == [7200, 5400, 5400, 1.5, 0.25]
    assert [module.ttl_seconds(t) for t in ("", "0", "abc", "-5m", "7200", "2H", "1 h")] == [None] * 7
    assert module.ttl_seconds("0s") == 0
    assert [module.span(s) for s in (7200, 5400, 5399.6, 59, 0.4)] == ["2h", "1h30m", "1h30m", "59s", "0s"]
