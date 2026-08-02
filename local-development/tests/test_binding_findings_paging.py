"""The binding-findings response is bounded, and its counts still describe the cluster.

Third endpoint with this defect, and the reason the pattern is now a rule in
`docs/api-contract.md`. Measured before the fix at ten times the reference cluster: 2,280
rows and 545,800 bytes in one response, re-fetched every 30 seconds by the page's own
auto-refresh — 5.3x the payload that got `list_users` bounded.

The trap in fixing it is the same one that shipped twice: bound the rows, forget the counts,
and the tier totals silently become totals of the page. That is worse than the unbounded
version, because a wrong number reads as a fact while a slow page reads as a slow page. So
these tests care much more about `counts` than about `limit`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

# 210 bindings across the tiers. Enough that a page of 50 is a small slice of it, so a count
# taken from the page cannot coincidentally match the count taken from the cluster.
RESOLVED = 100        # groups that exist
UNMANAGED = 30        # of those, bound with no policy provenance
OK = RESOLVED - UNMANAGED   # the rest, templated by the operator
DANGLING = 60
BUILT_IN = 50
TOTAL = OK + UNMANAGED + DANGLING + BUILT_IN


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "t.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    now = now_iso()

    # Groups that exist, so their bindings resolve.
    store.replace_group_state(
        "c1",
        [{"name": f"grp-{i}", "member_count": 1, "sync_provider": "gs_ldap",
          "group_synced_at": now, "ldap_uid": None} for i in range(RESOLVED)],
        now,
    )
    # A group the operator once managed and no longer syncs -> its bindings are `dangling`.
    store.record_managed_groups(
        "c1", [{"name": f"gone-{i}", "sync_provider": "gs_ldap"} for i in range(DANGLING)]
        + [{"name": f"grp-{i}", "sync_provider": "gs_ldap"} for i in range(UNMANAGED)],
        now,
    )

    bindings = []
    # `ok`: resolves, and templated by the policy operator.
    bindings += [
        {"binding_kind": "RoleBinding", "binding_namespace": f"ns{i}",
         "binding_name": f"ok-{i}", "role_kind": "ClusterRole", "role_name": "view",
         "group_name": f"grp-{i}", "managed_source": "policy"}
        for i in range(UNMANAGED, RESOLVED)
    ]
    # `unmanaged`: resolves, operator-synced, but nothing templates the binding.
    bindings += [
        {"binding_kind": "RoleBinding", "binding_namespace": f"nsu{i}",
         "binding_name": f"un-{i}", "role_kind": "ClusterRole", "role_name": "admin",
         "group_name": f"grp-{i}"}
        for i in range(UNMANAGED)
    ]
    # `dangling`: the operator managed this group, and it is gone.
    bindings += [
        {"binding_kind": "RoleBinding", "binding_namespace": f"nsd{i}",
         "binding_name": f"dang-{i}", "role_kind": "ClusterRole", "role_name": "edit",
         "group_name": f"gone-{i}"}
        for i in range(DANGLING)
    ]
    # `built_in`: a virtual group, no object by design.
    bindings += [
        {"binding_kind": "RoleBinding", "binding_namespace": f"nsb{i}",
         "binding_name": f"bi-{i}", "role_kind": "ClusterRole",
         "role_name": "system:image-puller",
         "group_name": f"system:serviceaccounts:ns{i}"}
        for i in range(BUILT_IN)
    ]
    store.replace_bindings("c1", bindings, now)
    store.close()

    settings = Settings(db_path=db,
                        clusters=[ClusterConfig("c1", "https://x", token_env="T")])
    return TestClient(build_app(settings, run_poller=False))


def get(client, **params) -> dict:
    r = client.get("/api/clusters/c1/bindings/findings", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_rows_are_bounded(client):
    body = get(client, limit=50)
    returned = sum(len(body[t]) for t in
                   ("ok", "dangling", "unresolved", "built_in", "unmanaged"))
    assert returned == 50, "the limit applies across all tiers, not per tier"
    assert body["truncated"] is True


def test_counts_describe_the_cluster_not_the_page(client):
    """The whole point. A tier count taken from a page is a wrong number stated as a fact."""
    body = get(client, limit=50)
    assert sum(body["counts"].values()) == TOTAL
    assert body["total"] == TOTAL
    assert body["counts"]["dangling"] == DANGLING
    assert body["counts"]["unmanaged"] == UNMANAGED
    assert body["counts"]["built_in"] == BUILT_IN


def test_counts_do_not_move_with_the_page_size(client):
    """Same cluster, four page sizes, one set of counts."""
    seen = [tuple(sorted(get(client, limit=n)["counts"].items())) for n in (1, 50, 200, 5000)]
    assert len(set(seen)) == 1, f"counts changed with the limit: {seen}"


def test_a_complete_page_is_not_flagged_truncated(client):
    body = get(client, limit=5000)
    returned = sum(len(body[t]) for t in
                   ("ok", "dangling", "unresolved", "built_in", "unmanaged"))
    assert returned == TOTAL
    assert body["truncated"] is False


def test_offset_walks_the_set_exactly_once(client):
    """Paging must not skip or repeat a binding."""
    seen, offset = [], 0
    while True:
        body = get(client, limit=70, offset=offset)
        page = [b["binding_name"] for t in
                ("ok", "dangling", "unresolved", "built_in", "unmanaged") for b in body[t]]
        if not page:
            break
        seen += page
        offset += 70
    assert len(seen) == TOTAL
    assert len(set(seen)) == TOTAL, "a binding appeared on two pages"


def test_the_tier_structure_survives_paging(client):
    """The five keys are the feature; the UI indexes them directly."""
    body = get(client, limit=10)
    for tier in ("ok", "dangling", "unresolved", "built_in", "unmanaged"):
        assert tier in body, f"{tier} disappeared from the response"
        assert isinstance(body[tier], list)


def test_operator_configs_are_not_paged(client):
    """Bounded by CR count, and the UI reads `present` to tell 'absent' from 'zero CRs'."""
    assert "operator_configs" in get(client, limit=1)
