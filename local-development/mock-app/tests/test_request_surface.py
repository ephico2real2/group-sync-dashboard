"""Every endpoint a–p parsed by a REAL gsd.ClusterClient over the mock's real TLS."""

from __future__ import annotations

import pytest

from gsd.kube import ClusterClient


@pytest.fixture
def client(mock_cluster):
    return ClusterClient(mock_cluster.cluster_config(), timeout=5.0)


# ── (a) GroupSync + (b) Groups via fetch() ────────────────────────────────────────────────
def test_fetch_groupsyncs_and_groups(client):
    groupsyncs, groups = client.fetch()
    assert groupsyncs is not None
    assert [gs.name for gs in groupsyncs] == ["ldap-sync"]
    gs = groupsyncs[0]
    assert gs.namespace == "group-sync-operator"
    assert gs.schedule == "*/30 * * * *"
    assert gs.generation == 3
    assert gs.provider_names == ("acme-ldap",)
    assert gs.ldap_filter == "(objectClass=groupOfNames)"
    assert gs.success_at == "2026-09-14T08:00:00Z"

    by_name = {g.name: g for g in groups}
    assert by_name["app-ocp-rbac-demo-cluster-admin"].member_count == 1
    assert by_name["app-ocp-rbac-demo-cluster-admin"].members == ["kubeadmin"]
    assert by_name["app-ocp-rbac-demo-cluster-admin"].sync_provider == "acme-ldap"
    assert by_name["app-ocp-rbac-demo-cluster-admin"].ldap_uid == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"
    # The null-users group parses as empty, not an error.
    assert by_name["empty-team"].member_count == 0
    assert by_name["empty-team"].members == []


# ── (c) Users ──────────────────────────────────────────────────────────────────────────────
def test_fetch_users(client):
    users = client.fetch_users()
    assert users is not None
    by = {u["user_name"]: u for u in users}
    assert by["dana.lee"]["full_name"] == "Dana Lee"
    assert by["dana.lee"]["has_identity"] is True
    assert by["dana.lee"]["providers"] == ["acme-ldap"]
    assert by["kubeadmin"]["has_identity"] is False


# ── (d) Identities ───────────────────────────────────────────────────────────────────────
def test_fetch_identities(client):
    identities = client.fetch_identities()
    assert identities is not None
    assert identities["dana.lee"] == "2026-01-02T00:00:00Z"
    assert set(identities) == {"dana.lee", "lateef.o", "jane.smith"}


# ── (e) Namespaces ─────────────────────────────────────────────────────────────────────────
def test_fetch_namespaces(client):
    namespaces = client.fetch_namespaces(["team"])
    assert namespaces is not None
    by = {n["name"]: n for n in namespaces}
    assert by["acme-app"]["phase"] == "Active"
    # Only the configured key is copied, never the whole label map.
    assert by["acme-app"]["metadata"] == {"team": "acme"}


# ── (f)+(g) Group + User bindings ────────────────────────────────────────────────────────
def test_fetch_bindings(client):
    rows = client.fetch_bindings()
    by = {(r.binding_name, r.group_name): r for r in rows}
    admin = by[("cluster-admin-crb", "app-ocp-rbac-demo-cluster-admin")]
    assert admin.binding_kind == "ClusterRoleBinding"
    assert admin.role_name == "cluster-admin"
    assert admin.managed_source == "gitops"
    handmade = by[("handmade-reader-crb", "legacy-ops")]
    assert handmade.managed_source is None            # unmanaged finding
    assert handmade.exception == "reviewed 2026-09-10, temporary"


def test_fetch_user_bindings(client):
    rows = client.fetch_user_bindings()
    by = {(r.binding_name, r.user_name): r for r in rows}
    row = by[("viewer-rb", "lateef.o")]
    assert row.binding_kind == "RoleBinding"
    assert row.binding_namespace == "acme-app"
    assert row.role_name == "viewer"
    assert row.is_platform is False


# ── (h)+(i) Operator configs ────────────────────────────────────────────────────────────
def test_fetch_operator_configs(client):
    configs = client.fetch_operator_configs()
    assert configs is not None
    assert [c.name for c in configs] == ["acme-nsconfig"]
    assert configs[0].kind == "NamespaceConfig"
    assert configs[0].success_at == "2026-09-14T08:00:00Z"


# ── (j) Nodes (labelSelector honoured) ───────────────────────────────────────────────────
def test_fetch_nodes(client):
    nodes = client.fetch_nodes("node-role.kubernetes.io/master=")
    assert nodes == ["master-0", "master-1"]           # sorted; worker-0 filtered out


# ── (k) OAuth CR ─────────────────────────────────────────────────────────────────────────
def test_fetch_oauth(client):
    providers = client.fetch_oauth_providers()
    assert providers == ["acme-ldap"]
    dn = client.fetch_access_group_dn()
    assert dn == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"


# ── (l) OAuth pods ───────────────────────────────────────────────────────────────────────
def test_fetch_oauth_pods(client):
    pods = client.fetch_oauth_pods("openshift-authentication")
    assert pods is not None
    # Only Running pods; the Pending one is dropped.
    assert sorted(pods) == [
        "oauth-openshift-6d8f9c7b4-abcde",
        "oauth-openshift-6d8f9c7b4-fghij",
    ]


# ── (m) Pod log ──────────────────────────────────────────────────────────────────────────
def test_fetch_pod_log(client):
    lines = client.fetch_pod_log("openshift-authentication", "oauth-openshift-6d8f9c7b4-abcde")
    assert lines is not None
    assert any('succeeded for "jane.smith"' in ln for ln in lines)
    for ln in lines:
        assert ln[:4].isdigit()                        # RFC3339 prefix present


# ── (n) Node-log listing + (o) file read ─────────────────────────────────────────────────
def test_node_log_listing_and_read(client):
    names = client.list_node_log_files("master-0", "oauth-server")
    assert names == ["audit-2026-09-01T00-00-00.000.log", "audit.log"]

    read = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    assert read is not None
    assert read.rotated is False
    text = read.data.decode("utf-8")
    assert '"authentication.openshift.io/username":"jane.smith"' in text
    assert text.count("\n") == 3                        # three events in the live file


def test_node_log_range_resume(client):
    full = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    total = len(full.data)
    # A ranged read from the middle returns the tail; a read at EOF returns nothing new.
    tail = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=10)
    assert tail is not None and tail.rotated is False
    assert tail.data == full.data[10:]
    at_eof = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=total)
    assert at_eof is not None and at_eof.data == b"" and at_eof.rotated is False


# ── (p) SubjectAccessReview ──────────────────────────────────────────────────────────────
def test_subject_access_review(client):
    allowed = client.create_subject_access_review(
        "kubeadmin",
        ["app-ocp-rbac-demo-cluster-admin", "system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert allowed is True
    denied = client.create_subject_access_review(
        "lateef.o",
        ["system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert denied is False


# ── auth gate ────────────────────────────────────────────────────────────────────────────
def test_wrong_token_is_auth_failed(mock_cluster):
    import os

    from gsd.kube import AUTH_FAILED, ClusterError

    cfg = mock_cluster.cluster_config(token_env="GSD_BAD_TOKEN")
    # resolve_token reads the env at call time, so overwrite AFTER the helper set the good one.
    os.environ["GSD_BAD_TOKEN"] = "not-the-token"
    client = ClusterClient(cfg, timeout=5.0)
    with pytest.raises(ClusterError) as exc:
        client.fetch()
    assert exc.value.outcome == AUTH_FAILED


@pytest.mark.parametrize(("kind", "api_version"), [
    ("GroupSyncList", "redhatcop.redhat.io/v1alpha1"), ("GroupList", "user.openshift.io/v1"),
    ("UserList", "user.openshift.io/v1"), ("IdentityList", "user.openshift.io/v1"),
    ("NamespaceList", "v1"), ("RoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("ClusterRoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("NamespaceConfigList", "redhatcop.redhat.io/v1alpha1"),
    ("GroupConfigList", "redhatcop.redhat.io/v1alpha1"), ("NodeList", "v1"), ("PodList", "v1"),
])
def test_list_envelope_carries_the_real_api_version(kind, api_version):
    # review #118 C4: no literal "unknown".
    from mock_app.responses import k8s_list
    assert k8s_list([], kind=kind)["apiVersion"] == api_version
