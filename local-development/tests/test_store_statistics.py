"""The store keeps the query planner's statistics current, and its readers use them (#626).

Without statistics SQLite plans from the shape of the indexes alone. Two reads chose an index that narrows only to
cluster_id and so read a cluster's whole table once per row: the Groups list's binding count (2.5 s at 999 groups
and 50,000 bindings) and group detail's first-seen (5.5 s at 300,000 membership events). The store now runs
SQLite's recommended `PRAGMA optimize` at open and after every write cycle (`maintain`), and a reader opened before
a refresh reconnects, because an open connection never loads new statistics. The bound is the operator's: a
cluster never has 1,000 groups.

The plans are read from the SQL the store itself runs (the reader's trace callback gives it with its values bound),
so a test cannot pass on a copy of a query that has drifted from the real one.
"""

from __future__ import annotations

import importlib.util
import pathlib
import random
import shutil
import sqlite3
import threading
import time
from unittest.mock import patch

import pytest

from gsd.store import Store

if sqlite3.sqlite_version_info < (3, 46, 0):
    pytest.skip(
        f"SQLite {'.'.join(map(str, sqlite3.sqlite_version_info))}: planner statistics require SQLite >= 3.46.0; "
        "image-proof.py proves the behaviour on the image's own SQLite at every build",
        allow_module_level=True,
    )

GROUPS, BINDINGS, EVENTS, MEMBERS = 999, 50_000, 100_000, 25
BIG = "g0000"


def test_image_proof_planner_statistics(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "image_proof", pathlib.Path(__file__).resolve().parents[1] / "image-proof.py")
    proof = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proof)
    proof.prove_planner_statistics(str(tmp_path))


@pytest.fixture(scope="module")
def seeded(tmp_path_factory) -> pathlib.Path:
    """A database at the operator's bound, written straight to the tables, with no statistics in it."""
    path = tmp_path_factory.mktemp("stats") / "seed.db"
    store = Store(str(path))
    store.upsert_cluster("c", "https://x", True)
    conn = store._conn
    names = [f"g{i:04d}" for i in range(GROUPS)]
    rnd = random.Random(626)
    conn.executemany("INSERT INTO group_state(cluster_id, name, member_count, sync_provider, observed_at) "
                     "VALUES ('c', ?, 25, 'gs_ldap', '2026-10-05T00:00:00Z')", [(n,) for n in names])
    conn.executemany("INSERT INTO rbac_group_binding(cluster_id, binding_kind, binding_namespace, binding_name, role_kind, "
                     "role_name, subject_kind, group_name, observed_at) VALUES ('c', 'RoleBinding', ?, ?, 'ClusterRole', "
                     "'view', 'Group', ?, '2026-10-05T00:00:00Z')",
                     [(f"ns{j % 500}", f"b{j}", rnd.choice(names)) for j in range(BINDINGS)])
    conn.executemany("INSERT INTO group_member(cluster_id, group_name, user_name, first_seen_at, last_seen_at) "
                     "VALUES ('c', ?, ?, 't', 't')", [(BIG, f"u{i}") for i in range(MEMBERS)])
    conn.executemany("INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at) VALUES ('c', ?, ?, ?, ?)",
                     [(rnd.choice(names), f"u{rnd.randrange(5000)}", rnd.choice(("added", "removed")),
                       f"2026-{1 + j % 9:02d}-{1 + j % 28:02d}T00:00:00Z") for j in range(EVENTS)])
    conn.commit()
    conn.execute("DROP TABLE IF EXISTS sqlite_stat1")
    conn.commit()
    store.close()
    return path


@pytest.fixture()
def db(seeded, tmp_path) -> pathlib.Path:
    path = tmp_path / "gsd.db"
    shutil.copy(seeded, path)
    return path


def _traced(store: Store, read) -> list[str]:
    """The SQL a store read runs on this thread's reader, values bound."""
    seen: list[str] = []
    conn = store._reader()
    conn.set_trace_callback(seen.append)
    try:
        read()
    finally:
        conn.set_trace_callback(None)
    return seen


def _plan(store: Store, sql: str) -> str:
    return " | ".join(row[3] for row in store._reader().execute("EXPLAIN QUERY PLAN " + sql))


def _timed(read) -> float:
    start = time.perf_counter()
    read()
    return time.perf_counter() - start


def test_open_gathers_statistics_and_both_reads_use_their_index(db):
    store = Store(str(db))
    try:
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        (members_sql,) = _traced(store, lambda: store.group_members("c", BIG))
        assert "SEARCH b USING INDEX rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql)
        assert "SEARCH e USING INDEX membership_event_by_user (cluster_id=? AND user_name=?)" in _plan(store, members_sql)
    finally:
        store.close()


def test_both_reads_stay_inside_a_budget_at_the_operator_s_bound(db):
    """Measured without statistics on this data: about 2.2 s and 0.6 s. With them: about 15 ms and 0.5 ms."""
    store = Store(str(db))
    try:
        assert len(store.groups("c", "all")) == GROUPS
        assert len(store.group_members("c", BIG)) == MEMBERS
        assert _timed(lambda: store.groups("c", "all")) < 0.5
        assert _timed(lambda: store.group_members("c", BIG)) < 0.2
    finally:
        store.close()


def test_the_rows_are_the_same_with_and_without_statistics(db, tmp_path):
    bare = tmp_path / "bare.db"
    shutil.copy(db, bare)
    raw = sqlite3.connect(bare)
    raw.row_factory = sqlite3.Row
    store = Store(str(db))
    try:
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        (members_sql,) = _traced(store, lambda: store.group_members("c", BIG))
        assert not raw.execute("SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat1'").fetchone()[0]
        for sql in (groups_sql, members_sql):
            assert sorted(map(tuple, raw.execute(sql))) == sorted(map(tuple, store._reader().execute(sql)))
    finally:
        raw.close()
        store.close()


def test_a_reader_opened_before_a_refresh_reconnects_and_uses_the_new_statistics(tmp_path, seeded):
    """An open connection keeps the plans it made: the planner loads statistics when a connection reads the
    schema, and ANALYZE does not change it (lang_analyze.html §3; measured). The reader reconnects instead."""
    path = tmp_path / "gsd.db"
    store = Store(str(path))   # a fresh install: empty tables, so open gathers nothing
    try:
        store.upsert_cluster("c", "https://x", True)
        before = store._reader()
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        epoch = store._stats_epoch
        src = sqlite3.connect(seeded)
        for table in ("group_state", "rbac_group_binding"):
            store._conn.execute(f"DELETE FROM {table}")
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            store._conn.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)
        store._conn.commit()
        src.close()
        assert "rbac_binding_by_group" not in _plan(store, groups_sql)
        store.maintain()
        assert store._stats_epoch == epoch + 1
        after = store._reader()
        assert after is not before
        assert "rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql)
    finally:
        store.close()


def test_nothing_changed_means_no_refresh_and_no_reconnect(db):
    store = Store(str(db))
    try:
        reader, epoch = store._reader(), store._stats_epoch
        store.maintain()
        store.maintain()
        assert store._stats_epoch == epoch
        assert store._reader() is reader
    finally:
        store.close()


def test_a_reader_inside_a_read_snapshot_is_not_replaced_until_the_snapshot_ends(db):
    store = Store(str(db))
    try:
        reader = store._reader()
        with store.read_snapshot():
            store._stats_epoch += 1          # a refresh lands while this thread holds a snapshot
            assert store._reader() is reader
            store.groups("c", "all")
        assert store._reader() is not reader
    finally:
        store.close()


def test_a_reader_on_another_thread_reconnects_too(db):
    """Readers are per thread; the epoch is read by each, so an API worker's reader reconnects as the poller's does."""
    store = Store(str(db))
    try:
        replaced: list[bool] = []

        def worker():
            first = store._reader()
            store._stats_epoch += 1
            replaced.append(store._reader() is not first)

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        assert replaced == [True]
    finally:
        store.close()


def test_reader_recovers_after_reconnect_failure(tmp_path):
    store = Store(str(tmp_path / "reader.db"))
    try:
        store.upsert_cluster("c", "https://x", True)
        store.clusters()
        store._stats_epoch += 1
        with patch("gsd.store.sqlite3.connect", side_effect=sqlite3.OperationalError(
                "unable to open database file")):
            try:
                store.clusters()
            except sqlite3.OperationalError:
                pass
            else:
                raise AssertionError("injected connect failure did not happen")
        assert [row["id"] for row in store.clusters()] == ["c"]
    finally:
        store.close()


def test_refresh_failure_is_optional_at_open_and_maintain(tmp_path):
    import gsd.store as module

    path = str(tmp_path / "optional.db")
    store = Store(path)
    store.upsert_cluster("c", "https://x", True)
    store.close()
    harden = module._harden

    def deny_analysis(action, arg1, arg2, database, source):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ANALYZE else sqlite3.SQLITE_OK

    def harden_and_deny(conn):
        harden(conn)
        conn.set_authorizer(deny_analysis)

    with patch.object(module, "_harden", harden_and_deny):
        store = Store(path)
    try:
        epoch = store._stats_epoch
        store.maintain()
        assert store._stats_epoch == epoch
        assert not store._conn.in_transaction
        assert [row["id"] for row in store.clusters()] == ["c"]
        store._conn.set_authorizer(None)
        store.maintain()
        assert store._stats_epoch == epoch + 1
        assert not store._conn.in_transaction
    finally:
        store.close()


def test_a_refresh_of_existing_statistics_reaches_a_reader_opened_before_it(tmp_path):
    """The case the reconnect is for. The first refresh creates sqlite_stat1, a schema change, so an open connection
    reloads on its next query without help; a later refresh only rewrites rows of sqlite_stat1, the schema stays the
    same, and an open connection keeps the statistics it loaded (lang_analyze.html §3). Statistics gathered on one
    group make the binding count read the cluster's covering index; growth of 250 times re-arms optimize, and only a
    reader that reconnects plans with the new ones."""
    store = Store(str(tmp_path / "gsd.db"))
    try:
        store.upsert_cluster("c", "https://x", True)

        def add(groups: list[str], first: int, count: int) -> None:
            store._conn.executemany("INSERT INTO group_state(cluster_id, name, member_count, sync_provider, observed_at) "
                                    "VALUES ('c', ?, 1, 'gs_ldap', 't')", [(g,) for g in groups])
            store._conn.executemany("INSERT INTO rbac_group_binding(cluster_id, binding_kind, binding_namespace, "
                                    "binding_name, role_kind, role_name, subject_kind, group_name, observed_at) VALUES "
                                    "('c', 'RoleBinding', ?, ?, 'ClusterRole', 'view', 'Group', ?, 't')",
                                    [(f"ns{j % 50}", f"b{j}", groups[j % len(groups)]) for j in range(first, first + count)])
            store._conn.commit()

        add([BIG], 0, 200)
        store.maintain()                                   # the first statistics: sqlite_stat1 is created
        (groups_sql,) = _traced(store, lambda: store.groups("c", "all"))
        version = store._reader().execute("PRAGMA schema_version").fetchone()[0]
        assert "rbac_binding_by_group" not in _plan(store, groups_sql)      # one group: the covering index wins
        epoch = store._stats_epoch
        add([f"g{i:04d}" for i in range(1, GROUPS)], 200, BINDINGS)
        store.maintain()                                   # a re-analysis: rows of sqlite_stat1 only
        assert store._stats_epoch == epoch + 1
        assert store._reader().execute("PRAGMA schema_version").fetchone()[0] == version
        # A new statement text, so neither connection can answer from Python's statement cache.
        assert "rbac_binding_by_group (cluster_id=? AND group_name=?)" in _plan(store, groups_sql + " ")
    finally:
        store.close()


def test_the_refresh_never_commits_an_enclosing_transaction(db):
    """The writer is shared, so a refresh inside a transaction leaves the boundary to its owner: run inside a poll
    snapshot that then fails, it must not have committed the snapshot's rows."""
    store = Store(str(db))
    try:
        with pytest.raises(RuntimeError, match="the cycle failed"):
            with store.poll_snapshot():
                store.replace_namespaces("c", [{"name": f"ns{i}"} for i in range(500)], "t")   # a table to analyse
                store.maintain()
                raise RuntimeError("the cycle failed")
        assert not store._rows("SELECT name FROM cluster_namespace WHERE cluster_id = 'c'")
    finally:
        store.close()


def _refuse_analyze(action, *rest):
    """An authorizer that refuses ANALYZE: a deterministic stand-in for any error inside the refresh."""
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ANALYZE else sqlite3.SQLITE_OK


def test_a_failed_refresh_leaves_a_successful_poll_ok_and_its_backup_written(tmp_path, monkeypatch):
    """maintain() is the first call of the poll's upkeep tail (Poller._after_poll): raised from it, a refresh error
    recorded a successful poll `unreachable` / `internal poller error` and skipped the cycle's backup on b65ce09d."""
    from gsd import poller as poller_module
    from gsd.config import ClusterConfig, Settings

    store = Store(str(tmp_path / "gsd.db"))
    cluster = ClusterConfig("c1", "https://api.c1.example:6443", token_env="GSD_TEST_TOKEN")
    store.upsert_cluster("c1", cluster.api_url, True)
    store._conn.set_authorizer(_refuse_analyze)
    poller = poller_module.Poller(
        store=store,
        settings=Settings(clusters=[cluster], db_path=store.path,
                          backup_dir=str(tmp_path / "backup"), backup_keep=3),
        elector=None,
    )

    def a_successful_poll(st, cl, *args, **kwargs):    # it leaves a table for the refresh to analyse
        st.replace_namespaces(cl.name, [{"name": f"ns{i}"} for i in range(500)], "2026-10-05T00:00:00Z")
        st.record_poll(cl.name, "ok", None)
        return "ok"

    monkeypatch.setenv("GSD_TEST_TOKEN", "token")
    monkeypatch.setattr(poller_module, "poll_once", a_successful_poll)
    monkeypatch.setattr(poller_module, "capture_once", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller_module, "refresh_bindings", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller, "_discover_doors", lambda *args, **kwargs: None)
    monkeypatch.setattr(poller, "_wait_cycle", lambda *args, **kwargs: poller._stop.set())
    try:
        poller._run_cluster(cluster)
        assert next(r for r in store.clusters() if r["id"] == "c1")["status"] == "ok"
        assert list((tmp_path / "backup").glob("gsd-*.db"))
    finally:
        store.close()
