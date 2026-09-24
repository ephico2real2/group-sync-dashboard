"""A failing remote is held, not asked again by every viewer (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.5).

A remote-sar cluster's TierResolver is built with `failure_hold_seconds`: after a failed resolution no request
CALLS that remote until the hold expires, and the first one that would call after it is the single probe,
re-arming the hold before it calls. The gate (`TierResolver._may_call`) is passed by a leader and by a follower
that steals a stuck slot alike; a request for a viewer already being resolved rides that resolution, the probe
included. The host's resolvers pass no hold and must behave exactly as before.

The clock is `gsd.kube`'s own `time.monotonic`, replaced by a counter the test moves, so every window is exact;
a follower's give-up bound (`TIER_CHECK_TIMEOUT_SECONDS * 2 + 1` of REAL time) is shrunk where a case needs it.
"""

from __future__ import annotations

import threading
import time as real_time

import pytest

from gsd import kube
from gsd.config import ClusterConfig, Settings
from gsd.kube import TIER_ALL, TIER_SELF, ClusterError, RemoteTierResolvers, TierResolver

HOLD = 30.0


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def __getattr__(self, name):
        return getattr(real_time, name)


class _Remote:
    """TierResolver._kube's two calls. `answer` is "fail" (the group list raises), "deny" or "allow". A viewer
    named in `gates` blocks inside its FIRST group list until the gate is set."""

    def __init__(self, answer: str = "fail") -> None:
        self.cluster = ClusterConfig("west", "https://api.west.example:6443", token_env="X")
        self.answer = answer
        self.calls: list[str] = []
        self.gates: dict[str, threading.Event] = {}
        self.entered = threading.Semaphore(0)
        self._lock = threading.Lock()

    def fetch_groups_of_user(self, viewer: str) -> list[str]:
        with self._lock:
            self.calls.append(viewer)
        self.entered.release()
        gate = self.gates.pop(viewer, None)
        if gate is not None:
            gate.wait(10)
        if self.answer == "fail":
            raise ClusterError("unreachable", "ConnectTimeout: timed out")
        return []

    def create_subject_access_review(self, viewer, groups, attrs) -> bool:
        return self.answer == "allow"


def _resolver(remote: _Remote, *, hold: float = HOLD, observe=None) -> TierResolver:
    r = TierResolver(remote.cluster, verb="list", resource="clusterrolebindings", api_group="rbac.authorization.k8s.io",
                     subresource="", ttl_seconds=60.0, observe=observe, failure_hold_seconds=hold)
    r._kube = remote
    return r


def _burst(r: TierResolver, viewers) -> tuple[list[threading.Thread], dict]:
    out: dict = {}
    threads = [threading.Thread(target=lambda v=v: out.__setitem__(v, r.tier_for(v))) for v in viewers]
    for t in threads:
        t.start()
    return threads, out


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(kube, "time", c)
    return c


class TestTheHold:
    def test_a_failure_holds_every_viewer_and_the_first_request_after_expiry_is_the_one_probe(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        assert r.tier_for("a") == TIER_SELF                      # fails: held until t+30
        for v in ("b", "c", "d", "e", "a"):
            assert r.tier_for(v) == TIER_SELF
        assert remote.calls == ["a"], "a held remote was asked"
        clock.t += HOLD + 1
        remote.gates["p"] = gate = threading.Event()
        probe, _ = _burst(r, ["p"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        others, answers = _burst(r, [f"v{i}" for i in range(8)])
        for t in others:
            t.join(5)
        assert set(answers.values()) == {TIER_SELF} and remote.calls == ["a", "p"], "only the probe calls"
        gate.set()
        for t in probe:
            t.join(5)
        assert r.tier_for("q") == TIER_SELF and remote.calls == ["a", "p"], "the failed probe re-armed the hold"

    def test_a_success_ends_the_hold_for_every_viewer(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.answer = "allow"
        assert r.tier_for("p") == TIER_ALL
        assert r.tier_for("q") == TIER_ALL and r.tier_for("a") == TIER_ALL
        assert remote.calls == ["a", "p", "q", "a"]

    def test_a_cached_verdict_still_serves_during_a_hold(self, clock):
        remote = _Remote(answer="allow")
        r = _resolver(remote)
        assert r.tier_for("admin") == TIER_ALL                   # cached for the TTL
        remote.answer = "fail"
        assert r.tier_for("other") == TIER_SELF                  # fails: the hold is armed
        assert r.tier_for("admin") == TIER_ALL, "a decided verdict is not a call and is not held"
        assert remote.calls == ["admin", "other"]

    def test_the_first_failure_costs_one_attempt_per_viewer_already_in_flight(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        gate = threading.Event()
        for v in ("a", "b", "c", "d", "e"):
            remote.gates[v] = gate
        threads, _ = _burst(r, ["a", "b", "c", "d", "e"])
        for _ in range(5):
            assert remote.entered.acquire(timeout=5)
        gate.set()
        for t in threads:
            t.join(5)
        assert len(remote.calls) == 5
        for v in ("a", "b", "c", "d", "e", "f"):
            r.tier_for(v)
        assert len(remote.calls) == 5, "after the first failure landed, the hold covers everyone"

    def test_every_hold_expiry_makes_the_next_request_the_probe_that_pays_the_call(self, clock):
        """SPEC_D2b §6: an unreachable remote costs the request that asks, before the hold engages AND on the
        first request after every expiry — measured 15.03 s for three unreachable remotes."""
        remote = _Remote()
        r = _resolver(remote)
        per_request = []
        for at, viewer in ((0.0, "a"), (10.0, "b"), (31.0, "c"), (40.0, "d"), (62.0, "e")):
            clock.t = 1000.0 + at
            before = len(remote.calls)
            r.tier_for(viewer)
            per_request.append(len(remote.calls) - before)
        assert per_request == [1, 0, 1, 0, 1]

    def test_a_resolver_without_a_hold_asks_on_every_request_as_before(self, clock):
        """The host's resolvers pass no hold: every indeterminate check is uncached and asked again."""
        remote = _Remote()
        r = _resolver(remote, hold=0.0)
        for v in ("a", "a", "b"):
            assert r.tier_for(v) == TIER_SELF
        assert remote.calls == ["a", "a", "b"]


class TestEveryCallingPathPassesTheGate:
    """N2 of PR #339's confirmation pass: the gate sits on the CALL, not on the request."""

    def test_the_probes_own_viewer_rides_the_probe_and_gets_its_answer(self, clock):
        """A page sends four to seven requests in one burst: they must read one tier, not the probe's and self."""
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.answer = "allow"
        remote.gates["admin"] = gate = threading.Event()
        probe, first = _burst(r, ["admin"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        siblings, rest = _burst(r, ["admin", "admin", "admin"])
        real_time.sleep(0.2)
        gate.set()
        for t in probe + siblings:
            t.join(5)
        assert first["admin"] == TIER_ALL and set(rest.values()) == {TIER_ALL}
        assert remote.calls == ["a", "admin"], "the siblings rode the probe"

    def test_a_follower_that_gives_up_on_a_stuck_leader_does_not_call_while_the_remote_is_held(self, clock, monkeypatch):
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)    # a follower gives up after 1.1 s of real time
        remote = _Remote()
        r = _resolver(remote)
        remote.gates["v"] = stuck = threading.Event()
        leader, _ = _burst(r, ["v"])
        assert remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["v"])
        real_time.sleep(0.2)
        clock.t += 1.0
        assert r.tier_for("u") == TIER_SELF                       # another viewer's failure arms the hold
        held = list(remote.calls)
        for t in follower:
            t.join(5)
        stuck.set()
        for t in leader:
            t.join(5)
        assert remote.calls == held, f"a call went out during the hold: {remote.calls}"
        assert answers == {"v": TIER_SELF}

    def test_a_follower_of_a_leader_stalled_in_the_observe_callback_does_not_call_during_its_hold(self, clock, monkeypatch):
        """The threat model §3.5 orders `_start_hold` before `_note` for: the observe callback is not bounded."""
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        remote = _Remote()
        stall = threading.Event()
        r = _resolver(remote, observe=lambda outcome: stall.wait(10))
        remote.gates["v"] = release = threading.Event()
        leader, _ = _burst(r, ["v"])
        assert remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["v"])
        real_time.sleep(0.2)
        release.set()                                             # fails, arms the hold, stalls in _note
        real_time.sleep(0.2)
        held = list(remote.calls)
        for t in follower:
            t.join(5)
        stall.set()
        for t in leader:
            t.join(5)
        assert remote.calls == held, f"a call went out during the hold: {remote.calls}"
        assert answers == {"v": TIER_SELF}

    def test_a_follower_of_a_stuck_probe_does_not_start_a_second_probe(self, clock, monkeypatch):
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.gates["p"] = stuck = threading.Event()
        probe, _ = _burst(r, ["p"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["p"])
        for t in follower:
            t.join(5)
        stuck.set()
        for t in probe:
            t.join(5)
        assert remote.calls == ["a", "p"] and answers == {"p": TIER_SELF}


class TestARebuildStartsFresh:
    def test_a_rotated_token_builds_a_new_resolver_without_the_old_hold_or_cache(self, clock, tmp_path):
        host = ClusterConfig("home", "https://kubernetes.default.svc", token_env="X", dashboard_controller=True)
        settings = Settings(clusters=[host], db_path=str(tmp_path / "r.db"), view_restrictions_enabled=True)
        east = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~first-token-aaaaaaa",
                             source="secret:gsd-cluster-east")
        settings.cluster_registry.replace([east], [], at="t0")
        remotes: list[_Remote] = []

        def make(c: ClusterConfig) -> TierResolver:
            remotes.append(_Remote())
            return _resolver(remotes[-1])

        pool = RemoteTierResolvers(settings, make)
        assert pool.get("east").tier_for("a") == TIER_SELF       # fails: that resolver is held
        assert pool.get("east").tier_for("b") == TIER_SELF and remotes[0].calls == ["a"]
        rotated = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~second-token-bbbbbb",
                                source="secret:gsd-cluster-east")
        settings.cluster_registry.replace([rotated], [], at="t1")
        assert pool.get("east").tier_for("b") == TIER_SELF
        assert len(remotes) == 2 and remotes[1].calls == ["b"], "the new connection is asked at once"
