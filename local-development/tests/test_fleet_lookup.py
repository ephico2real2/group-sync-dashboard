"""#284 (SPEC_S4b): the saTokenLookup lookup against a fake target and a fake host — a login as the
fleet account, one GET of the poller ServiceAccount's token Secret by name, the values handed to the
shipped writer, and the session revoked on every path. R1 the loop end to end; R2 the write follows the
declaration (create for a stanza, in place for a Secret); R3 the target's Secret is checked before it is
stored; R4 a refused password is gated; R5 a trust failure names its host; R6 the schedule; R7 no
credential reaches a line."""

from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

import gsd.fleetlookup as fleetlookup
from gsd.clusterconfig import FINDING_CODES
from gsd.clusterconfig.parser import Finding
from gsd.clusterconfig.writer import (
    LOOKUP_ACCOUNT_ANNOTATION, MANAGED_BY_ANNOTATION, MANAGED_BY_LOOKUP, SOURCE_NAMESPACE_ANNOTATION,
    SOURCE_SERVICE_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION,
)
from gsd.config import ClusterConfig, Settings
from gsd.fleetlogin import USER_TOKEN_API
from gsd.fleetlookup import CODES, INVALID_SINCE_LABEL, LAST_USED_LABEL, CredentialGate, LookupRefused, lookup
from gsd.kube import ClusterClient, ClusterError
from test_fleet_login import (
    API, DISCOVERY_PATH, PASSWORD, TOKEN, USER, Target, _pki, _require_openssl, down, login_302, refused_401,
)

SA_TOKEN = "eyJhbGciOiJSUzI1NiJ9.sa-token-that-must-never-reach-a-log.sig"
SOURCE = "/api/v1/namespaces/group-sync-operator/secrets/group-sync-dashboard-cluster-poller-token"


def sa_secret(token: str = SA_TOKEN, sa: str = "group-sync-dashboard-cluster-poller", labels: dict | None = None,
              type_: str = "kubernetes.io/service-account-token") -> dict:
    """The lab's poller token Secret, as the API server answers it (SPEC_S4b §2)."""
    return {"metadata": {"name": "group-sync-dashboard-cluster-poller-token", "namespace": "group-sync-operator",
                         "labels": {LAST_USED_LABEL: "2026-09-22", **(labels or {})},
                         "annotations": {"kubernetes.io/service-account.name": sa}},
            "type": type_, "data": {"token": base64.b64encode(token.encode()).decode(), "ca.crt": "Y2E="}}


class LookupTarget(Target):
    """S4a's fake target, plus the token Secret the session reads (a Response, or an exception)."""

    def __init__(self, *answers, secret=None, **kw):
        super().__init__(*answers, **kw)
        self.secret = httpx.Response(200, json=sa_secret()) if secret is None else secret

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == SOURCE:
            self.requests.append(request)
            return self._answer(self.secret, request)
        return super().__call__(request)

    @property
    def reads(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == SOURCE]


class FakeHost(ClusterClient):
    """The LOCAL cluster: the fleet password Secret and the cluster Secrets, with every write kept."""

    def __init__(self, secrets: dict[str, dict] | None = None):
        super().__init__(ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"))
        self.secrets = {"/api/v1/namespaces/ns/secrets/gsd-fleet-account":
                        {"data": {"password": base64.b64encode(PASSWORD.encode()).decode()}}, **(secrets or {})}
        self.writes: list[tuple[str, str, dict]] = []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _client(self): return self._Ctx()

    def _get(self, client, path, params):
        if path not in self.secrets:
            raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")
        return self.secrets[path]

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.writes.append((method, path, json))
        if method == "POST":
            self.secrets[f"{path}/{json['metadata']['name']}"] = json
        return None


def settings(*clusters: ClusterConfig, writes: bool = True) -> Settings:
    return Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                    db_path=":memory:", cluster_secrets_writes_enabled=writes)


@pytest.fixture
def wire(monkeypatch):
    """Every httpx.Client the module builds — the login's and the read's — goes to the fake target."""
    target = LookupTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", API),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


RND = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER)


def run(cluster: ClusterConfig, host: FakeHost | None = None, *, write: bool = True, gate=None, s: Settings | None = None):
    host = host or FakeHost()
    result = lookup(cluster, s or settings(cluster), host, own_namespace="ns", gate=gate or CredentialGate(),
                    write=write, sleep=lambda _: None)
    return result, host


# ── R1 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheLoop:
    def test_a_stanza_becomes_a_labelled_secret_with_the_lookups_values(self, wire):
        result, host = run(RND)
        wire_order = [(r.method, r.url.path) for r in wire.requests]
        assert wire_order[:3] == [("GET", DISCOVERY_PATH), ("GET", "/oauth/authorize"), ("GET", SOURCE)]
        assert len(wire_order) == 4 and wire_order[3][0] == "DELETE" and wire_order[3][1].startswith(USER_TOKEN_API + "/")
        assert wire.reads[0].headers["authorization"] == f"Bearer {TOKEN}", "the read is the session's, not the SA token's"
        (method, path, obj), = host.writes
        assert (method, path, obj["metadata"]["name"]) == ("POST", "/api/v1/namespaces/ns/secrets", "gsd-cluster-rnd")
        assert obj["metadata"]["labels"] == {"groupsync-dashboard.io/secret-type": "cluster"}, "stamped by secret_object()"
        assert obj["metadata"]["annotations"] == {
            MANAGED_BY_ANNOTATION: MANAGED_BY_LOOKUP, TOKEN_SOURCE_ANNOTATION: "remote-lookup",
            SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
            SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller", LOOKUP_ACCOUNT_ANNOTATION: USER}
        config = json.loads(obj["stringData"]["config"])
        assert config == {"tlsClientConfig": {"insecure": False}, "bearerToken": SA_TOKEN}, "the declaration's trust, no caData"
        assert obj["stringData"]["visibility"] == "self-only" and obj["stringData"]["identity"] == "none"
        assert result.written == "created" and result.sa_token.last_used == "2026-09-22"
        assert len(wire.revokes) == 1, "the login's token is revoked; the stored one is the target's"
        assert set(result.secrets) == {PASSWORD, TOKEN, SA_TOKEN}

    def test_write_false_is_the_ping_the_same_read_and_nothing_stored(self, wire):
        result, host = run(RND, write=False)
        assert result.written is None and result.sa_token.token == SA_TOKEN and host.writes == []
        assert len(wire.reads) == 1 and len(wire.revokes) == 1

    def test_a_ca_bundle_file_is_carried_into_the_secret_as_the_declared_trust(self, wire, tmp_path):
        _require_openssl()
        pem, _, _ = _pki(tmp_path, "both-hosts")      # a real CA: the writer's parser LOADS caData before it writes
        cluster = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER, ca_bundle_file=str(pem))
        _, host = run(cluster, FakeHost(), s=settings(cluster))
        config = json.loads(host.writes[0][2]["stringData"]["config"])
        assert config["tlsClientConfig"] == {"insecure": False, "caData": base64.b64encode(pem.read_bytes()).decode()}

    def test_the_type_label_is_stamped_whatever_labels_a_caller_supplies(self):
        """The operator's requirement (SPEC_S4b notes): an invariant, not a convention. `validate()`
        refuses the app's prefix, but `secret_object()` has callers that do not validate — measured
        on the merged tree, a caller label `secret-type: onboard` replaced the discovery label."""
        from gsd.clusterconfig import SECRET_TYPE_LABEL
        from gsd.clusterconfig.writer import CreateRequest, secret_object
        req = CreateRequest(name="x", server=API, credential_kind="bearerToken", token="tok-12345678",
                            labels={SECRET_TYPE_LABEL: "onboard", "environment": "rnd"})
        assert secret_object(req, "ns")["metadata"]["labels"] == {"environment": "rnd", SECRET_TYPE_LABEL: "cluster"}


# ── R2 ─────────────────────────────────────────────────────────────────────────────────────────

class TestADeclaringSecretIsUpdatedInPlace:
    def test_the_mode_leaves_config_the_credential_arrives_and_the_annotations_remember(self, wire):
        declared = {"metadata": {"name": "gsd-cluster-rnd", "namespace": "ns", "resourceVersion": "7",
                                 "labels": {"groupsync-dashboard.io/secret-type": "cluster", "environment": "rnd"},
                                 "annotations": {MANAGED_BY_ANNOTATION: "ui"}},
                    "data": {k: base64.b64encode(v.encode()).decode() for k, v in {
                        "name": "rnd", "server": API,
                        "config": json.dumps({"saTokenLookup": True, "ldapConnectionBootstrap": USER,
                                              "tlsClientConfig": {"insecure": False, "caData": "Y2E="}})}.items()}}
        host = FakeHost({"/api/v1/namespaces/ns/secrets/gsd-cluster-rnd": declared})
        cluster = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER, source="secret:gsd-cluster-rnd")
        result, _ = run(cluster, host)
        (method, path, obj), = host.writes
        assert (method, path, result.written) == ("PUT", "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd", "updated")
        config = json.loads(base64.b64decode(obj["data"]["config"]))
        assert config == {"tlsClientConfig": {"insecure": False, "caData": "Y2E="}, "bearerToken": SA_TOKEN}
        assert obj["metadata"]["resourceVersion"] == "7", "PUT as read: a rewrite underneath is a 409, not a silent overwrite"
        assert obj["metadata"]["labels"]["environment"] == "rnd"
        assert obj["metadata"]["annotations"] == {MANAGED_BY_ANNOTATION: "ui", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
                                                  SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
                                                  SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
                                                  LOOKUP_ACCOUNT_ANNOTATION: USER}


# ── R3 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheTargetsSecretIsCheckedBeforeItIsStored:
    @pytest.mark.parametrize("answer,code,words", [
        (httpx.Response(404, text="not found"), "sa-token-secret-missing", "create the token Secret on the target"),
        (httpx.Response(403, text="forbidden"), "sa-token-unreadable", "get on that one Secret"),
        (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "2027-09-22"})), "sa-token-invalidated", "invalidated it after a year unused"),
        (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: ""})), "sa-token-invalidated", "invalidated it after a year unused"),
        (httpx.Response(200, json=sa_secret(sa="somebody-else")), "sa-token-unreadable", "13 characters long and does not match"),
        (httpx.Response(200, json=sa_secret(type_="Opaque")), "sa-token-unreadable", "is not type kubernetes.io/service-account-token"),
        (httpx.Response(200, json=sa_secret(token="")), "sa-token-unreadable", "has no token yet"),
    ])
    def test_each_refusal_names_its_fix_stores_nothing_and_still_logs_out(self, wire, answer, code, words):
        """The empty `invalid-since` value is review of #295, P1-5: the label's PRESENCE is the fact."""
        wire.secret = answer
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == code and exc.value.spent is True
        assert words in exc.value.detail + " " + exc.value.action
        assert "somebody-else" not in exc.value.detail and "Opaque" not in exc.value.detail, "a remote name is never echoed"
        assert SA_TOKEN not in str(exc.value) + exc.value.detail + exc.value.action
        assert len(wire.revokes) == 1, "the session is revoked after a failed read too"

    def test_every_code_this_module_raises_is_in_the_closed_set(self):
        assert set(CODES) <= set(FINDING_CODES)


# ── R4 ─────────────────────────────────────────────────────────────────────────────────────────

class TestARefusedPasswordIsGated:
    def test_the_second_lookup_sends_no_login_until_the_password_moves(self, wire):
        wire.answers = [refused_401(), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as first:
            run(RND, gate=gate)
        assert first.value.code == "login-refused" and first.value.spent is True and len(wire.authorize) == 1
        host = FakeHost()
        with pytest.raises(LookupRefused) as second:
            run(RND, host, gate=gate)
        assert second.value.code == "login-refused" and second.value.spent is False
        assert len(wire.authorize) == 1, "the refusal was retried — that is the lockout walk"
        host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {"data": {"password": base64.b64encode(b"rotated-pass-9").decode()}}
        wire.secret = httpx.Response(200, json=sa_secret())
        result, _ = run(RND, host, gate=gate)
        assert result.written == "created" and len(wire.authorize) == 2

    def test_no_password_secret_is_a_free_finding_that_names_the_grant(self, wire):
        host = FakeHost(); host.secrets.clear()
        with pytest.raises(LookupRefused) as exc:
            run(RND, host)
        assert exc.value.code == "fleet-credential-missing" and exc.value.spent is False
        assert "gsd-fleet-account" in exc.value.detail and wire.authorize == []

    def test_a_500_on_authorize_is_one_bind_and_a_gated_credential(self, wire):
        """Review of #295, P0-1: a LOCKED account answers 500 (code 19 is not 48/49), #283 made it
        terminal inside the login, and the schedule must not re-enter it — one bind, then the gate."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as first:
            run(RND, gate=gate)
        assert first.value.code == "login-failed" and first.value.spent is True and len(wire.authorize) == 1
        with pytest.raises(LookupRefused) as second:
            run(RND, gate=gate)
        assert second.value.code == "login-refused" and second.value.spent is False
        assert len(wire.authorize) == 1, "a 500 was retried — that is the lockout walk one layer up"

    def test_a_read_timeout_after_the_password_was_sent_gates_that_target(self, wire):
        """The GET was written and nothing came back: the target may have bound, #283 makes it
        terminal, and the same password must not reach THAT target again — an in-memory "final" that
        any shape change re-armed was not a stop (review of #295, second pass, R2-1/R2-2)."""
        wire.answers = [lambda r: httpx.ReadTimeout("timed out"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as exc:
            run(RND, gate=gate)
        assert exc.value.code == "login-failed" and exc.value.spent is True and len(wire.authorize) == 1
        assert gate.refused(API, USER, PASSWORD)
        with pytest.raises(LookupRefused) as again:
            run(RND, gate=gate)
        assert again.value.code == "login-refused" and again.value.spent is False
        assert len(wire.authorize) == 1, "the password reached a target that may have bound it, twice"

    def test_one_target_spelled_three_ways_is_one_gate_entry(self):
        """Third pass, R3-1: a stanza edited from api.example.com to API.example.com was a new key and
        the password went to the same target again. httpx canonicalises the host; a malformed URL
        must not raise inside the gate."""
        gate = CredentialGate()
        gate.refuse("https://api.example.com:6443", USER, PASSWORD)
        for spelling in ("https://api.example.com:6443/", "https://API.Example.COM:6443", "https://API.example.com:6443/"):
            assert gate.refused(spelling, USER, PASSWORD), spelling
        assert not gate.refused("https://api.example.com:6444", USER, PASSWORD), "a different port is a different target"
        gate.refuse("https://[::1/broken", USER, PASSWORD)
        assert gate.refused("https://[::1/broken/", USER, PASSWORD), "the fallback key, not an exception"

    def test_the_gate_is_per_target_so_a_sick_cluster_does_not_stop_a_healthy_one(self, wire):
        """Review of #295, second pass, R2-1: keyed without the target, a 500 from A blocked B."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused):
            run(RND, gate=gate)
        other = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
        result, _ = run(other, gate=gate, s=settings(other))
        assert result.written == "created" and len(wire.authorize) == 2
        assert gate.refused(API, USER, PASSWORD) and not gate.refused(other.api_url, USER, PASSWORD)


# ── R5 ─────────────────────────────────────────────────────────────────────────────────────────

class TestATrustFailureNamesItsHost:
    def test_the_oauth_route_is_named_when_authorize_cannot_connect(self, wire):
        wire.answers = [lambda r: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")] * 5
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "login-failed" and "against oauth-openshift.apps.example.com" in exc.value.detail
        assert "phase=tls" in exc.value.detail and "BOTH the API host and the OAuth route" in exc.value.action

    def test_the_api_host_is_named_when_discovery_cannot_connect(self, wire):
        wire.discovery = down
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "login-failed" and "against api.example.com:6443" in exc.value.detail


# ── R6 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheSchedule:
    """The poller's half: attempts, backoff, gave up, and the free findings rechecked every cycle."""

    def _poller(self, tmp_path, monkeypatch, *, writes=True):
        from gsd.poller import Poller
        from gsd.store import Store
        monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
        s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), RND],
                     db_path=str(tmp_path / "p.db"), cluster_secrets_writes_enabled=writes)
        return Poller(Store(str(tmp_path / "p.db")), s)

    def test_a_spent_failure_backs_off_and_gives_up_out_loud(self, tmp_path, monkeypatch, caplog):
        clock = [1000.0]
        monkeypatch.setattr("gsd.poller.time.monotonic", lambda: clock[0])

        def failing(*a, **kw):
            raise LookupRefused("sa-token-secret-missing", "gone", action="create the token Secret on the target", spent=True)
        monkeypatch.setattr(fleetlookup, "lookup", failing)
        poller = self._poller(tmp_path, monkeypatch)
        interval = poller.settings.binding_interval_seconds
        with caplog.at_level(logging.INFO, logger="gsd"):
            waits = []
            for n in range(1, 6):
                poller._retrieve_pending()
                state = poller._lookups["rnd"]
                waits.append(state.not_before - clock[0])
                clock[0] = state.not_before
            poller._retrieve_pending()          # gave up: nothing runs, nothing is logged
        lines = [m for m in caplog.messages if m.startswith("fleet-lookup-failed ")]
        assert len(lines) == 5 and waits[:4] == [interval, 2 * interval, 4 * interval, 8 * interval] and waits[4] == 0
        assert "attempt=1/5" in lines[0] and "retry_in=" in lines[0] and "gave_up=true" in lines[4] and "outcome=sa-token-secret-missing" in lines[4]
        finding = next(f for f in poller.settings.cluster_registry.findings() if f.code == "sa-token-secret-missing")
        assert finding.secret == "gsd-cluster-rnd" and "create the token Secret on the target" in finding.detail

    def test_writes_off_is_a_free_finding_said_once_and_no_login(self, tmp_path, monkeypatch, caplog, wire):
        """The switch is checked inside `lookup()` (review of #295, P1-4), before any password is read
        and before any login; the poller announces the free finding once and rechecks every cycle."""
        poller = self._poller(tmp_path, monkeypatch, writes=False)
        monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: FakeHost())
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending(); poller._retrieve_pending()
        assert wire.requests == [] and sum(m.startswith("fleet-lookup-failed ") for m in caplog.messages) == 1
        assert [f.code for f in poller.settings.cluster_registry.findings()] == ["fleet-write-disabled"]

    def test_the_lookup_itself_refuses_to_write_with_the_switch_off_and_the_ping_needs_no_grant(self, wire):
        with pytest.raises(LookupRefused) as exc:
            run(RND, s=settings(RND, writes=False))
        assert exc.value.code == "fleet-write-disabled" and exc.value.spent is False and wire.requests == []
        result, host = run(RND, write=False, s=settings(RND, writes=False))
        assert result.written is None and host.writes == [] and len(wire.reads) == 1

    def test_above_one_replica_without_an_elector_no_replica_retrieves(self, tmp_path, monkeypatch, caplog, wire):
        """Review of #295, P0-2: with election off `elector` is None on every replica, and a
        Secret-declared mode is invisible to the render's refusal — so the pod refuses it itself."""
        import dataclasses
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings = dataclasses.replace(poller.settings, replica_count=2)
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()
        assert wire.requests == []
        finding, = poller.settings.cluster_registry.findings()
        assert finding.code == "fleet-write-disabled" and "2 replicas" in finding.detail

    def test_a_gated_credential_says_gave_up_once_and_then_is_silent_but_still_re_read(self, tmp_path, monkeypatch, caplog, wire):
        """Third pass, R3-2: after the gate fires, each cycle took the free refusal silently forever.
        The operator must see `gave_up=true` once; the cheap per-cycle read of the password Secret
        stays, because it is the rotation detector — and a rotated password resumes the login."""
        clock = [1000.0]
        monkeypatch.setattr("gsd.poller.time.monotonic", lambda: clock[0])
        host = FakeHost()
        monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        poller = self._poller(tmp_path, monkeypatch)
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()                     # the bind: spent, attempt=1/5, gates the target
            clock[0] += 10 * poller.settings.binding_interval_seconds
            poller._retrieve_pending()                     # the gate: free, announced once with gave_up=true
            poller._retrieve_pending(); poller._retrieve_pending()   # silent, still re-reading the password
        lines = [m for m in caplog.messages if m.startswith("fleet-lookup-failed ")]
        assert len(lines) == 2 and "attempt=1/5" in lines[0] and "outcome=login-failed" in lines[0]
        assert "outcome=login-refused" in lines[1] and "gave_up=true" in lines[1] and "until the fleet password Secret" in lines[1]
        assert len(wire.authorize) == 1, "the gate held across the cycles"
        host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {"data": {"password": base64.b64encode(b"rotated-pass-9").decode()}}
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()
        assert len(wire.authorize) == 2 and any(m.startswith("fleet-lookup ") for m in caplog.messages), "a rotated password resumed the login"

    def test_a_non_scalar_token_and_an_error_body_are_refusals_that_carry_nothing(self, wire):
        """Review of #295, second pass, R2-3: a `data.token` that is not a string raised TypeError in
        front of every refusal; a 500 body on the Secret GET carried the token straight into the
        finding, because an undecoded token is not among the secrets a refusal is scrubbed against."""
        wire.answers = [login_302(), login_302()]      # two logins, one per probe
        odd = sa_secret(); odd["data"]["token"] = 123
        wire.secret = httpx.Response(200, json=odd)
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "sa-token-unreadable" and "has no token yet" in exc.value.detail
        wire.secret = httpx.Response(500, text=f"boom {SA_TOKEN} boom")
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "sa-token-unreadable" and "HTTP 500 on " in exc.value.detail
        assert SA_TOKEN not in str(exc.value) + exc.value.detail + exc.value.action, "a remote body is never quoted"

    def test_success_clears_the_finding_and_wakes_discovery(self, tmp_path, monkeypatch, caplog):
        from gsd.fleetlookup import LookupResult, SaToken
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings.cluster_registry.set_lookup_finding("rnd", Finding("gsd-cluster-rnd", "login-failed", "x"))
        monkeypatch.setattr(fleetlookup, "lookup", lambda *a, **kw: LookupResult(
            "rnd", USER, SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="poller", secret_name="poller-token", last_used="2026-09-22"),
            "gsd-cluster-rnd", "created", (SA_TOKEN,)))
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()
        assert poller.settings.cluster_registry.findings() == [] and poller._discover_now.is_set()
        line = next(m for m in caplog.messages if m.startswith("fleet-lookup "))
        assert "written=created" in line and "last_used=2026-09-22" in line and SA_TOKEN not in line

    def test_a_retrieved_stanza_whose_secret_vanished_stops_polling_rather_than_polling_the_stanza(self, tmp_path, monkeypatch):
        """SPEC_S3 §4.2: a pending credential is never presented. With the lookup's Secret gone the
        stanza is pending again, so its thread stops; a values cluster with its own credential is
        still never stopped at runtime."""
        import threading
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings.clusters.append(ClusterConfig("east", "https://api.east:6443", token_env="X"))
        poller._cluster_stops["rnd"] = threading.Event()
        poller._cluster_stops["east"] = threading.Event()
        poller._reconcile_threads()
        assert poller._cluster_stops["rnd"].is_set(), "the pending stanza kept polling"
        assert not poller._cluster_stops["east"].is_set(), "a values cluster with a credential was stopped"


# ── R7 ─────────────────────────────────────────────────────────────────────────────────────────

class TestNoCredentialReachesALine:
    def test_the_password_the_session_and_the_sa_token_are_absent_from_every_refusal_and_line(self, wire, caplog):
        planted = httpx.Response(200, json=sa_secret(sa=f"somebody {PASSWORD} {TOKEN} {SA_TOKEN}"))
        wire.secret = planted
        with caplog.at_level(logging.DEBUG, logger="gsd"):
            with pytest.raises(LookupRefused) as exc:
                run(RND)
        text = str(exc.value) + exc.value.detail + exc.value.action + " ".join(caplog.messages)
        assert PASSWORD not in text and TOKEN not in text and SA_TOKEN not in text, "review of #295, P1-1: all three"
        assert set(exc.value.secrets) >= {PASSWORD, TOKEN, SA_TOKEN}, "the poller's line is handed everything in play"


class TestTheSwitchReadsAWord:
    def test_a_quoted_false_in_the_configmap_does_not_enable_writes(self, tmp_path):
        """Review of #295, P1-3: `bool("false")` is True, so the ConfigMap path enabled writes on an
        explicit disable. The env path already read the word; the ConfigMap path now does too."""
        from gsd.config import load_settings
        clusters = "clusters:\n  - name: host\n    apiUrl: https://kubernetes.default.svc\n    tokenEnv: X\n"
        for spelling, expected in (('"false"', False), ("false", False), ('"true"', True), ("true", True), ('"no"', False)):
            path = tmp_path / "c.yaml"
            path.write_text(clusters + f"clusterSecretsWritesEnabled: {spelling}\n")
            assert load_settings(str(path)).cluster_secrets_writes_enabled is expected, spelling

    def test_a_value_that_is_neither_a_boolean_nor_a_word_is_the_default_and_names_its_source(self, tmp_path, caplog):
        """Review of #295, second pass, R2-4: `2`, `-1` and `[false]` enabled the switch by truthiness,
        silently; `null` and `[]` disabled it silently; the warning named the env variable for a
        ConfigMap value. The default is off, so every odd spelling must read as off, and say so."""
        from gsd.config import load_settings
        clusters = "clusters:\n  - name: host\n    apiUrl: https://kubernetes.default.svc\n    tokenEnv: X\n"
        for spelling in ("2", "-1", "[false]", "[]", '""', "maybe", "{a: 1}"):
            path = tmp_path / "c.yaml"
            path.write_text(clusters + f"clusterSecretsWritesEnabled: {spelling}\n")
            caplog.clear()
            with caplog.at_level(logging.WARNING, logger="gsd"):
                assert load_settings(str(path)).cluster_secrets_writes_enabled is False, spelling
            assert any("clusterSecretsWritesEnabled=" in m and "not a boolean" in m for m in caplog.messages), spelling
        path = tmp_path / "c.yaml"
        path.write_text(clusters + "clusterSecretsWritesEnabled: null\n")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="gsd"):
            assert load_settings(str(path)).cluster_secrets_writes_enabled is False
        assert caplog.messages == [], "a null is an absent key, not an odd value"
