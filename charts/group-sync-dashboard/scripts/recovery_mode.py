#!/usr/bin/env python3
"""Recovery mode (#303): the dashboard pod with its data volume mounted and the app stopped.

The chart runs this instead of uvicorn while `recovery.enabled` is true. It ships in a ConfigMap
(templates/recovery.yaml), not in the image, so it runs under any image with python3.14: the older
image a rollback targets has no recovery code of its own. Standard library only. It never imports
gsd or sqlite3 and opens nothing under the data directory, so no process holds gsd.db while an
operator restores it.

It prints what the pod is, then the time left every --report-every seconds, and exits 1 at the
TTL so the pod reads CrashLoopBackOff, saying how to extend recovery mode or leave it: a change to
the release's values file, rolled out through the release's deployment pipeline. As the container's
PID 1, its exit at the TTL also ends every process in the container, an `oc exec` restore included.

The deadline is kept in $TMPDIR (the pod's /tmp, an emptyDir), because the kubelet restarts an
exited container in the same pod at once and resets its back-off after ten minutes of running: a
TTL counted from each start would sleep another full TTL after every expiry. The emptyDir survives
a container restart and goes with the pod, so a new pod (a new recovery.ttl, a deleted or evicted
pod) starts a new TTL. The time left is measured on the node's monotonic clock, which a change of the
wall clock does not move and a container restart does not reset; after a node restart it cannot be
measured, so the TTL counts as reached. #302's restore wrapper reads the same file.

Exit status: 0 on SIGTERM, 1 at the TTL, 2 when the TTL or the deadline file cannot be used.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import select
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

#: The file under $TMPDIR (default /tmp) that keeps this pod's deadline across container restarts.
STATE_NAME = "gsd-recovery.json"
#: Generated once per boot of the node (random(4)); CLOCK_MONOTONIC counts from that boot (clock_gettime(2)).
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
#: Seconds between two "time left" lines.
REPORT_EVERY = 1800.0
#: The Go duration grammar of the chart's gsd.durationSeconds helper (templates/_helpers.tpl), so
#: the script accepts exactly what the render accepted. \u00b5 is the micro sign Go also accepts.
_DURATION = re.compile("(?:[0-9]+(?:\\.[0-9]+)?(?:ns|us|\u00b5s|ms|s|m|h))+")
_TOKEN = re.compile("([0-9]+(?:\\.[0-9]+)?)(ns|us|\u00b5s|ms|s|m|h)")
_UNIT = {"ns": 1e-9, "us": 1e-6, "\u00b5s": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}
_IDLE = "the app is NOT running and no data is collected"


class _Stop(Exception):
    """SIGTERM arrived. Raised from the handler so a wait ends at once."""


def _on_sigterm(signum: int, frame: object) -> None:
    # A handler of our own, not the default: as the container's PID 1 the process receives only
    # the signals it has a handler for (pid_namespaces(7)), and Python installs none for SIGTERM,
    # so without this the kubelet would wait out the whole grace period and then SIGKILL.
    raise _Stop


def ttl_seconds(text: str) -> float | None:
    """A Go duration as seconds (`2h`, `90m`, `1h30m`, `1.5s`), or None when the text is not one."""
    if not _DURATION.fullmatch(text):
        return None
    return sum(float(number) * _UNIT[unit] for number, unit in _TOKEN.findall(text))


def span(seconds: float) -> str:
    """Whole seconds as a compact Go duration (`2h`, `1h30m`, `45s`), valid as a recovery.ttl."""
    total = max(0, int(round(seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    text = (f"{hours}h" if hours else "") + (f"{minutes}m" if minutes else "") + (f"{secs}s" if secs else "")
    return text or "0s"


def instant(epoch: float) -> str:
    """ISO-8601 UTC to the second."""
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def say(message: str) -> None:
    print(f"{instant(time.time())} gsd-recovery {message}", flush=True)


def boot_id() -> str:
    """The node's boot ID; empty where there is none (a development machine that is not Linux)."""
    try:
        return BOOT_ID.read_text().strip()
    except OSError:
        return ""


def deadline(state: Path, ttl: float, ttl_text: str, wall: float, monotonic: float, boot: str) -> tuple[dict, bool]:
    """This pod's deadline record, and whether an earlier start in the pod wrote it.

    The first start writes it (to a temporary name, then renamed, so a kill mid-write leaves no
    half file); every later start in the same pod reads it back unchanged. A record that lacks a
    field is refused (KeyError, ValueError) rather than replaced, so a bad file never restarts the
    clock."""
    try:
        kept = json.loads(state.read_text())
        for key in ("started_epoch", "deadline_epoch", "deadline_monotonic"):
            if not math.isfinite(float(kept[key])):
                raise ValueError(f"{key} is not a finite number")
        instant(float(kept["started_epoch"]))  # a finite epoch that is no instant is refused here, not as a traceback from the banner
        str(kept["boot_id"])
        return kept, True
    except FileNotFoundError:
        pass
    record = {"ttl": ttl_text, "started": instant(wall), "started_epoch": wall,
              "deadline": instant(wall + ttl), "deadline_epoch": wall + ttl,
              "deadline_monotonic": monotonic + ttl, "boot_id": boot}
    partial = state.with_name(state.name + ".tmp")
    partial.write_text(json.dumps(record) + "\n")
    os.replace(partial, state)
    return record, False


def remaining(record: dict, ttl: float, monotonic: float, boot: str) -> float:
    """Seconds left, on the node's monotonic clock, never more than the TTL.

    The wall clock is not read: a step of it backwards would lengthen the TTL (review of the spec,
    Codex F1). CLOCK_MONOTONIC is system-wide and counts from the node's boot, so it runs on across
    container restarts; a different boot ID means the node restarted under the pod and the time
    left cannot be measured, which counts as reached."""
    if str(record["boot_id"]) != boot:
        return 0.0
    return min(float(record["deadline_monotonic"]) - monotonic, ttl)


def _expired(ttl_text: str, ttl: float, release: str, db: str, rebooted: bool) -> None:
    # The values file, rolled out through the release's own pipeline, is the one way recovery mode changes
    # (the operator, 2026-10-01): no Helm or Argo CD command line, which an estate's pipeline owns.
    longer = span(max(2 * ttl, 1.0))
    if rebooted:
        say("the node restarted since this pod's first start, so the time left cannot be measured; the TTL counts as reached")
    say(f"TTL {ttl_text} reached at {instant(time.time())}; exiting 1: the app is still NOT running and no data is collected")
    say(f"to extend: set a longer recovery.ttl (for example {longer}) in release {release}'s values file and roll it"
        f" out through its deployment pipeline; the new pod counts it from its start")
    say(f"to leave: set recovery.enabled: false in release {release}'s values file and roll it out; the app starts on {db}")
    say(f"TTL {ttl_text} reached; exiting 1. Extend with recovery.ttl, leave with recovery.enabled: false, in the"
        f" release's values file (lines above)")


def run(args: argparse.Namespace, wakeup_fd: int) -> int:
    ttl_text = os.environ.get("GSD_RECOVERY_MODE_TTL", "")
    ttl = ttl_seconds(ttl_text)
    if not ttl:
        say(f"GSD_RECOVERY_MODE_TTL {ttl_text!r} is not a positive Go duration such as 2h, 90m or 1h30m; exiting 2")
        return 2
    state = Path(os.environ.get("TMPDIR") or "/tmp") / STATE_NAME
    boot = boot_id()
    try:
        record, kept = deadline(state, ttl, ttl_text, time.time(), time.monotonic(), boot)
        left = remaining(record, ttl, time.monotonic(), boot)
    except (OSError, OverflowError, ValueError, KeyError, TypeError) as exc:
        say(f"the deadline file {state} cannot be used ({type(exc).__name__}: {exc}), so the TTL could not be kept;"
            f" exiting 2. Delete the pod to start a new one with a new TTL")
        return 2
    db = os.environ.get("GSD_DB_PATH", "/data/gsd.db")
    say(f"RECOVERY MODE (GSD_RECOVERY_MODE={os.environ.get('GSD_RECOVERY_MODE', '')}, GSD_RECOVERY_MODE_TTL={ttl_text})")
    say(_IDLE)
    say(f"data path {db} (not opened by this process)")
    since = f" (kept from this pod's first start at {instant(float(record['started_epoch']))}; the container restarted)" if kept else ""
    say(f"TTL {ttl_text}: ends {instant(time.time() + max(left, 0.0))}, {span(left)} left{since}")
    say("check the time left before a restore: at the TTL this process exits and every process in the container"
        " stops with it")
    while True:
        left = remaining(record, ttl, time.monotonic(), boot)
        if left <= 0:
            _expired(ttl_text, ttl, args.release, db, str(record["boot_id"]) != boot)
            return 1
        # #555: a signal arriving before the wait leaves a byte, so the wait cannot miss it.
        select.select([wakeup_fd], [], [], min(left, args.report_every))
        left = remaining(record, ttl, time.monotonic(), boot)
        if left > 0:
            say(f"{span(left)} left; {_IDLE}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recovery mode (#303): hold the pod with the app stopped until the TTL.")
    parser.add_argument("--release", default="group-sync-dashboard", help="the release whose values file the TTL lines name")
    parser.add_argument("--report-every", type=float, default=REPORT_EVERY, help="seconds between two 'time left' lines")
    args = parser.parse_args(argv)
    read_fd, write_fd = os.pipe()
    os.set_blocking(write_fd, False)
    previous_wakeup_fd = signal.set_wakeup_fd(write_fd)
    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
        return run(args, read_fd)
    except _Stop:
        say("SIGTERM: stopping (exit 0); the app was not running")
        return 0
    finally:
        signal.set_wakeup_fd(previous_wakeup_fd)
        os.close(read_fd)
        os.close(write_fd)


if __name__ == "__main__":
    sys.exit(main())
