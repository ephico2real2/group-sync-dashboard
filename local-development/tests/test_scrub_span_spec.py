"""#465: the scrub-span spec is present, checkable, and records its measurements and its decisions — phase 1's, and
phase 2's: the operator dropped part (1), the refusal, so the code is applied from the notes' blocks, not §6's."""
from __future__ import annotations

import importlib.util
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "specs" / "SPEC_D6_scrub_span.md"
INDEX = REPO / "docs" / "specs" / "README.md"
TOOL = pathlib.Path(__file__).resolve().parents[1] / "apply-spec-blocks.py"
#: The file the applied create block writes: absent in phase 1, the spec's own in phase 2.
CREATED = "local-development/tests/test_scrub_span.py"
NOTES, NOTES_END, BLOCKS = "\n## Orchestrator's notes\n", "\n## 1. The point", "\n## 6. Implementation blocks\n"


def prose() -> str:
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    text = SPEC.read_text()
    prose_text, found, _ = text.partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_D6 has no implementation-blocks heading to stop at"
    return prose_text


def blocks(text: str | None = None) -> list[dict]:
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    loader = importlib.util.spec_from_file_location("apply_spec_blocks", TOOL)
    tool = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(tool)
    return tool.blocks(SPEC.read_text() if text is None else text)


def notes() -> str:
    text = SPEC.read_text()
    start = text.index(NOTES)
    return text[start:text.index(NOTES_END, start)]


def applied() -> list[dict]:
    """The blocks phase 2 is applied from: the notes' own. §6's are superseded (the operator's decision, 2026-09-29)."""
    return blocks(notes())


def test_the_spec_file_and_index_row_exist():
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    row = [line for line in INDEX.read_text().splitlines() if line.startswith("| D6 |")]
    assert len(row) == 1, row
    assert "SPEC_D6_scrub_span.md" in row[0] and "#465" in row[0]
    status = row[0].rstrip(" |").rsplit("|", 1)[1].strip()
    expected = ("merged", "released") if (REPO / CREATED).exists() else ("specified",)
    assert status in expected, (status, expected)


def test_the_defect_is_measured_on_the_issues_two_cases():
    body = prose()
    assert "who may <redacted> clusterrolebindings" in body       # `update`, username bob
    assert "Signed in to e<redacted>st <redacted>s bob" in body    # `a`, cluster east
    assert "class of one" in body                                 # read back, measured by pressing candidates
    assert "Un<red<redacted>cted>uthorized" in body                # the scrub cutting its own marks


def test_every_place_the_scrub_runs_is_mapped():
    body = prose()
    for helper in ("gsd/rejoin.py#_scrub", "gsd/fleetlookup.py#_scrub", "gsd/clusterconfig/events.py#redact",
                   "gsd/kube.py#redact_text"):
        assert f"`{helper}`" in body, helper
    for line in ("rejoin.py:231", "rejoin.py:234", "rejoin.py:254", "events.py:52", "kube.py:379-400"):
        assert line in body, line


def test_both_rules_are_measured_and_one_is_decided():
    body = prose()
    assert "`date` `pdat` `pdate` `upda` `updat` `update`" in body   # (a) leaves `update` six guesses
    assert "the field `cluster=` is the password" in body             # (a) cannot hide a whole field
    assert "The decision is rule (b)" in body
    for number in ("406", "385", "79", "19", "58"):                   # the NCSC population, §2.4
        assert re.search(rf"\b{number}\b", body), number


def test_the_sources_read_are_cited():
    body = prose()
    for needle in ("NIST SP 800-63B-4 §3.1.1.2", "OWASP Logging Cheat Sheet", "KEP-1753", "maskValue", "Edact-Ray",
                   'realm `"openshift"`', "GitLab", "Sentry"):
        assert needle in body, needle


def test_no_length_floor_and_the_measurement_behind_it():
    body = prose()
    assert "### 3.4 No length floor" in body and "95 existing" in body


def test_what_must_not_change_is_listed():
    must = prose().split("### 3.6 What must not change", 1)[1].split("## 4.", 1)[0]
    for needle in ("every existing scrub", "the one-login budget", "D4-7", "#447", "#286"):
        assert needle in must, needle


def test_the_over_refusal_is_broken_down_by_cause():
    """§5.5: the 58 over-refusals are three causes, not one (OB2's re-measurement on the design's `check` over the same
    list: 21 by case only, 27 words of text the fifteen paths did not write, 10 under a line's floor; 21 + 27 + 10 = 58),
    and a case-sensitive compare would leave 26 of the 100,000, not 19."""
    five = prose().split("**Over-refusal.**", 1)[1].split("\n6. ", 1)[0]
    for number in ("58", "21", "27", "10", "26"):
        assert re.search(rf"\b{number}\b", five), number


def test_the_issues_two_cases_are_tests_in_the_blocks():
    """The issue's passwords, `update` and `a` with the username `bob`, as phase 2 tests them: each is sent, as the
    operator decided, and `a` leaves no span in what Rejoin quotes."""
    created = [b for b in applied() if b["path"] == CREATED]
    assert len(created) == 1, "the notes carry the one create block phase 2 is applied from"
    test_file = created[0]["fences"][0]
    assert '    "update",' in test_file and '    "a",' in test_file
    assert "def test_a_password_found_in_the_words_rejoin_writes_is_sent_as_before(" in test_file
    assert "def test_the_issues_password_a_leaves_no_span_in_what_rejoin_quotes(" in test_file
    assert 'username="bob", password="a"' in test_file


def test_no_block_edits_a_version_field():
    paths = {b["path"] for b in blocks()}
    assert not paths & {"local-development/pyproject.toml", "local-development/gsd/__init__.py",
                        "charts/group-sync-dashboard/Chart.yaml"}, paths


def test_implementation_blocks_check_out_against_this_tree(tmp_path):
    """Phase 2 is applied from the notes' nine blocks; §6's nineteen stay as phase 1 wrote them, superseded. Without
    the change (the file the notes' create block writes absent), the nine apply cleanly to this tree. With it, every
    one is already in the tree — a create's file is its fence, an edit's New text and an insertion's text occur in
    their file — so the spec and the code cannot drift apart silently."""
    found = applied()
    assert len(found) == 9 and [b["path"] for b in found if b["kind"] == "create"] == [CREATED]
    assert len(blocks(SPEC.read_text().split(BLOCKS, 1)[1])) == 19, "§6 is the phase-1 record, kept whole"
    if not (REPO / CREATED).exists():
        (tmp_path / "notes.md").write_text(notes())
        done = subprocess.run([sys.executable, str(TOOL), str(tmp_path / "notes.md"), str(REPO)], capture_output=True,
                              text=True)
        assert done.returncode == 0, done.stderr or done.stdout
        assert "blocks check out" in done.stdout
        return
    for b in found:
        text = (REPO / b["path"]).read_text()
        if b["kind"] == "create":
            assert text == b["fences"][0], f"block {b['n']}: {b['path']} is not the spec's file"
        elif b["kind"] == "edit":
            assert b["fences"][1] in text, f"block {b['n']}: {b['path']} lacks the New text"
        else:
            assert b["fences"][0].strip("\n") in text, f"block {b['n']}: {b['path']} lacks the inserted text"


def test_emit_callsite_measurement():
    import ast
    repo = REPO
    counts = {}
    for path in (repo / 'local-development/gsd').rglob('*.py'):
        tree = ast.parse(path.read_text())
        emitters = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.module.endswith('events')
            for alias in node.names if alias.name in ('event', 'failure')
        }
        count = sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in emitters for node in ast.walk(tree))
        if count:
            counts[str(path.relative_to(repo))] = count
    expected = f"{sum(counts.values())} call sites in {len(counts)} consuming modules"
    body = (repo / 'docs/specs/SPEC_D6_scrub_span.md').read_text().split('## 6. Implementation blocks')[0]
    assert expected in body, (expected, counts)


def test_phase_2_records_the_operators_decision_and_what_it_supersedes():
    """The operator's decision of 2026-09-29 drops part (1), the refusal. The notes quote it, say what becomes of each
    of §6's nineteen blocks, and hold the figures re-measured by pressing: part (2) alone leaves 332 of main's 406, and
    §6 applied would have left 29 (the body's 19 was a model's)."""
    body = " ".join(notes().split())
    for quote in ("So let them rejoin with their password without any hiccups.",
                  "Just redact the password in the error logs."):
        assert quote in body, quote
    assert "is not applied: Rejoin refuses no password for being found in the words it writes" in body
    table = notes().split("| §6 block | file | what it held | phase 2 |", 1)[1].split("\n\n", 1)[0]
    numbered = [int(n) for row in table.splitlines()[2:] for n in row.split("|")[1].split(",")]
    assert sorted(numbered) == list(range(1, 20)), numbered
    for figure in ("| still leaving a span | 406 | 332 | 29 |", "Part (2) closes 74", "§6 applied leaves 29, not 19"):
        assert figure in body, figure
