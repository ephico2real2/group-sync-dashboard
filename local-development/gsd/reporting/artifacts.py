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
from dataclasses import asdict, dataclass, field, fields
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
    # How the run was requested: 'viewer' (a human's ticket), 'schedule' (service token + a named
    # schedule) or 'service' (service token, no schedule). Persisted so the worker's window recheck
    # (design §5) sees the same origin the endpoint gated on. Defaults to 'viewer' so a manifest written
    # before P4 (no origin key) still loads and is never mistaken for automated.
    origin: str = "viewer"

    def public(self) -> dict:
        return asdict(self)


# The manifest is a forward/backward-tolerant envelope: unknown keys are dropped on load and missing
# known keys fall back to defaults, so a rollback that reads a newer manifest does not drop the run.
_RUN_FIELDS = frozenset(f.name for f in fields(Run))


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
                data = json.loads(manifest.read_text(encoding="utf-8"))
                # Drop keys this build does not know (a newer manifest on rollback) rather than let
                # Run(**data) TypeError and silently lose the run from the index (design §5).
                self._runs[d.name] = Run(**{k: v for k, v in data.items() if k in _RUN_FIELDS})
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

    def prune(self, *, scheduled_keep: int, scheduled_days: int, manual_days: int,
              manual_max_runs: int, now: datetime,
              overrides: dict[str, tuple[int, int]] | None = None) -> int:
        """Two-tier retention (design R2) so a burst of manual runs can never evict a scheduled report.

        A SCHEDULED run (`schedule` set, `generated_by='schedule:<name>'`) is kept while within the newest
        `scheduled_keep` per (schedule, cluster) OR younger than `scheduled_days`, and is EXEMPT from the
        manual run-count cap — the live bug this fixes was the single cap slicing ALL finished runs by id,
        so a burst of manual runs pushed a still-valid scheduled report past `max_runs` and deleted it.
        `overrides[name] = (keep, days)` win over the globals for that schedule; a schedule with no override
        inherits them. A MANUAL run (no `schedule`) is kept `manual_days` and at most `manual_max_runs`,
        whichever prunes first. A bound of 0 is disabled. Queued/running runs are never doomed: they are
        still the worker's, and deleting their directory made GET /runs/{id} a 404 after a 202 while the
        worker skipped them silently (review of C3, Cursor). Deletion is by run directory, so the index and
        the disk cannot disagree for long."""
        overrides = overrides or {}

        def older_than(run: Run, day_bound: int) -> bool:
            return day_bound > 0 and run.id[:15] < (now - timedelta(days=day_bound)).strftime("%Y%m%dT%H%M%S")

        with self._lock:
            finished = [r for r in self._runs.values() if r.status in ("done", "failed")]
            doomed: list[Run] = []

            # Manual tier: keep the newest `manual_max_runs`, then drop anything older than `manual_days`.
            manual = sorted((r for r in finished if not r.schedule), key=lambda r: r.id, reverse=True)
            if manual_max_runs > 0:
                doomed += manual[manual_max_runs:]
                manual = manual[:manual_max_runs]
            doomed += [r for r in manual if older_than(r, manual_days)]

            # Scheduled tier: per (schedule, cluster) keep the newest K; beyond K keep only while young.
            by_key: dict[tuple[str, str], list[Run]] = {}
            for r in sorted((r for r in finished if r.schedule), key=lambda r: r.id, reverse=True):
                by_key.setdefault((r.schedule, r.cluster), []).append(r)
            for (name, _cluster), group in by_key.items():
                keep, days = overrides.get(name, (scheduled_keep, scheduled_days))
                doomed += [r for i, r in enumerate(group)
                           if not (keep > 0 and i < keep) and older_than(r, days)]

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
