"""Chart 0.14.0's rule: every boolean in values.yaml defaults to true unless the switch costs RBAC
beyond a namespaced read, a credential, a second image or a cluster-wide write — or is an
operator's product choice (skipProviderButton). The exceptions are enumerated here, so a new
boolean that lands false has to be added to the list with its reason, and the documents that
state defaults are held to the file.
"""
from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
VALUES = REPO / "charts" / "group-sync-dashboard" / "values.yaml"

KEPT_OFF = {
    "securityContext.allowPrivilegeEscalation": "a hardening posture, not a feature switch",
    "trustedCA.existingConfigMap.enabled": "needs the name of a ConfigMap the operator supplies",
    "ingress.enabled": "exclusive with the Route, which the chart renders by default",
    "authLogLevel.manage": "a cluster-wide write that rolls the OAuth server; the audit log replaces it",
    "authLogLevel.enabled": "same decision as manage",
    "oauthProxy.skipProviderButton": "operator decision 2026-09-05: people log in from the OpenShift screen",
    "monitoring.serviceMonitor.enabled": "operator decision 2026-09-05: the reference cluster runs no Prometheus; needs the Operator CRDs",
    "monitoring.prometheusRule.enabled": "same decision; rendering with both on was verified before the default went back",
}

# Switches the release flipped; the docs below must not describe them as off.
FLIPPED = (
    "podDisruptionBudget.enabled",
    "loginCapture.enabled",
    "oauthProxy.apiTokenAccess.enabled",
    "oauthProxy.requestLogging",
)

# Documents an operator follows. Records (reviews, the changelog's history, superseded designs and
# the spec bodies) are deliberately not held: a record quotes the state it recorded.
CURRENT_DOCS = (
    "README.md",
    "charts/group-sync-dashboard/README.md",
    "charts/group-sync-dashboard/templates/NOTES.txt",
    "docs/api-access.md",
    "docs/LOGIN_CAPTURE_QUICKCHECK.md",
    "environments/README.md",
    "environments/example-production.yaml",
)


def flatten(data, prefix=""):
    out = {}
    for key, value in (data or {}).items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            out.update(flatten(value, path + "."))
        else:
            out[path] = value
    return out


def test_the_only_false_defaults_are_the_stated_exceptions() -> None:
    values = flatten(yaml.safe_load(VALUES.read_text()))
    false_keys = {k for k, v in values.items() if v is False}
    assert false_keys == set(KEPT_OFF), (
        f"unexpected false defaults: {sorted(false_keys - set(KEPT_OFF))}; "
        f"listed but no longer false: {sorted(set(KEPT_OFF) - false_keys)}"
    )
    for key in FLIPPED:
        assert values[key] is True, key


def _line_of(key: str, lines: list[str]) -> int:
    """Index of the line that sets `key` (dotted path) in values.yaml, by indentation, so that
    `authLogLevel.enabled` and `trustedCA.existingConfigMap.enabled` are told apart."""
    stack: list[tuple[int, str]] = []
    for i, raw in enumerate(lines):
        stripped = raw.lstrip(" ")
        if not stripped or stripped.startswith("#") or raw.startswith("---"):
            continue
        indent = len(raw) - len(stripped)
        name = stripped.split(":", 1)[0]
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, name))
        if ".".join(n for _, n in stack) == key:
            return i
    raise AssertionError(f"{key} not found in values.yaml")


def test_every_kept_off_boolean_has_a_reason_comment_above_it() -> None:
    lines = VALUES.read_text().splitlines()
    for key in KEPT_OFF:
        i = _line_of(key, lines)
        assert lines[i].split(":", 1)[1].strip() == "false", (key, lines[i])
        # The reason sits in the comment block immediately above the key or its parent.
        window = "\n".join(lines[max(0, i - 14): i])
        assert "#" in window, (key, window)
        assert any(word in window.lower() for word in ("0.14.0", "stays false", "default", "off")), (key, window)


def test_no_current_doc_tells_the_operator_to_enable_a_default() -> None:
    for rel in CURRENT_DOCS:
        text = (REPO / rel).read_text()
        for key in FLIPPED:
            assert f"--set {key}=true" not in text, (rel, key)
            assert f"| `{key}` | `false` |" not in text, (rel, key)


def test_the_root_readme_rows_state_the_real_defaults() -> None:
    values = flatten(yaml.safe_load(VALUES.read_text()))
    rows = {m[1]: m[2] for m in re.finditer(r"^\| `([^`]+)` \| `([^`]+)` \|", (REPO / "README.md").read_text(), re.M)}
    for key in FLIPPED + tuple(KEPT_OFF):
        if key in rows:
            claimed = rows[key]
            assert claimed == str(values[key]).lower(), (key, claimed, values[key])


def test_the_wide_tier_check_in_the_docs_is_the_one_values_yaml_ships() -> None:
    """Review of chart 0.14.0 (Codex): docs/ACCESS_CONTROL.md and the chart README still named the
    superseded `list groups.user.openshift.io` threshold. The default is security-sensitive, so the
    documents are held to the file."""
    sar = yaml.safe_load(VALUES.read_text())["visibility"]["adminSar"]
    dotted = f"{sar['verb']} {sar['resource']}.{sar['apiGroup']}"
    access = (REPO / "docs" / "ACCESS_CONTROL.md").read_text()
    assert f"| **wide tier** | `visibility.adminSar` | `{dotted}` |" in access
    assert (f"resourceAttributes: {{group: {sar['apiGroup']}, resource: {sar['resource']}, "
            f"verb: {sar['verb']}}}") in access
    chart_readme = (REPO / "charts" / "group-sync-dashboard" / "README.md").read_text()
    assert (f"| `visibility.adminSar.apiGroup` / `.resource` / `.verb` | `{sar['apiGroup']}` / "
            f"`{sar['resource']}` / `{sar['verb']}` |") in chart_readme
