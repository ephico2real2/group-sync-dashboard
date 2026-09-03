"""Who a granted binding reaches: Store.all_bindings(reach=True).

A binding names a Group; the Group has members; some of those members have logged in. The Access
granted tab shows the last two numbers beside every granted row, because "admin in prod-ns is
granted to app-ocp-rbac-alpha-ns-admin" answers nothing until you know whether that group is two
people or nobody — and whether any of them has ever used the cluster.

The numbers are opt-in on the query because all_bindings has three hot callers that want none of
them (the metrics scrape, the poller's audit planning, /api/clusters); a join they never asked for
would be paid on every scrape. So the first thing pinned here is that `reach=False` is what it was.
"""

from __future__ import annotations

from gsd.store import Store
from gsd.timeutil import now_iso

T = "2026-09-03T12:00:00Z"


def _binding(group, name="rb", kind="RoleBinding", ns="prod", role="admin"):
    return {"binding_kind": kind, "binding_namespace": ns if kind == "RoleBinding" else "",
            "binding_name": name, "role_kind": "ClusterRole", "role_name": role, "group_name": group}


def _group(name, members):
    return {"name": name, "member_count": members, "sync_provider": "ldap", "group_synced_at": T, "ldap_uid": None}


def _user(name, identity=True):
    return {"user_name": name, "full_name": None, "created_at": T, "providers": ["ldap"] if identity else [],
            "has_identity": identity}


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.upsert_cluster("c1", "https://x", True)
    return store


def test_reach_false_returns_exactly_the_columns_it_always_did(tmp_path):
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group("team", 1)], T)
    store.replace_bindings("c1", [_binding("team")], T)
    rows = store.all_bindings("c1")
    assert set(rows[0]) == {"binding_kind", "binding_namespace", "binding_name", "role_kind", "role_name",
                            "group_name", "managed_source", "exception", "audit_stamped", "finding"}
    assert "member_count" not in rows[0] and "logged_in_count" not in rows[0]


def test_reach_counts_members_and_the_members_who_have_logged_in(tmp_path):
    """Three members; one has a User with an identity, one a hand-created User without, one no
    User at all. Members: 3. Logged in: 1. The manual account is a member and not a login."""
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group("team", 3)], T)
    store.sync_members("c1", {"team": ["alice", "manual", "dave"]}, {}, T)
    store.replace_users("c1", [_user("alice"), _user("manual", identity=False)], T)
    store.replace_bindings("c1", [_binding("team")], T)
    row = store.all_bindings("c1", reach=True)[0]
    assert (row["finding"], row["member_count"], row["logged_in_count"]) == ("ok", 3, 1)


def test_a_group_with_no_members_reaches_nobody_and_says_zero_not_null(tmp_path):
    """The group exists, so the binding is `ok` — and it grants nobody today. 0, distinct from
    the NULL a missing Group object produces."""
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group("empty", 0)], T)
    store.replace_bindings("c1", [_binding("empty")], T)
    row = store.all_bindings("c1", reach=True)[0]
    assert (row["finding"], row["member_count"], row["logged_in_count"]) == ("ok", 0, 0)


def test_no_group_object_means_null_on_both_whatever_the_tier(tmp_path):
    store = _store(tmp_path)
    store.record_managed_groups("c1", [{"name": "gone", "sync_provider": "ldap"}], T)
    store.replace_bindings("c1", [
        _binding("gone", name="dangling-rb"),
        _binding("never-existed", name="unresolved-rb"),
        _binding("system:authenticated", name="builtin-crb", kind="ClusterRoleBinding"),
    ], T)
    rows = {r["binding_name"]: r for r in store.all_bindings("c1", reach=True)}
    assert {n: r["finding"] for n, r in rows.items()} == {
        "dangling-rb": "dangling", "unresolved-rb": "unresolved", "builtin-crb": "built_in"}
    assert all(r["member_count"] is None and r["logged_in_count"] is None for r in rows.values())


def test_the_join_cannot_multiply_a_binding_row(tmp_path):
    """Two bindings on one group of four members: still exactly two rows."""
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group("team", 4)], T)
    store.sync_members("c1", {"team": ["a", "b", "c", "d"]}, {}, T)
    store.replace_users("c1", [_user("a"), _user("b")], T)
    store.replace_bindings("c1", [_binding("team", name="rb1"), _binding("team", name="rb2", ns="dev")], T)
    rows = store.all_bindings("c1", reach=True)
    # Ordered by group, kind, namespace, name — so rb2 in `dev` precedes rb1 in `prod`.
    assert [r["binding_name"] for r in rows] == ["rb2", "rb1"]
    assert all((r["member_count"], r["logged_in_count"]) == (4, 2) for r in rows)


def test_the_name_join_is_byte_exact(tmp_path):
    """`Alice` the User is not `alice` the member — the same rule every join onto ocp_user keeps."""
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group("team", 1)], T)
    store.sync_members("c1", {"team": ["alice"]}, {}, T)
    store.replace_users("c1", [_user("Alice")], T)
    store.replace_bindings("c1", [_binding("team")], T)
    row = store.all_bindings("c1", reach=True)[0]
    assert (row["member_count"], row["logged_in_count"]) == (1, 0)


def test_logged_in_never_exceeds_members_and_paging_still_applies(tmp_path):
    store = _store(tmp_path)
    store.replace_group_state("c1", [_group(f"g{i}", 2) for i in range(5)], T)
    store.sync_members("c1", {f"g{i}": ["p", "q"] for i in range(5)}, {}, T)
    store.replace_users("c1", [_user("p"), _user("q")], T)
    store.replace_bindings("c1", [_binding(f"g{i}", name=f"rb{i}") for i in range(5)], T)
    rows = store.all_bindings("c1", limit=2, offset=2, reach=True)
    assert [r["binding_name"] for r in rows] == ["rb2", "rb3"]
    assert all(r["logged_in_count"] <= r["member_count"] for r in rows)
