"""#445: SPEC_S4c §3.12 step 6's lab arrangement, hermetically, on the repository's own harness.

The arrangement phase 2 deploys (README, "The arrangement"): the chart names `developer`, its password Secret is
ABSENT, no stanza names `developer`, and the lab's `shared-rnd` is a cluster the lookup retrieved as the fleet account.
Two claims are checked here, on `tests/test_fleet_lifecycle.py`'s LeaseHost (one fake API server, CAS enforced, every
write counted) and `tests/test_ping_account_scope.py`'s lab-as-found:

1. The running pod, as leader, never reads, creates or claims `developer`'s Lease, reads no password, and puts
   nothing on the wire — across cadences, and while step 6's process A holds the claim. So 6.0's wait is for the
   walk's own claim only, and the pod cannot race A for it.
2. Step 6's two claim-only handles, `walk-step6-a` and `walk-step6-b`, as the coordinator builds them (identity,
   no backstop), on that same API: A's claim creates the absent Lease (POST), B's claim raises ClaimHeld with the
   exact text the coordinator checks and writes nothing, A's release clears the holder; still nothing on the wire.

A control proves the probe is not vacuous: with a stanza naming `developer` (the full §3.12 walk's shape), the same
pod DOES read `developer`'s Lease.

Run from a tree's local-development with PYTHONPATH=<tree>/local-development:<tree>/local-development/tests
(scripts/offline_proofs.sh does).
"""

from __future__ import annotations

import copy

import pytest

from gsd.fleetstate import ClaimHeld, FleetLease, lease_name
from test_fleet_lifecycle import LeaseHost, process
from test_fleet_login import login_302
from test_fleet_lookup import wire  # noqa: F401  (the fixture)
from test_ping_account_scope import FLEET, at, lab_as_found

DEV = "developer"
PASSWORD_SECRET = "/api/v1/namespaces/ns/secrets/gsd-fleet-account"   # the harness's chart-named password Secret


def watch(host: LeaseHost) -> list[tuple[str, str]]:
    """Every GET the host answers or refuses, in order: (kind, name) — the Leases and the password Secret."""
    seen: list[tuple[str, str]] = []
    get = host._get

    def logged(client, path, params):
        if "/leases/" in path:
            seen.append(("lease", path.rsplit("/", 1)[1]))
        elif path == PASSWORD_SECRET:
            seen.append(("password-secret", path))
        return get(client, path, params)
    host._get = logged
    return seen


def the_walk_pod(tmp_path, monkeypatch, host, *stanzas, discovered=None):
    return process(tmp_path, monkeypatch, host, *stanzas, discovered=discovered or [at("shared-rnd", FLEET)],
                   name="walk", fleet_account_username=DEV, fleet_ping_enabled=True)


def test_step6_the_walk_pod_never_touches_developers_lease_and_the_claim_is_held(tmp_path, monkeypatch, wire):
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)                 # the chart named FLEET; shared-rnd pinged once
    on_the_wire = len(wire.requests)
    fleet_lease = copy.deepcopy(host.leases.objects[lease_name(FLEET)])
    del host.secrets[PASSWORD_SECRET]                         # the walk values name a Secret the walk never creates
    seen = watch(host)
    writes = len(host.leases.writes)

    p = the_walk_pod(tmp_path, monkeypatch, host)
    for _ in range(3):                                        # three discovery cadences, as leader (no elector)
        p._retrieve_pending(); p._ping_accounts()
    assert lease_name(DEV) not in host.leases.objects, "the pod created developer's Lease"
    assert ("lease", lease_name(DEV)) not in seen, "the pod read developer's Lease"
    assert ("password-secret", PASSWORD_SECRET) not in seen, "the pod read the password Secret"

    # 6.1-6.3, as the coordinator builds its handles: FleetLease(client, ns, "developer", identity=...), no backstop.
    a = FleetLease(host, "ns", DEV, claim_seconds=195, identity="walk-step6-a")
    b = FleetLease(host, "ns", DEV, claim_seconds=195, identity="walk-step6-b")
    a.claim()
    assert (a.record.holder, a.name) == ("walk-step6-a", "gsd-fleet-88fa0d759f845b47")   # the HELD line's fields
    p._retrieve_pending(); p._ping_accounts()                 # the pod's cadence while A holds
    with pytest.raises(ClaimHeld) as held:
        b.claim()
    assert str(held.value).startswith("walk-step6-a holds gsd-fleet-88fa0d759f845b47 until "), str(held.value)
    released = a.release()
    assert released is not None and released.holder == "" and a.read().holder == ""

    dev_writes = [w for w in host.leases.writes[writes:] if w[1] == lease_name(DEV)]
    assert dev_writes == [("POST", lease_name(DEV)), ("PUT", lease_name(DEV))], dev_writes   # A's claim, A's release
    assert [w for w in host.leases.writes[writes:] if w[1] != lease_name(DEV)] == [], "another Lease was written"
    assert len(wire.requests) == on_the_wire, "a request reached the target (an authorize or a token read)"
    assert host.leases.objects[lease_name(FLEET)] == fleet_lease, "the fleet account's Lease changed"
    assert ("password-secret", PASSWORD_SECRET) not in seen, "a password Secret was read"


def test_step6_control_a_stanza_naming_developer_makes_the_pod_read_its_lease(tmp_path, monkeypatch, wire):
    """The probe above can fail: the full §3.12 walk's shape (a lookup retrieved as developer) reads the Lease."""
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)
    del host.secrets[PASSWORD_SECRET]
    seen = watch(host)
    p = the_walk_pod(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("walk-lookup", DEV)])
    p._retrieve_pending(); p._ping_accounts()
    assert ("lease", lease_name(DEV)) in seen
