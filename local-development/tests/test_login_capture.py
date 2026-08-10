"""Login-capture storage, against shapes taken off the live cluster.

Written from defects found by DEPLOYING, not by reviewing. Each class below names the thing that was
wrong on the cluster and what the row said at the time, because the assertion on its own does not
explain why anyone would think to write it.

Rows are built through gsd.logincapture.event_dict() from real LoginAttempt objects rather than
hand-assembled dicts, so a fixture cannot drift from what the capture loop actually writes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gsd import loginlog
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store

HTPASSWD = ("developer",)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "logins.db"))
    s.upsert_cluster("crc-local", "https://api.crc.testing:6443", True)
    yield s
    s.close()


def _record(store, attempts, pod="oauth-openshift-aaa", observed=None):
    """attempts: list of (user, outcome, seconds_ago, provider)."""
    now = datetime.now(UTC)
    rows = [
        event_dict(LoginAttempt(user, outcome, now - timedelta(seconds=ago), provider=provider),
                   pod, observed or _iso(now))
        for user, outcome, ago, provider in attempts
    ]
    return store.record_login_events("crc-local", rows)


class TestTheUngovernedRowDescribesOneSetOfAttempts:
    """The defect: `kubeadmin — 1 attempt, last seen 19:55:58, last outcome signed in`.

    Reproduced from the live record exactly. kubeadmin had three attempts: two successes on the
    HTPasswd provider (excluded — a break-glass account has no synced group to belong to) and one
    `rejected` on the directory provider. The count, first_at and last_at correctly described the one
    directory attempt while `last_outcome` was read from ALL of them, so the row reported an outcome
    belonging to an attempt it claimed not to count.
    """

    def _kubeadmin(self, store):
        _record(store, [
            ("kubeadmin", loginlog.OUTCOME_SUCCESS, 1700, "developer"),    # 19:51:37, excluded
            ("kubeadmin", loginlog.OUTCOME_REJECTED, 1440, "ldap-local"),  # 19:55:58, counted
            ("kubeadmin", loginlog.OUTCOME_SUCCESS, 540, "developer"),     # 20:10:59, excluded
        ])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        return next(r for r in rows if r["user_name"] == "kubeadmin")

    def test_the_last_outcome_comes_from_a_counted_attempt(self, store):
        row = self._kubeadmin(store)
        assert row["attempts"] == 1, row
        assert row["last_outcome"] == loginlog.OUTCOME_REJECTED, (
            "last_outcome was read from a row this line excludes — it said 'success', from the "
            "20:10:59 break-glass attempt, beside a last_at of 19:55:58"
        )

    def test_last_at_and_last_outcome_agree(self, store):
        """Stated as its own test because it is the invariant, not the example.

        Whatever the exclusion is, the newest COUNTED attempt is the one whose outcome is shown.
        """
        row = self._kubeadmin(store)
        counted = [a for a in store.login_events("crc-local", user_name="kubeadmin")
                   if a["provider"] not in HTPASSWD]
        newest = max(counted, key=lambda a: a["at"])
        assert row["last_at"] == newest["at"]
        assert row["last_outcome"] == newest["outcome"]

    def test_with_no_exclusions_every_attempt_counts(self, store):
        """The subquery must not acquire a filter of its own when there is nothing to exclude."""
        self._kubeadmin(store)
        row = next(r for r in store.ungoverned_login_users("crc-local", exclude_providers=())
                   if r["user_name"] == "kubeadmin")
        assert row["attempts"] == 3
        assert row["last_outcome"] == loginlog.OUTCOME_SUCCESS, (
            "with nothing excluded the newest attempt IS the 20:10:59 success"
        )

    def test_the_count_and_the_list_cannot_disagree(self, store):
        """docs/api-contract.md requires a limited list to report its whole-set total.

        Both come from the same predicate through the same helper; this is what stops a future edit
        putting the filter in one and not the other.
        """
        _record(store, [(f"ghost{i}", loginlog.OUTCOME_REJECTED, 100 + i, "ldap-local")
                        for i in range(5)])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD, limit=3)
        total = store.count_ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        assert len(rows) == 3 and total == 5, (rows, total)


class TestBreakGlassExclusionIsPerAttempt:
    """A break-glass NAME can still appear, on the strength of a directory attempt.

    Deliberate, and the page says so. The rejected alternative was excluding any name ever seen on a
    local provider — reachable by anybody: type a real directory username at the HTPasswd form once
    and that person is excluded from the findings list permanently.
    """

    def test_an_account_only_ever_seen_on_a_local_provider_never_appears(self, store):
        _record(store, [("developer", loginlog.OUTCOME_SUCCESS, 60, "developer")])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        assert [r["user_name"] for r in rows] == []

    def test_a_directory_attempt_on_a_break_glass_name_does_appear(self, store):
        _record(store, [
            ("kubeadmin", loginlog.OUTCOME_SUCCESS, 200, "developer"),
            ("kubeadmin", loginlog.OUTCOME_REJECTED, 100, "ldap-local"),
        ])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        assert [r["user_name"] for r in rows] == ["kubeadmin"]

    def test_a_row_with_no_provider_still_counts(self, store):
        """A failure whose provider could not be determined is exactly the interesting one."""
        store.record_login_events("crc-local", [event_dict(
            LoginAttempt("mystery", loginlog.OUTCOME_FAILED, datetime.now(UTC), provider=None),
            "oauth-openshift-aaa", _iso(datetime.now(UTC)))])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        assert [r["user_name"] for r in rows] == ["mystery"]

    def test_a_governed_member_is_not_ungoverned(self, store):
        store.sync_members("crc-local", {"app-x": ["jane.smith"]}, {}, _iso(datetime.now(UTC)))
        _record(store, [("jane.smith", loginlog.OUTCOME_SUCCESS, 60, "ldap-local")])
        rows = store.ungoverned_login_users("crc-local", exclude_providers=HTPASSWD)
        assert [r["user_name"] for r in rows] == []


class TestTheDedupKey:
    """UNIQUE(cluster_id, pod_name, user_name, at, outcome). Reads overlap ON PURPOSE."""

    def test_re_reading_the_same_lines_inserts_nothing_new(self, store):
        # ONE row built once and offered twice. Rebuilding it would restamp `at` to a new microsecond,
        # which is a different attempt by the key's own definition — so the test would pass a
        # duplicate through and prove nothing. (It did, first run.)
        now = datetime.now(UTC)
        row = event_dict(
            LoginAttempt("jane.smith", loginlog.OUTCOME_SUCCESS, now, provider="ldap-local"),
            "oauth-openshift-aaa", _iso(now))
        assert store.record_login_events("crc-local", [row]) == 1
        assert store.record_login_events("crc-local", [row]) == 0, (
            "the overlap re-read inserted a duplicate"
        )
        # And the same batch containing it twice, which is what a single overlapping read produces.
        assert store.record_login_events("crc-local", [row, row]) == 0

    def test_two_replicas_at_the_same_instant_are_two_attempts(self, store):
        """pod_name is IN the key, and this is why.

        Two oauth replicas serve different attempts. Without pod_name a genuine attempt on the second
        replica at the same microsecond as one on the first is silently discarded — proven in a scratch
        database at the time: [1,0,1] / 2 rows with it, [1,0,0] / 1 row without.
        """
        now = datetime.now(UTC)
        made = LoginAttempt("jane.smith", loginlog.OUTCOME_SUCCESS, now, provider="ldap-local")
        first = store.record_login_events("crc-local", [event_dict(made, "pod-a", _iso(now))])
        again = store.record_login_events("crc-local", [event_dict(made, "pod-a", _iso(now))])
        other = store.record_login_events("crc-local", [event_dict(made, "pod-b", _iso(now))])
        assert [first, again, other] == [1, 0, 1]

    def test_the_same_person_twice_in_one_second_is_two_rows(self, store):
        """Microsecond precision is part of the key for this reason."""
        now = datetime.now(UTC)
        n = store.record_login_events("crc-local", [
            event_dict(LoginAttempt("bob", loginlog.OUTCOME_FAILED, now, provider="ldap-local"),
                       "pod-a", _iso(now)),
            event_dict(LoginAttempt("bob", loginlog.OUTCOME_FAILED,
                                    now + timedelta(microseconds=1), provider="ldap-local"),
                       "pod-a", _iso(now)),
        ])
        assert n == 2


class TestTheWatermark:
    def test_it_refuses_to_rewind(self, store):
        """A late write from a demoted leader must not undo progress.

        The lease is best-effort admission control, not a write fence, so this is what makes the
        residual window tolerable: a stale writer can repeat rows (the dedup key collapses them) but
        cannot move the watermark backwards and cause a re-read that grows without bound.
        """
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:50:00.000000Z", "x")
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:40:00.000000Z", "y")
        assert store.login_watermarks("crc-local")["pod-a"] == "2026-08-07T23:50:00.000000Z"

    def test_it_advances(self, store):
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:40:00.000000Z", "x")
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:50:00.000000Z", "y")
        assert store.login_watermarks("crc-local")["pod-a"] == "2026-08-07T23:50:00.000000Z"

    def test_each_pod_keeps_its_own(self, store):
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:40:00.000000Z", "x")
        store.set_login_watermark("crc-local", "pod-b", "2026-08-07T23:50:00.000000Z", "x")
        marks = store.login_watermarks("crc-local")
        assert marks == {"pod-a": "2026-08-07T23:40:00.000000Z",
                         "pod-b": "2026-08-07T23:50:00.000000Z"}

    def test_pruning_an_empty_list_removes_nothing(self, store):
        """A cycle that listed no pods must not be read as "every pod is gone"."""
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:40:00.000000Z", "x")
        store.prune_login_watermarks("crc-local", [])
        assert "pod-a" in store.login_watermarks("crc-local")

    def test_pruning_drops_only_pods_that_are_gone(self, store):
        store.set_login_watermark("crc-local", "pod-a", "2026-08-07T23:40:00.000000Z", "x")
        store.set_login_watermark("crc-local", "pod-b", "2026-08-07T23:40:00.000000Z", "x")
        store.prune_login_watermarks("crc-local", ["pod-b"])
        assert list(store.login_watermarks("crc-local")) == ["pod-b"]


class TestCaptureStatus:
    def test_started_at_is_set_once_and_never_moves(self, store):
        """It is what lets the UI say when watching began.

        If it drifted forward with each read the page would claim the window is newer than it is, and
        an empty list would look like a fresh start rather than a quiet cluster.
        """
        store.record_login_read("crc-local", "2026-08-07T23:47:59Z")
        store.record_login_read("crc-local", "2026-08-07T23:52:59Z")
        s = store.login_capture_status("crc-local")
        assert s["started_at"] == "2026-08-07T23:47:59Z"
        assert s["last_read_at"] == "2026-08-07T23:52:59Z"

    def test_absent_before_the_first_read(self, store):
        assert store.login_capture_status("crc-local") in (None, {})


class TestRetention:
    def test_it_drops_only_rows_past_the_window(self, store):
        _record(store, [
            ("old", loginlog.OUTCOME_FAILED, 60 * 60 * 24 * 500, "ldap-local"),
            ("new", loginlog.OUTCOME_FAILED, 60, "ldap-local"),
        ])
        before = _iso(datetime.now(UTC) - timedelta(days=400))
        removed = store.prune_login_events("crc-local", before)
        assert removed == 1
        assert [a["user_name"] for a in store.login_events("crc-local")] == ["new"]

    def test_it_is_bounded_per_call(self, store):
        """An unbounded DELETE holds the write lock while every reader and the next poll wait.

        A full chunk means more remains and the next cycle continues; there is no need to finish in
        one pass.
        """
        _record(store, [(f"old{i}", loginlog.OUTCOME_FAILED, 60 * 60 * 24 * 500 + i, "ldap-local")
                        for i in range(10)])
        before = _iso(datetime.now(UTC) - timedelta(days=400))
        first = store.prune_login_events("crc-local", before, max_rows=4)
        assert first == 4, "the cap was not applied"
        assert store.prune_login_events("crc-local", before, max_rows=100) == 6


class TestTheSummaryDescribesTheWholeRecord:
    """Never the page. A header that moved with a filter would make every number mean "whatever is
    selected", which is not a number anyone can act on."""

    def test_it_is_not_affected_by_a_filtered_read(self, store):
        _record(store, [
            ("jane.smith", loginlog.OUTCOME_SUCCESS, 300, "ldap-local"),
            ("jane.smith", loginlog.OUTCOME_BAD_PASSWORD, 200, "ldap-local"),
            ("ghost", loginlog.OUTCOME_REJECTED, 100, "ldap-local"),
        ])
        summary = store.login_event_summary("crc-local", exclude_providers=HTPASSWD)
        page = store.login_events("crc-local", outcome=loginlog.OUTCOME_SUCCESS)
        assert len(page) == 1
        assert summary["total"] == 3
        assert summary["distinct_users"] == 2
        assert summary["by_outcome"] == {
            loginlog.OUTCOME_SUCCESS: 1,
            loginlog.OUTCOME_BAD_PASSWORD: 1,
            loginlog.OUTCOME_REJECTED: 1,
        }

    def test_first_and_last_bound_the_retained_record(self, store):
        _record(store, [
            ("a", loginlog.OUTCOME_FAILED, 300, "ldap-local"),
            ("b", loginlog.OUTCOME_FAILED, 100, "ldap-local"),
        ])
        s = store.login_event_summary("crc-local", exclude_providers=HTPASSWD)
        assert s["first_at"] < s["last_at"]

    def test_an_empty_record_reports_zeroes_and_nulls_not_an_error(self, store):
        s = store.login_event_summary("crc-local", exclude_providers=HTPASSWD)
        assert s["total"] == 0 and s["by_outcome"] == {}
        assert s["first_at"] is None and s["last_at"] is None


class TestEnrichment:
    def test_known_user_and_has_history_separate_the_two_reasons(self, store):
        """The pair that makes this feature worth building.

        removed  — was in a group, is not now: an offboarding that did not finish.
        never    — nobody has ever governed this name.
        """
        now = _iso(datetime.now(UTC))
        store.sync_members("crc-local", {"app-x": ["stayed", "removed"]}, {}, now)
        store.sync_members("crc-local", {"app-x": ["stayed"]}, {}, now)
        _record(store, [
            ("stayed", loginlog.OUTCOME_SUCCESS, 300, "ldap-local"),
            ("removed", loginlog.OUTCOME_REJECTED, 200, "ldap-local"),
            ("never", loginlog.OUTCOME_REJECTED, 100, "ldap-local"),
        ])
        by_user = {a["user_name"]: a for a in store.login_events("crc-local")}
        assert (bool(by_user["stayed"]["known_user"]), bool(by_user["stayed"]["has_history"])) \
            == (True, True)
        assert (bool(by_user["removed"]["known_user"]), bool(by_user["removed"]["has_history"])) \
            == (False, True)
        assert (bool(by_user["never"]["known_user"]), bool(by_user["never"]["has_history"])) \
            == (False, False)

    def test_the_display_name_comes_from_the_same_source_as_every_member_list(self, store):
        store.replace_users("crc-local", {"jane.smith": "Jane Smith"}, _iso(datetime.now(UTC)))
        _record(store, [("jane.smith", loginlog.OUTCOME_SUCCESS, 60, "ldap-local")])
        assert store.login_events("crc-local")[0]["full_name"] == "Jane Smith"

    def test_a_username_with_no_user_object_has_no_name_rather_than_a_blank(self, store):
        _record(store, [("ghost", loginlog.OUTCOME_REJECTED, 60, "ldap-local")])
        assert store.login_events("crc-local")[0]["full_name"] is None

def test_a_negative_retention_limit_cannot_become_unbounded(store):
    """SQLite LIMIT -1 means every row, the opposite of this method's contract."""
    _record(store, [(f"old{i}", loginlog.OUTCOME_FAILED, 60 * 60 * 24 * 500 + i,
                     "ldap-local") for i in range(10)])
    before = _iso(datetime.now(UTC) - timedelta(days=400))
    assert store.prune_login_events("crc-local", before, max_rows=-1) == 0
    assert len(store.login_events("crc-local", limit=100)) == 10

def test_gate_only_summary_is_not_capped_at_ten_thousand(store):
    """A whole-cluster KPI must not secretly be the length of a capped page."""
    with store._write() as conn:
        conn.executemany(
            """INSERT INTO group_member(cluster_id,group_name,user_name,
                                          first_seen_at,last_seen_at) VALUES(?,?,?,?,?)""",
            [("crc-local", "gate", f"user{i}", "t", "t") for i in range(10_001)],
        )
    store.set_cluster_access_group("crc-local", "cn=gate,dc=x", "config", "gate", "t")
    assert store.cluster_access_summary("crc-local")["login_without_access"] == 10_001


class TestRetentionSignals:
    def test_the_prune_notes_what_it_deleted(self, store):
        """§3.8 of docs/DESIGN_metrics_refresh.md: the login_event increments come from
        _prune itself — the same count the log line reports, from the same call."""
        from gsd.config import ClusterConfig, Settings
        from gsd.logincapture import _prune
        from gsd.metrics import RuntimeSignals

        _record(store, [("old", loginlog.OUTCOME_FAILED, 60 * 60 * 24 * 500, "ldap-local")])
        signals = RuntimeSignals()
        settings = Settings(
            clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443",
                                    token_env="X")],
            db_path=":memory:", login_retention_days=400)
        _prune(store, settings.clusters[0], settings, None, signals)
        assert signals.snapshot()["retention"]["login_event"] == 1
