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
"""A failure whose cause this parser does not recognise.

Kept as a distinct outcome rather than folded into `rejected`, because those two would then be
indistinguishable in the data as well as in the log — and an unrecognised cause is a signal that the
grammar has grown a case worth adding, not that the login was merely refused.
"""

# The kubelet's RFC3339 prefix, present because the reader passes `?timestamps=true`. THIS is the
# timestamp to keep. klog's own stamp on the same line (`I0807 16:15:27.435262`) carries no year and no
# timezone, so it cannot be resolved to an instant without guessing both.
_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)\s")

# `Login with provider "<provider>" (succeeded|failed) for login "<user>"`. Anchored on the whole phrase
# rather than the file:line, because basicauth.go's line numbers move between OpenShift releases while
# the message has been stable.
_VERDICT = re.compile(
    r'Login with provider "(?P<provider>[^"]*)" (?P<verdict>succeeded|failed) for login "(?P<user>[^"]*)"'
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
# mapped; anything else stays `bad_password`, which is what 52e actually is.
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


def parse(lines: list[str] | str) -> list[LoginAttempt]:
    """Every login attempt in these lines, oldest first.

    Correlates by username within ATTEMPT_WINDOW: the provider-order noise means one attempt spans
    several lines, and a `failed` for the same person can be part of a SUCCESS. An attempt is concluded
    when a verdict arrives for a provider after the deciding one, when the window expires, or at the end
    of the input.

    Lines with no kubelet timestamp are skipped rather than guessed at — a record whose instant is
    invented is worse than one that is absent.
    """
    if isinstance(lines, str):
        lines = lines.splitlines()

    pending: dict[str, _Pending] = {}
    out: list[LoginAttempt] = []
    # A cause line names NO user, and on a cluster whose only identity provider is LDAP it arrives
    # BEFORE any verdict — the attempt starts with `ldap.go:131 searching`, so nothing has created a
    # pending entry yet. That is the ordinary production shape, not an edge case: this cluster only
    # gets a username first because htpasswd is tried before ldap and logs a failure. Dropping these
    # would lose every cause on a single-provider cluster, including expired passwords.
    orphan: dict | None = None

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
        out.append(LoginAttempt(
            user_name=user,
            outcome=outcome,
            at=p.first_at,
            provider=p.provider,
            ldap_result_code=p.bind_code,
            detail=_detail(p, outcome),
        ))

    for raw in lines:
        ts = parse_timestamp(raw)
        if ts is None:
            continue

        # Expire anything whose window has passed, so a long-running read does not merge two attempts
        # by the same person minutes apart.
        for user in [u for u, p in pending.items() if ts - p.first_at > ATTEMPT_WINDOW]:
            conclude(user)

        v = _VERDICT.search(raw)
        if v:
            user = v.group("user")
            provider = v.group("provider")
            p = pending.get(user)
            if p is None:
                p = pending[user] = _Pending(first_at=ts, last_at=ts)
                # Adopt a cause seen just before this verdict — same attempt, and the verdict is the
                # first line that names who it was about. Windowed, so an unrelated earlier cause
                # cannot attach to a later person.
                if orphan is not None and ts - orphan["at"] <= ATTEMPT_WINDOW:
                    p.first_at = orphan["at"]
                    p.saw_no_entries = orphan["no_entries"]
                    p.bind_code = orphan["code"]
                    p.bind_diagnostic = orphan["diagnostic"]
                orphan = None
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

        # Cause lines carry no username, so they attach to the attempt in flight. With one oauth pod
        # serving one request at a time per connection this is the same attempt; where two interleave,
        # the cause attaches to the most recent unconcluded username, which is the closest the log
        # allows — it names no user on these lines at all.
        no_entries = bool(_NO_ENTRIES.search(raw))
        b = None if no_entries else _BIND_ERROR.search(raw)
        if not no_entries and b is None:
            continue

        if pending:
            newest = max(pending, key=lambda u: pending[u].last_at)
            if no_entries:
                pending[newest].saw_no_entries = True
            else:
                pending[newest].bind_code = int(b.group("code"))
                pending[newest].bind_diagnostic = b.group("diagnostic") or ""
            pending[newest].last_at = ts
        else:
            # Held for the verdict that follows — see `orphan` above.
            orphan = {
                "at": ts,
                "no_entries": no_entries,
                "code": None if b is None else int(b.group("code")),
                "diagnostic": "" if b is None else (b.group("diagnostic") or ""),
            }

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
        return None if outcome != OUTCOME_FAILED else f"unrecognised failure from provider {p.provider!r}"
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
