"""#481 (SPEC_S4f): the fleet gate's backstop — a deleted fleet Lease is put back from the copy kept beside the
database, so `crc start` (which deletes every Lease on the cluster) sends no refused password again and pings no
second time in a day.

The harness is SPEC_S4c's (`tests/test_fleet_lifecycle.py`): `wire` counts authorize requests on the fake OAuth
server — the unit every budget is stated in — and a new `Poller` over the same fake API server is a restarted pod.
Every process's database sits in `tmp_path`, so the copy beside it, `tmp_path/fleet-gate.json`, is one data volume
that outlives the pods. Two events are modelled:

  crc_start(host)   every Lease deleted — crc-org/crc pkg/crc/cluster/cluster.go:509, `oc delete -A lease --all`, run
                    on every cold start — and the caller builds new processes: every pod restarted, its memory gone.
  delete_leases     the same deletion while a process keeps running.

`ApiServer` is the suite's `LeaseAPI` plus the two API-server behaviours a deleted Lease meets (Kubernetes v1.35.6,
`fc0e7a6c`): every create stamps a `metadata.uid`; and a PUT to an absent name creates it only when its body carries no
uid (pkg/registry/coordination/lease/strategy.go:84, AllowCreateOnUpdate; registry/generic/registry/store.go:646-712),
while a body carrying one — every PUT the dashboard sends, built from the object it read — is a UID precondition that
an absent object fails with 409 (registry/rest/update.go:188-203, storage/interfaces.go:150-155,
storage/errors/storage.go:80-81). No test logs in as the fleet account of any cluster: USER is the harness's own
name."""

from __future__ import annotations

import json
import logging
import uuid

import pytest

from gsd.fleetstate import PREFIX, FleetLease, lease_name
from gsd.kube import ClusterError
from gsd.poller import Poller
from gsd.store import Store
from test_fleet_lifecycle import (ANSWERS, LEASES, LeaseAPI, LeaseHost, lines, process, retrieved, self_login,
                                  sessions, stanza)
from test_fleet_login import T0, USER, login_302, refused_401
from test_fleet_lookup import wire  # noqa: F401 - the fixture

REFUSED = PREFIX + "refused"
COPY = "fleet-gate.json"


class ApiServer(LeaseAPI):
    """The suite's LeaseAPI with what the API server does to a PUT that meets a deleted Lease (module docstring)."""

    def write(self, method: str, name: str, obj: dict) -> dict:
        uid = obj["metadata"].get("uid")
        stored = self.objects.get(name)
        if not self.refuse and method == "PUT" and uid and uid != (stored or {}).get("metadata", {}).get("uid"):
            self.writes.append((method, name))
            raise ClusterError("unreachable", f"HTTP 409 on PUT {LEASES}/{name}: Precondition failed: UID")
        if not self.refuse and method == "PUT" and stored is None:
            method = "POST"                                       # no uid in the body: AllowCreateOnUpdate
        created = method == "POST" and name not in self.objects
        out = super().write(method, name, obj)
        if created:
            out["metadata"]["uid"] = self.objects[name]["metadata"]["uid"] = str(uuid.uuid4())
        return out


def api_host() -> LeaseHost:
    return LeaseHost(ApiServer())


def estate(host: LeaseHost) -> LeaseHost:
    """The account's Lease exists, empty, as every retrieval since #285 leaves it: an estate, not a first install."""
    lease = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-0")
    lease.claim()
    lease.release()
    return host


def delete_leases(host: LeaseHost) -> None:
    host.leases.objects.clear()


def crc_start(host: LeaseHost, tmp_path=None) -> None:
    """The Lease half of `crc start`; with `tmp_path`, persistence is off and the copy goes with the pod."""
    delete_leases(host)
    if tmp_path is not None:
        (tmp_path / COPY).unlink(missing_ok=True)


def clear_by_hand(host: LeaseHost) -> None:
    """SPEC_S4c §5 Q7: `oc annotate leases.coordination.k8s.io gsd-fleet-… groupsync-dashboard.io/refused-`."""
    obj = host.leases.objects[lease_name(USER)]
    obj["metadata"]["annotations"].pop(REFUSED)
    host.leases.serial += 1
    obj["metadata"]["resourceVersion"] = str(host.leases.serial)


def kept(tmp_path) -> dict:
    assert (tmp_path / COPY).is_file(), "nothing is kept beside the database"
    return json.loads((tmp_path / COPY).read_text())


class Binds:
    """Authorize requests since the last `step`."""

    def __init__(self, wire):
        self.wire, self.seen, self.steps = wire, 0, []

    def step(self) -> int:
        self.steps.append(len(self.wire.authorize) - self.seen)
        self.seen = len(self.wire.authorize)
        return self.steps[-1]


def run(path: str, p: Poller) -> None:
    """One cycle of one bind path in process `p`."""
    if path == "lookup":
        p._retrieve_pending()
    elif path == "ping":
        p._ping_accounts()
    else:
        sessions(p, [T0]).credential_for(p.settings.cluster("sl"))


CLUSTERS = {"lookup": ((stanza("l1"),), ()), "ping": ((), (retrieved("r1"),)), "self-login": ((self_login("sl"),), ())}


def pod(tmp_path, monkeypatch, host, path: str, name: str) -> Poller:
    clusters, discovered = CLUSTERS[path]
    return process(tmp_path, monkeypatch, host, *clusters, discovered=discovered, name=name)


# ── B2: a refused password stays refused across a deletion ───────────────────────────────────────

@pytest.mark.parametrize("path", sorted(CLUSTERS))
@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_a_refused_password_stays_refused_across_crc_starts(tmp_path, monkeypatch, wire, answer, path):
    """The issue's Definition of Done: a wrong (401) or locked (500) password on each bind path, then a restart with
    the Lease kept, then two `crc start`s. Before #481 each start cost one more bind: [1, 0, 1, 1]."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [ANSWERS[answer]() for _ in range(6)]
    first = pod(tmp_path, monkeypatch, host, path, "boot")
    run(path, first); run(path, first)
    binds.step()
    run(path, pod(tmp_path, monkeypatch, host, path, "restart"))
    binds.step()
    for n in (1, 2):
        crc_start(host)
        run(path, pod(tmp_path, monkeypatch, host, path, f"crc{n}"))
        binds.step()
        assert REFUSED in host.leases.annotations(), "the Lease is not back with its entry, where §5 Q7 can clear it"
    assert binds.steps == [1, 0, 0, 0], binds.steps


def test_an_uncertain_reservation_survives_a_crc_start(tmp_path, monkeypatch, wire):
    """A process that died after the authorize GET left its reservation (#419, D1) on the Lease and beside the
    database; after a `crc start` it still gates. Before #481: +1."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [lambda request: SystemExit("the process dies after the authorize GET"), refused_401()]
    first = process(tmp_path, monkeypatch, host, stanza("l1"), name="boot")
    with pytest.MonkeyPatch.context() as crash, pytest.raises(SystemExit):
        crash.setattr(FleetLease, "release", lambda *a, **k: None)          # nothing runs after a crash
        first._retrieve_pending()
    binds.step()
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="crc")._retrieve_pending()
    binds.step()
    assert binds.steps == [1, 0], binds.steps


def test_a_live_deletion_then_an_ordinary_restart_binds_nothing(tmp_path, monkeypatch, wire):
    """The Lease deleted while the pod runs: its own gate held, but the Lease it re-created carried no entry, so the
    next ordinary restart bound again. Before #481: [1, 0, 1]."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [refused_401() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    p._retrieve_pending()
    binds.step()
    delete_leases(host)
    for state in p._lookups.values():
        state.not_before = 0.0                                               # the lookup's own backoff elapsed
    p._retrieve_pending(); p._retrieve_pending()
    binds.step()
    process(tmp_path, monkeypatch, host, stanza("l1"), name="redeploy")._retrieve_pending()
    binds.step()
    assert binds.steps == [1, 0, 0], binds.steps


def test_a_deletion_while_an_attempt_is_on_the_wire_admits_no_second_bind(tmp_path, monkeypatch, wire):
    """One process, two paths: the lookup's authorize is in flight when every Lease is deleted, and the same process's
    self-login thread tries. The claim was all that stood between them; the reservation, kept beside the database
    before the wire, now gates the second. Before #481: 2 authorizes."""
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), self_login("sl"), name="pod")
    s = sessions(p, [T0])

    def mid_flight(request):
        delete_leases(host)
        s.credential_for(p.settings.cluster("sl"))                          # the other thread, meanwhile
        return refused_401()

    wire.answers = [mid_flight, refused_401(), refused_401()]
    p._retrieve_pending()
    assert len(wire.authorize) == 1, len(wire.authorize)


def test_a_refusal_written_after_a_live_deletion_is_not_lost(tmp_path, monkeypatch, wire):
    """The refusal's PUT carries the uid it read, so the API server answers 409 and does not re-create the Lease
    (retracting #481's research, §1.3): the answer is not on any Lease. The reservation kept beside the database
    still gates the restart. Before #481: 2 authorizes."""
    host = api_host()

    def deleted_in_flight(request):
        delete_leases(host)
        return refused_401()

    wire.answers = [deleted_in_flight, refused_401()]
    process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")._retrieve_pending()
    assert lease_name(USER) not in host.leases.objects, "a PUT carrying the uid it read re-created the Lease"
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 1, len(wire.authorize)


# ── B3: the ping stays once a day across the same events ─────────────────────────────────────────

def test_the_ping_stays_once_a_day_across_crc_starts_and_a_live_deletion(tmp_path, monkeypatch, wire):
    """A VALID password, three retrieved clusters: one ping per interval across a restart, two `crc start`s the same
    day and a live deletion; a day later the next target by name. Before #481: [1, 0, 1, 1, 1, …]."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [login_302() for _ in range(8)]
    fleet = [retrieved("c00"), retrieved("c01"), retrieved("c02")]
    p = process(tmp_path, monkeypatch, host, discovered=fleet, name="boot")
    p._ping_accounts(); p._ping_accounts()
    binds.step()
    process(tmp_path, monkeypatch, host, discovered=fleet, name="restart")._ping_accounts()
    binds.step()
    for n in (1, 2):
        crc_start(host)
        p = process(tmp_path, monkeypatch, host, discovered=fleet, name=f"crc{n}")
        p._ping_accounts()
        binds.step()
    delete_leases(host)
    p._ping_accounts()
    binds.step()
    host.leases.backdate(USER, PREFIX + "ping-last-attempt", 86400)
    p._ping_accounts()
    binds.step()
    assert binds.steps == [1, 0, 0, 0, 0, 1], binds.steps
    assert host.leases.annotations()[PREFIX + "ping-last-target"] == "c01", "the rotation restarted at the first name"


# ── the Lease stays the authority; §5 Q7's clear re-arms; the runbook's second clear ─────────────

def test_the_lease_stays_the_authority_whenever_it_exists(tmp_path, monkeypatch, wire):
    """The copy still holds an entry the Lease no longer does (removed by hand, and no pod read it since): the Lease
    exists, so it decides — one bind, the re-arm — and the copy follows it on that read."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    process(tmp_path, monkeypatch, host, stanza("l1"), name="boot")._retrieve_pending()
    clear_by_hand(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restart")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)
    assert REFUSED not in kept(tmp_path)[lease_name(USER)], "the copy did not follow the Lease"


def test_a_clear_the_running_pod_has_read_survives_a_crc_start(tmp_path, monkeypatch, wire):
    """§5 Q7's clear made while the pod runs: its sweep reads the cleared Lease within a cadence and the copy follows
    it, so a `crc start` before the restart does not bring the entry back — the restarted pod binds once, the re-arm."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    p._retrieve_pending()
    clear_by_hand(host)
    p._ping_accounts()                                                     # the sweep's read: no claim, no write
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="crc")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)


def test_q7s_clear_still_rearms_the_gate(tmp_path, monkeypatch, wire):
    """SPEC_S4c §5 Q7, unchanged: the entry removed by hand, the running pod's own gate holds until the restart,
    and the restart binds once."""
    host = api_host()
    wire.answers = [refused_401(), login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="pod")
    p._retrieve_pending(); p._ping_accounts()
    clear_by_hand(host)
    p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1, (len(wire.authorize), "the running pod keeps its gate until it restarts")
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 2, len(wire.authorize)


@pytest.mark.parametrize("path", ["lookup", "ping"])
def test_a_clear_by_hand_then_a_crc_start_before_any_read_is_undone_and_said(tmp_path, monkeypatch, wire, caplog, path):
    """The one ordering the copy changes: the entry removed while no pod read the Lease, then a `crc start` — the copy
    puts it back, an over-block, said once. The runbook's step: the Lease is back (for a ping-only account, the lab's
    shape, the sweep puts it back), so remove the entry again and restart the pod — the re-arm, one bind. Before #481
    the start kept the clear: the first cycle bound."""
    host = estate(api_host())
    wire.answers = [refused_401(), *[login_302() for _ in range(4)]]
    run(path, pod(tmp_path, monkeypatch, host, path, "boot"))
    clear_by_hand(host)
    crc_start(host)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = pod(tmp_path, monkeypatch, host, path, "crc")
        run(path, p); run(path, p)
    assert len(wire.authorize) == 1, (len(wire.authorize), "a clear no pod read survived the start")
    said = lines(caplog, "fleet-lease-absent")
    assert len(said) == 1, said
    assert f"account={USER}" in said[0] and "kept=true" in said[0] and "refused=login-refused" in said[0]
    assert "remove it again and restart the pod" in said[0]
    clear_by_hand(host)
    if path == "ping":
        host.leases.backdate(USER, PREFIX + "ping-last-attempt", 86400)     # the refused attempt's day has passed
    run(path, pod(tmp_path, monkeypatch, host, path, "restarted"))
    assert len(wire.authorize) == 2, len(wire.authorize)


# ── the warning: said once, by the process that puts the Lease back ──────────────────────────────

def test_the_restore_is_said_once_by_the_process_that_creates_it(tmp_path, monkeypatch, wire, caplog):
    """Two processes after a `crc start`, each running the lookup and the sweep twice: one create is admitted, so one
    line, whichever path made it."""
    host = api_host()
    wire.answers = [refused_401() for _ in range(4)]
    process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="boot")._retrieve_pending()
    crc_start(host)
    with caplog.at_level(logging.INFO, logger="gsd"):
        a = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="a")
        b = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="b")
        for p in (a, b, a, b):
            p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1, len(wire.authorize)
    assert len(lines(caplog, "fleet-lease-absent")) == 1, lines(caplog, "fleet-lease-absent")
    assert host.leases.objects[lease_name(USER)]["spec"]["holderIdentity"] == "", "the restore left a claim held"


def test_nothing_kept_is_said_once_and_the_ping_binds_again(tmp_path, monkeypatch, wire, caplog):
    """Persistence off (the copy goes with the pod), then a `crc start`, on an account with retrieved clusters: the
    Lease cannot be put back as it was, and the line says so once — the row #481 does not fix: +1 ping."""
    host, binds = estate(api_host()), Binds(wire)
    wire.answers = [login_302() for _ in range(3)]
    process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="boot")._ping_accounts()
    binds.step()
    crc_start(host, tmp_path)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="crc")
        p._ping_accounts(); p._ping_accounts()
    binds.step()
    assert binds.steps == [1, 1], binds.steps
    said = lines(caplog, "fleet-lease-absent")
    assert len(said) == 1 and "kept=false" in said[0] and "may be sent once more" in said[0], said


@pytest.mark.parametrize("path", ["lookup", "self-login"])
def test_persistence_off_is_the_row_not_fixed(tmp_path, monkeypatch, wire, path):
    """The operator's accepted row (2026-09-29): with the copy gone with the pod, a `crc start` still costs one bind for
    a refused password — as before #481."""
    host, binds = api_host(), Binds(wire)
    wire.answers = [refused_401() for _ in range(4)]
    run(path, pod(tmp_path, monkeypatch, host, path, "boot"))
    binds.step()
    crc_start(host, tmp_path)
    run(path, pod(tmp_path, monkeypatch, host, path, "crc"))
    binds.step()
    assert binds.steps == [1, 1], binds.steps


def test_a_first_install_binds_once_and_says_nothing(tmp_path, monkeypatch, wire, caplog):
    """No Lease and nothing kept, with no retrieved cluster: a first install, not a deletion — the sweep, which runs
    first here, neither creates the Lease nor says a word, and the lookup binds once, as before."""
    host = api_host()
    wire.answers = [refused_401()]
    with caplog.at_level(logging.INFO, logger="gsd"):
        p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
        p._ping_accounts()
        assert host.leases.writes == [], "the sweep wrote a Lease for an account with no trace of one"
        p._retrieve_pending(); p._ping_accounts()
    assert len(wire.authorize) == 1 and lines(caplog, "fleet-lease-absent") == []


def test_a_standbys_view_after_a_crc_start_is_the_kept_copy_and_it_writes_nothing(tmp_path, monkeypatch, wire):
    """A standby serves the tab and /metrics from the Lease it reads (SPEC_S4c §3.4); after a `crc start` it reads the
    copy — the last success stays on the page — and, not being the leader, it does not put the Lease back. Before
    #481 `last_ok` read null until the leader's next ping."""
    host = estate(api_host())
    wire.answers = [login_302()]
    leader = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="leader")
    leader._ping_accounts()
    before = leader.signals.fleet_accounts()[USER]["last_ok"]
    crc_start(host)
    standby = process(tmp_path, monkeypatch, host, discovered=[retrieved("r1")], name="standby")
    standby.elector = type("Standby", (), {"is_leader": False})()
    standby._ping_accounts()
    assert before and standby.signals.fleet_accounts()[USER]["last_ok"] == before
    assert host.leases.objects == {} and len(wire.authorize) == 1


# ── fail closed ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("content", ["{", json.dumps({"gsd-fleet-x": "not a map"}), json.dumps(["a list"])])
def test_an_unreadable_copy_behind_an_absent_lease_binds_nothing(tmp_path, monkeypatch, wire, content):
    """Absent AND unknown: every path fails closed with `fleet-state-unavailable` naming the copy, as for an
    unreadable Lease (SPEC_S4c R8). Before #481 an absent Lease read as empty and every path bound."""
    host = api_host()
    (tmp_path / COPY).write_text(content)
    wire.answers = [refused_401() for _ in range(3)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), self_login("sl"), discovered=[retrieved("r1")], name="pod")
    p._retrieve_pending(); p._ping_accounts()
    assert sessions(p, [T0]).credential_for(p.settings.cluster("sl")) is None
    assert wire.authorize == [], (len(wire.authorize), "a bind behind an absent Lease whose copy cannot be read")
    assert host.leases.writes == [], "a Lease was created over a gate nobody can read"
    found = {f.secret: f for f in p.settings.cluster_registry.findings() if f.code == "fleet-state-unavailable"}
    assert {"gsd-cluster-l1", "gsd-cluster-r1", "sl"} <= set(found), sorted(found)
    assert all(COPY in f.detail for f in found.values())


def test_a_copy_that_cannot_be_written_at_the_reservation_binds_nothing_and_strands_no_entry(tmp_path, monkeypatch,
                                                                                            wire, caplog):
    """The reservation must be kept in both places before the wire. When the copy cannot be written, nothing is sent
    and the reservation goes again — else it would gate, until §5 Q7's clear, a password the directory never saw
    (#481's probe on the research prototype: 0 authorizes, the `uncertain` entry left). Said when the copy starts
    failing, not on every write: three cycles, one line."""
    host = api_host()
    (tmp_path / f"{COPY}.tmp").mkdir()                                       # every write of the copy fails
    wire.answers = [refused_401() for _ in range(3)]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    with caplog.at_level(logging.INFO, logger="gsd"):
        for _ in range(3):
            p._retrieve_pending()
    assert wire.authorize == [], len(wire.authorize)
    assert REFUSED not in host.leases.annotations(), "a reservation for a password never sent gates the account"
    found = [f for f in p.settings.cluster_registry.findings() if f.secret == "gsd-cluster-l1"]
    assert [f.code for f in found] == ["fleet-state-unavailable"] and COPY in found[0].detail, found
    said = lines(caplog, "fleet-state-unavailable")
    assert len(said) == 1 and COPY in said[0], said


# ── what is kept, where, and where not ───────────────────────────────────────────────────────────

def test_the_copy_is_the_gate_and_the_ping_instants_as_the_lease_holds_them(tmp_path, monkeypatch, wire):
    """`<the database's directory>/fleet-gate.json`: `{Lease name: {annotation: value}}`, the refusal and the five
    ping annotations byte for byte, never the claim or the account; written by rename, nothing left beside it."""
    host = api_host()
    wire.answers = [login_302(), refused_401()]
    p = process(tmp_path, monkeypatch, host, stanza("l1"), discovered=[retrieved("r1")], name="pod")
    p._ping_accounts()
    host.rotate("a-wrong-password")
    p._retrieve_pending()
    lease = host.leases.objects[lease_name(USER)]["metadata"]["annotations"]
    assert kept(tmp_path) == {lease_name(USER): {k: v for k, v in lease.items() if k != PREFIX + "account"}}
    assert sorted(kept(tmp_path)[lease_name(USER)]) == sorted(
        PREFIX + k for k in ("refused", "ping-last-attempt", "ping-last-ok", "ping-last-outcome", "ping-last-target",
                             "ping-digest"))
    assert sorted(x.name for x in tmp_path.iterdir() if not x.name.endswith((".db", ".db-wal", ".db-shm"))) == [COPY]


def test_a_database_in_memory_keeps_no_copy(tmp_path, monkeypatch, wire):
    """`:memory:` keeps nothing across a restart, so it keeps no copy either, and writes nothing in the working
    directory: a `crc start` costs +1 there, as before #481."""
    from gsd.config import ClusterConfig, Settings
    from gsd.metrics import RuntimeSignals
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    host = api_host()
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    wire.answers = [refused_401(), refused_401()]

    def memory_pod() -> Poller:
        s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), stanza("l1")],
                     db_path=":memory:", cluster_secrets_writes_enabled=True, fleet_account_username=USER)
        return Poller(Store(":memory:"), s, signals=RuntimeSignals())

    memory_pod()._retrieve_pending()
    crc_start(host)
    memory_pod()._retrieve_pending()
    assert len(wire.authorize) == 2 and list(tmp_path.iterdir()) == []


# Reviewer regressions: test_review_backstop.py
"""Deterministic interleavings of the discovery reader and a self-login writer."""
import threading
from concurrent.futures import ThreadPoolExecutor

from test_fleet_gate_backstop import api_host, estate, clear_by_hand, crc_start
from test_fleet_lifecycle import process, stanza
from test_fleet_login import USER, refused_401, login_302
from test_fleet_lookup import wire
from gsd.fleetstate import FleetLease


def overlap(monkeypatch, observer, newer):
    """An old response pauses immediately before it reaches the file; newer work runs meanwhile."""
    paused, release, started = threading.Event(), threading.Event(), threading.Event()
    original = FleetLease._keep
    def delayed(self, record, **kw):
        if self is observer:
            paused.set()
            assert release.wait(5), "reader was never released"
        return original(self, record, **kw)
    monkeypatch.setattr(FleetLease, "_keep", delayed)
    def newer_work():
        started.set()
        return newer()
    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(observer.read)
        assert paused.wait(5), "reader did not reach the file"
        new = pool.submit(newer_work)
        assert started.wait(5)
        # Old code lets the newer response reach the file first. Serialized code blocks it.
        try:
            new.result(timeout=0.2)
        except TimeoutError:
            pass
        finally:
            release.set()
        old.result(timeout=5)
        new.result(timeout=5)


def test_delayed_read_cannot_erase_a_reserved_and_refused_password(tmp_path, monkeypatch, wire):
    host = estate(api_host())
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    observer = p._fleet_lease(host, "ns", USER)
    wire.answers = [refused_401(), refused_401()]
    overlap(monkeypatch, observer, p._retrieve_pending)
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 1, "a late empty snapshot erased the durable gate: second bind"


def test_delayed_read_cannot_undo_a_clear_another_reader_observed(tmp_path, monkeypatch, wire):
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401(), login_302()]
    p._retrieve_pending()
    observer = p._fleet_lease(host, "ns", USER)
    def observe_clear():
        clear_by_hand(host)
        p._fleet_lease(host, "ns", USER).read()
    overlap(monkeypatch, observer, observe_clear)
    crc_start(host)
    process(tmp_path, monkeypatch, host, stanza("l1"), name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 2, "a late refused snapshot undid an observed Q7 clear"


def test_restore_preserves_a_q7_clear_during_its_release(tmp_path, monkeypatch, wire):
    from test_fleet_gate_backstop import REFUSED, kept
    from gsd.fleetstate import lease_name
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401()]
    p._retrieve_pending()
    crc_start(host)
    lease = p._fleet_lease(host, "ns", USER)
    record = lease.read()
    original = host._send
    def clear_before_release(client, method, path, **kw):
        if method == "PUT":
            monkeypatch.setattr(host, "_send", original)
            clear_by_hand(host)
        return original(client, method, path, **kw)
    monkeypatch.setattr(host, "_send", clear_before_release)
    restored = lease.restore(record)
    assert restored.refused is None
    assert REFUSED not in host.leases.annotations()
    assert REFUSED not in kept(tmp_path)[lease_name(USER)]
    assert len(wire.authorize) == 1, "restore caused a bind"


def test_two_absent_readers_have_only_one_successful_create(tmp_path, monkeypatch, wire, caplog):
    import pytest
    from gsd.fleetstate import ClaimHeld
    from test_fleet_lifecycle import lines
    host = api_host()
    p = process(tmp_path, monkeypatch, host, stanza("l1"), name="pod")
    wire.answers = [refused_401()]
    p._retrieve_pending()
    crc_start(host)
    a = p._fleet_lease(host, "ns", USER, identity="a")
    b = p._fleet_lease(host, "ns", USER, identity="b")
    ar, br = a.read(), b.read()
    a.claim(ar)
    with pytest.raises(ClaimHeld):
        b.claim(br)
    assert len(lines(caplog, "fleet-lease-absent")) == 1
    assert len(wire.authorize) == 1


# Reviewer regressions: test_review_scope.py
from pathlib import Path
import pytest
from test_fleet_gate_backstop import api_host, estate, crc_start
from test_fleet_lifecycle import process, retrieved
from test_fleet_login import USER, refused_401, login_302
from test_fleet_lookup import wire


@pytest.mark.parametrize("answer", [refused_401, login_302])
def test_independent_pod_copy_can_miss_a_refusal_before_crc(tmp_path, monkeypatch, wire, answer):
    host = estate(api_host())
    a, b = tmp_path / "pod-a", tmp_path / "pod-b"
    a.mkdir(); b.mkdir()
    first = process(a, monkeypatch, host, discovered=[retrieved("r1")], name="pod-a")
    second = process(b, monkeypatch, host, discovered=[retrieved("r1")], name="pod-b")
    second._fleet_lease(host, "ns", USER).read()  # B has not yet seen A's later refusal.
    wire.answers = [answer(), answer()]
    first._ping_accounts()
    assert len(wire.authorize) == 1
    crc_start(host)
    process(b, monkeypatch, host, discovered=[retrieved("r1")], name="pod-b")._ping_accounts()
    assert len(wire.authorize) == 2
    # The code's residual is accepted explicitly, rather than described as covered at each pod.
    import gsd
    spec = Path(gsd.__file__).resolve().parents[2] / "docs/specs/SPEC_S4f_fleet_gate_backstop.md"
    scope = spec.read_text().split("### 3.9 Above one replica, and with persistence off", 1)[1].split("## 4.", 1)[0]
    assert "A stale per-pod copy can allow +1 bind or +1 ping after a Lease deletion" in scope


# Reviewer regressions: test_review_docs.py
from pathlib import Path
import gsd

ROOT = Path(gsd.__file__).resolve().parents[2]

def test_proof_heading_distinguishes_regressions_from_unchanged_controls():
    spec = (ROOT / 'docs/specs/SPEC_S4f_fleet_gate_backstop.md').read_text()
    section = spec.split('## 5. The documents, and the proof', 1)[1].split('### 5.1', 1)[0]
    text = ' '.join(section.split())
    assert '22 assertion failures and 6 passing controls' in text
    assert '28 passes with the blocks' in text


def test_runbook_describes_reservation_failures_and_present_lease_saves():
    runbook = (ROOT / 'charts/group-sync-dashboard/RUNBOOK.md').read_text()
    text = ' '.join(runbook.split('## 7.', 1)[1].split())
    assert "a path already gated need not attempt a reservation or publish another finding" in text
    assert "Saving a present Lease also parses the existing file" in text
    assert "Run one replica for the +0 guarantee" in text
