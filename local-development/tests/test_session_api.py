from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd import kube
from gsd.api import ACCESS_TOKEN_HEADER, build_app
from gsd.config import Settings
from gsd.kube import (
    OAUTHACCESSTOKEN_API,
    oauth_token_object_name,
    revoke_oauth_access_token,
    self_cluster_client,
)
from gsd.store import Store


def _client(tmp_path, **settings_kw):
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "gsd.db"), **settings_kw), run_poller=False)
    )


class TestWhoamiSession:
    def test_logout_and_session_are_offered_behind_the_proxy(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["authenticated"] is True
            # OUR route, not the proxy's: a link straight at <prefix>/sign_out would end
            # the session while silently skipping the token revocation.
            assert body["logout_url"] == "/sign-out"
            assert body["proxy_logout_url"] == "/oauth/sign_out"
            assert body["session"] == {
                "cookie_expire_seconds": 14400,
                "cookie_refresh_seconds": 0,
            }

    def test_the_dead_session_exit_follows_the_configured_prefix(self, tmp_path):
        """The proxy's routes hang off --proxy-prefix, so the dead-session exit is composed
        from config rather than hardcoded — a hardcoded /oauth would 404 into the dashboard
        the moment the prefix changed, which reads as a logout that silently did nothing."""
        with _client(tmp_path, oauth_proxy_enabled=True, oauth_proxy_prefix="/gate") as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["proxy_logout_url"] == "/gate/sign_out"
            # The revoking route is the app's own and does not move with the prefix.
            assert body["logout_url"] == "/sign-out"

    def test_the_configured_durations_are_the_ones_reported(self, tmp_path):
        """whoami restates config; it must not normalise, clamp or invent."""
        with _client(tmp_path, oauth_proxy_enabled=True,
                     session_cookie_expire_seconds=600,
                     session_cookie_refresh_seconds=60) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
            }

    def test_nothing_is_offered_when_the_proxy_is_off(self, tmp_path):
        """No proxy means no session exists to end and no idle timeout anyone enforces.
        A logout link or a countdown here would claim a control that is not there — and the
        identity beside them would be caller-supplied anyway."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["proxy_logout_url"] is None
            assert body["session"] is None

    def test_nothing_is_offered_to_an_anonymous_request(self, tmp_path):
        """Proxy on but no identity header — there is no session to describe, so none is."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami").json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["proxy_logout_url"] is None
            assert body["session"] is None


class TestTokenObjectName:
    """The console's tokenToObjectName derivation, reproduced exactly.

    The lab verified the formula end to end — the derived name resolved a real
    OAuthAccessToken object (docs/design-drafts/05-upstream-reference.md §2) — so these
    vectors pin the IMPLEMENTATION to that verified formula, not to a re-derivation.
    """

    # sha256("abc") is the classic NIST vector; its digest's STANDARD base64 is
    # "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=", so this single expectation proves all
    # three encoding choices at once: URL-safe alphabet (+ -> -, / -> _) and no padding.
    def test_prefix_stripped_hashed_and_encoded_url_safe_without_padding(self):
        assert (oauth_token_object_name("sha256~abc")
                == "sha256~ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD_YfIAFa0")

    def test_a_prefixless_token_hashes_the_whole_string(self):
        """Go's TrimPrefix is a no-op when the prefix is absent (pre-4.6 opaque tokens);
        removeprefix must mirror that, not slice seven characters unconditionally."""
        assert oauth_token_object_name("abc") == oauth_token_object_name("sha256~abc")

    def test_the_name_is_always_a_legal_kubernetes_object_name(self):
        """43 base64url characters after the prefix, never the +, / or = that standard
        base64 would emit — those are not legal in an object name, which is the whole
        reason upstream chose RawURLEncoding."""
        name = oauth_token_object_name("d")  # digest chosen: its std base64 has + AND /
        assert name == "sha256~GKw-c0PwFokMUQ6T-TUmEWnZ4_VlQ2Qpgw-vCTT0-OQ"
        body = name.removeprefix("sha256~")
        assert len(body) == 43
        assert not set(body) & set("+/=")

    def test_the_secret_is_not_recoverable_from_the_name(self):
        """The name is a hash of the token, so logging or listing names can never leak a
        usable credential — the property the failure-path log lines rely on."""
        assert "abc" not in oauth_token_object_name("sha256~abc")


class TestSelfClusterClient:
    def test_targets_the_hosting_cluster_as_the_user(self):
        """The revocation goes to the API server that minted the session — the in-cluster
        service DNS name, never an entry from the observed-clusters list — and it carries
        the USER's token, which is what keeps the ServiceAccount free of write grants."""
        client = self_cluster_client("sha256~tok", timeout=5.0)
        try:
            assert str(client.base_url).startswith("https://kubernetes.default.svc")
            assert client.headers["authorization"] == "Bearer sha256~tok"
        finally:
            client.close()


class TestRevokeCall:
    """revoke_oauth_access_token: best-effort, never raises, never leaks the token."""

    TOKEN = "sha256~test-token-value"

    def _mock(self, handler):
        return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api")

    def test_deletes_exactly_the_derived_object(self):
        seen = {}

        def handler(request):
            seen["method"] = request.method
            seen["path"] = request.url.path
            return httpx.Response(200, json={"kind": "Status", "status": "Success"})

        with self._mock(handler) as client:
            revoked, why = revoke_oauth_access_token(client, self.TOKEN)
        assert revoked and why == "revoked"
        assert seen["method"] == "DELETE"
        expected = f"{OAUTHACCESSTOKEN_API}/{oauth_token_object_name(self.TOKEN)}"
        assert seen["path"] == expected
        # The raw token must never be spent as a path segment — only its hash.
        assert self.TOKEN.removeprefix("sha256~") not in seen["path"]

    def test_a_404_counts_as_revoked(self):
        """Another tab's sign-out winning the race reaches the same end state this call
        exists to reach; reporting it as failure would log a warning for a success."""
        with self._mock(lambda r: httpx.Response(404, json={"kind": "Status"})) as client:
            revoked, why = revoke_oauth_access_token(client, self.TOKEN)
        assert revoked and "404" in why

    @pytest.mark.parametrize("status", [401, 403, 500])
    def test_refusals_fail_softly_with_the_status_named(self, status):
        with self._mock(lambda r: httpx.Response(status, json={})) as client:
            revoked, why = revoke_oauth_access_token(client, self.TOKEN)
        assert revoked is False
        assert str(status) in why

    def test_an_unreachable_cluster_fails_softly(self):
        def handler(request):
            raise httpx.ConnectError("boom")

        with self._mock(handler) as client:
            revoked, why = revoke_oauth_access_token(client, self.TOKEN)
        assert revoked is False
        assert "ConnectError" in why

    def test_the_failure_detail_never_carries_the_token(self):
        """The `why` strings reach log lines, so they are built from status codes and
        exception type names only — an httpx message can embed the request URL."""
        def handler(request):
            raise httpx.ConnectTimeout(f"timed out on {request.url}")

        with self._mock(handler) as client:
            _, why = revoke_oauth_access_token(client, self.TOKEN)
        assert self.TOKEN not in why
        assert self.TOKEN.removeprefix("sha256~") not in why


class TestSignOutEndpoint:
    """GET /sign-out: revoke as the user, then hand the browser to the proxy's sign_out."""

    TOKEN = "sha256~endpoint-token"

    @pytest.fixture()
    def revocations(self, monkeypatch):
        """Route the endpoint's cluster call into a MockTransport, recording each DELETE.

        Patched at self_cluster_client, the endpoint's one seam to the network, so the
        endpoint's own logic — header reading, ordering, redirect — runs unmodified.
        """
        state = {"calls": [], "status": 200}

        def fake_client(token, timeout):
            def handler(request):
                state["calls"].append({"path": request.url.path, "token": token})
                return httpx.Response(state["status"], json={"kind": "Status"})

            return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api")

        monkeypatch.setattr(kube, "self_cluster_client", fake_client)
        return state

    def test_revokes_the_forwarded_token_then_redirects_to_the_proxy(self, tmp_path, revocations):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            r = c.get("/sign-out", headers={ACCESS_TOKEN_HEADER: self.TOKEN},
                      follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/oauth/sign_out"
        assert r.headers["cache-control"] == "no-store"
        assert revocations["calls"] == [{
            "path": f"{OAUTHACCESSTOKEN_API}/{oauth_token_object_name(self.TOKEN)}",
            "token": self.TOKEN,
        }]

    def test_the_redirect_follows_the_configured_prefix(self, tmp_path, revocations):
        with _client(tmp_path, oauth_proxy_enabled=True, oauth_proxy_prefix="/gate") as c:
            r = c.get("/sign-out", headers={ACCESS_TOKEN_HEADER: self.TOKEN},
                      follow_redirects=False)
        assert r.headers["location"] == "/gate/sign_out"

    @pytest.mark.parametrize("status", [401, 403, 404, 500])
    def test_a_failed_revocation_still_ends_the_session(self, tmp_path, revocations, status):
        """The exit is unconditional: whatever the API server answers, the browser is
        handed to the proxy's sign_out and the cookie dies. Blocking the exit on a
        revocation error would hold a user hostage to an API server hiccup."""
        revocations["status"] = status
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            r = c.get("/sign-out", headers={ACCESS_TOKEN_HEADER: self.TOKEN},
                      follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/oauth/sign_out"

    def test_no_forwarded_token_still_ends_the_session(self, tmp_path, monkeypatch, caplog):
        """A proxy running without -pass-access-token (a chart-version skew) must degrade
        to exactly the old behaviour — cookie cleared, token orphaned — and say so."""
        monkeypatch.setattr(kube, "self_cluster_client",
                            lambda *a, **k: pytest.fail("no token, so no cluster call"))
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            with caplog.at_level(logging.WARNING):
                r = c.get("/sign-out", follow_redirects=False)
        assert r.status_code == 303
        assert "pass-access-token" in caplog.text

    def test_refused_when_the_proxy_is_off(self, tmp_path, monkeypatch):
        """Without the proxy the token header is caller-supplied, and acting on it would
        let an unauthenticated caller aim a credentialed DELETE at the API server. Same
        trust boundary, same 403, as /api/dashboard/activity."""
        monkeypatch.setattr(kube, "self_cluster_client",
                            lambda *a, **k: pytest.fail("must not touch the cluster"))
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            r = c.get("/sign-out", headers={ACCESS_TOKEN_HEADER: self.TOKEN},
                      follow_redirects=False)
        assert r.status_code == 403

    def test_the_token_never_reaches_a_log_line(self, tmp_path, revocations, caplog):
        """The failure paths log status codes; the token is a live credential and the pod
        log is readable by anyone with pods/log in the namespace."""
        revocations["status"] = 403
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            with caplog.at_level(logging.DEBUG):
                c.get("/sign-out", headers={ACCESS_TOKEN_HEADER: self.TOKEN},
                      follow_redirects=False)
        assert self.TOKEN not in caplog.text
        assert self.TOKEN.removeprefix("sha256~") not in caplog.text


class TestSignedOutPage:
    def test_served_with_no_headers_at_all(self, tmp_path):
        """The proxy's -logout-url target: reached at the exact moment the session cookie
        was cleared, so it must depend on nothing the proxy would have added."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            r = c.get("/signed-out")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/html")

    def test_served_even_with_the_proxy_off(self, tmp_path):
        """Unreachable in that mode in practice, but it must not 500 on a mode check."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            assert c.get("/signed-out").status_code == 200

    def test_never_cached(self, tmp_path):
        """Same reasoning as index(): a stale copy after a redeploy would misdescribe what
        logout does — and its honest limits are this page's entire message."""
        with _client(tmp_path) as c:
            assert "no-cache" in c.get("/signed-out").headers["cache-control"]

    def test_wording_is_true_whether_or_not_revocation_happened(self, tmp_path):
        """Three arrivals share this page — revocation succeeded, revocation failed, and
        the expired-session exit that never attempts one — and a static, script-free page
        cannot tell them apart. So it must describe what sign-out ASKS FOR, never assert
        that a revocation happened."""
        with _client(tmp_path) as c:
            text = c.get("/signed-out").text.lower()
        assert "revoke" in text, "the page must say the sign-out requests revocation"
        assert "has been revoked" not in text and "was revoked" not in text, (
            "asserting a completed revocation would be false on two of the three arrivals"
        )

    def test_does_not_overclaim_a_cluster_signout(self, tmp_path):
        """Revoking the dashboard's token ends nothing else: console and oc sessions ride
        their own tokens, and behind an external IdP the upstream SSO session survives
        every mechanism this design has. A governance dashboard implying full sign-out
        would be worse than no logout button."""
        with _client(tmp_path) as c:
            text = c.get("/signed-out").text.lower()
        assert "console" in text and "oc" in text
        assert "separate" in text

    def test_stays_script_free_and_style_free(self, tmp_path):
        """The page renders while unauthenticated, so it ships no behaviour to attack and
        keeps the repo's no-inline-style rule; its only assets are the two the proxy's
        skipAuthRegex admits."""
        with _client(tmp_path) as c:
            text = c.get("/signed-out").text.lower()
        assert "<script" not in text and "<style" not in text

    def test_records_no_activity_even_with_forged_headers(self, tmp_path):
        """It is reachable unauthenticated, so its headers are caller-supplied by
        definition — the same trust boundary as /healthz, enforced by SKIP_AUTH_PATHS."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            c.get("/signed-out", headers={"X-Forwarded-User": "impostor",
                                          "X-GSD-Interaction": "1"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []
