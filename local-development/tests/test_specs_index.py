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
#: The 2026-09 programme's thirteen modules, on the R1–R7 ladder.
PROGRAMME = frozenset({"A1", "A2", "A3", "B1", "B2", "B3", "B4", "C1", "C2", "C3", "C4", "D1", "D2"})
HEADER_ROW = re.compile(r"^\| (?P<key>Release|Version on release|Issue|Status) \| (?P<value>.+?) \|$", re.M)


def _index_rows() -> dict[str, dict[str, str]]:
    rows = {m["id"]: m.groupdict() for m in INDEX_ROW.finditer(INDEX.read_text())}
    # The programme's thirteen, by name: a later spec may reuse a batch letter (D2b, #338; D3, #311, Epic D)
    # and rides a later release like E1.
    programme = sorted(fid for fid in rows if fid in PROGRAMME)
    post = sorted(fid for fid in rows if fid not in programme)
    assert len(programme) == 13, f"expected the programme's thirteen index rows, matched {programme}"
    # the alternation admits `—` for the post-programme batches only; a programme row must still carry its
    # milestone (review of #233, Codex — A1's R1 mutated to `—` passed before this line)
    wrong = {fid: rows[fid]["release"] for fid in programme if not re.fullmatch(r"R\d", rows[fid]["release"])}
    assert not wrong, f"programme rows require an R<number> release: {wrong}"
    assert all(rows[fid]["release"] == "—" for fid in post), "a post-programme row carries `—`"
    # the count catches an index row dropped silently; it moves by one per new spec (E1 #229, S1 #230, T1 #239, G1 #239, E2 #303, G2 #255, E4 #391, G3 #503, E5 #304, E3 #302, E6 #306, E9 #425)
    # a design's STEP carries the design's id and a letter (S4a, #283): the same slot, not a fifth design
    assert len(rows) == 44, f"expected forty-four index rows, including D3 (#311), S4e (#432), D4 (#316), D5 (#244), D6 (#465), S4f (#481), G1 (#239), E2 (#303), G2 (#255), E4 (#391), G3 (#503), E5 (#304), E3 (#302), E6 (#306) and E9 (#425); matched {sorted(rows)}"
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
    # D5 (#244) is specified after later work (D3/D4, S4e) because the operator's rulings
    # arrived later; it sits at the end of the table and is excluded from the rising-number assert.
    # G1 is #239's second design (SPEC_G1, Epic G #387), specified after everything above it; it shares
    # T1's issue, as the S steps share #230, so it is excluded from both asserts — and pinned to #239 here,
    # so the exclusion covers that one sharing and no other number (review of SPEC_G1, OB3 and Codex).
    assert ROWS["G1"]["issue"] == ROWS["T1"]["issue"] == "239", (
        "only T1 and G1 may share #239", ROWS["T1"]["issue"], ROWS["G1"]["issue"])
    # E2 (#303) is Epic E's first step, specified after G1; it sits at the end like D5 and is excluded from
    # the rising-number assert by its id, pinned to #303 the same narrow way, so a mistyped issue fails here.
    assert ROWS["E2"]["issue"] == "303", ("E2 is #303", ROWS["E2"]["issue"])
    # G2 is #255 (filed 2026-09-21), specified after #481 in Epic G's build order: excluded from the rising-number
    # assert by its id and pinned to #255, so a mistyped issue on that row still fails (review of SPEC_G2, OB3 and Codex).
    assert ROWS["G2"]["issue"] == "255", ("G2 is #255", ROWS["G2"]["issue"])
    # E4 (#391) was filed while Epic E was drafted and specified on 2026-10-01 after G2; excluded the same way, by
    # its id, and pinned to #391 (review of SPEC_E4, OB3 and OB2). D5 is excluded by its id too and pinned to #244:
    # excluded by the number alone, D5's row and header mistyped as #445 passed every index test (review of SPEC_E4, OB3).
    assert ROWS["E4"]["issue"] == "391", ("E4 is #391", ROWS["E4"]["issue"])
    assert ROWS["D5"]["issue"] == "244", ("D5 is #244", ROWS["D5"]["issue"])
    # G3 (#503) is Epic G's third step, after G2 in the epic's build order: excluded by its id and pinned to #503 the
    # same narrow way, so the row's place follows the build order and a mistyped issue still fails (review of SPEC_G3).
    assert ROWS["G3"]["issue"] == "503", ("G3 is #503", ROWS["G3"]["issue"])
    # E5 (#304), Epic E's offsite step, specified after G3: excluded the same way, by its id, and pinned to #304
    # (review of SPEC_E5, OB3 and OB2: excluded by the number alone, E5 mistyped as #504 passed every index test).
    assert ROWS["E5"]["issue"] == "304", ("E5 is #304", ROWS["E5"]["issue"])
    # E3 (#302) is Epic E's restore script, specified after S4f (#481): excluded from the rising-number assert by its id
    # and pinned to #302, so a mistyped issue on that row still fails (confirmation pass of SPEC_E3, OB3, F3).
    assert ROWS["E3"]["issue"] == "302", ("E3 is #302", ROWS["E3"]["issue"])
    # E6 (#306) is Epic E's KPI backups card, specified after E3: excluded by its id and pinned to #306 the same way.
    assert ROWS["E6"]["issue"] == "306", ("E6 is #306", ROWS["E6"]["issue"])
    # E9 (#425) is Epic E's `:latest` step, specified after E6: excluded from the rising-number assert by its id and
    # pinned to #425 the same narrow way, so a mistyped issue on that row still fails (SPEC_E9, Orchestrator's notes 7).
    assert ROWS["E9"]["issue"] == "425", ("E9 is #425", ROWS["E9"]["issue"])
    issues = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid not in ("D5", "G1", "E2", "G2", "E4", "G3", "E5", "E3", "E6", "E9")]
    assert issues == sorted(issues), issues
    programme = [int(ROWS[fid]["issue"]) for fid in _ordered_ids() if not fid.startswith("S") and fid != "G1"]
    assert len(set(programme)) == len(programme), programme
    # S1-S3 are three steps of one issue (#230). S4 is its own issue set (#283-#286): the credential
    # RETRIEVAL machinery is separable work with its own steps, not a fourth step of the Secret
    # contract, so the batch now spans two issues rather than one.
    # S4's steps each carry their own issue (S4a #283, S4b #284, S4c #285, S4d #315, S4e #432, S4f #481): one design, one row per step.
    s_issues = {int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid.startswith("S")}
    assert s_issues == {230, 283, 284, 285, 293, 315, 432, 481}, f"the S batch includes ConfigMap onboarding #293 (S5), the per-account gate #315 (S4d), the ping's account scope #432 (S4e) and the gate's backstop #481 (S4f); got {sorted(s_issues)}"


def _ordered_ids() -> list[str]:
    return [m["id"] for m in INDEX_ROW.finditer(INDEX.read_text())]


def test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached() -> None:
    """A spec at `specified` that the CHANGELOG does not yet record by name (`SPEC_<id>`) has shipped
    nothing, so the versions it names are the ones its release WILL carry — above Chart.yaml's and
    pyproject.toml's current rungs. S4c said `chart 0.51.0` on a main at 0.52.1, and 0.51.0 had already
    shipped (review of #325, all three seats; the test is OB1-lite's). S3 and S4b are recorded by name
    and, since the index took the four-word lifecycle, are `in progress` and `merged` — this rule reads
    `specified` rows only. S4c was the row it was written for; its implementation (#285) takes the chart
    rung it names and records it by name, so the rule may have no row to read until the next spec."""
    chart = re.search(r"^version: (\d+\.\d+\.\d+)$",
                      (REPO / "charts/group-sync-dashboard/Chart.yaml").read_text(), re.M).group(1)
    app = re.search(r'^version = "(\d+\.\d+\.\d+)"$', (REPO / "local-development/pyproject.toml").read_text(), re.M).group(1)
    changelog = (REPO / "docs/CHANGELOG.md").read_text()
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    for fid, row in ROWS.items():
        if row["status"] != "specified" or re.search(rf"SPEC_{fid}[_ §.:,)]", changelog):
            continue
        m_chart = re.search(r"chart (\d+\.\d+\.\d+)", row["version"])
        m_app = re.search(r"app (\d+\.\d+\.\d+)", row["version"])
        if m_chart:
            assert as_tuple(m_chart.group(1)) > as_tuple(chart), (fid, row["version"], f"Chart.yaml is already {chart}")
        if m_app:
            assert as_tuple(m_app.group(1)) > as_tuple(app), (fid, row["version"], f"pyproject.toml is already {app}")


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


def test_a_released_spec_with_application_code_names_its_app_version() -> None:
    """A spec whose code "rides the next application release" is written before that release exists;
    once the row is `released`, the release is known and the cell must name it (review of #423: S4d
    was promoted still reading "rides the next application release", naming no app version)."""
    for fid, row in ROWS.items():
        if row["status"] == "released" and "application code" in row["version"]:
            assert re.search(r"\bapp \d+\.\d+\.\d+", row["version"]), (fid, row["version"])

