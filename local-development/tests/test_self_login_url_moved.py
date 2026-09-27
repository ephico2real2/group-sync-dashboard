"""A self-login session is presented only to the URL it was minted for (#285, the code review of #419, N1)."""
from __future__ import annotations

import dataclasses

from test_fleet_lookup import wire  # noqa: F401
from test_fleet_login import T0, TOKEN, login_302
from test_fleet_lifecycle import TOKEN_2, LeaseHost, process, self_login, sessions


def test_a_session_is_never_presented_to_a_url_it_was_not_minted_for(tmp_path, monkeypatch, wire):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"))
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600"), login_302(expires_in="3600", token=TOKEN_2)]
    first = s.credential_for(p.settings.cluster("sl"))
    assert first.token_value == TOKEN and first.api_url == "https://api.sl.example.com:6443"
    # The stanza's server is edited in place (a Secret- or ConfigMap-declared cluster: no pod roll, same thread).
    moved = dataclasses.replace(p.settings.cluster("sl"), api_url="https://api.elsewhere.example.com:6443")
    polled = s.credential_for(moved)
    assert polled is None or polled.token_value != TOKEN, \
        f"the session minted by {first.api_url} was handed to the poll against {moved.api_url}"
    assert [r.headers["authorization"] for r in wire.revokes] == [f"Bearer {TOKEN}"], "revoked where it was minted"
    assert wire.revokes[0].url.host == "api.sl.example.com"
