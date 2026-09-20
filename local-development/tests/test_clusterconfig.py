"""Clusters as labelled Secrets (#230 S1, docs/specs/SPEC_S1_cluster_secrets.md): the parser (one test per
contract row), the registry's precedence, the reader over a paged fake client, the poller's discovery
stage, the API and — the pin that matters most — that the credential never leaves the Secret and the
process's memory: not the database, not a log record, not a response, not /metrics."""

from __future__ import annotations

import base64
import json
import logging
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
        assert [(c.name, c.source) for c in clusters] == [("east", "secret:a-first"), ("west", "secret:d-shadow"), ("north", "secret:e-oauth")]
        assert sorted((f.secret, f.code) for f in findings) == [("b-dup", "duplicate-cluster-name"), ("c-bad", "config-not-json"),
                                                                ("d-shadow", "shadows-values-entry"), ("e-oauth", "oauth-exchange-not-built")]

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
