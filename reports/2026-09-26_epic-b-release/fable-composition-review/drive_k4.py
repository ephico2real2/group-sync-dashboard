"""K4: after a rollback + restore, the dashboard (Store) and the report service (Snapshot) on one volume.

Image N is the real build (KNOWN=20). The volume holds gsd.db and /report snapshots as the leader writes them
(Store.snapshot), the newest of which was written by image N+1 (user_version 21) before the rollback.
"""
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import gsd.store as S
from gsd.reporting.snapshot import Snapshot, SnapshotError, newest_snapshot

ROOT = Path(tempfile.mkdtemp(prefix="k4-", dir=os.environ["SCRATCH"]))
db = ROOT / "gsd.db"
report = ROOT / "report"
out = []


def report_pod():
    """What the report pod's readyz / a run sees: newest snapshot -> open -> (stamp, schema) or the refusal."""
    try:
        with Snapshot(newest_snapshot(str(report))) as snap:
            info = snap.info()
            return f"SERVES snapshot {Path(snap.path).name} schema {info.schema_version}"
    except SnapshotError as exc:
        return f"REFUSES: {exc}"


def say(step, dashboard):
    row = {"step": step, "dashboard": dashboard, "report": report_pod(),
           "snapshots": sorted(p.name for p in report.glob("*.db"))}
    out.append(row)
    print(json.dumps(row))


# 1. Image N+1 ran: its database is at 21 and it wrote the newest snapshot at 21.
st = S.Store(str(db))
st.upsert_cluster("crc", "https://api.crc.testing:6443", True)
st.snapshot(str(report), keep=2)                       # a snapshot at 20 from "before the upgrade"
st.close()
time.sleep(0.01)
conn = sqlite3.connect(db); conn.execute("PRAGMA user_version = 21"); conn.commit(); conn.close()
st_conn = sqlite3.connect(db)                            # "image N+1" writes the newest snapshot at 21
newest = report / f"gsd-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}.999999Z.db"
st_conn.execute(f"VACUUM INTO '{newest}'"); st_conn.close()
say("1 image N+1 ran: db at 21, newest snapshot at 21", "image N+1 (not under test)")

# 2. Roll back to image N: the dashboard refuses, the report pod refuses.
try:
    S.Store(str(db)); dash = "opened (WRONG)"
except S.StoreSchemaTooNew as exc:
    dash = f"REFUSES: {str(exc)[:70]}"
say("2 rollback to image N, database still at 21", dash)

# 3. Operator restores a schema-20 copy (runbook §4a) and redeploys image N.
for side in ("-wal", "-shm"):
    Path(f"{db}{side}").unlink(missing_ok=True)
conn = sqlite3.connect(db); conn.execute("PRAGMA user_version = 20"); conn.commit(); conn.close()
st = S.Store(str(db))
say("3 restored copy at 20, image N started; before its first snapshot", "opened, serving")

# 4. The leader's next _maybe_report_snapshot (reporting.snapshot.intervalSeconds, default 300).
time.sleep(1.1)                                           # the stamp has whole seconds
st.snapshot(str(report), keep=2)
say("4 after the dashboard's next snapshot (keep=2)", "opened, serving")
st.close()
(ROOT / "results.json").write_text(json.dumps(out, indent=1))
print("root:", ROOT)
