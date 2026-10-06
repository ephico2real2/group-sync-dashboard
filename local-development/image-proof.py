"""The runtime image proves itself at build time — run as the runtime user, on the finished
filesystem, by the Containerfile's runtime stage. fluentd-hec's principle: prove from the outside.

Everything here is a thing the base change could have broken, or a removal that must be observed
rather than assumed:

* every module the build stage proved imports again under THIS interpreter — the runtime's, not
  the builder's — with the SQLite the store will use, WAL mode working on /data, and the zoneinfo
  the chart's `timezone` relies on;
* the store gathers planner statistics and its Groups query uses the group-binding index on
  the image's own SQLite (3.46.0 or later);
* `uuid` works while `_uuid` must fail to import: that is the libuuid removal, observed;
* `pip` must fail to import, and the paths the uninstall is known to have missed once (the wheel
  directory, pip's site-packages, the libuuid library, a completion shim) must be gone — a spot
  check of the historically missed paths, not the full lists, which the uninstall step itself
  verifies one by one before this runs;
* the RPM database directory holds rpmdb.sqlite and rpm's own lock files, nothing else.

The script is staged in the build stage and bind-mounted into this one step, never copied into a
layer of the shipped image, and removes what it created under /data; nothing of it ships, in the
filesystem or in any layer beneath it.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import uuid
import zoneinfo

# The build stage proves these under the builder's interpreter; the same list, here, under the
# runtime's. tests/test_containerfile.py holds the two lists equal.
import croniter, fastapi, gsd, httpx, prometheus_client, uvicorn, yaml  # noqa: E401,F401
from gsd.store import Store

REMOVED = (
    "/usr/lib64/libuuid.so.1",
    "/usr/share/python-wheels",
    "/usr/lib/python3.14/site-packages/pip",
    "/usr/share/bash-completion/completions/pip3.14",
    "/rpmdb-erased-files",      # bind-mounted into their step; must not have been copied in
    "/rpmdb-erased-dirs",
)
# Not in that list: this script's own path. It is bind-mounted for exactly this step, so it exists
# while this runs; that it is in no layer of the image is checked from outside, on the saved image.


def must_not_import(name: str, reason: str) -> None:
    try:
        __import__(name)
    except ImportError:
        return
    sys.exit(f"{name} is still importable: {reason}")


def prove_planner_statistics(directory: str) -> None:
    """Prove the store's refresh and real Groups plan on the SQLite that will ship."""
    if sqlite3.sqlite_version_info < (3, 46, 0):
        sys.exit(f"planner statistics proof requires SQLite >= 3.46.0; found {sqlite3.sqlite_version}")

    store = Store(os.path.join(directory, ".planner-statistics-proof.db"))
    reader = None
    try:
        store.upsert_cluster("c", "https://x", True)
        # 100 groups with 10 bindings each: well past the threshold. Measured on SQLite 3.53.4, three groups with
        # one binding each is already enough for the group index; a seed at the threshold could flip with a future
        # SQLite and fail an image build for no defect, so this one has a margin of about thirty times.
        store._conn.executemany(
            "INSERT INTO group_state(cluster_id, name, member_count, sync_provider, observed_at) "
            "VALUES ('c', ?, 1, 'gs_ldap', 't')", [(f"g{i}",) for i in range(100)])
        store._conn.executemany(
            "INSERT INTO rbac_group_binding(cluster_id, binding_kind, binding_namespace, binding_name, "
            "role_kind, role_name, subject_kind, group_name, observed_at) "
            "VALUES ('c', 'RoleBinding', 'ns', ?, 'ClusterRole', 'view', 'Group', ?, 't')",
            [(f"b{i}", f"g{i % 100}") for i in range(1000)])
        store._conn.commit()
        store.maintain()

        reader = store._reader()
        if (not reader.execute("SELECT 1 FROM sqlite_schema WHERE name = 'sqlite_stat1'").fetchone()
                or not reader.execute(
                    "SELECT 1 FROM sqlite_stat1 WHERE idx = 'rbac_binding_by_group'").fetchone()):
            sys.exit("planner statistics proof failed: maintain() did not gather sqlite_stat1 "
                     "for rbac_binding_by_group")

        seen: list[str] = []
        reader.set_trace_callback(seen.append)
        try:
            store.groups("c", "all")
        finally:
            reader.set_trace_callback(None)
        if len(seen) != 1:
            sys.exit(f"planner statistics proof expected one Groups query; captured {seen!r}")
        plan = " | ".join(row[3] for row in reader.execute("EXPLAIN QUERY PLAN " + seen[0]))
        expected = "SEARCH b USING INDEX rbac_binding_by_group (cluster_id=? AND group_name=?)"
        if expected not in plan:
            sys.exit(f"planner statistics proof failed: expected {expected}; got {plan}")
    finally:
        if reader is not None:
            reader.close()
        store.close()
    print("planner statistics proof OK; sqlite", sqlite3.sqlite_version)


def main() -> None:
    zoneinfo.ZoneInfo("America/New_York")
    uuid.uuid4()
    must_not_import("_uuid", "libuuid was not removed")
    must_not_import("pip", "pip was not removed")
    for path in REMOVED:
        if os.path.lexists(path):
            sys.exit(f"still present: {path}")
    # rpmdb.sqlite and rpm's own dot-lock files, nothing else — no WAL side files, no leftover
    # Packages. Not an exact listing: the base floats, and on 2026-09-09 its rpm began leaving
    # `.keyring.lock` beside `.rpm.lock` after the pack stage's erase, which failed this proof
    # against a list of two names (measured in CI on 2026-09-11).
    listing = sorted(os.listdir("/usr/lib/sysimage/rpm"))
    locks = [name for name in listing if name.startswith(".") and name.endswith(".lock")]
    if "rpmdb.sqlite" not in listing or sorted(locks + ["rpmdb.sqlite"]) != listing:
        sys.exit(f"the RPM database directory holds {listing}, not rpmdb.sqlite and rpm's lock files")

    db = "/data/.build-proof.db"
    conn = sqlite3.connect(db)
    if conn.execute("pragma journal_mode=wal").fetchone() != ("wal",):
        sys.exit("WAL mode did not take on /data")
    conn.execute("create table t(x)")
    conn.commit()
    conn.close()
    prove_planner_statistics("/data")
    for name in os.listdir("/data"):
        os.remove(os.path.join("/data", name))
    if os.listdir("/data"):
        sys.exit("/data is not empty after the proof")

    print("runtime proof OK; sqlite", sqlite3.sqlite_version)


if __name__ == "__main__":
    main()
