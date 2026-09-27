"""#315 (SPEC_S4d): the credential gate is per ACCOUNT for every bound failure — the operator's ruling at
the review of #325 (SPEC_S4c, orchestrator's notes) — while #293's success mark stays per target
(SPEC_S5 §3.3). The fake target is S4a's and `wire` counts authorize requests, the unit the budget is
stated in: a wire mock measures authorize requests, not directory binds."""

from __future__ import annotations

import dataclasses

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.fleetlookup import CredentialGate, LookupRefused, lookup
from test_configmap_onboarding import STANZA, Host, cm, cycle
from test_fleet_login import login_302, refused_401
from test_fleet_lookup import USER, run, sa_secret, settings, wire  # noqa: F401

ANSWERS = {"401": refused_401, "500": lambda: httpx.Response(500, text="Internal Server Error")}


def target(name: str, url: str) -> ClusterConfig:
    return ClusterConfig(name, url, sa_token_lookup=True, ldap_connection_bootstrap=USER)


def attempt(cluster: ClusterConfig, gate: CredentialGate) -> LookupRefused:
    with pytest.raises(LookupRefused) as exc:
        run(cluster, gate=gate, s=settings(cluster))
    return exc.value


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_one_answered_failure_gates_every_target_of_the_account(wire, answer):
    """N = 4 distinct targets on one account and a failure on the first: exactly one authorize, and the
    other three refused as gated, each naming the target that answered. A 500 is what a LOCKED 389-ds
    account answers (LDAP code 19), so it gates exactly like a 401."""
    targets = [target(n, f"https://api.{n}.example.com:6443") for n in ("rnd", "east", "west", "north")]
    wire.answers = [ANSWERS[answer]() for _ in targets]     # enough for a per-target gate to spend them all
    gate = CredentialGate()
    first = attempt(targets[0], gate)
    others = [attempt(other, gate) for other in targets[1:]]
    assert len(wire.authorize) == 1, f"{len(wire.authorize)} authorize requests for one account and one password"
    assert first.spent is True and not first.gated
    for other, refusal in zip(targets[1:], others):
        assert (refusal.code, refusal.gated, refusal.spent) == ("login-refused", True, False), other.name
        assert refusal.detail.startswith(f"{targets[0].api_url} evaluated this password for {USER}"), refusal.detail
        assert refusal.detail.endswith(f"{other.name} does not send it"), refusal.detail


def test_two_urls_for_one_cluster_are_one_authorize(wire):
    """The lab's case 1 (#315): one physical cluster entered as `https://api.crc.testing:6443` and as
    `https://kubernetes.default.svc`. No URL canonicalisation folds two host names; the account key does."""
    wire.answers = [ANSWERS["500"](), ANSWERS["500"]()]
    gate = CredentialGate()
    attempt(target("shared-rnd", "https://api.crc.testing:6443"), gate)
    gated = attempt(target("dashboard", "https://kubernetes.default.svc"), gate)
    assert len(wire.authorize) == 1
    assert gated.gated and gated.detail.startswith("https://api.crc.testing:6443 evaluated this password"), gated.detail


def test_two_successful_configmap_onboardings_on_one_account_are_two_authorizes(wire):
    """#293's budget table (SPEC_S5 §3.3) is unchanged: a SUCCESSFUL ConfigMap session spends its own target
    only, so a second cluster on the same account and password still onboards. Passes before #315 and after;
    fails under a naive per-account key, which gates `east` on `rnd`'s success."""
    east = {**STANZA, "name": "east", "apiUrl": "https://api.east.example.com:6443"}
    host = Host([cm([STANZA, east])])
    s, clusters, _, _ = cycle(host)
    assert sorted(c.name for c in clusters) == ["east", "rnd"] and all(c.onboarding for c in clusters)
    wire.answers = [login_302(), login_302()]
    gate = CredentialGate()
    for cluster in clusters:
        wire.secret = httpx.Response(200, json=sa_secret())
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == 2 and {"gsd-cluster-rnd", "gsd-cluster-east"} <= set(host.secrets)


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_the_budget_over_the_system(wire, answer):
    """The harness (#315's Definition of Done): authorize requests for one account and one wrong or locked
    password, as (the first lookup, what the second adds), per shape. The state reset is a NEW
    CredentialGate — what a restart or a second replica starts with — and it adds ONE: that residual is
    stated, not covered, until #285's account Lease (SPEC_S4c §3.3)."""
    rnd = target("shared-rnd", "https://api.crc.testing:6443")
    shapes = {
        "two URLs, one cluster": (target("dashboard", "https://kubernetes.default.svc"), False),
        "two clusters, one credential": (target("east", "https://api.east.example.com:6443"), False),
        "state reset (a new gate)": (rnd, True),
        "irrelevant config edit (visibility)": (dataclasses.replace(rnd, visibility="self-only"), False),
    }
    measured = {}
    for shape, (second, reset) in shapes.items():
        wire.requests.clear()
        wire.answers = [ANSWERS[answer](), ANSWERS[answer]()]
        gate = CredentialGate()
        attempt(rnd, gate)
        first = len(wire.authorize)
        attempt(second, CredentialGate() if reset else gate)
        measured[shape] = (first, len(wire.authorize) - first)
    assert measured == {
        "two URLs, one cluster": (1, 0),
        "two clusters, one credential": (1, 0),
        "state reset (a new gate)": (1, 1),
        "irrelevant config edit (visibility)": (1, 0),
    }


def test_username_case_residual(wire):
    """PINS A RESIDUAL, not a guarantee (review of SPEC_S4d, Codex F3): "account" is the exact configured
    username string, so two spellings of one directory identity are two entries and two answered failures.
    Folding case would over-block distinct accounts on a case-sensitive provider; every stanza for one
    identity must use one spelling."""
    wire.answers = [ANSWERS["401"](), ANSWERS["401"]()]
    gate = CredentialGate()
    attempt(target("rnd", "https://api.rnd.example.com:6443"), gate)
    upper = dataclasses.replace(target("east", "https://api.east.example.com:6443"), ldap_connection_bootstrap=USER.upper())
    attempt(upper, gate)
    assert len(wire.authorize) == 2
