"""Epic B (#382) lab checks, run on COPIES of a backup of the lab's gsd.db, never on the live file.

    python3 walk_epic_b.py <backup.db> <work-dir>

#305: a copy set to top+1 is refused with both numbers, and left byte-identical.
#301: a copy opened by this build plus a walk-only no-op migration top+1 writes the pre-upgrade copy before the
      migration line; the copy verifies against its sidecar and keeps the old user_version; five more starts keep
      exactly that one copy.
R1-R5: the backup is restorable: integrity and schema, the release opens it with no migration and no copy, nothing
      changes on open, the app serves it (poller off), and #301's copy passes the same checks.
Each check prints PASS or FAIL with its measurement.
"""
import hashlib
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

import gsd.store as store
from gsd.config import Settings

SRC, WORK = Path(sys.argv[1]), Path(sys.argv[2])
TOP = store.KNOWN_SCHEMA_VERSION
TABLES = ("membership_event", "sync_event", "login_event", "binding_event", "cluster")
results: list[tuple[str, bool, str]] = []


class Lines(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.lines: list[str] = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def capture() -> Lines:
    h = Lines()
    logger = logging.getLogger("gsd.store")
    logger.setLevel(logging.INFO)
    logger.addHandler(h)
    return h


def check(name: str, ok: bool, detail: str) -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ro(p: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{p}?mode=ro", uri=True)


def fresh(name: str) -> Path:
    d = WORK / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    dst = d / "gsd.db"
    shutil.copyfile(SRC, dst)
    return dst


def counts(p: Path) -> dict:
    c = ro(p)
    try:
        return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
    finally:
        c.close()


# ---- #305: refuse a database newer than the build ------------------------------------------------------
db = fresh("305")
c = sqlite3.connect(db)
c.execute(f"PRAGMA user_version = {TOP + 1}")
c.commit()
c.close()
before = sha(db)
try:
    store.Store(str(db))
    check("#305 refuses a newer database", False, "opened without raising")
except store.StoreSchemaTooNew as exc:
    check("#305 refuses a newer database", f"schema {TOP + 1}" in str(exc) and f"({TOP})" in str(exc), str(exc))
check("#305 leaves the file byte-identical", sha(db) == before, f"sha256 {before[:16]}… before and after")

# ---- R1-R4: the backup itself is restorable ----------------------------------------------------------
def restorable(label: str, db: Path) -> None:
    c = ro(db)
    integrity, version = c.execute("PRAGMA integrity_check").fetchone()[0], c.execute("PRAGMA user_version").fetchone()[0]
    c.close()
    check(f"{label} R1 integrity and schema", integrity == "ok" and version == TOP,
          f"integrity_check={integrity}, user_version={version}, build={TOP}")
    n_before = counts(db)
    h = capture()
    s = store.Store(str(db))
    s.close()
    logging.getLogger("gsd.store").removeHandler(h)
    moved = [m for m in h.lines if "schema migration" in m or "pre-upgrade copy" in m]
    copies = sorted((db.parent / store.PRE_UPGRADE_DIR).glob("*.db")) if (db.parent / store.PRE_UPGRADE_DIR).exists() else []
    check(f"{label} R2 the release opens it", not moved and not copies,
          f"migration/copy log lines: {len(moved)}, pre-upgrade copies: {len(copies)}")
    n_after = counts(db)
    check(f"{label} R3 nothing changes on open", n_before == n_after, ", ".join(f"{t}={n_after[t]}" for t in TABLES))
    from fastapi.testclient import TestClient
    from gsd.api import build_app
    from gsd.config import ClusterConfig
    c = ro(db)
    # The API serves a cluster only when it is configured and enabled (is_served; #96 keeps a retired cluster's
    # history but not its card), so the restored copy is configured as the lab is: its enabled rows, host first.
    enabled = [(r[0], r[1]) for r in c.execute("SELECT id, api_url FROM cluster WHERE enabled = 1 ORDER BY id != 'dashboard', id")]
    clusters = {i for i, _ in enabled}
    marks = ",".join("?" * len(clusters))
    group = c.execute(f"SELECT cluster_id, group_name, COUNT(*) n FROM membership_event WHERE cluster_id IN ({marks}) "
                      "GROUP BY 1, 2 HAVING n BETWEEN 2 AND 100 ORDER BY n DESC LIMIT 1", sorted(clusters)).fetchone()
    c.close()
    if group is None:
        check(f"{label} R4 the app serves it", False, f"no group on the {len(clusters)} enabled clusters has 2-100 stored changes")
        return
    configured = [ClusterConfig(i, u, token_env="WALK_UNUSED") for i, u in enabled]
    with TestClient(build_app(Settings(db_path=str(db), clusters=configured, oauth_proxy_enabled=False),
                              run_poller=False)) as client:
        health = client.get("/healthz").status_code
        served = {row["id"] for row in client.get("/api/clusters").json()}
        detail = client.get(f"/api/clusters/{group[0]}/groups/{group[1]}").json()
    check(f"{label} R4 the app serves it", health == 200 and served == clusters and len(detail.get("changes", [])) == group[2],
          f"/healthz {health}; /api/clusters {len(served)} = enabled cluster rows {len(clusters)}: {served == clusters}; "
          f"group {group[1]!r} on {group[0]}: {len(detail.get('changes', []))} changes served, {group[2]} stored")


restorable("backup", fresh("restore"))

# ---- #301: the pre-upgrade copy, under a walk-only migration top+1 ------------------------------------
db = fresh("301")
store._MIGRATIONS.append((TOP + 1, "walk-only no-op (Epic B lab check)", ["SELECT 1"]))
store.KNOWN_SCHEMA_VERSION = TOP + 1
h = capture()
store.Store(str(db)).close()
logging.getLogger("gsd.store").removeHandler(h)
copy_at = next((i for i, m in enumerate(h.lines) if "pre-upgrade copy" in m), None)
mig_at = next((i for i, m in enumerate(h.lines) if f"schema migration {TOP + 1} applied" in m), None)
check("#301 the copy is taken before the migration", copy_at is not None and mig_at is not None and copy_at < mig_at,
      f"copy line #{copy_at}: {h.lines[copy_at] if copy_at is not None else '-'} | migration line #{mig_at}")
pre = db.parent / store.PRE_UPGRADE_DIR
copies = sorted(pre.glob("*.db"))
side = Path(str(copies[0]) + ".sha256") if copies else None
sidecar_ok = bool(side and side.exists() and side.read_text().split()[0] == sha(copies[0]))
cc = ro(copies[0]) if copies else None
copy_version = cc.execute("PRAGMA user_version").fetchone()[0] if cc else None
cc and cc.close()
check("#301 one copy, verified by its sidecar, at the old schema", len(copies) == 1 and sidecar_ok and copy_version == TOP,
      f"copies={[p.name for p in copies]}, sidecar matches={sidecar_ok}, copy user_version={copy_version}")
for _ in range(5):
    store.Store(str(db)).close()
after = sorted(pre.glob("*.db"))
check("#301 five more starts keep exactly that copy", [p.name for p in after] == [p.name for p in copies],
      f"{len(after)} copy after five starts")
store._MIGRATIONS.pop()
store.KNOWN_SCHEMA_VERSION = TOP

# ---- R5: the pre-upgrade copy is restorable too --------------------------------------------------------
if copies:
    SRC = copies[0]
    restorable("pre-upgrade copy", fresh("restore-pre-upgrade"))

failed = [n for n, ok, _ in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
