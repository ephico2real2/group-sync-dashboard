"""The Cluster Configurations tab's writes (docs/specs/SPEC_S2_cluster_configurations_tab.md, #230 S2):
the writer over a fake host client that records every request, the four routes, the connection test,
the chart's writes switch, and the pin that the credential reaches no response, log record, row or
metric. The page is in tests/test_ui.py::TestClusterConfigPage.
"""

from __future__ import annotations

import base64
import json
import logging

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import SECRET_TYPE_LABEL, parse_secret
from gsd.clusterconfig.writer import (
    MANAGED_BY_ANNOTATION, CreateRequest, WriteFailed, WriteRefused, create, delete, rotate, secret_object, validate,
)
from gsd.clusterconfig.writer import test_connection as probe_connection   # not a test: pytest would collect the name
from gsd.config import ClusterConfig
from gsd.kube import FORBIDDEN, UNREACHABLE, ClusterClient, ClusterError
from test_chart_pdb import _render
from test_chart_strategy import render as _render_text
from test_clusterconfig import TOKEN, _secret
from test_visibility import H, _MapResolver, _seed, _settings

NS = "ns"
PEM = base64.b64encode(
    b"-----BEGIN CERTIFICATE-----\nMIIBszCCAVmgAwIBAgIUJ9Q1J7v8Zz0i0N2vG3Yc0z4o4rswCgYIKoZIzj0EAwIw\n-----END CERTIFICATE-----\n"
).decode()


class _Host(ClusterClient):
    """The host cluster's client over an in-memory namespace: GET/POST/PUT/DELETE on Secrets, every
    request recorded; `refuse` makes the API server answer 403 on writes."""

    def __init__(self, secrets=None, *, refuse=False):
        super().__init__(ClusterConfig(name="c1", api_url="https://host", token_env="T"))
        self.secrets = dict(secrets or {})
        self.calls: list[tuple[str, str]] = []
        self.refuse = refuse

    def _client(self):
        import contextlib
        return contextlib.nullcontext(object())

    def _get(self, client, path, params):
        self.calls.append(("GET", path))
        name = path.rsplit("/", 1)[1]
        if name in self.secrets:
            return self.secrets[name]
        raise ClusterError(UNREACHABLE, f"HTTP 404 on {path}: not found")

    def _send(self, client, method, path, *, json=None):
        self.calls.append((method, path))
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {method} {path}")
        if method == "POST":
            self.secrets[json["metadata"]["name"]] = json
            return json
        name = path.rsplit("/", 1)[1]
        if method == "PUT":
            self.secrets[name] = json
            return json
        if method == "DELETE":
            self.secrets.pop(name, None)
            return {"kind": "Status", "status": "Success"}
        raise AssertionError(method)


def _req(**kw) -> CreateRequest:
    base = dict(name="west", server="https://api.west.example:6443", credential_kind="bearerToken", token=TOKEN,
                tls_mode="trustedBundle", labels={"environment": "prod"})
    base.update(kw)
    return CreateRequest(**base)


# ── the writer ────────────────────────────────────────────────────────────────────────────────────────────

class TestWriter:
    def test_the_secret_written_is_the_pages_twin_with_the_credential_substituted_and_parses_as_discovery_would(self):
        live, twin = secret_object(_req(), NS), secret_object(_req(), NS, redact=True)
        assert live["metadata"] == twin["metadata"] == {
            "name": "gsd-cluster-west", "namespace": NS,
            "labels": {SECRET_TYPE_LABEL: "cluster", "environment": "prod"},
            "annotations": {MANAGED_BY_ANNOTATION: "ui"}}
        assert {k: v for k, v in live["stringData"].items() if k != "config"} == \
               {k: v for k, v in twin["stringData"].items() if k != "config"} == \
               {"name": "west", "server": "https://api.west.example:6443", "visibility": "self-only", "identity": "none", "enabled": "true"}
        assert json.loads(live["stringData"]["config"]) == {"tlsClientConfig": {"insecure": False}, "bearerToken": TOKEN}
        assert json.loads(twin["stringData"]["config"]) == {"tlsClientConfig": {"insecure": False}, "bearerToken": "<redacted>"}
        parsed = parse_secret(live, host_name="c1")
        assert isinstance(parsed, ClusterConfig) and parsed.name == "west" and parsed.credential_kind == "bearer"
        assert parsed.tls_mode == {"insecure": False, "ca": "trusted-bundle"} and parsed.labels == (("environment", "prod"),)

    @pytest.mark.parametrize("kw,code", [
        (dict(credential_kind="oauth"), "oauth-exchange-not-built"),
        (dict(token=" "), "credential-missing"),
        (dict(tls_mode="caData"), "ca-data-invalid"),
        (dict(tls_mode="caData", ca_data="not-base64!"), "ca-data-invalid"),
        (dict(tls_mode="caData", ca_data=base64.b64encode(b"not a pem").decode()), "ca-data-invalid"),
        (dict(tls_mode="mutual"), "unsupported-config-key"),
        (dict(name="West Cluster"), "name-invalid"),
        (dict(server="http://api.west.example"), "server-invalid"),
        (dict(name="c1"), "host-cluster-not-from-secret"),
        (dict(server="https://kubernetes.default.svc"), "host-cluster-not-from-secret"),
        (dict(labels={"groupsync-dashboard.io/secret-type": "cluster"}), "unsupported-config-key"),
        (dict(visibility="remote-sar"), "visibility-invalid"),
    ])
    def test_each_refusal_names_its_code_before_any_write(self, kw, code):
        with pytest.raises(WriteRefused) as exc:
            validate(_req(**kw), NS, host_name="c1", taken={})
        assert exc.value.code == code and TOKEN not in str(exc.value)

    def test_the_three_tls_modes_write_what_the_contract_says(self):
        assert json.loads(secret_object(_req(tls_mode="trustedBundle"), NS)["stringData"]["config"])["tlsClientConfig"] == {"insecure": False}
        assert json.loads(secret_object(_req(tls_mode="insecure"), NS)["stringData"]["config"])["tlsClientConfig"] == {"insecure": True}
        assert json.loads(secret_object(_req(tls_mode="caData", ca_data=PEM), NS)["stringData"]["config"])["tlsClientConfig"] == {"insecure": False, "caData": PEM}
        assert validate(_req(tls_mode="insecure"), NS, host_name="c1", taken={}).tls_mode == {"insecure": True, "ca": None}

    def test_a_duplicate_name_is_a_conflict_naming_the_source_that_has_it(self):
        with pytest.raises(WriteRefused) as exc:
            validate(_req(), NS, host_name="c1", taken={"west": "secret:gsd-cluster-west"})
        assert exc.value.code == "duplicate-cluster-name" and exc.value.conflict and "secret:gsd-cluster-west" in exc.value.detail

    def test_create_posts_into_the_namespace_after_a_404_probe_and_logs_the_person_the_verb_and_the_secret(self, caplog):
        host = _Host()
        with caplog.at_level(logging.INFO):
            assert create(host, NS, _req(), host_name="c1", taken={}, viewer="root") == "gsd-cluster-west"
        assert host.calls == [("GET", "/api/v1/namespaces/ns/secrets/gsd-cluster-west"), ("POST", "/api/v1/namespaces/ns/secrets")]
        assert host.secrets["gsd-cluster-west"]["metadata"]["annotations"] == {MANAGED_BY_ANNOTATION: "ui"}
        assert "cluster Secret gsd-cluster-west created by root for cluster west" in caplog.text
        assert TOKEN not in caplog.text
        with pytest.raises(WriteRefused) as exc:
            create(host, NS, _req(), host_name="c1", taken={}, viewer="root")
        assert exc.value.code == "secret-exists" and exc.value.conflict

    def test_a_403_from_the_api_server_names_the_chart_switch(self):
        with pytest.raises(WriteFailed) as exc:
            create(_Host(refuse=True), NS, _req(), host_name="c1", taken={}, viewer="root")
        assert exc.value.outcome == FORBIDDEN and "clusterConfig.secrets.writes" in exc.value.message

    def test_rotate_replaces_the_token_in_place_and_keeps_every_other_key(self, caplog):
        existing = _secret("gsd-cluster-east", config={"bearerToken": "old", "tlsClientConfig": {"insecure": True}}, visibility="inherit")
        host = _Host({"gsd-cluster-east": existing})
        with caplog.at_level(logging.INFO):
            rotate(host, NS, "gsd-cluster-east", "new-token-1234", viewer="root", cluster="east")
        written = host.secrets["gsd-cluster-east"]
        config = json.loads(base64.b64decode(written["data"]["config"]))
        assert config == {"bearerToken": "new-token-1234", "tlsClientConfig": {"insecure": True}}
        assert base64.b64decode(written["data"]["visibility"]) == b"inherit"
        assert host.calls[-1] == ("PUT", "/api/v1/namespaces/ns/secrets/gsd-cluster-east")
        assert "credential rotated by root for cluster east" in caplog.text and "new-token-1234" not in caplog.text

    def test_a_secret_without_our_label_is_never_touched_and_an_absent_one_is_named(self):
        plain = {"metadata": {"name": "other", "labels": {"app": "x"}}, "data": {}}
        host = _Host({"other": plain})
        for fn in (lambda: rotate(host, NS, "other", "t", viewer="root", cluster="x"),
                   lambda: delete(host, NS, "other", viewer="root", cluster="x")):
            with pytest.raises(WriteRefused) as exc:
                fn()
            assert exc.value.code == "not-our-secret"
        assert all(m == "GET" for m, _ in host.calls) and "other" in host.secrets
        with pytest.raises(WriteRefused) as exc:
            delete(host, NS, "missing", viewer="root", cluster="x")
        assert exc.value.code == "not-our-secret"

    def test_delete_removes_the_secret_and_logs_it(self, caplog):
        host = _Host({"gsd-cluster-east": _secret("gsd-cluster-east")})
        with caplog.at_level(logging.INFO):
            delete(host, NS, "gsd-cluster-east", viewer="root", cluster="east")
        assert "gsd-cluster-east" not in host.secrets and host.calls[-1][0] == "DELETE"
        assert "cluster Secret gsd-cluster-east deleted by root for cluster east" in caplog.text

    def test_the_connection_test_probes_version_and_identity_and_stores_nothing(self, monkeypatch, caplog):
        answers = {"/version": {"gitVersion": "v1.31.6"}, "/apis/user.openshift.io/v1/users/~": {"metadata": {"name": "system:serviceaccount:ns:reader"}}}
        seen: list[str] = []

        class _Probe(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                seen.append(path)
                if path in answers:
                    return answers[path]
                raise ClusterError(UNREACHABLE, f"HTTP 404 on {path}: not found")

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Probe)
        with caplog.at_level(logging.INFO):
            out = probe_connection(_req(), NS, host_name="c1", timeout=5.0, viewer="root")
        assert out == {"reachable": True, "server_version": "v1.31.6", "identity": "system:serviceaccount:ns:reader", "error": None}
        assert seen == ["/version", "/apis/user.openshift.io/v1/users/~"]
        assert "connection test by root against https://api.west.example:6443: reachable" in caplog.text and TOKEN not in caplog.text
        del answers["/apis/user.openshift.io/v1/users/~"]      # a cluster without the OpenShift user API
        assert probe_connection(_req(), NS, host_name="c1", timeout=5.0, viewer="root")["identity"] is None
        answers.clear()
        answers["/version"] = None

        def boom(self, client, path, params):
            raise ClusterError("auth_failed", "401 Unauthorized — token invalid or expired")
        monkeypatch.setattr(_Probe, "_get", boom)
        out = probe_connection(_req(), NS, host_name="c1", timeout=5.0, viewer="root")
        assert out["reachable"] is False and out["error"].startswith("auth_failed:")

    def test_an_open_version_with_a_refused_identity_is_not_reachable(self, monkeypatch):
        """`/version` answers an ANONYMOUS request on OpenShift, so a connection test that set
        `reachable` there reported a working credential for a token that was expired, revoked or
        wrong — the one answer this control exists to give (review of #237, Grok)."""
        class _Probe(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                if path == "/version":
                    return {"gitVersion": "v1.31.6"}
                raise ClusterError("auth_failed", "401 Unauthorized — token invalid or expired")

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Probe)
        out = probe_connection(_req(), NS, host_name="c1", timeout=5.0, viewer="root")
        assert out["reachable"] is False and out["error"].startswith("auth_failed:")
        assert out["server_version"] == "v1.31.6"     # what was learned is still reported


# ── the API ───────────────────────────────────────────────────────────────────────────────────────────────

class TestApi:
    @pytest.fixture
    def rig(self, tmp_path, monkeypatch):
        import dataclasses
        db = str(tmp_path / "gsd.db"); _seed(db)
        settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True)   # the switch, on for this rig
        settings.cluster_registry.namespace = NS
        east = parse_secret(_secret(), host_name="c1")
        settings.cluster_registry.replace([east], [], at="2026-09-20T16:05:12Z")
        host = _Host({"gsd-cluster-east": _secret()})
        monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
        monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        # The Cluster Configurations tier's own two seams (#230): root holds both levels here, and
        # the tier's tests below drive every other combination.
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            yield c, app, host, settings

    BODY = {"name": "west", "server": "https://api.west.example:6443",
            "credential": {"kind": "bearerToken", "token": TOKEN},
            "tls": {"mode": "trustedBundle"}, "visibility": "self-only", "identity": "none", "labels": {"environment": "prod"}}

    def test_every_route_is_administrator_tier(self, rig):
        c, *_ = rig
        assert c.post("/api/clusterconfigs", json=self.BODY, headers=H("alice")).status_code == 403
        assert c.put("/api/clusterconfigs/east/credential", json={"token": "t"}, headers=H("alice")).status_code == 403
        assert c.delete("/api/clusterconfigs/east", headers=H("alice")).status_code == 403
        assert c.post("/api/clusterconfigs/test", json=self.BODY, headers=H("alice")).status_code == 403

    @pytest.mark.parametrize("body,where", [
        ({**BODY, "config": '{"bearerToken": "x"}'}, "body"),
        ({**BODY, "tls": {"mode": "caData", "caData": PEM, "insecure": True}}, "tls"),
        ({**BODY, "credential": {"kind": "bearerToken", "token": TOKEN, "execProviderConfig": {}}}, "credential"),
    ])
    def test_a_field_the_shape_does_not_carry_is_refused_by_name_never_ignored(self, rig, body, where):
        """`tls: {mode: caData, caData: …, insecure: true}` answered 201 and wrote `insecure: false`:
        the caller asked for two contradictory things and was told they got both. The operator's rule
        for this surface is that caData beside insecure is refused naming both fields, never
        normalised (#230; review of #237, Codex C4)."""
        c, _, host, _ = rig
        before = list(host.calls)
        r = c.post("/api/clusterconfigs", json=body, headers=H("root"))
        assert r.status_code == 422 and where in r.json()["detail"]
        assert host.calls == before, "refused before any request to the API server"

    def test_create_writes_the_secret_requests_a_discovery_and_answers_201_without_the_token(self, rig, caplog):
        c, app, host, settings = rig

        class _P:
            woken = 0

            def request_discovery(self):
                self.woken += 1
        app.state.poller = _P()
        with caplog.at_level(logging.DEBUG):
            r = c.post("/api/clusterconfigs", json=self.BODY, headers=H("root"))
        assert r.status_code == 201, r.text
        assert r.json() == {"secret": "gsd-cluster-west", "cluster": "west", "discovery": "requested"}
        assert app.state.poller.woken == 1
        assert host.secrets["gsd-cluster-west"]["stringData"]["name"] == "west"
        assert TOKEN not in r.text and TOKEN not in caplog.text
        assert "cluster Secret gsd-cluster-west created by root for cluster west" in caplog.text

    @pytest.mark.parametrize("patch,status,code", [
        ({"credential": {"kind": "oauth", "username": "u", "password": "p"}}, 422, "oauth-exchange-not-built"),
        ({"tls": {"mode": "caData"}}, 422, "ca-data-invalid"),
        ({"name": "c1"}, 422, "host-cluster-not-from-secret"),
        ({"name": "east"}, 409, "duplicate-cluster-name"),
        ({"name": "Bad Name"}, 422, "name-invalid"),
    ])
    def test_each_refusal_answers_its_code_and_writes_nothing(self, rig, patch, status, code):
        c, app, host, settings = rig
        r = c.post("/api/clusterconfigs", json={**self.BODY, **patch}, headers=H("root"))
        assert r.status_code == status and r.json()["detail"].startswith(code + ":"), r.text
        assert not any(m in ("POST", "PUT", "DELETE") for m, _ in host.calls)

    def test_the_writes_switch_off_registers_no_write_route_and_the_read_says_so(self, tmp_path):
        """The default (SPEC_S2 C6): the dashboard is a reader — a POST is a 405 from a route that does not
        exist, never a route that refuses; the read payload says `writes: false` so the tab is read-only."""
        db = str(tmp_path / "off.db"); _seed(db)
        settings = _settings(db)
        assert settings.cluster_secrets_writes_enabled is False
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            # a POST on the read path is a 405 (the path exists for GET); the write-only paths are 404s — routes that
            # were never registered, never routes that refuse
            assert c.post("/api/clusterconfigs", json=self.BODY, headers=H("root")).status_code == 405
            for r in (c.put("/api/clusterconfigs/east/credential", json={"token": "t"}, headers=H("root")),
                      c.delete("/api/clusterconfigs/east", headers=H("root")),
                      c.post("/api/clusterconfigs/test", json=self.BODY, headers=H("root"))):
                assert r.status_code == 404, (r.status_code, r.text)
            body = c.get("/api/clusterconfigs", headers=H("root")).json()
            assert body["secrets"]["writes"] is False
        paths = app.openapi()["paths"]
        assert "/api/clusterconfigs/test" not in paths and "post" not in paths["/api/clusterconfigs"]

    def test_the_rig_with_writes_on_says_so(self, rig):
        c, *_ = rig
        assert c.get("/api/clusterconfigs", headers=H("root")).json()["secrets"]["writes"] is True

    def test_rotate_and_delete_are_for_secret_clusters_only(self, rig):
        c, app, host, settings = rig
        assert c.put("/api/clusterconfigs/nope/credential", json={"token": "t"}, headers=H("root")).status_code == 404
        r = c.put("/api/clusterconfigs/c1/credential", json={"token": "t"}, headers=H("root"))
        assert r.status_code == 409 and r.json()["detail"].startswith("not-a-secret-cluster:")
        r = c.delete("/api/clusterconfigs/c1", headers=H("root"))
        assert r.status_code == 409 and r.json()["detail"].startswith("not-a-secret-cluster:")
        r = c.put("/api/clusterconfigs/east/credential", json={"token": "rotated-9876"}, headers=H("root"))
        assert r.status_code == 200 and r.json() == {"secret": "gsd-cluster-east", "cluster": "east", "discovery": "on the next cadence"}
        assert "rotated-9876" not in r.text
        assert json.loads(base64.b64decode(host.secrets["gsd-cluster-east"]["data"]["config"]))["bearerToken"] == "rotated-9876"
        r = c.delete("/api/clusterconfigs/east", headers=H("root"))
        assert r.status_code == 200 and r.json() == {"secret": "gsd-cluster-east", "cluster": "east", "retired": "on the next discovery"}
        assert "gsd-cluster-east" not in host.secrets

    def test_the_api_servers_403_is_a_502_naming_the_switch(self, rig):
        c, app, host, settings = rig
        host.refuse = True
        r = c.post("/api/clusterconfigs", json=self.BODY, headers=H("root"))
        assert r.status_code == 502 and "clusterConfig.secrets.writes" in r.json()["detail"]

    def test_the_connection_test_never_writes_and_never_registers(self, rig, monkeypatch):
        c, app, host, settings = rig
        monkeypatch.setattr("gsd.clusterconfig.writer.test_connection",
                            lambda req, ns, **kw: {"reachable": False, "server_version": None, "identity": None, "error": "unreachable: ConnectError"})
        r = c.post("/api/clusterconfigs/test", json={k: v for k, v in self.BODY.items() if k != "name"}, headers=H("root"))
        assert r.status_code == 200 and r.json()["reachable"] is False
        assert host.calls == [] and "probe" not in {x["id"] for x in c.get("/api/clusterconfigs", headers=H("root")).json()["clusters"]}

    def test_the_credential_reaches_no_response_no_log_record_no_row_and_no_metric(self, rig, caplog):
        c, app, host, settings = rig
        with caplog.at_level(logging.DEBUG):
            texts = [c.post("/api/clusterconfigs", json=self.BODY, headers=H("root")).text,
                     c.put("/api/clusterconfigs/east/credential", json={"token": TOKEN}, headers=H("root")).text]
            texts += [c.get(p, headers=H("root")).text for p in ("/api/clusterconfigs", "/api/clusters", "/readyz", "/metrics")]
            # THE REFUSAL PATHS TOO, not only the happy ones: a 422 or 409 is where a handler is most
            # tempted to echo the request back for context, and the request carries the token
            # (review of #237, Grok). One of each refusal that reaches the body with a credential in it.
            texts += [c.post("/api/clusterconfigs", json={**self.BODY, "name": "Bad Name"}, headers=H("root")).text,
                      c.post("/api/clusterconfigs", json={**self.BODY, "tls": {"mode": "caData", "caData": "not-base64!"}}, headers=H("root")).text,
                      c.post("/api/clusterconfigs", json={**self.BODY, "config": "raw"}, headers=H("root")).text,
                      c.post("/api/clusterconfigs", json={**self.BODY, "name": "east"}, headers=H("root")).text,
                      c.post("/api/clusterconfigs/test", json={**self.BODY, "server": "http://insecure"}, headers=H("root")).text]
        assert all(TOKEN not in t for t in texts)
        assert TOKEN not in "\n".join(r.getMessage() for r in caplog.records)
        assert TOKEN not in "\n".join(app.state.store._conn.iterdump())


# ── the chart ─────────────────────────────────────────────────────────────────────────────────────────────

class TestChart:
    def test_the_writes_switch_is_off_by_default_and_on_adds_exactly_the_three_verbs(self):
        role = next(d for d in _render() if d.get("kind") == "Role" and d["metadata"]["name"].endswith("-cluster-secrets"))
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
        from test_chart_reporting import _config_data
        ok, out = _render_text()
        assert ok and _config_data(out)["clusterSecretsWritesEnabled"] is False
        role = next(d for d in _render("clusterConfig.secrets.writes.enabled=true")
                    if d.get("kind") == "Role" and d["metadata"]["name"].endswith("-cluster-secrets"))
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch", "create", "update", "delete"]}]
        ok, out = _render_text(clusterConfig__secrets__writes__enabled="true")
        assert ok and _config_data(out)["clusterSecretsWritesEnabled"] is True


# ── the Cluster Configurations tier (#230): two levels, Argo's model in OpenShift RBAC ────────────
#
# `clusterconfig:view` (default SAR `get secrets` in the dashboard's namespace) gates the tab and the
# read; `clusterconfig:manage` (`create secrets`) gates the four writes and the form's controls. The
# wide tier is NOT enough: it admits cluster-reader, the deliberate auditor persona, and the operator
# ruled this surface cluster-admin-only (2026-09-20). Measured on CRC the same day: cluster-reader
# carries no rule covering `secrets` at all, so it fails both levels by construction.
class TestClusterConfigTier:
    BODY = TestApi.BODY

    @pytest.fixture
    def rig(self, tmp_path, monkeypatch):
        """Three personas against one app: `root` holds both levels, `viewer` only `view`, and
        `auditor` neither — but `auditor` DOES hold the wide tier, which is what makes the mutant
        test below meaningful."""
        import dataclasses
        db = str(tmp_path / "tier.db"); _seed(db)
        settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True)
        settings.cluster_registry.namespace = NS
        settings.cluster_registry.replace([parse_secret(_secret(), host_name="c1")], [],
                                          at="2026-09-20T16:05:12Z")
        host = _Host({"gsd-cluster-east": _secret()})
        monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
        monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
        app = build_app(settings, run_poller=False)
        # EVERY persona passes the wide tier, exactly as cluster-reader does on a real cluster.
        app.state.tier_resolver = _MapResolver({"root": "all", "viewer": "all", "auditor": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all", "viewer": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            yield c

    def _writes(self, c, who):
        h = H(who) if who else {}          # no X-Forwarded-User at all: the anonymous caller
        return [c.post("/api/clusterconfigs", json=self.BODY, headers=h),
                c.put("/api/clusterconfigs/east/credential", json={"token": "t"}, headers=h),
                c.delete("/api/clusterconfigs/east", headers=h),
                c.post("/api/clusterconfigs/test", json=self.BODY, headers=h)]

    def test_the_auditor_is_refused_everywhere_and_is_never_told_the_surface_exists(self, rig):
        """The mutant killer: `auditor` passes the WIDE tier, so any route that reverted to
        require_admin_tier would answer 200/201 here."""
        read = rig.get("/api/clusterconfigs", headers=H("auditor"))
        assert read.status_code == 403
        assert "east" not in read.text and "gsd-cluster" not in read.text    # no cluster names in a refusal
        assert [r.status_code for r in self._writes(rig, "auditor")] == [403, 403, 403, 403]
        who = rig.get("/api/whoami", headers=H("auditor")).json()
        assert who["clusterconfig"] == {"view": False, "manage": False}      # no tab for this reader

    def test_view_without_manage_reads_the_surface_and_changes_nothing(self, rig):
        body = rig.get("/api/clusterconfigs", headers=H("viewer")).json()
        assert body["can"] == {"view": True, "manage": False}
        assert [c["id"] for c in body["clusters"]]                            # the cards are there to read
        assert [r.status_code for r in self._writes(rig, "viewer")] == [403, 403, 403, 403]
        assert rig.get("/api/whoami", headers=H("viewer")).json()["clusterconfig"] == {"view": True, "manage": False}

    def test_the_administrator_holds_both_levels(self, rig):
        assert rig.get("/api/clusterconfigs", headers=H("root")).json()["can"] == {"view": True, "manage": True}
        assert rig.get("/api/whoami", headers=H("root")).json()["clusterconfig"] == {"view": True, "manage": True}
        assert rig.post("/api/clusterconfigs/test", json=self.BODY, headers=H("root")).status_code == 200

    def test_a_reader_with_no_trusted_identity_is_refused(self, rig):
        """The proxy-off hole: `trusted_viewer` is None, the tier machinery is inert, and the write
        routes used to stamp the audit line "anonymous" and mint cluster access anyway."""
        assert rig.get("/api/clusterconfigs").status_code == 403
        assert [r.status_code for r in (
            rig.post("/api/clusterconfigs", json=self.BODY),
            rig.put("/api/clusterconfigs/east/credential", json={"token": "t"}),
            rig.delete("/api/clusterconfigs/east"),
            rig.post("/api/clusterconfigs/test", json=self.BODY))] == [403, 403, 403, 403]

    def test_every_write_refuses_a_caller_with_no_trusted_identity_even_with_restrictions_off(self, tmp_path, monkeypatch):
        """The anonymous path (OB2 design review, #230 C7). `visibilityEnabled: false` is a documented
        choice about READING — every tier answers `all` and, with the proxy off, there is no identity
        at all. A write into the credential store, audited as "anonymous", is not covered by it, so the
        writes need a proxy-verified viewer AND the tier machinery on."""
        import dataclasses
        db = str(tmp_path / "anon.db"); _seed(db)
        settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True,
                                       view_restrictions_enabled=False)    # reads widen; writes must not
        settings.cluster_registry.namespace = NS
        settings.cluster_registry.replace([parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        host = _Host({"gsd-cluster-east": _secret()})
        monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
        monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
        app = build_app(settings, run_poller=False)
        with TestClient(app) as c:
            before = list(host.calls)
            for r in self._writes(c, None):
                assert r.status_code == 403, r.text
                assert "identity" in r.json()["detail"]
            assert host.calls == before, "nothing reached the API server"

    def test_no_resolver_fails_closed(self, rig):
        """Argo's `policy.default: deny`: an instance that built no resolver — restrictions off, or no
        host cluster to review against — refuses rather than falling back to the wide tier."""
        rig.app.state.clusterconfig_view_resolver = None
        rig.app.state.clusterconfig_manage_resolver = None
        assert rig.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "root")] == [403, 403, 403, 403]
