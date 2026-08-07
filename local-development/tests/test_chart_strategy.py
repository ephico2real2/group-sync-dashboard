"""The chart must not render a manifest that puts two processes on one SQLite file.

Codex found the hole these tests close: `replicaCount=1` with an explicit
`strategy=RollingUpdate` rendered perfectly happily. The existing guard only rejected
RollingUpdate against ReadWriteOncePod — the mode where the scheduler refuses the second
pod anyway — while the DEFAULT ReadWriteMany, which mounts twice without complaint, went
straight through. During the rollout the outgoing and incoming pod both open
/data/gsd.db, and WAL corrupts rather than errors when two hosts share it.

These shell out to `helm template` because the guard IS Helm templating; asserting on
rendered output is the only thing that tests what actually ships.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(**values):
    """Render the chart. Returns (ok, combined output)."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


class TestSingleReplicaRollingUpdate:
    def test_the_case_codex_found_is_now_refused(self):
        """One replica, persistence on, explicit RollingUpdate, default RWX."""
        ok, out = render(replicaCount=1, strategy="RollingUpdate")
        assert not ok, "renders a rollout that puts two pods on one SQLite file"
        assert "two processes on one SQLite file" in out

    def test_refused_for_every_access_mode_not_just_RWOP(self):
        """The original guard keyed on ReadWriteOncePod, which was the SAFE mode here —
        the scheduler refuses the second pod. The permissive modes were the risk."""
        for mode in ("ReadWriteMany", "ReadWriteOnce", "ReadWriteOncePod"):
            ok, _ = render(replicaCount=1, strategy="RollingUpdate",
                           persistence__accessMode=mode)
            assert not ok, f"accessMode={mode} still renders a shared-file rollout"


class TestStillRenders:
    """The guard must not be so broad that it breaks legitimate configurations."""

    def test_defaults(self):
        ok, out = render()
        assert ok, out
        assert "type: Recreate" in out

    def test_explicit_recreate_at_one_replica(self):
        ok, out = render(replicaCount=1, strategy="Recreate")
        assert ok, out

    def test_rollingupdate_above_one_replica_is_correct_and_allowed(self):
        """Each pod owns /data/$POD_NAME/gsd.db up there, so overlap is harmless — and
        Recreate at 3 replicas would take the whole deployment down on every upgrade,
        removing the only reason to scale."""
        ok, out = render(replicaCount=3, leaderElection__enabled=False,
                         strategy="RollingUpdate")
        assert ok, out
        assert "value: /data/$(POD_NAME)/gsd.db" in out

    def test_rollingupdate_at_one_replica_without_persistence(self):
        """No PVC means no shared file: each pod gets its own emptyDir, so an overlapping
        rollout cannot collide. Ephemeral, but not corrupting."""
        ok, out = render(replicaCount=1, strategy="RollingUpdate",
                         persistence__enabled=False)
        assert ok, out

    def test_derived_strategy_above_one_replica_is_rollingupdate(self):
        ok, out = render(replicaCount=2, leaderElection__enabled=False)
        assert ok, out
        assert "type: RollingUpdate" in out


class TestNoPatchVerbAtAnyAuditMode:
    """`docs/unmanaged-audit-design.md` I1 asserted this and said no test enforced it.

    The chart used to grant `patch` on rolebindings/clusterrolebindings when
    `config.unmanagedAudit.mode` was `annotate`, so the dashboard could label its own
    findings. A live cluster measured 0 of 4 labels landing and the API server demanding 175
    additional rule sets to place one, so the mode and the grant were both removed. What
    stops them coming back is this test.

    It PARSES the rendered YAML rather than grepping it. `rbac.yaml` deliberately keeps the
    history of the removed grant in its comments, and Helm emits template comments verbatim —
    three lines of rendered output contain the word `patch` today. A text search would either
    fail on the comments or be written loosely enough to miss a real regression.
    """

    # `annotate` and `bogus` are not valid values; the app downgrades both to `log`. They are
    # here because the RBAC must not depend on the value being valid — a typo in a values file
    # must never be the thing standing between a reader and a write grant.
    MODES = ("off", "log", "annotate", "bogus", "")

    def _rules(self, mode):
        import yaml
        ok, out = render(config__unmanagedAudit__mode=mode)
        assert ok, f"mode={mode!r} failed to render:\n{out}"
        rules = []
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") in ("ClusterRole", "Role"):
                for rule in doc.get("rules") or []:
                    rules.append((doc["metadata"]["name"], rule))
        assert rules, f"mode={mode!r} rendered no Role/ClusterRole rules at all"
        return rules

    @pytest.mark.parametrize("mode", MODES)
    def test_no_write_verb_on_any_rbac_object(self, mode):
        """The specific escalation: write access to the objects that grant access."""
        rbac_resources = {"rolebindings", "clusterrolebindings", "roles", "clusterroles"}
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        for name, rule in self._rules(mode):
            resources = set(rule.get("resources") or [])
            if resources & rbac_resources:
                offending = set(rule.get("verbs") or []) & writes
                assert not offending, (
                    f"mode={mode!r}: ClusterRole {name} grants {sorted(offending)} on "
                    f"{sorted(resources & rbac_resources)} — a reader of RBAC must never be "
                    f"able to edit RBAC"
                )

    @pytest.mark.parametrize("mode", MODES)
    def test_the_only_write_in_the_role_is_the_dashboards_own_lease(self, mode):
        """Guards the claim in the other direction.

        Three documents said the dashboard "writes nothing to any cluster" while the role
        granted create/update on leases. Pinning the Lease as the one permitted write keeps
        both the grant and the sentences describing it honest.
        """
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        for name, rule in self._rules(mode):
            offending = set(rule.get("verbs") or []) & writes
            if offending:
                assert set(rule.get("resources") or []) == {"leases"}, (
                    f"mode={mode!r}: ClusterRole {name} grants {sorted(offending)} on "
                    f"{rule.get('resources')} — the leader-election Lease is the only object "
                    f"this application may write. If that changed deliberately, update "
                    f"rbac.yaml's header, values.yaml, the chart README and "
                    f"docs/reference-architecture.md in the same commit."
                )


class TestTheUsersGrantIsReadOnlyAndOptional:
    """The `users` grant exists for one field, `fullName`, and must stay the smallest thing that
    buys it.

    A User object carries identities and group membership as well as a display name, and the read
    is cluster-wide — every account on the cluster, not just group members. So `get`/`list` and
    nothing else, and it has to remain switchable off: an operator who will not grant a read over
    every identity on the cluster should lose display names and keep the dashboard.

    NOTE ON PLACEMENT: like the class below, this lives here because `.github/workflows/ci.yml`
    points the `chart` job at THIS FILE by name. A chart-rendering test in any other module is not
    run by that job.
    """

    def _users_rules(self, out):
        import yaml
        found = []
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") in ("ClusterRole", "Role"):
                for rule in doc.get("rules") or []:
                    if "users" in (rule.get("resources") or []):
                        found.append(rule)
        return found

    def test_granted_by_default_and_read_only(self):
        ok, out = render()
        assert ok, out
        rules = self._users_rules(out)
        assert len(rules) == 1, f"expected exactly one users rule, got {len(rules)}"
        rule = rules[0]
        assert rule["apiGroups"] == ["user.openshift.io"]
        assert sorted(rule["verbs"]) == ["get", "list"], (
            f"the users grant must be read-only and must not add watch: {rule['verbs']}. "
            f"If that changed deliberately, update rbac.yaml's header, values.yaml, the chart "
            f"README and docs/reference-architecture.md in the same commit."
        )

    def test_declining_the_grant_drops_the_rule_and_keeps_the_rest(self):
        """rbac.users=false must cost display names only — the group data must survive."""
        ok, out = render(rbac__users="false")
        assert ok, out
        assert self._users_rules(out) == [], "rbac.users=false still grants users"
        import yaml
        groups_granted = any(
            "groups" in (rule.get("resources") or [])
            for doc in yaml.safe_load_all(out)
            if doc and doc.get("kind") == "ClusterRole"
            for rule in doc.get("rules") or []
        )
        assert groups_granted, "declining the users grant must not disturb the groups grant"

    def test_users_is_never_granted_when_rbac_is_off_entirely(self):
        ok, out = render(rbac__create="false")
        assert ok, out
        assert self._users_rules(out) == []


class TestTheProxyTrustsTheSameCAsTheApp:
    """The oauth-proxy needs the corporate CA too, and for a while only the app got it.

    MEASURED on a corporate cluster whose *.apps wildcard is signed by an internal CA. Login
    returned `500 Internal Error` with a healthy pod, a valid Route and correct RBAC:

        provider.go:631   Performing OAuth discovery against https://172.31.0.1/...
        provider.go:671   200 GET https://172.31.0.1/.well-known/oauth-authorization-server
        oauthproxy.go:661 error redeeming code: Post
            "https://oauth-openshift.apps.ocp4.company.net/oauth/token":
            tls: failed to verify certificate: x509: certificate signed by unknown authority

    Discovery SUCCEEDS and redemption FAILS, and that asymmetry is the whole bug. Discovery
    goes to the in-cluster API address, which the ServiceAccount CA covers. Discovery then
    returns the PUBLIC issuer, so the code exchange goes to the ingress-served OAuth route,
    signed by a CA the ServiceAccount bundle knows nothing about.

    The chart already had the bundles. They reached `GSD_TRUSTED_CA_FILE` and nothing else, so
    the dashboard could poll a corporate-signed cluster while nobody could log in to read the
    result — the failure was in the half nobody had wired up.

    NOTE ON PLACEMENT: this lives here because `.github/workflows/ci.yml` points the `chart`
    job at THIS FILE by name. A chart-rendering test in any other module is not run by that
    job, and the `tests` job skips these for want of a helm binary.
    """

    CA_ARG = "-openshift-ca="
    SA_CA = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"

    def _proxy(self, **values):
        import yaml
        ok, out = render(**values)
        assert ok, f"failed to render with {values}:\n{out}"
        for doc in yaml.safe_load_all(out):
            if doc and doc.get("kind") == "Deployment":
                spec = doc["spec"]["template"]["spec"]
                proxy = next((c for c in spec["containers"] if c["name"] == "oauth-proxy"), None)
                assert proxy, "the oauth-proxy container did not render"
                return proxy, spec
        raise AssertionError("no Deployment in the rendered output")

    def test_the_service_account_ca_is_still_passed_explicitly(self):
        """Passing any -openshift-ca REPLACES the flag's default, so this cannot be dropped.

        Its own help: "paths to CA roots for the OpenShift API (may be given multiple times,
        defaults to /var/run/secrets/kubernetes.io/serviceaccount/ca.crt)". Losing it breaks
        OAuth DISCOVERY against the in-cluster API address — the half that currently works.
        """
        proxy, _ = self._proxy()
        cas = [a for a in proxy["args"] if a.startswith(self.CA_ARG)]
        assert f"{self.CA_ARG}{self.SA_CA}" in cas, (
            f"the ServiceAccount CA is no longer passed; got {cas}"
        )

    def test_an_enabled_bundle_reaches_the_proxy_and_not_only_the_app(self):
        """The regression itself: bundles configured, app trusts them, proxy does not."""
        for values, expect in (
            ({}, "injected"),                                                  # default
            ({"trustedCA__existingConfigMap__enabled": "true"}, "enterprise"),
        ):
            proxy, _ = self._proxy(**values)
            cas = [a for a in proxy["args"] if a.startswith(self.CA_ARG)]
            assert any(expect in a for a in cas), (
                f"with {values or 'defaults'} the proxy gets {cas} — the {expect} bundle is "
                f"mounted for the dashboard but never handed to the proxy, so login fails on "
                f"any cluster whose OAuth route is signed by that CA"
            )

    def test_every_ca_path_the_proxy_is_given_is_actually_mounted(self):
        """A path the proxy cannot read is worse than no flag: it fails to start.

        Checks the pairing rather than the two halves separately, because they are edited in
        different parts of the template and drift apart silently.
        """
        for values in ({},
                       {"trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false",
                        "trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false"}):
            proxy, _ = self._proxy(**values)
            mounts = [m["mountPath"].rstrip("/") for m in proxy.get("volumeMounts", [])]
            for arg in proxy["args"]:
                if not arg.startswith(self.CA_ARG):
                    continue
                path = arg[len(self.CA_ARG):]
                if path == self.SA_CA:
                    continue          # projected by the kubelet, not by a chart volume
                assert any(path.startswith(m + "/") for m in mounts), (
                    f"with {values or 'defaults'} the proxy is told to read {path} but only "
                    f"mounts {mounts} — the container would fail to start"
                )

    def test_no_volume_mount_names_a_volume_that_does_not_exist(self):
        """Guards the other direction: a mount with no matching volume makes the pod unschedulable.

        Applies to BOTH containers, since the bundles are mounted twice now.
        """
        for values in ({},
                       {"trustedCA__existingConfigMap__enabled": "true"},
                       {"trustedCA__injected__enabled": "false"},
                       {"trustedCA__injected__enabled": "false",
                        "trustedCA__existingConfigMap__enabled": "false"}):
            _, spec = self._proxy(**values)
            volumes = {v["name"] for v in spec.get("volumes", [])}
            for container in spec["containers"]:
                for mount in container.get("volumeMounts", []):
                    assert mount["name"] in volumes, (
                        f"with {values or 'defaults'} container {container['name']} mounts "
                        f"{mount['name']!r}, which is not in {sorted(volumes)}"
                    )
