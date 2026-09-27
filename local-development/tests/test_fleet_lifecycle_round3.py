"""Round 3 (#419): a late self-login success must respect an intervening suspension."""
from datetime import datetime, timedelta

import pytest

from gsd.fleetstate import PREFIX, claim_seconds
from test_fleet_lifecycle import (
    PASSWORD, T0, TOKEN_2, TOKEN_3, USER, LeaseHost, login_302,
    process, self_login, sessions,
)
from test_fleet_lookup import wire  # noqa: F401


@pytest.mark.parametrize("renewal", [False, True], ids=["initial", "renewal"])
def test_late_success_cannot_install_over_a_sweep_suspension(tmp_path, monkeypatch, wire, renewal):
    """C3: the discovery thread parks A while A's authorize is still in flight."""
    host = LeaseHost()
    p = process(tmp_path, monkeypatch, host, self_login("a"))
    now = [T0]
    s = sessions(p, now)
    cluster = p.settings.cluster("a")
    if renewal:
        wire.answers = [login_302(token=TOKEN_3, expires_in="3600")]
        assert s.credential_for(cluster) is not None
        now[0] += timedelta(seconds=2700)

    def sweep_during_authorize(request):
        # The authorize is paused beyond its own window while discovery keeps running.
        now[0] += timedelta(seconds=claim_seconds(p.settings) + 2)

        class SweepClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now[0]

        monkeypatch.setattr("gsd.poller.datetime", SweepClock)
        p._ping_accounts()
        assert s.view("a")["state"] == "suspended"
        assert p._credential_gate.account_refusal(USER, PASSWORD) is not None
        return login_302(token=TOKEN_2)

    wire.answers = [sweep_during_authorize]
    credential = s.credential_for(cluster)
    following = s.credential_for(cluster)
    print(f"LATE-SUCCESS renewal={renewal}: usable={credential is not None}, "
          f"next_cycle_usable={following is not None}, state={s.view('a')['state']}, "
          f"authorizes={len(wire.authorize)}, revokes={len(wire.revokes)}")
    assert credential is None, "late success installed a token after the account was parked"
    assert s.view("a")["state"] == "suspended"
    assert following is None
    assert any(f.code == "self-login-suspended" for f in p.settings.cluster_registry.findings())
    assert PREFIX + "refused" not in host.leases.annotations()
    assert len(wire.authorize) == 1 + int(renewal)
    assert len(wire.revokes) == 1 + int(renewal), "the rejected late token still needs its one revoke"
