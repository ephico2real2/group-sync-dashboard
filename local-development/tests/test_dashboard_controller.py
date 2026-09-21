"""#249 second pass (review of PR #251): the declared controller must be THE host everywhere
the app asks "which cluster is the host" — load_settings' host-only refusals, the four tier
resolvers build_app constructs, the startup log and the Cluster Configurations payload — not only
in `Settings.host_cluster()`. Measured on the head: with the controller declared second,
`host_cluster()` said `home` while every TierResolver reviewed against `ocp-east`, and `hidden`
on `home` was accepted (the login cluster hidden) while `hidden` on `ocp-east` was refused as
"the hosting cluster"."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import parse_secret
from gsd.config import ClusterConfig, ConfigError, Settings, load_settings
from test_chart_strategy import CHART
from test_visibility import H, _MapResolver, _seed

_TWO = """
clusters:
  - name: ocp-east
    apiUrl: https://api.east.example.com:6443
    tokenEnv: T
{east}
  - name: home
    apiUrl: https://kubernetes.default.svc
    tokenEnv: T
    dashboardController: true
{home}
"""


def _load(tmp_path, *, east: str = "", home: str = ""):
    p = tmp_path / "config.yaml"
    p.write_text(_TWO.format(east=east, home=home))
    return load_settings(p)


class TestLoadSettingsHostChecksFollowTheDeclaredController:
    @pytest.mark.parametrize("policy", ("hidden", "remote-sar"))
    def test_hidden_or_remote_sar_on_a_declared_controller_that_is_not_first_is_refused(self, tmp_path, policy):
        home = f"    visibility: {policy}" + ("\n    identity: same-as-host" if policy == "remote-sar" else "")
        with pytest.raises(ConfigError, match="clusters\\[1\\]: visibility .* is not allowed on the hosting cluster"):
            _load(tmp_path, home=home)

    def test_the_first_entry_is_a_remote_when_another_entry_declares_the_controller(self, tmp_path):
        # `hidden` on the remote is an ordinary choice, and remote-sar with same-as-host is the documented pair.
        s = _load(tmp_path, east="    visibility: hidden")
        assert s.host_cluster().name == "home" and s.cluster_policy("ocp-east") == ("hidden", "none")
        s = _load(tmp_path, east="    visibility: remote-sar\n    identity: same-as-host")
        assert s.cluster_policy("ocp-east") == ("remote-sar", "same-as-host")

    def test_remote_sar_without_same_as_host_is_still_refused_on_a_first_entry_that_is_not_the_host(self, tmp_path):
        with pytest.raises(ConfigError, match="clusters\\[0\\]: visibility remote-sar needs identity: same-as-host"):
            _load(tmp_path, east="    visibility: remote-sar")

    def test_without_the_flag_the_refusals_stay_exactly_positional(self, tmp_path):
        # Behaviour-preservation: no flag → the first enabled entry is the host, as before #249.
        p = tmp_path / "c.yaml"
        p.write_text(_TWO.format(east="    visibility: hidden", home="").replace("    dashboardController: true\n", ""))
        with pytest.raises(ConfigError, match="clusters\\[0\\]: visibility 'hidden' is not allowed on the hosting cluster \\(the first enabled entry"):
            load_settings(p)


class TestBuildAppUsesTheDeclaredController:
    def _settings(self, tmp_path, **kw) -> Settings:
        db = str(tmp_path / "gsd.db"); _seed(db)
        return Settings(
            clusters=[ClusterConfig("ocp-east", "https://api.east.example.com:6443", token_env="X"),
                      ClusterConfig("home", "https://kubernetes.default.svc", token_env="X", dashboard_controller=True)],
            db_path=db, oauth_proxy_enabled=True, **kw)

    def test_every_tier_resolver_reviews_on_the_declared_controller(self, tmp_path):
        settings = self._settings(tmp_path, view_restrictions_enabled=True)
        app = build_app(settings, run_poller=False)
        targets = {name: getattr(app.state, name)._kube.cluster.name
                   for name in ("tier_resolver", "usage_tier_resolver",
                                "clusterconfig_view_resolver", "clusterconfig_manage_resolver")}
        assert targets == {k: "home" for k in targets}, targets
        assert "home" not in app.state.remote_tier_resolvers

    def test_startup_names_the_controller_and_whether_it_was_declared(self, tmp_path, caplog):
        with caplog.at_level(logging.INFO, logger="gsd.api"):
            build_app(self._settings(tmp_path), run_poller=False)
        assert "controller-cluster name=home declared=true" in caplog.text
        caplog.clear()
        db = str(tmp_path / "second.db"); _seed(db)
        undeclared = Settings(clusters=[ClusterConfig("ocp-east", "https://api.east.example.com:6443", token_env="X")],
                              db_path=db, oauth_proxy_enabled=True)
        with caplog.at_level(logging.INFO, logger="gsd.api"):
            build_app(undeclared, run_poller=False)
        assert "controller-cluster name=ocp-east declared=false" in caplog.text
        assert "moves if clusters[] is reordered" in caplog.text

    def test_the_cluster_configurations_payload_marks_the_declared_controller_as_host(self, tmp_path, monkeypatch):
        monkeypatch.setattr("gsd.api.own_namespace", lambda: "ns")
        app = build_app(self._settings(tmp_path), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            body = c.get("/api/clusterconfigs", headers=H("root")).json()
        assert [r["id"] for r in body["clusters"] if r["host"]] == ["home"]


class TestTheRenameIsSaidToRetireHistory:
    def test_the_clusters_stanza_says_a_rename_retires_the_old_row(self):
        """C2 of the review: `name` is the id every observation table keys on, and a renamed
        entry is a NEW cluster — the old row is retired (#96), its history stays under the old
        id, and the Cluster Configurations tab shows it retired. The stanza the operator edits
        must say so beside the name."""
        text = (CHART / "values.yaml").read_text()
        stanza = text[text.index("\nclusters:\n"):text.index("# ArgoCD / GitOps")]
        assert "retire" in stanza and "history" in stanza, "the rename's cost is not stated where the name is set"


class TestTheParserRefusesTheFlagAtBothLevels:
    @staticmethod
    def _secret(data: dict, config: dict | None) -> dict:
        import base64, json
        d = {"name": "prod-east", "server": "https://api.east.example.com:6443", **data}
        if config is not None:
            d["config"] = json.dumps(config)
        return {"metadata": {"name": "gsd-cluster-prod-east"},
                "data": {k: base64.b64encode(v.encode()).decode() for k, v in d.items()}}

    def test_top_level_and_nested_are_both_an_unsupported_config_key_naming_the_key(self):
        top = parse_secret(self._secret({"dashboardController": "true"}, {"bearerToken": "t"}), host_name="dashboard")
        assert top.code == "unsupported-config-key" and top.detail.startswith("data.dashboardController:")
        nested = parse_secret(self._secret({}, {"bearerToken": "t", "dashboardController": True}), host_name="dashboard")
        assert nested.code == "unsupported-config-key" and nested.detail.startswith("dashboardController:")
        assert not hasattr(parse_secret(self._secret({}, {"bearerToken": "t"}), host_name="dashboard"), "code")
