"""A five-field cron expression, the way Kubernetes reads a CronJob's schedule: next and previous fire
instants in a zone, and a short cadence for a person to read (#149 R5/R6).

Written rather than depended on: the service needs three answers about a handful of schedules — when
the next fire is, when the last one should have been, and what the cadence is called — and the
standard semantics fit in a page: `*`, lists, ranges, steps, the @-shorthands, and the day-of-month /
day-of-week rule (when BOTH are restricted a day matches if EITHER does). Sunday is 0 or 7. Names are
not accepted (the chart's values use numbers; Kubernetes accepts names but every example here is
numeric). Scanning is by day, then the hour and minute sets, so a `* * * * *` schedule still resolves
in well under a second and a monthly one in microseconds.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

SHORTHANDS = {
    "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *",
}
_BOUNDS = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_NAMES = ("minute", "hour", "day-of-month", "month", "day-of-week")


class CronError(ValueError):
    pass


def _field(text: str, lo: int, hi: int, name: str) -> tuple[set[int], bool]:
    """The set of values a field admits, and whether it is unrestricted (`*` or `*/n`)."""
    out: set[int] = set()
    star = False
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            if not step_s.isdigit() or int(step_s) < 1:
                raise CronError(f"{name}: bad step in {text!r}")
            step = int(step_s)
        if part == "*":
            a, b = lo, hi
            star = star or step == 1
        elif "-" in part:
            a_s, b_s = part.split("-", 1)
            if not (a_s.isdigit() and b_s.isdigit()):
                raise CronError(f"{name}: bad range in {text!r}")
            a, b = int(a_s), int(b_s)
        elif part.isdigit():
            a = b = int(part)
            if step != 1:      # `5/10` means 5,15,25… up to the bound
                b = hi
        else:
            raise CronError(f"{name}: cannot read {text!r}")
        if a < lo or b > hi or a > b:
            raise CronError(f"{name}: {text!r} is outside {lo}-{hi}")
        out.update(range(a, b + 1, step))
    return out, star


@dataclass(frozen=True)
class CronSpec:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]     # 0 = Sunday … 6 = Saturday (7 folded onto 0)
    days_star: bool
    weekdays_star: bool
    text: str

    def day_matches(self, d: _dt.date) -> bool:
        if d.month not in self.months:
            return False
        dom = d.day in self.days
        dow = (d.isoweekday() % 7) in self.weekdays
        if self.days_star and self.weekdays_star:
            return True
        if self.days_star:
            return dow
        if self.weekdays_star:
            return dom
        return dom or dow      # both restricted: either (Vixie cron, and Kubernetes)


def parse(expr: str) -> CronSpec:
    text = expr.strip()
    expanded = SHORTHANDS.get(text, text)
    parts = expanded.split()
    if len(parts) != 5:
        raise CronError(f"expected five fields, got {len(parts)} in {expr!r}")
    sets = []
    stars = []
    for part, (lo, hi), name in zip(parts, _BOUNDS, _NAMES):
        values, star = _field(part, lo, hi, name)
        sets.append(values)
        stars.append(star)
    weekdays = frozenset(0 if v == 7 else v for v in sets[4])
    return CronSpec(frozenset(sets[0]), frozenset(sets[1]), frozenset(sets[2]), frozenset(sets[3]), weekdays,
                    stars[2], stars[4], text)


def _zone(tz: str | None) -> _dt.tzinfo:
    return ZoneInfo(tz) if tz else _dt.UTC


def next_fire(spec: CronSpec, after: _dt.datetime, tz: str | None = None) -> _dt.datetime | None:
    """The first fire strictly after `after` (an aware instant), in the zone the CronJob runs in; None
    if none within 366 days (a February-30th kind of schedule)."""
    local = after.astimezone(_zone(tz))
    start = local.replace(second=0, microsecond=0)
    hours, minutes = sorted(spec.hours), sorted(spec.minutes)
    for offset in range(0, 367):
        day = (start + _dt.timedelta(days=offset)).date() if offset else start.date()
        if not spec.day_matches(day):
            continue
        for h in hours:
            for m in minutes:
                candidate = _dt.datetime(day.year, day.month, day.day, h, m, tzinfo=local.tzinfo)
                if candidate > local:
                    return candidate.astimezone(_dt.UTC)
    return None


def prev_fire(spec: CronSpec, before: _dt.datetime, tz: str | None = None) -> _dt.datetime | None:
    """The last fire at or before `before` — when the schedule should most recently have run."""
    local = before.astimezone(_zone(tz))
    start = local.replace(second=0, microsecond=0)
    hours, minutes = sorted(spec.hours, reverse=True), sorted(spec.minutes, reverse=True)
    for offset in range(0, 367):
        day = (start - _dt.timedelta(days=offset)).date()
        if not spec.day_matches(day):
            continue
        for h in hours:
            for m in minutes:
                candidate = _dt.datetime(day.year, day.month, day.day, h, m, tzinfo=local.tzinfo)
                if candidate <= local:
                    return candidate.astimezone(_dt.UTC)
    return None


_DOW = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
_MONTHS = ("", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def describe(expr: str) -> str:
    """A cadence a person reads on the status page — `Daily 02:00`, `Weekly Mon 06:00`, `1st & 16th
    06:00`, `Quarterly 06:00` — and the expression itself when it is none of those shapes."""
    try:
        spec = parse(expr)
    except CronError:
        return expr
    if len(spec.hours) != 1 or len(spec.minutes) != 1:
        return expr
    clock = f"{next(iter(spec.hours)):02d}:{next(iter(spec.minutes)):02d}"
    all_months = len(spec.months) == 12
    if spec.days_star and spec.weekdays_star and all_months:
        return f"Daily {clock}"
    if spec.days_star and all_months:
        names = " & ".join(_DOW[d] for d in sorted(spec.weekdays))
        return f"{'Weekdays' if spec.weekdays == frozenset(range(1, 6)) else 'Weekly ' + names} {clock}"
    if spec.weekdays_star:
        days = " & ".join(_ordinal(d) for d in sorted(spec.days))
        if all_months:
            return f"{'Monthly ' if len(spec.days) == 1 else ''}{days} {clock}"
        if spec.months == frozenset((1, 4, 7, 10)) and spec.days == frozenset((1,)):
            return f"Quarterly {clock}"
        if len(spec.months) == 1 and len(spec.days) == 1:
            return f"Yearly {_MONTHS[next(iter(spec.months))]} {days} {clock}"
        return f"{days} of {', '.join(_MONTHS[m] for m in sorted(spec.months))} {clock}"
    return expr
