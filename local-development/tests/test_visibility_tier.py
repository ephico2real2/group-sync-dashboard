"""The visibility tier decision: groups resolved fresh, a SAR that carries them, fail-closed.

Every failure test here is requirement §5.4 (an indeterminate answer yields the self view,
never the wide one) made executable, and the group-carrying tests pin the measured finding
that shaped the code: a SubjectAccessReview without spec.groups answers allowed=false for a
cluster-admin whose grant arrives through a Group — which is every real administrator on the
reference cluster — so omitting them would invert the feature, not weaken it.

HTTP is mocked at the transport, the test_kube_reader idiom: no cluster is needed, and the
real request/response parsing runs.
"""
from __future__ import annotations

import json
import threading
import time

import httpx
import pytest

from gsd.config import ClusterConfig, load_settings
from gsd.kube import (
    SAR_API,
    TIER_ALL,
    TIER_SELF,
    TIER_TTL_SECONDS,
    VIRTUAL_AUTH_GROUPS,
    TierResolver,
)

GROUPS_PATH = "/apis/user.openshift.io/v1/groups"

BASE_CONFIG = """
clusters:
  - name: crc-local
    apiUrl: https://api.crc.testing:6443
    tokenEnv: GSD_TOKEN_CRC
"""


def _group(name: str, users: list[str]) -> dict:
    return {"metadata": {"name": name}, "users": users}


class FakeCluster:
    """Answers the resolver's two calls and records exactly what was asked."""

    def __init__(self, groups: list[dict], allowed: bool = True):
        self.groups = groups
        self.allowed = allowed
        self.sar_bodies: list[dict] = []
        self.group_lists = 0
        self.raise_exc: Exception | None = None       # raised for every call when set
        self.sar_status = 201
        self.sar_body_override: dict | str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.raise_exc is not None:
            raise self.raise_exc
        if request.url.path == GROUPS_PATH:
            self.group_lists += 1
            return httpx.Response(
                200, json={"kind": "GroupList", "items": self.groups, "metadata": {}}
            )
        assert request.url.path == SAR_API, request.url.path
        self.sar_bodies.append(json.loads(request.content))
        if isinstance(self.sar_body_override, str):
            return httpx.Response(self.sar_status, text=self.sar_body_override)
        if self.sar_body_override is not None:
            return httpx.Response(self.sar_status, json=self.sar_body_override)
        return httpx.Response(self.sar_status, json={"status": {"allowed": self.allowed}})


def _resolver(monkeypatch, fake: FakeCluster, **kwargs) -> TierResolver:
    kwargs.setdefault("verb", "list")
    kwargs.setdefault("resource", "groups")
    kwargs.setdefault("api_group", "user.openshift.io")
    # Both explicit, because TierResolver deliberately defaults NEITHER — see its constructor
    # comment: a default on either is what let a configured value go unused in silence. A test
    # that cares about expiry or a subresource passes its own; the rest just need a value.
    kwargs.setdefault("subresource", "")
    kwargs.setdefault("ttl_seconds", TIER_TTL_SECONDS)
    resolver = TierResolver(ClusterConfig("c", "https://api.example", token_env="X"), **kwargs)
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        resolver._kube, "_client",
        lambda: httpx.Client(transport=transport, base_url="https://api.example"),
    )
    return resolver


class TestTheReviewCarriesTheGroups:
    def test_a_group_granted_admin_is_admitted_with_polled_plus_virtual_groups(self, monkeypatch):
        """The measured trap: user-only, this exact admin was allowed=false. The review must
        carry the memberships read from the cluster AND the virtual groups every token has."""
        fake = FakeCluster(
            groups=[
                _group("app-ocp-rbac-demo-cluster-admin", ["john.doe"]),
                _group("some-other-team", ["jane.smith"]),
            ],
            allowed=True,
        )
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        spec = fake.sar_bodies[0]["spec"]
        assert spec["user"] == "john.doe"
        assert spec["groups"] == ["app-ocp-rbac-demo-cluster-admin", *VIRTUAL_AUTH_GROUPS]
        assert spec["resourceAttributes"] == {
            "verb": "list", "resource": "groups", "group": "user.openshift.io",
        }

    def test_membership_is_matched_byte_exact_not_casefolded(self, monkeypatch):
        """OpenShift User names are case-sensitive: two Users differing only in case are two
        identities, and a casefolded match would hand one the other's groups — and tier."""
        fake = FakeCluster(groups=[_group("admins", ["lateef.o"])])
        resolver = _resolver(monkeypatch, fake)
        resolver.tier_for("LATEEF.O")
        assert fake.sar_bodies[0]["spec"]["groups"] == list(VIRTUAL_AUTH_GROUPS)

    def test_the_operators_threshold_shapes_the_review_namespace_included(self, monkeypatch):
        """D2: the threshold is the review itself — verb, resource, apiGroup, namespace."""
        fake = FakeCluster(groups=[])
        resolver = _resolver(
            monkeypatch, fake,
            verb="list", resource="rolebindings",
            api_group="rbac.authorization.k8s.io", namespace="team-a",
        )
        resolver.tier_for("someone")
        assert fake.sar_bodies[0]["spec"]["resourceAttributes"] == {
            "verb": "list", "resource": "rolebindings",
            "group": "rbac.authorization.k8s.io", "namespace": "team-a",
        }

    def test_an_empty_api_group_is_sent_as_the_core_group(self, monkeypatch):
        """'' names the core API group; rewriting it to a default would refuse every admin."""
        fake = FakeCluster(groups=[])
        resolver = _resolver(monkeypatch, fake, verb="list", resource="pods", api_group="")
        resolver.tier_for("someone")
        attrs = fake.sar_bodies[0]["spec"]["resourceAttributes"]
        assert attrs["group"] == "" and "namespace" not in attrs

    def test_a_subresource_threshold_reaches_the_review(self, monkeypatch):
        """`pods/log` must be CHECKED as pods/log, not as pods.

        The chart's own guard accepts `resource: pods/log`, and config has split that into
        resource + subresource since the tier shipped — but the constructor never accepted the
        second half, so the review asked about `pods` instead. A different permission, possibly
        a BROADER one, admitting readers the operator meant to exclude, with nothing on screen
        or in the log to say the configured threshold was not the threshold applied.
        """
        fake = FakeCluster(groups=[])
        resolver = _resolver(monkeypatch, fake, verb="get", resource="pods",
                             api_group="", subresource="log")
        resolver.tier_for("someone")
        assert fake.sar_bodies[0]["spec"]["resourceAttributes"] == {
            "verb": "get", "resource": "pods", "group": "", "subresource": "log",
        }

    def test_no_subresource_omits_the_key_rather_than_sending_empty(self, monkeypatch):
        """An empty subresource is OMITTED rather than sent as `""`.

        The reason first written here was wrong and is corrected: it claimed the API server
        treats `""` as a value distinct from an absent key. Measured against the live cluster,
        `subresource: ""` and an omitted subresource produce the SAME verdict — they are
        equivalent, not different. So this test pins a wire-format convention, not a
        behavioural difference: the review we send should say only what the operator
        configured, and a key present-but-empty invites the next reader to wonder whether it
        meant something.
        """
        fake = FakeCluster(groups=[])
        _resolver(monkeypatch, fake, subresource="").tier_for("someone")
        assert "subresource" not in fake.sar_bodies[0]["spec"]["resourceAttributes"]


class TestFailClosed:
    def test_a_clean_denial_is_the_self_tier(self, monkeypatch):
        fake = FakeCluster(groups=[], allowed=False)
        assert _resolver(monkeypatch, fake).tier_for("lateef.o") == TIER_SELF

    def test_no_viewer_is_self_without_touching_the_cluster(self, monkeypatch):
        fake = FakeCluster(groups=[])
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("") == TIER_SELF
        assert resolver.tier_for(None) == TIER_SELF
        assert fake.group_lists == 0 and fake.sar_bodies == []

    @pytest.mark.parametrize(
        "break_it",
        [
            pytest.param(lambda f: setattr(f, "sar_status", 401), id="401"),
            pytest.param(lambda f: setattr(f, "sar_status", 403), id="403"),
            pytest.param(lambda f: setattr(f, "sar_status", 500), id="500"),
            pytest.param(
                lambda f: setattr(f, "raise_exc", httpx.ConnectTimeout("simulated timeout")),
                id="timeout",
            ),
            pytest.param(
                lambda f: setattr(f, "sar_body_override", {"kind": "SubjectAccessReview"}),
                id="missing-status",
            ),
            pytest.param(
                lambda f: setattr(f, "sar_body_override", {"status": {"allowed": "yes"}}),
                id="non-boolean-allowed",
            ),
            pytest.param(
                lambda f: (setattr(f, "sar_status", 200),
                           setattr(f, "sar_body_override", "<html>login</html>")),
                id="non-json",
            ),
        ],
    )
    def test_every_failure_collapses_to_the_self_tier(self, monkeypatch, break_it, caplog):
        """§5.4: an indeterminate answer is the self view, never the wide one — and it is
        said in the log, because the reader sees their own data rather than an error."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        break_it(fake)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_SELF
        assert "failing closed to the self view" in caplog.text

    def test_a_failure_is_not_cached_so_recovery_is_the_next_request(self, monkeypatch):
        """A failure is not a decision: caching one would pin an administrator to the narrow
        view for a full TTL over a transient API-server blip."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        fake.sar_status = 500
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_SELF
        fake.sar_status = 201
        assert resolver.tier_for("john.doe") == TIER_ALL


class TestTheCacheBoundsTheWindow:
    def test_a_decided_tier_is_cached_within_the_ttl(self, monkeypatch):
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        assert resolver.tier_for("john.doe") == TIER_ALL
        assert fake.group_lists == 1 and len(fake.sar_bodies) == 1

    def test_a_revoked_admin_loses_the_wide_view_after_the_ttl(self, monkeypatch):
        """DoD #8: the worst-case retained-visibility window is the TTL, and expiry re-reads
        BOTH inputs — the groups fresh from the cluster and the review against live RBAC."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake, ttl_seconds=0.05)
        assert resolver.tier_for("john.doe") == TIER_ALL
        fake.allowed = False                        # the revocation lands on the cluster
        assert resolver.tier_for("john.doe") == TIER_ALL   # inside the TTL: the stated window
        time.sleep(0.06)
        assert resolver.tier_for("john.doe") == TIER_SELF
        assert fake.group_lists == 2, "expiry must re-read the groups, not reuse the snapshot"

    def test_tiers_are_cached_per_viewer_not_globally(self, monkeypatch):
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        fake.allowed = False
        assert resolver.tier_for("lateef.o") == TIER_SELF
        assert resolver.tier_for("john.doe") == TIER_ALL


class TestSingleFlight:
    """Concurrent cold-cache requests for one viewer resolve ONCE.

    The browser dispatches four to seven API calls per refresh in ONE burst (index.html's
    refresh() went parallel, 2026-08-10), so every one of them hits a cold tier interval
    at the same instant. Unserialised, each raced into its own group-read + review —
    measured as the 120-250ms first-call penalty, multiplied by the burst width.

    Deterministic by gating, not by sleeping: the leader is held inside its group read
    until the followers have been started, so the followers provably arrive mid-flight.
    """

    def _gated(self, allowed: bool = True, sar_status: int = 201):
        entered, release = threading.Event(), threading.Event()

        class GatedFake(FakeCluster):
            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH:
                    entered.set()
                    release.wait(5)
                return super().handler(request)

        fake = GatedFake(groups=[_group("admins", ["john.doe"])], allowed=allowed)
        fake.sar_status = sar_status
        return fake, entered, release

    def _burst(self, resolver, entered, release, followers: int = 5) -> list[str]:
        results: list[str] = []
        record = lambda: results.append(resolver.tier_for("john.doe"))
        leader = threading.Thread(target=record)
        leader.start()
        assert entered.wait(5), "the leader never reached the cluster"
        rest = [threading.Thread(target=record) for _ in range(followers)]
        for t in rest:
            t.start()
        time.sleep(0.05)          # let the followers reach the in-flight wait
        release.set()
        leader.join(5)
        for t in rest:
            t.join(5)
        return results

    def test_a_cold_burst_asks_the_cluster_once_and_every_caller_gets_the_verdict(
        self, monkeypatch
    ):
        fake, entered, release = self._gated(allowed=True)
        resolver = _resolver(monkeypatch, fake)
        results = self._burst(resolver, entered, release)
        assert results == [TIER_ALL] * 6
        assert fake.group_lists == 1, "followers must ride the leader's read, not repeat it"
        assert len(fake.sar_bodies) == 1

    def test_followers_of_a_failed_leader_fail_closed_and_recovery_is_the_next_request(
        self, monkeypatch
    ):
        """The leader's failure is not cached (a failure is not a decision), and the
        followers inherit it as the self view for THEIR request only — the next request
        after the blip resolves fresh and wins the wide view back."""
        fake, entered, release = self._gated(allowed=True, sar_status=500)
        resolver = _resolver(monkeypatch, fake)
        results = self._burst(resolver, entered, release)
        assert results == [TIER_SELF] * 6
        assert fake.group_lists == 1, "a failed leader must not trigger follower re-resolves"
        fake.sar_status = 201
        assert resolver.tier_for("john.doe") == TIER_ALL


class TestSettings:
    def _write(self, tmp_path, text: str) -> str:
        p = tmp_path / "clusters.yaml"
        p.write_text(text)
        return str(p)

    def test_view_restrictions_default_on(self, tmp_path):
        """D1: this is a fix for an exposure; shipping it off by default leaves the exposure
        in place on exactly the installs that never read release notes."""
        s = load_settings(self._write(tmp_path, BASE_CONFIG))
        assert s.view_restrictions_enabled is True
        assert s.visibility_admin_sar_verb == "list"
        assert s.visibility_admin_sar_resource == "clusterrolebindings"
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_sar_namespace == ""

    def test_the_exact_env_var_spelling_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "false")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).view_restrictions_enabled is False

    def test_the_operators_typo_spelling_does_not_disable(self, tmp_path, monkeypatch):
        """The variable's spelling is load-bearing: the misspelled RESCRICTIONS variant is
        read by nothing, so setting it must leave the control ON, not silently off."""
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESCRICTIONS", "false")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).view_restrictions_enabled is True

    def test_a_malformed_disable_falls_back_to_restricted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "flase")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).view_restrictions_enabled is True

    def test_the_threshold_flows_from_the_configmap(self, tmp_path):
        cfg = BASE_CONFIG + (
            "visibilityAdminSarVerb: list\n"
            "visibilityAdminSarResource: rolebindings\n"
            "visibilityAdminSarApiGroup: rbac.authorization.k8s.io\n"
            "visibilityAdminSarNamespace: team-a\n"
        )
        s = load_settings(self._write(tmp_path, cfg))
        assert s.visibility_admin_sar_resource == "rolebindings"
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_sar_namespace == "team-a"

    # BOTH endpoints, because they are served by DIFFERENT resolvers and each has its own
    # `ttl_seconds=` argument to lose. Proven necessary by mutation: with only the /groups case,
    # deleting `ttl_seconds=` from the USAGE construction left this test green.
    #   /api/clusters/c1/groups  -> the wide tier   (app.state.tier_resolver)
    #   /api/dashboard/activity  -> the usage tier  (app.state.usage_tier_resolver)
    @pytest.mark.parametrize("endpoint", [
        "/api/clusters/c1/groups",
        "/api/dashboard/activity",
    ])
    @pytest.mark.parametrize("ttl,requests,pause,expected_reviews", [
        (60, 3, 0.0, 1),      # cached: one review answers all three requests
        (0, 3, 0.0, 3),       # caching off: a review per request, which is what 0 buys
        (1, 3, 0.6, 2),       # expires once across the two 0.6s gaps
    ])
    def test_the_configured_ttl_changes_how_often_the_cluster_IS_ASKED(
        self, tmp_path, endpoint, ttl, requests, pause, expected_reviews
    ):
        """The values key is only real if it changes BEHAVIOUR, so this counts the
        SubjectAccessReviews the cluster actually receives rather than reading `_ttl` back.

        Reading the attribute would pass while the number went unused — and that is not
        hypothetical: `visibility_tier_ttl_seconds` was once committed and documented while
        NOTHING passed it to the resolver, so the values file said 60 and the code used its own
        module constant. Each half was correct in isolation, which is exactly why an
        introspection assertion would not have caught it. The Usage tier later added a SECOND
        resolver, doubling the number of places that can quietly stop reading it.

        Real app, real TierResolver, real caching. Only the HTTP transport is faked, and the
        group listing must be a proper `items` collection — a body without one is REFUSED
        rather than read as "no groups" (a deliberate guard), which fails the tier closed
        before any review is attempted and would make this test count zero forever.
        """
        import httpx
        from fastapi.testclient import TestClient

        from gsd.api import build_app
        from gsd.config import ClusterConfig, Settings

        settings = Settings(
            clusters=[ClusterConfig("c1", "https://x", token_env="T")],
            db_path=str(tmp_path / "ttl.db"),
            oauth_proxy_enabled=True,
            visibility_tier_ttl_seconds=ttl,
        )
        app = build_app(settings, run_poller=False)
        assert app.state.tier_resolver is not None, "restrictions are on; the resolver must exist"
        assert app.state.usage_tier_resolver is not None
        # Separate instances with separate caches, so one verdict cannot answer the other's
        # question about the same person.
        assert app.state.tier_resolver is not app.state.usage_tier_resolver
        assert app.state.tier_resolver._cache is not app.state.usage_tier_resolver._cache

        reviews = {"n": 0}
        groups = {"kind": "GroupList",
                  "items": [{"metadata": {"name": "team-a"}, "users": ["someone"]}]}

        def handler(request):
            if "subjectaccessreviews" in str(request.url):
                reviews["n"] += 1
                return httpx.Response(201, json={"status": {"allowed": True}})
            return httpx.Response(200, json=groups)

        for resolver in (app.state.tier_resolver, app.state.usage_tier_resolver):
            resolver._kube._client = lambda: httpx.Client(
                transport=httpx.MockTransport(handler), base_url="https://x")

        scopes = []
        with TestClient(app) as client:
            for i in range(requests):
                if i and pause:
                    time.sleep(pause)
                scopes.append(client.get(
                    endpoint,
                    headers={"X-Forwarded-User": "someone"}).json()["scope"])

        assert scopes == ["all"] * requests, (
            f"the review said allowed, so every response must be the wide view; got {scopes} — "
            f"a 'self' here means the tier failed closed and the count below is meaningless"
        )
        assert reviews["n"] == expected_reviews, (
            f"ttl={ttl} over {requests} requests {pause}s apart should ask the cluster "
            f"{expected_reviews} time(s), asked {reviews['n']}"
        )

    def test_an_explicit_empty_api_group_means_core_not_the_default(self, tmp_path):
        """`or`-chaining would rewrite '' into user.openshift.io and silently change a
        core-group threshold into one that refuses every administrator."""
        cfg = BASE_CONFIG + 'visibilityAdminSarApiGroup: ""\n'
        assert load_settings(self._write(tmp_path, cfg)).visibility_admin_sar_api_group == ""


class TestObservedOutcomes:
    """The §3.1 observe seam (docs/DESIGN_metrics_refresh.md): one enum outcome per FRESH
    check, reported through a callback so kube.py never imports the metrics module.

    The vocabulary is load-bearing: allowed/denied are verdicts, everything else is a check
    that FAILED and served the self view fail-closed — the signal that makes a broken
    SubjectAccessReview distinguishable from a healthy quiet one.
    """

    @pytest.mark.parametrize(
        "mutate,expected",
        [
            pytest.param(lambda f: None, "allowed", id="allowed"),
            pytest.param(lambda f: setattr(f, "allowed", False), "denied", id="denied"),
            pytest.param(lambda f: setattr(f, "sar_status", 401), "auth_failed", id="401"),
            pytest.param(lambda f: setattr(f, "sar_status", 403), "forbidden", id="403"),
            pytest.param(
                lambda f: setattr(f, "raise_exc", httpx.ConnectTimeout("simulated timeout")),
                "unreachable", id="timeout"),
        ],
    )
    def test_verdicts_and_failures_map_to_the_outcome_enum(self, monkeypatch, mutate, expected):
        fake = FakeCluster(groups=[])
        mutate(fake)
        seen: list[str] = []
        _resolver(monkeypatch, fake, observe=seen.append).tier_for("someone")
        assert seen == [expected]

    def test_a_cache_hit_is_not_a_second_check(self, monkeypatch):
        """The counter counts decisions, not requests: a hit re-decides nothing."""
        fake = FakeCluster(groups=[])
        seen: list[str] = []
        resolver = _resolver(monkeypatch, fake, observe=seen.append)
        resolver.tier_for("someone")
        resolver.tier_for("someone")
        assert seen == ["allowed"] and fake.group_lists == 1

    def test_a_parallel_burst_produces_one_observation(self, monkeypatch):
        """The browser dispatches its refresh in one burst; single-flight makes that ONE
        fresh check, and the counter must agree — six failures for one outage would make
        every rate threshold wrong. Deterministic by gating, the TestSingleFlight idiom."""
        entered, release = threading.Event(), threading.Event()

        class Gated(FakeCluster):
            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH:
                    entered.set()
                    release.wait(5)
                return super().handler(request)

        fake = Gated(groups=[])
        seen: list[str] = []
        resolver = _resolver(monkeypatch, fake, observe=seen.append)
        leader = threading.Thread(target=lambda: resolver.tier_for("someone"))
        leader.start()
        assert entered.wait(5), "the leader never reached the cluster"
        followers = [threading.Thread(target=lambda: resolver.tier_for("someone"))
                     for _ in range(5)]
        for t in followers:
            t.start()
        time.sleep(0.05)          # let the followers reach the in-flight wait
        release.set()
        for t in (leader, *followers):
            t.join(5)
        assert seen == ["allowed"], f"six parallel requests, one check — saw {seen}"

    def test_a_broken_callback_never_breaks_the_decision(self, monkeypatch):
        """Best-effort by contract: a metrics bug must not become a security bug."""
        def boom(outcome: str) -> None:
            raise RuntimeError("observer bug")

        fake = FakeCluster(groups=[])
        assert _resolver(monkeypatch, fake, observe=boom).tier_for("someone") == TIER_ALL


class TestAWedgedLeaderDoesNotPinTheViewer:
    """A resolution that never returns must not pin its viewer to the self tier forever.

    THE DEFECT. The in-flight slot was released only in the leader's `finally`, so a leader
    stuck past its own worst case — blocked in the observe callback, or on I/O outliving the
    client timeout — kept the entry indefinitely. Every later request for that viewer became a
    follower, waited the full `TIER_CHECK_TIMEOUT_SECONDS * 2 + 1` budget, found no cache entry
    and fell back to the self tier. One stuck resolution therefore demoted an administrator
    permanently and added ~11s to each of their requests, and nothing reported a fault, because
    failing closed on an indeterminate check is the designed behaviour.

    A follower whose wait expires now steals the slot and resolves the viewer itself.
    """

    @staticmethod
    def _fast_budget(monkeypatch) -> float:
        """Shrink the follower wait so the wedge is testable in about a second.

        `tier_for` reads TIER_CHECK_TIMEOUT_SECONDS at call time, so patching the module global
        works; the mocked transport means the client's own timeout is never consulted.
        """
        monkeypatch.setattr("gsd.kube.TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        return 0.05 * 2 + 1

    def test_a_follower_steals_the_slot_and_resolves(self, monkeypatch) -> None:
        budget = self._fast_budget(monkeypatch)
        entered = threading.Event()
        release = threading.Event()

        class WedgedOnce(FakeCluster):
            """Blocks the FIRST group list; later calls answer normally."""

            def __init__(self) -> None:
                super().__init__([_group("admins", ["admin"])], allowed=True)
                self.blocked = False

            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH and not self.blocked:
                    self.blocked = True
                    entered.set()
                    # Bounded so a regression is a failure, not a hung suite.
                    release.wait(30)
                return super().handler(request)

        fake = WedgedOnce()
        resolver = _resolver(monkeypatch, fake)
        leader_result: list[str] = []
        leader = threading.Thread(
            target=lambda: leader_result.append(resolver.tier_for("admin")), daemon=True
        )
        leader.start()
        try:
            assert entered.wait(5), "the leader never reached the wedged call"
            started = time.monotonic()
            stolen = resolver.tier_for("admin")
            waited = time.monotonic() - started
        finally:
            release.set()
            leader.join(timeout=10)

        assert stolen == TIER_ALL, (
            "the follower gave up on the wedged leader and returned the self tier without "
            "resolving; before the fix this recurred for every later request, so an "
            "administrator stayed narrowed for as long as the leader stayed stuck"
        )
        assert waited >= budget, "the follower should have ridden the leader before stealing"
        assert leader_result == [TIER_ALL], "the wedged leader's own answer changed"

    def test_the_steal_is_cached_so_later_requests_do_not_wait(self, monkeypatch) -> None:
        """The point of stealing is that the NEXT request is fast, not merely correct."""
        self._fast_budget(monkeypatch)
        entered = threading.Event()
        release = threading.Event()

        class WedgedOnce(FakeCluster):
            def __init__(self) -> None:
                super().__init__([_group("admins", ["admin"])], allowed=True)
                self.blocked = False

            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH and not self.blocked:
                    self.blocked = True
                    entered.set()
                    release.wait(30)
                return super().handler(request)

        fake = WedgedOnce()
        resolver = _resolver(monkeypatch, fake)
        leader = threading.Thread(target=lambda: resolver.tier_for("admin"), daemon=True)
        leader.start()
        try:
            assert entered.wait(5)
            assert resolver.tier_for("admin") == TIER_ALL      # steals and caches
            started = time.monotonic()
            third = resolver.tier_for("admin")
            elapsed = time.monotonic() - started
        finally:
            release.set()
            leader.join(timeout=10)

        assert third == TIER_ALL
        assert elapsed < 0.5, (
            f"the third request took {elapsed:.2f}s, so the steal did not cache its answer and "
            f"every request keeps paying the follower wait"
        )

    def test_the_stolen_from_leader_leaves_the_slot_clean(self, monkeypatch) -> None:
        """Its late return must not evict the stealer's entry, and must not leak its own.

        Deleting an entry it no longer owns would drop the single-flight guarantee for a viewer
        who has a resolution in progress, so a burst would issue one review each.
        """
        self._fast_budget(monkeypatch)
        entered = threading.Event()
        release = threading.Event()

        class WedgedOnce(FakeCluster):
            def __init__(self) -> None:
                super().__init__([_group("admins", ["admin"])], allowed=True)
                self.blocked = False

            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH and not self.blocked:
                    self.blocked = True
                    entered.set()
                    release.wait(30)
                return super().handler(request)

        fake = WedgedOnce()
        resolver = _resolver(monkeypatch, fake)
        leader = threading.Thread(target=lambda: resolver.tier_for("admin"), daemon=True)
        leader.start()
        try:
            assert entered.wait(5)
            resolver.tier_for("admin")
        finally:
            release.set()
            leader.join(timeout=10)

        assert resolver._inflight == {}, (
            f"in-flight slots left behind: {resolver._inflight!r}. A leaked entry is the defect "
            f"this class exists for; an evicted one costs the single-flight guarantee"
        )


class TestABlockingObserveCallbackCannotStopTheCacheWrite:
    """`_note` reports the outcome; it must not stand between the answer and the cache.

    It calls out to the metrics seam and is best-effort by contract, but it is not bounded. It
    used to run BEFORE the cache write, so a callback that blocked prevented the decided tier
    from ever being cached while also holding the in-flight slot — a metrics stall presenting as
    a broken tier check. Nothing in the caching needs the metric to have been recorded.
    """

    def test_the_tier_is_cached_before_the_outcome_is_reported(self, monkeypatch) -> None:
        monkeypatch.setattr("gsd.kube.TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        blocking = threading.Event()
        noted = threading.Event()

        def observe(outcome: str) -> None:
            noted.set()
            blocking.wait(30)

        fake = FakeCluster([_group("admins", ["admin"])], allowed=True)
        resolver = _resolver(monkeypatch, fake, observe=observe)
        leader = threading.Thread(target=lambda: resolver.tier_for("admin"), daemon=True)
        leader.start()
        try:
            assert noted.wait(5), "the observe callback was never reached"
            started = time.monotonic()
            second = resolver.tier_for("admin")
            elapsed = time.monotonic() - started
        finally:
            blocking.set()
            leader.join(timeout=10)

        assert second == TIER_ALL, (
            "a blocked metrics callback denied a second reader the tier that had already been "
            "decided and returned to the first"
        )
        assert elapsed < 0.5, (
            f"the second request took {elapsed:.2f}s: it rode the in-flight slot instead of "
            f"reading a cache entry that should already have been written"
        )
        assert fake.group_lists == 1, "the cached answer should have served the second request"


class TestStealingDoesNotTurnAnOutageIntoAStampede:
    """A leader that FAILED is a decision, not a wedge, and its followers must not retry it.

    Behaviour-preservation for the steal above. A failure wakes the followers by setting the
    event, and a woken follower fails closed for its own request without resolving again. If it
    stole instead, an unreachable API server would turn every burst of requests into a burst of
    reviews against the thing that is already down — each one waiting out its own timeout.

    The retry still happens, just per later request rather than per queued follower: failures are
    deliberately not cached, so the next arrival finds no slot and leads.
    """

    def test_followers_of_a_failed_leader_do_not_resolve_again(self, monkeypatch) -> None:
        monkeypatch.setattr("gsd.kube.TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        in_call = threading.Event()
        let_fail = threading.Event()

        class FailsSlowly(FakeCluster):
            """Holds the first group list open, then fails it — a leader that loses, slowly."""

            def __init__(self) -> None:
                super().__init__([_group("admins", ["admin"])], allowed=True)
                self.attempts = 0

            def handler(self, request: httpx.Request) -> httpx.Response:
                if request.url.path == GROUPS_PATH:
                    self.attempts += 1
                    if self.attempts == 1:
                        in_call.set()
                        let_fail.wait(30)
                        return httpx.Response(503, json={"message": "down"})
                return super().handler(request)

        fake = FailsSlowly()
        resolver = _resolver(monkeypatch, fake)
        leader_result: list[str] = []
        leader = threading.Thread(
            target=lambda: leader_result.append(resolver.tier_for("admin")), daemon=True
        )
        leader.start()
        assert in_call.wait(5)

        follower: list[str] = []
        rider = threading.Thread(
            target=lambda: follower.append(resolver.tier_for("admin")), daemon=True
        )
        rider.start()
        # Let the leader fail while the follower is still riding it, so the follower is woken by
        # the failure rather than by its own timeout expiring.
        time.sleep(0.2)
        let_fail.set()
        leader.join(timeout=10)
        rider.join(timeout=10)

        assert leader_result == [TIER_SELF], "a 503 must fail closed"
        assert follower == [TIER_SELF], "the follower must inherit the failure, closed"
        assert fake.attempts == 1, (
            f"the cluster was asked {fake.attempts} times for one decision: a woken follower "
            f"retried instead of failing closed, so an outage now costs a review per follower"
        )
        assert resolver._inflight == {}
