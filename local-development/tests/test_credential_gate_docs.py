"""#315 (SPEC_S4d, review F2 and F3): the maintained documents that stated the superseded per-target
failure rule say the per-account one, and the gate states what "account" and "process" mean."""

from __future__ import annotations

import pathlib

import pytest

from gsd.fleetlookup import CredentialGate

REPO = pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("path,stale", [
    ("docs/specs/SPEC_S5_configmap_onboarding.md", "Different targets still have different #284 gate keys;"),
    ("charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md", "Cross-process and cross-target account-wide\nlockout protection is #285"),
    ("docs/diagrams/remote-cluster-access/source.html", "once refused, not re-sent to that target by this process"),
    ("docs/diagrams/remote-cluster-access/source.html", "a password the target already refused is not sent again"),
    ("docs/DESIGN_remote_cluster_access.md", "a password this target already refused is not sent again"),
    ("docs/CLUSTER_STANZA.md", "the same canonical target/account/password is not sent again"),
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
