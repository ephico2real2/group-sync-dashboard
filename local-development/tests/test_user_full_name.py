"""Display names read off the OpenShift User object.

A User exists only once that person has AUTHENTICATED. OpenShift creates it on first login and the
identity provider fills `fullName` from its `attributes.name` mapping; group membership creates
nothing, because the group-sync operator only writes LDAP uids into a Group's `users` array.

MEASURED ON THE REFERENCE CLUSTER, which is what these tests encode:

  62 User objects, 8 carrying a fullName.
  10 distinct group members: 7 named, 3 with no User object at all.
  `hello1` is a member with no directory entry either, so it can never acquire one.
  The IdP maps `attributes.name: ["displayName", "cn"]` — dana.lee, sarah.jones and jeff have NO
  displayName and got "Dana Lee", "Sarah Jones", "jeff bush" from `cn`, so a fullName may be a
  display name, a login-shaped name, or (ocp-oauth-bind-serviceid) the uid itself.

So an absent name is the ORDINARY case, not an edge case, and the two things worth protecting are:
the UI renders a bare id exactly as it did before the feature existed, and a missing RBAC grant
costs new names rather than the names already known.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.kube import USER_API, ClusterClient, ClusterError
from gsd.store import Store
from gsd.timeutil import now_iso

USERS = {
    "kind": "UserList",
    "items": [
        {"metadata": {"name": "alice.cooper"}, "fullName": "Alice Cooper"},
        # No displayName in LDAP; the IdP fell back to cn. Lowercase first letter on purpose —
        # this is real data, and the UI must not tidy it.
        {"metadata": {"name": "jeff"}, "fullName": "jeff bush"},
        # Logged in via htpasswd, which supplies no name attribute: the User exists, fullName does
        # not. Downstream this is identical to having no User at all, and must not be stored as "".
        {"metadata": {"name": "developer"}},
        # Present but empty, the other way the same thing is expressed by the API server.
        {"metadata": {"name": "kubeadmin"}, "fullName": ""},
        # Whitespace only. Stripped to nothing, so also absent.
        {"metadata": {"name": "spacey"}, "fullName": "   "},
    ],
}


def _client(handler):
    """A ClusterClient whose HTTP goes to `handler`."""
    cluster = ClusterConfig("names", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(handler)
    client._client = lambda: httpx.Client(transport=transport, base_url="https://x")
    return client


def _handler(status=200, body=None):
    def handle(request):
        if request.url.path.startswith(USER_API):
            if status == 200:
                return httpx.Response(200, json=body if body is not None else USERS)
            return httpx.Response(status, json={"message": "nope"})
        return httpx.Response(404, json={"message": "unexpected path"})
    return handle


class TestFetch:
    def test_only_names_that_are_actually_set_are_returned(self):
        """Empty, missing and whitespace-only all mean "no name", and none reaches the store."""
        names = _client(_handler()).fetch_users()
        assert names == {"alice.cooper": "Alice Cooper", "jeff": "jeff bush"}, (
            "a User with no usable fullName must be absent from the map, not present as ''"
        )

    def test_forbidden_is_tolerated_and_reported_as_none(self):
        """The grant is new, so an image upgraded without re-applying RBAC gets a 403 here.

        None, not {}: the caller must be able to tell "not permitted" from "permitted, nobody has
        a name", because writing {} would blank every name already on screen.
        """
        assert _client(_handler(status=403)).fetch_users() is None

    @pytest.mark.parametrize("status", [401, 404, 500, 503])
    def test_every_other_status_still_raises(self, status):
        """Only 403 is forgiven, and only because this data is cosmetic.

        The inverse of the rule fetch() enforces: there, swallowing a 403 would report a missing
        grant as a healthy operator-less cluster. Here a 403 costs display names and nothing else,
        so it is tolerated in this one method — and nowhere near correctness.
        """
        with pytest.raises(ClusterError):
            _client(_handler(status=status)).fetch_users()

    def test_the_log_names_the_grant_to_add(self, caplog):
        """A silent absence of names is indistinguishable from nobody having logged in."""
        with caplog.at_level("DEBUG", logger="gsd.kube"):
            _client(_handler(status=403)).fetch_users()
        assert "not permitted to list users" in caplog.text


class TestStore:
    def test_replace_is_wholesale_so_a_departed_user_loses_their_name(self, tmp_path):
        """An upsert would leave a stale name on a deleted account, which is worse than none."""
        store = Store(str(tmp_path / "t.db"))
        store.replace_users("c1", {"a": "Ann", "b": "Bob"}, now_iso())
        assert store.user_full_name("c1", "b") == "Bob"
        store.replace_users("c1", {"a": "Ann"}, now_iso())
        assert store.user_full_name("c1", "a") == "Ann"
        assert store.user_full_name("c1", "b") is None

    def test_names_are_per_cluster(self, tmp_path):
        """Two clusters can hold the same username as different people."""
        store = Store(str(tmp_path / "t.db"))
        store.replace_users("c1", {"a": "Ann One"}, now_iso())
        store.replace_users("c2", {"a": "Ann Two"}, now_iso())
        assert store.user_full_name("c1", "a") == "Ann One"
        assert store.user_full_name("c2", "a") == "Ann Two"

    def test_unknown_user_is_none_not_an_error(self, tmp_path):
        store = Store(str(tmp_path / "t.db"))
        assert store.user_full_name("c1", "never-seen") is None


class TestMigration:
    def test_an_existing_database_gains_the_table(self, tmp_path):
        """The upgrade path: a v3 database must acquire ocp_user without losing anything."""
        p = str(tmp_path / "t.db")
        Store(p)
        conn = sqlite3.connect(p)
        conn.execute("DROP TABLE ocp_user")
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
        conn.close()

        Store(p)
        conn = sqlite3.connect(p)
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) >= 4
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ocp_user'"
        ).fetchone(), "migration 4 did not create ocp_user"

    def test_replaying_against_a_fresh_database_is_a_no_op(self, tmp_path):
        """SCHEMA already created the table, so the migration must use IF NOT EXISTS.

        _migrate tolerates exactly one error, "duplicate column name" — a bare CREATE TABLE would
        raise "table already exists" and take the process down on every start.
        """
        p = str(tmp_path / "t.db")
        Store(p)
        conn = sqlite3.connect(p)
        conn.execute("PRAGMA user_version = 3")   # force the replay, table still present
        conn.commit()
        conn.close()
        Store(p)   # must not raise


class TestJoin:
    def test_members_carry_their_name_and_absence_stays_absent(self, tmp_path):
        """The LEFT JOIN, which is why no handler needed a second store call."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["named", "unnamed"]}, {}, seen)
        store.replace_users("c1", {"named": "Named Person"}, seen)

        rows = {r["user_name"]: r["full_name"] for r in store.group_members("c1", "g1")}
        assert rows == {"named": "Named Person", "unnamed": None}, (
            "a member with no User object must come back with full_name None, not be dropped"
        )

    def test_ordering_is_still_by_user_id(self, tmp_path):
        """Sorting by display name would scatter the members who have none.

        The id is also what an operator matches against `oc` output, which is the whole reason it
        stays the primary text in the UI.
        """
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["aaa", "bbb", "ccc"]}, {}, seen)
        # Names that would invert the order if they were sorted on.
        store.replace_users("c1", {"aaa": "Zoe", "ccc": "Adam"}, seen)
        assert [r["user_name"] for r in store.group_members("c1", "g1")] == ["aaa", "bbb", "ccc"]

    def test_users_index_carries_the_name_and_absence_stays_absent(self, tmp_path):
        """The same join on the cluster-wide index, so the Users tab can filter on either field."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["named", "unnamed"]}, {}, seen)
        store.replace_users("c1", {"named": "Named Person"}, seen)

        rows = {r["user_name"]: r for r in store.users("c1")}
        assert {n: r["full_name"] for n, r in rows.items()} == {"named": "Named Person", "unnamed": None}
        # The join must not disturb what the index already reported.
        assert {n: r["group_count"] for n, r in rows.items()} == {"named": 1, "unnamed": 1}
        assert all(r["first_seen_at"] == seen for r in rows.values())

    def test_users_index_ordering_is_still_by_user_id(self, tmp_path):
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["aaa", "bbb", "ccc"]}, {}, seen)
        store.replace_users("c1", {"aaa": "Zoe", "ccc": "Adam"}, seen)
        assert [r["user_name"] for r in store.users("c1")] == ["aaa", "bbb", "ccc"]

    def test_users_index_stays_one_row_per_user_across_groups(self, tmp_path):
        """Guards the GROUP BY: a join that multiplied rows would inflate group_count silently."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["multi"], "g2": ["multi"], "g3": ["multi"]}, {}, seen)
        store.replace_users("c1", {"multi": "Many Groups"}, seen)
        rows = store.users("c1")
        assert len(rows) == 1
        assert rows[0]["group_count"] == 3 and rows[0]["full_name"] == "Many Groups"

    def test_users_index_still_fetches_limit_plus_one(self, tmp_path):
        """The truncation contract survives the join: the caller detects a clip by the extra row."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["a", "b", "c"]}, {}, seen)
        assert [r["user_name"] for r in store.users("c1", limit=2)] == ["a", "b", "c"]
