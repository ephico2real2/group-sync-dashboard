"""Clusters as labelled Secrets (#230 S1, docs/specs/SPEC_S1_cluster_secrets.md): the parser (one test per
contract row), the registry's precedence, the reader over a paged fake client, the poller's discovery
stage, the API and — the pin that matters most — that the credential never leaves the Secret and the
process's memory: not the database, not a log record, not a response, not /metrics."""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import FINDING_CODES, LABEL_SELECTOR, SECRET_TYPE_LABEL, ClusterRegistry, Finding, discover, parse_secret
from gsd.config import ClusterConfig, ConfigError, Settings
from gsd.kube import FORBIDDEN, ClusterError
from gsd.poller import Poller
from gsd.store import Store
from test_chart_pdb import _render
from test_chart_strategy import render as _render_text
from test_kyverno import _FakeClient
from test_visibility import H, _MapResolver, _seed, _settings

TOKEN = "sekrit-bearer-token-9f8e7d"        # the sentinel no response, row or log line may carry


def _secret(name="gsd-cluster-east", *, cluster="east", server="https://api.east.example:6443", config=None,
            labels=None, **data):
    cfg = {"bearerToken": TOKEN} if config is None else config
    d = {"name": cluster, "server": server, "config": json.dumps(cfg) if not isinstance(cfg, str) else cfg, **data}
    return {"metadata": {"name": name, "labels": {SECRET_TYPE_LABEL: "cluster", **(labels or {})}},
            "data": {k: base64.b64encode(v.encode()).decode() for k, v in d.items() if v is not None}}


# ── the parser: one test per contract row (C1/C2) ────────────────────────────────────────────────────────

class TestParser:
    def test_a_well_formed_secret_is_a_cluster_with_its_source_labels_and_bearer_kind(self):
        c = parse_secret(_secret(labels={"environment": "prod"}, visibility="self-only", identity="none"), host_name="host")
        assert isinstance(c, ClusterConfig)
        assert (c.name, c.api_url, c.source, c.credential_kind) == ("east", "https://api.east.example:6443", "secret:gsd-cluster-east", "bearer")
        assert c.labels == (("environment", "prod"),) and c.visibility == "self-only" and c.identity == "none" and c.enabled
        assert c.resolve_token() == TOKEN
        assert TOKEN not in repr(c) and TOKEN not in str(c), "the credential is never in a repr"

    def test_the_api_serves_data_base64_and_a_fixture_may_hand_stringdata(self):
        s = {"metadata": {"name": "x"}, "stringData": {"name": "east", "server": "https://a", "config": json.dumps({"bearerToken": "t"})}}
        assert isinstance(parse_secret(s, host_name=None), ClusterConfig)

    @pytest.mark.parametrize("data,code", [
        ({"cluster": ""}, "name-missing"),
        ({"cluster": "Bad_Name"}, "name-invalid"),
        ({"server": ""}, "server-missing"),
        ({"server": "http://plain"}, "server-invalid"),
        ({"server": "https://a/with/path"}, "server-invalid"),
        ({"config": ""}, "config-missing"),
        ({"config": "{not json"}, "config-not-json"),
        ({"config": "[1,2]"}, "config-not-json"),
        ({"config": {"bearerToken": "t", "username": "u", "password": "p"}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "execProviderConfig": {}}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "awsAuthConfig": {}}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "proxyUrl": "http://p"}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "somethingElse": 1}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "tlsClientConfig": {"certData": "x"}}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "tlsClientConfig": {"serverName": "x"}}}, "unsupported-config-key"),
        ({"config": {"bearerToken": "t", "tlsClientConfig": {"insecure": "yes"}}}, "unsupported-config-key"),
        ({"config": {}}, "credential-missing"),
        ({"config": {"bearerToken": "  "}}, "credential-missing"),
        ({"config": {"oauth": {"username": "u"}}}, "credential-missing"),
        ({"config": {"bearerToken": "t", "oauth": {"username": "u", "password": "p"}}}, "credential-ambiguous"),
        ({"config": {"bearerToken": "t", "tlsClientConfig": {"caData": "bm90IGEgcGVt"}}}, "ca-data-invalid"),
        ({"config": {"bearerToken": "t", "tlsClientConfig": {"caData": "bm90IGEgcGVt", "insecure": True}}}, "insecure-with-ca"),
        ({"visibility": "everyone"}, "visibility-invalid"),
        ({"visibility": "remote-sar"}, "visibility-invalid"),
        ({"identity": "same"}, "identity-invalid"),
        ({"enabled": "yes"}, "enabled-invalid"),
    ])
    def test_each_refusal_names_its_code_and_never_a_value(self, data, code):
        f = parse_secret(_secret(**data), host_name="host")
        assert isinstance(f, Finding) and f.code == code, f
        assert TOKEN not in f.detail and "sekrit" not in f.detail
        assert code in FINDING_CODES

    def test_the_unsupported_key_finding_names_the_key(self):
        f = parse_secret(_secret(config={"bearerToken": "t", "proxyUrl": "x"}), host_name=None)
        assert f.detail.startswith("proxyUrl:")
        f = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"keyData": "x"}}), host_name=None)
        assert f.detail.startswith("tlsClientConfig.keyData:")

    def test_the_host_is_never_sourced_from_a_secret_by_name_or_by_the_internal_server(self):
        assert parse_secret(_secret(cluster="host"), host_name="host").code == "host-cluster-not-from-secret"
        assert parse_secret(_secret(server="https://kubernetes.default.svc"), host_name="host").code == "host-cluster-not-from-secret"
        assert isinstance(parse_secret(_secret(cluster="host"), host_name=None), ClusterConfig), "no host configured: nothing to protect"

    def test_oauth_parses_as_a_kind_and_refuses_to_resolve_naming_p2(self):
        c = parse_secret(_secret(config={"oauth": {"username": "svc", "password": "pw"}}), host_name=None)
        assert isinstance(c, ClusterConfig) and c.credential_kind == "oauth"
        with pytest.raises(ConfigError, match="#119 P2"):
            c.resolve_token()
        assert "pw" not in repr(c)

    def test_ca_data_loads_into_the_ssl_context_and_insecure_verifies_nothing(self, tmp_path):
        import shutil, ssl, subprocess
        if not shutil.which("openssl"):
            pytest.skip("openssl not on PATH")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                        "-keyout", str(tmp_path / "k.pem"), "-out", str(tmp_path / "ca.pem"), "-days", "2", "-subj", "/CN=test-ca"],
                       check=True, capture_output=True)
        pem = (tmp_path / "ca.pem").read_text()
        c = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"caData": base64.b64encode(pem.encode()).decode()}}), host_name=None)
        assert isinstance(c, ClusterConfig), c
        assert isinstance(c.verify(), ssl.SSLContext) and c.ca_data == pem
        c = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"insecure": True}}), host_name=None)
        assert c.verify() is False

    def test_the_three_trust_modes_and_the_refusal_that_names_both_fields(self, tmp_path, monkeypatch):
        """The operator's ruling (2026-09-20): no caData → the dashboard's own trust store; caData → that bundle
        alone; insecure → off; caData beside insecure refused naming both. The wire says the mode, never the PEM."""
        import shutil, ssl, subprocess
        monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
        default = parse_secret(_secret(), host_name=None)
        assert default.tls_mode == {"insecure": False, "ca": "trusted-bundle"} and default.verify() is True, \
            "mode 1 with no bundle mounted is the system store (httpx verify=True)"
        if shutil.which("openssl"):
            subprocess.run(["openssl", "req", "-x509", "-newkey", "ec", "-pkeyopt", "ec_paramgen_curve:prime256v1", "-nodes",
                            "-keyout", str(tmp_path / "k.pem"), "-out", str(tmp_path / "trusted.pem"), "-days", "2", "-subj", "/CN=trusted"],
                           check=True, capture_output=True)
            monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(tmp_path / "trusted.pem"))
            from gsd import config as cfg
            cfg._ca_cache.clear()
            assert isinstance(default.verify(), ssl.SSLContext), "mode 1 with the chart's bundle mounted is that context"
            pem = (tmp_path / "trusted.pem").read_text()
            override = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"caData": base64.b64encode(pem.encode()).decode()}}), host_name=None)
            assert override.tls_mode == {"insecure": False, "ca": "caData"} and pem not in json.dumps(override.tls_mode)
        off = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"insecure": True}}), host_name=None)
        assert off.tls_mode == {"insecure": True, "ca": None} and off.verify() is False
        both = parse_secret(_secret(config={"bearerToken": "t", "tlsClientConfig": {"caData": "bm90IGEgcGVt", "insecure": True}}), host_name=None)
        assert both.code == "insecure-with-ca" and "caData" in both.detail and "insecure" in both.detail
        # a values entry says its mode the same way
        assert ClusterConfig("h", "https://x", token_file="/var/run/secrets/kubernetes.io/serviceaccount/token",
                             ca_bundle_file="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt").tls_mode == {"insecure": False, "ca": "serviceAccount"}
        assert ClusterConfig("r", "https://x", token_env="X", ca_bundle_file="/etc/gsd/r/ca.crt").tls_mode == {"insecure": False, "ca": "caBundleFile"}

    def test_a_finding_refuses_a_code_outside_the_closed_set(self):
        with pytest.raises(ValueError):
            Finding("x", "made-up", "y")


# ── the registry and the reader (C2/C3) ──────────────────────────────────────────────────────────────────

def _values(*names):
    return [ClusterConfig(n, f"https://api.{n}.example:6443", token_env="X") for n in names]


class TestRegistryAndReader:
    def test_a_secret_shadows_a_values_entry_of_the_same_name_and_the_host_is_never_replaced(self):
        r = ClusterRegistry()
        east = parse_secret(_secret(cluster="east", server="https://moved.example:6443"), host_name="host")
        r.replace([east], [], at="2026-09-20T00:00:00Z")
        merged = r.merge(_values("host", "east", "west"))
        assert [c.name for c in merged] == ["host", "east", "west"]
        assert merged[1].api_url == "https://moved.example:6443" and merged[1].source == "secret:gsd-cluster-east"
        assert merged[0].source == "values"

    def test_a_failed_list_keeps_the_previous_set_and_is_the_cycles_one_finding(self):
        r = ClusterRegistry()
        r.replace([parse_secret(_secret(), host_name=None)], [], at="t1")
        r.fail("t2", "forbidden: 403 on secrets")
        assert [c.name for c in r.discovered()] == ["east"] and r.last_discovery == "t2"
        assert [f.code for f in r.findings()] == ["discovery-failed"] and r.findings()[0].secret == "-"

    def test_the_reader_lists_by_label_pages_and_applies_the_duplicate_and_shadow_rules(self):
        path = "/api/v1/namespaces/ns/secrets"
        page1 = {"items": [_secret("b-dup", cluster="east", server="https://second.example:6443"), _secret("c-bad", config="{")],
                 "metadata": {"continue": "more"}}
        page2 = {"items": [_secret("a-first", cluster="east"), _secret("d-shadow", cluster="west"),
                           _secret("e-oauth", cluster="north", config={"oauth": {"username": "u", "password": "p"}})]}

        class _Paged(_FakeClient):
            def _get(self, client, p, params):
                self.calls.append((p, dict(params)))
                if p != path: raise ClusterError("unreachable", f"HTTP 404 on {p}: not found")
                return page2 if params.get("continue") == "more" else page1
        client = _Paged({})
        clusters, findings = discover(client, "ns", host_name="host", values_names=("host", "west"))
        assert all(p == path and params["labelSelector"] == LABEL_SELECTOR for p, params in client.calls) and len(client.calls) == 2
        # `east` is declared twice, so NEITHER Secret loads it — a duplicate name is fail-closed, not
        # first-wins, because first-by-metadata.name would let `aaa-anything` replace a cluster's
        # server and token (design review of #230, OB2). Each Secret gets a finding naming the other.
        assert [(c.name, c.source) for c in clusters] == [("west", "secret:d-shadow"), ("north", "secret:e-oauth")]
        assert sorted((f.secret, f.code) for f in findings) == [("a-first", "duplicate-cluster-name"),
                                                                ("b-dup", "duplicate-cluster-name"), ("c-bad", "config-not-json"),
                                                                ("d-shadow", "shadows-values-entry"), ("e-oauth", "oauth-exchange-not-built")]
        dup = {f.secret: f.detail for f in findings if f.code == "duplicate-cluster-name"}
        assert "b-dup" in dup["a-first"] and "a-first" in dup["b-dup"], "each names the other"
        assert "neither is loaded" in dup["a-first"]

    def test_argos_scope_and_routing_keys_are_refused_with_the_key_named(self):
        """A Secret copied from Argo CD carrying `namespaces: team-a` declares a NARROWED cluster;
        this contract reads the whole cluster, so honouring the copy silently would read far more
        than its author declared. Refused, with the key named (design review of #230, OB2)."""
        for key, value in (("namespaces", "team-a,team-b"), ("clusterResources", "false"),
                           ("project", "platform"), ("shard", "1")):
            obj = _secret("argo-copy")
            obj["data"][key] = base64.b64encode(value.encode()).decode()
            parsed = parse_secret(obj, host_name="host")
            assert isinstance(parsed, Finding), f"{key} was accepted"
            assert parsed.code == "unsupported-config-key" and key in parsed.detail

    def test_a_403_on_the_list_raises_for_the_caller_to_record(self):
        client = _FakeClient({"/api/v1/namespaces/ns/secrets": FORBIDDEN})
        with pytest.raises(ClusterError) as exc:
            discover(client, "ns", host_name=None)
        assert exc.value.outcome == FORBIDDEN


# ── the store (migration 19) ─────────────────────────────────────────────────────────────────────────────

class TestStore:
    def test_the_cluster_row_carries_its_source_and_credential_kind_never_a_value(self, tmp_path):
        s = Store(str(tmp_path / "s.db"))
        s.upsert_cluster("east", "https://a", True, source="secret:gsd-cluster-east", credential="bearer")
        s.upsert_cluster("host", "https://b", True)
        rows = {r["id"]: r for r in s.clusters()}
        assert (rows["east"]["source"], rows["east"]["credential"]) == ("secret:gsd-cluster-east", "bearer")
        assert (rows["host"]["source"], rows["host"]["credential"]) == ("values", "")
        dump = "\n".join(s._conn.iterdump())
        assert TOKEN not in dump


# ── the poller: discovery on the cadence, a discovered cluster polls, a vanished one retires ──────────────

class _Host(_FakeClient):
    """The host's client: the Secrets LIST answers from a mutable table the test edits between cycles."""
    secrets: dict = {"items": []}

    def __init__(self, cfg, timeout=15.0):
        super().__init__({}, cfg.name)
        self.cfg = cfg

    def _get(self, client, path, params):
        self.calls.append(path)
        if path == "/api/v1/namespaces/ns/secrets":
            if _Host.secrets is FORBIDDEN:
                raise ClusterError(FORBIDDEN, "403 Forbidden on /api/v1/namespaces/ns/secrets")
            return _Host.secrets
        raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")


class TestPoller:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
        monkeypatch.setattr("gsd.poller.ClusterClient", _Host)
        _Host.secrets = {"items": []}
        polled: list[str] = []
        monkeypatch.setattr("gsd.poller.poll_once", lambda store, cluster, *a, **k: polled.append(cluster.name) or "ok")
        monkeypatch.setattr("gsd.poller.capture_once", lambda *a, **k: None)
        monkeypatch.setattr("gsd.poller.refresh_bindings", lambda *a, **k: None)
        self.polled = polled

    def _poller(self, tmp_path, **kw):
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
                            db_path=str(tmp_path / "p.db"), poll_interval_seconds=1, binding_interval_seconds=1, **kw)
        return Poller(store, settings), store, settings

    def _wait(self, cond, timeout=5.0):
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond(): return True
            time.sleep(0.05)
        return cond()

    def test_a_discovered_cluster_is_polled_like_a_values_one_and_a_vanished_one_retires_with_its_rows(self, tmp_path):
        _Host.secrets = {"items": [_secret(labels={"environment": "prod"})]}
        poller, store, settings = self._poller(tmp_path)
        poller.start()
        try:
            assert self._wait(lambda: "east" in self.polled), "the Secret-sourced cluster never polled"
            row = next(r for r in store.clusters() if r["id"] == "east")
            assert (row["source"], row["credential"], row["enabled"]) == ("secret:gsd-cluster-east", "bearer", 1)
            assert settings.cluster("east").labels == (("environment", "prod"),)
            # the Secret vanishes: the next cycle retires the cluster, its thread stops, the row stays
            _Host.secrets = {"items": []}
            assert self._wait(lambda: next(r for r in store.clusters() if r["id"] == "east")["enabled"] == 0)
            assert self._wait(lambda: poller._cluster_stops["east"].is_set())
            assert "east" not in {c.name for c in settings.effective_clusters()}
            assert next(r for r in store.clusters() if r["id"] == "east")["source"] == "secret:gsd-cluster-east"
        finally:
            poller.stop()

    def test_a_bad_secret_is_a_finding_the_good_one_still_polls_and_a_failed_list_keeps_the_set(self, tmp_path):
        _Host.secrets = {"items": [_secret(), _secret("gsd-cluster-broken", cluster="broken", config="{")]}
        poller, store, settings = self._poller(tmp_path)
        poller.start()
        try:
            assert self._wait(lambda: "east" in self.polled)
            assert [f.code for f in settings.cluster_registry.findings()] == ["config-not-json"]
            _Host.secrets = FORBIDDEN
            assert self._wait(lambda: settings.cluster_registry.error is not None)
            assert [c.name for c in settings.cluster_registry.discovered()] == ["east"], "the previous set stands"
            assert settings.cluster("east") is not None
        finally:
            poller.stop()

    def test_the_switch_off_means_no_list_and_no_discovery_thread(self, tmp_path):
        _Host.secrets = {"items": [_secret()]}
        poller, store, settings = self._poller(tmp_path, cluster_secrets_enabled=False)
        poller.start()
        try:
            assert self._wait(lambda: "host" in self.polled)
            assert settings.cluster_registry.last_discovery is None and settings.cluster("east") is None
            assert not any(t.name == "cluster-secrets" for t in poller._threads)
        finally:
            poller.stop()

    def test_an_oauth_cluster_is_listed_but_never_polled(self, tmp_path):
        _Host.secrets = {"items": [_secret(config={"oauth": {"username": "u", "password": "p"}})]}
        poller, store, settings = self._poller(tmp_path)
        poller.start()
        try:
            assert self._wait(lambda: "host" in self.polled)
            assert settings.cluster("east").credential_kind == "oauth"
            import time; time.sleep(0.3)
            assert "east" not in self.polled and "east" not in poller._cluster_stops
            assert [f.code for f in settings.cluster_registry.findings()] == ["oauth-exchange-not-built"]
        finally:
            poller.stop()

    def test_a_rotated_token_lands_on_the_next_cycle_without_a_restart(self, tmp_path):
        _Host.secrets = {"items": [_secret()]}
        poller, store, settings = self._poller(tmp_path)
        poller.start()
        try:
            assert self._wait(lambda: "east" in self.polled)
            assert settings.cluster("east").resolve_token() == TOKEN
            _Host.secrets = {"items": [_secret(config={"bearerToken": "rotated-1"})]}
            assert self._wait(lambda: settings.cluster("east").resolve_token() == "rotated-1")
        finally:
            poller.stop()


# ── the API and the credential-never-leaves pin ───────────────────────────────────────────────────────────

class TestApi:
    @pytest.fixture
    def client(self, tmp_path):
        db = str(tmp_path / "gsd.db"); _seed(db)
        settings = _settings(db)
        east = parse_secret(_secret(labels={"environment": "prod"}), host_name="c1")
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace([east], [Finding("gsd-cluster-broken", "config-not-json", "Expecting value")], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        # The read route is gated on clusterconfig:view, NOT the wide tier (#230, the operator's
        # ruling of 2026-09-20): the wide tier admits the auditor persona by design.
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            yield c, app.state.store

    def test_the_payload_shape_the_tier_and_the_findings(self, client, caplog):
        c, store = client
        assert c.get("/api/clusterconfigs", headers=H("alice")).status_code == 403
        body = c.get("/api/clusterconfigs", headers=H("root")).json()
        assert body["secrets"] == {"enabled": True, "namespace": "ns", "label": LABEL_SELECTOR,
                                   "last_discovery": "2026-09-20T16:05:12Z", "error": None}
        by = {x["id"]: x for x in body["clusters"]}
        assert by["c1"]["host"] is True and by["c1"]["source"] == "values" and by["c1"]["credential"] == "file"
        assert by["east"] == {"id": "east", "source": "secret:gsd-cluster-east", "host": False,
                              "api_url": "https://api.east.example:6443", "enabled": True, "credential": "bearer",
                              "labels": {"environment": "prod"}, "visibility": "self-only", "identity": "none",
                              "tls": {"insecure": False, "ca": "trusted-bundle"},
                              "status": None, "last_poll": None, "error": None, "retired": False}
        assert by["c1"]["tls"] == {"insecure": False, "ca": "trusted-bundle"}
        assert body["findings"] == [{"secret": "gsd-cluster-broken", "code": "config-not-json", "detail": "Expecting value"}]
        # a cluster the store holds but no source names — its Secret vanished — is listed as retired, never dropped
        store.upsert_cluster("gone", "https://api.gone.example:6443", False, source="secret:gsd-cluster-gone", credential="bearer")
        gone = next(x for x in c.get("/api/clusterconfigs", headers=H("root")).json()["clusters"] if x["id"] == "gone")
        assert gone["retired"] is True and gone["enabled"] is False and gone["source"] == "secret:gsd-cluster-gone"
        # the discovered cluster is served by the routes and counted by readiness
        assert c.get("/readyz").json()["clusters"] == 3
        # served, and narrowed: a Secret-sourced cluster is self-only by default (D2), so the administrator view
        # refuses (403) rather than not knowing the cluster (404)
        r = c.get("/api/clusters/east/kyverno", headers=H("root"))
        assert r.status_code == 403 and "unknown cluster" not in r.text

    def test_the_credential_reaches_no_response_no_row_no_log_record_and_no_metric(self, client, caplog):
        c, store = client
        with caplog.at_level(logging.DEBUG):
            texts = [c.get(p, headers=H("root")).text for p in ("/api/clusterconfigs", "/api/clusters", "/readyz", "/metrics", "/api/whoami")]
        for t in texts:
            assert TOKEN not in t
        assert TOKEN not in "\n".join(r.getMessage() for r in caplog.records)
        assert TOKEN not in "\n".join(store._conn.iterdump())


# ── the chart ────────────────────────────────────────────────────────────────────────────────────────────

class TestChart:
    def test_the_role_grants_read_only_on_secrets_in_the_release_namespace_and_the_switch_removes_it(self):
        docs = _render()
        role = next(d for d in docs if d.get("kind") == "Role" and d["metadata"]["name"].endswith("-cluster-secrets"))
        assert role["metadata"]["namespace"] == "x"
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
        binding = next(d for d in docs if d.get("kind") == "RoleBinding" and d["metadata"]["name"].endswith("-cluster-secrets"))
        assert binding["roleRef"]["kind"] == "Role" and binding["subjects"][0]["kind"] == "ServiceAccount"
        assert not any(d.get("kind") == "ClusterRole" and "secrets" in {r for rule in d.get("rules", []) for r in rule.get("resources", [])}
                       for d in docs), "never cluster-wide"
        ok, out = _render_text()
        from test_chart_reporting import _config_data
        assert ok and _config_data(out)["clusterSecretsEnabled"] is True
        off = _render("clusterConfig.secrets.enabled=false")
        assert not any(d.get("metadata", {}).get("name", "").endswith("-cluster-secrets") for d in off)
        ok, out = _render_text(clusterConfig__secrets__enabled="false")
        assert ok and _config_data(out)["clusterSecretsEnabled"] is False


class TestDiscoveryFailureDoesNotRetire:
    """A failed LIST is "we could not look", never "they were deleted" (review of #235, Grok C6).

    On a FRESH process the registry has no previous set to stand on, so every Secret-sourced
    cluster looks absent; retiring them would take the whole fleet out of the served set because
    one API call timed out — and their rows would say `retired` to every reader until a later
    cycle put them back.
    """

    def test_a_failed_start_discovery_spares_secret_sourced_rows_and_still_retires_dropped_values(self, tmp_path):
        db = str(tmp_path / "gsd.db"); _seed(db)
        settings = _settings(db)
        store = Store(db)
        try:
            # Two rows from an earlier life: one discovered from a Secret, one from the values list
            # that the configuration has since dropped.
            store.upsert_cluster("east", "https://api.east.example:6443", True,
                                 source="secret:gsd-cluster-east", credential="bearer")
            store.upsert_cluster("dropped", "https://api.dropped.example:6443", True,
                                 source="values", credential="file")
            store.retire_absent_clusters(["c1"], keep_sources=("secret:",))
            rows = {r["id"]: r for r in store.clusters()}
            assert rows["east"]["enabled"] == 1, "a failed LIST retired a Secret-sourced cluster"
            assert rows["dropped"]["enabled"] == 0, "a values cluster the config dropped is still retired"
            # and with no failure, the Secret row retires like any other
            store.retire_absent_clusters(["c1"])
            assert {r["id"]: r["enabled"] for r in store.clusters()}["east"] == 0
        finally:
            store.close()


class TestTheCredentialNeverLeavesTheSecret:
    """The invariant the operator set: a cluster's credential lives in its Secret and nowhere else.

    The interesting path is not our own code printing it — it is the REMOTE printing it back at us.
    A cluster controls its error bodies, and anything that echoes the request (a proxy's 502 page, a
    debug handler) returns our bearer token inside `response.text`, which `_get` copies into the
    ClusterError message — persisted by `record_poll` and served on /api/clusters (review of #235,
    Codex C8).
    """

    def test_a_remote_that_echoes_the_authorization_header_does_not_get_it_stored(self):
        import httpx

        from gsd.config import ClusterConfig as CC
        from gsd.kube import UNREACHABLE, ClusterClient, ClusterError

        token = "sha256~a-very-secret-token-value"
        cluster = CC(name="east", api_url="https://api.east.example:6443", token_env="T_EAST")
        os.environ["T_EAST"] = token
        try:
            client = ClusterClient(cluster)
            body = ('{"kind":"Status","message":"upstream refused: '
                    f'Authorization: Bearer {token}"}}')
            transport = httpx.MockTransport(lambda _: httpx.Response(500, text=body))
            with httpx.Client(transport=transport, base_url=cluster.api_url) as http:
                with pytest.raises(ClusterError) as exc:
                    client._get(http, "/api/v1/namespaces", {})
            assert exc.value.outcome == UNREACHABLE
            assert token not in exc.value.message, "the remote's echo carried our token into a stored error"
            assert "<redacted>" in exc.value.message
            assert "upstream refused" in exc.value.message, "the diagnostic itself is still useful"
        finally:
            os.environ.pop("T_EAST", None)


class TestClusterConfigTier:
    """The cluster-configuration tier (#230; the operator's ruling of 2026-09-20, "a new tier boss
    — look at how argocd does it").

    Argo CD's RBAC carries a first-class `clusters` resource with `get` and `create/update/delete`
    actions; ours is the same two levels asked natively as SubjectAccessReviews about the objects
    this surface exposes — `get secrets` for view, `create secrets` for manage, in the dashboard's
    own namespace.

    WHY NOT THE WIDE TIER, measured on CRC 2026-09-20: `oc get clusterrole cluster-reader -o json`
    has ZERO of its 172 rules covering core/`secrets` and `oc auth can-i {get,list,create,update,
    delete} secrets` answers `no` — while that same cluster-reader, the deliberate auditor persona,
    PASSES the wide tier by design (see api.usage_scope). Gating this surface on the wide tier would
    hand the auditor the fleet's wiring, and at S2 the writes that change it.
    """

    @pytest.fixture
    def make_app(self, tmp_path):
        """A FACTORY, not one app: each case gets its own store, because a TestClient's exit
        closes it and these cases need several clients."""
        seq = iter(range(100))

        def _make(view=None, manage=None):
            db = str(tmp_path / f"gsd{next(seq)}.db"); _seed(db)
            settings = _settings(db)
            settings.cluster_registry.namespace = "ns"
            settings.cluster_registry.replace(
                [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
            app = build_app(settings, run_poller=False)
            # Everyone passes the WIDE tier here, auditor included — exactly the live situation
            # this gate exists for, so a passing test cannot be passing for the wrong reason.
            app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all", "viewer": "all"})
            app.state.clusterconfig_view_resolver = view
            app.state.clusterconfig_manage_resolver = manage
            return app

        return _make

    def test_the_auditor_passes_the_wide_tier_and_is_still_refused_with_no_cluster_named(self, make_app):
        app = make_app(view=_MapResolver({"root": "all"}), manage=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            # the same persona the wide tier admits
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            refused = c.get("/api/clusterconfigs", headers=H("auditor"))
            assert refused.status_code == 403
            body = refused.json()["detail"]
            assert "cluster-configuration administrators" in body
            # the refusal names no cluster, no Secret and no namespace: it reaches the refused
            # person, and a sentence that named the Secret would be a map for the next attempt.
            # Whole words: "ns" lives inside "instance", which is not a leak.
            words = set(re.findall(r"[A-Za-z0-9_.-]+", body))
            assert not words & {"c1", "east", "ns", "gsd-cluster-east", "secrets"}
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_view_and_manage_are_asked_separately_and_manage_does_not_imply_view(self, make_app):
        # A site may grant the two apart: passing manage alone must NOT open the read route.
        app = make_app(view=_MapResolver({"root": "all"}),
                       manage=_MapResolver({"root": "all", "manager": "all"}))
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("manager")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_it_fails_closed_on_no_resolver_no_identity_and_an_exploding_check(self, make_app):
        """Argo's `policy.default: deny` in our vocabulary — a surface naming cluster credentials
        must not widen because a SubjectAccessReview blipped.

        The no-resolver case leaves the seam None, so the resolver build_app made against the
        configured cluster answers: it cannot reach one, reports `auth_failed`, and the gate
        refuses — the live shape of "the check did not come back"."""
        class _Explodes:
            def resolve(self, viewer):
                raise RuntimeError("the API server said no such luck")

        with TestClient(make_app(view=None)) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        with TestClient(make_app(view=_MapResolver({"root": "all"}))) as c:
            assert c.get("/api/clusterconfigs").status_code == 403          # no identity
        with TestClient(make_app(view=_Explodes())) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403

    def test_the_wide_tier_alone_never_opens_it_the_mutant_this_kills(self, make_app):
        """The mutant: gating the route on `require_admin_tier` again. Everyone here passes the
        wide tier, so that revert makes this assertion fail."""
        app = make_app(view=_MapResolver({}))    # nobody passes the new tier
        with TestClient(app) as c:
            for who in ("root", "auditor", "viewer"):
                assert c.get("/api/clusterconfigs", headers=H(who)).status_code == 403

    def test_restrictions_off_does_not_open_the_surface(self, tmp_path):
        """`visibility.enabled=false` must not, as a side effect, hand the auditor the wiring.

        The wide views widen in that state by design — the deployment has said it trusts everyone
        its proxy admits for cluster DATA. This surface is not cluster data: it says how the fleet
        is wired. Usage made the same call (usage_scope stays self); we go further and still ask,
        so a cluster-admin keeps the tab (review of #235, Grok C2)."""
        db = str(tmp_path / "off.db"); _seed(db)
        # BOTH widening switches at once: `visibility.enabled=false` widens the wide views, and
        # `userActivity.visibility: all` widens Usage for every viewer. Neither is a statement about
        # who may read this namespace's Secrets, so neither may widen this tier.
        settings = _settings(db, view_restrictions_enabled=False, user_activity_visibility="all")
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace(
            [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"auditor": "all", "root": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})   # auditor absent
        with TestClient(app) as c:
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_build_app_constructs_two_resolvers_with_two_questions_and_two_caches(self, tmp_path):
        """The share-one-resolver mutant: one instance, its cache keyed by viewer alone, so a
        `view` verdict would answer `manage`. Also pins that construction no longer depends on
        the wide-view switch."""
        db = str(tmp_path / "two.db"); _seed(db)
        app = build_app(_settings(db), run_poller=False)          # no injection: the real path
        v = app.state.clusterconfig_view_resolver
        m = app.state.clusterconfig_manage_resolver
        assert v is not None and m is not None and v is not m
        assert v._attributes["verb"] == "get" and m._attributes["verb"] == "create"
        assert v._attributes["resource"] == "secrets" == m._attributes["resource"]
        assert v._cache is not m._cache

    def test_a_namespace_admin_who_can_create_the_secret_is_admitted(self, make_app):
        """Each level asks ITS OWN question and nothing else (the operator's ruling of 2026-09-20,
        reversing an earlier ordering).

        A reader who passes `create secrets` in this namespace — a namespace admin, say — can write
        the cluster Secret with `oc` whether or not the dashboard lets them; refusing them in the UI
        protects nothing, and because the gate IS the action's own question the ServiceAccount that
        performs the write is not acting beyond what the asker could do. RBAC is additive: holding
        the auditor role and a namespace-admin grant is not a contradiction to resolve.

        What still excludes the auditor is the plain question, measured on CRC 2026-09-20 with the
        persona's groups carried (`--as=lateef.o` plus his three groups): `get secrets` no,
        `create secrets` no.
        """
        app = make_app(view=_MapResolver({"root": "all", "nsadmin": "all"}),
                       manage=_MapResolver({"root": "all", "nsadmin": "all"}))
        app.state.tier_resolver = _MapResolver({"root": "all"})       # nsadmin is self on the wide tier
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("nsadmin")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_the_auditor_is_excluded_by_the_plain_question_without_composing_tiers(self, make_app):
        """The operator's ruling — the reporting auditor may neither view nor change this — holds
        with NO composition: the auditor simply fails `get secrets`."""
        app = make_app(view=_MapResolver({"root": "all"}), manage=_MapResolver({"root": "all"}))
        app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all"})   # wide admits them
        with TestClient(app) as c:
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403

    def test_the_two_levels_have_their_own_defaults_and_caches(self):
        """`manage` is not derived from `view`: separate settings, separate questions."""
        from gsd.config import Settings
        s = Settings(clusters=())
        assert (s.visibility_clusterconfig_view_sar_verb,
                s.visibility_clusterconfig_view_sar_resource) == ("get", "secrets")
        assert (s.visibility_clusterconfig_manage_sar_verb,
                s.visibility_clusterconfig_manage_sar_resource) == ("create", "secrets")
        assert s.visibility_clusterconfig_view_sar_api_group == ""      # the core group
