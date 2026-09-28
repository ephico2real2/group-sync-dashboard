"""#445: SPEC_S4c §3.12 step 6 is a lab procedure a walk can run.

The #444 walk stopped on the step as first written: a standby never reaches claim(),
an out-of-cluster copy is not a standby by default, and copying the pod's ServiceAccount
token off the cluster can read the fleet password through the walk's keep-grant
(`reports/2026-09-27_epic-c-walk-432/README.md`). This file holds the rewritten step
to that report and to the leadership gates the report named.
"""

from __future__ import annotations

import ast
import pathlib
import re
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SPEC = REPO / "docs/specs/SPEC_S4c_credential_lifecycle.md"

# The live walk, not §8's historical blocks (those quote the step as #432 left it).
_LIVE_WALK = re.compile(
    r"^### 3\.12 Verification on the reference cluster.*?(?=^### 3\.13 )",
    re.M | re.S,
)
_STEP6 = re.compile(
    r"^6\. \*\*.*?(?=^7\. \*\*)",
    re.M | re.S,
)
# The program the walk runs: the body of the `oc exec … python3.14 - <<'PY' … PY` command.
# ONE copy, the one that runs — a second copy in a fence is the one that drifts (OB2's review of #461).
_HEREDOC = re.compile(r"<<'PY'\n(.*?)\n[ \t]*PY\n", re.S)


def live_walk() -> str:
    walk = _LIVE_WALK.search(SPEC.read_text())
    assert walk, "SPEC_S4c has no live §3.12 walk before §3.13"
    return walk.group(0)


def live_step6() -> str:
    step = _STEP6.search(live_walk())
    assert step, "§3.12 has no step 6"
    return step.group(0)


def test_step6_is_not_an_out_of_cluster_copy_of_the_app():
    """The #444 stop: a second copy of the app out of cluster, started with the pod's token."""
    step = live_step6()
    for stale in (
        "out of cluster",
        "second copy of the app",
        "GSD_NAMESPACE, the pod's ServiceAccount token",
        "started from the same walk values",
    ):
        assert stale not in step, f"the #444 procedure is still in step 6: {stale!r}"


def test_step6_proves_claimheld_on_developers_lease_inside_the_pod():
    """#445: ClaimHeld across two in-pod processes, as developer, no password on the wire."""
    step = live_step6()
    assert "ClaimHeld" in step
    assert "developer" in step
    assert "`gsd/fleetstate.py#FleetLease.claim`" in step
    assert "`gsd/poller.py#Poller._run_cluster`" in step
    assert "`gsd/poller.py#Poller._retrieve_pending`" in step
    assert "`gsd/poller.py#Poller._ping_accounts`" in step
    assert "oc exec" in step and "-c dashboard" in step and "python3.14" in step
    assert "walk-step6-a" in step and "walk-step6-b" in step
    assert "gsd-fleet-88fa0d759f845b47" in step


def test_step6_names_the_counts_and_the_aborts():
    step = live_step6()
    assert "developer authorize records, any decision: 0" in step
    assert "ocp-oauth-bind-serviceid authorize records, any decision: 0" in step
    assert "openshift-challenging-client: 2" in step
    assert "0 0 0" in step
    for abort in (
        "ABORT: process A did not hold",
        "ABORT: process B did not raise ClaimHeld",
        "ABORT: an authorize ran in the window",
        "ABORT: a credential left the cluster",
    ):
        assert abort in step, f"step 6 is missing the abort {abort!r}"


def test_step6_script_claims_and_never_reads_a_password():
    """The in-pod program — the heredoc the walk runs — is real Python, calls claim(), and cannot present a password."""
    bodies = _HEREDOC.findall(live_step6())
    assert bodies, "step 6 has no <<'PY' heredoc for the in-pod processes"
    tree = ast.parse(textwrap.dedent(bodies[0]))
    worker = next(node.value.value for node in tree.body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "WORKER" for t in node.targets))
    worker_tree = ast.parse(worker)
    names: set[str] = set()
    for node in [*ast.walk(tree), *ast.walk(worker_tree)]:
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
    assert "FleetLease" in names and "ClaimHeld" in names and "claim" in names
    for forbidden in ("fleet_password", "FleetLogin", "lookup", "FleetSession"):
        assert forbidden not in names, f"step 6's script can present a password: {forbidden}"


def test_walk_stays_one_numbered_list():
    """A fence at column 0 under a step closes the step AND the list, and the next step then renders as
    text inside the previous paragraph (CommonMark: an ordered list that interrupts a paragraph must
    start at 1 — "7. **The end.**" became running text under #461's first head). Every code block under
    a step is indented to the step's content, as the walk's `oc` blocks are."""
    walk = live_walk()
    fences = [m.start() for m in re.finditer(r"^```", walk, re.M)]
    assert not fences, "a fence at column 0 inside the §3.12 walk breaks its numbered list"


def test_step6_coordinator_shows_why_b_failed():
    """B's output is captured to be checked; on an abort it must reach the walker. Otherwise a 403, a 409 race and
    B taking the claim — the failure this step exists to catch — all print the same line (OB1-lite's review of #461)."""
    tree = ast.parse(textwrap.dedent(_HEREDOC.findall(live_step6())[0]))
    read = {(node.value.id, node.attr) for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    assert ("b", "stderr") in read, "the coordinator discards process B's stderr on an abort"


def test_step6_block_has_no_trailing_whitespace():
    """The heredoc's blank lines are empty, as every other block's are (`git diff --check`)."""
    assert not [line for line in live_step6().splitlines() if line != line.rstrip()]
