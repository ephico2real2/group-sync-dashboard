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

import pathlib
import random
import shutil
import sqlite3
import threading
import time

import pytest

from gsd.store import Store

GROUPS, BINDINGS, EVENTS, MEMBERS = 999, 50_000, 100_000, 25
BIG = "g0000"


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
    """Measured without statistics on this data: about 2.5 s and 1.8 s. With them: about 20 ms and 1 ms."""
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
