#!/usr/bin/env python3
"""The helper restore-db.sh runs (#302): list the database copies the recovery pod can restore, and restore one.

Not shipped in the image. restore-db.sh streams this file into the release's recovery pod (#303) over
`oc exec -i ... python3.14 /dev/stdin`, so it runs under whatever image that pod runs, the older one a rollback
targets included, and that image's own gsd.store says which schema it understands. Standard library only, apart
from gsd.store (KNOWN_SCHEMA_VERSION) and the yaml the image reads its configuration with, both imported in the
pod only. Every file operation happens here, in Python: the image has no cp, mv or sha256sum.

    preflight     on the laptop, from `oc get pods -o json` on stdin: the release's one pod, in recovery mode,
                  with at least MARGIN_SECONDS of its TTL left. Prints "<pod>\\t<image>\\t<time left>".
    list          in the pod: one row per restorable copy (backup, pre-upgrade, offsite) and its ID.
    check ID      in the pod: every check on one copy, what restoring it would discard, and a confirmation line
                  (the copy's sha256 and size, the live set's fingerprint). Writes nothing.
    restore ID    in the pod: the TTL left as SPEC_E2 counts it; the checks again, and with --expected-* the very
                  copy and live set the check showed; the copy written beside the live file under a temporary
                  name and checked there; the live set kept under pre-restore/<stamp>/; the old file made whole
                  and its -wal, -shm and -journal removed; the copy renamed onto it.

One helper operation runs in the pod at a time (list, check and restore all take the same lock).

Exit status: 0 done; 1 failed (the message says what was and was not changed); 2 refused because the pod is
not ready for a restore (not in recovery mode, uvicorn running, another operation running, too little TTL left);
3 refused because of the copy (an unknown ID, twins that differ, a schema newer than this image, a sidecar that
does not match, integrity_check, a copy or a live set other than the ones the check showed). Nothing is written before every
check has passed.

docs/specs/SPEC_E3_restore_db.md is the design; charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md, section 4, the manual fallback.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

#: Refuse a restore with less than this much of the recovery TTL left. At the TTL the recovery container exits
#: and ends every `oc exec` session in it, a restore's included. The whole restore of the lab's 14 MB database
#: is seconds under the lab's emulation; ten minutes covers a database about a hundred times larger (SPEC_E3 §2.11).
MARGIN_SECONDS = 600.0
#: The history tables a restore can lose rows from: the store's own Store._HISTORY_TABLES and login_event, which
#: it prunes on its own. Every id is AUTOINCREMENT, so an id above the copy's highest is a row inserted after the
#: copy was taken (tests/test_restore_db.py holds this list against the store's).
HISTORY = ("membership_event", "sync_event", "binding_event", "kyverno_result_event", "login_event")
#: One `sha256sum -c` line, parsed exactly as charts/group-sync-dashboard/scripts/offsite_backup.py parses it
#: (tests/test_restore_db.py holds the two equal).
SIDECAR_LINE = re.compile(r"([0-9A-Fa-f]{64})[ \t]+(.+?)\r?\n?")
SUM_SUFFIX = ".sha256"
#: Store._vacuum_into's gsd-<stamp>.db. Anything after the stamp is accepted, so a name that also carries a pod
#: still lists; the stamp is the copy's own, microseconds included, because two copies can share a second.
BACKUP_NAME = re.compile(r"gsd-(\d{8}T\d{6}\.\d{6}Z)(?:-[^/]+)?\.db")
#: _pre_upgrade_copy's pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db.
PRE_UPGRADE_NAME = re.compile(r"pre-upgrade-(\d{8}T\d{6}\.\d{6}Z)-schema-\d+-to-(\d+)-.+\.db")
#: The files SQLite keeps beside a database. A -wal or a hot -journal holds committed rows of the file it
#: belongs to, and one left beside another file is replayed into that file.
SIDE_FILES = ("-wal", "-shm", "-journal")
#: Where copies come from, in the order a byte-identical twin is read from.
SOURCES = ("backup", "pre-upgrade", "offsite")
#: SPEC_E2's record of this pod's TTL, in the pod's /tmp, and where the node's boot ID it is counted on is read.
RECOVERY_STATE = "gsd-recovery.json"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
CHUNK = 1 << 20
MIB = 1048576
EXIT_FAILED, EXIT_POD, EXIT_COPY = 1, 2, 3
#: The Go duration grammar of the chart's gsd.durationSeconds helper, which recovery.ttl is written in.
_DURATION = re.compile("(?:[0-9]+(?:\\.[0-9]+)?(?:ns|us|µs|ms|s|m|h))+")
_TOKEN = re.compile("([0-9]+(?:\\.[0-9]+)?)(ns|us|µs|ms|s|m|h)")
_UNIT = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}


class Refused(Exception):
    """A refusal or a failure the operator must read, with its exit status."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def say(line: str = "", stream=None) -> None:
    """Print, and never let a closed stream stop the work. When the oc session drops, the process in the pod
    goes on (measured on the lab), and a failed print must not abort a restore between two of its steps."""
    try:
        print(line, file=stream or sys.stdout, flush=True)
    except OSError:
        pass


def ttl_seconds(text: str) -> float | None:
    """A Go duration as seconds (`2h`, `90m`, `1h30m`), or None when the text is not one."""
    if not _DURATION.fullmatch(text):
        return None
    return sum(float(number) * _UNIT[unit] for number, unit in _TOKEN.findall(text))


def span(seconds: float) -> str:
    """Whole seconds as a compact Go duration (`2h`, `1h30m`, `45s`)."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return ((f"{hours}h" if hours else "") + (f"{minutes}m" if minutes else "") + (f"{secs}s" if secs else "")) or "0s"


def utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_epoch(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


# ---------------------------------------------------------------------------------------------------------------
# preflight: on the laptop, from the pod spec alone (no exec)
# ---------------------------------------------------------------------------------------------------------------

def _values_hint(change: str) -> str:
    return (f"  Set {change} in this release's values file and roll it out through the release's deployment "
            "pipeline (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md, section 4). Not with oc set env: recovery mode is the chart's "
            "recovery.enabled, and a hand edit of the Deployment is not it.")


def preflight(doc: dict, release: str, namespace: str, now: float, margin: float = MARGIN_SECONDS) -> tuple[str, str, float]:
    """The release's one pod, its image, and how much of its recovery TTL is left at least; or a refusal.

    The TTL is counted from the pod's first container start and kept across container restarts (#303), so
    the deadline is bounded with the pod's status.startTime, which the kubelet sets before it pulls the image
    and therefore never after that first start: the time left printed is never more than the pod has."""
    pods = doc.get("items") or []
    names = [p["metadata"]["name"] for p in pods]
    if len(pods) != 1:
        raise Refused(EXIT_POD, f"{len(pods)} pods match app={release} or app={release}-recovery in {namespace} "
                                f"({', '.join(names) or 'none'}); "
                                "a restore needs exactly one, the release's recovery pod. Wait until one is left "
                                "(a terminating pod still counts), then run this again")
    pod, name = pods[0], names[0]
    spec = next((c for c in pod["spec"]["containers"] if c["name"] == "dashboard"), {})
    env = {e["name"]: e.get("value") for e in spec.get("env") or []}
    if env.get("GSD_RECOVERY_MODE") != "true":
        raise Refused(EXIT_POD, f"pod {name} is not in recovery mode: its dashboard container has no "
                                "GSD_RECOVERY_MODE=true, so the dashboard may be writing the database.\n"
                                + _values_hint("recovery.enabled: true and recovery.ttl: 2h"))
    status = pod.get("status") or {}
    state = next((s.get("state") or {} for s in status.get("containerStatuses") or [] if s["name"] == "dashboard"), {})
    longer = "a longer recovery.ttl (a new pod, with a new TTL)"
    if "running" not in state:
        raise Refused(EXIT_POD, f"pod {name}: the dashboard container is not running ({', '.join(state) or 'no status yet'}). "
                                "At the TTL recovery mode exits and the pod reads CrashLoopBackOff.\n"
                                + _values_hint(longer))
    ttl_text = env.get("GSD_RECOVERY_MODE_TTL") or ""
    ttl = ttl_seconds(ttl_text)
    started = status.get("startTime")
    if not ttl or not started:
        raise Refused(EXIT_POD, f"pod {name}: its recovery TTL ({ttl_text!r}) or its start time ({started!r}) cannot be "
                                "read, so the time left cannot be known")
    left = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() + ttl - now
    if left < margin:
        raise Refused(EXIT_POD, f"pod {name}: at most {span(left)} of recovery.ttl {ttl_text} is left, less than the "
                                f"{span(margin)} a restore keeps in hand: at the TTL the container exits and ends every "
                                "oc exec in it.\n" + _values_hint(longer))
    return name, spec.get("image") or "unknown", left


# ---------------------------------------------------------------------------------------------------------------
# in the pod
# ---------------------------------------------------------------------------------------------------------------

def in_recovery(proc: Path) -> None:
    """This container is the recovery pod's and nothing in it serves: GSD_RECOVERY_MODE (#303) and no uvicorn.
    Every process's argv is read, because PID 1 is not always the program: on the lab's arm64 node it is
    qemu-x86_64-static running python3.14."""
    if os.environ.get("GSD_RECOVERY_MODE") != "true":
        raise Refused(EXIT_POD, "GSD_RECOVERY_MODE is not true in this container, so it is not the recovery pod (#303)")
    if not proc.is_dir():
        raise Refused(EXIT_POD, f"{proc} cannot be read, so whether uvicorn runs here cannot be told")
    for cmdline in sorted(proc.glob("[0-9]*/cmdline")):
        try:
            argv = cmdline.read_bytes().split(b"\0")
        except OSError:
            continue                                # a process that ended while the list was read
        if any(arg == b"uvicorn" or arg.endswith(b"/uvicorn") for arg in argv):
            raise Refused(EXIT_POD, f"uvicorn is running here (pid {cmdline.parent.name}): the dashboard may be "
                                    "writing the database")


def known_schema() -> int:
    """The schema this pod's image understands: KNOWN_SCHEMA_VERSION (#305), or, in an image older than it,
    the same maximum read from _MIGRATIONS."""
    try:
        import gsd.store as store
    except ImportError as exc:
        raise Refused(EXIT_POD, f"gsd.store cannot be imported here ({exc}): this is not a dashboard image") from exc
    known = getattr(store, "KNOWN_SCHEMA_VERSION", None)
    return int(known if known is not None else max(migration[0] for migration in store._MIGRATIONS))


def config_backup_dir() -> str:
    """config.backup.dir as the app reads it (gsd/config.py): GSD_BACKUP_DIR, else backupDir in GSD_CONFIG."""
    if os.environ.get("GSD_BACKUP_DIR"):
        return os.environ["GSD_BACKUP_DIR"]
    path = Path(os.environ.get("GSD_CONFIG") or "/etc/gsd/clusters.yaml")
    if not path.is_file():
        return ""
    import yaml                                     # the image's: gsd reads its configuration with it
    raw = yaml.safe_load(path.read_text()) or {}
    return str(raw.get("backupDir") or "") if isinstance(raw, dict) else ""


class Layout:
    """Where the live database and every source of copies are, in this pod."""

    def __init__(self, offsite: Path) -> None:
        self.db = Path(os.environ.get("GSD_DB_PATH") or "/data/gsd.db")
        backup = config_backup_dir()
        self.backup = Path(backup) if backup else None
        self.pre_upgrade = self.db.parent / "pre-upgrade"
        self.pre_restore = self.db.parent / "pre-restore"
        self.offsite = offsite
        self.lock = Path(os.environ.get("TMPDIR") or "/tmp") / "gsd-restore.lock"
        self.state = Path(os.environ.get("TMPDIR") or "/tmp") / RECOVERY_STATE
        self.tmp = self.db.with_name(self.db.name + ".restore.tmp")

    def live_set(self) -> list[Path]:
        return [p for p in (self.db, *(Path(f"{self.db}{s}") for s in SIDE_FILES)) if p.is_file()]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def live_fingerprint(lay: Layout) -> str:
    """The live set's content: each of gsd.db, -wal and -journal that exists, by name, size and bytes. Not -shm,
    the index SQLite rewrites on any open, even a read-only one (§2.2)."""
    digest = hashlib.sha256()
    for path in lay.live_set():
        if path.name.endswith("-shm"):
            continue
        digest.update(f"{path.name}\0{path.stat().st_size}\0".encode())
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
    return digest.hexdigest()


def sidecar_expected(sidecar: Path, name: str) -> str | None:
    """The digest a `sha256sum -c` sidecar records for `name`, or None when it is empty, unreadable, malformed
    or names another file: offsite_backup.py's sidecar_expected, line for line, apart from an unreadable file."""
    try:
        text = sidecar.read_text()
    except OSError:
        return None
    match = SIDECAR_LINE.fullmatch(text)
    if match is None or match.group(2) != name:
        return None
    return match.group(1).lower()


def schema_of(path: Path) -> int | None:
    """A copy's user_version, read from its header: the 4-byte big-endian integer at offset 60 that PRAGMA
    user_version reads and sets (sqlite.org/fileformat2.html). From the header, so a damaged copy still gets its
    ID and is refused by integrity_check by name; None when the file does not start with the SQLite header.
    Right for a copy only: no -wal belongs to a copy, while a live file's -wal may hold a newer page 1."""
    try:
        with path.open("rb") as fh:
            header = fh.read(64)
    except OSError:
        return None
    if len(header) < 64 or not header.startswith(b"SQLite format 3\x00"):
        return None
    return int.from_bytes(header[60:64], "big")


def integrity(path: Path) -> str:
    """'ok', or what PRAGMA integrity_check (or the open) said instead."""
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?immutable=1&mode=ro", uri=True)
        try:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"cannot be checked: {exc}"


def history(conn: sqlite3.Connection) -> dict[str, tuple[int, int] | None]:
    """(rows, highest id) per history table; None for a table this database does not have."""
    out: dict[str, tuple[int, int] | None] = {}
    for table in HISTORY:
        try:
            count, highest = conn.execute(f"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM {table}").fetchone()
            out[table] = (int(count), int(highest))
        except sqlite3.Error:
            out[table] = None
    return out


class Row:
    """One ID: one copy, or the same name under two sources (the offsite job keeps a backup's name)."""

    def __init__(self, rid: str, entries: list[tuple[str, Path]]) -> None:
        self.id = rid
        self.entries = sorted(entries, key=lambda e: (SOURCES.index(e[0]), str(e[1])))
        head, self.stamp = rid.split("-", 1)
        self.schema = None if head == "?" else int(head)
        self.path = self.entries[0][1]
        self._digests: dict[Path, str] = {}

    @property
    def sources(self) -> str:
        return "+".join(dict.fromkeys(source for source, _ in self.entries))

    def digest(self, path: Path) -> str:
        if path not in self._digests:
            self._digests[path] = sha256_of(path)
        return self._digests[path]

    def differ(self) -> bool:
        return len({self.digest(path) for _, path in self.entries}) > 1

    def sidecar(self) -> tuple[str, str]:
        """ok / mismatch / none, and why. Twins are byte-identical, so one matching sidecar verifies both."""
        verdicts = []
        for _, path in self.entries:
            side = path.with_name(path.name + SUM_SUFFIX)
            if not side.exists():
                continue
            expected = sidecar_expected(side, path.name)
            if expected is None:
                verdicts.append(("mismatch", f"{side} is empty, malformed or names another file"))
            elif expected != self.digest(path):
                verdicts.append(("mismatch", f"{path} has sha256 {self.digest(path)}; its sidecar says {expected}"))
            else:
                verdicts.append(("ok", f"{side} matches"))
        for word in ("mismatch", "ok"):
            for verdict in verdicts:
                if verdict[0] == word:
                    return verdict
        return "none", "no .sha256 beside it (scheduled backups write none), so integrity_check is its only check"


def catalogue(lay: Layout) -> dict[str, Row]:
    """Every restorable copy, by ID: <user_version>-<the copy's own stamp>. Copies are only ever read here."""
    found: dict[str, list[tuple[str, Path]]] = {}

    def scan(source: str, paths) -> None:
        for path in sorted(paths):
            match = BACKUP_NAME.fullmatch(path.name) or PRE_UPGRADE_NAME.fullmatch(path.name)
            if match and path.is_file():
                schema = schema_of(path)
                found.setdefault(f"{'?' if schema is None else schema}-{match.group(1)}", []).append((source, path))

    if lay.backup is not None and lay.backup.is_dir():
        scan("backup", lay.backup.glob("gsd-*.db"))
    if lay.pre_upgrade.is_dir():
        scan("pre-upgrade", lay.pre_upgrade.glob("pre-upgrade-*.db"))
    if lay.offsite.is_dir():
        scan("offsite", lay.offsite.rglob("*.db"))
    return {rid: Row(rid, entries) for rid, entries in found.items()}


def understood(schema: int | None, known: int) -> str:
    if schema is None:
        return "no (not a database)"
    if schema > known:
        return f"no ({schema} > {known})"
    return "yes" if schema == known else f"yes, migrates {schema} -> {known} on start"


def live_version(db: Path) -> int | None:
    """The live database's user_version, read through SQLite so a -wal is seen; it changes nothing but the
    -shm index SQLite rebuilds on any open (measured, SPEC_E3 §2.2)."""
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def aside_notes(lay: Layout, known: int) -> list[str]:
    """Runbook §6: a pre-upgrade copy taken for a schema this image does not understand makes a retried upgrade
    take no copy of what this image writes from now on. Said, never done: this script moves nothing."""
    notes = []
    for path in sorted(lay.pre_upgrade.glob("pre-upgrade-*.db")) if lay.pre_upgrade.is_dir() else []:
        match = PRE_UPGRADE_NAME.fullmatch(path.name)
        if match and int(match.group(2)) > known:
            notes.append(f"note: {path} was taken before an upgrade to schema {match.group(2)}, which this image does "
                         f"not understand. Before that upgrade is tried again, move it and its {SUM_SUFFIX} out of "
                         f"{lay.pre_upgrade} (to {lay.pre_restore}/, for example), or the new attempt finds it and takes "
                         "no copy of what this image writes from now on (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md, section 6). "
                         "This script moves nothing.")
    return notes


def cmd_list(lay: Layout, known: int) -> int:
    rows = sorted(catalogue(lay).values(), key=lambda r: (r.stamp, r.id), reverse=True)
    live = live_version(lay.db)
    say(f"image    understands schema {known} and older")
    say(f"live     {lay.db} · " + ("absent" if not lay.db.is_file() else
                                   "unreadable" if live is None else f"user_version {live}"))
    say(f"{'ID':<28}{'SCHEMA':<8}{'STAMP (UTC)':<22}{'SIZE':>11}  {'SOURCE':<20}{'SIDECAR':<10}THIS IMAGE")
    notes = []
    for row in rows:
        size = row.path.stat().st_size / MIB
        sidecar = row.sidecar()[0]
        if row.differ():
            notes.append(f"# {row.id}: " + " and ".join(f"{p} (sha256 {row.digest(p)})" for _, p in row.entries)
                         + " differ; --from-version refuses this ID")
        schema = "?" if row.schema is None else str(row.schema)
        # SOURCE is 20 wide: "pre-upgrade+offsite", a pre-upgrade copy #304 has shipped, is 19.
        say(f"{row.id:<28}{schema:<8}{utc(stamp_epoch(row.stamp)):<22}{size:>7.2f} MiB  {row.sources:<20}"
            f"{sidecar:<10}{understood(row.schema, known)}")
    say(f"# {len(rows)} candidates. none: no .sha256 beside it (scheduled backups write none), so integrity_check is "
        "its only check. mismatch: --from-version refuses it.")
    if lay.backup is None:
        say("# backup: config.backup is off (no backupDir), so there are no scheduled backups to list")
    if not lay.offsite.is_dir():
        say(f"# offsite: {lay.offsite} is not mounted in this pod. The chart's recovery pod mounts the offsite claim, "
            "read-only, when backup.offsite uses its pvc destination; restore a copy that is only on that claim with "
            "charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md section 4b")
    for line in notes + aside_notes(lay, known):
        say(line)
    return 0


def checked(lay: Layout, rid: str, known: int) -> tuple[Row, str]:
    """The copy an ID names, and its sha256, once every check has passed; a refusal otherwise. Reads only."""
    rows = catalogue(lay)
    if rid not in rows:
        raise Refused(EXIT_COPY, f"no copy has the ID {rid}; run --list for the IDs")
    row = rows[rid]
    if row.differ():
        raise Refused(EXIT_COPY, f"{rid} names copies that differ: "
                                 + "; ".join(f"{p} (sha256 {row.digest(p)})" for _, p in row.entries)
                                 + ". Decide which one is right and restore it by hand (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md, "
                                 "section 4)")
    if row.schema is None:
        raise Refused(EXIT_COPY, f"{row.path} is not a database SQLite can open")
    if row.schema > known:
        better = sorted((r for r in rows.values() if r.schema is not None and r.schema <= known),
                        key=lambda r: r.stamp)
        hint = (f" The newest copy this image understands: --from-version {better[-1].id} (source {better[-1].sources})."
                if better else "")
        raise Refused(EXIT_COPY, f"{rid}: database schema {row.schema} is newer than this dashboard understands ({known}); "
                                 f"restore a copy at or below schema {known}, or run the image that understands "
                                 f"{row.schema}.{hint}")
    verdict, detail = row.sidecar()
    if verdict == "mismatch":
        raise Refused(EXIT_COPY, f"{rid}: {detail}")
    result = integrity(row.path)
    if result != "ok":
        raise Refused(EXIT_COPY, f"{rid}: {row.path}: integrity_check said {result!r}")
    return row, row.digest(row.path)


def cmd_check(lay: Layout, rid: str, known: int) -> int:
    row, digest = checked(lay, rid, known)
    now = time.time()
    copy = sqlite3.connect(f"file:{row.path.as_posix()}?immutable=1&mode=ro", uri=True)
    try:
        copied = history(copy)
    finally:
        copy.close()
    live_rows: dict[str, tuple[int, int] | None] = {table: None for table in HISTORY}
    live = live_version(lay.db)
    if live is not None:
        conn = sqlite3.connect(f"file:{lay.db.as_posix()}?mode=ro", uri=True)
        try:
            for table in HISTORY:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    after = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE id > ?",
                                         ((copied[table] or (0, 0))[1],)).fetchone()[0]
                    live_rows[table] = (int(count), int(after))
                except sqlite3.Error:
                    live_rows[table] = None
        finally:
            conn.close()
    live_word = "absent" if not lay.db.is_file() else "unreadable" if live is None else str(live)
    say(f"candidate    {row.path} · {row.path.stat().st_size / MIB:.2f} MiB · {row.sources}")
    say("integrity    ok  (PRAGMA integrity_check on the copy, opened immutable)")
    say(f"sidecar      {row.sidecar()[0]}: {row.sidecar()[1]}")
    say(f"schema       copy {row.schema} · live {live_word} · this image understands {known} and older")
    say(f"loss window  {utc(stamp_epoch(row.stamp))} -> {utc(now)} ({span(now - stamp_epoch(row.stamp))}): what the "
        "dashboard recorded since is discarded")
    say(f"             {'table':<22}{'live':>7}{'in copy':>10}{'discarded':>12}")
    for table in HISTORY:
        mine, theirs = live_rows[table], copied[table]
        say(f"             {table:<22}{'-' if mine is None else mine[0]:>7}{'-' if theirs is None else theirs[0]:>10}"
            f"{'-' if mine is None else mine[1]:>12}")
    say("             discarded is an estimate: the live rows with an id above the copy's highest. Not live minus "
        "copy (retention may have pruned rows the copy still has); after an earlier restore two branches of history "
        "can reuse ids, which no id count can tell apart.")
    say("             also rolled back, not counted: the current users, groups and bindings, the poll and login "
        "capture state, dashboard_user_activity, kpi_daily, report_run and the current Kyverno results. The first "
        "poll reads the clusters again; the activity, KPI and report records do not come back.")
    # restore-db.sh hands these to `restore`, which refuses a copy or a live set that changed in between.
    say(f"confirmation sha256={digest} size={row.path.stat().st_size} live-sha256={live_fingerprint(lay)}")
    for line in aside_notes(lay, known):
        say(line)
    return 0


@contextmanager
def operation_lock(lay: Layout, operation: str):
    """One helper operation in this pod at a time: a restore, and every --list or check, which open the live
    database read-only, a connection that must not be open while a restore folds and renames it. flock, so the
    kernel releases it when the process ends, however it ends: a restore whose oc session dropped holds it until it
    finishes, and a killed one leaves nothing held."""
    fd = os.open(lay.lock, os.O_RDWR | os.O_CREAT, 0o664)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = os.read(fd, 512).decode(errors="replace").strip() or "its start was not recorded yet"
            raise Refused(EXIT_POD, f"another restore or database inspection is running in this pod ({holder}). One "
                                    "runs at a time; a restore whose oc session dropped goes on until it ends. Run this "
                                    "again after it has")
        os.ftruncate(fd, 0)
        os.write(fd, f"started {utc(time.time())}, pid {os.getpid()}, {operation}\n".encode())
        yield
    finally:
        os.close(fd)


def recovery_left(lay: Layout) -> float:
    """Seconds of the recovery TTL left, counted as SPEC_E2's own script counts them: its deadline on the node's
    monotonic clock minus the clock now, while the node's boot ID is the one it recorded; 0 when it is not (the node
    restarted under the pod); never more than the TTL. A record that cannot be read leaves the time unknown."""
    try:
        record = json.loads(lay.state.read_text())
        deadline, recorded = float(record["deadline_monotonic"]), str(record["boot_id"])
        ttl = ttl_seconds(str(record["ttl"]))
        if not math.isfinite(deadline):             # SPEC_E2's deadline() refuses the same record
            raise ValueError(f"deadline_monotonic {deadline} is not a finite number")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refused(EXIT_POD, f"the recovery TTL cannot be read from {lay.state} ({type(exc).__name__}: {exc}), so "
                                "how long this container has before it exits is unknown; nothing was written")
    try:
        boot = BOOT_ID.read_text().strip()
    except OSError:
        boot = ""                                   # not Linux: E2 records an empty boot ID there too
    if recorded != boot:
        return 0.0
    left = deadline - time.monotonic()
    return min(left, ttl) if ttl else left


def share(path: Path, group: int) -> None:
    """chgrp 0 and chmod g=u, OpenShift's arbitrary-UID rule: the next pod may run as another UID in group 0."""
    os.chown(path, -1, group)
    mode = path.stat().st_mode & 0o7777
    os.chmod(path, (mode & ~0o070) | ((mode & 0o700) >> 3))


def fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_file(source: Path, target: Path) -> str:
    """Stream source to a new target, fsynced; the sha256 of the bytes written."""
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("xb") as writer:
        while chunk := reader.read(CHUNK):
            writer.write(chunk)
            digest.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest()


def keep(lay: Layout, live_set: list[Path], group: int) -> Path:
    """The live set as found, under pre-restore/<stamp>/: written as <stamp>.tmp/ and renamed when complete."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    final, partial = lay.pre_restore / stamp, lay.pre_restore / f"{stamp}.tmp"
    if not lay.pre_restore.is_dir():
        lay.pre_restore.mkdir()
        share(lay.pre_restore, group)
    partial.mkdir()
    share(partial, group)
    for path in live_set:
        copy_file(path, partial / path.name)
        share(partial / path.name, group)
    fsync_directory(partial)
    os.replace(partial, final)
    fsync_directory(lay.pre_restore)
    return final


def write(lay: Layout, row: Row, digest: str, known: int, group: int) -> None:
    """The copy beside the live file under a temporary name (a rename needs one filesystem), checked again there:
    the bytes written are the ones checked, and the snapshot itself has the schema and the integrity the checks
    saw, so a copy replaced between its header read and its hash never takes the live name. Its group and mode
    are set before it does."""
    written = copy_file(row.path, lay.tmp)
    if written != digest:
        raise OSError(f"{lay.tmp} holds sha256 {written}, but the copy checked had {digest}: it changed while it was read")
    schema = schema_of(lay.tmp)
    if schema is None or schema != row.schema or schema > known:
        raise Refused(EXIT_COPY, f"the copy written for {row.id} reads schema {schema}, but the checks saw "
                                 f"{row.schema} and this image understands {known}: it changed while it was read. "
                                 "Nothing in the live set changed")
    result = integrity(lay.tmp)
    if result != "ok":
        raise Refused(EXIT_COPY, f"the copy written for {row.id} failed integrity_check ({result!r}). Nothing in the "
                                 "live set changed")
    share(lay.tmp, group)


def fold(lay: Layout) -> list[str]:
    """Make the old file whole, then remove what SQLite keeps beside it. Opening and closing it is SQLite's own
    way to fold a -wal into the file and remove it, and to roll back a hot -journal; neither reads the schema, so
    a file a newer image wrote folds too. SQLite does neither, silently, while another process has the file open
    or when it cannot write it (measured, SPEC_E3 §2.1): a -wal or -journal that still holds bytes after the
    close was not folded, and removing it would take committed rows out of the live file, so the restore stops
    here with nothing removed. A file SQLite cannot open as a database is removed around: the set was kept first.
    A damaged file whose -wal holds page 1 is not that file: SQLite opens it through the -wal, and its close cannot
    write the -wal back (an explicit checkpoint says `database disk image is malformed`, SPEC_E3 §2.1), so it stops
    here as a held file does, and the message names that cause too."""
    if lay.db.is_file():
        unreadable = False
        try:
            conn = sqlite3.connect(lay.db)
            try:
                conn.execute("PRAGMA user_version").fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            pass                                    # locked, read-only, I/O: what is left beside it decides
        except sqlite3.DatabaseError:
            unreadable = True                       # not a database SQLite can open, or a corrupt one
        held = [side.name for side in (Path(f"{lay.db}-wal"), Path(f"{lay.db}-journal"))
                if side.is_file() and side.stat().st_size]
        if held and not unreadable:
            raise sqlite3.OperationalError(
                f"SQLite did not fold {' and '.join(held)} into {lay.db} when it closed it: another process has the "
                "database open (an oc exec session), the file cannot be written, or it is damaged so that SQLite cannot "
                "write the -wal back into it. Nothing beside it was removed. If nothing holds it and it can be written, "
                "it is damaged: restore over it by hand (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md, section 4a)")
    removed = []
    for suffix in SIDE_FILES:
        side = Path(f"{lay.db}{suffix}")
        if side.exists():
            side.unlink()
            removed.append(side.name)
    return removed


def cmd_restore(lay: Layout, rid: str, known: int, group: int, confirmed: tuple | None = None) -> int:
    with operation_lock(lay, f"restore {rid}"):
        left = recovery_left(lay)
        if left < MARGIN_SECONDS:
            raise Refused(EXIT_POD, f"{span(left)} of the recovery TTL is left in this pod, as SPEC_E2's script counts "
                                    f"it, less than the {span(MARGIN_SECONDS)} a restore keeps in hand: at the TTL the "
                                    "container exits and ends this session. Nothing was written.\n"
                                    + _values_hint("a longer recovery.ttl (a new pod, with a new TTL)"))
        row, digest = checked(lay, rid, known)
        if confirmed is not None:
            sha256, size, live_sha256 = confirmed
            if (digest, row.path.stat().st_size) != (sha256.lower(), size):
                raise Refused(EXIT_COPY, f"{rid} changed after the check you answered: it is now sha256 {digest}, "
                                         f"{row.path.stat().st_size} bytes; the check showed sha256 {sha256}, {size} "
                                         "bytes. Nothing was written; run this again to see the plan for it now")
            now = live_fingerprint(lay)
            if now != live_sha256.lower():
                raise Refused(EXIT_COPY, f"the live database set changed after the check you answered (live-sha256 "
                                         f"{now}, the check showed {live_sha256}), so what it said a restore discards "
                                         "no longer holds. Nothing was written; run this again to see the plan now")
        say(f"checked again  {rid}: schema {row.schema} (this image understands {known}), sidecar {row.sidecar()[0]}, "
            f"integrity_check ok; {span(left)} of the recovery TTL left")
        # No output from here to the swap: a closed stream must not stop the work between two steps.
        stage, kept, before, removed, live_set = "tidy", None, None, [], []
        try:
            # What a killed restore left: the temporary copy, and a keep that never finished. Neither is a copy.
            lay.tmp.unlink(missing_ok=True)
            for partial in lay.pre_restore.glob("*.tmp") if lay.pre_restore.is_dir() else []:
                shutil.rmtree(partial)
            live_set = lay.live_set()
            need = sum(p.stat().st_size for p in live_set) + row.path.stat().st_size
            free = shutil.disk_usage(lay.db.parent).free
            if free < need:
                raise Refused(EXIT_FAILED, f"free space {free / MIB:.1f} MiB on {lay.db.parent}, {need / MIB:.1f} MiB "
                                           "needed (the live set kept, and the copy written beside it); nothing was written")
            stage = "write"
            write(lay, row, digest, known, group)
            stage = "keep"
            kept = keep(lay, live_set, group) if live_set else None
            before = live_version(lay.db)
            stage = "fold"
            removed = fold(lay)
            stage = "swap"
            os.replace(lay.tmp, lay.db)
            stage = "sync"
            fsync_directory(lay.db.parent)
        except Refused:
            lay.tmp.unlink(missing_ok=True)
            raise
        except (OSError, sqlite3.Error) as exc:
            lay.tmp.unlink(missing_ok=True)
            state = {"tidy": "nothing in the live set changed",
                     "write": "nothing in the live set changed",
                     "keep": "nothing in the live set changed",
                     "fold": f"{lay.db} is the database it was, whole: its -wal folded into it, or still beside it",
                     "swap": f"{lay.db} is the database it was, whole, without its -wal",
                     "sync": f"{lay.db} is the copy, but the directory sync failed: check the volume"}[stage]
            message = f"the restore failed at the step {stage}: {exc}. {state}"
            raise Refused(EXIT_FAILED, message + (f"; the live set as found is kept under {kept}" if kept else "")) from exc
    after = schema_of(lay.db)
    say(f"kept         {kept}/  {', '.join(p.name for p in live_set)} (the live set, as found)" if kept else
        f"kept         nothing: there was no {lay.db}")
    say(f"removed      {', '.join(removed) or 'nothing'} (after opening and closing the old file, which folds its "
        "-wal into it)")
    say(f"written      {lay.db} <- {row.path} · sha256 {digest} · chgrp {group} · chmod g=u")
    say(f"user_version {'absent' if before is None else before} -> {after}")
    say("restored. Turn recovery mode off the way it was turned on: set recovery.enabled: false in this release's "
        "values file and roll it out through the release's deployment pipeline, or, under the break glass "
        "(charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md section 4d), give the release back to Git (its step 5). The app starts on "
        "the restored file once the recovery pod is gone.")
    if kept:
        say(f"way back     {kept}/ is the database as it was; charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md section 4, \"Undo a "
            "restore\", puts it back (fold it first: its rows may be only in its -wal)")
    for line in aside_notes(lay, known):
        say(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="restore-db.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight", help="on the laptop: the pod list on stdin")
    pre.add_argument("--release", required=True)
    pre.add_argument("--namespace", required=True)
    for name in ("list", "check", "restore"):
        command = sub.add_parser(name)
        if name != "list":
            command.add_argument("id", help="an ID as --list prints it: <user_version>-<the copy's stamp>")
        command.add_argument("--offsite", type=Path, default=Path("/offsite"),
                             help="where recovery mode mounts the offsite claim, read-only")
        command.add_argument("--proc", type=Path, default=Path("/proc"), help=argparse.SUPPRESS)
        command.add_argument("--group", type=int, default=0, help=argparse.SUPPRESS)
        if name == "restore":
            command.add_argument("--expected-sha256", help="the copy's sha256 on check's confirmation line")
            command.add_argument("--expected-size", type=int, help="the copy's size on that line")
            command.add_argument("--expected-live-sha256", help="the live set's fingerprint on that line")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            try:
                doc = json.load(sys.stdin)
            except ValueError as exc:
                raise Refused(EXIT_POD, f"the pod list is not JSON ({exc}): did oc get pods fail?") from exc
            name, image, left = preflight(doc, args.release, args.namespace, time.time())
            say(f"{name}\t{image}\t{span(left)}")
            return 0
        in_recovery(args.proc)
        lay = Layout(args.offsite)
        known = known_schema()
        if args.command == "list":
            with operation_lock(lay, "list"):
                return cmd_list(lay, known)
        if args.command == "check":
            with operation_lock(lay, f"check {args.id}"):
                return cmd_check(lay, args.id, known)
        confirmed = (args.expected_sha256, args.expected_size, args.expected_live_sha256)
        if any(value is None for value in confirmed) and any(value is not None for value in confirmed):
            raise Refused(EXIT_COPY, "restore takes all three of --expected-sha256, --expected-size and "
                                     "--expected-live-sha256 (check's confirmation line), or none")
        return cmd_restore(lay, args.id, known, args.group, None if confirmed[0] is None else confirmed)
    except Refused as exc:
        say(("failed: " if exc.code == EXIT_FAILED else "refused: ") + str(exc), sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
