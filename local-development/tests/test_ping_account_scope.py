"""#432: the fleet password is presented only as an account the configuration names now."""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from gsd.clusterconfig.parser import Finding, parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import LOOKUP_ACCOUNT_ANNOTATION, store_lookup
from gsd.config import ClusterConfig, valid_bootstrap_username
from gsd.fleetstate import FleetLease, lease_digest, lease_name
from gsd.kube import OK
from test_configmap_onboarding import Host, cycle, generated
from test_fleet_lifecycle import LeaseHost, process, retrieved, sessions
from test_fleet_login import T0, login_302, refused_401
from test_fleet_lookup import API, PASSWORD, SA_TOKEN, UID, USER, wire  # noqa: F401  (the fixture)

FLEET, WALK, OTHER, STANZA = "fleet-bind-account", "walk-developer", "other-account", "stanza-account"
FLEET_PASSWORD, WALK_PASSWORD, OTHER_PASSWORD, WRONG = "fleet-pw-1", "walk-pw-2", "other-pw-3", "wrong-pw-4"
TOKENS = [f"sha256~V2Fsa1Nlc3Npb25Ub2tlbk51bWJlcj{n:02d}" for n in range(8)]
SPEC = Path(__file__).parents[2] / "docs/specs/SPEC_S4e_ping_account_scope.md"


def credentials(request: httpx.Request) -> tuple[str, str]:
    user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
    return user, password


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize, in the order it reached the target."""
    return [credentials(request) for request in target.authorize]


def directory(passwords: dict[str, str], verdicts: list | None = None) -> list:
    """A directory: an account's own password gets a session, any other a 401, judged when it arrives."""
    def answer(request):
        user, password = credentials(request)
        accepted = passwords.get(user) == password
        if verdicts is not None:
            verdicts.append((user, accepted))
        return login_302() if accepted else refused_401()
    return [answer] * 64


def at(name: str, account: str, **kw) -> ClusterConfig:
    """A cluster the lookup retrieved as `account`, recorded in its Secret's `lookup-account`."""
    return dataclasses.replace(retrieved(name), lookup_account=account, **kw)


def lab_as_found(tmp_path, monkeypatch, host: LeaseHost) -> None:
    """The lab on 2026-09-27: the chart names FLEET, shared-rnd was retrieved as FLEET and pinged once."""
    host.rotate(FLEET_PASSWORD)
    lab = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET)], name="lab", fleet_account_username=FLEET)
    lab._ping_accounts()
    lab._ping_accounts()                                # inside the interval: not due


def spec_prose() -> str:
    """The spec before its blocks: the blocks quote this file, so its own assertions would always match."""
    prose, found, _ = SPEC.read_text().partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_S4e has no implementation-blocks heading to stop at"
    return prose


def declared_secret(explicit: bool) -> dict:
    """A Secret that declares saTokenLookup, with or without its own ldapConnectionBootstrap."""
    config = {"saTokenLookup": True}
    if explicit:
        config["ldapConnectionBootstrap"] = OTHER
    return {"metadata": {"name": "gsd-cluster-east", "resourceVersion": "1",
                         "labels": {"groupsync-dashboard.io/secret-type": "cluster"}},
            "data": {k: base64.b64encode(v.encode()).decode() for k, v in
                     {"name": "east", "server": API, "config": json.dumps(config)}.items()}}


# ── the Definition of Done: the corrected §3.12 walk ────────────────────────────────────────────────

@pytest.mark.parametrize("rotation_back", ["same-process", "after-a-restart"])
def test_the_walk_presents_nothing_as_the_fleet_account(tmp_path, monkeypatch, wire, rotation_back):
    """Two accounts, one password Secret: the walk's steps 2-3 send FLEET nothing and WALK exactly its budget."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, WALK: WALK_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    assert presented(wire) == [(FLEET, FLEET_PASSWORD)], "the product's own daily ping, as at 10:27:05Z"
    fleet_lease = copy.deepcopy(host.leases.objects[lease_name(FLEET)])

    def walk(name: str):
        return process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("walk-lookup", WALK)],
                       name=name, fleet_account_username=WALK, fleet_ping_interval_seconds=60)
    host.rotate(WALK_PASSWORD)
    p = walk("walk")
    p._ping_accounts()                                  # step 2: the ping, as WALK
    host.rotate(WRONG)
    for _ in range(3):
        p._ping_accounts()                              # step 3: refused once, then three cadences of nothing
    host.rotate(WALK_PASSWORD)
    if rotation_back == "after-a-restart":
        p = walk("restarted")
    p._ping_accounts()                                  # rotated back: one confirming ping
    after = presented(wire)[1:]
    assert [password for user, password in after if user == FLEET] == [], "a walk password was presented as FLEET"
    assert after == [(WALK, WALK_PASSWORD), (WALK, WRONG), (WALK, WALK_PASSWORD)], after
    assert host.leases.objects[lease_name(FLEET)] == fleet_lease, "the fleet account's Lease was written"


@pytest.mark.parametrize("fleet_lease", ["as-found", "carrying-a-refusal"])
def test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account(
        tmp_path, monkeypatch, wire, fleet_lease):
    """Grok's note on PR #433: the walk's self-login arrangement with the ping on never presents as FLEET."""
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)
    if fleet_lease == "carrying-a-refusal":            # the branch that reads the password Secret for the account
        holder = FleetLease(host, "ns", FLEET, claim_seconds=195, identity="elsewhere")
        holder.claim()
        holder.refuse("https://api.crc.testing:6443", lease_digest(FLEET, "another-password", UID), "login-refused")
        holder.release()
    fleet_writes = len([w for w in host.leases.writes if w[1] == lease_name(FLEET)])
    authorizes = len(wire.authorize)

    host.rotate(WALK_PASSWORD)
    stanza = ClusterConfig("walk-self", "https://api.crc.testing:6443", user_self_login=True, ldap_connection_bootstrap=WALK)
    p = process(tmp_path, monkeypatch, host, stanza, discovered=[at("shared-rnd", FLEET)], name="walk",
                fleet_account_username=WALK, fleet_ping_enabled=True)
    p.store.upsert_cluster("walk-self", stanza.api_url, True, source="values", credential="self-login")
    now = [T0]
    s = sessions(p, now)
    cluster = p.settings.cluster("walk-self")
    wire.answers = [login_302(token=TOKENS[0]), login_302(token=TOKENS[1]), refused_401(),
                    login_302(expires_in="600", token=TOKENS[2]), login_302(expires_in="600", token=TOKENS[3])]
    p._ping_accounts(); p._retrieve_pending()
    assert [user for user, _ in presented(wire)[authorizes:]] == [], "the first cadence presented a password"
    assert s.credential_for(cluster).token_value == TOKENS[0]            # step 4: acquisition
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")                             # step 5: the session deleted from outside
    assert s.credential_for(cluster).token_value == TOKENS[1]            # one re-authentication
    s.poll_answered(cluster, OK)                                        # the poll green again: the episode ends
    host.rotate(WRONG)                                                  # step 5b: a wrong password + the deletion
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")
    assert s.credential_for(cluster) is None                            # refused once: suspended
    for _ in range(3):
        now[0] += timedelta(seconds=60)
        p._ping_accounts(); p._retrieve_pending()
        assert s.credential_for(cluster) is None                        # parked: no second authorize
    host.rotate(WALK_PASSWORD)                                          # the rotation back re-arms it
    now[0] += timedelta(seconds=60)
    assert s.credential_for(cluster).token_value == TOKENS[2]            # #310 Part A: a 600 s session
    now[0] += timedelta(seconds=450)                                    # renew_at = expires_at - 150 s
    assert s.credential_for(cluster).token_value == TOKENS[3]            # renewed
    p._ping_accounts()

    walk_presented = presented(wire)[authorizes:]
    assert [user for user, _ in walk_presented] == [WALK] * 5, walk_presented
    assert [password for _, password in walk_presented] == [WALK_PASSWORD, WALK_PASSWORD, WRONG, WALK_PASSWORD,
                                                            WALK_PASSWORD]
    assert len([w for w in host.leases.writes if w[1] == lease_name(FLEET)]) == fleet_writes, "the fleet Lease written"


# ── the budget over the system: every event in scope ────────────────────────────────────────────────
# Each scenario starts from the lab as found, sets up what it needs, and returns where its EVENT begins on the wire.

def _username_change(tmp_path, monkeypatch, host, passwords, wire, *, then=()):
    """The chart moves from FLEET to OTHER and the Secret to OTHER's password; then a restart, a process, a rotation."""
    start = len(wire.authorize)
    host.rotate(OTHER_PASSWORD)
    config = dict(discovered=[at("shared-rnd", FLEET), at("north", OTHER)], fleet_account_username=OTHER)
    process(tmp_path, monkeypatch, host, name="moved", **config)._ping_accounts()
    for step in then:
        if step == "rotation":
            passwords[OTHER] = "other-pw-rotated"
            host.rotate("other-pw-rotated")
        process(tmp_path, monkeypatch, host, name=step, **config)._ping_accounts()
    return start


def _stanza_moved(tmp_path, monkeypatch, host, passwords, wire, *, change):
    """A values stanza names STANZA, then is removed, renamed or disabled, and the fleet password rotates."""
    east = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=STANZA)
    found = [at("shared-rnd", FLEET), at("east", STANZA), at("west", STANZA)]
    process(tmp_path, monkeypatch, host, east, discovered=found, name="declared", fleet_account_username=FLEET)._ping_accounts()
    start = len(wire.authorize)
    passwords[FLEET] = "fleet-pw-rotated"
    host.rotate("fleet-pw-rotated")
    moved = {"removed": (), "renamed": (dataclasses.replace(east, ldap_connection_bootstrap="renamed-account"),),
             "disabled": (dataclasses.replace(east, enabled=False),)}[change]
    process(tmp_path, monkeypatch, host, *moved, discovered=found, name="moved", fleet_account_username=FLEET)._ping_accounts()
    return start


def _stanza_added(tmp_path, monkeypatch, host, passwords, wire):
    """A stanza naming OTHER while the Secret holds FLEET's password: refused once, then gated (B2)."""
    start = len(wire.authorize)
    north = ClusterConfig("north", "https://api.north.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=OTHER)
    for name in ("added", "restarted"):
        p = process(tmp_path, monkeypatch, host, north, discovered=[at("shared-rnd", FLEET)], name=name,
                    fleet_account_username=FLEET)
        p._retrieve_pending(); p._ping_accounts()
    return start


def _rotation(tmp_path, monkeypatch, host, passwords, wire):
    """The named account's own password rotates: one confirming ping (B3), a restart included."""
    start = len(wire.authorize)
    passwords[FLEET] = "fleet-pw-rotated"
    host.rotate("fleet-pw-rotated")
    for name in ("rotated", "restarted"):
        process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET)], name=name,
                fleet_account_username=FLEET)._ping_accounts()
    return start


#: event -> (the scenario, the accounts the configuration names once the event has happened)
EVENTS = {
    "a username change": (_username_change, {OTHER}),
    "+ a restart": (lambda *a: _username_change(*a, then=("restart",)), {OTHER}),
    "+ a second process": (lambda *a: _username_change(*a, then=("replica",)), {OTHER}),
    "+ a rotation of the new account's password": (lambda *a: _username_change(*a, then=("rotation",)), {OTHER}),
    "a stanza removed, then a rotation": (lambda *a: _stanza_moved(*a, change="removed"), {FLEET}),
    "a stanza's account changed, then a rotation": (lambda *a: _stanza_moved(*a, change="renamed"),
                                                    {FLEET, "renamed-account"}),
    "a stanza disabled, then a rotation": (lambda *a: _stanza_moved(*a, change="disabled"), {FLEET}),
    "a stanza added (a false declaration)": (_stanza_added, {FLEET, OTHER}),
    "the named account's own rotation": (_rotation, {FLEET}),
}


def test_the_pairing_budget_over_the_system(tmp_path, monkeypatch, wire):
    """SPEC_S4e §3.2: per event, (sent to an account no longer named, sent to a named account wrongly)."""
    measured = {}
    for n, (event, (scenario, named)) in enumerate(EVENTS.items()):
        run = tmp_path / f"event-{n}"
        run.mkdir()
        host = LeaseHost()
        passwords = {FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD, STANZA: FLEET_PASSWORD}
        verdicts: list[tuple[str, bool]] = []
        wire.requests.clear()
        wire.answers = directory(passwords, verdicts)
        lab_as_found(run, monkeypatch, host)
        start = scenario(run, monkeypatch, host, passwords, wire)
        assert [u for u, _ in verdicts] == [u for u, _ in presented(wire)], "one verdict per authorize"
        measured[event] = (len([u for u, _ in verdicts[start:] if u not in named]),
                           len([u for u, accepted in verdicts[start:] if u in named and not accepted]))
    assert measured == {
        "a username change": (0, 0),
        "+ a restart": (0, 0),
        "+ a second process": (0, 0),
        "+ a rotation of the new account's password": (0, 0),
        "a stanza removed, then a rotation": (0, 0),
        "a stanza's account changed, then a rotation": (0, 0),
        "a stanza disabled, then a rotation": (0, 0),
        "a stanza added (a false declaration)": (0, 1),
        "the named account's own rotation": (0, 0),
    }, measured


def test_leadership_changes_between_read_and_claim(tmp_path, monkeypatch, wire):
    """A leader change between the Lease read and the claim sends only the declared account (Codex)."""
    host = LeaseHost()
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    args = dict(discovered=[at("old", FLEET), at("current", OTHER)], fleet_account_username=OTHER)
    first = process(tmp_path, monkeypatch, host, name="first", **args)
    second = process(tmp_path, monkeypatch, host, name="second", **args)
    first.elector = SimpleNamespace(is_leader=True)
    second.elector = SimpleNamespace(is_leader=False)
    original = first._fleet_lease
    switched = False

    def lease_for(*args):
        lease = original(*args)
        claim = lease.claim

        def switch(*a, **kw):
            nonlocal switched
            if not switched:
                switched = True
                first.elector.is_leader = False
                second.elector.is_leader = True
                second._ping_accounts()
            return claim(*a, **kw)
        lease.claim = switch
        return lease
    monkeypatch.setattr(first, "_fleet_lease", lease_for)
    first._ping_accounts()
    assert switched and presented(wire) == [(OTHER, OTHER_PASSWORD)]


def test_lease_already_records_ping_digest_for_undeclared_account(tmp_path, monkeypatch, wire):
    """A digest the old account's Lease already holds does not license a ping as it (Grok)."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    assert host.leases.objects[lease_name(FLEET)]["metadata"]["annotations"]["groupsync-dashboard.io/ping-digest"]
    host.leases.backdate(FLEET, "groupsync-dashboard.io/ping-last-attempt", 86400)
    start = len(wire.authorize)
    process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("north", OTHER)],
            name="stale-digest", fleet_account_username=OTHER)._ping_accounts()
    after = presented(wire)[start:]
    assert [user for user, _ in after if user == FLEET] == [], after


@pytest.mark.parametrize("spelling", ["User", " user", "user ", "user\t", "user\n"])
def test_account_spelling_contract(tmp_path, monkeypatch, wire, spelling):
    """Usernames are exact strings: whitespace and a trailing newline are refused, case variants are two accounts."""
    if any(c.isspace() for c in spelling):
        assert not valid_bootstrap_username(spelling)
        obj = declared_secret(True)
        obj["data"]["config"] = base64.b64encode(json.dumps(
            {"saTokenLookup": True, "ldapConnectionBootstrap": spelling}).encode()).decode()
        assert isinstance(parse_secret(obj, host_name="host"), Finding)
        return
    host = LeaseHost()
    host.rotate("wrong")
    wire.answers = directory({})
    declarations = [ClusterConfig(n, API, sa_token_lookup=True, ldap_connection_bootstrap=u)
                    for n, u in [("lower", "user"), ("upper", spelling)]]
    p = process(tmp_path, monkeypatch, host, *declarations,
                discovered=[at("lower", "user"), at("upper", spelling)], fleet_account_username="")
    p._ping_accounts()
    assert sorted(presented(wire)) == sorted([("user", "wrong"), (spelling, "wrong")])
    assert lease_name("user") != lease_name(spelling)


def test_old_replica_still_uses_its_loaded_declaration(tmp_path, monkeypatch, wire):
    """A process that still names FLEET presents a repurposed Secret as FLEET: drain it first (the stated boundary)."""
    host = LeaseHost()
    old = process(tmp_path, monkeypatch, host, name="old-values",
                  discovered=[at("old", FLEET)], fleet_account_username=FLEET)
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    old._ping_accounts()
    assert presented(wire) == [(FLEET, OTHER_PASSWORD)]
    assert "Drain old processes" in spec_prose()


# ── where the account comes from: declarations, never the annotation ────────────────────────────────

def test_configmap_digest_does_not_authorize_a_changed_lookup_annotation(tmp_path, monkeypatch, wire):
    """An owned output whose lookup-account alone was edited does not authorize that account (Codex C2)."""
    host = Host()
    wire.answers = directory({USER: PASSWORD})
    settings = generated(host)
    host.secrets["gsd-cluster-rnd"]["metadata"]["annotations"][LOOKUP_ACCOUNT_ANNOTATION] = FLEET
    _, clusters, findings, _ = cycle(host, settings)
    assert not findings and len(clusters) == 1
    lease_host = LeaseHost()
    lease_host.rotate(PASSWORD)
    p = process(tmp_path, monkeypatch, lease_host, discovered=clusters, fleet_account_username=USER)
    wire.requests.clear()
    p._ping_accounts()
    assert presented(wire) == [], "owner digest must not make an edited annotation a declaration"
    assert clusters[0].ldap_connection_bootstrap == USER


@pytest.mark.parametrize("explicit", [True, False])
def test_secret_retrieval_preserves_only_explicit_intent(tmp_path, monkeypatch, wire, explicit):
    """Retrieval keeps a Secret's own ldapConnectionBootstrap, and never makes a chart default one (C4 i)."""
    path = "/api/v1/namespaces/ns/secrets/gsd-cluster-east"
    host = LeaseHost(secrets={path: declared_secret(explicit)})
    store_lookup(host, "ns", "gsd-cluster-east", token=SA_TOKEN, cluster="east",
                 source_namespace="group-sync-operator", source_service_account="reader", lookup_account=OTHER)
    stored = host.writes[-1][2]
    parsed = parse_secret(stored, host_name="host")
    assert not isinstance(parsed, Finding)
    assert parsed.ldap_connection_bootstrap == (OTHER if explicit else None)
    found, findings = discover(host, "ns", host_name="host", values_names=("host",), items=[stored])
    assert not findings
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    p = process(tmp_path, monkeypatch, host, discovered=found, fleet_account_username=FLEET)
    p._ping_accounts()
    assert presented(wire) == ([(OTHER, OTHER_PASSWORD)] if explicit else [])


# ── what #432 keeps ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", ["chart-username", "values-stanza", "configmap-onboarded"])
def test_every_account_the_configuration_names_keeps_its_ping(tmp_path, monkeypatch, wire, shape):
    """No narrowing: the chart's account, a values stanza's and a ConfigMap onboarding's are still pinged."""
    host = LeaseHost()
    host.rotate(FLEET_PASSWORD)
    wire.answers = directory({FLEET: FLEET_PASSWORD, STANZA: FLEET_PASSWORD})
    stanzas, found = (), [at("east", FLEET if shape == "chart-username" else STANZA)]
    if shape == "values-stanza":
        stanzas = (ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True,
                                 ldap_connection_bootstrap=STANZA),)
    if shape == "configmap-onboarded":
        found = [at("east", STANZA, onboarding=("fleet", "cm-uid-1", "east"), ldap_connection_bootstrap=STANZA)]
    process(tmp_path, monkeypatch, host, *stanzas, discovered=found, fleet_account_username=FLEET)._ping_accounts()
    assert presented(wire) == [(FLEET if shape == "chart-username" else STANZA, FLEET_PASSWORD)]


def test_an_account_no_longer_named_remains_visible_without_a_login(tmp_path, monkeypatch, wire):
    """After a username change the old account keeps its row, is not pinged, and its Lease is untouched."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    original = copy.deepcopy(host.leases.objects[lease_name(FLEET)])
    host.rotate(OTHER_PASSWORD)
    p = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("north", OTHER)],
                name="moved", fleet_account_username=OTHER)
    p._ping_accounts()
    assert set(p.signals.fleet_accounts()) == {FLEET, OTHER}
    assert presented(wire)[1:] == [(OTHER, OTHER_PASSWORD)]
    assert host.leases.objects[lease_name(FLEET)] == original


def test_historical_refusal_stays_visible_without_reading_password(tmp_path, monkeypatch, wire):
    """An undeclared account's saved refusal is served, suspended included, with no password read (C4 ii)."""
    host = LeaseHost()
    lease = FleetLease(host, "ns", FLEET, claim_seconds=195)
    lease.claim()
    lease.refuse(API, "historic-digest", "login-refused")
    lease.release()
    snapshot = copy.deepcopy(host.leases.objects)
    p = process(tmp_path, monkeypatch, host, discovered=[at("east", FLEET)], fleet_account_username=OTHER)

    def no_password(*a, **kw):
        pytest.fail("historical row read the fleet password")
    monkeypatch.setattr("gsd.fleetlookup.fleet_password", no_password)
    p._ping_accounts()
    assert FLEET in p.signals.fleet_accounts(), "historical account disappeared"
    assert p.signals.fleet_accounts()[FLEET]["suspended"]
    from prometheus_client import generate_latest
    from gsd.metrics import build_registry
    metrics = generate_latest(build_registry(p.store, timedelta(0), signals=p.signals, settings=p.settings)).decode()
    assert "gsd_fleet_account_suspended 1.0" in metrics
    assert host.leases.objects == snapshot
    assert not wire.authorize


# ── the refusal record's real bound (Codex C3) and the residual of a false declaration ─────────────

def test_rotation_replay_contract_matches_the_lease(tmp_path, monkeypatch, wire):
    """The Lease keeps the latest refusal only: A, B, A across fresh processes sends A twice, as the spec states."""
    host = LeaseHost()
    wire.answers = directory({})
    for i, password in enumerate(["wrong-A", "wrong-B", "wrong-A"]):
        host.rotate(password)
        p = process(tmp_path, monkeypatch, host, discovered=[at("retrieved", OTHER)],
                    name=f"restart-{i}", fleet_account_username=OTHER)
        p._ping_accounts()
    assert presented(wire) == [(OTHER, "wrong-A"), (OTHER, "wrong-B"), (OTHER, "wrong-A")]
    text = spec_prose()
    assert "The Lease remembers only the latest refusal" in text
    assert "A → B → A" in text


def test_secret_recreation_rearms_a_fresh_process(tmp_path, monkeypatch, wire):
    """A recreated password Secret (a new uid) re-arms a fresh process once, as the spec states."""
    host = LeaseHost()
    host.rotate("wrong")
    wire.answers = directory({})
    for i in range(2):
        if i:
            host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"]["metadata"]["uid"] = "replacement-uid"
        process(tmp_path, monkeypatch, host, name=f"process-{i}",
                discovered=[at("target", OTHER)], fleet_account_username=OTHER)._ping_accounts()
    assert presented(wire) == [(OTHER, "wrong"), (OTHER, "wrong")]
    assert "A new Secret UID" in spec_prose()


def test_the_lookup_and_self_login_present_the_account_their_stanza_names(tmp_path, monkeypatch, wire):
    """PINS THE RESIDUAL: a stanza's account is a declaration; a false one is refused once, then gated (B2)."""
    host = LeaseHost()
    host.rotate(FLEET_PASSWORD)
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    looked_up = ClusterConfig("other", "https://api.other.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=OTHER)
    self_login = ClusterConfig("other-self", "https://api.other-self.example.com:6443", user_self_login=True,
                               ldap_connection_bootstrap=OTHER)
    for name in ("first", "restarted"):
        p = process(tmp_path, monkeypatch, host, looked_up, self_login, name=name, fleet_account_username=FLEET,
                    fleet_ping_enabled=False)
        p.store.upsert_cluster("other-self", self_login.api_url, True, source="values", credential="self-login")
        p._retrieve_pending()                           # the lookup: the Secret's password, as the stanza's OTHER
        assert sessions(p, [T0]).credential_for(p.settings.cluster("other-self")) is None   # gated: not sent
    assert presented(wire) == [(OTHER, FLEET_PASSWORD)]
