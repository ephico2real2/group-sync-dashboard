"""#592: a report's window ends at the snapshot's stamp, so a copy must hold nothing later than its stamp."""
from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

from gsd.reporting.snapshot import Snapshot, stamp_instant
from gsd.timeutil import now_iso
from reporting_seed import CLUSTER, seed_store


def test_t592_3_a_snapshot_holds_no_row_later_than_its_stamp(tmp_path):
    """The stamp is taken under the store's lock, so a poll holding the lock when the copy is asked for commits
    BEFORE the stamp. Stamped before the lock (the bug), the copy waits for the poll, carries its rows, and is named
    over a second before them: a window that "ends at the stamp" counts a row after it."""
    store = seed_store(str(tmp_path / "writer.db"))
    holding = threading.Event()
    written: dict[str, str] = {}

    def a_poll_holding_the_lock():
        with store.poll_snapshot():                 # one transaction, the lock held for the whole cycle
            holding.set()                           # the copy is asked for only once the poll holds the lock
            time.sleep(1.5)
            written["at"] = now_iso()
            store.sync_members(CLUSTER, {"team-b": ["carol", "zed"]}, {"team-b": written["at"]}, written["at"])

    poll = threading.Thread(target=a_poll_holding_the_lock)
    poll.start()
    assert holding.wait(10), "the poll never took the lock"
    try:
        path = store.snapshot(str(tmp_path / "snapshots"), keep=2)
    finally:
        poll.join()
        store.close()
    assert path
    with Snapshot(Path(path)) as snap:
        committed = datetime.strptime(written["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        assert any(r["user_name"] == "zed" for r in snap.membership_changes(CLUSTER, written["at"])), \
            "the copy holds the poll's row"
        assert stamp_instant(snap.stamp) >= committed, \
            f"the copy is stamped {snap.stamp}, before its own row at {written['at']}"
