"""A cluster with no group-sync-operator must still report its groups.

REPORTED FROM A REAL CLUSTER. Deployed where the operator is not installed, the dashboard
warned that it could not detect the CRD and then showed no groups at all. The hand-made Groups
on that cluster should have appeared as `unattributed`.

Ordering plus an unhandled status. `fetch()` lists GroupSync FIRST; a 404 on the absent CRD
became `ClusterError(UNREACHABLE)`, `poll_once` caught it, recorded the cluster unreachable and
returned — so the Groups list call was never made. The dashboard's whole subject is groups, and
it was reporting none of them because a CR type it can live without was missing.

This file also covers the `empty` and `unattributed` filters behind the dashboard's "Group
state" selector. `empty` used to be scoped to operator-synced groups, which made it useless on
exactly this cluster: with no operator every group is unattributed, so `empty` matched nothing
however many groups granted nobody. It now means "zero members, whatever created it", and
therefore OVERLAPS `unattributed` on purpose.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.kube import GROUP_API, GROUPSYNC_API, ClusterClient, ClusterError
from gsd.poller import poll_once
from gsd.store import Store
from gsd.timeutil import now_iso

GROUPS = {
    "kind": "GroupList",
    "items": [
        # Hand-made, with members. No sync-provider label, because nothing synced it.
        {"metadata": {"name": "platform-admins"}, "users": ["alice", "bob"]},
        # Hand-made and has no members: `unattributed` AND `empty`, both by design.
        {"metadata": {"name": "placeholder-team"}, "users": []},
    ],
}


def _client(handler):
    """A ClusterClient whose HTTP goes to `handler`."""
    cluster = ClusterConfig("no-operator", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(handler)
    original = client._client

    def patched():
        return httpx.Client(transport=transport, base_url="https://x")

    client._client = patched
    return client, cluster, original


def _handler(groupsync_status=404, groupsync_body=None, groups=GROUPS):
    """Serve Groups normally and the GroupSync CRD with whatever status the test wants."""
    def handle(request):
        if request.url.path.startswith(GROUPSYNC_API):
            if groupsync_status == 200:
                return httpx.Response(200, json=groupsync_body or {"kind": "GroupSyncList",
                                                                   "items": []})
            # What the API server actually returns for an uninstalled CRD.
            return httpx.Response(groupsync_status, json={
                "kind": "Status", "status": "Failure", "code": groupsync_status,
                "message": "the server could not find the requested resource",
            })
        if request.url.path.startswith(GROUP_API):
            return httpx.Response(200, json=groups)
        return httpx.Response(404, json={"kind": "Status"})
    return handle


class TestAMissingCRDIsNotAPollFailure:
    def test_groups_are_still_fetched(self):
        """The regression: a 404 on the CRD used to abort before Groups was ever listed."""
        client, _, _ = _client(_handler())
        groupsyncs, groups = client.fetch()
        assert groupsyncs == [], "an absent CRD must read as zero CRs, not raise"
        assert [g.name for g in groups] == ["placeholder-team", "platform-admins"] or \
               sorted(g.name for g in groups) == ["placeholder-team", "platform-admins"], \
               f"groups were not fetched: {[g.name for g in groups]}"

    def test_the_warning_says_what_it_means_for_the_reader(self, caplog):
        """A bare "CRD not found" leaves the operator wondering why everything is unattributed."""
        client, _, _ = _client(_handler())
        with caplog.at_level("WARNING", logger="gsd.kube"):
            client.fetch()
        assert "group-sync-operator is not installed" in caplog.text
        assert "unattributed" in caplog.text, (
            "the log must connect the absent CRD to what the reader will see on the Groups tab"
        )

    @pytest.mark.parametrize("status", [401, 403, 500, 503])
    def test_every_other_status_still_fails_the_poll(self, status):
        """"The CRD does not exist" and "you may not read it" are different problems.

        Swallowing 403 would present a missing RBAC grant as a healthy operator-less cluster,
        which is the failure this dashboard exists to prevent, applied to itself.
        """
        client, _, _ = _client(_handler(groupsync_status=status))
        with pytest.raises(ClusterError):
            client.fetch()

    def test_a_500_whose_body_mentions_404_is_not_read_as_an_absent_crd(self):
        """The reason the check is anchored on the path rather than a bare "404" substring.

        `_get` appends 200 characters of the response body to the message, so a loose
        `"404" in message` test would silently turn a real outage into "operator not installed".
        """
        def handle(request):
            if request.url.path.startswith(GROUPSYNC_API):
                return httpx.Response(500, json={"kind": "Status", "message":
                                                 "upstream returned 404 from etcd proxy"})
            return httpx.Response(200, json=GROUPS)
        client, _, _ = _client(handle)
        with pytest.raises(ClusterError):
            client.fetch()


class TestTheClusterPollsOkAndTheGroupsLand:
    """End to end: poll a CRD-less cluster and read the result back out of the store."""

    @pytest.fixture()
    def polled(self, tmp_path, monkeypatch):
        store = Store(str(tmp_path / "t.db"))
        store.upsert_cluster("no-operator", "https://x", True)

        import gsd.poller as poller_mod
        client, cluster, _ = _client(_handler())
        monkeypatch.setattr(poller_mod, "ClusterClient", lambda *a, **kw: client)
        outcome = poll_once(store, cluster, timeout=5)
        return store, outcome

    def test_the_cluster_is_ok_not_unreachable(self, polled):
        """It used to record `unreachable`, so the card was red on a perfectly healthy cluster."""
        store, outcome = polled
        assert outcome == "ok", f"a CRD-less cluster polled as {outcome!r}"

    def test_both_groups_are_stored_and_unattributed(self, polled):
        store, _ = polled
        counts = store.group_counts("no-operator")
        assert counts["total"] == 2, f"groups did not reach the store: {counts}"
        assert counts["unattributed"] == 2, (
            f"with no CR to claim them every group must be unattributed: {counts}"
        )

    def test_a_memberless_group_is_reported_empty_even_with_no_operator(self, polled):
        """The point of rescoping `empty`.

        While it required `sync_provider IS NOT NULL`, this assertion was `== 0`: a cluster with
        no operator could have every group granting nobody and the `empty` filter would show an
        empty list. `placeholder-team` is now returned by BOTH filters, which is intended — they
        answer different questions and are never summed.
        """
        store, _ = polled
        assert store.group_counts("no-operator")["empty"] == 1
        assert [g["name"] for g in store.groups("no-operator", "empty")] == ["placeholder-team"]
        assert "placeholder-team" in [
            g["name"] for g in store.groups("no-operator", "unattributed")]


class TestTheDashboardsGroupStateSelector:
    """`all` / `empty` / `unattributed` — the three options the Groups tab offers.

    Driven through the HTTP API rather than the store, because that is what the selector calls
    and the `state` parameter is validated by a regex at the route.
    """

    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "t.db")
        store = Store(db)
        store.upsert_cluster("c1", "https://x", True)
        now = now_iso()
        store.replace_group_state("c1", [
            # synced with members -> neither empty nor unattributed
            {"name": "synced-full", "member_count": 3, "sync_provider": "corp_ldap",
             "group_synced_at": now, "ldap_uid": None},
            # synced, zero members -> EMPTY (the LDAP-side failure)
            {"name": "synced-empty", "member_count": 0, "sync_provider": "corp_ldap",
             "group_synced_at": now, "ldap_uid": None},
            {"name": "synced-empty-2", "member_count": 0, "sync_provider": "corp_ldap",
             "group_synced_at": now, "ldap_uid": None},
            # hand-made -> UNATTRIBUTED whether or not it has members
            {"name": "hand-made", "member_count": 2, "sync_provider": None,
             "group_synced_at": None, "ldap_uid": None},
            {"name": "hand-made-empty", "member_count": 0, "sync_provider": None,
             "group_synced_at": None, "ldap_uid": None},
        ], now)
        settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")],
                            db_path=db)
        return TestClient(build_app(settings, run_poller=False))

    def _names(self, client, state):
        r = client.get("/api/clusters/c1/groups", params={"state": state})
        assert r.status_code == 200, r.text
        return [g["name"] for g in r.json()]

    def test_all_returns_every_group(self, client):
        assert len(self._names(client, "all")) == 5

    def test_empty_selects_every_group_with_no_members(self, client):
        """Provenance-blind: two synced and one hand-made, all granting nobody."""
        assert self._names(client, "empty") == [
            "hand-made-empty", "synced-empty", "synced-empty-2"]

    def test_empty_includes_the_hand_made_one(self, client):
        """The specific regression. This asserted `not in` while `empty` required a provider."""
        assert "hand-made-empty" in self._names(client, "empty")

    def test_unattributed_selects_by_provenance_not_by_member_count(self, client):
        assert self._names(client, "unattributed") == ["hand-made", "hand-made-empty"]

    def test_the_two_filters_overlap_and_that_is_the_contract(self, client):
        """Pinned as a FACT, not an accident, so nobody re-adds the provider scoping quietly.

        A hand-made group with no members is in both lists. The consequence, which is the thing
        to protect: `empty` and `unattributed` must never be added together to describe a
        cluster, in a KPI, a metric or a doc.
        """
        overlap = set(self._names(client, "empty")) & set(self._names(client, "unattributed"))
        assert overlap == {"hand-made-empty"}, (
            f"expected exactly the memberless hand-made group in both, got {overlap}"
        )

    def test_results_are_sorted_by_name(self, client):
        """The tab renders them in order; the ORDER BY is what makes the list stable."""
        for state in ("all", "empty", "unattributed"):
            names = self._names(client, state)
            assert names == sorted(names), f"{state} came back unsorted: {names}"

    def test_the_counts_match_the_filtered_lists(self, client):
        """A count that disagrees with its own list is the defect class this repo keeps hitting."""
        r = client.get("/api/clusters")
        card = next(c for c in r.json() if c["id"] == "c1")
        assert card["empty_groups"] == len(self._names(client, "empty"))
        assert card["unattributed_groups"] == len(self._names(client, "unattributed"))

    def test_an_unknown_state_is_rejected_rather_than_silently_ignored(self, client):
        """Ignoring it would return every group under a label the caller did not ask for."""
        assert client.get("/api/clusters/c1/groups", params={"state": "bogus"}).status_code == 422
