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

    def test_remote_sar_with_the_lookup_renders_and_only_identity_none_beside_it_is_refused(self, tmp_path):
        """SPEC_D2b: the lookup's Secret is asked like any other remote, so `remote-sar` is accepted beside it."""
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar"}], values=WRITES)
        assert ok, out[-600:]
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar", "identity": "none"}], values=WRITES)
        assert not ok and "clusters[1] (shared-rnd): visibility remote-sar needs identity: same-as-host" in out

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


class TestTheCredentialLifecycleInTheChart:
    """SPEC_S4c §3.8 (#285): the ping's two values reach the ConfigMap; a self-login stanza above one replica is
    refused by name; the Lease rule renders wherever a fleet account is in use, election on or off — and a Lease
    stays the one object the application writes."""

    SL = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "userSelfLogin": True}
    OFF = {"leaderElection": {"enabled": False}}

    @staticmethod
    def _rules(out: str) -> list[dict]:
        return [r for d in yaml.safe_load_all(out) if d and d.get("kind") in ("ClusterRole", "Role")
                and not d["metadata"]["name"].endswith("-secrets-mint") for r in d.get("rules") or []]

    def test_the_ping_values_reach_the_configmap(self, tmp_path):
        for values, expected in (({}, (True, 86400)),
                                 ({"clusterConfig": {"fleetAccount": {"ping": {"enabled": False, "intervalSeconds": 3600}}}},
                                  (False, 3600))):
            ok, out = _render_values(tmp_path, [HOME], select="templates/configmap.yaml", values=values)
            assert ok, out[-600:]
            docs = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "ConfigMap"]
            settings = yaml.safe_load(next(d for d in docs if "clusters.yaml" in d["data"])["data"]["clusters.yaml"])
            assert (settings["fleetPingEnabled"], settings["fleetPingIntervalSeconds"]) == expected

    def test_self_login_above_one_replica_is_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, self.SL], values={"replicaCount": 2, **self.OFF, "reporting": {"enabled": False}})
        assert not ok and "cluster shared-rnd declares userSelfLogin with replicaCount 2" in out, out[-600:]
        ok, out = _render_values(tmp_path, [HOME, self.SL], values=self.OFF)
        assert ok, out[-600:]

    @pytest.mark.parametrize("clusters,values,renders", [
        ([HOME, SL], OFF, True),                                                              # a mode in use, election off
        ([HOME], {**OFF, "clusterConfig": {"fleetAccount": {"username": "svc-gsd"}}}, True),  # the chart names an account
        ([HOME], OFF, False),                                                                 # no account, election off
        ([HOME], {}, True),                                                                   # election on: as before
    ], ids=["mode-in-use-election-off", "username-election-off", "no-account-election-off", "election-on"])
    def test_the_lease_rule_renders_where_a_claim_is_needed_and_stays_the_only_write(self, tmp_path, clusters, values, renders):
        ok, out = _render_values(tmp_path, clusters, values=values)
        assert ok, out[-600:]
        rules = self._rules(out)
        leases = [r for r in rules if "leases" in (r.get("resources") or [])]
        assert bool(leases) is renders and all(sorted(r["verbs"]) == ["create", "get", "update"] for r in leases)
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        assert all(set(r.get("resources") or []) == {"leases"} for r in rules if set(r.get("verbs") or []) & writes)


#: #420 (SPEC_G4): the renders the Lease grant is measured on — the four cases of the credential-lifecycle test above,
#: and the chart's three values files as written and with election off — and whether the grant renders in each.
_SL = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "userSelfLogin": True}
_OFF = {"leaderElection": {"enabled": False}}
LEASE_RENDERS = [
    pytest.param({"clusters": [HOME, _SL], **_OFF}, None, True, id="mode-in-use-election-off"),
    pytest.param({"clusters": [HOME], **_OFF, "clusterConfig": {"fleetAccount": {"username": "svc-gsd"}}}, None, True,
                 id="username-election-off"),
    pytest.param({"clusters": [HOME], **_OFF}, None, False, id="no-account-election-off"),
    pytest.param({"clusters": [HOME]}, None, True, id="election-on"),
    pytest.param({}, "environments/crc.yaml", True, id="crc"),
    pytest.param(_OFF, "environments/crc.yaml", True, id="crc-election-off"),
    pytest.param({}, "environments/example-production.yaml", True, id="env-production"),
    pytest.param(_OFF, "environments/example-production.yaml", False, id="env-production-election-off"),
    pytest.param({}, "charts/group-sync-dashboard/example-production.yaml", True, id="chart-production"),
    pytest.param(_OFF, "charts/group-sync-dashboard/example-production.yaml", True, id="chart-production-election-off"),
]


class TestTheLeaseGrantIsNamespaced:
    """#420 (SPEC_G4): the dashboard's Leases are granted by a Role and RoleBinding in the release namespace,
    `<fullname>-leases`, rendered exactly where the Lease grant always rendered — election on, or a fleet account in
    use — and only with rbac.create. The code reads and writes Leases in its own namespace only (T420-6, in
    tests/test_leader.py and tests/test_fleet_lifecycle.py), so this Role is the whole grant it needs."""

    NS = "gsd-leases"

    @classmethod
    def _docs(cls, tmp_path, values: dict, values_file: str | None) -> list[dict]:
        mine = tmp_path / "values.yaml"
        mine.write_text(yaml.safe_dump(values, sort_keys=False))
        files = ["-f", str(CHART.parents[1] / values_file)] if values_file else []
        done = subprocess.run(["helm", "template", "t", str(CHART), "-n", cls.NS, *files, "-f", str(mine)],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr[-600:]
        return [d for d in yaml.safe_load_all(done.stdout) if d]

    @pytest.mark.parametrize("values,values_file,renders", LEASE_RENDERS)
    def test_the_lease_role_renders_where_the_grant_did_and_nowhere_else(self, tmp_path, values, values_file, renders):
        """T420-2: one Role with exactly get, create, update on leases and no resourceNames, and its RoleBinding to the
        dashboard's ServiceAccount, both in the release namespace — or neither, where no Lease is written."""
        docs = self._docs(tmp_path, values, values_file)
        reader = next(d for d in docs if d["kind"] == "ClusterRoleBinding" and d["metadata"]["name"].endswith("-reader"))
        name = reader["metadata"]["name"].removesuffix("-reader") + "-leases"
        roles = [d for d in docs if d["kind"] == "Role" and any("leases" in (r.get("resources") or []) for r in d.get("rules") or [])]
        bindings = [d for d in docs if d["kind"] == "RoleBinding" and d["metadata"]["name"] == name]
        if not renders:
            assert roles == [] and bindings == [], "a Lease grant where nothing writes a Lease"
            return
        assert [(r["metadata"]["name"], r["metadata"]["namespace"]) for r in roles] == [(name, self.NS)]
        assert roles[0]["rules"] == [{"apiGroups": ["coordination.k8s.io"], "resources": ["leases"],
                                      "verbs": ["get", "create", "update"]}]
        assert len(bindings) == 1 and bindings[0]["metadata"]["namespace"] == self.NS
        assert bindings[0]["roleRef"] == {"apiGroup": "rbac.authorization.k8s.io", "kind": "Role", "name": name}
        assert bindings[0]["subjects"] == reader["subjects"] == [
            {"kind": "ServiceAccount", "name": reader["subjects"][0]["name"], "namespace": self.NS}]

    def test_rbac_create_false_renders_no_lease_grant(self, tmp_path):
        """T420-3: with rbac.create false the estate applies its own RBAC, the Lease Role included (chart README)."""
        docs = self._docs(tmp_path, {"clusters": [HOME], "rbac": {"create": False},
                                     "clusterConfig": {"fleetAccount": {"username": "svc-gsd"}}}, None)
        rbac = [(d["kind"], d["metadata"]["name"]) for d in docs if d["kind"] in ("ClusterRole", "Role", "RoleBinding")]
        assert not [n for n in rbac if n[1].endswith(("-reader", "-leases"))], rbac
