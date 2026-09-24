"""A lookup-owned Secret takes its stanza's policy and switch; any other Secret wins wholesale
(docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.4).

Ownership is the test the reader already makes: the Secret's `groupsync-dashboard.io/token-source` annotation
equals the credential kind of the values stanza of the same name. The reader records it on the parsed config
(`ClusterConfig.token_source`) and `ClusterRegistry.merge` keeps the Secret's credential and serves the stanza's
`visibility`, `identity` and `enabled`. Driven through the real reader, registry and `Poller._discover_once` over
Secrets kept the way the API server keeps them.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging

import pytest

import gsd.poller as poller_mod
from gsd.clusterconfig import ClusterRegistry
from gsd.config import ClusterConfig, Settings
from gsd.fleetlookup import SaToken, store
from gsd.kube import ClusterError, RemoteTierResolvers
from gsd.poller import Poller
from gsd.store import Store

TOKEN_SOURCE = "groupsync-dashboard.io/token-source"
SA_TOKEN = "eyJhbGciOiJSUzI1NiJ9.a-lookup-written-token-aaaaaaaaaaaaaaaa.sig"


class _Host:
    """The host API's labelled Secrets in the pod's namespace: LIST for discovery, GET/POST/PUT for the writer."""

    def __init__(self, cfg=None, timeout=15.0):
        pass

    secrets: dict[str, dict] = {}

    def _client(self):
        class _Ctx:
            def __enter__(self_inner):  # noqa: N805
                return self_inner

            def __exit__(self_inner, *a):  # noqa: N805
                return False
        return _Ctx()

    def _list_all_with(self, client, path, extra):
        return [copy.deepcopy(o) for o in _Host.secrets.values()]

    def _get(self, client, path, params):
        name = path.rsplit("/", 1)[1]
        if name not in _Host.secrets:
            raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")
        return copy.deepcopy(_Host.secrets[name])

    def _send(self, client, method, path, *, json=None, secrets=()):
        obj = copy.deepcopy(json)
        data = dict(obj.get("data") or {})
        for k, v in (obj.pop("stringData", None) or {}).items():
            data[k] = base64.b64encode(str(v).encode()).decode()
        obj["data"] = data
        _Host.secrets[obj["metadata"]["name"]] = obj
        return None


def _secret(cluster: str, *, annotations: dict | None = None, **data) -> dict:
    payload = {"name": cluster, "server": f"https://api.{cluster}.example:6443",
               "config": json.dumps({"bearerToken": "sha256~a-hand-made-token-bbbbbbbb"}), **data}
    return {"metadata": {"name": f"gsd-cluster-{cluster}", "labels": {"groupsync-dashboard.io/secret-type": "cluster"},
                         "annotations": dict(annotations or {})},
            "data": {k: base64.b64encode(str(v).encode()).decode() for k, v in payload.items()}}


@pytest.fixture
def discovering(tmp_path, monkeypatch):
    monkeypatch.setattr(poller_mod, "own_namespace", lambda: "ns")
    monkeypatch.setattr(poller_mod, "ClusterClient", _Host)
    _Host.secrets = {}

    def make(*stanzas: ClusterConfig):
        settings = Settings(clusters=[ClusterConfig("home", "https://kubernetes.default.svc", token_env="X",
                                                    dashboard_controller=True), *stanzas],
                            db_path=str(tmp_path / "p.db"), view_restrictions_enabled=True)
        db = Store(settings.db_path)
        return settings, Poller(db, settings), db
    return make


RND = ClusterConfig("rnd", "https://api.rnd.example:6443", sa_token_lookup=True)
OWNED = {TOKEN_SOURCE: "remote-lookup"}


class TestTheMerge:
    def test_an_owned_secret_keeps_its_credential_and_source_and_serves_the_stanzas_policy(self):
        reg = ClusterRegistry()
        found = dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                  source="secret:gsd-cluster-rnd", visibility="self-only",
                                                  identity="none"), token_source="remote-lookup")
        reg.replace([found], [], at="t")
        served, = [c for c in reg.merge([dataclasses.replace(RND, visibility="hidden")]) if c.name == "rnd"]
        assert (served.source, served.token_value, served.credential_kind) == ("secret:gsd-cluster-rnd", "sha256~t-aaaaaaaa", "bearer")
        assert (served.visibility, served.identity) == ("hidden", None), "the stanza's policy, as stated"

    @pytest.mark.parametrize("token_source", [None, "self-login"], ids=["unowned", "another-mode"])
    def test_any_other_secret_over_a_mode_stanza_wins_wholesale(self, token_source):
        reg = ClusterRegistry()
        found = dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                  source="secret:gsd-cluster-rnd", visibility="self-only",
                                                  enabled=False), token_source=token_source)
        reg.replace([found], [], at="t")
        served, = [c for c in reg.merge([RND]) if c.name == "rnd"]
        assert served == found and (served.visibility, served.enabled) == ("self-only", False)

    def test_a_plain_values_entry_is_replaced_wholesale_and_a_secret_with_no_entry_is_appended(self):
        reg = ClusterRegistry()
        east = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~t-aaaaaaaa",
                             source="secret:gsd-cluster-east", token_source="remote-lookup")
        tab = ClusterConfig("tab", "https://api.tab.example:6443", token_value="sha256~t-bbbbbbbb", source="secret:gsd-cluster-tab")
        reg.replace([east, tab], [], at="t")
        stanza = ClusterConfig("east", "https://api.east.example:6443", token_env="X", visibility="self-only")
        merged = reg.merge([stanza])
        assert [c.name for c in merged] == ["east", "tab"]
        assert merged[0] is east, "no connection mode on the stanza: the Secret wins, policy included"

    @pytest.mark.parametrize("stanza_enabled,secret_enabled,served", [(False, True, False), (True, False, False),
                                                                       (True, True, True)])
    def test_either_side_may_disable_an_owned_secret(self, stanza_enabled, secret_enabled, served):
        reg = ClusterRegistry()
        reg.replace([dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                       source="secret:gsd-cluster-rnd", enabled=secret_enabled),
                                         token_source="remote-lookup")], [], at="t")
        merged, = [c for c in reg.merge([dataclasses.replace(RND, enabled=stanza_enabled)]) if c.name == "rnd"]
        assert merged.enabled is served

    def test_replace_keeps_every_compare_false_credential_field(self):
        found = ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa", ca_data="PEM",
                              source="secret:gsd-cluster-rnd", token_source="remote-lookup")
        served = dataclasses.replace(found, visibility="self-only", identity="none", enabled=True)
        assert (served.token_value, served.ca_data, served.oauth_username, served.oauth_password) == \
               ("sha256~t-aaaaaaaa", "PEM", None, None)
        assert served.connection_fingerprint() == found.connection_fingerprint()


class TestDiscoveryServesAndSaysTheStanzasPolicy:
    def test_the_resolved_line_prints_the_served_pair_not_the_secrets_own(self, discovering, caplog):
        settings, poller, _ = discovering(RND)
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", annotations=OWNED, visibility="self-only", identity="none")}
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._discover_once()
        assert settings.cluster_policy("rnd") == ("remote-sar", "same-as-host")
        line, = [m for m in caplog.messages if m.startswith("cluster-resolved ") and "cluster=rnd" in m]
        assert "visibility=remote-sar identity=same-as-host enabled=true" in line, line

    def test_an_ownership_flip_alone_logs_the_pair_now_served(self, discovering, caplog):
        settings, poller, _ = discovering(RND)
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", visibility="self-only")}
        poller._discover_once()
        assert settings.cluster_policy("rnd") == ("self-only", "none")
        for annotations, pair in ((OWNED, "visibility=remote-sar identity=same-as-host"),
                                  ({}, "visibility=self-only identity=none")):
            _Host.secrets["gsd-cluster-rnd"]["metadata"]["annotations"] = dict(annotations)
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="gsd"):
                poller._discover_once()
            lines = [m for m in caplog.messages if m.startswith("cluster-resolved ") and "cluster=rnd" in m]
            assert lines and pair in lines[-1], caplog.messages

    def test_a_disabled_lookup_stanza_is_not_served_polled_or_reviewed(self, discovering, caplog):
        settings, poller, db = discovering(dataclasses.replace(RND, enabled=False))
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", annotations=OWNED, visibility="remote-sar",
                                                    identity="same-as-host", enabled="true")}
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._discover_once()
        assert settings.cluster("rnd").enabled is False
        assert next(r for r in db.clusters() if r["id"] == "rnd")["enabled"] == 0
        assert any("cluster=rnd" in m and "enabled=false" in m for m in caplog.messages if m.startswith("cluster-resolved "))
        assert RemoteTierResolvers(settings, lambda c: pytest.fail("built for a disabled cluster")).get("rnd") is None


class TestTheLookupWritesThePairItServes:
    @pytest.mark.parametrize("stanza", [RND, dataclasses.replace(RND, visibility="self-only")], ids=["unstated", "self-only"])
    def test_the_pair_the_lookup_writes_is_the_pair_served_before_and_after_discovery(self, discovering, stanza):
        settings, poller, _ = discovering(stanza)
        before = settings.cluster_policy("rnd")
        store(_Host(), "ns", settings.cluster("rnd"), settings,
              SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="group-sync-dashboard-cluster-poller"),
              account="ocp-oauth-bind-serviceid")
        data = {k: base64.b64decode(v).decode() for k, v in _Host.secrets["gsd-cluster-rnd"]["data"].items()}
        assert (data["visibility"], data["identity"]) == before
        poller._discover_once()
        assert settings.cluster("rnd").source == "secret:gsd-cluster-rnd"
        assert settings.cluster_policy("rnd") == before
