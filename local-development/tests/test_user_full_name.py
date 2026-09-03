"""The User objects: what the cluster knows about the people who have logged in.

A User exists only once that person has AUTHENTICATED. OpenShift creates it on first login and the
identity provider fills `fullName` from its `attributes.name` mapping; group membership creates
nothing, because the group-sync operator only writes LDAP uids into a Group's `users` array.

This module began as the display-name feature (chart 0.7.x): one field read off the object, joined
onto every member surface, absent by default. Since the Users tab was re-sourced
(docs/DESIGN_users_tab_logins.md) the read returns the whole record and the row IS the fact of a
login — so what these tests protect has grown, and the original guarantees are all still here:
the UI renders a bare id exactly as it did before the feature existed, a User with no usable name is
stored WITHOUT a name rather than dropped or blanked, and a missing RBAC grant is tolerated by the
poll and reported by name.

MEASURED ON THE REFERENCE CLUSTER, which is what these tests encode:

  62 User objects, 61 with an identity, 8 carrying a fullName.
  11 distinct group members: 8 with a User object, 3 with none.
  `hello1` is a member with no directory entry either, so it can never acquire one.
  The IdP maps `attributes.name: ["displayName", "cn"]` — dana.lee, sarah.jones and jeff have NO
  displayName and got "Dana Lee", "Sarah Jones", "jeff bush" from `cn`, so a fullName may be a
  display name, a login-shaped name, or (ocp-oauth-bind-serviceid) the uid itself.
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
        {"metadata": {"name": "alice.cooper", "creationTimestamp": "2026-08-05T16:14:16Z"},
         "fullName": "Alice Cooper", "identities": ["ldap-local:dWlkPWFsaWNl"]},
        # No displayName in LDAP; the IdP fell back to cn. Lowercase first letter on purpose —
        # this is real data, and the UI must not tidy it.
        {"metadata": {"name": "jeff", "creationTimestamp": "2026-08-07T03:09:04Z"},
         "fullName": "jeff bush", "identities": ["ldap-local:dWlkPWplZmY"]},
        # Logged in via htpasswd, which supplies no name attribute: the User exists, fullName does
        # not. A user of the cluster all the same — stored, with no name, never as "".
        {"metadata": {"name": "developer", "creationTimestamp": "2025-04-19T02:02:34Z"},
         "identities": ["developer:developer"]},
        # Present but empty, the other way the same thing is expressed by the API server. Two
        # providers, which happens when one person logs in through both.
        {"metadata": {"name": "kubeadmin", "creationTimestamp": "2025-04-19T02:02:33Z"},
         "fullName": "", "identities": ["developer:kubeadmin", "ldap-local:a3ViZWFkbWlu"]},
        # Whitespace only. Stripped to nothing, so also absent.
        {"metadata": {"name": "spacey", "creationTimestamp": "2026-01-01T00:00:00Z"},
         "fullName": "   ", "identities": ["ldap-local:c3BhY2V5"]},
        # Created by hand with `oc create user`: no identity, so nobody has ever logged in as it.
        # Measured on the reference cluster (`test-python-user`).
        {"metadata": {"name": "manual", "creationTimestamp": "2025-05-18T02:44:11Z"}},
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


def _recs(names: dict[str, str | None], created: str | None = None) -> list[dict]:
    """Records for provider-created Users, from a name -> fullName map."""
    return [{"user_name": n, "full_name": f, "created_at": created or now_iso(),
             "providers": ["ldap-local"], "has_identity": True} for n, f in names.items()]


class TestFetch:
    def test_every_user_is_returned_and_only_set_names_are_kept(self):
        """Empty, missing and whitespace-only all mean "no name" — and the user is still a row."""
        by_name = {r["user_name"]: r for r in _client(_handler()).fetch_users()}
        assert set(by_name) == {"alice.cooper", "jeff", "developer", "kubeadmin", "spacey", "manual"}
        assert {n: r["full_name"] for n, r in by_name.items()} == {
            "alice.cooper": "Alice Cooper", "jeff": "jeff bush",
            "developer": None, "kubeadmin": None, "spacey": None, "manual": None,
        }, "a User with no usable fullName must carry None, never ''"

    def test_the_record_carries_first_login_providers_and_whether_anyone_logged_in(self):
        by_name = {r["user_name"]: r for r in _client(_handler()).fetch_users()}
        assert by_name["alice.cooper"]["created_at"] == "2026-08-05T16:14:16Z"
        assert by_name["alice.cooper"]["providers"] == ["ldap-local"]
        assert by_name["kubeadmin"]["providers"] == ["developer", "ldap-local"], "sorted, one per provider"
        assert by_name["manual"]["providers"] == [] and by_name["manual"]["has_identity"] is False, (
            "an empty identities list is the mark of an account created by hand"
        )
        assert all(r["has_identity"] for n, r in by_name.items() if n != "manual")

    def test_forbidden_is_tolerated_and_reported_as_none(self):
        """An image upgraded without re-applying RBAC gets a 403 here.

        None, not []: the caller must be able to tell "not permitted" from "permitted, no User
        yet", because writing [] would erase every row and read as "nobody has logged in".
        """
        assert _client(_handler(status=403)).fetch_users() is None

    @pytest.mark.parametrize("status", [401, 404, 500, 503])
    def test_every_other_status_still_raises(self, status):
        """Only 403 is forgiven, and it is forgiven because the poll must not fail on it — the
        refusal itself is recorded and shown, not hidden (see the poller tests)."""
        with pytest.raises(ClusterError):
            _client(_handler(status=status)).fetch_users()

    def test_the_log_names_the_grant_to_add(self, caplog):
        with caplog.at_level("DEBUG", logger="gsd.kube"):
            _client(_handler(status=403)).fetch_users()
        assert "not permitted to list users" in caplog.text


class TestStore:
    def test_replace_is_wholesale_so_a_departed_user_disappears(self, tmp_path):
        """An upsert would leave a deleted account listed as a user of the cluster."""
        store = Store(str(tmp_path / "t.db"))
        store.replace_users("c1", _recs({"a": "Ann", "b": "Bob"}), now_iso())
        assert store.user_full_name("c1", "b") == "Bob"
        store.replace_users("c1", _recs({"a": "Ann"}), now_iso())
        assert store.user_full_name("c1", "a") == "Ann"
        assert store.user_full_name("c1", "b") is None
        assert [u["user_name"] for u in store.users("c1")] == ["a"]

    def test_names_are_per_cluster(self, tmp_path):
        """Two clusters can hold the same username as different people."""
        store = Store(str(tmp_path / "t.db"))
        store.replace_users("c1", _recs({"a": "Ann One"}), now_iso())
        store.replace_users("c2", _recs({"a": "Ann Two"}), now_iso())
        assert store.user_full_name("c1", "a") == "Ann One"
        assert store.user_full_name("c2", "a") == "Ann Two"

    def test_unknown_user_is_none_not_an_error(self, tmp_path):
        store = Store(str(tmp_path / "t.db"))
        assert store.user_full_name("c1", "never-seen") is None
        assert store.user_record("c1", "never-seen") is None

    def test_a_successful_replace_records_the_source_as_ok_and_a_refusal_as_forbidden(self, tmp_path):
        store = Store(str(tmp_path / "t.db"))
        assert store.users_source("c1") is None, "nothing has reported yet"
        store.replace_users("c1", _recs({"a": None}), "2026-09-03T10:00:00Z")
        assert store.users_source("c1") == {"state": "ok", "observed_at": "2026-09-03T10:00:00Z"}
        store.mark_users_unavailable("c1", "2026-09-03T10:15:00Z")
        assert store.users_source("c1") == {"state": "forbidden", "observed_at": "2026-09-03T10:15:00Z"}
        assert [u["user_name"] for u in store.users("c1")] == ["a"], "a refusal leaves last cycle's rows"


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
        assert int(conn.execute("PRAGMA user_version").fetchone()[0]) >= 7
        cols = {r[1]: r for r in conn.execute("PRAGMA table_info(ocp_user)")}
        assert {"cluster_id", "user_name", "full_name", "created_at", "providers", "has_identity",
                "observed_at"} <= set(cols)
        assert cols["full_name"][3] == 0, "full_name is nullable now: a user with no name is still a user"

    def test_a_v6_database_with_the_name_cache_is_rebuilt_in_the_new_shape(self, tmp_path):
        """Migration 7 replaces the display-name cache. Nothing in it is worth carrying: the next
        poll rewrites the table wholesale, and until then the source is 'pending', not 'ok'."""
        p = str(tmp_path / "t.db")
        Store(p)
        conn = sqlite3.connect(p)
        conn.execute("DROP TABLE ocp_user")
        conn.execute("DROP TABLE ocp_user_status")
        conn.execute("""CREATE TABLE ocp_user (cluster_id TEXT NOT NULL, user_name TEXT NOT NULL,
                        full_name TEXT NOT NULL, observed_at TEXT NOT NULL, PRIMARY KEY(cluster_id, user_name))""")
        conn.execute("INSERT INTO ocp_user VALUES ('c1', 'a', 'Ann', 'x')")
        conn.execute("PRAGMA user_version = 6")
        conn.commit()
        conn.close()
        store = Store(p)
        assert store.users("c1") == [] and store.users_source("c1") is None

    def test_replaying_against_a_fresh_database_is_a_no_op(self, tmp_path):
        """SCHEMA already created the tables. _migrate tolerates exactly one error ("duplicate
        column name"), so every statement in the replay must be safe against a table that exists."""
        p = str(tmp_path / "t.db")
        Store(p)
        conn = sqlite3.connect(p)
        conn.execute("PRAGMA user_version = 3")   # force the replay, tables still present
        conn.commit()
        conn.close()
        Store(p)   # must not raise


class TestJoin:
    def test_members_carry_their_name_and_absence_stays_absent(self, tmp_path):
        """The LEFT JOIN on the member surfaces, which is why no handler needed a second store call."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["named", "unnamed"]}, {}, seen)
        store.replace_users("c1", _recs({"named": "Named Person"}), seen)

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
        store.replace_users("c1", _recs({"aaa": "Zoe", "ccc": "Adam"}), seen)
        assert [r["user_name"] for r in store.group_members("c1", "g1")] == ["aaa", "bbb", "ccc"]

    def test_the_users_index_is_the_user_objects_with_membership_as_an_attribute(self, tmp_path):
        """The re-sourced index: a User in no group is a row with group_count 0; a member with no
        User is not a row, and is reported by synced_members_without_user instead."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["named", "unnamed"]}, {}, seen)
        store.replace_users("c1", _recs({"named": "Named Person", "loner": None}), seen)

        rows = {r["user_name"]: r for r in store.users("c1")}
        assert set(rows) == {"named", "loner"}
        assert rows["named"]["full_name"] == "Named Person" and rows["loner"]["full_name"] is None
        assert rows["named"]["group_count"] == 1 and rows["named"]["first_seen_at"] == seen
        assert rows["loner"]["group_count"] == 0 and rows["loner"]["first_seen_at"] is None
        assert store.synced_members_without_user("c1") == ["unnamed"]

    def test_users_index_ordering_is_still_by_user_id(self, tmp_path):
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["aaa", "bbb", "ccc"]}, {}, seen)
        store.replace_users("c1", _recs({"aaa": "Zoe", "bbb": None, "ccc": "Adam"}), seen)
        assert [r["user_name"] for r in store.users("c1")] == ["aaa", "bbb", "ccc"]

    def test_users_index_stays_one_row_per_user_across_groups(self, tmp_path):
        """Guards the pre-grouped joins: a join that multiplied rows would inflate group_count silently."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.sync_members("c1", {"g1": ["multi"], "g2": ["multi"], "g3": ["multi"]}, {}, seen)
        store.replace_users("c1", _recs({"multi": "Many Groups"}), seen)
        rows = store.users("c1")
        assert len(rows) == 1
        assert rows[0]["group_count"] == 3 and rows[0]["full_name"] == "Many Groups"

    def test_users_index_still_fetches_limit_plus_one_and_pages(self, tmp_path):
        """The truncation contract survives the re-sourcing: the caller detects a clip by the extra
        row. And offset pages, because a cluster's User count is everyone who has ever logged in."""
        store = Store(str(tmp_path / "t.db"))
        seen = now_iso()
        store.replace_users("c1", _recs({"a": None, "b": None, "c": None}), seen)
        assert [r["user_name"] for r in store.users("c1", limit=2)] == ["a", "b", "c"]
        assert [r["user_name"] for r in store.users("c1", limit=2, offset=2)] == ["c"]
        assert store.count_users("c1") == 3
