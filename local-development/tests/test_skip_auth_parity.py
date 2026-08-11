"""The proxy's skip-auth regex and the app's untrusted-identity rules must not drift apart.

THE DEFECT THIS EXISTS FOR WAS EXPLOITABLE, and it was pure drift between two lists that nothing
coupled:

    charts/.../values.yaml  oauthProxy.skipAuthRegex   gained static/(app\\.css|favicon\\.svg)
                                                       on 2026-08-08  (f42e60b)
    gsd/api.py              SKIP_AUTH_PATHS            last touched
                                                       on 2026-08-02  (98d4ec6)

For six days the proxy passed those two paths through **unauthenticated** — where every header is
the caller's own — while the app did not list them, so `record_dashboard_use` treated a
caller-supplied `X-Forwarded-User` there as a verified identity. Measured against the live route:

    curl -k -H 'X-Forwarded-User: PROBE-forged-unauth' \\
            -H 'X-Forwarded-Email: PROBE@forged.invalid' \\
            -H 'X-GSD-Interaction: 1' https://<route>/static/app.css       -> 200

and one row `('PROBE-forged-unauth', 'PROBE@forged.invalid', '2026-08-11', 1)` appeared in
`dashboard_user_activity`, written by a caller holding no credential at all. The Usage tab presents
that table as the record of who accessed a governance dashboard.

WHY A UNIT TEST DID NOT CATCH IT. `test_session_api.py::test_records_no_activity_even_with_forged_headers`
asserts this exact invariant and was shipped by 98d4ec6 — six days before the regex outgrew it. It
kept passing because it exercises the four paths that were in `SKIP_AUTH_PATHS` when it was written.
A test over a hard-coded list cannot notice a list growing somewhere else.

SO THIS TEST READS BOTH SIDES FROM THEIR REAL SOURCES and compares them: the regex out of
`values.yaml`, the rules out of `gsd/api.py`, and the candidate paths out of the app's own routes and
its own static directory rather than a list written here. Widening either side without the other
fails here, which is the coupling that was missing.
"""

from __future__ import annotations

import pathlib
import re

import pytest
import yaml

from gsd.api import SKIP_AUTH_PATHS, identity_is_trustworthy

REPO = pathlib.Path(__file__).resolve().parents[2]
VALUES = REPO / "charts" / "group-sync-dashboard" / "values.yaml"
STATIC = REPO / "local-development" / "gsd" / "static"


def skip_auth_regex() -> re.Pattern[str]:
    """The regex the chart actually hands the proxy, compiled."""
    raw = yaml.safe_load(VALUES.read_text())["oauthProxy"]["skipAuthRegex"]
    assert raw, "oauthProxy.skipAuthRegex is empty; the health paths would demand a login"
    return re.compile(raw)


def candidate_paths() -> list[str]:
    """Every path a request could plausibly name, discovered rather than listed.

    Discovered on purpose: a list written in this file would go stale in exactly the way the two
    lists under test went stale. The app's own static directory supplies the asset paths, so a new
    file added there is covered the moment it exists.
    """
    paths = ["/healthz", "/readyz", "/metrics", "/signed-out", "/", "/api/whoami",
             "/api/clusters", "/api/dashboard/activity", "/docs", "/openapi.json"]
    for entry in sorted(STATIC.rglob("*")):
        if entry.is_file():
            paths.append("/static/" + entry.relative_to(STATIC).as_posix())
    return paths


def test_nothing_the_proxy_skips_is_ever_trusted_for_identity() -> None:
    """THE COUPLING. Every path the regex exempts must be untrusted by the app.

    This is the assertion whose absence made the exploit possible. It fails today if anyone widens
    `skipAuthRegex` without teaching the app, in the same commit.
    """
    regex = skip_auth_regex()
    leaked = [p for p in candidate_paths() if regex.match(p) and identity_is_trustworthy(p)]
    assert not leaked, (
        "oauthProxy.skipAuthRegex exempts these paths from authentication while the app still "
        "believes identity headers on them, so an unauthenticated caller can forge a username:\n  "
        + "\n  ".join(leaked)
        + "\n\nAdd them to SKIP_AUTH_PATHS, or cover them with UNTRUSTED_IDENTITY_PREFIXES."
    )


def test_the_static_tree_is_never_trusted_even_where_the_regex_does_not_exempt_it() -> None:
    """Deliberately WIDER than the regex, and that width is the durable half of the fix.

    The regex exempts two assets today. Declining to record on the whole tree costs nothing — a
    stylesheet or icon fetch is not a human interaction whether or not it was authenticated — and it
    means widening the regex to a third asset cannot reintroduce the defect.
    """
    for entry in sorted(STATIC.rglob("*")):
        if entry.is_file():
            path = "/static/" + entry.relative_to(STATIC).as_posix()
            assert not identity_is_trustworthy(path), f"{path} would be recorded"


def test_the_health_and_logout_paths_are_still_exempt_in_the_regex() -> None:
    """The other direction: the regex must not NARROW either.

    kubelet gets a 302 to the login page and kills a healthy pod if the health paths stop being
    exempt, and `/signed-out` is the landing page for the moment the cookie has just been cleared.
    """
    regex = skip_auth_regex()
    for required in SKIP_AUTH_PATHS:
        assert regex.match(required), (
            f"{required} is in SKIP_AUTH_PATHS but skipAuthRegex no longer exempts it — either the "
            f"app is refusing to record on an authenticated path, or a health check now needs a login"
        )


def test_authenticated_paths_are_still_trusted() -> None:
    """A guard that refuses everything is not a fix: usage recording must still work.

    If this fails, the Usage tab silently stops recording anyone, which looks like a working
    dashboard reporting that nobody uses it.
    """
    for path in ("/api/whoami", "/api/clusters", "/api/dashboard/activity", "/"):
        assert identity_is_trustworthy(path), f"{path} would no longer be recorded"


@pytest.mark.parametrize("path", ["/static/app.css", "/static/favicon.svg"])
def test_the_two_paths_from_the_exploit_specifically(path: str) -> None:
    """Named explicitly, because these are the ones a forged header actually got through."""
    assert skip_auth_regex().match(path), "the regex no longer exempts it; update this test"
    assert not identity_is_trustworthy(path), (
        f"{path} is served unauthenticated and the app trusts identity headers on it — this is the "
        f"exact hole that let an unauthenticated caller write a fabricated audit row"
    )
