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


# ── review of #221 (OB3): the two DST transitions, and the words for a list that means every day ──

def _minutes(start, n):
    from datetime import timedelta
    return (start + timedelta(minutes=i) for i in range(n))


@pytest.mark.parametrize("expr", ["30 2 * * *", "0 2 * * *", "30 1 * * *", "*/15 * * * *"])
def test_next_is_strictly_after_and_prev_at_or_before_through_both_new_york_dst_transitions(expr):
    # Measured before the fix: `candidate > local` compared wall times in one zone, which ignores `fold`,
    # so in the repeated 01:xx EST hour next_fire returned an instant up to 45 minutes in the PAST and
    # prev_fire skipped the 05:30Z fire; on the spring-forward day a 02:30 schedule's prev_fire sat in
    # the future (07:30Z at 07:00Z). Kubernetes' cron steps real time: no fire in a gap, two in an overlap.
    spec = cron.parse(expr)
    for start in (datetime(2026, 3, 8, 4, 0, tzinfo=UTC), datetime(2026, 11, 1, 3, 0, tzinfo=UTC)):
        last_n = last_p = None
        for at in _minutes(start, 8 * 60):
            n, p = cron.next_fire(spec, at, "America/New_York"), cron.prev_fire(spec, at, "America/New_York")
            assert n > at, (expr, at, n)
            assert p <= at, (expr, at, p)
            assert last_n is None or n >= last_n, (expr, at, last_n, n)
            assert last_p is None or p >= last_p, (expr, at, last_p, p)
            last_n, last_p = n, p


def test_a_fire_in_the_spring_forward_gap_is_skipped_and_a_fire_in_the_fall_back_overlap_happens_twice():
    ny = "America/New_York"
    daily_0230 = cron.parse("30 2 * * *")
    # 2026-03-08: 02:00 EST → 03:00 EDT; 02:30 does not exist, so that day has no fire (Kubernetes skips it)
    assert cron.next_fire(daily_0230, datetime(2026, 3, 8, 6, 0, tzinfo=UTC), ny) == datetime(2026, 3, 9, 6, 30, tzinfo=UTC)
    assert cron.prev_fire(daily_0230, datetime(2026, 3, 8, 7, 0, tzinfo=UTC), ny) == datetime(2026, 3, 7, 7, 30, tzinfo=UTC)
    daily_0130 = cron.parse("30 1 * * *")
    # 2026-11-01: 02:00 EDT → 01:00 EST; 01:30 happens at 05:30Z (EDT) and again at 06:30Z (EST)
    assert cron.next_fire(daily_0130, datetime(2026, 11, 1, 4, 0, tzinfo=UTC), ny) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert cron.next_fire(daily_0130, datetime(2026, 11, 1, 5, 30, tzinfo=UTC), ny) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert cron.next_fire(daily_0130, datetime(2026, 11, 1, 6, 15, tzinfo=UTC), ny) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert cron.prev_fire(daily_0130, datetime(2026, 11, 1, 6, 15, tzinfo=UTC), ny) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert cron.prev_fire(daily_0130, datetime(2026, 11, 1, 6, 45, tzinfo=UTC), ny) == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)


@pytest.mark.parametrize("expr,cadence", [
    ("0 6 * 1,4,7,10 *", "0 6 * 1,4,7,10 *"),     # every day of four months: no name, the expression (was 31 ordinals)
    ("0 6 * * 0-6", "Daily 06:00"),                # every weekday listed IS daily (was "Weekly Sun & Mon & … & Sat")
    ("0 6 * * 1-7", "Daily 06:00"),
    ("0 6 1-31 * *", "Daily 06:00"),
    ("0 6 */2 * *", "0 6 */2 * *"),                # sixteen dates: past four the list stops reading
    ("0 6 1,8,15,22 * *", "1st & 8th & 15th & 22nd 06:00"),
    ("0 6 1 * 1-5", "0 6 1 * 1-5"),                # both restricted: the expression stands
])
def test_a_list_that_means_every_day_is_daily_and_a_long_list_is_the_expression(expr, cadence):
    assert cron.describe(expr) == cadence
