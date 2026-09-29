"""#465 (docs/specs/SPEC_D6_scrub_span.md, part (2), by the operator's decision of 2026-09-29): the scrub cuts a password
out of text wherever it occurs, so a text Rejoin only quotes — a failure's evidence, D8's reason — that held the
password left `<redacted>` spans a reader fills back in, and the scrub cut into its own marks: measured on this rig,
the password `a` read `401 Un<red<redacted>cted>uthorized` in a refused login's evidence. Such a text is fixed words
now, whole. Rejoin refuses no password for being found in the words it writes (SPEC_D6's part (1) is not applied):
the press goes to the login as it always did. The rig is test_cluster_rejoin's: the fake remote counts the wire, the
host is in memory."""

from __future__ import annotations

import logging

import httpx
import pytest

from gsd.fleetlookup import INVALID_SINCE_LABEL
from test_cluster_rejoin import ADMIN_REASON, _rejoin, _writes, presented, remote, review, rig  # noqa: F401 - fixtures
from test_fleet_login import login_302, refused_401
from test_fleet_lookup import sa_secret

#: The contract's own string, written out rather than imported: a test that imported it would pass whatever it said.
MARK = "<redacted: the text contained the credential>"
CONTROL = "Zq9-control-pw-unused-3141"   # occurs in nothing Rejoin writes


# ── no hiccups: a password found in the words Rejoin writes is sent, as before ───────────────────────────────────

@pytest.mark.parametrize("password", [
    "update",            # the question: `who may update clusterrolebindings`
    "a",                 # a letter of nearly every word, the mark's included
    "password",          # the refusal sentences
    "cluster-admin",     # an outcome code: `not-cluster-admin`
    "openshift",         # the platform's own words: the OAuth host, the realm
    "east",              # the cluster's name
    "root",              # the person who pressed
    "credential",        # the mark's own word
    " ",                 # a space: every gap in a sentence
])
def test_a_password_found_in_the_words_rejoin_writes_is_sent_as_before(rig, password):
    """The operator's decision (2026-09-29): "let them rejoin with their password without any hiccups". SPEC_D6's
    part (1) would have answered each of these `422 rejoin-password-in-known-text` before any request. Each is sent
    instead: one authorize with this password, and the same requests and writes, in the same order, as a press whose
    password occurs nowhere. Main behaves the same; the test holds that part (1) stays out."""
    c, app, settings, host, remote = rig

    def press(secret: str):
        remote.answers = [login_302()]
        remote.requests.clear()
        host.calls.clear()
        r = _rejoin(c, username="bob", password=secret)
        return r, [(q.method, q.url.path) for q in remote.requests], _writes(host)

    _, wire, writes = press(CONTROL)
    r, seen_wire, seen_writes = press(password)
    assert r.status_code == 200 and r.json()["outcome"] == "rejoined", r.text
    assert presented(remote) == [("bob", password)]
    assert (seen_wire, seen_writes) == (wire, writes)
    assert app.state.poller.woke == 2


# ── what Rejoin only quotes becomes fixed words whole: a span there would show where the password was cut ─────────

@pytest.mark.parametrize("outcome", ["rejoined", "login-refused"])
def test_the_issues_password_a_leaves_no_span_in_what_rejoin_quotes(rig, caplog, outcome):
    """The issue's second case: password `a`, username `bob`, cluster `east`. On main D8's reason read
    `RBAC: <redacted>llowed by ClusterRoleBinding 'cluster-<redacted>dmins' …`, and a refused login's evidence
    `401 Un<red<redacted>cted>uthorized … B<red<red<redacted>cted>cted>sic …` in the answer. Each is the whole mark
    now, in the answer and in Rejoin's line; the mark holds `a` and is not cut. Rejoin's own sentence still loses its
    `a`s to the scrub: the part of the leak the operator accepted with part (1)."""
    c, app, settings, host, remote = rig
    if outcome == "login-refused":
        remote.answers = [refused_401()]
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password="a")
    assert r.status_code == 200 and r.json()["outcome"] == outcome, r.text
    assert len(remote.authorize) == 1
    ours = [m for m in caplog.messages if m.startswith("cluster-rejoin")]
    if outcome == "rejoined":
        line = next(m for m in ours if m.startswith("cluster-rejoin-review "))
        assert line.endswith(f'reason="{MARK}"'), line
    else:
        assert r.json()["message"].endswith(f"({MARK})"), r.text
        line = next(m for m in ours if m.startswith("cluster-rejoin-failed "))
        assert line.endswith(f'detail="{MARK}"'), line
    assert "<red<" not in r.text + "\n".join(ours)


def test_the_remotes_reason_holding_the_password_is_replaced_whole(rig, caplog):
    """D8's reason is the remote's text, unknown until the password was sent. A binding named like the password left
    `ClusterRoleBinding '<redacted>'` beside the RBAC reason's fixed words; the whole reason is fixed words now."""
    c, app, settings, host, remote = rig
    password = "platform-admins-7c"
    remote.review = review(reason=f'RBAC: allowed by ClusterRoleBinding "{password}" of ClusterRole "cluster-admin" '
                                  f'to Group "{password}"')
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password=password)
    assert r.json()["outcome"] == "rejoined", r.text
    line = next(m for m in caplog.messages if m.startswith("cluster-rejoin-review "))
    assert line.endswith(f'reason="{MARK}"'), line
    assert "<redacted>" not in r.text + caplog.text and password not in r.text + caplog.text


def _echo_in_the_login_500(remote):
    remote.answers = [httpx.Response(500, text="bad credentials Echo-pw-4d1c")]


def _invalidated_token_secret(remote):
    remote.secret = httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "x"}))


@pytest.mark.parametrize("password,prepare", [("Echo-pw-4d1c", _echo_in_the_login_500),
                                              ("target", _invalidated_token_secret)],
                         ids=["an-echo-in-the-login-500", "a-word-of-the-token-reads-evidence"])
def test_a_secret_in_a_failures_evidence_replaces_the_whole_evidence(rig, caplog, password, prepare):
    """A failure's evidence quotes the login's, the token read's or the remote's text. An echo of the password in a
    500's body, or a password that is a word of the token read's own sentence (`the target's legacy-token cleaner`),
    left a span in the answer and in `cluster-rejoin-failed`; both carry fixed words for the whole evidence now."""
    c, app, settings, host, remote = rig
    prepare(remote)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password=password)
    assert r.status_code == 200 and r.json()["message"].endswith(f"({MARK})"), r.text
    line = next(m for m in caplog.messages if m.startswith("cluster-rejoin-failed "))
    assert line.endswith(f'detail="{MARK}"'), line
    assert password not in r.text and "<redacted>" not in r.text


def test_evidence_that_holds_no_secret_is_quoted_as_it_came(rig, caplog):
    """The mark replaces a quoted text only when a secret occurs in it. With a password that occurs nowhere, D8's
    reason and a refused login's evidence read as they were written, in the answer and in Rejoin's lines, as on main."""
    c, app, settings, host, remote = rig
    with caplog.at_level(logging.DEBUG):
        allowed = _rejoin(c, username="bob", password=CONTROL)
        remote.answers = [refused_401()]
        refused = _rejoin(c, username="bob", password=CONTROL)
    assert allowed.json()["outcome"] == "rejoined" and refused.json()["outcome"] == "login-refused"
    review_line = next(m for m in caplog.messages if m.startswith("cluster-rejoin-review "))
    assert review_line.endswith(f'''reason="{ADMIN_REASON.replace('"', "'")}"'''), review_line
    failed = next(m for m in caplog.messages if m.startswith("cluster-rejoin-failed "))
    assert '(401 Unauthorized from ' in refused.json()["message"] and 'detail="401 Unauthorized from ' in failed
    assert MARK not in allowed.text + refused.text + caplog.text
