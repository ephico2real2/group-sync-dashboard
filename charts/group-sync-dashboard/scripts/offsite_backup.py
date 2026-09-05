#!/usr/bin/env python3
"""Carry the newest on-volume backup off the volume. Standard library only, on purpose.

The dashboard's own backups (gsd/store.py Store.backup, VACUUM INTO) land on the claim they
protect. This script runs in the chart's CronJob (templates/backup-offsite.yaml) with that claim
mounted READ-ONLY at /data and a destination mounted writable, and does five things, in order,
failing loudly on any of them:

  1. pick the newest gsd-*.db under --source, by NAME — the stamp is UTC with microseconds, so
     lexicographic order is chronological, and it is the same rule Store.backup rotates by;
  2. stream it to --dest as <name>.part, hashing and fsyncing it, then re-hash the .part and
     refuse publication unless the destination holds exactly the bytes read from the source;
  3. open the COPY with sqlite3 and run PRAGMA integrity_check — `immutable=1` so a WAL-flagged
     header cannot make SQLite want a -shm file it has no business creating here;
  4. write and fsync <name>.sha256.part (`sha256sum -c` format), rename the copy, rename the
     sidecar, fsync the destination directory — a copy never sits without its sidecar except
     across a kill between the two renames, which the next run repairs;
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
import re
import sqlite3
import sys
from pathlib import Path

CHUNK = 1024 * 1024
PATTERN = "gsd-*.db"
SIDECAR_LINE = re.compile(r"([0-9A-Fa-f]{64})[ \t]+(.+?)\r?\n?")
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


def sidecar_expected(sidecar: Path, name: str) -> str | None:
    """The digest a `sha256sum -c` sidecar records for `name`, or None when the sidecar is empty,
    malformed, names another file or carries something that is not a sha256 — a crash between
    creating the sidecar and writing it leaves a 0-byte file, and that must mean "copy again",
    never a traceback beside a copy that already verified (review of B1)."""
    try:
        text = sidecar.read_text()
    except OSError as exc:
        raise BackupError(f"cannot read sidecar {sidecar}: {exc}") from exc
    # One `sha256sum` line: the digest, horizontal whitespace (sha256sum writes two spaces), the
    # name — which may contain spaces if a copy was made by hand — and at most one line ending.
    # Not `.split()`: that accepted a digest and a name on separate lines, which `sha256sum -c`
    # rejects, and broke a name with a space into two fields (review of B1, second pass).
    match = SIDECAR_LINE.fullmatch(text)
    if match is None or match.group(2) != name:
        return None
    return match.group(1).lower()


def write_sidecar_part(part: Path, digest: str, name: str) -> None:
    """The sidecar's contents, fsynced, under a temporary name; the caller renames it into place
    beside the copy — the same care the copy gets, or a crash could leave a good copy beside an
    empty sidecar (review of B1)."""
    with part.open("w") as fh:
        fh.write(f"{digest}  {name}\n")
        fh.flush()
        os.fsync(fh.fileno())


def fsync_directory(directory: Path) -> None:
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def prune(dest: Path, keep: int) -> int:
    """Store.backup's rule: sorted(glob)[:-keep] goes. 0 keeps everything. Sidecars follow their
    copies; a sidecar whose copy is gone, and any .part a killed run left, go too (review of B1)."""
    for transient in (*dest.glob(PATTERN + PART_SUFFIX), *dest.glob(PATTERN + SUM_SUFFIX + PART_SUFFIX)):
        transient.unlink(missing_ok=True)
    copies = sorted(p for p in dest.glob(PATTERN) if p.is_file())
    victims = copies[:-keep] if keep > 0 else []
    for stale in victims:
        stale.unlink()
        stale.with_name(stale.name + SUM_SUFFIX).unlink(missing_ok=True)
    for orphan in dest.glob(PATTERN + SUM_SUFFIX):
        if not orphan.with_name(orphan.name[: -len(SUM_SUFFIX)]).is_file():
            orphan.unlink(missing_ok=True)
    return len(victims)


REPICK_ATTEMPTS = 3


def ship(source: Path, dest: Path, keep: int) -> int:
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"destination {dest} is not writable: {exc}") from exc
    if dest.resolve() == source.resolve():
        raise BackupError(f"destination {dest} IS the source directory — that is not off the volume")
    # A SIGKILL mid-copy skips `finally`; whatever .part a killed run left is not a copy and goes now.
    prune(dest, 0)

    # The app writes backups on its own timer (Store.backup), so the newest file can change while
    # this one is being copied — the picked file stays readable through its open descriptor, and
    # the copy is still a verified backup, one interval old. Re-pick a bounded number of times so
    # the destination ends the run holding the newest; past that, keep the verified copy and say so
    # in the log rather than chase a source that keeps moving (review of B1, both passes).
    for attempt in range(1, REPICK_ATTEMPTS + 1):
        newest = newest_backup(source)
        target = dest / newest.name
        sidecar = dest / (newest.name + SUM_SUFFIX)
        if target.exists() and sidecar.exists():
            expected = sidecar_expected(sidecar, newest.name)
            if expected is not None and sha256_of(target) == expected:
                print(f"already shipped: {target} matches its sidecar; nothing to copy")
                break
            print(f"{target} exists but does not match its sidecar; copying again", file=sys.stderr)

        part = dest / (newest.name + PART_SUFFIX)
        sidecar_part = dest / (newest.name + SUM_SUFFIX + PART_SUFFIX)
        published = False
        try:
            source_digest, size = copy_hashed(newest, part)
            # Verify what the DESTINATION persisted, not only what was read: a copy the storage
            # altered by a same-length value is still a structurally valid database, so
            # integrity_check alone would pass it (review of B1, Codex).
            digest = sha256_of(part)
            if digest != source_digest:
                raise BackupError(f"{part}: the destination holds sha256 {digest}, the source read "
                                  f"{source_digest} — the copy is not the bytes that were read")
            facts = integrity(part)
            # Publish in an order that never leaves a copy without its sidecar: the sidecar's
            # contents are durable under a temporary name first, then both are renamed into place.
            write_sidecar_part(sidecar_part, digest, newest.name)
            os.replace(part, target)
            published = True
            os.replace(sidecar_part, sidecar)
            fsync_directory(dest)
        except BackupError:
            if published:
                target.unlink(missing_ok=True)
                sidecar.unlink(missing_ok=True)
            raise
        except OSError as exc:
            if published:
                target.unlink(missing_ok=True)
                sidecar.unlink(missing_ok=True)
            raise BackupError(f"copying {newest} to {dest} failed: {exc}") from exc
        finally:
            part.unlink(missing_ok=True)
            sidecar_part.unlink(missing_ok=True)

        print(f"copied {newest} -> {target} ({size} bytes, sha256 {digest})")
        print(f"integrity_check ok; user_version {facts['user_version']}; "
              + "; ".join(f"{t} rows {facts[t]}" for t in HISTORY_TABLES))
        try:
            later = newest_backup(source)
        except BackupError:
            later = newest
        # Re-pick only when the name moved FORWARD: if the picked file vanished and an older one
        # is now the newest, the copy just published is the most recent this run saw.
        if later.name <= newest.name:
            break
        if attempt < REPICK_ATTEMPTS:
            print(f"note: {later.name} landed during the copy; shipping it too (attempt {attempt + 1})")
        else:
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
        expected = sidecar_expected(sidecar, path.name)
        if expected is None:
            raise BackupError(f"{path}: sidecar {sidecar} is empty or malformed")
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
