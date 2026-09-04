"""Tests for the derived-state logic.

These cover the two places the design is easiest to get wrong: the cron interval maths
behind `late`/`overdue`, and the sticky ReconcileError condition.
"""

from datetime import UTC, datetime, timedelta

import pytest

from gsd import state as st

HOURLY = "0 * * * *"
HALF_HOURLY = "*/30 * * * *"
GRACE = timedelta(seconds=120)


def t(iso: str) -> datetime:
    return datetime.fromisoformat(iso).replace(tzinfo=UTC)


class TestScheduleInterval:
    def test_hourly_and_half_hourly_differ(self):
        """The whole point of a real cron parser: these two look identical at :00."""
        at = t("2026-08-01T09:15:00")
        assert st.schedule_interval(HOURLY, at) == timedelta(hours=1)
        assert st.schedule_interval(HALF_HOURLY, at) == timedelta(minutes=30)

    def test_irregular_cron_uses_local_gap(self):
        """`0 9,17 * * *` alternates 8h and 16h; the interval is the gap that just passed."""
        assert st.schedule_interval("0 9,17 * * *", t("2026-08-01T18:00:00")) == timedelta(hours=8)
        assert st.schedule_interval("0 9,17 * * *", t("2026-08-01T10:00:00")) == timedelta(hours=16)

    def test_invalid_schedule_is_none(self):
        assert st.schedule_interval("not a cron", t("2026-08-01T09:00:00")) is None
        assert st.schedule_interval("", t("2026-08-01T09:00:00")) is None


class TestNextExpected:
    def test_distinguishes_the_two_schedules_at_half_past(self):
        now = t("2026-08-01T09:15:00")
        assert st.next_expected(HOURLY, now) == t("2026-08-01T10:00:00")
        assert st.next_expected(HALF_HOURLY, now) == t("2026-08-01T09:30:00")

    def test_is_always_in_the_future_even_for_a_broken_cr(self):
        """Anchoring on a stale last-sync would return a past time for exactly the CRs
        that are already broken, which reads as a bug rather than as information."""
        now = t("2026-08-01T09:15:00")
        assert st.next_expected(HOURLY, now) > now


class TestComputeState:
    def test_fresh_sync_is_ok(self):
        now = t("2026-08-01T09:05:00")
        assert st.compute_state(t("2026-08-01T09:00:05"), HOURLY, now, GRACE) == st.OK

    def test_late_then_overdue(self):
        now = t("2026-08-01T12:00:00")
        assert st.compute_state(t("2026-08-01T10:30:00"), HOURLY, now, GRACE) == st.LATE
        assert st.compute_state(t("2026-08-01T09:00:00"), HOURLY, now, GRACE) == st.OVERDUE

    def test_healthy_cr_does_not_flap_to_late_between_firing_and_being_observed(self):
        """Regression: the plan's literal thresholds flap once per cycle.

        The window is *after* the next sync fires but *before* our poll sees it. The
        operator fires at 10:00:07 (3-14s of scheduler latency was measured on CRC), but
        our stored last_sync is still 09:00:07 until the next poll lands up to 60s later.
        For those ~70s the observed age exceeds one full interval even though nothing is
        wrong, so `ok: age <= interval` reports `late` on every single cycle.
        """
        last_sync = t("2026-08-01T09:00:07")
        fired_but_not_yet_polled = t("2026-08-01T10:00:50")
        assert (fired_but_not_yet_polled - last_sync) > timedelta(hours=1)  # premise of the bug
        assert st.compute_state(last_sync, HOURLY, fired_but_not_yet_polled, GRACE) == st.OK

    def test_grace_does_not_mask_a_genuinely_overdue_cr(self):
        """Grace shifts the boundary; it must not widen it into hiding a real failure."""
        now = t("2026-08-01T12:30:00")
        assert st.compute_state(t("2026-08-01T09:00:00"), HOURLY, now, GRACE) == st.OVERDUE

    def test_unreachable_and_never_synced_are_unknown(self):
        now = t("2026-08-01T12:00:00")
        assert st.compute_state(t("2026-08-01T11:59:00"), HOURLY, now, GRACE, reachable=False) == st.UNKNOWN
        assert st.compute_state(None, HOURLY, now, GRACE) == st.UNKNOWN

    def test_unparseable_schedule_is_unknown_not_overdue(self):
        """An unreadable schedule is missing information, not evidence of failure."""
        now = t("2026-08-01T12:00:00")
        assert st.compute_state(t("2026-08-01T01:00:00"), "banana", now, GRACE) == st.UNKNOWN


class TestReconcileErrorIsCurrent:
    def test_stale_error_alongside_newer_success_is_not_current(self):
        """The observed CRC case: a 2026-07-30 error still at status=True on 2026-08-01,
        never cleared by ~100 successful syncs since."""
        assert not st.reconcile_error_is_current(
            t("2026-07-30T15:16:17"), t("2026-08-01T07:00:10")
        )

    def test_error_newer_than_success_is_current(self):
        assert st.reconcile_error_is_current(t("2026-08-01T08:00:00"), t("2026-08-01T07:00:10"))

    def test_error_with_no_success_ever_is_current(self):
        assert st.reconcile_error_is_current(t("2026-07-30T15:16:17"), None)

    def test_no_error_is_never_current(self):
        assert not st.reconcile_error_is_current(None, t("2026-08-01T07:00:10"))


class TestStaleGroupThreshold:
    def test_threshold_clears_the_intra_sync_write_window(self):
        """PLAN §3.1: one sync stamps its groups across ~10s and the CR last, so equality
        would report the earliest-written groups as stale on every healthy cycle."""
        window = timedelta(minutes=2)
        assert st.stale_group_threshold(timedelta(seconds=30), window) >= window
        assert st.stale_group_threshold(None, window) == window

    def test_threshold_grows_with_the_interval(self):
        assert st.stale_group_threshold(timedelta(hours=1), timedelta(minutes=2)) == timedelta(hours=1)


class TestAlerts:
    def _cr(self, **kw):
        base = {
            "name": "ldap-groupsync",
            "schedule": HALF_HOURLY,
            "last_sync_at": "2026-08-01T09:00:00Z",
            "provider_keys": ["ldap-groupsync_ldap"],
        }
        base.update(kw)
        return base

    def _group(self, **kw):
        base = {
            "name": "app-ocp-rbac-alpha-ns-admin",
            "member_count": 2,
            "sync_provider": "ldap-groupsync_ldap",
            "group_synced_at": "2026-08-01T09:00:00Z",
        }
        base.update(kw)
        return base

    def test_clean_cluster_has_no_alerts(self):
        now = t("2026-08-01T09:10:00")
        assert st.compute_alerts("crc", [self._cr()], [self._group()], now, GRACE) == []

    def test_empty_and_unattributed_groups_alert(self):
        now = t("2026-08-01T09:10:00")
        groups = [
            self._group(name="empty-one", member_count=0),
            self._group(name="orphan", sync_provider=None),
        ]
        kinds = {a.kind for a in st.compute_alerts("crc", [self._cr()], groups, now, GRACE)}
        assert kinds == {"empty_group", "unattributed"}

    def test_unattributed_group_is_not_also_reported_as_empty(self):
        """Caught on CRC: a hand-made `oc adm groups new` group has zero members, and was
        being alerted as 'synced with zero members' — which it never was. NOTE the `empty`
        FILTER does return such a group (see test_no_groupsync_operator.py); only the ALERT is
        provenance-scoped, because the alert carries an LDAP-side remedy. EMPTY here means an
        operator-managed group whose members vanished (PLAN §7); this is a different fault
        with a different fix, and double-reporting it says the wrong thing twice.
        """
        now = t("2026-08-01T09:10:00")
        groups = [self._group(name="gsd-test-unattributed", member_count=0, sync_provider=None)]
        alerts = st.compute_alerts("crc", [self._cr()], groups, now, GRACE)
        assert [a.kind for a in alerts] == ["unattributed"]

    def test_overdue_cr_alerts_as_critical(self):
        now = t("2026-08-01T11:00:00")
        alerts = st.compute_alerts("crc", [self._cr()], [self._group()], now, GRACE)
        overdue = [a for a in alerts if a.kind == "overdue"]
        assert len(overdue) == 1 and overdue[0].severity == "critical"

    def test_stale_group_detected_while_cr_looks_healthy(self):
        """The failure the CR status cannot show: 39 of 40 groups refreshed."""
        now = t("2026-08-01T09:10:00")
        groups = [
            self._group(name="fresh"),
            self._group(name="forgotten", group_synced_at="2026-08-01T06:00:00Z"),
        ]
        alerts = st.compute_alerts("crc", [self._cr()], groups, now, GRACE)
        stale = [a for a in alerts if a.kind == "stale_group"]
        assert len(stale) == 1 and stale[0].subject == "forgotten"

    def test_stale_group_of_a_later_provider_is_still_detected(self):
        """The regression this guards: attribution once kept only the FIRST provider key of
        a multi-provider CR, so a stale group belonging to the second was matched by no CR
        and checked by nothing. It was not reported as unattributed either — it carries a
        perfectly good label — so it left no trace anywhere. Silence, not a wrong answer."""
        now = t("2026-08-01T09:10:00")
        cr = self._cr(name="corp", provider_keys=["corp_ldap-a", "corp_ldap-b"])
        groups = [
            self._group(name="from-a", sync_provider="corp_ldap-a"),
            self._group(
                name="from-b", sync_provider="corp_ldap-b", group_synced_at="2026-08-01T06:00:00Z"
            ),
        ]
        stale = [a for a in st.compute_alerts("crc", [cr], groups, now, GRACE) if a.kind == "stale_group"]
        assert [a.subject for a in stale] == ["from-b"]

    def test_intra_sync_write_window_does_not_alert(self):
        """A group stamped 10s before its CR is normal, not stale (PLAN §3.1)."""
        now = t("2026-08-01T09:10:00")
        groups = [self._group(group_synced_at="2026-08-01T08:59:50Z")]
        alerts = st.compute_alerts("crc", [self._cr()], groups, now, GRACE)
        assert [a for a in alerts if a.kind == "stale_group"] == []

    def test_stale_reconcile_error_does_not_alert(self):
        now = t("2026-08-01T09:10:00")
        cr = self._cr(error_at="2026-07-30T15:16:17Z", error_message="kyverno webhook down")
        alerts = st.compute_alerts("crc", [cr], [self._group()], now, GRACE)
        assert [a for a in alerts if a.kind == "reconcile_error"] == []

    def test_current_reconcile_error_alerts(self):
        now = t("2026-08-01T09:10:00")
        cr = self._cr(error_at="2026-08-01T09:05:00Z", error_message="LDAP bind failed")
        alerts = st.compute_alerts("crc", [cr], [self._group()], now, GRACE)
        errs = [a for a in alerts if a.kind == "reconcile_error"]
        assert len(errs) == 1 and "LDAP bind failed" in errs[0].detail


@pytest.mark.parametrize(
    "value,expected_none",
    [("2026-08-01T07:00:10Z", False), (None, True), ("", True), ("not-a-time", True)],
)
def test_parse_time_is_total(value, expected_none):
    """A malformed timestamp must not crash a poll — it degrades to 'unknown'."""
    assert (st.parse_time(value) is None) is expected_none


class TestStoppedSyncWithUnusableSchedule:
    """Found adversarially: a CR whose schedule cannot be parsed fell into `unknown`, and
    `unknown` alerts on nothing — so a CR that had stopped syncing for days reported
    complete silence. The worst failure class for this dashboard."""

    def _cr(self, schedule, last_sync):
        return {"name": "cr", "schedule": schedule,
                "last_sync_at": last_sync.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "provider_keys": ["cr_ldap"]}

    @pytest.mark.parametrize("schedule", ["not-a-cron", None, "", "* * *"])
    def test_unusable_schedule_alerts_even_though_state_is_unknown(self, schedule):
        now = t("2026-08-01T12:00:00")
        long_ago = now - timedelta(days=3)
        alerts = st.compute_alerts("crc", [self._cr(schedule, long_ago)], [], now, GRACE)
        kinds = {a.kind for a in alerts}
        assert "invalid_schedule" in kinds, "the config defect itself must be reported"
        assert "sync_stopped" in kinds, "a 3-day-old sync must not be silent"
        assert st.compute_state(long_ago, schedule, now, GRACE) == st.UNKNOWN

    def test_recent_sync_with_bad_schedule_reports_config_not_stoppage(self):
        """A bad schedule is always a defect, but a CR that synced minutes ago has not
        stopped — saying so would be a false alarm."""
        now = t("2026-08-01T12:00:00")
        alerts = st.compute_alerts(
            "crc", [self._cr("not-a-cron", now - timedelta(minutes=5))], [], now, GRACE
        )
        kinds = {a.kind for a in alerts}
        assert "invalid_schedule" in kinds
        assert "sync_stopped" not in kinds

    def test_valid_schedule_is_unaffected(self):
        now = t("2026-08-01T12:00:00")
        alerts = st.compute_alerts(
            "crc", [self._cr("*/30 * * * *", now - timedelta(minutes=2))], [], now, GRACE
        )
        assert alerts == []


class TestGroupCountCliff:
    """docs/specs/SPEC_B4_group_count_cliff.md B4: before = after + removed - added."""

    NOW = t("2026-09-04T12:00:00")
    POLICY = st.CliffPolicy(min_members=10, drop_ratio=0.5, window_hours=24.0)

    def _group(self, name="app-ocp-rbac-team-ns-view", member_count=5, **kw):
        return {"name": name, "member_count": member_count, "sync_provider": "ldap-groupsync_ldap",
                "group_synced_at": "2026-09-04T11:00:00Z", **kw}

    def _alerts(self, groups, changes, policy=POLICY):
        return [a for a in st.compute_alerts("crc", [], groups, self.NOW, GRACE,
                                             count_changes=changes, cliff=policy)
                if a.kind.startswith("group_count_cliff")]

    def test_fires_exactly_at_the_floor_and_the_ratio(self):
        # before = 5 + 5 - 0 = 10 (the floor), drop 5/10 = 0.5 (the ratio): both boundaries inclusive.
        got = self._alerts([self._group(member_count=5)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
        assert [a.kind for a in got] == ["group_count_cliff"]
        assert got[0].severity == "warning" and not got[0].silenced and got[0].silenced_by is None
        assert "members 10 -> 5" in got[0].detail and "24h" in got[0].detail

    def test_one_below_the_floor_is_silent(self):
        # before = 4 + 5 = 9 < 10, even though the ratio (5/9) clears 0.5.
        assert self._alerts([self._group(member_count=4)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}) == []

    def test_just_under_the_ratio_is_silent(self):
        # before = 11 + 9 = 20, drop 9/20 = 0.45 < 0.5.
        assert self._alerts([self._group(member_count=11)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 9}}) == []

    def test_a_recovered_group_nets_out(self):
        # 20 -> 5 -> 18 inside the window: before = 18 + 15 - 13 = 20, drop 2/20.
        assert self._alerts([self._group(member_count=18)], {"app-ocp-rbac-team-ns-view": {"added": 13, "removed": 15}}) == []

    def test_a_brand_new_group_has_no_before(self):
        # Every member was `added` inside the window: before = 50 - 50 = 0.
        assert self._alerts([self._group(member_count=50)], {"app-ocp-rbac-team-ns-view": {"added": 50, "removed": 0}}) == []

    def test_a_group_with_no_events_or_no_state_is_not_evaluated(self):
        assert self._alerts([self._group(member_count=5)], {}) == []
        # events for a deleted group (absent from group_state) are the dangling finding's job
        assert self._alerts([], {"gone": {"added": 0, "removed": 40}}) == []

    def test_module_off_computes_nothing(self):
        assert self._alerts([self._group(member_count=0)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 40}}, policy=None) == []

    def test_silenced_by_annotation_true_is_reported_not_dropped(self):
        got = self._alerts([self._group(member_count=5, cliff_silence="true")], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
        assert [(a.kind, a.silenced, a.silenced_by) for a in got] == [("group_count_cliff_silenced", True, "annotation")]
        assert "members 10 -> 5" in got[0].detail, "the numbers stay; only the kind changes"

    def test_silenced_until_a_future_or_todays_date(self):
        for value in ("until=2026-09-04", "until=2026-12-31", " UNTIL=2026-09-05 "):
            got = self._alerts([self._group(member_count=5, cliff_silence=value)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
            assert got[0].kind == "group_count_cliff_silenced", value

    def test_an_expired_or_malformed_until_unsilences(self):
        for value in ("until=2026-09-03", "until=yesterday", "maybe", ""):
            got = self._alerts([self._group(member_count=5, cliff_silence=value)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}})
            assert got[0].kind == "group_count_cliff", value

    def test_silenced_by_values_glob(self):
        policy = st.CliffPolicy(min_members=10, drop_ratio=0.5, window_hours=24.0,
                                silence=("app-ocp-rbac-team-*",))
        got = self._alerts([self._group(member_count=5)], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert (got[0].kind, got[0].silenced_by) == ("group_count_cliff_silenced", "values")
        other = self._alerts([self._group(name="app-ocp-rbac-ops-ns-view", member_count=5)], {"app-ocp-rbac-ops-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert other[0].kind == "group_count_cliff", "globs are exact and case-sensitive"

    def test_annotation_wins_over_values_in_the_reason(self):
        policy = st.CliffPolicy(silence=("*",))
        got = self._alerts([self._group(member_count=5, cliff_silence="true")], {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 5}}, policy=policy)
        assert got[0].silenced_by == "annotation"

    def test_the_ratio_boundary_is_inclusive_in_exact_arithmetic(self):
        """0.07 * 100 is 7.000000000000001 as a double, so `drop < ratio * before` missed a drop of
        exactly seven in a hundred — the boundary the values promise fires. Measured: 141 such
        boundaries among two-decimal ratios and group sizes up to 1000. Found in review (PR #72)."""
        for ratio, before, drop in ((0.07, 100, 7), (0.07, 300, 21), (0.3, 10, 3), (0.15, 20, 3)):
            policy = st.CliffPolicy(min_members=10, drop_ratio=ratio, window_hours=24.0)
            got = self._alerts([self._group(member_count=before - drop)],
                               {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": drop}}, policy=policy)
            assert [a.kind for a in got] == ["group_count_cliff"], (ratio, before, drop)
            assert f"members {before} -> {before - drop}" in got[0].detail
        one_under = st.CliffPolicy(min_members=10, drop_ratio=0.3, window_hours=24.0)
        assert self._alerts([self._group(member_count=8)],
                            {"app-ocp-rbac-team-ns-view": {"added": 0, "removed": 2}}, policy=one_under) == []

    def test_since_is_in_the_pollers_timestamp_format(self):
        assert self.POLICY.since(self.NOW) == "2026-09-03T12:00:00Z"

    def test_as_dict_carries_the_silence_fields_for_every_kind(self):
        plain = st.Alert("crc", "overdue", "x", "y", "critical").as_dict()
        assert plain["silenced"] is False and plain["silenced_by"] is None
