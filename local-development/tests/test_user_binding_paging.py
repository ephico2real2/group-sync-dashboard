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


def test_limit_is_bounded(client):
    """An unbounded limit is the same defect wearing a query parameter."""
    assert client.get("/api/clusters/c1/user-bindings",
                      params={"limit": 99999}).status_code == 422
    assert client.get("/api/clusters/c1/user-bindings",
                      params={"limit": 0}).status_code == 422
