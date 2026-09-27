"""#315 (SPEC_S4d, review F1): the gated refusal names the target that answered, and must not copy the
credentials a URL may carry into the exception, the public finding or the `fleet-lookup-failed` line. Both
parsers now refuse such a URL (the Secret's `server` rule, and the values `apiUrl` rule since #415), so the
cluster is built directly: this holds the gate's own structural strip as defence in depth."""

from __future__ import annotations

import json
import logging

import pytest

from gsd.config import ClusterConfig
from gsd.fleetlookup import CredentialGate, LookupRefused
from gsd.poller import Poller, _LookupState
from gsd.store import Store
from test_fleet_login import refused_401
from test_fleet_lookup import PASSWORD, USER, run, settings, wire  # noqa: F401


def fail(cluster: ClusterConfig, gate: CredentialGate) -> LookupRefused:
    with pytest.raises(LookupRefused) as caught:
        run(cluster, gate=gate, s=settings(cluster))
    return caught.value


def test_gated_target_never_exports_url_credentials(wire, tmp_path, caplog):
    # The ClusterConfig the values parser built for this stanza before #415 refused it at load.
    url = "https://url-user:url-secret@api.a.example.com:6443"
    first = ClusterConfig("a", url, sa_token_lookup=True, ldap_connection_bootstrap=USER)
    wire.answers = [refused_401()]
    gate = CredentialGate()
    fail(first, gate)
    second = ClusterConfig("b", "https://api.b.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
    exc = fail(second, gate)
    s = settings(second)
    poller = Poller(Store(str(tmp_path / "detail.db")), s)
    with caplog.at_level(logging.INFO):
        poller._lookup_failed(_LookupState(), "b", "gsd-cluster-b", exc, 0)
    public = json.dumps([f.public() for f in s.cluster_registry.findings()])
    combined = f"{exc}\n{exc.detail}\n{public}\n{caplog.text}"
    assert (exc.code, exc.gated, exc.spent) == ("login-refused", True, False) and len(wire.authorize) == 1
    for secret in ("url-user", "url-secret", PASSWORD):
        assert secret not in combined, secret
    assert exc.detail.startswith("https://api.a.example.com:6443"), exc.detail
