"""Schema migrations against databases created by OLDER code.

The mechanism exists because the implicit one silently does nothing: the schema is applied
with CREATE TABLE IF NOT EXISTS, so a column added to the SCHEMA string never appears on an
existing database — the statement no-ops, and the first SELECT naming the column crashes on
upgraded deployments while passing on every fresh test database. That asymmetry is the
whole danger: the test suite cannot see it unless a test builds the OLD schema first,
which is what this file does.
"""

from __future__ import annotations

import sqlite3

import pytest

from gsd.store import Store


def _v0_database(path: str) -> None:
    """A database as the PREVIOUS release would have left it: no provenance columns,
    no operator_config tables, user_version 0."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE rbac_group_binding (
            cluster_id          TEXT NOT NULL,
            binding_kind        TEXT NOT NULL,
            binding_namespace   TEXT NOT NULL,
            binding_name        TEXT NOT NULL,
            role_kind           TEXT NOT NULL,
            role_name           TEXT NOT NULL,
            group_name          TEXT NOT NULL,
            observed_at         TEXT NOT NULL,
            PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
        );
        INSERT INTO rbac_group_binding VALUES
            ('crc', 'RoleBinding', 'ns-a', 'old-row', 'ClusterRole', 'view',
             'app-ocp-rbac-team-ns-audit', '2026-08-01T00:00:00Z');
    """)
    conn.commit()
    conn.close()


class TestUpgradeFromV0:
    def test_opening_an_old_database_adds_the_columns(self, tmp_path):
        db = str(tmp_path / "old.db")
        _v0_database(db)
        store = Store(db)
        try:
            cols = {r[1] for r in store._conn.execute("PRAGMA table_info(rbac_group_binding)")}
            assert {"managed_source", "exception"} <= cols, "migration did not run"
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 1
        finally:
            store.close()

    def test_existing_rows_survive_with_null_provenance(self, tmp_path):
        """The pre-migration rows are a cache and are replaced on the next refresh, but
        they must survive the upgrade itself — a migration that empties the table renders
        the bindings view blank until the next 300s cycle for no reason."""
        db = str(tmp_path / "old.db")
        _v0_database(db)
        store = Store(db)
        try:
            rows = store.all_bindings("crc")
            assert len(rows) == 1
            assert rows[0]["managed_source"] is None
        finally:
            store.close()

    def test_reopening_is_idempotent(self, tmp_path):
        """Every pod restart runs the migrations; running them twice must change nothing."""
        db = str(tmp_path / "old.db")
        _v0_database(db)
        for _ in range(3):
            Store(db).close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 1
        finally:
            store.close()

    def test_a_fresh_database_lands_at_the_same_version(self, tmp_path):
        """Fresh databases get the columns from SCHEMA and then replay the migrations,
        which must tolerate the change already existing."""
        store = Store(str(tmp_path / "fresh.db"))
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 1
        finally:
            store.close()


def test_a_fresh_database_lands_on_the_latest_migration(tmp_path):
    """Tuple placement must not make a fresh database report an older schema version."""
    from gsd.store import _MIGRATIONS
    store = Store(str(tmp_path / "fresh.db"))
    try:
        got = store._conn.execute("PRAGMA user_version").fetchone()[0]
        assert got == max(target for target, _, _ in _MIGRATIONS)
    finally:
        store.close()


def test_migration_8_adds_cliff_silence_and_the_time_index_to_an_older_database(tmp_path):
    """A pre-0.12 group_state has no cliff_silence; opening it must add the column (NULL for
    every existing row) and the membership_event time index, and land on the latest version."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE group_state (
            cluster_id TEXT NOT NULL, name TEXT NOT NULL, member_count INTEGER NOT NULL,
            sync_provider TEXT, group_synced_at TEXT, ldap_uid TEXT, observed_at TEXT NOT NULL,
            PRIMARY KEY(cluster_id, name));
        INSERT INTO group_state VALUES ('crc','g',3,NULL,NULL,NULL,'2026-09-01T00:00:00Z');
        PRAGMA user_version = 7;
    """)
    conn.commit()
    conn.close()

    from gsd.store import _MIGRATIONS
    store = Store(path)
    try:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(group_state)")}
        assert "cliff_silence" in cols
        assert store._conn.execute("SELECT cliff_silence FROM group_state").fetchone()[0] is None
        indexes = {r[1] for r in store._conn.execute("PRAGMA index_list(membership_event)")}
        assert "membership_event_by_time" in indexes
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) >= 8
    finally:
        store.close()


def test_migration_9_adds_the_identity_time_and_status_table_to_an_older_database(tmp_path):
    """A pre-0.15 ocp_user has no identity_created_at and no ocp_identity_status table; opening it
    must add both (NULL for every existing row — nothing is backfilled) and land on the latest version."""
    path = str(tmp_path / "old.db")
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE ocp_user (
            cluster_id TEXT NOT NULL, user_name TEXT NOT NULL, full_name TEXT, created_at TEXT,
            providers TEXT NOT NULL DEFAULT '[]', has_identity INTEGER NOT NULL DEFAULT 0,
            observed_at TEXT NOT NULL, PRIMARY KEY(cluster_id, user_name));
        INSERT INTO ocp_user VALUES ('crc','alice','Alice','2026-08-05T16:14:16Z','["ldap-local"]',1,'2026-09-01T00:00:00Z');
        PRAGMA user_version = 8;
    """)
    conn.commit()
    conn.close()

    from gsd.store import _MIGRATIONS
    store = Store(path)
    try:
        cols = {r[1] for r in store._conn.execute("PRAGMA table_info(ocp_user)")}
        assert "identity_created_at" in cols
        assert store._conn.execute("SELECT identity_created_at FROM ocp_user").fetchone()[0] is None
        tables = {r[0] for r in store._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "ocp_identity_status" in tables
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 9
        # And the row reads back as approximate, which is the truth about it.
        assert store.users("crc")[0]["first_login_source"] == "user"
    finally:
        store.close()
