"""reports/README.md lists every evidence folder once.

Found 2026-09-24: the index listed 7 of the 28 folders under `reports/`. Nothing tied a new folder to its row, so
21 walks were committed that a reader of the index could not find.
"""
from __future__ import annotations

import re
from pathlib import Path

REPORTS = Path(__file__).resolve().parents[2] / "reports"
ROW = re.compile(r"^\| `(?P<folder>\d{4}-\d{2}-\d{2}_[^`/]+)/` \|", re.M)


def test_every_report_folder_has_one_index_row() -> None:
    listed = [m["folder"] for m in ROW.finditer((REPORTS / "README.md").read_text())]
    on_disk = sorted(d.name for d in REPORTS.iterdir() if d.is_dir())
    assert len(listed) == len(set(listed)), sorted({f for f in listed if listed.count(f) > 1})
    assert sorted(set(on_disk) - set(listed)) == [], "folders under reports/ with no row in reports/README.md"
    assert sorted(set(listed) - set(on_disk)) == [], "rows in reports/README.md naming no folder"
