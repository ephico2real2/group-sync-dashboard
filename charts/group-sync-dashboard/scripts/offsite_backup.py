#!/usr/bin/env python3
"""Carry the newest on-volume backup off the volume. Standard library only, on purpose.

The dashboard's own backups (gsd/store.py Store.backup, VACUUM INTO) land on the claim they
protect. This script runs in the chart's CronJob (templates/backup-offsite.yaml) with that claim
mounted READ-ONLY at /data and a destination mounted writable, and does five things, in order,
failing loudly on any of them:

  1. pick the newest gsd-*.db under --source, by NAME — the stamp is UTC with microseconds, so
     lexicographic order is chronological, and it is the same rule Store.backup rotates by;
  2. stream it to --dest as <name>.part, hashing as it goes (one pass, 1 MiB chunks, fsync);
  3. open the COPY with sqlite3 and run PRAGMA integrity_check — `immutable=1` so a WAL-flagged
     header cannot make SQLite want a -shm file it has no business creating here;
  4. rename .part to <name> and write <name>.sha256 in `sha256sum -c` format;
  5. prune --dest to --keep copies (0 keeps everything), sidecars with their copies.

Idempotent: a destination copy that already matches its sidecar is left alone and the run still
succeeds, so a schedule denser than the app's backups is harmless. Every failure raises
BackupError and exits 1 with the reason on stderr — the CronJob's status is the only signal the
chart's alert can see.

No tar, no gzip, no aws: the image has none (docs/DESIGN_hardened_image.md §10) and a shell copy
could not verify what it copied. S3 is deliberately NOT implemented here — see values.yaml under
backup.offsite.destination.s3 for why a write-only credential and a lifecycle rule beat a pruner.

    --check FILE   verify one copy in place (integrity, sha256 against its sidecar if present,
                   user_version, row counts) without copying anything. The runbook uses it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

CHUNK = 1024 * 1024
PATTERN = "gsd-*.db"
PART_SUFFIX = ".part"
SUM_SUFFIX = ".sha256"
HISTORY_TABLES = ("membership_event", "sync_event")


class BackupError(Exception):
    """A failure the operator must see. Every one exits non-zero with its message."""


def newest_backup(source: Path) -> Path:
    if not source.is_dir():
        raise BackupError(
            f"source {source} is not a directory — is config.backup.dir mounted here, "
            f"and is config.backup.enabled on?"
        )
    candidates = sorted(p for p in source.glob(PATTERN) if p.is_file())
    if not candidates:
        raise BackupError(
            f"no {PATTERN} under {source}: the dashboard has not written a backup yet "
            f"(it takes one on its first poll), or config.backup is off"
        )
    return candidates[-1]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def copy_hashed(src: Path, dst: Path) -> tuple[str, int]:
    """Stream src to dst, hashing as it goes. Returns (sha256 hex, bytes written)."""
    digest = hashlib.sha256()
    size = 0
    with src.open("rb") as reader, dst.open("wb") as writer:
        while chunk := reader.read(CHUNK):
            writer.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest(), size


def integrity(path: Path) -> dict:
    """PRAGMA integrity_check on a copy, plus the facts the runbook asks for.

    Raises BackupError on anything but 'ok' — including a file that is not a database at
    all, which is what a truncated or garbage copy looks like to sqlite3.
    """
    uri = f"file:{path.as_posix()}?immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"{path}: cannot open: {exc}") from exc
    try:
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error as exc:
            raise BackupError(f"{path}: integrity_check failed to run: {exc}") from exc
        if verdict != "ok":
            raise BackupError(f"{path}: integrity_check said {verdict!r}")
        facts: dict = {"user_version": conn.execute("PRAGMA user_version").fetchone()[0]}
        for table in HISTORY_TABLES:
            try:
                facts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                facts[table] = None          # a database from before the table existed
    finally:
        conn.close()
    return facts


def sidecar_expected(sidecar: Path) -> str | None:
    """The first field of a `sha256sum -c` sidecar, or None when it is empty or malformed — a
    crash between creating the sidecar and writing it leaves a 0-byte file, and that must mean
    "copy again", never a traceback beside a copy that already verified (review of B1)."""
    parts = sidecar.read_text().split()
    return parts[0] if parts else None


def write_sidecar(sidecar: Path, digest: str, name: str) -> None:
    """Write the sidecar durably: to a temporary name, fsync, rename, fsync the directory — the
    same care the copy gets, or a crash could leave a good copy beside an empty sidecar."""
    tmp = sidecar.with_name(sidecar.name + PART_SUFFIX)
    with tmp.open("w") as fh:
        fh.write(f"{digest}  {name}\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, sidecar)
    dir_fd = os.open(str(sidecar.parent), os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def prune(dest: Path, keep: int) -> int:
    """Store.backup's rule: sorted(glob)[:-keep] goes. 0 keeps everything. Sidecars follow."""
    if keep <= 0:
        return 0
    copies = sorted(p for p in dest.glob(PATTERN) if p.is_file())
    removed = 0
    for stale in copies[:-keep]:
        stale.unlink()
        stale.with_name(stale.name + SUM_SUFFIX).unlink(missing_ok=True)
        removed += 1
    return removed


def ship(source: Path, dest: Path, keep: int) -> int:
    newest = newest_backup(source)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"destination {dest} is not writable: {exc}") from exc
    if dest.resolve() == source.resolve():
        raise BackupError(f"destination {dest} IS the source directory — that is not off the volume")
    # A SIGKILL mid-copy skips `finally`; whatever .part it left is not a copy and goes now.
    for stale in dest.glob("*" + PART_SUFFIX):
        stale.unlink(missing_ok=True)

    target = dest / newest.name
    sidecar = dest / (newest.name + SUM_SUFFIX)
    if target.exists() and sidecar.exists():
        expected = sidecar_expected(sidecar)
        if expected is not None and sha256_of(target) == expected:
            print(f"already shipped: {target} matches its sidecar; nothing to copy")
            removed = prune(dest, keep)
            print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
            return 0
        print(f"{target} exists but does not match its sidecar; copying again", file=sys.stderr)

    part = dest / (newest.name + PART_SUFFIX)
    try:
        digest, size = copy_hashed(newest, part)
        facts = integrity(part)
        os.replace(part, target)
        write_sidecar(sidecar, digest, newest.name)
    except OSError as exc:
        raise BackupError(f"copying {newest} to {dest} failed: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)

    print(f"copied {newest} -> {target} ({size} bytes, sha256 {digest})")
    print(f"integrity_check ok; user_version {facts['user_version']}; "
          + "; ".join(f"{t} rows {facts[t]}" for t in HISTORY_TABLES))
    # The app may have written a newer backup while this one copied (Store.backup runs on its own
    # timer). The copy above is still a verified backup; the newer one ships on the next run, and
    # the log says so rather than looping here (review of B1).
    try:
        later = newest_backup(source)
    except BackupError:
        later = newest
    if later.name != newest.name:
        print(f"note: {later.name} landed during the copy; it ships on the next run")
    removed = prune(dest, keep)
    print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
    return 0


def check(path: Path) -> int:
    if not path.is_file():
        raise BackupError(f"{path} is not a file")
    digest = sha256_of(path)
    facts = integrity(path)
    sidecar = path.with_name(path.name + SUM_SUFFIX)
    print(f"{path}: integrity_check ok")
    print(f"sha256 {digest}")
    if sidecar.exists():
        expected = sidecar.read_text().split()[0]
        if expected != digest:
            raise BackupError(f"{path}: sha256 {digest} does not match sidecar {expected}")
        print("sidecar matches")
    else:
        print("no sidecar (an on-volume backup, or one copied by hand)")
    print(f"user_version {facts['user_version']}; "
          + "; ".join(f"{t} rows {facts[t]}" for t in HISTORY_TABLES))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="directory of gsd-*.db files (config.backup.dir)")
    parser.add_argument("--dest", type=Path, help="where the newest one goes")
    parser.add_argument("--keep", type=int, default=0, help="copies to keep at --dest; 0 keeps all")
    parser.add_argument("--check", type=Path, metavar="FILE", help="verify one copy and exit")
    args = parser.parse_args(argv)
    try:
        if args.check is not None:
            return check(args.check)
        if args.source is None or args.dest is None:
            parser.error("--source and --dest are required unless --check is given")
        return ship(args.source, args.dest, args.keep)
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
