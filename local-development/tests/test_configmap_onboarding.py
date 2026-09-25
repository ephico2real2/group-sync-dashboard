"""SPEC_S5: complete inventories, shared parsing, guarded ownership, and the #284 bind budget."""
from __future__ import annotations

import base64
import copy
import dataclasses
import json
import threading

import httpx
import pytest
import yaml

from gsd.clusterconfig import CONFIG_SELECTOR, CONFIG_TYPE_LABEL, LABEL_SELECTOR
from gsd.clusterconfig.onboarding import discover_onboarding
from gsd.clusterconfig.writer import (
    MANAGED_BY_ANNOTATION, MANAGED_BY_ONBOARD, CONFIGMAP_UID_ANNOTATION,
    CreateRequest, WriteRefused, onboarding_owner, rotate, secret_object,
)
from gsd.config import ClusterConfig, ConfigError, load_settings, parse_cluster_entries
from gsd.fleetlookup import CredentialGate, LookupRefused, lookup
from gsd.kube import ClusterError
from gsd.poller import Poller
from gsd.store import Store
from test_clusterconfig_tab import _Host, _as_stored
from test_fleet_lookup import API, PASSWORD, USER, SA_TOKEN, settings, wire  # noqa: F401
from test_fleet_login import login_302, refused_401

STANZA = {"name": "rnd", "apiUrl": API, "saTokenLookup": True, "ldapConnectionBootstrap": USER}


def cm(entries=None, *, name="fleet", uid="cm-1", label="onboard"):
    return {"metadata": {"name": name, "uid": uid, "labels": {CONFIG_TYPE_LABEL: label}},
            "data": {"clusters.yaml": yaml.safe_dump({"clusters": [STANZA] if entries is None else entries})}}


class Host(_Host):
    def __init__(self, maps=None):
        password = {"metadata": {"name": "gsd-fleet-account"},
                    "data": {"password": base64.b64encode(PASSWORD.encode()).decode()}}
        super().__init__({"gsd-fleet-account": password})
        self.maps = [cm()] if maps is None else maps
        self.lists = []
        self.fail_list = None
        self.fail_delete = False
        self.serial = 1
        self.mutations = []
        self.race = False

    def _list_all_with(self, client, path, params):
        self.lists.append((path, params))
        if path.endswith(self.fail_list or "never"):
            raise ClusterError("forbidden", "HTTP 403 on inventory")
        objects = self.maps if path.endswith("/configmaps") else self.secrets.values()
        selector = params.get("labelSelector", "")
        if not selector:
            return copy.deepcopy(list(objects))
        if " in " in selector:
            key, values = selector.split(" in ", 1)
            allowed = {value.strip() for value in values.strip("()").split(",")}
        else:
            key, value = selector.split("=", 1)
            allowed = {value}
        return copy.deepcopy([obj for obj in objects
                              if obj.get("metadata", {}).get("labels", {}).get(key.strip()) in allowed])

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.mutations.append((method, path, copy.deepcopy(json)))
        name = json["metadata"]["name"] if method == "POST" else path.rsplit("/", 1)[-1]
        if method == "DELETE":
            if self.fail_delete:
                raise ClusterError("forbidden", "HTTP 403 on delete")
            if self.race:
                self.secrets[name]["metadata"]["uid"] = "replacement"
            meta = self.secrets[name]["metadata"]
            assert json["preconditions"] == {"uid": "secret-1", "resourceVersion": "1"}
            if any(meta[k] != v for k, v in json["preconditions"].items()):
                raise ClusterError("unreachable", "HTTP 409 on delete")
        if method == "POST" and name in self.secrets:
            raise ClusterError("unreachable", "HTTP 409 on create")
        if method == "PUT":
            if json["metadata"]["resourceVersion"] != self.secrets[name]["metadata"]["resourceVersion"]:
                raise ClusterError("unreachable", "HTTP 409 on update")
        result = super()._send(client, method, path, json=json, secrets=secrets)
        if method != "DELETE":
            self.secrets[name]["metadata"].update(uid="secret-1", resourceVersion=str(self.serial))
            self.serial += 1
        return result


def cycle(host, s=None, *, mutate=True):
    s = s or settings()
    clusters, findings, blocked = discover_onboarding(host, "ns", settings=s, mutate=mutate)
    s.cluster_registry.replace(clusters, findings, at="now", blocked=blocked)
    return s, clusters, findings, blocked


def generated(host, s=None, gate=None):
    s, clusters, _, _ = cycle(host, s)
    declaration, = clusters
    lookup(declaration, s, host, own_namespace="ns", gate=gate or CredentialGate(), sleep=lambda _: None)
    return s


@pytest.mark.parametrize("label", ["onboard", "sideload"])
def test_full_loop_uses_each_synonym_and_the_existing_secret_reader(label, wire):
    host = Host([cm(label=label)])
    s = generated(host)
    _, clusters, findings, _ = cycle(host, s)
    cluster, = clusters
    assert not findings and cluster.source == "secret:gsd-cluster-rnd" and cluster.credential_kind == "bearer"
    assert cluster.resolve_token() == SA_TOKEN and cluster.onboarding[:2] == ("fleet", "cm-1")
    obj = host.secrets["gsd-cluster-rnd"]
    assert obj["metadata"]["labels"] == {"groupsync-dashboard.io/secret-type": "cluster"}
    assert obj["metadata"]["annotations"][MANAGED_BY_ANNOTATION] == MANAGED_BY_ONBOARD
    assert onboarding_owner(obj) == cluster.onboarding
    assert host.lists[:2] == [("/api/v1/namespaces/ns/configmaps", {"labelSelector": CONFIG_SELECTOR}),
                             ("/api/v1/namespaces/ns/secrets", {"labelSelector": LABEL_SELECTOR})]
    assert len(wire.authorize) == 1 and len(wire.revokes) == 1
    writes = len(host.mutations)
    cycle(host, s)
    assert len(host.mutations) == writes, "unchanged reconciliation must not write"


def test_values_and_configmap_call_the_same_parser(tmp_path, monkeypatch):
    import gsd.config as config
    import gsd.clusterconfig.onboarding as onboarding
    calls = []
    real = parse_cluster_entries
    def record(*a, **kw):
        calls.append(kw.get("remote_host"))
        return real(*a, **kw)
    monkeypatch.setattr(config, "parse_cluster_entries", record)
    monkeypatch.setattr(onboarding, "parse_cluster_entries", record)
    home = {"name": "host", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X"}
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump({"clusters": [home, STANZA]}))
    values = load_settings(path)
    runtime_path = tmp_path / "runtime-values.yaml"
    runtime_path.write_text(yaml.safe_dump({"clusters": [home]}))
    runtime = load_settings(runtime_path)
    _, clusters, findings, _ = cycle(Host(), runtime)
    assert not findings and calls[0] is None and calls[1] is None and calls[2] is runtime.host_cluster()
    remote, = clusters
    assert dataclasses.replace(remote, source="values", onboarding=()) == values.clusters[1]


@pytest.mark.parametrize("changes", [
    {"unknown": "sentinel-private-value"}, {"tokenEnv": "X"}, {"tokenFile": ""},
    {"bearerToken": "sentinel-private-value"}, {"password": "sentinel-private-value"},
    {"dashboardController": True}, {"name": "host"}, {"apiUrl": "https://kubernetes.default.svc"},
    {"apiUrl": "https://u:sentinel-private-value@host"}, {"saTokenLookup": "true"},
    {"userSelfLogin": True}, {"saTokenLookup": False}, {"visibility": "typo"},
    {"visibility": "remote-sar", "identity": "none"}, {"enabled": "yes"},
    {"caBundleFile": "/not-a-file", "insecureSkipVerify": True},
    {"labels": {"environment": "prod"}}, {"name": " rnd "},
])
def test_refused_stanzas_never_reach_lookup_or_echo_input(changes, wire, caplog):
    host = Host([cm([{**STANZA, **changes}])])
    _, clusters, findings, _ = cycle(host)
    assert not clusters and findings and not host.mutations and not wire.requests
    assert "sentinel-private-value" not in repr(findings) + caplog.text


@pytest.mark.parametrize("extra", [{"tokenFile": "X"}, {"surprise": True}, {"userSelfLogin": True}, {"enabled": "yes"}])
def test_common_invalid_rules_refuse_both_feeds(extra):
    s = settings()
    home = {"name": "host", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X"}
    with pytest.raises(ConfigError):
        parse_cluster_entries([home, {**STANZA, **extra}], "values")
    with pytest.raises(ConfigError):
        parse_cluster_entries([{**STANZA, **extra}], "configmap", remote_host=s.host_cluster())


def test_label_mismatch_is_unclaimed_and_multiple_maps_are_one_list():
    host = Host([cm(name="a"), cm([{**STANZA, "name": "west"}], name="b", label="sideload"),
                 cm(name="ignored", label="cluster")])
    _, clusters, findings, _ = cycle(host)
    assert {c.name for c in clusters} == {"rnd", "west"} and not findings
    assert len(host.lists) == 2


@pytest.mark.parametrize("duplicate", ["values", "map", "same-map", "secret"])
def test_every_conflicting_declaration_is_a_finding_and_none_loads(duplicate):
    host = Host()
    s = settings()
    if duplicate == "values":
        s.clusters.append(ClusterConfig("rnd", API, token_env="X"))
    elif duplicate == "same-map":
        host.maps = [cm([STANZA, STANZA])]
    elif duplicate == "map":
        host.maps.append(cm(name="second", uid="cm-2"))
    else:
        host.secrets["human"] = _as_stored(secret_object(CreateRequest("rnd", API, "bearerToken", token=SA_TOKEN), "ns"))
        host.secrets["human"]["metadata"]["name"] = "human"
    _, clusters, findings, blocked = cycle(host, s)
    assert not clusters and blocked == {"rnd"} and s.cluster("rnd") is None
    assert len([f for f in findings if f.code == "duplicate-cluster-name"]) == 2
    assert not host.mutations


@pytest.mark.parametrize("labelled", [False, True])
def test_existing_physical_secret_name_is_never_adopted_or_bound(labelled, wire):
    host = Host()
    obj = secret_object(CreateRequest("other", API, "bearerToken", token=SA_TOKEN), "ns")
    obj["metadata"]["name"] = "gsd-cluster-rnd"
    if not labelled:
        obj["metadata"]["labels"] = {}
    host.secrets["gsd-cluster-rnd"] = _as_stored(obj)
    before = copy.deepcopy(host.secrets)
    _, clusters, findings, _ = cycle(host)
    assert "rnd" not in {c.name for c in clusters}
    assert any(f.code == "onboarding-ownership-conflict" for f in findings)
    assert host.secrets == before and not host.mutations and not wire.requests


@pytest.mark.parametrize("removal", ["entry", "map", "label", "uid"])
def test_removed_outputs_are_pruned_from_inventory_even_after_restart(removal, wire):
    host = Host(); generated(host)
    if removal == "entry": host.maps = [cm([])]
    if removal == "map": host.maps = []
    if removal == "label": host.maps = [cm(label="elsewhere")]
    if removal == "uid": host.maps = [cm(uid="replacement-cm")]
    # A new Settings has an empty registry: deletion cannot depend on the previous process's set.
    _, clusters, _, _ = cycle(host, settings())
    assert "gsd-cluster-rnd" not in host.secrets and not clusters
    method, _, body = host.mutations[-1]
    assert method == "DELETE" and body["preconditions"] == {"uid": "secret-1", "resourceVersion": "1"}


def test_failed_delete_is_retried_each_cycle_without_displaced_set_memory(wire):
    host = Host(); generated(host); host.maps = []
    host.fail_delete = True
    for _ in range(2):
        _, clusters, findings, _ = cycle(host, settings())
        assert not clusters and any(f.code == "onboarding-cleanup-pending" for f in findings)
        assert "gsd-cluster-rnd" in host.secrets
    host.fail_delete = False
    cycle(host, settings())
    assert "gsd-cluster-rnd" not in host.secrets
    assert [m[0] for m in host.mutations].count("DELETE") == 3


def test_delete_preconditions_protect_a_replacement_object(wire):
    host = Host(); generated(host); host.maps = []; host.race = True
    _, clusters, findings, _ = cycle(host)
    assert not clusters and findings
    assert host.secrets["gsd-cluster-rnd"]["metadata"]["uid"] == "replacement"


@pytest.mark.parametrize("corrupt", ["owner", "name", "uid"])
def test_changed_ownership_is_never_deleted(wire, corrupt):
    host = Host(); generated(host); host.maps = []
    obj = host.secrets["gsd-cluster-rnd"]
    if corrupt == "owner": obj["metadata"]["annotations"][MANAGED_BY_ANNOTATION] = "ui"
    if corrupt == "name": obj["data"]["name"] = base64.b64encode(b"other").decode()
    if corrupt == "uid": obj["metadata"]["annotations"].pop(CONFIGMAP_UID_ANNOTATION)
    cycle(host)
    assert "gsd-cluster-rnd" in host.secrets and len(host.mutations) == 1


@pytest.mark.parametrize("malformed", ["clusters: [", "clusters: null", "clusters: []\nclusters: []", "other: []"])
def test_bad_documents_hold_outputs_without_polling_or_deleting(wire, malformed):
    host = Host(); generated(host)
    host.maps[0]["data"]["clusters.yaml"] = malformed
    _, clusters, findings, _ = cycle(host)
    assert not clusters and "gsd-cluster-rnd" in host.secrets
    assert len(host.mutations) == 1 and any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("failed", ["/configmaps", "/secrets"])
def test_failed_list_is_not_absence_and_cannot_authorize_lookup(tmp_path, monkeypatch, wire, failed):
    host = Host(); s = generated(host); host.maps = []; host.fail_list = failed
    poller = Poller(Store(str(tmp_path / "p.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    before = s.cluster_registry.discovered()
    poller._discover_once(); poller._retrieve_pending()
    assert s.cluster_registry.discovered() == before and s.cluster_registry.error
    assert len(host.mutations) == 1 and len(wire.authorize) == 1


@pytest.mark.parametrize("mutate,writes", [(False, True), (True, False)])
def test_read_only_or_nonleader_reports_cleanup_and_never_deletes(wire, mutate, writes):
    host = Host(); generated(host); host.maps = []
    _, clusters, findings, _ = cycle(host, settings(writes=writes), mutate=mutate)
    assert not clusters and len(host.mutations) == 1
    assert any(f.code == "onboarding-cleanup-pending" for f in findings)


def test_policy_and_enabled_changes_keep_the_token_and_do_not_bind(wire):
    host = Host(); s = generated(host)
    host.maps = [cm([{**STANZA, "enabled": False, "visibility": "self-only", "identity": "none"}])]
    _, clusters, findings, _ = cycle(host, s)
    cluster, = clusters
    assert not findings and not cluster.enabled and cluster.resolve_token() == SA_TOKEN
    assert s.cluster_policy("rnd") == ("self-only", "none")
    stored = host.secrets["gsd-cluster-rnd"]
    assert base64.b64decode(stored["data"]["enabled"]) == b"false"
    assert [m[0] for m in host.mutations] == ["POST", "PUT"] and len(wire.authorize) == 1


@pytest.mark.parametrize("answer", ["success", "401", "403", "500", "timeout", "bad-read", "write-failure"])
def test_one_bind_budget_survives_rename_and_policy_changes(wire, answer):
    host = Host(); s, clusters, _, _ = cycle(host); cluster, = clusters
    gate = CredentialGate()
    if answer == "401": wire.answers = [refused_401()]
    if answer == "403": wire.answers = [httpx.Response(403)]
    if answer == "500": wire.answers = [httpx.Response(500)]
    if answer == "timeout": wire.answers = [lambda r: httpx.ReadTimeout("lost after send")]
    if answer == "bad-read": wire.secret = httpx.Response(403, text=SA_TOKEN)
    if answer == "write-failure": host.refuse = True
    try:
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    except LookupRefused as error:
        assert answer != "success"
        if answer == "403":
            assert gate.refused(API, USER, PASSWORD) and "phase=credential" in error.detail
    for _ in range(5):
        _, current, _, _ = cycle(host, s)
        if answer == "success":
            assert current[0].credential_kind == "bearer"
        else:
            with pytest.raises(LookupRefused) as exc:
                lookup(current[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
            assert exc.value.gated
        assert len(wire.authorize) == 1
    wire.answers = [login_302()]
    moved = dataclasses.replace(cluster, name="renamed", source="configmap:new-name:9", visibility="self-only",
                                api_url=API.replace("api.example", "API.Example"), onboarding=("new-name", "new-uid", "a" * 64))
    with pytest.raises(LookupRefused) as exc:
        lookup(moved, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert exc.value.gated and len(wire.authorize) == 1
    assert SA_TOKEN not in str(exc.value)


def test_conflicting_values_thread_stops_and_its_history_retires(tmp_path, monkeypatch):
    host = Host()
    s = settings(ClusterConfig("rnd", API, token_env="X"))
    store = Store(str(tmp_path / "p.db")); store.upsert_cluster("rnd", API, True)
    poller = Poller(store, s); poller._cluster_stops["rnd"] = threading.Event()
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda _: None)
    poller._discover_once(); poller._reconcile_threads()
    assert poller._cluster_stops["rnd"].is_set()
    assert next(r for r in store.clusters() if r["id"] == "rnd")["enabled"] == 0
    host.maps = []
    poller._discover_once()
    assert s.cluster("rnd") is not None


def test_generated_secret_cannot_be_rotated_through_stale_ui_state(wire):
    host = Host(); generated(host)
    with pytest.raises(WriteRefused, match="source ConfigMap"):
        rotate(host, "ns", "gsd-cluster-rnd", "replacement-token", viewer="root", cluster="rnd")
    assert len(host.mutations) == 1


@pytest.mark.parametrize("writes,enabled", [(False, True), (True, False)])
def test_off_switches_do_not_spend_a_configmap_bind(wire, writes, enabled):
    host = Host(); s, clusters, _, _ = cycle(host, settings(writes=writes))
    s = dataclasses.replace(s, cluster_secrets_enabled=enabled)
    with pytest.raises(LookupRefused) as exc:
        lookup(clusters[0], s, host, own_namespace="ns", gate=CredentialGate(), sleep=lambda _: None)
    assert exc.value.code == "fleet-write-disabled" and not wire.requests and not host.mutations


def test_disabled_pending_declaration_is_not_retrieved(tmp_path, monkeypatch, wire):
    host = Host([cm([{**STANZA, "enabled": False}])]); s, _, _, _ = cycle(host)
    poller = Poller(Store(str(tmp_path / "p.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    poller._retrieve_pending()
    assert not wire.requests and not host.mutations


def test_password_rotation_rearms_the_existing_gate(wire):
    host = Host(); s, clusters, _, _ = cycle(host); gate = CredentialGate()
    wire.answers = [refused_401()]
    with pytest.raises(LookupRefused):
        lookup(clusters[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    host.secrets["gsd-fleet-account"]["data"]["password"] = base64.b64encode(b"rotated-password").decode()
    wire.answers = [login_302()]
    lookup(clusters[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == 2 and "gsd-cluster-rnd" in host.secrets


def test_connection_change_prunes_before_any_recreation(wire):
    host = Host(); s = generated(host)
    host.maps = [cm([{**STANZA, "insecureSkipVerify": True}])]
    _, clusters, _, _ = cycle(host, s)
    assert not clusters and "gsd-cluster-rnd" not in host.secrets
    _, clusters, _, _ = cycle(host, s)
    assert len(clusters) == 1 and clusters[0].credential_pending is not None
    assert len(wire.authorize) == 1


def test_displaced_owned_output_is_held_when_new_authors_conflict(wire):
    host = Host(); generated(host)
    host.maps = [cm(name="new-a", uid="a"), cm(name="new-b", uid="b")]
    _, clusters, findings, blocked = cycle(host)
    assert not clusters and blocked == {"rnd"} and "gsd-cluster-rnd" in host.secrets
    assert any(f.code == "onboarding-cleanup-pending" for f in findings)
    assert len(host.mutations) == 1


def test_numeric_values_names_reserve_the_same_identity_as_quoted_names():
    host = Host([cm([{**STANZA, "name": 1}]), cm([{**STANZA, "name": "1"}], name="second", uid="cm-2")])
    _, clusters, findings, blocked = cycle(host)
    assert not clusters and blocked == {"1"}
    assert len([f for f in findings if f.code == "duplicate-cluster-name"]) == 2
    assert not host.mutations


@pytest.mark.parametrize("api", [
    f"{scheme}://{name}{port}"
    for name in ("kubernetes.default.svc", "kubernetes.default.svc.cluster.local", "kubernetes.default")
    for scheme in ("http", "https") for port in ("", ":443", ":6443")
] + ["https://KUBERNETES.DEFAULT.SVC.:8443"])
def test_in_cluster_url_aliases_are_host_and_do_not_bind(api, wire):
    with pytest.raises(ConfigError, match="host is declared only in values"):
        parse_cluster_entries([{**STANZA, "apiUrl": api}], "configmap", remote_host=settings().host_cluster())
    host = Host([cm([{**STANZA, "apiUrl": api}])])
    _, clusters, findings, _ = cycle(host)
    assert not clusters and not host.mutations and not wire.requests
    assert any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("host_url,api", [
    ("https://api.host.example", "https://API.HOST.EXAMPLE:443/"),
    ("https://api.host.example:6443", "https://api.host.example:6443/"),
    ("http://api.host.example", "http://api.host.example:80"),
])
def test_values_host_endpoint_is_refused(host_url, api, wire):
    s = settings()
    s.clusters[0] = dataclasses.replace(s.clusters[0], api_url=host_url)
    with pytest.raises(ConfigError, match="host is declared only in values"):
        parse_cluster_entries([{**STANZA, "apiUrl": api}], "configmap", remote_host=s.host_cluster())
    _, clusters, findings, _ = cycle(Host([cm([{**STANZA, "apiUrl": api}])]), s)
    assert not clusters and not wire.requests
    assert any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("host_url", ["https://kubernetes.default.svc", "https://api.example.com:443",
                                     "http://api.example.com:6443"])
def test_external_url_of_same_cluster_is_allowed(host_url, wire):
    # shared-rnd intentionally uses its external API even when it is the controller's physical cluster.
    s = settings()
    s.clusters[0] = dataclasses.replace(s.clusters[0], api_url=host_url)
    host = Host([cm([{**STANZA, "name": "shared-rnd"}])])
    generated(host, s)
    assert "gsd-cluster-shared-rnd" in host.secrets and len(wire.authorize) == 1


def test_insecure_configmap_is_accepted_and_secret_preserves_tls_choice(wire):
    host = Host([cm([{**STANZA, "insecureSkipVerify": True}])])
    generated(host)
    config = json.loads(base64.b64decode(host.secrets["gsd-cluster-rnd"]["data"]["config"]))
    assert config["tlsClientConfig"]["insecure"] is True
    assert len(wire.authorize) == 1


def test_invalid_configmap_stanza_does_not_stop_values(tmp_path, monkeypatch):
    host = Host([cm([{**STANZA, "unknown": True}])])
    s = settings(ClusterConfig("rnd", API, token_env="X"))
    poller = Poller(Store(str(tmp_path / "invalid.db")), s)
    poller._cluster_stops["rnd"] = threading.Event()
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda _: None)
    _, _, findings, blocked = cycle(host, s)
    poller._discover_once(); poller._reconcile_threads()
    assert blocked == set() and not poller._cluster_stops["rnd"].is_set()
    assert s.cluster("rnd").source == "values"
    assert any(f.code == "onboarding-invalid" for f in findings)
    assert not any(f.code == "duplicate-cluster-name" for f in findings)


@pytest.mark.parametrize("feed", ["configmap", "values"])
@pytest.mark.parametrize("failure", ["connect", "tls"])
def test_pre_write_failure_can_retry(feed, failure, wire):
    host = Host(); s, clusters, _, _ = cycle(host)
    cluster = clusters[0] if feed == "configmap" else dataclasses.replace(clusters[0], onboarding=(), source="values")
    gate = CredentialGate()
    def before_write(request):
        import ssl
        if failure == "tls":
            raise httpx.ConnectError("certificate verify failed") from ssl.SSLCertVerificationError("untrusted")
        raise httpx.ConnectError("connection refused")
    wire.answers = [before_write] * 10
    with pytest.raises(LookupRefused):
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert not gate.refused(API, USER, PASSWORD)
    attempted = len(wire.authorize)
    wire.answers = [login_302()]
    lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == attempted + 1 and "gsd-cluster-rnd" in host.secrets


@pytest.mark.parametrize("feed", ["configmap", "values"])
def test_restart_has_a_new_bind_budget(feed, wire):
    host = Host(); s, clusters, _, _ = cycle(host)
    cluster = clusters[0] if feed == "configmap" else dataclasses.replace(clusters[0], onboarding=(), source="values")
    wire.answers = [login_302(), login_302()]
    for _ in range(2):
        # A process/replica gets a fresh gate; no durable claim exists in S5.
        wire.secret = httpx.Response(403)
        with pytest.raises(LookupRefused):
            lookup(cluster, s, host, own_namespace="ns", gate=CredentialGate(), sleep=lambda _: None)
    assert len(wire.authorize) == 2


@pytest.mark.parametrize("answer", ["success", "401", "403", "500", "timeout", "bad-read", "write-failure"])
def test_values_bind_budget_is_unchanged(tmp_path, monkeypatch, wire, answer):
    from gsd.fleetlookup import LOOKUP_ATTEMPTS
    host = Host([])
    s = settings(parse_cluster_entries([STANZA], "values", remote_host=settings().host_cluster())[0])
    poller = Poller(Store(str(tmp_path / "values.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    if answer == "401": wire.answers = [refused_401()]
    if answer == "403": wire.answers = [httpx.Response(403)]
    if answer == "500": wire.answers = [httpx.Response(500)]
    if answer == "timeout": wire.answers = [lambda r: httpx.ReadTimeout("lost after send")]
    if answer == "bad-read": wire.secret = httpx.Response(403)
    if answer == "write-failure": host.refuse = True
    if answer in ("bad-read", "write-failure"):
        wire.answers = [login_302() for _ in range(LOOKUP_ATTEMPTS)]
    for _ in range(6):  # first cycle, then the next five, with the retry delay elapsed
        for state in poller._lookups.values():
            state.not_before = 0
        poller._discover_once(); poller._retrieve_pending()
    expected = min(6, LOOKUP_ATTEMPTS) if answer in ("bad-read", "write-failure") else 1
    assert len(wire.authorize) == expected
