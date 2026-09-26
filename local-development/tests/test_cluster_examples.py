"""Cluster examples (#389): real readers and a ConfigMap-only GitOps resource list."""
from __future__ import annotations

import itertools
import json
import pathlib
import textwrap

import yaml

from gsd.clusterconfig import CONFIG_TYPE_LABEL, SECRET_TYPE_LABEL
from gsd.clusterconfig.onboarding import discover_onboarding
from gsd.clusterconfig.parser import parse_secret
from gsd.config import ClusterConfig
from test_configmap_onboarding import Host
from test_fleet_lookup import settings

REPO = pathlib.Path(__file__).resolve().parents[2]
ONBOARDING = REPO / "examples" / "cluster-onboarding"


def _manifest(path):
    obj, = yaml.safe_load_all(path.read_text())
    return obj


def _applied(path):
    # Only a plain resource list: no generators, patches or remote bases to hide extra objects.
    config = _manifest(path / "kustomization.yaml")
    assert config == {
        "apiVersion": "kustomize.config.k8s.io/v1beta1",
        "kind": "Kustomization",
        "resources": ["configmap.yaml"],
    }
    return [_manifest(path / resource) for resource in config["resources"]]


def test_secret_parses_with_its_placeholder_and_verified_platform_trust(monkeypatch):
    obj = _manifest(REPO / "examples" / "cluster-secret" / "secret.yaml")
    assert (obj["apiVersion"], obj["kind"], obj["type"]) == ("v1", "Secret", "Opaque")
    assert obj["metadata"]["namespace"] == "group-sync-dashboard"
    assert obj["metadata"]["labels"][SECRET_TYPE_LABEL] == "cluster"
    config = json.loads(obj["stringData"]["config"])
    assert config == {"bearerToken": "<paste a token>", "tlsClientConfig": {"insecure": False}}
    cluster = parse_secret(obj, host_name="host")
    assert isinstance(cluster, ClusterConfig), cluster
    assert cluster.name == "ocp-east"
    assert cluster.api_url == "https://api.ocp-east.example.com:6443"
    assert cluster.resolve_token() == "<paste a token>"
    assert cluster.ca_data is None and cluster.ca_bundle_file is None
    assert cluster.insecure_skip_verify is False
    monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
    assert cluster.verify() is True, "without a mounted bundle, httpx uses its verified default trust"


def test_configmap_is_accepted_and_matches_the_documented_stanza_keys():
    obj = _manifest(ONBOARDING / "configmap.yaml")
    assert (obj["apiVersion"], obj["kind"]) == ("v1", "ConfigMap")
    assert obj["metadata"]["labels"][CONFIG_TYPE_LABEL] == "onboard"
    assert set(obj["data"]) == {"clusters.yaml"}
    stanza, = yaml.safe_load(obj["data"]["clusters.yaml"])["clusters"]
    assert stanza == {"name": "ocp-east", "apiUrl": "https://api.ocp-east.example.com:6443",
                      "saTokenLookup": True, "enabled": True}
    # Parse the indented Markdown code blocks, then select the ConfigMap by its YAML kind.
    lines = (REPO / "docs" / "CLUSTER_STANZA.md").read_text().splitlines(keepends=True)
    blocks = [textwrap.dedent("".join(group)) for indented, group in
              itertools.groupby(lines, key=lambda line: line.startswith("    ")) if indented]
    documents = [yaml.safe_load(block) for block in blocks]
    documented, = [doc for doc in documents if isinstance(doc, dict) and doc.get("kind") == "ConfigMap"]
    documented_stanza, = yaml.safe_load(documented["data"]["clusters.yaml"])["clusters"]
    assert stanza.keys() == documented_stanza.keys()
    namespace = obj["metadata"]["namespace"]
    assert namespace == "group-sync-dashboard"
    obj["metadata"]["uid"] = "api-assigned-example-uid"
    host = Host([obj])
    clusters, findings, blocked = discover_onboarding(host, namespace, settings=settings(), mutate=True)
    assert not findings and not blocked
    cluster, = clusters
    assert isinstance(cluster, ClusterConfig)
    assert (cluster.name, cluster.api_url) == (stanza["name"], stanza["apiUrl"])
    assert cluster.sa_token_lookup and cluster.enabled
    assert cluster.source == "configmap:cluster-onboarding:0"
    assert not host.mutations, "discovery queues the existing lookup; it does not write the ConfigMap"


def test_argocd_self_heals_only_the_configmap():
    obj = _manifest(ONBOARDING / "argocd-application.yaml")
    assert (obj["apiVersion"], obj["kind"]) == ("argoproj.io/v1alpha1", "Application")
    assert obj["metadata"]["namespace"] == "openshift-gitops"
    spec = obj["spec"]
    assert spec["project"] == "default"
    assert spec["source"] == {
        "repoURL": "https://github.com/<your-org>/<your-repo>.git",
        "targetRevision": "main", "path": "examples/cluster-onboarding",
    }, "leave directory unset so Argo CD detects Kustomize"
    assert "sources" not in spec
    assert spec["destination"] == {"server": "https://kubernetes.default.svc",
                                   "namespace": "group-sync-dashboard"}
    assert spec["syncPolicy"]["automated"] == {"prune": True, "selfHeal": True}
    assert _applied(REPO / spec["source"]["path"]) == [_manifest(ONBOARDING / "configmap.yaml")]


def test_flux_prunes_and_reconciles_only_the_configmap():
    obj = _manifest(ONBOARDING / "flux-kustomization.yaml")
    assert (obj["apiVersion"], obj["kind"]) == ("kustomize.toolkit.fluxcd.io/v1", "Kustomization")
    assert obj["metadata"]["namespace"] == "flux-system"
    spec = obj["spec"]
    assert spec == {
        "interval": "5m", "path": "./examples/cluster-onboarding", "prune": True,
        "sourceRef": {"kind": "GitRepository", "name": "cluster-config"},
        "targetNamespace": "group-sync-dashboard",
    }, "no patches or substitutions may add objects or disable drift correction"
    assert _applied(REPO / spec["path"]) == [_manifest(ONBOARDING / "configmap.yaml")]


def test_kustomization_selects_exactly_the_configmap():
    applied = _applied(ONBOARDING)
    assert applied == [_manifest(ONBOARDING / "configmap.yaml")]
    assert [(obj["apiVersion"], obj["kind"]) for obj in applied] == [("v1", "ConfigMap")]
