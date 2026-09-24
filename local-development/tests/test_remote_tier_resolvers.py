"""Resolvers follow the cluster's current configuration (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.1),
and the review's error text is redacted before it is truncated (§3.6).

`RemoteTierResolvers.get` finds or builds one TierResolver per remote-sar cluster on each request, from ONE merged
`ClusterConfig` snapshot, keyed by `ClusterConfig.connection_fingerprint()` — equality cannot see a rotated Secret
credential, which is compare=False by design.
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.kube import (
    REMOTE_FAILURE_HOLD_SECONDS, SAR_API, ClusterClient, ClusterError, RemoteTierResolvers, TierResolver,
)

PEM_A = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"
PEM_B = "-----BEGIN CERTIFICATE-----\nBBBB\n-----END CERTIFICATE-----\n"


def _settings(tmp_path, *values: ClusterConfig, **kw) -> Settings:
    host = ClusterConfig("home", "https://kubernetes.default.svc", token_env="X", dashboard_controller=True)
    return Settings(clusters=[host, *values], db_path=str(tmp_path / "r.db"), **{"view_restrictions_enabled": True, **kw})


def _secret(name: str = "east", **kw) -> ClusterConfig:
    base = dict(api_url=f"https://api.{name}.example:6443", token_value="sha256~token-one-aaaaaaaa",
                source=f"secret:gsd-cluster-{name}")
    return ClusterConfig(name, **{**base, **kw})


class _Built:
    """A `make` that records what it was built from and hands back a distinct object per build."""

    def __init__(self) -> None:
        self.configs: list[ClusterConfig] = []

    def __call__(self, c: ClusterConfig):
        self.configs.append(c)
        return object()


class TestTheResolverFollowsTheCurrentConfiguration:
    def test_a_secret_declared_cluster_gets_a_resolver_and_the_same_one_while_nothing_changes(self, tmp_path):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        first = pool.get("east")
        assert first is not None and pool.get("east") is first
        settings.cluster_registry.replace([_secret()], [], at="t1")      # the next discovery, the same Secret
        assert pool.get("east") is first and len(built.configs) == 1

    @pytest.mark.parametrize("change", [
        {"token_value": "sha256~token-two-bbbbbbbb"},
        {"ca_data": PEM_B},
        {"api_url": "https://api.east-2.example:6443"},
        {"insecure_skip_verify": True},
    ], ids=["token", "ca", "url", "insecure"])
    def test_a_connection_change_builds_a_new_resolver_on_the_new_values(self, tmp_path, change):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret(ca_data=PEM_A)], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        first = pool.get("east")
        settings.cluster_registry.replace([dataclasses.replace(_secret(ca_data=PEM_A), **change)], [], at="t1")
        second = pool.get("east")
        assert second is not first
        for key, value in change.items():
            assert getattr(built.configs[-1], key) == value

    def test_a_values_entry_rebuilds_on_a_named_file_but_not_on_its_content(self, tmp_path):
        """A tokenFile's content and a caBundleFile's are re-read by every ClusterClient._client call; only
        their names are fixed on the config, and only a name moves the fingerprint."""
        a = ClusterConfig("far", "https://api.far.example:6443", token_file="/etc/gsd/far/token")
        b = dataclasses.replace(a, token_file="/etc/gsd/far/token-2")
        assert a.connection_fingerprint() == dataclasses.replace(a).connection_fingerprint()
        assert a.connection_fingerprint() != b.connection_fingerprint()
        assert a.connection_fingerprint() != dataclasses.replace(a, ca_bundle_file="/etc/gsd/far/ca.crt").connection_fingerprint()

    def test_a_policy_change_is_not_a_connection_change(self, tmp_path):
        a = _secret()
        assert a.connection_fingerprint() == dataclasses.replace(a, visibility="remote-sar", identity="same-as-host",
                                                                  labels=(("team", "x"),)).connection_fingerprint()

    @pytest.mark.parametrize("case", ["retired", "disabled", "pending", "host", "hidden", "inherit", "self-only",
                                      "remote-sar with identity none"])
    def test_none_and_the_entry_forgotten_for_a_cluster_that_is_not_an_askable_remote(self, tmp_path, case):
        settings = _settings(tmp_path, ClusterConfig("rnd", "https://api.rnd.example:6443", sa_token_lookup=True))
        settings.cluster_registry.replace([_secret()], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        assert pool.get("east") is not None
        cluster = "east"
        if case == "retired":
            settings.cluster_registry.replace([], [], at="t1")
        elif case == "disabled":
            settings.cluster_registry.replace([_secret(enabled=False)], [], at="t1")
        elif case == "pending":
            cluster = "rnd"                                      # the stanza's lookup has not written its Secret
        elif case == "host":
            cluster = "home"
        elif case == "remote-sar with identity none":           # refused by every reader; a hand-built Settings
            settings.cluster_registry.replace([_secret(visibility="remote-sar", identity="none")], [], at="t1")
        else:
            settings.cluster_registry.replace([_secret(visibility=case)], [], at="t1")
        assert pool.get(cluster) is None
        if cluster == "east":
            assert "east" not in pool._built, "a cluster that stopped being askable keeps no resolver"
        assert len(built.configs) == 1

    @pytest.mark.parametrize("case", ["retired", "disabled"])
    def test_a_cluster_nobody_asks_about_again_keeps_no_resolver_or_credential(self, tmp_path, case):
        """A retired or disabled cluster is not served, so viewer_scope never asks the pool for it again: the next
        lookup of ANY remote must drop its resolver, and with it the configuration carrying the Secret's token."""
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret(), _secret("west")], [], at="t0")
        pool = RemoteTierResolvers(settings, _Built())
        assert pool.get("east") is not None and pool.get("west") is not None
        gone = [_secret("west")] if case == "retired" else [_secret(enabled=False), _secret("west")]
        settings.cluster_registry.replace(gone, [], at="t1")
        assert pool.get("west") is not None
        assert "east" not in pool._built, "a resolver outlived its cluster's configuration"

    def test_one_configuration_snapshot_per_lookup(self, tmp_path):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        reads = []
        real = settings.cluster_registry.merge

        def merge(values):
            reads.append(1)
            return real(values)
        object.__setattr__(settings.cluster_registry, "merge", merge)
        RemoteTierResolvers(settings, _Built()).get("east")
        assert len(reads) == 1, "the policy must be resolved from the snapshot the connection came from"


class TestTheAppBuildsThePool:
    def test_the_pool_builds_each_remote_on_its_own_api_with_the_hold(self, tmp_path):
        settings = _settings(tmp_path, ClusterConfig("far", "https://api.far.example:6443", token_env="X"),
                             oauth_proxy_enabled=True)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        app = build_app(settings, run_poller=False)
        pool = app.state.remote_tier_resolvers
        assert isinstance(pool, RemoteTierResolvers) and pool.get("home") is None
        for name in ("far", "east"):                             # a values entry and a Secret, neither states a policy
            r = pool.get(name)
            assert isinstance(r, TierResolver) and r._kube.cluster.name == name
            assert r._hold == REMOTE_FAILURE_HOLD_SECONDS
            assert r._attributes == {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}

    def test_restrictions_off_builds_no_pool(self, tmp_path):
        app = build_app(_settings(tmp_path, view_restrictions_enabled=False), run_poller=False)
        assert app.state.remote_tier_resolvers == {}


# ── §3.6: the review's error text is redacted before it is truncated ─────────────────────────────────────────
JWT = "eyJhbGciOiJSUzI1NiJ9." + "A" * 700 + ".signature-part-zzzzzzzz"


def _client_answering(monkeypatch, handler) -> ClusterClient:
    cluster = ClusterConfig("west", "https://api.west.example:6443", token_value=JWT, source="secret:gsd-cluster-west")
    client = ClusterClient(cluster, timeout=5.0)
    monkeypatch.setattr(client, "_client", lambda: httpx.Client(
        base_url=cluster.api_url, headers={"Authorization": f"Bearer {JWT}"}, transport=httpx.MockTransport(handler)))
    return client


class TestTheReviewsErrorTextIsRedacted:
    def test_a_jwt_echoed_in_an_error_body_never_reaches_the_message_even_across_the_cut(self, monkeypatch):
        client = _client_answering(monkeypatch, lambda request: httpx.Response(
            502, text="x" * 150 + " proxy echo: Bearer " + JWT + " " + "y" * 100))
        with pytest.raises(ClusterError) as exc:
            client.create_subject_access_review("alice", [], {"verb": "list", "resource": "clusterrolebindings"})
        message = exc.value.message
        assert message.startswith(f"HTTP 502 on {SAR_API}: ") and "<redacted>" in message
        assert JWT[:24] not in message, "a prefix of the token survived the 200-character cut"

    def test_a_connect_error_carrying_the_credential_is_redacted(self, monkeypatch):
        def refuse(request):
            raise httpx.ConnectError(f"proxy said no to Bearer {JWT}", request=request)
        client = _client_answering(monkeypatch, refuse)
        with pytest.raises(ClusterError) as exc:
            client.create_subject_access_review("alice", [], {"verb": "list", "resource": "clusterrolebindings"})
        assert exc.value.outcome == "unreachable" and JWT[:24] not in exc.value.message
        assert json.dumps(exc.value.message).count("<redacted>") == 1
