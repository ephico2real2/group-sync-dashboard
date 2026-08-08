"""Parse oauth-server logs into login attempts.

PURE FUNCTIONS, no I/O and no cluster. The reader that fetches logs lives elsewhere; everything here
takes text and returns records, so every rule below is testable against the real lines that produced it.

WHAT THIS READS. The oauth-server writes a line per login attempt naming the account that made it, but
only at `spec.logLevel: Debug` on `authentications.operator.openshift.io/cluster` — the authentication
OPERATOR CR, not the OAuth CR. At the default verbosity the lines do not exist, so capture is inert
until somebody enables it. See docs/LOGIN_CAPTURE_QUICKCHECK.md.

EVERY USERNAME IS CAPTURED, successful or not. There is no allowlist and there must not be one: a
username that appears here and belongs to NO synced group is the most interesting row this produces —
either somebody whose access was removed and is still trying, or an account nobody governs. Filtering
against known members would drop exactly those.

── THE GRAMMAR, MEASURED ─────────────────────────────────────────────────────────────────────────────

Five cases run on a live cluster with two identity providers (`developer` = HTPasswd, `ldap-local` =
LDAP). One attempt writes SEVERAL lines across two source files, so a line is not an attempt:

  LDAP success        basicauth.go:48 failed "developer"  (htpasswd tried first and rejects)
                      ldap.go:131     searching for (filter)
                      ldap.go:148     found dn="uid=..." for (filter)
                      basicauth.go:51 SUCCEEDED "ldap-local"

  LDAP bad password   basicauth.go:48 failed "developer"
                      ldap.go:148     found dn="uid=jane.smith,..."
                      ldap.go:152     error binding password for "<dn>": LDAP Result Code 49
                                      "Invalid Credentials"
                      basicauth.go:48 failed "ldap-local"

  LDAP rejected       basicauth.go:48 failed "developer"
                      ldap.go:139     no entries matching (filter)
                      basicauth.go:48 failed "ldap-local"

  unknown user        IDENTICAL to LDAP rejected — see OUTCOME_REJECTED below

  HTPasswd success    basicauth.go:51 SUCCEEDED "developer"   — and nothing else

THE BROWSER IS A SECOND CODE PATH, and it says the same things one word differently. The four cases
above are `oc login` (HTTP basic auth -> basicauth.go). The console's HTML form is served by
login.go, which omits the word `login` from the phrase and, because the reader picks ONE provider,
writes no chain of failures ahead of the deciding one:

  browser HTPasswd    login.go:191    SUCCEEDED "developer"    — no `login` in the phrase
  browser HTPasswd    login.go:183    failed "testuser"        — a REAL failure, not chain noise,
                                                                 and HTPasswd logs no cause at all
  browser LDAP        ldap.go:131     searching for (filter)   — the attempt STARTS here: no
                      ldap.go:139     no entries matching      verdict has named anybody yet
                      login.go:183    failed "bob.wilson"

Measured on the reference cluster: all three of those browser lines can share ONE kubelet timestamp,
because they land in the same read chunk. The correlation window absorbs that.

So: a `failed` line is NOT a failed login (every provider tried before the matching one logs one, which
means a SUCCESSFUL LDAP login contains `failed for login "john.doe"`), and whether that noise exists is
provider-ORDER dependent — an HTPasswd login has none. The outcome is a property of the GROUP of lines
for one username within one attempt window, never of a single line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# What a parsed attempt concluded. Deliberately few, and each one is a distinction the log can actually
# support — see OUTCOME_REJECTED for the one it cannot.
OUTCOME_SUCCESS = "success"
OUTCOME_BAD_PASSWORD = "bad_password"
OUTCOME_REJECTED = "rejected"
"""Not found OR not permitted, and the log cannot tell them apart.

The identity provider's search filter carries the login-gate group, so a real person who is not in that
group and a username that does not exist produce the same `no entries matching (<filter>)` line. Telling
them apart would need a second directory search WITHOUT the gate clause, which is an LDAP read this
application does not have and should not acquire. One bucket, honestly labelled, is better than a guess:
both are still captured against the username that was attempted.
"""
# Causes that only a directory can distinguish, and only some directories report. Each is a DIFFERENT
# operational action — reset a password, unlock an account, wait for a window — so collapsing them into
# "failed" would throw away the only part of the row that tells somebody what to do.
OUTCOME_PASSWORD_EXPIRED = "password_expired"
OUTCOME_MUST_CHANGE_PASSWORD = "must_change_password"
OUTCOME_ACCOUNT_LOCKED = "account_locked"
OUTCOME_ACCOUNT_DISABLED = "account_disabled"
OUTCOME_ACCOUNT_EXPIRED = "account_expired"
OUTCOME_LOGON_NOT_PERMITTED = "logon_not_permitted"

OUTCOME_FAILED = "failed"
"""A failure the log gives no cause for.

Usually because the provider writes none: on HTPasswd the server logs a verdict and nothing else, so
a wrong password and a username that does not exist are identical to it. That is the NORMAL shape for
a local account, not a gap in this parser — 3 of the 12 attempts measured on the reference cluster
arrive this way, all of them browser logins against `developer`.

Kept as a distinct outcome rather than folded into `rejected`, because those two would then be
indistinguishable in the data as well as in the log. It also stays the place a genuinely unrecognised
cause would surface, which is a signal that the grammar has grown a case worth adding.
"""

# The kubelet's RFC3339 prefix, present because the reader passes `?timestamps=true`. THIS is the
# timestamp to keep. klog's own stamp on the same line (`I0807 16:15:27.435262`) carries no year and no
# timezone, so it cannot be resolved to an instant without guessing both.
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s")

# THE VERDICT LINE COMES IN TWO GRAMMARS, and the difference is one word. Measured on the live
# cluster, all four shapes the oauth-server actually emits:
#
#   basicauth.go:48]  Login with provider "developer" failed for login "jane.smith"
#   basicauth.go:51]  Login with provider "ldap-local" succeeded for login "jane.smith"
#   login.go:183]     Login with provider "developer" failed for "developer"
#   login.go:191]     Login with provider "developer" succeeded for "developer": &groupmapper...
#
# basicauth.go serves the CLI (`oc login -u -p`, HTTP basic auth) and says `for login "<user>"`.
# login.go serves the HTML FORM — the console, which is how people actually sign in — and says
# `for "<user>"` with no `login`. So requiring the word dropped every browser login on the cluster
# while capturing every CLI one, and the failure was silent: the tab simply showed fewer rows than
# had happened. Found by signing in through the console and finding nothing recorded; counted in the
# pod's whole log at the time, 29 CLI verdicts captured and 3 browser verdicts missed.
#
# `(?:login )?` rather than two patterns: it is one message with an optional word, and two regexes
# would be two places to keep in step.
#
# Anchored on the phrase rather than the file:line, because those line numbers move between
# OpenShift releases while the message has been stable — and anchored to the START of the klog
# message (the `]` that closes the header, then whitespace) because the phrase alone also matched
# itself QUOTED INSIDE another message: a line relaying text that contains the sentence produced a
# login attempt for somebody who never logged in. The oauth-server writes its verdicts as the
# message's first words; relayed copies sit mid-message. A relayed copy of a WHOLE klog line,
# header included, would still match — only a request id could reject that, and the log has none.
#
# The correlation below needs no change for the new shape — it keys on username and window, not on
# provider or call site. A browser login picks ONE provider (`idp=developer`), so there is no
# provider chain and a lone `failed` is a real failure rather than the ordinary CLI noise; retries
# arrive seconds apart, well outside ATTEMPT_WINDOW, so fail-fail-succeed stays three attempts.
_VERDICT = re.compile(
    r'\]\s+Login with provider "(?P<provider>[^"]*)" '
    r'(?P<verdict>succeeded|failed) for (?:login )?"(?P<user>[^"]*)"'
)

# ── WHY code 49 ALONE IS NOT THE ANSWER ───────────────────────────────────────────────────────────
# go-ldap formats bind errors as `LDAP Result Code %d %q: %s`, and that last field is the SERVER's
# diagnostic message. Measured on this cluster's OpenLDAP:
#
#   ldap.go:152] error binding password for "uid=jane.smith,...": LDAP Result Code 49
#                "Invalid Credentials":
#                                       ^ empty — OpenLDAP sends no diagnostic
#
# Active Directory fills that slot, and it is where the real cause lives:
#
#   ... LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9,
#       comment: AcceptSecurityContext error, data 532, v4563
#                                                    ^^^ THE SUB-CODE
#
# So on AD every one of these arrives as a bare 49 — expired password, locked account, disabled
# account, all indistinguishable — unless the hex after `data ` is read. That is the "expired
# password" case, and without this map it would be recorded as a wrong password, which sends somebody
# to reset a credential that is already correct.
#
# Sub-codes per the AD convention. Only the ones that mean something operationally different are
# mapped. An UNMAPPED sub-code becomes `failed`, not `bad_password` — see _classify_bind, which is
# where that decision lives and why. (This comment used to claim `bad_password`, contradicting the
# code eleven lines below it; the code is right, and a test now pins the behaviour.)
_AD_SUBCODE = {
    "525": OUTCOME_REJECTED,                 # user not found — same bucket as our no-entries case
    "52e": OUTCOME_BAD_PASSWORD,             # invalid credentials, i.e. genuinely the wrong password
    "530": OUTCOME_LOGON_NOT_PERMITTED,      # not permitted at this time
    "531": OUTCOME_LOGON_NOT_PERMITTED,      # not permitted at this workstation
    "532": OUTCOME_PASSWORD_EXPIRED,         # password expired
    "533": OUTCOME_ACCOUNT_DISABLED,         # account disabled
    "701": OUTCOME_ACCOUNT_EXPIRED,          # account expired
    "773": OUTCOME_MUST_CHANGE_PASSWORD,     # must reset password at next logon
    "775": OUTCOME_ACCOUNT_LOCKED,           # account locked out
}
_AD_DATA = re.compile(r"\bdata ([0-9a-fA-F]{3,4})\b")

# Result codes other than 49 that a bind can fail with, where the code alone is the cause. OpenLDAP's
# ppolicy overlay refuses an expired password with 53 (unwillingToPerform) rather than 49, which is why
# 49 cannot be treated as "all password failures".
_RESULT_CODE = {
    49: OUTCOME_BAD_PASSWORD,                # refined by the AD sub-code above when one is present
    50: OUTCOME_LOGON_NOT_PERMITTED,         # insufficient access rights
    53: OUTCOME_PASSWORD_EXPIRED,            # unwillingToPerform — OpenLDAP ppolicy expiry/lockout
    19: OUTCOME_MUST_CHANGE_PASSWORD,        # constraintViolation — password must be changed
}

# The two ldap.go lines that carry a CAUSE. Everything else ldap.go logs is progress.
_NO_ENTRIES = re.compile(r"no entries matching ")
_BIND_ERROR = re.compile(
    r"error binding password for \"(?P<dn>[^\"]*)\".*?"
    r"LDAP Result Code (?P<code>\d+) \"(?P<text>[^\"]*)\":(?P<diagnostic>.*)$"
)

# How long one attempt's lines may span. Measured at ~30-125ms per attempt across the five cases; a
# second is three orders of magnitude of headroom and still far below the gap between two humans logging
# in as the same account, which is what this must not merge.
ATTEMPT_WINDOW = timedelta(seconds=1)


@dataclass
class LoginAttempt:
    """One login attempt by one account: what happened, when, and how sure we are of the cause."""

    user_name: str
    outcome: str
    at: datetime
    """UTC, from the kubelet prefix. Stored as UTC and rendered in the configured zone at display
    time — the same rule the rest of this application follows, so one row cannot disagree with another
    because the container's TZ changed between them."""
    provider: str | None = None
    """The identity provider that DECIDED the outcome — the one that succeeded, or the last to fail.
    This is what separates a directory identity (`ldap-local`) from a break-glass account
    (`developer`, `kubeadmin` on HTPasswd), which matters because the latter are not people to govern."""
    ldap_result_code: int | None = None
    """From `LDAP Result Code <n>`; 49 is "Invalid Credentials". Only the bad-password path emits one."""
    detail: str | None = None
    """A short, NON-SENSITIVE note. Never the raw line: ldap.go embeds the full bind filter and the
    user's DN, which disclose the gate group and the directory's layout — more sensitive than the
    username this row is already keyed on."""


def _classify_bind(code: int, diagnostic: str) -> str:
    """The outcome of a failed bind, from the result code REFINED BY the diagnostic message.

    The sub-code wins where there is one: on Active Directory every cause arrives as a bare 49, so
    reading the code alone would label an expired password as a wrong password — and send somebody to
    reset a credential that is already correct.
    """
    sub = _AD_DATA.search(diagnostic or "")
    if sub:
        mapped = _AD_SUBCODE.get(sub.group(1).lower())
        if mapped:
            return mapped
        # A sub-code we have not mapped is NOT a wrong password. Recording it as `failed` keeps the
        # code in `detail` so the gap is visible instead of silently mislabelled.
        return OUTCOME_FAILED
    return _RESULT_CODE.get(code, OUTCOME_FAILED)


@dataclass
class _Pending:
    """Lines seen for one username, not yet concluded."""

    first_at: datetime
    last_at: datetime
    named_at: datetime
    """The instant of the first line that NAMED this user, which cannot move.

    `first_at` can be pulled BACK onto an adopted cause, and that is right for a failure — the attempt
    began when the directory refused it. It is wrong for a success, whose cause was never its own: see
    conclude(), which stamps a success from here instead."""
    provider: str | None = None
    succeeded: bool = False
    saw_no_entries: bool = False
    bind_code: int | None = None
    bind_diagnostic: str = ""
    """The server's diagnostic message after the result code. Empty on OpenLDAP; on Active Directory it
    carries `data <hex>`, which is the only place the real cause appears."""
    failures: list[str] = field(default_factory=list)


def parse_timestamp(line: str) -> datetime | None:
    """The kubelet RFC3339 prefix as an aware UTC datetime, or None if the line has none."""
    m = _TS.match(line)
    if not m:
        return None
    # fromisoformat handles the fractional seconds; the trailing Z needs the explicit swap on
    # Python < 3.11 and is harmless after.
    return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))


# The DN the directory search RESOLVED for one login — `found dn="<dn>" for (<filter>)` — logged
# between `searching` and the bind. Progress, not a cause, but it is the ONLY line that ties a bind
# DN back to the login that produced it: the filter it quotes embeds the typed login on every
# directory, while the DN itself does so only on directories that happen to name entries by their
# login attribute. OpenLDAP here writes `uid=jane.smith,...`; Active Directory writes
# `CN=Jane Smith,...` for a login of `jsmith`, and without this line an AD bind error could not be
# attributed to anybody by its own text.
_FOUND = re.compile(r'found dn="(?P<dn>[^"]*)" for ')


def _cause_mentions_user(text: str, user: str) -> bool:
    """Whether an `attribute=value` assertion in this cause text names exactly this login.

    The assertion forms are what the cause grammars actually carry: a bind error quotes the entry's
    DN, `no entries matching` quotes the search filter (whose last clause embeds the typed login on
    every directory), and a `found dn=` line quotes both. EXACT boundaries, not a substring test —
    `uid=bob` must not be credited to `bobby` — which is the wrong-person bug this check exists to
    prevent. Correlation only: nothing this reads is ever persisted (see _detail).
    """
    value = re.escape(user)
    return re.search(
        rf'(?i)["(,]\s*[a-z0-9.-]+\s*=\s*{value}\s*(?:[,)"]|$)', text
    ) is not None


def parse(lines: list[str] | str) -> list[LoginAttempt]:
    """Every login attempt in these lines, oldest first.

    Correlates by username within ATTEMPT_WINDOW: the provider-order noise means one attempt spans
    several lines, and a `failed` for the same person can be part of a SUCCESS. An attempt is concluded
    when a verdict arrives for a provider after the deciding one, when the window expires, or at the end
    of the input.

    CAUSE LINES NAME NO USER, so attribution is by evidence with a narrow adjacency fallback, never by
    recency between two people: under interleaving, "the most recent attempt" assigned one person's
    directory diagnosis to another, and a false cause is worse than the provider's honest no-reason
    result. The evidence is the cause's own text plus the `found dn=` line that resolved its bind DN —
    the latter because an Active Directory DN (`CN=Jane Smith,...`) never repeats the login (`jsmith`),
    and requiring the cause itself to name the user would silently discard every AD cause.

    Lines with no kubelet timestamp are skipped rather than guessed at — a record whose instant is
    invented is worse than one that is absent.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()

    pending: dict[str, _Pending] = {}
    out: list[LoginAttempt] = []
    # A cause can arrive BEFORE any line names its user, and on a cluster whose only identity provider
    # is LDAP it always does — the attempt starts at `ldap.go:131 searching`, so nothing has created a
    # pending entry yet. That is the ordinary production shape, not an edge case: this cluster only
    # gets a username first because htpasswd is tried before ldap and logs a failure. Dropping these
    # would lose every cause on a single-provider cluster, including expired passwords. A LIST, not a
    # slot: an identified orphan waits for the verdict that names its person, so an interleaved
    # stranger's verdict must be able to pass it by without destroying it.
    orphans: list[dict] = []
    # Recent `found dn=` lines by DN, kept one window: the bind error that follows quotes the DN, and
    # this is what lets it be attributed on a directory whose DNs do not contain the login. A LIST
    # per DN, not a slot: two logins can resolve the SAME entry inside one window (sAMAccountName and
    # userPrincipalName both name it on AD), and a slot silently rewrote the first login's tie to the
    # DN with the second's — every bind error for that DN then read as the second person's.
    found: dict[str, list[dict]] = {}

    def conclude(user: str) -> None:
        p = pending.pop(user, None)
        if p is None:
            return
        if p.succeeded:
            outcome = OUTCOME_SUCCESS
        elif p.bind_code is not None:
            outcome = _classify_bind(p.bind_code, p.bind_diagnostic)
        elif p.saw_no_entries:
            outcome = OUTCOME_REJECTED
        elif p.failures:
            outcome = OUTCOME_FAILED
        else:
            # Progress lines only, no verdict — nothing happened worth recording.
            return
        # A BIND FAILURE CANNOT EXPLAIN A LOGIN THAT SUCCEEDED. `adopt` now refuses to hand an
        # unidentified cause to a succeeding verdict, so the foreign-cause route is closed where it
        # starts; this remains as the second line of defence, because a cause can also reach a pending
        # by NAMING it and then be overtaken by a success in the same window — the multi-directory
        # provider chain does exactly that, and its bind code belongs to the IdP that rejected her,
        # not to the one that let her in. Measured before either guard: `jane.smith / success` carrying
        # `ldap_result_code=49, detail="LDAP result code 49"`, three false claims on the row a reader
        # trusts most, about somebody who typed the right password. The stamp comes from the line that
        # named her rather than from a cause, so the same success read with and without that cause in
        # window is one row and not two — `at` is in the dedup key.
        succeeded = outcome == OUTCOME_SUCCESS
        out.append(LoginAttempt(
            user_name=user,
            outcome=outcome,
            at=p.named_at if succeeded else p.first_at,
            provider=p.provider,
            ldap_result_code=None if succeeded else p.bind_code,
            detail=None if succeeded else _detail(p, outcome),
        ))

    def adopt(p: _Pending, user: str, ts: datetime, succeeded: bool) -> None:
        """Give a fresh pending attempt the orphan cause that belongs to it, if one is waiting.

        An IDENTIFIED orphan (its evidence names a login) is taken only by that login's verdict —
        adopting by arrival order is how one person's diagnosis reached another. An UNIDENTIFIED
        orphan (a bind whose `found dn=` fell outside this read, so nothing ties its DN to a login)
        goes to the first verdict inside the window ONLY WHEN IT IS ALONE: refusing the lone one
        would discard every cause on a directory whose DNs do not carry the login, which is a
        systematic loss, and adjacency to a single cause is only wrong when a stranger's verdict
        beats the owner's to it. With TWO unidentified causes waiting, arrival order is the only
        tiebreak left, and it is exactly wrong whenever the directory answers out of order —
        measured as two strangers' bind codes swapped, an expired password recorded as somebody
        else's wrong one. Two waiting causes with no evidence have no honest owner; both verdicts
        degrade to the provider's own result, which is true.

        AND NEVER INTO A SUCCESS, for the unidentified case. The verdict IS known here, because the
        pending is created by the verdict line itself. A bind failure cannot explain a login that
        succeeded, and conclude() suppresses whatever a success adopted, so taking the orphan would
        have exactly one effect: it is destroyed, and the failure it genuinely belonged to concludes
        with no reason. Passed by, it is still in the list when its owner's verdict arrives inside the
        window. The identified path needs no such guard — it already refuses every verdict its own
        evidence does not name, and a cause that names the person who succeeded is hers.
        """
        def take(i: int) -> None:
            o = orphans.pop(i)
            p.first_at = o["at"]
            p.saw_no_entries = o["no_entries"]
            p.bind_code = o["code"]
            p.bind_diagnostic = o["diagnostic"]

        in_window = [(i, o) for i, o in enumerate(orphans)
                     if timedelta(0) <= ts - o["at"] <= ATTEMPT_WINDOW]
        # Evidence outranks adjacency: a cause that NAMES this login wins even when an
        # unidentified one arrived first.
        for i, o in in_window:
            if o["identified"] and _cause_mentions_user(o["evidence"], user):
                take(i)
                return
        unidentified = [i for i, o in in_window if not o["identified"]]
        if len(unidentified) == 1 and not succeeded:
            take(unidentified[0])

    for raw in lines:
        ts = parse_timestamp(raw)
        if ts is None:
            continue

        # Expire anything that has gone QUIET for a window, so a long-running read does not merge two
        # attempts by the same person minutes apart — and so stale correlation state cannot leak
        # forward. Quiet since the LAST line, not old since the first: two attempts are separated by
        # silence, while one slow attempt is separated by nothing — a provider chain whose directory
        # answers slowly can stretch a single login past any fixed span, and expiring it mid-flight
        # concluded the chain noise as its own `failed` row beside the real outcome.
        for user in [u for u, p in pending.items() if ts - p.last_at > ATTEMPT_WINDOW]:
            conclude(user)
        orphans[:] = [o for o in orphans if ts - o["at"] <= ATTEMPT_WINDOW]
        for dn in list(found):
            found[dn] = [f for f in found[dn] if ts - f["at"] <= ATTEMPT_WINDOW]
            if not found[dn]:
                del found[dn]

        v = _VERDICT.search(raw)
        if v:
            user = v.group("user")
            provider = v.group("provider")
            p = pending.get(user)
            if p is None:
                p = pending[user] = _Pending(first_at=ts, last_at=ts, named_at=ts)
                adopt(p, user, ts, succeeded=v.group("verdict") == "succeeded")
            p.last_at = ts
            if v.group("verdict") == "succeeded":
                p.succeeded = True
                p.provider = provider
                conclude(user)          # a success ends the attempt; nothing after it can change it
            else:
                p.failures.append(provider)
                # The provider that decided a FAILURE is the last one to reject, so this is overwritten
                # deliberately as later providers are tried.
                p.provider = provider
            continue

        f = _FOUND.search(raw)
        if f:
            found.setdefault(f.group("dn"), []).append({"at": ts, "raw": raw})
            continue

        no_entries = bool(_NO_ENTRIES.search(raw))
        b = None if no_entries else _BIND_ERROR.search(raw)
        if not no_entries and b is None:
            continue

        # What this cause can prove about WHO it belongs to. `no entries matching` quotes the search
        # filter, which embeds the typed login on every directory. A bind error only quotes the DN, so
        # it is identifying evidence only together with the `found dn=` line that resolved it — and
        # only when that line is UNIQUE: two logins resolving this DN inside one window mean the bind
        # errors that follow cannot be told apart by their own text, and attributing either is a coin
        # flip between named humans. Dropped, the same trade as everywhere else here.
        evidence = raw
        identified = no_entries
        if b is not None:
            ctxs = found.get(b.group("dn"), [])
            if len(ctxs) > 1:
                continue
            if ctxs:
                evidence = f'{raw} {ctxs[0]["raw"]}'
                identified = True

        mentioned = [u for u in pending if _cause_mentions_user(evidence, u)]
        if len(mentioned) == 1:
            target = mentioned[0]
        elif not mentioned and not identified and len(pending) == 1:
            # A bind whose found line fell outside this read window: adjacency is the only evidence
            # left, and with exactly one attempt in flight it is sound.
            target = next(iter(pending))
        else:
            target = None

        if target is not None:
            if no_entries:
                pending[target].saw_no_entries = True
            else:
                pending[target].bind_code = int(b.group("code"))
                pending[target].bind_diagnostic = b.group("diagnostic") or ""
            pending[target].last_at = ts
        elif len(mentioned) > 1:
            # One cause naming two in-flight logins has no honest owner. Dropping it degrades both
            # to the provider's own verdict, which is true; guessing would make one of them false.
            pass
        elif identified or not pending:
            # Held for the verdict that names this person — see `orphans` above.
            orphans.append({
                "at": ts,
                "evidence": evidence,
                "identified": identified,
                "no_entries": no_entries,
                "code": None if b is None else int(b.group("code")),
                "diagnostic": "" if b is None else (b.group("diagnostic") or ""),
            })
        # An unidentified cause with SEVERAL people in flight is dropped: any attachment would be a
        # guess between named humans, and the guess is exactly the defect this branch replaced.

    for user in list(pending):
        conclude(user)

    out.sort(key=lambda a: (a.at, a.user_name))
    return out


def _detail(p: _Pending, outcome: str) -> str | None:
    """A short, non-sensitive note — the codes only, never the raw line.

    ldap.go embeds the full bind filter and the user's DN, which disclose the gate group and the
    directory's layout. Those are more sensitive than the username this row is already keyed on, so
    nothing from the line itself is carried through.
    """
    if p.bind_code is None:
        # "reported no reason", not "unrecognised failure" — the distinction matters to whoever reads
        # it. On an HTPasswd provider this is the NORMAL shape, not a gap in our parsing: the server
        # logs a verdict and nothing else, so a wrong password and a username that does not exist are
        # identical to it. Saying "unrecognised" invited the reader to treat their own browser login as
        # a parser bug. Measured: 3 of the 12 attempts on the reference cluster arrive this way.
        return (None if outcome != OUTCOME_FAILED
                else f"provider {p.provider!r} reported no reason")
    sub = _AD_DATA.search(p.bind_diagnostic or "")
    if sub:
        return f"LDAP result code {p.bind_code}, sub-code {sub.group(1).lower()}"
    return f"LDAP result code {p.bind_code}"


def is_break_glass(attempt: LoginAttempt, htpasswd_providers: frozenset[str]) -> bool:
    """Whether this attempt is a local break-glass account rather than a directory identity.

    Not filtered out at parse time — the caller decides, because "who used kubeadmin, and when" is a
    governance question in its own right even though those accounts are not people to offboard.
    """
    return attempt.provider in htpasswd_providers
