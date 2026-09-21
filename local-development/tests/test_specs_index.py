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
# The programme's thirteen (A–D) carry a milestone R1–R7; a spec after the programme (E…) carries `—`
# there and rides the next release instead (E1, #229).
INDEX_ROW = re.compile(
    # ids A–D are the 2026-09 programme's batches on its R1–R7 ladder; a later batch (E, #229; S, #230) sits
    # after the ladder with `—` for its release, and its header's Release row starts with the same dash
    r"^\| (?P<id>[A-Z]\d) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)[^|]*\| [^|]+\| "
    r"(?P<release>R\d|—) \| (?P<version>[^|]+?) \| \[#(?P<issue>\d+)\]\([^)]+\) \| (?P<status>[^|]+?) \|$",
    re.M,
)
HEADER_ROW = re.compile(r"^\| (?P<key>Release|Version on release|Issue|Status) \| (?P<value>.+?) \|$", re.M)


def _index_rows() -> dict[str, dict[str, str]]:
    rows = {m["id"]: m.groupdict() for m in INDEX_ROW.finditer(INDEX.read_text())}
    programme = sorted(fid for fid in rows if fid[0] in "ABCD")
    post = sorted(fid for fid in rows if fid[0] not in "ABCD")
    assert len(programme) == 13, f"expected the programme's thirteen index rows, matched {programme}"
    # the alternation admits `—` for the post-programme batches only; a programme row must still carry its
    # milestone (review of #233, Codex — A1's R1 mutated to `—` passed before this line)
    wrong = {fid: rows[fid]["release"] for fid in programme if not re.fullmatch(r"R\d", rows[fid]["release"])}
    assert not wrong, f"programme rows require an R<number> release: {wrong}"
    assert all(rows[fid]["release"] == "—" for fid in post), "a post-programme row carries `—`"
    # the count catches an index row dropped silently; it moves by one per new spec (E1 #229, S1 #230, T1 #239)
    assert len(rows) == 19, f"expected nineteen index rows (the programme's thirteen, E1, S1, S2, S3, S4 and T1), matched {sorted(rows)}"
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


@pytest.mark.parametrize("fid", sorted(ROWS), ids=sorted(ROWS))
def test_a_superseding_version_in_the_notes_is_the_header_version(fid: str) -> None:
    """Chart 0.14.0 moved the ladder after the notes were written; a note that names the
    superseding chart version must name the one the header now carries."""
    spec = SPECS / ROWS[fid]["file"]
    header_chart = re.search(r"chart (\d+\.\d+\.\d+)", ROWS[fid]["version"])
    for m in re.finditer(r"superseded by chart (\d+\.\d+\.\d+)", spec.read_text()):
        assert header_chart is not None, (fid, m.group(0))
        assert m.group(1) == header_chart.group(1), (fid, m.group(0), ROWS[fid]["version"])


def test_every_spec_file_has_an_index_row() -> None:
    on_disk = {p.name for p in SPECS.glob("SPEC_*.md")}
    indexed = {row["file"] for row in ROWS.values()}
    assert on_disk == indexed, f"missing from the index: {on_disk - indexed}; indexed but absent: {indexed - on_disk}"


def test_issue_numbers_are_unique_and_follow_the_implementation_order() -> None:
    """The issues were created in ladder order, so the numbers rise down the table. The programme's
    thirteen have one issue each; the S batch is one issue (#230) in three steps, so its rows share it."""
    issues = [int(ROWS[fid]["issue"]) for fid in _ordered_ids()]
    assert issues == sorted(issues), issues
    programme = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if not fid.startswith("S")]
    assert len(set(programme)) == len(programme), programme
    # S1-S3 are three steps of one issue (#230). S4 is its own issue set (#283-#286): the credential
    # RETRIEVAL machinery is separable work with its own steps, not a fourth step of the Secret
    # contract, so the batch now spans two issues rather than one.
    s_issues = {int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid.startswith("S")}
    assert s_issues == {230, 283}, f"the S batch is #230 (S1-S3) and #283 (S4); got {sorted(s_issues)}"


def _ordered_ids() -> list[str]:
    return [m["id"] for m in INDEX_ROW.finditer(INDEX.read_text())]
