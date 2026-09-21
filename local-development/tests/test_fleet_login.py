"""#283 (SPEC_S4a): log in to a target as the fleet account, read the expiry, apply the retry policy,
log out — against a fake OAuth server that records every request the module makes, in order.

Each class is one of the business owner's requirements as the spec numbers them: R1 login only,
R2 the session logs out on every exit path, R3 the retry policy (a refusal is NEVER retried — the
call count is asserted to be exactly one), R4 the expiry is an absolute instant from the target's own
`expires_in`, R5 the token is read off the `Location` fragment and the redirect is not followed,
R6 the OAuth host is discovered, R7 TLS follows the cluster's `tls_mode`, R8 the three log fields,
no new phase, and the redaction pin over every new path."""

from __future__ import annotations

import ast
import base64
import hashlib
import logging
import pathlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest

import gsd.fleetlogin as fleetlogin
from gsd.clusterconfig.events import PHASES, is_verify_failure
from gsd.config import ClusterConfig, ConfigError
from gsd.fleetlogin import (
    CHALLENGING_CLIENT, DISCOVERY_PATH, EVENTS, LOGIN_REFUSED, TOKEN_PREFIX, USER_TOKEN_API,
    FleetLogin, LoginError, RetryPolicy, token_object_name,
)
from gsd.kube import AUTH_FAILED, UNREACHABLE, ClusterError

API = "https://api.example.com:6443"
OAUTH = "https://oauth-openshift.apps.example.com"
DISCOVERY = {"issuer": OAUTH, "authorization_endpoint": f"{OAUTH}/oauth/authorize",
             "token_endpoint": f"{OAUTH}/oauth/token"}
USER = "svc-gsd-fleet"
PASSWORD = "c0rrect-horse-battery-staple"
TOKEN = "sha256~Qm9ndXNUb2tlblRoYXRNdXN0TmV2ZXJSZWFjaEFMb2c"
T0 = datetime(2026, 9, 21, 12, 0, 0, tzinfo=UTC)
POLICY = RetryPolicy(attempts=5, base_seconds=1.0, max_wait_seconds=30.0)
BASIC = 'Basic realm="openshift"'


def login_302(expires_in: str = "31536000", token: str = TOKEN) -> httpx.Response:
    """What the reference cluster answered a correct password with (SPEC_S4a §2): a 302 with an
    empty body and everything in the fragment."""
    location = (f"{OAUTH}/oauth/token/implicit#access_token={token}&expires_in={expires_in}"
                f"&scope=user%3Afull&token_type=Bearer")
    return httpx.Response(302, headers={"Location": location})


def refused_401(body: str = "") -> httpx.Response:
    """A refused password as SPEC_S4 §6 measured it: a bare 401, the Basic challenge, an empty body."""
    return httpx.Response(401, headers={"Www-Authenticate": BASIC}, text=body)


def down(request: httpx.Request) -> Exception:
    return httpx.ConnectError("[Errno 61] Connection refused")


class Target:
    """The fake target: a discovery document at the API host, an authorize endpoint at the OAuth
    host answering from a script (a Response, or a callable given the request that returns a
    Response or an exception to raise), a revoke endpoint, and every request in order."""

    def __init__(self, *answers, discovery=None, revoke=None):
        self.answers = list(answers)
        self.discovery = DISCOVERY if discovery is None else discovery
        self.revoke = httpx.Response(200, json={"kind": "OAuthAccessToken"}) if revoke is None else revoke
        self.requests: list[httpx.Request] = []

    @staticmethod
    def _answer(answer, request):
        if callable(answer):
            answer = answer(request)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == DISCOVERY_PATH:
            if isinstance(self.discovery, dict):
                return httpx.Response(200, json=self.discovery)
            return self._answer(self.discovery, request)
        if request.url.path == "/oauth/authorize":
            return self._answer(self.answers.pop(0), request)
        if request.method == "DELETE" and request.url.path.startswith(USER_TOKEN_API + "/"):
            return self._answer(self.revoke, request)
        return httpx.Response(599, text=f"the fake target has no {request.method} {request.url}")

    @property
    def authorize(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == "/oauth/authorize"]

    @property
    def revokes(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == "DELETE"]


def scripted(*answers):
    """A discovery endpoint answering from a script, one answer per call."""
    queue = list(answers)
    return lambda request: queue.pop(0)


def make(target: Target, *, cluster: ClusterConfig | None = None, policy: RetryPolicy = POLICY,
         clock=None) -> tuple[FleetLogin, list[float]]:
    """A FleetLogin wired to the fake target, with the sleeps it asked for recorded and the clock
    held at T0 unless the test brings its own."""
    cluster = cluster or ClusterConfig("east", API, insecure_skip_verify=True)
    sleeps: list[float] = []
    fl = FleetLogin(cluster, USER, PASSWORD, policy=policy, sleep=sleeps.append, clock=clock or (lambda: T0))
    fl._build_client = lambda: httpx.Client(transport=httpx.MockTransport(target), base_url=API,
                                            follow_redirects=False)
    return fl, sleeps


def lines(caplog, name: str) -> list[str]:
    return [m for m in caplog.messages if m.startswith(name + " ")]


# ── R6 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheOAuthHostIsDiscovered:
    def test_the_login_goes_to_the_discovered_endpoint_not_the_api_host(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        wire = [(r.method, r.url.host, r.url.path) for r in target.requests]
        assert wire[0] == ("GET", "api.example.com", DISCOVERY_PATH)
        assert wire[1] == ("GET", "oauth-openshift.apps.example.com", "/oauth/authorize")
        assert "authorization" not in target.requests[0].headers, "discovery is unauthenticated"

    def test_the_authorize_request_is_the_challenging_client_flow(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        req = target.authorize[0]
        assert dict(req.url.params) == {"client_id": CHALLENGING_CLIENT, "response_type": "token"}
        assert req.headers["x-csrf-token"] == "1"
        basic = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        assert req.headers["authorization"] == f"Basic {basic}"

    def test_the_client_id_is_the_one_the_audit_log_classifies_as_cli(self):
        from gsd.auditlog import CHALLENGING_CLIENT as audited
        assert CHALLENGING_CLIENT == audited

    def test_a_plain_http_endpoint_is_refused_before_any_password_is_sent(self):
        target = Target(login_302(), discovery={"authorization_endpoint": "http://oauth.example.com/oauth/authorize"})
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert target.authorize == [] and sleeps == []
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False and exc.value.phase == "connect"

    def test_the_issuer_is_the_documents_and_falls_back_to_the_endpoints_host(self):
        with make(Target(login_302()))[0] as s:
            assert s.issuer == OAUTH
        bare = {"authorization_endpoint": f"{OAUTH}/oauth/authorize"}
        with make(Target(login_302(), discovery=bare))[0] as s:
            assert s.issuer == OAUTH


# ── R5 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheTokenIsReadOffTheLocationFragment:
    def test_the_token_and_expiry_come_from_the_fragment_and_the_redirect_is_not_followed(self):
        target = Target(login_302(expires_in="86400"))
        fl, _ = make(target)
        with fl as session:
            assert session.token == TOKEN and session.expires_in == 86400
        assert [r.url.path for r in target.requests] == [
            DISCOVERY_PATH, "/oauth/authorize", f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"]
        assert not any("/oauth/token/implicit" in str(r.url) for r in target.requests), "the redirect was followed"

    def test_a_302_without_a_token_is_not_a_session_and_is_retried_within_the_ceiling(self):
        no_token = httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error=server_error"})
        target = Target(no_token, login_302())
        fl, sleeps = make(target)
        with fl as s:
            assert s.attempts == 2
        assert sleeps == [1.0] and len(target.authorize) == 2

    def test_a_token_without_a_usable_expiry_is_revoked_at_once_and_not_retried(self):
        target = Target(login_302(expires_in="soon"), login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and exc.value.phase == "credential"
        assert len(target.authorize) == 1 and sleeps == [] and fl.session is None
        assert [r.url.path for r in target.revokes] == [f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"]
        assert "revoked" in exc.value.message


# ── R4 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheExpiryIsAnAbsoluteInstant:
    @pytest.mark.parametrize("expires_in,expected", [
        ("31536000", T0 + timedelta(days=365)),   # the reference cluster: a year
        ("86400", T0 + timedelta(days=1)),        # OpenShift's default: a day
        ("3600", T0 + timedelta(hours=1)),        # an estate that tightened it
    ])
    def test_it_is_obtained_at_plus_the_targets_own_expires_in(self, expires_in, expected):
        with make(Target(login_302(expires_in=expires_in)))[0] as s:
            assert s.obtained_at == T0 and s.expires_at == expected
            assert s.expires_at.utcoffset() == timedelta(0)
            assert s.expires_at_iso == expected.strftime("%Y-%m-%dT%H:%M:%SZ")

    def test_the_clock_is_read_before_the_request_leaves(self):
        order: list[str] = []

        def clock():
            order.append("clock")
            return T0

        def answer(request):
            order.append("authorize")
            return login_302()

        with make(Target(answer), clock=clock)[0]:
            pass
        assert order == ["clock", "authorize"]

    def test_the_success_line_carries_the_instant_never_an_age(self, caplog):
        with caplog.at_level(logging.INFO):
            with make(Target(login_302(expires_in="3600")))[0]:
                pass
        line = lines(caplog, "fleet-login")[0]
        assert "expires_at=2026-09-21T13:00:00Z" in line
        assert "ago" not in line and "expires_in" not in line and "hour" not in line


# ── R2 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheSessionLogsOut:
    def test_the_revoke_is_by_name_with_the_token_as_bearer_and_is_the_last_request(self):
        target = Target(login_302())
        fl, _ = make(target)
        with fl:
            pass
        last = target.requests[-1]
        assert last.method == "DELETE"
        assert last.url.path == f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"
        assert last.headers["authorization"] == f"Bearer {TOKEN}"
        assert len(target.revokes) == 1

    def test_an_exception_in_the_body_still_revokes_and_propagates(self):
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(RuntimeError, match="the read failed"):
            with fl:
                raise RuntimeError("the read failed")
        assert len(target.revokes) == 1 and target.requests[-1].method == "DELETE"

    def test_a_base_exception_in_the_body_still_revokes(self):
        class Abort(BaseException):
            pass

        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(Abort):
            with fl:
                raise Abort()
        assert len(target.revokes) == 1

    def test_the_object_name_is_the_measured_derivation(self):
        """`sha256~` + base64url(sha256(the part after the prefix)), unpadded — the name the
        reference cluster listed for a token this flow minted (SPEC_S4a §2)."""
        raw = TOKEN[len(TOKEN_PREFIX):]
        expected = TOKEN_PREFIX + base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")
        assert token_object_name(TOKEN) == expected and "=" not in expected and expected != TOKEN
        assert token_object_name("legacy-token-value") == "legacy-token-value"

    def test_an_already_gone_token_is_not_a_failure(self, caplog):
        for status in (404, 401):
            target = Target(login_302(), revoke=httpx.Response(status, text="gone"))
            with caplog.at_level(logging.INFO):
                with make(target)[0]:
                    pass
        assert lines(caplog, "fleet-logout-failed") == []
        assert all("outcome=already-gone" in m for m in lines(caplog, "fleet-logout"))

    def test_a_revoke_the_target_refused_is_said_out_loud_and_does_not_raise(self, caplog):
        target = Target(login_302(), revoke=httpx.Response(500, text="oops"))
        with caplog.at_level(logging.WARNING):
            with make(target)[0]:
                pass
        line = lines(caplog, "fleet-logout-failed")[0]
        assert f"token={token_object_name(TOKEN)}" in line and "phase=poll" in line and "HTTP 500" in line
        assert "oc delete oauthaccesstoken" in line

    def test_a_failed_revoke_does_not_replace_the_bodys_exception(self, caplog):
        target = Target(login_302(), revoke=lambda request: httpx.ConnectError("the target went away"))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(RuntimeError, match="the body's own"):
                with make(target)[0]:
                    raise RuntimeError("the body's own")
        assert "phase=connect" in lines(caplog, "fleet-logout-failed")[0]

    def test_a_login_that_failed_has_nothing_to_revoke(self):
        target = Target(refused_401())
        with pytest.raises(LoginError):
            with make(target)[0]:
                pass
        assert target.revokes == []

    def test_one_instance_is_one_session(self):
        fl, _ = make(Target(login_302(), login_302()))
        with fl:
            pass
        with pytest.raises(RuntimeError, match="one session"):
            with fl:
                pass


# ── R3 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheRetryPolicy:
    def test_a_refused_password_is_never_retried(self, caplog):
        target = Target(refused_401(), login_302())     # the second answer must never be asked for
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1, "the refusal was retried — that is the lockout walk"
        assert len(target.answers) == 1, "the scripted second answer was consumed"
        assert sleeps == [] and target.revokes == []
        assert exc.value.outcome == AUTH_FAILED and exc.value.retryable is False and exc.value.attempts == 1
        line = lines(caplog, "fleet-login-refused")[0]
        assert f"outcome={LOGIN_REFUSED}" in line and "phase=credential" in line and f"account={USER}" in line
        assert "Www-Authenticate: Basic" in line, "the server's own words — the status line and the challenge"
        assert "attempt=" not in line and "retry_in=" not in line and "gave_up=" not in line
        assert lines(caplog, "fleet-login-failed") == []

    def test_a_refusal_is_a_typed_cluster_error_the_caller_can_branch_on(self):
        with pytest.raises(ClusterError) as exc:
            with make(Target(refused_401()))[0]:
                pass
        assert isinstance(exc.value, LoginError) and exc.value.outcome == AUTH_FAILED

    def test_a_401_without_a_basic_challenge_is_not_a_refusal_and_is_not_retried_either(self, caplog):
        target = Target(httpx.Response(401, text="no challenge"), login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1 and sleeps == []
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False
        assert lines(caplog, "fleet-login-refused") == []
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=credential" in line and "<absent>" in line and "not retried" in line

    @pytest.mark.parametrize("transient", [
        down,
        lambda request: httpx.ReadTimeout("timed out"),
        lambda request: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                           "self-signed certificate in certificate chain"),
        lambda request: httpx.Response(503, text="oauth-server unavailable"),
    ], ids=["refused-socket", "read-timeout", "tls-verify", "http-503"])
    def test_an_unreachable_target_is_retried_with_exponential_backoff(self, transient, caplog):
        target = Target(transient, transient, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.INFO):
            with fl as s:
                assert s.attempts == 3
        assert len(target.authorize) == 3 and sleeps == [1.0, 2.0]
        failed = lines(caplog, "fleet-login-failed")
        assert len(failed) == 2
        assert "attempt=1/5" in failed[0] and "retry_in=1" in failed[0] and "gave_up=" not in failed[0]
        assert "attempt=2/5" in failed[1] and "retry_in=2" in failed[1]
        assert "attempt=3/5" in lines(caplog, "fleet-login")[0]

    def test_it_gives_up_out_loud_at_the_ceiling(self, caplog):
        target = Target(down, down, down, down, down, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 5 and sleeps == [1.0, 2.0, 4.0, 8.0]
        assert len(target.answers) == 1, "a sixth attempt was made past the ceiling"
        assert exc.value.outcome == UNREACHABLE and exc.value.attempts == 5 and exc.value.retryable is True
        last = lines(caplog, "fleet-login-failed")[-1]
        assert "gave_up=true" in last and "attempt=5/5" in last and "retry_in=" not in last
        assert "Connection refused" in last, "the last error travels with the gave_up line"
        assert target.revokes == []

    def test_the_wait_sequence_is_the_stated_one(self):
        assert [POLICY.wait_after(n) for n in range(1, 5)] == [1.0, 2.0, 4.0, 8.0]
        assert RetryPolicy(attempts=8).wait_after(7) == 30.0, "capped at max_wait_seconds"
        assert fleetlogin.RETRY_POLICY == RetryPolicy(attempts=5, base_seconds=1.0, max_wait_seconds=30.0)
        with pytest.raises(ValueError):
            RetryPolicy(attempts=0)

    def test_a_discovery_failure_counts_as_an_attempt_and_is_retried(self, caplog):
        target = Target(login_302(), discovery=scripted(httpx.Response(502, text="bad gateway"),
                                                         httpx.Response(200, json=DISCOVERY)))
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with fl as s:
                assert s.attempts == 2
        assert sleeps == [1.0] and len(target.authorize) == 1
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=connect" in line and "attempt=1/5" in line and "HTTP 502" in line

    def test_a_tls_failure_is_phase_tls_and_a_socket_failure_phase_connect(self, caplog):
        tls = lambda request: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        target = Target(tls, down, login_302())
        with caplog.at_level(logging.WARNING):
            with make(target)[0]:
                pass
        failed = lines(caplog, "fleet-login-failed")
        assert "phase=tls" in failed[0] and "phase=connect" in failed[1]


# ── R7 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTLSFollowsTheClustersMode:
    class Recorder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            pass

    def test_verify_is_the_clusters_own_decision_and_redirects_are_never_followed(self, monkeypatch):
        monkeypatch.setattr(fleetlogin.httpx, "Client", self.Recorder)
        sentinel = object()
        monkeypatch.setattr(ClusterConfig, "verify", lambda self: sentinel)
        client = FleetLogin(ClusterConfig("east", API), USER, PASSWORD, timeout=7.5)._build_client()
        assert client.kwargs["verify"] is sentinel
        assert client.kwargs["follow_redirects"] is False
        assert client.kwargs["timeout"] == 7.5 and client.kwargs["base_url"] == API

    def test_insecure_and_default_modes_pass_what_the_poller_passes(self, monkeypatch):
        monkeypatch.setattr(fleetlogin.httpx, "Client", self.Recorder)
        monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
        insecure = ClusterConfig("east", API, insecure_skip_verify=True)
        assert FleetLogin(insecure, USER, PASSWORD)._build_client().kwargs["verify"] is False
        default = ClusterConfig("east", API)
        assert FleetLogin(default, USER, PASSWORD)._build_client().kwargs["verify"] == default.verify()

    def test_a_ca_bundle_this_pod_cannot_load_is_a_tls_stop_before_any_request(self, tmp_path, caplog):
        cluster = ClusterConfig("east", API, ca_bundle_file=str(tmp_path / "missing.pem"))
        fl = FleetLogin(cluster, USER, PASSWORD, sleep=lambda s: pytest.fail("slept"))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert exc.value.outcome == UNREACHABLE and exc.value.retryable is False and exc.value.phase == "tls"
        assert isinstance(exc.value.__cause__, ConfigError)
        line = lines(caplog, "fleet-login-failed")[0]
        assert "phase=tls" in line and "tls=caBundleFile" in line and "not retried" in line


# ── R8 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheLogVocabulary:
    def test_no_new_phase_was_added(self):
        assert PHASES == ("discovery", "parse", "credential", "tls", "connect", "poll")

    def test_the_shared_verify_classifier_keeps_the_pollers_provenance_rule(self):
        assert is_verify_failure("ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        assert is_verify_failure("ConnectError: unable to get local issuer certificate")
        assert not is_verify_failure("HTTP 502 on /apis: certificate verify failed"), "a remote's words decide nothing"
        assert not is_verify_failure("ConnectError: [Errno 61] Connection refused")
        assert not is_verify_failure("")

    def test_every_line_names_the_cluster_the_account_and_the_tls_mode(self, caplog):
        with caplog.at_level(logging.INFO):
            with make(Target(down, login_302()))[0]:
                pass
        for line in [*lines(caplog, "fleet-login-failed"), *lines(caplog, "fleet-login"), *lines(caplog, "fleet-logout")]:
            assert "cluster=east" in line and f"account={USER}" in line and "tls=insecure" in line, line


class TestTheRedactionPin:
    """Every event this module can emit, driven with the password and the token planted in every
    text a remote controls, the whole log grepped for both. The set of events driven must equal
    EVENTS, and EVENTS must equal what the source emits — so a new emit site fails here twice, once
    for not being declared and once for not being driven with a secret in force."""

    def _drive_everything(self, caplog):
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(LoginError) as refused:                       # fleet-login-refused
                with make(Target(refused_401(body=f"denied pw={PASSWORD}")))[0]:
                    pass
            echo = lambda request: httpx.ConnectError(f"connect to https://{USER}:{PASSWORD}@host failed")
            with pytest.raises(LoginError) as gave_up:                       # fleet-login-failed, retried, gave up
                with make(Target(echo, echo, echo, echo, echo))[0]:
                    pass
            with make(Target(login_302()))[0]:                               # fleet-login, fleet-logout
                pass
            with make(Target(login_302(), revoke=httpx.Response(500, text=f"echo {TOKEN} {PASSWORD}")))[0]:
                pass                                                         # fleet-logout-failed
            with pytest.raises(LoginError) as stopped:                       # fleet-login-failed, not retried
                with make(Target(httpx.Response(401, text=f"csrf pw={PASSWORD}")))[0]:
                    pass
            with pytest.raises(LoginError):                                  # revoke inside the login
                with make(Target(login_302(expires_in=f"{PASSWORD}")))[0]:
                    pass
        return refused.value, gave_up.value, stopped.value

    def test_every_new_log_path_is_driven_and_none_leaks(self, caplog):
        self._drive_everything(caplog)
        whole = "\n".join(caplog.messages)
        assert PASSWORD not in whole, "the password reached the log"
        assert TOKEN not in whole, "the token reached the log"
        assert "<redacted>" in whole
        seen = {m.split()[0] for m in caplog.messages if m.startswith("fleet-")}
        assert seen == set(EVENTS), f"driven {sorted(seen)}, declared {sorted(EVENTS)}"

    def test_the_error_handed_to_the_caller_carries_no_password(self, caplog):
        for exc in self._drive_everything(caplog):
            assert PASSWORD not in exc.message and PASSWORD not in str(exc)

    def test_the_source_declares_every_event_it_emits_and_passes_secrets_on_each(self):
        tree = ast.parse(pathlib.Path(fleetlogin.__file__).read_text())
        emits = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("event", "failure")]
        assert emits
        assert all(any(k.arg == "secrets" for k in n.keywords) for n in emits), "an emit site without secrets="
        names = {(n.args[2] if n.func.id == "event" else n.args[1]).value for n in emits}
        assert names == set(EVENTS)


# ── R1 ─────────────────────────────────────────────────────────────────────────────────────────

class TestScopeIsLoginOnly:
    def test_the_module_only_ever_gets_and_deletes_its_own_token(self, caplog):
        target = Target(down, login_302())
        with make(target)[0]:
            pass
        assert {r.method for r in target.requests} == {"GET", "DELETE"}
        assert all(r.url.path.startswith(USER_TOKEN_API + "/") for r in target.revokes)

    def test_the_source_neither_writes_a_secret_nor_starts_a_timer(self):
        """Parsed, not grepped: the docstring says "schedules" and "Secret" while saying the module
        does neither. What is asserted is what the code IMPORTS and which methods it calls on its
        client — a write verb or a scheduler is a fact of the AST, not of the prose."""
        tree = ast.parse(pathlib.Path(fleetlogin.__file__).read_text())
        imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert imported.isdisjoint({"threading", "sched", "asyncio", "signal", "subprocess"}), imported
        called = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        assert called.isdisjoint({"post", "put", "patch", "request", "stream", "Timer", "Thread"}), called
        assert {"get", "delete"} <= called
