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
    r"^\| (?P<id>[A-Z]\d[a-z]?) \| \[`(?P<file>SPEC_[A-Za-z0-9_]+\.md)`\]\([^)]+\)[^|]*\| [^|]+\| "
    r"(?P<release>R\d|—) \| (?P<version>[^|]+?) \| \[#(?P<issue>\d+)\]\([^)]+\) \| (?P<status>[^|]+?) \|$",
    re.M,
)
HEADER_ROW = re.compile(r"^\| (?P<key>Release|Version on release|Issue|Status) \| (?P<value>.+?) \|$", re.M)


def _index_rows() -> dict[str, dict[str, str]]:
    rows = {m["id"]: m.groupdict() for m in INDEX_ROW.finditer(INDEX.read_text())}
    # A programme id is a batch letter A-D and a number, nothing more: a step of a programme design that lands
    # after R7 (D2b, #338) carries the design's id and a letter, and rides a later release like E1.
    programme = sorted(fid for fid in rows if re.fullmatch(r"[A-D]\d", fid))
    post = sorted(fid for fid in rows if fid not in programme)
    assert len(programme) == 13, f"expected the programme's thirteen index rows, matched {programme}"
    # the alternation admits `—` for the post-programme batches only; a programme row must still carry its
    # milestone (review of #233, Codex — A1's R1 mutated to `—` passed before this line)
    wrong = {fid: rows[fid]["release"] for fid in programme if not re.fullmatch(r"R\d", rows[fid]["release"])}
    assert not wrong, f"programme rows require an R<number> release: {wrong}"
    assert all(rows[fid]["release"] == "—" for fid in post), "a post-programme row carries `—`"
    # the count catches an index row dropped silently; it moves by one per new spec (E1 #229, S1 #230, T1 #239)
    # a design's STEP carries the design's id and a letter (S4a, #283): the same slot, not a fifth design
    assert len(rows) == 24, f"expected twenty-four index rows (the programme's thirteen, D2b, E1, S1, S2, S3, S4, S4a, S4b, S4c, T1 and U1), matched {sorted(rows)}"
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
    # S4's steps each carry their own issue (S4a #283, S4b #284, S4c #285): one design, one row per step.
    s_issues = {int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid.startswith("S")}
    assert s_issues == {230, 283, 284, 285}, f"the S batch is #230 (S1-S3), #283 (S4, S4a), #284 (S4b) and #285 (S4c); got {sorted(s_issues)}"


def _ordered_ids() -> list[str]:
    return [m["id"] for m in INDEX_ROW.finditer(INDEX.read_text())]


def test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached() -> None:
    """A spec at `specified` that the CHANGELOG does not yet record by name (`SPEC_<id>`) has shipped
    nothing, so the versions it names are the ones its release WILL carry — above Chart.yaml's and
    pyproject.toml's current rungs. S4c said `chart 0.51.0` on a main at 0.52.1, and 0.51.0 had already
    shipped (review of #325, all three seats; the test is OB1-lite's). S3 and S4b are recorded by name
    and, since the index took the four-word lifecycle, are `in progress` and `merged` — this rule reads
    `specified` rows only."""
    chart = re.search(r"^version: (\d+\.\d+\.\d+)$",
                      (REPO / "charts/group-sync-dashboard/Chart.yaml").read_text(), re.M).group(1)
    app = re.search(r'^version = "(\d+\.\d+\.\d+)"$', (REPO / "local-development/pyproject.toml").read_text(), re.M).group(1)
    changelog = (REPO / "docs/CHANGELOG.md").read_text()
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    checked = []
    for fid, row in ROWS.items():
        if row["status"] != "specified" or re.search(rf"SPEC_{fid}[_ §.:,)]", changelog):
            continue
        m_chart = re.search(r"chart (\d+\.\d+\.\d+)", row["version"])
        m_app = re.search(r"app (\d+\.\d+\.\d+)", row["version"])
        if m_chart:
            checked.append(fid)
            assert as_tuple(m_chart.group(1)) > as_tuple(chart), (fid, row["version"], f"Chart.yaml is already {chart}")
        if m_app:
            assert as_tuple(m_app.group(1)) > as_tuple(app), (fid, row["version"], f"pyproject.toml is already {app}")
    assert "S4c" in checked, checked


def test_s4c_gates_every_bound_failure_per_account() -> None:
    """#315: a lockout is per DIRECTORY account, and a locked account's 500 cannot be told from a sick
    target's. The review of #325 (the operator's ruling) made the gate one entry per account for every
    bound failure; a per-target entry anywhere in the Lease's contract would let T clusters present one
    wrong or locked password T times."""
    text = (SPECS / "SPEC_S4c_credential_lifecycle.md").read_text()
    budgets = text.split("### 3.2", 1)[1].split("### 3.3", 1)[0]
    lease = text.split("### 3.3", 1)[1].split("### 3.4", 1)[0]
    assert "per (account, password) until the password\n  changes, across every target, replica and restart" in budgets, \
        "B2 is not the account's budget"
    for shape in ("one target", "T targets sharing one account", "after a restart", "two replicas"):
        assert f"| {shape} |" in budgets, f"the system table lacks the row `{shape}`"
    assert "refused: dict | None" in lease and "def gated(self, digest: str)" in lease
    body = text.split("## Orchestrator's notes", 1)[1].split("## 0.", 1)[1]   # the design, not the history
    for stale in ("refused: dict[str, dict]", "gated(self, target", "gated_anywhere", "gated(target, digest)",
                  "one entry per target", "(target, password)"):   # the last two: confirmation pass of #325 (Grok)
        assert stale not in body, f"a per-target contract survives: {stale}"


STATUSES = ("specified", "in progress", "merged", "released")


def test_every_index_status_is_in_the_lifecycle() -> None:
    """The index's status vocabulary is the four words its lifecycle names. `in implementation`, on S1, S2
    and S4a, was none of them while the lifecycle named only specified / in progress / released (review of
    the index, 2026-09-24, Grok)."""
    bad = {fid: row["status"] for fid, row in ROWS.items() if row["status"] not in STATUSES}
    assert not bad, f"status is not one of {STATUSES}: {bad}"
