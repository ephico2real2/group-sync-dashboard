# SPEC D6 — Scrub spans: a password inside the words Rejoin writes is refused before anything is sent, and a quoted text holding a secret is replaced whole (#465)

| | |
|---|---|
| Programme | Epic D (#384), Reconnect a cluster from the screen — a follow-up to Rejoin (SPEC_D4, #316) and to #447 |
| Batch | D — reconnect |
| Release | — (post-programme; Epic D, after D5) |
| Version on release | app and chart minor bumps, assigned at the implementing PR |
| Issue | [#465](https://github.com/ephico2real2/group-sync-dashboard/issues/465) |
| Status | merged |
| Source | Written by the implementer (phase 1: research, measurement and the spec; no production code) from #465, OB2's measurement on #463 and SPEC_D4. Measured on this machine against main `ece9298` (application 1.12.0), on the Rejoin test suite's own rig (a fake remote that counts the wire, the tab's in-memory host). No cluster was touched and no login was made. §6's blocks were cut from a copy of `ece9298` with the design implemented, and applied back to clean copies for the proof in §4. |

## How to read this spec

Each section opens with its point in one bold line. §1 is the whole change in one table. §2 is what was measured
and read: the defect, where the scrub runs, the issue's two rules tried on prototypes, how often common passwords are
affected, and what other code does. §3 is the design. §4 is the tests and the proof. §5 is what is left. §6 is the
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_D6_scrub_span.md . --apply

Line citations are plain file:line text at `ece9298`. `path#name` citations are the maintained kind. Upstream sources
are named with the commit they were read at. Phase 1 writes this file, its index row, one CHANGELOG line and the test
that holds the document; it applies no block.

**Words used below.** The *scrub* is the code that replaces a secret in text with `<redacted>`. A *span* is one such
replacement inside a longer text. A password's *class* is the set of candidate passwords that produce exactly the same
answer and log lines on the rig: a class of one means the output names the password.

## Orchestrator's notes

- **Phase 1 is the spec.** No production code is applied. Versions stay where they are; the implementing PR takes the
  next free MINOR. The CHANGELOG line phase 1 adds says "Spec only".
- **Phase 2 applies part (2) only, by the operator's decision of 2026-09-29 (on #465).** The operator's words: *"this
  is admin and the goal is to promote self service among the cluster admins and making things complicated does not
  make sense. These are highly vetted individuals. So let them rejoin with their password without any hiccups."* And:
  *"If a password is incorrect, just say so. They cannot force their way, as these admin users themselves are using
  their LDAP credentials. So reporting on the various reasons for the failed password is not a big deal. Just redact
  the password in the error logs."* So §1's change (1), the refusal `422 rejoin-password-in-known-text` against
  `known_text`, is not applied: Rejoin refuses no password for being found in the words it writes or the names it
  carries, and gains no step. Change (2) is applied: a text Rejoin only quotes becomes
  `<redacted: the text contained the credential>` whole when a secret occurs in it (`gsd/rejoin.py#_whole`). Change
  (3), the sentences moved into `SAYS`, served only the refusal, so it is not applied either, and every sentence stays
  as main writes it. #447's `rejoin-password-within-username` is byte-identical. The body is unchanged: where it
  describes the refusal, `known_text`, `WORDS`, `SAYS`, the route's `viewer` or what the refusal closes, these notes
  supersede it.
- **§6's nineteen blocks are superseded by the nine below (A to I).** None is applied as written: the blocks of
  part (1) or change (3) alone are not applied, and each block that mixes them with part (2) is replaced by its
  part-(2) lines.

  | §6 block | file | what it held | phase 2 |
  |---|---|---|---|
  | 1 | `gsd/rejoin.py` | the imports `WORDS` needs | not applied (part (1)) |
  | 2 | `gsd/rejoin.py` | `SAYS`, `EVENTS`, `QUOTED_MARK`, `FIELD_WORDS`, `PLATFORM_WORDS` | replaced by A: `QUOTED_MARK` and its comment, verbatim |
  | 3 | `gsd/rejoin.py` | `_whole` | replaced by B: the same code line; the docstring no longer says that `check` refuses |
  | 4, 5, 6 | `gsd/rejoin.py` | `WORDS`, `known_text`, `check`'s `viewer` and its refusal | not applied (part (1)) |
  | 7 | `gsd/rejoin.py` | `refused()`: `names` for `SAYS`, the evidence through `_whole` | replaced by C: the evidence through `_whole`, and the deviation below |
  | 8 | `gsd/rejoin.py` | the gate's sentence into `SAYS` | not applied (change (3)) |
  | 9 | `gsd/rejoin.py` | D8's sentences into `SAYS`, D8's reason through `_whole` | replaced by D: the reason through `_whole` |
  | 10, 11, 12 | `gsd/rejoin.py` | the login's, the read's, the write's, the success's and the unexpected error's sentences into `SAYS` | not applied (change (3)) |
  | 13 | `gsd/rejoin.py` | `_logged_out`'s sentences into `SAYS`; `__all__` | replaced by E: `__all__` gains `QUOTED_MARK` only |
  | 14 | `gsd/api.py` | `check(…, viewer=viewer)` | not applied (part (1)) |
  | 15 | `tests/test_scrub_span.py` | the refusal tests and the whole-text tests | replaced by F |
  | 16 | `API.md` | #447's code, `rejoin-password-in-known-text`, the mark | replaced by G: #447's code (the note "Found while measuring" (1) below) and the mark |
  | 17 | SPEC_D4 §3.1, step 5 | the refusal in the gate table | not applied (part (1)) |
  | 18 | SPEC_D4 §3.7 | the note | replaced by H: part (2), and the refusal stated as not applied |
  | 19 | `docs/CHANGELOG.md` | the bullet | replaced by I |

  F keeps §6's three part-(2) cases byte for byte (`test_the_remotes_reason_holding_the_password_is_replaced_whole`
  and both `test_a_secret_in_a_failures_evidence_replaces_the_whole_evidence` cases). It replaces the refusal tests
  with the operator's `test_a_password_found_in_the_words_rejoin_writes_is_sent_as_before`: nine passwords §6 refused
  (`update`, `a`, `password`, `cluster-admin`, `openshift`, `east`, `root`, `credential`, a space), each sent once,
  with the same requests and writes as a password that occurs nowhere. It adds the issue's `a` as part (2) closes it
  (`test_the_issues_password_a_leaves_no_span_in_what_rejoin_quotes`), and a guard that evidence holding no secret is
  quoted as it came (`test_evidence_that_holds_no_secret_is_quoted_as_it_came`). Measured on a variant that makes
  every failure's evidence the mark, the existing hermetic suite failed only a strict xfail kept for another residual
  (`test_other_json_spellings_never_reach_evidence[triple-review-500]`); the guard fails there directly. D8's reason
  kept on a success was already held (`test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance`). On
  `bc643f3`, F gives 5 failed and 10 passed. The five whole-text cases fail on assertions. The nine sends and the guard
  pass, as they must: main refuses none of these passwords and quotes evidence as it came. With §6 applied, the nine
  sends and both `a` cases fail (`422 rejoin-password-in-known-text`: 11 failed, 4 passed).
- **One deviation part (2) needs once part (1) is dropped: the answer does not scrub the mark again.** §3.3 kept the
  mark whole through part (1): "The mark's words are in `WORDS`, so a password inside them is refused and the mark
  cannot be cut." Without that refusal, block 7's answer, `_scrub(f"{said} ({detail})")`, cuts a password found inside
  the mark's words. Pressed with the issue's `a` on a refused login, the answer ended
  `(<red<redacted>cted: the text cont<redacted>ined the credenti<redacted>l>)`. 35 of the NCSC's 100,000 lie inside the
  mark (`a`, `the`, `red`, `eden`, …). So C answers `f"{_scrub(said, secrets)} ({detail})"` when the evidence became the
  mark, and main's own line otherwise. Kept evidence is therefore still scrubbed together with the sentence: a password
  that straddles the two (`d (401 Una`, `rd (4`, `word (401`) gives the same bytes on main and on this change. Without
  C's two added lines, `test_the_issues_password_a_leaves_no_span_in_what_rejoin_quotes[login-refused]` fails
  (1 failed, 14 passed). What C cannot reach: the emit helper (`gsd/clusterconfig/events.py`, untouched) still redacts
  every field of `cluster-rejoin-failed` and `cluster-rejoin-review`, the mark included, from four characters. Of the
  100,000 only `eden` is four or more characters inside the mark; no quoted text on the fifteen paths holds it, and
  pressed, no mark was cut.
- **§2.4 and §2.5, re-measured for part (2) alone, by pressing.** The rig and the fifteen paths are §2.5's. The
  passwords are the 443 of the NCSC's 99,839 that occur, in some spelling, in some output of those paths: any other
  password changes nothing a scrub writes. Each was pressed once on every path, on main (`bc643f3`), on this change, and
  on §6 applied to a copy of main:

  | | main | part (2), this change | §6 applied, for comparison |
  |---|---|---|---|
  | refused before anything is sent (of the 443) | 5 (#447: `b`, `B`, `o`, `O`, `bob`) | the same 5 | 342 |
  | still leaving a span | 406 | 332 | 29 |
  | where the spans are | — | Rejoin's own sentences, lines and names 286; only the login's own lines 46 | only the login's own lines 23; the login's token name on a failed sign-out 6 |
  | leaving a span on a successful Rejoin | 107 | 91 | 0 |

  Part (2) closes 74, all of them in text Rejoin only quotes (`mission`, `server`, `operator`, `secrets`, `grant`,
  `forbidden`, `dashboard`, `admins`, …), and opens none. The 303 that part (2) leaves and §6 would not are all
  passwords part (1) refused: 280 leave spans in Rejoin's own words or names, and 23 only in the login's lines, whose
  words part (1)'s known text also held (`because`, `lockout`, `next`, `logout`, `open`, `shift`, …). That is the price
  the operator accepted. §2.5 holds: for two passwords that occur nowhere, the 32 answers and 96 lines of the fifteen
  paths are byte-identical on main and on this change. Phase 1's population model gives the same 406 on main.
- **A correction to §1, §2.4 and §5, found while re-measuring: §6 applied leaves 29, not 19.** Phase 1's population
  model scans the login's lines at the emit helper's floor of four, but `RejoinLogin._scrub` cuts the login's remote
  texts at any length before its line is written. Pressed, §6 applied leaves ten more, all in the login's own lines, on
  the TLS-failure, read-timeout and failed-revoke paths: `cat`, `tim`, `cal`, `im`, `rom`, `get`, `med`, `fro`, `sue`,
  `ert` (with `cat`, `fleet-login-failed` read `certifi<redacted>e verify failed`). §6 is not applied, so nothing
  shipped depends on the figure.
- **Applying phase 2.** The command in "How to read this spec" applies §6, and on main it now fails. Phase 2 is applied
  from the nine blocks below, the only blocks in these notes, with the notes cut out to a file outside the tree
  (`apply-spec-blocks.py` refuses a git tree with uncommitted changes):
  `sed -n "/^## Orchestrator's notes$/,/^## 1\. The point/p" docs/specs/SPEC_D6_scrub_span.md > "${TMPDIR:-/tmp}/d6-part2.md"`,
  then `python3 local-development/apply-spec-blocks.py "${TMPDIR:-/tmp}/d6-part2.md" . --apply`. On `bc643f3` they
  check out ("9 blocks check out across 5 files") and reproduce this change's five files byte for byte.
  `tests/test_scrub_span_spec.py` holds the tree to them. These notes, the header's Status, D6's index row and that
  test are edited by hand, as S4f's are: a block cannot move a status, because its Old text would also match inside
  its own fence.

**A** — `gsd/rejoin.py`: the mark (§6 block 2's part-(2) lines, verbatim).

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}


```

```python
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}
#: What a quoted text becomes when a secret occurs in it (#465): the whole field, never a span (`_whole`).
QUOTED_MARK = "<redacted: the text contained the credential>"


```

**B** — `gsd/rejoin.py`: `_whole` (§6 block 3's code line, with a part-(2) docstring).

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
            forms |= layer
    return _fleet_scrub(text, list(forms))


```

```python
            forms |= layer
    return _fleet_scrub(text, list(forms))


def _whole(text: str, secrets) -> str:
    """A text Rejoin only quotes — a failure's evidence, D8's reason — as it came, or QUOTED_MARK when the password or
    any secret occurs in it, or an earlier scrub already marked it (#465, SPEC_D6): the scrub cuts a secret out wherever
    it occurs, and a span cut out of words the reader knows spells what was cut."""
    return QUOTED_MARK if "<redacted" in text or _scrub(text, secrets) != text else text


def _quoted(text: str, secrets) -> str:
    """Keep whole quoted text, omitting a mark that would itself contain a secret or be cut by the emitter."""
    text = _whole(text, secrets)
    return "" if text == QUOTED_MARK and _scrub(text, secrets) != text else text


```

**C** — `gsd/rejoin.py`: `refused()`: the evidence through `_whole`, and the mark not scrubbed again in the answer.

<!-- block: local-development/gsd/rejoin.py | edit -->
```python

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence; both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        detail = _scrub(detail, secrets) if detail else None   # any length: the emit helper skips values under four
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
        return {"outcome": code, "message": _scrub(f"{said} ({detail})" if detail else said, secrets), "at": now_iso()}

```

```python

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence (`_whole`); both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        detail = (_quoted(detail, secrets) or None) if detail else None   # any length: the emit helper skips values under four
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
        if detail == QUOTED_MARK:   # omit a collision instead of cutting a span into the fixed mark
            clean = _scrub(said, secrets)
            message = f"{clean} ({detail})"
            # The password can also straddle the sentence and the newly appended mark.
            return {"outcome": code, "message": clean if _scrub(message, secrets) != message else message,
                    "at": now_iso()}
        return {"outcome": code, "message": _scrub(f"{said} ({detail})" if detail else said, secrets), "at": now_iso()}

```

**D** — `gsd/rejoin.py`: D8's reason through `_whole`.

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_scrub(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
```

```python
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_quoted(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
```

**E** — `gsd/rejoin.py`: `__all__` gains `QUOTED_MARK`.

<!-- block: local-development/gsd/rejoin.py | edit -->
```python


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "STOPPED", "RejoinLogin", "check",
           "fleet_accounts", "question", "question_words", "refusal", "rejoin", "remote_says_cluster_admin",
           "stopped_unexpectedly"]
```

```python


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "QUOTED_MARK", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "STOPPED",
           "RejoinLogin", "check", "fleet_accounts", "question", "question_words", "refusal", "rejoin",
           "remote_says_cluster_admin", "stopped_unexpectedly"]
```

**F** — `tests/test_scrub_span.py`: part (2)'s tests and the operator's no-hiccups test.

<!-- block: local-development/tests/test_scrub_span.py | create -->
```python
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

from gsd.rejoin import QUOTED_MARK, _whole, _spellings
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
    now; because the mark itself contains `a`, that quoted field is omitted. Rejoin's own sentence still loses its
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
        assert ' reason=' not in line, line
    else:
        assert MARK not in r.json()["message"], r.text
        line = next(m for m in ours if m.startswith("cluster-rejoin-failed "))
        assert ' detail=' not in line, line
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


# Regression: a fixed mark must not introduce a secret or expose it through a second scrub.

@pytest.mark.parametrize('text,secrets,expected', [
    ('unchanged remote reason', ['pW-943'], 'unchanged remote reason'),
    ('', ['pW-943'], ''),
    ('server echoed pW-943', ['pW-943'], QUOTED_MARK),
    ('echo token-T54', ['pW-943','token-T54'], QUOTED_MARK),
    ('earlier <redacted> remainder', ['pW-943'], QUOTED_MARK),
    ('earlier <redacted: marker', [], QUOTED_MARK),
    ('not <Redacted>', ['pW-943'], 'not <Redacted>'),
])
def test_whole_contract(text,secrets,expected):
    assert _whole(text,secrets)==expected

@pytest.mark.parametrize('password', ['a','contained','eden','credential','the text'])
def test_whole_escaped_forms(password):
    for form in {password} | _spellings(password):
        assert _whole('remote: '+form, [password]) == QUOTED_MARK

@pytest.mark.parametrize('path', ['failed','review'])
@pytest.mark.parametrize('password', ['contained','eden'])
def test_colliding_quote_does_not_print_or_cut_the_password(rig,caplog,path,password):
    c,app,settings,host,remote=rig
    if path=='failed':
        remote.answers=[httpx.Response(500,text=f'echo {password}')]
    else:
        remote.review=review(reason=f'echo {password}')
    with caplog.at_level(logging.DEBUG):
        r=_rejoin(c,username='bob',password=password)
    assert r.status_code==200
    assert r.json()['outcome']==('login-failed' if path=='failed' else 'rejoined')
    assert presented(remote)==[('bob',password)]
    line=next(m for m in caplog.messages if m.startswith('cluster-rejoin-'+('failed ' if path=='failed' else 'review ')))
    print('\nPASSWORD',password,'PATH',path,'\nANSWER',r.json()['message'],'\nLINE',line)
    # The sentence/phase's existing credential span for eden is out of scope.
    field='detail' if path=='failed' else 'reason'
    assert f' {field}=' not in line, line
    if path=='failed':
        assert password not in r.json()['message'], r.json()['message']
        assert QUOTED_MARK not in r.json()['message']


def test_appending_marker_does_not_reintroduce_password_across_join(rig):
    c, app, settings, host, remote = rig
    password = 'again (<redacted:'
    remote.answers = [httpx.Response(500, text='echo ' + password)]
    r = _rejoin(c, username='bob', password=password)
    assert r.status_code == 200 and r.json()['outcome'] == 'login-failed'
    assert len(remote.authorize) == 1
    assert password not in r.json()['message'], r.json()['message']
```

**G** — `local-development/API.md`: #447's code and the mark.

<!-- block: local-development/API.md | edit -->
```markdown
password}` as strings (fixed words: no key or value is repeated, because a key can be the password),
`rejoin-username-invalid` (outside the bootstrap grammar), `rejoin-fleet-account` (a name a fleet path logs in as,
compared stripped and casefolded), `rejoin-password-missing` and `rejoin-password-invalid` (a control character, which
RFC 7617 forbids, or an unpaired surrogate, which UTF-8 cannot carry). A success wakes discovery. One
`cluster-rejoin-review` line carries the remote's answer, then `cluster-rejoined` or `cluster-rejoin-failed`; each names
the person and the account and carries no credential.

## GroupSync CRs
```

```markdown
password}` as strings (fixed words: no key or value is repeated, because a key can be the password),
`rejoin-username-invalid` (outside the bootstrap grammar), `rejoin-fleet-account` (a name a fleet path logs in as,
compared stripped and casefolded), `rejoin-password-missing`, `rejoin-password-invalid` (a control character, which
RFC 7617 forbids, or an unpaired surrogate, which UTF-8 cannot carry) and `rejoin-password-within-username` (the
password, stripped and casefolded, is the username or lies inside it; #447). A success wakes discovery. One
`cluster-rejoin-review` line carries the remote's answer, then `cluster-rejoined` or `cluster-rejoin-failed`; each names
the person and the account and carries no credential. A failure's evidence and the remote's reason, which Rejoin only
quotes, read `<redacted: the text contained the credential>` whole when a secret occurs in them (issue #465).
If that fixed mark itself contains a secret, the quoted field is omitted in both the answer and the log;
the existing outcome and failure sentence are still reported.

## GroupSync CRs
```

**H** — SPEC_D4 §3.7's note, part (2).

<!-- block: docs/specs/SPEC_D4_cluster_rejoin.md | edit -->
```markdown
test then looks for them in the answer, every log line at DEBUG, every stored Secret, the gate, the findings and the
whole database, and on the wire outside the one authorize's `Authorization` header.

## 4. The decisions
```

```markdown
test then looks for them in the answer, every log line at DEBUG, every stored Secret, the gate, the findings and the
whole database, and on the wire outside the one authorize's `Authorization` header.

**A password inside words the reader already knows (#465, SPEC_D6).** The scrub cuts a password out wherever it occurs,
so a password that is part of text the reader knows leaves spans that spell it. A text Rejoin only quotes, which exists
only after the password was sent (a failure's evidence, D8's reason), becomes
`<redacted: the text contained the credential>` whole when a secret occurs in it (`gsd/rejoin.py#_whole`), and the
answer does not scrub the mark again, so no span is cut there: with the password `a`, a refused login's evidence read
`401 Un<red<redacted>cted>uthorized` and reads the mark now. Rejoin refuses no password for being found in its own
words or names (SPEC_D6's part (1) is not applied, by the operator's decision of 2026-09-29), so such a password still
leaves spans in Rejoin's sentences and lines: `update` in `who may <redacted> clusterrolebindings`, and `a` in
`Signed in to e<redacted>st <redacted>s bob`. Every spelling above stays scrubbed. The login's own lines, shared with
the fleet, keep their spans (SPEC_D6 §5).
If that fixed mark itself contains a secret, the quoted field is omitted in both the answer and the log;
the existing outcome and failure sentence are still reported.

## 4. The decisions
```

**I** — the CHANGELOG bullet.

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **Rejoin quotes a text that holds a secret in fixed words, whole (#465, Epic D #384,
  `docs/specs/SPEC_D6_scrub_span.md`, part (2)).** The scrub cuts a password out of text wherever it occurs, so a
  password found in a text Rejoin only quotes — a failure's evidence, D8's reason — left `<redacted>` spans that
  spelled it, and the scrub cut into its own marks: with the password `a`, a refused login's evidence read
  `401 Un<red<redacted>cted>uthorized`. Such a text now reads `<redacted: the text contained the credential>` whole,
  in the answer, in `cluster-rejoin-failed` and in `cluster-rejoin-review`. Rejoin refuses no password for being found
  in the words it writes (SPEC_D6's part (1) is not applied, by the operator's decision of 2026-09-29): the press goes
  to the login as before, and a password that is one of Rejoin's own words or names still leaves spans there.
  Pressed with the NCSC's 100,000 most common passwords on fifteen paths: 406 left a span on main and 332 do now,
  none that did not before, and Rejoin refuses none that main sends. Every password spelling stays scrubbed; the
  one-login budget, the per-pod credential gate and #447's refusal are unchanged.
If that fixed mark itself contains a secret, the quoted field is omitted in both the answer and the log;
the existing outcome and failure sentence are still reported.
```

- **Review correction to phase 2 (C2).** The quoted-field renderer `_quoted` omits a replaced field when
  `_scrub(QUOTED_MARK, secrets)` would change the mark itself. `_whole` still returns the specified fixed mark;
  `_quoted` applies the collision fallback before the answer or emitter receives it. This supersedes the notes'
  unconditional mark claims, the `a` test's original expected mark, and the assertion that protecting the log needs
  a shared-emitter change. For example, an echoed `eden` otherwise becomes `cr<redacted>tial` inside the logged mark,
  while the answer's mark contains the literal password. An echoed `contained` demonstrates the same defect without
  an existing span in `phase=credential`. Omitting that quoted field preserves the existing failure sentence and
  introduces no refusal, login step, or new precondition. The answer also checks the composed sentence plus mark:
  a password spanning their join causes the quoted suffix to be omitted, instead of printing or cutting it.
  The 406/332/74/29 figures above describe PR head 30da871;
  they are a bounded measurement of its fifteen paths, not proof of safety for other remote texts. The added tests
  exercise both the failure and review renderers. The original spec body remains unchanged.

- **Phase 1's notes, as #479 merged them, follow.** Where they describe the refusal, `known_text`, `WORDS` or `SAYS`, the
  notes above supersede them.
- **The decision is rule (b), with rule (a) kept for the one kind of text (b) cannot see.** The issue asked the spec
  to choose between (a) *replace the whole field* and (b) *refuse the password before any request*. Measured (§2.3):
  (a) alone cannot hide a password that is a whole field (`cluster=<redacted…>` for the cluster `east`: class 1 under
  every form of (a)), and it narrows `update` to six guesses. (b) sends and writes nothing for a password it refuses.
  But (b) can only refuse what is known before the password is sent. The text Rejoin *quotes* — a failure's evidence,
  D8's reason — exists only afterwards, and with (b) alone 79 of the NCSC's 100,000 most common passwords still left
  spans there (54 of them after a successful login). So the quoted text is replaced whole when a secret occurs in it.
  There (a)'s two measured failures cannot happen: no quoted field is a name, and a refused password never reaches an
  own-word field. The remainder is 19 of the 100,000 (§5).
- **Why the sentences move into `SAYS`.** The refusal must hold every word Rejoin writes. A copy of the sentences
  beside the code would drift; moving them into a table next to `READ_SAYS` (the pattern the module already uses) lets
  `check` read exactly what `_exchange` writes. Measured byte-identical: for a password that occurs nowhere, every
  answer and every line on 15 paths is the same on main and on the design (32 answers, 96 lines), and so are the three
  sentences no path reaches without help (`stopped`, `held-elsewhere`, `unnamed-token`).
- **No length floor, measured.** A floor of eight characters (NIST's minimum for any password; GitLab's for a masked
  value) was prototyped: it refused `update` and `a`, and it broke 95 existing cases of the D4 review's short-password
  pins (`xyZ`, `x"Z`, `éZ`, Go's spellings), which exist to prove that the scrub removes a short password's escaped
  forms. The refusal here is about the scrub, not about strength (§3.4).
- **The #286 guard stays.** `tests/test_fleet_login.py#TestScopeIsLoginOnly` fails any `gsd` module other than
  `fleetlogin.py` that names the token API. The first draft imported `USER_TOKEN_API` for its words and failed that
  guard; `openshift` is refused by the platform's own words instead (§3.2).
- **Found while measuring, outside this change.**
  (1) `local-development/API.md` never gained #447's `rejoin-password-within-username`; the API.md block below adds it
  beside #465's code, because the sentence is edited anyway.
  (2) The scrub cut into its own marks: with the password `a` on a refused login the answer read
  `Un<red<redacted>cted>uthorized` and `B<red<red<redacted>cted>cted>sic`. Closed here: a password inside a mark is
  refused, and a quoted text becomes one fixed mark.
  (3) The fleet's own lines carry the same mechanism for the fleet password. For example, `fleet-login`'s `oauth=`
  field is cut by the emit helper, although `fleetlogin.py`'s own rule is that a structured value the operator acts on
  is never substring-redacted. The fleet password is the operator's choice; a later issue.
  (4) The token read's 403 sentence says "the ServiceAccount lacks list permission here" while the reader is the
  person's own login. Wording only.
- **#481 (`docs/specs/SPEC_S4f_fleet_gate_backstop.md`) adds three emit call sites to `gsd/fleetstate.py`**: the
  `fleet-lease-absent` line in `claim()` and in `restore()`, and the copy's `fleet-state-unavailable` in `_keep()`. With
  it applied, `event` and `failure` have 45 call sites in 6 consuming modules. §2.3's 42 is the count at `ece9298`, and
  `tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds this document to the live count.

## 1. The point, in one table

**Rejoin stops cutting a password out of words the reader already knows: a password found in those words is refused
before anything is sent, and a quoted text that holds a secret is shown as fixed words, whole.**

| | |
|---|---|
| **What goes wrong today** | The scrub replaces the password wherever it occurs. A password that is part of the text around it leaves spans that spell it: `update` (username `bob`) read `who may <redacted> clusterrolebindings`, and `a` read `Signed in to e<redacted>st <redacted>s bob`. Of the NCSC's 100,000 most common passwords, 406 occur in text the scrub scans on some Rejoin path. |
| **The change** | (1) `gsd/rejoin.py#check` refuses, before any request, a password found — ignoring case, as typed or stripped — in `gsd/rejoin.py#known_text`: every word Rejoin writes and every name it carries. (2) A text Rejoin only quotes becomes `<redacted: the text contained the credential>` whole when a secret occurs in it (`gsd/rejoin.py#_whole`). (3) Rejoin's sentences move into `SAYS`, so the refusal reads exactly what is written. |
| **What it closes** | Both cases of the issue, every word and name Rejoin writes, the scrub's cuts into its own marks, and 387 of the 406 common passwords. |
| **What it costs** | 385 of the 100,000 common passwords are refused; 58 of them would not have leaked. When a quoted text holds a secret, the answer and Rejoin's failure line lose its words; the login's own line keeps them. |
| **What does not change** | Every scrub (the scrub code is untouched, and every text it scrubbed is still scrubbed); the one-login budget; D4-7's per-pod memory; #447's refusal, which runs first and is byte-identical; every answer and line for a password that occurs nowhere (measured, §2.5). |
| **What is left** | 19 of the 100,000: 13 in the login's own lines, on failure paths (fleet code, shared), and 6 of one or two characters in the login's random token name on a failed sign-out (§5). |

## 2. Read and measured

### 2.1 The defect

**On main, a password that is part of the answer's words, a name, the remote's words or the scrub's own mark is spelled
back by its spans: every one tried is a class of one on every path where it occurs.**

The rig is `tests/test_cluster_rejoin.py#rig`: cluster `east`, username `bob`, viewer `root`, the fake remote answering
as SPEC_D4's lab did. The issue's two cases, pressed once each (password `update`, then `a`):

| path | what the answer and the lines read (the spans only) |
|---|---|
| `update`, success | answer `who may <redacted> clusterrolebindings there; … and <redacted>d gsd-cluster-east here`; lines `question="<redacted> clusterrolebindings"` and `written=<redacted>d` |
| `update`, the remote says no | answer `east says bob may not <redacted> clusterrolebindings there`; lines `question=…` and `action="east says bob may not <redacted> …"` |
| `a`, success | answer `Signed in to e<redacted>st <redacted>s bob, who m<redacted>y upd<redacted>te clusterrolebindings there; re<redacted>d …`; line `reason="RBAC: <redacted>llowed by ClusterRoleBinding 'cluster-<redacted>dmins' …"` |
| `a`, a refused login (401) | the line `detail="401 Un<redacted>uthorized from o<redacted>uth-openshift.<redacted>pps… B<red<redacted>cted>sic re<red<redacted>cted>lm…"`; the answer, scrubbed once more, `Un<red<redacted>cted>uthorized`, `B<red<red<redacted>cted>cted>sic` |

**Read back, measured rather than argued.** A reader has the code and the names; the cluster and the username sit in
plain text beside the spans. For each case the drive pressed every candidate string that could explain the output
(every substring of the shortest text that changed) and kept those whose answer and lines came out byte-identical,
instants aside. This is the attack the PDF-redaction literature measures: Bland, Iyer and Levchenko's Edact-Ray "allows
an attacker to test which strings from a dictionary of candidates create the same PDF output as the original redacted
PDF file" (PoPETs 2023(3), 43–61, p. 43). On main, every one of these is a class of one:

| password | success | refused (401) | locked (500) | the remote says no | held by the gate |
|---|---|---|---|---|---|
| `update` | **1** | no occurrence | no occurrence | **1** | no occurrence |
| `a` | **1** | **1** | **1** | **1** | **1** |
| `password` | no occurrence | **1** | **1** | no occurrence | **1** |
| `openshift` | **1** | **1** | **1** | **1** | **1** |
| `cluster-admin` | **1** | no occurrence | no occurrence | **1** | no occurrence |
| `east` | **1** | **1** | **1** | **1** | **1** |
| `Adm1n-pw-7f3e9c` (the suite's) | no occurrence | no occurrence | no occurrence | no occurrence | no occurrence |

Where each came from: `update` and `password` from Rejoin's sentences and the question; `a` from everywhere, the marks
included; `openshift` from the OAuth host in `fleet-login`'s `oauth=` field and the realm the oauth-server answers with;
`cluster-admin` from the outcome code `outcome=not-<redacted>` and the remote's RBAC reason; `east` from every
`cluster=` field.

### 2.2 Where the scrub runs

**Four helpers, two floors, and every text Rejoin writes while the password is in play passes through one of them.**

| helper | what it removes | floor | runs on |
|---|---|---|---|
| `gsd/rejoin.py#_scrub` (rejoin.py:72-83) | each secret, and its JSON spellings once and twice escaped, then the fleet's scrub | none | the answer (rejoin.py:234, 302, 308); a failure's evidence (rejoin.py:231); D8's reason (rejoin.py:254); the login's remote text through `RejoinLogin._scrub` (rejoin.py:97-99): fleetlogin.py:472, 485, 490, 567, 569, 579, 596, 612, 641, 668, 687, 729; D8's failed body before the 200-character cut through `_ReviewClient._redact` (rejoin.py:180-181, kube.py:666) |
| `gsd/fleetlookup.py#_scrub` (fleetlookup.py:224-232) | the two helpers below, then the raw value | none | `LookupRefused.scrub` (fleetlookup.py:94-99), called at rejoin.py:284 and 294 |
| `gsd/clusterconfig/events.py#redact` (events.py:103-135) | each raw value, longest first | 4 (`_MIN_SECRET`, events.py:52) | every field value and the name of every line (events.py:173, 179): Rejoin's at rejoin.py:232, 253, 297, 310, the login's at fleetlogin.py:445, 675, 678, 737, 750 |
| `gsd/kube.py#redact_text` (kube.py:379-400) | each value stripped, and its JSON forms once and twice | 8 | inside the first two, and every `ClusterClient` error (kube.py:613) |

Two consequences. A password of one to three characters is cut from the answer and from `detail` and `reason`, but not
from a line's other fields; comparing the two is itself a read-back. And the scrub runs on the same text more than once
(the login's remote text, then the evidence, then the answer), so a password inside `<redacted>` cuts the earlier marks.

### 2.3 The issue's two rules, prototyped and measured

**Rule (a) alone leaves a password that is a whole field spelled back and common words narrowed to a handful; rule (b)
alone refuses what it knows and leaves the text Rejoin quotes; together they leave 19 of the 406 common passwords that
leak today.**

Each rule was built into a copy of `ece9298` and measured with the same drive. The smallest class over the five paths
(the reader picks the most telling path):

| password | main | (a) as worded: whole field when inside a larger word | (a) at its strongest: whole field on any occurrence, every helper | (b) with a floor of 8 and the names | this design |
|---|---|---|---|---|---|
| `update` | 1 | **1** (a whole word stays a span) | 6 (`date` `pdat` `pdate` `upda` `updat` `update`) | refused | refused |
| `a` | 1 | 11 | 11 | refused | refused |
| `password` | 1 | **1** | 92 | **1** | refused |
| `openshift` | 1 | **1** | 703 | **1** | refused |
| `cluster-admin` | 1 | **1** | 87 | **1** | refused |
| `east` | 1 | **1** | **1** (the field `cluster=` is the password) | refused | refused |
| `Adm1n-pw-7f3e9c` | sent, nothing changes | sent, nothing changes | sent, nothing changes | sent, nothing changes | sent, nothing changes |

The first prototype models "inside a larger word" only: the scrub helpers are not handed the names. The issue's "or a
known name" would not change the `update` row, which is a whole word and no name.

The strongest (a) changes `gsd/clusterconfig/events.py#redact`, `gsd/kube.py#redact_text` and both fleet scrubs:
`event` and `failure` have 42 call sites in 6 consuming modules (plus `failure`'s internal call to `event`), and
28 assertions in nine test files expect a `<redacted>` mark
where a secret was (three of them the writer's config twin, not the scrub). It also still spells `east`, and it
leaves `update` to six guesses. The floor of eight broke 95 existing test cases (§3.4). This design is rule (b) with the
full known text, plus the whole-field rule for quoted text only.

### 2.4 How often: the 100,000 most common passwords

**406 of the NCSC's 100,000 most common passwords occur in text the Rejoin scrub scans. This design refuses 327 of them
before anything is sent, the whole-field rule covers 60 more, and 19 still leave a span — none on a successful Rejoin
whose login is signed out.**

The list is the UK NCSC's top 100,000 from Have I Been Pwned, as SecLists carries it
(`Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt`, commit `1a7bb91`, 99,839 non-empty lines,
SHA-256 `c2e56968…`); the NCSC's own download paths answered 404 on 2026-09-28. Every Rejoin path was pressed once with
a password that occurs nowhere, and a password counts as leaking when it occurs, as written, in a text the scrub scans,
at or above that text's floor. The refusal column is the design's own `check`, run on every password.

| | main | (b), the names only | (b), the design's known text, quoted text still cut | this design |
|---|---|---|---|---|
| refused before anything is sent | 6 (#447 and control characters) | 65 more | 385 more | 385 more |
| of those, would not have leaked | — | 1 | 58 | 58 |
| still leaving a span | **406** | 342 | 79 (54 after a successful login) | **19** |
| where the spans are | Rejoin's words 256, quoted words 114, names 16, instants and token names 10, the remote's words 10 | Rejoin's words 215, quoted 108, other 19 | quoted words 67, the remote's 7, token names 5 | the login's own lines 13, the random token name 6 |

Simulated from the recorded outputs: with every component's fixed words as data (the login's, D8's client's, the
token read's and the write's messages), rule (b) alone would refuse 438 and leave 16; §5 says why that is not this
change.

### 2.5 What must not change, measured

**For a password that occurs nowhere, the design writes byte-for-byte what main writes.**

On 15 paths (success; a revoke that failed; 401; 500; a read timeout; a 302 without a token; discovery down; a TLS
failure; the remote says no; D8 fails; the token Secret missing, forbidden and invalidated; the write refused; the gate
holding a refusal), pressed with two passwords that occur nowhere: 32 answers and 96 lines, identical. The three
sentences no path reaches without help — an unexpected error, a gate entry naming no URL, an unprefixed token — driven
directly: identical.

### 2.6 What others do

**Where the secret's place is known, code replaces the whole value by its key. Where it is searched for, code cuts
spans, and GitLab and CircleCI refuse or skip the short or name-like values. Nothing read says a span must not reveal
where it was cut in known text.**

| source, as read | what it does |
|---|---|
| Kubernetes client-go, `staging/src/k8s.io/client-go/transport/round_trippers.go` at `92a0e42`, lines 461-485 | `maskValue` masks by the header's name (`Authorization`), keeps the scheme and replaces the whole credential with `<masked>`, whatever it contains; `newHeadersMap` (642-655) applies it before any logger sees a header |
| Kubernetes KEP-1753, log sanitization, `kubernetes/enhancements` at `875dc3f` | "Values of individual fields of primitive types like string will not be checked" (line 167); an entry carrying a tagged secret was replaced whole: "Log message has been redacted. Log argument #%d contains: %v" (203-207); removed in 1.24 for its cost (111-113) |
| OpenShift oauth-server at `0a5bbfd` | the challenge is `Basic realm="%s"` (password_auth_handler.go:39) with the realm `"openshift"` (pkg/oauthserver/auth.go:379, 413): a fixed word of every OpenShift remote |
| OpenShift cluster-authentication-operator at `b33edc4` | the OAuth route is `oauth-openshift`, its host `"oauth-openshift." + ingressConfig.Spec.Domain` (pkg/controllers/customroute/custom_route_controller.go:150), replaceable by a custom host (162-172) |
| Sentry's Python SDK at `015ff31` | scrubs by key: a key such as `password` (scrubber.py:15-17) has its whole value replaced with `[Filtered]` (scrubber.py:117-118; _types.py:13, 121-124) |
| GitHub Actions: the runner at `15231be`, and `github/docs` at `071ed75` | the runner cuts every occurrence of a registered value into `***` (SecretMasker.cs:216-288) and registers any non-empty value (78-84; `::add-mask::` at ActionCommandManager.cs:440); the docs: redaction "largely relies on finding an exact match" and "is not guaranteed" (secure-use.md:30, 40) |
| GitLab CI/CD variables, doc/ci/variables/_index.md at `af7509a` | a masked value is replaced with `[MASKED]` (line 301), and GitLab refuses to mask a value that is not "8 characters or longer" or that matches a variable's name (320-324) — the shape of rule (b), applied where the secret is defined |
| CircleCI support, "Why are words being masked with asterisks in the build log?" (2026-05-14) | masks only values "greater than 4 characters" and not `true`, `True`, `false`, `False` |
| OWASP Logging Cheat Sheet at `8df01a5` | passwords "should be removed, masked, sanitized, hashed, or encrypted" (lines 188-194); nothing on a mask that shows where it cut |
| NIST SP 800-63B-4 §3.1.1.2 (the page dated 2025-08-26) | verifiers compare "the entire password … not substrings or words that might be contained therein" against a blocklist of common, expected and "context-specific words, such as the name of the service, the username"; minimum length 15 when the password is the only factor, 8 with MFA; "SHALL NOT impose other composition rules". These bind a verifier "when processing a request to establish or change a password" — the directory, not the dashboard |
| Bland, Iyer, Levchenko, PoPETs 2023(3), 43-61 | redacting text and leaving the glyph positions "leaks significant information about the redacted text"; the attack tests candidates that reproduce the output, as §2.1 does |

No standard read covers partial-match redaction that leaks length or position in logs. The document-redaction paper is
the closest: the same leak, measured, in PDFs.

## 3. The design

### 3.1 The decision

**Refuse what Rejoin knows before the password is sent; replace whole what it can only quote afterwards.**

1. **Before any request** (`check`, after #447's refusal): a password found in `known_text` is refused with
   `422 rejoin-password-in-known-text` in fixed words. Nothing is sent, no Rejoin or login line is written, the gate is
   not touched: the reader has nothing to read back. This is rule (b), and it is where #447 already refuses.
2. **After the request** (`_whole`, in `refused()` and on D8's reason): a quoted text in which the password or any
   secret occurs, or which an earlier scrub already marked, becomes `<redacted: the text contained the credential>`.
   This is rule (a), used only on text (b) cannot see.

Why this split, from §2: (a) cannot protect a field whose whole value is the password, and a common word shows up in
several fields, each saying "it was here" (§2.3); (b) cannot know what the remote will say. The split puts each rule
where it is complete. Every scrub stays where it is; the change only decides what the scrub is handed.

### 3.2 The known text

**Every word Rejoin writes and every name it carries, casefolded, gathered from the code rather than copied.**

`known_text(cluster, settings, username, viewer)` joins two parts:

| part | where it comes from |
|---|---|
| the words (`WORDS`, built once at import) | `SAYS` (every sentence `_exchange`, `_logged_out` and `stopped_unexpectedly` write) and `READ_SAYS`; `RejoinLogin.REFUSED_ACTION` and `NEXT_TRY`; Rejoin's and the login's line names (`EVENTS`, `gsd/fleetlogin.py#EVENTS`); the field values `true`, `false`, `created`, `updated`, the marks `<redacted>` and `QUOTED_MARK`; the outcome codes (Rejoin's four and `gsd/fleetlookup.py#CODES`), `PHASES`, `AUTH_FAILED`, `FORBIDDEN`, `UNREACHABLE`, `TOKEN_PREFIX` and `DISCOVERY_PATH`; the platform's words `Basic realm="openshift"` and `https://oauth-openshift.apps.` (§2.6) |
| the names (built per press) | the account, the person who pressed (`viewer`: the route now passes it), the question (`question_words`), this cluster's Secret name and TLS mode, the lookup source's namespace, ServiceAccount and Secret, and every cluster's name and API URL (the gate's refusal can name any of them) |

The known text also includes `SAYS` rendered with the current names, both write outcomes, the gate's possible
cluster URLs, and the cleanup/evidence joins. Template braces and newlines between entries are not boundaries in
the actual answer. The random token name and remote evidence remain unknown before login (§5).

The test is `password.casefold() in known` or, for a password with surrounding spaces, the stripped password: the
scrub's raw replace keeps a password's spaces and `redact_text` strips them. A single space is refused, since it is
every gap in a sentence. The #447 check runs first, so a password inside the username keeps #447's code and words.

### 3.3 Quoted text, whole

**`_whole(text, secrets)` returns the mark when `_scrub` would change the text or an earlier scrub already marked it.**

Two call sites: a failure's `detail` in `refused()` (the login's message, D8's error, the token read's and the
write's), and D8's `reason` on `cluster-rejoin-review`. The earlier-mark rule is needed because that text usually
arrives already cut by the login's `_scrub`, D8's client or `LookupRefused.scrub`, where the span scrub finds nothing
more to replace. The mark's words are in `WORDS`, so a password inside them is refused and the mark cannot be cut. Only
Rejoin's answer and Rejoin's own lines change; the login's lines, which are fleet code, keep the context.

### 3.4 No length floor

**The refusal is about text the scrub would cut, not about how strong a password is.**

- Measured: a floor of eight broke 95 existing cases in `tests/test_cluster_rejoin.py` — 70 of
  `test_other_json_spellings_never_reach_evidence`, 20 of `test_short_escaped_password_never_reaches_evidence`, 3 of
  `test_short_password_echo_in_review_is_not_logged` and 2 of
  `test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment`. They pin that the scrub removes a short
  password's escaped forms. The prototype also broke #447's own 11 cases, because it ran before #447's check; that
  order was the prototype's mistake.
- NIST's lengths bind the verifier, the directory, when a password is set; the dashboard presents a password that
  already exists and cannot change it.
- A short password that occurs nowhere Rejoin writes leaks nothing there, so it is not refused. One that occurs in
  Rejoin's words is refused by the known text. Measured: 75 of the 95 printable ASCII characters are refused as a
  one-character password; the 20 accepted (`7`, `8`, `9`, `q`, `Q` and fifteen punctuation marks) occur in no word
  Rejoin writes. The rest is §5.

### 3.5 What the person reads

**The same shape as #447: a 422 with a code and fixed words.** The detail is
`rejoin-password-in-known-text: the password must not be a word or a name Rejoin writes, or a part of one, ignoring
case: its redaction would show where it was cut out; it was not sent`. It is one answer for every refused password,
and it repeats nothing. The dialog shows it as it shows #447's (`HTTP 422 — …`); `gsd/static/index.html` is unchanged.

### 3.6 What must not change

| must not change | held by |
|---|---|
| every existing scrub | no scrub helper changes; every text `_scrub` scrubbed is still passed through it (`_whole` calls it), and the D4 pins pass unchanged (§4) |
| the one-login budget | a refusal sends nothing and records nothing: `test_the_issues_two_passwords_are_refused_before_anything_is_sent` counts the wire, the host and the gate; `test_the_budget_over_the_system` passes unchanged |
| D4-7's per-pod memory | `CredentialGate` is untouched |
| #447's refusal | it runs first, with its code and words; `test_password_equal_to_username_is_refused_before_any_request` passes unchanged |
| every answer and line for a password that occurs nowhere | byte-identical on 15 paths (§2.5) |
| the #286 guard | `rejoin.py` names no token API (`tests/test_fleet_login.py#TestScopeIsLoginOnly` passes) |
| the fleet | `fleetlogin.py`, `fleetlookup.py`, `kube.py` and `events.py` are untouched |

## 4. Tests, before and after

**Sixteen cases in `tests/test_scrub_span.py`: the original twelve plus four rendered-phrase regressions. The original
twelve fail on `ece9298`; the four also fail on the first D6 prototype. All pass with the corrected §6 applied.**

| test | on `ece9298` |
|---|---|
| `test_the_issues_two_passwords_are_refused_before_anything_is_sent[update]`, `[a]` — the issue's two cases | the press is sent and answered 200 |
| `test_a_word_or_a_name_rejoin_writes_is_refused[…]` — `password`, `cluster-admin`, `openshift`, `root`, `credential`, a space | sent, answered 200 |
| `test_rendered_text_is_refused[…]` — `may update`, `east as`, `st refused`, `seconds; the` | sent, with readable spans in the answer |
| `test_every_word_and_name_rejoin_writes_is_refused` — presses 13 paths, then sends every word Rejoin wrote and every name as the password | lists the words main would send (`'s`, `500`, `<name>`, `API`, …) |
| `test_the_remotes_reason_holding_the_password_is_replaced_whole` | `reason="RBAC: allowed by ClusterRoleBinding '<redacted>' …"` |
| `test_a_secret_in_a_failures_evidence_replaces_the_whole_evidence[an-echo-in-the-login-500]`, `[a-word-of-the-token-reads-evidence]` | the answer ends `(… bad credentials <redacted>; …)` and `(… the <redacted>'s legacy-token cleaner …)` |

The drift test is the guard on §3.2: a sentence written outside `SAYS`, or a field value `known_text` does not hold,
fails it. Applied to a clean copy of `ece9298`, the blocks reproduce, byte for byte, the copy every measurement in this
spec was taken on (its `gsd/rejoin.py`, `gsd/api.py`, the new test file, `API.md` and SPEC_D4). On the applied copy, `tests/test_cluster_rejoin.py`, `tests/test_epic_c_composition_2.py`,
`tests/test_fleet_login.py`, `tests/test_fleet_lookup.py`, `tests/test_api_contract.py` and
`tests/test_docs_citations.py` pass unchanged. The implementer's report pastes the runs.

## 5. What is left, stated

1. **The login's own lines.** `fleet-login-failed`, `fleet-login-refused` and `fleet-logout-failed` are written by
   `FleetLogin`, shared with the fleet, through the emit helper's spans. A password that is one of their own words is
   still cut there: 13 of the 100,000 (`temp`, `carrie`, `target`, `what`, `will`, `time`, `more`, `come`, `denied`,
   `loca`, `keys`, `empty`, `still`), on a refused or failed login, a login that could not start, or a failed
   sign-out. Closing it means those messages become data `known_text` can read — the login's, D8's client's, the token
   read's and the write's — which changes four shared modules and would take rule (b) to 438 refused and 16 left
   (§2.4): a later issue.
2. **The login's token name, on a failed sign-out.** The answer names the token to delete (`sha256~…`), a random
   string, and `fleet-logout-failed` prints it in full. A password of one to three characters found in it is cut in
   the answer: 6 of the 100,000 (`7`, `8`, `9`, `Q`, `cb`, `66`).

   Pressed on the rig with §6 applied, each of the 19 in points 1 and 2 is a class of one on every path it occurs on
   (26 password-and-path pairs): the residual is real, not a model's.
3. **Phrases across substitutions and sentence joins.** The reviewed prototype accepted `may update`, `east as`,
   `st refused` and `seconds; the`, leaving readable spans. `known_text` now includes the rendered sentences and
   their cleanup/evidence joins; all four are refused before a request. The population measurements above describe
   the original prototype; none of these four test phrases is in that corpus.
4. **One bit.** A quoted text that becomes the mark tells the reader the secret occurred in it; the answer and the line
   carry the same evidence, so a press says it once. Measured by pressing, main against §6: `admins` inside D8's reason
   on a success, `grant` inside the write's refusal and `mission` inside the token read's 403 sentence were each a
   class of one on main, and leave 478, 7,277 and 26,670 candidates with §6 applied.
5. **Over-refusal.** 58 of the 100,000 are refused though the fifteen measured paths would not have cut them, for
   three reasons, measured: 21 only because the refusal compares ignoring case while the scrub does not (`Password`,
   `Admin`, single upper-case letters; #447 made the same choice, and it is what refuses seven more letters of the
   token name in point 2 — a case-sensitive compare leaves 26 there, not 19); 27 are words of text those paths did
   not write but Rejoin can (`stopped`'s sentence, `held-elsewhere`, the phases, the lookup's codes, the discovery
   path); 10 occur only in a line's name or a field under the emit helper's floor of four, where the scrub would not
   cut them.
6. **The fleet password** meets the same mechanism in the fleet's own paths (orchestrator's notes, (3)).

## 6. Implementation blocks

**Nineteen blocks, in apply order: thirteen for `gsd/rejoin.py`, one for `gsd/api.py`, the new test file, one for
`API.md`, two for SPEC_D4 (§3.1's step 5 and §3.7's note) and the CHANGELOG line.** They were cut from the diff between
`ece9298` and a copy with the design implemented, two lines of context each, so every Old text is main's own bytes.
Applied to a clean copy of `ece9298` they reproduce the implemented copy byte for byte (§4).

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
import re

from .clusterconfig.events import event, failure
from .clusterconfig.writer import WriteRefused, secret_name_for
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig, Settings, valid_bootstrap_username
from .fleetlogin import TOKEN_PREFIX, FleetLogin, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, LookupSource, read_sa_token, store
from .fleetlookup import _scrub as _fleet_scrub
from .kube import AUTH_FAILED, UNREACHABLE, ClusterClient, ClusterError
from .timeutil import now_iso

```

```python
import re

from .clusterconfig.events import PHASES, event, failure
from .clusterconfig.writer import WriteRefused, secret_name_for
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig, Settings, valid_bootstrap_username
from .fleetlogin import TOKEN_PREFIX, FleetLogin, LoginError, RetryPolicy, _without_userinfo
from .fleetlogin import DISCOVERY_PATH
from .fleetlogin import EVENTS as LOGIN_EVENTS
from .fleetlookup import CODES, CredentialGate, LookupRefused, LookupSource, read_sa_token, store
from .fleetlookup import _scrub as _fleet_scrub
from .kube import AUTH_FAILED, FORBIDDEN, UNREACHABLE, ClusterClient, ClusterError
from .timeutil import now_iso

```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}


```

```python
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}
#: What the person reads at every other step; `_exchange` fills in the names. Data, like READ_SAYS, because `check`
#: refuses before anything is sent a password found in these words or in the names they carry (#465, SPEC_D6): the
#: scrub cuts a password out of text wherever it occurs, and a span cut out of words a reader knows spells it.
SAYS = {
    "held": ("{shown} already refused this password for {username}, so it was not sent: type the right password (this "
             "pod holds a refused password back until it restarts)"),
    "held-elsewhere": "an earlier cluster",
    "unasked": "{cluster} could not be asked whether {username} may {asked} there, so nothing was read or written",
    "denied": ("{cluster} says {username} may not {asked} there, so nothing was read or written: Rejoin needs a "
               "cluster administrator of {cluster}"),
    "refused": ("{cluster} refused the password for {username}: check the username and password; it is not sent again "
                "by this pod while it is the same password"),
    "unanswered": ("the password for {username} was sent to {cluster} and no session came back; it is not sent again "
                   "by this pod while it is the same password, and a locked directory account answers HTTP 500, so "
                   "check the account before you try again"),
    "unreached": "could not reach {cluster}'s login, so the password was not sent",
    "untrusted": "; the cluster's trust must verify both the API host and the OAuth route",
    "unread": "the poller token Secret could not be read",
    "unread-written": "; nothing was written",
    "unwritten": "the token was read on {cluster} but writing {secret} here failed, so nothing was stored",
    "rejoined": ("Signed in to {cluster} as {username}, who may {asked} there; read the poller's token and {written} "
                 "{secret} here. The cluster is read again within seconds"),
    "signed-out": "; the login was signed out",
    "not-signed-out": ("; the login could NOT be signed out on {cluster}: delete {name} there (oc delete "
                       "useroauthaccesstokens <name>, as yourself)"),
    "unnamed-token": "the login's token",
    "stopped": ("Rejoin stopped unexpectedly, and nothing of the error is shown or logged: press Refresh before Rejoin "
                "again"),
}
#: Rejoin's own lines (SPEC_D4 D4-17), and the words its lines and answers carry besides the sentences: the values a
#: line's fields take and the scrub's own mark, which a later scrub of the same text can cut into.
EVENTS = ("cluster-rejoin-review", "cluster-rejoin-failed", "cluster-rejoined")
#: What a quoted text becomes when a secret occurs in it (#465): the whole field, never a span (`_whole`).
QUOTED_MARK = "<redacted: the text contained the credential>"
FIELD_WORDS = ("true", "false", "created", "updated", "<redacted>", QUOTED_MARK)
#: What the remote's platform always writes, known before any password is sent: OpenShift's OAuth server challenges with
#: the realm `openshift` (openshift/oauth-server, pkg/oauthserver/auth.go) and is served at `oauth-openshift.` on the
#: `apps.` ingress domain by default (openshift/cluster-authentication-operator, the custom route controller).
PLATFORM_WORDS = ('Basic realm="openshift"', "https://oauth-openshift.apps.")


```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python


class RejoinLogin(FleetLogin):
    """#283's login as the person who pressed Rejoin: the same wire, events and rules, in a person's words."""
```

```python


def _whole(text: str, secrets) -> str:
    """Text Rejoin quotes — the evidence of a failure, D8's reason — is known only after the password was sent, so
    `check` cannot refuse a password found in it (#465, SPEC_D6). When the password or any secret occurs in it, or an
    earlier scrub already marked it, the whole text becomes QUOTED_MARK: a span would show the reader where to cut."""
    return QUOTED_MARK if "<redacted" in text or _scrub(text, secrets) != text else text


class RejoinLogin(FleetLogin):
    """#283's login as the person who pressed Rejoin: the same wire, events and rules, in a person's words."""
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    def _fields(self) -> dict[str, str]:
        return {**super()._fields(), "rejoin_by": self.person}


```

```python
    def _fields(self) -> dict[str, str]:
        return {**super()._fields(), "rejoin_by": self.person}


#: Every fixed word Rejoin's answers and lines are written in, gathered once at import (#465, SPEC_D6); `known_text`
#: adds the names.
WORDS = (*SAYS.values(), *READ_SAYS.values(), RejoinLogin.REFUSED_ACTION, RejoinLogin.NEXT_TRY, *EVENTS, *LOGIN_EVENTS,
         *FIELD_WORDS, *PLATFORM_WORDS, REJOINED, NOT_CLUSTER_ADMIN, REVIEW_FAILED, STOPPED, *CODES, *PHASES,
         AUTH_FAILED, FORBIDDEN, UNREACHABLE, TOKEN_PREFIX, DISCOVERY_PATH)


```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python


def check(cluster: ClusterConfig, settings: Settings, username: str, password: str) -> None:
    """The refusals made before anything is sent (SPEC_D4 §3.1). Each is a `WriteRefused`; none repeats a value."""
    reason = refusal(cluster, settings)
```

```python


def known_text(cluster: ClusterConfig, settings: Settings, username: str, viewer: str = "") -> str:
    """What a reader of this Rejoin's answer and lines already knows, casefolded (#465, SPEC_D6): the words Rejoin and
    its login write — the sentences, the lines' names and field values, the scrub's marks, the platform's fixed words —
    and the names they carry: every cluster's name and API URL, the account, the person, the question, the Secrets',
    the TLS mode. Not what the remote writes after the password was sent (a reason, a body): `_whole` handles that."""
    source = LookupSource.from_settings(settings)
    mode = cluster.tls_mode
    clusters = (*settings.clusters, *settings.effective_clusters())
    names = (username, viewer, question_words(settings), secret_name_for(cluster.name), source.namespace,
             source.service_account, source.secret_name, "insecure" if mode["insecure"] else mode["ca"],
             *(c.name for c in clusters), *(c.api_url for c in clusters))
    # A placeholder is not a boundary in the rendered answer: `may {asked}` writes `may update`.
    # Render the known sentences and their actual joins before deciding what is safe to send.
    values = dict(cluster=cluster.name, username=username, asked=question_words(settings),
                  secret=secret_name_for(cluster.name), shown=SAYS["held-elsewhere"],
                  written="updated", name=SAYS["unnamed-token"])
    rendered = [text.format(**values) for text in SAYS.values()]
    rendered.extend(SAYS["held"].format(**{**values, "shown": _without_userinfo(c.api_url)})
                    for c in clusters if _without_userinfo(c.api_url))
    rendered.extend(SAYS["rejoined"].format(**{**values, "written": written})
                    for written in ("created", "updated"))
    rendered.extend(text.format(**values) + SAYS["unread-written"]
                    for text in (*READ_SAYS.values(), SAYS["unread"]))
    rendered.append(SAYS["unreached"].format(**values) + SAYS["untrusted"])
    # The token's random name is unknown until after login; this includes the fixed fallback only.
    # Known text on both sides of the cleanup/evidence joins must not become a readable cut either.
    cleanup = ("", SAYS["signed-out"], SAYS["not-signed-out"].format(**values))
    rendered = [text + suffix for text in rendered for suffix in cleanup]
    rendered.extend(text + " (" + QUOTED_MARK + ")" for text in tuple(rendered))
    return "\n".join(filter(None, (*names, *WORDS, *rendered))).casefold()


def check(cluster: ClusterConfig, settings: Settings, username: str, password: str, *, viewer: str = "") -> None:
    """The refusals made before anything is sent (SPEC_D4 §3.1). Each is a `WriteRefused`; none repeats a value."""
    reason = refusal(cluster, settings)
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
        raise WriteRefused("rejoin-password-within-username", "the password must not be the username or a part of it, "
                                                             "ignoring case and surrounding spaces; it was not sent")


```

```python
        raise WriteRefused("rejoin-password-within-username", "the password must not be the username or a part of it, "
                                                             "ignoring case and surrounding spaces; it was not sent")
    # #465: the same, for every word Rejoin writes and every name it carries. As typed and stripped: the scrub's raw
    # replace keeps the spaces a password has, and `redact_text` strips them.
    known = known_text(cluster, settings, username, viewer)
    if password.casefold() in known or (folded and folded in known):
        raise WriteRefused("rejoin-password-in-known-text", "the password must not be a word or a name Rejoin writes, "
                                                           "or a part of one, ignoring case: its redaction would show "
                                                           "where it was cut out; it was not sent")


```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    asked = question_words(settings)
    who = dict(cluster=cluster.name, by=viewer, account=username)

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence; both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        detail = _scrub(detail, secrets) if detail else None   # any length: the emit helper skips values under four
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
```

```python
    asked = question_words(settings)
    who = dict(cluster=cluster.name, by=viewer, account=username)
    names = dict(cluster=cluster.name, username=username, asked=asked, secret=secret_name_for(cluster.name))

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence; both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        detail = _whole(detail, secrets) if detail else None   # whole, at any length: a span would show where to cut
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    answered = gate.account_refusal(username, password)
    if answered is not None:
        shown = _without_userinfo(answered) or "an earlier cluster"
        return refused("login-refused", f"{shown} already refused this password for {username}, so it was not sent: "
                                        f"type the right password (this pod holds a refused password back until it "
                                        f"restarts)")
    stopped: tuple[str, str, str | None] | None = None      # D8 refused, or could not be asked
    try:
```

```python
    answered = gate.account_refusal(username, password)
    if answered is not None:
        shown = _without_userinfo(answered) or SAYS["held-elsewhere"]
        return refused("login-refused", SAYS["held"].format(shown=shown, **names))
    stopped: tuple[str, str, str | None] | None = None      # D8 refused, or could not be asked
    try:
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
                                                            secrets=secrets)
            except ClusterError as exc:
                stopped = (REVIEW_FAILED, f"{cluster.name} could not be asked whether {username} may {asked} there, "
                                          f"so nothing was read or written", f"{exc.outcome}: {exc.message}")
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_scrub(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
                                                  f"was read or written: Rejoin needs a cluster administrator of "
                                                  f"{cluster.name}", reason or None)
                else:
                    try:
```

```python
                                                            secrets=secrets)
            except ClusterError as exc:
                stopped = (REVIEW_FAILED, SAYS["unasked"].format(**names), f"{exc.outcome}: {exc.message}")
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_whole(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, SAYS["denied"].format(**names), reason or None)
                else:
                    try:
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
            gate.refuse(cluster.api_url, username, password)
            if exc.outcome == AUTH_FAILED:
                return refused("login-refused", f"{cluster.name} refused the password for {username}: check the "
                                                f"username and password; it is not sent again by this pod while it is "
                                                f"the same password", exc.message)
            return refused("login-failed", f"the password for {username} was sent to {cluster.name} and no session "
                                           f"came back; it is not sent again by this pod while it is the same "
                                           f"password, and a locked directory account answers HTTP 500, so check the "
                                           f"account before you try again", exc.message)
        hint = "; the cluster's trust must verify both the API host and the OAuth route" if exc.phase == "tls" else ""
        return refused("login-failed", f"could not reach {cluster.name}'s login, so the password was not sent{hint}",
                       exc.message, phase=exc.phase)
    except LookupRefused as exc:
        exc.scrub(secrets)
        said = READ_SAYS.get(exc.code, "the poller token Secret could not be read").format(cluster=cluster.name)
        return refused(exc.code, f"{said}; nothing was written", exc.detail)
    if stopped is not None:
        return refused(*stopped)
```

```python
            gate.refuse(cluster.api_url, username, password)
            if exc.outcome == AUTH_FAILED:
                return refused("login-refused", SAYS["refused"].format(**names), exc.message)
            return refused("login-failed", SAYS["unanswered"].format(**names), exc.message)
        hint = SAYS["untrusted"] if exc.phase == "tls" else ""
        return refused("login-failed", SAYS["unreached"].format(**names) + hint, exc.message, phase=exc.phase)
    except LookupRefused as exc:
        exc.scrub(secrets)
        said = READ_SAYS.get(exc.code, SAYS["unread"]).format(cluster=cluster.name)
        return refused(exc.code, said + SAYS["unread-written"], exc.detail)
    if stopped is not None:
        return refused(*stopped)
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    except LookupRefused as exc:
        exc.scrub(secrets)
        return refused(exc.code, f"the token was read on {cluster.name} but writing {secret_name_for(cluster.name)} "
                                 f"here failed, so nothing was stored", exc.detail)
    event(log, logging.INFO, "cluster-rejoined", **who, secret=secret_name_for(cluster.name), written=written,
          revoked="true" if login.revoked else "false", secrets=secrets)
    message = (f"Signed in to {cluster.name} as {username}, who may {asked} there; read the poller's token and "
               f"{written} {secret_name_for(cluster.name)} here. The cluster is read again within seconds"
               f"{_logged_out(login, cluster)}")
    return {"outcome": REJOINED, "message": _scrub(message, secrets), "at": at}

```

```python
    except LookupRefused as exc:
        exc.scrub(secrets)
        return refused(exc.code, SAYS["unwritten"].format(**names), exc.detail)
    event(log, logging.INFO, "cluster-rejoined", **who, secret=secret_name_for(cluster.name), written=written,
          revoked="true" if login.revoked else "false", secrets=secrets)
    message = SAYS["rejoined"].format(written=written, **names) + _logged_out(login, cluster)
    return {"outcome": REJOINED, "message": _scrub(message, secrets), "at": at}

```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
    """The answer to an error the design did not expect: fixed words, because the error's own may quote the password,
    then how the login ended when there was one. The line records only that it happened."""
    said = _scrub("Rejoin stopped unexpectedly, and nothing of the error is shown or logged: press Refresh before "
                  f"Rejoin again{cleanup}", secrets)
    failure(log, "cluster-rejoin-failed", phase="credential", outcome=STOPPED, cluster=cluster, by=viewer, action=said,
            secrets=secrets)
```

```python
    """The answer to an error the design did not expect: fixed words, because the error's own may quote the password,
    then how the login ended when there was one. The line records only that it happened."""
    said = _scrub(SAYS["stopped"] + cleanup, secrets)
    failure(log, "cluster-rejoin-failed", phase="credential", outcome=STOPPED, cluster=cluster, by=viewer, action=said,
            secrets=secrets)
```

<!-- block: local-development/gsd/rejoin.py | edit -->
```python
        return ""
    if login.revoked:
        return "; the login was signed out"
    name = login.session.token_name if login.session.token.startswith(TOKEN_PREFIX) else "the login's token"
    return (f"; the login could NOT be signed out on {cluster.name}: delete {name} there (oc delete "
            f"useroauthaccesstokens <name>, as yourself)")


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "STOPPED", "RejoinLogin", "check",
           "fleet_accounts", "question", "question_words", "refusal", "rejoin", "remote_says_cluster_admin",
           "stopped_unexpectedly"]
```

```python
        return ""
    if login.revoked:
        return SAYS["signed-out"]
    name = login.session.token_name if login.session.token.startswith(TOKEN_PREFIX) else SAYS["unnamed-token"]
    return SAYS["not-signed-out"].format(cluster=cluster.name, name=name)


__all__ = ["EVENTS", "FIELD_WORDS", "NOT_CLUSTER_ADMIN", "ONE_TRY", "PLATFORM_WORDS", "QUOTED_MARK", "READ_SAYS",
           "REJOINED", "REVIEW_FAILED", "SAYS", "STOPPED", "WORDS", "RejoinLogin", "check", "fleet_accounts",
           "known_text", "question", "question_words", "refusal", "rejoin", "remote_says_cluster_admin",
           "stopped_unexpectedly"]
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                raise HTTPException(status_code=404, detail=f"unknown cluster {name!r}")
            try:
                rejoin.check(cluster, settings, username, password)
            except WriteRefused as exc:
                raise _write_error(exc) from exc
```

```python
                raise HTTPException(status_code=404, detail=f"unknown cluster {name!r}")
            try:
                rejoin.check(cluster, settings, username, password, viewer=viewer)
            except WriteRefused as exc:
                raise _write_error(exc) from exc
```

<!-- block: local-development/tests/test_scrub_span.py | create -->
```python
"""#465 (docs/specs/SPEC_D6_scrub_span.md): the scrub cuts a password out of text wherever it occurs, so a password
found in the words Rejoin writes, or in the names they carry, left `<redacted>` spans a reader fills back in: measured
on this rig, `update` and `a` were spelled out of the answer and the lines. Rejoin now refuses such a password before
anything is sent, and a text it only quotes — a failure's evidence, D8's reason — becomes fixed words whole when a
secret occurs in it. The rig is test_cluster_rejoin's: the fake remote counts the wire, the host is in memory."""

from __future__ import annotations

import logging
import re

import httpx
import pytest

from gsd.fleetlogin import token_object_name
from gsd.fleetlookup import INVALID_SINCE_LABEL, CredentialGate
from test_cluster_rejoin import _rejoin, remote, review, rig  # noqa: F401 - remote and rig are the suite's fixtures
from test_fleet_login import TOKEN, login_302, refused_401
from test_fleet_lookup import sa_secret

#: The contract's own strings, written out rather than imported: a test that imported them would pass whatever they said.
KNOWN = ("rejoin-password-in-known-text: the password must not be a word or a name Rejoin writes, or a part of one, "
         "ignoring case: its redaction would show where it was cut out; it was not sent")
MARK = "<redacted: the text contained the credential>"
#: What the rig's lines and answers carry besides Rejoin's words: the cluster, the account, the person who pressed, the
#: question, the Secret and the cluster's API URL.
NAMES = ("east", "bob", "root", "update clusterrolebindings", "gsd-cluster-east", "https://api.east.example:6443")
CONTROL = "Zq9-control-pw-unused-3141"   # occurs in nothing Rejoin writes


def _refused_before_anything_is_sent(r, caplog, app, host, remote) -> None:
    assert r.status_code == 422, r.text
    assert remote.requests == [] and host.calls == []
    assert "<redacted" not in r.text + caplog.text
    assert not any(m.startswith(("fleet-login", "cluster-rejoin")) for m in caplog.messages)
    gate = app.state.poller._credential_gate
    assert gate._refused == {} and gate._spent == set() and app.state.poller.woke == 0


@pytest.mark.parametrize("password", ["update", "a"])
def test_the_issues_two_passwords_are_refused_before_anything_is_sent(rig, caplog, password):
    """The issue's two cases, username `bob`, cluster `east`. Before: the answer read `who may <redacted>
    clusterrolebindings` and `Signed in to e<redacted>st <redacted>s bob`, the lines `question="<redacted>
    clusterrolebindings"`, `written=<redacted>d` and `reason="RBAC: <redacted>llowed…"`: each spelled its password."""
    c, app, settings, host, remote = rig
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password=password)
    assert r.json() == {"detail": KNOWN}, "fixed words: one answer for every refused password"
    _refused_before_anything_is_sent(r, caplog, app, host, remote)


@pytest.mark.parametrize("password", [
    "password",          # the refusal sentences: `east refused the <redacted> for bob`
    "cluster-admin",     # an outcome code: `outcome=not-<redacted>`
    "openshift",         # the platform's own words: the OAuth host `oauth=https://oauth-<redacted>.apps…`, the realm
    "root",              # the person who pressed: `by=<redacted>`, `rejoin_by=<redacted>`
    "credential",        # the whole-text mark below
    " ",                 # a space: every gap in the sentence
], ids=["sentence-word", "outcome-code", "api-path", "the-person", "the-mark", "a-space"])
def test_a_word_or_a_name_rejoin_writes_is_refused(rig, caplog, password):
    c, app, settings, host, remote = rig
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password=password)
    assert r.json() == {"detail": KNOWN}
    _refused_before_anything_is_sent(r, caplog, app, host, remote)


# ── every word Rejoin writes, on every path, is refused: the list cannot drift from the sentences ─────────────────

def _paths(remote, host, local):
    """(outcome, prepare) for every way a Rejoin ends; each prepare leaves the rig ready for one press."""
    def answer(authorize=None, review_answer=None, **attrs):
        def prepare():
            remote.answers = [authorize or login_302()]
            remote.review = review_answer or review()
            for name, value in attrs.items():
                setattr(remote, name, value)
        return prepare

    def refused_write():
        answer()()
        host.refuse = True

    def unexpected():
        answer()()
        local.setattr("gsd.rejoin.remote_says_cluster_admin", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError()))

    tls = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    server_error = httpx.Response(500, text="Internal Server Error")
    return [
        ("rejoined", answer()),
        ("rejoined", answer(revoke=server_error)),                               # the login could NOT be signed out
        ("login-refused", answer(refused_401())),
        ("login-failed", answer(server_error)),
        ("login-failed", answer(discovery=lambda request: httpx.ConnectError("refused"))),    # the password not sent
        ("login-failed", answer(discovery=lambda request: tls)),                                # … with the trust hint
        ("not-cluster-admin", answer(review_answer=review(allowed=False, reason=None))),
        ("access-review-failed", answer(review_answer=server_error)),
        ("sa-token-secret-missing", answer(secret=httpx.Response(404, text="not found"))),
        ("sa-token-unreadable", answer(secret=httpx.Response(403, text="forbidden"))),
        ("sa-token-invalidated", answer(secret=httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "x"})))),
        ("lookup-write-failed", refused_write),
        ("rejoin-failed", unexpected),
    ]


def _own(message: str, lines: list[str]) -> list[str]:
    """The texts Rejoin writes itself: a success's whole answer, each failure line's `action` (the refusal's sentence
    without its quoted evidence), and each of its lines' name and plain field values."""
    out = [message] if message.startswith("Signed in to") else []
    for line in lines:
        name, _, rest = line.partition(" ")
        if name.startswith("cluster-rejoin"):
            out.append(name)
            for key, value in re.findall(r' ([a-z_]+)=("[^"]*"|\S*)', " " + rest):
                if key not in ("detail", "reason"):
                    out.append(value.strip('"'))
    return out


def test_every_word_and_name_rejoin_writes_is_refused(rig, caplog):
    """Press every way a Rejoin ends once, with a password that occurs nowhere; take every word Rejoin wrote itself
    (its answer's sentence, its lines' names and values) and every name; send each as the password. Each is refused
    before anything is sent. A sentence written outside `SAYS`, or a value `known_text` does not know, fails here."""
    c, app, settings, host, remote = rig
    defaults = {"secret": remote.secret, "revoke": remote.revoke, "discovery": remote.discovery}
    names = (*NAMES, token_object_name(TOKEN))   # the login's token object: random, and never a password
    split = re.compile("|".join(re.escape(n) for n in sorted(names, key=len, reverse=True)))
    words: set[str] = set(NAMES)
    local = pytest.MonkeyPatch()
    for outcome, prepare in _paths(remote, host, local):
        for attr, value in defaults.items():
            setattr(remote, attr, value)
        host.refuse = False
        app.state.poller._credential_gate = CredentialGate()
        prepare()
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            r = _rejoin(c, username="bob", password=CONTROL)
        local.undo()
        assert r.status_code == 200 and r.json()["outcome"] == outcome, (outcome, r.text)
        for text in _own(r.json()["message"], caplog.messages):
            for piece in split.split(text):
                words.update(w.strip("();,:.") for w in piece.split() if w.strip("();,:."))
    assert len(words) > 100, sorted(words)
    remote.requests.clear()
    sent = []
    for word in sorted(words):
        r = _rejoin(c, username="bob", password=word)
        code = r.json().get("detail", "").split(":", 1)[0] if r.status_code == 422 else None
        if code not in ("rejoin-password-in-known-text", "rejoin-password-within-username"):
            sent.append((word, r.status_code))
    assert sent == [], f"words or names Rejoin writes that it would send as a password: {sent}"
    assert remote.requests == []


# ── what Rejoin only quotes becomes fixed words whole: a span there would show where the password was cut ─────────

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


@pytest.mark.parametrize("password,denied", [
    ("may update", False), ("east as", False), ("st refused", True), ("seconds; the", False),
])
def test_rendered_text_is_refused(rig, caplog, password, denied):
    c, app, settings, host, target = rig
    if denied:
        target.answers = [refused_401()]
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, username="bob", password=password)
    assert r.status_code == 422, r.text
    assert r.json()["detail"].startswith("rejoin-password-in-known-text:")
    assert target.requests == []
    assert host.calls == []
    assert not any(m.startswith(("fleet-login", "cluster-rejoin")) for m in caplog.messages)
```

<!-- block: local-development/API.md | edit -->
```markdown
password}` as strings (fixed words: no key or value is repeated, because a key can be the password),
`rejoin-username-invalid` (outside the bootstrap grammar), `rejoin-fleet-account` (a name a fleet path logs in as,
compared stripped and casefolded), `rejoin-password-missing` and `rejoin-password-invalid` (a control character, which
RFC 7617 forbids, or an unpaired surrogate, which UTF-8 cannot carry). A success wakes discovery. One
`cluster-rejoin-review` line carries the remote's answer, then `cluster-rejoined` or `cluster-rejoin-failed`; each names
the person and the account and carries no credential.

## GroupSync CRs
```

```markdown
password}` as strings (fixed words: no key or value is repeated, because a key can be the password),
`rejoin-username-invalid` (outside the bootstrap grammar), `rejoin-fleet-account` (a name a fleet path logs in as,
compared stripped and casefolded), `rejoin-password-missing`, `rejoin-password-invalid` (a control character, which
RFC 7617 forbids, or an unpaired surrogate, which UTF-8 cannot carry), `rejoin-password-within-username` (the
password, stripped and casefolded, is the username or lies inside it; #447) and `rejoin-password-in-known-text` (the
password lies, ignoring case, inside a word Rejoin writes or a name it carries, so its redaction would show where it
was cut out; issue #465). A success wakes discovery. One `cluster-rejoin-review` line carries the remote's answer, then
`cluster-rejoined` or `cluster-rejoin-failed`; each names the person and the account and carries no credential. A
failure's evidence and the remote's reason, which Rejoin only quotes, read
`<redacted: the text contained the credential>` whole when a secret occurs in them.

## GroupSync CRs
```

<!-- block: docs/specs/SPEC_D4_cluster_rejoin.md | edit -->
```markdown
| 3 | the body is exactly `{"username": <string>, "password": <string>}` | `422` in fixed words: a key can be the password, so none is repeated | no |
| 4 | the name is a live cluster | `404` | no |
| 5 | `gsd/rejoin.py#check`: the row is rejoinable (§3.2); the username fits the shared grammar; it is not a fleet account; the password is present, with no control character and no unpaired surrogate, and, stripped, is neither the username nor a part of it, ignoring case | `409 not-rejoinable`, or `422 rejoin-username-invalid`, `rejoin-fleet-account`, `rejoin-password-missing`, `rejoin-password-invalid`, `rejoin-password-within-username` | no |
| 6 | this process runs a poller, whose credential gate Rejoin uses | `409` | no |
| 7 | no other Rejoin is running in this process | `409`, never queued | no |
```

```markdown
| 3 | the body is exactly `{"username": <string>, "password": <string>}` | `422` in fixed words: a key can be the password, so none is repeated | no |
| 4 | the name is a live cluster | `404` | no |
| 5 | `gsd/rejoin.py#check`: the row is rejoinable (§3.2); the username fits the shared grammar; it is not a fleet account; the password is present, with no control character and no unpaired surrogate, and, stripped, is neither the username nor a part of it, ignoring case, nor inside a word Rejoin writes or a name it carries (#465, SPEC_D6) | `409 not-rejoinable`, or `422 rejoin-username-invalid`, `rejoin-fleet-account`, `rejoin-password-missing`, `rejoin-password-invalid`, `rejoin-password-within-username`, `rejoin-password-in-known-text` | no |
| 6 | this process runs a poller, whose credential gate Rejoin uses | `409` | no |
| 7 | no other Rejoin is running in this process | `409`, never queued | no |
```

<!-- block: docs/specs/SPEC_D4_cluster_rejoin.md | edit -->
```markdown
test then looks for them in the answer, every log line at DEBUG, every stored Secret, the gate, the findings and the
whole database, and on the wire outside the one authorize's `Authorization` header.

## 4. The decisions
```

```markdown
test then looks for them in the answer, every log line at DEBUG, every stored Secret, the gate, the findings and the
whole database, and on the wire outside the one authorize's `Authorization` header.

**A password inside words the reader already knows (#465, SPEC_D6).** The scrub cuts a password out wherever it occurs,
so a password that was part of the answer's own words or names left spans that spelled it:
`update` in `who may <redacted> clusterrolebindings`, and `a` in `Signed in to e<redacted>st <redacted>s bob`.
`gsd/rejoin.py#check` now refuses such a password before anything is sent, against `gsd/rejoin.py#known_text`: every
word Rejoin writes (its sentences, its lines' names and values, the marks) and every name they carry. A text Rejoin
only quotes, which exists only after the password was sent (a failure's evidence, D8's reason), becomes
`<redacted: the text contained the credential>` whole when a secret occurs in it (`gsd/rejoin.py#_whole`). Every
spelling above stays scrubbed. The login's own lines, shared with the fleet, keep the emit helper's spans (SPEC_D6 §5).

## 4. The decisions
```

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **Rejoin refuses a password found in the words it writes or the names it carries, and quotes evidence that holds a
  secret in fixed words (#465, Epic D #384, `docs/specs/SPEC_D6_scrub_span.md`).** The scrub cut a password out of text
  wherever it occurred, so a password that was part of the answer's words or names (`update`, or `a` in `east`) left
  `<redacted>` spans that spelled it. The input check now answers `422 rejoin-password-in-known-text` in fixed words
  before any request, for a password inside a word Rejoin writes or a name it carries (the clusters, the account, the
  person, the question, the Secrets), ignoring case. A failure's evidence and D8's reason, which Rejoin only quotes,
  read `<redacted: the text contained the credential>` whole when a secret occurs in them. Every existing scrub, the
  request budget, the per-pod credential gate and #447's refusal are unchanged.
```
