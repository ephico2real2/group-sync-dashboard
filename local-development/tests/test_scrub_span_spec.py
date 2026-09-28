"""#465 phase 1: the scrub-span spec is present, checkable, and records its measurements and its decision."""
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
#: The file the spec's one create block writes: absent in phase 1, the spec's own in phase 2.
CREATED = "local-development/tests/test_scrub_span.py"


def prose() -> str:
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    text = SPEC.read_text()
    prose_text, found, _ = text.partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_D6 has no implementation-blocks heading to stop at"
    return prose_text


def blocks() -> list[dict]:
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    loader = importlib.util.spec_from_file_location("apply_spec_blocks", TOOL)
    tool = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(tool)
    return tool.blocks(SPEC.read_text())


def test_the_spec_file_and_index_row_exist():
    assert SPEC.is_file(), "docs/specs/SPEC_D6_scrub_span.md is the #465 spec"
    row = [line for line in INDEX.read_text().splitlines() if line.startswith("| D6 |")]
    assert len(row) == 1, row
    assert "SPEC_D6_scrub_span.md" in row[0] and "#465" in row[0] and "specified" in row[0]


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


def test_the_issues_two_cases_are_tests_in_the_blocks():
    test_file = next(b for b in blocks() if b["path"] == CREATED)["fences"][0]
    assert '@pytest.mark.parametrize("password", ["update", "a"])' in test_file
    assert 'username="bob"' in test_file


def test_no_block_edits_a_version_field():
    paths = {b["path"] for b in blocks()}
    assert not paths & {"local-development/pyproject.toml", "local-development/gsd/__init__.py",
                        "charts/group-sync-dashboard/Chart.yaml"}, paths


def test_implementation_blocks_check_out_against_this_tree():
    """Phase 1: every block applies cleanly to this tree. Phase 2 (the file the create block writes exists): every
    block is already in the tree — a create's file is its fence, an edit's New text and an insertion's text occur in
    their file — so the spec and the code cannot drift apart silently."""
    found = blocks()
    assert [b["path"] for b in found if b["kind"] == "create"] == [CREATED]
    if not (REPO / CREATED).exists():
        done = subprocess.run([sys.executable, str(TOOL), str(SPEC), str(REPO)], capture_output=True, text=True)
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
