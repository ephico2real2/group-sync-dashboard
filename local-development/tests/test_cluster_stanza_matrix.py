"""The cluster stanza's accepted combinations and refusals, held against BOTH readers.

`docs/CLUSTER_STANZA.md` documents what a `clusters[]` entry may contain and — crucially — WHERE each
refusal fires: most fail `helm template`, four fail only at pod startup. That distinction is what an
operator plans a rollout around, so it is measured here rather than described: every row of the
document's tables is a case below, and this test fails the build when the two stop agreeing.

`helm` is not on every machine; the render half is skipped when it is missing and the loader half
still runs, because the loader is the boundary that actually protects the pod.
"""
from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml

from gsd.config import ConfigError, load_settings

CHART = "charts/group-sync-dashboard"
HOST = {"name": "dashboard", "apiUrl": "https://kubernetes.default.svc",
        "tokenFile": "/var/run/secrets/kubernetes.io/serviceaccount/token",
        "caBundleFile": "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt",
        "dashboardController": True, "enabled": True}
REMOTE = {"name": "r", "apiUrl": "https://a.example.com:6443"}

ACCEPTED = [
    ("host mounted SA", [HOST]),
    ("tokenEnv", [HOST, {**REMOTE, "tokenEnv": "R"}]),
    ("tokenFile", [HOST, {**REMOTE, "tokenFile": "/etc/t/token"}]),
    ("tokenEnv + caBundleFile", [HOST, {**REMOTE, "tokenEnv": "R", "caBundleFile": "/etc/ca/ca.crt"}]),
    ("tokenEnv + insecureSkipVerify", [HOST, {**REMOTE, "tokenEnv": "R", "insecureSkipVerify": True}]),
    ("saTokenLookup", [HOST, {**REMOTE, "saTokenLookup": True}]),
    ("userSelfLogin", [HOST, {**REMOTE, "userSelfLogin": True}]),
    ("saTokenLookup + bootstrap", [HOST, {**REMOTE, "saTokenLookup": True, "ldapConnectionBootstrap": "svc.fleet"}]),
    ("visibility self-only", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "self-only"}]),
    ("visibility hidden", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "hidden"}]),
    ("remote-sar + same-as-host", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "remote-sar", "identity": "same-as-host"}]),
    ("enabled false", [HOST, {**REMOTE, "tokenEnv": "R", "enabled": False}]),
]

#: (label, stanza, refused_by_render) — the third column is the document's "WHERE it fires" column.
REFUSED = [
    ("both modes", [HOST, {**REMOTE, "saTokenLookup": True, "userSelfLogin": True}], True),
    ("mode + tokenEnv", [HOST, {**REMOTE, "saTokenLookup": True, "tokenEnv": "R"}], True),
    ("no credential, no mode", [HOST, {**REMOTE}], True),
    ("bootstrap without a mode", [HOST, {**REMOTE, "tokenEnv": "R", "ldapConnectionBootstrap": "svc"}], True),
    ("bootstrap not a username", [HOST, {**REMOTE, "saTokenLookup": True, "ldapConnectionBootstrap": "not a username"}], True),
    ("mode on the host", [{k: v for k, v in HOST.items() if k != "tokenFile"} | {"saTokenLookup": True}], True),
    ("two controllers", [HOST, {**REMOTE, "tokenEnv": "R", "dashboardController": True}], True),
    ("controller disabled", [{**HOST, "enabled": False}], True),
    ("hidden on the host", [{**HOST, "visibility": "hidden"}], True),
    ("remote-sar on the host", [{**HOST, "visibility": "remote-sar", "identity": "same-as-host"}], True),
    ("remote-sar without same-as-host", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "remote-sar"}], True),
    ("visibility typo", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "self_only"}], True),
    ("identity typo", [HOST, {**REMOTE, "tokenEnv": "R", "identity": "Same-As-Host"}], True),
    ("enabled as a quoted word", [HOST, {**REMOTE, "tokenEnv": "R", "enabled": "yes"}], True),
    # The four the render does NOT catch. If one of these ever starts failing `helm template`, the
    # document's table is stale in the operator's favour — update it, do not delete the case.
    ("unknown key", [HOST, {**REMOTE, "tokenEnv": "R", "bearerToken": "x"}], False),
    ("duplicate name", [HOST, {**REMOTE, "name": "dashboard", "tokenEnv": "R"}], False),
    ("apiUrl without a scheme", [HOST, {**REMOTE, "apiUrl": "a.example.com:6443", "tokenEnv": "R"}], False),
    ("insecureSkipVerify + caBundleFile", [HOST, {**REMOTE, "tokenEnv": "R", "insecureSkipVerify": True, "caBundleFile": "/etc/ca.crt"}], False),
]


def _values(tmp_path, entries, name="v.yaml"):
    p = tmp_path / name
    # Rendered with the write grant on: a saTokenLookup row writes its Secret and is refused at
    # render without it (SPEC_S4b); the switch adds verbs to one Role and changes no other row.
    p.write_text(yaml.safe_dump({"clusters": entries, "clusterConfig": {"secrets": {"writes": {"enabled": True}}}}),
                 encoding="utf-8")
    return str(p)


def _renders(tmp_path, entries) -> bool:
    r = subprocess.run(["helm", "template", "t", CHART, "-f", _values(tmp_path, entries)],
                       capture_output=True, text=True, timeout=180, cwd="..")
    return r.returncode == 0


needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")


@pytest.mark.parametrize("label,entries", ACCEPTED, ids=[c[0] for c in ACCEPTED])
def test_the_documented_combinations_load(tmp_path, label, entries):
    load_settings(_values(tmp_path, entries))


@pytest.mark.parametrize("label,entries", ACCEPTED, ids=[c[0] for c in ACCEPTED])
@needs_helm
def test_the_documented_combinations_render(tmp_path, label, entries):
    assert _renders(tmp_path, entries), f"{label}: the chart refuses a combination the document calls accepted"


@pytest.mark.parametrize("label,entries,by_render", REFUSED, ids=[c[0] for c in REFUSED])
def test_the_documented_refusals_are_refused_by_the_loader(tmp_path, label, entries, by_render):
    with pytest.raises(ConfigError):
        load_settings(_values(tmp_path, entries))


@pytest.mark.parametrize("label,entries,by_render", REFUSED, ids=[c[0] for c in REFUSED])
@needs_helm
def test_where_each_refusal_fires_is_what_the_document_says(tmp_path, label, entries, by_render):
    # The operator plans a rollout around this: a stanza the render accepts and the pod refuses fails
    # AFTER a green upgrade, which reads as an outage rather than a config error.
    assert _renders(tmp_path, entries) is not by_render, (
        f"{label}: docs/CLUSTER_STANZA.md §5 says the render "
        f"{'refuses' if by_render else 'accepts'} this, and it does not"
    )


EXAMPLE = "../charts/group-sync-dashboard/example-production.yaml"


def test_the_production_example_loads_and_every_cluster_resolves_as_documented():
    """The example is offered to operators as a file that works, so it is loaded, not eyeballed.

    It renders too (below) — but rendering proves little here by the document's own §5: four bad
    stanzas render cleanly and are refused by the pod. The loader is the boundary that matters.
    """
    s = load_settings(EXAMPLE)
    by_name = {c.name: c for c in s.clusters}
    assert set(by_name) == {"dashboard", "prod-east", "prod-west", "lab", "shared-rnd", "decommissioned-dc"}
    assert s.host_cluster().name == "dashboard", "the declared controller is the host"
    assert by_name["dashboard"].credential_kind == "in-cluster"
    assert by_name["dashboard"].tls_mode["ca"] == "serviceAccount"
    assert by_name["prod-east"].tls_mode["ca"] == "caBundleFile", "a pinned CA"
    assert by_name["prod-west"].tls_mode["ca"] == "trusted-bundle", "no caBundleFile: the fleet bundle"
    assert by_name["prod-west"].visibility == "remote-sar" and by_name["prod-west"].identity == "same-as-host"
    assert by_name["lab"].visibility == "hidden"
    assert by_name["decommissioned-dc"].enabled is False
    # the mode cluster is listed with its reason and is NOT polled until S3b
    rnd = by_name["shared-rnd"]
    assert rnd.credential_kind == "remote-lookup" and rnd.connection_mode == "saTokenLookup"
    assert rnd.ldap_connection_bootstrap == "svc.gsd.fleet"
    assert rnd.credential_pending and "S3b" in rnd.credential_pending


@needs_helm
def test_the_production_example_renders(tmp_path):
    r = subprocess.run(["helm", "template", "t", CHART, "-f", "charts/group-sync-dashboard/example-production.yaml"],
                       capture_output=True, text=True, timeout=180, cwd="..")
    assert r.returncode == 0, r.stderr[-600:]
