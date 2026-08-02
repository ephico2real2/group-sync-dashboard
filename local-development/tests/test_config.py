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
