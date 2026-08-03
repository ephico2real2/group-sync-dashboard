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
