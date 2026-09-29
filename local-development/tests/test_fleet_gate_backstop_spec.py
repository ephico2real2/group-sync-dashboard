"""#481 phase 2: the fleet gate's backstop spec is present, checkable, and records its measurements and its decision."""
from __future__ import annotations

import ast
import importlib.util
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "specs" / "SPEC_S4f_fleet_gate_backstop.md"
INDEX = REPO / "docs" / "specs" / "README.md"
TOOL = pathlib.Path(__file__).resolve().parents[1] / "apply-spec-blocks.py"
#: The file the spec's one create block writes: absent in phase 2, the spec's own once it is implemented.
CREATED = "local-development/tests/test_fleet_gate_backstop.py"


def flat(text: str) -> str:
    """Whitespace folded, so a rewrapped paragraph still matches."""
    return " ".join(text.split())


def prose() -> str:
    assert SPEC.is_file(), "docs/specs/SPEC_S4f_fleet_gate_backstop.md is the #481 spec"
    text, found, _ = SPEC.read_text().partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_S4f has no implementation-blocks heading to stop at"
    return text


def section(start: str, end: str) -> str:
    return prose().split(start, 1)[1].split(end, 1)[0]


def blocks() -> list[dict]:
    loader = importlib.util.spec_from_file_location("apply_spec_blocks", TOOL)
    tool = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(tool)
    return tool.blocks(SPEC.read_text())


def created() -> str:
    return next(b for b in blocks() if b["path"] == CREATED)["fences"][0]


def test_the_spec_file_and_index_row_exist():
    row = [line for line in INDEX.read_text().splitlines() if line.startswith("| S4f |")]
    assert len(row) == 1, row
    assert "SPEC_S4f_fleet_gate_backstop.md" in row[0] and "[#481]" in row[0]
    status = row[0].rstrip(" |").rsplit("|", 1)[1].strip()
    expected = ("merged", "released") if (REPO / CREATED).exists() else ("specified",)
    assert status in expected, (status, expected)


def test_the_decision_and_what_it_does_not_fix_are_recorded():
    body = flat(prose())
    assert "option (c2), plus option (a)'s warning line" in body and "2026-09-29" in body
    not_fixed = flat(section("### 1.3 Not fixed, as the operator accepted", "## 2."))
    for row in ("persistence off", "an etcd restore", "a reinstall into another namespace",
                "a clear by hand made while no pod read the Lease, then a `crc start`"):
        assert row in not_fixed, row


def test_crc_and_ocpbugs_7583_are_measured_and_pinned():
    upstream = flat(section("### 2.1 Who deletes the fleet Lease", "### 2.2"))
    for needle in ("`v2.63.0` (`3a67a3687c`", "pkg/crc/cluster/cluster.go:495-509", '"delete", "-A", "lease", "--all"',
                   "pkg/crc/machine/start.go:584", "`9354dd4c18a1`", "Since crc **2.29.0**", "(`0aaea852`, 2026-09-28)",
                   "**Closed, Not a Bug**", "oc delete lease machine-config-controller -n openshift-machine-config-operator",
                   "crc's own widening"):
        assert needle in upstream, needle


def test_the_lab_measurement_and_b2s_premise():
    lab = flat(section("### 2.2 The lab, read-only", "### 2.3"))
    for needle in ("58 of 58 Leases postdate the start", "**0** created before 2026-09-28T17:55:17Z", "10:30:01Z",
                   "17:57:01Z", "**two pings inside one 86 400 s interval**"):
        assert needle in lab, needle
    premise = flat(section("### 2.3 B2's premise, refined", "### 2.4"))
    assert "`admin`" in premise and "`openshift-config`" in premise and "without being able to read the password" in premise


def test_the_research_retraction_is_stated_with_the_api_servers_source():
    notes = flat(section("## Orchestrator's notes", "## 1."))
    assert "A retraction from the research" in notes and "the answer is **409**, not a create" in notes
    source = flat(section("### 2.4 What the API server does with a write after a deletion", "### 2.5"))
    for needle in ("registry/rest/update.go:188-203", "storage/interfaces.go:150-155", "storage/errors/storage.go:78-81",
                   "coordination/lease/strategy.go:83-86", "**409 Conflict**", "reached only by a body with no uid"):
        assert needle in source, needle


def test_the_design_names_the_file_its_format_and_the_fail_closed_rules():
    design = flat(section("## 3. The design", "## 4."))
    for needle in ("`/data/fleet-gate.json` at one replica", "`/data/<pod>/fleet-gate.json`", "exactly as the Lease holds them",
                   "`refused`, `ping-last-attempt`, `ping-last-ok`, `ping-last-outcome`, `ping-last-target`, `ping-digest`",
                   "`os.replace`", "the directory `fsync`ed", "Only when the Lease is absent", "no PUT is ever sent to an absent name",
                   "no `uncertain` entry is stranded", "A store in memory, or one with no file path, keeps no copy",
                   "**Above one replica**", "**With persistence off**", "No new finding code"):
        assert needle in design, needle


def test_the_warnings_words_are_the_codes():
    """§3.7's two texts are the strings the code blocks define, so the spec cannot drift from what is said."""
    defined = {}
    for block in blocks():
        if block["path"] == "local-development/gsd/fleetstate.py":
            for fence in block["fences"][1:]:
                try:
                    tree = ast.parse(fence)
                except SyntaxError:
                    continue
                for node in tree.body:
                    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                        if node.targets[0].id in ("RESTORED", "NOTHING_KEPT"):
                            defined[node.targets[0].id] = ast.literal_eval(node.value)
    assert set(defined) == {"RESTORED", "NOTHING_KEPT"}, defined
    warning = flat(section("### 3.7 The warning", "### 3.8"))
    assert f'kept=true refused=<code> since=<entry\'s at> last_attempt=<the ping\'s> action="{defined["RESTORED"]}"' in warning
    assert f'kept=false action="{defined["NOTHING_KEPT"]}"' in warning


def test_every_budget_is_measured_by_a_test_in_the_blocks_or_marked():
    defined = set(re.findall(r"^def (test_\w+)\(", created(), re.M))
    for title, end in (("### 4.1 B2", "### 4.2"), ("### 4.2 B3", "### 4.3")):
        rows = [r for r in section(title, end).splitlines() if r.startswith("| ") and not r.startswith("| shape")]
        assert len(rows) >= 6, (title, rows)
        for row in rows:
            cell = row.rstrip(" |").rsplit("|", 1)[1]
            named = set(re.findall(r"`(test_\w+)", cell))
            assert named <= defined, (row, named - defined)
            assert named or "derived" in cell or "SPEC_S4c §8.2" in cell or cell.strip() == "the same", row


def test_the_issues_two_behaviours_are_tests_in_the_blocks():
    """#481's Definition of Done: a refused password stays refused after its Lease is deleted and the process restarts;
    the ping stays at most once a day across the same events — on a fake API server that behaves as §2.4 reads."""
    test_file = created()
    assert "def test_a_refused_password_stays_refused_across_crc_starts(" in test_file
    assert "def test_the_ping_stays_once_a_day_across_crc_starts_and_a_live_deletion(" in test_file
    assert "class ApiServer(LeaseAPI):" in test_file and "strategy.go:84" in test_file


def test_s4c_gets_a_note_and_its_body_stays_verbatim():
    """SPEC_S4c's B2 is superseded by a note, never rewritten: its block only inserts lines."""
    s4c, = [b for b in blocks() if b["path"] == "docs/specs/SPEC_S4c_credential_lifecycle.md"]
    old, new = (fence.splitlines() for fence in s4c["fences"])
    assert [line for line in new if line in old] == old and len(new) > len(old)
    note = flat("\n".join(line for line in new if line not in old))
    assert note.startswith("- **#481 (`docs/specs/SPEC_S4f_fleet_gate_backstop.md`") and "+1 per act" in note


def test_the_documents_it_changes_are_blocks():
    paths = {b["path"] for b in blocks()}
    assert {"docs/specs/SPEC_S4c_credential_lifecycle.md", "charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md",
            "charts/group-sync-dashboard/RUNBOOK.md", "docs/CHANGELOG.md"} <= paths, paths
    runbook, = [b for b in blocks() if b["path"] == "charts/group-sync-dashboard/RUNBOOK.md"]
    assert "## 7. The fleet account is held back: clear its entry by hand" in runbook["fences"][1]


def test_no_block_edits_a_version_field():
    paths = {b["path"] for b in blocks()}
    assert not paths & {"local-development/pyproject.toml", "local-development/gsd/__init__.py",
                        "charts/group-sync-dashboard/Chart.yaml"}, paths


def test_implementation_blocks_check_out_against_this_tree():
    """Phase 2: every block applies cleanly to this tree. Once implemented (the file the create block writes exists):
    every block is already in the tree — a create's file is its fence, an edit's New text and an insertion's text occur
    in their file — so the spec and the code cannot drift apart silently."""
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
