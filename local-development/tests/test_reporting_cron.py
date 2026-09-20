"""gsd.reporting.cron — the five-field expression as Kubernetes reads it (#149 R6)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from gsd.reporting import cron

NOW = datetime(2026, 9, 20, 5, 30, tzinfo=UTC)      # Sunday 01:30 EDT


@pytest.mark.parametrize("expr,cadence,nxt,prv", [
    ("0 6 1 1,4,7,10 *", "Quarterly 06:00", "2026-10-01T10:00Z", "2026-07-01T10:00Z"),
    ("0 6 1,16 * *", "1st & 16th 06:00", "2026-10-01T10:00Z", "2026-09-16T10:00Z"),
    ("0 2 * * *", "Daily 02:00", "2026-09-20T06:00Z", "2026-09-19T06:00Z"),
    ("0 6 * * 1", "Weekly Mon 06:00", "2026-09-21T10:00Z", "2026-09-14T10:00Z"),
    ("0 9 * * 1-5", "Weekdays 09:00", "2026-09-21T13:00Z", "2026-09-18T13:00Z"),
    ("@daily", "Daily 00:00", "2026-09-21T04:00Z", "2026-09-20T04:00Z"),
    ("30 4 15 3 *", "Yearly Mar 15th 04:30", "2027-03-15T08:30Z", "2026-03-15T08:30Z"),
    ("0 6 1 * *", "Monthly 1st 06:00", "2026-10-01T10:00Z", "2026-09-01T10:00Z"),
])
def test_next_previous_and_cadence_in_new_york(expr, cadence, nxt, prv):
    spec = cron.parse(expr)
    assert cron.describe(expr) == cadence
    assert cron.next_fire(spec, NOW, "America/New_York").strftime("%Y-%m-%dT%H:%MZ") == nxt
    assert cron.prev_fire(spec, NOW, "America/New_York").strftime("%Y-%m-%dT%H:%MZ") == prv


def test_steps_lists_and_utc():
    spec = cron.parse("*/15 * * * *")
    assert cron.next_fire(spec, NOW).strftime("%H:%M") == "05:45" and cron.prev_fire(spec, NOW).strftime("%H:%M") == "05:30"
    assert cron.describe("*/15 * * * *") == "*/15 * * * *"       # not a shape a person names; the expression stands
    spec = cron.parse("5 0,12 * * *")
    assert sorted(spec.hours) == [0, 12] and spec.minutes == frozenset({5})


def test_day_of_month_and_day_of_week_both_restricted_match_either():
    # Vixie cron and Kubernetes: `0 0 13 * 5` fires on the 13th AND on every Friday.
    spec = cron.parse("0 0 13 * 5")
    fri = datetime(2026, 9, 17, 12, 0, tzinfo=UTC)          # Thursday noon
    assert cron.next_fire(spec, fri).strftime("%Y-%m-%d") == "2026-09-18"   # Friday, not the 13th
    assert cron.next_fire(spec, datetime(2026, 11, 7, 0, 0, tzinfo=UTC)).strftime("%Y-%m-%d") == "2026-11-13"


def test_sunday_is_0_or_7_and_bad_expressions_are_refused():
    assert cron.parse("0 0 * * 7").weekdays == cron.parse("0 0 * * 0").weekdays == frozenset({0})
    for bad in ("0 0 * *", "60 0 * * *", "0 0 32 * *", "0 0 * 13 *", "a b c d e", "0 0 * * */0"):
        with pytest.raises(cron.CronError):
            cron.parse(bad)


def test_a_schedule_that_never_fires_yields_none():
    assert cron.next_fire(cron.parse("0 0 30 2 *"), NOW) is None      # February 30th
