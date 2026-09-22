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
import http.server
import json
import logging
import pathlib
import shutil
import ssl
import subprocess
import threading
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

import gsd.fleetlogin as fleetlogin
from gsd.clusterconfig.events import PHASES, is_verify_failure
from gsd.config import ClusterConfig, ConfigError
from gsd.fleetlogin import (
    CHALLENGING_CLIENT, DISCOVERY_PATH, EVENTS, LOGIN_REFUSED, MAX_EXPIRES_IN, TOKEN_PREFIX, USER_TOKEN_API,
    FleetLogin, FleetSession, LoginError, RetryPolicy, token_object_name,
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
         clock=None, password: str = PASSWORD) -> tuple[FleetLogin, list[float]]:
    """A FleetLogin wired to the fake target, with the sleeps it asked for recorded and the clock
    held at T0 unless the test brings its own."""
    cluster = cluster or ClusterConfig("east", API, insecure_skip_verify=True)
    sleeps: list[float] = []
    fl = FleetLogin(cluster, USER, password, policy=policy, sleep=sleeps.append, clock=clock or (lambda: T0))
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

    def test_a_discovery_endpoint_that_does_not_parse_is_a_scrubbed_stop(self):
        """Confirmation pass (Codex): `urlsplit` raises `ValueError: Invalid IPv6 URL` on an unclosed
        literal, and its text reached the caller through no LoginError at all."""
        hostile = {"authorization_endpoint": f"https://{USER}:{PASSWORD}@[::1/oauth/authorize"}
        target = Target(login_302(), discovery=hostile)
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and exc.value.phase == "connect"
        assert "does not parse" in exc.value.message and PASSWORD not in str(exc.value)
        assert target.authorize == [] and sleeps == []

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

    def test_a_302_without_a_token_is_not_a_session_and_is_terminal(self):
        """INVERTED by the review of #289: the first version retried this (2 binds). The bind
        happened and the grant failed after it, so a second attempt is a second bind."""
        no_token = httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error=server_error"})
        target = Target(no_token, login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert len(target.authorize) == 1 and sleeps == [] and target.revokes == []
        assert exc.value.retryable is False and "server_error" in exc.value.message

    def test_a_hostile_location_never_stands_between_the_mint_and_the_revoke(self):
        """Confirmation pass (Codex, measured `authorize=1 DELETE=0`): `urlsplit` raised on the
        malformed URL before the token was read, so a minted token was never named and never
        revoked. The header is split on its first `#` and the rest of the URL is never validated.

        THE STRING IS THE MEASURED ONE. `https://example.com]/…` is delivered by httpx as a 302 and
        makes `urlsplit` raise `Invalid IPv6 URL`; `https://[::1/…` is refused by httpx itself
        (`RemoteProtocolError: Invalid URL in location header`) inside `_send_handling_redirects`,
        which builds the redirect request even with `follow_redirects=False` — a token minted
        behind such a header is one this process never sees (the spec records the limit)."""
        hostile = f"https://example.com]/oauth/token/implicit#access_token={TOKEN}&expires_in=3600"
        target = Target(httpx.Response(302, headers={"Location": hostile}))
        with make(target)[0] as s:
            assert s.token == TOKEN and s.expires_in == 3600
        assert len(target.revokes) == 1 and target.requests[-1].method == "DELETE"
        unusable = f"https://example.com]/oauth/token/implicit#access_token={TOKEN}&expires_in=soon"
        target = Target(httpx.Response(302, headers={"Location": unusable}))
        fl, _ = make(target)
        with pytest.raises(LoginError):
            with fl:
                pass
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        no_token = Target(httpx.Response(302, headers={"Location": "https://a[b/x#error=server_error"}))
        with pytest.raises(LoginError) as exc:
            with make(no_token)[0]:
                pass
        assert "server_error" in exc.value.message and no_token.revokes == []

    def test_an_expiry_beyond_int32_is_bounded_revoked_once_and_terminal(self):
        """Review of #289, all three seats: 999999999999999 passed `int()` and the `<= 0` guard,
        then overflowed the instant arithmetic with an OverflowError that escaped `__enter__` —
        and the minted token was never revoked."""
        target = Target(login_302(expires_in="999999999999999"), login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and str(MAX_EXPIRES_IN) in exc.value.message
        assert len(target.authorize) == 1 and sleeps == [] and fl.session is None
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        with make(Target(login_302(expires_in=str(MAX_EXPIRES_IN))))[0] as s:
            assert s.expires_in == MAX_EXPIRES_IN and s.expires_at_iso.endswith("Z")
        with pytest.raises(LoginError):
            with make(Target(login_302(expires_in=str(MAX_EXPIRES_IN + 1))))[0]:
                pass

    def test_a_token_without_a_usable_expiry_is_revoked_at_once_and_not_retried(self):
        target = Target(login_302(expires_in="soon"), login_302())
        fl, sleeps = make(target)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        assert exc.value.retryable is False and exc.value.phase == "credential"
        assert len(target.authorize) == 1 and sleeps == [] and fl.session is None
        assert [r.url.path for r in target.revokes] == [f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"]
        assert "attempted once" in exc.value.message, "the message states the attempt, never a result it cannot know"


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

    def test_a_non_utc_clock_is_normalised_and_a_naive_one_refused(self):
        """Review of #289, Codex: an injected clock in another zone produced a `Z`-suffixed string
        that was not UTC."""
        chicago = T0.astimezone(timezone(timedelta(hours=-5)))
        assert chicago.hour == 7
        with make(Target(login_302(expires_in="3600")), clock=lambda: chicago)[0] as s:
            assert s.obtained_at == T0 and s.obtained_at.utcoffset() == timedelta(0)
            assert s.expires_at_iso == "2026-09-21T13:00:00Z"
        target = Target(login_302())
        with pytest.raises(ValueError, match="aware"):
            with make(target, clock=lambda: T0.replace(tzinfo=None))[0]:
                pass
        assert target.requests == [], "a naive clock is refused before anything is minted"
        with pytest.raises(ValueError, match="aware"):
            FleetSession(cluster="c", account="a", token=TOKEN, obtained_at=T0.replace(tzinfo=None),
                         expires_in=1, issuer=OAUTH, attempts=1)

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

    def test_a_token_is_never_abandoned_whatever_raises_after_it_was_minted(self, monkeypatch):
        """Review of #289: the invariant is "a minted token is never abandoned", and it must hold for
        exceptions nobody predicted — here a KeyboardInterrupt inside the success line's emit."""
        real_event = fleetlogin.event

        def interrupted(log, level, name, **fields):
            if name == "fleet-login":
                raise KeyboardInterrupt()
            real_event(log, level, name, **fields)

        monkeypatch.setattr(fleetlogin, "event", interrupted)
        target = Target(login_302())
        fl, _ = make(target)
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert fl.session is None
        assert len(target.revokes) == 1, "revocation attempted exactly once"
        assert target.requests[-1].url.path == f"{USER_TOKEN_API}/{token_object_name(TOKEN)}"
        # ... and from inside the interval between the response and the session (confirmation
        # pass, Codex: the first version raised only from the success line).
        monkeypatch.setattr(fleetlogin, "event", real_event)
        target = Target(login_302())
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_expiry_from", lambda fragment, endpoint: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):
            with fl:
                pass
        assert fl.session is None and len(target.revokes) == 1

    def test_a_failure_during_cleanup_never_replaces_the_original_exception(self, monkeypatch, caplog):
        """Confirmation pass (Codex: `raised=RuntimeError original=Marker`). The revoke's own
        failure is surfaced as a line and the body's exception is the one that propagates."""
        class BodyError(Exception):
            pass

        target = Target(login_302())
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_revoke", lambda token: (_ for _ in ()).throw(RuntimeError("cleanup broke")))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(BodyError):
                with fl:
                    raise BodyError()
        assert fl.revoked is False
        assert "cleanup broke" in lines(caplog, "fleet-logout-failed")[0]
        # the same inside the login's own guard
        target = Target(login_302(expires_in="soon"))
        fl, _ = make(target)
        monkeypatch.setattr(fl, "_revoke", lambda token: (_ for _ in ()).throw(RuntimeError("cleanup broke")))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError):
                with fl:
                    pass
        assert len(lines(caplog, "fleet-logout-failed")) == 2

    def test_a_revoke_that_failed_is_surfaced_never_reported_as_revoked(self, caplog):
        """Confirmation pass (Codex: `revoke-500: DELETE=1 caller_says_revoked=True`). The invariant
        is that revocation is ATTEMPTED exactly once and a failure is surfaced — `revoked` is False,
        the line says so — never that the object is gone."""
        for status, expected in ((200, True), (404, True), (500, False), (401, False)):
            target = Target(login_302(), revoke=httpx.Response(status, text="answer"))
            fl, _ = make(target)
            with caplog.at_level(logging.WARNING):
                with fl:
                    pass
            assert fl.revoked is expected, status
            assert len(target.revokes) == 1, "revocation attempted exactly once"
        assert len(lines(caplog, "fleet-logout-failed")) == 2
        target = Target(login_302(expires_in="soon"), revoke=httpx.Response(500, text="oops"))
        fl, _ = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert "attempted once" in exc.value.message and "was revoked" not in exc.value.message
        assert len(target.revokes) == 1 and len(lines(caplog, "fleet-logout-failed")) == 3
        assert fl.revoked is None, "nothing was handed to the caller, so nothing was revoked on exit"

    def test_the_object_name_is_the_measured_derivation(self):
        """PINNED TO A LITERAL, never regenerated from the code under test (review of #289, Cursor
        and OB1-lite: the first version recomputed the formula, so a wrong formula — and every
        DELETE answering 404 while the suite stayed green — would have passed). The value came from
        `printf '%s' 'testsecret123' | openssl dgst -sha256 -binary | base64 | tr '+/' '-_' | tr -d '='`
        and was confirmed against a live OAuthAccessToken object on the reference cluster."""
        assert token_object_name("sha256~testsecret123") == "sha256~AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY"
        assert token_object_name("legacy-token-value") == "legacy-token-value"

    def test_an_already_gone_token_is_not_a_failure(self, caplog):
        """INVERTED for 401 by the review of #289 (Codex): only a 404 means gone."""
        target = Target(login_302(), revoke=httpx.Response(404, text="gone"))
        with caplog.at_level(logging.INFO):
            with make(target)[0]:
                pass
        assert lines(caplog, "fleet-logout-failed") == []
        assert "outcome=already-gone" in lines(caplog, "fleet-logout")[0]

    def test_a_401_on_the_revoke_is_a_failure_not_already_gone(self, caplog):
        """A 401 proves the DELETE was unauthenticated and nothing about the object, which may be
        alive; logging a successful logout for it would be a lie the count would later expose."""
        target = Target(login_302(), revoke=httpx.Response(401, text="Unauthorized"))
        with caplog.at_level(logging.INFO):
            with make(target)[0]:
                pass
        assert lines(caplog, "fleet-logout") == []
        line = lines(caplog, "fleet-logout-failed")[0]
        assert "outcome=auth_failed" in line and "phase=credential" in line and "may still exist" in line
        assert f"token={token_object_name(TOKEN)}" in line and "cluster-admin" in line
        refused = Target(login_302(), revoke=httpx.Response(403, text="Forbidden"))
        with caplog.at_level(logging.INFO):
            with make(refused)[0]:
                pass
        assert "revoke refused" in lines(caplog, "fleet-logout-failed")[1] and "outcome=unreachable" in lines(caplog, "fleet-logout-failed")[1]

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

    def test_a_password_that_is_literally_basic_still_classifies_the_refusal(self, caplog):
        """Confirmation pass (Codex): P1-2's scrub ran BEFORE the challenge was classified, so a
        password of `Basic` redacted a genuine refusal into `unreachable`. Decide, then redact."""
        target = Target(refused_401())
        fl, _ = make(target, password="Basic")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert exc.value.outcome == AUTH_FAILED and len(target.authorize) == 1
        assert len(lines(caplog, "fleet-login-refused")) == 1
        assert "Basic" not in exc.value.message and "<redacted> realm" in exc.value.message

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
        lambda request: httpx.ConnectTimeout("timed out connecting"),
        lambda request: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
                                           "self-signed certificate in certificate chain"),
    ], ids=["refused-socket", "connect-timeout", "tls-verify"])
    def test_a_target_that_never_took_the_request_is_retried_with_exponential_backoff(self, transient, caplog):
        """The only retryable failures on the authorize step: the socket never opened or the TLS
        handshake failed, so the password bytes were provably never written. (The first version of
        this test also retried a read timeout and a 503 — INVERTED below, review of #289.)"""
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

    @pytest.mark.parametrize("answer", [
        lambda request: httpx.ReadTimeout("timed out"),
        lambda request: httpx.WriteError("connection reset while writing"),
        lambda request: httpx.ReadError("connection reset"),
        lambda request: httpx.RemoteProtocolError("illegal status line"),
        httpx.Response(200, text="<html>a proxy answered</html>"),
        httpx.Response(403, text="forbidden"),
        httpx.Response(429, text="slow down"),
        httpx.Response(500, text="Internal Server Error"),
        httpx.Response(502, text="Bad Gateway"),
        httpx.Response(503, text="oauth-server unavailable"),
        httpx.Response(504, text="Gateway Timeout"),
    ], ids=["read-timeout", "write-error", "read-error", "remote-protocol", "http-200", "http-403", "http-429",
            "http-500", "http-502", "http-503", "http-504"])
    def test_once_the_password_is_on_the_wire_every_answer_is_terminal(self, answer, caplog):
        """Review of #289 (Codex and Cursor; OB1-lite's narrower set rejected): the oauth-server
        answers EVERY directory result but 48/49 with a 500 — a locked account's code 19 included —
        so a "5xx is transient" rule retries hardest exactly when the account is locked; a 504 or
        502 means the upstream RECEIVED the request; a read timeout means it was written."""
        target = Target(answer, login_302())
        fl, sleeps = make(target)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert len(target.authorize) == 1, "the password was sent again"
        assert sleeps == [] and target.revokes == [] and len(target.answers) == 1
        assert exc.value.retryable is False and exc.value.outcome == UNREACHABLE
        assert lines(caplog, "fleet-login-refused") == []
        line = lines(caplog, "fleet-login-failed")[0]
        assert "not retried" in line and "attempt=" not in line
        if isinstance(answer, httpx.Response):
            assert exc.value.phase == "credential" and f"HTTP {answer.status_code}" in line

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


# ── R7, the split the reference lab cannot show ───────────────────────────────────────────────

OPENSSL = shutil.which("openssl")

_CA_CNF = """[req]
distinguished_name = dn
x509_extensions = ca
prompt = no
[dn]
CN = {name}
[ca]
basicConstraints = critical, CA:TRUE
keyUsage = critical, keyCertSign, cRLSign
subjectKeyIdentifier = hash
"""
_SERVER_EXT = """basicConstraints = CA:FALSE
subjectAltName = DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
keyUsage = critical, digitalSignature, keyEncipherment
"""


def _pki(root: pathlib.Path, name: str) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    """A CA with the extensions a real issuer carries — a bare `req -x509` lacks basicConstraints
    and keyUsage, and the failure then reads `CA cert does not include key usage extension`, a
    defect in the fixture rather than the real-world rejection — and a localhost server certificate
    it signed (SAN for localhost and 127.0.0.1, serverAuth). Returns (ca.crt, server.crt,
    server.key). Generated per test under tmp_path; nothing is committed."""
    cnf = root / f"ca{name}.cnf"
    cnf.write_text(_CA_CNF.format(name=f"test-ca-{name}"))
    ext = root / "server.ext"
    ext.write_text(_SERVER_EXT)
    ca_crt, ca_key = root / f"ca{name}.crt", root / f"ca{name}.key"
    srv_crt, srv_key, csr = root / f"srv{name}.crt", root / f"srv{name}.key", root / f"srv{name}.csr"

    def run(*args: object) -> None:
        subprocess.run([OPENSSL, *map(str, args)], check=True, capture_output=True)

    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", ca_key, "-out", ca_crt, "-days", "2",
        "-config", cnf, "-subj", f"/CN=test-ca-{name}")
    run("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", srv_key, "-out", csr, "-subj", "/CN=localhost")
    run("x509", "-req", "-in", csr, "-CA", ca_crt, "-CAkey", ca_key, "-CAcreateserial", "-out", srv_crt,
        "-days", "2", "-extfile", ext)
    return ca_crt, srv_crt, srv_key


class _QuietServer(http.server.ThreadingHTTPServer):
    """A handshake a client refuses raises in the handler thread; that is the point, not noise."""

    def handle_error(self, request, client_address) -> None:
        pass


class _TlsServer:
    """One loopback HTTPS server on its own thread."""

    def __init__(self, crt: pathlib.Path, key: pathlib.Path, handler: type) -> None:
        self.server = _QuietServer(("127.0.0.1", 0), handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(crt), str(key))
        self.server.socket = ctx.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def split_estate(tmp_path):
    """CA A signs the API server and CA B signs the OAuth server — the shape of a customer cluster
    whose ingress is re-signed by an enterprise PKI — plus a record of every Authorization header
    the OAuth host received and of every discovery the API host answered. Two bundles: A alone, and
    A with B (the control)."""
    if OPENSSL is None:
        pytest.skip("openssl is not on PATH; the split-CA fixture generates its certificates with it")
    ca_a, api_crt, api_key = _pki(tmp_path, "A")
    ca_b, oauth_crt, oauth_key = _pki(tmp_path, "B")
    seen: dict = {"discovery": 0, "authorization": []}

    class OAuthHost(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["authorization"].append(self.headers.get("Authorization"))
            self.send_response(302)
            self.send_header("Location", "https://localhost/oauth/token/implicit#error=fixture")
            self.end_headers()

        def log_message(self, *args):
            pass

    oauth = _TlsServer(oauth_crt, oauth_key, OAuthHost)
    document = json.dumps({"issuer": f"https://localhost:{oauth.port}",
                           "authorization_endpoint": f"https://localhost:{oauth.port}/oauth/authorize"}).encode()

    class ApiHost(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["discovery"] += 1
            self.send_response(200 if self.path == DISCOVERY_PATH else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(document if self.path == DISCOVERY_PATH else b"{}")

        def log_message(self, *args):
            pass

    api = _TlsServer(api_crt, api_key, ApiHost)
    api_only = tmp_path / "api-only.crt"
    api_only.write_text(ca_a.read_text())
    both = tmp_path / "both.crt"
    both.write_text(ca_a.read_text() + ca_b.read_text())
    try:
        yield SimpleNamespace(api_url=f"https://localhost:{api.port}", api_only=str(api_only), both=str(both), seen=seen)
    finally:
        oauth.close()
        api.close()


class TestTheSplitCATheLabCannotShow:
    """The reference lab is structurally blind to this (SPEC_S4a §2.1): CRC's kube-root-ca.crt
    carries six certificates and two of them are the ingress leaf and the ingress CA, so an
    API-only bundle verifies the OAuth host too. On a customer cluster whose ingress is re-signed by
    an enterprise PKI it will not, and the login must fail at the authorize step WITHOUT the
    credential reaching the host. `curl` on a Mac gives a false pass here (the system keychain);
    Python's ssl is what the dashboard uses and what this drives — two real TLS servers, no mock."""

    POLICY = RetryPolicy(attempts=2, base_seconds=0.01)

    def test_an_api_only_bundle_never_sends_the_credential_to_an_ingress_signed_oauth_host(self, split_estate, caplog):
        cluster = ClusterConfig("split", split_estate.api_url, ca_bundle_file=split_estate.api_only)
        fl = FleetLogin(cluster, USER, PASSWORD, policy=self.POLICY)
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        # 1. the point: the credential never reached the OAuth host
        assert split_estate.seen["authorization"] == [], "the credential reached the OAuth host"
        # 2. discovery succeeded first, so this proves the SPLIT and not merely a bad bundle
        assert split_estate.seen["discovery"] >= 1, "discovery failed: the test would pass for the wrong reason"
        # 3. a TLS failure before the password was written is the one class that still retries
        assert exc.value.phase == "tls" and exc.value.outcome == UNREACHABLE and exc.value.retryable is True
        assert exc.value.attempts == 2
        assert "unable to get local issuer certificate" in exc.value.message
        # 4. no password anywhere
        whole = "\n".join(caplog.messages)
        assert PASSWORD not in str(exc.value) and PASSWORD not in whole
        # 5. the gave_up action names the ingress CA
        last = lines(caplog, "fleet-login-failed")[-1]
        assert "gave_up=true" in last and "attempt=2/2" in last and "INGRESS CA" in last and "tls=caBundleFile" in last

    def test_the_control_a_bundle_with_both_cas_reaches_the_oauth_host(self, split_estate):
        """Without this, zero hits cannot be told from a broken fixture."""
        cluster = ClusterConfig("split", split_estate.api_url, ca_bundle_file=split_estate.both)
        fl = FleetLogin(cluster, USER, PASSWORD, policy=self.POLICY)
        with pytest.raises(LoginError) as exc:
            with fl:
                pass
        headers = split_estate.seen["authorization"]
        assert len(headers) == 1 and headers[0].startswith("Basic "), headers
        assert exc.value.retryable is False and exc.value.phase == "credential", "a 302 without a token is terminal"


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

    def _drive_everything(self, caplog) -> list[LoginError]:
        """Every event, and the password planted in EVERY remote-controlled field: the body, the
        Www-Authenticate challenge, the Location error query, the discovery endpoint's userinfo,
        expires_in, and a transport error's text (review of #289: three raise sites quoted a field
        unscrubbed, so the log was clean and `str(exc)` — which #284 will put on the page — was not)."""
        errors: list[LoginError] = []

        def failing(target, **kw):
            with pytest.raises(LoginError) as exc:
                with make(target, **kw)[0]:
                    pass
            errors.append(exc.value)

        with caplog.at_level(logging.DEBUG):
            failing(Target(refused_401(body=f"denied pw={PASSWORD}")))                     # fleet-login-refused
            failing(Target(httpx.Response(401, headers={"Www-Authenticate": f'Basic realm="{PASSWORD}"'})))
            echo = lambda request: httpx.ConnectError(f"connect to https://{USER}:{PASSWORD}@host failed")
            failing(Target(echo, echo, echo, echo, echo))                                   # retried, gave up
            failing(Target(httpx.Response(302, headers={
                "Location": f"{OAUTH}/oauth/token/implicit#error={PASSWORD}&error_description={PASSWORD}"})))
            failing(Target(login_302(), discovery={
                "authorization_endpoint": f"https://{USER}:{PASSWORD}@oauth.example.com/oauth/authorize"}))
            failing(Target(login_302(), discovery={                                         # does not parse
                "authorization_endpoint": f"https://{USER}:{PASSWORD}@[::1/oauth/authorize"}))
            failing(Target(httpx.Response(401, text=f"csrf pw={PASSWORD}")))                # not a refusal, stopped
            failing(Target(login_302(expires_in=f"{PASSWORD}")))                            # revoke inside the login
            failing(Target(httpx.Response(503, text=f"down pw={PASSWORD}")))                # terminal HTTP answer
            failing(Target(lambda request: httpx.ReadTimeout(f"timed out pw={PASSWORD}")))  # terminal transport
            planted_issuer = {"issuer": f"https://{PASSWORD}.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
            with make(Target(login_302(), discovery=planted_issuer))[0] as session:         # fleet-login, fleet-logout
                assert PASSWORD not in session.issuer and "<redacted>" in session.issuer
            with make(Target(login_302(), revoke=httpx.Response(500, text=f"echo {TOKEN} {PASSWORD}")))[0]:
                pass                                                                        # fleet-logout-failed
        return errors

    def test_every_new_log_path_is_driven_and_none_leaks(self, caplog):
        self._drive_everything(caplog)
        whole = "\n".join(caplog.messages)
        assert PASSWORD not in whole, "the password reached the log"
        assert TOKEN not in whole, "the token reached the log"
        assert "<redacted>" in whole
        seen = {m.split()[0] for m in caplog.messages if m.startswith("fleet-")}
        assert seen == set(EVENTS), f"driven {sorted(seen)}, declared {sorted(EVENTS)}"

    def test_the_error_handed_to_the_caller_carries_no_password(self, caplog):
        errors = self._drive_everything(caplog)
        assert len(errors) == 10
        for exc in errors:
            assert PASSWORD not in exc.message and PASSWORD not in str(exc), exc.message
            assert TOKEN not in exc.message

    def test_a_password_shorter_than_the_shared_floors_is_still_redacted(self, caplog):
        """Confirmation pass (Codex): `events.redact` floors at 4 and `kube.redact_text` at 8, so a
        three-character password reached the message AND the log. The floors are theirs and stay;
        the module scrubs the credential it holds regardless of length."""
        target = Target(refused_401(body="denied pw=abc"))
        fl, _ = make(target, password="abc")
        with caplog.at_level(logging.WARNING):
            with pytest.raises(LoginError) as exc:
                with fl:
                    pass
        assert "pw=abc" not in exc.value.message and "pw=<redacted>" in exc.value.message
        assert "pw=abc" not in "\n".join(caplog.messages)

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
