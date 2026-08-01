"""Membership tracking: who is in a group, since when, and who quietly left.

The API keeps no membership history, so these are accumulated the same way sync events are.
The tests that matter are the diff ones — a naive replace-each-poll strategy passes a
"current members" test and silently answers "when did they join?" with "just now, always".
"""

from __future__ import annotations

import pytest

from gsd.store import Store

T1 = "2026-08-01T09:00:00Z"
T2 = "2026-08-01T09:01:00Z"
T3 = "2026-08-01T09:02:00Z"


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


def sync(store, members, at, sync_times=None):
    return store.sync_members("crc", members, sync_times or {}, at)


class TestFirstSeen:
    def test_first_seen_survives_later_polls(self, store):
        """The whole point. If first_seen_at is rewritten every poll, "when did this user
        join?" answers "a minute ago" forever and the field is worse than absent."""
        sync(store, {"g": ["alice"]}, T1)
        sync(store, {"g": ["alice"]}, T2)
        sync(store, {"g": ["alice"]}, T3)
        member = store.group_members("crc", "g")[0]
        assert member["first_seen_at"] == T1
        assert member["last_seen_at"] == T3

    def test_repeated_polls_emit_no_events(self, store):
        """Unchanged membership is not a change; otherwise the timeline is a poll log."""
        assert sync(store, {"g": ["alice", "bob"]}, T1) == 2
        assert sync(store, {"g": ["alice", "bob"]}, T2) == 0
        assert sync(store, {"g": ["alice", "bob"]}, T3) == 0
        assert len(store.membership_events("crc", group_name="g")) == 2

    def test_api_ordering_does_not_register_as_change(self, store):
        """Group.users ordering is not guaranteed stable across reads."""
        sync(store, {"g": ["alice", "bob", "carol"]}, T1)
        assert sync(store, {"g": ["carol", "alice", "bob"]}, T2) == 0


class TestChanges:
    def test_added_user_recorded(self, store):
        sync(store, {"g": ["alice"]}, T1)
        assert sync(store, {"g": ["alice", "bob"]}, T2) == 1
        events = store.membership_events("crc", group_name="g")
        assert (events[0]["user_name"], events[0]["change"]) == ("bob", "added")
        assert store.group_members("crc", "g")[1]["first_seen_at"] == T2

    def test_removed_user_recorded_and_dropped_from_current(self, store):
        """A user quietly falling out of a group is the invisible absence this exists for:
        nothing logs it, and the group looks perfectly healthy afterwards."""
        sync(store, {"g": ["alice", "bob"]}, T1)
        assert sync(store, {"g": ["alice"]}, T2) == 1
        events = store.membership_events("crc", group_name="g")
        assert (events[0]["user_name"], events[0]["change"]) == ("bob", "removed")
        assert [m["user_name"] for m in store.group_members("crc", "g")] == ["alice"]

    def test_rejoin_records_a_second_event_and_resets_first_seen(self, store):
        """Leaving and coming back is two events, and first_seen reflects the current
        membership rather than an ended one."""
        sync(store, {"g": ["alice"]}, T1)
        sync(store, {"g": []}, T2)
        sync(store, {"g": ["alice"]}, T3)
        changes = [(e["change"], e["observed_at"]) for e in store.membership_events("crc", group_name="g")]
        assert changes == [("added", T3), ("removed", T2), ("added", T1)]
        assert store.group_members("crc", "g")[0]["first_seen_at"] == T3

    def test_deleted_group_records_departures(self, store):
        """A group vanishing upstream must not let its members evaporate silently."""
        sync(store, {"g": ["alice", "bob"]}, T1)
        assert sync(store, {}, T2) == 2
        assert store.group_members("crc", "g") == []
        assert {e["change"] for e in store.membership_events("crc", group_name="g")} == {
            "added", "removed"
        }

    def test_group_sync_time_is_captured_on_the_event(self, store):
        """So a change can be attributed to the sync that caused it, not just to our poll."""
        sync(store, {"g": ["alice"]}, T1, {"g": "2026-08-01T08:59:55Z"})
        assert store.membership_events("crc", group_name="g")[0]["group_synced_at"] == (
            "2026-08-01T08:59:55Z"
        )


class TestReverseLookup:
    def test_user_groups(self, store):
        """"Why does this person have access?" — the cluster can only answer this by
        scanning every Group object."""
        sync(store, {"admins": ["alice"], "devs": ["alice", "bob"], "ops": ["bob"]}, T1)
        assert [g["group_name"] for g in store.user_groups("crc", "alice")] == ["admins", "devs"]
        assert [g["group_name"] for g in store.user_groups("crc", "bob")] == ["devs", "ops"]

    def test_user_groups_reflects_removal(self, store):
        sync(store, {"admins": ["alice"], "devs": ["alice"]}, T1)
        sync(store, {"admins": [], "devs": ["alice"]}, T2)
        assert [g["group_name"] for g in store.user_groups("crc", "alice")] == ["devs"]

    def test_users_index(self, store):
        sync(store, {"a": ["alice", "bob"], "b": ["alice"]}, T1)
        by_name = {u["user_name"]: u for u in store.users("crc")}
        assert by_name["alice"]["group_count"] == 2
        assert by_name["bob"]["group_count"] == 1

    def test_membership_events_filter_by_user(self, store):
        sync(store, {"a": ["alice"], "b": ["bob"]}, T1)
        events = store.membership_events("crc", user_name="alice")
        assert len(events) == 1 and events[0]["group_name"] == "a"


class TestIsolation:
    def test_clusters_do_not_bleed_into_each_other(self, store):
        store.upsert_cluster("other", "https://other:6443", True)
        sync(store, {"g": ["alice"]}, T1)
        store.sync_members("other", {"g": ["bob"]}, {}, T1)
        assert [m["user_name"] for m in store.group_members("crc", "g")] == ["alice"]
        assert [m["user_name"] for m in store.group_members("other", "g")] == ["bob"]

    def test_same_username_in_many_groups_is_independent(self, store):
        sync(store, {"a": ["alice"], "b": ["alice"]}, T1)
        sync(store, {"a": ["alice"], "b": []}, T2)
        assert [m["user_name"] for m in store.group_members("crc", "a")] == ["alice"]
        assert store.group_members("crc", "b") == []
