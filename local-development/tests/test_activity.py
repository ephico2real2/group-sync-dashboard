"""Dashboard usage capture: the recorder, the store merge, and the trust boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.activity import ActivityRecorder
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
            assert c.get("/api/dashboard/activity").json()["activity"] == []

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
