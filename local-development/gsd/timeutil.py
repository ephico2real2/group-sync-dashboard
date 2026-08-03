"""Clock formatting. Not a storage concern, though it used to live in store.py.

Four modules imported ``now_iso`` from ``gsd.store``, which quietly made "what time is it"
part of the storage contract — so a second backend, or a service split where the frontend
has no store at all, would still have had to import the SQLite module to stamp a timestamp.
Wrong seam, harmless today, load-bearing the moment anything moves.

The format is fixed-width UTC with a Z suffix, and that matters beyond tidiness: several
comparisons in the store rely on lexicographic order equalling chronological order —
notably the two-argument min()/max() in the activity upsert. Varying the width or dropping
the Z would break those silently.
"""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
