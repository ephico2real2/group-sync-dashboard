"""The event vocabulary for the cluster-connection path (#245).

WHY A VOCABULARY RATHER THAN log.info() AT EACH SITE. Measured on main (`62c385a`) before this
existed: `parser.py` 0 log calls, `registry.py` 0, `reader.py` 2 — so nothing recorded that
discovery ran, which TLS mode a cluster resolved to, or that one vanished. Meanwhile the pod wrote
1 784 lines in 90 minutes of which 1 082 were `httpx`'s request URLs. An operator grepping for a
cluster problem found the library's chatter, not the module that owns the connection. Adding
`log.info(...)` at each site would have fixed the silence and left three other problems: every call
site deciding its own field names, every call site responsible for redaction, and no way to pull one
cluster's story out of a fleet's interleaved log.

THE SHAPE: `event-name key=value key="value with spaces"`. Greppable by a person
(`grep 'cluster=ocp-east'`), parseable by a machine, and no commitment to JSON — which would have
made the lines unreadable in a terminal, which is where they are read.

THE FIVE RULES, from the issue's design comment:

1. TRANSITIONS AT INFO, STATES AT DEBUG. A discovery cycle that changes nothing logs nothing, so a
   line always means something happened. At forty clusters the alternative is an unreadable INFO.
2. `phase=` ON EVERY FAILURE, from the closed set below, so the first question — where did it
   break? — is answered by the line itself rather than by reading code.
3. `outcome=` REUSES THE API'S FINDING CODES (`clusterconfig.FINDING_CODES` plus the connection
   outcomes). The log and the page then speak one vocabulary: #244's page sentence and this line are
   two renderings of one fact, not two descriptions that drift.
4. `action=` IS THE FIX, NOT THE DIAGNOSIS — what to change, in the operator's terms. `detail=`
   keeps the raw exception beneath it as evidence. A line that says only what broke makes the reader
   do the translation; this module is the one that knows the translation.
5. REDACTION LIVES HERE, never at the call site. One place to prove, and the test drives a failure in
   every phase with a token and a password present and greps the whole captured log for both.
"""

from __future__ import annotations

import logging
import re

#: Where in the connection a failure happened. Closed, and ordered as the path runs, because the
#: order is the diagnosis: a `tls` failure means parse and credential already succeeded.
PHASES = ("discovery", "parse", "credential", "tls", "connect", "poll")

#: Values that are structurally secret whatever their content. A credential is not redacted by
#: matching a pattern — patterns miss — it is redacted because the caller handed it here as one.
_MASK = "<redacted>"

#: The shortest caller-supplied value still worth removing. LOWERED FROM 8 (review of #247, Codex
#: C1): a probe produced `detail="Bearer abc1234"` — a seven-character token from a test cluster
#: reached the log intact, because the floor was written for pattern-guessing and applied to values
#: the caller had explicitly named as credentials. The trade-off is real in both directions: below
#: about four characters a "secret" cannot be told from ordinary text and replacing it would corrupt
#: every line it appears in, so the floor stays — but a credential the caller handed us wins over
#: readability at any length above that.
_MIN_SECRET = 4

_NEEDS_QUOTING = re.compile(r"[\s\"=]")

#: The phrases OpenSSL and CPython actually produce for a certificate the trust store refused.
#: Matched only against a TRANSPORT message — `<ExceptionType>: <text>`, the one shape this process
#: gives a transport failure — and never against a remote's answer, which is remote-controlled: a
#: proxy's 502 body mentioning certificates is not a TLS problem this cluster has (review of #247,
#: Codex C3). Declared once, here, for the poller's classifier and the fleet login's alike.
VERIFY_FAILURE_PHRASES = (
    "certificate_verify_failed", "certificate verify failed", "sslcertverificationerror",
    "self-signed certificate", "self signed certificate", "unable to get local issuer",
)


def is_transport_message(message: str) -> bool:
    """Whether a failure message is one THIS process wrote for a transport failure — a Python
    identifier before the first colon — rather than a remote's answer (`HTTP 502 on …`)."""
    return message.split(":", 1)[0].strip().isidentifier()


def is_verify_failure(message: str) -> bool:
    """A certificate the trust store refused: a transport message carrying one of the phrases.
    Provenance first, words second."""
    lowered = message.lower()
    return is_transport_message(message) and any(phrase in lowered for phrase in VERIFY_FAILURE_PHRASES)


def _text(value: object) -> str:
    """`str(value)`, and never the reason a poll fails.

    THE GUARD BELONGS TO THE MODULE, NOT TO `redact` (second pass, OB3). The `redact` fix caught an
    unstringable member of `secrets` — but `event` converts the FIELD with a bare `str(value)`
    before handing it over, and `_format_value` converts again, so a value whose `__str__` raised
    still propagated out of a log call and killed the thread that polls a cluster. Measured on the
    working tree: `event(log, INFO, "ev", detail=<object whose __str__ raises>)` → RuntimeError.
    Every string conversion in this module goes through here.
    """
    try:
        return str(value)
    except Exception:  # noqa: BLE001 - a diagnostic must not fail its caller
        return f"<unprintable {type(value).__name__}>"


#: Everything a terminal or a log pipeline reads as structure rather than text: the C0 and C1
#: controls, and the two Unicode line separators — `str.splitlines()` breaks on U+0085, U+2028 and
#: U+2029 too, so a Python-side pipeline saw a forged second line through the first escape set
#: (second pass, OB2 C2).
_CONTROL = re.compile("[\x00-\x1f\x7f-\x9f\u2028\u2029]")


def redact(text: str, secrets: object) -> str:
    """Remove every known secret from text, longest first.

    LONGEST FIRST IS NOT COSMETIC. A password that is a substring of a token (or a token that
    contains one) would otherwise leave the longer value partly intact: replacing the short one
    first cuts the long one in half and the remaining halves are still the credential. Sorting by
    length descending removes the containing value before its substring can fragment it.

    BEFORE TRUNCATION, ALWAYS — the same order `ClusterClient._redact` states and for the same
    reason (review of #235, the Fable seat): `text[:200]` then redact misses a token straddling the
    cut and misses every JWT, which is longer than the window. Callers pass the full text; the
    truncation below happens after.

    Never raises — and the first version did (second pass: Grok C2, OB2 C2, Codex C2): it caught
    `TypeError` alone, so a value whose `__str__` raised anything else escaped through a log call.
    A diagnostic must not become the reason a poll fails, so anything unstringable is simply not
    redacted against, and the other secrets are still removed.
    """
    out = _text(text)
    values: list[str] = []
    try:
        for secret in secrets:
            try:
                if secret:
                    values.append(str(secret))
            except Exception:  # noqa: BLE001 - one unstringable secret must not stop the others
                continue
    except Exception:  # noqa: BLE001 - `secrets` not iterable at all
        return out
    for secret in sorted(values, key=len, reverse=True):
        if len(secret) >= _MIN_SECRET and secret in out:
            out = out.replace(secret, _MASK)
    return out


def _format_value(value: object) -> str:
    r"""One field's value, quoted when it needs to be and never able to forge a line.

    CONTROL CHARACTERS ARE ESCAPED, NOT QUOTED AWAY (review of #247, Codex C8). A remote cluster
    controls its error bodies, and that text reaches `detail=`: a body containing
    `timeout
cluster-resolved cycle=999 cluster=forged` produced TWO physical log lines, the second
    of which reads exactly like a real event. Quoting does not help — a newline inside quotes is
    still a newline to every terminal, `grep`, and key=value parser in the pipeline. So `
`, `
`,
    `	` and the rest become their escapes, and the value stays one line whatever the remote sends.
    """
    text = "" if value is None else _text(value)
    text = _CONTROL.sub(lambda m: {"\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(
        m.group(), f"\\u{ord(m.group()):04x}" if ord(m.group()) > 0xFF else f"\\x{ord(m.group()):02x}"), text)
    if text == "" or _NEEDS_QUOTING.search(text):
        return '"' + text.replace('"', "'") + '"'
    return text


def event(log: logging.Logger, level: int, name: str, *, secrets: object = (),
          detail_limit: int = 300, **fields: object) -> None:
    """Emit one `event-name key=value` line, redacted.

    `secrets` is the credentials in play at this call site — the caller knows them, this function
    does not have to guess. `detail_limit` truncates only `detail`, and only after redaction.

    Fields whose value is None are dropped rather than rendered as `key=None`: an absent field is
    absent, and `tls=None` would read as a mode called None.
    """
    rendered = []
    for key, value in fields.items():
        if value is None:
            continue
        text = redact(_text(value), secrets)
        if key == "detail" and len(text) > detail_limit:
            text = text[:detail_limit] + "…"
        rendered.append(f"{key}={_format_value(text)}")
    # The name itself is never a secret, but it is redacted with everything else rather than
    # exempted: an exemption is a hole somebody eventually puts a formatted string through.
    log.log(level, "%s", " ".join([redact(name, secrets), *rendered]))


def failure(log: logging.Logger, name: str, *, phase: str, outcome: str, action: str,
            detail: object = None, secrets: object = (), **fields: object) -> None:
    """A failure line: phase, outcome, the fix, and the evidence — in that order.

    WARNING rather than ERROR by default, matching the chart's documented ladder: one cluster
    unreachable is "degraded but scoped", not "an operator must act; nothing self-heals". A poll
    that recovers next cycle must not page anybody.

    `phase` is asserted against the closed set, because a typo'd phase is worse than no phase: it
    reads as a real one and greps as nothing.
    """
    assert phase in PHASES, f"unknown phase {phase!r}; the set is {PHASES}"
    # ORDER IS PART OF THE DESIGN: what and where (`phase`, `outcome`), then which (the caller's
    # `cluster=`, `secret=`, `tls=`), then the fix, then the evidence. `detail` is the only field
    # that can be hundreds of characters, so it goes last — a long exception must not push the
    # identifying facts off the end of a terminal, and `action` is the part to read first anyway.
    event(log, logging.WARNING, name, phase=phase, outcome=outcome, **fields,
          action=action, detail=detail, secrets=secrets)
