"""poll_once and the User read: what each outcome of the list call does to the store.

The Users tab is sourced from this read (docs/DESIGN_users_tab_logins.md), so the poller's handling
of it is load-bearing in a way the display-name feature never was. Three outcomes, three different
truths the store must end up telling:

    200  -> rows replaced wholesale, ocp_user_status = ok
    403  -> rows LEFT AS THEY WERE, ocp_user_status = forbidden   (the grant is missing; say so)
    5xx  -> rows left, status left, poll still ok                  (a transient; nothing to assert yet)

None of the three fails the poll: groups, bindings and events do not depend on the User read. The
Cursor review of PR #47 asked for exactly this matrix at the poller level, because the store and kube
tests each pass while the wiring between them rots.
"""

from __future__ import annotations

import httpx

from gsd.config import ClusterConfig
from gsd.kube import GROUP_API, GROUPSYNC_API, USER_API, ClusterClient
from gsd.poller import poll_once
from gsd.store import Store

GROUPS = {"kind": "GroupList", "items": [
    {"metadata": {"name": "team"}, "users": ["alice", "dave"]},
]}
USERS = {"kind": "UserList", "items": [
    {"metadata": {"name": "alice", "creationTimestamp": "2026-08-05T16:14:16Z"},
     "fullName": "Alice Cooper", "identities": ["ldap-local:x"]},
    {"metadata": {"name": "kubeadmin", "creationTimestamp": "2025-04-19T02:02:33Z"},
     "identities": ["developer:kubeadmin"]},
]}


def _handler(users_status: int, users_body=None):
    def handle(request):
        path = request.url.path
        if path.startswith(GROUPSYNC_API):
            return httpx.Response(404, json={"kind": "Status", "code": 404,
                                             "message": "the server could not find the requested resource"})
        if path.startswith(GROUP_API):
            return httpx.Response(200, json=GROUPS)
        if path.startswith(USER_API):
            if users_status == 200:
                return httpx.Response(200, json=users_body or USERS)
            return httpx.Response(users_status, json={"kind": "Status", "code": users_status, "message": "nope"})
        return httpx.Response(404, json={"kind": "Status"})
    return handle


def _poll(store: Store, monkeypatch, users_status: int, users_body=None) -> str:
    cluster = ClusterConfig("c1", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(_handler(users_status, users_body))
    client._client = lambda: httpx.Client(transport=transport, base_url="https://x")
    import gsd.poller as poller_mod
    monkeypatch.setattr(poller_mod, "ClusterClient", lambda *a, **kw: client)
    return poll_once(store, cluster, timeout=5)


def _store(tmp_path) -> Store:
    store = Store(str(tmp_path / "t.db"))
    store.upsert_cluster("c1", "https://x", True)
    return store


def test_a_successful_read_replaces_the_rows_and_marks_the_source_ok(tmp_path, monkeypatch):
    store = _store(tmp_path)
    assert _poll(store, monkeypatch, 200) == "ok"
    rows = {u["user_name"]: u for u in store.users("c1")}
    assert set(rows) == {"alice", "kubeadmin"}
    assert rows["alice"]["group_count"] == 1 and rows["kubeadmin"]["group_count"] == 0
    assert rows["alice"]["full_name"] == "Alice Cooper" and rows["alice"]["providers"] == ["ldap-local"]
    assert store.users_source("c1")["state"] == "ok"
    assert store.synced_members_without_user("c1") == ["dave"]


def test_a_forbidden_read_keeps_last_cycles_rows_and_marks_the_source_forbidden(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _poll(store, monkeypatch, 200)
    assert _poll(store, monkeypatch, 403) == "ok", "the grant is optional; the poll must not fail on it"
    assert {u["user_name"] for u in store.users("c1")} == {"alice", "kubeadmin"}, "nothing erased"
    assert store.users_source("c1")["state"] == "forbidden"


def test_a_forbidden_read_on_a_fresh_store_marks_forbidden_with_no_rows(tmp_path, monkeypatch):
    """The install that upgraded the image without the chart's RBAC: never polled successfully."""
    store = _store(tmp_path)
    assert _poll(store, monkeypatch, 403) == "ok"
    assert store.users("c1") == [] and store.users_source("c1")["state"] == "forbidden"
    assert store.synced_members_without_user("c1") == ["alice", "dave"], (
        "with no User rows every member reads as never-logged-in — which is why the API sends the source alongside"
    )


def test_any_other_error_touches_neither_the_rows_nor_the_status(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _poll(store, monkeypatch, 200)
    before = store.users_source("c1")
    assert _poll(store, monkeypatch, 503) == "ok"
    assert {u["user_name"] for u in store.users("c1")} == {"alice", "kubeadmin"}
    assert store.users_source("c1") == before, "a transient is not a verdict; the last verdict stands"


def test_a_successful_read_after_a_refusal_clears_it(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _poll(store, monkeypatch, 403)
    _poll(store, monkeypatch, 200)
    assert store.users_source("c1")["state"] == "ok"
    assert {u["user_name"] for u in store.users("c1")} == {"alice", "kubeadmin"}


def test_a_poll_that_fails_before_the_user_read_leaves_the_status_and_its_timestamp_alone(tmp_path, monkeypatch):
    """ACCEPTED behaviour, pinned so it is a decision and not a surprise: client.fetch() fails (the
    Groups list is unreachable), poll_once records the poll outcome and returns before the User
    read. ocp_user_status keeps its last verdict and its timestamp — which is why the tab shows
    when its source was last read, and the Overview shows the poll failure."""
    store = _store(tmp_path)
    _poll(store, monkeypatch, 200)
    before = store.users_source("c1")

    def failing_groups(request):
        if request.url.path.startswith(GROUP_API):
            return httpx.Response(503, json={"kind": "Status", "code": 503, "message": "down"})
        return _handler(200)(request)
    cluster = ClusterConfig("c1", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(failing_groups)
    client._client = lambda: httpx.Client(transport=transport, base_url="https://x")
    import gsd.poller as poller_mod
    monkeypatch.setattr(poller_mod, "ClusterClient", lambda *a, **kw: client)
    outcome = poll_once(store, cluster, timeout=5)
    assert outcome != "ok", "the poll itself is degraded"
    assert store.users_source("c1") == before
    assert {u["user_name"] for u in store.users("c1")} == {"alice", "kubeadmin"}


def test_a_departed_user_disappears_on_the_next_successful_read(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _poll(store, monkeypatch, 200)
    only_alice = {"kind": "UserList", "items": USERS["items"][:1]}
    _poll(store, monkeypatch, 200, users_body=only_alice)
    assert [u["user_name"] for u in store.users("c1")] == ["alice"]
