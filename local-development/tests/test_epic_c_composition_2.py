"""OB2's second composition review of Epic C (1.1.0 -> 1.5.0): S4e (#438), D3 (#434) and D4 (#446) composed onto the
fleet-login machinery, measured on the hermetic harnesses. Every budget counts authorize requests on the wire
(`presented`), as SPEC_S4c, S4e and D4 state their units. No real account: USER is the fleet harness's own name,
ADMIN a made-up person, BOB a made-up person who later becomes a declared account."""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd import rejoin as rejoin_module
from gsd.clusterconfig.parser import Finding, parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION
from gsd.config import ClusterConfig
from gsd.fleetlookup import CredentialGate, LookupRefused, lookup
from gsd.fleetstate import PREFIX, lease_name
from test_cluster_rejoin import ADMIN, ADMIN_PASSWORD, RemoteTarget, _app, _rejoin, presented, review
from test_clusterconfig import _secret
from test_clusterconfig_tab import NS, _as_stored
from test_fleet_lifecycle import LeaseHost, process, retrieved, self_login, sessions, stanza
from test_fleet_login import API, PASSWORD, T0, TOKEN, USER, login_302, refused_401
from test_fleet_lookup import RND, SA_TOKEN, sa_secret, run
from test_ping_account_scope import directory

BOB, BOB_PASSWORD, WRONG = "bob.person", "B0b-pw-31c7", "wr0ng-pw-9a2f"
EAST_ACCOUNT = "svc-east-bind"          # an explicit ldapConnectionBootstrap on a DECLARING Secret (S4e keeps it)


def declaring_secret(bootstrap: str | None = EAST_ACCOUNT, name="gsd-cluster-east", cluster="east",
                     server="https://api.east.example:6443") -> dict:
    """A Secret that declares saTokenLookup, with (or without) its own ldapConnectionBootstrap."""
    config = {"saTokenLookup": True}
    if bootstrap:
        config["ldapConnectionBootstrap"] = bootstrap
    return _secret(name, cluster=cluster, server=server, config=config)


@pytest.fixture
def remote(monkeypatch):
    """Every httpx.Client — the login's, D8's review, the token read, the ping's — goes to one fake target that
    answers as a directory: an account's own password gets a session, any other a 401 (test_ping_account_scope)."""
    target = RemoteTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", API),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


def logged_out_lines(caplog) -> list[str]:
    return [m for m in caplog.messages if m.startswith("fleet-logout")]


# ── K8 / K11: a Rejoin over a DECLARING Secret that names its own account (S4e x D4) ────────────────────────────

def test_rejoin_over_a_declaring_secret_with_an_explicit_account_keeps_the_cluster_loadable(tmp_path, monkeypatch, remote):
    """S4e (#438) made the parser keep `ldapConnectionBootstrap` on a bearer Secret only when `token-source` is
    `remote-lookup`; D4 (#446) writes `token-source: rejoin` and leaves the explicit account in `config`. Composed: the
    Secret a person's Rejoin just wrote does not parse, the cluster is a finding and leaves the served set — the recovery
    action retires the cluster."""
    remote.answers = directory({ADMIN: ADMIN_PASSWORD})
    from test_clusterconfig_tab import _Host
    host = _Host({"gsd-cluster-east": declaring_secret()})
    east = parse_secret(declaring_secret(), host_name="c1")
    assert not isinstance(east, Finding) and east.credential_kind == "remote-lookup" and east.ldap_connection_bootstrap == EAST_ACCOUNT
    app, settings = _app(tmp_path, monkeypatch, host, east)
    with TestClient(app) as c:
        r = _rejoin(c)
    assert r.status_code == 200 and r.json()["outcome"] == "rejoined", r.text
    assert presented(remote) == [(ADMIN, ADMIN_PASSWORD)]
    stored = host.secrets["gsd-cluster-east"]
    assert stored["metadata"]["annotations"][TOKEN_SOURCE_ANNOTATION] == "rejoin"
    config = json.loads(base64.b64decode(stored["data"]["config"]))
    parsed = parse_secret(copy.deepcopy(stored), host_name="c1")
    assert not isinstance(parsed, Finding), f"the rejoined Secret does not load: {parsed!r}; config={config}"
    clusters, findings = discover(None, NS, host_name="c1", items=[copy.deepcopy(stored)])
    assert findings == [] and [c.name for c in clusters] == ["east"], findings
    assert clusters[0].credential_kind == "bearer" and clusters[0].token_source == "rejoin"


# ── K8: the four paths after a Rejoin present only the declared pair ─────────────────────────────────────────────

def _rejoin_direct(p, host, cluster_name, username, password, viewer="root"):
    cluster = p.settings.cluster(cluster_name)
    rejoin_module.check(cluster, p.settings, username, password)
    return rejoin_module.rejoin(cluster, p.settings, host, own_namespace="ns", gate=p._credential_gate,
                                username=username, password=password, viewer=viewer)


def test_the_four_paths_with_a_rejoin_composed_present_each_password_as_its_own_account_only(tmp_path, monkeypatch, remote):
    """The budget over the system with a Rejoin in the mix: the lookup, the ping and self-login present the fleet
    password as USER only; the Rejoin presents the person's password as the person only; a refusal of (USER, pw)
    stands every fleet path down and leaves the person's (ADMIN, pw) budget untouched, and vice versa."""
    verdicts: list[tuple[str, bool]] = []
    passwords = {USER: PASSWORD, ADMIN: ADMIN_PASSWORD}
    remote.answers = directory(passwords, verdicts)
    host = LeaseHost()
    east_path = "/api/v1/namespaces/ns/secrets/gsd-cluster-east"
    host.secrets[east_path] = _as_stored(_secret())            # a bearer Secret row: rejoinable
    east = parse_secret(_secret(), host_name="host")
    p = process(tmp_path, monkeypatch, host, stanza("l1"), self_login("s1"),
                discovered=[east, retrieved("r1")], fleet_ping_interval_seconds=60)
    p.store.upsert_cluster("s1", "https://api.s1.example.com:6443", True, source="values", credential="self-login")
    now = [T0]
    s = sessions(p, now)

    p._retrieve_pending()                                        # the lookup for l1, as USER
    assert presented(remote) == [(USER, PASSWORD)]
    answer = _rejoin_direct(p, host, "east", ADMIN, ADMIN_PASSWORD)
    assert answer["outcome"] == "rejoined", answer
    assert presented(remote)[1:] == [(ADMIN, ADMIN_PASSWORD)]
    # discovery after the Rejoin: the rejoined Secret is served (token-source rejoin, no lookup-account)
    rejoined = [w[2] for w in host.writes if w[0] == "PUT" and w[1] == east_path][-1]
    rejoined_cfg = parse_secret(_as_stored(rejoined), host_name="host")
    assert not isinstance(rejoined_cfg, Finding)
    rejoined_cfg = dataclasses.replace(rejoined_cfg, token_source="rejoin", lookup_account=None)
    p.settings.cluster_registry.replace([rejoined_cfg, retrieved("r1")], [], at="2026-09-27T15:00:00Z")
    p._ping_accounts()                                           # the ping: as USER, against r1
    assert presented(remote)[2:] == [(USER, PASSWORD)]
    assert s.credential_for(p.settings.cluster("s1")).token_value == TOKEN   # self-login: as USER
    assert presented(remote)[3:] == [(USER, PASSWORD)]

    # the person's refusal: one authorize, then nothing from this pod; the fleet paths are untouched by it
    answer = _rejoin_direct(p, host, "east", ADMIN, WRONG)
    assert answer["outcome"] == "login-refused" and presented(remote)[4:] == [(ADMIN, WRONG)]
    assert _rejoin_direct(p, host, "east", ADMIN, WRONG)["outcome"] == "login-refused"
    assert presented(remote)[5:] == []
    # the fleet password rotated TO the very string the person was refused with: the gate is per (account, password),
    # so the fleet paths present (USER, WRONG) exactly once between them, then stand down on the Lease's entry
    host.rotate(WRONG)
    p.settings.cluster_registry.replace([rejoined_cfg, retrieved("r1")], [], at="2026-09-27T15:01:00Z")
    from datetime import timedelta
    now[0] += timedelta(seconds=120)
    p._ping_accounts()
    p._retrieve_pending()
    s.credential_for(p.settings.cluster("s1"))
    for _ in range(2):
        now[0] += timedelta(seconds=120)
        p._ping_accounts(); p._retrieve_pending(); s.credential_for(p.settings.cluster("s1"))
    after = presented(remote)[5:]
    assert after == [(USER, WRONG)], after
    assert host.leases.annotations(USER).get(PREFIX + "refused"), "the fleet refusal is on the Lease"
    # and the person's account is never presented with the fleet password, nor USER with the person's
    assert (ADMIN, PASSWORD) not in presented(remote) and (USER, ADMIN_PASSWORD) not in presented(remote)
    assert [u for u, _ in verdicts] == [u for u, _ in presented(remote)]


# ── K8: a rejoined Secret is no declaration, whatever its annotations say ────────────────────────────────────────

@pytest.mark.parametrize("token_source", ["rejoin", "remote-lookup"])
def test_a_rejoined_secret_whose_annotation_names_the_person_never_authorizes_a_ping_as_them(tmp_path, monkeypatch, remote,
                                                                                            token_source):
    """`rejoin-account` is never read as an account; a hand-planted `lookup-account: <person>` on the rejoined Secret
    (or its token-source edited back to remote-lookup) makes the person a Lease row, never a login (S4e's rule)."""
    remote.answers = directory({USER: PASSWORD, ADMIN: ADMIN_PASSWORD})
    host = LeaseHost()
    rejoined = dataclasses.replace(retrieved("east"), token_source=token_source, lookup_account=ADMIN)
    p = process(tmp_path, monkeypatch, host, discovered=[rejoined, retrieved("r1")], fleet_ping_interval_seconds=60)
    p._ping_accounts()
    assert presented(remote) == [(USER, PASSWORD)], presented(remote)
    assert p._declared_accounts(p.settings.effective_clusters()) == {USER}
    # a `rejoin` Secret is not a member of any account's sweep; one edited back to `remote-lookup` is a Lease row only
    assert set(p.signals.fleet_accounts()) == ({USER} if token_source == "rejoin" else {USER, ADMIN})


# ── K10: #440 and its sibling — the lookup's revoke line and the token it read ──────────────────────────────────

@pytest.mark.parametrize("path", ["success", "refused-read", "ping"])
def test_the_lookups_revoke_line_never_quotes_the_token_it_read(monkeypatch, caplog, path):
    """#440: the token the lookup read is not handed to the login before the revoke runs, so a remote that echoes it
    in the DELETE's answer puts it on `fleet-logout-failed`. Its sibling: a read the lookup REFUSED after decoding
    the token (wrong owner) carries it on `exc.secrets`, and the revoke line quotes it too. Rejoin does both
    (`gsd/rejoin.py:258,261`); the lookup and the ping do neither."""
    from test_fleet_lookup import LookupTarget
    target = LookupTarget(login_302(), revoke=httpx.Response(500, text=f"echo {SA_TOKEN} back"))
    if path == "refused-read":
        target.secret = httpx.Response(200, json=sa_secret(sa="wrong-owner"))
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(target), base_url=API,
                                                          headers=kw.get("headers"), follow_redirects=False))
    with caplog.at_level(logging.INFO, logger="gsd"):
        if path == "refused-read":
            with pytest.raises(LookupRefused) as info:
                run(RND)
            assert info.value.code == "sa-token-unreadable" and SA_TOKEN not in str(info.value)
        else:
            run(RND, write=path != "ping")
    lines = logged_out_lines(caplog)
    assert lines and all("fleet-logout-failed" in m for m in lines), lines
    assert all(SA_TOKEN not in m for m in lines), f"{path}: the token read is on the revoke line"


# ── K9: the Rejoin's per-pod gate and the Lease's account refusal, composed ─────────────────────────────────────

def test_rejoin_gate_and_lease_gate_compose_to_one_more_per_pod_and_never_more(tmp_path, monkeypatch, remote):
    """A person Rejoins as BOB (not a fleet account) with a password the directory refuses, on two pods; then BOB
    becomes a DECLARED account (a Secret-declared stanza names it) and the fleet password Secret holds that same
    password. Measured: (BOB, pw) is sent once per pod that Rejoined (D4-7's scope), and once more by the fleet
    paths over both pods (B2, the Lease), never twice by the fleet paths, never twice by one pod."""
    verdicts: list[tuple[str, bool]] = []
    remote.answers = directory({}, verdicts)                     # a directory that refuses everything
    host = LeaseHost()
    east_path = "/api/v1/namespaces/ns/secrets/gsd-cluster-east"
    host.secrets[east_path] = _as_stored(_secret())
    east = parse_secret(_secret(), host_name="host")
    pods = {name: process(tmp_path, monkeypatch, host, discovered=[east], name=name) for name in ("a", "b")}
    for name, p in pods.items():
        assert _rejoin_direct(p, host, "east", BOB, BOB_PASSWORD)["outcome"] == "login-refused"
    assert presented(remote) == [(BOB, BOB_PASSWORD)] * 2, "D4-7: one per pod"
    # BOB is declared now, and the fleet password IS the refused string
    declared = dataclasses.replace(parse_secret(declaring_secret(BOB, name="gsd-cluster-north", cluster="north",
                                                                 server="https://api.north.example:6443"), host_name="host"))
    host.rotate(BOB_PASSWORD)
    for p in pods.values():
        p.settings.cluster_registry.replace([east, declared], [], at="2026-09-27T15:02:00Z")
    with pytest.raises(Exception, match="rejoin-fleet-account"):
        _rejoin_direct(pods["a"], host, "east", BOB, BOB_PASSWORD)   # D4-9: refused by name now
    for _ in range(3):
        for p in pods.values():
            p._retrieve_pending(); p._ping_accounts()
    assert presented(remote)[2:] == [], "a pod whose gate holds the Rejoin's refusal sends the fleet paths nothing"
    # the lookup claimed and released BOB's Lease (poller.py:1644 claims before `lookup` consults the gate), but no
    # refusal reached it: the Rejoin's refusal is per pod, and a stand-down on the process's own gate writes no entry
    assert PREFIX + "refused" not in host.leases.annotations(BOB)
    # a THIRD pod, which never Rejoined: B2's one authorize as the declared account, then the Lease holds it
    c = process(tmp_path, monkeypatch, host, discovered=[east, declared], name="c")
    for _ in range(3):
        c._retrieve_pending(); c._ping_accounts()
    assert presented(remote)[2:] == [(BOB, BOB_PASSWORD)]
    assert host.leases.annotations(BOB).get(PREFIX + "refused"), "the fleet path's refusal reached the Lease"
    d = process(tmp_path, monkeypatch, host, discovered=[east, declared], name="d")
    d._retrieve_pending(); d._ping_accounts()
    for p in pods.values():
        p._retrieve_pending(); p._ping_accounts()
    assert presented(remote)[3:] == [], "the Lease's entry gates every fleet path on every pod"
    # the declaration removed again: a fresh pod's Rejoin as BOB never reads the Lease — D4-7's one more, stated
    e = process(tmp_path, monkeypatch, host, discovered=[east], name="e")
    assert _rejoin_direct(e, host, "east", BOB, BOB_PASSWORD)["outcome"] == "login-refused"
    assert presented(remote)[3:] == [(BOB, BOB_PASSWORD)]
    assert [u for u, _ in verdicts] == [u for u, _ in presented(remote)]
    assert len(presented(remote)) == 4     # 2 (D4-7: one per pod that pressed) + 1 (B2: the fleet paths, once) + 1 (D4-7 again)


# ── K11: the Rejoin route's thread and the poll thread, on one gate, at once ───────────────────────────────────

def test_a_rejoin_in_flight_while_the_ping_binds_writes_no_lease_and_shares_no_entry(tmp_path, monkeypatch, remote):
    """The Rejoin (route thread) and the ping (discovery thread) hold their authorize open at the same instant on one
    process: two authorizes, each as its own account; the Lease is written by the ping alone; the gate ends empty."""
    inside = threading.Barrier(2, timeout=10)

    def slow_directory(request):
        user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
        inside.wait()                                            # both passwords are on the wire before either answers
        return login_302() if {USER: PASSWORD, ADMIN: ADMIN_PASSWORD}.get(user) == password else refused_401()
    remote.answers = [slow_directory] * 4
    host = LeaseHost()
    east_path = "/api/v1/namespaces/ns/secrets/gsd-cluster-east"
    host.secrets[east_path] = _as_stored(_secret())
    east = parse_secret(_secret(), host_name="host")
    p = process(tmp_path, monkeypatch, host, discovered=[east, retrieved("r1")], fleet_ping_interval_seconds=60)
    answers: dict = {}
    t = threading.Thread(target=lambda: answers.setdefault("rejoin", _rejoin_direct(p, host, "east", ADMIN, ADMIN_PASSWORD)))
    t.start()
    p._ping_accounts()
    t.join(10)
    assert answers["rejoin"]["outcome"] == "rejoined", answers
    assert sorted(presented(remote)) == sorted([(USER, PASSWORD), (ADMIN, ADMIN_PASSWORD)])
    assert host.leases.annotations(USER)[PREFIX + "ping-last-outcome"] == "ok"
    assert lease_name(ADMIN) not in host.leases.objects, "a Rejoin wrote a Lease"
    assert p._credential_gate._refused == {} and p._credential_gate._spent == set()
