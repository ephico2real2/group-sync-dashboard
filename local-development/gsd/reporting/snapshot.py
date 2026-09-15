"""A read-only view over one `VACUUM INTO` copy of the dashboard's database.

THE SECOND BACKEND, DELIBERATELY. gsd/storage.py's contract has one implementation, Store, and
tests/test_storage_seam.py lets exactly one module speak SQL. This module is the second, for one
reason: the report service runs in ANOTHER POD, and a SQLite WAL database cannot be shared across
hosts — the -shm file is one host's shared memory (gsd/store.py#Store.__init__, the WAL-on-NFS
error). So the dashboard's leader writes a consistent copy (Store.snapshot, `VACUUM INTO`) and this
module opens THAT, and only that:

    file:<copy>?immutable=1&mode=ro

`immutable=1` tells SQLite the file cannot change, so it takes no lock and wants no -shm/-wal;
that is true of a VACUUM INTO output (journal_mode DELETE, measured) that nothing rewrites — the
writer creates each copy under a temporary name and renames it into place, and never touches a
copy again except to delete it. `mode=ro` is the belt to that brace: a write raises.

WHAT IT MUST NOT BECOME. Nothing here writes, nothing here opens the live gsd.db, and nothing here
redefines a classification: the CASE that decides dangling/unresolved/built_in/unmanaged/ok is
imported from Store, so a report and the RBAC policy tab cannot disagree about one binding.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..store import Store, _MIGRATIONS, _harden

log = logging.getLogger(__name__)

#: Store.backup / Store.snapshot name their files gsd-<%Y%m%dT%H%M%S.%fZ>.db.
_STAMP = re.compile(r"^gsd-(\d{8}T\d{6}\.\d{6}Z)\.db$")
#: The highest migration this build understands; a newer copy is refused (§4.4).
KNOWN_SCHEMA_VERSION = max(t for t, _, _ in _MIGRATIONS)
CLUSTER_SCOPE = Store.CLUSTER_SCOPE
PRIVILEGE_RANK = "CASE role_name WHEN 'cluster-admin' THEN 4 WHEN 'admin' THEN 3 WHEN 'edit' THEN 2 ELSE 1 END"


class SnapshotError(Exception):
    """No usable copy: absent directory, no file, or a schema newer than this build."""


@dataclass(frozen=True)
class SnapshotInfo:
    path: str
    stamp: str            # ISO-8601 UTC with microseconds, from the filename
    schema_version: int
    bytes: int

    def age_seconds(self, now: datetime) -> float:
        return (now - datetime.strptime(self.stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)).total_seconds()


def newest_snapshot(directory: str) -> Path:
    """The newest complete copy in `directory`, by the stamp in its name (lexicographic = chronological,
    fixed width). Temporary files (`.tmp`) are the writer's and are never candidates."""
    d = Path(directory)
    if not d.is_dir():
        raise SnapshotError(f"snapshot directory {directory} does not exist — the dashboard has not written a copy yet, or the volume is not mounted")
    # Regular files only, judged WITHOUT following links: the report pod mounts the whole data claim
    # read-only, so a symlink named like a copy could point at the live gsd.db — and immutable=1 on a
    # file that changes returns wrong results (review of C3, Codex).
    candidates = sorted(p for p in d.iterdir() if _STAMP.match(p.name) and stat.S_ISREG(p.lstat().st_mode))
    if not candidates:
        raise SnapshotError(f"no snapshot in {directory} yet — the dashboard's leader writes one every reporting.snapshot.intervalSeconds")
    return candidates[-1]


class Snapshot:
    """One open copy. Construct per run, close after: a run must read ONE consistent picture, and
    holding a copy open across runs would pin the file the writer wants to delete."""

    def __init__(self, path: Path):
        self.path = str(path)
        m = _STAMP.match(path.name)
        if not m:
            raise SnapshotError(f"{path.name} is not a snapshot file")
        raw = m.group(1)
        self.stamp = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}T{raw[9:11]}:{raw[11:13]}:{raw[13:15]}{raw[15:]}"
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise SnapshotError(f"{path.name} is not a regular snapshot file (a link or a directory under the name of a copy)")
        except OSError as exc:
            raise SnapshotError(f"cannot inspect snapshot {path.name}: {exc}") from exc
        uri = f"file:{path}?immutable=1&mode=ro"
        self._conn = None
        try:
            self._conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            _harden(self._conn)
            self._conn.row_factory = sqlite3.Row
            self.schema_version = int(self._conn.execute("PRAGMA user_version").fetchone()[0])
            if self.schema_version > KNOWN_SCHEMA_VERSION:
                raise SnapshotError(
                    f"snapshot schema {self.schema_version} is newer than this report service understands "
                    f"({KNOWN_SCHEMA_VERSION}); the reporting image must be the dashboard's appVersion")
            self._tables = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.Error as exc:
            # A file named like a copy but not a readable SQLite database — truncated, torn, or not a
            # database at all; the connect / PRAGMA / catalog reads are where that surfaces. Translated
            # to SnapshotError HERE, at the backend boundary, so a caller (the catalogue, the age probe)
            # sees one exception type and the engine never leaks past this module — the storage seam
            # (tests/test_storage_seam.py) forbids `import sqlite3` outside the backend.
            if self._conn is not None:
                self._conn.close()
            raise SnapshotError(f"cannot open snapshot {path.name}: not a readable SQLite database") from exc
        except SnapshotError:
            if self._conn is not None:
                self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Snapshot":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def info(self) -> SnapshotInfo:
        # From the open connection, never a second pathname lookup: the writer may prune this copy
        # while a run reads it, and Linux keeps the inode alive for our descriptor but not its name
        # (second review pass, Codex: a pruned-after-open snapshot raised FileNotFoundError here).
        page_count = int(self._conn.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(self._conn.execute("PRAGMA page_size").fetchone()[0])
        return SnapshotInfo(self.path, self.stamp, self.schema_version, page_count * page_size)

    def has_table(self, name: str) -> bool:
        return name in self._tables

    def _rows(self, sql: str, params: tuple | list = ()) -> list[dict]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _row(self, sql: str, params: tuple | list = ()) -> dict | None:
        r = self._conn.execute(sql, params).fetchone()
        return dict(r) if r else None

    # -- cluster and poll --------------------------------------------------------------------

    def clusters(self) -> list[dict]:
        return self._rows("""SELECT c.id, c.api_url, c.enabled, p.status, p.observed_at AS last_poll, p.message
                               FROM cluster c LEFT JOIN poll_outcome p ON p.cluster_id = c.id ORDER BY c.id""")

    def cluster(self, cluster_id: str) -> dict | None:
        return self._row("""SELECT c.id, c.api_url, c.enabled, p.status, p.observed_at AS last_poll, p.message
                              FROM cluster c LEFT JOIN poll_outcome p ON p.cluster_id = c.id WHERE c.id = ?""",
                         (cluster_id,))

    def history_retained_since(self, cluster_id: str) -> dict[str, str | None]:
        out = {}
        for table in ("membership_event", "sync_event", "login_event"):
            r = self._row(f"SELECT MIN(observed_at) AS since FROM {table} WHERE cluster_id = ?", (cluster_id,))
            out[table] = r["since"] if r else None
        return out

    # -- coverage sources ---------------------------------------------------------------------

    def users_source(self, cluster_id: str) -> dict | None:
        return self._row("SELECT state, observed_at FROM ocp_user_status WHERE cluster_id = ?", (cluster_id,))

    def namespaces_source(self, cluster_id: str) -> dict | None:
        if not self.has_table("cluster_namespace_status"):
            return None
        return self._row("SELECT state, observed_at FROM cluster_namespace_status WHERE cluster_id = ?", (cluster_id,))

    def cluster_namespaces(self, cluster_id: str) -> list[dict]:
        if not self.has_table("cluster_namespace"):
            return []
        return self._rows("SELECT name, created_at, phase FROM cluster_namespace WHERE cluster_id = ? ORDER BY name", (cluster_id,))

    def namespace_metadata_values(self, cluster_id: str, key: str) -> list[str]:
        """Distinct values captured for one metadata key, for the GUI's multi-select. Empty when the
        table is absent (pre-migration snapshot), the key is not captured, or no namespace carries it."""
        if not key or not self.has_table("cluster_namespace_label"):
            return []
        return [r["value"] for r in self._rows(
            "SELECT DISTINCT value FROM cluster_namespace_label "
            "WHERE cluster_id=? AND key=? ORDER BY value", (cluster_id, key))]

    def namespace_selectors(self, key: str) -> dict[str, dict]:
        """Per cluster id, the selector label and its captured values, for the B3 multi-select.

        The whole gather lives here, not in the caller, for one reason: a copy that OPENED cleanly can
        still raise sqlite3.Error from a later table read (partial b-tree damage on a copy that has
        rotted on disk after it was written). Translated to SnapshotError HERE, at the backend boundary,
        that becomes the catalogue's designed empty-map degradation instead of a 500 — and sqlite3 never
        has to be named in server.py (the storage seam, tests/test_storage_seam.py). A genuine query bug
        would fail the catalogue's own value assertions in the suite, so this does not mask one.
        """
        try:
            return {row["id"]: {"label": key,
                                "values": self.namespace_metadata_values(row["id"], key) if key else []}
                    for row in self.clusters()}
        except sqlite3.Error as exc:
            raise SnapshotError(f"cannot read snapshot {Path(self.path).name}: not readable SQLite data") from exc

    def namespaces_for_metadata(self, cluster_id: str, key: str, values: list[str]) -> list[str]:
        """Namespace names whose metadata `key` is one of `values`. The strict selector's expansion."""
        if not key or not values or not self.has_table("cluster_namespace_label"):
            return []
        marks = ",".join("?" for _ in values)
        return [r["name"] for r in self._rows(
            f"SELECT name FROM cluster_namespace_label WHERE cluster_id=? AND key=? AND value IN ({marks}) "
            "ORDER BY name", (cluster_id, key, *values))]

    def namespace_selector_dimensions(self, keys: list[str]) -> dict[str, list[dict]]:
        """Per cluster id, one {label, values} entry per configured selector key, for the P2
        multi-dimension multi-select. Behind the same sqlite3.Error -> SnapshotError boundary as
        namespace_selectors, so a rotted copy degrades the catalogue to an empty map, never a 500
        (the storage seam, tests/test_storage_seam.py)."""
        try:
            return {row["id"]: [{"label": k, "values": self.namespace_metadata_values(row["id"], k)}
                                for k in keys if k]
                    for row in self.clusters()}
        except sqlite3.Error as exc:
            raise SnapshotError(f"cannot read snapshot {Path(self.path).name}: not readable SQLite data") from exc

    def namespaces_for_selectors(self, cluster_id: str, selectors: dict[str, list[str]]) -> list[str]:
        """Namespace names matching EVERY selector dimension (AND across labels), where a dimension
        matches ANY of its values (OR within). Composes the single-key `namespaces_for_metadata`
        expansion and intersects in Python, so the SQL stays the form already tested and the AND is
        explicit (docs/DESIGN_reporting_selectors_snapshots_and_windows.md §3). Empty selection -> []."""
        if not selectors or not self.has_table("cluster_namespace_label"):
            return []
        result: set[str] | None = None
        for key, values in selectors.items():
            matched = set(self.namespaces_for_metadata(cluster_id, key, values))
            result = matched if result is None else (result & matched)
            if not result:
                return []
        return sorted(result or set())

    def login_capture_status(self, cluster_id: str) -> dict | None:
        return self._row("SELECT started_at, last_read_at FROM login_capture_status WHERE cluster_id = ?", (cluster_id,))

    def access_group(self, cluster_id: str) -> dict | None:
        return self._row("SELECT dn, source, group_name, observed_at FROM cluster_access_group WHERE cluster_id = ?", (cluster_id,))

    # -- bindings -----------------------------------------------------------------------------

    def binding_namespaces(self, cluster_id: str) -> list[dict]:
        """DISTINCT namespaces observed on any binding, with counts; '' is the cluster-scope sentinel
        (the current C3's store method, unchanged in meaning)."""
        return self._rows(
            """SELECT ns AS namespace, SUM(g) AS group_bindings, SUM(u) AS user_bindings
                 FROM (SELECT CASE WHEN binding_namespace='' THEN ? ELSE binding_namespace END AS ns, 1 AS g, 0 AS u
                         FROM rbac_group_binding WHERE cluster_id=?
                       UNION ALL
                       SELECT CASE WHEN binding_namespace='' THEN ? ELSE binding_namespace END, 0, 1
                         FROM user_binding WHERE cluster_id=? AND is_platform=0)
                GROUP BY ns ORDER BY ns""",
            (CLUSTER_SCOPE, cluster_id, CLUSTER_SCOPE, cluster_id))

    def group_bindings(self, cluster_id: str, namespaces: list[str] | None = None) -> list[dict]:
        """Every group-subject binding, classified by the dashboard's own CASE, with reach. Ordered
        namespace, finding severity, group, binding — deterministic so two reports diff cleanly."""
        reach = """
                      CASE WHEN g.name IS NULL THEN NULL ELSE COALESCE(li.member_count, 0) END AS member_count,
                      CASE WHEN g.name IS NULL OR ust.cluster_id IS NULL THEN NULL
                           ELSE COALESCE(li.logged_in_count, 0) END AS logged_in_count,"""
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name, b.role_kind, b.role_name,
                         b.group_name, b.managed_source, b.exception,""" + reach
               + Store._FINDING_CASE + " AS finding"
               + Store._FINDING_JOINS + Store._REACH_JOIN + Store._FINDING_WHERE)
        params: list = [cluster_id]
        if namespaces is not None:
            sql += " AND b.binding_namespace IN (" + ",".join("?" * len(namespaces)) + ")"
            params += namespaces
        sql += """ ORDER BY b.binding_namespace,
                          CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1 WHEN 'unmanaged' THEN 2
                                       WHEN 'ok' THEN 3 ELSE 4 END,
                          b.group_name, b.binding_name"""
        return self._rows(sql, params)

    def findings_counts(self, cluster_id: str) -> dict[str, int]:
        rows = self._rows("SELECT" + Store._FINDING_CASE + " AS finding, COUNT(*) AS n"
                          + Store._FINDING_JOINS + Store._FINDING_WHERE + " GROUP BY finding", (cluster_id,))
        return {r["finding"]: int(r["n"]) for r in rows}

    def user_bindings(self, cluster_id: str, namespaces: list[str] | None = None,
                      include_platform: bool = False) -> list[dict]:
        sql = """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name, user_name, is_platform
                   FROM user_binding WHERE cluster_id=?"""
        params: list = [cluster_id]
        if not include_platform:
            sql += " AND is_platform=0"
        if namespaces is not None:
            sql += " AND binding_namespace IN (" + ",".join("?" * len(namespaces)) + ")"
            params += namespaces
        sql += f" ORDER BY binding_namespace, {PRIVILEGE_RANK} DESC, user_name, binding_name"
        return self._rows(sql, params)

    def platform_user_binding_count(self, cluster_id: str) -> int:
        r = self._row("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1", (cluster_id,))
        return int(r["n"]) if r else 0

    def privileged_group_bindings(self, cluster_id: str, roles: tuple[str, ...]) -> list[dict]:
        """Group bindings to the named roles: any scope for cluster-admin, cluster scope for the rest —
        the privileged-access review's definition of 'privileged', stated in the report."""
        rows = self.group_bindings(cluster_id)
        return [r for r in rows if r["role_name"] in roles and (r["role_name"] == "cluster-admin" or r["binding_namespace"] == "")]

    def privileged_user_bindings(self, cluster_id: str, roles: tuple[str, ...]) -> list[dict]:
        rows = self.user_bindings(cluster_id)
        return [r for r in rows if r["role_name"] in roles and (r["role_name"] == "cluster-admin" or r["binding_namespace"] == "")]

    # -- groups and members -------------------------------------------------------------------

    def groups(self, cluster_id: str) -> list[dict]:
        return self._rows(
            """SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at, g.ldap_uid, g.observed_at, g.cliff_silence,
                      (SELECT COUNT(*) FROM rbac_group_binding b WHERE b.cluster_id = g.cluster_id AND b.group_name = g.name) AS bindings
                 FROM group_state g WHERE g.cluster_id = ? ORDER BY g.name""", (cluster_id,))

    def group_rosters(self, cluster_id: str, group_names: list[str]) -> dict[str, list[dict]]:
        """Members per group with the logged-in flag (a User object WITH an identity, the 0.9.0
        definition — docs/DESIGN_users_tab_logins.md). Opt-in on every report that calls it."""
        if not group_names:
            return {}
        out: dict[str, list[dict]] = {}
        marks = ",".join("?" * len(group_names))
        for r in self._rows(
                f"""SELECT m.group_name, m.user_name, m.first_seen_at, u.full_name,
                           CASE WHEN u.user_name IS NULL THEN NULL ELSE u.has_identity END AS logged_in
                      FROM group_member m LEFT JOIN ocp_user u ON u.cluster_id = m.cluster_id AND u.user_name = m.user_name
                     WHERE m.cluster_id = ? AND m.group_name IN ({marks}) ORDER BY m.group_name, m.user_name""",
                [cluster_id, *group_names]):
            out.setdefault(r["group_name"], []).append(r)
        return out

    def membership_changes(self, cluster_id: str, since_iso: str) -> list[dict]:
        return self._rows(
            """SELECT group_name, user_name, change, observed_at, group_synced_at FROM membership_event
                WHERE cluster_id = ? AND observed_at >= ? ORDER BY observed_at, group_name, user_name""",
            (cluster_id, since_iso))

    def membership_change_counts(self, cluster_id: str, since_iso: str) -> dict:
        r = self._row("""SELECT SUM(CASE WHEN change='added' THEN 1 ELSE 0 END) AS added,
                                SUM(CASE WHEN change='removed' THEN 1 ELSE 0 END) AS removed
                           FROM membership_event WHERE cluster_id = ? AND observed_at >= ?""", (cluster_id, since_iso))
        return {"added": int(r["added"] or 0), "removed": int(r["removed"] or 0)} if r else {"added": 0, "removed": 0}

    # -- users --------------------------------------------------------------------------------

    def users(self, cluster_id: str) -> list[dict]:
        """One row per User object (Store.users' shape, unpaged: a report is the whole set or nothing,
        and says so in `totals`)."""
        rows = self._rows(
            """SELECT u.user_name, u.full_name, u.created_at, u.providers, u.has_identity,
                      COALESCE(g.group_count, 0) AS group_count, g.first_seen_at,
                      COALESCE(d.direct_bindings, 0) AS direct_bindings
                 FROM ocp_user u
                 LEFT JOIN (SELECT cluster_id, user_name, COUNT(*) AS group_count, MIN(first_seen_at) AS first_seen_at
                              FROM group_member GROUP BY cluster_id, user_name) g
                        ON g.cluster_id = u.cluster_id AND g.user_name = u.user_name
                 LEFT JOIN (SELECT cluster_id, user_name, COUNT(*) AS direct_bindings
                              FROM user_binding WHERE is_platform = 0 GROUP BY cluster_id, user_name) d
                        ON d.cluster_id = u.cluster_id AND d.user_name = u.user_name
                WHERE u.cluster_id = ? ORDER BY u.user_name""", (cluster_id,))
        for r in rows:
            r["providers"] = json.loads(r.pop("providers") or "[]")
            r["logged_in"] = bool(r.pop("has_identity"))
        return rows

    def synced_members_without_user(self, cluster_id: str) -> list[dict]:
        return self._rows(
            """SELECT m.user_name, COUNT(DISTINCT m.group_name) AS group_count, MIN(m.first_seen_at) AS first_seen_at
                 FROM group_member m
                WHERE m.cluster_id = ? AND NOT EXISTS (SELECT 1 FROM ocp_user u WHERE u.cluster_id = m.cluster_id AND u.user_name = m.user_name)
                GROUP BY m.user_name ORDER BY m.user_name""", (cluster_id,))

    # -- the login gate and dormancy ----------------------------------------------------------

    def access_without_login(self, cluster_id: str) -> list[dict]:
        """Store.access_without_login's predicate, unpaged. Empty when no gate group is synced —
        the caller must say 'no gate', never 'nobody'."""
        access = self.access_group(cluster_id)
        if not access or not access["group_name"]:
            return []
        gate = access["group_name"]
        return self._rows(
            """SELECT m.user_name, COUNT(DISTINCT m.group_name) AS group_count, GROUP_CONCAT(DISTINCT m.group_name) AS groups,
                      MIN(m.first_seen_at) AS first_seen_at, u.full_name,
                      EXISTS(SELECT 1 FROM login_event e WHERE e.cluster_id = m.cluster_id AND e.user_name = m.user_name) AS has_tried
                 FROM group_member m LEFT JOIN ocp_user u ON u.cluster_id = m.cluster_id AND u.user_name = m.user_name
                WHERE m.cluster_id = ? AND m.group_name <> ?
                  AND NOT EXISTS(SELECT 1 FROM group_member g WHERE g.cluster_id = m.cluster_id AND g.group_name = ? AND g.user_name = m.user_name)
                GROUP BY m.user_name ORDER BY group_count DESC, m.user_name""", (cluster_id, gate, gate))

    def login_without_access(self, cluster_id: str) -> list[dict]:
        access = self.access_group(cluster_id)
        if not access or not access["group_name"]:
            return []
        gate = access["group_name"]
        return self._rows(
            """SELECT m.user_name, m.first_seen_at, u.full_name,
                      EXISTS(SELECT 1 FROM login_event e WHERE e.cluster_id=m.cluster_id AND e.user_name=m.user_name) AS has_tried
                 FROM group_member m LEFT JOIN ocp_user u ON u.cluster_id=m.cluster_id AND u.user_name=m.user_name
                WHERE m.cluster_id = ? AND m.group_name = ?
                  AND NOT EXISTS(SELECT 1 FROM group_member g WHERE g.cluster_id = m.cluster_id AND g.user_name = m.user_name AND g.group_name <> ?)
                ORDER BY m.user_name""", (cluster_id, gate, gate))

    def never_logged_in_members(self, cluster_id: str) -> list[dict]:
        """Synced members with no User object or a User without an identity: access nobody has used."""
        return self._rows(
            """SELECT m.user_name, COUNT(DISTINCT m.group_name) AS group_count, MIN(m.first_seen_at) AS first_seen_at,
                      CASE WHEN u.user_name IS NULL THEN 'no User object' ELSE 'manual account (no identity)' END AS why
                 FROM group_member m LEFT JOIN ocp_user u ON u.cluster_id = m.cluster_id AND u.user_name = m.user_name
                WHERE m.cluster_id = ? AND (u.user_name IS NULL OR u.has_identity = 0)
                GROUP BY m.user_name ORDER BY m.user_name""", (cluster_id,))

    def last_successful_login(self, cluster_id: str) -> dict[str, str]:
        rows = self._rows("""SELECT user_name, MAX(at) AS last_login_at FROM login_event
                              WHERE cluster_id = ? AND outcome = 'success' GROUP BY user_name""", (cluster_id,))
        return {r["user_name"]: r["last_login_at"] for r in rows}

    # -- login activity -----------------------------------------------------------------------

    def login_summary(self, cluster_id: str, since_iso: str) -> list[dict]:
        return self._rows("""SELECT outcome, COALESCE(provider, '') AS provider, COUNT(*) AS n
                               FROM login_event WHERE cluster_id = ? AND at >= ?
                              GROUP BY outcome, provider ORDER BY outcome, provider""", (cluster_id, since_iso))

    def login_by_user(self, cluster_id: str, since_iso: str, user_name: str | None) -> list[dict]:
        sql = """SELECT user_name, SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END) AS successes,
                        SUM(CASE WHEN outcome<>'success' THEN 1 ELSE 0 END) AS failures,
                        MAX(CASE WHEN outcome='success' THEN at END) AS last_success, MAX(at) AS last_attempt
                   FROM login_event WHERE cluster_id = ? AND at >= ?"""
        params: list = [cluster_id, since_iso]
        if user_name:
            sql += " AND user_name = ?"
            params.append(user_name)
        return self._rows(sql + " GROUP BY user_name ORDER BY failures DESC, user_name", params)

    def rejected_attempts(self, cluster_id: str, since_iso: str) -> list[dict]:
        """Rejected attempts with the facts api.py#_refusal_reason resolves against: gate membership,
        whether the name is a synced member anywhere, whether it has membership history."""
        access = self.access_group(cluster_id)
        gate = access["group_name"] if access and access["group_name"] else None
        return self._rows(
            """SELECT e.user_name, e.at, e.provider, e.detail,
                      CASE WHEN ? IS NULL THEN NULL
                           ELSE EXISTS(SELECT 1 FROM group_member g WHERE g.cluster_id=e.cluster_id AND g.group_name=? AND g.user_name=e.user_name) END AS in_access_group,
                      EXISTS(SELECT 1 FROM group_member g WHERE g.cluster_id=e.cluster_id AND g.user_name=e.user_name) AS known_user,
                      EXISTS(SELECT 1 FROM membership_event h WHERE h.cluster_id=e.cluster_id AND h.user_name=e.user_name) AS has_history
                 FROM login_event e WHERE e.cluster_id = ? AND e.at >= ? AND e.outcome = 'rejected'
                ORDER BY e.at DESC""", (gate, gate, cluster_id, since_iso))

    # -- the sync pipeline --------------------------------------------------------------------

    def groupsyncs(self, cluster_id: str) -> list[dict]:
        rows = self._rows(
            """SELECT s.name, s.namespace, s.schedule, s.last_sync_at, s.generation, s.observed_at,
                      r.failed_at AS error_at, r.observed_generation AS error_generation,
                      CASE WHEN r.message IS NULL THEN 0 ELSE 1 END AS has_error_message,
                      (SELECT COUNT(*) FROM groupsync_provider p JOIN group_state g
                          ON g.cluster_id = p.cluster_id AND g.sync_provider = p.provider_key
                        WHERE p.cluster_id = s.cluster_id AND p.groupsync_name = s.name AND p.groupsync_namespace = s.namespace) AS group_count
                 FROM groupsync_state s LEFT JOIN reconcile_error r ON r.cluster_id = s.cluster_id AND r.groupsync_name = s.name
                WHERE s.cluster_id = ? ORDER BY s.namespace, s.name""", (cluster_id,))
        # error_message deliberately not selected: it can carry the bind DN (§7.5).
        return rows

    def groupsync_presence(self, cluster_id: str) -> bool | None:
        r = self._row("SELECT present FROM groupsync_presence WHERE cluster_id = ?", (cluster_id,))
        return None if r is None else bool(r["present"])

    def sync_counts(self, cluster_id: str, since_iso: str) -> list[dict]:
        return self._rows(
            """SELECT groupsync_name, COUNT(*) AS syncs, MIN(synced_at) AS first_in_window, MAX(synced_at) AS last_in_window,
                      MAX(group_count) AS max_groups, MIN(group_count) AS min_groups
                 FROM sync_event WHERE cluster_id = ? AND observed_at >= ? GROUP BY groupsync_name ORDER BY groupsync_name""",
            (cluster_id, since_iso))

    def operator_configs(self, cluster_id: str) -> dict:
        p = self._row("SELECT present FROM operator_config_presence WHERE cluster_id = ?", (cluster_id,))
        rows = self._rows("""SELECT kind, name, error_at, success_at, observed_at,
                                    CASE WHEN error_message IS NULL THEN 0 ELSE 1 END AS has_error_message
                               FROM operator_config_state WHERE cluster_id = ? ORDER BY kind, name""", (cluster_id,))
        return {"present": None if p is None else bool(p["present"]), "configs": rows}

    # -- the compliance snapshot's scalars ----------------------------------------------------

    def counts(self, cluster_id: str) -> dict:
        one = lambda sql, *p: int((self._row(sql, (cluster_id, *p)) or {"n": 0})["n"] or 0)  # noqa: E731
        return {
            "groups": one("SELECT COUNT(*) AS n FROM group_state WHERE cluster_id=?"),
            "empty_groups": one("SELECT COUNT(*) AS n FROM group_state WHERE cluster_id=? AND member_count=0"),
            "unattributed_groups": one("SELECT COUNT(*) AS n FROM group_state WHERE cluster_id=? AND sync_provider IS NULL"),
            "members": one("SELECT COUNT(DISTINCT user_name) AS n FROM group_member WHERE cluster_id=?"),
            "users": one("SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=?"),
            "users_logged_in": one("SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=? AND has_identity=1"),
            "group_bindings": one("SELECT COUNT(*) AS n FROM rbac_group_binding WHERE cluster_id=?"),
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0"),
            "platform_user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1"),
            "namespaces_with_bindings": one("SELECT COUNT(DISTINCT binding_namespace) AS n FROM (SELECT binding_namespace FROM rbac_group_binding WHERE cluster_id=? AND binding_namespace<>'' UNION SELECT binding_namespace FROM user_binding WHERE cluster_id=? AND binding_namespace<>'')", cluster_id),
            "groupsyncs": one("SELECT COUNT(*) AS n FROM groupsync_state WHERE cluster_id=?"),
        }
