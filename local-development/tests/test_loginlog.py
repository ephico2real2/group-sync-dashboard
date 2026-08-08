"""The oauth-server log parser, against lines measured on a live cluster.

EVERY FIXTURE IN THIS FILE IS REAL. Each one was copied out of `oc logs -n
openshift-authentication deploy/oauth-openshift --timestamps` on CRC after driving the login by
hand — successful, wrong password, a real person outside the login-gate group, a username that does
not exist, and both the CLI and the browser code paths. Nothing here is invented, because the whole
risk this module carries is that the log does not say what we assumed it says.

WHY THIS FILE EXISTS AT ALL. It was written after a defect that only the cluster could show: the
verdict line comes in TWO grammars one word apart, and the parser required the word. `oc login` goes
through basicauth.go and logs `for login "<user>"`; the console's HTML form goes through login.go and
logs `for "<user>"`. So every browser login — which is how people actually sign in — was dropped,
silently, while every CLI login was captured. The tab showed fewer rows than had happened and looked
perfectly healthy. A unit test over the real grammar is the only thing that catches that class of
bug, and there was none.
"""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from gsd import loginlog
from gsd.loginlog import ATTEMPT_WINDOW, parse, parse_timestamp

# ── The four verdict grammars, verbatim ───────────────────────────────────────────────────────────
# Counted in one pod's whole log at the time of the fix: 24 + 5 basicauth, 3 login.go.
CLI_FAIL = ('2026-08-07T23:48:57.591593769Z I0807 23:48:57.591365       1 basicauth.go:48] '
            'Login with provider "developer" failed for login "jane.smith"')
CLI_OK = ('2026-08-07T23:48:58.039800273Z I0807 23:48:58.035917       1 basicauth.go:51] '
          'Login with provider "ldap-local" succeeded for login "jane.smith": '
          '&groupmapper.UserInfoGroupsWrapper{userInfo:(*user.DefaultInfo)(0xc000891f00), '
          'additionalGroups:sets.String{}}')
WEB_FAIL = ('2026-08-07T23:55:22.035263602Z I0807 23:55:22.035186       1 login.go:183] '
            'Login with provider "developer" failed for "developer"')
WEB_OK = ('2026-08-07T23:55:30.986602155Z I0807 23:55:30.984162       1 login.go:191] '
          'Login with provider "developer" succeeded for "developer": '
          '&groupmapper.UserInfoGroupsWrapper{userInfo:(*user.DefaultInfo)(0xc000d1f600), '
          'additionalGroups:sets.String{}}')

# ── The cause lines, verbatim ─────────────────────────────────────────────────────────────────────
SEARCHING = ('2026-08-07T23:48:57.688273440Z I0807 23:48:57.687787       1 ldap.go:131] '
             'searching for (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
             'dc=ephico2real,dc=com))(uid=jane.smith))')
FOUND_DN = ('2026-08-07T23:48:57.703907147Z I0807 23:48:57.703469       1 ldap.go:148] '
            'found dn="uid=jane.smith,ou=People,dc=ephico2real,dc=com" for (&(&(uid=*))'
            '(uid=jane.smith))')
# OpenLDAP sends NO diagnostic — the field after the colon is empty. That is the measured shape, and
# it is why code 49 alone cannot be the cause on a directory that does fill it in.
BIND_49 = ('2026-08-07T23:49:02.136205645Z I0807 23:49:02.136108       1 ldap.go:152] '
           'error binding password for "uid=jane.smith,ou=People,dc=ephico2real,dc=com": '
           'LDAP Result Code 49 "Invalid Credentials": ')
NO_ENTRIES = ('2026-08-07T23:49:04.534383395Z I0807 23:49:04.530341       1 ldap.go:139] '
              'no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
              'dc=ephico2real,dc=com))(uid=bob.wilson))')


# ── The browser + LDAP shape, verbatim ────────────────────────────────────────────────────────────
# Surfaced by the operator testing failed logins through the console rather than the CLI, and it is a
# combination neither path shows on its own: login.go's grammar AND an ldap.go cause, with NO HTPasswd
# failure ahead of it because the browser picks one provider. So the attempt STARTS at the cause line,
# before anything has named the user.
#
# Note all three share ONE kubelet timestamp — 23:56:11.902704407Z — while klog's own stamps differ
# (.897676 / .899056 / .899372). They landed in the same read chunk. The correlation window absorbs
# it; nothing here may depend on the three being distinguishable by the prefix.
WEB_LDAP_SEARCHING = ('2026-08-07T23:56:11.902704407Z I0807 23:56:11.897676       1 ldap.go:131] '
                      'searching for (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
                      'dc=ephico2real,dc=com))(uid=bob.wilson))')
WEB_LDAP_NO_ENTRIES = ('2026-08-07T23:56:11.902704407Z I0807 23:56:11.899056       1 ldap.go:139] '
                       'no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,'
                       'ou=Groups,dc=ephico2real,dc=com))(uid=bob.wilson))')
WEB_LDAP_FAIL = ('2026-08-07T23:56:11.902704407Z I0807 23:56:11.899372       1 login.go:183] '
                 'Login with provider "ldap-local" failed for "bob.wilson"')


# ── Browser + LDAP, the SUCCESS and the WRONG PASSWORD, verbatim ──────────────────────────────────
# From the operator signing in through the console as a gate member. Two shapes the CLI path cannot
# produce, and the ones a real deployment sees most:
#
#   success        starts at ldap.go:131, ends at login.go:191, and carries NO cause line at all —
#                  `found dn=` and `identitymapper` are progress. Spanned 432ms end to end.
#   wrong password the bind error arrives BEFORE the verdict names anybody (no HTPasswd failure ahead
#                  of it to create the pending attempt), so it is the orphan-cause path. Spanned 4ms.
WEB_LDAP_OK_SEARCH = ('2026-08-08T00:01:50.757097091Z I0808 00:01:50.757022       1 ldap.go:131] '
                      'searching for (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
                      'dc=ephico2real,dc=com))(uid=jane.smith))')
WEB_LDAP_OK_FOUND = ('2026-08-08T00:01:50.761343502Z I0808 00:01:50.761246       1 ldap.go:148] '
                     'found dn="uid=jane.smith,ou=People,dc=ephico2real,dc=com" for '
                     '(&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,'
                     'dc=com))(uid=jane.smith))')
WEB_LDAP_OK_MAPPER = ('2026-08-08T00:01:51.188940321Z I0808 00:01:51.188870       1 ldap.go:76] '
                      'identitymapper: got userIdentityMapping: '
                      '&groupmapper.UserInfoGroupsWrapper{userInfo:(*user.DefaultInfo)'
                      '(0xc0008905c0), additionalGroups:sets.String{}}')
WEB_LDAP_OK_VERDICT = ('2026-08-08T00:01:51.189132247Z I0808 00:01:51.189060       1 login.go:191] '
                       'Login with provider "ldap-local" succeeded for "jane.smith": '
                       '&groupmapper.UserInfoGroupsWrapper{userInfo:(*user.DefaultInfo)'
                       '(0xc0008905c0), additionalGroups:sets.String{}}')
WEB_LDAP_BADPW_BIND = ('2026-08-08T00:02:46.883182023Z I0808 00:02:46.883110       1 ldap.go:152] '
                       'error binding password for "uid=jane.smith,ou=People,dc=ephico2real,'
                       'dc=com": LDAP Result Code 49 "Invalid Credentials": ')
WEB_LDAP_BADPW_VERDICT = ('2026-08-08T00:02:46.884349367Z I0808 00:02:46.884152       1 '
                          'login.go:183] Login with provider "ldap-local" failed for "jane.smith"')


def _at(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def _restamp(line: str, kubelet: str) -> str:
    """Move a measured line to a new kubelet timestamp, leaving the message untouched.

    Needed because the fixtures are real lines from DIFFERENT attempts, and pairing them by hand is
    how a test comes to assert something the parser will rightly refuse: the correlation window is
    one second, so a verdict from 23:48:57 and a cause from 23:49:02 are two attempts, not one. The
    first draft of this file did exactly that and failed thirteen tests — the parser was right.
    """
    return re.sub(r"^\S+", kubelet, line, count=1)


# The bad-password attempt as the cluster actually logged it: verdict, cause, verdict, all inside
# 200ms. Built by restamping so the MESSAGES stay verbatim while the timing is the real timing.
BAD_PW_FIRST = _restamp(CLI_FAIL, "2026-08-07T23:49:01.941708992Z")
BAD_PW_LAST = _restamp(CLI_FAIL.replace('"developer"', '"ldap-local"'),
                       "2026-08-07T23:49:02.138390382Z")


class TestTheTwoGrammars:
    """The regression test for the defect this file was written after.

    Parametrised over both call sites rather than asserting the browser one in isolation: the risk is
    a future edit that fixes one grammar by breaking the other, and a single test per shape would let
    that through.
    """

    @pytest.mark.parametrize("line,who,provider", [
        pytest.param(CLI_OK, "jane.smith", "ldap-local", id="basicauth-cli"),
        pytest.param(WEB_OK, "developer", "developer", id="login-go-browser-form"),
    ])
    def test_a_success_is_recognised_in_both(self, line, who, provider):
        got = parse([line])
        assert len(got) == 1, f"the {provider} success was not parsed at all: {got}"
        assert got[0].user_name == who
        assert got[0].outcome == loginlog.OUTCOME_SUCCESS
        assert got[0].provider == provider

    def test_the_browser_form_omits_the_word_login_and_is_still_parsed(self):
        """The one-word difference, stated as its own test so the reason cannot be lost.

        basicauth.go: `... failed for login "developer"`
        login.go:     `... failed for "developer"`
        """
        assert 'for login "' in CLI_FAIL and 'for login "' not in WEB_FAIL, (
            "the fixtures no longer differ in the way this test exists to cover"
        )
        assert parse([WEB_FAIL]), "a browser-form failure parses to nothing"

    def test_a_lone_browser_failure_is_a_real_failure(self):
        """A browser login picks ONE provider, so there is no provider chain to explain it away.

        HTPasswd logs no cause line — a wrong password and an unknown username are identical to it —
        so `failed` with no attributable cause is the honest bucket rather than a guessed one.
        """
        got = parse([WEB_FAIL])
        assert len(got) == 1
        assert got[0].outcome == loginlog.OUTCOME_FAILED
        assert got[0].ldap_result_code is None

    def test_browser_retries_stay_separate_attempts(self):
        """fail, fail, succeed — measured 5s and 3s apart, all for the same account.

        Merging them would report one success and hide two failed attempts on a break-glass account,
        which is the opposite of what this record is for. ATTEMPT_WINDOW is 1s, and a human retyping
        a password cannot beat that.
        """
        second_fail = WEB_FAIL.replace("23:55:22.035263602", "23:55:27.353178245") \
                              .replace("23:55:22.035186", "23:55:27.353096")
        got = parse([WEB_FAIL, second_fail, WEB_OK])
        assert [a.outcome for a in got] == [
            loginlog.OUTCOME_FAILED, loginlog.OUTCOME_FAILED, loginlog.OUTCOME_SUCCESS
        ], got


class TestTheBrowserLdapShape:
    """Browser + LDAP: login.go's grammar with an ldap.go cause and no provider chain ahead of it.

    The operator found this one by testing failed logins in the console. It matters because it is the
    ONLY shape where the browser path produces an attributable cause, so a parser that handled the
    browser grammar but not the orphan-cause path would record it as a bare `failed` and lose the
    reason.
    """

    def test_a_gated_person_is_rejected_not_merely_failed(self):
        got = parse([WEB_LDAP_SEARCHING, WEB_LDAP_NO_ENTRIES, WEB_LDAP_FAIL])
        assert len(got) == 1, got
        assert got[0].user_name == "bob.wilson"
        assert got[0].outcome == loginlog.OUTCOME_REJECTED, (
            "the cause arrived before the verdict named anybody, and was dropped"
        )
        assert got[0].provider == "ldap-local"

    def test_it_works_when_all_three_lines_share_one_kubelet_timestamp(self):
        """Which is what the cluster actually did — they arrived in one read chunk."""
        stamps = {line.split()[0] for line in
                  (WEB_LDAP_SEARCHING, WEB_LDAP_NO_ENTRIES, WEB_LDAP_FAIL)}
        assert len(stamps) == 1, f"the fixture no longer shares one stamp: {stamps}"
        assert parse([WEB_LDAP_SEARCHING, WEB_LDAP_NO_ENTRIES, WEB_LDAP_FAIL])[0].outcome \
            == loginlog.OUTCOME_REJECTED

    def test_a_successful_browser_ldap_login_is_a_success(self):
        """The commonest real shape: console + directory, and no cause line anywhere in it.

        `found dn=` and `identitymapper` are progress, not causes — if either were treated as one, a
        clean success would acquire a spurious reason.
        """
        got = parse([WEB_LDAP_OK_SEARCH, WEB_LDAP_OK_FOUND, WEB_LDAP_OK_MAPPER,
                     WEB_LDAP_OK_VERDICT])
        assert len(got) == 1, got
        assert (got[0].user_name, got[0].outcome) == ("jane.smith", loginlog.OUTCOME_SUCCESS)
        assert got[0].provider == "ldap-local"
        assert got[0].ldap_result_code is None and got[0].detail is None, (
            f"a clean success picked up a cause it should not have: {got[0]}"
        )

    def test_a_browser_wrong_password_reads_the_code_through_the_orphan_path(self):
        """No HTPasswd failure ahead of it, so the bind error arrives before anybody is named.

        This is the case that would silently lose every cause on a single-provider cluster: the
        attempt starts at the cause, and the verdict is the first line that says who it was about.
        """
        got = parse([WEB_LDAP_OK_SEARCH, WEB_LDAP_OK_FOUND,
                     WEB_LDAP_BADPW_BIND, WEB_LDAP_BADPW_VERDICT])
        assert len(got) == 1, got
        assert got[0].outcome == loginlog.OUTCOME_BAD_PASSWORD
        assert got[0].ldap_result_code == 49
        # Stamped at the cause, which is where the attempt actually began.
        assert got[0].at == _at("2026-08-08T00:02:46.883182023Z")

    def test_a_wrong_password_then_a_success_seconds_later_stays_two_attempts(self):
        """Measured 8s apart, same person, same provider. One row would hide the failure."""
        got = parse([WEB_LDAP_BADPW_BIND, WEB_LDAP_BADPW_VERDICT,
                     _restamp(WEB_LDAP_OK_VERDICT, "2026-08-08T00:02:54.159359796Z")])
        assert [a.outcome for a in got] == [
            loginlog.OUTCOME_BAD_PASSWORD, loginlog.OUTCOME_SUCCESS], got

    def test_the_htpasswd_browser_failure_says_no_reason_was_given(self):
        """HTPasswd logs a verdict and nothing else, so there is no cause to find.

        The detail must say the provider gave no reason rather than implying we failed to parse
        something — a reader who has just watched their own login fail should not be sent looking for
        a bug in this code.
        """
        got = parse([WEB_FAIL])
        assert got[0].outcome == loginlog.OUTCOME_FAILED
        assert "no reason" in (got[0].detail or ""), got[0].detail
        assert "developer" in (got[0].detail or "")


class TestTheCliProviderChain:
    """A `failed` line is NOT a failed login — every provider tried before the matching one logs one.

    This is provider-ORDER dependent: on this cluster HTPasswd is tried before LDAP, so an LDAP login
    logs a `developer` failure first. An HTPasswd login logs no failure at all.
    """

    def test_a_failure_then_a_success_for_the_same_person_is_one_success(self):
        got = parse([CLI_FAIL, SEARCHING, FOUND_DN, CLI_OK])
        assert len(got) == 1, f"the provider-order noise was recorded as its own attempt: {got}"
        assert got[0].outcome == loginlog.OUTCOME_SUCCESS
        # The provider that DECIDED it, not the first one tried.
        assert got[0].provider == "ldap-local"
        # And the attempt is stamped at its first line, so the record orders by when it began.
        assert got[0].at == _at("2026-08-07T23:48:57.591593769Z")

    def test_the_attempt_window_keeps_two_logins_by_one_person_apart(self):
        """The same account failing and then succeeding minutes later is two attempts, not one.

        Without the window a long read would merge everything one person did into a single row.
        """
        later = CLI_OK.replace("23:48:58.039800273", "23:52:58.039800273") \
                      .replace("23:48:58.035917", "23:52:58.035917")
        got = parse([CLI_FAIL, later])
        assert len(got) == 2, got
        assert got[0].outcome == loginlog.OUTCOME_FAILED
        assert got[1].outcome == loginlog.OUTCOME_SUCCESS
        assert later.split()[0][11:19] != CLI_FAIL.split()[0][11:19]
        assert _at("2026-08-07T23:52:58.039800273Z") - _at("2026-08-07T23:48:57.591593769Z") \
            > ATTEMPT_WINDOW


class TestCauses:
    def test_a_wrong_password_is_read_from_the_bind_error(self):
        got = parse([BAD_PW_FIRST, BIND_49, BAD_PW_LAST])
        assert len(got) == 1, got
        assert got[0].outcome == loginlog.OUTCOME_BAD_PASSWORD
        assert got[0].ldap_result_code == 49

    def test_an_empty_openldap_diagnostic_stays_a_wrong_password(self):
        """The measured OpenLDAP shape: code 49 with nothing after the colon.

        This is the case that makes the AD sub-code map safe — a directory that sends no diagnostic
        must not fall through to some other outcome.
        """
        assert BIND_49.rstrip().endswith('"Invalid Credentials":'), (
            "the fixture no longer carries an EMPTY diagnostic, which is what it is here to prove"
        )
        got = parse([BAD_PW_FIRST, BIND_49])
        assert got and got[0].outcome == loginlog.OUTCOME_BAD_PASSWORD

    def test_no_entries_is_one_honest_bucket_for_two_causes(self):
        """A real person outside the gate group and a username that does not exist are IDENTICAL.

        Measured: both produce `no entries matching (<filter>)`, because the provider's search filter
        carries the gate group. Splitting them would be an invention, so both land in `rejected`.
        """
        # Restamped to the instants the cluster logged them at — 23:49:04 and 23:49:06.
        gated = parse([
            _restamp(CLI_FAIL.replace('"jane.smith"', '"bob.wilson"'),
                     "2026-08-07T23:49:04.463800921Z"),
            NO_ENTRIES,
        ])
        unknown = parse([
            _restamp(CLI_FAIL.replace('"jane.smith"', '"nosuchperson"'),
                     "2026-08-07T23:49:06.840942667Z"),
            _restamp(NO_ENTRIES.replace("uid=bob.wilson", "uid=nosuchperson"),
                     "2026-08-07T23:49:06.895739387Z"),
        ])
        assert gated[0].outcome == loginlog.OUTCOME_REJECTED
        assert unknown[0].outcome == loginlog.OUTCOME_REJECTED
        # Same outcome, same absence of a code: nothing in the record claims to tell them apart.
        assert gated[0].ldap_result_code is unknown[0].ldap_result_code is None

    def test_a_cause_arriving_before_any_username_is_still_attached(self):
        """The ordinary shape on a single-provider cluster, and the defect that shipped once.

        With LDAP as the only provider the attempt STARTS at `ldap.go:131 searching` — no username
        exists yet — so a cause that arrives before the first verdict has no pending attempt to
        attach to. Dropping those loses every cause on such a cluster, including expired passwords.
        """
        got = parse([BIND_49, BAD_PW_LAST])
        assert len(got) == 1, got
        assert got[0].outcome == loginlog.OUTCOME_BAD_PASSWORD, (
            "the cause was dropped because it arrived before the line naming the user"
        )
        # Stamped at the CAUSE, which is when the attempt actually began.
        assert got[0].at == _at("2026-08-07T23:49:02.136205645Z")


class TestActiveDirectorySubCodes:
    """AD returns a bare 49 for expired, locked and disabled alike; only `data <hex>` separates them.

    This cluster runs OpenLDAP, so these are synthesised from the documented AD format rather than
    measured — and they are marked as such. Recording an expired password as a wrong password sends
    somebody to reset a credential that is already correct, which is why the map exists.
    """

    @pytest.mark.parametrize("hexcode,expected", [
        ("532", loginlog.OUTCOME_PASSWORD_EXPIRED),
        ("773", loginlog.OUTCOME_MUST_CHANGE_PASSWORD),
        ("775", loginlog.OUTCOME_ACCOUNT_LOCKED),
        ("533", loginlog.OUTCOME_ACCOUNT_DISABLED),
        ("701", loginlog.OUTCOME_ACCOUNT_EXPIRED),
        ("530", loginlog.OUTCOME_LOGON_NOT_PERMITTED),
        ("531", loginlog.OUTCOME_LOGON_NOT_PERMITTED),
        ("525", loginlog.OUTCOME_REJECTED),
        ("52e", loginlog.OUTCOME_BAD_PASSWORD),
    ])
    def test_the_sub_code_decides_not_the_result_code(self, hexcode, expected):
        line = (BIND_49.rstrip()
                + f" 80090308: LdapErr: DSID-0C0903A9, comment: AcceptSecurityContext error, "
                  f"data {hexcode}, v4563")
        got = parse([BAD_PW_FIRST, line])
        assert got and got[0].outcome == expected, f"data {hexcode} -> {got}"
        # The code is still recorded: it is what the directory said, and the outcome is our reading.
        assert got[0].ldap_result_code == 49

    def test_an_unmapped_sub_code_is_failed_not_a_wrong_password(self):
        """An unmapped sub-code could mean anything, so it must not be guessed at.

        Calling it a wrong password would send somebody to reset a credential that may be perfectly
        correct — the exact harm the sub-code map exists to prevent — so it becomes `failed` and the
        code is kept in `detail`, which makes the gap visible instead of silently mislabelled.

        This assertion originally expected `bad_password`, taken from a comment above _AD_SUBCODE that
        contradicted _classify_bind eleven lines below it. The code was right; the comment is now
        fixed and this test is what stops the two drifting apart again.
        """
        line = BIND_49.rstrip() + " comment: AcceptSecurityContext error, data 999, v4563"
        got = parse([BAD_PW_FIRST, line])
        assert got and got[0].outcome == loginlog.OUTCOME_FAILED
        assert "999" in (got[0].detail or ""), (
            f"the unmapped code is not in the detail, so the gap is invisible: {got[0].detail!r}"
        )

    def test_openldap_ppolicy_expiry_uses_53_not_49(self):
        """Which is why 49 cannot be treated as "all password failures" on either directory."""
        line = BIND_49.replace('LDAP Result Code 49 "Invalid Credentials"',
                               'LDAP Result Code 53 "Unwilling To Perform"')
        got = parse([BAD_PW_FIRST, line])
        assert got and got[0].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED
        assert got[0].ldap_result_code == 53


class TestWhatIsDeliberatelyIgnored:
    def test_progress_lines_alone_record_nothing(self):
        """`searching` and `found dn=` say an attempt is underway, not how it ended.

        Recording them would put a row on the page for every keystroke of an in-flight login.
        """
        assert parse([SEARCHING, FOUND_DN]) == []

    def test_a_line_with_no_kubelet_timestamp_is_skipped_not_guessed_at(self):
        """klog's own stamp has no year and no zone, so it cannot be turned into an instant.

        A record whose timestamp is invented is worse than one that is absent — this page exists to
        be correlated against `oc` output and other logs.
        """
        naked = 'I0807 23:48:58.035917 1 basicauth.go:51] Login with provider "x" succeeded for login "y"'
        assert parse_timestamp(naked) is None
        assert parse([naked]) == []

    def test_http_access_lines_are_not_logins(self):
        """The oauth-server logs an httplog line per request, including for the login form itself."""
        httplog = ('2026-08-07T23:48:37.067994476Z I0807 23:48:37.067928       1 httplog.go:132] '
                   '"HTTP" verb="GET" URI="/oauth/authorize?client_id=console&idp=ldap-local" '
                   'resp=302')
        assert parse([httplog]) == []

    def test_the_username_is_taken_verbatim(self):
        """It is what was TYPED, which may match no User object and no group member.

        That mismatch is the finding, so normalising it here would destroy the signal.
        """
        odd = WEB_FAIL.replace('for "developer"', 'for "Bob.Wilson@EXAMPLE.com"')
        got = parse([odd])
        assert got[0].user_name == "Bob.Wilson@EXAMPLE.com"

    def test_no_raw_line_is_ever_carried_into_the_detail(self):
        """ldap.go embeds the bind filter and the user's DN — the gate group and the directory's
        layout. More sensitive than the username the row is already keyed on, and it must not be
        persisted."""
        got = parse([BAD_PW_FIRST, BIND_49])
        detail = got[0].detail or ""
        assert "memberOf" not in detail and "ou=People" not in detail, detail
        assert "dc=ephico2real" not in detail, detail


class TestTheWholeMeasuredSession:
    """All four attempts from the live run, in the order the pod logged them.

    This is the end-to-end shape: one success, one wrong password, one gated person, one unknown
    name — every one preceded by the HTPasswd failure that is not a failed login.
    """

    LINES = [
        CLI_FAIL, SEARCHING, FOUND_DN, CLI_OK,
        CLI_FAIL.replace("23:48:57.591593769", "23:49:01.941708992"),
        BIND_49,
        CLI_FAIL.replace('"developer"', '"ldap-local"').replace(
            "23:48:57.591593769", "23:49:02.138390382"),
        CLI_FAIL.replace('"jane.smith"', '"bob.wilson"').replace(
            "23:48:57.591593769", "23:49:04.463800921"),
        NO_ENTRIES,
        CLI_FAIL.replace('"jane.smith"', '"bob.wilson"').replace('"developer"', '"ldap-local"')
                .replace("23:48:57.591593769", "23:49:04.535286875"),
        CLI_FAIL.replace('"jane.smith"', '"nosuchperson"').replace(
            "23:48:57.591593769", "23:49:06.840942667"),
        NO_ENTRIES.replace("uid=bob.wilson", "uid=nosuchperson").replace(
            "23:49:04.534383395", "23:49:06.895739387"),
        CLI_FAIL.replace('"jane.smith"', '"nosuchperson"').replace('"developer"', '"ldap-local"')
                .replace("23:48:57.591593769", "23:49:06.900064650"),
    ]

    def test_it_reproduces_what_the_cluster_recorded(self):
        got = parse(self.LINES)
        assert [(a.user_name, a.outcome) for a in got] == [
            ("jane.smith", loginlog.OUTCOME_SUCCESS),
            ("jane.smith", loginlog.OUTCOME_BAD_PASSWORD),
            ("bob.wilson", loginlog.OUTCOME_REJECTED),
            ("nosuchperson", loginlog.OUTCOME_REJECTED),
        ], [(a.user_name, a.outcome, a.at.isoformat()) for a in got]

    def test_it_is_ordered_oldest_first(self):
        stamps = [a.at for a in parse(self.LINES)]
        assert stamps == sorted(stamps), stamps

    def test_adding_the_browser_login_adds_exactly_one_more(self):
        """The bug, expressed as a count. Before the fix this returned four, not five."""
        got = parse(self.LINES + [WEB_OK])
        assert len(got) == 5, [(a.user_name, a.outcome) for a in got]
        assert got[-1].user_name == "developer"
        assert got[-1].provider == "developer", (
            "the provider must be the HTPasswd one, or the row cannot be labelled break-glass"
        )


def test_a_verdict_phrase_inside_an_unrelated_message_is_not_an_attempt():
    """Quoted or relayed message text is not an oauth-server verdict."""
    line = (
        '2026-08-07T00:00:00.000000Z I0807 00:00:00.000000 1 audit.go:1] '
        'request rejected; submitted text: Login with provider "ldap-local" '
        'succeeded for login "alice"'
    )
    assert parse([line]) == []


def test_interleaved_people_do_not_swap_directory_causes():
    def line(ms, message):
        return f'2026-08-07T00:00:00.{ms:06d}Z I0807 00:00:00.0 1 x.go:1] {message}'
    got = parse([
        line(0, 'Login with provider "first" failed for login "alice"'),
        line(100000, 'Login with provider "first" failed for login "bob"'),
        line(200000, 'error binding password for "uid=alice,dc=example": '
                     'LDAP Result Code 49 "Invalid Credentials": '),
        line(300000, 'Login with provider "ldap" failed for login "alice"'),
        line(400000, 'Login with provider "ldap" failed for login "bob"'),
    ])
    assert {a.user_name: a.outcome for a in got} == {
        "alice": loginlog.OUTCOME_BAD_PASSWORD,
        "bob": loginlog.OUTCOME_FAILED,
    }


AD_DIAG = ('LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9, '
           'comment: AcceptSecurityContext error, data 532, v4563')


def _line(iso: str, message: str) -> str:
    return f"{iso} I0807 00:00:00.000000       1 x.go:1] {message}"


def test_an_active_directory_cause_survives_without_the_login_in_the_dn():
    """FAILS ON PASS 1'S TREE — the finding that rejects its parse replacement.

    On AD the verdict says `jsmith` while the DN says `CN=Jane Smith`. The sub-code map exists FOR
    this directory, so a correlation rule that requires the cause text to repeat the login deletes
    the feature exactly where it matters, and no OpenLDAP fixture can notice."""
    cli = parse([
        _line('2026-08-07T10:00:00.000000000Z',
              'Login with provider "developer" failed for login "jsmith"'),
        _line('2026-08-07T10:00:00.100000000Z',
              f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
        _line('2026-08-07T10:00:00.200000000Z',
              'Login with provider "ad" failed for login "jsmith"'),
    ])
    assert cli[0].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED, cli

    orphaned = parse([
        _line('2026-08-07T11:00:00.000000000Z',
              f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
        _line('2026-08-07T11:00:00.001000000Z',
              'Login with provider "ad" failed for "jsmith"'),
    ])
    assert orphaned[0].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED, orphaned


def test_an_identified_orphan_waits_for_the_verdict_that_names_it():
    """P3 done right: alice's cause (tied to her by the found line) must not attach to bob's
    verdict even when his lands first — and must still be there when hers lands. FAILS on the repo
    tree (bob steals the cause) AND on pass 1's tree (the orphan is destroyed at bob's verdict)."""
    got = parse([
        _line('2026-08-07T12:00:00.000000000Z',
              'found dn="uid=alice,dc=example" for (&(&(uid=*))(uid=alice))'),
        _line('2026-08-07T12:00:00.050000000Z',
              'error binding password for "uid=alice,dc=example": '
              'LDAP Result Code 49 "Invalid Credentials": '),
        _line('2026-08-07T12:00:00.900000000Z',
              'Login with provider "ldap" failed for "bob"'),
        _line('2026-08-07T12:00:00.950000000Z',
              'Login with provider "ldap" failed for "alice"'),
    ])
    by_user = {a.user_name: a for a in got}
    assert by_user["bob"].outcome == loginlog.OUTCOME_FAILED
    assert by_user["bob"].ldap_result_code is None
    assert by_user["alice"].outcome == loginlog.OUTCOME_BAD_PASSWORD
    assert by_user["alice"].ldap_result_code == 49


def test_the_mention_check_is_exact_not_substring():
    """`uid=bob` must reach bob even when bobby's attempt is the more recent one — a substring
    match reintroduces P3 one keystroke at a time."""
    got = parse([
        _line('2026-08-07T13:00:00.000000000Z',
              'Login with provider "developer" failed for login "bob"'),
        _line('2026-08-07T13:00:00.100000000Z',
              'Login with provider "developer" failed for login "bobby"'),
        _line('2026-08-07T13:00:00.200000000Z',
              'no entries matching (&(&(uid=*)(memberOf=cn=gate,dc=example))(uid=bob))'),
        _line('2026-08-07T13:00:00.300000000Z',
              'Login with provider "ldap" failed for login "bob"'),
        _line('2026-08-07T13:00:00.400000000Z',
              'Login with provider "ldap" failed for login "bobby"'),
    ])
    by_user = {a.user_name: a for a in got}
    assert by_user["bob"].outcome == loginlog.OUTCOME_REJECTED
    assert by_user["bobby"].outcome == loginlog.OUTCOME_FAILED


def test_two_people_in_flight_on_active_directory_attach_by_the_found_dn():
    """The found line's filter carries `sAMAccountName=jsmith`, so the bind that follows belongs
    to jsmith even though tbrown's attempt is more recent. FAILS on the repo tree (tbrown is
    newest and takes the cause) and on pass 1's tree (the cause is dropped)."""
    got = parse([
        _line('2026-08-07T14:00:00.000000000Z',
              'Login with provider "developer" failed for login "jsmith"'),
        _line('2026-08-07T14:00:00.100000000Z',
              'Login with provider "developer" failed for login "tbrown"'),
        _line('2026-08-07T14:00:00.150000000Z',
              'found dn="CN=Jane Smith,OU=People,DC=corp,DC=example" for '
              '(&(&(objectClass=person)(memberOf=CN=gate,OU=Groups,DC=corp,DC=example))'
              '(sAMAccountName=jsmith))'),
        _line('2026-08-07T14:00:00.200000000Z',
              f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
        _line('2026-08-07T14:00:00.300000000Z',
              'Login with provider "ad" failed for login "jsmith"'),
        _line('2026-08-07T14:00:00.400000000Z',
              'Login with provider "ad" failed for login "tbrown"'),
    ])
    by_user = {a.user_name: a for a in got}
    assert by_user["jsmith"].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED
    assert by_user["tbrown"].outcome == loginlog.OUTCOME_FAILED
    assert by_user["tbrown"].ldap_result_code is None
