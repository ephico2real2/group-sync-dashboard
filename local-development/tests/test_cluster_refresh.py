"""Refresh (#311, docs/specs/SPEC_D3_cluster_refresh.md): `POST /api/clusterconfigs/{name}/refresh` probes an
existing cluster with the credential it already holds and answers `{outcome, message, at}` in the poller's words.
It never logs in, never binds, stores nothing and forces no poll. The page's four states are in
tests/test_ui.py::TestClusterConfigPage.
"""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import re
import threading

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import parse_secret
from gsd.config import CREDENTIAL_PENDING_REASONS, ClusterConfig
from gsd.kube import AUTH_FAILED, FORBIDDEN, UNREACHABLE, ClusterClient, ClusterError
from test_clusterconfig import TOKEN, _secret
from test_clusterconfig_tab import NS, _Host
from test_visibility import H, _MapResolver, _seed, _settings

ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
VERSION = "/version"
WHOAMI = "/apis/user.openshift.io/v1/users/~"


class _Probe(ClusterClient):
    """The remote cluster: records which cluster was dialled, with which token, on which paths; answers from
    `answers` (a dict, or a ClusterError to raise) and 404s the rest."""

    seen: list[tuple[str, str, str]] = []
    answers: dict = {}

    def _client(self):
        self.token = self.cluster.resolve_token()     # what a real client would put in the Authorization header
        return contextlib.nullcontext(object())

    def _get(self, client, path, params):
        type(self).seen.append((self.cluster.name, self.token, path))
        answer = type(self).answers.get(path)
        if isinstance(answer, ClusterError):
            raise answer
        if answer is None:
            raise ClusterError(UNREACHABLE, f"HTTP 404 on {path}: not found")
        return answer


def _never(what):
    def boom(*a, **kw):
        raise AssertionError(f"Refresh called {what}")
    return boom


@pytest.fixture
def rig(tmp_path, monkeypatch):
    db = str(tmp_path / "gsd.db"); _seed(db)
    settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True)
    settings.cluster_registry.namespace = NS
    settings.cluster_registry.replace([parse_secret(_secret(), host_name="c1")], [], at="2026-09-27T14:00:00Z")
    host = _Host({"gsd-cluster-east": _secret()})
    monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
    monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
    _Probe.seen = []
    _Probe.answers = {VERSION: {"gitVersion": "v1.31.6"}, WHOAMI: {"metadata": {"name": "system:serviceaccount:gso:poller"}}}
    monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Probe)
    # Every path that can send a password to a directory, or wake a poll, fails the test if reached.
    monkeypatch.setattr("gsd.fleetlogin.FleetLogin.__init__", _never("FleetLogin"))
    monkeypatch.setattr("gsd.fleetlookup.lookup", _never("the lookup"))
    monkeypatch.setattr("gsd.fleetlookup.read_sa_token", _never("the token read"))
    monkeypatch.setattr("gsd.selflogin.SelfLoginSessions.credential_for", _never("a self-login session"))
    app = build_app(settings, run_poller=False)
    for method in ("account_refusal", "answered", "refused", "refuse", "spend"):   # the app builds a gate; Refresh never asks it
        monkeypatch.setattr(f"gsd.fleetlookup.CredentialGate.{method}", _never(f"CredentialGate.{method}"))
    app.state.tier_resolver = _MapResolver({"root": "all", "alice": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})

    class _Poller:
        def request_discovery(self):
            raise AssertionError("Refresh requested a discovery")
    app.state.poller = _Poller()
    with TestClient(app) as c:
        yield c, app, settings


def _refresh(c, name="east", who="root"):
    return c.post(f"/api/clusterconfigs/{name}/refresh", headers=H(who))


def test_the_stored_credential_is_probed_and_the_answer_is_three_fields(rig, caplog):
    c, app, _ = rig
    with caplog.at_level(logging.DEBUG):
        r = _refresh(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"outcome", "message", "at"}
    assert body["outcome"] == "ok" and ISO.match(body["at"]), body
    assert "system:serviceaccount:gso:poller" in body["message"] and "v1.31.6" in body["message"]
    assert _Probe.seen == [("east", TOKEN, VERSION), ("east", TOKEN, WHOAMI)], "the Secret's own token, both paths"
    assert TOKEN not in r.text and TOKEN not in caplog.text
    assert "cluster-refreshed cluster=east credential=bearer by=root outcome=ok" in caplog.text


def test_the_host_row_is_probed_too(rig, monkeypatch):
    c, *_ = rig
    monkeypatch.setenv("X", "host-token-12345678")
    r = _refresh(c, "c1")
    assert r.status_code == 200 and r.json()["outcome"] == "ok", r.text
    assert {(name, token) for name, token, _ in _Probe.seen} == {("c1", "host-token-12345678")}


@pytest.mark.parametrize("answers,word", [
    ({VERSION: ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")}, "auth_failed"),
    # `/version` is anonymous-readable: a refused identity is still a refused credential (reachable is set last)
    ({VERSION: {"gitVersion": "v1.31.6"}, WHOAMI: ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")}, "auth_failed"),
    ({VERSION: ClusterError(FORBIDDEN, "403 Forbidden on /version — the ServiceAccount lacks list permission here")}, "forbidden"),
    ({VERSION: ClusterError(UNREACHABLE, "ConnectError: [Errno 61] Connection refused")}, "unreachable"),
    ({VERSION: ClusterError(UNREACHABLE, "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                         "unable to get local issuer certificate (_ssl.c:1000)")}, "cert-verify-failed"),
    # a remote's body naming certificates is not a TLS failure here: the poller's provenance rule
    ({VERSION: ClusterError(UNREACHABLE, "HTTP 502 on /version: certificate verify failed upstream")}, "unreachable"),
])
def test_each_failure_is_answered_in_the_pollers_word(rig, answers, word):
    c, *_ = rig
    _Probe.answers = answers
    r = _refresh(c)
    assert r.status_code == 200 and r.json()["outcome"] == word, r.text
    assert r.json()["message"], "the refusal says what was met"


def test_a_404_on_the_user_api_is_an_ordinary_kubernetes_and_still_ok(rig):
    c, *_ = rig
    del _Probe.answers[WHOAMI]
    r = _refresh(c)
    assert r.json()["outcome"] == "ok", r.text


@pytest.mark.parametrize("cluster,word,message", [
    (ClusterConfig("pending", "https://api.pending:6443", sa_token_lookup=True, source="configmap:fleet:1"),
     "pending", CREDENTIAL_PENDING_REASONS["remote-lookup"]),
    (ClusterConfig("pw", "https://api.pw:6443", oauth_username="u", oauth_password="p4ssword-1234", source="secret:gsd-cluster-pw"),
     "pending", CREDENTIAL_PENDING_REASONS["oauth"]),
    (ClusterConfig("sl", "https://api.sl:6443", user_self_login=True, ldap_connection_bootstrap="svc-gsd", source="secret:gsd-cluster-sl"),
     "not-probed", None),
])
def test_a_row_with_no_stored_credential_is_answered_with_no_network_call(rig, monkeypatch, cluster, word, message):
    c, app, settings = rig
    east, = settings.cluster_registry.discovered()
    settings.cluster_registry.replace([east, cluster], [], at="2026-09-27T14:01:00Z")
    monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _never("a client"))
    r = _refresh(c, cluster.name)
    assert r.status_code == 200 and r.json()["outcome"] == word, r.text
    if message is not None:
        assert r.json()["message"] == message
    assert "p4ssword-1234" not in r.text


def test_nothing_is_stored_and_no_poll_or_discovery_is_forced(rig):
    c, app, _ = rig
    store = app.state.store
    before = {row["id"]: (row.get("status"), row.get("last_poll"), row.get("message")) for row in store.clusters()}
    _Probe.answers = {VERSION: ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")}
    assert _refresh(c).json()["outcome"] == "auth_failed"
    assert {row["id"]: (row.get("status"), row.get("last_poll"), row.get("message")) for row in store.clusters()} == before


def test_an_unknown_or_retired_name_is_404_and_nothing_is_dialled(rig):
    c, app, _ = rig
    app.state.store.upsert_cluster("gone", "https://api.gone:6443", False)     # the store keeps it; no source names it
    for name in ("nope", "gone"):
        r = _refresh(c, name)
        assert r.status_code == 404 and name in r.json()["detail"], r.text
    assert _Probe.seen == []


def test_below_the_cluster_admin_tier_is_403_and_nothing_is_dialled(rig):
    c, *_ = rig
    assert _refresh(c, who="alice").status_code == 403       # alice holds the wide tier, not this one
    assert c.post("/api/clusterconfigs/east/refresh").status_code == 403    # no identity at all
    assert _Probe.seen == []


def test_one_probe_per_cluster_is_in_flight(rig, monkeypatch):
    """A second press while the first probe runs is refused, not queued: the route answers 409 and dials nothing."""
    c, *_ = rig
    inside, release, second = threading.Event(), threading.Event(), {}

    def slow(self, client, path, params):
        type(self).seen.append((self.cluster.name, self.token, path))
        if path == VERSION and not inside.is_set():
            inside.set()
            release.wait(10)
        return {"gitVersion": "v1.31.6"} if path == VERSION else {"metadata": {"name": "sa"}}

    monkeypatch.setattr(_Probe, "_get", slow)
    first = threading.Thread(target=lambda: second.setdefault("first", _refresh(c)))
    first.start()
    try:
        assert inside.wait(10), "the first probe started"
        second["second"] = _refresh(c)
    finally:
        release.set()
        first.join(10)
    assert second["second"].status_code == 409 and "in flight" in second["second"].json()["detail"]
    assert second["first"].json()["outcome"] == "ok"
    assert [p for _, _, p in _Probe.seen] == [VERSION, WHOAMI], "the refused press dialled nothing"
    assert _refresh(c).status_code == 200, "the slot is released when the probe ends"


def test_a_remote_that_echoes_the_bearer_never_puts_it_in_the_answer_or_the_log(rig, caplog):
    c, *_ = rig
    _Probe.answers = {VERSION: ClusterError(UNREACHABLE, f"HTTP 500 on /version: upstream saw Bearer {TOKEN}")}
    with caplog.at_level(logging.DEBUG):
        r = _refresh(c)
    assert r.json()["outcome"] == "unreachable" and "<redacted>" in r.json()["message"], r.text
    assert TOKEN not in r.text and TOKEN not in caplog.text


def test_a_200_that_echoes_the_bearer_in_version_or_identity_never_puts_it_in_the_answer_or_the_log(rig, caplog):
    """SPEC_D3 §2/§3: the remote owns gitVersion and the users/~ name, so `ok` is scrubbed too (review of #434)."""
    c, *_ = rig
    _Probe.answers = {VERSION: {"gitVersion": TOKEN}, WHOAMI: {"metadata": {"name": TOKEN}}}
    with caplog.at_level(logging.DEBUG):
        r = _refresh(c)
    assert r.status_code == 200 and r.json()["outcome"] == "ok", r.text
    assert TOKEN not in r.text and TOKEN not in caplog.text
    assert "<redacted>" in r.json()["message"]


def test_with_the_writes_switch_off_the_route_does_not_exist(tmp_path):
    db = str(tmp_path / "off.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        assert _refresh(c, "c1").status_code == 404
    assert "/api/clusterconfigs/{name}/refresh" not in app.openapi()["paths"]


def test_the_runbook_says_the_card_rows_are_the_last_polls_not_refreshs():
    """Epic D composition review (OB2, K5): Refresh stores nothing (SPEC_D3 §3), and #492's chip names the last
    poll's outcome, so `verify failed` can sit above `Refresh: connected` (and `verified` above
    `Refresh: cert-verify-failed`) until the next poll. The runbook's section 1 says which rows are the poll's."""
    import pathlib
    runbook = (pathlib.Path(__file__).resolve().parents[2] / "charts/group-sync-dashboard/docs/RUNBOOK.md").read_text()
    section = runbook.split("## 1. ", 1)[1].split("## 2. ", 1)[0]
    assert ("The `connection` row and the `tls` row's chip (`verified` / `verify failed`) are the last poll's, not "
            "Refresh's: the `Refresh:` line carries its own instant, and the two rows follow at the next poll.") in section
