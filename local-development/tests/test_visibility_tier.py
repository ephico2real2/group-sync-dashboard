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
import time

import httpx
import pytest

from gsd.config import ClusterConfig, load_settings
from gsd.kube import (
    SAR_API,
    TIER_ALL,
    TIER_SELF,
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
        assert s.visibility_admin_sar_resource == "groups"
        assert s.visibility_admin_sar_api_group == "user.openshift.io"
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

    def test_an_explicit_empty_api_group_means_core_not_the_default(self, tmp_path):
        """`or`-chaining would rewrite '' into user.openshift.io and silently change a
        core-group threshold into one that refuses every administrator."""
        cfg = BASE_CONFIG + 'visibilityAdminSarApiGroup: ""\n'
        assert load_settings(self._write(tmp_path, cfg)).visibility_admin_sar_api_group == ""
