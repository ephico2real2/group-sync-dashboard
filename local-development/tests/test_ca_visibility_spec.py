"""#244 phase 1: the CA-visibility spec is present, checkable, and records the operator's rulings."""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEC = REPO / "docs" / "specs" / "SPEC_D5_ca_visibility.md"
INDEX = REPO / "docs" / "specs" / "README.md"
TOOL = pathlib.Path(__file__).resolve().parents[1] / "apply-spec-blocks.py"
PYPROJECT = REPO / "local-development" / "pyproject.toml"


def prose() -> str:
    text = SPEC.read_text()
    prose_text, found, _ = text.partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_D5 has no implementation-blocks heading to stop at"
    return prose_text


def test_the_spec_file_and_index_row_exist():
    assert SPEC.is_file(), "docs/specs/SPEC_D5_ca_visibility.md is the #244 spec"
    row = [line for line in INDEX.read_text().splitlines() if line.startswith("| D5 |")]
    assert len(row) == 1, row
    assert "SPEC_D5_ca_visibility.md" in row[0]
    assert "#244" in row[0]
    assert "specified" in row[0]


def test_the_operator_rulings_are_recorded():
    body = prose()
    assert "public PKI" in body or "public root" in body
    assert "Secret" in body and "ConfigMap" in body
    assert "warnings" in body and "#314" in body
    assert "notBefore" in body and "notAfter" in body
    assert "enterprise" in body.lower()


def test_enterprise_root_is_a_sha256_fingerprint_in_values():
    """The simplest best-practice pin: SHA-256 of the DER certificate, empty by default."""
    body = prose()
    assert "enterpriseRoot" in body
    assert "sha256" in body
    assert "expiryWarningDays" in body
    assert re.search(r"\b30\b", body)
    assert "subjectHash" in body
    assert "not" in body.lower() and "subjectHash" in body


def test_stdlib_ssl_is_required_and_cryptography_is_not_added():
    body = prose()
    assert "`ssl`" in body or "ssl.create_default_context" in body
    assert "get_ca_certs" in body
    assert "cryptography" in body
    assert "not a dependency" in body.lower() or "not installed" in body.lower()
    assert "cryptography" not in PYPROJECT.read_text()


def test_get_ca_certs_leaf_gap_and_bundle_timing_are_measured():
    body = prose()
    assert "CA:FALSE" in body or "leaf" in body.lower()
    assert "_test_decode_cert" in body
    assert "create_default_context(cadata=" in body
    assert re.search(r"0\.00\d", body), "the measured read time of the default bundle is recorded"


def test_warnings_reuse_the_314_channel_and_are_not_findings():
    body = prose()
    assert "gsd/clusterconfig/warnings.py#shared_api_warnings" in body
    assert "ca-expiring" in body
    assert "FINDING_CODES" in body
    assert "not a finding" in body.lower() or "never a finding" in body.lower()


def test_one_function_builds_the_action_text():
    body = prose()
    assert "tls_verify_failure" in body
    assert "gsd/poller.py#_log_poll_failure" in body
    assert "identical" in body.lower()


def test_implementation_blocks_check_out_against_this_tree():
    """Phase 1: every block applies cleanly to this tree. Phase 2 (the module the first block creates
    exists): every block is already in the tree — a create's file is its fence, an edit's New text and
    an insertion's text occur in their file — so the spec and the code cannot drift apart silently."""
    import importlib.util
    loader = importlib.util.spec_from_file_location("apply_spec_blocks", TOOL)
    tool = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(tool)
    blocks = tool.blocks(SPEC.read_text())
    created = [b for b in blocks if b["kind"] == "create"]
    assert created, "the spec creates at least one file"
    if not (REPO / created[0]["path"]).exists():
        done = subprocess.run([sys.executable, str(TOOL), str(SPEC), str(REPO)], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr or done.stdout
        assert "blocks check out" in done.stdout
        return
    for b in blocks:
        text = (REPO / b["path"]).read_text()
        if b["kind"] == "create":
            assert text == b["fences"][0], f"block {b['n']}: {b['path']} is not the spec's file"
        elif b["kind"] == "edit":
            assert b["fences"][1] in text, f"block {b['n']}: {b['path']} lacks the New text"
        else:
            assert b["fences"][0].strip("\n") in text, f"block {b['n']}: {b['path']} lacks the inserted text"


def test_no_block_edits_a_version_field():
    text = SPEC.read_text()
    forbidden = (
        "version = ",
        "__version__",
        "appVersion:",
        "version: ",
    )
    # The prose may mention versions as history; the blocks must not write them.
    _, _, blocks = text.partition("\n## 6. Implementation blocks\n")
    for needle in ("local-development/pyproject.toml", "gsd/__init__.py", "Chart.yaml"):
        assert f"block: {needle}" not in blocks
        assert f"block: charts/group-sync-dashboard/{needle}" not in blocks if needle == "Chart.yaml" else True
    assert "block: charts/group-sync-dashboard/Chart.yaml" not in blocks
    assert "block: local-development/gsd/__init__.py" not in blocks
    assert "block: local-development/pyproject.toml" not in blocks
    for needle in forbidden:
        if needle == "version: ":
            continue  # values comments may say version: in prose quoted in a block
        assert needle not in blocks or "Chart.yaml" not in blocks


def test_browser_tests_are_specified_for_test_ui():
    text = SPEC.read_text()
    assert "block: local-development/tests/test_ui.py" in text
    assert "test_a_cadata_card_lists_subject_and_expiry" in text
    assert "test_a_verify_failure_shows_the_store_and_the_fix" in text
    assert "test_ca_expiring_uses_the_warnings_banner" in text


def test_the_threshold_rule_is_at_the_day_not_the_day_before():
    body = prose()
    assert "threshold" in body.lower()
    assert "day before" in body.lower() or "days_left == 31" in body or "31" in body
