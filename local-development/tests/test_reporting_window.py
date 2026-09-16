"""The reporting-window predicate (design §5) — the pure core the create_run gate and the worker
recheck both call. Boundaries are half-open [start, end); a wrap window splits at midnight with the
post-midnight part belonging to the previous day; construction fails closed on anything malformed."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from gsd.reporting.window import ReportingWindow, WindowConfigError, WEEKDAYS

ALL = list(WEEKDAYS)


def _w(**kw) -> ReportingWindow:
    base = dict(enabled=True, timezone="UTC", start="09:00", end="17:00", days=list(WEEKDAYS))
    base.update(kw)
    return ReportingWindow.from_strings(**base)


def _at(day: str, hhmm: str, tz: str = "UTC") -> dt.datetime:
    # A timezone-aware instant on the given weekday (a fixed reference week: 2026-09-14 is a Monday).
    monday = dt.date(2026, 9, 14)
    d = monday + dt.timedelta(days=WEEKDAYS.index(day))
    h, m = map(int, hhmm.split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(tz))


class TestSameDayWindow:
    def test_half_open_boundaries(self):
        w = _w(start="09:00", end="17:00", days=["Mon"])
        assert w.contains(_at("Mon", "09:00"))          # start is inclusive
        assert w.contains(_at("Mon", "16:59"))
        assert not w.contains(_at("Mon", "17:00"))      # end is exclusive
        assert not w.contains(_at("Mon", "08:59"))

    def test_day_membership(self):
        w = _w(start="09:00", end="17:00", days=["Mon", "Tue", "Wed", "Thu", "Fri"])
        assert w.contains(_at("Fri", "12:00"))
        assert not w.contains(_at("Sat", "12:00"))
        assert not w.contains(_at("Sun", "12:00"))


class TestWrapWindow:
    def test_post_midnight_belongs_to_yesterday(self):
        # Sunday 22:00 -> Monday 06:00, days = {Sun} only.
        w = _w(start="22:00", end="06:00", days=["Sun"])
        assert w.contains(_at("Sun", "22:00"))          # Sunday evening: today in days
        assert w.contains(_at("Sun", "23:59"))
        assert w.contains(_at("Mon", "02:00"))          # Monday 02:00 belongs to SUNDAY's window
        assert w.contains(_at("Mon", "05:59"))
        assert not w.contains(_at("Mon", "06:00"))      # end exclusive
        assert not w.contains(_at("Mon", "22:00"))      # Monday night is not Sunday's window (Mon not in days)
        assert not w.contains(_at("Sun", "05:00"))      # Sunday 05:00 belongs to Saturday's window (Sat not in days)

    def test_wrap_with_all_days(self):
        w = _w(start="22:00", end="06:00", days=ALL)
        assert w.contains(_at("Wed", "23:00"))
        assert w.contains(_at("Thu", "01:00"))          # belongs to Wed's window; Wed in days
        assert not w.contains(_at("Wed", "12:00"))


class TestTimezoneLocalization:
    def test_utc_now_is_localized_to_the_window_zone(self):
        # Window 22:00-06:00 America/New_York, Mondays. 2026-09-15 02:00 UTC == 2026-09-14 22:00 EDT (Mon).
        w = _w(start="22:00", end="06:00", days=["Mon"], timezone="America/New_York")
        assert w.is_open(dt.datetime(2026, 9, 15, 2, 0, tzinfo=ZoneInfo("UTC")))
        # 2026-09-15 12:00 UTC == 08:00 EDT Monday — outside.
        assert not w.is_open(dt.datetime(2026, 9, 15, 12, 0, tzinfo=ZoneInfo("UTC")))

    def test_naive_now_is_rejected(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            _w().is_open(dt.datetime(2026, 9, 14, 12, 0))


class TestDisabledWindow:
    def test_disabled_is_always_open(self):
        w = ReportingWindow.from_strings(enabled=False, timezone="", start="09:00", end="17:00", days=[])
        assert w.is_open(_at("Sat", "03:00"))           # disabled never gates, even off-hours
        assert w.seconds_until_open(_at("Sat", "03:00")) == 0


class TestSecondsUntilOpen:
    def test_zero_when_open(self):
        assert _w(days=["Mon"]).seconds_until_open(_at("Mon", "10:00")) == 0

    def test_same_day_before_start(self):
        w = _w(start="09:00", end="17:00", days=["Mon"])
        assert w.seconds_until_open(_at("Mon", "08:00")) == 3600      # opens at 09:00, one hour out

    def test_next_allowed_day(self):
        w = _w(start="09:00", end="17:00", days=["Wed"])
        secs = w.seconds_until_open(_at("Mon", "10:00"))             # next Wed 09:00
        assert secs == (2 * 24 * 3600 - 3600)                        # Mon 10:00 -> Wed 09:00

    def test_retry_after_never_lands_early(self):
        w = _w(start="09:00", end="17:00", days=["Mon"])
        now = _at("Mon", "08:00").replace(second=30)
        assert not w.is_open(now.astimezone(ZoneInfo("UTC")) + dt.timedelta(seconds=w.seconds_until_open(now)) - dt.timedelta(seconds=1))


class TestValidationFailsClosed:
    @pytest.mark.parametrize("kw,needle", [
        (dict(start="9am"), "is not HH:MM"),
        (dict(start="25:00"), "not a valid 24h time"),
        (dict(start="12:60"), "not a valid 24h time"),
        (dict(start="12:00", end="12:00"), "start and end are equal"),
        (dict(days=[]), "days is empty"),
        (dict(days=["Mon", "Mon"]), "duplicate"),
        (dict(days=["Funday"]), "is not one of"),
        (dict(timezone=""), "timezone is empty"),
        (dict(timezone="Mars/Olympus"), "not a known IANA zone"),
    ])
    def test_malformed_enabled_window_raises(self, kw, needle):
        with pytest.raises(WindowConfigError, match=needle):
            _w(**kw)

    def test_day_names_are_case_insensitive(self):
        w = _w(days=["mon", "TUE", "weD"])
        assert w.contains(_at("Tue", "10:00"))


class TestWindowConfigEnv:
    """The GSD_REPORT_WINDOW_* env wiring in config.py (design §5) — disabled by default, fail-closed
    on a malformed enabled window (a startup failure, never log-and-disable)."""

    def _clear(self, mp):
        for k in ("GSD_REPORT_WINDOW_ENABLED", "GSD_REPORT_WINDOW_TIMEZONE", "GSD_REPORT_WINDOW_START",
                  "GSD_REPORT_WINDOW_END", "GSD_REPORT_WINDOW_DAYS"):
            mp.delenv(k, raising=False)

    def test_default_is_disabled(self, monkeypatch):
        from gsd.reporting.config import _window_env
        self._clear(monkeypatch)
        assert _window_env().enabled is False

    def test_enabled_valid(self, monkeypatch):
        from gsd.reporting.config import _window_env
        self._clear(monkeypatch)
        monkeypatch.setenv("GSD_REPORT_WINDOW_ENABLED", "true")
        monkeypatch.setenv("GSD_REPORT_WINDOW_TIMEZONE", "UTC")
        monkeypatch.setenv("GSD_REPORT_WINDOW_DAYS", '["Mon","Fri"]')
        w = _window_env()
        assert w.enabled and w.timezone == "UTC" and w.days == frozenset({0, 4})
        assert w.start == dt.time(22, 0) and w.end == dt.time(6, 0)     # the env defaults

    def test_malformed_days_json_fails_closed(self, monkeypatch):
        from gsd.reporting.config import _window_env, ReportConfigError
        self._clear(monkeypatch)
        monkeypatch.setenv("GSD_REPORT_WINDOW_ENABLED", "true")
        monkeypatch.setenv("GSD_REPORT_WINDOW_TIMEZONE", "UTC")
        monkeypatch.setenv("GSD_REPORT_WINDOW_DAYS", "not-json")
        with pytest.raises(ReportConfigError, match="not a JSON array"):
            _window_env()

    def test_enabled_but_no_days_fails_closed(self, monkeypatch):
        from gsd.reporting.config import _window_env, ReportConfigError
        self._clear(monkeypatch)
        monkeypatch.setenv("GSD_REPORT_WINDOW_ENABLED", "true")
        monkeypatch.setenv("GSD_REPORT_WINDOW_TIMEZONE", "UTC")
        with pytest.raises(ReportConfigError, match="days is empty"):
            _window_env()


class TestDSTTransitions:
    """DST edges (review of P4, C2/F1): a window inside the spring-forward gap never admits, is_open
    never raises across a transition, and seconds_until_open returns a Retry-After that lands OPEN —
    stepping the wall clock onto the nonexistent 02:xx would have promised a retry into a closed slot."""

    def test_spring_gap_never_admits_and_retry_lands_open(self):
        w = _w(timezone="America/New_York", start="02:15", end="02:45", days=["Sun"])
        utc = ZoneInfo("UTC")
        ny = ZoneInfo("America/New_York")
        real = [dt.datetime(2026, 3, 8, 5, 0, tzinfo=utc) + dt.timedelta(minutes=i) for i in range(241)]
        assert not any(w.is_open(x) for x in real)
        imaginary = dt.datetime(2026, 3, 8, 2, 30, tzinfo=ny)     # a nonexistent local time
        assert not w.contains(imaginary) and not w.is_open(imaginary)
        now = dt.datetime(2026, 3, 8, 6, 59, 30, tzinfo=utc)
        retry = w.seconds_until_open(now)
        assert w.is_open(now + dt.timedelta(seconds=retry))

    def test_autumn_second_fold_is_found_in_real_time(self):
        w = _w(timezone="America/New_York", start="01:15", end="01:45", days=["Sun"])
        now = dt.datetime(2026, 11, 1, 5, 50, tzinfo=ZoneInfo("UTC"))
        retry = w.seconds_until_open(now)
        assert retry == 25 * 60
        landing = now + dt.timedelta(seconds=retry)
        assert landing.astimezone(ZoneInfo("America/New_York")).fold == 1
        assert w.is_open(landing)
