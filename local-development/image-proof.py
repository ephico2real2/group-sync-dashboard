"""The runtime image proves itself at build time — run as the runtime user, on the finished
filesystem, by the Containerfile's runtime stage. fluentd-hec's principle: prove from the outside.

Everything here is a thing the base change could have broken, or a removal that must be observed
rather than assumed:

* every module the build stage proved imports again under THIS interpreter — the runtime's, not
  the builder's — with the SQLite the store will use, WAL mode working on /data, and the zoneinfo
  the chart's `timezone` relies on;
* `uuid` works while `_uuid` must fail to import: that is the libuuid removal, observed;
* `pip` must fail to import, and the paths the uninstall removed must be gone;
* the RPM database directory holds exactly the two files the base shipped.

The script removes what it created under /data and then itself; nothing of it ships.
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

REMOVED = (
    "/usr/lib64/libuuid.so.1",
    "/usr/share/python-wheels",
    "/usr/lib/python3.14/site-packages/pip",
    "/usr/share/bash-completion/completions/pip3.14",
    "/rpmdb-erased-files",
    "/rpmdb-erased-dirs",
)


def must_not_import(name: str, reason: str) -> None:
    try:
        __import__(name)
    except ImportError:
        return
    sys.exit(f"{name} is still importable: {reason}")


def main() -> None:
    zoneinfo.ZoneInfo("America/New_York")
    uuid.uuid4()
    must_not_import("_uuid", "libuuid was not removed")
    must_not_import("pip", "pip was not removed")
    for path in REMOVED:
        if os.path.lexists(path):
            sys.exit(f"still present: {path}")
    listing = sorted(os.listdir("/usr/lib/sysimage/rpm"))
    if listing != [".rpm.lock", "rpmdb.sqlite"]:
        sys.exit(f"the RPM database directory holds {listing}, not the base's two files")

    db = "/data/.build-proof.db"
    conn = sqlite3.connect(db)
    if conn.execute("pragma journal_mode=wal").fetchone() != ("wal",):
        sys.exit("WAL mode did not take on /data")
    conn.execute("create table t(x)")
    conn.commit()
    conn.close()
    for name in os.listdir("/data"):
        os.remove(os.path.join("/data", name))
    if os.listdir("/data"):
        sys.exit("/data is not empty after the proof")

    print("runtime proof OK; sqlite", sqlite3.sqlite_version)
    os.remove(__file__)


if __name__ == "__main__":
    main()
