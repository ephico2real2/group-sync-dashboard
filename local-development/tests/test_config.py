"""Configuration loading and validation.

Validation is strict on purpose: a typo'd key in a cluster entry should fail at startup
naming the offending key, not surface later as a cluster that silently never polls.
"""

from __future__ import annotations

import ssl

import pytest

from gsd.config import ClusterConfig, ConfigError, load_settings

BASE = """
clusters:
  - name: crc-local
    apiUrl: https://api.crc.testing:6443
    tokenEnv: GSD_TOKEN_CRC
"""


def write(tmp_path, text: str) -> str:
    p = tmp_path / "clusters.yaml"
    p.write_text(text)
    return str(p)


class TestValidation:
    def test_minimal_config_loads(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert [c.name for c in s.clusters] == ["crc-local"]
        assert s.poll_interval_seconds == 60 and s.schedule_grace_seconds == 120

    def test_trailing_slash_is_stripped_from_api_url(self, tmp_path):
        cfg = BASE.replace("https://api.crc.testing:6443", "https://api.crc.testing:6443/")
        assert load_settings(write(tmp_path, cfg)).clusters[0].api_url.endswith("6443")

    def test_unknown_key_is_rejected(self, tmp_path):
        """A typo like `tokenEnvv` must not silently leave the cluster tokenless."""
        with pytest.raises(ConfigError, match="unknown key"):
            load_settings(write(tmp_path, BASE + "    tokenEnvv: X\n"))

    def test_missing_token_source_is_rejected(self, tmp_path):
        cfg = BASE.replace("    tokenEnv: GSD_TOKEN_CRC\n", "")
        with pytest.raises(ConfigError, match="tokenEnv or tokenFile"):
            load_settings(write(tmp_path, cfg))

    def test_duplicate_cluster_names_rejected(self, tmp_path):
        with pytest.raises(ConfigError, match="duplicate"):
            load_settings(write(tmp_path, BASE + BASE.replace("clusters:\n", "")))

    def test_name_with_slash_rejected(self, tmp_path):
        """The name is used verbatim in API paths."""
        with pytest.raises(ConfigError, match="must not contain"):
            load_settings(write(tmp_path, BASE.replace("crc-local", "a/b")))

    def test_insecure_and_ca_bundle_are_mutually_exclusive(self, tmp_path):
        cfg = BASE + "    insecureSkipVerify: true\n    caBundleFile: ca.crt\n"
        with pytest.raises(ConfigError, match="mutually exclusive"):
            load_settings(write(tmp_path, cfg))

    def test_bad_api_url_scheme_rejected(self, tmp_path):
        with pytest.raises(ConfigError, match="http"):
            load_settings(write(tmp_path, BASE.replace("https://", "ftp://")))

    def test_empty_cluster_list_rejected(self, tmp_path):
        with pytest.raises(ConfigError, match="non-empty"):
            load_settings(write(tmp_path, "clusters: []\n"))


class TestDbPathOverride:
    def test_env_wins_over_file(self, tmp_path, monkeypatch):
        """The container sets GSD_DB_PATH so a ConfigMap need not know the volume path."""
        monkeypatch.setenv("GSD_DB_PATH", "/data/gsd.db")
        assert load_settings(write(tmp_path, BASE + "dbPath: local.db\n")).db_path == "/data/gsd.db"

    def test_file_used_when_env_absent(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_DB_PATH", raising=False)
        assert load_settings(write(tmp_path, BASE + "dbPath: local.db\n")).db_path == "local.db"


class TestBooleanSettings:
    def test_a_false_env_var_actually_disables(self, tmp_path, monkeypatch):
        """The trap this exists for: bool("false") is True, so a plain cast turns every
        explicit disable in an env var into an enable — silently, and in the direction
        that grants rather than withholds."""
        monkeypatch.setenv("GSD_OAUTH_PROXY_ENABLED", "false")
        assert load_settings(write(tmp_path, BASE)).oauth_proxy_enabled is False

    def test_the_yaml_spellings_are_accepted(self, tmp_path, monkeypatch):
        for word in ("true", "TRUE", "yes", "on", "1"):
            monkeypatch.setenv("GSD_OAUTH_PROXY_ENABLED", word)
            assert load_settings(write(tmp_path, BASE)).oauth_proxy_enabled is True
        for word in ("false", "FALSE", "no", "off", "0"):
            monkeypatch.setenv("GSD_OAUTH_PROXY_ENABLED", word)
            assert load_settings(write(tmp_path, BASE)).oauth_proxy_enabled is False

    def test_a_nonsense_value_falls_back_rather_than_crashing(self, tmp_path, monkeypatch):
        """Falls back to the default, which for the proxy flag is the SAFE direction:
        no identity is trusted."""
        monkeypatch.setenv("GSD_OAUTH_PROXY_ENABLED", "maybe")
        assert load_settings(write(tmp_path, BASE)).oauth_proxy_enabled is False

    def test_the_configmap_value_is_used_when_no_env(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_ENABLED", raising=False)
        cfg = BASE + "oauthProxyEnabled: true\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_enabled is True

    def test_user_activity_defaults_on_but_is_inert_without_the_proxy(self, tmp_path, monkeypatch):
        """Both flags are needed. On its own the setting grants nothing, because without
        the proxy there is no authentication to attribute a request to."""
        monkeypatch.delenv("GSD_OAUTH_PROXY_ENABLED", raising=False)
        monkeypatch.delenv("GSD_USER_ACTIVITY_ENABLED", raising=False)
        settings = load_settings(write(tmp_path, BASE))
        assert settings.user_activity_enabled is True
        assert settings.oauth_proxy_enabled is False


class TestTokenResolution:
    def test_token_from_env(self, monkeypatch):
        monkeypatch.setenv("TOK", "  abc123  ")
        c = ClusterConfig("c", "https://x", token_env="TOK")
        assert c.resolve_token() == "abc123"

    def test_empty_env_token_is_an_error(self, monkeypatch):
        monkeypatch.setenv("TOK", "   ")
        with pytest.raises(ConfigError, match="unset or empty"):
            ClusterConfig("c", "https://x", token_env="TOK").resolve_token()

    def test_token_from_file_is_reread_each_time(self, tmp_path):
        """A mounted Secret is updated in place on rotation; a cached token would keep
        presenting the stale one until the pod restarted."""
        f = tmp_path / "token"
        f.write_text("first\n")
        c = ClusterConfig("c", "https://x", token_file=str(f))
        assert c.resolve_token() == "first"
        f.write_text("rotated\n")
        assert c.resolve_token() == "rotated"

    def test_missing_token_file_is_an_error(self, tmp_path):
        c = ClusterConfig("c", "https://x", token_file=str(tmp_path / "nope"))
        with pytest.raises(ConfigError, match="cannot read tokenFile"):
            c.resolve_token()


class TestVerify:
    def test_insecure_returns_false(self):
        assert ClusterConfig("c", "https://x", insecure_skip_verify=True).verify() is False

    def test_default_returns_true(self):
        assert ClusterConfig("c", "https://x").verify() is True

    def test_ca_bundle_returns_ssl_context(self, tmp_path):
        """An SSLContext, not a path: httpx deprecated the bare-string form."""
        import subprocess

        crt = tmp_path / "ca.crt"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=test", "-keyout", str(tmp_path / "k.pem"), "-out", str(crt)],
            check=True, capture_output=True,
        )
        assert isinstance(ClusterConfig("c", "https://x", ca_bundle_file=str(crt)).verify(),
                          ssl.SSLContext)

    def test_unreadable_ca_bundle_fails_at_config_time(self, tmp_path):
        c = ClusterConfig("c", "https://x", ca_bundle_file=str(tmp_path / "missing.crt"))
        with pytest.raises(ConfigError, match="cannot load caBundleFile"):
            c.verify()


class TestTrustedCABundleFallback:
    """External clusters are usually signed by a corporate CA that is not in Python's
    default trust store. OpenShift injects that CA into a labelled ConfigMap; the app uses
    it so those clusters verify without per-cluster configuration."""

    def _bundle(self, tmp_path):
        import subprocess
        crt = tmp_path / "ca-bundle.crt"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=corp", "-keyout", str(tmp_path / "k.pem"), "-out", str(crt)],
            check=True, capture_output=True,
        )
        return str(crt)

    def test_injected_bundle_is_used_when_no_explicit_one(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", self._bundle(tmp_path))
        assert isinstance(ClusterConfig("c", "https://x").verify(), ssl.SSLContext)

    def test_explicit_bundle_wins_over_the_injected_one(self, tmp_path, monkeypatch):
        """A cluster naming its own bundle is stating what it trusts; silently widening
        that would be the wrong kind of helpful."""
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", "/nonexistent/injected.crt")
        explicit = self._bundle(tmp_path)
        assert isinstance(
            ClusterConfig("c", "https://x", ca_bundle_file=explicit).verify(), ssl.SSLContext
        )

    def test_insecure_still_overrides_everything(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", self._bundle(tmp_path))
        assert ClusterConfig("c", "https://x", insecure_skip_verify=True).verify() is False

    def test_missing_injected_file_falls_back_to_system_trust(self, monkeypatch):
        """A mount that is not there must not break verification outright."""
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", "/nonexistent/ca-bundle.crt")
        assert ClusterConfig("c", "https://x").verify() is True


class TestBothCASources:
    """Two independent CA sources can be mounted: the one OpenShift injects, and a
    ConfigMap supplied by hand for a CA the cluster has never been told about."""

    def _ca(self, tmp_path, cn):
        import subprocess
        crt = tmp_path / f"{cn}.crt"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", f"/CN={cn}", "-keyout", str(tmp_path / f"{cn}.key"), "-out", str(crt)],
            check=True, capture_output=True,
        )
        return str(crt)

    def test_both_bundles_load_together(self, tmp_path, monkeypatch):
        a, b = self._ca(tmp_path, "injected"), self._ca(tmp_path, "enterprise")
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", f"{a}:{b}")
        ctx = ClusterConfig("c", "https://x").verify()
        assert isinstance(ctx, ssl.SSLContext)
        subjects = {c["subject"][0][0][1] for c in ctx.get_ca_certs()}
        assert {"injected", "enterprise"} <= subjects, "both CAs must be trusted"

    def test_a_missing_path_is_skipped_not_fatal(self, tmp_path, monkeypatch):
        """The injected ConfigMap is populated asynchronously, so it can legitimately be
        absent for the first moments of a pod's life."""
        good = self._ca(tmp_path, "present")
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", f"/nonexistent/a.crt:{good}")
        ctx = ClusterConfig("c", "https://x").verify()
        assert isinstance(ctx, ssl.SSLContext)
        assert "present" in {c["subject"][0][0][1] for c in ctx.get_ca_certs()}

    def test_absence_is_not_cached_so_a_late_mount_is_picked_up(self, tmp_path, monkeypatch):
        """Caching the empty result would mean never seeing the injected bundle without a
        pod restart."""
        late = tmp_path / "late.crt"
        monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(late))
        assert ClusterConfig("c", "https://x").verify() is True   # not there yet
        import shutil
        shutil.copy(self._ca(tmp_path, "late-arrival"), late)
        assert isinstance(ClusterConfig("c", "https://x").verify(), ssl.SSLContext)

    def test_neither_source_falls_back_to_system_trust(self, monkeypatch):
        monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
        assert ClusterConfig("c", "https://x").verify() is True
