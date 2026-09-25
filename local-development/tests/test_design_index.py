"""docs/design/README.md lists each design artefact once, and every mock says where it stands.

Found by the review of the indexes (2026-09-24): `drilldown-mock.html` and `cluster-overview-mock.html` were listed
twice, the second time untagged, and two shipped mocks still read **Agreed** and **Proposed** ("nothing ships from
this") after their tabs had merged. A reader of the index could not tell a proposal from shipped work.
"""
from __future__ import annotations

import re
from pathlib import Path

INDEX = Path(__file__).resolve().parents[2] / "docs" / "design" / "README.md"
ROW = re.compile(r"^\| \[`(?P<file>[^`]+)`\]\([^)]+\) \| (?P<desc>.*) \|$", re.M)
TAGS = ("Implemented", "Agreed", "Proposed")


def _rows() -> list[tuple[str, str]]:
    return [(m["file"], m["desc"]) for m in ROW.finditer(INDEX.read_text())]


def test_each_artefact_is_listed_once() -> None:
    files = [f for f, _ in _rows()]
    assert files, "the index has no rows"
    assert len(files) == len(set(files)), sorted({f for f in files if files.count(f) > 1})


def test_every_mock_says_where_it_stands() -> None:
    untagged = [f for f, desc in _rows() if f.endswith("-mock.html")
                and not re.match(rf"\*\*({'|'.join(TAGS)})\*\*", desc)]
    assert not untagged, f"mocks without a leading **{'**/**'.join(TAGS)}** tag: {untagged}"
