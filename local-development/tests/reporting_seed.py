"""One seeded dashboard database and its VACUUM INTO copy, for every report-service test.

Not a test module (no test_ prefix): imported by test_reporting_snapshot.py, test_reporting_catalogue.py
and test_reporting_server.py, the way test_chart_reporting.py imports test_chart_pdb.py's helpers.
The seed is the Store's own writer API — never raw SQL — so the copy the report service reads is
exactly what the dashboard would have written.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from gsd import loginlog
from gsd.store import Store

CLUSTER = "crc-local"
NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)
RAW_ERROR = "LDAP bind failed for cn=svc-bind,ou=TrustedApplications,dc=example,dc=com: invalidCredentials"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_store(db_path: str, *, login_events: bool = True, gate: bool = True, reconcile_error: bool = True) -> Store:
    """Groups, members, Users, bindings of every classification, a GroupSync CR, optionally the
    login gate, login attempts and a reconcile error whose text must never reach a report."""
    now = _iso(NOW)
    store = Store(db_path)
    store.upsert_cluster(CLUSTER, "https://api.crc.testing:6443", True)
    store.record_poll(CLUSTER, "ok", None)
    store.replace_groupsync_state(CLUSTER, [
        {"name": "corp", "namespace": "group-sync-operator", "schedule": "*/10 * * * *", "ldap_filter": "(objectClass=group)",
         "last_sync_at": _iso(NOW - timedelta(minutes=3)), "generation": 1, "provider_keys": ["corp_ldap"]},
    ], now)
    store.replace_group_state(CLUSTER, [
        {"name": "team-a", "member_count": 2, "sync_provider": "corp_ldap", "group_synced_at": now, "ldap_uid": "cn=team-a,ou=groups,dc=example,dc=com"},
        {"name": "team-b", "member_count": 1, "sync_provider": "corp_ldap", "group_synced_at": now, "ldap_uid": None},
        {"name": "ocp-users", "member_count": 3, "sync_provider": "corp_ldap", "group_synced_at": now, "ldap_uid": "cn=ocp-users,ou=groups,dc=example,dc=com"},
        {"name": "hand-made", "member_count": 1, "sync_provider": None, "group_synced_at": None, "ldap_uid": None},
        {"name": "empty-group", "member_count": 0, "sync_provider": "corp_ldap", "group_synced_at": now, "ldap_uid": None},
    ], now)
    store.record_managed_groups(CLUSTER, [{"name": "team-a", "sync_provider": "corp_ldap"}, {"name": "team-b", "sync_provider": "corp_ldap"},
                                          {"name": "ocp-users", "sync_provider": "corp_ldap"}, {"name": "gone-group", "sync_provider": "corp_ldap"}], now)
    store.sync_members(CLUSTER, {"team-a": ["alice", "bob"], "team-b": ["carol"], "ocp-users": ["alice", "bob", "dave"], "hand-made": ["erin"], "empty-group": []},
                       {"team-a": now, "team-b": now, "ocp-users": now}, now)
    store.replace_bindings(CLUSTER, [
        {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "team-a-edit", "role_kind": "ClusterRole", "role_name": "edit", "group_name": "team-a", "managed_source": "GroupConfig/prod"},
        {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "gone-view", "role_kind": "ClusterRole", "role_name": "view", "group_name": "gone-group", "managed_source": "GroupConfig/prod"},
        {"binding_kind": "RoleBinding", "binding_namespace": "dev-ns", "binding_name": "typo-view", "role_kind": "ClusterRole", "role_name": "view", "group_name": "teem-a"},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "team-b-admin", "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": "team-b", "managed_source": "GroupConfig/admins"},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "authenticated-basic", "role_kind": "ClusterRole", "role_name": "basic-user", "group_name": "system:authenticated"},
        {"binding_kind": "RoleBinding", "binding_namespace": "dev-ns", "binding_name": "handmade-edit", "role_kind": "ClusterRole", "role_name": "edit", "group_name": "team-b"},
    ], now)
    store.replace_user_bindings(CLUSTER, [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "frank-admin", "role_kind": "ClusterRole", "role_name": "cluster-admin", "user_name": "frank", "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "erin-view", "role_kind": "ClusterRole", "role_name": "view", "user_name": "erin", "is_platform": 0},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "sa-admin", "role_kind": "ClusterRole", "role_name": "cluster-admin", "user_name": "system:serviceaccount:openshift-x:y", "is_platform": 1},
    ], now)
    store.replace_users(CLUSTER, [
        {"user_name": "alice", "full_name": "Alice Cooper", "created_at": _iso(NOW - timedelta(days=30)), "providers": ["corp_ldap"], "has_identity": True},
        {"user_name": "bob", "full_name": None, "created_at": _iso(NOW - timedelta(days=10)), "providers": ["corp_ldap"], "has_identity": True},
        {"user_name": "erin", "full_name": None, "created_at": _iso(NOW - timedelta(days=400)), "providers": [], "has_identity": False},
    ], now)
    if gate:
        store.set_cluster_access_group(CLUSTER, "cn=ocp-users,ou=groups,dc=example,dc=com", "ldap-filter", "ocp-users", now)
    if login_events:
        store.record_login_read(CLUSTER, now)
        store.record_login_events(CLUSTER, [
            {"pod_name": "oauth-1", "user_name": "alice", "outcome": loginlog.OUTCOME_SUCCESS, "at": _iso(NOW - timedelta(days=1)),
             "provider": "corp_ldap", "ldap_result_code": None, "detail": None, "observed_at": now},
            {"pod_name": "oauth-1", "user_name": "bob", "outcome": loginlog.OUTCOME_SUCCESS, "at": _iso(NOW - timedelta(days=120)),
             "provider": "corp_ldap", "ldap_result_code": None, "detail": None, "observed_at": now},
            {"pod_name": "oauth-1", "user_name": "mallory", "outcome": loginlog.OUTCOME_REJECTED, "at": _iso(NOW - timedelta(hours=2)),
             "provider": "corp_ldap", "ldap_result_code": None, "detail": None, "observed_at": now},
            {"pod_name": "oauth-1", "user_name": "carol", "outcome": loginlog.OUTCOME_REJECTED, "at": _iso(NOW - timedelta(hours=1)),
             "provider": "corp_ldap", "ldap_result_code": None, "detail": None, "observed_at": now},
        ])
    if reconcile_error:
        store.upsert_reconcile_error(CLUSTER, "corp", _iso(NOW - timedelta(minutes=2)), 1, RAW_ERROR)
    store.replace_operator_configs(CLUSTER, None, now)
    return store


def write_snapshot(store: Store, directory: Path) -> Path:
    path = store.snapshot(str(directory), keep=2)
    assert path, "snapshot was not written"
    return Path(path)


def seeded_dirs(tmp_path: Path, **seed_kwargs) -> tuple[Path, Path]:
    """(snapshot_dir, artifact_dir) with one seeded copy already written."""
    snapshots, artifacts = tmp_path / "snapshots", tmp_path / "artifacts"
    snapshots.mkdir(); artifacts.mkdir()
    store = seed_store(str(tmp_path / "writer.db"), **seed_kwargs)
    try:
        write_snapshot(store, snapshots)
    finally:
        store.close()
    return snapshots, artifacts
