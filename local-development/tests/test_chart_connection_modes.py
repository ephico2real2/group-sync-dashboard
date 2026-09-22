"""S3a (SPEC_S3 §4, #248): the chart's render-time guard refuses every connection-mode stanza the loader
refuses — so a bad stanza fails `helm template`, not the pod after a green upgrade — and a good one
renders into the ConfigMap the loader reads. Pure Helm: CI's chart job runs this without the app."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_dashboard_controller import EAST, HOME, _render_values
from test_chart_strategy import CHART

RND = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "saTokenLookup": True}
#: SPEC_S4b: a saTokenLookup stanza WRITES its Secret, so a green render needs the write grant on.
WRITES = {"clusterConfig": {"secrets": {"writes": {"enabled": True}}}}


class TestTheGuardMirrorsTheLoader:
    def test_a_mode_stanza_renders_and_reaches_the_configmap(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "ldapConnectionBootstrap": "svc-gsd.fleet@corp"}],
                                 select="templates/configmap.yaml", values=WRITES)
        assert ok, out
        docs = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "ConfigMap"]
        clusters = yaml.safe_load(next(d for d in docs if "clusters.yaml" in d["data"])["data"]["clusters.yaml"])["clusters"]
        rnd = next(c for c in clusters if c["name"] == "shared-rnd")
        assert rnd["saTokenLookup"] is True and rnd["ldapConnectionBootstrap"] == "svc-gsd.fleet@corp"
        assert "tokenEnv" not in rnd and "tokenFile" not in rnd

    @pytest.mark.parametrize("stanza,fragment", [
        ({**RND, "userSelfLogin": True}, "clusters[1] (shared-rnd) declares both saTokenLookup and userSelfLogin"),
        ({**RND, "tokenEnv": "T"}, "clusters[1] (shared-rnd) declares saTokenLookup and also tokenEnv/tokenFile"),
        ({**RND, "saTokenLookup": "yes"}, "clusters[1] (shared-rnd): saTokenLookup must be true or false, not \"yes\""),
        ({"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443"}, "clusters[1] (shared-rnd): one of tokenEnv or tokenFile is required"),
        ({**EAST, "name": "shared-rnd", "ldapConnectionBootstrap": "svc"}, "clusters[1] (shared-rnd): ldapConnectionBootstrap without saTokenLookup or userSelfLogin"),
        ({**RND, "ldapConnectionBootstrap": "svc gsd"}, "clusters[1] (shared-rnd): ldapConnectionBootstrap must be a username"),
    ])
    def test_the_refusals_name_the_cluster_and_the_key(self, tmp_path, stanza, fragment):
        ok, out = _render_values(tmp_path, [HOME, stanza])
        assert not ok and fragment in out, out[-600:]
        assert "svc gsd" not in out, "a bootstrap value is never echoed by the render"

    def test_a_mode_on_the_declared_controller_is_refused(self, tmp_path):
        home = {k: v for k, v in HOME.items() if k != "tokenEnv"}
        ok, out = _render_values(tmp_path, [EAST, {**home, "userSelfLogin": True}])
        assert not ok and "clusters[1] (home) is the hosting cluster — declared by dashboardController: true — and declares userSelfLogin" in out

    def test_a_mode_on_the_inferred_host_is_refused(self, tmp_path):
        ok, out = _render_values(tmp_path, [{"name": "only", "apiUrl": "https://api.example:6443", "saTokenLookup": True}])
        assert not ok and "clusters[0] (only) is the hosting cluster — the first enabled entry" in out and "declares saTokenLookup" in out

    def test_a_mode_declared_false_needs_a_credential_like_before(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "saTokenLookup": False}])
        assert not ok and "one of tokenEnv or tokenFile is required" in out

    def test_helm_lint_passes_with_a_mode_stanza_and_a_fleet_account(self, tmp_path):
        values = tmp_path / "v.yaml"
        values.write_text(yaml.safe_dump({"clusters": [HOME, RND],
                                          "clusterConfig": {"fleetAccount": {"username": "svc-gsd-fleet"},
                                                            "secrets": {"writes": {"enabled": True}}}}, sort_keys=False))
        done = subprocess.run(["helm", "lint", str(CHART), "-f", str(values), "--set", "ingress.host=t.example.com"],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stdout + done.stderr


class TestTheLookupIsRefusedAtRenderWithoutWhatItNeeds:
    """SPEC_S4b: a saTokenLookup stanza writes a Secret and discovery reads it back, so the render
    refuses it without the two switches, above one replica, and with a visibility the Secret parser
    would refuse — failing `helm template`, not a pod after a green upgrade. userSelfLogin needs none."""

    @pytest.mark.parametrize("values,fragment", [
        ({}, "cluster shared-rnd declares saTokenLookup but clusterConfig.secrets.writes.enabled is false"),
        ({"clusterConfig": {"secrets": {"enabled": False, "writes": {"enabled": True}}}},
         "cluster shared-rnd declares saTokenLookup but clusterConfig.secrets.enabled is false"),
        # reporting refuses > 1 replica by design (C3) and election must be off there: both set, so the
        # lookup's rule is the one refusal left to fire (the values test_chart_strategy renders at 2 with)
        ({**WRITES, "replicaCount": 2, "leaderElection": {"enabled": False}, "reporting": {"enabled": False}},
         "clusterConfig.secrets.writes.enabled with replicaCount 2"),
    ])
    def test_the_switches_and_the_replica_rule(self, tmp_path, values, fragment):
        ok, out = _render_values(tmp_path, [HOME, RND], values=values)
        assert not ok and fragment in out, out[-600:]

    def test_the_replica_rule_holds_without_a_values_stanza(self, tmp_path):
        """Review of #295, P0-2: a Secret may declare the mode at any time, so the rule is on the
        switch that makes a lookup possible, not on a stanza the render happens to see."""
        ok, out = _render_values(tmp_path, [HOME], values={**WRITES, "replicaCount": 2, "leaderElection": {"enabled": False},
                                                            "reporting": {"enabled": False}})
        assert not ok and "clusterConfig.secrets.writes.enabled with replicaCount 2" in out, out[-600:]
        ok, out = _render_values(tmp_path, [HOME], values={"replicaCount": 2, "leaderElection": {"enabled": False},
                                                            "reporting": {"enabled": False}})
        assert ok, out[-600:]     # writes off: two replicas render as before

    def test_remote_sar_with_the_lookup_is_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar", "identity": "same-as-host"}], values=WRITES)
        assert not ok and "clusters[1] (shared-rnd): visibility remote-sar with saTokenLookup" in out

    def test_self_login_needs_no_write_grant(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "userSelfLogin": True}])
        assert ok, out

    def test_the_pod_learns_the_account_and_the_address(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, RND], select="templates/configmap.yaml",
                                 values={**WRITES, "clusterConfig": {**WRITES["clusterConfig"], "fleetAccount": {
                                     "username": "svc", "passwordSecret": {"namespace": "openshift-config", "name": "ldap-oauth-bind-secret", "key": "bindPassword"}}}})
        assert ok, out
        docs = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "ConfigMap"]
        # the settings and the clusters share one key, `clusters.yaml` (templates/configmap.yaml)
        settings = yaml.safe_load(next(d for d in docs if "clusters.yaml" in d["data"])["data"]["clusters.yaml"])
        assert (settings["fleetAccountUsername"], settings["fleetPasswordSecretNamespace"], settings["fleetPasswordSecretName"],
                settings["fleetPasswordSecretKey"]) == ("svc", "openshift-config", "ldap-oauth-bind-secret", "bindPassword")
        assert (settings["saTokenLookupSourceNamespace"], settings["saTokenLookupSourceServiceAccount"], settings["saTokenLookupTokenSecretName"]) \
            == ("group-sync-operator", "group-sync-dashboard-cluster-poller", "")
        assert settings["replicaCount"] == 1
