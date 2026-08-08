"""The seam three files share: `loginlog.adopt` → the capture read window → the store's UNIQUE key.

AN ATTEMPT'S `at` IS NOT DECIDED BY THE LOGIN. It is decided by which lines the read returned.
`parse` stamps an attempt at its CAUSE when the cause is in the same read — `adopt` moves `first_at`
back to it, which `test_loginlog.py` asserts in as many words ("stamped at the cause, which is where
the attempt actually began") — and at its VERDICT when the cause fell outside the window. Both `at`
and `outcome` are components of `UNIQUE(cluster_id, pod_name, user_name, at, outcome)`, so one real
login read two different ways is two different rows and INSERT OR IGNORE cannot collapse them.

WHY THIS NEEDED A MODULE OF ITS OWN. `test_loginlog.py` proves the parse in both shapes and never
touches a store. `test_logincapture_loop.py` drives the loop, but its double returns the same lines
whatever window it is asked for — it asserts the `since_seconds` REQUESTED, which is the right
contract for what that suite covers and blind to this one, because nothing has ever clipped a log.
The failure this guards is the class deployment found and two review passes did not: a phantom row
beside a real one, stating something false about a named person.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gsd import logincapture
from gsd.config import ClusterConfig, Settings
from gsd.logincapture import (FIRST_SIGHT_SECONDS, OVERLAP_SECONDS, SETTLE_SECONDS,
                             capture_once)
from gsd.loginlog import ATTEMPT_WINDOW, parse, parse_timestamp
from gsd.store import Store
from gsd.timeutil import now_iso

POD = "oauth-openshift-6b9f7c8d5-abcde"
CLUSTER = ClusterConfig("crc-local", "https://api.example", token_env="X")

# The measured browser+LDAP wrong-password sequence, from the session recorded in test_loginlog.py.
# The message bodies are verbatim; only the kubelet stamps move, for the reason _restamp exists there.
_SEARCH = ('I0808 00:01:50.757022       1 ldap.go:131] searching for (&(&(uid=*)'
           '(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))(uid=jane.smith))')
_FOUND = ('I0808 00:01:50.761246       1 ldap.go:148] found dn="uid=jane.smith,ou=People,'
          'dc=ephico2real,dc=com" for (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
          'dc=ephico2real,dc=com))(uid=jane.smith))')
_BIND = ('I0808 00:02:46.883110       1 ldap.go:152] error binding password for '
         '"uid=jane.smith,ou=People,dc=ephico2real,dc=com": LDAP Result Code 49 '
         '"Invalid Credentials": ')
_VERDICT = ('I0808 00:02:46.884152       1 login.go:183] Login with provider "ldap-local" '
            'failed for "jane.smith"')

# Offsets within the one attempt, in seconds. The bind→verdict figure is the MEASURED 1.167 ms —
# `00:02:46.883182023` to `00:02:46.884349367` — and is deliberately not widened: the width of that
# gap is the width of the slot a read boundary has to land in, so rounding it up would make the
# defect look likelier than the cluster's own logs say it is.
SEARCH_OFFSET = 0.000
FOUND_OFFSET = 0.004
BIND_OFFSET = 0.010
VERDICT_OFFSET = 0.011167


def _stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")


def _attempt_lines(begins: datetime) -> list[str]:
    """The four lines of one wrong-password attempt, anchored at `begins`."""
    return [
        f"{_stamp(begins + timedelta(seconds=SEARCH_OFFSET))} {_SEARCH}",
        f"{_stamp(begins + timedelta(seconds=FOUND_OFFSET))} {_FOUND}",
        f"{_stamp(begins + timedelta(seconds=BIND_OFFSET))} {_BIND}",
        f"{_stamp(begins + timedelta(seconds=VERDICT_OFFSET))} {_VERDICT}",
    ]


class WindowedClient:
    """A fake cluster that HONOURS `since_seconds`, slicing the log the way the kubelet does.

    The existing loop suite's double records the window it was asked for and returns the same lines
    regardless. That is the right contract for what it tests and blind to this one: a boundary can
    only clip an attempt if something actually slices.

    Deriving the cutoff from `since_seconds` rather than taking it as a parameter is deliberate, and
    a first draft of this file got it wrong. Imposing a cutoff directly decouples the lines returned
    from the window the loop believes it asked for — and the guard under test is defined in terms of
    that window, so it could never see the clip and the test passed while the defect stood.
    """

    def __init__(self, lines, pods=(POD,)):
        self._lines = list(lines)
        self._pods = list(pods)
        self.windows: list[int | None] = []
        self.returned: list[int] = []

    def fetch_oauth_pods(self, namespace):
        return list(self._pods)

    def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw):
        self.windows.append(since_seconds)
        if since_seconds is None:
            out = list(self._lines)
        else:
            cutoff = datetime.now(UTC) - timedelta(seconds=since_seconds)
            out = [raw for raw in self._lines
                   if (ts := parse_timestamp(raw)) is not None and ts > cutoff]
        self.returned.append(len(out))
        return out


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "crossseam.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "crossseam.db"),
                    login_capture_enabled=True)


@pytest.fixture()
def install(monkeypatch):
    def _install(client):
        monkeypatch.setattr(logincapture, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


class TestTheParseShiftsTheStampWithTheWindow:
    """The premise, established on the parser alone before any store is involved.

    If these two reads agreed on `at` and `outcome`, the dedup key would collapse them and there
    would be nothing further to test.
    """

    def test_the_whole_attempt_is_stamped_at_its_cause(self):
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        got = parse(_attempt_lines(begins))
        assert len(got) == 1, got
        assert got[0].outcome == "bad_password"
        assert got[0].ldap_result_code == 49
        assert got[0].at == begins + timedelta(seconds=BIND_OFFSET), (
            "the attempt should carry the CAUSE's instant, not the verdict's"
        )

    def test_the_same_login_clipped_of_its_cause_is_stamped_at_its_verdict(self):
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        clipped = _attempt_lines(begins)[3:]            # the verdict alone, as a late window sees it
        got = parse(clipped)
        assert len(got) == 1, got
        assert got[0].outcome == "failed", "with no cause there is no code to classify"
        assert got[0].ldap_result_code is None
        assert got[0].at == begins + timedelta(seconds=VERDICT_OFFSET)

    def test_so_the_two_reads_disagree_on_both_key_columns(self):
        """`at` AND `outcome` both differ, and both are in UNIQUE(...) — hence two rows, not one."""
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        whole = parse(_attempt_lines(begins))[0]
        clipped = parse(_attempt_lines(begins)[3:])[0]
        assert whole.user_name == clipped.user_name
        assert whole.at != clipped.at
        assert whole.outcome != clipped.outcome


class TestOneLoginReadTwiceIsOneRow:
    """The invariant that matters: however the window falls, one login is one row.

    Cycle 1 reads the whole attempt. Cycle 2's window is made to open between the bind error and its
    verdict — the state the sweeping `watermark − OVERLAP_SECONDS` boundary reaches on its own — by
    setting the watermark that decides `since_seconds`, so the loop's real arithmetic does the slicing.

    THE GAP IS WIDENED HERE, to 0.5 s from the measured 1.167 ms, and only here. `since_seconds` is a
    whole number, so the boundary's position inside its second is fixed by the instant of the call:
    against a 1.167 ms gap the assertion would turn on milliseconds of scheduler noise. 0.5 s is still
    one attempt — ATTEMPT_WINDOW is a full second — and a directory that takes that long to answer a
    bind is ordinary. The measured width is asserted where it can be, in the parse-only tests above
    and in TestTheClipIsReachable.
    """

    # Chosen so `int(age) + OVERLAP_SECONDS` lands on a known integer, below.
    WINDOW = 94
    HALF_GAP = 0.25

    def _straddling_lines(self, t0: datetime) -> list[str]:
        """One attempt whose bind and verdict sit either side of `t0 - WINDOW`."""
        begins = t0 - timedelta(seconds=self.WINDOW + self.HALF_GAP + BIND_OFFSET)
        lines = _attempt_lines(begins)
        # Push the verdict to the far side of the boundary; the first three lines stay before it.
        verdict_at = t0 - timedelta(seconds=self.WINDOW - self.HALF_GAP)
        lines[3] = f"{_stamp(verdict_at)} {_VERDICT}"
        return lines

    def test_a_window_that_clips_the_cause_does_not_add_a_second_row(
            self, store, settings, install):
        t0 = datetime.now(UTC)
        lines = self._straddling_lines(t0)

        first = install(WindowedClient(lines))
        assert capture_once(store, CLUSTER, settings) == 1
        assert first.windows == [FIRST_SIGHT_SECONDS]
        assert first.returned == [4], "cycle 1 must see the whole attempt"
        rows = store.login_events(CLUSTER.name)
        assert [(r["user_name"], r["outcome"]) for r in rows] == [("jane.smith", "bad_password")], rows

        # Put the watermark where a steady-state cycle would have it, so the loop computes
        # since_seconds = int(age) + OVERLAP_SECONDS = 34 + 60 = WINDOW, opening the window inside
        # the gap. set_login_watermark takes max(), and this instant is newer than cycle 1's.
        store.set_login_watermark(
            CLUSTER.name, POD, _stamp(t0 - timedelta(seconds=34.5)), now_iso())

        second = install(WindowedClient(lines))
        capture_once(store, CLUSTER, settings)
        assert second.windows == [self.WINDOW], (
            f"the watermark did not produce the intended window: {second.windows}"
        )
        assert second.returned == [1], (
            "the window did not clip between the cause and the verdict, so this test proves nothing "
            f"— it returned {second.returned[0]} lines instead of the verdict alone"
        )

        rows = store.login_events(CLUSTER.name)
        assert len(rows) == 1, (
            "one login produced two rows: the same person is reported both as a wrong password and "
            f"as an unexplained failure — {[(r['user_name'], r['outcome'], r['at']) for r in rows]}"
        )
        assert rows[0]["outcome"] == "bad_password", (
            "the surviving row is the one with no reason; a later, worse-informed read displaced the "
            "diagnosis"
        )

    def test_a_log_that_never_contained_the_cause_still_records_the_failure(
            self, store, settings, install):
        """A pod whose log begins after the bind has no better information anywhere.

        Recording the verdict alone is right here, and asserting it is what stops the guard above from
        being implemented as "drop anything without a cause".
        """
        begins = datetime.now(UTC) - timedelta(seconds=95)
        install(WindowedClient(_attempt_lines(begins)[3:]))
        assert capture_once(store, CLUSTER, settings) == 1
        rows = store.login_events(CLUSTER.name)
        assert [(r["user_name"], r["outcome"]) for r in rows] == [("jane.smith", "failed")], rows


class TestTheClipIsReachable:
    """Whether the loop's own window arithmetic can put a boundary inside that 1.167 ms gap.

    If it could not, the row above would be unreachable in production and this would be a curiosity
    rather than a defect. `since_seconds` is whole seconds, which is the reason to check: a boundary
    quantised to a whole second could never land between two lines that share one.
    """

    def test_the_boundary_carries_the_request_instant_s_sub_second_phase(self):
        """`since_seconds` is coarse; `now − since_seconds` is not.

        The kubelet resolves sinceSeconds against the request's own instant, so the boundary inherits
        that instant's fractional part and can fall anywhere inside a second.
        """
        boundaries = set()
        for micros in (0, 250_000, 500_000, 883_500, 999_999):
            now = datetime(2026, 8, 8, 0, 4, 21, micros, tzinfo=UTC)
            boundaries.add((now - timedelta(seconds=95)).microsecond)
        assert len(boundaries) == 5, (
            "a whole-second sinceSeconds still yields sub-second boundaries; if these collapsed to "
            "one value the clip would be unreachable"
        )

    def test_the_sweeping_boundary_passes_through_the_gap(self):
        """The read window's start is `watermark − OVERLAP_SECONDS`, and the watermark advances every
        cycle, so the boundary sweeps forward through log time and crosses every instant — including
        the 1.167 ms between a cause and its verdict."""
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        bind = begins + timedelta(seconds=BIND_OFFSET)
        verdict = begins + timedelta(seconds=VERDICT_OFFSET)

        # A watermark that lands the boundary inside the gap: any settled line at bind + overlap.
        watermark = bind + timedelta(seconds=OVERLAP_SECONDS, microseconds=500)
        now = watermark + timedelta(seconds=SETTLE_SECONDS)
        since = max(OVERLAP_SECONDS, int((now - watermark).total_seconds()) + OVERLAP_SECONDS)
        boundary = now - timedelta(seconds=since)
        assert bind < boundary < verdict, (
            f"boundary {boundary.isoformat()} did not land in the gap "
            f"({bind.isoformat()}, {verdict.isoformat()})"
        )

    def test_the_settle_rules_do_not_withhold_the_clipped_attempt(self):
        """`_recordable` is what could have saved this, and does not: it withholds attempts younger
        than SETTLE_SECONDS + ATTEMPT_WINDOW, and by the time the boundary has swept far enough to
        clip a cause, the attempt is a minute older than that."""
        begins = datetime.now(UTC) - timedelta(seconds=95)
        verdict_only = parse(_attempt_lines(begins)[3:])
        assert logincapture._recordable(verdict_only) == verdict_only, (
            "an attempt this old is recordable, so nothing holds the clipped read back"
        )
        cutoff = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS) - ATTEMPT_WINDOW
        assert verdict_only[0].at <= cutoff
