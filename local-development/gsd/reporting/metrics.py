"""The report service's own exposition. Process-local counters: there is no store to mirror
(gsd/metrics.py's first rule), and every event here happens exactly once in this process.
NO NAMES: labels are the report's catalogue name and a status, never a viewer or a cluster's
subjects — the dashboard's rule for /metrics, which is unauthenticated on the Service."""

from __future__ import annotations

import threading

from prometheus_client import CollectorRegistry
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from .. import __version__
from .artifacts import STATUSES
from .config import REPORT_NAMES


class ReportSignals:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._submitted = {n: 0 for n in REPORT_NAMES}
        self._finished = {(n, s): 0 for n in REPORT_NAMES for s in ("done", "failed")}
        self._seconds = {n: 0.0 for n in REPORT_NAMES}
        self._bytes = {n: 0 for n in REPORT_NAMES}

    def note_submitted(self, report: str) -> None:
        with self._lock:
            self._submitted[report] = self._submitted.get(report, 0) + 1

    def note_finished(self, report: str, status: str, seconds: float, size: int) -> None:
        with self._lock:
            key = (report, status if status in ("done", "failed") else "failed")
            self._finished[key] = self._finished.get(key, 0) + 1
            self._seconds[report] = self._seconds.get(report, 0.0) + (seconds or 0.0)
            self._bytes[report] = self._bytes.get(report, 0) + (size or 0)

    def snapshot(self) -> dict:
        with self._lock:
            return {"submitted": dict(self._submitted), "finished": dict(self._finished),
                    "seconds": dict(self._seconds), "bytes": dict(self._bytes)}


class ReportCollector:
    def __init__(self, signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe):
        self.signals, self.store, self.runs, self.snapshot_dir, self.snapshot_probe = signals, store, runs, snapshot_dir, snapshot_probe

    def collect(self):
        snap = self.signals.snapshot()
        submitted = CounterMetricFamily("gsd_report_runs_submitted_total", "Report runs accepted into the queue.", labels=["report"])
        finished = CounterMetricFamily("gsd_report_runs_finished_total", "Report runs finished, by outcome.", labels=["report", "status"])
        seconds = CounterMetricFamily("gsd_report_render_seconds_total", "Wall time spent rendering, by report; divide by finished runs for a mean.", labels=["report"])
        size = CounterMetricFamily("gsd_report_artifact_bytes_total", "Artefact bytes written, by report.", labels=["report"])
        for n in REPORT_NAMES:
            submitted.add_metric([n], snap["submitted"].get(n, 0))
            seconds.add_metric([n], snap["seconds"].get(n, 0.0))
            size.add_metric([n], snap["bytes"].get(n, 0))
            for s in ("done", "failed"):
                finished.add_metric([n, s], snap["finished"].get((n, s), 0))
        yield submitted
        yield finished
        yield seconds
        yield size
        queued = GaugeMetricFamily("gsd_report_queue_length", "Runs waiting for the worker.")
        queued.add_metric([], self.runs.queued())
        yield queued
        disk = GaugeMetricFamily("gsd_report_artifacts_disk_bytes", "Bytes held under the artefact volume.")
        disk.add_metric([], self.store.disk_bytes())
        yield disk
        age = GaugeMetricFamily("gsd_report_snapshot_age_seconds", "Age of the newest snapshot the service would render from; absent when there is none.")
        stamp_age = self.snapshot_probe()
        if stamp_age is not None:
            age.add_metric([], stamp_age)
        yield age
        info = GaugeMetricFamily("gsd_report_build_info", "Version of the report service (always 1).", labels=["version"])
        info.add_metric([__version__], 1)
        yield info


def build_report_registry(signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe) -> CollectorRegistry:
    reg = CollectorRegistry()
    reg.register(ReportCollector(signals, store, runs, snapshot_dir, snapshot_probe))
    return reg
