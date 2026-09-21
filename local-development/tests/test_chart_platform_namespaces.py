"""#259 (Codex C6): the chart rendered `platformNamespaces` straight into the ConfigMap without
looking at it, so a typo'd key and a numeric entry both produced a green `helm upgrade` and a pod
that refused them on its next start — the failure class this chart has shipped three of (#251).
The render now refuses what the loader refuses."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_strategy import CHART


def _render(tmp_path, stanza):
    values = tmp_path / "v.yaml"
    values.write_text(yaml.safe_dump({"platformNamespaces": stanza}, sort_keys=False))
    done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values),
                           "--set", "ingress.host=t.example.com"], capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


@pytest.mark.parametrize("stanza, fragment", [
    ({"additionalSufixes": ["-op"]}, "additionalSufixes is not a key this chart defines"),
    ({"prefixes": [1]}, "every entry must be a string"),
    ({"additionalNames": ["team-*"]}, "matching is literal, not a glob"),
    ({"additionalSuffixes": "-op"}, "must be a list"),
])
def test_the_render_refuses_what_the_loader_refuses(tmp_path, stanza, fragment):
    ok, out = _render(tmp_path, stanza)
    assert not ok and fragment in out, out[-500:]


def test_a_valid_stanza_still_renders(tmp_path):
    ok, out = _render(tmp_path, {"additionalSuffixes": ["-operator"], "additionalNames": ["kyverno"]})
    assert ok, out
    assert '"additionalSuffixes":["-operator"]' in out and '"additionalNames":["kyverno"]' in out


def test_an_absent_stanza_renders_no_key_at_all(tmp_path):
    values = tmp_path / "none.yaml"
    values.write_text("{}\n")
    done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values),
                           "--set", "ingress.host=t.example.com"], capture_output=True, text=True)
    assert done.returncode == 0 and "platformNamespaces:" not in done.stdout
