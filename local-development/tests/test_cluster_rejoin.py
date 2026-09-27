"""Rejoin (#316, docs/specs/SPEC_D4_cluster_rejoin.md): `POST /api/clusterconfigs/{name}/rejoin` takes a cluster
administrator's own username and password for ONE login to the remote, asks the remote whether that person is a
cluster administrator there (D8), reads the poller's token Secret, revokes the login and writes gsd-cluster-<name>
here. The password is presented at most once per press, never retried, never stored, never presented as any other
account, and the fleet account is never used. The page's dialog is in tests/test_ui.py::TestClusterConfigPage.

The remote is S4b's fake target, which records every request in order (`presented` decodes each authorize's Basic
header, so every budget here counts the wire), plus D8's SelfSubjectAccessReview. The host is the tab's in-memory
namespace (`_Host`). No real account or password appears here: ADMIN is a made-up administrator, and USER the fleet
harness's own fleet account."""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import pathlib
import re
import sqlite3
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import (
    LOOKUP_ACCOUNT_ANNOTATION, MANAGED_BY_ANNOTATION, SOURCE_NAMESPACE_ANNOTATION, SOURCE_SERVICE_ACCOUNT_ANNOTATION,
    TOKEN_SOURCE_ANNOTATION,
)
from gsd.config import ClusterConfig
from gsd.fleetlookup import INVALID_SINCE_LABEL, CredentialGate
from test_clusterconfig import TOKEN as STORED_TOKEN, _secret
from test_clusterconfig_tab import NS, _Host
from test_fleet_lifecycle import LeaseHost, process, retrieved
from test_fleet_login import DISCOVERY_PATH, OAUTH, PASSWORD, TOKEN, USER, USER_TOKEN_API, down, login_302, refused_401
from test_fleet_lookup import SA_TOKEN, SOURCE, LookupTarget, sa_secret
from test_visibility import H, _MapResolver, _seed, _settings

REPO = pathlib.Path(__file__).resolve().parents[2]
#: The contract's own strings, written out rather than imported: a test that imported them would pass whatever they said.
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
REJOINED_BY_ANNOTATION = "groupsync-dashboard.io/rejoined-by"
REJOIN_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/rejoin-account"
REJOINED_AT_ANNOTATION = "groupsync-dashboard.io/rejoined-at"
ADMIN, ADMIN_PASSWORD = "alice.admin", "Adm1n-pw-7f3e9c"
BASIC = base64.b64encode(f"{ADMIN}:{ADMIN_PASSWORD}".encode()).decode()
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
ADMIN_REASON = 'RBAC: allowed by ClusterRoleBinding "cluster-admins" of ClusterRole "cluster-admin" to Group "admins"'


def review(allowed=True, reason: str | None = ADMIN_REASON, **status) -> httpx.Response:
    """The remote's SelfSubjectAccessReview answer, in the shape measured on the lab (SPEC_D4, Appendix A.3)."""
    body = {"allowed": allowed, **({"reason": reason} if reason else {}), **status}
    return httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "apiVersion": "authorization.k8s.io/v1",
                                     "metadata": {}, "status": body})


class RemoteTarget(LookupTarget):
    """S4b's fake target plus D8's review, answered from `review` (a Response, or a callable given the request)."""

    def __init__(self, *answers, review_answer=None, **kw):
        super().__init__(*answers, **kw)
        self.review = review() if review_answer is None else review_answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == SSAR_API:
            self.requests.append(request)
            return self._answer(self.review, request)
        return super().__call__(request)

    @property
    def reviews(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == SSAR_API]


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize request, in the order it reached the target."""
    out = []
    for request in target.authorize:
        user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
        out.append((user, password))
    return out


class _Poller:
    """The route's two needs from the poller: its one credential gate (#315) and the discovery wake."""

    def __init__(self):
        self._credential_gate = CredentialGate()
        self.woke = 0

    def request_discovery(self):
        self.woke += 1


@pytest.fixture
def remote(monkeypatch):
    """Every httpx.Client the login, the review and the read build goes to one fake target."""
    target = RemoteTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", "https://api.east.example:6443"),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


def _app(tmp_path, monkeypatch, host, *discovered, name="gsd", **kw):
    """One dashboard process: its own store, its own poller gate, `discovered` on its registry."""
    db = str(tmp_path / f"{name}.db"); _seed(db)
    settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True, **kw)
    settings.cluster_registry.namespace = NS
    settings.cluster_registry.replace(list(discovered), [], at="2026-09-27T14:00:00Z")
    monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
    monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.poller = _Poller()
    return app, settings


@pytest.fixture
def rig(tmp_path, monkeypatch, remote):
    host = _Host({"gsd-cluster-east": _secret(), "gsd-cluster-west": _secret("gsd-cluster-west", cluster="west",
                                                                           server="https://api.west.example:6443")})
    east = parse_secret(_secret(), host_name="c1")
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    app, settings = _app(tmp_path, monkeypatch, host, east, west)
    with TestClient(app) as c:
        yield c, app, settings, host, remote


def _rejoin(c, name="east", who="root", *, username=ADMIN, password=ADMIN_PASSWORD):
    return c.post(f"/api/clusterconfigs/{name}/rejoin", headers=H(who), json={"username": username, "password": password})


def _writes(host) -> list[tuple[str, str]]:
    return [call for call in host.calls if call[0] != "GET"]


# ── the exchange ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance(rig, caplog, monkeypatch):
    c, app, settings, host, remote = rig

    def never(*a, **kw):
        raise AssertionError("Rejoin entered the fleet account's lookup")
    monkeypatch.setattr("gsd.fleetlookup.lookup", never)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"outcome", "message", "at"} and body["outcome"] == "rejoined" and ISO.match(body["at"])
    assert "Signed in to east as alice.admin, who may update clusterrolebindings there" in body["message"]
    assert "the login was signed out" in body["message"]
    # the wire: discovery, ONE authorize as the person, D8 with the login's token, the read, the revoke
    order = [(q.method, q.url.path) for q in remote.requests]
    assert order[:4] == [("GET", DISCOVERY_PATH), ("GET", "/oauth/authorize"), ("POST", SSAR_API), ("GET", SOURCE)]
    assert len(order) == 5 and order[4][0] == "DELETE" and order[4][1].startswith(USER_TOKEN_API + "/")
    assert presented(remote) == [(ADMIN, ADMIN_PASSWORD)]
    assert remote.reviews[0].headers["authorization"] == f"Bearer {TOKEN}" == remote.reads[0].headers["authorization"]
    assert json.loads(remote.reviews[0].content) == {
        "apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": {"verb": "update", "resource": "clusterrolebindings",
                                        "group": "rbac.authorization.k8s.io"}}}
    # the host: updated in place with the person's provenance, and no lookup-account
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]
    assert [path for _, path in host.calls if "gsd-fleet-account" in path] == [], "the fleet password was read"
    stored = host.secrets["gsd-cluster-east"]
    assert json.loads(base64.b64decode(stored["data"]["config"])) == {"bearerToken": SA_TOKEN}
    assert stored["metadata"]["annotations"] == {
        TOKEN_SOURCE_ANNOTATION: "rejoin", SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
        SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        REJOINED_BY_ANNOTATION: "root", REJOIN_ACCOUNT_ANNOTATION: ADMIN, REJOINED_AT_ANNOTATION: body["at"]}
    assert app.state.poller.woke == 1, "a write wakes discovery, as every write in the tab does"
    # the lines: the login's own, marked as a Rejoin; the remote's answer, as D8 asks; the outcome
    assert any(m.startswith("fleet-login ") and "account=alice.admin" in m and "rejoin_by=root" in m for m in caplog.messages)
    assert any(m.startswith("cluster-rejoin-review cluster=east by=root account=alice.admin") and "allowed=true" in m
               and 'question="update clusterrolebindings"' in m and "cluster-admins" in m for m in caplog.messages)
    assert "cluster-rejoined cluster=east by=root account=alice.admin secret=gsd-cluster-east written=updated revoked=true" in caplog.text
    assert "cluster-secret-rotated secret=gsd-cluster-east namespace=ns cluster=east by=root" in caplog.text


def test_a_lookup_written_secret_rejoined_drops_lookup_account_and_keeps_who_made_it(rig):
    """A Secret the lookup wrote records the fleet account in `lookup-account`. Rejoin replaces the provenance and
    removes that key — the daily ping logs in as whatever account it names (#432) — and keeps `managed-by`."""
    c, app, settings, host, remote = rig
    written = _secret(); written["metadata"]["annotations"] = {
        MANAGED_BY_ANNOTATION: "sa-token-lookup", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
        SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator", SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        LOOKUP_ACCOUNT_ANNOTATION: USER}
    host.secrets["gsd-cluster-east"] = written
    assert _rejoin(c).json()["outcome"] == "rejoined"
    ann = host.secrets["gsd-cluster-east"]["metadata"]["annotations"]
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann and ann[MANAGED_BY_ANNOTATION] == "sa-token-lookup"
    assert ann[TOKEN_SOURCE_ANNOTATION] == "rejoin" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN


def test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own(tmp_path, monkeypatch, remote):
    """A values stanza whose lookup has not written its Secret yet (the fleet account locked, say): Rejoin creates
    gsd-cluster-rnd with the stanza's policy, `managed-by: ui`, and the person's provenance; discovery then counts it
    as the stanza's own (`owned_by_mode`), so it is no shadow and the stanza's policy is what is served."""
    rnd = ClusterConfig("rnd", "https://api.rnd.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER,
                        visibility="self-only", identity="none")
    host = _Host({})
    app, settings = _app(tmp_path, monkeypatch, host)
    settings.clusters.append(rnd)
    with TestClient(app) as c:
        r = _rejoin(c, "rnd")
    assert r.status_code == 200 and r.json()["outcome"] == "rejoined", r.text
    assert _writes(host) == [("POST", f"/api/v1/namespaces/{NS}/secrets")]
    stored = host.secrets["gsd-cluster-rnd"]
    ann = stored["metadata"]["annotations"]
    assert ann[MANAGED_BY_ANNOTATION] == "ui" and ann[TOKEN_SOURCE_ANNOTATION] == "rejoin"
    assert ann[REJOINED_BY_ANNOTATION] == "root" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann
    data = {k: base64.b64decode(v).decode() for k, v in stored["data"].items()}
    assert (data["visibility"], data["identity"]) == ("self-only", "none")
    clusters, findings = discover(None, NS, host_name="c1", values_names=("c1", "c2", "rnd"),
                                  values_modes={"rnd": "remote-lookup"}, items=[stored])
    assert [f.code for f in findings] == [], "the rejoined Secret over its own stanza is no shadow"
    settings.cluster_registry.replace(clusters, findings, at="2026-09-27T14:05:00Z")
    served = settings.cluster("rnd")
    assert served.credential_kind == "bearer" and served.token_source == "rejoin" and served.lookup_account is None
    assert (served.visibility, served.identity) == ("self-only", "none"), "the stanza's policy, not the Secret's own"


def test_the_daily_ping_never_logs_in_as_the_person_who_rejoined(rig, tmp_path, monkeypatch):
    """#432, read forward: the ping logs in as whatever account a retrieved Secret's `lookup-account` names, WITH THE
    FLEET PASSWORD. Had Rejoin written the person there, the ping would present the fleet password as the person —
    a refused login counted against their directory entry, once a day. It writes `rejoin-account` instead."""
    c, app, settings, host, remote = rig
    assert _rejoin(c).json()["outcome"] == "rejoined"
    rejoined, findings = discover(None, NS, host_name="c1", items=[host.secrets["gsd-cluster-east"]])
    assert findings == [] and rejoined[0].token_source == "rejoin"
    remote.answers = [login_302()] * 4
    start = len(remote.authorize)
    lease_host = LeaseHost()
    lease_host.rotate(PASSWORD)
    fleet = process(tmp_path, monkeypatch, lease_host, discovered=[*rejoined, retrieved("shared-rnd")],
                    fleet_account_username=USER)
    fleet._ping_accounts()
    assert presented(remote)[start:] == [(USER, PASSWORD)], "the ping presented the fleet password as someone else"


# ── the route's refusals: nothing is sent, and no value is repeated ─────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    f'"{ADMIN_PASSWORD}"',                                                        # a JSON string: a typed body quoted it whole
    f'["{ADMIN}", "{ADMIN_PASSWORD}"]',
    "12345",
    "",                                                                           # no body at all
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}", "token": "x"}}',  # a key the contract does not know
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}", "{ADMIN_PASSWORD}": "x"}}',  # a key that IS the password
    f'{{"username": "{ADMIN}", "password": 12345}}',
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}"',                  # not JSON
], ids=["string", "list", "number", "empty", "unknown-key", "password-as-key", "not-a-string", "malformed"])
def test_the_body_is_username_and_password_and_nothing_else(rig, raw):
    c, app, settings, host, remote = rig
    r = c.post("/api/clusterconfigs/east/rejoin", headers={**H("root"), "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422, r.text
    assert ADMIN_PASSWORD not in r.text and remote.requests == [] and _writes(host) == []


@pytest.mark.parametrize("name,username,password,status,code", [
    ("c1", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # the host: the pod's own ServiceAccount
    ("c2", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a values entry with its own credential
    ("sl", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a Secret declaring userSelfLogin
    ("cm", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # generated from a ConfigMap
    ("east", "alice:admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),   # RFC 7617: no colon in a user-id
    ("east", "alice admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),
    ("east", "SVC-GSD-Fleet\n", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),  # a final newline: refused by the grammar (#438)
    ("east", "SVC-GSD-Fleet", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),    # the chart's fleet account, any case
    ("east", "stanza-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # a stanza's ldapConnectionBootstrap
    ("east", "recorded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"), # a Secret's lookup-account
    ("east", "padded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # one recorded with a final newline
    ("east", ADMIN, "", 422, "rejoin-password-missing"),
    ("east", ADMIN, "Adm1n-pw\nsecond-line", 422, "rejoin-password-invalid"),  # RFC 7617: no control characters
    ("east", ADMIN, "Adm1n-pw-\ud800", 422, "rejoin-password-invalid"),        # not encodable: an unpaired surrogate
])
def test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value(tmp_path, monkeypatch, remote, name, username,
                                                                          password, status, code):
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    discovered = [parse_secret(_secret(), host_name="c1"),
                  ClusterConfig("sl", "https://api.sl.example:6443", user_self_login=True, ldap_connection_bootstrap="svc-sl",
                                source="secret:gsd-cluster-sl"),
                  dataclasses.replace(west, name="cm", source="secret:gsd-cluster-cm", onboarding=("fleet", "uid-1", "0" * 64)),
                  dataclasses.replace(west, name="rec", source="secret:gsd-cluster-rec", token_source="remote-lookup",
                                      lookup_account="recorded-account"),
                  dataclasses.replace(west, name="pad", source="secret:gsd-cluster-pad", token_source="remote-lookup",
                                      lookup_account="padded-account\n")]
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, *discovered, fleet_account_username=USER)
    settings.clusters.append(ClusterConfig("st", "https://api.st.example:6443", sa_token_lookup=True,
                                           ldap_connection_bootstrap="stanza-account"))
    with TestClient(app) as c:
        r = c.post(f"/api/clusterconfigs/{name}/rejoin", headers={**H("root"), "Content-Type": "application/json"},
                   content=json.dumps({"username": username, "password": password}))
    assert r.status_code == status and r.json()["detail"].startswith(f"{code}: "), r.text
    assert remote.requests == [] and _writes(host) == []
    if code.startswith("rejoin-"):
        assert username not in r.text and (not password or password not in r.text), "a refusal repeats no value"
    gate = app.state.poller._credential_gate
    assert gate._refused == {} and gate._spent == set(), "a refusal before the wire records nothing"


def test_below_the_cluster_admin_tier_is_403_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    assert _rejoin(c, who="auditor").status_code == 403       # the wide tier, not the cluster-admin tier
    assert c.post("/api/clusterconfigs/east/rejoin", json={"username": ADMIN, "password": ADMIN_PASSWORD}).status_code == 403
    assert remote.requests == [] and _writes(host) == []


def test_an_unknown_or_retired_name_is_404_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    app.state.store.upsert_cluster("gone", "https://api.gone:6443", False)
    for name in ("nope", "gone"):
        r = _rejoin(c, name)
        assert r.status_code == 404 and name in r.json()["detail"], r.text
    assert remote.requests == []


def test_no_poller_means_no_gate_and_no_login(rig):
    c, app, settings, host, remote = rig
    app.state.poller = None
    r = _rejoin(c)
    assert r.status_code == 409 and "nothing was sent" in r.json()["detail"] and remote.requests == []


def test_with_the_writes_switch_off_the_route_does_not_exist(tmp_path):
    db = str(tmp_path / "off.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        assert c.post("/api/clusterconfigs/c1/rejoin", headers=H("root"), json={}).status_code in (404, 405)
    assert "/api/clusterconfigs/{name}/rejoin" not in app.openapi()["paths"]


# ── the gate: once the password is on the wire, the outcome is terminal (#283, #315) ─────────────────────────

@pytest.mark.parametrize("answer,first", [
    (refused_401, "login-refused"),
    (lambda: httpx.Response(500, text="Internal Server Error"), "login-failed"),    # a LOCKED account's LDAP code 19
    (lambda: (lambda request: httpx.ReadTimeout("timed out")), "login-failed"),     # written, then no answer
], ids=["401", "500", "read-timeout"])
def test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again(rig, answer, first):
    c, app, settings, host, remote = rig
    remote.answers = [answer(), login_302()]
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == first and len(remote.authorize) == 1
    assert "it is not sent again" in r1.json()["message"]
    r2 = _rejoin(c, "west")                                  # another cluster: the gate is the ACCOUNT's (#315)
    assert r2.json()["outcome"] == "login-refused" and "so it was not sent" in r2.json()["message"]
    assert len(remote.authorize) == 1, "the same password reached the directory twice"
    r3 = _rejoin(c, password="Adm1n-pw-corrected")          # a different password is a different entry
    assert r3.json()["outcome"] == "rejoined" and len(remote.authorize) == 2
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]


def test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated(rig):
    """ONE_TRY: the fleet's schedule retries a failure that bound nothing; a person is waiting, so it is answered at
    once, and the password is free to be sent on the next press."""
    c, app, settings, host, remote = rig
    remote.discovery = down
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == "login-failed" and "the password was not sent" in r1.json()["message"]
    assert [q.url.path for q in remote.requests] == [DISCOVERY_PATH], "one attempt, no retry"
    remote.discovery = {"issuer": OAUTH, "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
    assert _rejoin(c).json()["outcome"] == "rejoined" and presented(remote) == [(ADMIN, ADMIN_PASSWORD)]


# ── D8: the remote decides, with the login's own token ─────────────────────────────────────────────────────────

def test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked(rig, caplog):
    c, app, settings, host, remote = rig
    remote.review = review(allowed=False, reason=None)
    with caplog.at_level(logging.INFO):
        r = _rejoin(c)
    body = r.json()
    assert body["outcome"] == "not-cluster-admin" and "east says alice.admin may not update clusterrolebindings" in body["message"]
    assert "the login was signed out" in body["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1
    assert "cluster-rejoin-review cluster=east by=root account=alice.admin" in caplog.text and "allowed=false" in caplog.text
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None, "the password was right"


@pytest.mark.parametrize("answer", [
    httpx.Response(403, text="forbidden"),
    httpx.Response(500, text="Internal Server Error"),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {}}),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {"allowed": "true"}}),
    lambda request: httpx.ReadTimeout("timed out"),
], ids=["403", "500", "no-status", "string-true", "timeout"])
def test_a_review_that_does_not_answer_is_a_refusal_never_a_yes(rig, answer):
    c, app, settings, host, remote = rig
    remote.review = answer
    r = _rejoin(c)
    assert r.json()["outcome"] == "access-review-failed" and "could not be asked" in r.json()["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1


def test_the_review_asks_the_configured_cluster_admin_question(tmp_path, monkeypatch, remote):
    """#322's question is configurable (visibility.clusterAdminSar); the remote is asked the host's own question."""
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"),
                         visibility_cluster_admin_sar_verb="get", visibility_cluster_admin_sar_resource="secrets",
                         visibility_cluster_admin_sar_api_group="", visibility_cluster_admin_sar_namespace="group-sync-operator")
    with TestClient(app) as c:
        r = _rejoin(c)
    assert json.loads(remote.reviews[0].content)["spec"]["resourceAttributes"] == {
        "verb": "get", "resource": "secrets", "group": "", "namespace": "group-sync-operator"}
    assert "may get secrets in namespace group-sync-operator there" in r.json()["message"]


# ── the read, the write, and one Rejoin at a time ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("secret,code", [
    (httpx.Response(404, text="not found"), "sa-token-secret-missing"),
    (httpx.Response(403, text="forbidden"), "sa-token-unreadable"),
    (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "2027-09-22"})), "sa-token-invalidated"),
])
def test_a_token_read_refusal_writes_nothing_and_revokes_the_login(rig, secret, code):
    c, app, settings, host, remote = rig
    remote.secret = secret
    r = _rejoin(c)
    assert r.json()["outcome"] == code and "nothing was written" in r.json()["message"]
    assert _writes(host) == [] and len(remote.revokes) == 1
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None


def test_a_refused_write_stores_nothing_and_says_so(rig):
    c, app, settings, host, remote = rig
    host.refuse = True
    r = _rejoin(c)
    assert r.json()["outcome"] == "lookup-write-failed" and "nothing was stored" in r.json()["message"]
    assert json.loads(base64.b64decode(host.secrets["gsd-cluster-east"]["data"]["config"])) == {"bearerToken": STORED_TOKEN}


def test_one_rejoin_at_a_time_in_this_process(rig):
    """A second press — the other tab, a script, another cluster — while the first is out is refused, never queued:
    the gate's check and the login it guards are one step, so no two presses reach a password's first use."""
    c, app, settings, host, remote = rig
    inside, release, answers = threading.Event(), threading.Event(), {}

    def slow(request):
        inside.set()
        release.wait(10)
        return login_302()

    remote.answers = [slow]
    first = threading.Thread(target=lambda: answers.setdefault("first", _rejoin(c)))
    first.start()
    try:
        assert inside.wait(10), "the first login started"
        answers["second"] = _rejoin(c, "west")
    finally:
        release.set()
        first.join(10)
    assert answers["second"].status_code == 409 and "already in flight" in answers["second"].json()["detail"]
    assert answers["first"].json()["outcome"] == "rejoined" and len(remote.authorize) == 1
    remote.answers = [login_302()]
    assert _rejoin(c, "west").json()["outcome"] == "rejoined", "the slot is released when the Rejoin ends"


# ── the redaction pin (#283's, carried): the password is on one header of one request, and nowhere else ─────

def _planted(target_kind: str) -> dict:
    """One scenario's remote, with every secret in play at that point planted in every field it controls: the
    password and its Basic form from the authorize on, the login's token from the 302 on, the token read from the
    read on. A value the dashboard has not been handed yet is not its secret to scrub, and is not planted."""
    login = f"pw={ADMIN_PASSWORD} basic={BASIC}"
    session = f"{login} bearer={TOKEN}"
    read = f"{session} sa={SA_TOKEN}"
    return {
        "401": dict(answers=[refused_401(body=login)]),
        "401-challenge": dict(answers=[httpx.Response(401, headers={"Www-Authenticate": f'Basic realm="{ADMIN_PASSWORD}"'})]),
        "500": dict(answers=[httpx.Response(500, text=login)]),
        "302-error": dict(answers=[httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error={ADMIN_PASSWORD}"})]),
        "issuer": dict(discovery={"issuer": f"https://{ADMIN}:{ADMIN_PASSWORD}@oauth.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}),
        "review-reason": dict(review_answer=review(reason=session, evaluationError=session)),
        "review-denied": dict(review_answer=review(allowed=False, reason=session)),
        "review-500": dict(review_answer=httpx.Response(500, text=session)),
        "read-500": dict(secret=httpx.Response(500, text=session)),
        "read-owner": dict(secret=httpx.Response(200, json=sa_secret(sa=read))),
        "revoke-500": dict(revoke=httpx.Response(500, text=read)),
        # the read is refused AFTER the token was decoded, then the revoke fails echoing it (review of the spec, C3)
        "read-refused-revoke-500": dict(secret=httpx.Response(200, json=sa_secret(sa="wrong-owner")),
                                        revoke=httpx.Response(500, text=read)),
        "write-echo": dict(host_echo=True),
        "success": {},
    }[target_kind]


@pytest.mark.parametrize("kind", ["401", "401-challenge", "500", "302-error", "issuer", "review-reason", "review-denied",
                                  "review-500", "read-500", "read-owner", "revoke-500", "read-refused-revoke-500",
                                  "write-echo", "success"])
def test_the_password_appears_on_one_header_and_nowhere_else(tmp_path, monkeypatch, remote, caplog, kind):
    """The scrub is for accidental echoes: a remote, a proxy's error page or a debug handler that quotes what it got,
    as written or as Python's or Go's JSON encoder writes it, up to two layers (SPEC_D4 §3.7 lists the set). A hostile
    remote already holds the password and can pick an encoding nothing recognises; that is stated, not claimed (§6)."""
    scenario = _planted(kind)
    for field in ("answers", "discovery", "secret", "revoke"):
        if field in scenario:
            setattr(remote, field, scenario[field])
    remote.review = scenario.get("review_answer", remote.review)
    host = _Host({"gsd-cluster-east": _secret()}, echo=scenario.get("host_echo", False))
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"))
    with caplog.at_level(logging.DEBUG), TestClient(app) as c:
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    gate = app.state.poller._credential_gate
    kept = "\n".join([r.text, caplog.text, json.dumps(host.secrets), repr(gate._refused), repr(gate._spent),
                      json.dumps([f.public() for f in settings.cluster_registry.findings()]),
                      "\n".join(sqlite3.connect(settings.db_path).iterdump())])
    for value in (ADMIN_PASSWORD, BASIC, TOKEN):
        assert value not in kept, f"{kind}: a secret was kept or echoed"
    assert SA_TOKEN not in kept.replace(json.dumps(host.secrets), ""), f"{kind}: the token read was echoed"
    for request in remote.requests:                        # on the wire: the authorize's Basic header, once
        seen = f"{request.url} {request.content!r} " + " ".join(f"{k}={v}" for k, v in request.headers.items()
                                                                if not (request.url.path == "/oauth/authorize" and k == "authorization"))
        assert ADMIN_PASSWORD not in seen and BASIC not in seen, (kind, request.method, request.url.path)
    assert len(remote.authorize) <= 1


@pytest.mark.parametrize("answer", [review(reason="remote echo: xyZ"), review(allowed=False, reason="remote echo: xyZ"),
                                    httpx.Response(500, text="remote echo: xyZ")], ids=["allowed", "denied", "review-500"])
def test_short_password_echo_in_review_is_not_logged(rig, caplog, answer):
    """The emit helper skips a secret under four characters, and a password can be that short: D8's text is
    scrubbed before any line, whatever the length (review of the spec, C3)."""
    c, app, settings, host, remote = rig
    remote.review = answer
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password="xyZ")
    assert r.status_code == 200 and "xyZ" not in caplog.text + r.text


def _escaped(value: str, layers: int) -> str:
    for _ in range(layers):
        value = json.dumps(value)[1:-1]
    return value


def _echo(remote, phase: str, text: str) -> None:
    """Plant `text` in the free text the remote answers with at `phase`: a review's reason, or a 500's body."""
    if phase in ("allowed", "denied"):
        remote.review = review(allowed=phase == "allowed", reason=text)
    elif phase == "review-500":
        remote.review = httpx.Response(500, text=text)
    elif phase == "login-500":
        remote.answers = [httpx.Response(500, text=text)]
    else:
        remote.revoke = httpx.Response(500, text=text)


PHASES = ["allowed", "denied", "review-500", "login-500", "revoke-500"]


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("password", ['x"Z', "éZ"])
@pytest.mark.parametrize("layers", [1, 2])
def test_short_escaped_password_never_reaches_evidence(rig, caplog, phase, password, layers):
    """A remote may quote the password JSON-escaped, once or twice, so a quote or a non-ASCII letter changes its
    spelling. The shared escaped-form scrub stops at eight characters; Rejoin removes every spelling at any length
    (review round 1, P1)."""
    c, app, settings, host, remote = rig
    escaped = _escaped(password, layers)
    _echo(remote, phase, "remote echo: " + escaped)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password=password)
    assert r.status_code == 200
    shown = caplog.text + r.json()["message"]
    assert escaped not in shown and password not in shown
    assert escaped.replace('"', "'") not in caplog.text   # a line's value has its double quotes turned single


#: Go's encoding/json.Marshal of each password, once and twice, as the Go runtime wrote them (review round 3, Codex's
#: go-spellings.json): `<`, `>`, `&`, U+2028 and U+2029 as lower-case `\\u` escapes, every other character as is.
GO_SPELLINGS = [
    ("lt", "x<Z", "x\\u003cZ", "x\\\\u003cZ"),
    ("gt", "x>Z", "x\\u003eZ", "x\\\\u003eZ"),
    ("amp", "x&Z", "x\\u0026Z", "x\\\\u0026Z"),
    ("e-lt", "é<Z", "é\\u003cZ", "é\\\\u003cZ"),
    ("e-2028", "é\u2028Z", "é\\u2028Z", "é\\\\u2028Z"),
    ("emoji", "x😀Z", "x😀Z", "x😀Z"),
]


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("password,spelled", [
    pytest.param("x/Z", "x\\/Z", id="slash"),         # `/` as `\/`, which some encoders write
    pytest.param("éZ", "\\u00E9Z", id="hex-case"),    # `\u` hex in upper case, which other encoders write
    *(pytest.param(password, spelled, id=f"go-{name}-{layer}") for name, password, *spelled_by_layer in GO_SPELLINGS
      for layer, spelled in zip(("once", "twice"), spelled_by_layer)),
    pytest.param('x"Z', _escaped('x"Z', 3), id="triple", marks=pytest.mark.xfail(strict=True, reason=(
        "a stated residual (SPEC_D4 §6): three layers of escaping are no accidental echo, and the scrub covers two"))),
])
def test_other_json_spellings_never_reach_evidence(rig, caplog, phase, password, spelled):
    """Real JSON encoders also write `/` as `\\/` and `\\u` hex in upper case (review round 2), and Go's, the remote's
    own, escapes five characters and leaves the rest as is (round 3). Three layers are left, stated: a hostile remote
    holds the password anyway."""
    c, app, settings, host, remote = rig
    _echo(remote, phase, "remote echo: " + spelled)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password=password)
    shown = caplog.text + r.json()["message"]
    assert r.status_code == 200 and spelled not in shown and password not in shown
    assert spelled.replace('"', "'") not in caplog.text


@pytest.mark.parametrize("spelled", [_escaped('x"Z', 1), 'x"Z'], ids=["escaped", "raw"])
def test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment(rig, caplog, spelled):
    """D8's client quotes a failed answer's body cut at 200 characters. A password straddling the cut left a fragment
    no later scrub could recognise, so every spelling is removed before the cut (review round 2)."""
    c, app, settings, host, remote = rig
    remote.review = httpx.Response(500, text="Q" * 198 + spelled)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password='x"Z')
    fragment = "Q" * 198 + spelled[:2]
    shown = caplog.text + r.json()["message"]
    assert r.status_code == 200 and fragment not in shown and fragment.replace('"', "'") not in caplog.text


@pytest.mark.parametrize("phase", ["review", "store"])
@pytest.mark.parametrize("revoke_status", [200, 500])
def test_unexpected_error_still_reports_cleanup(rig, monkeypatch, caplog, phase, revoke_status):
    """An unexpected error after the login exists still says how the login ended: signed out, or the token to delete
    (review round 1, P2). The error's own words never appear."""
    c, app, settings, host, remote = rig

    def explode(*args, **kwargs):
        raise RuntimeError(ADMIN_PASSWORD)
    monkeypatch.setattr("gsd.rejoin." + ("remote_says_cluster_admin" if phase == "review" else "store"), explode)
    remote.revoke = httpx.Response(revoke_status, text="answer")
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c)
    message = r.json()["message"]
    assert r.json()["outcome"] == "rejoin-failed" and len(remote.revokes) == 1
    if revoke_status == 500:
        assert "could NOT be signed out" in message and "oc delete useroauthaccesstokens" in message
    else:
        assert "the login was signed out" in message
    assert ADMIN_PASSWORD not in r.text + caplog.text


@pytest.mark.parametrize("where", ["remote_says_cluster_admin", "RejoinLogin"])
def test_unexpected_exception_cannot_escape_with_secrets(rig, monkeypatch, caplog, where):
    """An error the design did not expect may quote the password. It never leaves the route, so the server has no
    traceback to print: the answer and the line are fixed text. Inside the exchange Rejoin answers it and the login is
    still revoked; before a login exists the route does (review, C3; round 1, P2)."""
    c, app, settings, host, remote = rig

    def explode(*args, **kwargs):
        raise RuntimeError(f"{ADMIN_PASSWORD} {BASIC} {TOKEN}")
    monkeypatch.setattr(f"gsd.rejoin.{where}", explode)
    with caplog.at_level(logging.DEBUG):
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/clusterconfigs/east/rejoin", headers=H("root"), json={"username": ADMIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200 and r.json()["outcome"] == "rejoin-failed", r.text
    assert all(secret not in r.text + caplog.text for secret in (ADMIN_PASSWORD, BASIC, TOKEN))
    assert len(remote.revokes) == (where == "remote_says_cluster_admin") and _writes(host) == []


def test_dialog_does_not_promise_to_control_password_managers():
    """The dialog says what the dashboard controls and nothing more (review of the spec, C3): the HTML Standard lets
    a browser override autocomplete="off", and the Secret records the username. It says the gate's scope (D4-7)."""
    page = (REPO / "local-development/gsd/static/index.html").read_text()
    start = page.index('<dialog id="rejoin-dialog"')
    dialog = " ".join(page[start:page.index("</dialog>", start)].split())   # the source wraps its sentences
    assert "password managers may ignore" in dialog
    assert "Secret records your username" in dialog
    assert "Your username and password are used for this one login and are not stored" not in dialog
    assert "A restarted pod or another replica" in dialog


# ── the budget over the system ───────────────────────────────────────────────────────────────────────────────

#: SPEC_D4 §2's rows: (the remote's answers in order, the presses as (process, password)). A new process name is a
#: restart or a second replica: its own poller gate, over the same host and remote.
OTHER = "https://elsewhere.example"


def _moved(status: int, host: str) -> httpx.Response:
    """An authorize answered by a redirect that carries no token: the password was sent, and no session came back."""
    return httpx.Response(status, headers={"Location": f"{host}/oauth/token/implicit#error=access_denied"})


BUDGET = {
    "one press, the right password": ([login_302()], [("p", ADMIN_PASSWORD)]),
    "two presses, the right password": ([login_302(), login_302()], [("p", ADMIN_PASSWORD)] * 2),
    "a 401, then the same password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-1")] * 2),
    "a 500 (a locked account), then the same password": ([httpx.Response(500), login_302()], [("p", "L0cked-pw-1")] * 2),
    "a timeout after the password was sent, then the same": (
        [lambda request: httpx.ReadTimeout("timed out"), login_302()], [("p", "T1meout-pw-1")] * 2),
    "a 401, then the right password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-2"), ("p", ADMIN_PASSWORD)]),
    "a 401, then the same password on a restarted process": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-3"), ("restarted", "Wr0ng-pw-3")]),
    "a 401, then the same password on a second replica": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-4"), ("replica", "Wr0ng-pw-4")]),
    "a 302 without a token, then the same": ([_moved(302, OAUTH), login_302()], [("p", "N0-token-pw-1")] * 2),
    "a 302 to another host, then the same": ([_moved(302, OTHER), login_302()], [("p", "N0-token-pw-2")] * 2),
    "a 307 to another host, then the same": ([_moved(307, OTHER), login_302()], [("p", "N0-token-pw-3")] * 2),
    "a proxy replaying a successful press to another pod": (
        [login_302(), login_302()], [("p", ADMIN_PASSWORD), ("replica", ADMIN_PASSWORD)]),
}


def test_the_budget_over_the_system(tmp_path, monkeypatch, remote):
    """SPEC_D4 §2's table, measured: authorize requests on the wire for each shape. One press presents the password
    at most once, and a password the directory answered is not presented again by that process. A restart, a second
    replica and a replay to another pod each meet an empty gate: the stated scope (D4-7)."""
    host = _Host({"gsd-cluster-east": _secret()})
    east = parse_secret(_secret(), host_name="c1")
    measured = {}
    for n, (shape, (answers, presses)) in enumerate(BUDGET.items()):
        remote.requests.clear()
        remote.answers = list(answers)
        outcomes, clients = [], {}
        for process_name, password in presses:
            if process_name not in clients:
                app, _ = _app(tmp_path, monkeypatch, host, east, name=f"budget-{n}-{process_name}")
                clients[process_name] = TestClient(app).__enter__()
            outcomes.append(_rejoin(clients[process_name], password=password).json()["outcome"])
        for client in clients.values():
            client.__exit__(None, None, None)
        measured[shape] = (len(remote.authorize), outcomes)
    assert measured == {
        "one press, the right password": (1, ["rejoined"]),
        "two presses, the right password": (2, ["rejoined", "rejoined"]),
        "a 401, then the same password": (1, ["login-refused", "login-refused"]),
        "a 500 (a locked account), then the same password": (1, ["login-failed", "login-refused"]),
        "a timeout after the password was sent, then the same": (1, ["login-failed", "login-refused"]),
        "a 401, then the right password": (2, ["login-refused", "rejoined"]),
        "a 401, then the same password on a restarted process": (2, ["login-refused", "login-refused"]),
        "a 401, then the same password on a second replica": (2, ["login-refused", "login-refused"]),
        "a 302 without a token, then the same": (1, ["login-failed", "login-refused"]),
        "a 302 to another host, then the same": (1, ["login-failed", "login-refused"]),
        "a 307 to another host, then the same": (1, ["login-failed", "login-refused"]),
        "a proxy replaying a successful press to another pod": (2, ["rejoined", "rejoined"]),
    }, measured


# ── the runbook (the 2026-09-23 requirement) ───────────────────────────────────────────────────────────────

def test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it():
    runbook = REPO / "charts/group-sync-dashboard/RUNBOOK.md"
    headings = re.findall(r"^## (\d)\. ", runbook.read_text(), re.M)
    assert headings == ["1", "2", "3", "4", "5", "6"], headings
    assert "../charts/group-sync-dashboard/RUNBOOK.md" in (REPO / "docs/README.md").read_text()
    assert "(RUNBOOK.md)" in (REPO / "charts/group-sync-dashboard/README.md").read_text()
    credentials = (REPO / "charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md").read_text()
    assert "Rejoin **PLANNED**" not in credentials and "(RUNBOOK.md)" in credentials
