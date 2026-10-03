"""The direct-user-grant list is bounded, and says so when it truncates.

This was unbounded at every layer: the store returned every row, the API returned every
row, and the page rendered every row. On a test cluster with six grants that is invisible;
on a cluster with a few thousand it is a payload and a DOM built to show a list nobody can
read end to end.

The fix is only safe if two things hold, and both are tested here:

  * ordering is applied BEFORE the limit, so a truncated page is the WORST n rather than an
    arbitrary n. A truncated audit list that dropped the cluster-admin would be worse than
    no list at all.
  * `total` counts what the limit left out, so the page can say so. Silent truncation is
    the actual danger — it reads as "these are all of them".

`by_namespace` is deliberately NOT paged, and that asymmetry is tested too: it is one row
per namespace, it is the view the risk ranking is computed from, and truncating it would
make the ranking a ranking of an arbitrary subset.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

ROLES = ["view", "edit", "admin"]


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "t.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    rows = [
        {"binding_kind": "RoleBinding", "binding_namespace": f"ns-{i % 3}",
         "binding_name": f"rb{i}", "role_kind": "ClusterRole",
         "role_name": ROLES[i % 3], "user_name": f"u{i}", "is_platform": 0}
        for i in range(25)
    ]
    rows.append(
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "crb", "role_kind": "ClusterRole",
         "role_name": "cluster-admin", "user_name": "root", "is_platform": 0})
    # A platform identity, to prove the default exclusion survives paging.
    rows.append(
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "ka", "role_kind": "ClusterRole",
         "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1})
    store.replace_user_bindings("c1", rows, now_iso())
    settings = Settings(db_path=db,
                        clusters=[ClusterConfig("c1", "https://x", token_env="T")])
    return TestClient(build_app(settings, run_poller=False))


def get(client, **params) -> dict:
    r = client.get("/api/clusters/c1/user-bindings", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_total_counts_past_the_limit(client):
    """The number the page reports is the number that exists, not the number returned."""
    body = get(client, limit=5)
    assert body["total"] == 26, "26 non-platform rows were seeded"
    assert len(body["bindings"]) == 5
    assert body["truncated"] is True


def test_untruncated_says_so(client):
    body = get(client, limit=5000)
    assert body["total"] == len(body["bindings"]) == 26
    assert body["truncated"] is False, (
        "a complete list reported as truncated would send the reader looking for rows that "
        "are already on the page"
    )


def test_the_limit_keeps_the_worst_rows(client):
    """Ordering before the limit is the whole reason this is safe to truncate.

    If LIMIT were applied to an unordered scan, the one cluster-admin could fall off a
    truncated page and the audit would omit exactly the row it exists to surface.
    """
    body = get(client, limit=1)
    assert body["bindings"][0]["role_name"] == "cluster-admin"


def test_offset_walks_the_whole_set_exactly_once(client):
    """Paging must not skip or repeat a binding — an audit that does either is wrong."""
    seen, offset = [], 0
    while True:
        body = get(client, limit=7, offset=offset)
        if not body["bindings"]:
            break
        seen += [b["binding_name"] for b in body["bindings"]]
        offset += 7
    assert len(seen) == 26
    assert len(set(seen)) == 26, "a binding appeared on two pages"


def test_last_page_is_not_truncated(client):
    """`truncated` compares offset+len against total, so the final page must read False."""
    assert get(client, limit=5, offset=24)["truncated"] is False


def test_namespace_filter_scopes_rows_and_total(client):
    body = get(client, namespace="ns-1")
    assert body["total"] == len(body["bindings"]) == 8
    assert {b["binding_namespace"] for b in body["bindings"]} == {"ns-1"}


def test_cluster_scope_sentinel(client):
    """'' cannot travel in a query string, so the API speaks a token instead.

    Without the sentinel there is no way to ask for the cluster-scoped rows: an empty
    `namespace=` is indistinguishable from the parameter being absent, which returns
    everything — the opposite of the filter that was asked for.
    """
    body = get(client, namespace="(cluster-scoped)")
    assert body["total"] == 1
    assert [b["binding_namespace"] for b in body["bindings"]] == [""]


def test_rollup_is_never_paged(client):
    """by_namespace stays whole even when the rows are filtered and limited.

    The rollup is what the page ranks risk from. A filtered or truncated rollup would rank
    a subset while looking like it ranked the cluster.
    """
    full = get(client, limit=5000)["by_namespace"]
    assert len(full) == 4, "ns-0, ns-1, ns-2 and the cluster-scoped row"
    assert get(client, limit=1)["by_namespace"] == full
    assert get(client, namespace="ns-1")["by_namespace"] == full


def test_platform_identities_stay_excluded_under_paging(client):
    """The kubeadmin exclusion is not something a limit or filter may quietly undo."""
    body = get(client, limit=5000)
    assert all(b["user_name"] != "kubeadmin" for b in body["bindings"])
    assert body["excluded_platform"] == 1
    assert get(client, include_platform=True)["total"] == 27


# ── #503: the grants the operator acknowledged — counted beside the platform's, each one reachable ──

def _acknowledged_app(tmp_path):
    """Three acknowledged grants (two by the label, one by the exception annotation), one to review, and a
    platform identity whose binding is labelled too: the platform wins."""
    db = str(tmp_path / "ack.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    grants = [("ClusterRoleBinding", "", "poller", "cluster-admin", "ocp-oauth-bind-serviceid", 0, "group-sync-operator-helm", None),
              ("RoleBinding", "ops", "reader", "view", "ocp-oauth-bind-serviceid", 0, "group-sync-operator-helm", None),
              ("RoleBinding", "pay", "vendor-view", "view", "vendor-support", 0, None, "vendor read-only access, TICKET-7"),
              ("RoleBinding", "pay", "jdoe-edit", "edit", "jdoe", 0, None, None),
              ("ClusterRoleBinding", "", "ka", "cluster-admin", "kubeadmin", 1, "team-x", None)]
    store.replace_user_bindings("c1", [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
         "role_name": role, "user_name": user, "is_platform": platform}
        for k, ns, name, role, user, platform, _, _ in grants], now_iso())
    store.replace_bindings("c1", [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
         "role_name": role, "group_name": user, "subject_kind": "User", "is_platform": platform,
         "managed_source": label, "exception": exception}
        for k, ns, name, role, user, platform, label, exception in grants], now_iso())
    store.close()
    settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")])
    return TestClient(build_app(settings, run_poller=False))


def test_t503_9_the_acknowledged_grants_are_counted_and_listed_with_what_acknowledged_them(tmp_path):
    body = _acknowledged_app(tmp_path).get("/api/clusters/c1/user-bindings").json()
    assert [b["user_name"] for b in body["bindings"]] == ["jdoe"] and body["total"] == 1
    assert [r["namespace"] for r in body["by_namespace"]] == ["pay"]
    assert body["excluded_platform"] == 1, "a labelled platform identity stays the platform's"
    assert body["acknowledged"] == 3 and body["acknowledged_truncated"] is False
    assert [(b["user_name"], b["binding_namespace"], b["binding_name"], b["role_name"], b["managed_source"], b["exception"])
            for b in body["acknowledged_bindings"]] == [
        ("ocp-oauth-bind-serviceid", "", "poller", "cluster-admin", "group-sync-operator-helm", None),
        ("ocp-oauth-bind-serviceid", "ops", "reader", "view", "group-sync-operator-helm", None),
        ("vendor-support", "pay", "vendor-view", "view", None, "vendor read-only access, TICKET-7")]


def test_t503_9_the_acknowledged_list_pages_like_bindings_and_ignores_the_namespace_filter(tmp_path):
    client = _acknowledged_app(tmp_path)
    get_ = lambda **p: client.get("/api/clusters/c1/user-bindings", params=p).json()   # noqa: E731
    first, second = get_(limit=2), get_(limit=2, offset=2)
    assert [b["binding_name"] for b in first["acknowledged_bindings"]] == ["poller", "reader"]
    assert first["acknowledged_truncated"] is True and first["acknowledged"] == 3
    assert [b["binding_name"] for b in second["acknowledged_bindings"]] == ["vendor-view"]
    assert second["acknowledged_truncated"] is False
    narrowed = get_(namespace="pay")
    assert narrowed["total"] == 1 and narrowed["acknowledged"] == 3 and len(narrowed["acknowledged_bindings"]) == 3


def test_limit_is_bounded(client):
    """An unbounded limit is the same defect wearing a query parameter."""
    assert client.get("/api/clusters/c1/user-bindings",
                      params={"limit": 99999}).status_code == 422
    assert client.get("/api/clusters/c1/user-bindings",
                      params={"limit": 0}).status_code == 422


# ── #255: the platform list the excluded count comes from, and its stale entries ───────────────────

def _platform_users_app(tmp_path, *, proxy: bool):
    """kubeadmin and ocp-oauth-bind-serviceid stored as the poller classifies them under
    `platformUsers.additionalNames: [ocp-oauth-bind-serviceid, ghost]`; nothing names `ghost`."""
    from gsd.config import PlatformUsers
    db = str(tmp_path / "pu.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    store.replace_user_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "poller",
         "role_kind": "ClusterRole", "role_name": "poller", "user_name": "ocp-oauth-bind-serviceid", "is_platform": 1},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ka",
         "role_kind": "ClusterRole", "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1},
        {"binding_kind": "RoleBinding", "binding_namespace": "legacy", "binding_name": "jdoe-edit",
         "role_kind": "ClusterRole", "role_name": "edit", "user_name": "jdoe", "is_platform": 0},
    ], now_iso())
    store.close()
    settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")],
                        oauth_proxy_enabled=proxy,
                        platform_users=PlatformUsers(additional_names=frozenset({"ocp-oauth-bind-serviceid", "ghost"})))
    return TestClient(build_app(settings, run_poller=False))


def test_t255_7_a_stale_additional_name_is_named_at_the_wide_tier(tmp_path):
    """`ghost` matches no User subject on this cluster; the bind account matches its own (platform) rows, so it is
    not stale — the judgement is against every User subject, platform ones included."""
    body = _platform_users_app(tmp_path, proxy=False).get("/api/clusters/c1/user-bindings").json()
    assert body["scope"] == "all"
    assert body["platform_users_unmatched"] == {"additionalNames": ["ghost"]}
    assert body["platform_users_source"] == {"configMap": None, "replaced": [], "additional": ["additionalNames"]}
    assert body["excluded_platform"] == 2 and body["total"] == 1


def test_t255_7_the_stale_entries_and_the_source_are_withheld_at_self(tmp_path):
    body = _platform_users_app(tmp_path, proxy=True).get(
        "/api/clusters/c1/user-bindings", headers={"X-Forwarded-User": "jdoe"}).json()
    assert body["scope"] == "self"
    assert body["platform_users_unmatched"] is None and body["platform_users_source"] is None
    assert body["excluded_platform"] is None
