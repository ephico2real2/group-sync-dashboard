from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings
from gsd.store import Store


def _visible(html: str) -> str:
    """The page's copy, lowercased, with HTML comments removed.

    Comments are stripped because they explain the wording's own history — including the
    phrases the assertions forbid — and a substring test over the raw file cannot tell an
    explanation from a claim made to the reader. A first version of these tests failed on the
    comment rather than the copy.
    """
    import re

    return re.sub(r"<!--.*?-->", "", html, flags=re.S).lower()


def _client(tmp_path, **settings_kw):
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "gsd.db"), **settings_kw), run_poller=False)
    )


class TestWhoamiSession:
    def test_logout_and_session_are_offered_behind_the_proxy(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["authenticated"] is True
            # The proxy's own sign_out, composed from the configured prefix. An app-side
            # route that revoked the token first was measured failing — a ServiceAccount
            # client's tokens carry user:info and user:check-access, which cannot delete —
            # so there is nothing for the app to add on the way out.
            assert body["logout_url"] == "/oauth/sign_out"
            assert body["session"] == {
                "cookie_expire_seconds": 14400,
                "cookie_refresh_seconds": 0,
                "idle_timeout": {"enabled": False},
            }

    def test_the_idle_timeout_is_restated_when_on_and_never_a_deadline(self, tmp_path):
        """Inputs to the page's model, like the cap: seconds and the warning, no expiry instant."""
        with _client(tmp_path, oauth_proxy_enabled=True, session_idle_timeout_enabled=True,
                     session_idle_timeout_seconds=900, session_idle_timeout_warning_seconds=45) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"]["idle_timeout"] == {
                "enabled": True, "seconds": 900, "warning_seconds": 45}
            assert body["logout_url"] == "/oauth/sign_out", "the URL the countdown ends at"

    def test_the_dead_session_exit_follows_the_configured_prefix(self, tmp_path):
        """The proxy's routes hang off --proxy-prefix, so the dead-session exit is composed
        from config rather than hardcoded — a hardcoded /oauth would 404 into the dashboard
        the moment the prefix changed, which reads as a logout that silently did nothing."""
        with _client(tmp_path, oauth_proxy_enabled=True, oauth_proxy_prefix="/gate") as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["logout_url"] == "/gate/sign_out", (
                "a hardcoded /oauth would 404 into the dashboard the moment the prefix "
                "changed, which reads as a logout that silently did nothing")

    def test_the_configured_durations_are_the_ones_reported(self, tmp_path):
        """whoami restates config; it must not normalise, clamp or invent."""
        with _client(tmp_path, oauth_proxy_enabled=True,
                     session_cookie_expire_seconds=600,
                     session_cookie_refresh_seconds=60) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
                "idle_timeout": {"enabled": False},
            }

    def test_nothing_is_offered_when_the_proxy_is_off(self, tmp_path):
        """No proxy means no session exists to end and no idle timeout anyone enforces.
        A logout link or a countdown here would claim a control that is not there — and the
        identity beside them would be caller-supplied anyway."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None

    def test_nothing_is_offered_to_an_anonymous_request(self, tmp_path):
        """Proxy on but no identity header — there is no session to describe, so none is."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami").json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None


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

    def test_it_does_not_claim_the_token_was_revoked(self, tmp_path):
        """Three arrivals share this page — a deliberate sign-out, an idle expiry, and the
        absolute cap — and a static, script-free page cannot tell them apart. It also cannot
        claim revocation at all: the app no longer attempts one, because a ServiceAccount
        client's token scope (user:info, user:check-access) cannot delete, measured as HTTP
        403 on the lab. What it must say instead is that the token OUTLIVES the session.
        """
        with _client(tmp_path) as c:
            text = _visible(c.get("/signed-out").text)
        assert "stays valid" in text, (
            "the reader is entitled to know the token outlives their session")
        for claim in ("has been revoked", "was revoked", "asks the cluster to revoke"):
            assert claim not in text, f"the page claims {claim!r}, which is no longer true"

    def test_does_not_overclaim_a_cluster_signout(self, tmp_path):
        """Clearing the dashboard's cookie ends nothing else: console and oc sessions ride
        their own tokens, and behind an external IdP the upstream SSO session survives every
        mechanism this design has. A governance dashboard implying a full sign-out would be
        worse than no logout button."""
        with _client(tmp_path) as c:
            text = _visible(c.get("/signed-out").text)
        assert "console" in text and "oc" in text
        assert "separate" in text
        assert "only this dashboard" in text

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
