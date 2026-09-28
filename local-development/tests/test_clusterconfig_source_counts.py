"""Exercise the page's JavaScript counts without launching a browser (#404)."""

import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest


@pytest.fixture
def render():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the page's JavaScript")
    html = (Path(__file__).parents[1] / "gsd/static/index.html").read_text()
    functions = "\n".join(
        re.search(rf"^function {name}\(.*?^}}", html, re.M | re.S).group()
        for name in ("esc", "ccSourceKind", "ccSourceChip", "clusterConfigPage")
    )

    def run(clusters):
        script = functions + """
const data = {clusterconfigs: {clusters: JSON.parse(process.argv[1]), secrets: {}}};
// Only unrelated page sections are stubbed; counts and chips run the production functions.
const ccClusterCard = () => '', ccFleetRows = () => '', ccAddForm = () => '', ccFinding = () => '';
console.log(JSON.stringify({
  kinds: data.clusterconfigs.clusters.map(ccSourceKind),
  chips: data.clusterconfigs.clusters.map(ccSourceChip),
  page: clusterConfigPage(),
}));
"""
        result = subprocess.run([node, "-e", script, json.dumps(clusters)],
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    return run


GENERATED = {"source": "secret:gsd-cluster-east", "onboarding_configmap": "fleet"}


def test_generated_cluster_counts_under_its_configmap(render):
    result = render([GENERATED])
    assert 'ConfigMap 1</span>' in result["page"]
    assert 'Secret 0</span>' in result["page"]
    assert result["kinds"] == ["configmap"]


def test_generated_chip_names_declaration_and_storage(render):
    assert render([GENERATED])["chips"] == [
        '<span class="rp-chip cc-src-configmap cc-chip">ConfigMap fleet → Secret gsd-cluster-east</span>'
    ]


def test_discovery_excludes_retired_but_includes_generated_and_disabled_secrets(render):
    result = render([
        GENERATED,
        {"source": "secret:manual", "enabled": False},
        {"source": "secret:gone", "retired": True},
        {"source": "configmap:fleet:1"},
        {"source": "secret:host", "host": True},
        {"source": "values"},
    ])
    assert '2 Secrets carry the discovery label' in result["page"]


def test_existing_sources_and_discovery_singular_are_preserved(render):
    rows = [{"host": True}, {"source": "values"}, {"source": "secret:manual"},
            {"source": "configmap:fleet:1"}]
    result = render(rows)
    assert result["kinds"] == ["in-cluster", "values", "secret", "configmap"]
    assert [re.sub('<[^>]+>', '', chip) for chip in result["chips"]] == [
        "in-cluster", "values", "Secret manual", "ConfigMap fleet"]
    assert '1 Secret carry the discovery label' in result["page"]
    assert '0 Secrets carry the discovery label' in render([])["page"]


def test_configmap_chip_escapes_the_origin(render):
    result = render([{**GENERATED, "onboarding_configmap": "<fleet>"}])
    assert 'ConfigMap &lt;fleet&gt; → Secret gsd-cluster-east' in result["chips"][0]
