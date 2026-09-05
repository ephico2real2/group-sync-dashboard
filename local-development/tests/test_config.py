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


class TestViewRestrictions:
    """The per-user visibility switch and the admin-threshold SubjectAccessReview.

    The switch guards personal data, so every failure here must land on the restricted
    side: unknown values, misspelt variables and unusable SAR shapes all leave the
    control ON with the default check, never off and never half-custom.
    """

    def test_restrictions_default_on(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True

    def test_the_env_var_spelled_exactly_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is False

    def test_the_operators_original_typo_changes_nothing(self, tmp_path, monkeypatch):
        """GSD_ENABLE_VIEW_RESCRICTIONS — the misspelling that motivated the warning in
        the requirements. A misspelt variable is never read, and the default is ON, so
        the typo cannot silently disable a security control."""
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESCRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True

    def test_a_nonsense_value_stays_restricted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "maybe")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True

    def test_the_configmap_spelling_works_too(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        s = load_settings(write(tmp_path, BASE + "visibilityEnabled: false\n"))
        assert s.view_restrictions_enabled is False

    def test_admin_sar_defaults_to_cluster_wide_rbac_read(self, tmp_path):
        """The floor, and it is `list clusterrolebindings` for a measured reason.

        It was `list groups.user.openshift.io` — the threshold this repository documents as "WRONG
        — a privilege escalation, proven on the reference cluster" when it was the bearer path's
        check: an account holding only `list groups` was handed 229 bindings including a
        cluster-admin CRB. `require_admin_tier` claimed to apply that raised floor and posted the
        lower one. Among stock roles the two admit the same personas, so this is not about
        cluster-admin or cluster-reader — it is about a custom role granting directory read
        WITHOUT RBAC read, which the old default handed the whole binding surface to.
        """
        s = load_settings(write(tmp_path, BASE))
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_sar_resource == "clusterrolebindings"
        assert s.visibility_admin_sar_subresource == ""
        assert s.visibility_admin_sar_verb == "list"
        assert s.visibility_admin_sar_namespace == ""

    def test_admin_sar_is_read_from_the_configmap_keys(self, tmp_path):
        cfg = BASE + (
            'visibilityAdminSarApiGroup: "rbac.authorization.k8s.io"\n'
            'visibilityAdminSarResource: "rolebindings"\n'
            'visibilityAdminSarVerb: "list"\n'
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_sar_resource == "rolebindings"

    def test_a_subresource_spelling_is_split_for_the_sar_builder(self, tmp_path):
        cfg = BASE + (
            'visibilityAdminSarApiGroup: ""\n'
            'visibilityAdminSarResource: "pods/log"\n'
            'visibilityAdminSarVerb: "get"\n'
            'visibilityAdminSarNamespace: "openshift-authentication"\n'
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_api_group == ""       # the core group is expressible
        assert s.visibility_admin_sar_resource == "pods"
        assert s.visibility_admin_sar_subresource == "log"
        assert s.visibility_admin_sar_verb == "get"
        assert s.visibility_admin_sar_namespace == "openshift-authentication"

    def test_an_unusable_field_falls_back_to_the_whole_default_check(self, tmp_path):
        """Whole, not per-field: the operator's resource under the default verb would be
        a question nobody chose to ask. And never toward 'everyone passes'."""
        cfg = BASE + (
            'visibilityAdminSarResource: "rolebindings"\n'
            'visibilityAdminSarVerb: "List"\n'   # miscased: RBAC matching is exact
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_verb == "list"
        assert s.visibility_admin_sar_resource == "clusterrolebindings"  # not rolebindings
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"

    def test_a_nil_key_means_not_set_not_empty(self, tmp_path):
        """A hand-written `visibilityAdminSarVerb:` with no value must take the default,
        matching the chart's treatment of a commented-out sub-key."""
        s = load_settings(write(tmp_path, BASE + "visibilityAdminSarVerb:\n"))
        assert s.visibility_admin_sar_verb == "list"

    def test_the_tier_ttl_defaults_to_the_documented_window(self, tmp_path):
        assert load_settings(write(tmp_path, BASE)).visibility_tier_ttl_seconds == 60

    def test_usage_sar_defaults_to_update_clusterrolebindings(self, tmp_path):
        """The Usage tab's stricter default: a WRITE verb, the one thing that separates
        cluster-admin from the read-everything cluster-reader. Its OWN default, not adminSar's."""
        s = load_settings(write(tmp_path, BASE))
        assert s.visibility_usage_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_usage_admin_sar_resource == "clusterrolebindings"
        assert s.visibility_usage_admin_sar_subresource == ""
        assert s.visibility_usage_admin_sar_verb == "update"
        assert s.visibility_usage_admin_sar_namespace == ""

    def test_usage_sar_is_read_from_its_own_configmap_keys(self, tmp_path):
        """Its own key prefix, independent of adminSar — one parser, two thresholds."""
        cfg = BASE + (
            'visibilityUsageAdminSarApiGroup: ""\n'
            'visibilityUsageAdminSarResource: "secrets"\n'
            'visibilityUsageAdminSarVerb: "get"\n'
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_usage_admin_sar_api_group == ""      # the core group is expressible
        assert s.visibility_usage_admin_sar_resource == "secrets"
        assert s.visibility_usage_admin_sar_verb == "get"
        # adminSar is untouched by usageAdminSar keys — the two are parsed separately. Both now
        # name clusterrolebindings and differ only in VERB (list vs update), so this assertion is
        # weaker than it looks; the verb assertions above are what separate the two tiers.
        assert s.visibility_admin_sar_resource == "clusterrolebindings"
        assert s.visibility_admin_sar_verb == "list"

    def test_usage_sar_falls_back_whole_to_its_own_default(self, tmp_path):
        """An unusable field takes the ENTIRE usage default (not adminSar's, and never
        'everyone passes') — the same whole-or-nothing discipline as adminSar."""
        cfg = BASE + (
            'visibilityUsageAdminSarResource: "secrets"\n'
            'visibilityUsageAdminSarVerb: "Get"\n'   # miscased: RBAC matching is exact
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_usage_admin_sar_verb == "update"
        assert s.visibility_usage_admin_sar_resource == "clusterrolebindings"
        assert s.visibility_usage_admin_sar_api_group == "rbac.authorization.k8s.io"


class TestGroupCountCliff:
    def test_defaults_are_on_with_the_documented_floor(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert s.group_count_cliff_enabled is True
        assert (s.group_count_cliff_min_members, s.group_count_cliff_drop_ratio,
                s.group_count_cliff_window_hours, s.group_count_cliff_silence) == (10, 0.5, 24.0, ())

    def test_configmap_keys_load_and_the_silence_list_splits_on_commas(self, tmp_path):
        cfg = BASE + ("groupCountCliffEnabled: false\ngroupCountCliffMinMembers: 25\n"
                      "groupCountCliffDropRatio: 0.3\ngroupCountCliffWindowHours: 6\n"
                      "groupCountCliffSilence: \"app-ocp-rbac-contractors-*, app-ocp-rbac-x-ns-view\"\n")
        s = load_settings(write(tmp_path, cfg))
        assert s.group_count_cliff_enabled is False
        assert (s.group_count_cliff_min_members, s.group_count_cliff_drop_ratio, s.group_count_cliff_window_hours) == (25, 0.3, 6.0)
        assert s.group_count_cliff_silence == ("app-ocp-rbac-contractors-*", "app-ocp-rbac-x-ns-view")

    @pytest.mark.parametrize("line", [
        "groupCountCliffDropRatio: 0\n", "groupCountCliffDropRatio: 1.5\n",
        "groupCountCliffMinMembers: 0\n", "groupCountCliffWindowHours: 0\n",
    ])
    def test_a_threshold_that_cannot_or_always_fires_is_refused(self, tmp_path, line):
        with pytest.raises(ConfigError):
            load_settings(write(tmp_path, BASE + line))

    def test_the_window_must_cover_at_least_one_poll_interval(self, tmp_path):
        """Reconstructed from polls, a window shorter than one interval has no observation at
        its start and a cliff in it can vanish before the rule's pending period (review, PR #72)."""
        with pytest.raises(ConfigError, match="at least one poll interval"):
            load_settings(write(tmp_path, BASE + "pollIntervalSeconds: 3600\ngroupCountCliffWindowHours: 0.5\n"))
        s = load_settings(write(tmp_path, BASE + "pollIntervalSeconds: 3600\ngroupCountCliffWindowHours: 1\n"))
        assert s.group_count_cliff_window_hours == 1.0, "exactly one interval is allowed"

    def test_env_overrides_the_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_GROUP_COUNT_CLIFF_ENABLED", "false")
        monkeypatch.setenv("GSD_GROUP_COUNT_CLIFF_SILENCE", "a-*,b")
        try:
            s = load_settings(write(tmp_path, BASE + "groupCountCliffEnabled: true\n"))
        finally:
            monkeypatch.delenv("GSD_GROUP_COUNT_CLIFF_ENABLED", raising=False)
            monkeypatch.delenv("GSD_GROUP_COUNT_CLIFF_SILENCE", raising=False)
        assert s.group_count_cliff_enabled is False
        assert s.group_count_cliff_silence == ("a-*", "b")


class TestUsersProvidersAndIdentitiesRead:
    """C2: the allow-list is strict at startup (a name that can never match would list nobody) and
    the Identity read switch parses like every boolean."""

    BASE = "clusters:\n  - name: c1\n    apiUrl: https://x\n    tokenEnv: T\n"

    def test_a_comma_list_becomes_a_tuple_in_order_without_duplicates(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_USERS_PROVIDERS", raising=False)
        p = tmp_path / "c.yaml"; p.write_text(self.BASE + 'usersProviders: "ldap-local, corp,ldap-local"\n')
        assert load_settings(str(p)).users_providers == ("ldap-local", "corp")
        p.write_text(self.BASE)
        assert load_settings(str(p)).users_providers == ()

    def test_a_malformed_name_is_a_startup_error(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_USERS_PROVIDERS", raising=False)
        p = tmp_path / "c.yaml"; p.write_text(self.BASE + 'usersProviders: "bad:name"\n')
        with pytest.raises(ConfigError, match="usersProviders"):
            load_settings(str(p))

    def test_the_env_var_wins(self, tmp_path, monkeypatch):
        p = tmp_path / "c.yaml"; p.write_text(self.BASE + 'usersProviders: "ldap-local"\n')
        monkeypatch.setenv("GSD_USERS_PROVIDERS", "corp")
        assert load_settings(str(p)).users_providers == ("corp",)

    def test_the_names_openshift_refuses_are_startup_errors_and_the_ones_it_accepts_pass(self, tmp_path, monkeypatch):
        """`oc explain oauth.spec.identityProviders.name`: a path segment, not '.' or '..', no '/', '%'
        or ':' — and NOTHING stricter. Review of C2: Cursor proposed DNS-1123 (rejected: upper case and
        underscores are legal); a whitespace refusal was then removed when Codex showed spaces are legal."""
        monkeypatch.delenv("GSD_USERS_PROVIDERS", raising=False)
        p = tmp_path / "c.yaml"
        for bad in (".", "..", "a/b", "a%b", "bad:name"):
            p.write_text(self.BASE + f'usersProviders: "{bad}"\n')
            with pytest.raises(ConfigError, match="usersProviders"):
                load_settings(str(p))
        for ok in ("LDAP", "foo_bar", "ldap-local", "corp.example", "a b"):
            p.write_text(self.BASE + f'usersProviders: "{ok}"\n')
            assert load_settings(str(p)).users_providers == (ok,)

    def test_the_list_form_carries_every_legal_name_including_a_comma(self, tmp_path, monkeypatch):
        """Review (Codex): a comma-joined string cannot express a provider literally named `a,b`,
        which OpenShift accepts. The chart renders the list as a YAML flow sequence and the app takes
        the list as it is; a non-string entry is a startup error."""
        monkeypatch.delenv("GSD_USERS_PROVIDERS", raising=False)
        p = tmp_path / "c.yaml"
        p.write_text(self.BASE + 'usersProviders: ["a,b", "a b", "LDAP", " foo_bar ", "a,b"]\n')
        assert load_settings(str(p)).users_providers == ("a,b", "a b", "LDAP", "foo_bar")
        p.write_text(self.BASE + 'usersProviders: []\n')
        assert load_settings(str(p)).users_providers == ()
        p.write_text(self.BASE + 'usersProviders: ["ok", 7]\n')
        with pytest.raises(ConfigError, match="usersProviders"):
            load_settings(str(p))

    def test_an_empty_env_var_means_all_providers_not_an_empty_name(self, tmp_path, monkeypatch):
        p = tmp_path / "c.yaml"; p.write_text(self.BASE + 'usersProviders: "ldap-local"\n')
        monkeypatch.setenv("GSD_USERS_PROVIDERS", "")
        assert load_settings(str(p)).users_providers == ()

    def test_identities_read_parses_and_defaults_off(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_IDENTITIES_READ_ENABLED", raising=False)
        p = tmp_path / "c.yaml"; p.write_text(self.BASE)
        assert load_settings(str(p)).identities_read_enabled is False
        p.write_text(self.BASE + "identitiesReadEnabled: true\n")
        assert load_settings(str(p)).identities_read_enabled is True
        monkeypatch.setenv("GSD_IDENTITIES_READ_ENABLED", "off")
        assert load_settings(str(p)).identities_read_enabled is False


class TestIdleTimeout:
    """Its own keys, never the cookie pair; a bad number falls back to the SHORTER window."""

    def test_off_by_default_with_the_documented_numbers(self, tmp_path, monkeypatch):
        for var in ("GSD_SESSION_IDLE_TIMEOUT_ENABLED", "GSD_SESSION_IDLE_TIMEOUT_MINUTES",
                    "GSD_SESSION_IDLE_TIMEOUT_WARNING_SECONDS"):
            monkeypatch.delenv(var, raising=False)
        s = load_settings(write(tmp_path, BASE))
        assert (s.session_idle_timeout_enabled, s.session_idle_timeout_seconds,
                s.session_idle_timeout_warning_seconds) == (False, 1800, 60)

    def test_the_configmap_keys_are_read_in_minutes_and_served_in_seconds(self, tmp_path):
        cfg = BASE + ("sessionIdleTimeoutEnabled: true\nsessionIdleTimeoutMinutes: 15\n"
                      "sessionIdleTimeoutWarningSeconds: 90\n")
        s = load_settings(write(tmp_path, cfg))
        assert (s.session_idle_timeout_enabled, s.session_idle_timeout_seconds,
                s.session_idle_timeout_warning_seconds) == (True, 900, 90)

    def test_a_warning_longer_than_the_window_falls_back_to_a_shorter_one(self, tmp_path, caplog):
        cfg = BASE + "sessionIdleTimeoutMinutes: 1\nsessionIdleTimeoutWarningSeconds: 120\n"
        s = load_settings(write(tmp_path, cfg))
        assert s.session_idle_timeout_seconds == 60 and s.session_idle_timeout_warning_seconds == 30
        assert "must be at least 5 and shorter" in caplog.text

    def test_zero_minutes_falls_back_to_thirty(self, tmp_path):
        s = load_settings(write(tmp_path, BASE + "sessionIdleTimeoutMinutes: 0\n"))
        assert s.session_idle_timeout_seconds == 1800

    def test_a_cap_of_zero_or_below_is_not_a_cap(self, tmp_path, caplog):
        """Review of C4 (Cursor): a non-positive cap made `seconds >= cap` always true and logged
        "can never fire" for a window that fires fine."""
        from gsd.config import _idle_timeout_setting
        enabled, seconds, warning = _idle_timeout_setting(
            {"sessionIdleTimeoutEnabled": True, "sessionIdleTimeoutMinutes": 30}, -1)
        assert (enabled, seconds, warning) == (True, 1800, 60)
        assert "can never fire" not in caplog.text

    def test_a_fractional_minute_falls_back_rather_than_truncating(self, tmp_path, caplog, monkeypatch):
        """Review of C4 (Cursor): YAML `1.5` truncated to 1 while the same value from the environment
        fell back to 30 — one key, two answers. Both fall back now."""
        monkeypatch.delenv("GSD_SESSION_IDLE_TIMEOUT_MINUTES", raising=False)
        s = load_settings(write(tmp_path, BASE + "sessionIdleTimeoutMinutes: 1.5\n"))
        assert s.session_idle_timeout_seconds == 1800
        assert "not a whole number" in caplog.text
        monkeypatch.setenv("GSD_SESSION_IDLE_TIMEOUT_MINUTES", "1.5")
        assert load_settings(write(tmp_path, BASE)).session_idle_timeout_seconds == 1800

    def test_an_idle_window_past_the_cap_is_inert_and_logged(self, tmp_path, caplog):
        cfg = BASE + ("oauthProxyEnabled: true\nsessionCookieExpire: 10m\n"
                      "sessionIdleTimeoutEnabled: true\nsessionIdleTimeoutMinutes: 30\n")
        load_settings(write(tmp_path, cfg))
        assert "can never fire" in caplog.text
