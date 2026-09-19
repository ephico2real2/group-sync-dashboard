"""Rendering, one run at a time, on a worker thread with a bounded queue.

ONE WORKER, ON PURPOSE. A render is CPU and memory (fpdf2 lays out the whole document before
writing); two at once double the peak and the pod's memory limit is what ends a render that
grows too large. A bounded queue answers 429 rather than accepting work it will hold for minutes.
The dashboard is never on this path — the browser polls GET /report/api/runs/{id}.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
import traceback
from datetime import UTC, datetime

from .. import TITLE
from .artifacts import ArtifactStore, Run
from .catalogue import REGISTRY, RunContext, ValidationError, validate_params
from .config import ReportSettings
from .render_html import render_html
from .snapshot import Snapshot, SnapshotError, newest_snapshot

log = logging.getLogger(__name__)


class QueueFull(Exception):
    pass


class RunManager:
    def __init__(self, settings: ReportSettings, store: ArtifactStore, metrics, *, clock=None):
        self.settings = settings
        self.store = store
        self.metrics = metrics
        self._clock = clock or (lambda: datetime.now(UTC))
        self._queue: queue.Queue[str] = queue.Queue(maxsize=settings.max_queued_runs)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="report-worker", daemon=True)
        self._last_prune = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def submit(self, run: Run) -> Run:
        self.store.create(run)
        try:
            self._queue.put_nowait(run.id)
        except queue.Full:
            # Refused is finished: stamp it like every other terminal transition (the render's `finally`,
            # the window recheck) so the manifest carries its completion and retention ages it from it
            # (#163) rather than through the id fallback.
            run.status, run.error = "failed", "the render queue is full; try again shortly"
            run.finished_at = self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
            self.store.update(run)
            raise QueueFull()
        self.metrics.note_submitted(run.report)
        return run

    def queued(self) -> int:
        return self._queue.qsize()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                self._maybe_prune()
                continue
            run = self.store.get(run_id)
            if run is None:
                continue
            self._render(run)
            self._maybe_prune()

    def _maybe_prune(self) -> None:
        now = time.monotonic()
        if now - self._last_prune < 3600:
            return
        self._last_prune = now
        try:
            self.store.prune(scheduled_keep=self.settings.scheduled_keep_per_schedule,
                             scheduled_days=self.settings.scheduled_retention_days,
                             manual_days=self.settings.manual_retention_days,
                             manual_max_runs=self.settings.manual_retention_max_runs,
                             now=self._clock())
        except Exception:  # noqa: BLE001 — retention must never stop rendering
            log.exception("artifact prune failed")

    def _admitted_in_window(self, run: Run) -> bool:
        """Whether the run was requested INSIDE the reporting window — the worker's belt for the
        queue-crossing case (design §5). Recheck against requested_at, not now: a run admitted just
        before the close still renders (end-of-window schedules are not flaky), but a run that never
        was in-window (a replayed manifest, config drift) is failed here rather than rendered. A
        malformed timestamp is not the window's business — create_run already gated on it."""
        if not self.settings.window.enabled:
            return True
        try:
            requested = datetime.strptime(run.requested_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return True
        return self.settings.window.is_open(requested)

    def _render(self, run: Run) -> None:
        if run.origin != "viewer" and not self._admitted_in_window(run):
            run.status, run.error = "failed", "outside the reporting window at request time (rechecked at render)"
            run.finished_at = self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
            self.store.update(run)
            self.metrics.note_outside_window(run.origin)
            # submit() counted it SUBMITTED when it entered the queue, so the recheck failure counts it
            # FINISHED here too — the early return skips the completion `finally` below, and without this
            # gsd_report_runs_submitted_total minus finished_total reads as one run in flight for ever
            # (review of P4, C5). Zero seconds, zero bytes: nothing rendered.
            self.metrics.note_finished(run.report, "failed", 0.0, 0)
            log.warning("run %s failed the window recheck (origin=%s requested_at=%s)",
                        run.id, run.origin, run.requested_at)
            return
        run.status, run.started_at = "running", self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
        self.store.update(run)
        started = time.perf_counter()
        try:
            spec, build = REGISTRY[run.report]
            params = validate_params(spec, run.params)
            path = newest_snapshot(self.settings.snapshot_dir)
            with Snapshot(path) as snap:
                info = snap.info()
                cluster = snap.cluster(run.cluster)
                if cluster is None:
                    raise ValidationError(f"unknown cluster {run.cluster!r} in the snapshot")
                now = self._clock()
                ctx = RunContext(settings=self.settings, cluster=cluster, now=now, run_id=run.id,
                                 generated_by=run.generated_by, generated_by_note=run.generated_by_note,
                                 snapshot_stamp=info.stamp, snapshot_age_seconds=info.age_seconds(now),
                                 schema_version=info.schema_version,
                                 namespace_selector_labels=self.settings.namespace_selector_labels)
                from .catalogue.common import assemble
                report = assemble(spec, snap, ctx, params, build(snap, ctx, params))
            run.snapshot_stamp, run.sha256 = info.stamp, report.sha256
            canonical = report.to_json().encode("utf-8")
            run.bytes["json"] = self.store.write(run.id, "json", canonical)
            if "html" in run.formats:
                run.bytes["html"] = self.store.write(run.id, "html", render_html(report, TITLE).encode("utf-8"))
            if "pdf" in run.formats:
                from .render_pdf import render_pdf
                run.pdf_variant = self.settings.pdf_variant
                run.bytes["pdf"] = self.store.write(run.id, "pdf", render_pdf(
                    report, TITLE, self.settings.pdf_variant, self.settings.font_regular, self.settings.font_bold, canonical))
            run.status = "done"
        except (ValidationError, SnapshotError) as exc:
            run.status, run.error = "failed", str(exc)
        except Exception as exc:  # noqa: BLE001 — the trace goes to the log, a sentence to the run
            log.error("run %s failed:\n%s", run.id, traceback.format_exc())
            run.status, run.error = "failed", f"render failed: {type(exc).__name__}"
        finally:
            run.render_seconds = round(time.perf_counter() - started, 3)
            run.finished_at = self._clock().strftime("%Y-%m-%dT%H:%M:%SZ")
            self.store.update(run)
            self.metrics.note_finished(run.report, run.status, run.render_seconds, sum(run.bytes.values()))
            # The evidence-gap signal (design §5): stamp the schedule's last success so a monitor can
            # alert on "no success within its period" — a wrong timezone must not silently stop evidence.
            if run.status == "done" and run.schedule:
                self.metrics.note_schedule_success(run.schedule, self._clock().timestamp())
