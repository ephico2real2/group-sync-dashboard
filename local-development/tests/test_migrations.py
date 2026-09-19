"""Schema migrations against databases created by OLDER code.

The mechanism exists because the implicit one silently does nothing: the schema is applied
with CREATE TABLE IF NOT EXISTS, so a column added to the SCHEMA string never appears on an
existing database — the statement no-ops, and the first SELECT naming the column crashes on
upgraded deployments while passing on every fresh test database. That asymmetry is the
whole danger: the test suite cannot see it unless a test builds the OLD schema first,
which is what this file does.
"""

from __future__ import annotations

import re
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
        assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) >= 9
        # And the row reads back as approximate, which is the truth about it.
        assert store.users("crc")[0]["first_login_source"] == "user"
    finally:
        store.close()


_V9_DDL = """
CREATE TABLE login_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    outcome             TEXT NOT NULL,
    at                  TEXT NOT NULL,
    provider            TEXT,
    ldap_result_code    INTEGER,
    detail              TEXT,
    observed_at         TEXT NOT NULL,
    UNIQUE(cluster_id, pod_name, user_name, at, outcome)
);
CREATE TABLE ocp_user (
    cluster_id          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    full_name           TEXT,
    created_at          TEXT,
    providers           TEXT NOT NULL DEFAULT '[]',
    has_identity        INTEGER NOT NULL DEFAULT 0,
    identity_created_at TEXT,           -- migration 9: the earliest Identity creationTimestamp naming the User; NULL when not read
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, user_name)
);
        INSERT INTO login_event(cluster_id, pod_name, user_name, outcome, at, provider,
                                ldap_result_code, detail, observed_at)
        VALUES ('crc','oauth-pod','alice','success','2026-08-01T12:00:00.000000Z','developer',NULL,'ok',
                '2026-08-01T12:00:01Z');
        INSERT INTO ocp_user(cluster_id, user_name, full_name, created_at, providers, has_identity,
                             identity_created_at, observed_at)
        VALUES ('crc','alice','Alice','2026-08-05T16:14:16Z','["ldap-local"]',1,NULL,'2026-09-01T00:00:00Z');
        PRAGMA user_version = 9;
    """


@pytest.mark.parametrize("version", [5, 8, 9])
def test_migration_10_opens_a_v9_database_and_matches_a_fresh_one(tmp_path, version):
    """Cursor, review D1 — and the reference cluster, which crashed on exactly this: SCHEMA runs
    before _migrate, so an index in SCHEMA on a column only migration 10 adds raised
    "no such column: audit_id" and no 0.16 database could be opened. The tables below are the
    0.16.0 definitions copied from that release's SCHEMA (login_event from migration 5's shape,
    ocp_user with migration 9's identity_created_at)."""
    path = str(tmp_path / "v9.db")
    conn = sqlite3.connect(path)
    ddl = _V9_DDL
    if version == 8:
        # migration 9 had not run: no identity_created_at column, and the seed row omits it
        ddl = "\n".join(l for l in ddl.splitlines() if "identity_created_at TEXT" not in l)
        ddl = ddl.replace("identity_created_at, observed_at)", "observed_at)").replace("1,NULL,'2026-09-01T00:00:00Z'", "1,'2026-09-01T00:00:00Z'")
    if version == 5:
        # no ocp_user table at all before migration 4's Users read; keep every other statement
        ddl = re.sub(r"CREATE TABLE ocp_user \(.*?\);\n", "", ddl, flags=re.S)
        ddl = re.sub(r"INSERT INTO ocp_user\(.*?\);\n", "", ddl, flags=re.S)
    conn.executescript(ddl.replace("PRAGMA user_version = 9;", f"PRAGMA user_version = {version};"))
    conn.commit()
    conn.close()
    from gsd.store import _MIGRATIONS
    upgraded = Store(path)
    fresh = Store(str(tmp_path / "fresh.db"))
    try:
        def cols(store, table):
            # As a set by name: ALTER TABLE appends, so a migrated table's column ORDER differs
            # from a fresh one's (migration 9's identity_created_at already did), and nothing
            # here selects by position.
            return sorted((r[1], r[2].upper(), r[3], r[4], r[5]) for r in store._conn.execute(f"PRAGMA table_info({table})"))
        for table in ("login_event", "login_audit_cursor", "ocp_user", "cluster_namespace", "cluster_namespace_status", "report_run"):
            assert cols(upgraded, table) == cols(fresh, table), table   # migrations 10 and 11
        def indexes(store, table):
            return sorted(r[1] for r in store._conn.execute(f"PRAGMA index_list({table})") if r[3] == "c")
        assert indexes(upgraded, "login_event") == indexes(fresh, "login_event")
        assert "login_event_by_audit_id" in indexes(upgraded, "login_event")
        assert {"report_run_by_time", "report_run_by_user"} <= set(indexes(upgraded, "report_run")) == set(indexes(fresh, "report_run"))
        row = upgraded._conn.execute("SELECT source, kind, audit_id FROM login_event").fetchone()
        assert tuple(row) == ("pod-log", "credential", None)
        if version >= 8:
            assert upgraded._conn.execute("SELECT identities FROM ocp_user").fetchone()[0] == "[]"
        for u in ("u1", "u2"):
            upgraded._conn.execute(
                "INSERT INTO login_event(cluster_id,pod_name,user_name,outcome,at,detail,observed_at)"
                " VALUES('crc','p',?,'failed','t','d','o')", (u,))
        assert upgraded._conn.execute("SELECT count(*) FROM login_event WHERE audit_id IS NULL").fetchone()[0] == 3
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 17
    finally:
        upgraded.close()
        fresh.close()


def test_a_successfully_polled_empty_cluster_is_marked_at_the_next_open(tmp_path):
    """Codex, review 2 of #177 (S3 refuted): a successful poll writes groupsync_presence in the same
    transaction as sync_members, even when the cluster returned no Group at all — durable proof the
    stream was observed before observation_state existed. The seed runs at every open (OB1), so a
    store rewound to user_version 14 with the marker gone is marked again. Fails before (baseline == 1)."""
    from gsd.store import Store
    db = str(tmp_path / "polled-empty-v14.db")
    store = Store(db)
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    with store.poll_snapshot():
        store.replace_groupsync_state("crc", [], "2026-09-17T22:00:00Z")
        store.replace_group_state("crc", [], "2026-09-17T22:00:00Z")
        assert store.sync_members("crc", {}, {}, "2026-09-17T22:00:00Z") == 0
        store.record_poll("crc", "ok", None)
    for table in ("group_state", "group_member", "membership_event"):
        assert store._conn.execute(f"SELECT count(*) FROM {table} WHERE cluster_id='crc'").fetchone()[0] == 0
    assert store._conn.execute("SELECT count(*) FROM groupsync_presence WHERE cluster_id='crc'").fetchone()[0] == 1
    # rewind only the new mechanism: the shape a marker-less build leaves behind (migration 14 will not re-run)
    store._conn.execute("DELETE FROM observation_state")
    store._conn.execute("PRAGMA user_version = 14")
    store._conn.commit()
    store.close()

    upgraded = Store(db)
    try:
        streams = [r["stream"] for r in upgraded._conn.execute(
            "SELECT stream FROM observation_state WHERE cluster_id='crc'")]
        assert streams == ["membership"]
        assert upgraded.sync_members("crc", {"g": ["alice"]}, {}, "2026-09-17T22:05:00Z") == 1
        event = upgraded.membership_events("crc", user_name="alice")[0]
        assert (event["change"], event["baseline"]) == ("added", 0)
    finally:
        upgraded.close()


def test_a_committed_ok_poll_marks_membership_but_a_failed_one_does_not(tmp_path):
    """OB1, review 2 of #177: poll_outcome.status='ok' is written LAST inside the same snapshot as
    sync_members, so it proves the membership stream was observed even when it was empty; a
    failed poll proves nothing. Fails without the poll_outcome seed (`[] == [('nil', 'membership')]`)."""
    from gsd.store import Store
    db = str(tmp_path / "v13.db")
    fresh = Store(db)
    fresh.upsert_cluster("nil", "https://nil:6443", True)
    fresh.upsert_cluster("down", "https://down:6443", True)
    fresh.record_poll("nil", "ok", None)           # polled, empty, committed
    fresh.record_poll("down", "error", "refused")  # never observed
    fresh._conn.executescript("DROP TABLE observation_state; PRAGMA user_version = 13;")
    fresh.close()
    upgraded = Store(db)
    try:
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == 17
        markers = [tuple(r) for r in upgraded._conn.execute(
            "SELECT cluster_id, stream FROM observation_state ORDER BY 1")]
        assert markers == [("nil", "membership")]
        assert upgraded.sync_members("nil", {"g": ["zed"]}, {}, "2026-09-18T00:00:00Z") == 1
        assert upgraded.membership_events("nil", user_name="zed")[0]["baseline"] == 0
        assert upgraded.sync_members("down", {"g": ["ann"]}, {}, "2026-09-18T00:00:00Z") == 1
        assert upgraded.membership_events("down", user_name="ann")[0]["baseline"] == 1
    finally:
        upgraded.close()


def test_rows_written_without_a_marker_are_marked_at_the_next_open(tmp_path):
    """OB1, review 2 of #177 (V1): a build without observation_state (1f55cb1, which the lab ran)
    against a v14 store — a rollback — writes rows for a new cluster but no marker, and user_version
    stays 14 so migration 14 never re-runs. The next open must still mark that cluster, or its next
    real additions are flagged baseline. Simulated by writing the rows directly, as that build would."""
    from gsd.store import Store
    db = str(tmp_path / "v14.db")
    s = Store(db)
    s.upsert_cluster("x", "https://x:6443", True)
    s._conn.execute("INSERT INTO group_member(cluster_id, group_name, user_name, first_seen_at, last_seen_at)"
                    " VALUES('x','g','alice','t','t')")
    s._conn.execute("INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at)"
                    " VALUES('x','g','alice','added','t')")
    s._conn.commit()
    s.close()
    reopened = Store(db)
    try:
        assert [tuple(r) for r in reopened._conn.execute(
            "SELECT cluster_id, stream FROM observation_state")] == [("x", "membership")]
        assert reopened.sync_members("x", {"g": ["alice", "bob"]}, {}, "2026-09-18T00:00:00Z") == 1
        assert reopened.membership_events("x", user_name="bob")[0]["baseline"] == 0
    finally:
        reopened.close()
