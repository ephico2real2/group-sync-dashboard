"""K1/K2 drive: #305 (StoreSchemaTooNew) and #301 (_pre_upgrade_copy) composed, on the worktree's gsd.

Image N is simulated by setting gsd.store.KNOWN_SCHEMA_VERSION and trimming _MIGRATIONS; both are read at
call time by Store.__init__ and _pre_upgrade_copy. A database "written by image N" is the real Store's,
rewound to N (the same construction tests/test_pre_upgrade_copy.py uses).
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import gsd
import gsd.store as S

print("gsd:", gsd.__file__)
REAL_KNOWN = S.KNOWN_SCHEMA_VERSION
REAL_MIGRATIONS = list(S._MIGRATIONS)
N = REAL_KNOWN            # "image N" = this build (20)
os.environ["POD_NAME"] = "gsd-drive-pod"
ROOT = Path(tempfile.mkdtemp(prefix="k1k2-", dir=os.environ["SCRATCH"]))
results = []


def image(known):
    """Make the module behave as the build whose highest migration is `known`."""
    S.KNOWN_SCHEMA_VERSION = known
    if known <= REAL_KNOWN:
        S._MIGRATIONS = [m for m in REAL_MIGRATIONS if m[0] <= known]
    else:
        S._MIGRATIONS = REAL_MIGRATIONS + [(k, f"synthetic {k}", [f"CREATE TABLE IF NOT EXISTS synthetic_{k}(x)"])
                                           for k in range(REAL_KNOWN + 1, known + 1)]


def facts(path):
    if not Path(path).exists():
        return None
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        v = c.execute("PRAGMA user_version").fetchone()[0]
        fresh = c.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is None
        n = None if fresh else c.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0]
        m = None if fresh else c.execute("SELECT COUNT(*) FROM membership_event").fetchone()[0]
        return {"user_version": v, "fresh": fresh, "sync_events": n, "membership_events": m}
    finally:
        c.close()


def copies(db):
    d = Path(db).parent / S.PRE_UPGRADE_DIR
    return sorted(p.name for p in d.glob("*")) if d.exists() else []


def db_at(version, case):
    """A database written by the real build, rewound to `version` (or fresh/absent per case)."""
    d = ROOT / case
    d.mkdir()
    db = d / "gsd.db"
    if version is None:
        return db
    st = S.Store(str(db))
    st.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    st.record_sync_event("crc", "corp", "ns", "2026-09-26T10:00:00Z", "2026-09-26T10:00:30Z", "0 * * * *", 3)
    st.close()
    c = sqlite3.connect(db)
    c.execute(f"PRAGMA user_version = {version}")
    c.commit()
    c.close()
    return db


def start(db, known, label):
    """One start of image `known` on `db`: returns the outcome and the state after."""
    image(known)
    wal_before = os.path.getsize(f"{db}-wal") if os.path.exists(f"{db}-wal") else 0
    before = facts(db)
    try:
        st = S.Store(str(db))
        st.close()
        outcome = "opened"
    except S.StoreSchemaTooNew as exc:
        outcome = f"REFUSED StoreSchemaTooNew: {exc}"
    except S.StorePreUpgradeCopyFailed as exc:
        outcome = f"REFUSED StorePreUpgradeCopyFailed: {exc}"
    except Exception as exc:  # the simulated crash
        outcome = f"CRASH {type(exc).__name__}: {exc}"
    wal_after = os.path.getsize(f"{db}-wal") if os.path.exists(f"{db}-wal") else 0
    row = {"case": label, "image": known, "before": before, "outcome": outcome, "after": facts(db),
           "copies": copies(db), "wal_bytes": [wal_before, wal_after]}
    results.append(row)
    print(json.dumps(row, default=str))
    return row


def hot_wal(db):
    """Commit rows into the -wal from another process and kill it before any checkpoint."""
    w = subprocess.Popen([sys.executable, "-c", (
        "import sqlite3, sys, time\n"
        "c = sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_autocheckpoint=0')\n"
        "c.executemany(\"INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at)"
        " VALUES ('crc', 'g', ?, 'added', '2026-09-26T00:00:00Z')\", [(f'u{i}',) for i in range(23)])\n"
        "c.commit(); print('ready', flush=True); time.sleep(30)\n"), str(db)], stdout=subprocess.PIPE, text=True)
    assert w.stdout.readline().strip() == "ready"
    w.kill(); w.wait(); w.stdout.close()


# ── K1: image N against every file state ───────────────────────────────────────────────────
start(db_at(None, "k1-absent"), N, "K1 absent file")
db = ROOT / "k1-zero-byte" / "gsd.db"; db.parent.mkdir(); db.touch()
start(db, N, "K1 zero-byte file")
start(db_at(N, "k1-at-N"), N, "K1 file at N")
start(db_at(N - 1, "k1-at-N-1"), N, "K1 file at N-1")
start(db_at(N + 1, "k1-at-N+1"), N, "K1 file at N+1")
db = db_at(N - 1, "k1-hot-wal-N-1"); hot_wal(db)
r = start(db, N, "K1 file at N-1 with a hot WAL (23 rows committed only in -wal)")
copy = sorted((db.parent / S.PRE_UPGRADE_DIR).glob("*.db"))[0]
print("   copy holds:", facts(copy))
db = db_at(N + 1, "k1-hot-wal-N+1"); hot_wal(db)
start(db, N, "K1 file at N+1 with a hot WAL")
print("   after refusal:", facts(db), "wal exists:", os.path.exists(f"{db}-wal"))

# crash between the copy and the migration, then the next start
db = db_at(N - 1, "k1-crash-between")
real_migrate = S._migrate
def crash_migrate(conn):
    raise RuntimeError("simulated crash after the copy, before the migration")
S._migrate = crash_migrate
start(db, N, "K1 crash between copy and migration (first start)")
S._migrate = real_migrate
start(db, N, "K1 next start after that crash")

# a .tmp left by a process killed mid-copy
db = db_at(N - 1, "k1-tmp-left")
d = db.parent / S.PRE_UPGRADE_DIR; d.mkdir()
(d / f"pre-upgrade-20260101T000000.000000Z-schema-{N-1}-to-{N}-dead.db.tmp").write_bytes(b"torn")
(d / f"pre-upgrade-20260101T000000.000000Z-schema-{N-1}-to-{N}-dead.db.sha256").write_text("x  y\n")
start(db, N, "K1 next start after a kill mid-copy (.tmp + orphan sidecar left)")

# ── K2: upgrade, roll back, restore, re-run old image, upgrade again ────────────────────────
db = db_at(N - 1, "k2")
start(db, N, "K2.1 upgrade N-1 -> N")
start(db, N - 1, "K2.2 roll back to image N-1")
copy = sorted((db.parent / S.PRE_UPGRADE_DIR).glob("*.db"))[0]
for side in ("-wal", "-shm"):
    Path(f"{db}{side}").unlink(missing_ok=True)
shutil.copyfile(copy, db)                                     # runbook §4a: rm -wal/-shm, cat copy > gsd.db
print("   restored", copy.name, "->", facts(db))
r = start(db, N - 1, "K2.3 image N-1 on the restored copy")
image(N - 1); st = S.Store(str(db))
st.record_sync_event("crc", "corp", "ns", "2026-09-27T10:00:00Z", "2026-09-27T10:00:30Z", "0 * * * *", 4)
st.close()
print("   image N-1 wrote one more row:", facts(db))
start(db, N, "K2.4 upgrade N-1 -> N again, the earlier -to-N- copy still there")
copy_now = sorted((db.parent / S.PRE_UPGRADE_DIR).glob("*.db"))
print("   copies now:", [c.name for c in copy_now], "copy holds:", facts(copy_now[-1]))
# runbook §6: move the earlier -to-N- copy and its .sha256 out, then retry
for side in ("-wal", "-shm"):
    Path(f"{db}{side}").unlink(missing_ok=True)
shutil.copyfile(copy, db)
(db.parent / "pre-restore").mkdir()
for p in copy_now:
    shutil.move(p, db.parent / "pre-restore" / p.name)
    shutil.move(p.with_name(p.name + ".sha256"), db.parent / "pre-restore" / (p.name + ".sha256"))
image(N - 1); st = S.Store(str(db))
st.record_sync_event("crc", "corp", "ns", "2026-09-27T11:00:00Z", "2026-09-27T11:00:30Z", "0 * * * *", 5)
st.close()
start(db, N, "K2.5 upgrade again after moving the earlier copy out (runbook §6)")
copy_now = sorted((db.parent / S.PRE_UPGRADE_DIR).glob("*.db"))
print("   copies now:", [c.name for c in copy_now], "copy holds:", facts(copy_now[-1]))

(ROOT / "results.json").write_text(json.dumps(results, indent=1, default=str))
print("root:", ROOT)
