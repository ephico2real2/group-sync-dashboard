"""GSD_LOG_LEVEL is a promise about what you will see. These tests are the promise.

    CRITICAL  the process cannot serve truthfully — expect never to see it
    ERROR     an operator must act; something advertised is broken and won't self-heal
    WARNING   degraded but scoped or self-healing
    INFO      one line per completed unit of work or state change; readable at steady state
    DEBUG     the app's own reasoning — never third-party protocol framing

WHY THIS FILE EXISTS. Before it, `GSD_LOG_LEVEL` had no test of any kind, and three things were
wrong at once. Measured in the live pod at DEBUG: 428 lines, 366 of them DEBUG, attributed
`httpcore.http11` 260, `httpcore.connection` 96, `gsd.poller` 6, `gsd.kube` 4 — so 97% of what the
level produced was somebody else's TCP framing and the ten lines an operator turned it on for were
buried. Meanwhile `logincapture` had zero DEBUG calls while demonstrably working (73 attempts
stored, 13 distinct users), so its silence was indistinguishable from breakage. And an unrecognised
value raised `ValueError` inside `create_app` — which IS the uvicorn factory — so `logLevel: debug`
crash-looped the pod.

EACH VALUE RUNS IN A SUBPROCESS. `logging.basicConfig` is a no-op once the root logger has handlers,
so a loop over levels in one process measures the first value three times and passes for the wrong
reason.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

#: Emitted inside the subprocess: configure logging exactly as create_app does, then report what the
#: root logger will actually pass and which of the five severities reach the stream.
PROBE = r"""
import io, json, logging, os, sys
sys.path.insert(0, %(dev)r)
from gsd.api import _resolve_log_level, _quiet_transport_framing

level, complaint = _resolve_log_level(os.environ.get("GSD_LOG_LEVEL"))
stream = io.StringIO()
logging.basicConfig(level=level, format="%%(levelname)s %%(name)s %%(message)s", stream=stream)
_quiet_transport_framing()

for name in ("debug", "info", "warning", "error", "critical"):
    getattr(logging.getLogger("gsd.probe"), name)(name + "-line")
# The framing logger the pin is about, and the semantic one it must NOT touch.
logging.getLogger("httpcore.http11").debug("httpcore-line")
logging.getLogger("httpx").info("httpx-line")

text = stream.getvalue()
print(json.dumps({
    "complaint": complaint,
    "effective": logging.getLevelName(logging.getLogger().getEffectiveLevel()),
    "emitted": [n for n in ("debug", "info", "warning", "error", "critical")
                if n + "-line" in text],
    "httpcore": "httpcore-line" in text,
    "httpx": "httpx-line" in text,
}))
"""


def probe(value: str | None, *, debug_http: bool = False) -> dict:
    env = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent"}
    if value is not None:
        env["GSD_LOG_LEVEL"] = value
    if debug_http:
        env["GSD_DEBUG_HTTP"] = "true"
    dev = str(REPO / "local-development")
    done = subprocess.run(
        [sys.executable, "-c", PROBE % {"dev": dev}],
        cwd=dev, env=env, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 0, f"the probe itself failed:\n{done.stdout}\n{done.stderr}"
    return json.loads(done.stdout.strip().splitlines()[-1])


LADDER = {
    "DEBUG": ["debug", "info", "warning", "error", "critical"],
    "INFO": ["info", "warning", "error", "critical"],
    "WARNING": ["warning", "error", "critical"],
    "ERROR": ["error", "critical"],
    "CRITICAL": ["critical"],
}


@pytest.mark.parametrize("level,expected", LADDER.items())
def test_each_level_emits_exactly_its_ladder(level: str, expected: list[str]) -> None:
    """The promise, severity by severity. A level that lets through more or less than this is lying."""
    got = probe(level)
    assert got["effective"] == level
    assert got["emitted"] == expected, f"{level} passed {got['emitted']}, expected {expected}"
    assert got["complaint"] is None, f"{level} is valid and must not complain"


@pytest.mark.parametrize("written", ["debug", "Debug", "info", "WaRnInG"])
def test_case_is_normalised_rather_than_fatal(written: str) -> None:
    """`logLevel: debug` is the natural thing to type, and it used to crash-loop the pod.

    `create_app` is the uvicorn factory, so the ValueError from `basicConfig` meant the container
    never started. Upper-casing removes an outage class with no loss of meaning: there is exactly
    one level `debug` could have meant.
    """
    got = probe(written)
    assert got["effective"] == written.upper()
    assert got["complaint"] is None, "a case variant is understood, so it must not complain"


@pytest.mark.parametrize("written", ["TRACE", "VERBOSE", "20", "0", "  ", "nonsense"])
def test_an_unrecognised_value_degrades_to_info_and_says_so(written: str) -> None:
    """Never raise. A log level is not a security control, so crashing over its spelling is
    disproportionate — but running at a level nobody asked for silently is also wrong, so it warns.
    """
    got = probe(written)
    assert got["effective"] == "INFO"
    if written.strip():
        assert got["complaint"], f"{written!r} degraded silently"
        assert "DEBUG, INFO, WARNING, ERROR, CRITICAL" in got["complaint"]


@pytest.mark.parametrize("written", ["Normal", "Trace", "TraceAll"])
def test_the_openshift_vocabulary_is_rejected_and_the_collision_is_named(written: str) -> None:
    """The trap this chart sets for anyone who knows the platform.

    OpenShift's own `spec.logLevel` takes Normal | Debug | Trace | TraceAll, and this chart carries
    BOTH log levels: `logLevel` for the dashboard's Python logging and `authLogLevel` for
    `spec.logLevel` on authentications.operator.openshift.io/cluster — which is what makes the
    oauth-server emit the login lines the dashboard reads. So an operator typing `Trace` here is
    making an understandable mistake, and the complaint has to name the other one or it is useless.
    """
    got = probe(written)
    assert got["effective"] == "INFO"
    assert "authLogLevel" in got["complaint"], (
        f"{written!r} is OpenShift's vocabulary; the complaint must point at authLogLevel"
    )


def test_unset_is_info() -> None:
    got = probe(None)
    assert got["effective"] == "INFO" and got["complaint"] is None


class TestDebugIsTheAppsOwnReasoning:
    """The half of the contract that says "never third-party protocol framing"."""

    def test_httpcore_framing_is_absent_at_debug(self) -> None:
        """The measured defect: 356 of 366 DEBUG lines in the pod were httpcore socket events."""
        got = probe("DEBUG")
        assert got["emitted"][0] == "debug", "sanity: the app's own DEBUG must still pass"
        assert not got["httpcore"], (
            "httpcore is emitting at DEBUG again, so the level is back to being 97% TCP/TLS "
            "framing and the app's own ten lines are buried in it"
        )

    def test_httpx_is_deliberately_left_alone(self) -> None:
        """Its lines are SEMANTIC — which API call, against what, with which status.

        `HTTP Request: GET <url> "200 OK"` is the record of what the poller actually asked the
        cluster for, it costs 12 lines a cycle rather than 356, and the chart README documents it as
        intentionally present at the default. Pinning it too would have been the easy over-reach.
        """
        assert probe("INFO")["httpx"], "httpx's request lines vanished from INFO"
        assert probe("DEBUG")["httpx"], "httpx's request lines vanished from DEBUG"

    def test_the_framing_is_thresholded_not_deleted(self) -> None:
        """A TLS handshake failing against a corporate CA is a real thing to have to diagnose, and
        it is invisible above WARNING — so the capability is one environment variable away.
        """
        assert probe("DEBUG", debug_http=True)["httpcore"], (
            "GSD_DEBUG_HTTP=true no longer restores the transport framing, so the only way to "
            "debug a handshake is to edit the code"
        )
        assert not probe("DEBUG")["httpcore"], "the default must stay quiet"


class TestTheRejectedValueIsNotRepublished:
    """An environment variable is a place credentials get miswired, and this runs early.

    The first version of `_resolve_log_level` repeated the rejected value back in its warning,
    which is the friendlier message and the wrong one. Measured: a value of
    `sha256~…-secret-token-value` came back verbatim, and a one-million-character value produced a
    1,000,369-character log record — a typo turned into a disclosure and a log-pipeline problem at
    the same time. Found by review, not by us.
    """

    def test_a_credential_shaped_value_is_not_echoed(self) -> None:
        from gsd.api import _resolve_log_level
        secret = "sha256~AbCdEf-not-a-log-level-at-all"
        _, complaint = _resolve_log_level(secret)
        assert complaint, "an unrecognised value must still be reported"
        assert secret not in complaint, (
            "the rejected value was copied into the complaint, so anything miswired into "
            "GSD_LOG_LEVEL lands in an admin-readable pod log"
        )
        for fragment in ("sha256", "AbCdEf", "not-a-log-level"):
            assert fragment not in complaint, f"{fragment!r} survived into the complaint"

    def test_the_complaint_is_bounded_regardless_of_input_size(self) -> None:
        """One log record should not be able to grow with an env var."""
        from gsd.api import _resolve_log_level
        _, complaint = _resolve_log_level("x" * 1_000_000)
        assert len(complaint) < 1000, (
            f"a 1,000,000-character value produced a {len(complaint)}-character complaint; the "
            f"message must describe the value, not contain it"
        )

    def test_it_still_says_how_long_the_value_was(self) -> None:
        """Not echoing is not the same as saying nothing: the length is a safe, useful fact.

        It distinguishes "someone typed `INFo`" from "someone wired a 900-character token in here",
        which are very different mistakes with the same symptom.
        """
        from gsd.api import _resolve_log_level
        _, complaint = _resolve_log_level("q" * 42)
        assert "42-character" in complaint


def test_the_openshift_hint_is_a_membership_test_not_an_echo() -> None:
    """The hint has to survive not echoing, because it is the most useful thing the message says.

    `Normal` and `Trace` are what somebody who knows the platform types, so the collision is
    checked against a fixed vocabulary and reported as a fact ABOUT that vocabulary — carrying none
    of the input forward.
    """
    from gsd.api import _resolve_log_level
    for openshift_word in ("Normal", "Trace", "TraceAll"):
        _, complaint = _resolve_log_level(openshift_word)
        assert "authLogLevel" in complaint, f"{openshift_word} must point at authLogLevel"
        assert "OpenShift's own vocabulary" in complaint, (
            f"{openshift_word} is recognisably OpenShift's, so the message should say so directly "
            f"rather than offering it as a possibility"
        )
    # And a value that is NOT OpenShift's gets the softer form, so the specific hint stays meaningful.
    _, other = _resolve_log_level("nonsense")
    assert "OpenShift's own vocabulary" not in other
