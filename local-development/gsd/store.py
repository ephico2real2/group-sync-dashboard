"""SQLite store (PLAN §10).

`sync_event` is the whole point of the store: the API keeps no sync history, so a timeline
exists only if we accumulate it (PLAN §2). Everything else is current-state cache that could
in principle be re-fetched, and is kept only so the API can answer without blocking on a
cluster round-trip.

Two tables here are not in PLAN §10 and are additions the first slice found it needed:

* ``groupsync_state`` — §10 stores group state but not CR state, yet §11's groupsync list
  must return schedule and filter for a CR that has *never* synced and so has no sync_event.
* ``poll_outcome`` — §11's ``GET /api/clusters`` returns ``reachable``/``last_poll``/``error``,
  which §12 step 7 computes but §10 gives nowhere to put.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from .storage import SqliteHealth, StorageHealth  # noqa: F401
from .timeutil import now_iso

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cluster (
    id                  TEXT PRIMARY KEY,   -- the configured name; used in API paths
    api_url             TEXT NOT NULL,
    enabled             INTEGER NOT NULL DEFAULT 1
);

-- One row per OBSERVED sync, written only when lastSyncSuccessTime CHANGES (PLAN §6).
CREATE TABLE IF NOT EXISTS sync_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    groupsync_namespace TEXT NOT NULL,
    synced_at           TEXT NOT NULL,  -- the operator's timestamp
    observed_at         TEXT NOT NULL,  -- ours; observed_at - synced_at is OUR lag
    schedule            TEXT,           -- snapshot: schedules change, old rows must stay readable
    group_count         INTEGER,
    UNIQUE(cluster_id, groupsync_name, synced_at)
);
CREATE INDEX IF NOT EXISTS sync_event_lookup
    ON sync_event(cluster_id, groupsync_name, synced_at DESC);

-- Current CR state, replaced each poll.
CREATE TABLE IF NOT EXISTS groupsync_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    namespace           TEXT NOT NULL,
    schedule            TEXT,
    ldap_filter         TEXT,
    last_sync_at        TEXT,
    generation          INTEGER,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name, namespace)
);

-- The sync-provider label values a CR's groups carry, replaced with the CR state above and
-- in the same transaction. A separate table because a CR may declare SEVERAL providers and
-- each produces its own label value; the single `provider_key` column this replaces held
-- only the first, so every group of every later provider had no owner and so was never
-- staleness-checked. Databases created before this keep that column, unwritten and unread:
-- groupsync_state is a per-poll cache, so a vestigial NULL column costs nothing and there
-- is no migration step to get wrong.
CREATE TABLE IF NOT EXISTS groupsync_provider (
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    groupsync_namespace TEXT NOT NULL,
    provider_key        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, groupsync_name, groupsync_namespace, provider_key)
);
CREATE INDEX IF NOT EXISTS groupsync_provider_key
    ON groupsync_provider(cluster_id, provider_key);

-- Current group state, replaced each poll; history not kept (PLAN §10).
CREATE TABLE IF NOT EXISTS group_state (
    cluster_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    member_count        INTEGER NOT NULL,
    sync_provider       TEXT,
    group_synced_at     TEXT,           -- the group's OWN sync-time annotation
    ldap_uid            TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name)
);

-- Last reconcile FAILURE per CR (PLAN §2.1). Separate from sync_event because failures and
-- successes advance independently: a months-old error coexists with a 60s-old success.
CREATE TABLE IF NOT EXISTS reconcile_error (
    cluster_id          TEXT NOT NULL,
    groupsync_name      TEXT NOT NULL,
    failed_at           TEXT,
    observed_generation INTEGER,
    message             TEXT,
    PRIMARY KEY(cluster_id, groupsync_name)
);

CREATE TABLE IF NOT EXISTS poll_outcome (
    cluster_id          TEXT PRIMARY KEY,
    observed_at         TEXT NOT NULL,
    status              TEXT NOT NULL,  -- ok | auth_failed | forbidden | unreachable
    message             TEXT
);

-- Current membership. Unlike group_state this is NOT wholly replaced each poll: first_seen_at
-- must survive, or "when did this user join?" resets on every cycle and answers nothing.
CREATE TABLE IF NOT EXISTS group_member (
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    first_seen_at       TEXT NOT NULL,  -- when WE first observed them, not when LDAP added them
    last_seen_at        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, group_name, user_name)
);
CREATE INDEX IF NOT EXISTS group_member_by_user
    ON group_member(cluster_id, user_name);

-- Membership changes, append-only. The API has no history (PLAN §2), and a user quietly
-- dropping out of a group is exactly the invisible absence this dashboard exists for:
-- nothing logs it, no event fires, and the group still looks healthy afterwards.
CREATE TABLE IF NOT EXISTS membership_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    change              TEXT NOT NULL,  -- added | removed
    observed_at         TEXT NOT NULL,
    group_synced_at     TEXT            -- the group's own sync-time when we saw the change
);
CREATE INDEX IF NOT EXISTS membership_event_lookup
    ON membership_event(cluster_id, group_name, id DESC);
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);

-- One row per (binding, Group subject). Current state, replaced each refresh: a binding
-- is fully re-readable from the API, so nothing here is irreplaceable history.
CREATE TABLE IF NOT EXISTS rbac_group_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,   -- Role | ClusterRole
    role_name           TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
);
CREATE INDEX IF NOT EXISTS rbac_binding_by_group
    ON rbac_group_binding(cluster_id, group_name);

-- Provenance: group names we have EVER seen carrying an operator sync-provider label.
-- This is what separates "this binding's group broke" from "this binding names something
-- that never existed". Append-only and never replaced — the whole point is that it
-- outlives the Group object's disappearance.
CREATE TABLE IF NOT EXISTS managed_group_seen (
    cluster_id          TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    sync_provider       TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    PRIMARY KEY(cluster_id, group_name)
);

-- Who used the dashboard, aggregated to one row per user per UTC day.
--
-- Deliberately NOT a per-request access log. Aggregating bounds the table at
-- users x days — a hundred users for three years is ~110k rows — where a request log grows
-- without limit and would need the retention policy the event tables still lack. It also
-- keeps this to "who uses this and when", not "who looked at whose membership": the
-- dashboard shows group membership, and a page-view trail of colleagues reading it is a
-- materially different thing to hold.
--
-- Identity comes from the oauth-proxy's X-Forwarded-User header, so rows exist only when
-- the proxy is enabled. With it disabled the app binds 0.0.0.0 with no authentication at
-- all and the header would be trivially forgeable — see activity.py.
CREATE TABLE IF NOT EXISTS dashboard_user_activity (
    user_name           TEXT NOT NULL,
    day                 TEXT NOT NULL,  -- UTC date, YYYY-MM-DD
    email               TEXT,
    first_seen_at       TEXT NOT NULL,
    last_seen_at        TEXT NOT NULL,
    request_count       INTEGER NOT NULL,
    PRIMARY KEY(user_name, day)
);
CREATE INDEX IF NOT EXISTS dashboard_user_activity_by_day
    ON dashboard_user_activity(day DESC);
"""


_PRAGMA_WORDS = {"OFF", "NORMAL", "FULL", "EXTRA"}


def _safe_pragma_word(value: str, default: str) -> str:
    """PRAGMA takes no bound parameters, so its argument is interpolated — allowlist it."""
    word = str(value).strip().upper()
    if word not in _PRAGMA_WORDS:
        log.warning("ignoring unsupported synchronous=%r, using %s", value, default)
        return default
    return word


# `now_iso` is imported at the top and therefore still re-exported from this module for any
# caller that has not moved. Its definition lives in gsd/timeutil.py: it was never a storage
# concern, and keeping it here meant a service split would need the SQLite module just to
# stamp a timestamp.
__all__ = ["Store", "now_iso"]


class Store:
    """SQLite with one writer connection and a reader per thread.

    The locking story has three parts, and all three have to hold or reads stall behind the
    60s bulk write:

    1. WAL, so readers never block on the writer. Verified rather than assumed — see below.
    2. `busy_timeout`, so a connection that does hit contention WAITS instead of failing.
       SQLite's default is 0: it raises "database is locked" the instant a lock is held,
       with no retry at all. That default is the single most common cause of the error.
    3. A checkpoint that actually runs, so the WAL does not grow without bound.
    """

    def __init__(
        self,
        path: str,
        busy_timeout_ms: int = 5000,
        reader_busy_timeout_ms: int = 2000,
        synchronous: str = "NORMAL",
        wal_checkpoint_mb: float = 8.0,
    ):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        # Readers get a SHORTER budget than the writer on purpose: /readyz performs a read
        # and the probe gives up at 5s, so a reader inheriting the writer's 5s would turn
        # a moment of contention into a failed probe and a restarted pod.
        self.reader_busy_timeout_ms = reader_busy_timeout_ms
        self.wal_checkpoint_bytes = int(wal_checkpoint_mb * 1024 * 1024)
        self._checkpoint_busy_total = 0
        self._lock = threading.RLock()
        self._local = threading.local()

        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

        # PRAGMA journal_mode returns the mode actually in force, which is NOT always the one
        # requested. WAL coordinates readers and writers through an mmap'd -shm file, so on a
        # filesystem without working shared memory or POSIX locks — NFS, EFS, SMB, most RWX
        # network storage — SQLite refuses the switch and stays in rollback-journal mode.
        # It does that SILENTLY, and the consequence is not subtle: in rollback mode a reader
        # blocks for the whole duration of the writer's transaction, so every API request
        # queues behind the bulk poll. Read it back and say so, because the alternative is
        # diagnosing that from latency graphs.
        self._journal_mode = str(
            self._conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        ).lower()
        if path != ":memory:" and self._journal_mode != "wal":
            log.error(
                "SQLite is in %r mode, not WAL — the filesystem under %s does not support it. "
                "Readers will now BLOCK on every write. This is expected on NFS/EFS/SMB and "
                "is why network storage is not supported for the database file.",
                self._journal_mode,
                path,
            )

        self._conn.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
        # NORMAL is the documented companion to WAL: commits stop fsyncing, and a power loss
        # can lose the most recent transactions but CANNOT corrupt the database. The exposure
        # is one poll interval of history; the alternative is an fsync on every commit of a
        # 50k-row refresh. Set GSD_SQLITE_SYNCHRONOUS=FULL if that trade is wrong for you.
        self._conn.execute(f"PRAGMA synchronous={_safe_pragma_word(synchronous, 'NORMAL')}")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        # Under the lock: closing while another thread is mid-transaction would
        # otherwise raise from inside that thread rather than here.
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """Serialise whole transactions, not just statements.

        One connection is shared by a poller thread PER CLUSTER plus every API handler.
        Python's sqlite3 serialises individual statement execution, but NOT the multi-
        statement transaction boundary this block spans — so without the lock, two poller
        threads can interleave inside `with self._conn:` and one thread's commit can commit
        the other's half-written work, or a rollback discard it.

        Latent while only one cluster is configured (the default deployment), real the
        moment a second is added.

        RLock avoids a self-deadlock if _tx is ever nested, but nesting would still be
        WRONG: the inner ``with self._conn`` commits the shared transaction when it exits,
        so the outer block's remaining work would land outside it. Do not nest _tx.
        """
        with self._lock, self._conn:
            yield self._conn

    def _reader(self) -> sqlite3.Connection:
        """A per-thread READ connection, separate from the writer's.

        WAL gives such a connection a consistent snapshot of committed data without taking
        the writer's lock, which fixes both problems at once: it cannot observe a half-
        written transaction, and it does not queue behind one.

        The previous approach — every read taking the write lock — was correct but
        serialising. Measured against a 50k-row binding refresh, exactly ONE read completed
        for the whole duration of the write, at 0.92s on fast local storage. /readyz does a
        read and has a 5s timeout, so on slower storage the pod goes NotReady during a
        routine refresh while /healthz stays green — an outage caused by the fix for a
        different bug.

        `:memory:` is the exception and must keep using the shared connection: each
        connection to `:memory:` is its OWN empty database, so a separate reader would see
        nothing at all. Tests use it; the deployment uses a file.
        """
        if self.path == ":memory:":
            return self._conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            # Every connection needs its OWN busy_timeout — it is connection state, not a
            # property of the database, so the writer's setting does not reach these.
            conn.execute(f"PRAGMA busy_timeout={int(self.reader_busy_timeout_ms)}")
            self._local.conn = conn
        return conn

    def _wal_bytes(self) -> int:
        """Size of the -wal sidecar, or 0 when there is none (`:memory:`, or rollback mode)."""
        if self.path == ":memory:":
            return 0
        try:
            return os.path.getsize(self.path + "-wal")
        except OSError:
            return 0

    def _checkpoint(self) -> tuple[int, int, int] | None:
        """Truncate the WAL once it exceeds the threshold. Returns (busy, log, moved).

        SQLite auto-checkpoints when the WAL passes ~1000 pages, but that runs PASSIVE: it
        copies what it can and gives up the moment a reader holds an older snapshot open.
        Under a steady trickle of API reads "gives up" can be every single time, and then the
        WAL grows without bound while the database file itself stays small. The failure
        surfaces as a FULL VOLUME, not as a database error — which is why the size is also
        exported as a metric rather than only acted on here.

        TRUNCATE waits for readers and then returns the file to zero. It is called from the
        poller thread after a cycle, never from a request, so the wait costs no user latency.
        A busy result is not an error: it means readers were active, and the next cycle
        retries. It IS worth counting, because a busy result EVERY cycle is the starvation
        case and the metric is how you would ever notice.
        """
        if self.path == ":memory:" or self._journal_mode != "wal":
            return None
        if self._wal_bytes() < self.wal_checkpoint_bytes:
            return None
        with self._lock:
            row = self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy, log_frames, moved = int(row[0]), int(row[1]), int(row[2])
        if busy:
            self._checkpoint_busy_total += 1
            log.warning(
                "WAL checkpoint blocked by an open reader (%d frames, %.1f MiB); will retry "
                "next cycle",
                log_frames,
                self._wal_bytes() / 1048576,
            )
        else:
            log.debug("WAL checkpointed: %d frames reclaimed", moved)
        return busy, log_frames, moved

    # -- the engine-neutral half of the seam ---------------------------------------------
    #
    # These two are what the poller and the metrics collector are allowed to call. They
    # used to call wal_bytes(), maybe_checkpoint() and read .journal_mode directly, which
    # meant both of them knew the database was SQLite — the leak that made the "decoupled"
    # claim untrue. See gsd/storage.py.

    def maintain(self) -> None:
        """Periodic upkeep after a write cycle. For SQLite, a WAL checkpoint.

        Returns nothing. It briefly returned a dict describing the checkpoint, which the
        only caller discarded — a contract that implied a signal it did not deliver. The
        durable signal is the starved-checkpoint count, which is cumulative and reported
        through health() where a scrape can read it.
        """
        self._checkpoint()

    def health(self) -> StorageHealth:
        """Engine-reported operational facts, namespaced under the engine that produced them.

        Not a flat dict. A flat one was described as engine-neutral and was not: the
        collector still had to know `wal_bytes`, `wal_enabled` and `checkpoint_busy_total`
        by name, so the coupling had moved from attributes to string literals. Worse, a
        backend without a WAL would omit `wal_enabled` and a defaulting caller would read
        False — which means "the filesystem refused WAL" and fires an alert on a healthy
        database.
        """
        return {
            "engine": "sqlite",
            "sqlite": {
                "wal_enabled": self._journal_mode == "wal",
                "wal_bytes": self._wal_bytes(),
                "checkpoint_busy_total": self._checkpoint_busy_total,
            },
        }

    def _rows(self, sql: str, params: tuple | list = ()) -> list[dict]:
        """Run a read on the per-thread reader (or under the lock for :memory:).

        Reads share the writer's connection, so they see its UNCOMMITTED state. Without
        this lock a reader can land inside the delete/insert window of
        ``replace_group_state`` and observe a partially-populated table — measured at
        40030 of 40419 concurrent reads returning a wrong count, including zero groups.
        Reporting "0 groups" while a poll is in flight is precisely the false
        everything-vanished alarm this dashboard exists to avoid raising.

        Every read goes through here or _row; a bare ``self._conn.execute`` in a query
        method is a bug.
        """
        if self.path == ":memory:":
            with self._lock:
                return [dict(r) for r in self._conn.execute(sql, params).fetchall()]
        return [dict(r) for r in self._reader().execute(sql, params).fetchall()]

    def _row(self, sql: str, params: tuple | list = ()) -> dict | None:
        if self.path == ":memory:":
            with self._lock:
                row = self._conn.execute(sql, params).fetchone()
        else:
            row = self._reader().execute(sql, params).fetchone()
        return dict(row) if row else None

    # -- configuration -----------------------------------------------------------------

    def upsert_cluster(self, cluster_id: str, api_url: str, enabled: bool) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO cluster(id, api_url, enabled) VALUES(?,?,?)
                   ON CONFLICT(id) DO UPDATE SET api_url=excluded.api_url,
                                                 enabled=excluded.enabled""",
                (cluster_id, api_url, int(enabled)),
            )

    def clusters(self) -> list[dict]:
        return self._rows(
            """SELECT c.id, c.api_url, c.enabled,
                      p.status, p.message, p.observed_at AS last_poll
                 FROM cluster c LEFT JOIN poll_outcome p ON p.cluster_id = c.id
                ORDER BY c.id"""
        )

    # -- poll results ------------------------------------------------------------------

    def record_poll(self, cluster_id: str, status: str, message: str | None) -> None:
        with self._tx() as conn:
            conn.execute(
                """INSERT INTO poll_outcome(cluster_id, observed_at, status, message)
                   VALUES(?,?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET observed_at=excluded.observed_at,
                                                          status=excluded.status,
                                                          message=excluded.message""",
                (cluster_id, now_iso(), status, message),
            )

    def record_sync_event(
        self,
        cluster_id: str,
        name: str,
        namespace: str,
        synced_at: str,
        observed_at: str,
        schedule: str | None,
        group_count: int,
    ) -> bool:
        """Insert one observed sync. Returns True if this was a new event.

        The UNIQUE constraint makes this idempotent, so polling faster than the schedule
        costs nothing (PLAN §10) — re-observing the same lastSyncSuccessTime is a no-op
        rather than a duplicate timeline entry.
        """
        with self._tx() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO sync_event(
                       cluster_id, groupsync_name, groupsync_namespace,
                       synced_at, observed_at, schedule, group_count)
                   VALUES(?,?,?,?,?,?,?)""",
                (cluster_id, name, namespace, synced_at, observed_at, schedule, group_count),
            )
            return cursor.rowcount > 0

    def replace_groupsync_state(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's CR rows and their provider attributions together.

        Both in ONE transaction: a CR whose state is visible while its providers are not
        owns nothing for the duration, and every one of its groups would read as
        unattributed — a burst of phantom findings on each poll.
        """
        with self._tx() as conn:
            conn.execute("DELETE FROM groupsync_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_state(cluster_id, name, namespace, schedule,
                       ldap_filter, last_sync_at, generation, observed_at)
                   VALUES(:cluster_id,:name,:namespace,:schedule,:ldap_filter,
                          :last_sync_at,:generation,:observed_at)""",
                [
                    {k: v for k, v in r.items() if k != "provider_keys"}
                    | {"cluster_id": cluster_id, "observed_at": observed_at}
                    for r in rows
                ],
            )
            conn.execute("DELETE FROM groupsync_provider WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_provider(
                       cluster_id, groupsync_name, groupsync_namespace, provider_key)
                   VALUES(?,?,?,?)""",
                [
                    (cluster_id, r["name"], r["namespace"], key)
                    for r in rows
                    for key in r.get("provider_keys") or []
                ],
            )

    def replace_group_state(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's group rows wholesale.

        Delete-then-insert inside one transaction, so a group that disappeared upstream also
        disappears here — an upsert would leave deleted groups behind forever and quietly
        inflate every count on the overview.
        """
        with self._tx() as conn:
            conn.execute("DELETE FROM group_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO group_state(cluster_id, name, member_count, sync_provider,
                       group_synced_at, ldap_uid, observed_at)
                   VALUES(:cluster_id,:name,:member_count,:sync_provider,
                          :group_synced_at,:ldap_uid,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )

    def sync_members(
        self,
        cluster_id: str,
        memberships: dict[str, list[str]],
        sync_times: dict[str, str | None],
        observed_at: str,
    ) -> int:
        """Reconcile observed membership and append an event for every change.

        ``memberships`` MUST be the complete map for this cluster — every group and every
        member seen in the poll. Any group absent from it is treated as deleted upstream and
        its members are recorded as departures. Passing a partial map (say, one group at a
        time) therefore silently empties every group you left out.

        Diff-and-append rather than replace: the replace strategy used for `group_state`
        would be wrong here, because it destroys `first_seen_at` and can record no history.
        The whole value of this table is the two questions the API cannot answer — when did
        this user join, and who quietly disappeared.

        Returns the number of change events written.
        """
        changes = 0
        with self._tx() as conn:
            existing: dict[str, set[str]] = {}
            for row in conn.execute(
                "SELECT group_name, user_name FROM group_member WHERE cluster_id=?",
                (cluster_id,),
            ):
                existing.setdefault(row["group_name"], set()).add(row["user_name"])

            for group, members in memberships.items():
                observed = set(members)
                known = existing.get(group, set())
                synced_at = sync_times.get(group)

                for user in sorted(observed - known):
                    conn.execute(
                        """INSERT INTO group_member(cluster_id, group_name, user_name,
                               first_seen_at, last_seen_at)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(cluster_id, group_name, user_name)
                           DO UPDATE SET last_seen_at=excluded.last_seen_at""",
                        (cluster_id, group, user, observed_at, observed_at),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at)
                           VALUES(?,?,?,'added',?,?)""",
                        (cluster_id, group, user, observed_at, synced_at),
                    )
                    changes += 1

                # Chunked because SQLITE_LIMIT_VARIABLE_NUMBER is per-statement and varies by
                # build: 32766 in the UBI9 runtime (SQLite 3.34.1) but 250000 on a dev Mac
                # (3.53.0). An unchunked IN-list therefore passes every local test and then
                # raises "too many SQL variables" in production on a group with >32k members,
                # which a large LDAP directory can genuinely have.
                observed_users = sorted(observed)
                for start in range(0, len(observed_users), 500):
                    batch = observed_users[start:start + 500]
                    conn.execute(
                        f"""UPDATE group_member SET last_seen_at=?
                             WHERE cluster_id=? AND group_name=?
                               AND user_name IN ({','.join('?' * len(batch))})""",
                        (observed_at, cluster_id, group, *batch),
                    )

                for user in sorted(known - observed):
                    conn.execute(
                        "DELETE FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
                        (cluster_id, group, user),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at)
                           VALUES(?,?,?,'removed',?,?)""",
                        (cluster_id, group, user, observed_at, synced_at),
                    )
                    changes += 1

            # A group deleted upstream takes its membership with it, and each departure is
            # recorded — otherwise the members simply vanish from the store with no trace.
            for group in set(existing) - set(memberships):
                for user in sorted(existing[group]):
                    conn.execute(
                        "DELETE FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
                        (cluster_id, group, user),
                    )
                    conn.execute(
                        """INSERT INTO membership_event(cluster_id, group_name, user_name,
                               change, observed_at, group_synced_at)
                           VALUES(?,?,?,'removed',?,NULL)""",
                        (cluster_id, group, user, observed_at),
                    )
                    changes += 1
        return changes

    def group_members(self, cluster_id: str, group_name: str) -> list[dict]:
        """Current members, with BOTH the current and the original join date.

        `first_seen_at` resets when a user leaves and rejoins, because the row is deleted
        and reinserted — that is correct for "how long has this access been continuous?",
        but on its own it silently overwrites the original grant date, which is the one an
        auditor asking "when did this person get access?" actually wants.

        The original is recovered from membership_event, which is append-only and keeps
        every join even across removals — so no schema change is needed to answer both.
        """
        return self._rows(
                """SELECT m.user_name, m.first_seen_at, m.last_seen_at,
                          (SELECT MIN(e.observed_at) FROM membership_event e
                            WHERE e.cluster_id = m.cluster_id
                              AND e.group_name = m.group_name
                              AND e.user_name  = m.user_name
                              AND e.change = 'added') AS original_first_seen_at
                     FROM group_member m
                    WHERE m.cluster_id=? AND m.group_name=?
                    ORDER BY m.user_name""",
                (cluster_id, group_name),
        )

    def group_detail(self, cluster_id: str, group_name: str) -> dict | None:
        row = self._row(
            """SELECT name, member_count, sync_provider, group_synced_at, ldap_uid, observed_at
                 FROM group_state WHERE cluster_id=? AND name=?""",
            (cluster_id, group_name),
        )
        return dict(row) if row else None

    def membership_events(
        self, cluster_id: str, group_name: str | None = None,
        user_name: str | None = None, limit: int = 200,
    ) -> list[dict]:
        sql = """SELECT group_name, user_name, change, observed_at, group_synced_at
                   FROM membership_event WHERE cluster_id=?"""
        params: list = [cluster_id]
        if group_name:
            sql += " AND group_name=?"
            params.append(group_name)
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def user_groups(self, cluster_id: str, user_name: str) -> list[dict]:
        """Every group a user belongs to — the reverse lookup.

        This is the "why does this person have access?" question, which the cluster can only
        answer by scanning every Group object by hand.
        """
        return self._rows(
                """SELECT m.group_name, m.first_seen_at, m.last_seen_at, g.sync_provider
                     FROM group_member m
                     LEFT JOIN group_state g
                            ON g.cluster_id = m.cluster_id AND g.name = m.group_name
                    WHERE m.cluster_id=? AND m.user_name=?
                    ORDER BY m.group_name""",
                (cluster_id, user_name),
        )

    def users(self, cluster_id: str) -> list[dict]:
        return self._rows(
                """SELECT user_name, COUNT(*) AS group_count, MIN(first_seen_at) AS first_seen_at
                     FROM group_member WHERE cluster_id=?
                    GROUP BY user_name ORDER BY user_name""",
                (cluster_id,),
        )

    # -- RBAC bindings -----------------------------------------------------------------

    def replace_bindings(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's binding rows wholesale, in one transaction."""
        with self._tx() as conn:
            conn.execute("DELETE FROM rbac_group_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO rbac_group_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, group_name, observed_at)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:group_name,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )

    def record_managed_groups(
        self, cluster_id: str, groups: list[dict], observed_at: str
    ) -> None:
        """Remember which groups the operator manages, so their later absence is meaningful.

        Only groups carrying a sync-provider label are recorded. A group we have never seen
        managed cannot later be called a broken binding — at most an unresolved one.
        """
        managed = [g for g in groups if g.get("sync_provider")]
        if not managed:
            return
        with self._tx() as conn:
            conn.executemany(
                """INSERT INTO managed_group_seen(
                       cluster_id, group_name, sync_provider, first_seen_at, last_seen_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cluster_id, group_name) DO UPDATE SET
                       sync_provider=excluded.sync_provider,
                       last_seen_at=excluded.last_seen_at""",
                [
                    (cluster_id, g["name"], g["sync_provider"], observed_at, observed_at)
                    for g in managed
                ],
            )

    def group_bindings(self, cluster_id: str, group_name: str) -> list[dict]:
        """Direct role bindings naming this group. NOT effective permissions."""
        return self._rows(
            """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name
                 FROM rbac_group_binding
                WHERE cluster_id=? AND group_name=?
                ORDER BY binding_kind, binding_namespace, binding_name""",
            (cluster_id, group_name),
        )

    def user_bindings(self, cluster_id: str, user_name: str) -> list[dict]:
        """Every binding reachable by this user THROUGH their current group memberships.

        `via_group` is carried on every row: without it the user page would assert access
        with no way to see which membership confers it, which is the first thing anyone
        asks when revoking it.
        """
        return self._rows(
            """SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name AS via_group
                 FROM group_member m
                 JOIN rbac_group_binding b
                   ON b.cluster_id = m.cluster_id AND b.group_name = m.group_name
                WHERE m.cluster_id=? AND m.user_name=?
                ORDER BY b.binding_kind, b.binding_namespace, b.binding_name""",
            (cluster_id, user_name),
        )

    def binding_findings(self, cluster_id: str) -> list[dict]:
        """Classify every binding whose Group subject has no Group object.

        Three tiers, because two would be useless here. On the target cluster 110 of 149
        distinct Group subjects are built-in virtual groups; lumping those in with real
        problems gives 119 findings of which 9 matter, and a list that is 92% noise is one
        operators stop reading.

            built_in    system:* — virtual, authorises real access, no object expected
            dangling    was observed operator-managed, now absent -> something broke
            unresolved  never seen managed -> names a group that has never existed

        `dangling` is the high-confidence tier and is the only one that should alert.
        """
        return [r for r in self.all_bindings(cluster_id) if r["finding"] != "ok"]

    def all_bindings(self, cluster_id: str) -> list[dict]:
        """Every group-subject binding, each classified.

        Includes the ones that resolve normally (`ok`). Those are the majority of a healthy
        cluster — 74 of 228 here — and omitting them made a view labelled "Bindings" show
        only the broken subset, which misrepresents what is on the cluster.
        """
        return self._rows(
            """SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name,
                      CASE
                        -- A resolving group is the normal case and outranks everything.
                        WHEN g.name IS NOT NULL            THEN 'ok'
                        -- Provenance FIRST. We watched the operator manage this group, so
                        -- its disappearance is evidence, and evidence outranks a naming
                        -- heuristic. Testing `system:` first silently downgraded a real
                        -- dangling binding to `built_in` whenever a managed group happened
                        -- to carry that prefix — a grants-nobody binding with no alert,
                        -- which is the worst failure this dashboard can have.
                        WHEN s.group_name IS NOT NULL     THEN 'dangling'
                        WHEN b.group_name LIKE 'system:%' THEN 'built_in'
                        ELSE 'unresolved'
                      END AS finding
                 FROM rbac_group_binding b
                 LEFT JOIN group_state g
                        ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                 LEFT JOIN managed_group_seen s
                        ON s.cluster_id = b.cluster_id AND s.group_name = b.group_name
                WHERE b.cluster_id = ?
                ORDER BY b.group_name, b.binding_kind, b.binding_namespace, b.binding_name""",
            (cluster_id,),
        )

    def upsert_reconcile_error(
        self,
        cluster_id: str,
        name: str,
        failed_at: str | None,
        generation: int | None,
        message: str | None,
    ) -> None:
        with self._tx() as conn:
            if failed_at is None:
                conn.execute(
                    "DELETE FROM reconcile_error WHERE cluster_id=? AND groupsync_name=?",
                    (cluster_id, name),
                )
                return
            conn.execute(
                """INSERT INTO reconcile_error(cluster_id, groupsync_name, failed_at,
                       observed_generation, message)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(cluster_id, groupsync_name) DO UPDATE SET
                       failed_at=excluded.failed_at,
                       observed_generation=excluded.observed_generation,
                       message=excluded.message""",
                (cluster_id, name, failed_at, generation, message),
            )

    # -- dashboard access ----------------------------------------------------------------

    def record_user_activity(self, buckets: list[dict]) -> int:
        """Merge buffered per-user-per-day activity. Returns the number of buckets written.

        One transaction for the whole flush, not one per user: this runs while the poller
        may be mid-cycle, and taking the write lock once for a handful of rows keeps it out
        of the way. Callers buffer in memory and flush on an interval — see activity.py for
        why a write per request is the wrong shape.

        first/last_seen use SQLite's two-argument min/max rather than the caller's values,
        so a flush that arrives out of order — a slow flush overtaken by a later one — still
        widens the window instead of narrowing it. Lexicographic comparison IS chronological
        here because now_iso() emits fixed-width UTC with a Z suffix.
        """
        if not buckets:
            return 0
        with self._tx() as conn:
            conn.executemany(
                """INSERT INTO dashboard_user_activity(
                       user_name, day, email, first_seen_at, last_seen_at, request_count)
                   VALUES(:user_name,:day,:email,:first_seen_at,:last_seen_at,:request_count)
                   ON CONFLICT(user_name, day) DO UPDATE SET
                       email         = COALESCE(excluded.email, email),
                       first_seen_at = min(first_seen_at, excluded.first_seen_at),
                       last_seen_at  = max(last_seen_at, excluded.last_seen_at),
                       request_count = request_count + excluded.request_count""",
                buckets,
            )
        return len(buckets)

    def prune_user_activity(self, before_day: str) -> int:
        """Drop activity rows for days strictly before ``before_day`` (YYYY-MM-DD)."""
        with self._tx() as conn:
            cursor = conn.execute(
                "DELETE FROM dashboard_user_activity WHERE day < ?", (before_day,)
            )
            return cursor.rowcount

    def user_activity(
        self,
        since_day: str | None = None,
        limit: int = 500,
        user_name: str | None = None,
    ) -> list[dict]:
        """Activity rows, optionally narrowed to one user.

        `user_name` is the privacy scope, not a convenience filter: the API passes the
        authenticated viewer's own name unless the deployment has opted into showing
        everyone. Filtering in SQL rather than after the fetch matters — `limit` is applied
        by the database, so filtering afterwards would silently return fewer than `limit`
        of the caller's own rows whenever busier colleagues filled the page.
        """
        sql = """SELECT user_name, day, email, first_seen_at, last_seen_at, request_count
                   FROM dashboard_user_activity"""
        where, params = [], []
        if since_day:
            where.append("day >= ?")
            params.append(since_day)
        if user_name:
            where.append("user_name = ?")
            params.append(user_name)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY day DESC, user_name LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def active_user_count(self, day: str) -> int:
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM dashboard_user_activity WHERE day = ?", (day,)
        )
        return int(rows[0]["n"]) if rows else 0

    # -- queries -----------------------------------------------------------------------

    def groupsyncs(self, cluster_id: str) -> list[dict]:
        """Current CR state, each row carrying the full list of provider keys it owns.

        `provider_keys` is stitched in from a second read rather than GROUP_CONCAT'd: the
        callers need a list to test membership against, and building one by splitting a
        delimited string means picking a delimiter that a label value can never contain.
        Two reads of a handful of rows is the cheaper correctness.
        """
        rows = self._rows(
            """SELECT g.name, g.namespace, g.schedule, g.ldap_filter, g.last_sync_at,
                      g.generation, g.observed_at,
                      e.failed_at AS error_at, e.message AS error_message,
                      e.observed_generation AS error_generation,
                      (SELECT COUNT(*) FROM group_state gs
                        WHERE gs.cluster_id = g.cluster_id
                          AND gs.sync_provider IN (
                              SELECT p.provider_key FROM groupsync_provider p
                               WHERE p.cluster_id = g.cluster_id
                                 AND p.groupsync_name = g.name
                                 AND p.groupsync_namespace = g.namespace)) AS group_count
                 FROM groupsync_state g
                 LEFT JOIN reconcile_error e
                        ON e.cluster_id = g.cluster_id AND e.groupsync_name = g.name
                WHERE g.cluster_id = ?
                ORDER BY g.name""",
            (cluster_id,),
        )
        keys: dict[tuple[str, str], list[str]] = {}
        for p in self._rows(
            """SELECT groupsync_name, groupsync_namespace, provider_key
                 FROM groupsync_provider WHERE cluster_id=?
                ORDER BY provider_key""",
            (cluster_id,),
        ):
            keys.setdefault((p["groupsync_name"], p["groupsync_namespace"]), []).append(
                p["provider_key"]
            )
        for row in rows:
            row["provider_keys"] = keys.get((row["name"], row["namespace"]), [])
        return rows

    def sync_events(self, cluster_id: str, name: str, since: str | None, limit: int) -> list[dict]:
        sql = """SELECT synced_at, observed_at, schedule, group_count
                   FROM sync_event
                  WHERE cluster_id=? AND groupsync_name=?"""
        params: list = [cluster_id, name]
        if since:
            sql += " AND synced_at >= ?"
            params.append(since)
        sql += " ORDER BY synced_at DESC LIMIT ?"
        params.append(limit)
        return self._rows(sql, params)

    def groups(self, cluster_id: str, state: str = "all") -> list[dict]:
        sql = """SELECT name, member_count, sync_provider, group_synced_at, ldap_uid,
                        observed_at
                   FROM group_state WHERE cluster_id=?"""
        params: list = [cluster_id]
        if state == "empty":
            # PLAN §7 defines EMPTY as "synced, zero members" — an operator-managed group
            # whose members vanished, which points at the LDAP side. A hand-made group with
            # no members is not that; it is UNATTRIBUTED, and reporting it here would both
            # double-count it and describe it wrongly.
            sql += " AND member_count = 0 AND sync_provider IS NOT NULL"
        elif state == "unattributed":
            sql += " AND sync_provider IS NULL"
        elif state != "all":
            raise ValueError(f"unknown group state filter {state!r}")
        sql += " ORDER BY name"
        return self._rows(sql, params)

    def group_counts(self, cluster_id: str) -> dict:
        row = self._row(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN member_count = 0 AND sync_provider IS NOT NULL
                               THEN 1 ELSE 0 END) AS empty,
                      SUM(CASE WHEN sync_provider IS NULL THEN 1 ELSE 0 END) AS unattributed
                 FROM group_state WHERE cluster_id=?""",
            (cluster_id,),
        )
        return {
            "total": row["total"] or 0,
            "empty": row["empty"] or 0,
            "unattributed": row["unattributed"] or 0,
        }

    def oldest_last_sync(self, cluster_id: str) -> str | None:
        row = self._row(
            """SELECT MIN(last_sync_at) AS oldest FROM groupsync_state
                WHERE cluster_id=? AND last_sync_at IS NOT NULL""",
            (cluster_id,),
        )
        return row["oldest"] if row else None
