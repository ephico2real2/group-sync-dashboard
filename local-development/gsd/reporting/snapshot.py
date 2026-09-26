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

from ..kpi.predicates import GROUP_EMPTY, GROUP_UNATTRIBUTED
from ..store import KNOWN_SCHEMA_VERSION, Store, _harden

log = logging.getLogger(__name__)

#: Store.backup / Store.snapshot name their files gsd-<%Y%m%dT%H%M%S.%fZ>.db.
_STAMP = re.compile(r"^gsd-(\d{8}T\d{6}\.\d{6}Z)\.db$")
CLUSTER_SCOPE = Store.CLUSTER_SCOPE
PRIVILEGE_RANK = "CASE role_name WHEN 'cluster-admin' THEN 4 WHEN 'admin' THEN 3 WHEN 'edit' THEN 2 ELSE 1 END"

#: Report-only: drop system:* GROUP subjects (the Store's built_in arm,
#: `g.name IS NULL AND b.group_name LIKE 'system:%'`). They stay in the copy so
#: the RBAC-policy tab and unmanaged-audit still see them; reports must not list
#: them as a person's grant or as unmanaged/handmade (#147). Same LIKE as the CASE.
#: The `system:` test is for Group subjects only; a platform ServiceAccount or User is omitted by
#: the flag the poller stored (is_platform: a platform namespace, a system: user, kubeadmin — the
#: operator's rule, #353), so no report lists the platform's own identities as a finding either.
#: PLATFORM-CLASSIFICATION (#255, #353): the reports' omit
_OMIT_SYSTEM_GROUP_SUBJECTS = (" AND NOT (b.subject_kind = 'Group' AND b.group_name LIKE 'system:%')"
                               " AND b.is_platform = 0")   # PLATFORM-CLASSIFICATION (#255, #353): the flag the poller stored
#: The group-shaped reads (a namespace's groups, a group's binding count): Group subjects only.
_GROUP_SUBJECTS_ONLY = " AND b.subject_kind = 'Group'"


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
            # A newer copy is refused (§4.4), against the store's own number: one source for both services.
            if self.schema_version > KNOWN_SCHEMA_VERSION:
                raise SnapshotError(
                    f"snapshot schema {self.schema_version} is newer than this report service understands "
                    f"({KNOWN_SCHEMA_VERSION}); the reporting image must be the dashboard's appVersion")
            self._tables = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # An OLDER copy is accepted (only a newer one is refused): while the pods roll, the newest copy
            # on the volume is the previous dashboard's until the new one writes. Before migration 20 the
            # binding table held Group rows only and had no subject columns, and every binding read here
            # names them — so the old table is read through a TEMP view that says what its rows are (a TEMP
            # object shadows the copy's own name; the immutable copy itself is never written) (SPEC_U1).
            if "rbac_group_binding" in self._tables and "subject_kind" not in {
                    r[1] for r in self._conn.execute("PRAGMA main.table_info(rbac_group_binding)")}:
                self._conn.execute("CREATE TEMP VIEW rbac_group_binding AS"
                                   " SELECT *, 'Group' AS subject_kind, '' AS subject_namespace, 0 AS is_platform"
                                   " FROM main.rbac_group_binding")
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

    def selector_capture_present(self) -> bool:
        """Whether this copy carries the namespace-label capture at all. A copy without the table
        cannot tell 'no namespace matches' from 'labels never captured' — an older dashboard's copy in
        the rolling window — so a caller answering a count or expanding a selection must degrade to
        'unknown', never an attested zero (review 2026-09-16, Fable N3 / Codex)."""
        return self.has_table("cluster_namespace_label")

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
        multi-dimension multi-select. ONE query for the whole estate (review PR #129, 2nd pass, V4-F1):
        the per-cluster-per-key gather was 2 + clusters x (dimensions + 1) reads on every 60s catalogue
        load, which does not scale to many clusters.

        The whole gather lives here, not in the caller, for one reason (the #117 D1 scar): a copy that
        OPENED cleanly can still raise sqlite3.Error from a later table read (partial b-tree damage on
        a copy that rotted on disk after it was written). Translated to SnapshotError HERE, at the
        backend boundary, that becomes the catalogue's designed empty-map degradation instead of a 500
        — and sqlite3 never has to be named in server.py (the storage seam,
        tests/test_storage_seam.py). A genuine query bug would fail the catalogue's own value
        assertions in the suite, so this does not mask one."""
        try:
            keys = [k for k in keys if k]
            cluster_ids = [row["id"] for row in self.clusters()]
            result = {cid: [{"label": k, "values": []} for k in keys] for cid in cluster_ids}
            if not keys or not self.has_table("cluster_namespace_label"):
                return result
            marks = ",".join("?" for _ in keys)
            positions = {k: i for i, k in enumerate(keys)}
            for row in self._rows(
                    "SELECT DISTINCT cluster_id, key, value FROM cluster_namespace_label "
                    f"WHERE key IN ({marks}) ORDER BY cluster_id, key, value", tuple(keys)):
                cid, key = row["cluster_id"], row["key"]
                if cid in result and key in positions:
                    result[cid][positions[key]]["values"].append(row["value"])
            return result
        except sqlite3.Error as exc:
            raise SnapshotError(f"cannot read snapshot {Path(self.path).name}: not readable SQLite data") from exc

    def namespaces_for_selectors(self, cluster_id: str, selectors: dict[str, list[str]]) -> list[str]:
        """Namespace names matching EVERY selector dimension (AND across labels), where a dimension
        matches ANY of its values (OR within). Composes the single-key `namespaces_for_metadata`
        expansion and intersects in Python, so the SQL stays the form already tested and the AND is
        explicit (docs/DESIGN_reporting_selectors_snapshots_and_windows.md §3). Empty selection -> [].

        A sqlite3.Error from a table read after a clean open becomes SnapshotError HERE, the same wrap
        as namespace_selector_dimensions, so GET /namespace-count degrades to a null count instead of a
        500 and sqlite3 is never named in server.py (the #117 D1 scar; storage seam)."""
        if not selectors or not self.has_table("cluster_namespace_label"):
            return []
        try:
            result: set[str] | None = None
            for key, values in selectors.items():
                matched = set(self.namespaces_for_metadata(cluster_id, key, values))
                result = matched if result is None else (result & matched)
                if not result:
                    return []
            return sorted(result or set())
        except sqlite3.Error as exc:
            raise SnapshotError(f"cannot read snapshot {Path(self.path).name}: not readable SQLite data") from exc

    # -- #149 R7: what the report forms can offer from the snapshot ---------------------------

    DISCOVERED_CAP = 5000

    def discovered(self, cluster_id: str, mnemonic_key: str, group_key: str) -> dict:
        """The discovered lookups for one cluster: identity providers (from ocp_user.providers), role
        names (both binding tables), user names, group names, the mnemonic label's values and the
        exact-group label's values — each sorted, each cut at DISCOVERED_CAP with `truncated` said. One
        read per set; a form load pays six small queries, not a scan per keystroke.

        A sqlite3.Error from a table read after a clean open becomes SnapshotError HERE, the same wrap
        as namespace_selector_dimensions, so GET /api/discovered degrades to empty menus instead of a
        500 and sqlite3 is never named in server.py (review of #222, Codex M4; the storage seam)."""
        try:
            return self._discovered(cluster_id, mnemonic_key, group_key)
        except sqlite3.Error as exc:
            raise SnapshotError(f"cannot read snapshot {Path(self.path).name}: not readable SQLite data") from exc

    def _discovered(self, cluster_id: str, mnemonic_key: str, group_key: str) -> dict:
        def cut(values: list[str]) -> dict:
            return {"values": values[:self.DISCOVERED_CAP], "truncated": len(values) > self.DISCOVERED_CAP}
        # Bounded reads (review of #222, Grok): LIMIT cap+1 on the two name lists, so a cluster with
        # fifty thousand users costs the form 5,001 rows, not all of them; the providers come from
        # the same bounded read, and a blob that is not JSON counts as no provider rather than a 500.
        limit = self.DISCOVERED_CAP + 1
        providers: set[str] = set()
        users: list[str] = []
        if self.has_table("ocp_user"):
            for r in self._rows("SELECT user_name, providers FROM ocp_user WHERE cluster_id = ? ORDER BY user_name LIMIT ?", (cluster_id, limit)):
                users.append(r["user_name"])
                try:
                    providers.update(json.loads(r["providers"] or "[]"))
                except ValueError:
                    pass
        roles: set[str] = set()
        # The roles a report's role filter can match: those bound to a group (the Group rows) or named
        # directly to a person (user_binding). A role bound only to ServiceAccounts is never offered —
        # nothing that takes this list reads account grants (SPEC_U1; on the lab 356 roles against 66).
        for table, only in (("rbac_group_binding", " AND subject_kind = 'Group'"), ("user_binding", "")):
            if self.has_table(table):
                roles.update(r["role_name"] for r in self._rows(f"SELECT DISTINCT role_name FROM {table} WHERE cluster_id = ?{only}", (cluster_id,)))
        # The member count beside each group name (operator, 2026-09-21): group_state's count as of THIS snapshot, a
        # sibling `members` map so `values` stays the list of strings every consumer reads; cut where the names are.
        group_rows = self._rows("SELECT name, member_count FROM group_state WHERE cluster_id = ? ORDER BY name LIMIT ?", (cluster_id, limit)) \
            if self.has_table("group_state") else []
        groups = [g["name"] for g in group_rows]
        # #143 phase 2: the namespaces the poll listed (rbac.namespaces) — the advanced field's picker; empty
        # without the grant, and the form falls back to a text field.
        namespaces = [r["name"] for r in self._rows("SELECT name FROM cluster_namespace WHERE cluster_id = ? ORDER BY name LIMIT ?", (cluster_id, limit))] \
            if self.has_table("cluster_namespace") else []
        return {"providers": cut(sorted(providers)), "roles": cut(sorted(roles)), "users": cut(users),
                "groups": {**cut(groups), "members": {g["name"]: g["member_count"] for g in group_rows[:self.DISCOVERED_CAP]}},
                "mnemonics": cut(self.namespace_metadata_values(cluster_id, mnemonic_key)),
                "oud-groups": cut(self.namespace_metadata_values(cluster_id, group_key)),
                "namespaces": cut(namespaces)}

    def members_of_groups(self, cluster_id: str, group_names: list[str]) -> set[str]:
        """The user names that are members of ANY of the groups — a group filter on person-keyed data."""
        if not group_names or not self.has_table("group_member"):
            return set()
        marks = ",".join("?" for _ in group_names)
        return {r["user_name"] for r in self._rows(
            f"SELECT DISTINCT user_name FROM group_member WHERE cluster_id = ? AND group_name IN ({marks})",
            (cluster_id, *group_names))}

    def groups_for_mnemonics(self, cluster_id: str, mnemonic_key: str, group_key: str, mnemonics: list[str]) -> set[str]:
        """The exact groups a business mnemonic names: the namespaces carrying `mnemonic_key` in
        `mnemonics`, then the `group_key` label those namespaces pin (#149 R7 — a naming convention
        was measured unreliable: beta → app-ocp-rbac-spar-ns-audit, alpha → bda-rbac-trino-alpha-users).
        Namespaces without the group label contribute nothing."""
        if not mnemonics or not mnemonic_key or not group_key or not self.has_table("cluster_namespace_label"):
            return set()
        names = self.namespaces_for_metadata(cluster_id, mnemonic_key, mnemonics)
        if not names:
            return set()
        marks = ",".join("?" for _ in names)
        return {r["value"] for r in self._rows(
            f"SELECT DISTINCT value FROM cluster_namespace_label WHERE cluster_id = ? AND key = ? AND name IN ({marks})",
            (cluster_id, group_key, *names))}

    def namespace_label_map(self, cluster_id: str, key: str) -> dict[str, str]:
        """namespace → the value of one label, for grouping a namespace report's sections."""
        if not key or not self.has_table("cluster_namespace_label"):
            return {}
        return {r["name"]: r["value"] for r in self._rows(
            "SELECT name, value FROM cluster_namespace_label WHERE cluster_id = ? AND key = ?", (cluster_id, key))}

    def login_capture_status(self, cluster_id: str) -> dict | None:
        return self._row("SELECT started_at, last_read_at FROM login_capture_status WHERE cluster_id = ?", (cluster_id,))

    def access_group(self, cluster_id: str) -> dict | None:
        return self._row("SELECT dn, source, group_name, observed_at FROM cluster_access_group WHERE cluster_id = ?", (cluster_id,))

    # -- bindings -----------------------------------------------------------------------------

    def binding_namespaces(self, cluster_id: str) -> list[dict]:
        """DISTINCT namespaces observed on a person-facing binding, with counts; '' is the
        cluster-scope sentinel.

        `system:*` GROUP subjects are omitted here, matching `group_bindings` (#147), so a namespace
        whose only grant is an image-puller `system:serviceaccounts:<ns>` binding is not reported as
        observed over an empty table."""
        return self._rows(
            """SELECT ns AS namespace, SUM(g) AS group_bindings, SUM(u) AS user_bindings
                 FROM (SELECT CASE WHEN b.binding_namespace='' THEN ? ELSE b.binding_namespace END AS ns, 1 AS g, 0 AS u
                         FROM rbac_group_binding b WHERE b.cluster_id=?"""
            + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS + """
                       UNION ALL
                       SELECT CASE WHEN binding_namespace='' THEN ? ELSE binding_namespace END, 0, 1
                         -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag, on the reports' copy
                         FROM user_binding WHERE cluster_id=? AND is_platform=0)
                GROUP BY ns ORDER BY ns""",
            (CLUSTER_SCOPE, cluster_id, CLUSTER_SCOPE, cluster_id))

    def group_bindings(self, cluster_id: str, namespaces: list[str] | None = None, *,
                       kinds: tuple[str, ...] = ("Group",)) -> list[dict]:
        """Bindings a report may list, classified by the dashboard's own CASE, with reach.

        `kinds` is the subject kinds to list: Group only by default, which is what the group-shaped
        reports (namespace access, privileged access, the matrix, the certification) want; the
        binding-findings report asks for every kind, because a ServiceAccount or User grant outside
        the policy system is a finding too (#353, SPEC_U1). A row of another kind carries
        `subject_kind`, `subject_namespace` and null reach.

        `system:*` virtual groups are omitted here (see `_OMIT_SYSTEM_GROUP_SUBJECTS`). The CASE is
        still Store._FINDING_CASE — a remaining row cannot disagree with the RBAC-policy tab.
        Ordered namespace, finding severity, subject, binding — deterministic so two reports diff cleanly."""
        reach = """
                      CASE WHEN g.name IS NULL THEN NULL ELSE COALESCE(li.member_count, 0) END AS member_count,
                      CASE WHEN g.name IS NULL OR ust.cluster_id IS NULL THEN NULL
                           ELSE COALESCE(li.logged_in_count, 0) END AS logged_in_count,"""
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name, b.role_kind, b.role_name,
                         b.subject_kind, b.subject_namespace, b.is_platform, b.group_name, b.managed_source, b.exception,""" + reach
               + Store._FINDING_CASE + " AS finding"
               + Store._FINDING_JOINS + Store._REACH_JOIN + Store._FINDING_WHERE
               + _OMIT_SYSTEM_GROUP_SUBJECTS
               + " AND b.subject_kind IN (" + ",".join("?" * len(kinds)) + ")")
        params: list = [cluster_id, *kinds]
        if namespaces is not None:
            sql += " AND b.binding_namespace IN (" + ",".join("?" * len(namespaces)) + ")"
            params += namespaces
        sql += """ ORDER BY b.binding_namespace,
                          CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1 WHEN 'unmanaged' THEN 2
                                       WHEN 'ok' THEN 3 ELSE 4 END,
                          b.group_name, b.binding_name, b.subject_kind, b.subject_namespace"""
        return self._rows(sql, params)

    def findings_counts(self, cluster_id: str) -> dict[str, int]:
        rows = self._rows("SELECT" + Store._FINDING_CASE + " AS finding, COUNT(*) AS n"
                          + Store._FINDING_JOINS + Store._FINDING_WHERE
                          + _OMIT_SYSTEM_GROUP_SUBJECTS + " GROUP BY finding", (cluster_id,))
        return {r["finding"]: int(r["n"]) for r in rows}

    def user_bindings(self, cluster_id: str, namespaces: list[str] | None = None,
                      include_platform: bool = False) -> list[dict]:
        sql = """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name, user_name, is_platform
                   FROM user_binding WHERE cluster_id=?"""
        params: list = [cluster_id]
        if not include_platform:
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view hides the platform's identities by default
            sql += " AND is_platform=0"
        if namespaces is not None:
            sql += " AND binding_namespace IN (" + ",".join("?" * len(namespaces)) + ")"
            params += namespaces
        sql += f" ORDER BY binding_namespace, {PRIVILEGE_RANK} DESC, user_name, binding_name"
        return self._rows(sql, params)

    def platform_user_binding_count(self, cluster_id: str) -> int:
        # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count
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
                      (SELECT COUNT(*) FROM rbac_group_binding b WHERE b.cluster_id = g.cluster_id AND b.subject_kind = 'Group' AND b.group_name = g.name) AS bindings
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
                              -- PLATFORM-CLASSIFICATION (#255, #353): a person's direct grants, the platform's identities left out
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

    def login_summary(self, cluster_id: str, since_iso: str, user_names: set[str] | None = None) -> list[dict]:
        """Attempts by outcome and provider in the window; `user_names` narrows them to the subject scope
        (an empty scope — named groups with no members — counts nothing), None counts the cluster."""
        sql = "SELECT outcome, COALESCE(provider, '') AS provider, COUNT(*) AS n FROM login_event WHERE cluster_id = ? AND at >= ?"
        params: list = [cluster_id, since_iso]
        if user_names is not None:
            if not user_names:
                return []
            names = sorted(user_names)
            sql += " AND user_name IN (" + ",".join("?" for _ in names) + ")"
            params.extend(names)
        return self._rows(sql + " GROUP BY outcome, provider ORDER BY outcome, provider", params)

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
            # The dashboard's own predicates (gsd/kpi/predicates.py), so the signed figure and the
            # KPI band count the same groups.
            "empty_groups": one(f"SELECT COUNT(*) AS n FROM group_state WHERE cluster_id=? AND {GROUP_EMPTY}"),
            "unattributed_groups": one(f"SELECT COUNT(*) AS n FROM group_state WHERE cluster_id=? AND {GROUP_UNATTRIBUTED}"),
            "members": one("SELECT COUNT(DISTINCT user_name) AS n FROM group_member WHERE cluster_id=?"),
            "users": one("SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=?"),
            "users_logged_in": one("SELECT COUNT(*) AS n FROM ocp_user WHERE cluster_id=? AND has_identity=1"),
            "group_bindings": one("SELECT COUNT(*) AS n FROM rbac_group_binding b WHERE b.cluster_id=?"
                                  + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS),
            # PLATFORM-CLASSIFICATION (#255, #353): the compliance snapshot's user-binding scalars split on the direct-user view's flag
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0"),
            "platform_user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1"),   # PLATFORM-CLASSIFICATION (#255, #353)
            "namespaces_with_bindings": one(
                "SELECT COUNT(DISTINCT binding_namespace) AS n FROM ("
                "SELECT b.binding_namespace FROM rbac_group_binding b"
                " WHERE b.cluster_id=? AND b.binding_namespace<>''"
                + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS
                + " UNION SELECT binding_namespace FROM user_binding"
                # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag, on the reports' copy
                " WHERE cluster_id=? AND binding_namespace<>'' AND is_platform=0)", cluster_id),
            "groupsyncs": one("SELECT COUNT(*) AS n FROM groupsync_state WHERE cluster_id=?"),
        }
