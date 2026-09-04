"""The spec index and the spec headers must say the same thing about every feature.

`docs/specs/README.md` carries one row per specification (release, version on release, issue,
status) and every `SPEC_*.md` carries the same facts in its header table. Two hand-written
copies of one fact drift — the adversarial review of PR #69 found five version strings that
already differed in wording the day the files were written. These checks hold them equal, so
the index can be trusted as the programme's state without opening thirteen files.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SPECS = REPO / "docs" / "specs"
INDEX = SPECS / "README.md"

# `| A1 | [`SPEC_A1_ui_tests_in_ci.md`](SPEC_A1_ui_tests_in_ci.md) — title | batch | R1 | version | [#56](url) | status |`
INDEX_ROW = re.compile(
    r"^\| (?P<id>[A-D]\d) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)[^|]*\| [^|]+\| "
    r"(?P<release>R\d) \| (?P<version>[^|]+?) \| \[#(?P<issue>\d+)\]\([^)]+\) \| (?P<status>[^|]+?) \|$",
    re.M,
)
HEADER_ROW = re.compile(r"^\| (?P<key>Release|Version on release|Issue|Status) \| (?P<value>.+?) \|$", re.M)


def _index_rows() -> dict[str, dict[str, str]]:
    rows = {m["id"]: m.groupdict() for m in INDEX_ROW.finditer(INDEX.read_text())}
    assert len(rows) == 13, f"expected thirteen index rows, matched {sorted(rows)}"
    return rows


def _header(spec: pathlib.Path) -> dict[str, str]:
    head = spec.read_text().split("## How to read this spec", 1)[0]
    found = {m["key"]: m["value"] for m in HEADER_ROW.finditer(head)}
    assert set(found) == {"Release", "Version on release", "Issue", "Status"}, (spec.name, found)
    return found


ROWS = _index_rows()


@pytest.mark.parametrize("fid", sorted(ROWS), ids=sorted(ROWS))
def test_the_index_row_matches_the_spec_header(fid: str) -> None:
    row = ROWS[fid]
    spec = SPECS / row["file"]
    assert spec.is_file(), f"index row {fid} points at {row['file']}, which does not exist"
    header = _header(spec)
    assert header["Release"].startswith(row["release"] + " "), (fid, header["Release"], row["release"])
    assert header["Version on release"] == row["version"], (fid, header["Version on release"], row["version"])
    assert re.fullmatch(rf"\[#{row['issue']}\]\(https://github\.com/[^)]+/issues/{row['issue']}\)", header["Issue"]), (
        fid, header["Issue"], row["issue"])
    assert header["Status"] == row["status"], (fid, header["Status"], row["status"])


def test_every_spec_file_has_an_index_row() -> None:
    on_disk = {p.name for p in SPECS.glob("SPEC_*.md")}
    indexed = {row["file"] for row in ROWS.values()}
    assert on_disk == indexed, f"missing from the index: {on_disk - indexed}; indexed but absent: {indexed - on_disk}"


def test_issue_numbers_are_unique_and_follow_the_implementation_order() -> None:
    """The issues were created in ladder order, so the numbers rise down the table."""
    issues = [int(ROWS[fid]["issue"]) for fid in _ordered_ids()]
    assert issues == sorted(issues) and len(set(issues)) == len(issues), issues


def _ordered_ids() -> list[str]:
    return [m["id"] for m in INDEX_ROW.finditer(INDEX.read_text())]
