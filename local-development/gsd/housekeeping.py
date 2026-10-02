"""Deleting report runs and database copies from the page (#542, docs/specs/SPEC_H1_gui_cleanup.md).

A one-off cleanup, nothing persisted: the chart's `reporting.retention` and `backup.*` stay the standing policy,
and a person in the cluster-admin tier either deletes items they chose or previews a tighter bound and confirms
it. This module holds what both pods share (the request shapes and the set digest) and the dashboard's own half:
the database copies on its data volume, in exactly three directories.

THE GUARD. In each directory the newest copy is never deleted from the page: the newest scheduled backup (a
restore needs a copy, docs/RUNBOOK_backup_restore.md §4), the newest pre-upgrade copy (the only way back across the
last schema upgrade, §6) and the newest pre-restore set (the way back from the last restore, §4 "Undo a restore").

THE BINDING. A cleanup's confirm carries the digest of the set its preview showed. The set is computed again under
the lock that deletes it, and a different set is refused (409) with the new preview, so the confirm deletes
exactly what the person saw or nothing (Kubernetes answers a failed delete precondition with 409 the same way).

NO PATH FROM THE REQUEST. A name is matched against the directory's own listing (os.scandir), never joined onto
a path, so `..`, a slash or a symlink cannot reach outside the three directories.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .storage import BACKUP_NAME
from .store import PRE_UPGRADE_DIR, PRE_UPGRADE_NAME

#: The three directories on the dashboard's data volume a copy may be deleted from, in the order the page lists them.
COPY_KINDS = ("backup", "pre-upgrade", "pre-restore")
#: Every kind of item the page deletes: the vocabulary of the audit line and of gsd_housekeeping_deleted_total.
KINDS = ("report-run", *COPY_KINDS)
#: Where a restore keeps the live set it replaced: beside the database, as restore-db.py's Layout names it.
PRE_RESTORE_DIR = "pre-restore"
#: A copy's own instant in its name: restore-db.py's keep and every copy writer stamp microseconds; the runbook's
#: manual keep (§4a) stamps whole seconds.
_STAMP = re.compile(r"(\d{8}T\d{6})(?:\.(\d{6}))?Z")
#: Why the newest copy of each kind is kept, in the words the page and the 409 say.
GUARDS = {
    "backup": "the newest scheduled backup is kept, so a restore always has a copy to restore "
              "(docs/RUNBOOK_backup_restore.md §4)",
    "pre-upgrade": "the newest pre-upgrade copy is kept: it is the only way back to the image before the last "
                   "schema upgrade (docs/RUNBOOK_backup_restore.md §6)",
    "pre-restore": "the newest pre-restore set is kept: it is the way back from the last restore "
                   "(docs/RUNBOOK_backup_restore.md §4, \"Undo a restore\")",
}
#: A schedule's name as the chart and the report service accept it: a short DNS label.
_SCHEDULE = r"[a-z0-9]([-a-z0-9]{0,40}[a-z0-9])?"


def set_digest(ids: Iterable[str]) -> str:
    """The digest a cleanup's confirm carries: sha256 of the sorted ids, one per line. Order-free, so the
    preview and the confirm agree however each listed the set."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


class CleanupChanged(Exception):
    """The set a confirmed cleanup would delete now is not the set its preview showed; nothing was deleted."""

    def __init__(self, plan: list) -> None:
        super().__init__("the set changed since the preview")
        self.plan = plan


class RunCleanupRequest(BaseModel):
    """A one-off cleanup of report runs: preview without `confirm`, delete with the preview's digest."""

    scope: str = Field(default="all", pattern=rf"^(all|manual|schedule:{_SCHEDULE})$",
                       description="Which runs: all, manual (a person's runs), or schedule:<name>, a schedule's runs "
                                   "whether or not the schedule is still configured.")
    older_than_days: int = Field(default=0, ge=0, le=3650,
                                 description="Only runs completed more than this many days ago; 0 is any age.")
    keep_newest: int = Field(default=0, ge=0, le=1000,
                             description="Keep the newest K runs of each (schedule, cluster); manual runs are one group "
                                         "per cluster. 0 keeps none.")
    confirm: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                description="The preview's digest: delete exactly that set, or 409 if it changed.")


class CopyCleanupRequest(BaseModel):
    """A one-off cleanup of database copies: preview without `confirm`, delete with the preview's digest."""

    kinds: list[Literal["backup", "pre-upgrade", "pre-restore"]] = Field(
        default_factory=lambda: list(COPY_KINDS), min_length=1, max_length=3,
        description="The directories to clean: backup, pre-upgrade, pre-restore.")
    older_than_days: int = Field(default=0, ge=0, le=3650,
                                 description="Only copies taken more than this many days ago; 0 is any age.")
    confirm: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                description="The preview's digest: delete exactly that set, or 409 if it changed.")


@dataclass(frozen=True)
class Copy:
    """One database copy on the data volume: a file (a backup, a pre-upgrade copy, a copy moved aside into
    pre-restore/) or a directory (a restore's kept live set)."""

    kind: str
    name: str
    path: Path
    is_dir: bool
    bytes: int
    at: datetime
    guarded: str | None

    @property
    def key(self) -> str:
        """The copy's id in a digest and in the API's path: `<kind>/<name>`."""
        return f"{self.kind}/{self.name}"

    def public(self) -> dict:
        return {"kind": self.kind, "name": self.name, "directory": str(self.path.parent),
                "type": "directory" if self.is_dir else "file", "bytes": self.bytes,
                "at": self.at.strftime("%Y-%m-%dT%H:%M:%SZ"), "guarded": self.guarded}


class CopyNotFound(LookupError):
    """No copy of that kind and name is listed (the name was never a copy, or it is already gone)."""


class CopyGuarded(Exception):
    """The copy named is the one its directory's guard keeps."""

    def __init__(self, copy: Copy) -> None:
        super().__init__(copy.guarded)
        self.copy = copy


def copy_dirs(db_path: str, backup_dir: str) -> dict[str, Path | None]:
    """The three directories, as the writers name them: config.backup.dir (None when backups are off), and
    pre-upgrade/ and pre-restore/ beside the database (/data/<pod>/ above one replica)."""
    beside = Path(db_path).parent
    return {"backup": Path(backup_dir) if backup_dir else None,
            "pre-upgrade": beside / PRE_UPGRADE_DIR, "pre-restore": beside / PRE_RESTORE_DIR}


def _is_copy(kind: str, name: str, is_dir: bool) -> bool:
    """Whether a directory entry is a copy of this kind. A writer's unfinished `.tmp`, a `.sha256` sidecar (it
    goes with its copy) and a hidden entry are never copies."""
    if name.startswith(".") or name.endswith((".tmp", ".sha256")):
        return False
    if kind == "backup":
        return not is_dir and BACKUP_NAME.fullmatch(name) is not None
    if kind == "pre-upgrade":
        return not is_dir and PRE_UPGRADE_NAME.fullmatch(name) is not None
    return (is_dir and _STAMP.fullmatch(name) is not None) or (not is_dir and name.endswith(".db"))


def _instant(name: str, path: Path) -> datetime:
    """The copy's own instant: the stamp in its name, else the file's modification time."""
    if (m := _STAMP.search(name)) is not None:
        return datetime.strptime(m.group(1) + "." + (m.group(2) or "000000"), "%Y%m%dT%H%M%S.%f").replace(tzinfo=UTC)
    return datetime.fromtimestamp(path.lstat().st_mtime, UTC)


def _size(path: Path, is_dir: bool) -> int:
    """Bytes the copy holds: a file and its sidecar, or the regular files directly inside a kept set."""
    if is_dir:
        with os.scandir(path) as inside:
            return sum(e.stat(follow_symlinks=False).st_size for e in inside if e.is_file(follow_symlinks=False))
    sidecar = path.with_name(path.name + ".sha256")
    return path.lstat().st_size + (sidecar.lstat().st_size if sidecar.is_file() else 0)


def list_copies(db_path: str, backup_dir: str) -> list[Copy]:
    """Every copy in the three directories, newest first, the newest of each kind guarded. A symlink is never
    listed, so nothing reached through one can be deleted."""
    out: list[Copy] = []
    for kind, directory in copy_dirs(db_path, backup_dir).items():
        if directory is None or not directory.is_dir():
            continue
        found = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if _is_copy(kind, entry.name, is_dir):
                    path = Path(entry.path)
                    found.append((entry.name, path, is_dir, _instant(entry.name, path), _size(path, is_dir)))
        # The guard's candidates: in pre-restore/ only a restore's kept set, never a copy moved aside into it.
        candidates = [f for f in found if kind != "pre-restore" or f[2]]
        newest = max(candidates, key=lambda f: (f[3], f[0]))[0] if candidates else None
        out.extend(Copy(kind, name, path, is_dir, size, at, GUARDS[kind] if name == newest else None)
                   for name, path, is_dir, at, size in found)
    return sorted(out, key=lambda c: (c.at, c.key), reverse=True)


#: One deletion at a time in this process: a listing and the deletions it decides are one step.
_lock = threading.Lock()


def _remove(copy: Copy) -> None:
    if copy.is_dir:
        shutil.rmtree(copy.path)
    else:
        copy.path.unlink(missing_ok=True)
        copy.path.with_name(copy.path.name + ".sha256").unlink(missing_ok=True)


def delete_copy(db_path: str, backup_dir: str, kind: str, name: str) -> Copy:
    """Delete one copy the listing names, unless it is the one its directory's guard keeps."""
    with _lock:
        found = next((c for c in list_copies(db_path, backup_dir) if c.kind == kind and c.name == name), None)
        if found is None:
            raise CopyNotFound(f"no {kind} copy named {name!r}")
        if found.guarded:
            raise CopyGuarded(found)
        _remove(found)
    return found


def cleanup_copies(db_path: str, backup_dir: str, *, kinds: list[str], older_than_days: int, now: datetime,
                   confirm: str | None) -> tuple[list[Copy], list[Copy], list[tuple[Copy, str]]]:
    """(the set, the guarded copies in scope, the failures). Without `confirm` nothing is deleted: the set is the
    preview. With it, the set is computed again under the lock and deleted only if its digest is `confirm`;
    otherwise CleanupChanged carries the set as it is now."""
    cutoff = now - timedelta(days=older_than_days)
    with _lock:
        listed = [c for c in list_copies(db_path, backup_dir) if c.kind in kinds]
        plan = [c for c in listed if not c.guarded and c.at < cutoff]
        kept = [c for c in listed if c.guarded]
        if confirm is None:
            return plan, kept, []
        if set_digest(c.key for c in plan) != confirm:
            raise CleanupChanged(plan)
        failed = []
        for copy in plan:
            try:
                _remove(copy)
            except OSError as exc:
                failed.append((copy, f"{type(exc).__name__}: {exc}"))
    return plan, kept, failed
