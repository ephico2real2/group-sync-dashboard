"""Self-reported system usage: the process's own cgroup (v2) and the filesystem under its volume.

Measured on the running dashboard pod before this existed (issue #156): cgroup v2, readable by the
non-root user, no extra RBAC —

    memory.current  105410560      memory.max  536870912     -> 19.6 % of a 512Mi limit
    cpu.max         50000 100000                             -> 0.5 CPU
    cpu.stat        nr_throttled 196   throttled_usec 5058284   (over 175931 periods)

THROTTLING IS THE SATURATION SIGNAL, not utilisation: `nr_throttled / nr_periods` and throttled time
show a workload hitting its ceiling while utilisation still reads as headroom — the report pod was
preempted 29 times at 99 % node CPU (#97) with no metric saying so.

UNAVAILABLE IS NOT ZERO. On cgroup v1 (`cgroup.controllers` absent from the root), or when a
controller's file is missing, the sampler returns None for what it cannot read and the KPI is
omitted. A limit of `max` is "no limit", also None: `0` would read as a zero-core budget.

Rates are the caller's business. `cpu.stat` counters are exported as counters (Prometheus derives
the rate); the in-app view derives a rate from two samples on a MONOTONIC clock, so an NTP step
cannot make the delta negative (`CpuRate`).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

CGROUP_ROOT = "/sys/fs/cgroup"


@dataclass(frozen=True)
class Memory:
    current_bytes: int
    limit_bytes: int | None      # None: no limit (`memory.max` is `max`)


@dataclass(frozen=True)
class Cpu:
    usage_seconds: float         # cpu.stat usage_usec, cumulative
    limit_cores: float | None    # cpu.max quota/period; None when `max` (unlimited)
    periods: int                 # cpu.stat nr_periods
    throttled_periods: int       # cpu.stat nr_throttled
    throttled_seconds: float     # cpu.stat throttled_usec
    monotonic: float             # time.monotonic() at the read — for rates


@dataclass(frozen=True)
class CpuRate:
    """Derived from two Cpu samples: cores used over the interval, and the throttled share of it."""

    cores_used: float
    throttled_fraction: float | None   # of periods in the interval; None when no period elapsed
    interval_seconds: float


@dataclass(frozen=True)
class Disk:
    used_bytes: int
    total_bytes: int


class CgroupSampler:
    """Reads the process's own cgroup v2 files. `root` is injectable for tests with synthetic files."""

    def __init__(self, root: str | None = None):
        # Resolved at call time, not bound at import: a test points CGROUP_ROOT at synthetic files.
        self.root = Path(root or CGROUP_ROOT)

    @property
    def available(self) -> bool:
        """cgroup v2 mounted at the root. v1 has no `cgroup.controllers`; nothing is read from it."""
        return (self.root / "cgroup.controllers").is_file()

    def _read(self, name: str) -> str | None:
        try:
            return (self.root / name).read_text(encoding="ascii").strip()
        except (OSError, UnicodeDecodeError):
            return None

    def memory(self) -> Memory | None:
        if not self.available:
            return None
        current, limit = self._read("memory.current"), self._read("memory.max")
        if current is None or limit is None:
            return None
        try:
            return Memory(current_bytes=int(current), limit_bytes=None if limit == "max" else int(limit))
        except ValueError:
            log.warning("cgroup memory files are not in the v2 shape: current=%r max=%r", current, limit)
            return None

    def cpu(self) -> Cpu | None:
        if not self.available:
            return None
        stat, quota = self._read("cpu.stat"), self._read("cpu.max")
        if stat is None or quota is None:
            return None
        try:
            fields = dict(line.split(None, 1) for line in stat.splitlines() if line.strip())
            usage = int(fields["usage_usec"])
            periods = int(fields.get("nr_periods", 0))
            throttled = int(fields.get("nr_throttled", 0))
            throttled_usec = int(fields.get("throttled_usec", 0))
            q, period = quota.split()
            limit = None if q == "max" else int(q) / int(period)
        except (KeyError, ValueError):
            log.warning("cgroup cpu files are not in the v2 shape: cpu.max=%r", quota)
            return None
        return Cpu(usage_seconds=usage / 1_000_000, limit_cores=limit, periods=periods,
                   throttled_periods=throttled, throttled_seconds=throttled_usec / 1_000_000,
                   monotonic=time.monotonic())


def cpu_rate(previous: Cpu | None, current: Cpu) -> CpuRate | None:
    """The interval between two samples, on the monotonic clock. None until there are two."""
    if previous is None:
        return None
    interval = current.monotonic - previous.monotonic
    if interval <= 0:
        return None
    periods = current.periods - previous.periods
    return CpuRate(
        cores_used=max(0.0, current.usage_seconds - previous.usage_seconds) / interval,
        throttled_fraction=(current.throttled_periods - previous.throttled_periods) / periods if periods > 0 else None,
        interval_seconds=interval,
    )


def disk(path: str) -> Disk | None:
    """The filesystem holding `path`: used and total bytes, as `df` reports them. On a hostPath
    volume that is the node's disk, which is the number that matters when it fills (measured
    84 % on CRC, docs/design/data-requirements.md). None when the path cannot be statted."""
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    total = st.f_frsize * st.f_blocks
    return Disk(used_bytes=total - st.f_frsize * st.f_bfree, total_bytes=total)


#: The shortest interval a CPU rate is derived over. Measured on CRC before this existed: the two
#: cluster threads pulled the report service's usage feed milliseconds apart, and the second view
#: reported `cores_used 0.0813` over `rate_interval_seconds 0.0` — a rate over a few milliseconds is
#: noise. A view inside the interval repeats the last rate instead of minting one.
MIN_RATE_INTERVAL_SECONDS = 5.0


class SystemMonitor:
    """One process's self-report, for the in-app surface: the sampler, the volume, and the previous
    CPU sample the next rate is derived from. `view()` is what the dashboard serves for itself and
    what the report service adds to its usage feed. None when the cgroup is unreadable — the page
    says "unavailable", never 0. The poll thread calls `view()` once a cycle so a page request always
    has a baseline at most one poll interval old; two callers inside MIN_RATE_INTERVAL_SECONDS share
    one rate rather than deriving a second over a sliver."""

    def __init__(self, sampler: CgroupSampler | None, volume: str | None,
                 min_rate_interval: float = MIN_RATE_INTERVAL_SECONDS):
        self.sampler = sampler
        self.volume = volume
        self.min_rate_interval = min_rate_interval
        self._previous: Cpu | None = None
        self._last_rate: CpuRate | None = None
        self._lock = threading.Lock()

    def _rate(self, cpu: Cpu) -> CpuRate | None:
        with self._lock:
            if self._previous is None:
                self._previous = cpu
                return None
            if cpu.monotonic - self._previous.monotonic < self.min_rate_interval:
                return self._last_rate
            self._last_rate = cpu_rate(self._previous, cpu)
            self._previous = cpu
            return self._last_rate

    def view(self) -> dict | None:
        if self.sampler is None:
            return None
        memory, cpu = self.sampler.memory(), self.sampler.cpu()
        if memory is None and cpu is None:
            return None
        view: dict = {}
        if memory is not None:
            view["memory"] = {"used_bytes": memory.current_bytes, "limit_bytes": memory.limit_bytes}
        if cpu is not None:
            rate = self._rate(cpu)
            view["cpu"] = {
                "limit_cores": cpu.limit_cores,
                "usage_seconds": cpu.usage_seconds,
                "periods": cpu.periods,
                "throttled_periods": cpu.throttled_periods,
                "throttled_seconds": cpu.throttled_seconds,
                "cores_used": None if rate is None else round(rate.cores_used, 4),
                "throttled_fraction": None if rate is None else rate.throttled_fraction,
                "rate_interval_seconds": None if rate is None else round(rate.interval_seconds, 1),
            }
        if self.volume is not None:
            d = disk(self.volume)
            if d is not None:
                view["disk"] = {"used_bytes": d.used_bytes, "total_bytes": d.total_bytes}
        return view
