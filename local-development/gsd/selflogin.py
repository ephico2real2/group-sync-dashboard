"""`userSelfLogin`: the session is the credential, and it renews or it stops (#285, SPEC_S4c §3.6).

A `self-login` cluster stores no token. Before each poll its thread asks `credential_for(cluster)` and gets the
cluster as it polls — the session's token substituted as `token_value`, the substitution `read_sa_token` already
uses, so the token is redacted from every line like any other credential — or None: no session this cycle, and
the poll is skipped rather than failed. After the poll it reports what the poll answered to `poll_answered`.

THE SCHEDULE IS THE SESSION'S OWN (SPEC_S4 §3.1, the business owner's ruling): renew at
`expires_at − min(2 h, ¼ × expires_in)`, from the `expires_in` the target put in the fragment — RFC 6749 §4.2.2,
"the lifetime in seconds of the access token" — never a percentage and never a fixed clock. A one-hour session
renews after 45 minutes; CRC's year renews two hours before it ends. Checked once per poll cycle, on the
cluster's own thread. The new session is entered before the old one exits, so the poll never runs without a
credential and the superseded token is revoked after its replacement exists.

EVERY LOGIN FOLLOWS THE ACCOUNT LEASE'S PROTOCOL (SPEC_S4c §3.3): claim, the gate, the bind, a bound answer
recorded on the Lease before the process's gate, release. ONE attempt per cycle: the poll interval is the retry
(SPEC_S3 §9.3.1), and #283's five-attempt policy inside every cycle would write five `fleet-login-failed` lines
a minute for a target that is down.

THE 401 RULE, reconciled with #283's revoke-side reading. A poll answered 401 BEFORE `expires_at` means the session
was invalidated by something the fragment does not carry — an inactivity timeout, an administrator's `oc delete
oauthaccesstoken`, a changed policy — so the next cycle logs in once more, and nothing is recorded as a refusal
because nothing evaluated the password. If the fresh session's first poll answers 401 too, the API server is
refusing sessions it just issued: the cluster is suspended rather than logged in again every cycle (B4). On the
revoke path a 401 keeps #283's reading: "not proven gone".

SUSPENSION (SPEC_S3 §9.3 rule 1). A bound answer on any acquisition gates the (account, password) and stops EVERY
self-login cluster on the account at once — its session revoked, the cluster parked, a standing finding, its poll
outcome recorded once — in one `fleet-credential-suspended` line that names what stopped and how many. So does an
entry any other path or replica wrote (#419, D3): the poller's account sweep observes it each discovery cadence and
calls `suspend_account`. A parked cluster re-reads the password each cycle at no cost to the directory and resumes
when it, the account or the cluster's URL changes.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import event, failure, redact
from .clusterconfig.parser import Finding
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig
from .fleetlogin import FleetLogin, FleetSession, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, fleet_account, fleet_password
from .fleetstate import ClaimHeld, FleetLease, FleetStateUnavailable, claim_seconds, lease_digest, lease_name, stamp
from .kube import AUTH_FAILED, OK, UNREACHABLE

log = logging.getLogger(__name__)

#: One login attempt per poll cycle: the poll interval is the retry (SPEC_S3 §9.3.1).
ONE_ATTEMPT = RetryPolicy(attempts=1)
#: The margin's ceiling (SPEC_S4 §3.1): two hours before the session ends, or a quarter of a shorter lifetime.
MARGIN = timedelta(hours=2)
#: The registry slot this module's standing findings live in.
SLOT = "self-login"
EVENTS = ("self-login-renewed", "self-login-failed", "fleet-credential-suspended")


def _evaluated(target: str, account: str, entry: dict | None) -> str:
    """What gates this password, said as what is known: a reservation left by an attempt that never recorded its
    answer (#419, D1) MAY have been evaluated; a refusal was."""
    said = "may have evaluated" if (entry or {}).get("uncertain") else "evaluated"
    return f"{_without_userinfo(target) or 'another target'} {said} this password for {account} already and it has not changed"


def renew_at(session: FleetSession) -> datetime:
    """`expires_at − min(2 h, ¼ × expires_in)` (SPEC_S4 §3.1): a fixed margin, a retry budget, not a fraction."""
    return session.expires_at - min(MARGIN, timedelta(seconds=session.expires_in / 4))


@dataclass
class _Session:
    login: FleetLogin                     # entered; its __exit__ is the revoke
    session: FleetSession
    account: str
    key: tuple                            # (account, the password's sha256 prefix, the cluster's URL) at login
    renew_at: datetime
    reauth: bool = False                  # a poll answered 401 before expires_at: log in again next cycle
    reauth_logins: int = 0                # B4: a re-authenticated session whose first poll 401s again is suspended


class SelfLoginSessions:
    """The poller's self-login sessions: one lock, a dict, replace and read — the ClusterRegistry shape. It reads
    the poller it belongs to (its settings, store, gate, signals and host client) each time, never a copy."""

    def __init__(self, poller, *, clock=None):
        self._poller = poller
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._parked: dict[str, tuple] = {}

    # ── the poll thread's two calls ───────────────────────────────────────────────────────────

    def credential_for(self, cluster: ClusterConfig) -> ClusterConfig | None:
        """The cluster as it polls — this cycle's session token substituted — or None when there is no session."""
        now = self._clock()
        with self._lock:
            held = self._sessions.get(cluster.name)
        if held is not None and now < held.renew_at and not held.reauth:
            return self._as(cluster, held)                      # the steady state: one comparison a cycle
        if held is not None and now >= held.session.expires_at:
            self._end(cluster.name, "the session reached expires_at with no replacement; the next cycle logs in again",
                      outcome="expired")
            held = None
        # What the poll keeps while a renewal waits: the current session, unless a 401 already invalidated it.
        live = self._as(cluster, held) if held is not None and not held.reauth else None
        poller = self._poller
        if poller.elector is None and poller.settings.replica_count > 1:
            # The render refuses userSelfLogin above one replica; a Secret-declared one is refused here (§3.8).
            self._finding(cluster.name, "self-login-suspended", f"{cluster.name} declares userSelfLogin on a release of "
                          f"{poller.settings.replica_count} replicas without leader election: every replica would log in "
                          f"as the fleet account — run one replica for a release that declares userSelfLogin")
            return None
        host = poller._host_client()
        if host is None:
            self._finding(cluster.name, "fleet-state-unavailable", "no host cluster or namespace: the fleet account's "
                          "Lease has nowhere to live, so no login is made — check the pod's ServiceAccount mount")
            return live
        client, namespace = host
        try:
            account = fleet_account(poller.settings, cluster)
            password, salt = fleet_password(client, poller.settings, namespace)
        except LookupRefused as exc:
            self._finding(cluster.name, exc.code, f"{exc.detail} — {exc.action}")
            return live
        key = (account, CredentialGate._digest(password), cluster.api_url)
        with self._lock:
            parked = self._parked.get(cluster.name)
            if parked is not None and parked != key:
                del self._parked[cluster.name]          # the password, the account or the URL moved: try again
        if parked == key:
            return None
        fresh = self._acquire(cluster, client, namespace, account, password, salt, key, held)
        if fresh is not None:
            return fresh
        with self._lock:                                  # a suspension may have ended the session meanwhile
            held = self._sessions.get(cluster.name)
        return self._as(cluster, held) if held is not None and not held.reauth else None

    def poll_answered(self, cluster: ClusterConfig, outcome: str) -> None:
        """What the poll with the session answered: a 401 before expires_at re-authenticates once (the 401 rule)."""
        now = self._clock()
        with self._lock:
            held = self._sessions.get(cluster.name)
            if held is not None and outcome == OK:
                held.reauth_logins = 0
        if held is None or outcome != AUTH_FAILED:
            return
        if now >= held.session.expires_at:
            self._end(cluster.name, "the session expired before it was renewed — the schedule failed; the next cycle "
                      "logs in again", outcome="expired")
            return
        if held.reauth_logins:
            with self._lock:
                self._parked[cluster.name] = held.key
            self._end(cluster.name, "the API server refused a session it had just issued, twice in one episode: not "
                      "logged in again until the password, the account or the cluster's URL changes, or the pod restarts",
                      outcome="self-login-suspended", finding=True)
            return
        with self._lock:
            held.reauth = True
        event(log, logging.INFO, "self-login-failed", phase="poll", outcome=AUTH_FAILED, cluster=cluster.name,
              account=held.account, expires_at=held.session.expires_at_iso, reauth="next-cycle",
              action="the session was invalidated before it expired (an inactivity timeout or a revoke): one login on "
                     "the next cycle; nothing is recorded as a refusal")

    def suspend_account(self, account: str, password: str, entry: dict) -> None:
        """An entry on the account's Lease for this password, whichever path or replica wrote it, stops every
        self-login cluster on the account now — not at its renewal (SPEC_S4c §3.6; #419, D3). Idempotent: when every
        one is parked on this password already, nothing is said, so the sweep that calls this each cadence says it
        once."""
        poller, digest = self._poller, CredentialGate._digest(password)
        clusters = [c for c in poller.settings.effective_clusters() if c.enabled and c.credential_kind == CREDENTIAL_SELF_LOGIN
                    and (c.ldap_connection_bootstrap or poller.settings.fleet_account_username) == account]
        with self._lock:
            live = [c for c in clusters if self._parked.get(c.name) != (account, digest, c.api_url)]
        if live:
            target = entry.get("target") or ""
            self._suspend(live[0], account, (account, digest, live[0].api_url), code=entry.get("code") or "login-refused",
                          target=target, detail=_evaluated(target, account, entry), secrets=(password,))

    def stop(self, name: str) -> None:
        """Exit (revoke) the cluster's session: it was disabled, retired, or its thread is stopping."""
        with self._lock:
            self._parked.pop(name, None)
        self._end(name, None)
        self._finding(name, None)
        if self._poller.signals is not None:
            self._poller.signals.note_self_login(name, None)

    def view(self, name: str) -> dict:
        """The API's `session` block: instants only, as the tab shows them."""
        with self._lock:
            held, parked = self._sessions.get(name), name in self._parked
        if held is None:
            return {"state": "suspended" if parked else "none", "expires_at": None, "renew_at": None}
        return {"state": "renewing" if held.reauth or self._clock() >= held.renew_at else "current",
                "expires_at": held.session.expires_at_iso, "renew_at": stamp(held.renew_at)}

    # ── the login ─────────────────────────────────────────────────────────────────────────────

    def _acquire(self, cluster, client, namespace, account, password, salt, key, held) -> ClusterConfig | None:
        poller = self._poller
        lease = FleetLease(client, namespace, account, claim_seconds=claim_seconds(poller.settings), clock=self._clock)
        try:
            lease.claim()
        except ClaimHeld:
            return None                                  # another holder binds as this account now: the next cycle
        except FleetStateUnavailable as exc:
            self._finding(cluster.name, exc.code, f"{exc.detail} — {exc.action}")
            return None
        acquired: tuple[FleetLogin, FleetSession] | None = None
        try:
            digest = lease_digest(account, password, salt)
            entry = lease.record.gated(digest)
            if entry is not None:
                poller._credential_gate.refuse(entry.get("target") or "", account, password)
            # The account's refusal alone: #293's per-target SPENT mark is not a self-login refusal (#419, F2).
            answered = poller._credential_gate.account_refusal(account, password)
            with self._lock:      # every session this process holds: the remote may echo any of them (#419, D4)
                carried = tuple(s.session.token for s in self._sessions.values())
            if answered is not None:
                self._suspend(cluster, account, key, code=(entry or {}).get("code") or "login-refused", target=answered,
                              detail=_evaluated(answered, account, entry), secrets=(password, *carried))
                return None
            try:
                lease.reserve(CredentialGate._target(cluster.api_url), digest)   # before the wire (SPEC_S4c §3.3, step 3)
            except ClaimHeld:
                return None                              # taken meanwhile: this attempt is abandoned, the next cycle
            except FleetStateUnavailable as exc:
                self._finding(cluster.name, exc.code, f"{exc.detail} — {exc.action}")
                return None
            login = FleetLogin(cluster, account, password, timeout=poller.settings.request_timeout_seconds,
                               policy=ONE_ATTEMPT, clock=self._clock, secrets=carried)
            try:
                acquired = login, login.__enter__()
                lease.complete()                         # a session came back: the attempt's entry goes
            except LoginError as exc:
                if not exc.bound:
                    # Before the password was written: nothing bound, the current session (if any) keeps polling.
                    lease.complete()
                    if held is None:
                        poller.store.record_poll(cluster.name, UNREACHABLE, f"self-login: {exc.message}")
                    return None
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                # The Lease first, the process second (SPEC_S4c §3.3, step 5), then the finding.
                lease.refuse(CredentialGate._target(cluster.api_url), digest, code)
                poller._credential_gate.refuse(cluster.api_url, account, password)
                self._suspend(cluster, account, key, code=code, target=cluster.api_url,
                              detail=f"phase={exc.phase}: {exc.message}", secrets=(password, *carried))
                return None
        finally:
            lease.release()
        login, session = acquired
        floor = 4 * poller.settings.poll_interval_seconds
        if session.expires_in <= floor:
            self._exit(login)
            with self._lock:
                self._parked[cluster.name] = key
            detail = (f"{cluster.name} states a session of {session.expires_in}s, and one renewed a margin before expiry on a "
                      f"{poller.settings.poll_interval_seconds}s poll cycle needs more than {floor}s: raise "
                      f"accessTokenMaxAgeSeconds on the target, or declare saTokenLookup")
            self._finding(cluster.name, "self-login-lifetime-too-short", detail)
            failure(log, "self-login-failed", phase="credential", outcome="self-login-lifetime-too-short",
                    cluster=cluster.name, account=account, gave_up="true", action=detail, secrets=(password,))
            self._note(cluster.name)
            return None
        fresh = _Session(login, session, account, key, renew_at(session),
                         reauth_logins=held.reauth_logins + 1 if held is not None and held.reauth else 0)
        with self._lock:
            # The sweep can park this credential while its authorize is in flight. The parked
            # check and installation share the suspension's lock: a late success must not
            # resurrect a session after the process has gated it (round 3, #419).
            parked = self._parked.get(cluster.name) == key
            old = self._sessions.get(cluster.name)
            if not parked:
                self._sessions[cluster.name] = fresh
        if parked:
            self._exit(login)                         # the late token was minted, so revoke it once
            return None                              # keep the suspension and its standing finding
        if old is not None:
            self._exit(old.login)                        # the superseded token, revoked after its replacement exists
            event(log, logging.INFO, "self-login-renewed", cluster=cluster.name, account=account,
                  expires_at=session.expires_at_iso, renew_at=stamp(fresh.renew_at),
                  reauth="true" if fresh.reauth_logins else None, secrets=(password, session.token))
        self._finding(cluster.name, None)
        self._note(cluster.name)
        return self._as(cluster, fresh)

    def _suspend(self, cluster: ClusterConfig, account: str, key: tuple, *, code: str, target: str, detail: str,
                 secrets: tuple[str, ...]) -> None:
        """Every self-login cluster on the account, stopped at once, and one line that says what stopped."""
        poller = self._poller
        stanzas = {c.name: c for c in poller.settings.effective_clusters()
                   if c.enabled and c.credential_kind == CREDENTIAL_SELF_LOGIN
                   and (c.ldap_connection_bootstrap or poller.settings.fleet_account_username) == account}
        stanzas.setdefault(cluster.name, cluster)
        names = sorted(stanzas)
        with self._lock:
            stopped = [self._sessions.pop(name) for name in names if name in self._sessions]
            for name in names:
                self._parked[name] = (account, key[1], stanzas[name].api_url)
        # Every value in play leaves the line AND the standing finding the API serves (#419, D4): the password, and each
        # session being stopped (a remote may echo one).
        secrets = (*secrets, *(held.session.token for held in stopped))
        detail = redact(detail, secrets)
        for held in stopped:
            self._exit(held.login, *secrets)             # the whole batch: each was popped before any revoke
        action = (f"every self-login cluster on {account} stopped polling: rotate the fleet password Secret or correct "
                  f"ldapConnectionBootstrap, or check the account is not locked; the gate on Lease {lease_name(account)} "
                  f"re-arms when the password changes")
        for name in names:
            # `auth_failed` for a refusal — the password WAS presented and refused, and the card goes critical —
            # `unreachable` with the code for any other bound answer. Once: a parked cluster does not poll.
            poller.store.record_poll(name, AUTH_FAILED if code == "login-refused" else UNREACHABLE,
                                     f"{code}: the self-login credential for {account} is suspended")
            self._finding(name, "self-login-suspended", f"{detail} — {action}")
            self._note(name)
        failure(log, "fleet-credential-suspended", phase="credential", outcome=code, account=account, suspended=account,
                scope="self-login", stopped=len(names), clusters=",".join(names),
                target=_without_userinfo(target) or "the answering target", action=action, detail=detail, secrets=secrets)

    # ── the bookkeeping ───────────────────────────────────────────────────────────────────────

    def _exit(self, login: FleetLogin, *secrets: str) -> None:
        """Revoke a session, scrubbed of `secrets` and of every token held now, a replacement's too (#419, round 2)."""
        with self._lock:
            held = tuple(s.session.token for s in self._sessions.values())
        login.add_secrets(*secrets, *held)
        login.__exit__(None, None, None)

    def _end(self, name: str, why: str | None, *, outcome: str | None = None, finding: bool = False) -> None:
        with self._lock:
            held = self._sessions.pop(name, None)
        if held is None:
            return
        self._exit(held.login)
        if why is not None:
            failure(log, "self-login-failed", phase="credential", outcome=outcome, cluster=name, account=held.account,
                    expires_at=held.session.expires_at_iso, gave_up="true" if finding else None, action=why)
        if finding:
            self._finding(name, outcome, why)
        self._note(name)

    def _finding(self, name: str, code: str | None, detail: str | None = None) -> None:
        self._poller.settings.cluster_registry.set_standing_finding(SLOT, name, Finding(name, code, detail) if code else None)

    def _note(self, name: str) -> None:
        if self._poller.signals is not None:
            self._poller.signals.note_self_login(name, self.view(name))

    @staticmethod
    def _as(cluster: ClusterConfig, held: _Session) -> ClusterConfig:
        return dataclasses.replace(cluster, token_value=held.session.token, user_self_login=False,
                                   ldap_connection_bootstrap=None)


__all__ = ["EVENTS", "MARGIN", "ONE_ATTEMPT", "SLOT", "SelfLoginSessions", "renew_at"]
