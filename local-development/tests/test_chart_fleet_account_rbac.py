"""The fleet account's password grant (SPEC_S3 §3.1, #248): the dashboard may RETRIEVE one Secret —
the fleet account's password — from this release's namespace or another, such as `openshift-config`
where a cluster's LDAP bind password already sits.

The scope is the whole point. `get` on a single Secret by `resourceNames`, never `list` (which
`resourceNames` cannot restrict, so it would expose every Secret in that namespace) and never a
ClusterRole. Pure Helm: CI's chart job runs this without the app.
"""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_strategy import CHART

HOME = {"name": "dashboard", "dashboardController": True, "apiUrl": "https://kubernetes.default.svc",
        "tokenFile": "/var/run/secrets/kubernetes.io/serviceaccount/token",
        "caBundleFile": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"}
MODE = {"name": "shared-rnd", "apiUrl": "https://api.shared-rnd.example.com:6443", "saTokenLookup": True}
NS = "gsd-test"


def _render(tmp_path, values: dict, clusters=None):
    f = tmp_path / "v.yaml"
    f.write_text(yaml.safe_dump({**values, "clusters": clusters or [HOME]}), encoding="utf-8")
    r = subprocess.run(["helm", "template", "t", CHART, "-n", NS, "-f", str(f)],
                       capture_output=True, text=True, timeout=180, cwd="..")
    return r.returncode == 0, (r.stdout if r.returncode == 0 else r.stderr)


def _objects(out):
    return [d for d in yaml.safe_load_all(out)
            if d and (d.get("metadata", {}).get("labels", {}) or {}).get("app.kubernetes.io/component") == "fleet-account"]


def _fleet(username="svc.gsd.fleet", **ps):
    return {"clusterConfig": {"fleetAccount": {"username": username, "passwordSecret": ps}}} if ps or username else {}


class TestItRendersOnlyWhenAFleetAccountIsInUse:
    def test_a_default_install_grants_nothing(self, tmp_path):
        ok, out = _render(tmp_path, {})
        assert ok, out
        assert _objects(out) == [], "a release that declares no connection mode must not grant Secret access"

    def test_a_mode_stanza_alone_is_enough(self, tmp_path):
        # the username may live on the stanza (ldapConnectionBootstrap); the PASSWORD is still this one
        # SPEC_S4b: a saTokenLookup stanza also needs the write grant, or the render refuses it
        ok, out = _render(tmp_path, {"clusterConfig": {"secrets": {"writes": {"enabled": True}}}},
                          clusters=[HOME, {**MODE, "ldapConnectionBootstrap": "svc.gsd.fleet"}])
        assert ok, out
        assert len(_objects(out)) == 2, "a stanza declaring a mode needs the password grant"

    def test_a_chart_level_username_is_enough(self, tmp_path):
        ok, out = _render(tmp_path, _fleet())
        assert ok, out
        assert len(_objects(out)) == 2


class TestTheScope:
    def test_get_on_one_named_secret_and_nothing_else(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(namespace="openshift-config", name="ldap-oauth-bind-secret",
                                           key="bindPassword"))
        assert ok, out
        role = next(o for o in _objects(out) if o["kind"] == "Role")
        assert len(role["rules"]) == 1, role["rules"]
        rule = role["rules"][0]
        assert rule["resources"] == ["secrets"] and rule["apiGroups"] == [""]
        assert rule["resourceNames"] == ["ldap-oauth-bind-secret"], "the grant must name the one Secret"
        assert rule["verbs"] == ["get"], (
            "get only: resourceNames cannot restrict list/watch, so either would expose every Secret "
            "in that namespace")

    def test_it_is_never_a_clusterrole(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(namespace="openshift-config", name="s", key="k"))
        assert ok, out
        assert {o["kind"] for o in _objects(out)} == {"Role", "RoleBinding"}, (
            "secrets cluster-wide would hand the dashboard every credential on the cluster")

    def test_the_subject_is_this_releases_service_account(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(namespace="openshift-config", name="s", key="k"))
        assert ok, out
        rb = next(o for o in _objects(out) if o["kind"] == "RoleBinding")
        assert rb["metadata"]["namespace"] == "openshift-config", "the grant lives where the Secret lives"
        assert rb["subjects"][0]["namespace"] == NS, "the subject lives where the dashboard runs"


class TestWhereTheGrantLands:
    def test_empty_namespace_means_this_release(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(name="gsd-fleet-account", key="password"))
        assert ok, out
        assert {o["metadata"]["namespace"] for o in _objects(out)} == {NS}

    def test_a_named_namespace_is_honoured(self, tmp_path):
        # the migration this field exists for: today openshift-config, once a replicator copies the
        # Secret locally, clearing `namespace` re-renders against the copy with no chart change
        ok, out = _render(tmp_path, _fleet(namespace="openshift-config", name="s", key="k"))
        assert ok, out
        assert {o["metadata"]["namespace"] for o in _objects(out)} == {"openshift-config"}


class TestTheOptOutActuallyOptsOut:
    """`create` is read as a WORD. `$rbac.create | default true` returns TRUE for an explicit false —
    Helm's `default` treats false as empty — which is an opt-out that silently does not opt out, the
    same trap `enabled: "false"` fell into on a cluster stanza."""

    @pytest.mark.parametrize("value", [False, "false"])
    def test_false_suppresses_the_grant(self, tmp_path, value):
        ok, out = _render(tmp_path, _fleet(name="s", key="k", rbac={"create": value}))
        assert ok, out
        assert _objects(out) == [], f"rbac.create={value!r} did not suppress the grant"

    @pytest.mark.parametrize("value", [True, "true"])
    def test_true_renders_it(self, tmp_path, value):
        ok, out = _render(tmp_path, _fleet(name="s", key="k", rbac={"create": value}))
        assert ok, out
        assert len(_objects(out)) == 2

    def test_a_word_that_is_neither_is_refused_by_name(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(name="s", key="k", rbac={"create": "yes"}))
        assert not ok and "must be true or false" in out, out


class TestTheRefusals:
    def test_a_mode_without_a_secret_name_is_refused_at_render(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(name="", key="password"))
        assert not ok, "a mode in use with no Secret named must fail helm template"
        assert "passwordSecret.name is empty" in out, out

    def test_a_missing_key_is_refused_and_names_the_secret(self, tmp_path):
        ok, out = _render(tmp_path, _fleet(name="ldap-oauth-bind-secret", key=""))
        assert not ok, out
        assert "key is empty" in out and "ldap-oauth-bind-secret" in out, out
