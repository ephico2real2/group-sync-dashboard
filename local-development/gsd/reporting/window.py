"""The global reporting window (design §5): a half-open, wrap-aware membership test that gates
automated report runs (`schedule`/`service` origins) to a configured time-of-day range on chosen
weekdays, in a chosen timezone.

Pure and self-contained: the predicate takes a timezone-aware `now` and localises it here, so the one
place the window logic lives is testable without env, a clock, or a server. Construction VALIDATES and
raises `WindowConfigError` on anything malformed — the report service turns that into a startup failure
(fail closed; an enabled-but-malformed window must never log-and-disable and silently stop gating).
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Index == datetime.weekday(): Monday is 0. The chart and env use these three-letter names.
WEEKDAYS: tuple[str, ...] = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAY_INDEX = {name.lower(): i for i, name in enumerate(WEEKDAYS)}


class WindowConfigError(ValueError):
    """A malformed reporting-window configuration. Raised at construction; the service fails startup."""


def _parse_hhmm(value: str, field: str) -> _dt.time:
    parts = value.strip().split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise WindowConfigError(f"reporting window {field}={value!r} is not HH:MM")
    hh, mm = int(parts[0]), int(parts[1])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise WindowConfigError(f"reporting window {field}={value!r} is not a valid 24h time")
    return _dt.time(hh, mm)


def _parse_days(days: list[str]) -> frozenset[int]:
    if not days:
        raise WindowConfigError("reporting window days is empty; give at least one weekday (Mon..Sun)")
    seen: set[int] = set()
    for name in days:
        idx = _WEEKDAY_INDEX.get(str(name).strip().lower())
        if idx is None:
            raise WindowConfigError(f"reporting window day {name!r} is not one of {', '.join(WEEKDAYS)}")
        if idx in seen:
            raise WindowConfigError(f"reporting window days has a duplicate: {name!r}")
        seen.add(idx)
    return frozenset(seen)


@dataclass(frozen=True)
class ReportingWindow:
    enabled: bool
    timezone: str
    start: _dt.time
    end: _dt.time
    days: frozenset[int]

    @classmethod
    def from_strings(cls, *, enabled: bool, timezone: str, start: str, end: str,
                     days: list[str]) -> "ReportingWindow":
        """Build and VALIDATE from the string forms the env/chart carry. A disabled window is not
        validated beyond its own shape here — but the service should only construct an enabled one when
        the operator asked for it, and an enabled window with a bad field raises."""
        if not enabled:
            # A disabled window never gates; keep a harmless, well-formed value so `is_open` is total.
            return cls(enabled=False, timezone=timezone.strip(), start=_dt.time(0, 0),
                       end=_dt.time(0, 0), days=frozenset(range(7)))
        tz = timezone.strip()
        if not tz:
            raise WindowConfigError("reporting window is enabled but timezone is empty; set an IANA zone")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise WindowConfigError(f"reporting window timezone {tz!r} is not a known IANA zone") from exc
        s, e = _parse_hhmm(start, "start"), _parse_hhmm(end, "end")
        if s == e:
            raise WindowConfigError(
                f"reporting window start and end are equal ({start!r}); that is neither empty nor a full "
                "day — pick a real range")
        return cls(enabled=True, timezone=tz, start=s, end=e, days=_parse_days(days))

    def _local(self, now_aware: _dt.datetime) -> _dt.datetime:
        if now_aware.tzinfo is None:
            raise ValueError("reporting window needs a timezone-aware `now`")
        # Canonicalise to a real instant via UTC first: a same-zone astimezone() can PRESERVE an
        # imaginary spring-forward wall time (which `contains` would then wrongly match), and the round
        # trip also fixes the correct `fold` during the autumn overlap (review of P4, C2/F1).
        return now_aware.astimezone(_dt.UTC).astimezone(ZoneInfo(self.timezone))

    def contains(self, now_aware: _dt.datetime) -> bool:
        """Half-open [start, end) membership, evaluated at the real instant localised to the window
        timezone. A wrap window (start > end, e.g. 22:00-06:00) splits at midnight: the pre-midnight
        part belongs to today's weekday; the post-midnight part belongs to YESTERDAY's window, so
        Monday 02:00 falls inside Sunday's 22:00-06:00 window (design §5)."""
        local_now = self._local(now_aware)
        t = local_now.time()
        today = local_now.weekday()
        yesterday = (today - 1) % 7
        if self.start < self.end:                                  # same-day window
            return self.start <= t < self.end and today in self.days
        return (t >= self.start and today in self.days) or (t < self.end and yesterday in self.days)

    def is_open(self, now_aware: _dt.datetime) -> bool:
        """Whether an automated run is admissible at this real instant. A disabled window never gates."""
        if not self.enabled:
            return True
        return self.contains(now_aware)

    def seconds_until_open(self, now_aware: _dt.datetime) -> int:
        """Seconds from `now` until the window next opens — the `Retry-After` for a 409. Scans REAL
        instants by stepping UTC (not the wall clock, which can step onto a nonexistent spring-forward
        time that `contains` would wrongly match, so the caller retries into a still-closed slot), up to
        8 days; a non-empty `days` with start != end always opens within a week. 0 if already open
        (review of P4, C2/F1)."""
        if self.is_open(now_aware):
            return 0
        now_utc = now_aware.astimezone(_dt.UTC)
        minute = now_utc.replace(second=0, microsecond=0)
        for step in range(1, 8 * 24 * 60 + 1):
            candidate = minute + _dt.timedelta(minutes=step)
            if self.is_open(candidate):
                delta = candidate - now_utc
                return max(1, int(delta.total_seconds()) + (1 if delta.microseconds else 0))
        raise RuntimeError("a validated reporting window did not open within eight real days")

    def next_change(self, now_aware: _dt.datetime) -> tuple[str, _dt.datetime | None]:
        """What the window does next and when: ("closes", at) while open, ("opens", at) while closed,
        ("never", None) for a disabled window (#149 R6 — the status page's "closes in 3h 12m"). The same
        real-instant scan as seconds_until_open, in the other direction too."""
        if not self.enabled:
            return "never", None
        open_now = self.is_open(now_aware)
        now_utc = now_aware.astimezone(_dt.UTC)
        minute = now_utc.replace(second=0, microsecond=0)
        for step in range(1, 8 * 24 * 60 + 1):
            candidate = minute + _dt.timedelta(minutes=step)
            if self.is_open(candidate) != open_now:
                return ("closes" if open_now else "opens"), candidate
        raise RuntimeError("a validated reporting window did not change within eight real days")
