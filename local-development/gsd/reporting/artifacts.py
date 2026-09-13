"""Where a run's files live and how long. One directory per run under the artefact volume, a
`run.json` manifest beside the files, and an in-memory index rebuilt from the manifests at
startup — no second SQLite writer (the seam stays one writer per file, and a JSON file per run
is what an operator can `ls` and `cat` from the pod: the image has both).

Run ids sort chronologically as strings (`<stamp>-<random>`), which is what lets the dashboard's
usage pull page with `since_id` and what makes `ls` show them in order.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

FORMATS = ("json", "html", "pdf")
STATUSES = ("queued", "running", "done", "failed")


@dataclass
class Run:
    id: str
    report: str
    cluster: str
    params: dict
    formats: list[str]
    generated_by: str
    generated_by_note: str
    schedule: str | None
    requested_at: str
    status: str = "queued"
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    sha256: str | None = None
    snapshot_stamp: str | None = None
    bytes: dict = field(default_factory=dict)     # format -> size
    pdf_variant: str | None = None
    render_seconds: float | None = None

    def public(self) -> dict:
        return asdict(self)


def new_run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S.%fZ") + "-" + secrets.token_hex(2)


class ArtifactStore:
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._runs: dict[str, Run] = {}
        self._load()

    def _load(self) -> None:
        for d in sorted(self.root.iterdir()):
            manifest = d / "run.json"
            if not d.is_dir() or not manifest.is_file():
                continue
            try:
                self._runs[d.name] = Run(**json.loads(manifest.read_text(encoding="utf-8")))
            except (OSError, ValueError, TypeError) as exc:
                log.warning("skipping unreadable run manifest %s: %s", manifest, exc)
        # A run that was 'running' when the pod died is failed, and the manifest says so.
        for r in self._runs.values():
            if r.status in ("queued", "running"):
                r.status, r.error = "failed", "the report service restarted before this run finished"
                self._write_manifest(r)
        log.info("artifact index: %d run(s) under %s", len(self._runs), self.root)

    def _dir(self, run_id: str) -> Path:
        return self.root / run_id

    def _write_manifest(self, run: Run) -> None:
        d = self._dir(run.id)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "run.json.tmp"
        tmp.write_text(json.dumps(run.public(), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, d / "run.json")

    def create(self, run: Run) -> Run:
        with self._lock:
            self._runs[run.id] = run
            self._write_manifest(run)
        return run

    def update(self, run: Run) -> None:
        with self._lock:
            self._runs[run.id] = run
            self._write_manifest(run)

    def write(self, run_id: str, fmt: str, data: bytes) -> int:
        if fmt not in FORMATS:
            raise ValueError(fmt)
        d = self._dir(run_id)
        d.mkdir(parents=True, exist_ok=True)      # belt: a run directory pruned mid-render is recreated, not a crash
        tmp = d / f"report.{fmt}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, d / f"report.{fmt}")
        return len(data)

    def read(self, run_id: str, fmt: str) -> bytes | None:
        p = self._dir(run_id) / f"report.{fmt}"
        return p.read_bytes() if p.is_file() else None

    def get(self, run_id: str) -> Run | None:
        with self._lock:
            return self._runs.get(run_id)

    def list(self, *, report: str | None = None, limit: int = 100, offset: int = 0,
             generated_by: str | None = None) -> tuple[list[Run], int]:
        with self._lock:
            runs = sorted(self._runs.values(), key=lambda r: r.id, reverse=True)
        if report:
            runs = [r for r in runs if r.report == report]
        if generated_by:
            runs = [r for r in runs if r.generated_by == generated_by]
        return runs[offset:offset + limit], len(runs)

    def since(self, since_id: str | None, limit: int) -> list[Run]:
        """Finished runs with id > since_id, oldest first — the dashboard's usage pull.

        NEVER a finished run whose id is greater than any queued or running id. The dashboard
        watermarks at MAX(id) of what it recorded, and finish order is not id order: a QueueFull
        failure has the newest id and is finished at once, so publishing it while older runs are
        still in flight would move the watermark past them and hide them from every later pull
        (review of C3, Cursor). The page stops at the oldest in-flight id and resumes when it settles.
        """
        with self._lock:
            unfinished = [r.id for r in self._runs.values() if r.status in ("queued", "running")]
            cap = min(unfinished) if unfinished else None
            runs = sorted((r for r in self._runs.values()
                           if r.status in ("done", "failed") and (since_id is None or r.id > since_id)
                           and (cap is None or r.id < cap)),
                          key=lambda r: r.id)
        return runs[:limit]

    def prune(self, *, days: int, max_runs: int, now: datetime) -> int:
        """Remove FINISHED runs older than `days` and beyond the newest `max_runs`; 0 disables either
        bound. Deletion is by run directory, so the index and the disk cannot disagree for long.
        Queued and running runs are never doomed: they are still in the worker's queue, and deleting
        their directory made GET /runs/{id} a 404 after a 202 while the worker skipped them silently
        (review of C3, Cursor)."""
        with self._lock:
            runs = sorted((r for r in self._runs.values() if r.status in ("done", "failed")),
                          key=lambda r: r.id, reverse=True)
            doomed: list[Run] = []
            if max_runs > 0:
                doomed += runs[max_runs:]
                runs = runs[:max_runs]
            if days > 0:
                cutoff = (now - timedelta(days=days)).strftime("%Y%m%dT%H%M%S")
                doomed += [r for r in runs if r.id[:15] < cutoff]
            for r in doomed:
                shutil.rmtree(self._dir(r.id), ignore_errors=True)
                self._runs.pop(r.id, None)
        if doomed:
            log.info("pruned %d report run(s)", len(doomed))
        return len(doomed)

    def disk_bytes(self) -> int:
        total = 0
        for d in self.root.iterdir():
            if d.is_dir():
                for f in d.iterdir():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
        return total
