"""The DESIGN §5.4 oracle: four measured personas × two verbs → measured tiers.

Drives the REAL SAR POST over TLS. ``spec.groups`` is built exactly as kube.py builds it —
byte-exact Group memberships (``fetch_groups_of_user``) + the virtual ``system:*`` groups — so
this asserts the whole path, not just the authorizer class.
"""

from __future__ import annotations

import pytest

from gsd.kube import ClusterClient

from mock_app.app import groups_for_user

WIDE = {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
USAGE = {"verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}

# persona → (wide allowed, usage allowed)
ORACLE = {
    "kubeadmin": (True, True),
    "dana.lee": (True, False),      # cluster-reader: read yes, write no — excludes the auditor
    "lateef.o": (False, False),
    "jane.smith": (False, False),   # decoy group named "...-cluster-admin", no binding behind it
}


@pytest.mark.parametrize("persona", list(ORACLE))
def test_persona_tiers(mock_cluster, persona):
    client = ClusterClient(mock_cluster.cluster_config(), timeout=5.0)
    groups = groups_for_user(mock_cluster.fixture, persona)
    wide = client.create_subject_access_review(persona, groups, WIDE)
    usage = client.create_subject_access_review(persona, groups, USAGE)
    assert (wide, usage) == ORACLE[persona], f"{persona}: got wide={wide} usage={usage}"


def test_groups_resolution_is_byte_exact(mock_cluster):
    # fetch_groups_of_user must resolve the same membership the SAR relies on.
    client = ClusterClient(mock_cluster.cluster_config(), timeout=5.0)
    assert client.fetch_groups_of_user("kubeadmin") == ["app-ocp-rbac-demo-cluster-admin"]
    assert client.fetch_groups_of_user("jane.smith") == ["platform-team-cluster-admin"]
    # Case-sensitive: KUBEADMIN is a different identity and resolves no groups.
    assert client.fetch_groups_of_user("KUBEADMIN") == []


def test_decoy_group_name_grants_nothing(mock_cluster):
    """The key negative fixture: membership in a suggestively-named group must NOT grant a tier."""
    client = ClusterClient(mock_cluster.cluster_config(), timeout=5.0)
    groups = groups_for_user(mock_cluster.fixture, "jane.smith")
    assert "platform-team-cluster-admin" in groups        # she IS in the admin-named group
    assert client.create_subject_access_review("jane.smith", groups, WIDE) is False
