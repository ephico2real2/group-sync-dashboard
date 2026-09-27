"""#285 (SPEC_S4c): the credential lifecycle — the fleet account's Lease (the claim, the durable gate, fail
closed), the daily ping, `self-login` renewal and suspension, the metric families and the API blocks.

The fake target is S4a's and `wire` counts its authorize requests — the unit every budget here is stated in (a
wire mock counts authorize requests, not directory binds). The fake host is S4b's, with the Lease resource
answered by `LeaseAPI`: the API server's coordination.k8s.io/v1 Lease — GET, POST and PUT by name, and the
resourceVersion compare-and-swap (a PUT carrying a stale resourceVersion answers 409). One `LeaseAPI` behind two
pollers is one API server behind two processes; a new `Poller` over it is a restart. No test logs in as the fleet
account of any cluster: USER is the harness's own name."""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd.clusterconfig import FINDING_CODES
from gsd.config import ClusterConfig, Settings
from gsd.fleetlogin import FleetSession
from gsd.fleetlookup import CODES, CredentialGate, lookup
from gsd.fleetstate import PREFIX, ClaimHeld, FleetLease, claim_seconds, lease_digest, lease_name
from gsd.kube import FORBIDDEN, ClusterError
from gsd.metrics import RuntimeSignals, build_registry
from gsd.poller import Poller
from gsd.selflogin import SelfLoginSessions, renew_at
from gsd.store import Store
from test_fleet_login import API, PASSWORD, T0, TOKEN, USER, login_302, refused_401
from test_fleet_lookup import SA_TOKEN, UID, FakeHost, sa_secret, wire  # noqa: F401

LEASES = "/apis/coordination.k8s.io/v1/namespaces/ns/leases"
ANSWERS = {"401": refused_401, "500": lambda: httpx.Response(500, text="Internal Server Error")}
TOKEN_2 = "sha256~U2Vjb25kU2Vzc2lvblRva2VuVGhhdE11c3ROZXZlckxlYWs"
TOKEN_3 = "sha256~VGhpcmRTZXNzaW9uVG9rZW5UaGF0TXVzdE5ldmVyTGVhaw"


class LeaseAPI:
    """The API server's Lease resource, shared by every host built over it. `refuse` answers 403 to everything."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.serial = 0
        self.writes: list[tuple[str, str]] = []
        self.refuse = False

    def get(self, name: str) -> dict:
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {LEASES}/{name}")
        if name not in self.objects:
            raise ClusterError("unreachable", f"HTTP 404 on {LEASES}/{name}: not found")
        return copy.deepcopy(self.objects[name])

    def write(self, method: str, name: str, obj: dict) -> dict:
        self.writes.append((method, name))
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {method} {LEASES}")
        if method == "POST" and name in self.objects:
            raise ClusterError("unreachable", f"HTTP 409 on POST {LEASES}: AlreadyExists")
        if method == "PUT" and obj["metadata"].get("resourceVersion") != self.objects[name]["metadata"]["resourceVersion"]:
            raise ClusterError("unreachable", f"HTTP 409 on PUT {LEASES}/{name}: Conflict")
        self.serial += 1
        stored = copy.deepcopy(obj)
        stored["metadata"]["resourceVersion"] = str(self.serial)
        self.objects[name] = stored
        return copy.deepcopy(stored)

    def annotations(self, account: str = USER) -> dict:
        return self.objects.get(lease_name(account), {}).get("metadata", {}).get("annotations", {})

    def backdate(self, account: str, key: str, seconds: int) -> None:
        """Move an instant annotation back in time: the harness's clock for the ping's cadence."""
        ann = self.objects[lease_name(account)]["metadata"]["annotations"]
        moment = datetime.fromisoformat(ann[key].replace("Z", "+00:00")) - timedelta(seconds=seconds)
        ann[key] = moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class LeaseHost(FakeHost):
    """S4b's fake host — the fleet password Secret and the cluster Secrets — with the Lease resource on `leases`."""

    def __init__(self, leases: LeaseAPI | None = None, secrets: dict | None = None):
        super().__init__(secrets)
        self.leases = leases or LeaseAPI()

    def _get(self, client, path, params):
        if path.startswith(LEASES + "/"):
            return self.leases.get(path.rsplit("/", 1)[1])
        return super()._get(client, path, params)

    def _send(self, client, method, path, *, json=None, secrets=()):
        if path.startswith(LEASES):
            return self.leases.write(method, json["metadata"]["name"] if method == "POST" else path.rsplit("/", 1)[1], json)
        return super()._send(client, method, path, json=json, secrets=secrets)

    def rotate(self, password: str) -> None:
        self.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {    # an update in place keeps the uid
            "metadata": {"uid": UID}, "data": {"password": base64.b64encode(password.encode()).decode()}}


def stanza(name: str, url: str | None = None, **kw) -> ClusterConfig:
    return ClusterConfig(name, url or f"https://api.{name}.example.com:6443", sa_token_lookup=True,
                         ldap_connection_bootstrap=USER, **kw)


def retrieved(name: str) -> ClusterConfig:
    """A cluster the lookup retrieved: its own Secret, the token it stored, and the account it logged in as."""
    return ClusterConfig(name, f"https://api.{name}.example.com:6443", token_value=SA_TOKEN, source=f"secret:gsd-cluster-{name}",
                         token_source="remote-lookup", lookup_account=USER)


def self_login(name: str) -> ClusterConfig:
    return ClusterConfig(name, f"https://api.{name}.example.com:6443", user_self_login=True, ldap_connection_bootstrap=USER)


def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One process over `host`; USER is named on the chart, since only declared accounts are pinged (#432)."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True,
                 **{"fleet_account_username": USER, **kw})
    s.cluster_registry.replace(list(discovered), [], at="2026-09-26T00:00:00Z")
    return Poller(Store(str(tmp_path / f"{name}.db")), s, signals=RuntimeSignals())


def lines(caplog, event: str) -> list[str]:
    return [m for m in caplog.messages if m.startswith(event + " ")]


# ── R1: the claim is a compare-and-swap ──────────────────────────────────────────────────────────

def test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind(tmp_path, monkeypatch, wire):
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-a")
    b = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-b")
    seen_a, seen_b = a.read(), b.read()            # both read the absent Lease...
    a.claim(seen_a)                                 # ...A creates it
    with pytest.raises(ClaimHeld):
        b.claim(seen_b)                             # B's create answers 409: A won
    with pytest.raises(ClaimHeld):
        b.claim()                                   # a fresh read shows A's live claim
    a.release()
    stale = b.read()                                # released: no live claim in it...
    a.claim(); a.release()                          # ...but A claims and lets go again after B's read
    with pytest.raises(ClaimHeld):
        b.claim(stale)                              # B's PUT carries the older resourceVersion: 409, the CAS
    b.claim()
    b.release()
    # Through the poller: while another process holds the account, nothing binds; once it lets go, one bind.
    wire.answers = [login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("rnd"))
    a.claim()
    p._retrieve_pending()
    assert wire.authorize == [], "a bind without the claim"
    a.release()
    p._retrieve_pending()
    assert len(wire.authorize) == 1 and "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd" in host.secrets


def test_r1_a_paused_holders_refusal_is_recorded_and_it_never_clears_the_claim_that_took_over(wire):
    """B1's residual, stated rather than claimed away: a holder paused past its claim can still bind after another
    process took the claim over. When it resumes, its bound answer is re-applied to the Lease as it now is (the API
    conventions' duty on a 409) and the claim that took over is left standing."""
    from datetime import datetime
    host, now = LeaseHost(), [datetime(2026, 9, 26, 12, 0, tzinfo=UTC)]
    paused = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-a", clock=lambda: now[0])
    paused.claim()
    now[0] += timedelta(seconds=61)                  # judged expired...
    taker = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-b", clock=lambda: now[0])
    taker.claim()                                    # ...and taken
    paused.refuse("https://api.crc.testing:6443", lease_digest(USER, PASSWORD, UID), "login-refused")
    paused.release()
    obj = host.leases.objects[lease_name(USER)]
    assert json.loads(obj["metadata"]["annotations"]["groupsync-dashboard.io/refused"])["code"] == "login-refused"
    assert obj["spec"]["holderIdentity"] == "pod-b", "the resumed holder cleared the claim that took over"


# ── R2: the gate is on the object, and it is the account's ───────────────────────────────────────

@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_r2_the_budget_over_the_system_one_authorize_across_two_processes_three_targets_a_restart_and_an_edit(
        tmp_path, monkeypatch, wire, answer):
    """The Definition of Done: one wrong or locked password on one account, measured in authorize requests as
    (first, what each later shape adds). Before #285 the in-memory gate covered only its own process: a second
    replica, a restart and an irrelevant edit's rollout each sent the password once more."""
    host = LeaseHost()
    targets = [stanza("rnd", "https://api.crc.testing:6443"), stanza("east"), stanza("west")]
    wire.answers = [ANSWERS[answer]() for _ in range(8)]
    measured = {}
    first = process(tmp_path, monkeypatch, host, *targets, name="first")
    first._retrieve_pending()
    measured["one process, three targets"] = len(wire.authorize)
    for shape, clusters in (("a second replica", targets), ("a restart", targets),
                            ("an irrelevant config edit (visibility)", [dataclasses.replace(t, visibility="self-only") for t in targets])):
        before = len(wire.authorize)
        process(tmp_path, monkeypatch, host, *clusters, name=shape.split()[1])._retrieve_pending()
        measured[shape] = len(wire.authorize) - before
    assert measured == {"one process, three targets": 1, "a second replica": 0, "a restart": 0,
                        "an irrelevant config edit (visibility)": 0}, measured
    entry = json.loads(host.leases.annotations()["groupsync-dashboard.io/refused"])
    assert entry["digest"] == lease_digest(USER, PASSWORD, UID) != CredentialGate._digest(PASSWORD)
    assert entry["code"] == ("login-refused" if answer == "401" else "login-failed")
    assert entry["target"] == "https://api.crc.testing:6443", "the target that answered, kept as evidence"
    # A rotated password is a new (account, password): it binds once, and its success retires the old entry.
    host.rotate("rotated-pass-9")
    wire.answers = [login_302()]
    process(tmp_path, monkeypatch, host, targets[0], name="rotated")._retrieve_pending()
    assert len(wire.authorize) == 2 and "groupsync-dashboard.io/refused" not in host.leases.annotations()


def test_r2_the_lease_digest_is_salted_and_slow_not_the_gates_prefix():
    """The Lease is readable by `cluster-reader` (measured on the reference cluster), which cannot read the password
    Secret: a fingerprint whose other inputs are public would be an offline guessing oracle for the bind password.
    scrypt salted with the account AND the Secret's uid (#419, D2), 64 bits kept."""
    assert lease_digest(USER, PASSWORD, UID) != CredentialGate._digest(PASSWORD)
    assert lease_digest(USER, PASSWORD, UID) != lease_digest("another-account", PASSWORD, UID), "salted with the account"
    assert lease_digest(USER, PASSWORD, UID) != lease_digest(USER, PASSWORD, "another-secret-uid"), "salted with the uid"
    assert len(lease_digest(USER, PASSWORD, UID)) == 16 and lease_digest(USER, PASSWORD, UID) == lease_digest(USER, PASSWORD, UID)


# ── #293: the Lease never turns a per-target success mark into an account-wide refusal ──────────

def test_293s_success_mark_stays_per_target_and_off_the_lease(tmp_path, monkeypatch, wire):
    """#293's budget (SPEC_S5 §3.3), with the Lease in the loop: two SUCCESSFUL ConfigMap onboardings on one
    account are two authorizes; the Lease records no refusal; a restart with a missing output binds once more,
    as #293's table says; and the daily ping never writes the success mark."""
    host = LeaseHost()
    onboarded = [dataclasses.replace(stanza(n), onboarding=("fleet", "cm-1", n)) for n in ("rnd", "east")]
    wire.answers = [login_302() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, *onboarded, name="p")
    p._retrieve_pending()
    assert len(wire.authorize) == 2, "a success on one target gated the other"
    assert "groupsync-dashboard.io/refused" not in host.leases.annotations()
    assert all(p._credential_gate.refused(c.api_url, USER, PASSWORD) for c in onboarded), "#293's mark, per target"
    # A restart with the output missing: a new gate, the same Lease — one more bind (#293's row, unchanged).
    del host.secrets["/api/v1/namespaces/ns/secrets/gsd-cluster-rnd"]
    wire.secret = httpx.Response(403)
    process(tmp_path, monkeypatch, host, onboarded[0], name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 3
    # The ping of an onboarded cluster marks nothing: onboarding=() is what it logs in with.
    wire.secret = httpx.Response(200, json=sa_secret())
    ping = process(tmp_path, monkeypatch, host, discovered=[dataclasses.replace(retrieved("rnd"), onboarding=("fleet", "cm-1", "rnd"))],
                   name="ping")
    ping._ping_accounts()
    assert len(wire.authorize) == 4 and not ping._credential_gate._spent


# ── R3: the ping is one bind per account per cadence ─────────────────────────────────────────────

def test_r3_twenty_clusters_on_one_account_are_one_ping_a_cadence_rotating_by_name(tmp_path, monkeypatch, wire, caplog):
    host = LeaseHost()
    fleet = [retrieved(f"c{n:02d}") for n in range(20)]
    wire.answers = [login_302() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, discovered=fleet)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._ping_accounts()
        p._ping_accounts()                                     # not due: nothing
    assert len(wire.authorize) == 1 and len(wire.reads) == 1 and len(wire.revokes) == 1
    ann = host.leases.annotations()
    assert (ann["groupsync-dashboard.io/ping-last-target"], ann["groupsync-dashboard.io/ping-last-outcome"]) == ("c00", "ok")
    line, = lines(caplog, "fleet-ping")
    assert f"account={USER}" in line and "target=c00" in line and "last_ok=" in line and "last_used=2026-09-22" in line
    assert not [w for w in host.writes if "/secrets" in w[1]], "the ping stores nothing: no cluster Secret is written"
    # A restart reads the instant off the Lease and does not ping again inside the cadence.
    process(tmp_path, monkeypatch, host, discovered=fleet, name="restarted")._ping_accounts()
    assert len(wire.authorize) == 1
    # A cadence later, the next target by name.
    host.leases.backdate(USER, "groupsync-dashboard.io/ping-last-attempt", 86400)
    p._ping_accounts()
    assert len(wire.authorize) == 2 and host.leases.annotations()["groupsync-dashboard.io/ping-last-target"] == "c01"
    # A rotated password is confirmed within the discovery cadence, once — and once only when its read keeps
    # failing (a revoked grant on the target): the Lease records the password each ATTEMPT was for (B3).
    host.rotate("rotated-pass-9")
    wire.secret = httpx.Response(403, text="forbidden")
    p._ping_accounts(); p._ping_accounts(); p._ping_accounts()
    assert len(wire.authorize) == 3 and host.leases.annotations()["groupsync-dashboard.io/ping-last-outcome"] == "sa-token-unreadable"


# ── R4: the ping stands down ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["login-refused", "login-failed"])
def test_r4_a_gated_account_is_not_pinged_and_is_said_once(tmp_path, monkeypatch, wire, caplog, code):
    host = LeaseHost()
    holder = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-a")
    holder.claim()
    holder.refuse("https://api.other.example.com:6443", lease_digest(USER, PASSWORD, UID), code)
    holder.release()
    p = process(tmp_path, monkeypatch, host, discovered=[retrieved("c00")])
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._ping_accounts(); p._ping_accounts(); p._ping_accounts()
    assert wire.requests == [], "a gated account was pinged — one more bind a day against a locked account"
    line, = lines(caplog, "fleet-ping-failed")
    assert f"outcome={code}" in line and "gave_up=true" in line and f"suspended={USER}" in line and "scope=ping" in line
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "gsd-cluster-c00"]
    assert finding.code == code and "stands down" in finding.detail


# ── R5: the margin ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expires_in,seconds", [(3600, 2700), (86400, 79200), (31536000, 31528800)])
def test_r5_renewal_is_a_fixed_margin_before_expiry(expires_in, seconds):
    """SPEC_S4 §3.1: expires_at − min(2 h, ¼ × expires_in) — CRC's year renews two hours before it ends. The
    reference cluster cannot fire this path (SPEC_S4c §2.3), so the clock here is injected."""
    session = FleetSession("c", USER, TOKEN, obtained_at=T0, expires_in=expires_in, issuer="i", attempts=1)
    assert renew_at(session) == T0 + timedelta(seconds=seconds)


def sessions(p: Poller, now: list) -> SelfLoginSessions:
    p.self_login = SelfLoginSessions(p, clock=lambda: now[0])
    return p.self_login


def test_r5_a_session_too_short_to_renew_is_not_chased(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"), poll_interval_seconds=60)
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="200"), login_302(expires_in="200")]
    with caplog.at_level(logging.INFO, logger="gsd"):
        assert s.credential_for(p.settings.cluster("sl")) is None
        now[0] += timedelta(seconds=60)
        assert s.credential_for(p.settings.cluster("sl")) is None
    assert len(wire.authorize) == 1 and len(wire.revokes) == 1, "the short session was exited at once, and not chased"
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "sl"]
    assert finding.code == "self-login-lifetime-too-short" and "200s" in finding.detail and "240s" in finding.detail


# ── R6: renewal keeps the poll fed and revokes the old token second ─────────────────────────────

def test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"))
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600"), lambda r: httpx.ConnectError("refused"),
                    login_302(expires_in="3600", token=TOKEN_2)]
    first = s.credential_for(p.settings.cluster("sl"))
    assert first.token_value == TOKEN and first.credential_kind == "bearer"
    now[0] = T0 + timedelta(seconds=2700)                    # renew_at
    kept = s.credential_for(p.settings.cluster("sl"))
    assert kept.token_value == TOKEN and wire.revokes == [], "an unreachable renewal keeps the session it has"
    now[0] += timedelta(seconds=60)
    with caplog.at_level(logging.INFO, logger="gsd"):
        renewed = s.credential_for(p.settings.cluster("sl"))
    assert renewed.token_value == TOKEN_2
    order = [(r.method, r.url.path) for r in wire.requests]
    assert order.index(("GET", "/oauth/authorize"), 2) < next(i for i, (m, _) in enumerate(order) if m == "DELETE")
    assert wire.revokes[0].headers["authorization"] == f"Bearer {TOKEN}", "the superseded token, revoked second"
    assert lines(caplog, "self-login-renewed")
    assert s.view("sl")["state"] == "current" and s.view("sl")["expires_at"] == "2026-09-21T13:46:00Z"


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_r6_a_bound_failure_suspends_every_self_login_cluster_on_the_account(tmp_path, monkeypatch, wire, caplog, answer):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"), self_login("b"))
    for name in ("a", "b"):
        p.store.upsert_cluster(name, f"https://api.{name}.example.com:6443", True, source="values", credential="self-login")
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600"), login_302(expires_in="3600", token=TOKEN_2), ANSWERS[answer]()]
    s.credential_for(p.settings.cluster("a")); s.credential_for(p.settings.cluster("b"))
    now[0] = T0 + timedelta(seconds=2700)
    with caplog.at_level(logging.INFO, logger="gsd"):
        assert s.credential_for(p.settings.cluster("a")) is None
        assert s.credential_for(p.settings.cluster("b")) is None
    assert len(wire.authorize) == 3 and len(wire.revokes) == 2, "both sessions revoked, and b did not log in again"
    line, = lines(caplog, "fleet-credential-suspended")
    assert f"suspended={USER}" in line and "scope=self-login" in line and "stopped=2" in line and "clusters=a,b" in line
    rows = {r["id"]: r["status"] for r in p.store.clusters()}
    assert rows == {"a": "auth_failed" if answer == "401" else "unreachable", "b": "auth_failed" if answer == "401" else "unreachable"}
    assert json.loads(host.leases.annotations()["groupsync-dashboard.io/refused"])["digest"] == lease_digest(USER, PASSWORD, UID)
    # A restart reads the gate off the Lease: no login.
    other = process(tmp_path, monkeypatch, host, self_login("a"), name="restarted")
    assert sessions(other, now).credential_for(other.settings.cluster("a")) is None and len(wire.authorize) == 3


# ── R7: the 401 rule ─────────────────────────────────────────────────────────────────────────────

def test_r7_a_401_before_expiry_reauthenticates_once_and_a_second_suspends(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"))
    s = sessions(p, now)
    wire.answers = [login_302(), login_302(token=TOKEN_2)]
    wire.revoke = httpx.Response(401, text="Unauthorized")       # the revoke of an invalidated token: 401
    cluster = p.settings.cluster("sl")
    s.credential_for(cluster)
    now[0] += timedelta(seconds=60)
    with caplog.at_level(logging.INFO, logger="gsd"):
        s.poll_answered(cluster, "auth_failed")                     # an administrator revoked it, say
        assert s.credential_for(cluster).token_value == TOKEN_2     # one login on the next cycle
        assert "groupsync-dashboard.io/refused" not in host.leases.annotations(), "nothing evaluated the password"
        assert not p._credential_gate.refused(cluster.api_url, USER, PASSWORD)
        s.poll_answered(cluster, "auth_failed")                     # the fresh session refused too
        assert s.credential_for(cluster) is None and s.credential_for(cluster) is None
    assert len(wire.authorize) == 2, "a re-login loop"
    assert any("outcome=auth_failed" in m for m in lines(caplog, "fleet-logout-failed")), "#283's revoke-side reading"
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "sl"]
    assert finding.code == "self-login-suspended" and s.view("sl")["state"] == "suspended"


# ── R8: fail closed ──────────────────────────────────────────────────────────────────────────────

def test_r8_an_unreadable_lease_binds_nothing_on_any_path_and_is_said_once(tmp_path, monkeypatch, wire, caplog):
    host = LeaseHost()
    host.leases.refuse = True
    p = process(tmp_path, monkeypatch, host, stanza("rnd"), self_login("sl"), discovered=[retrieved("c00")])
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._retrieve_pending(); p._retrieve_pending()
        p._ping_accounts()
        assert p.self_login.credential_for(p.settings.cluster("sl")) is None
    assert wire.authorize == [], "a bind without the gate"
    codes = {(f.secret, f.code) for f in p.settings.cluster_registry.findings()}
    assert {("gsd-cluster-rnd", "fleet-state-unavailable"), ("gsd-cluster-c00", "fleet-state-unavailable"),
            ("sl", "fleet-state-unavailable")} <= codes
    assert len([m for m in lines(caplog, "fleet-lookup-failed") if "fleet-state-unavailable" in m]) == 1
    assert all("coordination.k8s.io/leases" in f.detail for f in p.settings.cluster_registry.findings()
               if f.code == "fleet-state-unavailable")


# ── R9: no credential reaches a line ─────────────────────────────────────────────────────────────

def test_r9_every_new_event_carries_no_password_and_no_token(tmp_path, monkeypatch, wire, caplog):
    """The redaction pin (SPEC_S3 §3.1 rule 4): the password echoed by the OAuth server, and the session a renewal
    replaces echoed beside it, reach no line of the events this change adds — nor the password any line at all."""
    host, now = LeaseHost(), [T0]
    # The self-login cluster logs in as another account, so the ping's refusal does not gate it first.
    other = dataclasses.replace(self_login("a"), ldap_connection_bootstrap="svc-other")
    p = process(tmp_path, monkeypatch, host, other, discovered=[retrieved("c00"), retrieved("c01")])
    s = sessions(p, now)
    wire.answers = [login_302(), login_302(token=TOKEN_2), login_302(token=TOKEN_3),
                    httpx.Response(500, text=f"echo {PASSWORD}"), httpx.Response(500, text=f"echo {PASSWORD} {TOKEN_2}")]
    with caplog.at_level(logging.DEBUG, logger="gsd"):
        cluster = p.settings.cluster("a")
        s.credential_for(cluster)                                   # a session (TOKEN)
        now[0] += timedelta(seconds=60)
        s.poll_answered(cluster, "auth_failed")                     # self-login-failed
        s.credential_for(cluster)                                   # self-login-renewed (TOKEN_2)
        p._ping_accounts()                                          # fleet-ping (TOKEN_3)
        host.leases.backdate(USER, "groupsync-dashboard.io/ping-last-attempt", 86400)
        p._ping_accounts()                                          # fleet-ping-failed: the password echoed
        p._ping_accounts()                                          # the stand-down, said once
        p.self_login._sessions["a"].renew_at = now[0]               # due: the renewal meets the password and TOKEN_2
        s.credential_for(cluster)                                   # fleet-credential-suspended
    new = [m for event in ("self-login-failed", "self-login-renewed", "fleet-ping", "fleet-ping-failed",
                           "fleet-credential-suspended") for m in lines(caplog, event)]
    assert {m.split()[0] for m in new} == {"self-login-failed", "self-login-renewed", "fleet-ping", "fleet-ping-failed",
                                           "fleet-credential-suspended"}
    assert any("echo <redacted>" in m for m in lines(caplog, "fleet-credential-suspended")), "the echo was not met"
    for secret in (PASSWORD, TOKEN, TOKEN_2, TOKEN_3, SA_TOKEN):
        assert secret not in "\n".join(new), secret
    assert PASSWORD not in "\n".join(caplog.messages) and SA_TOKEN not in "\n".join(caplog.messages)


# ── the metric families: unlabelled, absent until true ───────────────────────────────────────────

def test_the_fleet_families_are_unlabelled_and_absent_until_a_ping_succeeds():
    store = Store(":memory:")
    try:
        signals, settings = RuntimeSignals(), Settings(clusters=[ClusterConfig("h", "https://h", token_env="X")], db_path=":memory:")
        text = generate_latest(build_registry(store, timedelta(0), signals=signals, settings=settings)).decode()
        assert "# HELP gsd_fleet_account_last_ok_timestamp_seconds " in text
        assert "\ngsd_fleet_account_last_ok_timestamp_seconds " not in text, "absence means never, not zero"
        assert "\ngsd_fleet_account_ping_enabled 1.0" in text and "\ngsd_fleet_account_suspended 0.0" in text
        signals.note_fleet_accounts({USER: {"last_ok": "2026-09-22T06:00:05Z", "suspended": []},
                                     "acct-two": {"last_ok": "2026-09-21T06:00:05Z",
                                                "suspended": [{"target": "https://x", "since": "t", "code": "login-refused"}]}})
        text = generate_latest(build_registry(store, timedelta(0), signals=signals,
                                              settings=dataclasses.replace(settings, fleet_ping_enabled=False))).decode()
        value = next(float(l.split()[1]) for l in text.splitlines() if l.startswith("gsd_fleet_account_last_ok_timestamp_seconds "))
        assert value == datetime(2026, 9, 21, 6, 0, 5, tzinfo=UTC).timestamp(), "the OLDEST account's instant"
        assert "\ngsd_fleet_account_ping_enabled 0.0" in text and "\ngsd_fleet_account_suspended 1.0" in text
        assert "gsd_fleet_account_" not in "".join(l for l in text.splitlines() if "{" in l), "a label on a fleet family"
        assert USER not in text and "acct-two" not in text, "a username on a public endpoint"
    finally:
        store.close()


# ── the API's two blocks ─────────────────────────────────────────────────────────────────────────

def test_the_api_serves_the_fleet_block_and_a_self_login_session_as_instants(tmp_path):
    from gsd.api import build_app
    from gsd.clusterconfig import parse_secret
    from test_clusterconfig import _secret
    from test_visibility import H, _MapResolver, _seed, _settings
    db = str(tmp_path / "gsd.db"); _seed(db)
    settings = _settings(db)
    sl = parse_secret(_secret("gsd-cluster-sl", cluster="sl", config={"userSelfLogin": True, "ldapConnectionBootstrap": USER}),
                      host_name="c1")
    settings.cluster_registry.replace([sl], [], at="2026-09-26T00:00:00Z")
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.signals.note_fleet_accounts({USER: {"lease": lease_name(USER), "last_attempt": "2026-09-22T06:00:04Z",
                                                  "last_ok": "2026-09-22T06:00:05Z", "last_outcome": "ok",
                                                  "last_target": "shared-rnd", "suspended": []}})
    app.state.signals.note_self_login("sl", {"state": "current", "expires_at": "2026-09-23T06:00:05Z",
                                             "renew_at": "2026-09-23T04:00:05Z"})
    with TestClient(app) as c:
        body = c.get("/api/clusterconfigs", headers=H("root")).json()
    assert body["fleet"] == {"ping": {"enabled": True, "interval_seconds": 86400},
                             "accounts": [{"username": USER, "lease": lease_name(USER), "last_attempt": "2026-09-22T06:00:04Z",
                                           "last_ok": "2026-09-22T06:00:05Z", "last_outcome": "ok",
                                           "last_target": "shared-rnd", "suspended": []}]}
    by = {x["id"]: x for x in body["clusters"]}
    assert by["sl"]["credential"] == "self-login" and by["sl"]["session"]["expires_at"] == "2026-09-23T06:00:05Z"
    assert "session" not in by["c1"], "the session block is a self-login cluster's alone"


# ── the vocabulary ───────────────────────────────────────────────────────────────────────────────

def test_the_new_codes_join_the_closed_set_and_claim_seconds_is_computed():
    from gsd.fleetstate import FleetStateUnavailable
    assert set(CODES) <= set(FINDING_CODES) and FleetStateUnavailable.code in FINDING_CODES
    assert {"fleet-state-unavailable", "self-login-suspended", "self-login-lifetime-too-short"} <= set(FINDING_CODES)
    s = Settings(clusters=[], db_path=":memory:")
    assert claim_seconds(s) == 195
    assert claim_seconds(dataclasses.replace(s, request_timeout_seconds=30)) == 375


def test_the_gate_docstring_names_the_lease_as_its_durable_half():
    doc = " ".join((CredentialGate.__doc__ or "").split())
    assert "the cache of the account Lease's gate (SPEC_S4c §3.3)" in doc
    assert "not covered until #285" not in doc and "The SPENT kind is never on the Lease" in doc
    assert lookup.__kwdefaults__["lease"] is None


# ── the review of #419: round 1's accepted findings and OB2's rulings, as behaviour ─────────────────

def expire(host: LeaseHost) -> None:
    """Every claim judged expired: what clock skew larger than claim_seconds, or a pause that long, looks like."""
    for obj in host.leases.objects.values():
        obj["spec"]["renewTime"] = "2000-01-01T00:00:00.000000Z"


def kind(obj: dict) -> str:
    entry = obj.get("metadata", {}).get("annotations", {}).get("groupsync-dashboard.io/refused")
    return "reservation" if entry and json.loads(entry).get("uncertain") else "refusal" if entry else "other"


@pytest.mark.parametrize("failure", ["lost-write", "crash"])
def test_d1_the_budget_survives_a_lost_refusal_write_and_a_crash(tmp_path, monkeypatch, wire, failure):
    """D1 (Codex's `test_durable_budget`): the attempt is on the Lease before the password is on the wire, so neither
    a refusal write the API server rejects nor a process that dies after the authorize GET sends it again after the
    claim expires. The 74 blocks measured 2 authorizes in both."""
    host = LeaseHost()
    original = host.leases.write

    def reject_the_answer(method, name, obj):
        if kind(obj) == "refusal":
            raise ClusterError(FORBIDDEN, "HTTP 403 on the refusal write")
        return original(method, name, obj)

    first = process(tmp_path, monkeypatch, host, stanza("a"), stanza("b"), stanza("c"), name="first")
    if failure == "lost-write":
        wire.answers = [refused_401(), refused_401()]
        monkeypatch.setattr(host.leases, "write", reject_the_answer)
        first._retrieve_pending()
        monkeypatch.setattr(host.leases, "write", original)
    else:
        wire.answers = [lambda request: SystemExit("the process dies after the authorize GET"), refused_401()]
        with pytest.MonkeyPatch.context() as crash, pytest.raises(SystemExit):
            crash.setattr(FleetLease, "release", lambda *a, **k: None)          # nothing runs after a crash
            first._retrieve_pending()
    expire(host)
    process(tmp_path, monkeypatch, host, stanza("a"), stanza("b"), stanza("c"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 1, f"{failure}: {len(wire.authorize)} authorizes"


def test_d1_clock_skew_does_not_admit_a_second_bind(tmp_path, monkeypatch, wire):
    """D1 (Codex): a second replica judges the first's live claim expired while its authorize is in flight."""
    host = LeaseHost()
    other = process(tmp_path, monkeypatch, host, stanza("b"), name="second")

    def interleave(request):
        expire(host)
        other._retrieve_pending()
        return refused_401()

    wire.answers = [interleave, refused_401()]
    process(tmp_path, monkeypatch, host, stanza("a"), name="first")._retrieve_pending()
    assert len(wire.authorize) == 1


@pytest.mark.parametrize("point", ["reservation", "authorize", "refusal"])
def test_d1_skew_takeover_at_each_point_of_the_attempt(tmp_path, monkeypatch, wire, point):
    """D1 (OB2): the second replica takes the claim over — skew larger than claim_seconds — before the first's
    reservation lands, while its authorize is in flight, or before its refusal lands. One authorize each: the
    reservation is a strict compare-and-swap (a 409 abandons the attempt, never re-applied)."""
    host = LeaseHost()
    other = process(tmp_path, monkeypatch, host, stanza("b"), name="second")
    fired = []

    def takeover():
        if not fired:
            fired.append(point)
            expire(host)
            other._retrieve_pending()

    wire.answers = [refused_401() for _ in range(3)]
    if point == "authorize":
        wire.answers[0] = lambda request: takeover() or refused_401()
    original = host.leases.write
    monkeypatch.setattr(host.leases, "write", lambda method, name, obj: (
        takeover() if method == "PUT" and kind(obj) == point else None) or original(method, name, obj))
    process(tmp_path, monkeypatch, host, stanza("a"), name="first")._retrieve_pending()
    assert fired and len(wire.authorize) == 1, (fired, len(wire.authorize))


def test_d1_a_paused_winner_resumes_after_the_takeover_and_does_not_bind(tmp_path, monkeypatch, wire):
    """B1's residual as the 74 blocks stated it (one extra bind per paused winner, measured 2 there) is closed: the
    paused claimant's reservation meets the 409 of the claim taken over, and its attempt is abandoned."""
    host = LeaseHost()
    other = process(tmp_path, monkeypatch, host, stanza("b"), name="second")
    original, fired = host.leases.write, []

    def hooked(method, name, obj):
        if method == "PUT" and not fired and kind(obj) in ("reservation", "refusal"):
            fired.append(True)
            expire(host)
            other._retrieve_pending()
        return original(method, name, obj)

    wire.answers = [refused_401() for _ in range(3)]
    monkeypatch.setattr(host.leases, "write", hooked)
    process(tmp_path, monkeypatch, host, stanza("a"), name="first")._retrieve_pending()
    assert fired and len(wire.authorize) == 1


def test_d2_the_comparison_uses_compare_digest_and_a_secret_without_a_uid_is_refused(monkeypatch):
    """D2 (Codex's `test_comparison_uses_compare_digest`): `hmac.compare_digest`. And the salt is the Secret's uid,
    which every object an API server serves carries: a Secret without one is refused, never salted with less."""
    import hmac
    from gsd.fleetlookup import LookupRefused, fleet_password
    from gsd.fleetstate import PREFIX, _record
    calls, compare = [], hmac.compare_digest
    monkeypatch.setattr(hmac, "compare_digest", lambda a, b: calls.append(a) or compare(a, b))
    digest = lease_digest(USER, PASSWORD, UID)
    record = _record(USER, {"metadata": {"annotations": {PREFIX + "refused": json.dumps({"digest": digest})}}})
    assert record.gated(digest) is not None and calls == [digest]
    host = LeaseHost()
    host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"].pop("metadata")
    with pytest.raises(LookupRefused) as exc:
        fleet_password(host, Settings(clusters=[], db_path=":memory:"), "ns")
    assert exc.value.code == "fleet-credential-missing" and "metadata.uid" in exc.value.detail


def test_d3_a_lookup_refusal_stops_a_valid_self_login_session_within_the_same_cycle(tmp_path, monkeypatch, wire, caplog):
    """D3 (OB2): an entry the lookup wrote stops the account's valid self-login sessions in the same discovery cycle
    (`_retrieve_pending` then `_ping_accounts`), said once."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"), stanza("b"))
    s = sessions(p, now)
    wire.answers = [login_302(), refused_401()]
    assert s.credential_for(p.settings.cluster("a")) is not None
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._retrieve_pending()
        assert s.view("a")["state"] == "current"
        p._ping_accounts()
        assert s.credential_for(p.settings.cluster("a")) is None and s.view("a")["state"] == "suspended"
        p._ping_accounts()
    line, = lines(caplog, "fleet-credential-suspended")
    assert "scope=self-login" in line and "stopped=1" in line and len(wire.revokes) == 1


def test_d3_another_replicas_refusal_stops_this_replicas_valid_session_within_one_cadence(tmp_path, monkeypatch, wire):
    """D3 (OB2): the entry another replica wrote, observed by this replica's next sweep."""
    host, now = LeaseHost(), [T0]
    one = process(tmp_path, monkeypatch, host, self_login("a"), name="one")
    s = sessions(one, now)
    wire.answers = [login_302(), refused_401()]
    assert s.credential_for(one.settings.cluster("a")) is not None
    process(tmp_path, monkeypatch, host, stanza("b"), name="two")._retrieve_pending()
    assert s.view("a")["state"] == "current"
    one._ping_accounts()
    assert s.credential_for(one.settings.cluster("a")) is None and s.view("a")["state"] == "suspended"
    assert len(wire.authorize) == 2


def test_lookup_refusal_stops_existing_self_login(tmp_path, monkeypatch, wire):
    """Codex's F5 test, run in the discovery cycle's order: `_ping_accounts()` after `_retrieve_pending()`."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"), stanza("b"))
    s = sessions(p, now)
    wire.answers = [login_302(), refused_401()]
    s.credential_for(p.settings.cluster("a"))
    p._retrieve_pending()
    p._ping_accounts()
    assert s.credential_for(p.settings.cluster("a")) is None, "a current session ignored the account's refusal"
    assert s.view("a")["state"] == "suspended"


def test_d3_an_attempt_in_flight_on_another_replica_is_not_read_as_a_refusal(tmp_path, monkeypatch, wire, caplog):
    """The sweep reads the Lease outside any claim, so an `uncertain` entry under a LIVE claim may be an attempt still
    under way: it is left for the next cadence, and neither this process's gate nor its sessions are touched. Read as
    a refusal, a success elsewhere would leave this replica suspended and gated until a rotation or a restart."""
    host, now = LeaseHost(), [T0]
    one = process(tmp_path, monkeypatch, host, self_login("a"), name="one")
    s = sessions(one, now)
    wire.answers = [login_302()]
    assert s.credential_for(one.settings.cluster("a")) is not None
    other = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-b")
    other.claim()
    other.reserve("https://api.b.example.com:6443", lease_digest(USER, PASSWORD, UID))     # in flight
    with caplog.at_level(logging.INFO, logger="gsd"):
        one._ping_accounts()
        assert s.view("a")["state"] == "current" and one._credential_gate.account_refusal(USER, PASSWORD) is None
        other.complete()                                                                   # a session came back
        other.release()
        one._ping_accounts()
    assert s.credential_for(one.settings.cluster("a")) is not None and not lines(caplog, "fleet-credential-suspended")


def test_old_session_echo_not_in_findings(tmp_path, monkeypatch, wire, caplog):
    """D4 (Codex's test, with OB2's premise): the renewal's authorize GET carries no held session token, so only the
    issuing OAuth server can echo one; when it does, neither the standing finding the API serves nor any line carries
    it — `FleetLogin(secrets=...)` and the finding redacted like the line."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600", token=TOKEN_2), httpx.Response(500, text=f"echo {TOKEN_2}")]
    with caplog.at_level(logging.INFO, logger="gsd"):
        s.credential_for(p.settings.cluster("a"))
        now[0] += timedelta(seconds=2700)
        assert s.credential_for(p.settings.cluster("a")) is None
    assert not [r for r in wire.authorize if TOKEN_2 in str(r.headers) + str(r.url)], "the renewal carried the held token"
    assert lines(caplog, "fleet-login-failed") and lines(caplog, "fleet-credential-suspended")
    assert all(TOKEN_2 not in (f.detail or "") for f in p.settings.cluster_registry.findings())
    assert all(TOKEN_2 not in m for m in caplog.messages)
    # The finding is scrubbed by `_suspend` itself, whatever produced its detail — not only by FleetLogin's scrub.
    s._suspend(p.settings.cluster("a"), USER, (USER, "-", "-"), code="login-failed", target="", detail=f"echo {TOKEN_3}",
               secrets=(TOKEN_3,))
    assert all(TOKEN_3 not in (f.detail or "") for f in p.settings.cluster_registry.findings())


def test_spent_success_does_not_suspend_self_login_account(tmp_path, monkeypatch, wire):
    """F2 (Codex): #293's per-target SPENT mark is a writing lookup's budget, never an account refusal."""
    host, now = LeaseHost(), [T0]
    onboard = dataclasses.replace(stanza("a"), onboarding=("fixture", "uid-1", "a"))
    same_target = dataclasses.replace(self_login("b"), api_url=onboard.api_url)
    p = process(tmp_path, monkeypatch, host, onboard, same_target, self_login("c"))
    wire.answers = [login_302(), login_302()]
    p._retrieve_pending()
    s = sessions(p, now)
    assert s.credential_for(same_target) is not None, "a per-target success was treated as an account refusal"
    assert s.view("c")["state"] != "suspended" and len(wire.authorize) == 2


def test_ping_ignores_onboarding_spent_mark_in_same_process(tmp_path, monkeypatch, wire):
    """F2 (Codex): the read-only ping asks for an account refusal alone, so the process that onboarded a cluster
    still pings it — round 1 found the composition test built a fresh Poller and could not see this."""
    host = LeaseHost()
    onboard = dataclasses.replace(stanza("a"), onboarding=("fixture", "uid-1", "a"))
    p = process(tmp_path, monkeypatch, host, onboard)
    wire.answers = [login_302(), login_302()]
    p._retrieve_pending()
    p.settings = dataclasses.replace(p.settings, clusters=[p.settings.host_cluster()])
    p.settings.cluster_registry.replace([retrieved("a")], [], at="now")
    p._ping_accounts()
    assert len(wire.authorize) == 2, "the ping was silenced by a per-target onboarding success mark"


def test_ping_read_failure_with_no_retrieved_targets(tmp_path, monkeypatch, wire):
    """F3 (Codex): an account with no ping target and an unreadable Lease raised IndexError on `names[0]`. Its
    unavailable-state finding goes to the account's member clusters, and the next read clears it."""
    host = LeaseHost()
    host.leases.refuse = True
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    p._ping_accounts()
    assert not wire.authorize
    assert ("gsd-cluster-a", "fleet-state-unavailable") in {(f.secret, f.code) for f in p.settings.cluster_registry.findings()}
    host.leases.refuse = False
    p._ping_accounts()
    assert "fleet-state-unavailable" not in {f.code for f in p.settings.cluster_registry.findings()}


# ── the review of #419, round 2: the entry's owner, the sweep's window, the tokens held at a revoke ─────────

def test_d1_paused_winner_success_clears_its_own_reservation_on_409():
    """C5 (Grok): a holder paused past its claim whose attempt then gets a session removes its own reservation, though
    the claim was taken meanwhile — round 1 left it there, gating a password that had just worked."""
    host = LeaseHost()
    now = [datetime(2026, 9, 26, 12, 0, tzinfo=UTC)]
    digest = lease_digest(USER, PASSWORD, UID)
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-a", clock=lambda: now[0])
    a.claim()
    a.reserve("https://api.a.example.com:6443", digest)
    now[0] += timedelta(seconds=61)
    b = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-b", clock=lambda: now[0])
    b.claim()
    b.release()
    a.complete()
    a.release()
    assert PREFIX + "refused" not in host.leases.annotations(), "own reservation left after complete() met a 409"


def test_d1_paused_winner_complete_does_not_erase_a_foreign_refusal():
    """C5 (Grok): the late success leaves an answer another process recorded meanwhile."""
    host = LeaseHost()
    now = [datetime(2026, 9, 26, 12, 0, tzinfo=UTC)]
    digest = lease_digest(USER, PASSWORD, UID)
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-a", clock=lambda: now[0])
    a.claim()
    a.reserve("https://api.a.example.com:6443", digest)
    now[0] += timedelta(seconds=61)
    b = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-b", clock=lambda: now[0])
    b.claim()
    b.refuse("https://api.b.example.com:6443", lease_digest(USER, "other-pass", UID), "login-refused")
    b.release()
    a.complete()
    a.release()
    left = host.leases.annotations().get(PREFIX + "refused")
    assert left and '"uncertain"' not in left and "login-refused" in left


def test_paused_success_clears_only_its_reservation():
    """C5 (Codex): the removal leaves the claim that took over standing."""
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="a")
    a.claim()
    a.reserve("https://api.example", lease_digest(USER, PASSWORD, UID))
    expire(host)
    b = FleetLease(host, "ns", USER, claim_seconds=60, identity="b")
    b.claim()
    a.complete()
    assert PREFIX + "refused" not in host.leases.annotations()
    assert host.leases.objects[lease_name(USER)]["spec"]["holderIdentity"] == "b"


def test_reservations_from_different_attempts_are_distinguishable():
    """C5 (Codex's probe): a rotation and a rotation back within one second reserve the same password against the same
    target at the same instant — byte for byte the paused holder's entry, but for the nonce. Its late success must not
    erase that attempt's reservation."""
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="a", clock=lambda: T0)
    a.claim()
    digest = lease_digest(USER, PASSWORD, UID)
    a.reserve("https://api.example", digest)
    first = host.leases.annotations()[PREFIX + "refused"]
    expire(host)
    b = FleetLease(host, "ns", USER, claim_seconds=60, identity="b", clock=lambda: T0)
    b.claim()
    b.reserve("https://api.example", lease_digest(USER, "fixture-rotation", UID))
    b.complete()
    b.release()
    c = FleetLease(host, "ns", USER, claim_seconds=60, identity="c", clock=lambda: T0)
    c.claim()
    c.reserve("https://api.example", digest)
    latest = host.leases.annotations()[PREFIX + "refused"]
    assert first != latest, "byte equality cannot identify an attempt"
    a.complete()
    assert host.leases.annotations()[PREFIX + "refused"] == latest


def test_stale_refusal_does_not_overwrite_new_password_reservation():
    """F1 (Codex): a paused holder's late refusal of the old password leaves the rotated password's reservation."""
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="a")
    a.claim()
    a.reserve("https://api.example", lease_digest(USER, PASSWORD, UID))
    expire(host)
    b = FleetLease(host, "ns", USER, claim_seconds=60, identity="b")
    b.claim()
    newer = lease_digest(USER, "fixture-rotated-password", UID)
    b.reserve("https://api.example", newer)
    a.refuse("https://api.example", lease_digest(USER, PASSWORD, UID), "login-refused")
    assert json.loads(host.leases.annotations()[PREFIX + "refused"])["digest"] == newer


def test_rotation_plus_stale_refusal_does_not_rearm_new_password(tmp_path, monkeypatch, wire):
    """F1 (Codex), on the wire — the rotation residual OB2's ruling D1 stated: the old password's late refusal lands
    while the rotated password is being sent, and the new holder crashes. Round 1 re-applied the refusal over the new
    reservation, and the restart sent the new password again: 2 authorizes."""
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=60, identity="paused")
    a.claim()
    a.reserve("https://api.old.example", lease_digest(USER, PASSWORD, UID))
    expire(host)
    host.rotate("fixture-new-wrong-password")

    def old_answer_arrives_during_new_authorize(request):
        a.refuse("https://api.old.example", lease_digest(USER, PASSWORD, UID), "login-refused")
        return SystemExit("new holder crashes after sending its password")

    wire.answers = [old_answer_arrives_during_new_authorize, refused_401()]
    p = process(tmp_path, monkeypatch, host, stanza("new"), name="new")
    with pytest.MonkeyPatch.context() as crash, pytest.raises(SystemExit):
        crash.setattr(FleetLease, "release", lambda *args, **kw: None)
        p._retrieve_pending()
    expire(host)
    process(tmp_path, monkeypatch, host, stanza("new"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 1, f"new password authorizes={len(wire.authorize)}"


def test_confirmed_refusal_under_live_claim_stops_sessions(tmp_path, monkeypatch, wire):
    """F2 (Codex): a holder that recorded a refusal and crashed before its release — a confirmed answer is observed
    at once, under a live claim too; a cadence need not outlast claim_seconds."""
    host = LeaseHost()
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    s = sessions(p, [T0])
    wire.answers = [login_302()]
    s.credential_for(p.settings.cluster("a"))
    other = FleetLease(host, "ns", USER, claim_seconds=3600, identity="other")
    other.claim()
    other.reserve("https://api.other.example", lease_digest(USER, PASSWORD, UID))
    other.refuse("https://api.other.example", lease_digest(USER, PASSWORD, UID), "login-refused")
    p._ping_accounts()
    assert s.view("a")["state"] == "suspended"


def test_new_claim_does_not_extend_old_uncertain_reservation(tmp_path, monkeypatch, wire):
    """F2 (Codex): an unanswered reservation is deferred inside its own attempt's window only; a later claim — a
    blocked lookup's, each cadence — does not make an attempt that ended long ago look under way."""
    host = LeaseHost()
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    s = sessions(p, [T0])
    wire.answers = [login_302()]
    s.credential_for(p.settings.cluster("a"))
    old = FleetLease(host, "ns", USER, claim_seconds=60, clock=lambda: T0)
    old.claim()
    old.reserve("https://api.example", lease_digest(USER, PASSWORD, UID))
    other = FleetLease(host, "ns", USER, claim_seconds=3600, identity="new-holder")
    other.claim()
    p._ping_accounts()
    assert s.view("a")["state"] == "suspended"


def test_revoke_of_old_session_scrubs_the_new_held_token(tmp_path, monkeypatch, wire, caplog):
    """F3 (Codex): a renewal revokes the old session after the new one is installed; the old login never saw the new
    token, so a revoke answer echoing it reached `fleet-logout-failed`."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600", token=TOKEN_2), login_302(token=TOKEN_3)]
    s.credential_for(p.settings.cluster("a"))
    wire.revoke = httpx.Response(500, text=f"remote echoes {TOKEN_3}")
    now[0] += timedelta(seconds=2700)
    with caplog.at_level(logging.INFO, logger="gsd"):
        assert s.credential_for(p.settings.cluster("a")) is not None
    assert any(m.startswith("fleet-logout-failed ") for m in caplog.messages)
    assert all(TOKEN_3 not in m for m in caplog.messages)


def test_a_suspension_scrubs_every_stopped_token_from_each_revoke(tmp_path, monkeypatch, wire, caplog):
    """F3's other half: a suspension pops every session on the account before it revokes any, so each revoke is told
    the whole batch — a remote echoing another stopped session's token is scrubbed too."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"), self_login("b"))
    s = sessions(p, now)
    wire.answers = [login_302(token=TOKEN_2), login_302(token=TOKEN_3)]
    s.credential_for(p.settings.cluster("a"))
    s.credential_for(p.settings.cluster("b"))
    wire.revoke = httpx.Response(500, text=f"remote echoes {TOKEN_2} and {TOKEN_3}")
    with caplog.at_level(logging.INFO, logger="gsd"):
        s.suspend_account(USER, PASSWORD, {"target": "https://api.a.example.com:6443", "code": "login-refused"})
    assert len(lines(caplog, "fleet-logout-failed")) == 2
    assert all(TOKEN_2 not in m and TOKEN_3 not in m for m in caplog.messages)


# ── OB2's composition review of Epic C (1.0.0): the ping among the other paths ───────────────────────

def test_the_ping_scrubs_the_token_it_holds_for_its_target_and_every_held_session(tmp_path, monkeypatch, wire, caplog):
    """The ping logs in on a cluster whose poller token this dashboard already stores, while self-login sessions are
    held: a remote echoing either reached the ping's login lines, the `fleet-ping-failed` line and the standing finding
    the API serves (OB2, Epic C composition review, K2). The password, the Basic form and a token the ping itself
    minted were already scrubbed; a token nobody holds must survive, since redaction is by value."""
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("s1"), discovered=[retrieved("r1")])
    s = sessions(p, now)
    wire.answers = [login_302(token=TOKEN_2), httpx.Response(500, text=f"echo {SA_TOKEN} and {TOKEN_2} and {TOKEN_3}")]
    assert s.credential_for(p.settings.cluster("s1")) is not None
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._ping_accounts()
    assert lines(caplog, "fleet-ping-failed"), "the echo was not met"
    for secret in (SA_TOKEN, TOKEN_2):
        assert all(secret not in m for m in caplog.messages), secret
        assert all(secret not in (f.detail or "") for f in p.settings.cluster_registry.findings()), secret
    assert any(TOKEN_3 in m for m in lines(caplog, "fleet-ping-failed")), "a token nobody holds was redacted"


@pytest.mark.parametrize("act", ["entry-removed-by-hand", "secret-recreated"])
def test_a_refusal_held_by_the_process_alone_stamps_no_ping_attempt(tmp_path, monkeypatch, wire, act):
    """§5 Q7's procedure and D2's recreation both end in a pod restart, because the running pod keeps its copy of the
    gate; until then the ping stands down WITHOUT recording an attempt — or the restarted pod waits out the whole
    interval, its `last_outcome` reading `login-refused` for a login never made (OB2, Epic C composition review, K7)."""
    host = LeaseHost()
    wire.answers = [refused_401()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="p")
    p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1 and PREFIX + "ping-last-attempt" not in host.leases.annotations()
    if act == "entry-removed-by-hand":
        obj = host.leases.objects[lease_name(USER)]
        obj["metadata"]["annotations"].pop(PREFIX + "refused")
        host.leases.serial += 1
        obj["metadata"]["resourceVersion"] = str(host.leases.serial)
    else:
        host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {
            "metadata": {"uid": "99999999-0000-4000-8000-000000000099"},
            "data": {"password": base64.b64encode(PASSWORD.encode()).decode()}}
    p._ping_accounts()
    assert len(wire.authorize) == 1, "the process's gate must hold until the restart"
    assert PREFIX + "ping-last-attempt" not in host.leases.annotations(), "an attempt stamped for a login never made"
    # The restart the procedure names, with the directory answering the password now: the first cadence pings.
    wire.answers = [login_302(), login_302()]
    q = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="q")
    q._retrieve_pending(); q._ping_accounts()
    assert host.leases.annotations()[PREFIX + "ping-last-outcome"] == "ok"
