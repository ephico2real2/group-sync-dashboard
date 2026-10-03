"""#255 at render: `platformUsers` reaches the settings file the way `platformNamespaces` does, the render refuses
what the loader refuses, and either list may come from an existing ConfigMap — mounted as a file, never beside an
inline list, with no new permission. Before #255 the chart had no such key: `helm template --set
'platformUsers.additionalNames={ocp-oauth-bind-serviceid}'` exited 0 with the value nowhere in the render, and
`platformNamespaces.existingConfigMap` was refused as an unknown key."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_strategy import CHART

REPO = CHART.parents[1]


def _render(tmp_path, values: dict | None = None, *files) -> tuple[bool, str]:
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for f in files:
        args += ["-f", str(f)]
    if values is not None:
        path = tmp_path / f"v-{abs(hash(repr(values))) % 10**8}.yaml"
        path.write_text(yaml.safe_dump(values, sort_keys=False))
        args += ["-f", str(path)]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(out: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(out) if d]


def _settings(out: str) -> dict:
    """The rendered settings file (the ConfigMap's clusters.yaml), parsed."""
    cm = next(d for d in _docs(out) if d["kind"] == "ConfigMap" and d["metadata"]["name"].endswith("-config"))
    return yaml.safe_load(cm["data"]["clusters.yaml"])


def _dashboard(out: str) -> dict:
    deploy = next(d for d in _docs(out) if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")
    return deploy["spec"]["template"]["spec"]


@pytest.mark.parametrize("stanza, fragment", [
    ({"additionalName": ["x"]}, "platformUsers.additionalName is not a key this chart defines"),
    ({"suffixes": ["-bot"]}, "platformUsers.suffixes is not a key this chart defines"),
    ({"additionalNames": ["svc-*"]}, 'platformUsers.additionalNames: "svc-*" contains * — matching is literal, not a glob'),
    ({"additionalNames": "x"}, "platformUsers.additionalNames must be a list, got string"),
    ({"names": [3]}, "platformUsers.names: every entry must be a string"),
    ({"existingConfigMap": {"enabld": True}}, "platformUsers.existingConfigMap.enabld is not a key this chart defines"),
    ({"existingConfigMap": {"enabled": "false", "name": "e"}}, "platformUsers.existingConfigMap.enabled must be true or false, got string"),
])
def test_t255_5_the_render_refuses_what_the_loader_refuses(tmp_path, stanza, fragment):
    ok, out = _render(tmp_path, {"platformUsers": stanza})
    assert not ok and fragment in out, out[-600:]


def test_t255_6_the_stanza_reaches_the_settings_file(tmp_path):
    ok, out = _render(tmp_path, {"platformUsers": {"additionalNames": ["ocp-oauth-bind-serviceid"]}})
    assert ok, out[-600:]
    assert _settings(out)["platformUsers"] == {"additionalNames": ["ocp-oauth-bind-serviceid"]}


def test_t255_6_an_absent_stanza_renders_no_key(tmp_path):
    ok, out = _render(tmp_path)
    assert ok, out[-600:]
    settings = _settings(out)
    assert not {"platformUsers", "platformUsersConfigMap", "platformNamespacesConfigMap"} & set(settings), settings


def test_an_empty_replacing_list_is_rendered_so_it_replaces(tmp_path):
    """`names: []` means "none of the shipped names". The namespace render dropped every empty list, so before
    #255 `platformNamespaces.names: []` rendered nothing and kept the five names silently."""
    ok, out = _render(tmp_path, {"platformUsers": {"names": []}, "platformNamespaces": {"names": []}})
    assert ok, out[-600:]
    settings = _settings(out)
    assert settings["platformUsers"] == {"names": []} and settings["platformNamespaces"] == {"names": []}
    # ... and the loader reads what was rendered as "none": the behaviour change the CHANGELOG names.
    from gsd.config import _platform_namespaces_setting, _platform_users_setting
    namespaces, users = _platform_namespaces_setting(settings), _platform_users_setting(settings)
    assert not namespaces.matches("default") and not namespaces.matches("openshift")
    assert namespaces.matches("openshift-monitoring"), "the prefix axis is untouched"
    assert not users.matches("kubeadmin") and users.matches("system:admin")


@pytest.mark.parametrize("stanza, inline", [("platformUsers", "additionalNames"),
                                            ("platformNamespaces", "additionalSuffixes")])
def test_t255_8_existing_configmap_beside_an_inline_list_fails_the_render(tmp_path, stanza, inline):
    ok, out = _render(tmp_path, {stanza: {inline: ["x"], "existingConfigMap": {"enabled": True, "name": "estate-platform"}}})
    assert not ok, out[-600:]
    assert f"{stanza}.existingConfigMap and {stanza}.{inline} are both set" in out, out[-600:]


@pytest.mark.parametrize("stanza", ["platformUsers", "platformNamespaces"])
def test_t255_8_a_replacing_key_set_empty_also_counts_as_inline(tmp_path, stanza):
    ok, out = _render(tmp_path, {stanza: {"names": [], "existingConfigMap": {"enabled": True, "name": "estate-platform"}}})
    assert not ok and f"{stanza}.existingConfigMap and {stanza}.names are both set" in out, out[-600:]


@pytest.mark.parametrize("cm, fragment", [
    ({"enabled": True}, "existingConfigMap.name must name a ConfigMap"),
    ({"enabled": True, "name": "e", "key": "a/b"}, "existingConfigMap.key must be a ConfigMap key"),
])
def test_an_unusable_reference_fails_the_render(tmp_path, cm, fragment):
    ok, out = _render(tmp_path, {"platformUsers": {"existingConfigMap": cm}})
    assert not ok and fragment in out, out[-600:]


def test_t255_9_existing_configmap_is_mounted_as_a_file_and_named_in_the_settings(tmp_path):
    values = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "key": "users.yaml"}},
              "platformNamespaces": {"existingConfigMap": {"enabled": True, "name": "estate-platform",
                                                           "key": "namespaces.yaml"}}}
    ok, out = _render(tmp_path, values)
    assert ok, out[-600:]
    settings = _settings(out)
    assert settings["platformUsersConfigMap"] == {"name": "estate-platform", "key": "users.yaml",
                                                  "path": "/etc/gsd/platform-users/users.yaml", "revision": ""}
    assert settings["platformNamespacesConfigMap"]["path"] == "/etc/gsd/platform-namespaces/namespaces.yaml"
    assert "platformUsers" not in settings and "platformNamespaces" not in settings
    pod = _dashboard(out)
    volumes = {v["name"]: v for v in pod["volumes"]}
    for name in ("platform-users", "platform-namespaces"):
        assert volumes[name]["configMap"] == {"name": "estate-platform"}, "the whole ConfigMap, and not optional"
    mounts = {m["name"]: m for c in pod["containers"] if c["name"] == "dashboard" for m in c["volumeMounts"]}
    assert mounts["platform-users"] == {"name": "platform-users", "mountPath": "/etc/gsd/platform-users", "readOnly": True}
    assert "subPath" not in mounts["platform-namespaces"], "a subPath mount never sees a ConfigMap update"
    proxy = [m["name"] for c in pod["containers"] if c["name"] != "dashboard" for m in c.get("volumeMounts", [])]
    assert "platform-users" not in proxy and "platform-namespaces" not in proxy


def test_changing_the_revision_rolls_the_pod_and_nothing_else_does_for_an_external_edit(tmp_path):
    """The chart cannot see the ConfigMap's content, so an edit to it alone changes no rendered byte; the
    `revision` value is the release's way to say "re-read it" (checksum/config moves, the pod rolls)."""
    base = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform"}}}
    bumped = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "revision": "2"}}}
    zero = {"platformUsers": {"existingConfigMap": {"enabled": True, "name": "estate-platform", "revision": 0}}}
    checksums = []
    for values in (base, base, bumped, zero):
        ok, out = _render(tmp_path, values)
        assert ok, out[-600:]
        deploy = next(d for d in _docs(out) if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")
        checksums.append(deploy["spec"]["template"]["metadata"]["annotations"]["checksum/config"])
    assert checksums[0] == checksums[1] != checksums[2]
    assert checksums[3] not in (checksums[0], checksums[2]), "`revision: 0` is a revision like any other, not unset"


@pytest.mark.parametrize("values_file", ["environments/crc.yaml", "environments/example-production.yaml",
                                         "charts/group-sync-dashboard/example-production.yaml", None])
def test_t255_12_existing_values_render_the_namespace_list_as_before_and_no_user_key(tmp_path, values_file):
    """The rendered settings carry no new key for a values file that sets none, and `platformNamespaces` is the
    lab's measured line (the live ConfigMap on CRC, 2026-10-01) or absent."""
    files = [REPO / values_file] if values_file else []
    ok, out = _render(tmp_path, None, *files)
    assert ok, out[-600:]
    settings = _settings(out)
    assert not {"platformUsers", "platformUsersConfigMap", "platformNamespacesConfigMap"} & set(settings)
    if values_file == "environments/crc.yaml":
        assert settings["platformNamespaces"] == {"additionalNames": ["kyverno", "group-sync-dashboard"],
                                                  "additionalSuffixes": ["-operator", "-manager", "-provisioner"]}


def test_t255_14_no_rendered_permission_moves_with_either_configmap(tmp_path):
    """A ConfigMap mounted as a volume is read by the kubelet, not by the dashboard's ServiceAccount: every Role,
    ClusterRole and binding renders identically with both lists inline or in ConfigMaps."""
    rbac_kinds = {"Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding"}

    def rbac(values):
        ok, out = _render(tmp_path, values)
        assert ok, out[-600:]
        objs = [d for d in _docs(out) if d["kind"] in rbac_kinds]
        for d in objs:
            d["metadata"].get("labels", {}).pop("helm.sh/chart", None)
        return sorted(yaml.safe_dump(d, sort_keys=True) for d in objs)

    inline = rbac({"platformUsers": {"additionalNames": ["x"]}})
    mounted = rbac({"platformUsers": {"existingConfigMap": {"enabled": True, "name": "e"}},
                    "platformNamespaces": {"existingConfigMap": {"enabled": True, "name": "e"}}})
    assert inline and inline == mounted
