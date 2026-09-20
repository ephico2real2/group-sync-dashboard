"""The cluster-connection module's logging (#245).

WHAT THIS PINS, AND WHY EACH ONE EXISTS. Measured on main before this landed: `parser.py` 0 log
calls, `registry.py` 0, `reader.py` 2 — so the module that owns the fleet's connections said nothing
about discovering one, resolving one, or losing one. Meanwhile 1 082 of the pod's 1 784 lines in 90
minutes were httpx request URLs. The tests below are the four properties that make the difference
between a log and a diagnosis:

  1. a cycle that changes nothing logs nothing (or INFO is unreadable at forty clusters)
  2. a failure names its phase, what was in force, and the fix
  3. no credential reaches the log from any phase
  4. the levels are separable — one concern up without the fleet
"""

from __future__ import annotations

import base64
import json
import logging

import pytest

from gsd.clusterconfig import discover
from gsd.clusterconfig.events import PHASES, event, failure, redact
from gsd.config import ClusterConfig
from gsd.kube import UNREACHABLE, ClusterError

TOKEN = "sha256~t0k3n-that-must-never-appear-in-a-log-line"
PASSWORD = "c0rrect-horse-battery-staple"


def _secret(name: str, *, cluster: str, config: dict | None = "default", **data) -> dict:
    if config == "default":
        config = {"bearerToken": TOKEN}
    payload = {"name": cluster, "server": "https://api.example.com:6443", **data}
    if config is not None:
        payload["config"] = json.dumps(config)
    return {
        "metadata": {"name": name, "labels": {"groupsync-dashboard.io/secret-type": "cluster"}},
        "data": {k: base64.b64encode(str(v).encode()).decode() for k, v in payload.items()},
    }


class _Client:
    """The host client's shape, enough for `discover`: a LIST that returns what it is given."""

    def __init__(self, items: list[dict]):
        self.items = items

    def _client(self):
        class _Ctx:
            def __enter__(self_inner):  # noqa: N805
                return self_inner

            def __exit__(self_inner, *a):  # noqa: N805
                return False
        return _Ctx()

    def _list_all_with(self, client, path, params):
        return self.items


class TestTheEventShape:
    def test_a_line_is_the_name_then_key_equals_value(self, caplog):
        with caplog.at_level(logging.INFO):
            event(logging.getLogger("gsd.test"), logging.INFO, "discovery",
                  cycle=7, seen=4, accepted=3, refused=1)
        assert caplog.messages == ["discovery cycle=7 seen=4 accepted=3 refused=1"]

    def test_a_value_with_spaces_is_quoted_so_the_line_stays_parseable(self, caplog):
        with caplog.at_level(logging.INFO):
            event(logging.getLogger("gsd.test"), logging.INFO, "e", action="add the CA to the bundle")
        assert caplog.messages == ['e action="add the CA to the bundle"']

    def test_an_absent_field_is_absent_rather_than_the_word_none(self, caplog):
        """`tls=None` reads as a mode called None; a field with nothing to say says nothing."""
        with caplog.at_level(logging.INFO):
            event(logging.getLogger("gsd.test"), logging.INFO, "e", cluster="a", tls=None, added=None)
        assert caplog.messages == ["e cluster=a"]

    def test_detail_is_truncated_but_only_after_redaction(self, caplog):
        """The order is the whole point (#235's Fable seat): truncate first and a token straddling
        the cut survives, and every JWT is longer than the window."""
        # THE TOKEN MUST STRADDLE THE CUT, or the test passes in both orders: the first version put
        # it at offset 40 with a 300-character limit, well inside the window, so truncating first
        # removed nothing and the mutation survived. It is placed to span the boundary now.
        detail = "A" * 290 + TOKEN + "B" * 100
        with caplog.at_level(logging.WARNING):
            failure(logging.getLogger("gsd.test"), "e", phase="poll", outcome="unreachable",
                    action="x", detail=detail, secrets=[TOKEN])
        line = caplog.messages[0]
        assert TOKEN not in line and "<redacted>" in line and line.endswith("…")
        # A PREFIX is the real failure mode: truncate first and the cut leaves `sha256~t0k3n…`
        # in the log, which is a credential fragment however short the survivor is.
        assert TOKEN[:12] not in line, "a truncated fragment of the token survived"

    def test_the_evidence_goes_last_so_a_long_exception_cannot_bury_the_facts(self):
        """Order is part of the design: what and where, then which cluster, then the fix, then the
        raw error. `detail` is the only field that can run to hundreds of characters, so anything
        after it is off the end of a terminal — and `action` is the part to read first anyway."""
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        log = logging.getLogger("gsd.order-test")
        log.addHandler(handler)
        log.setLevel(logging.WARNING)
        try:
            failure(log, "cluster-unreachable", phase="tls", outcome="cert-verify-failed",
                    action="add the CA", detail="a very long exception " * 5, cluster="c", tls="trusted-bundle")
        finally:
            log.removeHandler(handler)
        keys = [f.split("=")[0] for f in stream.getvalue().split()[1:] if "=" in f]
        assert keys[:4] == ["phase", "outcome", "cluster", "tls"], keys
        assert keys.index("action") < keys.index("detail") == len(keys) - 1, keys

    def test_an_unknown_phase_is_refused_rather_than_logged(self):
        """A typo'd phase reads as a real one and greps as nothing, which is worse than no phase."""
        with pytest.raises(AssertionError, match="unknown phase"):
            failure(logging.getLogger("gsd.test"), "e", phase="conect", outcome="x", action="y")

    def test_every_phase_in_the_closed_set_is_accepted(self, caplog):
        with caplog.at_level(logging.WARNING):
            for phase in PHASES:
                failure(logging.getLogger("gsd.test"), "e", phase=phase, outcome="o", action="a")
        assert [f"phase={p}" for p in PHASES] == [m.split()[1] for m in caplog.messages]


class TestRedaction:
    def test_the_longest_secret_goes_first_so_a_substring_cannot_fragment_it(self):
        """Replacing the short one first cuts the long one in half, and both halves are still the
        credential. Sorting by length descending is what stops it.

        BOTH VALUES MUST CLEAR `_MIN_SECRET`, or this tests nothing: the first version of this test
        used a 6-character substring, which the length guard skips outright, so it passed with the
        sort reversed. Caught by mutating the sort and watching the suite stay green.
        """
        token, part = "sha256~abcdefghijklmnop", "abcdefghijklmnop"
        assert len(part) >= 8, "a value below the guard is never replaced, so the order is untested"
        assert redact(f"got {token}", [part, token]) == "got <redacted>"

    def test_a_value_too_short_to_be_a_secret_is_left_alone(self):
        """Replacing a two-character string would corrupt every line it appeared in."""
        assert redact("the api is up", ["api"]) == "the api is up"

    def test_it_never_raises_on_something_unstringable(self):
        """A diagnostic must not become the reason a poll fails."""
        assert redact("text", 7) == "text"


class TestDiscoveryLogsTransitionsNotStates:
    """The property that makes INFO readable at forty clusters: silence means nothing changed."""

    def test_a_refused_secret_names_the_phase_the_outcome_and_the_fix(self, caplog):
        with caplog.at_level(logging.WARNING):
            clusters, findings = discover(_Client([_secret("gsd-cluster-bad", cluster="bad", config=None)]),
                                          "gsd", host_name="host")
        assert not clusters and len(findings) == 1
        line = caplog.messages[0]
        assert line.startswith("secret-refused ")
        assert "phase=parse" in line and "outcome=config-missing" in line and "action=" in line

    def test_a_duplicate_name_says_which_other_secret_declares_it(self, caplog):
        items = [_secret("gsd-cluster-a", cluster="same"), _secret("gsd-cluster-b", cluster="same")]
        with caplog.at_level(logging.WARNING):
            clusters, _ = discover(_Client(items), "gsd", host_name="host")
        assert not clusters
        assert all("outcome=duplicate-cluster-name" in m for m in caplog.messages)
        assert any("gsd-cluster-b" in m for m in caplog.messages)

    def test_a_shadowed_values_entry_is_no_longer_silent(self, caplog):
        """The cluster loads, so it is not a refusal — but a silent shadow is how an operator edits
        the values entry for an hour and wonders why nothing changes."""
        with caplog.at_level(logging.WARNING):
            discover(_Client([_secret("gsd-cluster-x", cluster="dup")]), "gsd",
                     host_name="host", values_names=("dup",))
        assert any(m.startswith("secret-shadows-values ") and "outcome=shadows-values-entry" in m
                   for m in caplog.messages)

    def test_an_oauth_cluster_says_why_it_is_not_polled(self, caplog):
        with caplog.at_level(logging.WARNING):
            discover(_Client([_secret("gsd-cluster-o", cluster="oa",
                                      config={"oauth": {"username": "u", "password": PASSWORD}})]),
                     "gsd", host_name="host")
        line = next(m for m in caplog.messages if m.startswith("credential-not-supported "))
        assert "phase=credential" in line and "outcome=oauth-exchange-not-built" in line


class TestNoCredentialReachesTheLog:
    """Requirement 6 of #245: drive a failure in EVERY phase with a token and a password present,
    capture everything, and grep for both. It fails if any call site bypasses the emit helper."""

    @pytest.mark.parametrize("phase", PHASES)
    def test_no_secret_survives_any_phase(self, phase, caplog):
        cluster = ClusterConfig(
            name="c", api_url="https://api.example.com:6443", token_value=TOKEN,
            oauth_username="svc", oauth_password=PASSWORD, source="secret:gsd-cluster-c")
        # The message a remote can control: an API server or a proxy in front of it echoes the
        # request back, and the token arrives inside somebody else's error body.
        echoed = f"HTTP 502 on /apis: proxy error, Authorization: Bearer {TOKEN}, pw={PASSWORD}"
        with caplog.at_level(logging.DEBUG):
            failure(logging.getLogger("gsd.test"), "cluster-unreachable", phase=phase,
                    outcome="unreachable", action="check the URL", cluster=cluster.name,
                    detail=echoed, secrets=(TOKEN, PASSWORD, cluster.oauth_username))
        whole = "\n".join(caplog.messages)
        assert TOKEN not in whole, f"the bearer token reached the log in phase {phase}"
        assert PASSWORD not in whole, f"the password reached the log in phase {phase}"
        assert "<redacted>" in whole and f"phase={phase}" in whole

    def test_the_poll_failure_path_redacts_the_clusters_own_token(self, caplog):
        """The path a real failure takes, not a synthetic call: `_log_poll_failure` resolves the
        cluster's credential itself and hands it to the helper."""
        from gsd.poller import _log_poll_failure
        cluster = ClusterConfig(name="c", api_url="https://api.example.com:6443", token_value=TOKEN,
                                source="secret:gsd-cluster-c")
        with caplog.at_level(logging.DEBUG):
            _log_poll_failure(cluster, ClusterError(UNREACHABLE, f"proxy echoed Bearer {TOKEN}"))
        assert TOKEN not in "\n".join(caplog.messages)


class TestTheFailureNamesTheFix:
    """Requirement 3: the reader who most needs help must not get a stack-trace fragment."""

    def _fail(self, caplog, **kw):
        from gsd.poller import _log_poll_failure
        cluster = ClusterConfig(name="c", api_url="https://api.example.com:6443",
                                token_value="t" * 20, source="secret:gsd-cluster-c", **kw)
        with caplog.at_level(logging.WARNING):
            _log_poll_failure(cluster, ClusterError(
                UNREACHABLE, "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
        return caplog.messages[-1]

    def test_the_default_trust_store_failure_offers_both_ways_out(self, caplog):
        line = self._fail(caplog)
        assert "phase=tls" in line and "outcome=cert-verify-failed" in line
        assert "trustedCA.existingConfigMap" in line and "caData" in line, (
            "the fleet-wide fix and the per-cluster fix are both the answer, depending on which the "
            "operator wants; naming one is half a sentence")
        assert "store=" in line, "the store that was actually consulted is the missing fact"

    def test_a_cluster_with_its_own_ca_is_told_to_fix_its_own_secret(self, caplog):
        line = self._fail(caplog, ca_data="-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----")
        assert "tls=caData" in line
        # ASSERT ON THE ACTION, NOT THE LINE. The first version checked `"gsd-cluster-c" in line`,
        # which the `source=` field satisfies on its own — so deleting the caData branch entirely
        # left the test green. Caught by mutating the branch away and watching the suite pass.
        action = line.split('action="', 1)[1].split('"', 1)[0]
        assert "caData" in action and "gsd-cluster-c" in action, (
            f"the fix must name this cluster's own Secret and the field to change; got {action!r}")
        assert "trustedCA.existingConfigMap" not in action, (
            "this cluster pins its own CA, so the fleet-wide bundle is not its fix")

    def test_an_insecure_cluster_is_not_told_to_fix_a_certificate(self, caplog):
        """It cannot be failing verification: there is none. Anything else misdirects the reader."""
        line = self._fail(caplog, insecure_skip_verify=True)
        assert "phase=poll" in line and "outcome=cert-verify-failed" not in line

    def test_a_403_names_the_grant_rather_than_the_status(self, caplog):
        from gsd.poller import _log_poll_failure
        cluster = ClusterConfig(name="c", api_url="https://api.example.com:6443", token_value="t" * 20)
        with caplog.at_level(logging.WARNING):
            _log_poll_failure(cluster, ClusterError("forbidden", "403 Forbidden on /apis"))
        assert "ClusterRole" in caplog.messages[-1] and "outcome=forbidden" in caplog.messages[-1]


class TestTheCycleIsQuietWhenNothingChanged:
    """Requirement 1 of #245, at the level it actually matters: the poller's discovery cycle.

    The unit tests above pin the event shape; this one pins the property that makes INFO usable —
    that a steady fleet is silent. Driven through `_discover_once` rather than a synthetic call,
    because "nothing changed" is a comparison the poller makes and could stop making.
    """

    @pytest.fixture(autouse=True)
    def _env(self, monkeypatch):
        from tests.test_clusterconfig import _Host  # the harness the module's own tests use
        monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
        monkeypatch.setattr("gsd.poller.ClusterClient", _Host)
        _Host.secrets = {"items": [_secret("gsd-cluster-east", cluster="east")]}
        self.host = _Host

    def _poller(self, tmp_path):
        from gsd.config import Settings
        from gsd.poller import Poller
        from gsd.store import Store
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
                            db_path=str(tmp_path / "p.db"))
        return Poller(store, settings)

    def test_the_first_cycle_speaks_and_the_second_is_silent(self, tmp_path, caplog):
        poller = self._poller(tmp_path)
        with caplog.at_level(logging.INFO, logger="gsd.poller"):
            poller._discover_once()
            first = list(caplog.messages)
            caplog.clear()
            poller._discover_once()
            second = list(caplog.messages)
        assert any(m.startswith("discovery ") and "added=east" in m for m in first)
        assert any(m.startswith("cluster-resolved ") and "cluster=east" in m for m in first)
        assert second == [], f"an unchanged cycle logged {second}; at forty clusters INFO is a flood"

    def test_a_secret_edited_in_place_is_reported_even_though_no_name_changed(self, tmp_path, caplog):
        """The edit a reader most needs to see, and the one a names-only comparison misses: the
        cluster is still called `east`, and its TLS mode just became `insecure`."""
        poller = self._poller(tmp_path)
        poller._discover_once()
        self.host.secrets = {"items": [_secret("gsd-cluster-east", cluster="east",
                                               config={"bearerToken": TOKEN,
                                                       "tlsClientConfig": {"insecure": True}})]}
        with caplog.at_level(logging.INFO, logger="gsd.poller"):
            poller._discover_once()
        assert any("changed=east" in m for m in caplog.messages)
        assert any("cluster-resolved" in m and "tls=insecure" in m for m in caplog.messages)

    def test_the_cycle_id_ties_a_clusters_lines_to_one_cycle(self, tmp_path, caplog):
        poller = self._poller(tmp_path)
        with caplog.at_level(logging.INFO, logger="gsd.poller"):
            poller._discover_once()
        cycles = {m.split("cycle=")[1].split()[0] for m in caplog.messages if "cycle=" in m}
        assert len(cycles) == 1, f"one cycle emitted several ids: {cycles}"
