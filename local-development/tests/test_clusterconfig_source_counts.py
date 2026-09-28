"""Exercise the page's JavaScript counts without launching a browser (#404, #467)."""

import ast
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from gsd.clusterconfig import FINDING_CODES


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

    def run(clusters, findings=(), secrets=None):
        script = functions + """
const data = {clusterconfigs: {clusters: JSON.parse(process.argv[1]), findings: JSON.parse(process.argv[2]),
                               secrets: JSON.parse(process.argv[3])}};
// Only unrelated page sections are stubbed; counts and chips run the production functions.
const ccClusterCard = () => '', ccFleetRows = () => '', ccAddForm = () => '', ccFinding = () => '';
console.log(JSON.stringify({
  kinds: data.clusterconfigs.clusters.map(ccSourceKind),
  chips: data.clusterconfigs.clusters.map(ccSourceChip),
  page: clusterConfigPage(),
}));
"""
        result = subprocess.run([node, "-e", script, json.dumps(clusters), json.dumps(list(findings)),
                                 json.dumps(secrets or {})],
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
    assert '2 served from Secrets' in result["page"]


def test_existing_sources_and_discovery_singular_are_preserved(render):
    rows = [{"host": True}, {"source": "values"}, {"source": "secret:manual"},
            {"source": "configmap:fleet:1"}]
    result = render(rows)
    assert result["kinds"] == ["in-cluster", "values", "secret", "configmap"]
    assert [re.sub('<[^>]+>', '', chip) for chip in result["chips"]] == [
        "in-cluster", "values", "Secret manual", "ConfigMap fleet"]
    assert '1 served from a Secret' in result["page"]
    assert '0 served from Secrets' in render([])["page"]


def test_configmap_chip_escapes_the_origin(render):
    result = render([{**GENERATED, "onboarding_configmap": "<fleet>"}])
    assert 'ConfigMap &lt;fleet&gt; → Secret gsd-cluster-east' in result["chips"][0]


def _finding(secret, code):
    return {"secret": secret, "code": code, "detail": "the reason"}


def test_refused_labelled_secrets_count_once_each_whatever_the_spelling(render):
    # #467: a parser refusal, the reader's duplicate pair, and onboarding's two codes on one generated Secret, whose
    # conflict spells it `secret:gen` — five labelled Secrets refused, beside the one served.
    page = render([{"source": "secret:manual"}], [
        _finding("bad", "server-invalid"),
        _finding("dup-a", "duplicate-cluster-name"), _finding("dup-b", "duplicate-cluster-name"),
        _finding("gen", "onboarding-ownership-conflict"), _finding("secret:gen", "duplicate-cluster-name"),
        _finding("held", "onboarding-cleanup-pending"),
    ])["page"]
    assert "1 served from a Secret · 5 labelled Secrets refused (see Findings) · last read" in page


def test_a_finding_whose_source_is_not_a_refused_labelled_secret_is_not_counted(render):
    # A ConfigMap or its stanza, the values list, a Secret that is still served, the cluster a lookup or a login is
    # about, a failed LIST: none is a refused labelled Secret, so the line names no refusal.
    page = render([{"source": "secret:gsd-cluster-east"}], [
        _finding("configmap:fleet", "onboarding-invalid"), _finding("configmap:fleet:0", "duplicate-cluster-name"),
        _finding("values", "duplicate-cluster-name"), _finding("configmap:fleet:1", "onboarding-ownership-conflict"),
        _finding("gsd-cluster-east", "shadows-values-entry"), _finding("gsd-cluster-east", "oauth-exchange-not-built"),
        _finding("gsd-cluster-east", "lookup-write-failed"), _finding("gsd-cluster-west", "login-refused"),
        _finding("sl", "self-login-suspended"), _finding("-", "discovery-failed"),
    ])["page"]
    assert "1 served from a Secret · last read" in page
    assert "refused (see Findings)" not in page


def test_switched_off_discovery_keeps_its_line(render):
    # Must not change (#467): the OFF state is its own sentence, with no count beside it.
    page = render([{"source": "secret:manual"}], [_finding("bad", "server-invalid")], {"enabled": False})["page"]
    assert "switched off (<code>clusterConfig.secrets.enabled: false</code>)" in page
    assert "served from" not in page and "refused (see Findings)" not in page


def test_the_pages_refusal_codes_are_the_parsers_and_discoverys_three():
    """#467: the page counts a refused labelled Secret by its finding's code, so a refusal the parser gains and the
    page does not list would be undercounted again. The parser's codes are read from its `finding(...)` calls."""
    html = (Path(__file__).parents[1] / "gsd/static/index.html").read_text()
    listed = re.search(r"const refusalCodes = new Set\(\[(.*?)\]\);", html, re.S)
    assert listed, "clusterConfigPage no longer names the codes it counts as refused labelled Secrets"
    page = set(re.findall(r'"([a-z-]+)"', listed.group(1)))
    tree = ast.parse((Path(__file__).parents[1] / "gsd/clusterconfig/parser.py").read_text())
    parser = {node.args[0].value for node in ast.walk(tree)
              if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "finding"
              and node.args and isinstance(node.args[0], ast.Constant)}
    assert page == parser | {"duplicate-cluster-name", "onboarding-cleanup-pending", "onboarding-ownership-conflict"}
    assert page <= set(FINDING_CODES)
