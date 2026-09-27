"""The walk's password scope: which ACCOUNT each walk arrangement presents the walk's password as, measured in
authorize requests on the code the lab runs (`local-development/gsd/` is byte-identical to the deployed 1.0.0
commit `05e32c8394`: `git diff 05e32c8394 22a485c -- local-development/gsd` is empty).

Why this exists. The fleet password Secret is PROCESS-WIDE: `gsd/fleetlookup.py#fleet_password` reads
`settings.fleet_password_secret_*` for every account, and `ldapConnectionBootstrap` changes only the username
(`gsd/fleetlookup.py#fleet_account`). The daily ping pings every account that a retrieved cluster's Secret records
(`gsd/poller.py#_ping_accounts`, `c.lookup_account`), with that one password. On the lab, `gsd-cluster-shared-rnd`
records the fleet account, and the fleet account's Lease shows the product's own ping of it
(`evidence/start-leases.txt`, `evidence/start-shared-rnd-secret.txt`).

No real account and no real password appear here: FLEET and WALK are placeholders, and the target is S4a's fake.
How to run it: this folder's README, "The finding"; the recorded run is evidence/hermetic-password-scope.txt."""

from __future__ import annotations

import base64
import dataclasses
from datetime import timedelta

import pytest

from gsd.config import ClusterConfig
from gsd.fleetstate import lease_name
from gsd.kube import OK
from test_fleet_lifecycle import LeaseHost, process, retrieved, sessions
from test_fleet_login import T0, login_302, refused_401
from test_fleet_lookup import wire  # noqa: F401  (the fixture)

FLEET = "fleet-bind-account"          # stands for the lab's fleet account
WALK = "walk-developer"               # stands for the htpasswd `developer`
FLEET_PASSWORD, WALK_PASSWORD, WRONG = "fleet-placeholder-1", "walk-placeholder-2", "walk-wrong-3"
TOKENS = [f"sha256~V2Fsa1Nlc3Npb25Ub2tlbk51bWJlcj{n:02d}" for n in range(12)]


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize request, decoded from its Basic header, in order."""
    out = []
    for request in target.authorize:
        user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
        out.append((user, password))
    return out


def shared_rnd():
    """The lab's shared-rnd: retrieved by the lookup, its Secret recording the fleet account."""
    return dataclasses.replace(retrieved("shared-rnd"), lookup_account=FLEET)


def lab_as_found(tmp_path, monkeypatch, host) -> None:
    """The fleet account's Lease as the lab holds it: the product pinged it once with the fleet account's own
    password, and a second cadence inside the interval does not ping again."""
    host.rotate(FLEET_PASSWORD)
    lab = process(tmp_path, monkeypatch, host, discovered=[shared_rnd()], name="lab", fleet_account_username=FLEET)
    lab._ping_accounts()
    lab._ping_accounts()


@pytest.mark.parametrize("rotation_back", ["same-process", "after-a-restart"])
def test_spec_3_12_steps_2_and_3_present_wrong_passwords_as_the_fleet_account(tmp_path, monkeypatch, wire,
                                                                             rotation_back):
    """SPEC_S4c §3.12 step 2 (the password Secret holding the walk account's password, the ping low) and step 3
    (rotated to a wrong password, then back), with shared-rnd retrieved by the fleet account as on the lab. In one
    process the rotation back is held by the in-memory gate (#315's refused kind keeps every refused pair; the Lease
    keeps ONE entry per account), so the fleet account sees two wrong passwords; a restart before the rotation back
    empties that gate and the Lease holds only the last pair, so it sees three."""
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)
    assert presented(wire) == [(FLEET, FLEET_PASSWORD)], "the product's own daily ping, as at 10:27:05Z"
    # Step 2: the walk account's retrieved cluster, the Secret holding its password, the ping every 60 s. Changing
    # the chart-level username to the walk account does not help: the fleet account is in use through shared-rnd.
    host.rotate(WALK_PASSWORD)
    walk = process(tmp_path, monkeypatch, host, discovered=[shared_rnd(), dataclasses.replace(retrieved("walk-lookup"),
                   lookup_account=WALK)], name="walk", fleet_account_username=WALK, fleet_ping_interval_seconds=60)
    wire.answers = [refused_401(), login_302()]          # accounts in name order: the fleet account first
    walk._ping_accounts()
    # Step 3: a wrong password, three cadences; then back to the walk account's password.
    host.rotate(WRONG)
    wire.answers = [refused_401(), refused_401()]
    for _ in range(3):
        walk._ping_accounts()
    host.rotate(WALK_PASSWORD)
    if rotation_back == "after-a-restart":
        walk = process(tmp_path, monkeypatch, host, discovered=[shared_rnd(), dataclasses.replace(
                       retrieved("walk-lookup"), lookup_account=WALK)], name="restarted", fleet_account_username=WALK,
                       fleet_ping_interval_seconds=60)
    wire.answers = [refused_401(), login_302()]
    walk._ping_accounts()
    to_fleet = [password for user, password in presented(wire)[1:] if user == FLEET]
    expected = [WALK_PASSWORD, WRONG] + ([WALK_PASSWORD] if rotation_back == "after-a-restart" else [])
    assert to_fleet == expected, to_fleet


@pytest.mark.parametrize("fleet_lease", ["as-found", "carrying-a-refusal"])
def test_the_self_login_walk_arrangement_never_presents_the_fleet_account(tmp_path, monkeypatch, wire, fleet_lease):
    """The arrangement this walk uses for #285 steps 4-5 and #310 Part A: the ping OFF, the chart-level username the
    walk account, the password Secret holding the walk account's password, one self-login stanza on the walk
    account, and shared-rnd retrieved by the fleet account as on the lab. Driven through acquisition, a revoked
    session's re-authentication, a wrong password's suspension, the sweep, the rotation back, and a 600 s session's
    renewal: every authorize is the walk account's, and the fleet account's Lease is never written."""
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)
    if fleet_lease == "carrying-a-refusal":            # the branch that reads the password with the ping off
        from gsd.fleetstate import FleetLease, lease_digest
        from test_fleet_lookup import UID
        holder = FleetLease(host, "ns", FLEET, claim_seconds=195, identity="elsewhere")
        holder.claim()
        holder.refuse("https://api.crc.testing:6443", lease_digest(FLEET, "another-password", UID), "login-refused")
        holder.release()
    fleet_writes = len([w for w in host.leases.writes if w[1] == lease_name(FLEET)])
    authorizes = len(wire.authorize)

    host.rotate(WALK_PASSWORD)
    stanza = ClusterConfig("walk-self", "https://api.crc.testing:6443", user_self_login=True,
                           ldap_connection_bootstrap=WALK)
    p = process(tmp_path, monkeypatch, host, stanza, discovered=[shared_rnd()], name="walk",
                fleet_account_username=WALK, fleet_ping_enabled=False)
    p.store.upsert_cluster("walk-self", stanza.api_url, True, source="values", credential="self-login")
    now = [T0]
    s = sessions(p, now)
    cluster = p.settings.cluster("walk-self")
    wire.answers = [login_302(token=TOKENS[0]), login_302(token=TOKENS[1]), refused_401(),
                    login_302(expires_in="600", token=TOKENS[2]), login_302(expires_in="600", token=TOKENS[3])]
    p._ping_accounts(); p._retrieve_pending()
    assert s.credential_for(cluster).token_value == TOKENS[0]            # step 4: acquisition
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")                             # step 5: the session deleted from outside
    assert s.credential_for(cluster).token_value == TOKENS[1]            # one re-authentication
    s.poll_answered(cluster, OK)                                        # the poll green again: the episode ends
    host.rotate(WRONG)                                                  # step 5b: a wrong password + the deletion
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")
    assert s.credential_for(cluster) is None                            # refused once: suspended
    for _ in range(3):
        now[0] += timedelta(seconds=60)
        p._ping_accounts(); p._retrieve_pending()
        assert s.credential_for(cluster) is None                        # parked: no second authorize
    host.rotate(WALK_PASSWORD)                                          # the rotation back re-arms it
    now[0] += timedelta(seconds=60)
    assert s.credential_for(cluster).token_value == TOKENS[2]            # #310 Part A: a 600 s session
    now[0] += timedelta(seconds=450)                                    # renew_at = expires_at - 150 s
    assert s.credential_for(cluster).token_value == TOKENS[3]            # renewed
    p._ping_accounts()

    walk_presented = presented(wire)[authorizes:]
    assert [user for user, _ in walk_presented] == [WALK] * 5, walk_presented
    assert [password for _, password in walk_presented] == [WALK_PASSWORD, WALK_PASSWORD, WRONG, WALK_PASSWORD,
                                                            WALK_PASSWORD]
    assert len([w for w in host.leases.writes if w[1] == lease_name(FLEET)]) == fleet_writes, "the fleet Lease written"
