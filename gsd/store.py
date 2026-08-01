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

import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

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
    provider_key        TEXT,           -- the sync-provider label value its groups carry
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, name, namespace)
);

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
"""


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
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
        moment a second is added. RLock rather than Lock so a future nested _tx cannot
        self-deadlock.
        """
        with self._lock, self._conn:
            yield self._conn

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
        rows = self._conn.execute(
            """SELECT c.id, c.api_url, c.enabled,
                      p.status, p.message, p.observed_at AS last_poll
                 FROM cluster c LEFT JOIN poll_outcome p ON p.cluster_id = c.id
                ORDER BY c.id"""
        ).fetchall()
        return [dict(r) for r in rows]

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
        with self._tx() as conn:
            conn.execute("DELETE FROM groupsync_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_state(cluster_id, name, namespace, schedule,
                       ldap_filter, last_sync_at, generation, provider_key, observed_at)
                   VALUES(:cluster_id,:name,:namespace,:schedule,:ldap_filter,
                          :last_sync_at,:generation,:provider_key,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
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
        return [
            dict(r)
            for r in self._conn.execute(
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
        ]

    def group_detail(self, cluster_id: str, group_name: str) -> dict | None:
        row = self._conn.execute(
            """SELECT name, member_count, sync_provider, group_synced_at, ldap_uid, observed_at
                 FROM group_state WHERE cluster_id=? AND name=?""",
            (cluster_id, group_name),
        ).fetchone()
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
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def user_groups(self, cluster_id: str, user_name: str) -> list[dict]:
        """Every group a user belongs to — the reverse lookup.

        This is the "why does this person have access?" question, which the cluster can only
        answer by scanning every Group object by hand.
        """
        return [
            dict(r)
            for r in self._conn.execute(
                """SELECT m.group_name, m.first_seen_at, m.last_seen_at, g.sync_provider
                     FROM group_member m
                     LEFT JOIN group_state g
                            ON g.cluster_id = m.cluster_id AND g.name = m.group_name
                    WHERE m.cluster_id=? AND m.user_name=?
                    ORDER BY m.group_name""",
                (cluster_id, user_name),
            )
        ]

    def users(self, cluster_id: str) -> list[dict]:
        return [
            dict(r)
            for r in self._conn.execute(
                """SELECT user_name, COUNT(*) AS group_count, MIN(first_seen_at) AS first_seen_at
                     FROM group_member WHERE cluster_id=?
                    GROUP BY user_name ORDER BY user_name""",
                (cluster_id,),
            )
        ]

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

    # -- queries -----------------------------------------------------------------------

    def groupsyncs(self, cluster_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT g.name, g.namespace, g.schedule, g.ldap_filter, g.last_sync_at,
                      g.generation, g.provider_key, g.observed_at,
                      e.failed_at AS error_at, e.message AS error_message,
                      e.observed_generation AS error_generation,
                      (SELECT COUNT(*) FROM group_state gs
                        WHERE gs.cluster_id = g.cluster_id
                          AND gs.sync_provider = g.provider_key) AS group_count
                 FROM groupsync_state g
                 LEFT JOIN reconcile_error e
                        ON e.cluster_id = g.cluster_id AND e.groupsync_name = g.name
                WHERE g.cluster_id = ?
                ORDER BY g.name""",
            (cluster_id,),
        ).fetchall()
        return [dict(r) for r in rows]

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
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

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
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def group_counts(self, cluster_id: str) -> dict:
        row = self._conn.execute(
            """SELECT COUNT(*) AS total,
                      SUM(CASE WHEN member_count = 0 AND sync_provider IS NOT NULL
                               THEN 1 ELSE 0 END) AS empty,
                      SUM(CASE WHEN sync_provider IS NULL THEN 1 ELSE 0 END) AS unattributed
                 FROM group_state WHERE cluster_id=?""",
            (cluster_id,),
        ).fetchone()
        return {
            "total": row["total"] or 0,
            "empty": row["empty"] or 0,
            "unattributed": row["unattributed"] or 0,
        }

    def oldest_last_sync(self, cluster_id: str) -> str | None:
        row = self._conn.execute(
            """SELECT MIN(last_sync_at) AS oldest FROM groupsync_state
                WHERE cluster_id=? AND last_sync_at IS NOT NULL""",
            (cluster_id,),
        ).fetchone()
        return row["oldest"] if row else None
