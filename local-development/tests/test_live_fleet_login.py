"""Live proof of #283 against a real OAuth server: the session is obtained, its expiry is the
target's own, the token authenticates while the session is open and not after it closes, and the
OAuthAccessToken it minted is gone when the session closes.

Skipped unless the environment names a target and an account the TARGET's identity provider will
authenticate. On the reference cluster that is the htpasswd `developer` account — NEVER the LDAP
fleet account: a wrong password there is the lockout walk this module exists to prevent, and its
loginability is proven by `oc get user <name>`, not by logging in (SPEC_S4a, orchestrator's notes).

    GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 \\
    GSD_LIVE_LOGIN_USER=developer GSD_LIVE_LOGIN_PASSWORD=… \\
    GSD_LIVE_LOGIN_CA=/path/to/the/poller/ca.crt \\
    KUBECONFIG=~/.crc/machines/crc/kubeconfig \\
    .venv/bin/python -m pytest tests/test_live_fleet_login.py -v -s

With KUBECONFIG pointing at a cluster-admin session, `oauth_token_count` also reads the target's
OAuthAccessToken objects for that account and client before, during and after the session — the
count the review holds the "logs out by construction" claim to: during == before + 1 with the
session's own name among them, and after == before with the name gone. Without `oc`, or without
the grant, the count is None and only the token's own behaviour is asserted.

THE TOKEN OUTLIVES ITS OBJECT, BRIEFLY. Measured on the reference cluster (2026-09-21): the object
is absent from the list the moment the session closes, while the revoked token goes on answering
`users/~` with 200 for 121 s — the API server's token authenticator cache — and then 401. So the
token's death is WAITED for, up to GSD_LIVE_LOGIN_DEAD_WAIT seconds (default 180), and the count
is what proves the logout; the wait proves the cache empties.
"""

from __future__ import annotations

import json
import os
import subprocess
import time

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.fleetlogin import CHALLENGING_CLIENT, TOKEN_PREFIX, FleetLogin

API = os.environ.get("GSD_LIVE_LOGIN_API")
USER = os.environ.get("GSD_LIVE_LOGIN_USER")
PASSWORD = os.environ.get("GSD_LIVE_LOGIN_PASSWORD")
CA = os.environ.get("GSD_LIVE_LOGIN_CA")
DEAD_WAIT = float(os.environ.get("GSD_LIVE_LOGIN_DEAD_WAIT", "180"))
ME = "/apis/user.openshift.io/v1/users/~"

pytestmark = pytest.mark.skipif(
    not (API and USER and PASSWORD),
    reason="set GSD_LIVE_LOGIN_API, GSD_LIVE_LOGIN_USER and GSD_LIVE_LOGIN_PASSWORD to run the live fleet-login test",
)


def oauth_token_count(user: str) -> tuple[int, set[str]] | None:
    """(count, names) of the OAuthAccessToken objects `user` holds for the challenging client, read
    with `oc` through KUBECONFIG — a cluster-admin list, so None when `oc` is absent or refused."""
    try:
        run = subprocess.run(["oc", "get", "oauthaccesstokens", "-o", "json"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if run.returncode != 0:
        return None
    names = {i["metadata"]["name"] for i in json.loads(run.stdout)["items"]
             if i.get("userName") == user and i.get("clientName") == CHALLENGING_CLIENT}
    return len(names), names


def _cluster() -> ClusterConfig:
    return ClusterConfig("live", API, ca_bundle_file=CA) if CA else ClusterConfig("live", API)


def _whoami(token: str) -> httpx.Response:
    with httpx.Client(verify=_cluster().verify(), timeout=15.0) as client:
        return client.get(f"{API}{ME}", headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})


def test_the_session_is_obtained_and_revoked():
    before = oauth_token_count(USER)
    with FleetLogin(_cluster(), USER, PASSWORD) as session:
        assert session.token.startswith(TOKEN_PREFIX)
        assert session.expires_in > 0 and session.expires_at > session.obtained_at
        assert session.attempts == 1
        me = _whoami(session.token)
        assert me.status_code == 200 and me.json()["metadata"]["name"] == USER, me.text[:200]
        during = oauth_token_count(USER)
        if before is not None and during is not None:
            assert during[0] == before[0] + 1, (before[0], during[0])
            assert session.token_name in during[1] - before[1]
        print(f"\nlive: account={USER} issuer={session.issuer} expires_in={session.expires_in} "
              f"expires_at={session.expires_at_iso} token_name={session.token_name} "
              f"count_before={None if before is None else before[0]} "
              f"count_during={None if during is None else during[0]}")
    after = oauth_token_count(USER)
    if before is not None and after is not None:
        assert after[0] == before[0] and session.token_name not in after[1], (before[0], after[0])
        print(f"live: count_after={after[0]} (before={before[0]})")
    # The OBJECT is gone at once (above). The token itself keeps authenticating from the API server's
    # token cache for a window — 121 s measured on the reference cluster — so its death is waited for,
    # not asserted on the first request after the close.
    started = time.monotonic()
    while True:
        dead = _whoami(session.token)
        elapsed = time.monotonic() - started
        if dead.status_code == 401 or elapsed > DEAD_WAIT:
            break
        time.sleep(2)
    assert dead.status_code == 401, f"the token still authenticates {elapsed:.0f} s after the session closed: {dead.status_code}"
    print(f"live: the revoked token stopped authenticating after {elapsed:.0f} s (the API server's token cache)")
