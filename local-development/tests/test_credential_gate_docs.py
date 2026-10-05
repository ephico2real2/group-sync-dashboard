"""#315 (SPEC_S4d, review F2 and F3): the maintained documents that stated the superseded per-target
failure rule say the per-account one, and the gate states what "account" and "process" mean."""

from __future__ import annotations

import pathlib

import pytest

from gsd.fleetlookup import CredentialGate

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path,stale", [
    ("docs/specs/SPEC_S5_configmap_onboarding.md", "Different targets still have different #284 gate keys;"),
    ("charts/group-sync-dashboard/docs/CLUSTER_CREDENTIALS.md", "Cross-process and cross-target account-wide\nlockout protection is #285"),
    ("docs/diagrams/remote-cluster-access/source.html", "once refused, not re-sent to that target by this process"),
    ("docs/diagrams/remote-cluster-access/source.html", "a password the target already refused is not sent again"),
    ("docs/design/DESIGN_remote_cluster_access.md", "a password this target already refused is not sent again"),
    ("charts/group-sync-dashboard/docs/CLUSTER_STANZA.md", "the same canonical target/account/password is not sent again"),
])
def test_current_docs_do_not_claim_failure_is_target_scoped(path, stale):
    text = (REPO / path).read_text()
    assert stale not in text
    assert "#315" in text


def test_the_gate_states_the_scope_of_account_and_process():
    doc = " ".join((CredentialGate.__doc__ or "").split())
    assert '"Account" is the exact configured username string' in doc
    assert "must use one spelling" in doc
    assert "\"Process\" is the production Poller's one gate" in doc


def test_the_release_notes_describe_the_gate_epic_c_shipped():
    """Epic C shipped #315 and #285 in one release (1.0.0): its section must not carry #315's pre-#285 residual as
    current, and the Secret-recreation re-arm must name the restart the running pod needs, as the hand-clear does
    (OB2, Epic C composition review, K1 and K5)."""
    text = (REPO / "docs/CHANGELOG.md").read_text()
    start = text.index("## Application 1.0.0")
    section = " ".join(text[start:text.index("\n## ", start + 1)].split())      # the entries wrap at 120 columns
    assert "still starts with an empty gate" not in section
    assert "recreating the Secret (a new uid) therefore allows one login once the pod restarts" in section
    spec = (REPO / "docs/specs/SPEC_S4c_credential_lifecycle.md").read_text()
    assert "same password (a new uid), and the pod restarted" in spec
    new = text[text.index("## Application 1.1.0"):start]
    new = " ".join(new.split())
    assert "password is rotated or the pod restarts" not in section, "a restart alone no longer clears the Lease's refusal"
    assert "refused Lease entry is cleared and the pod restarted" in section
    assert "Three sentences of 1.0.0's notes" not in new and "SPEC_S4c §3.2 B2 and §8.2" in new
