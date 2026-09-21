"""S3a (SPEC_S3 §4, §4.1, §4.2 — #248): the values loader and the Secret parser learn the three
connection-mode keys with the same refusals, each naming the cluster and the key; a cluster declaring a
mode is listed with a pending credential and is never polled (so never a false `auth_failed`); and the
guard that fails the commit on which the two readers' key sets diverge."""

from __future__ import annotations

import json
import time

import pytest

from gsd.clusterconfig import Finding, parse_secret
from gsd.clusterconfig.parser import ACCEPTED_CONFIG_KEYS, _ECHOABLE_KEYS
from gsd.config import (
    BOOTSTRAP_KEY, CONNECTION_KEYS, CONNECTION_MODE_KEYS, VALUES_CLUSTER_KEYS, ClusterConfig, ConfigError,
    Settings, load_settings,
)
from gsd.poller import Poller
from gsd.store import Store
from test_clusterconfig import _Host, _secret

_BASE = """
clusters:
  - name: dashboard
    apiUrl: https://kubernetes.default.svc
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
    dashboardController: true
  - name: shared-rnd
    apiUrl: https://api.crc.testing:6443
{extra}"""


def _load(tmp_path, extra: str = "", body: str | None = None):
    p = tmp_path / "clusters.yaml"
    p.write_text(body if body is not None else _BASE.format(extra=extra))
    return load_settings(str(p))


def _refused(tmp_path, extra: str = "", body: str | None = None) -> str:
    with pytest.raises(ConfigError) as exc:
        _load(tmp_path, extra, body)
    return str(exc.value)


# ── the loader (§4 items 1-6) ──────────────────────────────────────────────────────────────────

class TestTheLoader:
    @pytest.mark.parametrize("key,kind", [("saTokenLookup", "lookup"), ("userSelfLogin", "self-login")])
    def test_a_stanza_declaring_a_mode_loads_without_a_credential(self, tmp_path, key, kind):
        s = _load(tmp_path, f"    {key}: true\n")
        c = s.cluster("shared-rnd")
        assert (c.connection_mode, c.credential_kind, c.ldap_connection_bootstrap) == (key, kind, None)
        assert c.credential_pending and "S3b" in c.credential_pending
        with pytest.raises(ConfigError, match="S3b"):
            c.resolve_token()      # §4.2: nothing has been obtained, and the message says so
        assert s.host_cluster().name == "dashboard"

    def test_a_stanza_declaring_neither_mode_nor_credential_keeps_todays_refusal(self, tmp_path):
        assert "clusters[1]: one of tokenEnv or tokenFile is required" in _refused(tmp_path)

    def test_a_mode_declared_false_is_not_a_mode(self, tmp_path):
        assert "one of tokenEnv or tokenFile is required" in _refused(tmp_path, "    saTokenLookup: false\n")

    def test_both_modes_are_refused_naming_the_cluster_and_both_keys(self, tmp_path):
        msg = _refused(tmp_path, "    saTokenLookup: true\n    userSelfLogin: true\n")
        assert "'shared-rnd'" in msg and "saTokenLookup and userSelfLogin" in msg and "declare one" in msg

    @pytest.mark.parametrize("cred", ["tokenEnv: T", "tokenFile: /t"])
    def test_a_mode_beside_a_credential_is_refused_naming_both(self, tmp_path, cred):
        msg = _refused(tmp_path, f"    userSelfLogin: true\n    {cred}\n")
        assert "'shared-rnd' declares userSelfLogin and also " + cred.split(":")[0] in msg
        assert "two sources of truth" in msg

    @pytest.mark.parametrize("word", ["'yes'", "1", "null"])
    def test_a_mode_is_a_word_not_truthiness(self, tmp_path, word):
        msg = _refused(tmp_path, f"    saTokenLookup: {word}\n")
        assert "'shared-rnd': saTokenLookup must be true or false" in msg

    def test_a_mode_on_the_declared_controller_is_refused(self, tmp_path):
        body = _BASE.format(extra="    tokenEnv: T\n").replace(
            "    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token\n", "    saTokenLookup: true\n")
        msg = _refused(tmp_path, body=body)
        assert "'dashboard' is the hosting cluster (declared by dashboardController) and declares saTokenLookup" in msg

    def test_a_mode_on_the_inferred_host_is_refused_too(self, tmp_path):
        body = ("clusters:\n  - name: only\n    apiUrl: https://api.example:6443\n    userSelfLogin: true\n")
        msg = _refused(tmp_path, body=body)
        assert "'only' is the hosting cluster (the first enabled entry, since none declares dashboardController)" in msg
        assert "declares userSelfLogin" in msg

    def test_the_bootstrap_account_is_carried_when_a_mode_is_declared(self, tmp_path):
        c = _load(tmp_path, "    saTokenLookup: true\n    ldapConnectionBootstrap: svc-gsd.fleet@corp\n").cluster("shared-rnd")
        assert c.ldap_connection_bootstrap == "svc-gsd.fleet@corp"

    def test_the_bootstrap_account_without_a_mode_is_refused_by_name(self, tmp_path):
        msg = _refused(tmp_path, "    tokenEnv: T\n    ldapConnectionBootstrap: svc\n")
        assert "'shared-rnd': ldapConnectionBootstrap without saTokenLookup or userSelfLogin" in msg

    @pytest.mark.parametrize("value", ["'svc gsd'", "'a:b'", "'cn=x,ou=y'", "''", "42"])
    def test_the_bootstrap_account_is_a_username_not_free_text_and_is_never_echoed(self, tmp_path, value):
        msg = _refused(tmp_path, f"    saTokenLookup: true\n    ldapConnectionBootstrap: {value}\n")
        assert "'shared-rnd': ldapConnectionBootstrap must be a username" in msg
        assert value.strip("'") not in msg.split("ldapConnectionBootstrap", 1)[1] or value.strip("'") == ""

    def test_a_misspelled_mode_key_is_still_refused_by_name(self, tmp_path):
        assert "unknown key(s) ['saTokenLookupp']" in _refused(tmp_path, "    saTokenLookupp: true\n")

    def test_an_existing_credential_stanza_is_unchanged(self, tmp_path):
        c = _load(tmp_path, "    tokenEnv: T\n").cluster("shared-rnd")
        assert (c.credential_kind, c.connection_mode, c.credential_pending) == ("file", None, None)


# ── the parser (§4: the same three keys in `config`, a finding not a crash) ───────────────────

class TestTheParser:
    @pytest.mark.parametrize("key,kind", [("saTokenLookup", "lookup"), ("userSelfLogin", "self-login")])
    def test_a_secret_declaring_a_mode_parses_with_a_pending_credential(self, key, kind):
        c = parse_secret(_secret(config={key: True, BOOTSTRAP_KEY: "svc-gsd"}), host_name="dashboard")
        assert isinstance(c, ClusterConfig)
        assert (c.connection_mode, c.credential_kind, c.ldap_connection_bootstrap) == (key, kind, "svc-gsd")
        with pytest.raises(ConfigError, match="S3b"):
            c.resolve_token()

    @pytest.mark.parametrize("config,code,fragment", [
        ({"saTokenLookup": True, "userSelfLogin": True}, "credential-ambiguous", "both saTokenLookup and userSelfLogin"),
        ({"saTokenLookup": True, "bearerToken": "t0ken-t0ken"}, "credential-ambiguous", "a credential and saTokenLookup"),
        ({"userSelfLogin": True, "oauth": {"username": "u", "password": "p"}}, "credential-ambiguous", "a credential and userSelfLogin"),
        ({"saTokenLookup": "yes"}, "unsupported-config-key", "config.saTokenLookup: must be a boolean"),
        ({"bearerToken": "t0ken-t0ken", BOOTSTRAP_KEY: "svc"}, "unsupported-config-key", "without saTokenLookup or userSelfLogin"),
        ({"saTokenLookup": True, BOOTSTRAP_KEY: "svc gsd"}, "unsupported-config-key", "must be a username"),
        ({"saTokenLookup": True, BOOTSTRAP_KEY: 7}, "unsupported-config-key", "must be a username"),
        ({"saTokenLookup": False}, "credential-missing", "config needs bearerToken or oauth"),
    ])
    def test_the_refusals_are_findings_naming_the_key(self, config, code, fragment):
        f = parse_secret(_secret(config=config), host_name="dashboard")
        assert isinstance(f, Finding) and f.code == code, f
        assert fragment in f.detail
        assert "svc gsd" not in f.detail, "a bootstrap value is never echoed"

    def test_a_typo_of_a_mode_key_is_named_and_a_foreign_key_is_measured(self):
        typo = parse_secret(_secret(config={"satokenlookup": True}), host_name="dashboard")
        assert typo.code == "unsupported-config-key" and typo.detail.startswith("satokenlookup: not a key")
        foreign = parse_secret(_secret(config={"saTokenLookupp": True}), host_name="dashboard")
        assert foreign.code == "unsupported-config-key" and "14-character key" in foreign.detail
        assert "saTokenLookupp" not in foreign.detail


# ── §4.1: the guard that holds the two readers together ───────────────────────────────────────

class TestTheEquivalenceGuard:
    def test_every_connection_key_is_known_to_the_loader_accepted_by_the_parser_and_echoable(self):
        assert set(CONNECTION_KEYS) <= VALUES_CLUSTER_KEYS, "the loader would refuse a key the parser accepts"
        assert set(CONNECTION_KEYS) <= set(ACCEPTED_CONFIG_KEYS), "the parser would refuse a key the loader accepts"
        assert {k.lower() for k in CONNECTION_KEYS} <= _ECHOABLE_KEYS, "a typo would be reported by its length"
        assert set(CONNECTION_MODE_KEYS) == {"saTokenLookup", "userSelfLogin"} and BOOTSTRAP_KEY == "ldapConnectionBootstrap"

    @pytest.mark.parametrize("key", CONNECTION_MODE_KEYS)
    def test_the_same_declaration_loads_from_values_and_parses_from_a_secret(self, tmp_path, key):
        """§2's equivalence, driven: one declaration, two readers, the same ClusterConfig where it matters."""
        from_values = _load(tmp_path, f"    {key}: true\n    {BOOTSTRAP_KEY}: svc-gsd\n").cluster("shared-rnd")
        from_secret = parse_secret(_secret(cluster="shared-rnd", server="https://api.crc.testing:6443",
                                           config={key: True, BOOTSTRAP_KEY: "svc-gsd"}), host_name="dashboard")
        for field in ("name", "api_url", "connection_mode", "credential_kind", "credential_pending", "ldap_connection_bootstrap"):
            assert getattr(from_values, field) == getattr(from_secret, field), field


# ── §4.2: listed, never polled, never a false auth_failed ─────────────────────────────────────

class TestThePollPath:
    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
        monkeypatch.setattr("gsd.poller.ClusterClient", _Host)
        _Host.secrets = {"items": []}
        self.polled: list[str] = []
        monkeypatch.setattr("gsd.poller.poll_once", lambda store, cluster, *a, **k: self.polled.append(cluster.name) or "ok")
        monkeypatch.setattr("gsd.poller.capture_once", lambda *a, **k: None)
        monkeypatch.setattr("gsd.poller.refresh_bindings", lambda *a, **k: None)

    def _wait(self, cond, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cond():
                return True
            time.sleep(0.05)
        return cond()

    def test_a_values_stanza_with_a_mode_is_listed_with_its_credential_pending_and_not_polled(self, tmp_path, caplog):
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"),
                                      ClusterConfig("shared-rnd", "https://api.crc.testing:6443", sa_token_lookup=True)],
                            db_path=str(tmp_path / "p.db"), poll_interval_seconds=1, binding_interval_seconds=1)
        poller = Poller(store, settings)
        with caplog.at_level("INFO", logger="gsd.poller"):
            poller.start()
        try:
            assert self._wait(lambda: "host" in self.polled)
            row = next(r for r in store.clusters() if r["id"] == "shared-rnd")
            assert (row["credential"], row["enabled"], row["source"]) == ("lookup", 1, "values")
            assert "shared-rnd" not in poller._cluster_stops, "no poll thread for a pending credential"
            assert "shared-rnd" not in self.polled
            assert any("shared-rnd declares saTokenLookup" in r.getMessage() and "not polling" in r.getMessage()
                       for r in caplog.records)
        finally:
            poller.stop()

    def test_a_secret_declaring_a_mode_is_discovered_listed_and_not_polled(self, tmp_path):
        _Host.secrets = {"items": [_secret(config={"userSelfLogin": True})]}
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
                            db_path=str(tmp_path / "p.db"), poll_interval_seconds=1, binding_interval_seconds=1)
        poller = Poller(store, settings)
        poller.start()
        try:
            assert self._wait(lambda: "host" in self.polled)
            east = settings.cluster("east")
            assert east is not None and east.credential_kind == "self-login" and east.source == "secret:gsd-cluster-east"
            assert "east" not in poller._cluster_stops and "east" not in self.polled
            assert next(r for r in store.clusters() if r["id"] == "east")["credential"] == "self-login"
        finally:
            poller.stop()
