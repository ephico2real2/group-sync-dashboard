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
        #: Automated runs refused by the reporting window, by origin (config, not a person). §5.
        self._outside_window = {"schedule": 0, "service": 0}
        #: Unix time of the last successful run per schedule NAME (operator config, not a person) — the
        #: signal a monitor turns into "no success within its period", the evidence-gap alert (§5).
        self._schedule_last_success: dict[str, float] = {}

    def note_submitted(self, report: str) -> None:
        with self._lock:
            self._submitted[report] = self._submitted.get(report, 0) + 1

    def note_finished(self, report: str, status: str, seconds: float, size: int) -> None:
        with self._lock:
            key = (report, status if status in ("done", "failed") else "failed")
            self._finished[key] = self._finished.get(key, 0) + 1
            self._seconds[report] = self._seconds.get(report, 0.0) + (seconds or 0.0)
            self._bytes[report] = self._bytes.get(report, 0) + (size or 0)

    def note_outside_window(self, origin: str) -> None:
        with self._lock:
            self._outside_window[origin] = self._outside_window.get(origin, 0) + 1

    def note_schedule_success(self, schedule: str, when: float) -> None:
        with self._lock:
            self._schedule_last_success[schedule] = when

    def snapshot(self) -> dict:
        with self._lock:
            return {"submitted": dict(self._submitted), "finished": dict(self._finished),
                    "seconds": dict(self._seconds), "bytes": dict(self._bytes),
                    "outside_window": dict(self._outside_window),
                    "schedule_last_success": dict(self._schedule_last_success)}


class ReportCollector:
    def __init__(self, signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                 system=None, volume: str | None = None):
        self.signals, self.store, self.runs, self.snapshot_dir, self.snapshot_probe = signals, store, runs, snapshot_dir, snapshot_probe
        # The KPI module's sources (#156): this process's cgroup sampler and the artefact volume.
        self.system, self.volume = system, volume

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
        outside = CounterMetricFamily("gsd_report_runs_outside_window_total",
                                      "Automated runs refused because the reporting window is closed, by origin.",
                                      labels=["origin"])
        for origin in ("schedule", "service"):
            outside.add_metric([origin], snap["outside_window"].get(origin, 0))
        yield outside
        last_success = GaugeMetricFamily("gsd_report_schedule_last_success_timestamp",
                                         "Unix time of the last successful run per schedule name (operator config, "
                                         "not a person); monitor 'no success within its period' as an evidence gap.",
                                         labels=["schedule"])
        for sched, ts in snap["schedule_last_success"].items():
            last_success.add_metric([sched], ts)
        yield last_success
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
        # The KPI module's public families under component="report" (#156): the process's own cgroup
        # and volume. The churn counters need the dashboard's store and are absent here by construction
        # — no store, no signals — declared empty, never sampled.
        from ..kpi import COMPONENT_REPORT, Context
        from ..kpi.definitions import PUBLIC_KPIS
        from ..kpi.render_prom import render
        yield from render(PUBLIC_KPIS, Context(component=COMPONENT_REPORT, system=self.system, volume=self.volume))


def build_report_registry(signals: ReportSignals, store, runs, snapshot_dir: str, snapshot_probe,
                          system=None, volume: str | None = None) -> CollectorRegistry:
    reg = CollectorRegistry()
    reg.register(ReportCollector(signals, store, runs, snapshot_dir, snapshot_probe, system=system, volume=volume))
    return reg
