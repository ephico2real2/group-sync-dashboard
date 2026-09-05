"""First login from Identity objects, read behind rbac.identities (feature C2).

`ClusterClient.fetch_identities` returns the earliest Identity creationTimestamp per User, follows the
API server's continue tokens like every list, skips an Identity naming no User, and answers a 403
with None (reported, never fabricated over). `poll_once` reads them only when `identities_read` is
on, records the outcome in `ocp_identity_status`, and stamps each row's `first_login_source`.
"""

from __future__ import annotations

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.kube import GROUP_API, GROUPSYNC_API, IDENTITY_API, USER_API, ClusterClient, ClusterError
from gsd.poller import poll_once
from gsd.store import Store

GROUPS = {"kind": "GroupList", "items": []}
USERS = {"kind": "UserList", "items": [
    {"metadata": {"name": "alice", "creationTimestamp": "2026-08-05T16:14:16Z"},
     "fullName": "Alice Cooper", "identities": ["ldap-local:x"]},
    {"metadata": {"name": "kubeadmin", "creationTimestamp": "2025-04-19T02:02:33Z"},
     "identities": ["developer:kubeadmin"]},
]}
IDENTITIES_PAGE_1 = {"kind": "IdentityList", "metadata": {"continue": "tok"}, "items": [
    # Two Identities for alice: the later one first, so "keep the earlier" is exercised.
    {"metadata": {"name": "ldap-local:x2", "creationTimestamp": "2026-08-20T09:00:00Z"},
     "providerName": "ldap-local", "providerUserName": "x2", "user": {"name": "alice"}},
    {"metadata": {"name": "ldap-local:x", "creationTimestamp": "2026-08-10T08:00:00Z"},
     "providerName": "ldap-local", "providerUserName": "x", "user": {"name": "alice"}},
    # An Identity that names no User yet (provisioning in flight) is skipped.
    {"metadata": {"name": "ldap-local:orphan", "creationTimestamp": "2026-08-01T00:00:00Z"},
     "providerName": "ldap-local", "providerUserName": "orphan"},
]}
IDENTITIES_PAGE_2 = {"kind": "IdentityList", "items": [
    {"metadata": {"name": "developer:kubeadmin", "creationTimestamp": "2025-04-19T02:02:33Z"},
     "providerName": "developer", "providerUserName": "kubeadmin", "user": {"name": "kubeadmin"}},
]}


def _handler(identities_status: int, seen: list | None = None):
    def handle(request):
        path = request.url.path
        if seen is not None:
            seen.append((path, dict(request.url.params)))
        if path.startswith(GROUPSYNC_API):
            return httpx.Response(404, json={"kind": "Status", "code": 404, "message": "not found"})
        if path.startswith(GROUP_API):
            return httpx.Response(200, json=GROUPS)
        if path.startswith(USER_API):
            return httpx.Response(200, json=USERS)
        if path.startswith(IDENTITY_API):
            if identities_status != 200:
                return httpx.Response(identities_status, json={"kind": "Status", "code": identities_status, "message": "nope"})
            page = IDENTITIES_PAGE_2 if request.url.params.get("continue") == "tok" else IDENTITIES_PAGE_1
            return httpx.Response(200, json=page)
        return httpx.Response(404, json={"kind": "Status"})
    return handle


def _client(identities_status: int, seen: list | None = None) -> ClusterClient:
    cluster = ClusterConfig("c1", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(_handler(identities_status, seen))
    client._client = lambda: httpx.Client(transport=transport, base_url="https://x")
    return client


class TestFetchIdentities:
    def test_the_earliest_identity_per_user_across_pages_and_orphans_are_skipped(self):
        seen: list = []
        got = _client(200, seen).fetch_identities()
        assert got == {"alice": "2026-08-10T08:00:00Z", "kubeadmin": "2025-04-19T02:02:33Z"}
        identity_calls = [p for p in seen if p[0].startswith(IDENTITY_API)]
        assert len(identity_calls) == 2, "the continue token must be followed"
        assert identity_calls[1][1].get("continue") == "tok"

    def test_timestamps_are_compared_as_instants_not_strings(self):
        """Review of C2: Cursor proposed the instant comparison for a mixed-width reason Codex
        refuted (apimachinery's Time.MarshalJSON writes fixed-width RFC3339 seconds); the comparison
        stayed as the operation meant, and this holds it: a later instant at another width must not
        beat an earlier one, which a string minimum would let it do ('.' < 'Z'), and an unparsable
        stamp is skipped rather than compared."""
        def handle(request):
            if request.url.path.startswith(IDENTITY_API):
                return httpx.Response(200, json={"kind": "IdentityList", "items": [
                    {"metadata": {"name": "ldap-local:new", "creationTimestamp": "2026-08-10T08:00:00.100000Z"},
                     "user": {"name": "alice"}},
                    {"metadata": {"name": "ldap-local:old", "creationTimestamp": "2026-08-10T08:00:00Z"},
                     "user": {"name": "alice"}},
                    {"metadata": {"name": "ldap-local:junk", "creationTimestamp": "not a time"},
                     "user": {"name": "alice"}},
                ]})
            return httpx.Response(404, json={"kind": "Status"})
        cluster = ClusterConfig("c1", "https://x", token_env="T")
        client = ClusterClient(cluster, timeout=5)
        client._client = lambda: httpx.Client(transport=httpx.MockTransport(handle), base_url="https://x")
        assert client.fetch_identities() == {"alice": "2026-08-10T08:00:00Z"}

    def test_a_403_is_none_not_an_error(self):
        assert _client(403).fetch_identities() is None

    def test_any_other_failure_raises(self):
        with pytest.raises(ClusterError):
            _client(503).fetch_identities()


def _poll(store: Store, monkeypatch, identities_status: int, identities_read: bool, seen: list | None = None) -> str:
    cluster = ClusterConfig("c1", "https://x", token_env="T")
    client = _client(identities_status, seen)
    import gsd.poller as poller_mod
    monkeypatch.setattr(poller_mod, "ClusterClient", lambda *a, **kw: client)
    return poll_once(store, cluster, timeout=5, identities_read=identities_read)


class TestThePollerReadsIdentitiesOnlyWhenGranted:
    def test_off_never_requests_identities_and_says_so(self, tmp_path, monkeypatch):
        seen: list = []
        store = Store(str(tmp_path / "t.db"))
        try:
            _poll(store, monkeypatch, 200, identities_read=False, seen=seen)
            assert not [p for p in seen if p[0].startswith(IDENTITY_API)]
            assert store.identities_source("c1")["state"] == "off"
            rows = {r["user_name"]: r for r in store.users("c1")}
            assert rows["alice"]["first_login_source"] == "user"
            assert rows["alice"]["first_login_at"] == "2026-08-05T16:14:16Z"
        finally:
            store.close()

    def test_on_and_allowed_gives_the_identity_times(self, tmp_path, monkeypatch):
        store = Store(str(tmp_path / "t.db"))
        try:
            _poll(store, monkeypatch, 200, identities_read=True)
            assert store.identities_source("c1")["state"] == "ok"
            rows = {r["user_name"]: r for r in store.users("c1")}
            assert rows["alice"]["first_login_source"] == "identity"
            assert rows["alice"]["first_login_at"] == "2026-08-10T08:00:00Z"
            assert rows["kubeadmin"]["first_login_source"] == "identity"
        finally:
            store.close()

    def test_on_and_forbidden_keeps_the_rows_and_falls_back(self, tmp_path, monkeypatch):
        store = Store(str(tmp_path / "t.db"))
        try:
            _poll(store, monkeypatch, 403, identities_read=True)
            assert store.identities_source("c1")["state"] == "forbidden"
            rows = {r["user_name"]: r for r in store.users("c1")}
            assert set(rows) == {"alice", "kubeadmin"}
            assert rows["alice"]["first_login_source"] == "user"
        finally:
            store.close()

    def test_a_transient_failure_leaves_the_status_and_the_identity_times(self, tmp_path, monkeypatch):
        """Review (Cursor): a 503 is not a verdict — the status stays `ok` — and the rows must keep
        their last-known Identity times rather than all falling back to the User time."""
        store = Store(str(tmp_path / "t.db"))
        try:
            _poll(store, monkeypatch, 200, identities_read=True)
            assert store.identities_source("c1")["state"] == "ok"
            _poll(store, monkeypatch, 503, identities_read=True)
            assert store.identities_source("c1")["state"] == "ok", "a 503 is not a verdict"
            rows = {r["user_name"]: r for r in store.users("c1")}
            assert rows["alice"]["first_login_source"] == "identity"
            assert rows["alice"]["first_login_at"] == "2026-08-10T08:00:00Z"
        finally:
            store.close()

    def test_a_user_who_appears_during_a_transient_failure_carries_the_user_time(self, tmp_path, monkeypatch):
        """Review (Codex): a 503 while a new User appeared. Known rows keep their Identity times, the
        new row carries the User time with `first_login_source: user`, and the status stays `ok` with
        the OBSERVED_AT OF THE LAST SUCCESSFUL READ — the mixed page is honest because the note
        describes the source per row and the chips say which. Codex's alternative, an `error` state
        that downgrades every row on one 503, was rejected in docs/REVIEW_C2.md."""
        store = Store(str(tmp_path / "t.db"))
        try:
            _poll(store, monkeypatch, 200, identities_read=True)
            first = store.identities_source("c1")
            assert first["state"] == "ok"
            monkeypatch.setitem(USERS, "items", USERS["items"] + [
                {"metadata": {"name": "new-user", "creationTimestamp": "2026-08-30T00:00:00Z"},
                 "identities": ["ldap-local:new"]}])
            _poll(store, monkeypatch, 503, identities_read=True)
            assert store.identities_source("c1") == first, "the status row is the last successful read's"
            rows = {r["user_name"]: r for r in store.users("c1")}
            assert set(rows) == {"alice", "kubeadmin", "new-user"}
            assert rows["alice"]["first_login_source"] == "identity"
            assert rows["alice"]["first_login_at"] == "2026-08-10T08:00:00Z"
            assert rows["new-user"]["first_login_source"] == "user"
            assert rows["new-user"]["first_login_at"] == "2026-08-30T00:00:00Z"
        finally:
            store.close()
