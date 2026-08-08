"""The capture loop: what it reads, what it writes, and what it refuses to do.

THE LOOP'S CONTRACT IS MOSTLY ABOUT NOT DOING THINGS, which is why it needs tests of its own rather
than being covered incidentally by the store's. It must never take the group poll down; it must not
write when it has lost the lease; it must not stamp a successful read when no pod answered; and it must
advance its watermark, because the first draft did not and the read grew without bound.

A FAKE CLUSTER, NOT A MOCKED ONE. The double below implements the two methods capture_once calls and
records the `since_seconds` it was asked for, so the read WINDOW — the part that decides whether an
attempt is seen twice or missed — is asserted rather than assumed. capture_once constructs its own
ClusterClient, so the class is swapped in the module under test.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from gsd import logincapture, loginlog
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterError
from gsd.logincapture import (
    FIRST_SIGHT_SECONDS,
    OVERLAP_SECONDS,
    SETTLE_SECONDS,
    capture_once,
    event_dict,
)
from gsd.loginlog import LoginAttempt
from gsd.store import Store

CLUSTER = ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")
POD = "oauth-openshift-66444df7fc-nccmh"

# A real attempt, verbatim from the cluster: the HTPasswd failure that is not a failed login, the
# directory search, and the success. Reused so every test drives the loop with lines it will actually
# meet rather than with a synthetic single line.
def _lines(when: datetime, user: str = "jane.smith", ok: bool = True) -> list[str]:
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
    verdict = "succeeded" if ok else "failed"
    return [
        f'{stamp} I0807 23:48:57.591365       1 basicauth.go:48] '
        f'Login with provider "developer" failed for login "{user}"',
        f'{stamp} I0807 23:48:57.687787       1 ldap.go:131] searching for (uid={user})',
        f'{stamp} I0807 23:48:58.035917       1 basicauth.go:51] '
        f'Login with provider "ldap-local" {verdict} for login "{user}"',
    ]


class FakeClient:
    """The two methods capture_once calls, plus a record of how it was called."""

    #: Distinguishes "no pods argument given" from "fetch_oauth_pods returns None", which is what
    #: the real client does for FORBIDDEN. `pods=None` alone could not say the second thing.
    DEFAULT = object()

    def __init__(self, pods=DEFAULT, logs=None, list_error=None, log_error=None):
        self._pods = [POD] if pods is FakeClient.DEFAULT else pods
        self._logs = logs or {}
        self._list_error = list_error
        self._log_error = log_error
        self.since_by_pod: dict[str, int] = {}
        self.log_calls: list[str] = []

    def fetch_oauth_pods(self, namespace):
        self.namespace = namespace
        if self._list_error:
            raise self._list_error
        return self._pods

    def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw):
        self.log_calls.append(pod_name)
        self.since_by_pod[pod_name] = since_seconds
        if self._log_error and pod_name in self._log_error:
            raise self._log_error[pod_name]
        return self._logs.get(pod_name)


class FakeElector:
    """Leadership that can change between the read and the write, which is the whole point."""

    def __init__(self, leader=True, lose_after=None):
        self._leader = leader
        self._lose_after = lose_after
        self.checks = 0

    @property
    def is_leader(self):
        self.checks += 1
        if self._lose_after is not None and self.checks > self._lose_after:
            return False
        return self._leader


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "capture.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "capture.db"),
                    login_capture_enabled=True)


@pytest.fixture()
def install(monkeypatch):
    """Swap the client class capture_once constructs, and hand back the instance it used."""
    def _install(client):
        monkeypatch.setattr(logincapture, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


def _old_enough(seconds=SETTLE_SECONDS + 60) -> datetime:
    """An instant far enough in the past that the settle horizon considers it finished."""
    return datetime.now(UTC) - timedelta(seconds=seconds)


class TestItNeverTakesThePollDown:
    """capture_once must not raise for a cluster problem. Group polling is a separate concern with a
    separate failure mode, and a broken log read must not stop groups being observed."""

    def test_disabled_does_nothing_at_all(self, store, settings, monkeypatch):
        settings = Settings(clusters=[CLUSTER], db_path=settings.db_path,
                            login_capture_enabled=False)

        def explode(*a, **kw):  # pragma: no cover - must not be reached
            raise AssertionError("a cluster client was constructed with capture disabled")

        monkeypatch.setattr(logincapture, "ClusterClient", explode)
        assert capture_once(store, CLUSTER, settings) == 0

    def test_a_failed_pod_list_is_logged_and_swallowed(self, store, settings, install, caplog):
        install(FakeClient(list_error=ClusterError("auth_failed", "401 Unauthorized")))
        with caplog.at_level(logging.WARNING):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "group data is unaffected" in caplog.text
        assert "401 Unauthorized" in caplog.text

    def test_a_forbidden_pod_list_records_nothing(self, store, settings, install):
        """fetch_oauth_pods returns None for FORBIDDEN — a missing grant, not a fault."""
        install(FakeClient(pods=None))
        assert capture_once(store, CLUSTER, settings) == 0
        assert store.login_capture_status(CLUSTER.name) in (None, {})

    def test_no_running_pods_records_nothing(self, store, settings, install):
        install(FakeClient(pods=[]))
        assert capture_once(store, CLUSTER, settings) == 0

    def test_one_pod_failing_does_not_stop_the_others(self, store, settings, install):
        when = _old_enough()
        client = install(FakeClient(
            pods=["pod-a", "pod-b"],
            logs={"pod-b": _lines(when, "jane.smith")},
            log_error={"pod-a": ClusterError("error", "read timed out")},
        ))
        assert capture_once(store, CLUSTER, settings) == 1
        assert client.log_calls == ["pod-a", "pod-b"], "the loop stopped at the first failure"
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["jane.smith"]

    def test_a_refused_read_returning_none_is_skipped_quietly(self, store, settings, install):
        """fetch_pod_log returns None for roll noise or a missing grant; both are already logged."""
        install(FakeClient(logs={POD: None}))
        assert capture_once(store, CLUSTER, settings) == 0


class TestTheReadWindow:
    def test_a_first_sight_looks_back_one_hour(self, store, settings, install):
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod[POD] == FIRST_SIGHT_SECONDS, (
            "with no watermark the read must be bounded, not unbounded: a long-lived pod at Debug "
            "would otherwise have its entire history re-read on every restart"
        )

    def test_a_watermark_is_re_read_with_an_overlap(self, store, settings, install):
        """An attempt is SEVERAL lines and they can straddle two reads.

        The success line may land in the window after the failure lines that precede it, so the
        overlap is what makes the whole attempt present in one parse. The dedup key makes the repeats
        free.
        """
        mark = (datetime.now(UTC) - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
        store.set_login_watermark(CLUSTER.name, POD, mark, "x")
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        since = client.since_by_pod[POD]
        assert 300 + OVERLAP_SECONDS <= since <= 300 + OVERLAP_SECONDS + 5, since

    def test_an_unparsable_watermark_falls_back_to_a_first_sight(self, store, settings, install):
        """Rather than reading zero seconds and silently capturing nothing ever again."""
        store.set_login_watermark(CLUSTER.name, POD, "not-a-timestamp", "x")
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod[POD] == FIRST_SIGHT_SECONDS

    def test_each_pod_carries_its_own_window(self, store, settings, install):
        """Two replicas serve different attempts, so one shared position would skip lines."""
        mark = (datetime.now(UTC) - timedelta(seconds=200)).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
        store.set_login_watermark(CLUSTER.name, "pod-a", mark, "x")
        client = install(FakeClient(pods=["pod-a", "pod-b"], logs={"pod-a": [], "pod-b": []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod["pod-b"] == FIRST_SIGHT_SECONDS
        assert client.since_by_pod["pod-a"] < FIRST_SIGHT_SECONDS


class TestTheSettleHorizon:
    """The bug that shipped into the first draft, and the reason it is measured from NOW.

    Measuring from the newest attempt in the BATCH means a burst of logins inside SETTLE_SECONDS makes
    every one of them unsettled relative to its own peers, so the watermark never advances at all: the
    same window is re-read forever, sinceSeconds stays at first-sight, and the read grows without
    bound. It was caught by the healthy path writing zero watermarks — which is why the first test here
    asserts a watermark exists rather than only that events were recorded.
    """

    def test_the_healthy_path_advances_the_watermark(self, store, settings, install):
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        assert capture_once(store, CLUSTER, settings) == 1
        assert POD in store.login_watermarks(CLUSTER.name), (
            "events were recorded and the read position was not advanced — the next cycle re-reads "
            "the same window, forever"
        )

    def test_a_burst_inside_the_horizon_still_advances_it(self, store, settings, install):
        """Ten logins within a second of each other, all comfortably older than the horizon.

        Under the original bug every one of these was 'unsettled' because it was within
        SETTLE_SECONDS of its neighbours, and nothing advanced.
        """
        base = _old_enough()
        lines = []
        for i in range(10):
            lines += _lines(base + timedelta(milliseconds=100 * i), f"user{i}")
        install(FakeClient(logs={POD: lines}))
        assert capture_once(store, CLUSTER, settings) == 10
        assert POD in store.login_watermarks(CLUSTER.name)

    def test_attempts_newer_than_the_horizon_are_recorded_but_not_settled(
            self, store, settings, install):
        """Recording early and advancing late is the safe order.

        The newest lines of a live log are the ones most likely to be mid-attempt — the failure lines
        written, the success line not yet. So the events are stored (the dedup key makes the re-read
        harmless) while the position waits.
        """
        install(FakeClient(logs={POD: _lines(datetime.now(UTC))}))
        assert capture_once(store, CLUSTER, settings) == 1
        assert store.login_watermarks(CLUSTER.name) == {}, (
            "the position advanced past an attempt whose lines may still be arriving"
        )

    def test_the_horizon_is_the_newest_settled_attempt(self):
        now = datetime.now(UTC)
        attempts = [
            LoginAttempt("a", loginlog.OUTCOME_SUCCESS, now - timedelta(seconds=SETTLE_SECONDS + 90)),
            LoginAttempt("b", loginlog.OUTCOME_SUCCESS, now - timedelta(seconds=SETTLE_SECONDS + 30)),
            LoginAttempt("c", loginlog.OUTCOME_SUCCESS, now),          # newer than the horizon
        ]
        horizon = logincapture._settle_horizon(attempts)
        assert horizon == attempts[1].at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def test_no_attempts_means_no_horizon(self):
        assert logincapture._settle_horizon([]) is None


class TestLeadership:
    """`poller.py` calls its own lease "BEST-EFFORT admission control, NOT a write fence".

    That is fine for group polling and not fine here, because this reads logs over the network: the
    check can pass, the read can block, the lease can pass to another replica, and the old leader's
    read can then return and write. So leadership is rechecked immediately before the write.
    """

    def test_a_standby_writes_nothing(self, store, settings, install):
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        assert capture_once(store, CLUSTER, settings, elector=FakeElector(leader=False)) == 0
        assert store.login_events(CLUSTER.name) == []
        assert store.login_capture_status(CLUSTER.name) in (None, {})

    def test_losing_the_lease_during_the_read_discards_the_events(
            self, store, settings, install, caplog):
        """The sequence Codex named: leader check true, log GET blocks, lease lost, GET returns.

        The recheck cannot CLOSE that window — closing it needs a fencing token the lease does not
        provide — but it narrows it from the length of a log read to a few instructions, and nothing
        may be written on the far side of it.
        """
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        elector = FakeElector(leader=True, lose_after=0)
        with caplog.at_level(logging.INFO):
            assert capture_once(store, CLUSTER, settings, elector=elector) == 0
        assert store.login_events(CLUSTER.name) == []
        assert store.login_watermarks(CLUSTER.name) == {}
        assert "lost leadership while reading" in caplog.text

    def test_what_was_already_written_is_still_returned(self, store, settings, install):
        """Losing the lease mid-loop reports the events already committed, not zero.

        Two pods, leadership lost between them: the first pod's events are written and counted, the
        second pod's are discarded. Reporting zero would say nothing happened when something did.
        """
        when = _old_enough()
        install(FakeClient(pods=["pod-a", "pod-b"],
                           logs={"pod-a": _lines(when, "first"),
                                 "pod-b": _lines(when, "second")}))
        # One check passes (pod-a's write), the next fails (pod-b's).
        assert capture_once(store, CLUSTER, settings, elector=FakeElector(lose_after=1)) == 1
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["first"]

    def test_the_recheck_happens_after_the_read_not_only_before(self, store, settings, install):
        """If leadership were checked once at the top, a lease lost during the read would go
        unnoticed. The elector counts its calls, so this asserts the check is made per write."""
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        elector = FakeElector(leader=True)
        capture_once(store, CLUSTER, settings, elector=elector)
        assert elector.checks >= 2, (
            f"leadership was consulted {elector.checks} time(s); the write needs its own check"
        )


class TestLivenessAndTheWindowTheUiShows:
    def test_a_successful_read_stamps_the_status(self, store, settings, install):
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        status = store.login_capture_status(CLUSTER.name)
        assert status["started_at"] and status["last_read_at"]

    def test_started_at_does_not_move_on_later_cycles(self, store, settings, install):
        """It is what lets the page say when watching began. If it drifted forward, an empty list
        would look like a fresh start rather than a quiet cluster."""
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        first = store.login_capture_status(CLUSTER.name)["started_at"]
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name)["started_at"] == first

    def test_a_cycle_where_no_pod_answered_does_not_claim_a_read(self, store, settings, install):
        """`last_read_at` is the liveness signal the page uses to say capture has stopped.

        Stamping it when every read was refused would make a broken capture look healthy, and
        `started_at` would then claim we had been watching since a cycle that saw nothing.
        """
        install(FakeClient(logs={POD: None}))
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name) in (None, {}), (
            "a cycle in which no pod answered stamped a successful read"
        )

    def test_an_empty_log_is_a_successful_read(self, store, settings, install):
        """Capture on with Debug off reads real logs and finds nothing. That is correct, not broken,
        and it must still register as liveness — otherwise the page reports capture as stopped on a
        cluster where it is working perfectly and simply has nothing to see."""
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name)["last_read_at"]


class TestPruning:
    def test_read_positions_for_dead_pods_are_forgotten(self, store, settings, install):
        """Every oauth roll replaces the pods. _prune's docstring claimed to do this and did not, so
        the table grew by one row per pod name the cluster had ever had."""
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        store.set_login_watermark(CLUSTER.name, POD, "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert list(store.login_watermarks(CLUSTER.name)) == [POD]

    def test_a_standby_does_not_prune(self, store, settings, install):
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings, elector=FakeElector(leader=False))
        assert "pod-gone" in store.login_watermarks(CLUSTER.name)

    def test_positions_are_pruned_even_when_every_read_failed(self, store, settings, install):
        """On the strength of the POD LIST, which succeeded. A cluster whose reads are all refused is
        the case most likely to accumulate dead positions, so gating this on a successful read would
        leak exactly where it matters."""
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: None}))
        capture_once(store, CLUSTER, settings)
        assert "pod-gone" not in store.login_watermarks(CLUSTER.name)

    def test_events_past_retention_are_dropped(self, store, settings, install, tmp_path):
        old = datetime.now(UTC) - timedelta(days=500)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("ancient", loginlog.OUTCOME_FAILED, old, provider="ldap-local"),
            POD, "2026-01-01T00:00:00Z")])
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert store.login_events(CLUSTER.name) == []

    def test_retention_zero_keeps_everything(self, store, install, tmp_path):
        """0 disables retention deliberately — for a cluster that must keep the whole record."""
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "x.db"),
                     login_capture_enabled=True, login_retention_days=0)
        old = datetime.now(UTC) - timedelta(days=5000)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("ancient", loginlog.OUTCOME_FAILED, old, provider="ldap-local"),
            POD, "2026-01-01T00:00:00Z")])
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, s)
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["ancient"]

    def test_disabling_retention_does_not_disable_position_cleanup(self, store, install, tmp_path):
        """They are unrelated: one is a policy about how long to keep data, the other is a leak."""
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "x.db"),
                     login_capture_enabled=True, login_retention_days=0)
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, s)
        assert "pod-gone" not in store.login_watermarks(CLUSTER.name)


class TestEventDict:
    """The row shape, which is also the dedup key, so its format is load-bearing."""

    def test_the_pod_is_carried_because_it_is_in_the_key(self):
        row = event_dict(LoginAttempt("jane.smith", loginlog.OUTCOME_SUCCESS, datetime.now(UTC)),
                         POD, "2026-08-07T23:48:57Z")
        assert row["pod_name"] == POD

    def test_the_timestamp_keeps_microseconds_and_a_literal_z(self):
        """Two attempts one microsecond apart must not collide, and a format that varied between
        writer and reader would make the key match rows it should not."""
        at = datetime(2026, 8, 7, 23, 48, 57, 591593, tzinfo=UTC)
        row = event_dict(LoginAttempt("x", loginlog.OUTCOME_SUCCESS, at), POD, "obs")
        assert row["at"] == "2026-08-07T23:48:57.591593Z"

    def test_it_carries_the_parser_fields_through_unchanged(self):
        made = LoginAttempt("jane.smith", loginlog.OUTCOME_BAD_PASSWORD, datetime.now(UTC),
                            provider="ldap-local", ldap_result_code=49,
                            detail="LDAP result code 49")
        row = event_dict(made, POD, "obs")
        assert (row["user_name"], row["outcome"], row["provider"], row["ldap_result_code"],
                row["detail"], row["observed_at"]) == (
            "jane.smith", loginlog.OUTCOME_BAD_PASSWORD, "ldap-local", 49,
            "LDAP result code 49", "obs")


class TestTheWholeLoopIsIdempotent:
    def test_running_it_twice_over_the_same_log_records_each_attempt_once(
            self, store, settings, install):
        """Which is what the overlap guarantees will happen on every real cycle."""
        lines = _lines(_old_enough())
        client = FakeClient(logs={POD: lines})
        install(client)
        assert capture_once(store, CLUSTER, settings) == 1
        assert capture_once(store, CLUSTER, settings) == 0
        assert len(store.login_events(CLUSTER.name)) == 1

    def test_the_namespace_comes_from_configuration(self, store, settings, install):
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.namespace == settings.login_capture_namespace == "openshift-authentication"
