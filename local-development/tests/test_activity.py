"""Dashboard usage capture: the recorder, the store merge, and the trust boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.activity import MAX_FLUSH_ATTEMPTS, ActivityRecorder
from gsd.api import build_app
from gsd.config import Settings
from gsd.store import Store


@pytest.fixture()
def store():
    s = Store(":memory:")
    yield s
    s.close()


@pytest.fixture()
def recorder(store):
    # No start(): the flush thread is not wanted in tests, and flush() is called directly
    # so the assertions are about the merge rather than about timing.
    return ActivityRecorder(store, enabled=True, flush_interval_seconds=3600)


class TestBuffering:
    def test_recording_touches_no_database(self, recorder, store):
        """The request path must not write. A write per request would serialise every API
        call behind the poller's bulk write."""
        recorder.record("alice", "alice@example.com", "2026-08-01T09:00:00Z")
        assert store.user_activity() == []

    def test_flush_writes_one_row_per_user_day(self, recorder, store):
        recorder.record("alice", "a@x.com", "2026-08-01T09:00:00Z")
        recorder.record("alice", "a@x.com", "2026-08-01T17:00:00Z")
        recorder.record("bob", "b@x.com", "2026-08-01T10:00:00Z")
        assert recorder.flush() == 2
        rows = {r["user_name"]: r for r in store.user_activity()}
        assert rows["alice"]["request_count"] == 2
        assert rows["alice"]["first_seen_at"] == "2026-08-01T09:00:00Z"
        assert rows["alice"]["last_seen_at"] == "2026-08-01T17:00:00Z"
        assert rows["bob"]["request_count"] == 1

    def test_a_user_spanning_midnight_gets_two_rows(self, recorder, store):
        """Bucketing is per UTC day, so the buffer must key on the day rather than merging
        whatever happens to be in memory when the flush fires."""
        recorder.record("alice", None, "2026-08-01T23:59:00Z")
        recorder.record("alice", None, "2026-08-02T00:01:00Z")
        recorder.flush()
        assert [r["day"] for r in store.user_activity()] == ["2026-08-02", "2026-08-01"]

    def test_out_of_order_records_widen_the_window(self, recorder, store):
        """Requests are recorded from several worker threads and are not guaranteed to
        arrive in timestamp order."""
        recorder.record("alice", None, "2026-08-01T12:00:00Z")
        recorder.record("alice", None, "2026-08-01T08:00:00Z")
        recorder.flush()
        row = store.user_activity()[0]
        assert row["first_seen_at"] == "2026-08-01T08:00:00Z"
        assert row["last_seen_at"] == "2026-08-01T12:00:00Z"

    def test_flushes_accumulate_rather_than_replace(self, recorder, store):
        recorder.record("alice", None, "2026-08-01T09:00:00Z")
        recorder.flush()
        recorder.record("alice", None, "2026-08-01T18:00:00Z")
        recorder.flush()
        row = store.user_activity()[0]
        assert row["request_count"] == 2
        assert row["first_seen_at"] == "2026-08-01T09:00:00Z"
        assert row["last_seen_at"] == "2026-08-01T18:00:00Z"

    def test_a_late_flush_does_not_narrow_the_window(self, recorder, store):
        """A slow flush overtaken by a later one must still widen first/last seen, which is
        why the merge uses SQLite's min/max instead of the incoming value."""
        store.record_user_activity([{
            "user_name": "alice", "day": "2026-08-01", "email": None,
            "first_seen_at": "2026-08-01T08:00:00Z", "last_seen_at": "2026-08-01T20:00:00Z",
            "request_count": 5,
        }])
        recorder.record("alice", None, "2026-08-01T12:00:00Z")
        recorder.flush()
        row = store.user_activity()[0]
        assert row["first_seen_at"] == "2026-08-01T08:00:00Z"
        assert row["last_seen_at"] == "2026-08-01T20:00:00Z"
        assert row["request_count"] == 6

    def test_empty_flush_is_free(self, recorder):
        assert recorder.flush() == 0

    def test_disabled_recorder_records_nothing(self, store):
        off = ActivityRecorder(store, enabled=False)
        off.record("alice", None, "2026-08-01T09:00:00Z")
        off.flush()
        assert store.user_activity() == []

    def test_anonymous_requests_are_not_recorded(self, recorder, store):
        """No header means an unauthenticated path such as /metrics, not a user named ''."""
        recorder.record(None, None, "2026-08-01T09:00:00Z")
        recorder.record("", None, "2026-08-01T09:00:00Z")
        recorder.flush()
        assert store.user_activity() == []


class TestRetention:
    def test_prune_drops_only_days_past_the_window(self, recorder, store):
        for day in ("2026-01-01", "2026-07-30", "2026-08-01"):
            store.record_user_activity([{
                "user_name": "alice", "day": day, "email": None,
                "first_seen_at": f"{day}T09:00:00Z", "last_seen_at": f"{day}T09:00:00Z",
                "request_count": 1,
            }])
        recorder.retention_days = 30
        assert recorder.prune(today="2026-08-01") == 1
        assert {r["day"] for r in store.user_activity()} == {"2026-07-30", "2026-08-01"}

    def test_prune_runs_at_most_once_a_day(self, recorder):
        recorder.retention_days = 30
        recorder.prune(today="2026-08-01")
        assert recorder.prune(today="2026-08-01") == 0

    def test_zero_retention_disables_pruning(self, recorder, store):
        store.record_user_activity([{
            "user_name": "alice", "day": "2020-01-01", "email": None,
            "first_seen_at": "2020-01-01T09:00:00Z", "last_seen_at": "2020-01-01T09:00:00Z",
            "request_count": 1,
        }])
        recorder.retention_days = 0
        assert recorder.prune(today="2026-08-01") == 0
        assert len(store.user_activity()) == 1


def _client(tmp_path, **settings_kw):
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "gsd.db"), **settings_kw), run_poller=False)
    )


class TestTrustBoundary:
    """The header is only believable because the proxy is the sole way in."""

    def test_identity_is_ignored_when_the_proxy_is_off(self, tmp_path):
        """Without the proxy the app binds 0.0.0.0 with no authentication, so anything in
        X-Forwarded-User is caller-supplied. Recording it would fabricate an audit trail."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body == {"user": None, "email": None, "authenticated": False}
            # Refused, not merely empty. This used to return an empty list, which is the
            # same answer a legitimately-unused dashboard gives — so it could not be told
            # apart from "there is nothing to see". 403 says why.
            assert c.get("/api/dashboard/activity").status_code == 403

    def test_identity_is_honoured_when_the_proxy_is_on(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get(
                "/api/whoami",
                headers={"X-Forwarded-User": "alice", "X-Forwarded-Email": "a@x.com"},
            ).json()
            assert body == {"user": "alice", "email": "a@x.com", "authenticated": True}

    def test_interactions_are_captured_and_survive_shutdown(self, tmp_path):
        """The buffer is memory-only, so a graceful shutdown must flush it."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            for _ in range(3):
                c.get("/api/whoami", headers={"X-Forwarded-User": "alice",
                                              "X-GSD-Interaction": "1"})
        # The app has shut down; a fresh store reads what its final flush persisted.
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert len(rows) == 1
        assert rows[0]["user_name"] == "alice" and rows[0]["request_count"] == 3

    def test_background_polling_is_not_counted_as_use(self, tmp_path):
        """THE regression this guards. The page refreshes itself every 30s and each refresh
        is several API calls, so counting every request measured how long a tab had been
        left open: a real session recorded 722 for about a dozen clicks. Only requests the
        client marks as a human action count."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            for _ in range(50):  # an hour of idle auto-refresh
                c.get("/api/clusters", headers={"X-Forwarded-User": "alice"})
            c.get("/api/clusters", headers={"X-Forwarded-User": "alice",
                                            "X-GSD-Interaction": "1"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert len(rows) == 1, "the one real action should still be recorded"
        assert rows[0]["request_count"] == 1, (
            f"background polling inflated the count to {rows[0]['request_count']}"
        )

    def test_an_idle_tab_records_nothing_at_all(self, tmp_path):
        """A tab left open overnight must not invent a user who was never there."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            for _ in range(20):
                c.get("/api/alerts", headers={"X-Forwarded-User": "alice"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []

    def test_capture_off_records_nothing_even_behind_the_proxy(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True, user_activity_enabled=False)
        with TestClient(build_app(settings, run_poller=False)) as c:
            c.get("/api/whoami", headers={"X-Forwarded-User": "alice"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []


def _seed_two_users(db):
    store = Store(db)
    store.record_user_activity([
        {"user_name": u, "day": "2026-08-02", "email": f"{u}@x.com",
         "first_seen_at": "2026-08-02T09:00:00Z", "last_seen_at": "2026-08-02T17:00:00Z",
         "request_count": n}
        for u, n in (("alice", 5), ("bob", 9))
    ])
    store.close()


class TestActivityDisclosure:
    """Who may read the activity endpoint.

    It used to return every row to every authenticated user: username, email, which days
    somebody was present and the window they worked in. The dashboard's usual argument —
    "you could read the groups with oc anyway" — is true of group membership and false of
    who looked at it.
    """

    def test_self_only_by_default(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert body["scope"] == "self"
        assert {r["user_name"] for r in body["activity"]} == {"alice"}, \
            "alice can read bob's presence data"

    def test_visibility_all_is_an_explicit_opt_in(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True,
                            user_activity_visibility="all")
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert body["scope"] == "all"
        assert {r["user_name"] for r in body["activity"]} == {"alice", "bob"}

    def test_refused_outright_when_the_proxy_is_off(self, tmp_path):
        """Without the proxy the username header is caller-supplied, so scoping to it would
        let anyone read anyone by simply asserting a name. Refuse rather than scope."""
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        with TestClient(build_app(Settings(db_path=db, oauth_proxy_enabled=False),
                                  run_poller=False)) as c:
            assert c.get("/api/dashboard/activity",
                         headers={"X-Forwarded-User": "bob"}).status_code == 403

    def test_refused_when_no_identity_is_present(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        with TestClient(build_app(Settings(db_path=db, oauth_proxy_enabled=True),
                                  run_poller=False)) as c:
            assert c.get("/api/dashboard/activity").status_code == 403

    def test_the_limit_applies_after_scoping_not_before(self, tmp_path):
        """Filtering in SQL, not in Python. With the filter applied after the fetch, a
        busier colleague's rows would consume the page and the caller would see fewer of
        their own than `limit` allows."""
        db = str(tmp_path / "gsd.db")
        store = Store(db)
        store.record_user_activity(
            [{"user_name": "bob", "day": f"2026-07-{d:02d}", "email": None,
              "first_seen_at": f"2026-07-{d:02d}T09:00:00Z",
              "last_seen_at": f"2026-07-{d:02d}T09:00:00Z", "request_count": 1}
             for d in range(1, 21)]
            + [{"user_name": "alice", "day": "2026-06-01", "email": None,
                "first_seen_at": "2026-06-01T09:00:00Z",
                "last_seen_at": "2026-06-01T09:00:00Z", "request_count": 1}]
        )
        store.close()
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity?limit=5",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert [r["user_name"] for r in body["activity"]] == ["alice"]


class TestUsageTotalsSurviveTheLimit:
    """A KPI computed from a limited row set counts the page, not the record.

    The Usage tab did exactly that: `days`, `distinct users` and `interactions` were all
    derived from `body["activity"]`, which the API caps at `limit`. Measured against 1,092
    stored rows it reported 167 days and 5,000 interactions where the truth was 364 and
    10,920 — the same silent-truncation defect the user-bindings endpoint was fixed for.
    """

    @staticmethod
    def _seed_many(db):
        store = Store(db)
        store.record_user_activity(
            [{"user_name": u, "day": f"2026-{m:02d}-{d:02d}", "email": None,
              "first_seen_at": f"2026-{m:02d}-{d:02d}T09:00:00Z",
              "last_seen_at": f"2026-{m:02d}-{d:02d}T17:00:00Z", "request_count": 10}
             for u in ("alice", "bob", "carol")
             for m in range(1, 5)
             for d in range(1, 29)]
        )
        store.close()
        return 3 * 4 * 28  # 336 rows: 3 users x 112 days

    def test_the_summary_is_the_whole_set_not_the_page(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        total = self._seed_many(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True,
                            user_activity_visibility="all")
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity?limit=50",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert len(body["activity"]) == 50, "the rows are still bounded"
        assert body["total"] == total
        assert body["truncated"] is True
        assert body["summary"] == {
            "distinct_users": 3, "days": 112, "interactions": total * 10}

    def test_the_summary_is_scoped_the_same_way_the_rows_are(self, tmp_path):
        """Self-scope is a privacy boundary. A total that counted everybody would leak the
        size of everybody else's activity to a viewer who may not read a single row of it."""
        db = str(tmp_path / "gsd.db")
        self._seed_many(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert body["scope"] == "self"
        assert body["total"] == 112, "alice's own days only"
        assert body["summary"]["distinct_users"] == 1

    def test_a_complete_page_is_not_reported_as_truncated(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True,
                            user_activity_visibility="all")
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/api/dashboard/activity",
                         headers={"X-Forwarded-User": "alice"}).json()
        assert body["total"] == len(body["activity"]) == 2
        assert body["truncated"] is False


class TestUnauthenticatedPaths:
    def test_skipped_paths_never_record_even_with_headers(self, tmp_path):
        """/healthz, /readyz and /metrics bypass the proxy, so whether they carry an
        identity header is the caller's choice — which must not decide whether we record."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            for path in ("/healthz", "/readyz", "/metrics"):
                c.get(path, headers={"X-Forwarded-User": "impostor",
                                     "X-GSD-Interaction": "1"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []

    def test_metrics_exposes_no_personnel_data(self, tmp_path):
        """/metrics is deliberately unauthenticated. A distinct-user count still reports
        how many people worked on a given day to anyone who can reach the Service."""
        db = str(tmp_path / "gsd.db")
        _seed_two_users(db)
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            body = c.get("/metrics").text
        assert "gsd_dashboard_active_users" not in body
        for name in ("alice", "bob", "@x.com"):
            assert name not in body, f"{name!r} leaked into unauthenticated /metrics"


class TestFlushFailure:
    """A failed write used to destroy already-captured data.

    flush() swaps the buffer out before writing, so on an exception the swapped batch was
    simply gone — one moment of lock contention past busy_timeout and it was lost, with a
    log line that said so and no way to get it back.
    """

    class _FailingStore:
        """Wraps a real store and fails the next `fail_times` writes."""

        def __init__(self, inner, fail_times):
            self.inner, self.remaining, self.writes = inner, fail_times, 0

        def record_user_activity(self, buckets):
            self.writes += 1
            if self.remaining > 0:
                self.remaining -= 1
                raise RuntimeError("database is locked")
            return self.inner.record_user_activity(buckets)

    def test_a_failed_flush_is_retried_without_losing_or_double_counting(self, store):
        failing = self._FailingStore(store, fail_times=1)
        rec = ActivityRecorder(failing, enabled=True, flush_interval_seconds=3600)

        rec.record("alice", "a@x.com", "2026-08-01T09:00:00Z")
        assert rec.flush() == 0, "the first write is supposed to fail"
        assert store.user_activity() == []

        # More activity arrives while the failed batch waits.
        rec.record("alice", "a@x.com", "2026-08-01T18:00:00Z")
        assert rec.flush() == 1

        row = store.user_activity()[0]
        assert row["request_count"] == 2, "the requeued interaction was lost or duplicated"
        assert row["first_seen_at"] == "2026-08-01T09:00:00Z"
        assert row["last_seen_at"] == "2026-08-01T18:00:00Z"

    def test_a_permanently_failing_store_does_not_grow_the_buffer(self, store):
        """Retrying forever turns a storage outage into an OOM."""
        failing = self._FailingStore(store, fail_times=10_000)
        rec = ActivityRecorder(failing, enabled=True, flush_interval_seconds=3600)
        rec.record("alice", None, "2026-08-01T09:00:00Z")
        for _ in range(MAX_FLUSH_ATTEMPTS + 3):
            rec.flush()
        assert rec._buckets == {}, "buckets are retained past the retry bound"

    def test_buckets_survive_until_the_bound(self, store):
        failing = self._FailingStore(store, fail_times=10_000)
        rec = ActivityRecorder(failing, enabled=True, flush_interval_seconds=3600)
        rec.record("alice", None, "2026-08-01T09:00:00Z")
        rec.flush()
        assert rec._buckets, "dropped on the very first failure — the original bug"

    def test_stop_does_not_start_a_second_flush_while_one_is_in_flight(self, store):
        """The old stop() joined with a timeout and then flushed regardless, which could run
        a second concurrent write and still not make the first one finish."""
        import threading

        started, release = threading.Event(), threading.Event()

        class _Blocking:
            writes = 0

            def record_user_activity(self, buckets):
                _Blocking.writes += 1
                started.set()
                release.wait(timeout=10)
                return len(buckets)

        rec = ActivityRecorder(_Blocking(), enabled=True, flush_interval_seconds=0.05)
        rec.record("alice", None, "2026-08-01T09:00:00Z")
        rec.start()
        assert started.wait(timeout=5), "the flush thread never began writing"
        rec.record("bob", None, "2026-08-01T09:00:00Z")
        rec.stop()                      # must NOT launch a second write
        assert _Blocking.writes == 1
        release.set()
