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

-- Display names for users who have logged in. ONE row per person, joined onto the tables that
-- name them — deliberately not a column on group_member or user_binding, both of which are
-- per-membership and per-binding, so a name there would duplicate N times per person. On
-- group_member it would also outlive its truth: that table is diff-and-append so first_seen_at
-- survives, meaning a name removed upstream would never be cleared.
--
-- Only names that are SET are stored. A User with an empty fullName is downstream-identical to
-- no User at all, so the absent row is the single representation of "no name to show" and every
-- read is an outer join that yields NULL.
--
-- Wholly replaced each poll, like group_state and user_binding: an upsert would leave a name
-- behind after the User object is deleted. The poller skips the replace entirely when the fetch
-- was forbidden, so a missing RBAC grant costs nothing already known.
CREATE TABLE IF NOT EXISTS ocp_user (
    cluster_id          TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    full_name           TEXT NOT NULL,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, user_name)
);

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
    -- Provenance (migration 1). managed_source is the policy operator's config-source
    -- label; NULL means hand-made. exception is the operator-acknowledged justification
    -- for a deliberate hand-made binding, carried as an annotation on the object itself.
    managed_source      TEXT,
    exception           TEXT,
    -- Migration 2: whether the object already carries the dashboard's own unmanaged
    -- audit label — read back from the cluster each refresh, so it is the cluster's
    -- truth, not a local counter that can drift from it.
    audit_stamped       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
);

-- Bindings that name a USER directly, rather than a group. Replaced each refresh.
--
-- The governance violation in its purest form: access tied to a person instead of to an
-- enterprise-managed group. It survives offboarding — removing someone from an LDAP group
-- revokes their access everywhere, while a direct binding keeps granting to a name nobody
-- reviews — and it is invisible to every group-based audit, this dashboard's own included
-- until now.
--
-- is_platform separates cluster-internal identities (system:*, kube-apiserver, the node
-- identities) from people. Measured on the reference cluster: 36 direct-user bindings, 22
-- of them platform. They are STORED rather than filtered at ingest so the UI can report
-- what it excluded — a tool that silently drops rows cannot be trusted about the ones it
-- keeps.
CREATE TABLE IF NOT EXISTS user_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,
    role_name           TEXT NOT NULL,
    user_name           TEXT NOT NULL,
    is_platform         INTEGER NOT NULL DEFAULT 0,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, user_name)
);
CREATE INDEX IF NOT EXISTS user_binding_by_namespace
    ON user_binding(cluster_id, binding_namespace);

-- Health of the namespace-configuration-operator's CRs, replaced on the binding cadence.
-- Reconcile conditions ONLY: these CRs template the RoleBindings that give synced groups
-- their access, so a failing one means RBAC silently stops reconciling — but they have no
-- schedule, so there is no staleness to compute and no timeline worth accumulating.
CREATE TABLE IF NOT EXISTS operator_config_state (
    cluster_id          TEXT NOT NULL,
    kind                TEXT NOT NULL,   -- NamespaceConfig | GroupConfig
    name                TEXT NOT NULL,
    error_at            TEXT,
    error_message       TEXT,
    success_at          TEXT,
    observed_at         TEXT NOT NULL,
    PRIMARY KEY(cluster_id, kind, name)
);

-- Whether the operator's CRDs even exist on the cluster, auto-detected each refresh.
-- Absent (0) is a different truth from "present with zero CRs", and the UI must not
-- render "all healthy" for a concept the cluster does not have.
CREATE TABLE IF NOT EXISTS operator_config_presence (
    cluster_id          TEXT PRIMARY KEY,
    present             INTEGER NOT NULL,
    observed_at         TEXT NOT NULL
);

-- Same question for the group-sync-operator's own CRD. Tracked for the same reason and one
-- more: a cluster with no GroupSync CRD still HAS groups, and the dashboard reports them, so
-- "0 CRs" on the Overview is indistinguishable from "the operator is not installed" unless
-- absence is recorded. It used to be unmissable for the wrong reason — the poll failed and the
-- cluster showed `unreachable` — which hid every group on the cluster.
CREATE TABLE IF NOT EXISTS groupsync_presence (
    cluster_id          TEXT PRIMARY KEY,
    present             INTEGER NOT NULL,
    observed_at         TEXT NOT NULL
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

-- Login attempts read off the oauth-server's logs. One row per ATTEMPT, not per log line: a single
-- attempt writes several lines across two source files, and gsd/loginlog.py correlates them.
--
-- pod_name IS IN THE UNIQUE KEY, and that is the whole point of it. Reads overlap deliberately (a
-- sinceSeconds window plus a settle horizon), so the same line is seen more than once and must not
-- insert twice — the key suppresses that, because a line stays in its own pod's log and is never
-- copied to a peer. Without pod_name the key ALSO collapses the cross-replica same-instant pair: two
-- requests for the same username, same outcome and same microsecond, one served by each replica.
-- Measured in scratch SQLite: (pod-a,alice,T,success), a re-read of it, then the independent
-- (pod-b,alice,T,success) gives [1,0,1] and two rows with pod_name in the key; [1,0,0] and one row
-- without it — a genuine second attempt silently dropped.
--
-- `at` is the kubelet RFC3339 stamp with microseconds, stored UTC and rendered in the configured
-- zone. klog's own stamp on the same line carries no year and no timezone, so it cannot be resolved
-- to an instant without guessing both. `observed_at` is when WE read it — not the same thing, and
-- worth keeping when a pod's clock and ours disagree.
CREATE TABLE IF NOT EXISTS login_event (
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
CREATE INDEX IF NOT EXISTS login_event_lookup ON login_event(cluster_id, at DESC);
CREATE INDEX IF NOT EXISTS login_event_by_user ON login_event(cluster_id, user_name, at DESC);

-- How far each POD's log has been settled. Per pod because pods are read independently and every roll
-- replaces them; one cluster-wide value would let a lagging pod hold back the others, or a fast pod
-- advance past lines a slow one has not written yet.
CREATE TABLE IF NOT EXISTS login_capture_watermark (
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,
    settled_through     TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY(cluster_id, pod_name)
);

-- The PRODUCT-level boundary, deliberately NOT the watermark above.
--
-- `started_at` is the first successful read ever, set once and never moved, because it is what the UI
-- means by "watching since" — a sparse table must read as "nothing happened since then" rather than
-- as "this feature is broken". The per-pod watermark cannot answer that: it is per pod, it moves
-- constantly, and dead-pod rows get pruned, which would erase the evidence of when watching began.
-- `last_read_at` is liveness: if it stops advancing, capture has stopped.
CREATE TABLE IF NOT EXISTS login_capture_status (
    cluster_id          TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    last_read_at        TEXT NOT NULL
);
"""


# -- schema migrations ----------------------------------------------------------------
#
# THIS PROJECT'S FIRST REAL MIGRATION MECHANISM, built because the implicit one silently
# does nothing: the schema is applied with CREATE TABLE IF NOT EXISTS, so on an EXISTING
# database a column added to the SCHEMA string simply never appears — the table already
# exists, the statement no-ops, and the first SELECT naming the new column crashes at
# runtime on upgraded deployments while working perfectly on fresh ones. Measured before
# this existed, not assumed.
#
# PRAGMA user_version is the cursor: 0 on any database created before this mechanism,
# incremented once per applied step. Steps run in order, inside the writer's transaction,
# at startup, before anything reads. They must be written to be safe on a database that
# already has the change (fresh databases get the new SCHEMA and then replay migrations
# against it), which for ALTER TABLE ADD COLUMN means tolerating "duplicate column name".
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (
        1,
        "rbac_group_binding gains provenance: managed_source + exception",
        [
            "ALTER TABLE rbac_group_binding ADD COLUMN managed_source TEXT",
            "ALTER TABLE rbac_group_binding ADD COLUMN exception TEXT",
        ],
    ),
    (
        2,
        "rbac_group_binding records the audit stamp, for stamp idempotency + healing",
        [
            "ALTER TABLE rbac_group_binding ADD COLUMN audit_stamped INTEGER NOT NULL DEFAULT 0",
        ],
    ),
    (
        3,
        "groupsync_presence: is the group-sync-operator's CRD installed at all",
        [
            """CREATE TABLE IF NOT EXISTS groupsync_presence (
                   cluster_id          TEXT PRIMARY KEY,
                   present             INTEGER NOT NULL,
                   observed_at         TEXT NOT NULL
               )""",
            # No backfill row. Absence of a row reads as "not yet observed", which the first
            # poll after upgrade replaces with the truth. Defaulting every existing cluster to
            # present=1 would be a guess, and defaulting to 0 would alert every cluster that
            # upgrades before it next polls.
        ],
    ),
    (
        4,
        "ocp_user: display names for users who have logged in",
        [
            """CREATE TABLE IF NOT EXISTS ocp_user (
                   cluster_id          TEXT NOT NULL,
                   user_name           TEXT NOT NULL,
                   full_name           TEXT NOT NULL,
                   observed_at         TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, user_name)
               )""",
            # IF NOT EXISTS is required, not decorative: _migrate tolerates exactly one error,
            # "duplicate column name", so a bare CREATE TABLE would raise "table already
            # exists" when this replays against a database that got it from SCHEMA.
            #
            # No backfill, and none is possible — the names live on the cluster, not in here.
            # Until the next poll every read outer-joins to NULL, which is the same thing the
            # UI already renders for a user who has never logged in.
        ],
    ),
    (
        5,
        "login_event + capture watermark and status: who logged in, and since when we were watching",
        [
            """CREATE TABLE IF NOT EXISTS login_event (
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
               )""",
            "CREATE INDEX IF NOT EXISTS login_event_lookup ON login_event(cluster_id, at DESC)",
            """CREATE INDEX IF NOT EXISTS login_event_by_user
                   ON login_event(cluster_id, user_name, at DESC)""",
            """CREATE TABLE IF NOT EXISTS login_capture_watermark (
                   cluster_id          TEXT NOT NULL,
                   pod_name            TEXT NOT NULL,
                   settled_through     TEXT NOT NULL,
                   updated_at          TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, pod_name)
               )""",
            """CREATE TABLE IF NOT EXISTS login_capture_status (
                   cluster_id          TEXT PRIMARY KEY,
                   started_at          TEXT NOT NULL,
                   last_read_at        TEXT NOT NULL
               )""",
            # IF NOT EXISTS on every statement is required, not decorative: _migrate tolerates exactly
            # one error, "duplicate column name", so a bare CREATE would raise "table already exists"
            # on the replay against a database that got these from SCHEMA.
            #
            # No backfill, and none is possible — these logs exist only while the pod that wrote them
            # does, and nothing before capture was enabled was ever recorded anywhere. An empty table
            # on an upgraded cluster is the truth, which is exactly why login_capture_status exists:
            # so the UI can say WHEN watching began rather than implying nobody logged in.
        ],
    ),
]


def _migrate(conn: sqlite3.Connection) -> None:
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    for target, title, statements in _MIGRATIONS:
        if version >= target:
            continue
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError as exc:
                # A fresh database already has the column from SCHEMA; replaying the
                # migration against it must be a no-op, not a crash.
                if "duplicate column name" not in str(exc):
                    raise
        conn.execute(f"PRAGMA user_version = {target}")
        log.info("schema migration %d applied: %s", target, title)


_PRAGMA_WORDS = {"OFF", "NORMAL", "FULL", "EXTRA"}


def _harden(conn: sqlite3.Connection) -> None:
    """Drop capabilities this application never uses, on every connection.

    MITIGATES (partially): CVE-2025-70873 — SQLite information disclosure via a crafted
    ZIP file, reachable only through the zipfile extension. Disabling extension loading
    removes the mechanism it needs.

    RELATED, NOT MITIGATED BY THIS: CVE-2024-0232 — use-after-free in
    jsonParseAddNodeArray. It needs SQL JSON functions, which this store does not use
    (zero `json_` / `->>` occurrences); nothing here changes its reachability either way.

    NEITHER IS FIXABLE BY UPGRADING. UBI9 ships exactly one build,
    sqlite-libs-3.34.1-10.el9_8: `microdnf repoquery sqlite-libs` offers no other, and
    `microdnf update sqlite-libs` reports "Nothing to do". Since the version cannot move,
    the surface it exposes is reduced instead.

    Extension loading was ENABLED by default — verified in the shipped image, not assumed.
    It lets SQL pull arbitrary shared objects into the process, which beyond CVE-2025-70873
    is a general escalation primitive if a SQL string ever became attacker-influenced. The
    store builds every statement itself and binds every parameter, so nothing legitimate
    needed the capability and turning it off costs nothing.

    Applied to the writer AND to every per-thread reader: this is connection state, so
    hardening only the writer would leave every API request thread unprotected.

    Guarded because sqlite3 may be compiled without the call, in which case the capability
    already does not exist and there is nothing to disable.

    See docs/image-vulnerability-scan.md for the full scan and reachability analysis.
    """
    try:
        conn.enable_load_extension(False)
    except AttributeError:
        pass


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
        # Transaction depth is PER THREAD, not per Store. A plain attribute here was a
        # real bug: one poller thread opening a snapshot made every OTHER thread's write
        # join a transaction it does not own, which sqlite3 reports as "bad parameter or
        # other API misuse". A transaction belongs to the thread that opened it.

        self._conn = sqlite3.connect(path, check_same_thread=False)
        _harden(self._conn)
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
        _migrate(self._conn)
        self._conn.commit()

    def close(self) -> None:
        # Under the lock: closing while another thread is mid-transaction would
        # otherwise raise from inside that thread rather than here.
        with self._lock:
            self._conn.close()

    def _depth(self) -> int:
        """How many transactions THIS thread has open. Never another thread's."""
        return getattr(self._local, "tx_depth", 0)

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """Write inside the ambient transaction if one is open, else own a new one.

        This is what lets `poll_snapshot()` turn nine transactions into one without every
        store method growing a `conn` parameter. Inside a snapshot the method JOINS — it
        does not commit, so the snapshot still owns the boundary. Outside one, behaviour is
        exactly as before: its own transaction, committed on exit.

        `_tx` stays strict and refuses nesting. The distinction matters: `_write` is a
        deliberate join by a method designed for it, `_tx` nesting is an accident by code
        that believes it owns the transaction and will be surprised when its rollback does
        not roll back.
        """
        if self._depth():
            yield self._conn      # the snapshot commits; we must not
            return
        with self._tx() as conn:
            yield conn

    @contextmanager
    def poll_snapshot(self) -> Iterator[None]:
        """One transaction for a whole poll cycle. All of it lands, or none of it.

        The poll wrote in NINE separate transactions, so any read landing mid-cycle saw a
        mixture — measured at 11,598 torn reads out of 19,208, a 60.38% failure rate, not
        an edge case. A failed cycle could also stamp `record_poll(OK)` over half-written
        state, which is worse than a visible failure because it looks healthy.

        `record_sync_event` is deliberately NOT in here; poll_once commits it first. Its
        uniqueness key is the operator's own lastSyncSuccessTime, so a rollback would lose
        an observation permanently rather than re-deriving it next cycle, and it is
        INSERT OR IGNORE, so committing early costs nothing and repeats harmlessly.

        `membership_event` IS in here, because it self-heals: the next poll re-derives the
        identical change with a later observed_at, degrading only the timestamp by one
        poll interval — which values.yaml already documents as the error bar on "when did
        this person lose access?".

        Measured cost of the change: 26.79 -> 26.81 ms median, with p95 improving.
        """
        with self._lock:
            if self._depth():
                raise RuntimeError("poll_snapshot() is already open on this thread")
            self._local.tx_depth = self._depth() + 1
            try:
                with self._conn:
                    yield
            finally:
                self._local.tx_depth = self._depth() - 1

    @contextmanager
    def read_snapshot(self) -> Iterator[None]:
        """One consistent view of the database for a whole multi-call handler.

        Making the poll atomic (`poll_snapshot`) took torn reads from 60.38% to 3.00%, not
        to zero, because a handler that calls the store SIX times issues six independent
        statements and a poll can commit between any two of them. `groupsyncs()` alone is
        two reads. WAL gives each statement a consistent snapshot; it does not give a
        SEQUENCE of statements the same one. Only an explicit read transaction does.

        Read-only by construction: it always rolls back, never commits. A rollback is not
        an error path here, it is the only exit — the snapshot exists to be released.

        HOLDING A READ SNAPSHOT HOLDS A WAL READ-MARK, and that has a cost worth knowing
        before anyone widens the scope of one of these blocks: `wal_checkpoint(TRUNCATE)`
        cannot reclaim past the oldest live reader, so a long-held snapshot stalls the
        checkpoint and the WAL grows. Measured: a reader held across a checkpoint blocked
        it for the full writer busy_timeout with zero pages reclaimed. At reference scale
        these blocks are 3-13 ms against a 60 s poll, which is why this is safe today and
        why `tests/test_read_snapshot_scope.py` exists to keep it that way — no generators,
        no streaming, no awaits, no network calls inside one.
        """
        depth = getattr(self._local, "read_depth", 0)
        if depth:
            # Already inside one: join it. Nesting is fine for reads — the inner block
            # wants exactly the snapshot the outer one already took.
            self._local.read_depth = depth + 1
            try:
                yield
            finally:
                self._local.read_depth -= 1
            return

        if self.path == ":memory:":
            # Reads share the writer connection here, so the write lock IS the snapshot.
            with self._lock:
                self._local.read_depth = 1
                try:
                    yield
                finally:
                    self._local.read_depth = 0
            return

        conn = self._reader()
        if conn.in_transaction:
            # A previous snapshot leaked. Left alone this thread would serve permanently
            # stale data with no error at all — measured: a worker pinned to a 2,000-row
            # view while the truth was 4,000. Fail loudly instead.
            raise RuntimeError(
                "this thread's reader is already in a transaction — a read_snapshot "
                "leaked and the connection is pinned to a stale view"
            )
        conn.execute("BEGIN")
        self._local.read_depth = 1
        try:
            yield
        finally:
            self._local.read_depth = 0
            conn.rollback()

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

        NESTING IS NOW REFUSED, not merely discouraged. The docstring used to say "do not
        nest" and nothing enforced it, because RLock is reentrant: the inner
        ``with self._conn`` COMMITS the shared transaction on exit, so the outer block's
        work is committed early and survives the outer rollback. Measured — an outer
        transaction wrote `phase-one`, called one ordinary store method, then raised, and
        `phase-one` was still there afterwards. Eleven call sites could reach it.

        Depth counting turns that into a loud error at the point of the mistake. The outer
        block owns the transaction; an inner one raises rather than silently committing.
        `poll_snapshot` makes a long outer transaction the normal shape, so nesting stops
        being exotic and this stops being theoretical.
        """
        with self._lock:
            if self._depth():
                raise RuntimeError(
                    "nested Store._tx(): the inner block would COMMIT the outer "
                    "transaction on exit, so the outer block's remaining work would be "
                    "committed early and survive its own rollback. Call the raw _-prefixed "
                    "helper inside an existing transaction, or restructure so only one "
                    "block owns it."
                )
            self._local.tx_depth = self._depth() + 1
            try:
                with self._conn:
                    yield self._conn
            finally:
                self._local.tx_depth = self._depth() - 1

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
            _harden(conn)
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

    def backup(self, directory: str, keep: int = 3) -> str | None:
        """Write a consistent copy of the database to `directory`. Returns its path.

        THE ONLY EXISTENTIAL RISK IN THIS SYSTEM. The accumulated sync and membership
        history cannot be re-fetched from the Kubernetes API — it exists because this
        process observed it — and until now a corrupted or deleted PVC lost it outright.
        Nothing else here is irreplaceable; this is.

        VACUUM INTO rather than copying the file: it takes a read transaction for the
        duration, so the output is a single consistent snapshot even while the poller
        writes. Copying gsd.db with the WAL live produces a torn file that opens without
        complaint and is missing the most recent commits, which is the worst kind of
        backup — one that restores.

        Called from the POLL THREAD only, the same rule as _checkpoint: it holds a read
        transaction for the length of the copy, and doing that from a request handler
        would put a user's page behind it.

        `keep` bounds the directory. Backups live on the same PVC this protects against,
        so they are the first half of the answer, not the whole one — a CronJob shipping
        them off the volume is the other half.
        """
        if self.path == ":memory:":
            return None
        target_dir = Path(directory)
        # Sub-second precision, unlike now_iso(). VACUUM INTO refuses to overwrite —
        # "output file already exists" — so two backups inside the same second collide and
        # the second one fails. now_iso() is deliberately second-resolution because the
        # store relies on its fixed width for lexicographic ordering; a filename has no
        # such constraint and needs the extra digits.
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = target_dir / f"gsd-{stamp}.db"
        try:
            # Inside the try: an unwritable or read-only backup directory must return None
            # like every other failure here, not raise into the poll thread. The method
            # promises "None on failure" and mkdir was the one path that broke that.
            target_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                # A bound parameter is not accepted for the VACUUM target, so the path is
                # interpolated. It is built here from a timestamp and an operator-supplied
                # directory, never from request input; the quote-doubling is belt to that
                # brace rather than the only protection.
                self._conn.execute(f"VACUUM INTO '{str(target).replace(chr(39), chr(39) * 2)}'")
        except (sqlite3.Error, OSError):
            log.exception("backup to %s failed; the history is still only on the PVC", target)
            return None

        existing = sorted(target_dir.glob("gsd-*.db"))
        for stale in existing[:-keep] if keep > 0 else []:
            try:
                stale.unlink()
            except OSError:
                log.warning("could not remove old backup %s", stale)
        log.info("backed up to %s (%d kept)", target, min(len(existing), keep or len(existing)))
        return str(target)

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
        with self._write() as conn:
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
        with self._write() as conn:
            cursor = conn.execute(
                """INSERT OR IGNORE INTO sync_event(
                       cluster_id, groupsync_name, groupsync_namespace,
                       synced_at, observed_at, schedule, group_count)
                   VALUES(?,?,?,?,?,?,?)""",
                (cluster_id, name, namespace, synced_at, observed_at, schedule, group_count),
            )
            return cursor.rowcount > 0

    def replace_groupsync_state(
        self, cluster_id: str, rows: list[dict] | None, observed_at: str
    ) -> None:
        """Replace this cluster's CR rows and their provider attributions together.

        Both in ONE transaction: a CR whose state is visible while its providers are not
        owns nothing for the duration, and every one of its groups would read as
        unattributed — a burst of phantom findings on each poll.

        `rows=None` means the GroupSync CRD is NOT INSTALLED, which is distinct from `[]`
        ("installed, no CRs defined") for the same reason it is for the policy operator: the
        first is a fact about the cluster's shape, the second about its configuration. Both
        store zero CR rows, so only the presence flag can tell them apart — and the Overview
        needs to, or "GroupSync CRs: 0" silently describes two different clusters.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO groupsync_presence(cluster_id, present, observed_at)
                   VALUES(?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET
                       present=excluded.present, observed_at=excluded.observed_at""",
                (cluster_id, 0 if rows is None else 1, observed_at),
            )
            conn.execute("DELETE FROM groupsync_state WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_state(cluster_id, name, namespace, schedule,
                       ldap_filter, last_sync_at, generation, observed_at)
                   VALUES(:cluster_id,:name,:namespace,:schedule,:ldap_filter,
                          :last_sync_at,:generation,:observed_at)""",
                [
                    {k: v for k, v in r.items() if k != "provider_keys"}
                    | {"cluster_id": cluster_id, "observed_at": observed_at}
                    for r in rows or []
                ],
            )
            conn.execute("DELETE FROM groupsync_provider WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT INTO groupsync_provider(
                       cluster_id, groupsync_name, groupsync_namespace, provider_key)
                   VALUES(?,?,?,?)""",
                [
                    (cluster_id, r["name"], r["namespace"], key)
                    for r in rows or []
                    for key in r.get("provider_keys") or []
                ],
            )

    def replace_group_state(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's group rows wholesale.

        Delete-then-insert inside one transaction, so a group that disappeared upstream also
        disappears here — an upsert would leave deleted groups behind forever and quietly
        inflate every count on the overview.
        """
        with self._write() as conn:
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
        with self._write() as conn:
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
        # LEFT JOIN, not a second query: the handler that calls this is asserted to make exactly
        # one store call (tests/test_api_contract.py, the take-a-snapshot rule), and a name is
        # missing far more often than not — 3 of 10 members on the reference cluster — so NULL is
        # the ordinary result rather than a case to special-case.
        #
        # Ordering stays on user_name. Sorting by display name would reorder the list for the 70%
        # that have one and scatter the rest, and the id is what an operator matches against `oc`.
        return self._rows(
                """SELECT m.user_name, m.first_seen_at, m.last_seen_at, u.full_name,
                          (SELECT MIN(e.observed_at) FROM membership_event e
                            WHERE e.cluster_id = m.cluster_id
                              AND e.group_name = m.group_name
                              AND e.user_name  = m.user_name
                              AND e.change = 'added') AS original_first_seen_at
                     FROM group_member m
                     LEFT JOIN ocp_user u
                            ON u.cluster_id = m.cluster_id
                           AND u.user_name  = m.user_name
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

    def users(self, cluster_id: str, limit: int = 1000) -> list[dict]:
        """Every user with a membership. BOUNDED.

        Unbounded, this returned one row per distinct user across every group: 1,240 rows
        and 102,921 bytes on a reference-shaped cluster with 62 groups, and it grows with
        the DIRECTORY rather than with anything the dashboard controls. A real corporate
        LDAP makes that a response big enough to hurt the browser and the pod.

        `limit + 1` is fetched deliberately: the caller compares the length against the
        limit to know it truncated, without a second COUNT query. A silently truncated
        list is worse than a large one — the reader cannot tell a short directory from a
        clipped answer.
        """
        return self._rows(
                """SELECT user_name, COUNT(*) AS group_count, MIN(first_seen_at) AS first_seen_at
                     FROM group_member WHERE cluster_id=?
                    GROUP BY user_name ORDER BY user_name LIMIT ?""",
                (cluster_id, limit + 1),
        )

    # -- RBAC bindings -----------------------------------------------------------------

    def replace_bindings(self, cluster_id: str, rows: list[dict], observed_at: str) -> None:
        """Replace this cluster's binding rows wholesale, in one transaction."""
        with self._write() as conn:
            conn.execute("DELETE FROM rbac_group_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO rbac_group_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, group_name, observed_at,
                       managed_source, exception, audit_stamped)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:group_name,:observed_at,
                          :managed_source,:exception,:audit_stamped)""",
                [{"managed_source": None, "exception": None, "audit_stamped": 0, **r,
                  "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
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
        with self._write() as conn:
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

    # The classification, written once. Both all_bindings and count_bindings_by_finding
    # need it, and two copies of a five-branch CASE would drift the moment a tier changed —
    # producing counts that disagree with the rows they are counting.
    _FINDING_CASE = """
                      CASE
                        -- Broken-resolution tiers first: a binding that grants NOBODY is
                        -- worse than one that grants outside governance, whoever made it.
                        WHEN g.name IS NULL AND s.group_name IS NOT NULL
                                                           THEN 'dangling'
                        WHEN g.name IS NULL AND b.group_name LIKE 'system:%'
                                                           THEN 'built_in'
                        WHEN g.name IS NULL                THEN 'unresolved'
                        -- The group resolves. Now provenance: an operator-SYNCED group
                        -- granted access by a binding NO policy system manages is somebody
                        -- bypassing governance by hand. Requires the policy operator to be
                        -- in use at all (any managed binding on the cluster), or every
                        -- binding on a cluster that has never heard of config-source
                        -- labels would flag. An exception annotation on the binding
                        -- acknowledges a deliberate one and suppresses the finding.
                        WHEN b.managed_source IS NULL
                             AND b.exception IS NULL
                             AND s.group_name IS NOT NULL
                             AND EXISTS (SELECT 1 FROM rbac_group_binding m
                                          WHERE m.cluster_id = b.cluster_id
                                            AND m.managed_source IS NOT NULL)
                                                           THEN 'unmanaged'
                        ELSE 'ok'
                      END"""

    _FINDING_FROM = """
                 FROM rbac_group_binding b
                 LEFT JOIN group_state g
                        ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                 LEFT JOIN managed_group_seen s
                        ON s.cluster_id = b.cluster_id AND s.group_name = b.group_name
                WHERE b.cluster_id = ?"""

    def count_bindings_by_finding(self, cluster_id: str) -> dict[str, int]:
        """How many bindings fall in each tier, for the WHOLE cluster.

        Exists so the counts stay true when the rows beside them are paged. Counting a
        truncated page is the "showing 50 of 30" defect this codebase has now hit three
        times; the fix each time is a scalar query over the same predicate.
        """
        rows = self._rows(
            "SELECT" + self._FINDING_CASE + " AS finding, COUNT(*) AS n"
            + self._FINDING_FROM + " GROUP BY finding",
            (cluster_id,),
        )
        return {r["finding"]: r["n"] for r in rows}

    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0
    ) -> list[dict]:
        """Every group-subject binding, each classified.

        Includes the ones that resolve normally (`ok`). Those are the majority of a healthy
        cluster — 74 of 228 here — and omitting them made a view labelled "Bindings" show
        only the broken subset, which misrepresents what is on the cluster.

        `limit` because this was unbounded and grows with the cluster: measured at 2,280
        rows / 545,800 bytes at ten times the reference cluster, on a 30-second auto-refresh.
        Pair it with `count_bindings_by_finding` — the counts must describe the cluster, not
        the page.
        """
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name,
                      b.managed_source, b.exception, b.audit_stamped,"""
               + self._FINDING_CASE + " AS finding" + self._FINDING_FROM
               + """
                ORDER BY b.group_name, b.binding_kind, b.binding_namespace, b.binding_name""")
        params: list = [cluster_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def replace_user_bindings(
        self, cluster_id: str, rows: list[dict], observed_at: str
    ) -> None:
        """Replace this cluster's direct-user binding rows wholesale."""
        with self._write() as conn:
            conn.execute("DELETE FROM user_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO user_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, user_name, is_platform, observed_at)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:user_name,:is_platform,:observed_at)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )

    def replace_users(self, cluster_id: str, names: dict[str, str], observed_at: str) -> None:
        """Replace this cluster's display names wholesale.

        Delete-then-insert rather than upsert, for the same reason replace_group_state gives:
        an upsert would leave a name behind after its User object is deleted, and a stale name
        on a departed account is worse than no name at all.

        The caller must not reach here when the fetch was FORBIDDEN — passing {} would wipe
        every known name, which is exactly what tolerating the 403 exists to prevent.
        """
        with self._write() as conn:
            conn.execute("DELETE FROM ocp_user WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO ocp_user(
                       cluster_id, user_name, full_name, observed_at)
                   VALUES(:cluster_id,:user_name,:full_name,:observed_at)""",
                [
                    {"cluster_id": cluster_id, "user_name": name,
                     "full_name": full, "observed_at": observed_at}
                    for name, full in names.items()
                ],
            )

    def user_full_name(self, cluster_id: str, user_name: str) -> str | None:
        """One display name, or None when that person has no User object or no name on it."""
        rows = self._rows(
            "SELECT full_name FROM ocp_user WHERE cluster_id=? AND user_name=?",
            (cluster_id, user_name),
        )
        return rows[0]["full_name"] if rows else None

    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]:
        """Direct-user grants rolled up per namespace — the migration worklist.

        Ordered worst-first by PRIVILEGE, then cluster-scope, then count, then name — one
        forgotten cluster-admin outranks twenty view grants, and ordering by count alone
        put the twenty first and pushed the cluster-admin below the fold.

        Platform identities are excluded from the rollup (they are not migratable and would
        swamp it) but counted separately by `platform_user_binding_count`, so the page can
        say what it left out rather than quietly shrinking the number.

        `distinct_users` matters as much as the binding count: one person with five
        bindings in a namespace is one offboarding risk, five people is five.

        `users` is a LIST, stitched in from a second read, never a GROUP_CONCAT. Same
        reason as `provider_keys` in `groupsyncs()` below: a delimited string means picking
        a delimiter the value can never contain, and a user name can be an LDAP DN. The page
        unions these lists to count distinct people, so with GROUP_CONCAT a single
        `cn=jdoe,ou=people,dc=example,dc=com` split into four and the KPI read 4 people
        beside a row whose own People column said 1.
        """
        with self.read_snapshot():
            rows = self._rows(
                """SELECT CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          COUNT(*) AS bindings,
                          COUNT(DISTINCT user_name) AS distinct_users,
                          -- The worst privilege granted here, and whether it is
                          -- cluster-wide. Risk is ranked on PRIVILEGE, not on count: one
                          -- forgotten cluster-admin outranks twenty view grants, and a
                          -- list sorted by count puts the twenty first.
                          MAX(CASE role_name WHEN 'cluster-admin' THEN 4 WHEN 'admin' THEN 3
                                             WHEN 'edit' THEN 2 ELSE 1 END) AS worst_privilege,
                          MAX(CASE WHEN binding_namespace = '' THEN 1 ELSE 0 END)
                              AS cluster_scoped
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    GROUP BY namespace
                    ORDER BY worst_privilege DESC, cluster_scoped DESC,
                             bindings DESC, namespace""",
                (cluster_id,),
            )
            people: dict[str, list[str]] = {}
            for row in self._rows(
                """SELECT DISTINCT
                          CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          user_name
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    ORDER BY user_name""",
                (cluster_id,),
            ):
                people.setdefault(row["namespace"], []).append(row["user_name"])
            for row in rows:
                row["users"] = people.get(row["namespace"], [])
            return rows

    # Namespace sentinel for the cluster-scoped rows. Their binding_namespace is '', which
    # an HTTP query string cannot distinguish from "parameter absent", so the API and the
    # UI both speak this token and it is translated here at the boundary.
    CLUSTER_SCOPE = "(cluster-scoped)"

    def _direct_user_binding_where(
        self, cluster_id: str, include_platform: bool, namespace: str | None
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its COUNT, built once.

        Built once on purpose: a count computed from a different predicate than the rows
        it describes is how "showing 50 of 30" reaches a page, and the two drifting apart
        during a later edit is the likeliest way for that to happen.
        """
        sql, params = " WHERE cluster_id=?", [cluster_id]
        if not include_platform:
            sql += " AND is_platform=0"
        if namespace is not None:
            sql += " AND binding_namespace=?"
            params.append("" if namespace == self.CLUSTER_SCOPE else namespace)
        return sql, params

    def direct_user_bindings(
        self,
        cluster_id: str,
        include_platform: bool = False,
        namespace: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict]:
        """Every binding naming a User subject, worst-first by privilege then namespace.

        NOT to be confused with `user_bindings(cluster_id, user_name)` above, which answers
        the opposite question: what a person reaches THROUGH their group memberships. This
        one is the governance violation — a grant that names the person directly. The
        original name for this collided with that method and silently overrode it, which
        broke two reverse-lookup tests; the names now say which question each answers.

        `namespace` and `limit` exist because this was previously unbounded at every layer:
        the store returned every row, the API returned every row, and the page rendered
        every row. On a cluster with thousands of direct grants that is a payload and a DOM
        nobody asked for, to show a list nobody can read. Pair with
        `count_direct_user_bindings` so the caller can say what it left out — a silently
        truncated audit list is worse than a slow one.
        """
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace)
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind,
                         role_name, user_name, is_platform
                    FROM user_binding""" + where +
               # cluster-admin first, then cluster-scoped, then namespaced: the order
               # somebody migrating would work in. Ordering is applied BEFORE the limit, so
               # a truncated page is the worst N rather than an arbitrary N.
               """ ORDER BY CASE WHEN role_name='cluster-admin' THEN 0 ELSE 1 END,
                            CASE WHEN binding_namespace='' THEN 0 ELSE 1 END,
                            binding_namespace, user_name""")
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def count_direct_user_bindings(
        self, cluster_id: str, include_platform: bool = False,
        namespace: str | None = None,
    ) -> int:
        """How many rows `direct_user_bindings` would return before its limit."""
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace)
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + where, tuple(params))
        return rows[0]["n"] if rows else 0

    def platform_user_binding_count(self, cluster_id: str) -> int:
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
            (cluster_id,),
        )
        return int(rows[0]["n"]) if rows else 0

    # -- namespace-configuration-operator health -----------------------------------------

    def replace_operator_configs(
        self, cluster_id: str, configs: list[dict] | None, observed_at: str
    ) -> None:
        """Replace this cluster's operator-config health rows. None means CRDs absent.

        Presence is stored explicitly rather than inferred from row count, because
        "operator not installed" and "operator installed with zero CRs" are different
        truths: the first must render as nothing at all, the second as an empty-but-real
        section. Conflating them shows 'all healthy' for a concept the cluster lacks.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO operator_config_presence(cluster_id, present, observed_at)
                   VALUES(?,?,?)
                   ON CONFLICT(cluster_id) DO UPDATE SET
                       present=excluded.present, observed_at=excluded.observed_at""",
                (cluster_id, 0 if configs is None else 1, observed_at),
            )
            conn.execute("DELETE FROM operator_config_state WHERE cluster_id=?", (cluster_id,))
            if configs:
                conn.executemany(
                    """INSERT INTO operator_config_state(
                           cluster_id, kind, name, error_at, error_message,
                           success_at, observed_at)
                       VALUES(:cluster_id,:kind,:name,:error_at,:error_message,
                              :success_at,:observed_at)""",
                    [{**c, "cluster_id": cluster_id, "observed_at": observed_at}
                     for c in configs],
                )

    def groupsync_present(self, cluster_id: str) -> bool | None:
        """Is the GroupSync CRD installed? None = never observed (no poll since upgrade).

        Three-valued on purpose. False must mean "we looked and it is not there", so it can
        raise an alert; a cluster that has not polled since the migration added this table has
        not been looked at, and alerting on that would fire once for every existing cluster on
        upgrade.
        """
        row = self._row(
            "SELECT present FROM groupsync_presence WHERE cluster_id=?", (cluster_id,)
        )
        return None if row is None else bool(row["present"])

    def operator_configs(self, cluster_id: str) -> dict:
        """Health of the policy operator's CRs: {present: bool, configs: [...]}."""
        presence = self._row(
            "SELECT present FROM operator_config_presence WHERE cluster_id=?", (cluster_id,)
        )
        return {
            "present": bool(presence and presence["present"]),
            "configs": self._rows(
                """SELECT kind, name, error_at, error_message, success_at, observed_at
                     FROM operator_config_state WHERE cluster_id=?
                    ORDER BY kind, name""",
                (cluster_id,),
            ),
        }

    def upsert_reconcile_error(
        self,
        cluster_id: str,
        name: str,
        failed_at: str | None,
        generation: int | None,
        message: str | None,
    ) -> None:
        with self._write() as conn:
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

    def _user_activity_where(
        self, since_day: str | None, user_name: str | None
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its summary, built once.

        Built once for the same reason as `_direct_user_binding_where`: a total computed
        from a different predicate than the rows it describes is how "showing 50 of 30"
        reaches a page.
        """
        where, params = [], []
        if since_day:
            where.append("day >= ?")
            params.append(since_day)
        if user_name:
            where.append("user_name = ?")
            params.append(user_name)
        return (" WHERE " + " AND ".join(where)) if where else "", params

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

        BOUNDED. Pair with `user_activity_summary` for any headline number: counting these
        rows counts the page, not the record.
        """
        where, params = self._user_activity_where(since_day, user_name)
        sql = ("""SELECT user_name, day, email, first_seen_at, last_seen_at, request_count
                   FROM dashboard_user_activity""" + where +
               " ORDER BY day DESC, user_name LIMIT ?")
        params.append(limit)
        return self._rows(sql, params)

    def user_activity_summary(
        self, since_day: str | None = None, user_name: str | None = None
    ) -> dict:
        """Totals over the WHOLE activity set the caller may see, ignoring any row limit.

        The Usage tab used to compute its KPIs from the returned rows, which are capped:
        measured at 1,092 stored rows it reported 167 days and 5,000 interactions where the
        truth was 364 and 10,920.

        Each `COUNT(DISTINCT ...)` here is one scalar over the whole filtered set, not a
        per-group count that anything adds up — summing per-day distinct users would count
        everybody again on every day they came back.
        """
        where, params = self._user_activity_where(since_day, user_name)
        rows = self._rows(
            """SELECT COUNT(*) AS rows_total,
                      COUNT(DISTINCT user_name) AS distinct_users,
                      COUNT(DISTINCT day) AS days,
                      COALESCE(SUM(request_count), 0) AS interactions
                 FROM dashboard_user_activity""" + where,
            params,
        )
        return dict(rows[0])

    # -- queries -----------------------------------------------------------------------

    def groupsyncs(self, cluster_id: str) -> list[dict]:
        """Current CR state, each row carrying the full list of provider keys it owns.

        `provider_keys` is stitched in from a second read rather than GROUP_CONCAT'd: the
        callers need a list to test membership against, and building one by splitting a
        delimited string means picking a delimiter that a label value can never contain.
        Two reads of a handful of rows is the cheaper correctness.

        THOSE TWO READS TAKE THEIR OWN SNAPSHOT. WAL gives each statement a consistent
        view, not each pair of statements, so a poll committing between them stitched CR
        rows to a different generation of provider rows — a CR listing providers whose
        groups the same response says do not exist. Callers must not have to know this
        method reads twice; nesting is free because read_snapshot joins an open one.
        """
        with self.read_snapshot():
            return self._groupsyncs(cluster_id)

    def _groupsyncs(self, cluster_id: str) -> list[dict]:
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
            # EVERY group with no members, whatever created it. This was scoped to
            # `sync_provider IS NOT NULL` on PLAN §7's reading of EMPTY as "synced, then lost
            # its members" — an LDAP-side fault. That reading made the filter USELESS on the
            # cluster that most needs it: with no group-sync-operator installed, every group is
            # unattributed, so `empty` matched nothing however many groups had zero members.
            #
            # `empty` and `unattributed` therefore OVERLAP now, and that is intended: they are
            # two questions, not a partition. "Which groups grant nobody?" and "which groups is
            # no CR managing?" have different answers and a group can be both. Nothing sums
            # them — checked across store, api, metrics and the UI before the change.
            sql += " AND member_count = 0"
        elif state == "unattributed":
            sql += " AND sync_provider IS NULL"
        elif state != "all":
            raise ValueError(f"unknown group state filter {state!r}")
        sql += " ORDER BY name"
        return self._rows(sql, params)

    def group_counts(self, cluster_id: str) -> dict:
        row = self._row(
            """SELECT COUNT(*) AS total,
                      -- Must stay identical to the `empty` predicate in groups() above. A
                      -- count that disagrees with its own list is the defect class this
                      -- project keeps rediscovering, so a test pins them together.
                      SUM(CASE WHEN member_count = 0 THEN 1 ELSE 0 END) AS empty,
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
